"""Renders a Snapshot's tables into the .schema DSL text format.

This is the writer half of the DSL round-trip — the parser (dsl/parser.py)
that reads this format back is built in Phase 2. Column order in the
rendered text always matches Column.position, since position is itself
derived from file order when the parser eventually reads it back.
"""

from uuid import UUID

from schemavcs.model import Column, Constraint, Index, Snapshot, Table


def render_snapshot(snapshot: Snapshot) -> str:
    if not snapshot.tables:
        return ""
    tables_by_id = {t.id: t for t in snapshot.tables}
    return "\n\n".join(_render_table(table, tables_by_id) for table in snapshot.tables) + "\n"


def _render_table(table: Table, tables_by_id: dict) -> str:
    lines = [f"table {table.name} {{"]
    for column in sorted(table.columns, key=lambda c: c.position):
        lines.append(f"  {_render_column(column)}")
    for index in table.indexes:
        lines.append(f"  {_render_index(index, table)}")
    for constraint in table.constraints:
        rendered = _render_constraint(constraint, table, tables_by_id)
        if rendered:
            lines.append(f"  {rendered}")
    lines.append("}")
    return "\n".join(lines)


def _render_column(column: Column) -> str:
    modifiers = []
    if not column.nullable:
        modifiers.append("not_null")
    if column.default is not None:
        modifiers.append(f"default={column.default}")
    modifier_text = f" {' '.join(modifiers)}" if modifiers else ""
    return f"column {column.name}: {column.type}{modifier_text}"


def _render_index(index: Index, table: Table) -> str:
    column_names = [_column_name(table, cid) for cid in index.columns]
    unique_text = " unique" if index.unique else ""
    return f"index {index.name} on ({', '.join(column_names)}){unique_text}"


def _render_constraint(constraint: Constraint, table: Table, tables_by_id: dict) -> str | None:
    if constraint.kind == "foreign_key":
        column_names = [_column_name(table, cid) for cid in constraint.columns]
        ref_table = tables_by_id[constraint.references]
        return f"foreign_key ({', '.join(column_names)}) references {ref_table.name}"
    if constraint.kind == "unique":
        column_names = [_column_name(table, cid) for cid in constraint.columns]
        return f"unique ({', '.join(column_names)})"
    if constraint.kind == "check":
        return f"check {constraint.raw_expr}"
    return None


def _column_name(table: Table, column_id: UUID) -> str:
    for column in table.columns:
        if column.id == column_id:
            return column.name
    raise KeyError(column_id)
