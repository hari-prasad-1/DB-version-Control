from uuid import uuid4

from schemavcs.dsl.raw import RawColumn, RawTable
from schemavcs.model import (
    AddColumn,
    AlterColumnNullability,
    AlterColumnType,
    Column,
    CreateTable,
    DropColumn,
    DropTable,
    RenameColumn,
    Snapshot,
    Table,
    TypeSpec,
)
from schemavcs.snapshot.diff import diff_snapshot
from schemavcs.snapshot.to_operations import generate_operations


def test_new_table_becomes_create_table_plus_add_columns():
    old = Snapshot(branch="main", revision_id="r1", tables=[])
    new_raw = [
        RawTable(
            name="orders",
            columns=(RawColumn(name="id", type=TypeSpec("uuid"), position=0),),
        )
    ]
    diff = diff_snapshot(old, new_raw)

    generated = generate_operations(diff, confirm=lambda p: True)

    assert len(generated.operations) == 1
    ops = generated.operations[0].operations
    assert isinstance(ops[0], CreateTable)
    assert ops[0].table.name == "orders"
    assert isinstance(ops[1], AddColumn)
    assert ops[1].column.name == "id"


def test_removed_table_becomes_drop_table():
    table_id = uuid4()
    old = Snapshot(branch="main", revision_id="r1", tables=[Table(id=table_id, name="legacy")])
    diff = diff_snapshot(old, [])

    generated = generate_operations(diff, confirm=lambda p: True)

    assert len(generated.operations) == 1
    ops = generated.operations[0].operations
    assert ops == (DropTable(table_id=table_id),)


def test_retyped_column_becomes_alter_column_type():
    table_id, col_id = uuid4(), uuid4()
    old = Snapshot(
        branch="main",
        revision_id="r1",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[Column(id=col_id, name="status", type=TypeSpec("string"))],
            )
        ],
    )
    new_raw = [RawTable(name="users", columns=(RawColumn(name="status", type=TypeSpec("enum")),))]
    diff = diff_snapshot(old, new_raw)

    generated = generate_operations(diff, confirm=lambda p: True)

    ops = generated.operations[0].operations
    assert len(ops) == 1
    assert isinstance(ops[0], AlterColumnType)
    assert ops[0].column_id == col_id
    assert ops[0].new_type == TypeSpec("enum")


def test_nullability_change_becomes_alter_column_nullability():
    table_id, col_id = uuid4(), uuid4()
    old = Snapshot(
        branch="main",
        revision_id="r1",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[Column(id=col_id, name="email", type=TypeSpec("string"), nullable=True)],
            )
        ],
    )
    new_raw = [
        RawTable(
            name="users",
            columns=(RawColumn(name="email", type=TypeSpec("string"), nullable=False),),
        )
    ]
    diff = diff_snapshot(old, new_raw)

    generated = generate_operations(diff, confirm=lambda p: True)

    ops = generated.operations[0].operations
    assert isinstance(ops[0], AlterColumnNullability)
    assert ops[0].nullable is False


def test_confirmed_rename_becomes_rename_column_op():
    table_id, col_id = uuid4(), uuid4()
    old = Snapshot(
        branch="main",
        revision_id="r1",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[Column(id=col_id, name="subscription_type", type=TypeSpec("string"))],
            )
        ],
    )
    new_raw = [
        RawTable(name="users", columns=(RawColumn(name="plan_type", type=TypeSpec("enum")),))
    ]
    diff = diff_snapshot(old, new_raw)

    generated = generate_operations(diff, confirm=lambda p: True)

    ops = generated.operations[0].operations
    rename_ops = [op for op in ops if isinstance(op, RenameColumn)]
    retype_ops = [op for op in ops if isinstance(op, AlterColumnType)]
    assert len(rename_ops) == 1
    assert rename_ops[0].column_id == col_id
    assert rename_ops[0].new_name == "plan_type"
    assert len(retype_ops) == 1
    assert retype_ops[0].new_type == TypeSpec("enum")


def test_rejected_rename_becomes_plain_drop_and_add():
    table_id, col_id = uuid4(), uuid4()
    old = Snapshot(
        branch="main",
        revision_id="r1",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[Column(id=col_id, name="subscription_type", type=TypeSpec("string"))],
            )
        ],
    )
    new_raw = [
        RawTable(name="users", columns=(RawColumn(name="plan_type", type=TypeSpec("enum")),))
    ]
    diff = diff_snapshot(old, new_raw)

    generated = generate_operations(diff, confirm=lambda p: False)

    ops = generated.operations[0].operations
    assert any(isinstance(op, DropColumn) and op.column_id == col_id for op in ops)
    assert any(isinstance(op, AddColumn) and op.column.name == "plan_type" for op in ops)
    assert not any(isinstance(op, RenameColumn) for op in ops)


def test_no_changes_produces_no_operations():
    table_id, col_id = uuid4(), uuid4()
    old = Snapshot(
        branch="main",
        revision_id="r1",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[Column(id=col_id, name="email", type=TypeSpec("string"))],
            )
        ],
    )
    new_raw = [RawTable(name="users", columns=(RawColumn(name="email", type=TypeSpec("string")),))]
    diff = diff_snapshot(old, new_raw)

    generated = generate_operations(diff, confirm=lambda p: True)

    assert generated.operations == ()
