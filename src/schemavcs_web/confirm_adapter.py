"""Replicates `confirm_from_cli`'s branching (`merge/resolve.py`) as data
instead of blocking terminal I/O, and shapes engine dataclasses into plain
JSON for the browser. Does not call `confirm_from_cli` -- it can't, since
that function blocks on real stdin -- it re-derives the same three-way
choice a human sees at a terminal, so a browser offers the identical set of
options: acknowledge-only, [a]/[b], or [a]/[b]/[both].
"""

from typing import Literal
from uuid import uuid4

from schemavcs.merge.classify import ClassifiedGroup
from schemavcs.merge.resolve import HumanConfirmationToken, _corrective_drop_for
from schemavcs.model.serialize import to_jsonable
from schemavcs.rename_detect.detector import RenameProposal

UiMode = Literal["cross_object", "single_valued", "free_choice"]

Choice = Literal["a", "b", "both", "ack"]


def classify_ui_mode(group: ClassifiedGroup) -> UiMode:
    """Same three-way branch `confirm_from_cli` uses (resolve.py:58-90) --
    determines which set of buttons the browser renders, mirroring exactly
    what the CLI prompt would have offered for this same group."""
    if group.cross_object_referencing_op is not None:
        return "cross_object"
    if group.single_valued_field:
        return "single_valued"
    return "free_choice"


def build_token_from_choice(group: ClassifiedGroup, choice: str) -> HumanConfirmationToken:
    """The non-blocking equivalent of `confirm_from_cli`'s body. Constructs
    a real token via the real dataclass and a real fresh uuid4() nonce --
    `_corrective_drop_for` is imported directly from `merge.resolve` (first-
    party, same-repo, read-only) rather than duplicated, since a hand-copied
    match block would silently drift out of sync if a new dependent-op
    variant is ever added there."""
    if group.cross_object_referencing_op is not None:
        chosen = (_corrective_drop_for(group.cross_object_referencing_op),)
    elif choice == "b":
        chosen = tuple(group.group.ops_b)
    elif choice == "both" and not group.single_valued_field:
        chosen = tuple(group.group.ops_a) + tuple(group.group.ops_b)
    else:
        # choice == "a", or any unrecognized value for a single-valued
        # field, where only [a]/[b] are legal choices in the first place.
        chosen = tuple(group.group.ops_a)
    return HumanConfirmationToken(
        group_id=group.group.identity_id, chosen_resolution=chosen, _nonce=uuid4()
    )


def group_to_dict(group: ClassifiedGroup) -> dict:
    """JSON shape for one pending merge conflict, built from known-good
    sub-parts rather than running `to_jsonable` over the whole
    ClassifiedGroup directly (its nested IdentityGroup isn't itself
    registered in model/serialize.py's dataclass scan)."""
    return {
        "identity_id": str(group.group.identity_id),
        "classification": group.classification.value,
        "reason": group.reason,
        "ui_mode": classify_ui_mode(group),
        "ops_a": [to_jsonable(op) for op in group.group.ops_a],
        "ops_b": [to_jsonable(op) for op in group.group.ops_b],
        "agreed_fields": group.agreed_fields,
        "conflicting_fields": list(group.conflicting_fields),
    }


def proposal_to_dict(proposal: RenameProposal) -> dict:
    """JSON shape for one pending rename proposal. `similarity == -1.0` is
    the structural-fallback sentinel (`generate_migration_cmd.py`'s CLI
    handling of the same value) -- carried through as-is so the browser can
    render the same "no ambiguity" wording the CLI prints."""
    return {
        "old_column": to_jsonable(proposal.old_column),
        "new_column": to_jsonable(proposal.new_column),
        "similarity": proposal.similarity,
    }
