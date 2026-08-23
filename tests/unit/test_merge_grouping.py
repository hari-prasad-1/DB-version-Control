from uuid import uuid4

from schemavcs.merge.grouping import group_by_identity
from schemavcs.model import AddColumn, Column, CompoundOperation, RenameColumn, TypeSpec


def test_group_by_identity_splits_by_column_id():
    table_id = uuid4()
    col_x, col_y = uuid4(), uuid4()

    ops_a = (
        CompoundOperation(
            operations=(
                AddColumn(
                    table_id=table_id, column=Column(id=col_x, name="x", type=TypeSpec("int"))
                ),
            )
        ),
    )
    ops_b = (
        CompoundOperation(
            operations=(
                AddColumn(
                    table_id=table_id, column=Column(id=col_y, name="y", type=TypeSpec("int"))
                ),
            )
        ),
    )

    groups = group_by_identity(ops_a, ops_b)
    ids = {g.identity_id for g in groups}
    assert ids == {col_x, col_y}

    group_x = next(g for g in groups if g.identity_id == col_x)
    assert len(group_x.ops_a) == 1
    assert group_x.ops_b == []


def test_group_by_identity_same_column_touched_by_both():
    col_id = uuid4()
    ops_a = (
        CompoundOperation(operations=(RenameColumn(column_id=col_id, old_name="a", new_name="b"),)),
    )
    ops_b = (
        CompoundOperation(operations=(RenameColumn(column_id=col_id, old_name="a", new_name="c"),)),
    )

    groups = group_by_identity(ops_a, ops_b)
    assert len(groups) == 1
    assert groups[0].ops_a[0].new_name == "b"
    assert groups[0].ops_b[0].new_name == "c"
