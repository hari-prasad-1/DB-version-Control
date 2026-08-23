"""Groups operations from two branches by the identity id each one targets.

Independent creation on two branches can never mint the same id for two
different objects (identity is assigned once, at creation) — so a group
touched by both branches only arises when both sides are mutating (or
mutating vs. destroying) something that already existed at the common
ancestor. A group touched by only one branch carries an empty list for the
other side.
"""

from dataclasses import dataclass, field
from uuid import UUID

from schemavcs.model import (
    AddColumn,
    AddConstraint,
    AddIndex,
    CompoundOperation,
    CreateTable,
    Operation,
)


def _target_id(op: Operation) -> UUID | None:
    """The identity THIS operation is about — never the id of a containing
    table it merely references. AddColumn/AddIndex/AddConstraint all carry a
    table_id alongside the new object, but that table_id is a cross-object
    reference (relevant to the separate cross-object pass), not this
    operation's own identity — the created object's own id is what matters
    here, so those three variants are matched explicitly before falling
    back to the generic *_id fields the rest of the ADT uses."""
    match op:
        case CreateTable(table=table):
            return table.id
        case AddColumn(column=column):
            return column.id
        case AddIndex(index=index):
            return index.id
        case AddConstraint(constraint=constraint):
            return constraint.id
        case _:
            for attr in ("column_id", "index_id", "constraint_id", "table_id"):
                value = getattr(op, attr, None)
                if value is not None:
                    return value
            return None


def _flatten(compounds: tuple[CompoundOperation, ...]) -> list[Operation]:
    return [op for compound in compounds for op in compound.operations]


@dataclass
class IdentityGroup:
    identity_id: UUID
    ops_a: list[Operation] = field(default_factory=list)
    ops_b: list[Operation] = field(default_factory=list)


def group_by_identity(
    ops_a: tuple[CompoundOperation, ...], ops_b: tuple[CompoundOperation, ...]
) -> list[IdentityGroup]:
    groups: dict[UUID, IdentityGroup] = {}

    for op in _flatten(ops_a):
        identity_id = _target_id(op)
        if identity_id is None:
            continue
        groups.setdefault(identity_id, IdentityGroup(identity_id=identity_id)).ops_a.append(op)

    for op in _flatten(ops_b):
        identity_id = _target_id(op)
        if identity_id is None:
            continue
        groups.setdefault(identity_id, IdentityGroup(identity_id=identity_id)).ops_b.append(op)

    return list(groups.values())
