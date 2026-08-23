from schemavcs.cli.commands import branch_cmd, init_cmd, migrate_cmd
from schemavcs.dag.persistence import load
from schemavcs.model import AddColumn, CreateTable, RenameColumn


def test_author_migrations_and_rename_via_cli(tmp_path):
    init_cmd.run(tmp_path)

    # base state on main
    migrate_cmd.create_table(tmp_path, "main", "users")
    migrate_cmd.add_column(tmp_path, "main", "users", "subscription_type", "string(50)", True)

    branch_cmd.create(tmp_path, "branch-a", from_branch="main")
    migrate_cmd.rename_column(tmp_path, "branch-a", "users", "subscription_type", "plan_type")
    migrate_cmd.alter_column_type(tmp_path, "branch-a", "users", "plan_type", "enum")

    store = load(tmp_path)
    a_head = store.head("branch-a")
    main_head = store.head("main")

    assert a_head != main_head

    # walk branch-a's history back to main's head and confirm the exact
    # operations recorded, in order
    chain_ops = []
    rev = a_head
    while rev != main_head:
        node = store.get_node(rev)
        chain_ops.extend(node.operations)
        rev = node.parents[0]

    flattened = [op for compound in chain_ops for op in compound.operations]
    assert len(flattened) == 2
    # walked backward from branch-a's head, so the rename (authored first)
    # appears last and the retype (authored second) appears first
    assert isinstance(flattened[-1], RenameColumn)
    rename_op = flattened[-1]
    assert rename_op.old_name == "subscription_type"
    assert rename_op.new_name == "plan_type"


def test_branch_create_inherits_parent_head(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "orders")
    branch_cmd.create(tmp_path, "branch-b", from_branch="main")

    store = load(tmp_path)
    assert store.head("branch-b") == store.head("main")


def test_add_column_resolves_table_by_name(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "orders")
    migrate_cmd.add_column(tmp_path, "main", "orders", "total", "int", False)

    store = load(tmp_path)
    node = store.get_node(store.head("main"))
    op = node.operations[0].operations[0]
    assert isinstance(op, AddColumn)
    assert op.column.name == "total"
    assert op.column.nullable is False


def test_create_table_then_drop_it(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "temp")
    migrate_cmd.drop_table(tmp_path, "main", "temp")

    store = load(tmp_path)
    node = store.get_node(store.head("main"))
    op = node.operations[0].operations[0]
    from schemavcs.model import DropTable

    assert isinstance(op, DropTable)

    first_op = store.get_node(node.parents[0]).operations[0].operations[0]
    assert isinstance(first_op, CreateTable)
    assert first_op.table.id == op.table_id
