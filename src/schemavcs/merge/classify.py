"""Classifies each per-identity group of operations touched by both
branches since their common ancestor.

Field-level decomposition: a compound edit bundles several fields of one
column (name, type, nullable) into one intent. When both branches touch the
same column with different compound edits, each field is compared
independently rather than the bundle as a whole — so a rename both sides
already agree on auto-merges even if they disagree on the retype, instead of
forcing a human to re-confirm the part that was never in question.
"""

from dataclasses import dataclass
from enum import Enum

from schemavcs.merge.grouping import IdentityGroup
from schemavcs.model import (
    AlterColumnDefault,
    AlterColumnNullability,
    AlterColumnType,
    Operation,
    RenameColumn,
    RenameIndex,
)


class Classification(Enum):
    UNRELATED = "unrelated"
    IDENTICAL = "identical"
    COMMUTING = "commuting"
    ORDER_IRRELEVANT = "order_irrelevant"
    CONFLICT = "conflict"
    PARTIAL_CONFLICT = "partial_conflict"


@dataclass
class ClassifiedGroup:
    group: IdentityGroup
    classification: Classification
    reason: str
    # For PARTIAL_CONFLICT only: the fields both sides agree on, pre-resolved,
    # and the field name(s) still requiring a human decision.
    agreed_fields: dict[str, object] | None = None
    conflicting_fields: tuple[str, ...] = ()
    # True when this conflict is over ONE single-valued field (a type, a
    # nullability flag, a name) rather than two genuinely separate operations
    # -- "keep both" has no meaningful result for a field that can only ever
    # hold one value, so the CLI prompt only offers [a]/[b] for these.
    single_valued_field: bool = False
    # For cross_object_pass's synthetic groups only: the op that referenced
    # a since-dropped table/column. Undoing the drop isn't mechanically
    # supportable (it would mean resurrecting a dropped object from
    # nothing), so the only real resolution is a corrective drop of
    # WHATEVER this op added -- there is no generic ops_a/ops_b choice here.
    cross_object_referencing_op: Operation | None = None


_DESTRUCTIVE_VARIANTS = ("DropColumn", "DropTable", "DropIndex", "DropConstraint")

_MUTATION_FIELD = {
    RenameColumn: ("name", "new_name"),
    AlterColumnType: ("type", "new_type"),
    AlterColumnNullability: ("nullable", "nullable"),
    AlterColumnDefault: ("default", "new_default"),
}


def classify(group: IdentityGroup) -> ClassifiedGroup:
    if not group.ops_a or not group.ops_b:
        return ClassifiedGroup(group, Classification.UNRELATED, "touched by only one branch")

    if len(group.ops_a) == 1 and len(group.ops_b) == 1:
        return _classify_single_pair(group, group.ops_a[0], group.ops_b[0])

    return _classify_compound_pair(group)


def _classify_single_pair(
    group: IdentityGroup, op_a: Operation, op_b: Operation
) -> ClassifiedGroup:
    if op_a == op_b:
        return ClassifiedGroup(group, Classification.IDENTICAL, "identical operation on both sides")

    name_a, name_b = type(op_a).__name__, type(op_b).__name__

    if name_a in _DESTRUCTIVE_VARIANTS or name_b in _DESTRUCTIVE_VARIANTS:
        if name_a in _DESTRUCTIVE_VARIANTS and name_b in _DESTRUCTIVE_VARIANTS:
            return ClassifiedGroup(
                group, Classification.IDENTICAL, "same identity dropped on both sides"
            )
        return ClassifiedGroup(
            group,
            Classification.CONFLICT,
            "one branch removed this identity while the other mutated it",
        )

    if type(op_a) is type(op_b):
        mutation_field = _MUTATION_FIELD.get(type(op_a))
        if mutation_field is None:
            # Same op type, not in the field-mutation table (e.g. AddColumn,
            # AddIndex, AddConstraint) and already known not equal (checked
            # above) -- two different objects built for the same identity.
            return ClassifiedGroup(
                group,
                Classification.CONFLICT,
                "both branches built a different object for this identity",
            )
        field_name, attr = mutation_field
        if getattr(op_a, attr) != getattr(op_b, attr):
            return ClassifiedGroup(
                group,
                Classification.CONFLICT,
                f"both branches set a different {field_name}",
                single_valued_field=True,
            )
        return ClassifiedGroup(group, Classification.IDENTICAL, "same field, same target value")

    if isinstance(op_a, RenameIndex) or isinstance(op_b, RenameIndex):
        return ClassifiedGroup(
            group, Classification.COMMUTING, "different fields of the same identity touched"
        )

    return ClassifiedGroup(
        group, Classification.COMMUTING, "different, non-overlapping fields touched on each side"
    )


def _classify_compound_pair(group: IdentityGroup) -> ClassifiedGroup:
    fields_a = _decompose(group.ops_a)
    fields_b = _decompose(group.ops_b)

    all_field_names = set(fields_a) | set(fields_b)
    agreed: dict[str, object] = {}
    conflicting: list[str] = []

    for field_name in all_field_names:
        in_a, in_b = field_name in fields_a, field_name in fields_b
        if in_a and in_b:
            if fields_a[field_name] == fields_b[field_name]:
                agreed[field_name] = fields_a[field_name]
            else:
                conflicting.append(field_name)
        elif in_a:
            agreed[field_name] = fields_a[field_name]
        else:
            agreed[field_name] = fields_b[field_name]

    if not conflicting:
        return ClassifiedGroup(
            group,
            Classification.COMMUTING,
            "compound edits agree on every field",
            agreed_fields=agreed,
        )
    return ClassifiedGroup(
        group,
        Classification.PARTIAL_CONFLICT,
        f"compound edits disagree on: {', '.join(sorted(conflicting))}",
        agreed_fields=agreed,
        conflicting_fields=tuple(sorted(conflicting)),
    )


def _decompose(ops: list[Operation]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for op in ops:
        field_name, attr = _MUTATION_FIELD.get(type(op), (None, None))
        if field_name is not None:
            fields[field_name] = getattr(op, attr)
    return fields
