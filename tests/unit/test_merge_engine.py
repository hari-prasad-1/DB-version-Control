from uuid import uuid4

import pytest

from schemavcs.dag import DagStore
from schemavcs.dag.errors import NothingToMergeError
from schemavcs.merge.classify import ClassifiedGroup
from schemavcs.merge.engine import merge
from schemavcs.merge.resolve import HumanConfirmationToken
from schemavcs.model import (
    AddColumn,
    Column,
    CompoundOperation,
    CreateTable,
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

    merged_ops = [op for compound in result.migration.operations for op in compound.operations]
    added_names = {op.column.name for op in merged_ops if isinstance(op, AddColumn)}
    assert added_names == {"total", "status"}


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
