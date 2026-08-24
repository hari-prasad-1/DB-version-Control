"""Human-confirmation guardrail for merge conflicts.

Structural, not conventions-based: `commit_resolution` is the only function
that finalizes a CONFLICT/PARTIAL_CONFLICT group, and it accepts nothing but
a real `HumanConfirmationToken`. The only way to construct one is
`confirm_from_cli`, which blocks on real terminal input. Auto-resolve tiers
(IDENTICAL/COMMUTING/ORDER_IRRELEVANT) skip this module entirely -- they
never carry risk of a silent wrong merge, so they resolve directly in the
merge engine without a token.

This module must never be imported by `schemavcs.llm` -- enforced by
tests/unit/test_module_boundaries.py, not just this docstring.
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from schemavcs.merge.classify import Classification, ClassifiedGroup
from schemavcs.model import (
    AddColumn,
    AddConstraint,
    AddIndex,
    DropColumn,
    DropConstraint,
    DropIndex,
    Operation,
)


@dataclass(frozen=True)
class HumanConfirmationToken:
    group_id: UUID
    chosen_resolution: tuple[Operation, ...]
    _nonce: UUID


class TokenAlreadyUsedError(Exception):
    pass


def _corrective_drop_for(op: Operation) -> Operation:
    """The dependent-object drop needed when a cross-object conflict
    resolves toward keeping the drop that caused it. Undoing the drop
    itself isn't offered (see ClassifiedGroup.cross_object_referencing_op)
    -- resurrecting a dropped table/column from nothing isn't something
    this tool can do, so the referencing op's own object must go instead."""
    match op:
        case AddColumn(column=column):
            return DropColumn(table_id=op.table_id, column_id=column.id)
        case AddIndex(index=index):
            return DropIndex(index_id=index.id)
        case AddConstraint(constraint=constraint):
            return DropConstraint(constraint_id=constraint.id)
        case _:
            raise TypeError(f"no corrective drop defined for {type(op).__name__}")


def confirm_from_cli(group: ClassifiedGroup) -> HumanConfirmationToken:
    """Blocks on real terminal input. The only producer of a valid token."""
    if group.cross_object_referencing_op is not None:
        print(f"Conflict on identity {group.group.identity_id}: {group.reason}")
        input(
            "The dropped table/column wins; the dependent object above will "
            "also be dropped. Press enter to acknowledge. "
        )
        chosen = (_corrective_drop_for(group.cross_object_referencing_op),)
        return HumanConfirmationToken(
            group_id=group.group.identity_id, chosen_resolution=chosen, _nonce=uuid4()
        )

    print(f"Conflict on identity {group.group.identity_id}: {group.reason}")
    if group.single_valued_field:
        # A single-valued field (a type, a nullability flag, a name) can
        # only ever hold one value -- "keep both" has no meaningful result
        # here, so it's not offered at all, rather than silently doing
        # "whichever op replays last wins" behind a choice that implies an
        # actual merge happened.
        chosen_side = input("Keep [a]/[b]? ").strip().lower()
        chosen = tuple(group.group.ops_b) if chosen_side == "b" else tuple(group.group.ops_a)
    else:
        chosen_side = input("Keep [a]/[b]/[both]? ").strip().lower()
        if chosen_side == "a":
            chosen = tuple(group.group.ops_a)
        elif chosen_side == "b":
            chosen = tuple(group.group.ops_b)
        else:
            chosen = tuple(group.group.ops_a) + tuple(group.group.ops_b)
    return HumanConfirmationToken(
        group_id=group.group.identity_id, chosen_resolution=chosen, _nonce=uuid4()
    )


class ResolutionEngine:
    """Three-tier resolution: auto-resolve safe classifications, require a
    token for anything conflicting. Tracks spent tokens so a token can't be
    replayed against a different (or the same) group."""

    def __init__(self) -> None:
        self._spent_nonces: set[UUID] = set()

    def auto_resolve(self, group: ClassifiedGroup) -> tuple[Operation, ...] | None:
        """Returns the operations the MERGE NODE ITSELF must (re-)store for
        classifications safe to commit without a human, or None if this
        group needs `commit_resolution`.

        UNRELATED/IDENTICAL contribute nothing here -- the operation is
        already present in at least one parent's own ancestor chain, and
        replay()/emit_ddl() walk BOTH parents, so it's already reachable.
        Re-storing it in the merge node would apply it a second time --
        harmless for in-memory STATE (a mutation is idempotent to
        re-apply), but wrong for DDL TEXT: emit_ddl prints one SQL line per
        operation *instance* it walks, so a re-stored op that's already
        reachable through its own branch's ancestor chain would print as
        duplicate, nonsensical SQL, even though nothing is wrong with the
        resulting schema state.

        COMMUTING/ORDER_IRRELEVANT pair up two DIFFERENT mutation-type ops
        on one pre-existing identity (never a create/drop -- classify.py
        routes those to CONFLICT or IDENTICAL instead). Both `ops_a` (the
        target branch's own history) and `ops_b` (the source branch's own
        history) are already reachable through the merge node's two
        parent chains -- the merge node is exactly what makes both
        reachable at once. Nothing needs to be re-stored here, same as
        IDENTICAL/UNRELATED above."""
        if group.classification in (
            Classification.IDENTICAL,
            Classification.UNRELATED,
            Classification.COMMUTING,
            Classification.ORDER_IRRELEVANT,
        ):
            return ()
        return None

    def commit_resolution(
        self, group: ClassifiedGroup, token: HumanConfirmationToken
    ) -> tuple[Operation, ...]:
        if not isinstance(token, HumanConfirmationToken):
            raise TypeError("commit_resolution requires a real HumanConfirmationToken")
        if token.group_id != group.group.identity_id:
            raise ValueError("token was not issued for this group")
        if token._nonce in self._spent_nonces:
            raise TokenAlreadyUsedError("token has already been used to commit a resolution")
        self._spent_nonces.add(token._nonce)
        return token.chosen_resolution
