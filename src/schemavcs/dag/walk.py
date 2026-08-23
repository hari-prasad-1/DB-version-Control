"""DAG traversal: ancestors, merge-base, replay, operations-since.

merge_base finds the lowest common ancestor over full ancestor sets, not just
the first shared parent, so it also gets the "branch forked early, other
side advanced past that point via unrelated merges" case right. When the two
revisions have more than one maximal common ancestor at once (a criss-cross
merge — two merge nodes built in opposite directions from the same pair of
pre-merge heads), there is no single correct answer to pick from, so it
raises rather than silently choosing one side and dropping the other's
unique operations.
"""

from schemavcs.dag.errors import AmbiguousMergeBaseError
from schemavcs.dag.store import DagStore
from schemavcs.model import CompoundOperation, RevisionId, Snapshot


def ancestors(store: DagStore, revision_id: RevisionId) -> set[RevisionId]:
    """All revisions reachable by walking parent pointers, including
    revision_id itself. Cached per store instance since a node's ancestors
    never change once computed (nodes are immutable after append)."""
    cached = store.cached_ancestors(revision_id)
    if cached is not None:
        return cached

    seen: set[RevisionId] = set()
    frontier = [revision_id]
    while frontier:
        rev = frontier.pop()
        if rev in seen:
            continue
        seen.add(rev)
        frontier.extend(store.get_node(rev).parents)

    store.cache_ancestors(revision_id, seen)
    return seen


def merge_base(store: DagStore, rev_a: RevisionId, rev_b: RevisionId) -> RevisionId:
    if rev_a == rev_b:
        return rev_a

    ancestors_a = ancestors(store, rev_a)
    ancestors_b = ancestors(store, rev_b)
    common = ancestors_a & ancestors_b
    if not common:
        raise AmbiguousMergeBaseError(rev_a, rev_b, [])

    # Maximal elements of `common`: those with no other member of `common`
    # reachable as one of their descendants within the set.
    maximal = {
        candidate
        for candidate in common
        if not any(other != candidate and candidate in ancestors(store, other) for other in common)
    }
    if len(maximal) > 1:
        raise AmbiguousMergeBaseError(rev_a, rev_b, sorted(maximal))
    return next(iter(maximal))


def operations_since(
    store: DagStore, from_rev: RevisionId, to_rev: RevisionId
) -> tuple[CompoundOperation, ...]:
    """Operations on the path from `from_rev` (exclusive) to `to_rev`
    (inclusive), requiring `from_rev` to be an ancestor of `to_rev`. Sums each
    node's own stored operations rather than recomputing anything, so
    operations already folded into an earlier merge node are never
    re-derived or re-conflicted.

    At a merge node, follows whichever parent actually descends from
    `from_rev`; if both do (from_rev predates the fork on both sides), either
    is a valid path back and the first parent is used."""
    if from_rev == to_rev:
        return ()

    path: list[RevisionId] = []
    rev = to_rev
    while rev != from_rev:
        path.append(rev)
        node = store.get_node(rev)
        if not node.parents:
            raise ValueError(f"{from_rev!r} is not an ancestor of {to_rev!r}")
        candidates = [p for p in node.parents if p == from_rev or from_rev in ancestors(store, p)]
        if not candidates:
            raise ValueError(f"{from_rev!r} is not an ancestor of {to_rev!r}")
        rev = candidates[0]
    path.reverse()

    ops: list[CompoundOperation] = []
    for rev_id in path:
        ops.extend(store.get_node(rev_id).operations)
    return tuple(ops)


def replay(store: DagStore, revision_id: RevisionId, branch: str) -> Snapshot:
    """Reconstruct schema state at revision_id by applying every ancestor's
    operations exactly once, in a parent-before-child (topological) order —
    correct for merge nodes, where both parents' history must be applied,
    not just the first one."""
    ordered = _topological_order(store, revision_id)

    tables_by_id: dict = {}
    for rev_id in ordered:
        for compound in store.get_node(rev_id).operations:
            _apply_compound(tables_by_id, compound)

    return Snapshot(branch=branch, revision_id=revision_id, tables=list(tables_by_id.values()))


def _topological_order(store: DagStore, revision_id: RevisionId) -> list[RevisionId]:
    all_revs = ancestors(store, revision_id)
    visited: set[RevisionId] = set()
    order: list[RevisionId] = []

    def visit(rev: RevisionId) -> None:
        if rev in visited:
            return
        visited.add(rev)
        for parent in store.get_node(rev).parents:
            visit(parent)
        order.append(rev)

    for rev in all_revs:
        visit(rev)
    return order


def _apply_compound(tables_by_id: dict, compound: CompoundOperation) -> None:
    from schemavcs.dag.apply import apply_operation

    for op in compound.operations:
        apply_operation(tables_by_id, op)


def is_fast_forward(store: DagStore, base_rev: RevisionId, source_head: RevisionId) -> bool:
    """True when `source_head` contributed nothing beyond `base_rev` — i.e.
    the merge base equals source_head itself, so merging just needs to move
    the target branch's pointer forward rather than build a real merge node."""
    return base_rev == source_head
