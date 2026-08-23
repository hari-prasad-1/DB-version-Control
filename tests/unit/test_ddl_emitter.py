from uuid import uuid4

from schemavcs.ddl.emitter import emit_ddl
from schemavcs.model import (
    AddColumn,
    AddConstraint,
    AddIndex,
    AlterColumnNullability,
    AlterColumnType,
    Column,
    Constraint,
    CreateTable,
    DropColumn,
    DropTable,
    Index,
    RenameColumn,
    Table,
    TypeSpec,
)


def test_create_table_with_columns():
    table_id = uuid4()
    table = Table(
        id=table_id,
        name="orders",
        columns=[
            Column(id=uuid4(), name="id", type=TypeSpec("uuid"), position=0),
            Column(id=uuid4(), name="total", type=TypeSpec("int"), nullable=False, position=1),
        ],
    )
    sql = emit_ddl((CreateTable(table=table),))
    assert sql == "CREATE TABLE orders (id uuid, total int NOT NULL);"


def test_add_column_after_create_table_in_same_batch():
    table_id = uuid4()
    create = CreateTable(table=Table(id=table_id, name="orders"))
    add = AddColumn(
        table_id=table_id, column=Column(id=uuid4(), name="notes", type=TypeSpec("text"))
    )
    sql = emit_ddl((add, create))  # order given is dependency-sorted internally
    lines = sql.split("\n")
    assert lines[0] == "CREATE TABLE orders ();"
    assert lines[1] == "ALTER TABLE orders ADD COLUMN notes text;"


def test_drop_column_before_drop_table_resolves_names_from_pre_op_state():
    table_id, column_id = uuid4(), uuid4()
    state = {
        table_id: Table(
            id=table_id,
            name="orders",
            columns=[Column(id=column_id, name="legacy_id", type=TypeSpec("int"))],
        )
    }
    sql = emit_ddl(
        (DropTable(table_id=table_id), DropColumn(table_id=table_id, column_id=column_id)),
        tables_by_id=state,
    )
    lines = sql.split("\n")
    assert lines[0] == "ALTER TABLE orders DROP COLUMN legacy_id;"
    assert lines[1] == "DROP TABLE orders;"


def test_rename_column_and_alter_type_use_names_from_state():
    table_id, column_id = uuid4(), uuid4()
    state = {
        table_id: Table(
            id=table_id,
            name="users",
            columns=[Column(id=column_id, name="subscription_type", type=TypeSpec("string"))],
        )
    }
    sql = emit_ddl(
        (
            RenameColumn(column_id=column_id, old_name="subscription_type", new_name="plan_type"),
            AlterColumnType(
                column_id=column_id, old_type=TypeSpec("string"), new_type=TypeSpec("enum")
            ),
        ),
        tables_by_id=state,
    )
    lines = sql.split("\n")
    assert lines[0] == "ALTER TABLE users RENAME COLUMN subscription_type TO plan_type;"
    assert lines[1] == "ALTER TABLE users ALTER COLUMN plan_type TYPE enum;"


def test_alter_column_nullability():
    table_id, column_id = uuid4(), uuid4()
    state = {
        table_id: Table(
            id=table_id,
            name="users",
            columns=[Column(id=column_id, name="email", type=TypeSpec("string"))],
        )
    }
    sql = emit_ddl(
        (AlterColumnNullability(column_id=column_id, nullable=False),), tables_by_id=state
    )
    assert sql == "ALTER TABLE users ALTER COLUMN email SET NOT NULL;"


def test_add_index():
    table_id, column_id = uuid4(), uuid4()
    state = {
        table_id: Table(
            id=table_id,
            name="users",
            columns=[Column(id=column_id, name="email", type=TypeSpec("string"))],
        )
    }
    sql = emit_ddl(
        (
            AddIndex(
                table_id=table_id,
                index=Index(id=uuid4(), name="idx_email", columns=[column_id], unique=True),
            ),
        ),
        tables_by_id=state,
    )
    assert sql == "CREATE UNIQUE INDEX idx_email ON users (email);"


def test_add_foreign_key_constraint_depends_on_referenced_table_creation():
    orders_id, users_id, col_id = uuid4(), uuid4(), uuid4()
    create_orders = CreateTable(table=Table(id=orders_id, name="orders"))
    create_users = CreateTable(
        table=Table(
            id=users_id,
            name="users",
            columns=[Column(id=col_id, name="org_id", type=TypeSpec("uuid"))],
        )
    )
    add_fk = AddConstraint(
        table_id=users_id,
        constraint=Constraint(
            id=uuid4(), kind="foreign_key", columns=[col_id], references=orders_id
        ),
    )
    sql = emit_ddl((add_fk, create_users, create_orders))
    lines = sql.split("\n")
    assert lines.index("CREATE TABLE orders ();") < lines.index(
        "ALTER TABLE users ADD FOREIGN KEY (org_id) REFERENCES orders;"
    )


def test_dependency_ordering_is_applied_before_emission():
    # feed operations in a deliberately wrong order -- emit_ddl must
    # toposort them itself, not trust caller order.
    table_id = uuid4()
    create = CreateTable(table=Table(id=table_id, name="orders"))
    add = AddColumn(
        table_id=table_id, column=Column(id=uuid4(), name="notes", type=TypeSpec("text"))
    )
    sql = emit_ddl((add, create))
    lines = sql.split("\n")
    assert lines.index("CREATE TABLE orders ();") < lines.index(
        "ALTER TABLE orders ADD COLUMN notes text;"
    )
