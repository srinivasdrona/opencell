"""Unit tests for `scripts/l2_event/metrics.py` (D2/D3/D4/C6: count/timing/
payload gates, Karr-only clustered null bootstrap, spurious OC-only firing
detection). Requirement 6: synthetic single-fire and repeated-fire,
between-event OC extra fires, timing/count/payload fail, empty support,
seed cluster bootstrap.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import metrics
from scripts.l2_event.schema import EventObservation, EventTimeline


def _timeline(process: str, seed: int, fire_ticks: list[int], n_ticks: int = 20) -> EventTimeline:
    """Build a timeline that fires (fire_count=1) at exactly the given
    ticks and is otherwise quiescent."""
    fire_set = set(fire_ticks)
    obs = tuple(
        EventObservation(tick=t, fired=t in fire_set, fire_count=1 if t in fire_set else 0, timing_tick=t if t in fire_set else None)
        for t in range(n_ticks)
    )
    return EventTimeline(process=process, seed=seed, observations=obs)


def _rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


# ---------------------------------------------------------------------------
# count_gate
# ---------------------------------------------------------------------------


def test_count_gate_no_karr_support_when_both_zero():
    karr = [_timeline("P", s, []) for s in range(5)]
    oc = [_timeline("P", s, []) for s in range(5)]
    result = metrics.count_gate(karr, oc, rng=_rng())
    assert result.verdict == "NO_KARR_SUPPORT"
    assert result.statistic_value is None


def test_count_gate_hard_fail_when_karr_zero_and_oc_nonzero_no_zero_equals_zero_pass():
    """This is the exact 'no zero==zero PASS' case: Karr never fires but OC
    does -- must be a hard FAIL, never PASS."""
    karr = [_timeline("P", s, []) for s in range(5)]
    oc = [_timeline("P", s, [3]) for s in range(5)]
    result = metrics.count_gate(karr, oc, rng=_rng())
    assert result.verdict == "FAIL"


def test_count_gate_passes_for_identical_repeated_firing_cohorts():
    """Identical Karr/OC cohorts must not FAIL, but the per-seed counts
    must carry real inter-seed variance (not a constant pool) so the null
    bootstrap is not itself degenerate (M1: DEGENERATE_NULL can never be
    silently bypassed by using a variance-free fixture)."""
    counts_per_seed = ([2, 3, 4] * 7)[:20]
    karr = [_timeline("P", s, list(range(2, 2 + counts_per_seed[s])), n_ticks=20) for s in range(20)]
    oc = [_timeline("P", s, list(range(2, 2 + counts_per_seed[s])), n_ticks=20) for s in range(20)]
    result = metrics.count_gate(karr, oc, rng=_rng())
    assert result.verdict in ("PASS", "SEED_NOISE")


def test_count_gate_fails_when_oc_count_wildly_diverges_from_karr():
    """Every Karr seed fires once; every OC seed fires 10x more -- well
    outside D3's [floor(0.5*T), ceil(2*T)] support guard. Uses an explicit
    low `min_karr_support` override since this test isolates the D3 guard
    check from the M1 support-floor check (a dedicated test covers the
    floor itself)."""
    karr = [_timeline("P", s, [2]) for s in range(20)]
    oc = [_timeline("P", s, list(range(10))) for s in range(20)]
    result = metrics.count_gate(karr, oc, rng=_rng(), min_karr_support=1)
    assert result.verdict == "FAIL"
    assert result.extra["t_oc"] > result.extra["guard_ceiling"]


def test_count_gate_insufficient_karr_support_below_floor():
    """M1: a nonzero-but-under-powered Karr baseline (3 pooled fire ticks,
    well below the default floor of 50) must REFUSE
    (INSUFFICIENT_KARR_SUPPORT), never silently proceed to a bootstrap/
    PASS -- this reproduces the Opus5-reported false-green scenario."""
    karr = [_timeline("P", s, [2] if s < 3 else []) for s in range(5)]
    oc = [_timeline("P", s, [2] if s < 3 else []) for s in range(5)]
    result = metrics.count_gate(karr, oc, rng=_rng())
    assert result.verdict == "INSUFFICIENT_KARR_SUPPORT"
    assert result.statistic_value is None
    assert result.extra["t_karr"] == 3


def test_count_gate_degenerate_null_cannot_produce_seed_noise_or_pass():
    """M1: a constant per-seed count pool (q95_null == 0) must REFUSE
    (DEGENERATE_NULL), never report SEED_NOISE/PASS -- reproduces the
    Opus5-reported 'q95=0 falsely greens' scenario, using a guard-
    compliant T_oc so the D3 guard check does not mask this path."""
    karr = [_timeline("P", s, [2, 5, 9]) for s in range(20)]  # constant count=3/seed, t_karr=60
    oc = [_timeline("P", s, [2, 5, 9]) for s in range(20)]  # matches T_karr exactly (guard.ok)
    result = metrics.count_gate(karr, oc, rng=_rng())
    assert result.verdict == "DEGENERATE_NULL"
    assert result.q95_null == 0.0


def test_count_support_guard_bounds():
    guard = metrics.count_support_guard(t_karr=10, t_oc=5)
    assert guard.floor == 5
    assert guard.ceiling == 20
    assert guard.ok is True
    guard_bad = metrics.count_support_guard(t_karr=10, t_oc=21)
    assert guard_bad.ok is False
    # Small T_karr: floor is clamped to >= 1, never 0.
    guard_small = metrics.count_support_guard(t_karr=1, t_oc=1)
    assert guard_small.floor == 1


# ---------------------------------------------------------------------------
# timing_gate_repeated_firing (RibosomeAssembly-style)
# ---------------------------------------------------------------------------


def test_timing_gate_repeated_firing_no_karr_support():
    karr = [_timeline("P", s, []) for s in range(5)]
    oc = [_timeline("P", s, []) for s in range(5)]
    result = metrics.timing_gate_repeated_firing(karr, oc, rng=_rng())
    assert result.verdict == "NO_KARR_SUPPORT"


def test_timing_gate_repeated_firing_hard_fail_zero_karr_nonzero_oc():
    karr = [_timeline("P", s, []) for s in range(5)]
    oc = [_timeline("P", s, [4]) for s in range(5)]
    result = metrics.timing_gate_repeated_firing(karr, oc, rng=_rng())
    assert result.verdict == "FAIL"


def test_timing_gate_repeated_firing_single_fire_matches_pass():
    """Single-fire case: both sides fire exactly once per seed, at ticks
    that vary across seeds (so the null bootstrap is not itself
    degenerate) but match exactly between Karr and OC. Uses an explicit
    low `min_karr_support` override -- this test isolates the PASS/
    SEED_NOISE statistic logic from the M1 support-floor check (covered by
    its own dedicated test)."""
    karr = [_timeline("P", s, [5 + (s % 7)], n_ticks=20) for s in range(20)]
    oc = [_timeline("P", s, [5 + (s % 7)], n_ticks=20) for s in range(20)]
    result = metrics.timing_gate_repeated_firing(karr, oc, rng=_rng(), min_karr_support=1)
    assert result.verdict in ("PASS", "SEED_NOISE")


def test_timing_gate_repeated_firing_detects_timing_shift_fail():
    """Karr fires early every seed (varying slightly across seeds so the
    null is not degenerate), OC fires late every seed by a shift much
    larger than intrinsic seed noise -- must FAIL, not PASS."""
    karr = [_timeline("P", s, [1 + (s % 4), 2 + (s % 4)], n_ticks=30) for s in range(20)]
    oc = [_timeline("P", s, [17 + (s % 4), 18 + (s % 4)], n_ticks=30) for s in range(20)]
    result = metrics.timing_gate_repeated_firing(karr, oc, rng=_rng(), min_karr_support=1)
    assert result.verdict == "FAIL"


def test_timing_gate_repeated_firing_between_event_oc_extra_fires_visible_in_bag():
    """OC firing on additional ticks between Karr's real firing ticks must
    show up in the pooled fire-tick bag (this is what a firing-tick-only
    design misses per C6) -- proven here via a bag-length delta, with the
    dedicated oc_only_fire_ticks() check covering the C6 detector itself."""
    karr = [_timeline("P", s, [5], n_ticks=20) for s in range(20)]
    oc = [_timeline("P", s, [5, 6, 7, 8], n_ticks=20) for s in range(20)]
    result = metrics.timing_gate_repeated_firing(karr, oc, rng=_rng(), min_karr_support=1)
    assert result.extra["n_oc_fire_ticks"] > result.extra["n_karr_fire_ticks"]


def test_timing_gate_repeated_firing_insufficient_karr_support_below_floor():
    """M1: reproduces the Opus5-reported false-green scenario -- only 3
    pooled Karr fire ticks (well below the default floor of 50) must
    REFUSE, never silently proceed to a bootstrap/PASS."""
    karr = [_timeline("P", 0, [2, 5, 9], n_ticks=20)]
    oc = [_timeline("P", 0, [2, 5, 9], n_ticks=20)]
    result = metrics.timing_gate_repeated_firing(karr, oc, rng=_rng())
    assert result.verdict == "INSUFFICIENT_KARR_SUPPORT"


def test_timing_gate_repeated_firing_degenerate_null_cannot_produce_seed_noise_or_pass():
    """M1: a constant per-seed fire-tick bag (q95_null == 0) must REFUSE
    (DEGENERATE_NULL), never report SEED_NOISE/PASS."""
    karr = [_timeline("P", s, [7], n_ticks=20) for s in range(60)]
    oc = [_timeline("P", s, [7], n_ticks=20) for s in range(60)]
    result = metrics.timing_gate_repeated_firing(karr, oc, rng=_rng())
    assert result.verdict == "DEGENERATE_NULL"
    assert result.q95_null == 0.0


# ---------------------------------------------------------------------------
# timing_gate_single_firing (Cytokinesis-style)
# ---------------------------------------------------------------------------


def test_timing_gate_single_firing_no_karr_support():
    result = metrics.timing_gate_single_firing(np.array([]), np.array([]), rng=_rng())
    assert result.verdict == "NO_KARR_SUPPORT"


def test_timing_gate_single_firing_hard_fail_zero_karr_nonzero_oc():
    result = metrics.timing_gate_single_firing(np.array([]), np.array([3.0, 4.0]), rng=_rng())
    assert result.verdict == "FAIL"


def test_timing_gate_single_firing_passes_for_matching_offsets():
    karr_offsets = np.array([10.0 + i * 0.1 for i in range(30)])
    oc_offsets = np.array([10.0 + i * 0.1 for i in range(30)])
    result = metrics.timing_gate_single_firing(karr_offsets, oc_offsets, rng=_rng())
    assert result.verdict in ("PASS", "SEED_NOISE")


def test_timing_gate_single_firing_fails_for_large_offset_divergence():
    """Offsets vary slightly across seeds (so the null bootstrap is not
    itself degenerate) but the two cohorts are shifted by far more than
    that intrinsic seed noise -- must FAIL."""
    karr_offsets = np.array([10.0 + (i % 5) for i in range(30)])
    oc_offsets = np.array([80.0 + (i % 5) for i in range(30)])
    result = metrics.timing_gate_single_firing(karr_offsets, oc_offsets, rng=_rng())
    assert result.verdict == "FAIL"


def test_timing_gate_single_firing_insufficient_karr_fired_seed_fraction():
    """M1 (spec C2): Cytokinesis-style single_firing requires >=45/50
    (0.9) of the WHOLE ensemble to have Karr-fired. Only 40/50 fired here
    (fraction 0.8) -- must REFUSE (INSUFFICIENT_KARR_SUPPORT), never
    silently gate on the fired subset alone."""
    karr_offsets = np.array([10.0 + (i % 5) for i in range(40)])
    oc_offsets = np.array([10.0 + (i % 5) for i in range(40)])
    result = metrics.timing_gate_single_firing(karr_offsets, oc_offsets, rng=_rng(), n_seeds_total=50)
    assert result.verdict == "INSUFFICIENT_KARR_SUPPORT"
    assert result.extra["n_seeds_total"] == 50
    assert result.extra["n_karr_fired_seeds"] == 40


def test_timing_gate_single_firing_sufficient_karr_fired_seed_fraction_proceeds():
    """The mirror case: 45/50 (exactly the 0.9 floor) must NOT refuse on
    support grounds -- it proceeds to the normal statistic path."""
    karr_offsets = np.array([10.0 + (i % 5) for i in range(45)])
    oc_offsets = np.array([10.0 + (i % 5) for i in range(45)])
    result = metrics.timing_gate_single_firing(karr_offsets, oc_offsets, rng=_rng(), n_seeds_total=50)
    assert result.verdict != "INSUFFICIENT_KARR_SUPPORT"


def test_timing_gate_single_firing_degenerate_null_cannot_produce_seed_noise_or_pass():
    """M1: constant offsets (q95_null == 0) must REFUSE (DEGENERATE_NULL),
    never report SEED_NOISE/PASS -- reproduces the Opus5-reported
    'q95=0 falsely greens' scenario for the single_firing timing gate."""
    karr_offsets = np.array([10.0] * 30)
    oc_offsets = np.array([10.0] * 30)
    result = metrics.timing_gate_single_firing(karr_offsets, oc_offsets, rng=_rng())
    assert result.verdict == "DEGENERATE_NULL"
    assert result.q95_null == 0.0


# ---------------------------------------------------------------------------
# payload_gate
# ---------------------------------------------------------------------------


def test_payload_gate_no_karr_support():
    result = metrics.payload_gate([], [], rng=_rng())
    assert result.verdict == "NO_KARR_SUPPORT"


def test_payload_gate_hard_fail_zero_karr_nonzero_oc():
    result = metrics.payload_gate([], [{"a": 1.0}], rng=_rng())
    assert result.verdict == "FAIL"


def test_payload_gate_passes_for_matching_payloads():
    """Payload values vary across seeds (so the per-component null is not
    degenerate) but match exactly between Karr and OC."""
    karr_payloads = [{"a": 5.0 + (i % 3) * 0.5, "b": 2.0 + (i % 4) * 0.25} for i in range(20)]
    oc_payloads = [dict(p) for p in karr_payloads]
    result = metrics.payload_gate(karr_payloads, oc_payloads, rng=_rng())
    assert result.verdict in ("PASS", "SEED_NOISE")


def test_payload_gate_fails_for_diverging_component():
    """Component 'a' varies across seeds (non-degenerate null) but Karr
    and OC are shifted by two orders of magnitude -- must FAIL."""
    karr_payloads = [{"a": 5.0 + (i % 5) * 0.5} for i in range(20)]
    oc_payloads = [{"a": 500.0 + (i % 5) * 0.5} for i in range(20)]
    result = metrics.payload_gate(karr_payloads, oc_payloads, rng=_rng())
    assert result.verdict == "FAIL"


def test_payload_gate_no_oc_support_when_karr_has_payload_but_oc_is_empty():
    """M-metric-correctness: Karr has payload but OC produced none at all
    -- must never silently zero-fill into a numeric 'close enough' PASS."""
    karr_payloads = [{"a": 5.0} for _ in range(20)]
    oc_payloads = [{} for _ in range(20)]
    result = metrics.payload_gate(karr_payloads, oc_payloads, rng=_rng())
    assert result.verdict == "NO_OC_SUPPORT"


def test_payload_gate_disjoint_component_key_spaces_fails_hard():
    """M3 (Opus5 review): Karr and OC payload component key spaces
    completely disjoint (e.g. positional `complex_0`/`complex_1` never
    mapped onto OC's real wid-keyed names) is an adapter payload-mapping
    bug, not a numeric divergence -- must FAIL, never silently zero-fill
    the missing side into a spuriously small W1."""
    karr_payloads = [{"complex_0": 5.0 + (i % 3)} for i in range(20)]
    oc_payloads = [{"RIBOSOME_30S": 5.0 + (i % 3)} for i in range(20)]
    result = metrics.payload_gate(karr_payloads, oc_payloads, rng=_rng())
    assert result.verdict == "FAIL"
    assert result.extra["karr_components"] == ["complex_0"]
    assert result.extra["oc_components"] == ["RIBOSOME_30S"]


def test_payload_gate_degenerate_null_cannot_produce_seed_noise_or_pass():
    """M1: constant payload values (q95_null == 0 for every component)
    must REFUSE (DEGENERATE_NULL), never report SEED_NOISE/PASS."""
    karr_payloads = [{"a": 5.0, "b": 2.0} for _ in range(20)]
    oc_payloads = [{"a": 5.0, "b": 2.0} for _ in range(20)]
    result = metrics.payload_gate(karr_payloads, oc_payloads, rng=_rng())
    assert result.verdict == "DEGENERATE_NULL"
    assert result.q95_null == 0.0


# ---------------------------------------------------------------------------
# oc_only_fire_ticks (C6)
# ---------------------------------------------------------------------------


def test_oc_only_fire_ticks_empty_when_oc_subset_of_karr():
    karr = _timeline("P", 0, [3, 8])
    oc = _timeline("P", 0, [3])
    assert metrics.oc_only_fire_ticks(karr, oc) == []


def test_oc_only_fire_ticks_detects_between_event_spurious_firings():
    karr = _timeline("P", 0, [3, 8], n_ticks=20)
    oc = _timeline("P", 0, [3, 5, 6, 8], n_ticks=20)
    assert metrics.oc_only_fire_ticks(karr, oc) == [5, 6]


def test_oc_only_fire_ticks_all_oc_ticks_when_karr_never_fires():
    karr = _timeline("P", 0, [], n_ticks=10)
    oc = _timeline("P", 0, [1, 2], n_ticks=10)
    assert metrics.oc_only_fire_ticks(karr, oc) == [1, 2]


# ---------------------------------------------------------------------------
# Clustered null bootstrap (D4) -- basic sanity, not full calibration
# ---------------------------------------------------------------------------


def test_clustered_bootstrap_scalar_is_nonnegative_and_zero_for_constant_pool():
    pool = np.array([5.0] * 20)
    q95 = metrics.clustered_bootstrap_scalar(pool, b=200, rng=_rng())
    assert q95 == 0.0


def test_clustered_bootstrap_scalar_grows_with_pool_variance():
    low_variance = np.array([5.0, 5.0, 5.0, 5.0, 6.0, 4.0] * 5)
    high_variance = np.array([0.0, 10.0, 0.0, 10.0, 20.0, -10.0] * 5)
    q95_low = metrics.clustered_bootstrap_scalar(low_variance, b=300, rng=_rng(1))
    q95_high = metrics.clustered_bootstrap_scalar(high_variance, b=300, rng=_rng(1))
    assert q95_high >= q95_low


def test_clustered_bootstrap_scalar_empty_pool_returns_zero():
    assert metrics.clustered_bootstrap_scalar(np.array([]), b=50, rng=_rng()) == 0.0


def test_clustered_bootstrap_bag_empty_seed_bags_returns_zero():
    assert metrics.clustered_bootstrap_bag([], max_support=10.0, b=50, rng=_rng()) == 0.0


def test_clustered_bootstrap_bag_is_nonnegative():
    seed_bags = [np.array([1.0, 2.0]), np.array([3.0]), np.array([])]
    q95 = metrics.clustered_bootstrap_bag(seed_bags, max_support=10.0, b=100, rng=_rng())
    assert q95 >= 0.0


# ---------------------------------------------------------------------------
# _safe_wasserstein edge cases
# ---------------------------------------------------------------------------


def test_safe_wasserstein_both_empty_is_zero():
    assert metrics._safe_wasserstein(np.array([]), np.array([]), max_support=5.0) == 0.0


def test_safe_wasserstein_one_empty_returns_max_support_sentinel():
    assert metrics._safe_wasserstein(np.array([1.0]), np.array([]), max_support=7.0) == 7.0
    assert metrics._safe_wasserstein(np.array([]), np.array([1.0]), max_support=7.0) == 7.0


def test_safe_wasserstein_matches_scipy_for_nonempty_inputs():
    from scipy.stats import wasserstein_distance

    a = np.array([1.0, 2.0, 3.0])
    b = np.array([2.0, 3.0, 4.0])
    assert metrics._safe_wasserstein(a, b, max_support=100.0) == pytest.approx(wasserstein_distance(a, b))
