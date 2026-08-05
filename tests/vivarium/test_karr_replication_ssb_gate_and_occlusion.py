"""Standalone tests for the c1 (SSB-gate getters) and Finding-4 (RNA-
polymerase-collision Poisson-dwell stall + terC linking-number veto)
additions to `KarrReplicationProcess`.

c1 ports Replication.m:1583-1673 (`get.leadingStrandBoundSSBs`/
`get.laggingStrandBoundSSBs`/`get.numLaggingTemplateBoundSSBs`/
`get.areLaggingStrandSSBSitesBound`) literally, using the fixture-derived
footprint/spacing constants and the real `primase_binding_locations` arrays
(no fabricated numbers -- every threshold below is hand-derived from those
constants, see comments).

Finding 4 (2026-08-05) REPLACES the prior fail-closed stand-ins for the
RNA-polymerase-collision-stall path (Replication.m:845-863) and the terC
linking-number veto (Replication.m:820-843) -- `_assert_no_rna_polymerase_
occlusion`/`_assert_no_terc_linking_veto` (hard raises) are gone; this file
now tests their literal-port replacements, `_rna_polymerase_collision_stall`
(a real stochastic Poisson-dwell cap, using this process's own seeded
`self._rng`, never global state) and `_terc_linking_stall` (all 3 MATLAB
if/elseif branches). Ordinary foreign chromosome occupancy (e.g. a bound
DnaA-ATP complex) is unaffected by this Finding and remains handled by
`_occlusion_advance_cap`, a literal, narrowly-scoped port of
`isRegionAccessible`'s extent-cap arithmetic (Replication.m:786-796,
`Chromosome.m:651-745`/`calculateFootprintOverhangs` at `Chromosome.m:4241-
4244`) that REDUCES (never raises on) the requested advance to stop short
of the nearest foreign complex's own footprint.

No oracle trace file is read anywhere in this file (adjudication #7:
"no trace-after/oracle-file access").
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet
from opencell.vivarium.karr_replication import KarrReplicationProcess


@pytest.fixture(scope="module")
def process() -> KarrReplicationProcess:
    return KarrReplicationProcess({})


class _StubPoissonRNG:
    """Deterministic stand-in for `self._rng`, isolating
    `_rna_polymerase_collision_stall`'s single `.poisson(...)` draw: returns
    a fixed 4-cell dwelling pattern (0 == "dwelling", matching the
    production `poisson(...) == 0` test; any nonzero == "not dwelling"),
    regardless of the requested rate. `.random()` is intentionally absent
    -- `_rna_polymerase_collision_stall` itself never calls it, so any
    accidental call surfaces as an `AttributeError` rather than silently
    returning a plausible-looking value."""

    def __init__(self, dwelling: tuple[bool, bool, bool, bool]) -> None:
        self._dwelling = dwelling

    def poisson(self, *args: object, **kwargs: object) -> Any:
        return np.array([0 if dwell else 1 for dwell in self._dwelling])


class _StubCoinRNG:
    """Deterministic stand-in for `self._rng`, isolating `_terc_linking_
    stall`'s branch-1 (both-columns-crossing) fair-coin `.random()` draw."""

    def __init__(self, coin_value: float) -> None:
        self._coin_value = coin_value

    def random(self, *args: object, **kwargs: object) -> Any:
        return self._coin_value


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
# Finding 4: _rna_polymerase_collision_stall
# ----------------------------------------------------------------------


def test_rna_polymerase_collision_stall_noop_when_no_rna_polymerase_bound(
    process: KarrReplicationProcess,
) -> None:
    """Karr's own OUTER gate (Replication.m:846-848, `if any(tfs)`): with no
    RNA polymerase bound ANYWHERE on the chromosome, the whole mechanism is
    skipped entirely -- no draw, no cap, `leading_advance` passed through
    unchanged and both lagging caps `None`."""
    sites = _empty_triplet(process)
    process._rng = _StubPoissonRNG(dwelling=(True, True, True, True))
    advance0, advance1, cap0, cap1 = process._rna_polymerase_collision_stall(
        sites, helicase_pos=(1000, 5000), lagging_pol_pos=(-1, -1), leading_advance=(50, 60)
    )
    assert (advance0, advance1, cap0, cap1) == (50, 60, None, None)


