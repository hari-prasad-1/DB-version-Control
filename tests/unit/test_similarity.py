from uuid import uuid4

from schemavcs.dsl.raw import RawColumn
from schemavcs.model import Column, TypeSpec
from schemavcs.rename_detect.similarity import (
    THRESHOLD_ACCEPT,
    name_similarity,
    score,
    type_similarity,
)


def test_calibration_demo_pair_clears_acceptance_threshold():
    # the project's own running example: subscription_type: string renamed
    # to plan_type: enum. Before trusting this formula on anything else,
    # confirm it actually scores high enough to get proposed.
    old_column = Column(
        id=uuid4(), name="subscription_type", type=TypeSpec("string", (50,)), position=2
    )
    new_column = RawColumn(name="plan_type", type=TypeSpec("enum"), position=2)

    result = score(old_column, new_column, table_size=4)

    assert result.total >= THRESHOLD_ACCEPT, (
        f"demo pair scored {result.total:.3f}, below acceptance threshold "
        f"{THRESHOLD_ACCEPT} -- the formula needs recalibrating"
    )


def test_name_similarity_identical():
    assert name_similarity("email", "email") == 1.0


def test_name_similarity_completely_different():
    assert name_similarity("email", "zzz") < 0.3


def test_name_similarity_shared_suffix():
    # subscription_type -> plan_type: shares "_type", meaningfully similar
    assert name_similarity("subscription_type", "plan_type") > 0.3


def test_type_similarity_identical():
    assert type_similarity(TypeSpec("string"), TypeSpec("string")) == 1.0


def test_type_similarity_string_to_text_is_high():
    assert type_similarity(TypeSpec("string"), TypeSpec("text")) == 0.9


def test_type_similarity_string_to_enum_is_moderate():
    assert type_similarity(TypeSpec("string"), TypeSpec("enum")) == 0.5


def test_type_similarity_string_to_integer_is_zero():
    assert type_similarity(TypeSpec("string"), TypeSpec("int")) == 0.0


def test_type_similarity_symmetric():
    assert type_similarity(TypeSpec("string"), TypeSpec("enum")) == type_similarity(
        TypeSpec("enum"), TypeSpec("string")
    )


def test_score_same_name_same_type_scores_maximally():
    old_column = Column(id=uuid4(), name="email", type=TypeSpec("string"), position=0)
    new_column = RawColumn(name="email", type=TypeSpec("string"), position=0)

    result = score(old_column, new_column, table_size=1)

    assert result.total == 1.0


def test_score_unrelated_name_and_type_scores_low():
    old_column = Column(id=uuid4(), name="legacy_id", type=TypeSpec("int"), position=0)
    new_column = RawColumn(name="notes", type=TypeSpec("text"), position=5)

    result = score(old_column, new_column, table_size=6)

    assert result.total < THRESHOLD_ACCEPT


def test_score_ignore_position_flag_neutralizes_position_component():
    old_column = Column(id=uuid4(), name="email", type=TypeSpec("string"), position=0)
    new_column = RawColumn(name="email", type=TypeSpec("string"), position=9)

    with_position = score(old_column, new_column, table_size=10, ignore_position=False)
    without_position = score(old_column, new_column, table_size=10, ignore_position=True)

    assert without_position.total > with_position.total
    assert without_position.position == 1.0
