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
    karr = [_timeline("P", s, [2, 5, 9]) for s in range(20)]
    oc = [_timeline("P", s, [2, 5, 9]) for s in range(20)]
    result = metrics.count_gate(karr, oc, rng=_rng())
    assert result.verdict in ("PASS", "SEED_NOISE")


def test_count_gate_fails_when_oc_count_wildly_diverges_from_karr():
    """Every Karr seed fires once; every OC seed fires 10x more -- well
    outside D3's [floor(0.5*T), ceil(2*T)] support guard."""
    karr = [_timeline("P", s, [2]) for s in range(20)]
    oc = [_timeline("P", s, list(range(10))) for s in range(20)]
    result = metrics.count_gate(karr, oc, rng=_rng())
    assert result.verdict == "FAIL"
    assert result.extra["t_oc"] > result.extra["guard_ceiling"]


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
    """Single-fire case: both sides fire exactly once, at the same tick,
    across every seed."""
    karr = [_timeline("P", s, [7]) for s in range(20)]
    oc = [_timeline("P", s, [7]) for s in range(20)]
    result = metrics.timing_gate_repeated_firing(karr, oc, rng=_rng())
    assert result.verdict in ("PASS", "SEED_NOISE")


def test_timing_gate_repeated_firing_detects_timing_shift_fail():
    """Karr fires early every seed, OC fires late every seed, by a shift
    much larger than intrinsic seed noise -- must FAIL, not PASS."""
    karr = [_timeline("P", s, [1, 2], n_ticks=20) for s in range(20)]
    oc = [_timeline("P", s, [17, 18], n_ticks=20) for s in range(20)]
    result = metrics.timing_gate_repeated_firing(karr, oc, rng=_rng())
    assert result.verdict == "FAIL"


def test_timing_gate_repeated_firing_between_event_oc_extra_fires_visible_in_bag():
    """OC firing on additional ticks between Karr's real firing ticks must
    show up in the pooled fire-tick bag (this is what a firing-tick-only
    design misses per C6) -- proven here via a bag-length delta, with the
    dedicated oc_only_fire_ticks() check covering the C6 detector itself."""
    karr = [_timeline("P", s, [5], n_ticks=20) for s in range(20)]
    oc = [_timeline("P", s, [5, 6, 7, 8], n_ticks=20) for s in range(20)]
    result = metrics.timing_gate_repeated_firing(karr, oc, rng=_rng())
    assert result.extra["n_oc_fire_ticks"] > result.extra["n_karr_fire_ticks"]


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
    karr_offsets = np.array([10.0] * 30)
    oc_offsets = np.array([80.0] * 30)
    result = metrics.timing_gate_single_firing(karr_offsets, oc_offsets, rng=_rng())
    assert result.verdict == "FAIL"


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
    karr_payloads = [{"a": 5.0, "b": 2.0} for _ in range(20)]
    oc_payloads = [{"a": 5.0, "b": 2.0} for _ in range(20)]
    result = metrics.payload_gate(karr_payloads, oc_payloads, rng=_rng())
    assert result.verdict in ("PASS", "SEED_NOISE")


def test_payload_gate_fails_for_diverging_component():
    karr_payloads = [{"a": 5.0} for _ in range(20)]
    oc_payloads = [{"a": 500.0} for _ in range(20)]
    result = metrics.payload_gate(karr_payloads, oc_payloads, rng=_rng())
    assert result.verdict == "FAIL"


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