def test_rna_polymerase_collision_stall_passthrough_when_not_dwelling(
    process: KarrReplicationProcess,
) -> None:
    """Gate fires (RNA polymerase bound somewhere), but this cell's own
    Poisson draw is NOT "dwelling" (nonzero draw) -- no cap applied."""
    strand = process.leading_strand_indexs[0]
    sites = _bound_sites(process, [(800, strand, process.rna_polymerase_global_index)])
    process._rng = _StubPoissonRNG(dwelling=(False, False, False, False))
    advance0, advance1, cap0, cap1 = process._rna_polymerase_collision_stall(
        sites, helicase_pos=(1000, 5000), lagging_pol_pos=(-1, -1), leading_advance=(50, 60)
    )
    assert (advance0, advance1, cap0, cap1) == (50, 60, None, None)


def test_rna_polymerase_collision_stall_caps_leading0_when_dwelling(
    process: KarrReplicationProcess,
) -> None:
    """Literal `tmpLimits(1,1)` (Replication.m:855): an RNA polymerase (or
    holoenzyme) bound on column 0's own strand pair, ahead of the helicase
    in its (decreasing) direction of travel, caps `leading_advance[0]` to
    the gap remaining before the RNA polymerase's own footprint -- but only
    when this cell's dwell draw fires."""
    strand = process.leading_strand_indexs[0]
    rna_pol_footprint = process._foreign_dna_footprint_by_global_index[process.rna_polymerase_global_index]
    helicase_pos0 = 1000
    rna_pol_pos = 800
    sites = _bound_sites(process, [(rna_pol_pos, strand, process.rna_polymerase_global_index)])
    process._rng = _StubPoissonRNG(dwelling=(True, False, False, False))
    advance0, advance1, cap0, cap1 = process._rna_polymerase_collision_stall(
        sites, helicase_pos=(helicase_pos0, 500_000), lagging_pol_pos=(-1, -1), leading_advance=(1_000, 60)
    )
    expected_cap = max(0, helicase_pos0 - (rna_pol_pos + rna_pol_footprint))
    assert advance0 == expected_cap
    assert advance1 == 60
    assert cap0 is None
    assert cap1 is None


def test_rna_polymerase_collision_stall_zeros_leading1_when_dwelling_with_no_rna_polymerase_in_own_quadrant(
    process: KarrReplicationProcess,
) -> None:
    """COUNTERINTUITIVE-BUT-LITERAL Karr behavior (verified directly against
    Replication.m:855-858's unconditional `tmpLimits = zeros(2, 2)`
    initialization): the outer gate is GLOBAL (any RNA polymerase bound
    ANYWHERE fires it for all 4 cells), but each cell's own `tmpLimits`
    value defaults to 0 when no RNA polymerase happens to be found in that
    cell's OWN quadrant -- so a "dwelling" draw for a cell with nothing
    nearby still zeroes it, rather than being treated as a benign no-op.
    Here the only bound RNA polymerase is on column 0's strands (nowhere
    near column 1's), yet column 1's leading advance is still zeroed
    because its own dwell draw fired."""
    col0_strand = process.leading_strand_indexs[0]
    sites = _bound_sites(process, [(800, col0_strand, process.rna_polymerase_global_index)])
    process._rng = _StubPoissonRNG(dwelling=(False, True, False, False))
    advance0, advance1, cap0, cap1 = process._rna_polymerase_collision_stall(
        sites, helicase_pos=(1000, 5000), lagging_pol_pos=(-1, -1), leading_advance=(50, 60)
    )
    assert advance0 == 50
    assert advance1 == 0
    assert cap0 is None
    assert cap1 is None


