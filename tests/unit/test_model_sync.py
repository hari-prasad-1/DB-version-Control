from schemavcs.cli.commands import branch_cmd, init_cmd, migrate_cmd
from schemavcs.storage.paths import schema_file


def test_schema_file_reflects_authored_migrations(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")
    migrate_cmd.add_column(tmp_path, "main", "users", "email", "string(255)", False)
    migrate_cmd.add_column(tmp_path, "main", "users", "created_at", "timestamp", True)

    text = schema_file(tmp_path, "main").read_text()
    assert "table users {" in text
    assert "column email: string(255) not_null" in text
    assert "column created_at: timestamp" in text
    assert "not_null" not in text.split("created_at")[1].split("\n")[0]


def test_schema_file_reflects_rename(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")
    migrate_cmd.add_column(tmp_path, "main", "users", "subscription_type", "string(50)", True)
    migrate_cmd.rename_column(tmp_path, "main", "users", "subscription_type", "plan_type")

    text = schema_file(tmp_path, "main").read_text()
    assert "plan_type" in text
    assert "subscription_type" not in text


def test_branch_create_copies_current_schema_under_new_name(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "orders")

    branch_cmd.create(tmp_path, "branch-a")

    main_text = schema_file(tmp_path, "main").read_text()
    branch_text = schema_file(tmp_path, "branch-a").read_text()
    assert main_text == branch_text
    assert "table orders {" in branch_text


def test_column_order_matches_authoring_order(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "orders")
    migrate_cmd.add_column(tmp_path, "main", "orders", "id", "uuid", False)
    migrate_cmd.add_column(tmp_path, "main", "orders", "total", "int", False)

    text = schema_file(tmp_path, "main").read_text()
    assert text.index("column id:") < text.index("column total:")


def test_index_and_foreign_key_rendered(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "organizations")
    migrate_cmd.add_column(tmp_path, "main", "organizations", "id", "uuid", False)

    migrate_cmd.create_table(tmp_path, "main", "users")
    migrate_cmd.add_column(tmp_path, "main", "users", "org_id", "uuid", False)
    migrate_cmd.add_index(tmp_path, "main", "users", "idx_users_org", ["org_id"], False)
    migrate_cmd.add_foreign_key(tmp_path, "main", "users", ["org_id"], "organizations")

    text = schema_file(tmp_path, "main").read_text()
    assert "index idx_users_org on (org_id)" in text
    assert "foreign_key (org_id) references organizations" in text
