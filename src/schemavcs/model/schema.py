"""Id-bearing schema objects: Table, Column, Index, Constraint.

Identity (TableId/ColumnId/IndexId/ConstraintId) is a UUID assigned once at
creation by this tool, never derived from a database's own internal
identifiers, and never reused.

Constraint.kind excludes "not_null" on purpose: nullability lives solely on
Column.nullable. Modeling it a second time as a Constraint would let a merge's
per-identity grouping see the same fact through two different ids (column_id
vs constraint_id) and miss a real conflict between them.

Constraint.kind == "check" carries only an opaque raw_expr string. This tool
never parses or reasons about a check constraint's condition — it is passed
through to DDL verbatim.
"""

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from schemavcs.model.types import Expr, TypeSpec

ConstraintKind = Literal["unique", "foreign_key", "check"]


@dataclass
class Column:
    id: UUID
    name: str
    type: TypeSpec
    nullable: bool = True
    default: Expr | None = None
    position: int = 0


@dataclass
class Index:
    id: UUID
    name: str
    columns: list[UUID] = field(default_factory=list)
    unique: bool = False


@dataclass
class Constraint:
    id: UUID
    kind: ConstraintKind
    columns: list[UUID] = field(default_factory=list)
    references: UUID | None = None  # target TableId, only meaningful for "foreign_key"
    raw_expr: str | None = None  # only meaningful for "check"; opaque, never parsed


@dataclass
class Table:
    id: UUID
    name: str
    columns: list[Column] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
