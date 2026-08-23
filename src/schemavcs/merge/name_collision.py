"""Same-name column collisions: two branches independently add a column
with the same name (different ids -- each branch mints its own UUID at
creation, so this is never a same-identity conflict classify.py's grouping
would ever see). Left alone, both would survive the merge and produce a
table with two columns sharing one name -- invalid DDL.

Locked rule: keep whichever add is closer to the merge base (fewer commits
since the branches diverged); drop the later one. Distance is read directly
off `operations_since`'s own return order -- it already walks base-exclusive
to head-inclusive in parent-before-child order, so earlier position in that
list IS "closer to the common ancestor," with no separate distance
computation needed. A tie (equal position) breaks toward branch A, matching
the merge model's existing target-branch-wins asymmetry.
"""

from dataclasses import dataclass
from uuid import UUID

from schemavcs.model import AddColumn, CompoundOperation


@dataclass
class NameCollision:
    table_id: UUID
    name: str
    kept: AddColumn
    dropped: AddColumn
    kept_side: str  # "a" or "b"


def _add_columns_by_table_and_name(
    compounds: tuple[CompoundOperation, ...],
) -> dict[tuple, list[tuple[int, AddColumn]]]:
    """Maps (table_id, column_name) -> [(position, op), ...], position being
    this op's index within the branch's own operations_since list."""
    by_key: dict[tuple, list[tuple[int, AddColumn]]] = {}
    position = 0
    for compound in compounds:
        for op in compound.operations:
            if isinstance(op, AddColumn):
                key = (op.table_id, op.column.name)
                by_key.setdefault(key, []).append((position, op))
            position += 1
    return by_key


def find_name_collisions(
    ops_a: tuple[CompoundOperation, ...], ops_b: tuple[CompoundOperation, ...]
) -> list[NameCollision]:
    """Same table_id + same column name, added independently on both
    branches. Only flags cross-branch collisions -- two adds on the SAME
    branch with the same name is that branch's own bug, out of scope here."""
    by_key_a = _add_columns_by_table_and_name(ops_a)
    by_key_b = _add_columns_by_table_and_name(ops_b)

    collisions = []
    for key, adds_a in by_key_a.items():
        adds_b = by_key_b.get(key)
        if not adds_b:
            continue
        table_id, name = key
        # only the first add on each side can collide meaningfully; a
        # second same-name add on one side alone is that branch's own bug
        position_a, op_a = adds_a[0]
        position_b, op_b = adds_b[0]
        if position_a <= position_b:
            collisions.append(
                NameCollision(table_id=table_id, name=name, kept=op_a, dropped=op_b, kept_side="a")
            )
        else:
            collisions.append(
                NameCollision(table_id=table_id, name=name, kept=op_b, dropped=op_a, kept_side="b")
            )
    return collisions


def describe(collision: NameCollision) -> str:
    dropped_side = "b" if collision.kept_side == "a" else "a"
    return (
        f"column {collision.name!r} was independently added on both branches -- "
        f"the one from branch {collision.kept_side} was kept, the one from branch "
        f"{dropped_side} was dropped as a duplicate name, review if that's not what "
        f"you wanted"
    )
