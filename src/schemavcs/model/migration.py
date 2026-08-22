"""Migration: one node in the DAG-shaped revision history.

id is a content hash/uuid, never a sequential integer or timestamp — neither
carries causal meaning across independently-numbered branches.
parents has length 1 for an ordinary commit, length 2 for a merge node.
created_at is metadata only, never used for ordering or identity.
"""

from dataclasses import dataclass, field
from datetime import datetime

from schemavcs.model.operations import CompoundOperation

RevisionId = str


@dataclass(frozen=True)
class Migration:
    id: RevisionId
    parents: tuple[RevisionId, ...]
    branch: str
    operations: tuple[CompoundOperation, ...] = field(default_factory=tuple)
    created_at: datetime | None = None

    @property
    def is_merge(self) -> bool:
        return len(self.parents) == 2