def test_rna_polymerase_collision_stall_caps_lagging0_budget_when_dwelling(
    process: KarrReplicationProcess,
) -> None:
    """Literal `tmpLimits(2,1)` (Replication.m:857): column 0's LAGGING
    strand cell deliberately checks column 1's own strand pair (the
    cross-column template relationship, matching `_num_lagging_template_
    bound_ssbs`), capping the returned `lagging_cap0` (a per-tick BUDGET
    cap, not a direct `leading_advance` element) rather than `advance0`."""
    col1_strand = process.leading_strand_indexs[1]
    holo_footprint = process.polymerase_holoenzyme_footprint_bp
    lagging_pol_pos0 = 2000
    rna_pol_pos = 2500
    sites = _bound_sites(process, [(rna_pol_pos, col1_strand, process.rna_polymerase_global_index)])
    process._rng = _StubPoissonRNG(dwelling=(False, False, True, False))
    advance0, advance1, cap0, cap1 = process._rna_polymerase_collision_stall(
        sites,
        helicase_pos=(1_000_000, 2_000_000),
        lagging_pol_pos=(lagging_pol_pos0, -1),
        leading_advance=(50, 60),
    )
    assert advance0 == 50
    assert advance1 == 60
    assert cap0 == max(0, rna_pol_pos - (lagging_pol_pos0 + holo_footprint))
    assert cap1 is None


def test_rna_polymerase_collision_stall_uses_first_rna_polymerase_index_footprint(
    process: KarrReplicationProcess,
) -> None:
    """Karr always uses the FIRST RNA polymerase index's footprint
    (`rnaPolFtpt = c.getDNAFootprint([], rnaPolymeraseIndexs(1))`)
    regardless of which RNA-polymerase VARIANT (`RNA_POLYMERASE` vs
    `RNA_POLYMERASE_HOLOENZYME`) is actually bound at a given site -- so
    the cap computed for a bound holoenzyme must use the SAME footprint
    constant as the bare-RNA-polymerase test above, not the holoenzyme's
    own (generally larger) footprint."""
    strand = process.leading_strand_indexs[0]
    rna_pol_footprint = process._foreign_dna_footprint_by_global_index[process.rna_polymerase_global_index]
    helicase_pos0 = 1000
    rna_pol_pos = 800
    sites = _bound_sites(process, [(rna_pol_pos, strand, process.rna_polymerase_holoenzyme_global_index)])
    process._rng = _StubPoissonRNG(dwelling=(True, False, False, False))
    advance0, _advance1, _cap0, _cap1 = process._rna_polymerase_collision_stall(
        sites, helicase_pos=(helicase_pos0, 500_000), lagging_pol_pos=(-1, -1), leading_advance=(1_000, 60)
    )
    assert advance0 == max(0, helicase_pos0 - (rna_pol_pos + rna_pol_footprint))


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
# Finding 4: _terc_linking_stall
# ----------------------------------------------------------------------


def _crossing_helicase_and_advance(
    process: KarrReplicationProcess, *, column: int, lead_bp: int
) -> tuple[int, int]:
    """Constructs a `(helicase_pos, advance)` pair for `column` such that
    `_terc_linking_stall`'s own "crosses terC this tick" predicate is
    satisfied by exactly `lead_bp` bp (the helicase's own 5' edge is
    `lead_bp` bp short of terC before this tick's advance, and this tick's
    own `advance` is `lead_bp + 1` bp -- just enough to cross)."""
    hel_ftpt5 = process.helicase_footprint_5prime_bp
    terc = process.terc_position_bp
    advance = lead_bp + 1
    if column == 0:
        # col0_before: helicase_pos + hel_ftpt5 >= terc + 1
        # col0_this_tick: (helicase_pos + hel_ftpt5 - advance) < terc + 1
        helicase_pos = terc + 1 + lead_bp - hel_ftpt5
        return helicase_pos, advance
    # col1_before: helicase_pos + hel_ftpt5 - 1 <= terc
    # col1_this_tick: (helicase_pos + hel_ftpt5 - 1 + advance) > terc
    helicase_pos = terc - lead_bp + 1 - hel_ftpt5
    return helicase_pos, advance


def _far_from_terc_helicase(process: KarrReplicationProcess, *, column: int) -> int:
    """A helicase position guaranteed to leave `column` NOT crossing terC
    this tick regardless of `leading_advance`, used to hold the other
    column inert while isolating a single-column-crossing branch."""
    terc = process.terc_position_bp
    if column == 0:
        # col0_before requires helicase_pos + hel_ftpt5 >= terc + 1; make
        # this false unconditionally by placing the helicase far below terC.
        return 0
    # col1_before requires helicase_pos + hel_ftpt5 - 1 <= terc; make this
    # false unconditionally by placing the helicase far past terC.
    return terc + process.sequence_len_bp // 4


