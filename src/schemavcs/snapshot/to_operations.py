"""Turns a RawDiff (+ rename-detection results for each matched table) into
the same Operation/CompoundOperation types Phase 1's CLI verbs produce --
so the merge engine and DDL emitter built in Phase 1 need zero changes to
consume migrations authored this way.

Table-level renames are out of scope here: unmatched tables are always
treated as a plain create/drop pair, never proposed as a rename candidate.
The plan's rename-detection scenario is specifically about columns; adding
a second, parallel rename-detection pass for tables was judged
disproportionate scope for what this project actually needs to demonstrate.
"""

from dataclasses import dataclass
from uuid import uuid4

from schemavcs.dsl.raw import RawColumn, RawTable
from schemavcs.model import (
    AddColumn,
    AlterColumnDefault,
    AlterColumnNullability,
    AlterColumnType,
    Column,
    CompoundOperation,
    CreateTable,
    DropColumn,
    DropTable,
    Expr,
    Operation,
    RenameColumn,
    Table,
)
from schemavcs.rename_detect.detector import ConfirmFn, ProposalStatus, detect_renames
from schemavcs.snapshot.diff import MatchedTable, RawDiff


def _raw_column_to_column(raw: RawColumn) -> Column:
    return Column(
        id=uuid4(),
        name=raw.name,
        type=raw.type,
        nullable=raw.nullable,
        default=Expr(raw.default) if raw.default is not None else None,
        position=raw.position,
    )


def _raw_table_to_table(raw: RawTable) -> Table:
    return Table(id=uuid4(), name=raw.name, columns=[_raw_column_to_column(c) for c in raw.columns])


def _retype_ops(old_column: Column, new_column: RawColumn) -> list[Operation]:
    ops: list[Operation] = []
    if old_column.type != new_column.type:
        ops.append(
            AlterColumnType(
                column_id=old_column.id, old_type=old_column.type, new_type=new_column.type
            )
        )
    if old_column.nullable != new_column.nullable:
        ops.append(AlterColumnNullability(column_id=old_column.id, nullable=new_column.nullable))
    old_default_text = str(old_column.default) if old_column.default is not None else None
    if old_default_text != new_column.default:
        new_default = Expr(new_column.default) if new_column.default is not None else None
        ops.append(
            AlterColumnDefault(
                column_id=old_column.id, old_default=old_column.default, new_default=new_default
            )
        )
    return ops


def _matched_table_operations(matched: MatchedTable, confirm: ConfirmFn) -> list[Operation]:
    ops: list[Operation] = []

    for retype in matched.retyped_columns:
        ops.extend(_retype_ops(retype.column, retype.new_type))

    table_size = len(matched.table.columns)
    result = detect_renames(
        matched.unmatched_old_columns,
        matched.unmatched_new_columns,
        table_size=table_size,
        confirm=confirm,
        all_old_columns=matched.table.columns,
        all_new_columns=matched.raw.columns,
    )

    for proposal in result.proposals:
        if proposal.status != ProposalStatus.CONFIRMED:
            continue
        ops.append(
            RenameColumn(
                column_id=proposal.old_column.id,
                old_name=proposal.old_column.name,
                new_name=proposal.new_column.name,
            )
        )
        ops.extend(_retype_ops(proposal.old_column, proposal.new_column))

    for column in result.plain_drops:
        ops.append(DropColumn(table_id=matched.table.id, column_id=column.id))
    for raw_column in result.plain_adds:
        ops.append(AddColumn(table_id=matched.table.id, column=_raw_column_to_column(raw_column)))

    return ops


@dataclass
class GeneratedMigration:
    operations: tuple[CompoundOperation, ...]


def generate_operations(diff: RawDiff, confirm: ConfirmFn) -> GeneratedMigration:
    """Every real edit (a table create, a table drop, or everything found
    inside one matched table) becomes its own CompoundOperation -- matching
    how Phase 1's CLI verbs group operations, and keeping each edit
    independently inspectable in history."""
    compounds: list[CompoundOperation] = []

    for raw_table in diff.unmatched_new_tables:
        table = _raw_table_to_table(raw_table)
        create_and_columns: list[Operation] = [
            CreateTable(table=Table(id=table.id, name=table.name))
        ]
        for column in table.columns:
            create_and_columns.append(AddColumn(table_id=table.id, column=column))
        compounds.append(CompoundOperation(operations=tuple(create_and_columns)))

    for table in diff.unmatched_old_tables:
        compounds.append(CompoundOperation(operations=(DropTable(table_id=table.id),)))

    for matched in diff.matched_tables:
        ops = _matched_table_operations(matched, confirm)
        if ops:
            compounds.append(CompoundOperation(operations=tuple(ops)))

    return GeneratedMigration(operations=tuple(compounds))
