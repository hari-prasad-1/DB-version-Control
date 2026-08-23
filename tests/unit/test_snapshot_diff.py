from uuid import uuid4

from schemavcs.dsl.raw import RawColumn, RawTable
from schemavcs.model import Column, Snapshot, Table, TypeSpec
from schemavcs.snapshot.diff import diff_snapshot


def test_matched_table_unchanged_columns():
    table_id, col_id = uuid4(), uuid4()
    old = Snapshot(
        branch="main",
        revision_id="r1",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[Column(id=col_id, name="email", type=TypeSpec("string", (255,)))],
            )
        ],
    )
    new_raw = [
        RawTable(
            name="users",
            columns=(RawColumn(name="email", type=TypeSpec("string", (255,))),),
        )
    ]

    diff = diff_snapshot(old, new_raw)

    assert len(diff.matched_tables) == 1
    matched = diff.matched_tables[0]
    assert matched.unchanged_columns == [old.tables[0].columns[0]]
    assert matched.retyped_columns == []
    assert matched.unmatched_old_columns == []
    assert matched.unmatched_new_columns == []


def test_unmatched_new_table_is_a_plain_add_candidate():
    old = Snapshot(branch="main", revision_id="r1", tables=[])
    new_raw = [RawTable(name="orders")]

    diff = diff_snapshot(old, new_raw)

    assert diff.matched_tables == []
    assert diff.unmatched_old_tables == []
    assert diff.unmatched_new_tables == [RawTable(name="orders")]


def test_unmatched_old_table_is_a_plain_drop_candidate():
    table_id = uuid4()
    old = Snapshot(
        branch="main", revision_id="r1", tables=[Table(id=table_id, name="legacy_reports")]
    )
    new_raw: list[RawTable] = []

    diff = diff_snapshot(old, new_raw)

    assert diff.matched_tables == []
    assert diff.unmatched_new_tables == []
    assert diff.unmatched_old_tables == [old.tables[0]]


def test_same_name_different_type_is_a_retype_not_unmatched():
    # the plan's own point: a same-name type change must never leak into
    # the rename-detection candidate pool -- there's no ambiguity here.
    table_id, col_id = uuid4(), uuid4()
    old = Snapshot(
        branch="main",
        revision_id="r1",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[Column(id=col_id, name="subscription_type", type=TypeSpec("string"))],
            )
        ],
    )
    new_raw = [
        RawTable(
            name="users",
            columns=(RawColumn(name="subscription_type", type=TypeSpec("enum")),),
        )
    ]

    diff = diff_snapshot(old, new_raw)

    matched = diff.matched_tables[0]
    assert matched.unmatched_old_columns == []
    assert matched.unmatched_new_columns == []
    assert len(matched.retyped_columns) == 1
    assert matched.retyped_columns[0].column.id == col_id
    assert matched.retyped_columns[0].new_type.type == TypeSpec("enum")


def test_column_deleted_and_added_are_unmatched_candidates():
    # the rename-detection case (sub-phase 2.2/2.3): different names on
    # each side means genuine ambiguity, not something this sub-phase
    # should try to resolve.
    table_id, col_id = uuid4(), uuid4()
    old = Snapshot(
        branch="main",
        revision_id="r1",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[Column(id=col_id, name="subscription_type", type=TypeSpec("string"))],
            )
        ],
    )
    new_raw = [
        RawTable(name="users", columns=(RawColumn(name="plan_type", type=TypeSpec("enum")),))
    ]

    diff = diff_snapshot(old, new_raw)

    matched = diff.matched_tables[0]
    assert matched.retyped_columns == []
    assert [c.id for c in matched.unmatched_old_columns] == [col_id]
    assert [c.name for c in matched.unmatched_new_columns] == ["plan_type"]


def test_nullability_change_alone_is_a_retype():
    table_id, col_id = uuid4(), uuid4()
    old = Snapshot(
        branch="main",
        revision_id="r1",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[Column(id=col_id, name="email", type=TypeSpec("string"), nullable=True)],
            )
        ],
    )
    new_raw = [
        RawTable(
            name="users",
            columns=(RawColumn(name="email", type=TypeSpec("string"), nullable=False),),
        )
    ]

    diff = diff_snapshot(old, new_raw)

    matched = diff.matched_tables[0]
    assert matched.unchanged_columns == []
    assert len(matched.retyped_columns) == 1


def test_multiple_tables_split_correctly():
    table_id = uuid4()
    old = Snapshot(
        branch="main",
        revision_id="r1",
        tables=[Table(id=table_id, name="users"), Table(id=uuid4(), name="legacy")],
    )
    new_raw = [RawTable(name="users"), RawTable(name="organizations")]

    diff = diff_snapshot(old, new_raw)

    assert len(diff.matched_tables) == 1
    assert diff.matched_tables[0].table.name == "users"
    assert [t.name for t in diff.unmatched_old_tables] == ["legacy"]
    assert [t.name for t in diff.unmatched_new_tables] == ["organizations"]
