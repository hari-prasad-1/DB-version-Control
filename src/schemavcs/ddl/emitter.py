"""Emits SQL text for a dependency-ordered list of operations.

Name resolution (table/column/index/constraint id -> name) reads the schema
state as it exists immediately BEFORE each operation, then applies that
operation to advance the state before resolving the next one -- so a
CreateTable earlier in the same batch is visible by name to an AddColumn
later in it, and a rename is visible to whatever comes after it.
"""

from uuid import UUID

from schemavcs.dag.apply import apply_operation
from schemavcs.ddl.toposort import toposort
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


def emit_ddl(
    operations: tuple[Operation, ...], tables_by_id: dict[UUID, Table] | None = None
) -> str:
    """`tables_by_id` is the schema state the batch starts from (empty dict
    for a from-scratch batch such as the demo's initial CreateTable); it is
    mutated in place as operations are applied, exactly like replay()."""
    state = tables_by_id if tables_by_id is not None else {}
    ordered = toposort(operations)

    statements = []
    for op in ordered:
        statements.append(_emit_one(op, state))
        apply_operation(state, op)

    return "\n".join(statements)


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


def _table_owning_index(tables_by_id: dict[UUID, Table], index_id: UUID) -> Table:
    for table in tables_by_id.values():
        for index in table.indexes:
            if index.id == index_id:
                return table
    raise KeyError(index_id)


def _table_owning_constraint(tables_by_id: dict[UUID, Table], constraint_id: UUID) -> Table:
    for table in tables_by_id.values():
        for constraint in table.constraints:
            if constraint.id == constraint_id:
                return table
    raise KeyError(constraint_id)


def _column_def(column) -> str:
    parts = [column.name, str(column.type)]
    if not column.nullable:
        parts.append("NOT NULL")
    if column.default is not None:
        parts.append(f"DEFAULT {column.default}")
    return " ".join(parts)


def _constraint_def(constraint, table: Table) -> str:
    column_names = [_find_column(table, cid).name for cid in constraint.columns]
    if constraint.kind == "unique":
        return f"UNIQUE ({', '.join(column_names)})"
    if constraint.kind == "check":
        return f"CHECK ({constraint.raw_expr})"
    raise ValueError("foreign_key constraints are emitted via _emit_one, not _constraint_def")


def _emit_one(op: Operation, tables_by_id: dict[UUID, Table]) -> str:
    match op:
        case CreateTable(table=table):
            columns_sql = ", ".join(
                _column_def(c) for c in sorted(table.columns, key=lambda c: c.position)
            )
            return (
                f"CREATE TABLE {table.name} ({columns_sql});"
                if columns_sql
                else f"CREATE TABLE {table.name} ();"
            )

        case DropTable(table_id=table_id):
            return f"DROP TABLE {tables_by_id[table_id].name};"

        case AddColumn(table_id=table_id, column=column):
            return f"ALTER TABLE {tables_by_id[table_id].name} ADD COLUMN {_column_def(column)};"

        case DropColumn(table_id=table_id, column_id=column_id):
            table = tables_by_id[table_id]
            return f"ALTER TABLE {table.name} DROP COLUMN {_find_column(table, column_id).name};"

        case RenameColumn(column_id=column_id, old_name=old_name, new_name=new_name):
            table = _table_owning_column(tables_by_id, column_id)
            return f"ALTER TABLE {table.name} RENAME COLUMN {old_name} TO {new_name};"

        case AlterColumnType(column_id=column_id, new_type=new_type):
            table = _table_owning_column(tables_by_id, column_id)
            column_name = _find_column(table, column_id).name
            return f"ALTER TABLE {table.name} ALTER COLUMN {column_name} TYPE {new_type};"

        case AlterColumnNullability(column_id=column_id, nullable=nullable):
            table = _table_owning_column(tables_by_id, column_id)
            column_name = _find_column(table, column_id).name
            action = "DROP NOT NULL" if nullable else "SET NOT NULL"
            return f"ALTER TABLE {table.name} ALTER COLUMN {column_name} {action};"

        case AlterColumnDefault(column_id=column_id, new_default=new_default):
            table = _table_owning_column(tables_by_id, column_id)
            column_name = _find_column(table, column_id).name
            if new_default is None:
                return f"ALTER TABLE {table.name} ALTER COLUMN {column_name} DROP DEFAULT;"
            return f"ALTER TABLE {table.name} ALTER COLUMN {column_name} SET DEFAULT {new_default};"

        case AddIndex(table_id=table_id, index=index):
            table = tables_by_id[table_id]
            column_names = [_find_column(table, cid).name for cid in index.columns]
            unique = "UNIQUE " if index.unique else ""
            return (
                f"CREATE {unique}INDEX {index.name} ON {table.name} "
                f"({', '.join(column_names)});"
            )

        case DropIndex(index_id=index_id):
            table = _table_owning_index(tables_by_id, index_id)
            index_name = next(i.name for i in table.indexes if i.id == index_id)
            return f"DROP INDEX {index_name};"

        case RenameIndex(index_id=index_id, old_name=old_name, new_name=new_name):
            return f"ALTER INDEX {old_name} RENAME TO {new_name};"

        case AddConstraint(table_id=table_id, constraint=constraint):
            table = tables_by_id[table_id]
            if constraint.kind == "foreign_key":
                assert (
                    constraint.references is not None
                ), "foreign_key constraint has no target table"
                column_names = [_find_column(table, cid).name for cid in constraint.columns]
                ref_table = tables_by_id[constraint.references]
                return (
                    f"ALTER TABLE {table.name} ADD FOREIGN KEY ({', '.join(column_names)}) "
                    f"REFERENCES {ref_table.name};"
                )
            return f"ALTER TABLE {table.name} ADD {_constraint_def(constraint, table)};"

        case DropConstraint(constraint_id=constraint_id):
            # Constraint has no name field in the data model (see
            # model/schema.py) -- Postgres requires a name to drop one, so
            # this emits the raw id as a placeholder rather than inventing a
            # naming scheme this plan never locked.
            table = _table_owning_constraint(tables_by_id, constraint_id)
            return f"ALTER TABLE {table.name} DROP CONSTRAINT {constraint_id};"

        case _:
            raise TypeError(f"unhandled operation variant: {type(op).__name__}")
