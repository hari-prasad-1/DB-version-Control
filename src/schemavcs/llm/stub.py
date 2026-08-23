"""Deterministic, offline ConflictExplainer — no network calls, no
randomness, fully unit-testable. This is the default explainer for Phase 1;
a real model-backed provider is a drop-in replacement behind the same
interface (sub-phase 1.13)."""

from uuid import UUID

from schemavcs.llm.interface import ConflictExplainer, ConflictExplanation
from schemavcs.merge.classify import ClassifiedGroup
from schemavcs.model import Operation, Snapshot


class StubExplainer(ConflictExplainer):
    def explain(self, group: ClassifiedGroup, schema_context: Snapshot) -> ConflictExplanation:
        identity_name = _resolve_name(group.group.identity_id, schema_context)
        side_a = _describe_ops(group.group.ops_a)
        side_b = _describe_ops(group.group.ops_b)

        explanation = (
            f"Conflict on {identity_name}: branch A did {side_a}; branch B did {side_b}. "
            f"{group.reason}."
        )
        return ConflictExplanation(explanation=explanation, suggestion=None)


def _describe_ops(ops: list[Operation]) -> str:
    if not ops:
        return "nothing"
    return "; ".join(_describe_op(op) for op in ops)


def _describe_op(op: Operation) -> str:
    return f"{type(op).__name__}({', '.join(f'{k}={v}' for k, v in vars(op).items())})"


def _resolve_name(identity_id: UUID, schema_context: Snapshot) -> str:
    for table in schema_context.tables:
        if table.id == identity_id:
            return f"table {table.name!r}"
        for column in table.columns:
            if column.id == identity_id:
                return f"column {table.name}.{column.name!r}"
        for index in table.indexes:
            if index.id == identity_id:
                return f"index {index.name!r}"
        for constraint in table.constraints:
            if constraint.id == identity_id:
                return f"constraint on {table.name!r}"
    return str(identity_id)
