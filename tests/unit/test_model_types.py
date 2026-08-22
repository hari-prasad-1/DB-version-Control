from uuid import uuid4

from schemavcs.model import (
    AddColumn,
    AlterColumnDefault,
    AlterColumnNullability,
    AlterColumnType,
    Column,
    CompoundOperation,
    Constraint,
    CreateTable,
    Expr,
    Index,
    Migration,
    RenameColumn,
    RenameIndex,
    Snapshot,
    Table,
    TypeSpec,
)


def test_type_spec_str():
    assert str(TypeSpec("string", (255,))) == "string(255)"
    assert str(TypeSpec("uuid")) == "uuid"


def test_column_construction():
    col = Column(id=uuid4(), name="email", type=TypeSpec("string", (255,)), nullable=False)
    assert col.name == "email"
    assert col.nullable is False
    assert col.default is None
    assert col.position == 0


def test_index_and_constraint_construction():
    col_id = uuid4()
    idx = Index(id=uuid4(), name="idx_users_email", columns=[col_id], unique=True)
    assert idx.columns == [col_id]

    fk = Constraint(id=uuid4(), kind="foreign_key", columns=[col_id], references=uuid4())
    assert fk.kind == "foreign_key"

    check = Constraint(id=uuid4(), kind="check", raw_expr="price > 0")
    assert check.raw_expr == "price > 0"


def test_table_construction():
    table = Table(id=uuid4(), name="users")
    table.columns.append(Column(id=uuid4(), name="id", type=TypeSpec("uuid")))
    assert table.name == "users"
    assert len(table.columns) == 1


def test_snapshot_construction():
    snap = Snapshot(branch="main", revision_id=None)
    assert snap.tables == []


def test_operation_variants_constructible():
    table_id, col_id, idx_id = uuid4(), uuid4(), uuid4()
    ops = [
        CreateTable(table=Table(id=table_id, name="orders")),
        AddColumn(table_id=table_id, column=Column(id=col_id, name="notes", type=TypeSpec("text"))),
        RenameColumn(column_id=col_id, old_name="notes", new_name="comment"),
        AlterColumnType(
            column_id=col_id, old_type=TypeSpec("text"), new_type=TypeSpec("string", (255,))
        ),
        AlterColumnNullability(column_id=col_id, nullable=False),
        AlterColumnDefault(column_id=col_id, old_default=None, new_default=Expr("''")),
        RenameIndex(index_id=idx_id, old_name="idx_old", new_name="idx_new"),
    ]
    assert len(ops) == 7


def test_compound_operation():
    col_id = uuid4()
    compound = CompoundOperation(
        operations=(
            RenameColumn(column_id=col_id, old_name="subscription_type", new_name="plan_type"),
            AlterColumnType(
                column_id=col_id, old_type=TypeSpec("string"), new_type=TypeSpec("enum")
            ),
        )
    )
    assert len(compound.operations) == 2


def test_migration_node():
    m = Migration(id="rev1", parents=(), branch="main")
    assert m.is_merge is False

    merge = Migration(id="rev-merge", parents=("rev-a", "rev-b"), branch="main")
    assert merge.is_merge is True
