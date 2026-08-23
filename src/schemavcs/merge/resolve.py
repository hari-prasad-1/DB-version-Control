"""Human-confirmation guardrail for merge conflicts.

Structural, not conventions-based: `commit_resolution` is the only function
that finalizes a CONFLICT/PARTIAL_CONFLICT group, and it accepts nothing but
a real `HumanConfirmationToken`. The only way to construct one is
`confirm_from_cli`, which blocks on real terminal input. Auto-resolve tiers
(IDENTICAL/COMMUTING/ORDER_IRRELEVANT) skip this module entirely -- they
never carry risk of a silent wrong merge, so they resolve directly in the
merge engine without a token.

This module must never be imported by `schemavcs.llm` -- enforced by
tests/unit/test_module_boundaries.py, not just this docstring.
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from schemavcs.merge.classify import Classification, ClassifiedGroup
from schemavcs.model import Operation


@dataclass(frozen=True)
class HumanConfirmationToken:
    group_id: UUID
    chosen_resolution: tuple[Operation, ...]
    _nonce: UUID


class TokenAlreadyUsedError(Exception):
    pass


def confirm_from_cli(group: ClassifiedGroup) -> HumanConfirmationToken:
    """Blocks on real terminal input. The only producer of a valid token."""
    print(f"Conflict on identity {group.group.identity_id}: {group.reason}")
    chosen_side = input("Keep [a]/[b]/[both]? ").strip().lower()
    if chosen_side == "a":
        chosen = tuple(group.group.ops_a)
    elif chosen_side == "b":
        chosen = tuple(group.group.ops_b)
    else:
        chosen = tuple(group.group.ops_a) + tuple(group.group.ops_b)
    return HumanConfirmationToken(
        group_id=group.group.identity_id, chosen_resolution=chosen, _nonce=uuid4()
    )


class ResolutionEngine:
    """Three-tier resolution: auto-resolve safe classifications, require a
    token for anything conflicting. Tracks spent tokens so a token can't be
    replayed against a different (or the same) group."""

    def __init__(self) -> None:
        self._spent_nonces: set[UUID] = set()

    def auto_resolve(self, group: ClassifiedGroup) -> tuple[Operation, ...] | None:
        """Returns the merged operations for classifications safe to commit
        without a human, or None if this group needs `commit_resolution`."""
        if group.classification in (Classification.IDENTICAL, Classification.UNRELATED):
            return tuple(group.group.ops_a) or tuple(group.group.ops_b)
        if group.classification == Classification.COMMUTING:
            return tuple(group.group.ops_a) + tuple(group.group.ops_b)
        if group.classification == Classification.ORDER_IRRELEVANT:
            return tuple(group.group.ops_a) + tuple(group.group.ops_b)
        return None

    def commit_resolution(
        self, group: ClassifiedGroup, token: HumanConfirmationToken
    ) -> tuple[Operation, ...]:
        if not isinstance(token, HumanConfirmationToken):
            raise TypeError("commit_resolution requires a real HumanConfirmationToken")
        if token.group_id != group.group.identity_id:
            raise ValueError("token was not issued for this group")
        if token._nonce in self._spent_nonces:
            raise TokenAlreadyUsedError("token has already been used to commit a resolution")
        self._spent_nonces.add(token._nonce)
        return token.chosen_resolution
