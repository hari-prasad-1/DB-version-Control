import ast
from pathlib import Path
from uuid import uuid4

import pytest

from schemavcs.merge.classify import Classification, ClassifiedGroup
from schemavcs.merge.grouping import IdentityGroup
from schemavcs.merge.resolve import (
    HumanConfirmationToken,
    ResolutionEngine,
    TokenAlreadyUsedError,
    confirm_from_cli,
)
from schemavcs.model import AlterColumnType, RenameColumn, TypeSpec


def _group(classification: Classification) -> ClassifiedGroup:
    col_id = uuid4()
    op_a = RenameColumn(column_id=col_id, old_name="x", new_name="y")
    op_b = RenameColumn(column_id=col_id, old_name="x", new_name="z")
    return ClassifiedGroup(
        group=IdentityGroup(identity_id=col_id, ops_a=[op_a], ops_b=[op_b]),
        classification=classification,
        reason="test",
    )


def test_auto_resolve_handles_safe_tiers():
    engine = ResolutionEngine()
    for classification in (
        Classification.IDENTICAL,
        Classification.COMMUTING,
        Classification.ORDER_IRRELEVANT,
    ):
        assert engine.auto_resolve(_group(classification)) is not None


def test_auto_resolve_returns_none_for_conflict():
    engine = ResolutionEngine()
    assert engine.auto_resolve(_group(Classification.CONFLICT)) is None
    assert engine.auto_resolve(_group(Classification.PARTIAL_CONFLICT)) is None


def _single_valued_field_group() -> ClassifiedGroup:
    # both branches retyped the same column differently -- a genuine
    # single-value disagreement, not two separate operation objects.
    col_id = uuid4()
    op_a = AlterColumnType(column_id=col_id, old_type=TypeSpec("string"), new_type=TypeSpec("int"))
    op_b = AlterColumnType(
        column_id=col_id, old_type=TypeSpec("string"), new_type=TypeSpec("decimal")
    )
    return ClassifiedGroup(
        group=IdentityGroup(identity_id=col_id, ops_a=[op_a], ops_b=[op_b]),
        classification=Classification.CONFLICT,
        reason="both branches set a different type",
        single_valued_field=True,
    )


def test_confirm_from_cli_offers_only_a_b_for_single_valued_field(monkeypatch):
    group = _single_valued_field_group()
    prompts: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "b")
    token = confirm_from_cli(group)

    assert "both" not in prompts[0].lower()
    assert token.chosen_resolution == tuple(group.group.ops_b)


def test_confirm_from_cli_single_valued_field_defaults_to_a_on_any_non_b_answer(monkeypatch):
    group = _single_valued_field_group()
    monkeypatch.setattr("builtins.input", lambda prompt: "whatever")
    token = confirm_from_cli(group)

    assert token.chosen_resolution == tuple(group.group.ops_a)


def test_confirm_from_cli_still_offers_both_for_non_single_valued_conflict(monkeypatch):
    group = _group(Classification.CONFLICT)
    assert group.single_valued_field is False
    monkeypatch.setattr("builtins.input", lambda prompt: "both")
    token = confirm_from_cli(group)

    assert token.chosen_resolution == tuple(group.group.ops_a) + tuple(group.group.ops_b)


def test_commit_resolution_rejects_non_token_values():
    engine = ResolutionEngine()
    group = _group(Classification.CONFLICT)
    with pytest.raises(TypeError):
        engine.commit_resolution(group, "not a token")  # type: ignore[arg-type]


def test_commit_resolution_rejects_token_for_wrong_group():
    engine = ResolutionEngine()
    group = _group(Classification.CONFLICT)
    other_group = _group(Classification.CONFLICT)
    token = HumanConfirmationToken(
        group_id=other_group.group.identity_id, chosen_resolution=(), _nonce=uuid4()
    )
    with pytest.raises(ValueError):
        engine.commit_resolution(group, token)


def test_commit_resolution_rejects_stale_or_reused_token():
    engine = ResolutionEngine()
    group = _group(Classification.CONFLICT)
    token = HumanConfirmationToken(
        group_id=group.group.identity_id,
        chosen_resolution=tuple(group.group.ops_a),
        _nonce=uuid4(),
    )
    result = engine.commit_resolution(group, token)
    assert result == tuple(group.group.ops_a)

    with pytest.raises(TokenAlreadyUsedError):
        engine.commit_resolution(group, token)


def test_llm_package_never_imports_merge_resolve_or_engine():
    llm_dir = Path(__file__).resolve().parents[2] / "src" / "schemavcs" / "llm"
    for path in llm_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert (
                    "merge.resolve" not in node.module and "merge.engine" not in node.module
                ), f"{path} imports {node.module}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert (
                        "merge.resolve" not in alias.name and "merge.engine" not in alias.name
                    ), f"{path} imports {alias.name}"
