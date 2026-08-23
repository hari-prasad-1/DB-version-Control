"""Scores how likely an old column and a candidate new column are "the
same column, edited" -- feeds the rename/retype detector (sub-phase 2.3).
Pure functions, no state, no detection loop here.

score = 0.45*name_sim + 0.25*type_sim + 0.15*constraint_overlap + 0.15*position_proximity

Name weighted highest -- the strongest human-legible signal available, and
most renames still resemble the old name (subscription_type -> plan_type
shares "_type"). Type gets real but non-dominant weight so a rename+retype
together still scores well: a genuine rename shouldn't be penalized just
because the column's type also changed in the same edit.
"""

from dataclasses import dataclass

from schemavcs.dsl.raw import RawColumn
from schemavcs.model import Column, TypeSpec

THRESHOLD_ACCEPT = 0.6
THRESHOLD_AMBIGUOUS_GAP = 0.15

_NAME_WEIGHT = 0.45
_TYPE_WEIGHT = 0.25
_CONSTRAINT_WEIGHT = 0.15
_POSITION_WEIGHT = 0.15

# Symmetric type-family similarity. Unlisted pairs default to 0.0 (totally
# unrelated types -- a strong signal this isn't the same column), except a
# type paired with itself, which is always 1.0 regardless of this table.
_TYPE_FAMILY_SIMILARITY: dict[frozenset[str], float] = {
    frozenset({"string", "text"}): 0.9,  # same family, just a size/format tweak
    frozenset({"string", "enum"}): 0.5,  # common pattern: free text tightened to a fixed set
    frozenset({"text", "enum"}): 0.3,
    frozenset({"int", "bigint"}): 0.8,
    frozenset({"int", "decimal"}): 0.3,
    frozenset({"decimal", "bigint"}): 0.2,
}


def name_similarity(old_name: str, new_name: str) -> float:
    """Normalized Levenshtein ratio: 1.0 for identical strings, 0.0 for
    completely different ones with no shared structure."""
    if old_name == new_name:
        return 1.0
    distance = _levenshtein(old_name, new_name)
    longest = max(len(old_name), len(new_name))
    if longest == 0:
        return 1.0
    return 1.0 - (distance / longest)


def type_similarity(old_type: TypeSpec, new_type: TypeSpec) -> float:
    if old_type.name == new_type.name:
        return 1.0
    return _TYPE_FAMILY_SIMILARITY.get(frozenset({old_type.name, new_type.name}), 0.0)


def constraint_overlap(old_column: Column, new_column: RawColumn) -> float:
    """Fraction of the two constraint-shaped facts (nullable, has-a-default)
    that agree between the two sides."""
    facts_agree = [
        old_column.nullable == new_column.nullable,
        (old_column.default is not None) == (new_column.default is not None),
    ]
    return sum(facts_agree) / len(facts_agree)


def position_proximity(old_position: int, new_position: int, table_size: int) -> float:
    """1.0 for no movement at all, decaying toward 0.0 the further apart the
    two positions are relative to how big the table is. Sub-phase 2.3 is
    responsible for deciding when position should be ignored entirely (a
    lot of columns moved in the same edit) -- this function always scores
    literally, it doesn't know about that noise-filtering rule."""
    if table_size <= 1:
        return 1.0
    return 1.0 - (abs(old_position - new_position) / table_size)


@dataclass(frozen=True)
class SimilarityScore:
    total: float
    name: float
    type: float
    constraints: float
    position: float


def score(
    old_column: Column,
    new_column: RawColumn,
    table_size: int,
    ignore_position: bool = False,
) -> SimilarityScore:
    name = name_similarity(old_column.name, new_column.name)
    type_ = type_similarity(old_column.type, new_column.type)
    constraints = constraint_overlap(old_column, new_column)
    position = (
        1.0
        if ignore_position
        else position_proximity(old_column.position, new_column.position, table_size)
    )
    total = (
        _NAME_WEIGHT * name
        + _TYPE_WEIGHT * type_
        + _CONSTRAINT_WEIGHT * constraints
        + _POSITION_WEIGHT * position
    )
    return SimilarityScore(
        total=total, name=name, type=type_, constraints=constraints, position=position
    )


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous_row = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current_row = [i]
        for j, char_b in enumerate(b, start=1):
            insert_cost = current_row[j - 1] + 1
            delete_cost = previous_row[j] + 1
            substitute_cost = previous_row[j - 1] + (char_a != char_b)
            current_row.append(min(insert_cost, delete_cost, substitute_cost))
        previous_row = current_row
    return previous_row[-1]
