"""Orchestrates a full three-way merge: finds the common ancestor, classifies
every touched identity, runs the cross-object pass, resolves each group
(auto where safe, human-confirmed otherwise), and commits the result as a
merge Migration node.

Merge is asymmetric, like Git: only `target_branch`'s head advances. Fast
forward and self-merge are handled as explicit special cases rather than
falling through into a real merge node with nothing to contribute.
"""

from collections.abc import Callable
from dataclasses import dataclass

from schemavcs.dag.errors import NothingToMergeError
from schemavcs.dag.revision_id import make_revision_id
from schemavcs.dag.store import DagStore
from schemavcs.dag.walk import is_fast_forward, merge_base, operations_since, replay
from schemavcs.merge.classify import ClassifiedGroup, classify
from schemavcs.merge.cross_object import cross_object_pass
from schemavcs.merge.grouping import group_by_identity
from schemavcs.merge.resolve import HumanConfirmationToken, ResolutionEngine, confirm_from_cli
from schemavcs.model import CompoundOperation, Migration, Operation

ConfirmFn = Callable[[ClassifiedGroup], HumanConfirmationToken]


@dataclass
class MergeResult:
    migration: Migration
    fast_forward: bool
    conflicts_resolved: int


def merge(
    store: DagStore,
    target_branch: str,
    source_branch: str,
    confirm: ConfirmFn = confirm_from_cli,
) -> MergeResult:
    """Merges `source_branch` into `target_branch`. `confirm` is called once
    per CONFLICT/PARTIAL_CONFLICT group to obtain a HumanConfirmationToken --
    defaults to blocking on a real terminal, but tests pass a scripted stub."""
    target_head = store.head(target_branch)
    source_head = store.head(source_branch)

    if target_head == source_head:
        raise NothingToMergeError(target_head, source_head)

    base = merge_base(store, target_head, source_head)

    if is_fast_forward(store, base_rev=base, source_head=source_head):
        # source_head is already an ancestor of target -- nothing to bring in.
        raise NothingToMergeError(target_head, source_head)

    if is_fast_forward(store, base_rev=base, source_head=target_head):
        store.set_head(target_branch, source_head)
        return MergeResult(
            migration=store.get_node(source_head), fast_forward=True, conflicts_resolved=0
        )

    ops_a = operations_since(store, base, target_head)
    ops_b = operations_since(store, base, source_head)

    classified = [classify(g) for g in group_by_identity(ops_a, ops_b)]
    snapshot_ancestor = replay(store, base, branch="__merge_base__")
    classified = cross_object_pass(classified, ops_a, ops_b, snapshot_ancestor)

    engine = ResolutionEngine()
    resolved_ops: list[Operation] = []
    conflicts_resolved = 0

    for group in classified:
        auto = engine.auto_resolve(group)
        if auto is not None:
            resolved_ops.extend(auto)
            continue
        token = confirm(group)
        resolved_ops.extend(engine.commit_resolution(group, token))
        conflicts_resolved += 1

    merged_compound = (CompoundOperation(operations=tuple(resolved_ops)),) if resolved_ops else ()
    revision_id = make_revision_id((target_head, source_head), merged_compound)
    migration = store.append(
        revision_id=revision_id,
        branch=target_branch,
        parents=(target_head, source_head),
        operations=merged_compound,
    )
    return MergeResult(
        migration=migration, fast_forward=False, conflicts_resolved=conflicts_resolved
    )
