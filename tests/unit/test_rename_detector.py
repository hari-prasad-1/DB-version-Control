from uuid import uuid4

from schemavcs.dsl.raw import RawColumn
from schemavcs.model import Column, TypeSpec
from schemavcs.rename_detect.detector import ProposalStatus, detect_renames


def _col(name: str, type_name: str = "string", position: int = 0, **kwargs) -> Column:
    return Column(id=uuid4(), name=name, type=TypeSpec(type_name), position=position, **kwargs)


def _raw(name: str, type_name: str = "string", position: int = 0, **kwargs) -> RawColumn:
    return RawColumn(name=name, type=TypeSpec(type_name), position=position, **kwargs)


def test_one_drop_one_add_structural_fallback_proposes_regardless_of_score():
    # the demo pair -- also exercises the "exactly one candidate on each
    # side, no ambiguity" fallback rule directly.
    old = [_col("subscription_type", "string", position=2)]
    new = [_raw("plan_type", "enum", position=2)]

    result = detect_renames(old, new, table_size=4, confirm=lambda p: True)

    assert len(result.proposals) == 1
    assert result.proposals[0].status == ProposalStatus.CONFIRMED
    assert result.plain_drops == []
    assert result.plain_adds == []


def test_one_drop_one_add_rejected_becomes_plain_drop_and_add():
    old = [_col("legacy_id", "int")]
    new = [_raw("notes", "text")]

    result = detect_renames(old, new, table_size=2, confirm=lambda p: False)

    assert result.proposals[0].status == ProposalStatus.REJECTED
    assert result.plain_drops == old
    assert result.plain_adds == new


def test_split_degrades_to_plain_drop_and_two_plain_adds():
    # full_name deleted, first_name and last_name added -- neither should
    # clearly "win" as full_name's best match over the other, so this must
    # NOT get proposed as a rename at all.
    old = [_col("full_name", "string")]
    new = [_raw("first_name", "string"), _raw("last_name", "string")]

    result = detect_renames(old, new, table_size=3, confirm=lambda p: True)

    assert result.proposals == []
    assert result.plain_drops == old
    assert set(c.name for c in result.plain_adds) == {"first_name", "last_name"}


def test_clear_rename_proposed_and_confirmed():
    old = [
        _col("subscription_type", "string", position=0),
        _col("something_unrelated", "int", position=5),
    ]
    new = [
        _raw("plan_type", "enum", position=0),
        _raw("region", "int", position=5),
    ]

    result = detect_renames(old, new, table_size=6, confirm=lambda p: True)

    confirmed = {
        (p.old_column.name, p.new_column.name)
        for p in result.proposals
        if p.status == ProposalStatus.CONFIRMED
    }
    assert ("subscription_type", "plan_type") in confirmed


def test_rejected_pair_goes_back_in_the_pool_instead_of_finalizing_immediately():
    # a human says "no" to the first (correct) proposal -- the two columns
    # involved must go back into the pool and get compared against
    # whatever else remains, not immediately become a plain drop/add.
    # There's nothing else left here for either to match, so after the
    # rejection both correctly end up unmatched -- but the proposal itself
    # must be recorded as rejected, not silently dropped.
    old = [_col("email", "string", position=0)]
    new = [_raw("email", "string", position=0)]

    result = detect_renames(old, new, table_size=1, confirm=lambda p: False)

    assert len(result.proposals) == 1
    assert result.proposals[0].status == ProposalStatus.REJECTED
    assert result.plain_drops == old
    assert result.plain_adds == new


def test_rejected_pair_is_rechecked_against_a_different_remaining_candidate():
    # three old, three new columns. The first proposal offered gets
    # rejected; the columns it involved must still be considered against
    # whatever's left, and a real (if different) mutual match among the
    # remaining columns still gets found and confirmed afterward.
    old = [
        _col("subscription_type", "string", position=0),
        _col("something_unrelated", "int", position=5),
    ]
    new = [
        _raw("plan_type", "enum", position=0),
        _raw("region", "int", position=5),
    ]

    seen_first = []

    def confirm(proposal):
        if not seen_first:
            seen_first.append(proposal)
            return False
        return True

    result = detect_renames(old, new, table_size=6, confirm=confirm)

    assert len(result.proposals) == 2
    assert result.proposals[0].status == ProposalStatus.REJECTED
    assert result.proposals[1].status == ProposalStatus.CONFIRMED
    # the rejected pairing is never the one confirmed afterward
    rejected_pair = (result.proposals[0].old_column.name, result.proposals[0].new_column.name)
    confirmed_pair = (result.proposals[1].old_column.name, result.proposals[1].new_column.name)
    assert rejected_pair != confirmed_pair


def test_two_independent_renames_in_the_same_edit_resolved_correctly():
    # two unrelated columns each renamed in the same edit -- must not
    # confuse which old column matches which new one.
    old = [
        _col("email_address", "string", position=0),
        _col("phone_number", "string", position=1),
    ]
    new = [
        _raw("email_addr", "string", position=0),
        _raw("phone_num", "string", position=1),
    ]

    result = detect_renames(old, new, table_size=2, confirm=lambda p: True)

    confirmed_pairs = {
        (p.old_column.name, p.new_column.name)
        for p in result.proposals
        if p.status == ProposalStatus.CONFIRMED
    }
    assert confirmed_pairs == {("email_address", "email_addr"), ("phone_number", "phone_num")}


def test_position_noise_does_not_block_fallback_proposal():
    old = [_col("subscription_type", "string", position=0)]
    new = [_raw("plan_type", "enum", position=2)]

    result = detect_renames(old, new, table_size=3, confirm=lambda p: True)

    assert len(result.proposals) == 1
    assert result.proposals[0].status == ProposalStatus.CONFIRMED


def test_position_ignored_when_most_unmatched_columns_moved():
    # Two genuinely unmatched pairs, both plausible renames by name/type,
    # but their positions were shuffled by an unrelated edit elsewhere in
    # the same file -- represented here by a same-name column ("id") that
    # moved, alongside the table's OTHER, already-exact-name-matched
    # columns (which is where the position-noise check actually has to
    # look; the unmatched pool alone never contains a same-name pair to
    # judge movement from). With most of the table's columns having moved,
    # position is dropped as a signal entirely, so both unmatched pairs
    # resolve correctly on name/type alone.
    old = [
        _col("subscription_type", "string", position=1),
        _col("order_count", "int", position=2),
    ]
    new = [
        _raw("plan_type", "enum", position=6),
        _raw("order_total", "bigint", position=7),
    ]
    all_old = [_col("id", "uuid", position=0), *old]
    all_new = [_raw("id", "uuid", position=5), *new]

    result = detect_renames(
        old,
        new,
        table_size=8,
        confirm=lambda p: True,
        all_old_columns=all_old,
        all_new_columns=all_new,
    )

    confirmed_pairs = {
        (p.old_column.name, p.new_column.name)
        for p in result.proposals
        if p.status == ProposalStatus.CONFIRMED
    }
    assert confirmed_pairs == {
        ("subscription_type", "plan_type"),
        ("order_count", "order_total"),
    }
