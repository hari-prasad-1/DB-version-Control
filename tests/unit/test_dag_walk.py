from uuid import uuid4

import pytest

from schemavcs.dag import (
    AmbiguousMergeBaseError,
    DagStore,
    ancestors,
    is_fast_forward,
    merge_base,
    operations_since,
    replay,
)
from schemavcs.model import AddColumn, Column, CompoundOperation, CreateTable, Table, TypeSpec


def linear_chain(store: DagStore, branch: str, *revs: str) -> None:
    """Append revs[0] -> revs[1] -> ... on `branch`, each with no parent for
    the first one already present, single-parent for the rest."""
    for rev in revs:
        head = store.head(branch) if store.has_branch(branch) else None
        parents = (head,) if head else ()
        store.append(rev, branch, parents)


def test_ancestors_simple_chain():
    store = DagStore()
    linear_chain(store, "main", "r1", "r2", "r3")
    assert ancestors(store, "r3") == {"r1", "r2", "r3"}
    assert ancestors(store, "r1") == {"r1"}


def test_merge_base_simple_siblings():
    store = DagStore()
    store.append("root", "main", ())
    store.append("a1", "branch-a", ("root",))
    store.append("b1", "branch-b", ("root",))
    assert merge_base(store, "a1", "b1") == "root"


def test_merge_base_fork_then_advance_past():
    # branch-a forks at r3; main advances to r6 via unrelated commits before
    # branch-a is merged. merge_base(a_head, r6) must be r3, not r6.
    store = DagStore()
    store.append("r1", "main", ())
    store.append("r2", "main", ("r1",))
    store.append("r3", "main", ("r2",))
    store.append("a1", "branch-a", ("r3",))
    store.append("r4", "main", ("r3",))
    store.append("r5", "main", ("r4",))
    store.append("r6", "main", ("r5",))
    assert merge_base(store, "a1", "r6") == "r3"


def test_merge_base_self():
    store = DagStore()
    store.append("r1", "main", ())
    assert merge_base(store, "r1", "r1") == "r1"


def test_merge_base_criss_cross_raises():
    store = DagStore()
    store.append("root", "main", ())
    store.append("a1", "branch-a", ("root",))
    store.append("b1", "branch-b", ("root",))
    # M1: merge b1 into a's line, parents (a1, b1)
    store.append("m1", "branch-a", ("a1", "b1"))
    # M2: merge a1 into b's line, parents (b1, a1) — same pre-merge heads,
    # opposite direction, neither m1 nor m2 is an ancestor of the other.
    store.append("m2", "branch-b", ("b1", "a1"))

    with pytest.raises(AmbiguousMergeBaseError):
        merge_base(store, "m1", "m2")


def test_merge_base_not_criss_cross_does_not_raise():
    # A second, later merge of the same two branches is NOT a criss-cross —
    # only one merge node exists, so it's an unambiguous common ancestor.
    store = DagStore()
    store.append("root", "main", ())
    store.append("a1", "branch-a", ("root",))
    store.append("b1", "branch-b", ("root",))
    store.append("m1", "branch-a", ("a1", "b1"))
    store.append("a2", "branch-a", ("m1",))
    store.append("b2", "branch-b", ("b1",))
    assert merge_base(store, "a2", "b2") == "b1"


def test_is_fast_forward():
    store = DagStore()
    store.append("root", "main", ())
    store.append("b1", "branch-b", ("root",))
    assert is_fast_forward(store, base_rev="b1", source_head="b1") is True
    assert is_fast_forward(store, base_rev="root", source_head="b1") is False


def test_operations_since_simple_chain():
    store = DagStore()
    store.append("r1", "main", ())
    store.append("r2", "main", ("r1",))
    store.append("r3", "main", ("r2",))
    assert operations_since(store, "r1", "r3") == ()
    assert operations_since(store, "r1", "r1") == ()


def test_operations_since_through_merge_node_follows_correct_parent():
    store = DagStore()
    store.append("root", "main", ())
    store.append("a1", "branch-a", ("root",))
    store.append("b1", "branch-b", ("root",))
    store.append("m1", "branch-a", ("a1", "b1"))
    store.append("a2", "branch-a", ("m1",))

    # from root to a2, the path must go through a1 and m1 (not re-walk b1's
    # own history a second time as if it were on this line).
    assert operations_since(store, "root", "a2") == ()


def test_replay_through_merge_node():
    store = DagStore()
    table_id = uuid4()
    col_a, col_b = uuid4(), uuid4()

    store.append(
        "root",
        "main",
        (),
        operations=(
            CompoundOperation(operations=(CreateTable(table=Table(id=table_id, name="orders")),)),
        ),
    )
    store.append(
        "a1",
        "branch-a",
        ("root",),
        operations=(
            CompoundOperation(
                operations=(
                    AddColumn(
                        table_id=table_id,
                        column=Column(id=col_a, name="total", type=TypeSpec("int")),
                    ),
                )
            ),
        ),
    )
    store.append(
        "b1",
        "branch-b",
        ("root",),
        operations=(
            CompoundOperation(
                operations=(
                    AddColumn(
                        table_id=table_id,
                        column=Column(id=col_b, name="status", type=TypeSpec("string")),
                    ),
                )
            ),
        ),
    )
    store.append("m1", "branch-a", ("a1", "b1"))

    snapshot = replay(store, "m1", branch="branch-a")
    assert len(snapshot.tables) == 1
    column_names = {c.name for c in snapshot.tables[0].columns}
    assert column_names == {"total", "status"}


def test_replay_does_not_mutate_stored_history():
    # apply_operation must never hand back the same Table/Column object
    # that lives inside a Migration node's own stored operations -- a later
    # mutation (e.g. AddColumn appending a column) would otherwise bake
    # itself into that earlier CreateTable's payload permanently.
    store = DagStore()
    table_id = uuid4()
    create_op = CreateTable(table=Table(id=table_id, name="orders"))
    store.append("root", "main", (), operations=(CompoundOperation(operations=(create_op,)),))
    store.append(
        "a1",
        "main",
        ("root",),
        operations=(
            CompoundOperation(
                operations=(
                    AddColumn(
                        table_id=table_id,
                        column=Column(id=uuid4(), name="total", type=TypeSpec("int")),
                    ),
                )
            ),
        ),
    )

    replay(store, "a1", branch="main")
    replay(store, "a1", branch="main")  # replaying twice must not compound

    assert create_op.table.columns == []  # the ORIGINAL stored CreateTable is untouched
    snapshot = replay(store, "a1", branch="main")
    assert [c.name for c in snapshot.tables[0].columns] == ["total"]
