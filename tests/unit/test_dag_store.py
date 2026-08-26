import pytest

from schemavcs.dag.store import DagStore, UnknownBranchError


def test_delete_branch_removes_the_head():
    store = DagStore()
    store.append("root", "main", ())
    store.append("b1", "feature", ("root",))

    store.delete_branch("feature")

    assert store.has_branch("feature") is False
    assert "feature" not in store.all_heads()


def test_delete_branch_leaves_unrelated_branches_and_history_untouched():
    store = DagStore()
    store.append("root", "main", ())
    store.append("b1", "feature", ("root",))

    store.delete_branch("feature")

    assert store.has_branch("main") is True
    assert store.has_node("root") is True
    assert store.has_node("b1") is True  # the migration itself is never deleted


def test_delete_unknown_branch_raises():
    store = DagStore()
    store.append("root", "main", ())
    with pytest.raises(UnknownBranchError):
        store.delete_branch("does-not-exist")


def test_deleted_branch_name_can_be_reused_immediately():
    store = DagStore()
    store.append("root", "main", ())
    store.append("b1", "feature", ("root",))

    store.delete_branch("feature")
    store.set_head("feature", "root")

    assert store.has_branch("feature") is True
