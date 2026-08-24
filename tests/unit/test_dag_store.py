import pytest

from schemavcs.dag.store import DagStore, UnknownBranchError


def test_retire_branch_removes_the_head_and_marks_it_retired():
    store = DagStore()
    store.append("root", "main", ())
    store.append("b1", "feature", ("root",))

    store.retire_branch("feature")

    assert store.has_branch("feature") is False
    assert store.is_retired("feature") is True
    assert "feature" not in store.all_heads()


def test_retire_branch_leaves_unrelated_branches_and_history_untouched():
    store = DagStore()
    store.append("root", "main", ())
    store.append("b1", "feature", ("root",))

    store.retire_branch("feature")

    assert store.has_branch("main") is True
    assert store.has_node("root") is True
    assert store.has_node("b1") is True  # the migration itself is never deleted


def test_retire_unknown_branch_raises():
    store = DagStore()
    store.append("root", "main", ())
    with pytest.raises(UnknownBranchError):
        store.retire_branch("does-not-exist")


def test_is_retired_false_for_a_branch_that_was_never_deleted():
    store = DagStore()
    store.append("root", "main", ())
    assert store.is_retired("main") is False


def test_all_retired_returns_every_deleted_name():
    store = DagStore()
    store.append("root", "main", ())
    store.append("b1", "feature-a", ("root",))
    store.append("b2", "feature-b", ("root",))

    store.retire_branch("feature-a")
    store.retire_branch("feature-b")

    assert store.all_retired() == {"feature-a", "feature-b"}


def test_retire_branch_from_load_does_not_require_a_current_head():
    # this is how load() restores retired state from disk -- by the time
    # it runs, the head is already absent from the persisted heads.json,
    # so this must NOT raise UnknownBranchError the way retire_branch()
    # would for a branch with no head.
    store = DagStore()
    store.retire_branch_from_load("long-gone")
    assert store.is_retired("long-gone") is True
