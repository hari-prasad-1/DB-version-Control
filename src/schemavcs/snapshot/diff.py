"""Diffs a tracked Snapshot against freshly-parsed RawTables.

Matches by exact name first -- names are the strongest, cheapest signal
available, and most edits don't touch them at all. Only what's left over
after exact-name matching (a column that vanished under one name while a
different column appeared under another) is genuinely ambiguous, and gets
passed on to the similarity-scored rename detector (sub-phase 2.2/2.3).

A column matched by exact name that changed type is a plain retype, not a
rename candidate -- there's no ambiguity about identity here (the name
didn't change), so it must never leak into the rename-detection pool.
"""

from dataclasses import dataclass, field

from schemavcs.dsl.raw import RawColumn, RawTable
from schemavcs.model import Column, Snapshot, Table


@dataclass
class ColumnRetype:
    column: Column
    new_type: RawColumn


@dataclass
class MatchedTable:
    table: Table
    raw: RawTable
    unchanged_columns: list[Column] = field(default_factory=list)
    retyped_columns: list[ColumnRetype] = field(default_factory=list)
    unmatched_old_columns: list[Column] = field(default_factory=list)
    unmatched_new_columns: list[RawColumn] = field(default_factory=list)


@dataclass
class RawDiff:
    matched_tables: list[MatchedTable] = field(default_factory=list)
    unmatched_old_tables: list[Table] = field(default_factory=list)
    unmatched_new_tables: list[RawTable] = field(default_factory=list)


def diff_snapshot(old: Snapshot, new_raw: list[RawTable]) -> RawDiff:
    old_by_name = {t.name: t for t in old.tables}
    new_by_name = {t.name: t for t in new_raw}

    matched_names = set(old_by_name) & set(new_by_name)
    diff = RawDiff(
        unmatched_old_tables=[t for name, t in old_by_name.items() if name not in matched_names],
        unmatched_new_tables=[t for name, t in new_by_name.items() if name not in matched_names],
    )
    for name in matched_names:
        diff.matched_tables.append(_diff_table(old_by_name[name], new_by_name[name]))
    return diff


def _diff_table(old_table: Table, new_table: RawTable) -> MatchedTable:
    old_by_name = {c.name: c for c in old_table.columns}
    new_by_name = {c.name: c for c in new_table.columns}
    matched_names = set(old_by_name) & set(new_by_name)

    matched = MatchedTable(
        table=old_table,
        raw=new_table,
        unmatched_old_columns=[c for name, c in old_by_name.items() if name not in matched_names],
        unmatched_new_columns=[c for name, c in new_by_name.items() if name not in matched_names],
    )
    for name in matched_names:
        old_column = old_by_name[name]
        new_column = new_by_name[name]
        if _same_shape(old_column, new_column):
            matched.unchanged_columns.append(old_column)
        else:
            matched.retyped_columns.append(ColumnRetype(column=old_column, new_type=new_column))
    return matched


def _same_shape(old_column: Column, new_column: RawColumn) -> bool:
    return (
        old_column.type == new_column.type
        and old_column.nullable == new_column.nullable
        and (old_column.default is None) == (new_column.default is None)
        and (old_column.default is None or str(old_column.default) == new_column.default)
    )
