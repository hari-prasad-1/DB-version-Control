"""Phase 2 completion gate: the same scenario test_phase1_demo.py already
proved end to end, except branch-a's rename+retype is now DETECTED by
editing the .schema file and running `sync`, not authored via the direct
`rename-column`/`alter-column-type` CLI verbs. The merge and DDL-emission
code below is byte-for-byte what 1.12 already exercised -- proving the two
authoring paths are truly interchangeable at the Operation boundary.
"""

from schemavcs.cli.commands import branch_cmd, generate_migration_cmd, init_cmd, migrate_cmd
from schemavcs.dag.persistence import load
from schemavcs.dag.walk import replay, topological_order
from schemavcs.ddl.emitter import emit_ddl
from schemavcs.merge.engine import merge
from schemavcs.storage.paths import schema_file


def _fail_if_asked(group):
    raise AssertionError(
        f"unexpected human-confirmation request for identity {group.group.identity_id}: "
        f"{group.reason}"
    )


def test_phase2_demo_rename_detected_via_diff_then_merged_and_emitted(tmp_path, monkeypatch):
    init_cmd.run(tmp_path)

    migrate_cmd.create_table(tmp_path, "main", "users")
    migrate_cmd.add_column(tmp_path, "main", "users", "subscription_type", "string(50)", True)
    migrate_cmd.create_table(tmp_path, "main", "legacy_reports")

    branch_cmd.create(tmp_path, "branch-a", from_branch="main")
    branch_cmd.create(tmp_path, "branch-b", from_branch="main")

    # branch-a: a human edits the tracked .schema file directly -- renaming
    # AND retyping subscription_type in one edit -- then runs `sync`,
    # which diffs this against the tracked snapshot and must detect the
    # rename via similarity scoring (the one-drop-one-add structural
    # fallback: exactly one unmatched column on each side), not be told
    # about it explicitly.
    a_schema = schema_file(tmp_path, "branch-a")
    a_schema.write_text(
        "table users {\n" "  column plan_type: enum\n" "}\n" "table legacy_reports {\n" "}\n"
    )
    monkeypatch.setattr(generate_migration_cmd, "confirm_rename_from_cli", lambda proposal: True)
    generate_migration_cmd.run(tmp_path, "branch-a")

    # a separate, later edit adds an unrelated column -- kept as its own
    # sync call so this scenario doesn't accidentally feed the rename
    # detector a 1-old/2-new pool (which is a genuinely different, harder
    # case than what's being demonstrated here).
    a_schema.write_text(
        "table users {\n"
        "  column plan_type: enum\n"
        "  column notes: text\n"
        "}\n"
        "table legacy_reports {\n"
        "}\n"
    )
    generate_migration_cmd.run(tmp_path, "branch-a")

    # branch-b: independently adds a DIFFERENT column also named "notes"
    # (the collision) plus a genuinely unrelated column, and drops a table
    # -- authored via the direct CLI verbs, same as 1.12.
    migrate_cmd.add_column(tmp_path, "branch-b", "users", "notes", "string(500)", True)
    migrate_cmd.add_column(tmp_path, "branch-b", "users", "region", "string(10)", True)
    migrate_cmd.drop_table(tmp_path, "branch-b", "legacy_reports")

    store = load(tmp_path)
    result = merge(store, "branch-a", "branch-b", confirm=_fail_if_asked)

    assert result.conflicts_resolved == 0
    assert len(result.notes) == 1
    assert "notes" in result.notes[0]
    assert result.fast_forward is False

    snapshot = replay(store, result.migration.id, branch="branch-a")
    table_names = {t.name for t in snapshot.tables}
    assert "legacy_reports" not in table_names  # branch-b's drop took effect

    users = next(t for t in snapshot.tables if t.name == "users")
    column_names = {c.name for c in users.columns}
    assert "plan_type" in column_names  # branch-a's detected rename took effect
    assert "subscription_type" not in column_names
    assert "region" in column_names  # branch-b's unrelated add took effect

    plan_type = next(c for c in users.columns if c.name == "plan_type")
    assert plan_type.type.name == "enum"  # branch-a's detected retype took effect

    notes_columns = [c for c in users.columns if c.name == "notes"]
    assert len(notes_columns) == 1
    assert notes_columns[0].type.name == "string"

    # DDL emission is exactly the same call 1.12 already proved correct --
    # re-running it here is the strongest evidence the two authoring paths
    # are interchangeable at the Operation boundary.
    head = store.head("branch-a")
    ordered_revisions = topological_order(store, head)
    all_ops = tuple(
        op
        for revision_id in ordered_revisions
        for compound in store.get_node(revision_id).operations
        for op in compound.operations
    )
    sql = emit_ddl(all_ops)

    statements = sql.split("\n")
    create_users_idx = next(
        i for i, s in enumerate(statements) if s.startswith("CREATE TABLE users")
    )
    drop_legacy_idx = next(i for i, s in enumerate(statements) if "DROP TABLE legacy_reports" in s)
    rename_idx = next(i for i, s in enumerate(statements) if "RENAME COLUMN subscription_type" in s)
    assert create_users_idx < rename_idx
    assert drop_legacy_idx >= 0