def test_terc_linking_stall_passthrough_when_neither_column_crossing(
    process: KarrReplicationProcess,
) -> None:
    store = ChromosomeStore(shape=process.chromosome_shape)
    helicase_pos = (
        _far_from_terc_helicase(process, column=0),
        _far_from_terc_helicase(process, column=1),
    )
    advance0, advance1 = process._terc_linking_stall(
        store, helicase_pos=helicase_pos, leading_advance=(50, 60)
    )
    assert (advance0, advance1) == (50, 60)


def test_terc_linking_stall_passthrough_when_crossing_but_linking_all_zero(
    process: KarrReplicationProcess,
) -> None:
    store = ChromosomeStore(shape=process.chromosome_shape)
    helicase_pos0, advance0_in = _crossing_helicase_and_advance(process, column=0, lead_bp=5)
    helicase_pos = (helicase_pos0, _far_from_terc_helicase(process, column=1))
    advance0, advance1 = process._terc_linking_stall(
        store, helicase_pos=helicase_pos, leading_advance=(advance0_in, 60)
    )
    assert (advance0, advance1) == (advance0_in, 60)


def test_terc_linking_stall_branch2_zeros_column0_when_daughter_strand_not_polymerized(
    process: KarrReplicationProcess,
) -> None:
    """Branch 2 (Replication.m:827-833): column 0 alone crosses terC this
    tick, a nonzero linking number is recorded at the check position, and
    the daughter strand at `[terC, laggingStrandIndexs(2)]` is NOT already
    polymerized -> zero column 0's advance."""
    store = ChromosomeStore(shape=process.chromosome_shape)
    helicase_pos0, advance0_in = _crossing_helicase_and_advance(process, column=0, lead_bp=5)
    helicase_pos1 = _far_from_terc_helicase(process, column=1)
    check_pos_0based = min(process.terc_position_bp + 1, helicase_pos1 + process.helicase_footprint_5prime_bp - 1) - 1
    store.set_field(
        "linkingNumbers",
        SparseTriplet.from_regions(
            [(check_pos_0based, process.leading_strand_indexs[0], 5)],
            shape=process.chromosome_shape,
        ),
    )
    advance0, advance1 = process._terc_linking_stall(
        store, helicase_pos=(helicase_pos0, helicase_pos1), leading_advance=(advance0_in, 60)
    )
    assert (advance0, advance1) == (0, 60)


def test_terc_linking_stall_branch2_noop_when_daughter_strand_already_polymerized(
    process: KarrReplicationProcess,
) -> None:
    """Same setup as above, but the daughter strand IS already
    polymerized at the check position -- branch 2's veto must NOT fire."""
    store = ChromosomeStore(shape=process.chromosome_shape)
    helicase_pos0, advance0_in = _crossing_helicase_and_advance(process, column=0, lead_bp=5)
    helicase_pos1 = _far_from_terc_helicase(process, column=1)
    check_pos_0based = min(process.terc_position_bp + 1, helicase_pos1 + process.helicase_footprint_5prime_bp - 1) - 1
    store.set_field(
        "linkingNumbers",
        SparseTriplet.from_regions(
            [(check_pos_0based, process.leading_strand_indexs[0], 5)],
            shape=process.chromosome_shape,
        ),
    )
    store.set_field(
        "polymerizedRegions",
        SparseTriplet.from_regions(
            [(process.terc_position_0based, process.lagging_strand_indexs[1], 1)],
            shape=process.chromosome_shape,
        ),
    )
    advance0, advance1 = process._terc_linking_stall(
        store, helicase_pos=(helicase_pos0, helicase_pos1), leading_advance=(advance0_in, 60)
    )
    assert (advance0, advance1) == (advance0_in, 60)


def test_terc_linking_stall_branch3_zeros_column1_when_daughter_strand_not_polymerized(
    process: KarrReplicationProcess,
) -> None:
    """Branch 3 (Replication.m:834-840): the column-1-alone-crossing
    mirror of branch 2 above."""
    store = ChromosomeStore(shape=process.chromosome_shape)
    helicase_pos1, advance1_in = _crossing_helicase_and_advance(process, column=1, lead_bp=5)
    helicase_pos0 = _far_from_terc_helicase(process, column=0)
    check_pos_0based = min(process.terc_position_bp + 1, helicase_pos1 + process.helicase_footprint_5prime_bp - 1) - 1
    store.set_field(
        "linkingNumbers",
        SparseTriplet.from_regions(
            [(check_pos_0based, process.leading_strand_indexs[0], 5)],
            shape=process.chromosome_shape,
        ),
    )
    advance0, advance1 = process._terc_linking_stall(
        store, helicase_pos=(helicase_pos0, helicase_pos1), leading_advance=(70, advance1_in)
    )
    assert (advance0, advance1) == (70, 0)


