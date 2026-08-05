"""Standalone tests for the c1 (SSB-gate getters) and c2 (fail-closed scoped
occlusion/terC-linking guards) additions to `KarrReplicationProcess`.

c1 ports Replication.m:1583-1673 (`get.leadingStrandBoundSSBs`/
`get.laggingStrandBoundSSBs`/`get.numLaggingTemplateBoundSSBs`/
`get.areLaggingStrandSSBSitesBound`) literally, using the fixture-derived
footprint/spacing constants and the real `primase_binding_locations` arrays
(no fabricated numbers -- every threshold below is hand-derived from those
constants, see comments).

c2 is a scoped, source-faithful stand-in for the generic
`Chromosome.isRegionAccessible` extent machinery (Replication.m:786-801) and
the terC linking-number veto (Replication.m:820-838), both explicitly
deferred for this port (adjudication #2 and its follow-up "generic
occlusion narrowly but fail closed" adjudication): the RNA-polymerase-
collision-stall path (Replication.m:846-863) and the terC linking-number
veto remain explicit, hard-fail-with-telemetry conditions
(`_assert_no_rna_polymerase_occlusion`/`_assert_no_terc_linking_veto`);
ordinary foreign chromosome occupancy (e.g. a bound DnaA-ATP complex) is
instead handled by `_occlusion_advance_cap`, a literal, narrowly-scoped port
of `isRegionAccessible`'s extent-cap arithmetic (Replication.m:786-796,
`Chromosome.m:651-745`/`calculateFootprintOverhangs` at `Chromosome.m:4241-
4244`) that REDUCES (never raises on) the requested advance to stop short
of the nearest foreign complex's own footprint.

No oracle trace file is read anywhere in this file (adjudication #7:
"no trace-after/oracle-file access").
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet
from opencell.vivarium.karr_replication import KarrReplicationProcess, ReplicationTopologyError


@pytest.fixture(scope="module")
def process() -> KarrReplicationProcess:
    return KarrReplicationProcess({})


def _bound_sites(process: KarrReplicationProcess, entries: list[tuple[int, int, int]]) -> SparseTriplet:
    return SparseTriplet.from_regions(entries, shape=process.chromosome_shape)


def _empty_triplet(process: KarrReplicationProcess) -> SparseTriplet:
    return SparseTriplet.empty(*process.chromosome_shape)


# ----------------------------------------------------------------------
# c1: _fragment_start_or_boundary
# ----------------------------------------------------------------------


def test_fragment_start_or_boundary_fallback_when_no_fragment_bound(
    process: KarrReplicationProcess,
) -> None:
    # Replication.m:1610-1631: `fIdx == 0` falls back to the chromosome end
    # (column 0, "left" fork) or oriC/position 0 (column 1, "right" fork).
    assert process._fragment_start_or_boundary(0, 0) == process.sequence_len_bp - 1
    assert process._fragment_start_or_boundary(0, 1) == 0


def test_fragment_start_or_boundary_uses_primase_binding_locations(
    process: KarrReplicationProcess,
) -> None:
    assert process._fragment_start_or_boundary(1, 0) == int(process.primase_binding_locations[0][0])
    assert process._fragment_start_or_boundary(1, 1) == int(process.primase_binding_locations[1][0])
    assert process._fragment_start_or_boundary(2, 0) == int(process.primase_binding_locations[0][1])
    assert process._fragment_start_or_boundary(2, 1) == int(process.primase_binding_locations[1][1])


# ----------------------------------------------------------------------
# c1: _num_lagging_template_bound_ssbs / _are_lagging_strand_ssb_sites_bound
# ----------------------------------------------------------------------
#
# Window construction (both columns use fragment_index=1, i.e. the first
# real Okazaki fragment already primed, so `starts` is a real
# `primase_binding_locations` entry rather than the fallback):
#   col 0: starts0 = primase_binding_locations[0][0]; window = (helicase0, starts0)
#          on strand leading_strand_indexs[1].
#   col 1: starts1 = primase_binding_locations[1][0]; window = (starts1, helicase1)
#          on strand leading_strand_indexs[0].
#
# Threshold derivation (Replication.m:1660-1671):
#   floor((window_width - leadFtpt - lagFtpt) / (ssbFtpt + ssbSpcg) - 2)
# With fixture constants leadFtpt=lagFtpt=49, ssbFtpt=145, ssbSpcg=30 (sum
# 175), choosing window_width=798 gives
#   floor((798 - 98) / 175 - 2) = floor(4.0 - 2) = 2
# i.e. exactly 2 bound SSBs are required for `areLaggingStrandSSBSitesBound`
# to flip true.


def _window_width_for_threshold(threshold: int) -> int:
    lead_ftpt = 49
    lag_ftpt = 49
    ssb_ftpt = 145
    ssb_spcg = 30
    # Choose width so floor(diff/(ssb_ftpt+ssb_spcg) - 2) == threshold exactly,
    # landing diff on an exact multiple of (ssb_ftpt + ssb_spcg) to avoid an
    # off-by-one from floor() at the boundary.
    diff = (threshold + 2) * (ssb_ftpt + ssb_spcg)
    return diff + lead_ftpt + lag_ftpt


def test_num_lagging_template_bound_ssbs_counts_column0_window(
    process: KarrReplicationProcess,
) -> None:
    starts0 = int(process.primase_binding_locations[0][0])
    width = _window_width_for_threshold(2)
    helicase0 = starts0 - width
    strand = process.leading_strand_indexs[1]
    sites = _bound_sites(
        process,
        [
            (helicase0 + 100, strand, process.ssb8mer_global_index),
            (helicase0 + 300, strand, process.ssb8mer_global_index),
            # Outside the window (beyond starts0): must not be counted.
            (starts0 + 10, strand, process.ssb8mer_global_index),
            # Outside the window (at/before helicase0): must not be counted.
            (helicase0, strand, process.ssb8mer_global_index),
        ],
    )
    count0, count1 = process._num_lagging_template_bound_ssbs(
        sites, helicase_pos=(helicase0, -1), fragment_index=(1, 0)
    )
    assert count0 == 2
    assert count1 == 0


def test_num_lagging_template_bound_ssbs_counts_column1_window(
    process: KarrReplicationProcess,
) -> None:
    starts1 = int(process.primase_binding_locations[1][0])
    width = _window_width_for_threshold(2)
    helicase1 = starts1 + width
    strand = process.leading_strand_indexs[0]
    sites = _bound_sites(
        process,
        [
            (starts1 + 100, strand, process.ssb8mer_global_index),
            (starts1 + 300, strand, process.ssb8mer_global_index),
            # Outside the window (before starts1): must not be counted.
            (starts1 - 10, strand, process.ssb8mer_global_index),
        ],
    )
    count0, count1 = process._num_lagging_template_bound_ssbs(
        sites, helicase_pos=(-1, helicase1), fragment_index=(0, 1)
    )
    assert count0 == 0
    assert count1 == 2


def test_are_lagging_strand_ssb_sites_bound_true_at_exact_threshold(
    process: KarrReplicationProcess,
) -> None:
    starts0 = int(process.primase_binding_locations[0][0])
    width = _window_width_for_threshold(2)
    helicase0 = starts0 - width
    strand = process.leading_strand_indexs[1]
    sites = _bound_sites(
        process,
        [
            (helicase0 + 100, strand, process.ssb8mer_global_index),
            (helicase0 + 300, strand, process.ssb8mer_global_index),
        ],
    )
    bound0, bound1 = process._are_lagging_strand_ssb_sites_bound(
        sites, helicase_pos=(helicase0, -1), fragment_index=(1, 0)
    )
    assert bound0 is True
    assert bound1 is False


def test_are_lagging_strand_ssb_sites_bound_false_one_short_of_threshold(
    process: KarrReplicationProcess,
) -> None:
    starts0 = int(process.primase_binding_locations[0][0])
    width = _window_width_for_threshold(2)
    helicase0 = starts0 - width
    strand = process.leading_strand_indexs[1]
    sites = _bound_sites(
        process,
        [
            (helicase0 + 100, strand, process.ssb8mer_global_index),
        ],
    )
    bound0, _ = process._are_lagging_strand_ssb_sites_bound(
        sites, helicase_pos=(helicase0, -1), fragment_index=(1, 0)
    )
    assert bound0 is False


def test_are_lagging_strand_ssb_sites_bound_false_when_helicase_unbound(
    process: KarrReplicationProcess,
) -> None:
    sites = _empty_triplet(process)
    bound0, bound1 = process._are_lagging_strand_ssb_sites_bound(
        sites, helicase_pos=(-1, -1), fragment_index=(0, 0)
    )
    assert bound0 is False
    assert bound1 is False


# ----------------------------------------------------------------------
# c2: _assert_no_rna_polymerase_occlusion
# ----------------------------------------------------------------------


def test_assert_no_rna_polymerase_occlusion_passes_on_empty_window(
    process: KarrReplicationProcess,
) -> None:
    sites = _empty_triplet(process)
    process._assert_no_rna_polymerase_occlusion(
        sites, strand=process.leading_strand_indexs[0], window_lo=1000, window_hi=2000, context="test"
    )


def test_assert_no_rna_polymerase_occlusion_passes_on_own_complex(
    process: KarrReplicationProcess,
) -> None:
    strand = process.leading_strand_indexs[0]
    sites = _bound_sites(process, [(1500, strand, process.helicase_global_index)])
    process._assert_no_rna_polymerase_occlusion(
        sites, strand=strand, window_lo=1000, window_hi=2000, context="test"
    )


def test_assert_no_rna_polymerase_occlusion_passes_on_generic_foreign_complex(
    process: KarrReplicationProcess,
) -> None:
    # Generic foreign occupancy (e.g. the standalone DNA_POLYMERASE_GAMMA_
    # COMPLEX subunit, never bound alone by this process -- only as part of
    # the `core_beta_clamp_gamma_complex`/`two_core_beta_clamp_gamma_complex_
    # primase` composites) is NOT an RNA-polymerase occupant, so this guard
    # must NOT raise for it -- that case is instead handled by
    # `_occlusion_advance_cap` (a reduction, not a hard fail); see the
    # "generic occlusion narrowly but fail closed... generic occupancy alone
    # must not raise" adjudication.
    strand = process.leading_strand_indexs[0]
    assert process.gamma_complex_global_index not in process._rna_polymerase_global_indexs
    sites = _bound_sites(process, [(1500, strand, process.gamma_complex_global_index)])
    process._assert_no_rna_polymerase_occlusion(
        sites, strand=strand, window_lo=1000, window_hi=2000, context="test"
    )


def test_assert_no_rna_polymerase_occlusion_passes_on_own_complex_different_strand(
    process: KarrReplicationProcess,
) -> None:
    # An RNA-polymerase occupant on a *different* strand than the one being
    # checked must not trigger the guard.
    strand = process.leading_strand_indexs[0]
    other_strand = process.leading_strand_indexs[1]
    sites = _bound_sites(process, [(1500, other_strand, process.rna_polymerase_global_index)])
    process._assert_no_rna_polymerase_occlusion(
        sites, strand=strand, window_lo=1000, window_hi=2000, context="test"
    )


def test_assert_no_rna_polymerase_occlusion_raises_on_rna_polymerase(
    process: KarrReplicationProcess,
) -> None:
    strand = process.leading_strand_indexs[0]
    sites = _bound_sites(process, [(1500, strand, process.rna_polymerase_global_index)])
    with pytest.raises(ReplicationTopologyError, match="RNA-polymerase"):
        process._assert_no_rna_polymerase_occlusion(
            sites, strand=strand, window_lo=1000, window_hi=2000, context="fork-advance"
        )


def test_assert_no_rna_polymerase_occlusion_raises_on_rna_polymerase_holoenzyme(
    process: KarrReplicationProcess,
) -> None:
    strand = process.leading_strand_indexs[0]
    sites = _bound_sites(process, [(1500, strand, process.rna_polymerase_holoenzyme_global_index)])
    with pytest.raises(ReplicationTopologyError, match="RNA-polymerase"):
        process._assert_no_rna_polymerase_occlusion(
            sites, strand=strand, window_lo=1000, window_hi=2000, context="fork-advance"
        )


def test_assert_no_rna_polymerase_occlusion_noop_on_empty_or_inverted_window(
    process: KarrReplicationProcess,
) -> None:
    strand = process.leading_strand_indexs[0]
    sites = _bound_sites(process, [(1500, strand, process.rna_polymerase_global_index)])
    # window_hi <= window_lo must be treated as an empty (no-op) window even
    # though an RNA-polymerase occupant exists at a position that would
    # otherwise be "inside" the numeric range.
    process._assert_no_rna_polymerase_occlusion(
        sites, strand=strand, window_lo=2000, window_hi=1000, context="test"
    )
    process._assert_no_rna_polymerase_occlusion(
        sites, strand=strand, window_lo=1500, window_hi=1500, context="test"
    )


# ----------------------------------------------------------------------
# c2b: _occlusion_advance_cap -- literal isRegionAccessible extent-cap
# ----------------------------------------------------------------------
#
# `_footprint_overhangs` (calculateFootprintOverhangs, Chromosome.m:4241-
# 4244): footprint5 = ceil((total-1)/2), footprint3 = total-1-footprint5.
# MG_469_7MER_ATP (global-index 193, the exact complex/position the real
# tick-13 seed0 oracle replay hits): total footprint 11 -> (5, 5).
# DNA_POLYMERASE_GAMMA_COMPLEX (global-index 6, standalone/foreign here):
# total footprint 26 -> (13, 12).
#
# Cap derivation: d_max = direction*(foreign_pos-anchor) - foreign_ftpt5 -
# own_ftpt3 - 1, clipped to >=0.


def test_occlusion_advance_cap_noop_when_no_bound_sites(process: KarrReplicationProcess) -> None:
    sites = _empty_triplet(process)
    cap = process._occlusion_advance_cap(
        sites,
        strand=process.leading_strand_indexs[0],
        anchor=500_000,
        direction=-1,
        own_footprint_3prime=process.helicase_footprint_3prime_bp,
        requested_advance=200,
        context="test",
    )
    assert cap == 200


def test_occlusion_advance_cap_excludes_own_bindable_complex(process: KarrReplicationProcess) -> None:
    strand = process.leading_strand_indexs[0]
    sites = _bound_sites(process, [(499_950, strand, process.helicase_global_index)])
    cap = process._occlusion_advance_cap(
        sites,
        strand=strand,
        anchor=500_000,
        direction=-1,
        own_footprint_3prime=process.helicase_footprint_3prime_bp,
        requested_advance=200,
        context="test",
    )
    assert cap == 200


def test_occlusion_advance_cap_excludes_rna_polymerase(process: KarrReplicationProcess) -> None:
    # RNA-polymerase occupancy is handled exclusively by
    # `_assert_no_rna_polymerase_occlusion` (a hard fail); this cap function
    # must ignore it entirely (neither cap nor raise) so the two mechanisms
    # never silently disagree.
    strand = process.leading_strand_indexs[0]
    sites = _bound_sites(process, [(499_950, strand, process.rna_polymerase_global_index)])
    cap = process._occlusion_advance_cap(
        sites,
        strand=strand,
        anchor=500_000,
        direction=-1,
        own_footprint_3prime=process.helicase_footprint_3prime_bp,
        requested_advance=200,
        context="test",
    )
    assert cap == 200


def test_occlusion_advance_cap_excludes_obstacle_behind_own_edge(
    process: KarrReplicationProcess,
) -> None:
    # column 0 travels toward decreasing positions; a foreign complex
    # numerically *above* the anchor is behind this fork's own leading
    # edge and must not restrict a forward (decreasing) advance.
    strand = process.leading_strand_indexs[0]
    sites = _bound_sites(process, [(500_100, strand, process.gamma_complex_global_index)])
    cap = process._occlusion_advance_cap(
        sites,
        strand=strand,
        anchor=500_000,
        direction=-1,
        own_footprint_3prime=process.helicase_footprint_3prime_bp,
        requested_advance=200,
        context="test",
    )
    assert cap == 200


def test_occlusion_advance_cap_caps_at_nearest_foreign_complex_column0(
    process: KarrReplicationProcess,
) -> None:
    # gamma_complex (footprint 26 -> overhangs (13, 12)) placed 100bp ahead
    # (in the decreasing/column-0 travel direction) of the anchor:
    # d_max = 100 - 13 - own_ftpt3 - 1.
    strand = process.leading_strand_indexs[0]
    own_ftpt3 = process.helicase_footprint_3prime_bp
    anchor = 500_000
    foreign_pos = anchor - 100
    sites = _bound_sites(process, [(foreign_pos, strand, process.gamma_complex_global_index)])
    cap = process._occlusion_advance_cap(
        sites,
        strand=strand,
        anchor=anchor,
        direction=-1,
        own_footprint_3prime=own_ftpt3,
        requested_advance=200,
        context="test",
    )
    assert cap == 100 - 13 - own_ftpt3 - 1


def test_occlusion_advance_cap_caps_at_nearest_foreign_complex_column1(
    process: KarrReplicationProcess,
) -> None:
    # Mirror of the column-0 case above (direction=+1, strand
    # leading_strand_indexs[1]): the formula is direction-symmetric.
    strand = process.leading_strand_indexs[1]
    own_ftpt3 = process.helicase_footprint_3prime_bp
    anchor = 300_000
    foreign_pos = anchor + 100
    sites = _bound_sites(process, [(foreign_pos, strand, process.gamma_complex_global_index)])
    cap = process._occlusion_advance_cap(
        sites,
        strand=strand,
        anchor=anchor,
        direction=1,
        own_footprint_3prime=own_ftpt3,
        requested_advance=200,
        context="test",
    )
    assert cap == 100 - 13 - own_ftpt3 - 1


def test_occlusion_advance_cap_nearest_of_multiple_foreign_complexes(
    process: KarrReplicationProcess,
) -> None:
    strand = process.leading_strand_indexs[0]
    own_ftpt3 = process.helicase_footprint_3prime_bp
    anchor = 500_000
    near_pos = anchor - 100  # binding (smaller) cap
    far_pos = anchor - 5_000  # non-binding (larger) cap
    sites = _bound_sites(
        process,
        [
            (near_pos, strand, process.gamma_complex_global_index),
            (far_pos, strand, process.gamma_complex_global_index),
        ],
    )
    cap = process._occlusion_advance_cap(
        sites,
        strand=strand,
        anchor=anchor,
        direction=-1,
        own_footprint_3prime=own_ftpt3,
        requested_advance=10_000,
        context="test",
    )
    assert cap == 100 - 13 - own_ftpt3 - 1


def test_occlusion_advance_cap_zero_extent_benign_skip(process: KarrReplicationProcess) -> None:
    # Foreign complex placed exactly at the boundary where d_max == 0 (own
    # leading edge and the foreign complex's own footprint are immediately
    # adjacent, non-overlapping): the request must be capped to exactly 0,
    # not raise.
    strand = process.leading_strand_indexs[0]
    own_ftpt3 = process.helicase_footprint_3prime_bp
    foreign_footprint5, _ = process._footprint_overhangs(process._foreign_dna_footprint_by_global_index[process.gamma_complex_global_index])
    anchor = 500_000
    rel = foreign_footprint5 + own_ftpt3 + 1
    foreign_pos = anchor - rel
    sites = _bound_sites(process, [(foreign_pos, strand, process.gamma_complex_global_index)])
    cap = process._occlusion_advance_cap(
        sites,
        strand=strand,
        anchor=anchor,
        direction=-1,
        own_footprint_3prime=own_ftpt3,
        requested_advance=200,
        context="test",
    )
    assert cap == 0


def test_occlusion_advance_cap_wrap_oric_edge_obstacle_behind_is_ignored(
    process: KarrReplicationProcess,
) -> None:
    # A foreign complex sitting at position 0 (oriC, the numeric wrap
    # boundary of the position axis) is, for a column-1 fork that has
    # already advanced away from oriC, strictly BEHIND this fork's own
    # leading edge -- it must not restrict forward (increasing) advance,
    # and no chromosome-length modulo arithmetic is needed to get this
    # right (fork travel never re-crosses oriC).
    strand = process.leading_strand_indexs[1]
    own_ftpt3 = process.helicase_footprint_3prime_bp
    sites = _bound_sites(process, [(0, strand, process.gamma_complex_global_index)])
    cap = process._occlusion_advance_cap(
        sites,
        strand=strand,
        anchor=1_000,
        direction=1,
        own_footprint_3prime=own_ftpt3,
        requested_advance=200,
        context="test",
    )
    assert cap == 200


def test_occlusion_advance_cap_real_tick13_dnaa_atp_7mer_column0(
    process: KarrReplicationProcess,
) -> None:
    # Real hash-pinned seed0/100-tick oracle replay data (tick 13, before
    # this fix): helicase_pos[0]=578932, a bound MG_469_7MER_ATP
    # (global-index 193, "DnaA-ATP 7mer", total footprint 11 -> (5, 5)) at
    # position 578894 on strand leading_strand_indexs[0] -- the exact
    # complex/position/strand that used to hard-fail
    # `_assert_no_foreign_occlusion` and must now instead cap the helicase's
    # own advance to exactly 23 (= 38 - 5 - 9 - 1).
    dnaa_atp_7mer_global_index = 193
    assert process._foreign_dna_footprint_by_global_index[dnaa_atp_7mer_global_index] == 11
    strand = process.leading_strand_indexs[0]
    helicase_pos0 = 578_932
    sites = _bound_sites(process, [(578_894, strand, dnaa_atp_7mer_global_index)])
    cap = process._occlusion_advance_cap(
        sites,
        strand=strand,
        anchor=helicase_pos0,
        direction=-1,
        own_footprint_3prime=process.helicase_footprint_3prime_bp,
        requested_advance=92,
        context="test",
    )
    assert cap == 23


def test_occlusion_advance_cap_real_tick13_dnaa_atp_7mer_column1(
    process: KarrReplicationProcess,
) -> None:
    # Direction-mirrored synthetic replay of the same real complex/offset
    # (38bp ahead of the helicase in the direction of travel) for column 1.
    dnaa_atp_7mer_global_index = 193
    strand = process.leading_strand_indexs[1]
    helicase_pos1 = 300_000
    sites = _bound_sites(process, [(300_038, strand, dnaa_atp_7mer_global_index)])
    cap = process._occlusion_advance_cap(
        sites,
        strand=strand,
        anchor=helicase_pos1,
        direction=1,
        own_footprint_3prime=process.helicase_footprint_3prime_bp,
        requested_advance=92,
        context="test",
    )
    assert cap == 23


# ----------------------------------------------------------------------
# c2: _assert_no_terc_linking_veto
# ----------------------------------------------------------------------


def test_assert_no_terc_linking_veto_passes_when_window_misses_terc(
    process: KarrReplicationProcess,
) -> None:
    store = ChromosomeStore(shape=process.chromosome_shape)
    store.set_field(
        "linkingNumbers",
        SparseTriplet.from_regions(
            [(process.terc_position_bp + 10_000, process.leading_strand_indexs[0], 3)],
            shape=process.chromosome_shape,
        ),
    )
    process._assert_no_terc_linking_veto(
        store, column=0, window_lo=100, window_hi=200,
    )


def test_assert_no_terc_linking_veto_passes_when_linking_numbers_all_zero(
    process: KarrReplicationProcess,
) -> None:
    store = ChromosomeStore(shape=process.chromosome_shape)
    process._assert_no_terc_linking_veto(
        store,
        column=0,
        window_lo=process.terc_position_bp - 10,
        window_hi=process.terc_position_bp + 10,
    )


def test_assert_no_terc_linking_veto_raises_on_nonzero_linking_number_near_terc(
    process: KarrReplicationProcess,
) -> None:
    store = ChromosomeStore(shape=process.chromosome_shape)
    store.set_field(
        "linkingNumbers",
        SparseTriplet.from_regions(
            [(process.terc_position_bp, process.leading_strand_indexs[0], 5)],
            shape=process.chromosome_shape,
        ),
    )
    with pytest.raises(ReplicationTopologyError, match="terC linking-number veto"):
        process._assert_no_terc_linking_veto(
            store,
            column=0,
            window_lo=process.terc_position_bp - 10,
            window_hi=process.terc_position_bp + 10,
        )
