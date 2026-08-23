"""Applies a single Operation to an in-progress {table_id: Table} state.

Used by replay() to reconstruct a Snapshot from a chain of migrations, and
by the merge engine when assembling the merged result.
"""

from uuid import UUID

from schemavcs.model import (
    AddColumn,
    AddConstraint,
    AddIndex,
    AlterColumnDefault,
    AlterColumnNullability,
    AlterColumnType,
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


def _find_column(table: Table, column_id: UUID):
    for column in table.columns:
        if column.id == column_id:
            return column
    raise KeyError(column_id)


def _table_owning_column(tables_by_id: dict[UUID, Table], column_id: UUID) -> Table:
    for table in tables_by_id.values():
        for column in table.columns:
            if column.id == column_id:
                return table
    raise KeyError(column_id)


def apply_operation(tables_by_id: dict[UUID, Table], op: Operation) -> None:
    match op:
        case CreateTable(table=table):
            tables_by_id[table.id] = table
        case DropTable(table_id=table_id):
            del tables_by_id[table_id]
        case AddColumn(table_id=table_id, column=column):
            tables_by_id[table_id].columns.append(column)
        case DropColumn(table_id=table_id, column_id=column_id):
            table = tables_by_id[table_id]
            table.columns = [c for c in table.columns if c.id != column_id]
        case RenameColumn(column_id=column_id, new_name=new_name):
            table = _table_owning_column(tables_by_id, column_id)
            _find_column(table, column_id).name = new_name
        case AlterColumnType(column_id=column_id, new_type=new_type):
            table = _table_owning_column(tables_by_id, column_id)
            _find_column(table, column_id).type = new_type
        case AlterColumnNullability(column_id=column_id, nullable=nullable):
            table = _table_owning_column(tables_by_id, column_id)
            _find_column(table, column_id).nullable = nullable
        case AlterColumnDefault(column_id=column_id, new_default=new_default):
            table = _table_owning_column(tables_by_id, column_id)
            _find_column(table, column_id).default = new_default
        case AddIndex(table_id=table_id, index=index):
            tables_by_id[table_id].indexes.append(index)
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
            tables_by_id[table_id].constraints.append(constraint)
        case DropConstraint(constraint_id=constraint_id):
            for table in tables_by_id.values():
                table.constraints = [c for c in table.constraints if c.id != constraint_id]
        case _:
            raise TypeError(f"unhandled operation variant: {type(op).__name__}")
