"""Catches conflicts where two operations touch different identity ids, but
one branch destroyed something the other branch's operation still
references.

Per-identity classification (classify.py) groups by a single id — it never
sees a DropTable(t) paired against an AddColumn(table_id=t) on the other
branch, because those two operations are keyed by different ids (t's own id
vs. the new column's id). This pass exists solely to catch that shape of
conflict, checked symmetrically in both directions since either branch
could be the one that dropped something.

Scoped deliberately to table-drop and column-drop vs. a referencing object
added elsewhere — not the general cross-object conflict space. Two branches
adding different, non-overlapping FK constraints to the same table, CHECK
constraint expression interactions, and index/constraint enforcement
coupling are all out of scope: none of them are "something got destroyed,
something else still depends on it" failures, and none of them produce
invalid DDL if left undetected.
"""

from dataclasses import dataclass
from uuid import UUID

from schemavcs.merge.classify import Classification, ClassifiedGroup
from schemavcs.merge.grouping import IdentityGroup
from schemavcs.model import (
    AddColumn,
    AddConstraint,
    AddIndex,
    CompoundOperation,
    DropColumn,
    DropTable,
    Operation,
    Snapshot,
)


@dataclass
class _Destroyed:
    tables: set[UUID]
    columns: set[UUID]


def _destroyed_by(compounds: tuple[CompoundOperation, ...]) -> _Destroyed:
    tables: set[UUID] = set()
    columns: set[UUID] = set()
    for compound in compounds:
        for op in compound.operations:
            match op:
                case DropTable(table_id=table_id):
                    tables.add(table_id)
                case DropColumn(column_id=column_id):
                    columns.add(column_id)
    return _Destroyed(tables=tables, columns=columns)


def _referenced_ids(op: Operation) -> tuple[set[UUID], set[UUID]]:
    """(tables referenced, columns referenced) by a single operation."""
    match op:
        case AddColumn(table_id=table_id):
            return ({table_id}, set())
        case AddIndex(table_id=table_id, index=index):
            return ({table_id}, set(index.columns))
        case AddConstraint(table_id=table_id, constraint=constraint):
            tables = {table_id}
            if constraint.references is not None:
                tables.add(constraint.references)
            return (tables, set(constraint.columns))
        case _:
            return (set(), set())


def _find_conflicts(
    adding_compounds: tuple[CompoundOperation, ...], destroyed: _Destroyed
) -> list[tuple[Operation, UUID, str]]:
    """Operations in `adding_compounds` that reference a table/column in
    `destroyed`. Returns (operation, destroyed_id, kind) triples."""
    conflicts = []
    for compound in adding_compounds:
        for op in compound.operations:
            ref_tables, ref_columns = _referenced_ids(op)
            for table_id in ref_tables & destroyed.tables:
                conflicts.append((op, table_id, "table"))
            for column_id in ref_columns & destroyed.columns:
                conflicts.append((op, column_id, "column"))
    return conflicts


def _name_of(kind: str, destroyed_id: UUID, snapshot_ancestor: Snapshot) -> str:
    if kind == "table":
        for table in snapshot_ancestor.tables:
            if table.id == destroyed_id:
                return table.name
    else:
        for table in snapshot_ancestor.tables:
            for column in table.columns:
                if column.id == destroyed_id:
                    return f"{table.name}.{column.name}"
    return str(destroyed_id)


def cross_object_pass(
    classified: list[ClassifiedGroup],
    ops_a: tuple[CompoundOperation, ...],
    ops_b: tuple[CompoundOperation, ...],
    snapshot_ancestor: Snapshot,
) -> list[ClassifiedGroup]:
    destroyed_a = _destroyed_by(ops_a)
    destroyed_b = _destroyed_by(ops_b)

    new_groups: list[ClassifiedGroup] = []

    # branch A dropped it, branch B's operation still references it
    for op, destroyed_id, kind in _find_conflicts(ops_b, destroyed_a):
        new_groups.append(
            _build_conflict(
                destroyed_id, kind, "A", op, on_side_a=False, snapshot_ancestor=snapshot_ancestor
            )
        )

    # branch B dropped it, branch A's operation still references it
    for op, destroyed_id, kind in _find_conflicts(ops_a, destroyed_b):
        new_groups.append(
            _build_conflict(
                destroyed_id, kind, "B", op, on_side_a=True, snapshot_ancestor=snapshot_ancestor
            )
        )

    return classified + new_groups


def _build_conflict(
    destroyed_id: UUID,
    kind: str,
    dropper: str,
    referencing_op: Operation,
    on_side_a: bool,
    snapshot_ancestor: Snapshot,
) -> ClassifiedGroup:
    """The dropper's side is left empty deliberately — the drop lives in
    ops_a/ops_b at the destroyed identity's OWN id, not this synthetic
    group; fabricating a DropColumn here would need a table_id this pass
    was never given. The reason string already names what was dropped and
    by whom; that's the information this synthetic group exists to carry."""
    name = _name_of(kind, destroyed_id, snapshot_ancestor)
    reason = (
        f"branch {dropper} dropped {kind} {name!r} that another branch's operation still references"
    )
    group = IdentityGroup(
        identity_id=destroyed_id,
        ops_a=[referencing_op] if on_side_a else [],
        ops_b=[referencing_op] if not on_side_a else [],
    )
    return ClassifiedGroup(group=group, classification=Classification.CONFLICT, reason=reason)