def test_terc_linking_stall_branch3_noop_when_daughter_strand_already_polymerized(
    process: KarrReplicationProcess,
) -> None:
    store = ChromosomeStore(shape=process.chromosome_shape)
    helicase_pos1, advance1_in = _crossing_helicase_and_advance(process, column=1, lead_bp=5)
    helicase_pos0 = _far_from_terc_helicase(process, column=0)
    check_pos_0based = min(process.terc_position_bp + 1, helicase_pos1 + process.helicase_footprint_5prime_bp - 1) - 1
    store.set_field(
        "linkingNumbers",
        SparseTriplet.from_regions(
            [(check_pos_0based, process.leading_strand_indexs[0], 5)],
            shape=process.chromosome_shape,
        ),
    )
    store.set_field(
        "polymerizedRegions",
        SparseTriplet.from_regions(
            [(process.terc_position_bp, process.lagging_strand_indexs[1], 1)],
            shape=process.chromosome_shape,
        ),
    )
    advance0, advance1 = process._terc_linking_stall(
        store, helicase_pos=(helicase_pos0, helicase_pos1), leading_advance=(70, advance1_in)
    )
    assert (advance0, advance1) == (70, advance1_in)


def test_terc_linking_stall_branch1_coin_zeros_column0_on_high_draw(
    process: KarrReplicationProcess,
) -> None:
    """Branch 1 (Replication.m:820-826): BOTH columns cross terC
    simultaneously this tick with a nonzero linking number recorded -- a
    fair coin (drawn from this process's own seeded `self._rng`, never
    global state) zeros exactly one column. `self._rng.random() >= 0.5`
    zeros column 0 per `_terc_linking_stall`'s own literal mapping."""
    store = ChromosomeStore(shape=process.chromosome_shape)
    helicase_pos0, advance0_in = _crossing_helicase_and_advance(process, column=0, lead_bp=5)
    helicase_pos1, advance1_in = _crossing_helicase_and_advance(process, column=1, lead_bp=5)
    check_pos_0based = min(process.terc_position_bp + 1, helicase_pos1 + process.helicase_footprint_5prime_bp - 1) - 1
    store.set_field(
        "linkingNumbers",
        SparseTriplet.from_regions(
            [(check_pos_0based, process.leading_strand_indexs[0], 5)],
            shape=process.chromosome_shape,
        ),
    )
    process._rng = _StubCoinRNG(coin_value=0.9)
    advance0, advance1 = process._terc_linking_stall(
        store, helicase_pos=(helicase_pos0, helicase_pos1), leading_advance=(advance0_in, advance1_in)
    )
    assert (advance0, advance1) == (0, advance1_in)


def test_terc_linking_stall_branch1_coin_zeros_column1_on_low_draw(
    process: KarrReplicationProcess,
) -> None:
    store = ChromosomeStore(shape=process.chromosome_shape)
    helicase_pos0, advance0_in = _crossing_helicase_and_advance(process, column=0, lead_bp=5)
    helicase_pos1, advance1_in = _crossing_helicase_and_advance(process, column=1, lead_bp=5)
    check_pos_0based = min(process.terc_position_bp + 1, helicase_pos1 + process.helicase_footprint_5prime_bp - 1) - 1
    store.set_field(
        "linkingNumbers",
        SparseTriplet.from_regions(
            [(check_pos_0based, process.leading_strand_indexs[0], 5)],
            shape=process.chromosome_shape,
        ),
    )
    process._rng = _StubCoinRNG(coin_value=0.1)
    advance0, advance1 = process._terc_linking_stall(
        store, helicase_pos=(helicase_pos0, helicase_pos1), leading_advance=(advance0_in, advance1_in)
    )
    assert (advance0, advance1) == (advance0_in, 0)
