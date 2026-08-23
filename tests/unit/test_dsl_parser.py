from schemavcs.dsl import (
    RawCheck,
    RawColumn,
    RawForeignKey,
    RawIndex,
    RawTable,
    RawUnique,
    parse,
)
from schemavcs.model import TypeSpec


def test_parse_empty_text():
    assert parse("") == []


def test_parse_single_table_no_members():
    tables = parse("table users {\n}\n")
    assert tables == [RawTable(name="users")]


def test_parse_columns_with_types_and_params():
    tables = parse(
        """
        table users {
          column id: uuid
          column email: string(255)
        }
        """
    )
    assert tables[0].columns == (
        RawColumn(name="id", type=TypeSpec("uuid"), position=0),
        RawColumn(name="email", type=TypeSpec("string", (255,)), position=1),
    )


def test_parse_not_null_modifier():
    tables = parse("table users {\n  column email: string(255) not_null\n}\n")
    assert tables[0].columns[0].nullable is False


def test_parse_no_modifier_means_nullable():
    tables = parse("table users {\n  column notes: text\n}\n")
    assert tables[0].columns[0].nullable is True


def test_parse_default_string_value():
    tables = parse('table users {\n  column plan: string(50) default="free"\n}\n')
    assert tables[0].columns[0].default == "free"


def test_parse_default_and_not_null_together():
    tables = parse('table users {\n  column plan: string(50) not_null default="free"\n}\n')
    column = tables[0].columns[0]
    assert column.nullable is False
    assert column.default == "free"


def test_parse_column_position_matches_file_order():
    tables = parse(
        """
        table users {
          column c: int
          column a: int
          column b: int
        }
        """
    )
    positions = {c.name: c.position for c in tables[0].columns}
    assert positions == {"c": 0, "a": 1, "b": 2}


def test_parse_index_with_unique():
    tables = parse("table users {\n  index idx_email on (email) unique\n}\n")
    assert tables[0].indexes == (RawIndex(name="idx_email", columns=("email",), unique=True),)


def test_parse_index_without_unique():
    tables = parse("table users {\n  index idx_email on (email)\n}\n")
    assert tables[0].indexes == (RawIndex(name="idx_email", columns=("email",), unique=False),)


def test_parse_index_multiple_columns():
    tables = parse("table users {\n  index idx_name on (first, last)\n}\n")
    assert tables[0].indexes[0].columns == ("first", "last")


def test_parse_foreign_key():
    tables = parse("table users {\n  foreign_key (org_id) references organizations\n}\n")
    assert tables[0].foreign_keys == (
        RawForeignKey(columns=("org_id",), references_table="organizations"),
    )


def test_parse_unique_constraint():
    tables = parse("table users {\n  unique (email)\n}\n")
    assert tables[0].uniques == (RawUnique(columns=("email",)),)


def test_parse_check_constraint():
    tables = parse("table users {\n  check price > 0\n}\n")
    assert tables[0].checks == (RawCheck(raw_expr="price > 0"),)


def test_parse_multiple_tables():
    tables = parse(
        """
        table users {
          column id: uuid
        }

        table organizations {
          column id: uuid
        }
        """
    )
    assert [t.name for t in tables] == ["users", "organizations"]


def test_round_trips_through_render():
    from uuid import uuid4

    from schemavcs.dsl.render import render_snapshot
    from schemavcs.model import Column, Snapshot, Table

    table_id = uuid4()
    snapshot = Snapshot(
        branch="main",
        revision_id="root",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[
                    Column(id=uuid4(), name="id", type=TypeSpec("uuid"), position=0),
                    Column(
                        id=uuid4(),
                        name="email",
                        type=TypeSpec("string", (255,)),
                        nullable=False,
                        position=1,
                    ),
                ],
            )
        ],
    )
    rendered = render_snapshot(snapshot)
    parsed = parse(rendered)

    assert len(parsed) == 1
    assert parsed[0].name == "users"
    assert [c.name for c in parsed[0].columns] == ["id", "email"]
    assert parsed[0].columns[1].nullable is False
