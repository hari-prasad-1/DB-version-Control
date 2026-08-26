"""Resolves human-typed table/column/index names to their tracked ids,
against a branch's current (replayed) schema state."""

from uuid import UUID

from schemavcs.model import Snapshot, Table


class UnknownTableError(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"table {name!r} does not exist")


class UnknownColumnError(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"column {name!r} does not exist")


class UnknownIndexError(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"index {name!r} does not exist")


def find_table(snapshot: Snapshot, name: str) -> Table:
    for table in snapshot.tables:
        if table.name == name:
            return table
    raise UnknownTableError(name)


def find_column_id(table: Table, name: str) -> UUID:
    for column in table.columns:
        if column.name == name:
            return column.id
    raise UnknownColumnError(name)


def find_index_id(table: Table, name: str) -> UUID:
    for index in table.indexes:
        if index.name == name:
            return index.id
    raise UnknownIndexError(name)
