import pytest

from schemavcs.cli.commands import branch_cmd, checkout_cmd, init_cmd, migrate_cmd
from schemavcs.dag.persistence import load
from schemavcs.storage.paths import read_current_branch


def test_init_sets_current_branch_to_main(tmp_path):
    init_cmd.run(tmp_path)
    assert read_current_branch(tmp_path) == "main"


def test_branch_create_defaults_from_to_current_and_switches(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")  # explicit branch still works

    branch_cmd.create(tmp_path, "branch-a")  # from_branch omitted -> defaults to current ("main")

    assert read_current_branch(tmp_path) == "branch-a"
    store = load(tmp_path)
    assert store.head("branch-a") == store.head("main")


def test_checkout_switches_current_branch(tmp_path):
    init_cmd.run(tmp_path)
    branch_cmd.create(tmp_path, "branch-a")
    branch_cmd.create(tmp_path, "branch-b", from_branch="main")

    assert read_current_branch(tmp_path) == "branch-b"
    checkout_cmd.run(tmp_path, "branch-a")
    assert read_current_branch(tmp_path) == "branch-a"


def test_migrate_defaults_branch_to_current(tmp_path):
    init_cmd.run(tmp_path)
    branch_cmd.create(tmp_path, "branch-a")
    checkout_cmd.run(tmp_path, "branch-a")

    # relies on main.py's dispatch to resolve the omitted --branch, so drive
    # this through the CLI entry point rather than migrate_cmd directly
    from schemavcs.cli.main import build_parser, dispatch

    parser = build_parser()
    args = parser.parse_args(["--repo", str(tmp_path), "migrate", "create-table", "orders"])
    dispatch(args)

    store = load(tmp_path)
    assert store.head("branch-a") != store.head("main")


def test_checkout_unknown_branch_raises(tmp_path):
    init_cmd.run(tmp_path)
    with pytest.raises(ValueError):
        checkout_cmd.run(tmp_path, "does-not-exist")
