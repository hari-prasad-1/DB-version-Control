"""Applies a single Operation to an in-progress {table_id: Table} state.

Used by replay() to reconstruct a Snapshot from a chain of migrations, and
by the merge engine when assembling the merged result.

Create*/Add* ops store a deep copy of their payload, never the original
object -- the original still lives inside its Migration node, part of the
DagStore's permanent history, and later ops (AddColumn appending to
`.columns`, RenameColumn setting `.name`, etc.) mutate the in-progress
state in place. Without the copy that mutation silently corrupts the
stored operation itself.

Every operation except CreateTable/DropTable silently no-ops when its
target table/column no longer exists. This matters for merges: replaying a
merge node walks BOTH parents, and one branch's drop can legitimately be
resolved to "win" over the other branch's mutation/add of the same object
(cross_object_pass + resolve.py's corrective drop) -- by the time that
mutation/add is reached during replay, the object it targets is already
gone, and that's the correct, already-decided outcome, not a bug. A missing
CreateTable/DropTable target IS still a bug (a revision pointing at a
table id that was never created at all), so those two stay strict.
"""

import copy
from uuid import UUID

from schemavcs.model import (
    AddColumn,
    AddConstraint,
    AddIndex,
    AlterColumnDefault,
    AlterColumnNullability,
    AlterColumnType,
    Column,
    CreateTable,
    DropColumn,
    DropConstraint,
    DropIndex,
    DropTable,
    Operation,
    RenameColumn,
    RenameIndex,
    Table,
)


def _find_column(table: Table, column_id: UUID) -> Column | None:
    for column in table.columns:
        if column.id == column_id:
            return column
    return None


def _table_owning_column(tables_by_id: dict[UUID, Table], column_id: UUID) -> Table | None:
    for table in tables_by_id.values():
        for column in table.columns:
            if column.id == column_id:
                return table
    return None


def apply_operation(tables_by_id: dict[UUID, Table], op: Operation) -> None:
    match op:
        case CreateTable(table=table):
            tables_by_id[table.id] = copy.deepcopy(table)
        case DropTable(table_id=table_id):
            del tables_by_id[table_id]
        case AddColumn(table_id=table_id, column=column):
            if table_id in tables_by_id:
                tables_by_id[table_id].columns.append(copy.deepcopy(column))
        case DropColumn(table_id=table_id, column_id=column_id):
            table = tables_by_id.get(table_id)
            if table is not None:
                table.columns = [c for c in table.columns if c.id != column_id]
        case RenameColumn(column_id=column_id, new_name=new_name):
            table = _table_owning_column(tables_by_id, column_id)
            column = _find_column(table, column_id) if table is not None else None
            if column is not None:
                column.name = new_name
        case AlterColumnType(column_id=column_id, new_type=new_type):
            table = _table_owning_column(tables_by_id, column_id)
            column = _find_column(table, column_id) if table is not None else None
            if column is not None:
                column.type = new_type
        case AlterColumnNullability(column_id=column_id, nullable=nullable):
            table = _table_owning_column(tables_by_id, column_id)
            column = _find_column(table, column_id) if table is not None else None
            if column is not None:
                column.nullable = nullable
        case AlterColumnDefault(column_id=column_id, new_default=new_default):
            table = _table_owning_column(tables_by_id, column_id)
            column = _find_column(table, column_id) if table is not None else None
            if column is not None:
                column.default = new_default
        case AddIndex(table_id=table_id, index=index):
            if table_id in tables_by_id:
                tables_by_id[table_id].indexes.append(copy.deepcopy(index))
        case DropIndex(index_id=index_id):
            for table in tables_by_id.values():
                table.indexes = [i for i in table.indexes if i.id != index_id]
        case RenameIndex(index_id=index_id, new_name=new_name):
            for table in tables_by_id.values():
                for index in table.indexes:
                    if index.id == index_id:
                        index.name = new_name
                        return
        case AddConstraint(table_id=table_id, constraint=constraint):
            if table_id in tables_by_id:
                tables_by_id[table_id].constraints.append(copy.deepcopy(constraint))
        case DropConstraint(constraint_id=constraint_id):
            for table in tables_by_id.values():
                table.constraints = [c for c in table.constraints if c.id != constraint_id]
        case _:
            raise TypeError(f"unhandled operation variant: {type(op).__name__}")
