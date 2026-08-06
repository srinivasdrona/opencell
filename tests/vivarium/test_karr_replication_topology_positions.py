"""Standalone tests for the literal Okazaki-fragment position/index getters.

These exercise `KarrReplicationProcess._helicase_positions` /
`_leading_polymerase_positions` / `_lagging_polymerase_positions` /
`_backup_beta_clamp_positions` / `_leading_position` / `_lagging_position` /
`_okazaki_fragment_index` / `_okazaki_fragment_position` /
`_okazaki_fragment_length` / `_okazaki_fragment_progress` against the real
fixture-derived `primase_binding_locations` arrays and hand-derived 0-based
translations of `Replication.m`'s getters (see docstrings on each production
method for the exact `:line` anchors). None of these tests read the oracle
trace file -- only the process fixture (constants) and hand-built
`complexBoundSites`/`polymerizedRegions` sparse triples, per adjudication #7
("no trace-after/oracle-file access").
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencell.state.chromosome_store import SparseTriplet
from opencell.vivarium.karr_replication import KarrReplicationProcess, ReplicationTopologyError


@pytest.fixture(scope="module")
def process() -> KarrReplicationProcess:
    return KarrReplicationProcess({})


def _bound_sites(process: KarrReplicationProcess, entries: list[tuple[int, int, int]]) -> SparseTriplet:
    return SparseTriplet.from_regions(entries, shape=process.chromosome_shape)


def _empty_polymerized(process: KarrReplicationProcess) -> SparseTriplet:
    return SparseTriplet.empty(*process.chromosome_shape)


# ---------------------------------------------------------------------------
# Helicase / polymerase / backup-beta-clamp position getters
# ---------------------------------------------------------------------------


def test_helicase_positions_both_bound(process: KarrReplicationProcess) -> None:
    lead0, lead1 = process.leading_strand_indexs
    sites = _bound_sites(
        process,
        [
            (1000, lead0, process.helicase_global_index),
            (2000, lead1, process.helicase_global_index),
        ],
    )
    assert process._helicase_positions(sites) == (1000, 2000)


def test_helicase_positions_none_bound_returns_sentinel(process: KarrReplicationProcess) -> None:
    sites = _empty_polymerized(process)
    assert process._helicase_positions(sites) == (-1, -1)


def test_helicase_positions_more_than_one_raises(process: KarrReplicationProcess) -> None:
    lead0 = process.leading_strand_indexs[0]
    sites = _bound_sites(
        process,
        [
            (1000, lead0, process.helicase_global_index),
            (1500, lead0, process.helicase_global_index),
        ],
    )
    with pytest.raises(ReplicationTopologyError):
        process._helicase_positions(sites)


def test_leading_polymerase_positions_matches_either_global_index(process: KarrReplicationProcess) -> None:
    lead0, lead1 = process.leading_strand_indexs
    sites = _bound_sites(
        process,
        [
            (1000, lead0, process.core_beta_clamp_gamma_complex_global_index),
            (2000, lead1, process.two_core_beta_clamp_gamma_complex_primase_global_index),
        ],
    )
    assert process._leading_polymerase_positions(sites) == (1000, 2000)


def test_leading_polymerase_positions_more_than_one_raises(process: KarrReplicationProcess) -> None:
    lead0 = process.leading_strand_indexs[0]
    sites = _bound_sites(
        process,
        [
            (1000, lead0, process.core_beta_clamp_gamma_complex_global_index),
            (1500, lead0, process.two_core_beta_clamp_gamma_complex_primase_global_index),
        ],
    )
    with pytest.raises(ReplicationTopologyError):
        process._leading_polymerase_positions(sites)


def test_lagging_polymerase_positions_max_min_semantics(process: KarrReplicationProcess) -> None:
    lag0, lag1 = process.lagging_strand_indexs
    sites = _bound_sites(
        process,
        [
            (1000, lag0, process.core_beta_clamp_primase_global_index),
            (2000, lag0, process.core_beta_clamp_primase_global_index),
            (5000, lag1, process.core_beta_clamp_primase_global_index),
            (4000, lag1, process.core_beta_clamp_primase_global_index),
        ],
    )
    positions = process._lagging_polymerase_positions(sites)
    assert positions == (2000, 4000)


def test_lagging_polymerase_positions_allows_transient_handoff_of_two(
    process: KarrReplicationProcess,
) -> None:
    lag0 = process.lagging_strand_indexs[0]
    sites = _bound_sites(
        process,
        [
            (1000, lag0, process.core_beta_clamp_primase_global_index),
            (2000, lag0, process.core_beta_clamp_primase_global_index),
        ],
    )
    # 2 matches allowed (transient handoff), matches Replication.m:1457-1469.
    assert process._lagging_polymerase_positions(sites)[0] == 2000


def test_lagging_polymerase_positions_more_than_two_raises(process: KarrReplicationProcess) -> None:
    lag0 = process.lagging_strand_indexs[0]
    sites = _bound_sites(
        process,
        [
            (1000, lag0, process.core_beta_clamp_primase_global_index),
            (2000, lag0, process.core_beta_clamp_primase_global_index),
            (3000, lag0, process.core_beta_clamp_primase_global_index),
        ],
    )
    with pytest.raises(ReplicationTopologyError):
        process._lagging_polymerase_positions(sites)


def test_backup_beta_clamp_positions(process: KarrReplicationProcess) -> None:
    lag0, lag1 = process.lagging_strand_indexs
    sites = _bound_sites(
        process,
        [
            (1000, lag0, process.beta_clamp_global_index),
            (2000, lag1, process.beta_clamp_global_index),
        ],
    )
    assert process._backup_beta_clamp_positions(sites) == (1000, 2000)


# ---------------------------------------------------------------------------
# leadingPosition / laggingPosition offset+wrap formulas
# ---------------------------------------------------------------------------


def test_leading_position_offsets_match_hand_derivation(process: KarrReplicationProcess) -> None:
    seq_len = process.sequence_len_bp
    leading_pol_pos = (100, 100)
    result = process._leading_position(leading_pol_pos)
    expected0 = (100 + process.core_footprint_5prime_bp) % seq_len
    expected1 = (
        100 + process.polymerase_holoenzyme_footprint_bp - process.core_footprint_5prime_bp - 1
    ) % seq_len
    assert result == (expected0, expected1)


def test_leading_position_unbound_sentinel_propagates(process: KarrReplicationProcess) -> None:
    assert process._leading_position((-1, -1)) == (-1, -1)


def test_lagging_position_offsets_match_hand_derivation(process: KarrReplicationProcess) -> None:
    seq_len = process.sequence_len_bp
    lagging_pol_pos = (200, 200)
    result = process._lagging_position(lagging_pol_pos)
    expected0 = (
        200 + process.polymerase_holoenzyme_footprint_bp - process.core_footprint_5prime_bp - 1
    ) % seq_len
    expected1 = (200 + process.core_footprint_5prime_bp) % seq_len
    assert result == (expected0, expected1)


def test_leading_position_wraps_past_sequence_end(process: KarrReplicationProcess) -> None:
    seq_len = process.sequence_len_bp
    # Column 1 offset is `+corFtpt5`; push position near the end so it wraps.
    near_end = seq_len - 1
    result = process._leading_position((near_end, -1))
    expected0 = (near_end + process.core_footprint_5prime_bp) % seq_len
    assert result[0] == expected0
    assert result[0] < seq_len


# ---------------------------------------------------------------------------
# okazakiFragmentIndex / Position / Length / Progress -- both strand arrays,
# including region B (column 2, `primase_binding_locations[1]`, ascending).
# ---------------------------------------------------------------------------


def test_fragment_index_column0_first_fragment_at_and_above_first_site(
    process: KarrReplicationProcess,
) -> None:
    # Column 0 array (`primase_binding_locations[0]`) is descending. Fragment
    # 1 ("mother remainder" spanning the first site up to the sequence end,
    # `okazakiFragmentLength`'s `elseif fIdx==1: ends=sequenceLen` branch) is
    # active for any position >= array0[0] -- verified empirically against
    # the real seed0 oracle trace (tick 30: helicase/lagging polymerase
    # bound, laggingPosition column0 == 579302 > array0[0] == 578691,
    # derived fragment index == 1).
    array0 = process.primase_binding_locations[0]
    fidx_at_site = process._okazaki_fragment_index((int(array0[0]), -1), _empty_polymerized(process))
    assert fidx_at_site[0] == 1
    fidx_above_site = process._okazaki_fragment_index(
        (int(array0[0]) + 500, -1), _empty_polymerized(process)
    )
    assert fidx_above_site[0] == 1


def test_fragment_index_column0_advances_once_position_drops_below_first_site(
    process: KarrReplicationProcess,
) -> None:
    array0 = process.primase_binding_locations[0]
    # Position just below the first (largest) descending site -> crosses
    # into fragment 2's range `[array0[1], array0[0])`.
    lagging_pos = (int(array0[0]) - 1, -1)
    fidx = process._okazaki_fragment_index(lagging_pos, _empty_polymerized(process))
    assert fidx[0] == 2


def test_fragment_index_column0_last_fragment_at_final_site(process: KarrReplicationProcess) -> None:
    array0 = process.primase_binding_locations[0]
    # Position exactly at the smallest (last) descending site -> the final
    # fragment (index == array0.size), matching the seed0 trace's terC-
    # adjacent behavior.
    lagging_pos = (int(array0[-1]), -1)
    fidx = process._okazaki_fragment_index(lagging_pos, _empty_polymerized(process))
    assert fidx[0] == array0.size


def test_fragment_index_column0_unbound_below_last_site(process: KarrReplicationProcess) -> None:
    array0 = process.primase_binding_locations[0]
    # Below the smallest site: fork1 has passed all its own Okazaki
    # fragments (terC-adjacent / terminated); no `array0` entry satisfies
    # `<= threshold`, so the getter reports the same "unbound" sentinel (0)
    # `initiateOkazakiFragment` treats as "eligible to (re)start" -- correct
    # per source, since this getter never distinguishes "not yet started"
    # from "already terminated" (both read as fIdx == 0).
    lagging_pos = (int(array0[-1]) - 1, -1)
    fidx = process._okazaki_fragment_index(lagging_pos, _empty_polymerized(process))
    assert fidx[0] == 0


def test_fragment_index_region_b_column1_first_fragment_at_and_below_first_site(
    process: KarrReplicationProcess,
) -> None:
    # Region B: column 1 array (`primase_binding_locations[1]`) is ascending.
    # Fragment 1 (`okazakiFragmentLength`'s `elseif fIdx==1: ends=0` branch,
    # 0-based) is active for any position <= array1[0].
    array1 = process.primase_binding_locations[1]
    fidx_at_site = process._okazaki_fragment_index((-1, int(array1[0])), _empty_polymerized(process))
    assert fidx_at_site[1] == 1
    fidx_below_site = process._okazaki_fragment_index(
        (-1, int(array1[0]) - 500), _empty_polymerized(process)
    )
    assert fidx_below_site[1] == 1


def test_fragment_index_region_b_advances_once_position_rises_above_first_site(
    process: KarrReplicationProcess,
) -> None:
    array1 = process.primase_binding_locations[1]
    lagging_pos = (-1, int(array1[0]) + 1)
    fidx = process._okazaki_fragment_index(lagging_pos, _empty_polymerized(process))
    assert fidx[1] == 2


def test_fragment_index_region_b_last_fragment_at_final_site(process: KarrReplicationProcess) -> None:
    array1 = process.primase_binding_locations[1]
    lagging_pos = (-1, int(array1[-1]))
    fidx = process._okazaki_fragment_index(lagging_pos, _empty_polymerized(process))
    assert fidx[1] == array1.size


def test_fragment_position_matches_array_lookup(process: KarrReplicationProcess) -> None:
    array0 = process.primase_binding_locations[0]
    array1 = process.primase_binding_locations[1]
    fpos = process._okazaki_fragment_position((1, 1))
    assert fpos == (int(array0[0]), int(array1[0]))


def test_fragment_position_unbound_is_zero(process: KarrReplicationProcess) -> None:
    assert process._okazaki_fragment_position((0, 0)) == (0, 0)


def test_fragment_length_first_fragment_column0_ends_at_sequence_end(
    process: KarrReplicationProcess,
) -> None:
    array0 = process.primase_binding_locations[0]
    length = process._okazaki_fragment_length((1, 0))
    expected = abs((process.sequence_len_bp - 1) - int(array0[0])) + 1
    assert length[0] == expected
    assert length[1] == 0


def test_fragment_length_first_fragment_column1_ends_at_zero(process: KarrReplicationProcess) -> None:
    array1 = process.primase_binding_locations[1]
    length = process._okazaki_fragment_length((0, 1))
    expected = abs(0 - int(array1[0])) + 1
    assert length[1] == expected
    assert length[0] == 0


def test_fragment_length_interior_fragment_matches_site_gap(process: KarrReplicationProcess) -> None:
    array0 = process.primase_binding_locations[0]
    length = process._okazaki_fragment_length((2, 0))
    expected = abs((int(array0[0]) - 1) - int(array0[1])) + 1
    assert length[0] == expected


def test_fragment_progress_is_distance_above_fragment_lower_reference(
    process: KarrReplicationProcess,
) -> None:
    # Column 0 fragment 1's active range is position >= array0[0] (matching
    # the fragment-index tests above); progress grows as position rises
    # above that lower reference (empirically confirmed: seed0 trace tick 99
    # showed fIdx=4, position 11bp above `array0[3]`, progress==11).
    array0 = process.primase_binding_locations[0]
    lagging_pos = (int(array0[0]) + 5, -1)
    fidx = (1, 0)
    progress = process._okazaki_fragment_progress(lagging_pos, fidx)
    assert progress[0] == 5
    assert progress[1] == 0


def test_fragment_progress_region_b_is_distance_below_fragment_upper_reference(
    process: KarrReplicationProcess,
) -> None:
    # Region B (column 1) fragment 1's active range is position <=
    # array1[0]; progress grows as position falls below that upper
    # reference (mirror image of column 0 -- empirically confirmed: seed0
    # trace tick 30 showed fIdx=1, position 311bp below `array1[0]`,
    # progress==311).
    array1 = process.primase_binding_locations[1]
    lagging_pos = (-1, int(array1[0]) - 7)
    fidx = (0, 1)
    progress = process._okazaki_fragment_progress(lagging_pos, fidx)
    assert progress[1] == 7
    assert progress[0] == 0


# ---------------------------------------------------------------------------
# isRegionPolymerized correction term (affects fragment-index boundary math).
# ---------------------------------------------------------------------------


def test_is_region_polymerized_true_when_covered(process: KarrReplicationProcess) -> None:
    strand = process.lagging_strand_indexs[0]
    polymerized = SparseTriplet.from_regions([(100, strand, 50)], shape=process.chromosome_shape)
    assert process._is_region_polymerized(polymerized, 120, strand) is True
    assert process._is_region_polymerized(polymerized, 99, strand) is False
    assert process._is_region_polymerized(polymerized, 150, strand) is False


def test_is_region_polymerized_false_on_empty_triplet(process: KarrReplicationProcess) -> None:
    polymerized = _empty_polymerized(process)
    assert process._is_region_polymerized(polymerized, 100, process.lagging_strand_indexs[0]) is False


# ---------------------------------------------------------------------------
# `_growth_window` -- literal `Chromosome.setRegionPolymerized` position
# normalization (`positionsStrands(:,1) = positionsStrands(:,1) +
# min(0, lengths+1)`, Chromosome.m:1988-1989). Regression coverage for the
# off-by-one bug discovered at seed0 tick 75: the naive
# `sorted((anchor, anchor + direction*step))` window used for BOTH
# directions is correct for `direction=+1` (forward growth, e.g. column 0's
# lagging strand) but silently drops the anchor bp for `direction=-1`
# (backward growth, e.g. column 1's lagging strand and column 0's leading/
# helicase advance), which only became visible once a fragment's growth
# reached exactly to its terminal boundary (oriC=0) with no further step to
# compensate the dropped bp.
# ---------------------------------------------------------------------------


def test_growth_window_forward_direction_matches_naive_convention(process: KarrReplicationProcess) -> None:
    # direction=+1: anchor is the inclusive low edge, unaffected by the fix
    # (`min(0, positive)=0` leaves `pos` unchanged in the MATLAB source).
    assert process._growth_window(1000, direction=1, step=25) == (1000, 1025)
    assert process._growth_window(0, direction=1, step=1) == (0, 1)


def test_growth_window_backward_direction_shifts_by_one(process: KarrReplicationProcess) -> None:
    # direction=-1: anchor is the inclusive HIGH edge -- `hi=anchor+1,
    # lo=anchor-step+1` -- NOT the naive `sorted((anchor, anchor-step)) ==
    # (anchor-step, anchor)`.
    assert process._growth_window(49, direction=-1, step=50) == (0, 50)
    assert process._growth_window(1000, direction=-1, step=25) == (976, 1001)


def test_growth_window_backward_direction_seed0_tick75_boundary_case(
    process: KarrReplicationProcess,
) -> None:
    """Exact seed0/tick-75 column-1 lagging-strand values (see
    `_probe_seed0_tick75c.py`/`_probe_strand_growth.py` diagnostics):
    `lagging_pos[1]=49` (pre-advance anchor), `step=50` (the fragment's
    exact remaining length, `fragment_length[1]=2061` minus
    `fragment_progress[1]=2011`). The correct window `[0, 50)` touches
    (merges cleanly with, no gap, no wrap) the real oracle's pre-existing
    `[50, 2061)` region into a complete `[0, 2061)` fragment -- the naive
    `sorted((49, 49-50)) == (-1, 49)` instead produced a spurious 1bp wrap
    past oriC that collided with column 0's own real region on the same
    strand, crashing `merge_adjacent_regions` with an "overlapping
    regions" `ValueError`."""
    lo, hi = process._growth_window(49, direction=-1, step=50)
    assert (lo, hi) == (0, 50)
    # Touches (does not overlap, does not gap) the real pre-existing
    # [50, 2061) region.
    assert hi == 50


