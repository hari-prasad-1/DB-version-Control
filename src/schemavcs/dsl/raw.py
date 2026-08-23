"""Plain, id-less values parsed straight from .schema text -- no UUIDs, no
identity, no notion of "this is the same column as before." Matching these
up against a tracked Snapshot (exact-name match, then similarity-scored
rename detection for what's left over) is snapshot_diff's job, not the
parser's -- this module only turns text into structured data.
"""

from dataclasses import dataclass, field

from schemavcs.model import TypeSpec


@dataclass(frozen=True)
class RawColumn:
    name: str
    type: TypeSpec
    nullable: bool = True
    default: str | None = None
    position: int = 0


@dataclass(frozen=True)
class RawIndex:
    name: str
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True)
class RawForeignKey:
    columns: tuple[str, ...]
    references_table: str


@dataclass(frozen=True)
class RawUnique:
    columns: tuple[str, ...]


@dataclass(frozen=True)
class RawCheck:
    raw_expr: str


@dataclass(frozen=True)
class RawTable:
    name: str
    columns: tuple[RawColumn, ...] = field(default_factory=tuple)
    indexes: tuple[RawIndex, ...] = field(default_factory=tuple)
    foreign_keys: tuple[RawForeignKey, ...] = field(default_factory=tuple)
    uniques: tuple[RawUnique, ...] = field(default_factory=tuple)
    checks: tuple[RawCheck, ...] = field(default_factory=tuple)
