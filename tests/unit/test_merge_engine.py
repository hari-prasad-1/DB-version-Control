from uuid import uuid4

import pytest

from schemavcs.dag import DagStore, replay
from schemavcs.dag.errors import NothingToMergeError
from schemavcs.merge.classify import ClassifiedGroup
from schemavcs.merge.engine import merge
from schemavcs.merge.resolve import HumanConfirmationToken, _corrective_drop_for
from schemavcs.model import (
    AddColumn,
    Column,
    CompoundOperation,
    CreateTable,
    DropTable,
    RenameColumn,
    Table,
    TypeSpec,
)


def _scripted_confirm_keep_a(group: ClassifiedGroup) -> HumanConfirmationToken:
    return HumanConfirmationToken(
        group_id=group.group.identity_id,
        chosen_resolution=tuple(group.group.ops_a),
        _nonce=uuid4(),
    )


def test_merge_self_raises_nothing_to_merge():
    store = DagStore()
    store.append("root", "main", ())
    with pytest.raises(NothingToMergeError):
        merge(store, "main", "main")


def test_merge_fast_forward_advances_pointer_without_new_node():
    store = DagStore()
    store.append("root", "main", ())
    store.append("b1", "branch-b", ("root",))

    result = merge(store, "main", "branch-b")

    assert result.fast_forward is True
    assert store.head("main") == "b1"


def test_merge_source_already_ancestor_raises_nothing_to_merge():
    # branch-b's head (root) is already an ancestor of main's head (a1) --
    # merging branch-b into main would bring in nothing new.
    store = DagStore()
    store.append("root", "main", ())
    store.append("a1", "main", ("root",))
    store.set_head("branch-b", "root")

    with pytest.raises(NothingToMergeError):
        merge(store, "main", "branch-b")


def test_merge_diverged_branches_auto_resolves_non_overlapping_columns():
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
        "main",
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

    result = merge(store, "main", "branch-b")

    assert result.fast_forward is False
    assert result.conflicts_resolved == 0
    assert store.head("main") == result.migration.id
    assert store.head("branch-b") == "b1"  # asymmetric: only target advances

    # UNRELATED groups aren't re-stored in the merge node itself -- each is
    # already reachable through its own parent chain -- so the final state
    # is only checkable by replaying, not by inspecting the merge node's
    # own operations directly.
    snapshot = replay(store, result.migration.id, branch="main")
    column_names = {c.name for c in snapshot.tables[0].columns}
    assert column_names == {"total", "status"}


def test_merge_conflict_requires_confirm_and_uses_chosen_resolution():
    store = DagStore()
    col_id = uuid4()

    store.append("root", "main", ())
    store.append(
        "a1",
        "main",
        ("root",),
        operations=(
            CompoundOperation(
                operations=(RenameColumn(column_id=col_id, old_name="x", new_name="y"),)
            ),
        ),
    )
    store.append(
        "b1",
        "branch-b",
        ("root",),
        operations=(
            CompoundOperation(
                operations=(RenameColumn(column_id=col_id, old_name="x", new_name="z"),)
            ),
        ),
    )

    result = merge(store, "main", "branch-b", confirm=_scripted_confirm_keep_a)

    assert result.conflicts_resolved == 1
    merged_ops = [op for compound in result.migration.operations for op in compound.operations]
    assert merged_ops == [RenameColumn(column_id=col_id, old_name="x", new_name="y")]


def test_merge_with_drop_table_on_one_side_replays_without_double_apply():
    # regression: a merge node must not re-store an UNRELATED op that's
    # already reachable through its own parent chain -- doing so made
    # replay() try to delete an already-deleted table (or insert an
    # already-inserted one), a KeyError crash on ANY merge involving a
    # create/drop-type op on either side, not just genuine conflicts. Two
    # tables, dropped/added independently and unrelated to each other, so
    # this exercises the UNRELATED path without also raising a real
    # cross-object conflict (that has its own dedicated test below).
    store = DagStore()
    dropped_table_id, other_table_id = uuid4(), uuid4()

    store.append(
        "root",
        "main",
        (),
        operations=(
            CompoundOperation(
                operations=(
                    CreateTable(table=Table(id=dropped_table_id, name="legacy")),
                    CreateTable(table=Table(id=other_table_id, name="orders")),
                )
            ),
        ),
    )
    store.append(
        "a1",
        "main",
        ("root",),
        operations=(
            CompoundOperation(
                operations=(
                    AddColumn(
                        table_id=other_table_id,
                        column=Column(id=uuid4(), name="total", type=TypeSpec("int")),
                    ),
                )
            ),
        ),
    )
    store.append(
        "b1",
        "branch-b",
        ("root",),
        operations=(CompoundOperation(operations=(DropTable(table_id=dropped_table_id),)),),
    )

    result = merge(store, "main", "branch-b")

    snapshot = replay(store, result.migration.id, branch="main")
    table_names = {t.name for t in snapshot.tables}
    assert table_names == {"orders"}
    orders = next(t for t in snapshot.tables if t.name == "orders")
    assert {c.name for c in orders.columns} == {"total"}


def test_merge_cross_object_conflict_resolves_by_dropping_the_dependent_column():
    # branch-a drops `orders`; branch-b independently adds a column to it.
    # The only mechanically sound resolution is "the drop wins, the
    # dependent column drops with it" -- confirm_from_cli's cross-object
    # path takes exactly that, with no a/b/both choice.
    store = DagStore()
    table_id = uuid4()

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
        "main",
        ("root",),
        operations=(CompoundOperation(operations=(DropTable(table_id=table_id),)),),
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
                        column=Column(id=uuid4(), name="total", type=TypeSpec("int")),
                    ),
                )
            ),
        ),
    )

    # exercise the real corrective-drop path directly rather than through
    # stdin (confirm_from_cli blocks on input()); the acknowledgment prompt
    # itself is not the behavior under test.
    def _acknowledge(group):
        assert group.cross_object_referencing_op is not None
        corrective = _corrective_drop_for(group.cross_object_referencing_op)
        return HumanConfirmationToken(
            group_id=group.group.identity_id, chosen_resolution=(corrective,), _nonce=uuid4()
        )

    result = merge(store, "main", "branch-b", confirm=_acknowledge)

    snapshot = replay(store, result.migration.id, branch="main")
    assert snapshot.tables == []


def test_merge_result_has_two_parents():
    store = DagStore()
    table_id = uuid4()
    store.append(
        "root",
        "main",
        (),
        operations=(
            CompoundOperation(operations=(CreateTable(table=Table(id=table_id, name="orders")),)),
        ),
    )
    store.append("a1", "main", ("root",))
    store.append("b1", "branch-b", ("root",))

    result = merge(store, "main", "branch-b")

    assert result.migration.parents == ("a1", "b1")
    assert result.migration.is_merge is True