# ---------------------------------------------------------------------------
# `_extend_polymerized_region` -- origin-wraparound splitting. Regression
# coverage for the corruption discovered at seed0 tick 75 (BEFORE the
# `_growth_window` fix was also applied, `_extend_polymerized_region` was
# reached with a genuinely wrapping `lo=-1, hi=49` span): `SparseTriplet`'s
# canonicalization (`chromosome_store.py::_canonicalize_triplet`,
# `positions = np.mod(positions, row_count)`) only wraps the START
# position, not the paired length, so an unsplit wrapping span silently
# corrupts into an invalid region exceeding the chromosome length. This
# wraparound-split logic remains necessary for any future genuine
# wraparound case (e.g. a multi-column-of-budget single advance step that
# spans the origin), even though the specific tick-75 crash turned out to
# additionally require the `_growth_window` fix to avoid a wrap
# altogether.
# ---------------------------------------------------------------------------


def test_extend_polymerized_region_splits_origin_wrapping_span(
    process: KarrReplicationProcess,
) -> None:
    strand = int(process.lagging_strand_indexs[1])
    row_count = process.chromosome_shape[0]
    polymerized = _empty_polymerized(process)
    extended = process._extend_polymerized_region(polymerized, strand=strand, lo=-1, hi=49)
    regions = sorted(r for r in extended.to_regions() if r[1] == strand)
    # Split into 2 non-wrapping, non-overlapping entries covering exactly
    # the requested 50bp span (1bp at the chromosome's high end + 49bp from
    # the origin), never a single overflowing region.
    assert regions == [(0, strand, 49), (row_count - 1, strand, 1)]
    assert sum(length for _pos, _strand, length in regions) == 49 + 1
    for pos, _strand, length in regions:
        assert pos >= 0
        assert pos + length <= row_count


def test_extend_polymerized_region_non_wrapping_span_unaffected(
    process: KarrReplicationProcess,
) -> None:
    strand = int(process.lagging_strand_indexs[0])
    polymerized = _empty_polymerized(process)
    extended = process._extend_polymerized_region(polymerized, strand=strand, lo=100, hi=150)
    regions = [r for r in extended.to_regions() if r[1] == strand]
    assert regions == [(100, strand, 50)]
