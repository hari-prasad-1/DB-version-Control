"""The Operation ADT — the unit stored in a migration's operation list.

CompoundOperation groups operations that share one edit's intent (e.g.
RenameColumn + AlterColumnType on the same column_id, authored as one CLI
invocation or detected as one rename+retype).
"""

from dataclasses import dataclass, field
from uuid import UUID

from schemavcs.model.schema import Column, Constraint, Index, Table
from schemavcs.model.types import Expr, TypeSpec


@dataclass(frozen=True)
class CreateTable:
    table: Table


@dataclass(frozen=True)
class DropTable:
    table_id: UUID


@dataclass(frozen=True)
class AddColumn:
    table_id: UUID
    column: Column


@dataclass(frozen=True)
class DropColumn:
    table_id: UUID
    column_id: UUID


@dataclass(frozen=True)
class RenameColumn:
    column_id: UUID
    old_name: str
    new_name: str


@dataclass(frozen=True)
class AlterColumnType:
    column_id: UUID
    old_type: TypeSpec
    new_type: TypeSpec


@dataclass(frozen=True)
class AlterColumnNullability:
    column_id: UUID
    nullable: bool


@dataclass(frozen=True)
class AlterColumnDefault:
    column_id: UUID
    old_default: Expr | None
    new_default: Expr | None


@dataclass(frozen=True)
class AddIndex:
    index: Index


@dataclass(frozen=True)
class DropIndex:
    index_id: UUID


@dataclass(frozen=True)
class RenameIndex:
    index_id: UUID
    old_name: str
    new_name: str


@dataclass(frozen=True)
class AddConstraint:
    constraint: Constraint


@dataclass(frozen=True)
class DropConstraint:
    constraint_id: UUID


Operation = (
    CreateTable
    | DropTable
    | AddColumn
    | DropColumn
    | RenameColumn
    | AlterColumnType
    | AlterColumnNullability
    | AlterColumnDefault
    | AddIndex
    | DropIndex
    | RenameIndex
    | AddConstraint
    | DropConstraint
)


@dataclass(frozen=True)
class CompoundOperation:
    operations: tuple[Operation, ...] = field(default_factory=tuple)
