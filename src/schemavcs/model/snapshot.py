"""Per-branch schema state: the set of tables at a given revision."""

from dataclasses import dataclass, field

from schemavcs.model.schema import Table


@dataclass
class Snapshot:
    branch: str
    revision_id: str | None  # None only for the empty snapshot before any migration
    tables: list[Table] = field(default_factory=list)
