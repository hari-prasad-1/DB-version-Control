"""Rename/retype detector: takes the genuinely-unmatched columns a
MatchedTable left over (§B) and proposes which old column plausibly became
which new column, asking a human to confirm each proposal.

Only proposes a pair when both sides prefer each other (mutual best match)
with a clear enough lead over the next-best alternative -- otherwise a
plain "delete X, add Y" is indistinguishable from "X became Y" by scoring
alone, and guessing wrong is worse than not guessing (a split like
full_name -> first_name + last_name must NOT get proposed as a rename).

A rejected proposal puts both columns back in the pool to compare against
whatever's left, rather than immediately giving up on them -- only once a
column has been checked against every remaining candidate and nothing fits
does it finalize as a plain drop (old side) or plain add (new side).

Position is dropped as a scoring signal for a table's whole edit when a
large fraction of its columns visibly changed position in the same edit --
otherwise unrelated reordering elsewhere in the same file would wrongly
penalize a genuine rename.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from schemavcs.dsl.raw import RawColumn
from schemavcs.model import Column
from schemavcs.rename_detect.similarity import THRESHOLD_ACCEPT, THRESHOLD_AMBIGUOUS_GAP, score

# Position is ignored for a table's scoring when at least this fraction of
# its unmatched columns have moved -- an empirically chosen cutoff (this
# formula's weights are explicitly tuning targets, not derived constants).
_POSITION_NOISE_FRACTION = 0.5


class ProposalStatus(Enum):
    PENDING = "pending"
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


@dataclass
class RenameProposal:
    old_column: Column
    new_column: RawColumn
    similarity: float
    status: ProposalStatus = ProposalStatus.PENDING


@dataclass
class DetectionResult:
    proposals: list[RenameProposal]
    plain_drops: list[Column]
    plain_adds: list[RawColumn]


ConfirmFn = Callable[[RenameProposal], bool]


def detect_renames(
    old_columns: list[Column],
    new_columns: list[RawColumn],
    table_size: int,
    confirm: ConfirmFn,
    all_old_columns: list[Column] | None = None,
    all_new_columns: list[RawColumn] | None = None,
) -> DetectionResult:
    """Scores every remaining (old, new) pair, proposes mutual-best-matches
    for human confirmation one at a time, and puts a rejected pair's two
    columns back in the pool before finalizing anything as a plain
    drop/add.

    `old_columns`/`new_columns` are the genuinely UNMATCHED pool (2.1's
    diff already resolved same-name matches before this point). The
    position-noise rule -- "ignore position if most columns in this edit
    moved" -- needs to look at the table's FULL column set to judge that,
    not just the unmatched leftovers, so `all_old_columns`/
    `all_new_columns` (defaulting to the unmatched pool itself, when the
    caller has nothing more to offer) are used for that check only."""
    remaining_old = list(old_columns)
    remaining_new = list(new_columns)
    proposals: list[RenameProposal] = []

    ignore_position = _should_ignore_position(
        all_old_columns if all_old_columns is not None else old_columns,
        all_new_columns if all_new_columns is not None else new_columns,
    )

    # The one-drop-one-add structural fallback: with exactly one candidate
    # on each side, there's no ambiguity to guess wrong about, so propose
    # it regardless of score -- still requires human confirmation like any
    # other proposal.
    if len(remaining_old) == 1 and len(remaining_new) == 1:
        proposal = RenameProposal(
            old_column=remaining_old[0], new_column=remaining_new[0], similarity=-1.0
        )
        return _resolve_single_proposal(proposal, confirm)

    rejected_pairs: set[tuple[int, int]] = set()

    while remaining_old and remaining_new:
        best = _best_mutual_match(
            remaining_old, remaining_new, table_size, ignore_position, rejected_pairs
        )
        if best is None:
            break
        old_column, new_column, similarity = best
        proposal = RenameProposal(
            old_column=old_column,
            new_column=new_column,
            similarity=similarity,
            status=ProposalStatus.PROPOSED,
        )
        proposals.append(proposal)

        if confirm(proposal):
            proposal.status = ProposalStatus.CONFIRMED
            remaining_old.remove(old_column)
            remaining_new.remove(new_column)
        else:
            # rejected -- both columns stay in the pool (not immediately
            # finalized as a plain drop/add); only this exact pairing is
            # excluded so the search can consider each of them against
            # whatever else remains on the next iteration.
            proposal.status = ProposalStatus.REJECTED
            rejected_pairs.add((id(old_column), id(new_column)))

    return DetectionResult(proposals=proposals, plain_drops=remaining_old, plain_adds=remaining_new)


def _resolve_single_proposal(proposal: RenameProposal, confirm: ConfirmFn) -> DetectionResult:
    proposal.status = ProposalStatus.PROPOSED
    if confirm(proposal):
        proposal.status = ProposalStatus.CONFIRMED
        return DetectionResult(proposals=[proposal], plain_drops=[], plain_adds=[])
    proposal.status = ProposalStatus.REJECTED
    return DetectionResult(
        proposals=[proposal], plain_drops=[proposal.old_column], plain_adds=[proposal.new_column]
    )


def _should_ignore_position(old_columns: list[Column], new_columns: list[RawColumn]) -> bool:
    if not old_columns or not new_columns:
        return False
    new_by_name = {c.name: c for c in new_columns}
    moved = 0
    compared = 0
    for old_column in old_columns:
        new_column = new_by_name.get(old_column.name)
        if new_column is None:
            continue
        compared += 1
        if new_column.position != old_column.position:
            moved += 1
    if compared == 0:
        return False
    return (moved / compared) >= _POSITION_NOISE_FRACTION


def _best_mutual_match(
    old_columns: list[Column],
    new_columns: list[RawColumn],
    table_size: int,
    ignore_position: bool,
    excluded: set[tuple[int, int]] | None = None,
) -> tuple[Column, RawColumn, float] | None:
    """The pair (old, new) such that new is old's best match, old is new's
    best match, and the gap to each side's runner-up clears
    THRESHOLD_AMBIGUOUS_GAP -- or None if no such pair exists."""
    excluded = excluded or set()

    scores: dict[tuple[int, int], float] = {}
    for old_column in old_columns:
        for new_column in new_columns:
            key = (id(old_column), id(new_column))
            if key in excluded:
                continue
            scores[key] = score(old_column, new_column, table_size, ignore_position).total

    if not scores:
        return None

    best_for_old = _best_per_key(old_columns, new_columns, scores, by_old=True)
    best_for_new = _best_per_key(old_columns, new_columns, scores, by_old=False)

    candidates = []
    for old_column in old_columns:
        old_best = best_for_old.get(id(old_column))
        if old_best is None:
            continue
        new_column, sim, gap = old_best
        new_best = best_for_new.get(id(new_column))
        if new_best is None:
            continue
        reciprocal_old, _, new_gap = new_best
        if id(reciprocal_old) != id(old_column):
            continue
        if sim < THRESHOLD_ACCEPT:
            continue
        if gap < THRESHOLD_AMBIGUOUS_GAP or new_gap < THRESHOLD_AMBIGUOUS_GAP:
            continue
        candidates.append((old_column, new_column, sim))

    if not candidates:
        return None
    return max(candidates, key=lambda c: c[2])


def _best_per_key(
    old_columns: list[Column],
    new_columns: list[RawColumn],
    scores: dict[tuple[int, int], float],
    by_old: bool,
) -> dict[int, tuple]:
    """For each old column (by_old=True) or new column (by_old=False),
    returns (best-matching-partner, its score, gap-to-runner-up)."""
    result: dict[int, tuple] = {}
    outer = old_columns if by_old else new_columns
    inner = new_columns if by_old else old_columns

    for item in outer:
        ranked = []
        for partner in inner:
            key = (id(item), id(partner)) if by_old else (id(partner), id(item))
            if key in scores:
                ranked.append((partner, scores[key]))
        if not ranked:
            continue
        ranked.sort(key=lambda p: p[1], reverse=True)
        best_partner, best_score = ranked[0]
        runner_up_score = ranked[1][1] if len(ranked) > 1 else 0.0
        gap = best_score - runner_up_score
        result[id(item)] = (best_partner, best_score, gap)
    return result
