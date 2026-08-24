import pytest

from schemavcs.cli.commands import branch_cmd, checkout_cmd, init_cmd, migrate_cmd
from schemavcs.dag.persistence import load
from schemavcs.dag.store import BranchNameRetiredError
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


def test_branch_delete_removes_it_and_retires_the_name(tmp_path):
    init_cmd.run(tmp_path)
    branch_cmd.create(tmp_path, "feature")
    checkout_cmd.run(tmp_path, "main")

    branch_cmd.delete(tmp_path, "feature")

    store = load(tmp_path)
    assert store.has_branch("feature") is False
    assert store.is_retired("feature") is True


def test_branch_delete_refuses_to_delete_the_current_branch(tmp_path):
    init_cmd.run(tmp_path)
    branch_cmd.create(tmp_path, "feature")  # create() switches to "feature"

    with pytest.raises(ValueError):
        branch_cmd.delete(tmp_path, "feature")

    store = load(tmp_path)
    assert store.has_branch("feature") is True  # refused, nothing changed


def test_creating_a_branch_with_a_retired_name_raises(tmp_path):
    init_cmd.run(tmp_path)
    branch_cmd.create(tmp_path, "feature")
    checkout_cmd.run(tmp_path, "main")
    branch_cmd.delete(tmp_path, "feature")

    with pytest.raises(BranchNameRetiredError):
        branch_cmd.create(tmp_path, "feature")


def test_deleted_branchs_history_stays_reachable_through_replay(tmp_path):
    from schemavcs.dag.walk import replay

    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")
    branch_cmd.create(tmp_path, "feature")
    migrate_cmd.add_column(tmp_path, "feature", "users", "email", "string", True)
    checkout_cmd.run(tmp_path, "main")

    store = load(tmp_path)
    feature_head = store.head("feature")
    branch_cmd.delete(tmp_path, "feature")

    # the migration node itself is never deleted -- only the branch's own
    # head pointer to it is gone. Replaying by revision id (not by branch
    # name) still works, exactly like an orphaned commit in git.
    store = load(tmp_path)
    snapshot = replay(store, feature_head, branch="feature")
    assert {c.name for t in snapshot.tables for c in t.columns} == {"email"}


def test_rollback_moves_head_back_one_step_by_default(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")
    before_add = load(tmp_path).head("main")
    migrate_cmd.add_column(tmp_path, "main", "users", "email", "string", True)

    branch_cmd.rollback(tmp_path, "main")

    store = load(tmp_path)
    assert store.head("main") == before_add

    from schemavcs.dag.walk import replay

    snapshot = replay(store, store.head("main"), branch="main")
    assert {c.name for t in snapshot.tables for c in t.columns} == set()  # email is gone


def test_rollback_multiple_steps(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")
    root = load(tmp_path).head("main")
    migrate_cmd.add_column(tmp_path, "main", "users", "email", "string", True)
    migrate_cmd.add_column(tmp_path, "main", "users", "name", "string", True)

    branch_cmd.rollback(tmp_path, "main", steps=2)

    assert load(tmp_path).head("main") == root


def test_rollback_past_the_root_raises(tmp_path):
    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")

    with pytest.raises(ValueError):
        branch_cmd.rollback(tmp_path, "main", steps=2)


def test_rollback_does_not_delete_the_rolled_back_node(tmp_path):
    from schemavcs.dag.walk import replay

    init_cmd.run(tmp_path)
    migrate_cmd.create_table(tmp_path, "main", "users")
    migrate_cmd.add_column(tmp_path, "main", "users", "email", "string", True)
    rolled_back_from = load(tmp_path).head("main")

    branch_cmd.rollback(tmp_path, "main")

    store = load(tmp_path)
    assert store.has_node(rolled_back_from)  # node stays, just orphaned from any head
    snapshot = replay(store, rolled_back_from, branch="main")
    assert {c.name for t in snapshot.tables for c in t.columns} == {"email"}
