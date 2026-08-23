"""Model-agnostic conflict-explanation interface.

This module names no vendor. Any real backend (Anthropic, OpenAI, a local
model, etc.) implements ConflictExplainer via llm/providers/<name>.py; which
one is active is chosen by a factory reading configuration, never by
merge/resolve.py importing a concrete provider class directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from schemavcs.merge.classify import ClassifiedGroup
from schemavcs.model import Snapshot


@dataclass(frozen=True)
class ConflictExplanation:
    explanation: str
    suggestion: str | None = None


class ConflictExplainer(ABC):
    @abstractmethod
    def explain(self, group: ClassifiedGroup, schema_context: Snapshot) -> ConflictExplanation: ...
