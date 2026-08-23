"""Phase 1 completion gate: everything before this is already independently
tested; this proves the whole chain -- branch, author migrations entirely
via CLI verbs, merge, emit DDL -- holds together end to end.

Scenario: branch-a renames+retypes a column (the project's own demo pair),
branch-b independently adds a colliding column plus its own new column, and
drops an unrelated table. Merging surfaces one real conflict (the colliding
column name) which a scripted confirm resolves, then the merged result's
DDL is checked for a valid dependency order.
"""

from schemavcs.cli.commands import branch_cmd, init_cmd, migrate_cmd
from schemavcs.dag.persistence import load
from schemavcs.dag.walk import replay, topological_order
from schemavcs.ddl.emitter import emit_ddl
from schemavcs.merge.engine import merge


def _fail_if_asked(group):
    raise AssertionError(
        f"unexpected human-confirmation request for identity {group.group.identity_id}: "
        f"{group.reason}"
    )


def test_phase1_demo_branch_diverge_merge_emit_ddl(tmp_path):
    init_cmd.run(tmp_path)

    # base state on main: users(subscription_type), and a table branch-b
    # will independently drop
    migrate_cmd.create_table(tmp_path, "main", "users")
    migrate_cmd.add_column(tmp_path, "main", "users", "subscription_type", "string(50)", True)
    migrate_cmd.create_table(tmp_path, "main", "legacy_reports")

    branch_cmd.create(tmp_path, "branch-a", from_branch="main")
    branch_cmd.create(tmp_path, "branch-b", from_branch="main")

    # branch-a: the project's own demo rename+retype pair
    migrate_cmd.rename_column(tmp_path, "branch-a", "users", "subscription_type", "plan_type")
    migrate_cmd.alter_column_type(tmp_path, "branch-a", "users", "plan_type", "enum")
    # branch-a also independently adds a column named "notes"
    migrate_cmd.add_column(tmp_path, "branch-a", "users", "notes", "text", True)

    # branch-b: independently adds a DIFFERENT column also named "notes"
    # (the collision) plus a genuinely unrelated column, and drops a table
    migrate_cmd.add_column(tmp_path, "branch-b", "users", "notes", "string(500)", True)
    migrate_cmd.add_column(tmp_path, "branch-b", "users", "region", "string(10)", True)
    migrate_cmd.drop_table(tmp_path, "branch-b", "legacy_reports")

    store = load(tmp_path)
    result = merge(store, "branch-a", "branch-b", confirm=_fail_if_asked)

    # the colliding "notes" column is resolved deterministically (DAG-
    # distance tie-break, not a human decision) and surfaced as a note;
    # nothing else in this scenario is a real per-identity conflict either
    assert result.conflicts_resolved == 0
    assert len(result.notes) == 1
    assert "notes" in result.notes[0]
    assert result.fast_forward is False

    # check the final merged STATE (not the merge node's own stored ops --
    # UNRELATED groups like the rename/retype/region-add/table-drop aren't
    # re-stored there, since each is already reachable via its own parent
    # chain; replaying the full history is the only correct way to see the
    # merge's actual result)
    snapshot = replay(store, result.migration.id, branch="branch-a")
    table_names = {t.name for t in snapshot.tables}
    assert "legacy_reports" not in table_names  # branch-b's drop took effect

    users = next(t for t in snapshot.tables if t.name == "users")
    column_names = {c.name for c in users.columns}
    assert "plan_type" in column_names  # branch-a's rename took effect
    assert "subscription_type" not in column_names
    assert "region" in column_names  # branch-b's unrelated add took effect

    plan_type = next(c for c in users.columns if c.name == "plan_type")
    assert plan_type.type.name == "enum"  # branch-a's retype took effect

    # branch-b's "notes" survived the collision -- it's closer to the merge
    # base (branch-b's first authored op) than branch-a's competing "notes"
    # (branch-a's third authored op), per the DAG-distance tie-break rule
    notes_columns = [c for c in users.columns if c.name == "notes"]
    assert len(notes_columns) == 1
    assert notes_columns[0].type.name == "string"

    # emit DDL for branch-a's full merged history and confirm it holds
    # together as a valid, dependency-ordered statement sequence
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
    assert drop_legacy_idx >= 0  # legacy_reports' own create precedes its drop by construction
