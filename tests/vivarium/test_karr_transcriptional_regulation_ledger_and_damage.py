"""Dedicated unit coverage for the 2026-09-08 TranscriptionalRegulation
accessibility-completeness fixes (Opus review: "implement full-footprint
double-stranded, undamaged, excludeOverlapping accessibility"), the
chromosome-RNG-ledger mechanism's fail-closed contract, and the
releasable-proteins fixture loader's fail-closed contract.

The full 4000-tick genuine seed-0 trace has zero entries in every damage
field and no self-overlapping candidate draws at any compared tick (see
`docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json`'s
`genuine_evidence.bit_identity.note`), so that dedicated bit-identity replay
(`tests/vivarium/test_karr_transcriptional_regulation_l2_replay.py`) alone
never exercises `_site_damaged`/`_sites_overlap`'s actual branches. This
module tests them directly, with synthetic damage/overlap scenarios, so the
2026-09-08 additions are genuinely covered rather than merely
correct-by-absence-of-counterexample.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet
from opencell.util.txreg_mcg_rand import TxRegChromosomeLedgerRandStream
from opencell.vivarium.karr_transcriptional_regulation import (
    KarrTranscriptionalRegulationProcess,
    _load_releasable_proteins,
)


@pytest.fixture(scope="module")
def process() -> KarrTranscriptionalRegulationProcess:
    return KarrTranscriptionalRegulationProcess({})


def _store_with_field(process: KarrTranscriptionalRegulationProcess, field: str, position: int, strand: int) -> ChromosomeStore:
    store = ChromosomeStore(shape=process.chromosome_shape)
    store.set_field(
        field,
        SparseTriplet(
            positions=np.asarray([position], dtype=np.int64),
            strands=np.asarray([strand], dtype=np.int64),
            values=np.asarray([1], dtype=np.int64),
            shape=process.chromosome_shape,
        ),
    )
    return store


# ---------------------------------------------------------------------------
# _site_damaged
# ---------------------------------------------------------------------------


def test_site_damaged_false_when_chromosome_store_empty(process: KarrTranscriptionalRegulationProcess) -> None:
    store = ChromosomeStore(shape=process.chromosome_shape)
    assert process._site_damaged(store, 1000, 0, tf_i=0) is False


def test_site_damaged_true_for_damage_within_own_footprint_same_strand(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    own_footprint = int(process._own_footprint_by_tf[0])
    store = _store_with_field(process, "damagedBases", 1000 + own_footprint - 1, 0)
    assert process._site_damaged(store, 1000, 0, tf_i=0) is True


def test_site_damaged_false_for_damage_just_outside_own_footprint(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    own_footprint = int(process._own_footprint_by_tf[0])
    store = _store_with_field(process, "damagedBases", 1000 + own_footprint, 0)
    assert process._site_damaged(store, 1000, 0, tf_i=0) is False


def test_site_damaged_mirrors_across_dsdna_strand_pair(process: KarrTranscriptionalRegulationProcess) -> None:
    # Query strand 0 (chromosome copy 1, strand pair 0). A damage entry
    # recorded on strand 1 (the OTHER strand of the SAME copy, also pair
    # 0) still counts -- every TF this process binds is dsDNA-stranded, so
    # real isRegionUndamaged is called with isEitherStrandDamaged=true
    # (see _site_damaged docstring).
    store = _store_with_field(process, "gapSites", 1010, 1)
    assert process._site_damaged(store, 1000, 0, tf_i=0) is True


def test_site_damaged_false_for_damage_on_other_chromosome_copy(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    # Strand 2 is chromosome copy 2 (strand pair 1) -- must not occlude a
    # copy-1 (strand pair 0) query regardless of position.
    store = _store_with_field(process, "abasicSites", 1010, 2)
    assert process._site_damaged(store, 1000, 0, tf_i=0) is False


@pytest.mark.parametrize(
    "field",
    ["damagedBases", "gapSites", "abasicSites", "damagedSugarPhosphates", "intrastrandCrossLinks", "strandBreaks", "hollidayJunctions"],
)
def test_site_damaged_true_for_every_disclosed_damage_field(
    process: KarrTranscriptionalRegulationProcess, field: str
) -> None:
    store = _store_with_field(process, field, 1005, 0)
    assert process._site_damaged(store, 1000, 0, tf_i=0) is True


def test_site_damaged_false_when_own_footprint_is_zero(process: KarrTranscriptionalRegulationProcess) -> None:
    # tf_i=0 has a real nonzero own_footprint; force the zero-footprint
    # short-circuit by monkeypatching the array directly on a private copy
    # (never mutate the shared fixture-derived array).
    store = _store_with_field(process, "damagedBases", 1000, 0)
    original = process._own_footprint_by_tf
    process._own_footprint_by_tf = [0.0] + list(original[1:])
    try:
        assert process._site_damaged(store, 1000, 0, tf_i=0) is False
    finally:
        process._own_footprint_by_tf = original


# ---------------------------------------------------------------------------
# _site_damaged: position-shifted damage-adjacency fields
# (intrastrandCrossLinks5, strandBreaks5/3, hollidayJunctions5/3)
# ---------------------------------------------------------------------------


def test_shifted_damage_position_base3_even_strand_shifts_plus_one() -> None:
    # 2026-09-08 (Opus re-review, second round): `intrastrandCrossLinks5`
    # is `shiftCircularSparseMatBase3Prime`, not a `base5`-named kind --
    # the correct, line-verified sign convention is even-strand +1 /
    # odd-strand -1 (the exact inverse of this test's prior, wrong
    # `base5` expectation of even -1 / odd +1). See the
    # `_DAMAGE_FIELD_SHIFTS` module comment.
    from opencell.vivarium.karr_transcriptional_regulation import _shifted_damage_position

    assert _shifted_damage_position(1000, 0, "base3") == 1001
    assert _shifted_damage_position(1000, 1, "base3") == 999


def test_shifted_damage_position_unbond5_only_shifts_even_strand() -> None:
    # `strandBreaks5` is `unshiftCircularSparseMatBond5Prime` -- even-strand
    # +1, odd-strand unchanged (the exact inverse of the pre-fix even -1
    # this module used to apply under a wrongly-attributed "bond5"-style
    # kind).
    from opencell.vivarium.karr_transcriptional_regulation import _shifted_damage_position

    assert _shifted_damage_position(1000, 0, "unbond5") == 1001
    assert _shifted_damage_position(1000, 1, "unbond5") == 1000


def test_shifted_damage_position_unbond3_only_shifts_odd_strand() -> None:
    # `strandBreaks3` is `unshiftCircularSparseMatBond3Prime` -- odd-strand
    # +1, even-strand unchanged (the exact inverse of the pre-fix odd -1
    # this module used to apply under a wrongly-attributed "bond3"-style
    # kind for strandBreaks).
    from opencell.vivarium.karr_transcriptional_regulation import _shifted_damage_position

    assert _shifted_damage_position(1000, 0, "unbond3") == 1000
    assert _shifted_damage_position(1000, 1, "unbond3") == 1001


def test_shifted_damage_position_bond5_only_shifts_even_strand() -> None:
    from opencell.vivarium.karr_transcriptional_regulation import _shifted_damage_position

    assert _shifted_damage_position(1000, 0, "bond5") == 999
    assert _shifted_damage_position(1000, 1, "bond5") == 1000


def test_shifted_damage_position_bond3_only_shifts_odd_strand() -> None:
    from opencell.vivarium.karr_transcriptional_regulation import _shifted_damage_position

    assert _shifted_damage_position(1000, 0, "bond3") == 1000
    assert _shifted_damage_position(1000, 1, "bond3") == 999


def test_site_damaged_true_via_intrastrand_crosslink_base3_adjacency(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    # own_footprint (tf_i=0) is 30. `intrastrandCrossLinks` only carries the
    # `base3` shift term (even-strand +1 / odd-strand -1). A raw entry at
    # position 1030 on strand 1 (odd) is just OUTSIDE the query's raw span
    # [1000, 1029] at its own recorded position (1030 > 1029), but its
    # base3-shifted adjacency virtual position (odd -> -1 -> 1029) falls
    # inside -- this only fires because the shift is modeled; the
    # un-shifted entry alone would report inaccessible == False (see the
    # next test for confirmation of that baseline). `strand_pair` mirrors
    # strand 0 and 1 together, so a strand-1 entry occludes a strand-0
    # query too.
    store = _store_with_field(process, "intrastrandCrossLinks", 1030, 1)
    assert process._site_damaged(store, 1000, 0, tf_i=0) is True


def test_site_damaged_false_for_gapsites_at_same_position_no_shift_applies(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    # gapSites carries NO shift terms in Karr's fixed calcDamagedSites
    # formula -- the same position (1030, just past the footprint) must
    # NOT be treated as damaging (confirms shifts are field-specific, not
    # applied blanket to every field).
    store = _store_with_field(process, "gapSites", 1030, 0)
    assert process._site_damaged(store, 1000, 0, tf_i=0) is False


def test_site_damaged_true_via_strand_break_unbond3_adjacency_on_odd_strand(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    # `strandBreaks` carries both `unbond5` (even +1) and `unbond3` (odd
    # +1) shift terms. A strandBreaks entry recorded at position 999 on
    # strand 1 (odd) is just OUTSIDE the query's raw span [1000, 1029] at
    # its own recorded position (999 < 1000), but its unbond3-shifted
    # adjacency virtual position (odd -> +1 -> 1000) falls inside --
    # strand_pair mirrors strand 0 and 1 together, so a strand-1 entry
    # occludes a strand-0 query too.
    store = _store_with_field(process, "strandBreaks", 999, 1)
    assert process._site_damaged(store, 1000, 0, tf_i=0) is True


# ---------------------------------------------------------------------------
# _sites_overlap
# ---------------------------------------------------------------------------


def test_sites_overlap_true_for_identical_position(process: KarrTranscriptionalRegulationProcess) -> None:
    assert process._sites_overlap(position_a=1000, strand_a=0, position_b=1000, strand_b=0, footprint=30) is True


def test_sites_overlap_true_within_footprint(process: KarrTranscriptionalRegulationProcess) -> None:
    assert process._sites_overlap(position_a=1000, strand_a=0, position_b=1010, strand_b=0, footprint=30) is True


def test_sites_overlap_false_just_outside_footprint(process: KarrTranscriptionalRegulationProcess) -> None:
    assert process._sites_overlap(position_a=1000, strand_a=0, position_b=1030, strand_b=0, footprint=30) is False


def test_sites_overlap_false_across_different_strand_pairs(process: KarrTranscriptionalRegulationProcess) -> None:
    assert process._sites_overlap(position_a=1000, strand_a=0, position_b=1010, strand_b=2, footprint=30) is False


def test_sites_overlap_true_mirrors_within_same_strand_pair(process: KarrTranscriptionalRegulationProcess) -> None:
    assert process._sites_overlap(position_a=1000, strand_a=0, position_b=1010, strand_b=1, footprint=30) is True


def test_sites_overlap_true_circular_wraparound(process: KarrTranscriptionalRegulationProcess) -> None:
    length = process.chromosome_shape[0]
    assert (
        process._sites_overlap(position_a=5, strand_a=0, position_b=length - 6, strand_b=0, footprint=30)
        is True
    )


# ---------------------------------------------------------------------------
# _sample_accessible_sites_batched excludeOverlapping integration
# ---------------------------------------------------------------------------


class _FixedOrderStream:
    """Deterministic stand-in for `_chromosome_rng`: always returns the
    first `k` entries of a fixed, pre-declared 1-based draw order,
    regardless of weights -- enough to exercise
    `_sample_accessible_sites_batched`'s post-draw filtering logic without
    depending on any real RNG algorithm."""

    def __init__(self, order_1based: list[int]) -> None:
        self._order = list(order_1based)

    def randsample(self, n: int, k: int, replacement: bool, w: np.ndarray) -> np.ndarray:
        del n, replacement, w
        return np.asarray(self._order[:k], dtype=np.int64)


def test_sample_accessible_sites_batched_excludes_self_overlap_within_same_batch(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    process._chromosome_rng = _FixedOrderStream([1, 2])
    try:
        chosen = process._sample_accessible_sites_batched(
            n_needed=2,
            weights=np.asarray([1.0, 1.0]),
            is_accessible=[True, True],
            positions=[100, 110],
            strands=[0, 0],
            own_footprint=30,
        )
    finally:
        process._chromosome_rng = None
    # Both candidates are drawn in the same (only) batch and both pass the
    # occlusion/damage accessible_mask, but their footprints (30nt each,
    # 10nt apart) overlap -- only the first-processed one may be accepted,
    # exactly like real Karr's `excludeOverlappingRegions`.
    assert chosen == [0]


def test_sample_accessible_sites_batched_without_geometry_args_keeps_both(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    # Omitting positions/strands/own_footprint (the pre-2026-09-08 call
    # shape) must NOT apply the new exclusion -- confirms the new
    # behaviour is opt-in via those parameters, never silently applied to
    # an unrelated caller.
    process._chromosome_rng = _FixedOrderStream([1, 2])
    try:
        chosen = process._sample_accessible_sites_batched(
            n_needed=2,
            weights=np.asarray([1.0, 1.0]),
            is_accessible=[True, True],
        )
    finally:
        process._chromosome_rng = None
    assert chosen == [0, 1]


def test_sample_accessible_sites_batched_accepts_non_overlapping_candidates(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    process._chromosome_rng = _FixedOrderStream([1, 2])
    try:
        chosen = process._sample_accessible_sites_batched(
            n_needed=2,
            weights=np.asarray([1.0, 1.0]),
            is_accessible=[True, True],
            positions=[100, 1000],
            strands=[0, 0],
            own_footprint=30,
        )
    finally:
        process._chromosome_rng = None
    assert chosen == [0, 1]


class _SequencedOrderStream:
    """Like `_FixedOrderStream` but returns a DIFFERENT fixed 1-based
    order on each successive `randsample` call, to exercise
    `_sample_accessible_sites_batched`'s multi-batch (multiple
    while-loop iterations) quirk behavior."""

    def __init__(self, orders_1based: list[list[int]]) -> None:
        self._orders = [list(order) for order in orders_1based]
        self._call = 0

    def randsample(self, n: int, k: int, replacement: bool, w: np.ndarray) -> np.ndarray:
        del n, replacement, w
        order = self._orders[self._call]
        self._call += 1
        return np.asarray(order[:k], dtype=np.int64)


def test_exclude_overlapping_quirk_skips_first_k_new_candidates_on_second_batch(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    """Literal `excludeOverlappingRegions` quirk (Opus re-review): once
    `numel(idxs) == k` candidates are already accepted from a prior
    while-loop batch, the FIRST `k` NEW candidates of the NEXT batch are
    exempt from the overlap check entirely -- kept unconditionally, even
    if they overlap something already accepted.

    Real `sampleAccessibleRegions`'s batch size is
    `min(max(2*(n_needed-len(idxs)), 10), nnz(weights))` -- with 11 total
    candidates and `n_needed=2`, batch 1 draws `min(max(4,10),11)=10` of
    them (candidates 0-9, positions 100,110,...,190, footprint 30):
    candidate 0 (pos 100) is accepted; every one of 1-9 ends up excluded,
    each via a chained overlap with the immediately-preceding one at a
    10nt offset (the same "rejected candidate still blocks a later one"
    mechanic the companion test below exercises directly) -- so only
    candidate 0 is actually accepted from this 10-candidate batch, leaving
    `idxs=[0]` (`k=1`) and one still-undrawn candidate (index 10, weight
    still nonzero). Batch 2 then draws exactly that 1 remaining candidate
    (`n_more=min(max(2,10),1)=1`), placed at position 105 -- deliberately
    OVERLAPPING candidate 0's span ([100,129]). Without the quirk, this
    candidate would be checked against combined=[0] and excluded (it
    overlaps 0). WITH the quirk: this is new-candidate local index 1,
    and `k=1`, so `1 <= k` -- exempted from the check entirely, kept
    regardless. Final: `[0, 10]`, not `[0]` -- the quirk's effect is
    directly observable in the returned selection."""
    positions = [100 + 10 * i for i in range(10)] + [105]
    strands = [0] * 11
    weights = np.ones(11, dtype=np.float64)
    process._chromosome_rng = _SequencedOrderStream([list(range(1, 11)), [11]])
    try:
        chosen = process._sample_accessible_sites_batched(
            n_needed=2,
            weights=weights,
            is_accessible=[True] * 11,
            positions=positions,
            strands=strands,
            own_footprint=30,
        )
    finally:
        process._chromosome_rng = None
    assert chosen == [0, 10]


def test_exclude_overlapping_quirk_rejected_candidate_still_blocks_later_one(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    """A candidate excluded for overlapping an EARLIER one is still
    present in the comparison list for candidates checked AFTER it in the
    same batch -- it is never removed from consideration just because it
    was itself rejected. Three mutually-chained-overlapping candidates
    (0-1 overlap, 1-2 overlap, 0-2 do NOT overlap) drawn in a single batch
    (k=0, so no quirk exemption applies): candidate 0 accepted
    (nothing earlier); candidate 1 checked against combined=[0] ->
    overlaps 0 -> excluded; candidate 2 checked against combined=[0,1] ->
    does not overlap 0, but the exclusion decision must consider ALL
    earlier list entries regardless of their own accept/reject outcome --
    if candidate 1's rejection incorrectly removed it from consideration,
    candidate 2 would be evaluated only against 0 and (correctly) kept
    either way for THIS particular geometry, so this test uses a stricter
    chain where 2 also overlaps 1 (but not 0) to make the distinction
    observable: candidate 2 must be excluded because rejected-candidate 1
    still blocks it, even though 1 was never accepted."""
    # positions: 0 at 100 (footprint 30 -> span [100,129]), 1 at 120
    # (span [120,149], overlaps 0's span), 2 at 140 (span [140,169],
    # overlaps 1's span [120,149] at 140-149, but NOT 0's span [100,129]).
    process._chromosome_rng = _FixedOrderStream([1, 2, 3])
    try:
        chosen = process._sample_accessible_sites_batched(
            n_needed=3,
            weights=np.asarray([1.0, 1.0, 1.0]),
            is_accessible=[True, True, True],
            positions=[100, 120, 140],
            strands=[0, 0, 0],
            own_footprint=30,
        )
    finally:
        process._chromosome_rng = None
    # 0 accepted; 1 excluded (overlaps 0); 2 excluded (overlaps 1, even
    # though 1 was itself excluded -- 1 still counts as a blocker for 2).
    assert chosen == [0]


# ---------------------------------------------------------------------------
# _footprint_double_stranded_polymerized / _span_fully_polymerized
# ---------------------------------------------------------------------------


def test_footprint_double_stranded_polymerized_true_for_fully_covered_span(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    length = process.chromosome_shape[0]
    intervals_by_strand = {0: [(0, length)], 1: [(0, length)]}
    assert process._footprint_double_stranded_polymerized(intervals_by_strand, 1000, 0, tf_i=0) is True


def test_footprint_double_stranded_polymerized_false_when_one_substrand_missing(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    length = process.chromosome_shape[0]
    # Only strand 0 (not strand 1, the other half of the pair) is polymerized.
    intervals_by_strand = {0: [(0, length)]}
    assert process._footprint_double_stranded_polymerized(intervals_by_strand, 1000, 0, tf_i=0) is False


def test_footprint_double_stranded_polymerized_false_for_partial_footprint_coverage(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    own_footprint = int(process._own_footprint_by_tf[0])
    # Both sub-strands polymerized, but only PART of the footprint span
    # (a short run ending before the footprint's far edge) -- must fail,
    # since real isRegionDoubleStranded requires the WHOLE query span.
    short_run = max(1, own_footprint - 5)
    intervals_by_strand = {0: [(1000, short_run)], 1: [(1000, short_run)]}
    assert process._footprint_double_stranded_polymerized(intervals_by_strand, 1000, 0, tf_i=0) is False


def test_footprint_double_stranded_polymerized_handles_wraparound_run(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    # A single run starting well AFTER the query position but whose
    # length wraps circularly all the way back around to cover it (the
    # exact bug this module's _span_fully_polymerized fixes: a naive
    # "rel_start >= span_len -> skip" check would incorrectly discard
    # this run instead of recognizing its wraparound coverage).
    own_footprint = int(process._own_footprint_by_tf[0])
    length = process.chromosome_shape[0]
    query_position = 1000
    run_start = 9000
    rel_start = (run_start - query_position) % length
    # Sized so the run wraps exactly far enough to cover [0, own_footprint)
    # in the query's relative frame.
    run_len = length + own_footprint - rel_start
    intervals_by_strand = {0: [(run_start, run_len)], 1: [(run_start, run_len)]}
    assert (
        process._footprint_double_stranded_polymerized(
            intervals_by_strand, query_position, 0, tf_i=0
        )
        is True
    )


def test_span_fully_polymerized_false_for_empty_intervals(
    process: KarrTranscriptionalRegulationProcess,
) -> None:
    assert (
        process._span_fully_polymerized({}, 1000, 30, 0, process.chromosome_shape[0]) is False
    )


# ---------------------------------------------------------------------------
# Chromosome-RNG-ledger fail-closed persistence contract
# ---------------------------------------------------------------------------


def test_ledger_stream_injected_as_chromosome_rng_replays_recorded_draws() -> None:
    stream = TxRegChromosomeLedgerRandStream([0.1, 0.9], tick_label="unit-test-tick")
    assert stream.rand() == pytest.approx(0.1)
    assert stream.rand() == pytest.approx(0.9)
    stream.assert_fully_consumed()


def test_missing_chromosome_rng_on_active_tick_raises(process: KarrTranscriptionalRegulationProcess) -> None:
    process._chromosome_rng = None
    with pytest.raises(RuntimeError, match="_chromosome_rng is None"):
        process._sample_accessible_sites_batched(n_needed=1, weights=np.asarray([1.0, 1.0]))


# ---------------------------------------------------------------------------
# _load_releasable_proteins fail-closed contract
# ---------------------------------------------------------------------------


def test_load_releasable_proteins_raises_on_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError, match="not found"):
        _load_releasable_proteins(str(missing), n_tf=5)


def test_load_releasable_proteins_raises_on_empty_per_tf(tmp_path: Path) -> None:
    fixture = tmp_path / "releasable.json"
    fixture.write_text(json.dumps({"per_tf": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="per_tf"):
        _load_releasable_proteins(str(fixture), n_tf=5)


def test_load_releasable_proteins_raises_on_missing_own_footprint(tmp_path: Path) -> None:
    fixture = tmp_path / "releasable.json"
    fixture.write_text(
        json.dumps({"per_tf": [{"local_idx": 1, "releasable_monomer_global_idxs": []}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="own_footprint"):
        _load_releasable_proteins(str(fixture), n_tf=5)


def test_load_releasable_proteins_raises_on_out_of_range_local_idx(tmp_path: Path) -> None:
    fixture = tmp_path / "releasable.json"
    fixture.write_text(
        json.dumps({"per_tf": [{"local_idx": 99, "own_footprint": 10.0}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="local_idx"):
        _load_releasable_proteins(str(fixture), n_tf=5)


def test_load_releasable_proteins_raises_on_incomplete_tf_coverage(tmp_path: Path) -> None:
    fixture = tmp_path / "releasable.json"
    fixture.write_text(
        json.dumps({"per_tf": [{"local_idx": 1, "own_footprint": 30.0}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no entry for local TF index"):
        _load_releasable_proteins(str(fixture), n_tf=5)


def test_load_releasable_proteins_accepts_well_formed_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "releasable.json"
    fixture.write_text(
        json.dumps(
            {
                "per_tf": [
                    {
                        "local_idx": 1,
                        "own_footprint": 30.0,
                        "releasable_monomer_global_idxs": [5, 6],
                        "releasable_complex_global_idxs": [7],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monomer_sets, complex_sets, own_footprints = _load_releasable_proteins(str(fixture), n_tf=1)
    assert own_footprints[0] == 30.0
    assert monomer_sets[0] == {5, 6}
    assert complex_sets[0] == {7}
