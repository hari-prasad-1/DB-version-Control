from schemavcs.cli.commands import generate_migration_cmd, init_cmd, migrate_cmd
from schemavcs.dag.persistence import load
from schemavcs.dag.walk import replay
from schemavcs.storage.paths import schema_file


def test_generate_migration_detects_rename_via_edited_schema_file(tmp_path, monkeypatch):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")
    migrate_cmd.add_column(tmp_path, "main", "users", "subscription_type", "string(50)", True)

    # simulate a human editing the .schema file directly, Rails-schema.rb-style
    schema_file(tmp_path, "main").write_text("table users {\n  column plan_type: enum\n}\n")

    monkeypatch.setattr(generate_migration_cmd, "confirm_rename_from_cli", lambda proposal: True)
    generate_migration_cmd.run(tmp_path, "main")

    store = load(tmp_path)
    snapshot = replay(store, store.head("main"), "main")
    column_names = {c.name for c in snapshot.tables[0].columns}
    assert column_names == {"plan_type"}


def test_generate_migration_rejected_rename_becomes_plain_drop_and_add(tmp_path, monkeypatch):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")
    migrate_cmd.add_column(tmp_path, "main", "users", "subscription_type", "string(50)", True)

    schema_file(tmp_path, "main").write_text("table users {\n  column plan_type: enum\n}\n")

    monkeypatch.setattr(generate_migration_cmd, "confirm_rename_from_cli", lambda proposal: False)
    generate_migration_cmd.run(tmp_path, "main")

    store = load(tmp_path)
    snapshot = replay(store, store.head("main"), "main")
    column_names = {c.name for c in snapshot.tables[0].columns}
    assert column_names == {"plan_type"}


def test_generate_migration_no_edit_commits_nothing(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")

    store = load(tmp_path)
    head_before = store.head("main")

    generate_migration_cmd.run(tmp_path, "main")

    store_after = load(tmp_path)
    assert store_after.head("main") == head_before


def test_generate_migration_new_table_added_to_file(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")

    existing_text = schema_file(tmp_path, "main").read_text()
    schema_file(tmp_path, "main").write_text(
        existing_text + "\ntable orders {\n  column total: int\n}\n"
    )

    generate_migration_cmd.run(tmp_path, "main")

    store = load(tmp_path)
    snapshot = replay(store, store.head("main"), "main")
    table_names = {t.name for t in snapshot.tables}
    assert table_names == {"users", "orders"}
