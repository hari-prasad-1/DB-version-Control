from schemavcs.cli.commands import branch_cmd, init_cmd, merge_cmd, migrate_cmd
from schemavcs.cli.main import build_parser, dispatch
from schemavcs.dag.persistence import load


def _keep_a(group):
    from uuid import uuid4

    from schemavcs.merge.resolve import HumanConfirmationToken

    return HumanConfirmationToken(
        group_id=group.group.identity_id,
        chosen_resolution=tuple(group.group.ops_a),
        _nonce=uuid4(),
    )


def test_merge_cmd_diverged_branches_no_conflict(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "orders")
    branch_cmd.create(tmp_path, "branch-b", from_branch="main")

    migrate_cmd.add_column(tmp_path, "main", "orders", "total", "int", True)
    migrate_cmd.add_column(tmp_path, "branch-b", "orders", "status", "string(20)", True)

    from schemavcs.merge.engine import merge

    store = load(tmp_path)
    result = merge(store, "main", "branch-b")
    assert result.fast_forward is False
    assert result.conflicts_resolved == 0


def test_merge_cmd_via_dispatch_fast_forward(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "orders")
    branch_cmd.create(tmp_path, "branch-b", from_branch="main")
    migrate_cmd.add_column(tmp_path, "branch-b", "orders", "status", "string(20)", True)

    parser = build_parser()
    args = parser.parse_args(["--repo", str(tmp_path), "merge", "branch-b", "--into", "main"])
    dispatch(args)

    store = load(tmp_path)
    assert store.head("main") == store.head("branch-b")


def test_merge_conflict_resolved_via_confirm_callback(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")
    migrate_cmd.add_column(tmp_path, "main", "users", "x", "string(10)", True)
    branch_cmd.create(tmp_path, "branch-b", from_branch="main")

    migrate_cmd.rename_column(tmp_path, "main", "users", "x", "y")
    migrate_cmd.rename_column(tmp_path, "branch-b", "users", "x", "z")

    store = load(tmp_path)
    from schemavcs.merge.engine import merge

    result = merge(store, "main", "branch-b", confirm=_keep_a)
    assert result.conflicts_resolved == 1


def test_emit_ddl_cmd_prints_sql_for_full_history(tmp_path, capsys):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "orders")
    migrate_cmd.add_column(tmp_path, "main", "orders", "total", "int", False)

    parser = build_parser()
    args = parser.parse_args(["--repo", str(tmp_path), "emit-ddl", "--branch", "main"])
    dispatch(args)

    output = capsys.readouterr().out
    assert "CREATE TABLE orders" in output
    assert "ALTER TABLE orders ADD COLUMN total int NOT NULL;" in output


def test_full_pipeline_branch_diverge_merge_emit_ddl(tmp_path, capsys):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "orders")
    branch_cmd.create(tmp_path, "branch-b", from_branch="main")

    migrate_cmd.add_column(tmp_path, "main", "orders", "total", "int", True)
    migrate_cmd.add_column(tmp_path, "branch-b", "orders", "status", "string(20)", True)

    merge_cmd.run(tmp_path, "main", "branch-b")

    parser = build_parser()
    args = parser.parse_args(["--repo", str(tmp_path), "emit-ddl", "--branch", "main"])
    dispatch(args)

    output = capsys.readouterr().out
    assert "ADD COLUMN total int;" in output
    assert "ADD COLUMN status string(20);" in output
