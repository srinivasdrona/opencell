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
    """Opus5 review round 3, item #2: Karr and OC payload component key
    spaces completely disjoint (e.g. positional `complex_0`/`complex_1`
    never mapped onto OC's real wid-keyed names) is an adapter
    payload-mapping bug, not a numeric divergence -- must FAIL-class,
    never silently zero-fill the missing side into a spuriously small W1.
    Fully disjoint keyspaces produce ONE NO_OC_COMPONENT result (for
    Karr's 'complex_0', which OC never produced) and ONE
    SPURIOUS_OC_COMPONENT result (for OC's 'RIBOSOME_30S', which Karr
    never produced); NO_OC_COMPONENT sorts worse in the aggregation
    priority, so it wins deterministically as the channel verdict."""
    karr_payloads = [{"complex_0": 5.0 + (i % 3)} for i in range(20)]
    oc_payloads = [{"RIBOSOME_30S": 5.0 + (i % 3)} for i in range(20)]
    result = metrics.payload_gate(karr_payloads, oc_payloads, rng=_rng())
    assert result.verdict == "NO_OC_COMPONENT"
    assert result.extra["karr_components"] == ["complex_0"]
    assert result.extra["oc_components"] == ["RIBOSOME_30S"]
    per_component_verdicts = {c.component: c.verdict for c in result.per_component}
    assert per_component_verdicts == {
        "complex_0": "NO_OC_COMPONENT",
        "RIBOSOME_30S": "SPURIOUS_OC_COMPONENT",
    }


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


# ---------------------------------------------------------------------------
# Opus5 review round 3: per-component payload verdict aggregation (item #1)
# ---------------------------------------------------------------------------


def test_payload_gate_big_small_masking_worst_component_verdict_wins():
    """Opus5 review round 3, item #1: reproduce the exact false-green
    scenario -- a component ('BIG') with a large raw W1 that is actually
    WITHIN its own (large) seed-cluster null (so its own verdict is only
    SEED_NOISE), alongside a second component ('SMALL') whose raw W1 is
    tiny in absolute terms but ~750x its own (near-zero) null (a real
    FAIL). The pre-round-3 bug picked whichever component had the larger
    RAW w1 (BIG, 40.0 > SMALL's 3.0) and reported the WHOLE channel using
    BIG's own null -- silently masking SMALL's genuine divergence as
    SEED_NOISE. The channel verdict must be the WORST per-component
    verdict (FAIL), not derived from the raw-largest statistic."""
    karr_big = [100.0 + (i % 5) * 100.0 for i in range(30)]
    oc_big = [v + (i % 5) * 20.0 for i, v in enumerate(karr_big)]
    karr_small = [5.0 + (i % 3) * 0.01 for i in range(30)]
    oc_small = [v + 3.0 for v in karr_small]
    karr_payloads = [{"BIG": b, "SMALL": s} for b, s in zip(karr_big, karr_small)]
    oc_payloads = [{"BIG": b, "SMALL": s} for b, s in zip(oc_big, oc_small)]

    result = metrics.payload_gate(karr_payloads, oc_payloads, rng=_rng())

    per_component = {c.component: c for c in result.per_component}
    assert per_component["BIG"].verdict == "SEED_NOISE"
    assert per_component["BIG"].statistic_value == pytest.approx(40.0)
    assert per_component["SMALL"].verdict == "FAIL"
    assert per_component["SMALL"].standardized_ratio > 100.0  # ~750x its own null
    # The channel verdict must be the WORST across components, not derived
    # from whichever component has the largest raw statistic (BIG=40.0 >
    # SMALL=3.0, yet BIG alone would falsely green the whole channel).
    assert result.verdict == "FAIL"


def test_payload_gate_missing_oc_component_is_no_oc_component_not_silent_zero_fill():
    """Opus5 review round 3, item #2: a component Karr reports on every
    firing but OC NEVER reports at all (dropped from OC's payload
    entirely, not merely zero-valued) must be its own distinct
    NO_OC_COMPONENT verdict -- never zero-filled into a numeric W1
    comparison alongside a shared component that otherwise matches
    cleanly."""
    karr_payloads = [{"shared": 5.0 + (i % 3), "dropped_by_oc": 9.0} for i in range(20)]
    oc_payloads = [{"shared": 5.0 + (i % 3)} for i in range(20)]
    result = metrics.payload_gate(karr_payloads, oc_payloads, rng=_rng())
    assert result.verdict == "NO_OC_COMPONENT"
    per_component = {c.component: c.verdict for c in result.per_component}
    assert per_component["dropped_by_oc"] == "NO_OC_COMPONENT"
    assert per_component["shared"] in ("PASS", "SEED_NOISE")


def test_payload_gate_spurious_oc_only_component_detected():
    """Opus5 review round 3, item #2: the mirror image -- OC invents a
    payload component Karr never produced at all -- must be its own
    distinct SPURIOUS_OC_COMPONENT verdict."""
    karr_payloads = [{"shared": 5.0 + (i % 3)} for i in range(20)]
    oc_payloads = [{"shared": 5.0 + (i % 3), "oc_only": 9.0} for i in range(20)]
    result = metrics.payload_gate(karr_payloads, oc_payloads, rng=_rng())
    assert result.verdict == "SPURIOUS_OC_COMPONENT"
    per_component = {c.component: c.verdict for c in result.per_component}
    assert per_component["oc_only"] == "SPURIOUS_OC_COMPONENT"
    assert per_component["shared"] in ("PASS", "SEED_NOISE")


def test_payload_gate_per_component_null_is_not_pooled_across_components():
    """Metric correctness: each component's null must be bootstrapped from
    THAT component's own Karr values, not pooled with a heterogeneous
    component's values -- a low-variance component and a high-variance
    component in the SAME cohort must produce DIFFERENT q95_null values."""
    low_variance = [5.0, 5.0, 5.0, 5.0, 6.0, 4.0] * 5
    high_variance = [0.0, 10.0, 0.0, 10.0, 20.0, -10.0] * 5
    karr_payloads = [{"lo": lo, "hi": hi} for lo, hi in zip(low_variance, high_variance)]
    oc_payloads = [dict(p) for p in karr_payloads]
    result = metrics.payload_gate(karr_payloads, oc_payloads, rng=_rng(1))
    per_component = {c.component: c for c in result.per_component}
    assert per_component["lo"].q95_null != per_component["hi"].q95_null
    assert per_component["hi"].q95_null > per_component["lo"].q95_null


def test_payload_gate_required_components_enforced_before_metric():
    """Opus5 review round 3, item #2/#3: an adapter-declared exact
    required payload keyspace (e.g. RA's 2 real WIDs) is checked BEFORE
    any per-component metric is computed -- a partial/wrong keyspace must
    hard-refuse even though every observed component's own numeric
    comparison would otherwise pass cleanly."""
    karr_payloads = [{"RIBOSOME_30S": 5.0 + (i % 3)} for i in range(20)]
    oc_payloads = [{"RIBOSOME_30S": 5.0 + (i % 3)} for i in range(20)]
    result = metrics.payload_gate(
        karr_payloads,
        oc_payloads,
        rng=_rng(),
        required_components=frozenset({"RIBOSOME_30S", "RIBOSOME_50S"}),
    )
    assert result.verdict == "FAIL"
    assert "RIBOSOME_50S" in result.extra["required_components"]

    # The exact matching keyspace must NOT be refused.
    result_ok = metrics.payload_gate(
        karr_payloads,
        oc_payloads,
        rng=_rng(),
        required_components=frozenset({"RIBOSOME_30S"}),
    )
    assert result_ok.verdict != "FAIL"


def test_ribosome_assembly_smoke_adapter_required_payload_components_two_wids():
    """Opus5 review round 3, item #2/#3: 'exact required keyspace for RA
    adapter (2 WIDs) enforced before metric'. The adapter itself must
    declare its 2-WID keyspace, and `payload_gate` must refuse a
    single-WID-only cohort against it -- exercised directly (RA stays out
    of gate-mode scope per this task) rather than through a full gate
    run."""
    from scripts.l2_event.adapters.ribosome_assembly_smoke import RibosomeAssemblySmokeAdapter

    adapter = RibosomeAssemblySmokeAdapter(complex_index_by_wid={0: "RIBOSOME_30S", 1: "RIBOSOME_50S"})
    assert adapter.required_payload_components == frozenset({"RIBOSOME_30S", "RIBOSOME_50S"})

    karr_payloads = [{"RIBOSOME_30S": 5.0 + (i % 3)} for i in range(20)]
    oc_payloads = [{"RIBOSOME_30S": 5.0 + (i % 3)} for i in range(20)]
    result = metrics.payload_gate(
        karr_payloads, oc_payloads, rng=_rng(), required_components=adapter.required_payload_components
    )
    assert result.verdict == "FAIL"


def test_ribosome_assembly_smoke_adapter_required_payload_components_none_without_mapping():
    """No mapping supplied at all (the placeholder-`complex_{i}`-key
    fallback path used by this adapter's own no-mapping unit tests) must
    return `None` (no keyspace constraint enforced) rather than an empty
    frozenset that would refuse every payload cohort."""
    from scripts.l2_event.adapters.ribosome_assembly_smoke import RibosomeAssemblySmokeAdapter

    adapter = RibosomeAssemblySmokeAdapter()
    assert adapter.required_payload_components is None


# ---------------------------------------------------------------------------
# Opus5 review round 3: adapter-specific support floors (item #3)
# ---------------------------------------------------------------------------


def test_count_support_floor_repeated_firing_is_bare_pooled_count():
    assert metrics.count_support_floor("repeated_firing", n_seeds_total=50) == 50
    assert metrics.count_support_floor("repeated_firing", n_seeds_total=1000000) == 50


def test_count_support_floor_single_firing_is_fraction_of_ensemble():
    assert metrics.count_support_floor("single_firing", n_seeds_total=50) == 45
    assert metrics.count_support_floor("single_firing", n_seeds_total=10) == 9


def test_count_support_floor_unknown_timing_model_raises():
    with pytest.raises(ValueError):
        metrics.count_support_floor("not_a_real_model", n_seeds_total=50)


def test_count_gate_repeated_firing_boundary_49_refuses_50_proceeds():
    """RA-style repeated_firing: >=50 pooled Karr fire ticks required.
    49 must REFUSE (INSUFFICIENT_KARR_SUPPORT); 50 must not."""
    floor = metrics.count_support_floor("repeated_firing", n_seeds_total=10)
    karr_49 = [_timeline("P", 0, list(range(49)), n_ticks=60)]
    oc_49 = [_timeline("P", 0, list(range(49)), n_ticks=60)]
    result_49 = metrics.count_gate(karr_49, oc_49, rng=_rng(), min_karr_support=floor)
    assert result_49.verdict == "INSUFFICIENT_KARR_SUPPORT"
    assert result_49.extra["t_karr"] == 49

    karr_50 = [_timeline("P", 0, list(range(50)), n_ticks=60)]
    oc_50 = [_timeline("P", 0, list(range(50)), n_ticks=60)]
    result_50 = metrics.count_gate(karr_50, oc_50, rng=_rng(), min_karr_support=floor)
    assert result_50.verdict != "INSUFFICIENT_KARR_SUPPORT"


def test_count_gate_single_firing_boundary_44_refuses_45_proceeds():
    """Cytokinesis-style single_firing: >=45/50 (0.9) fired-seed fraction
    required. 44/50 fired seeds must REFUSE (INSUFFICIENT_KARR_SUPPORT);
    45/50 must not -- this is a DIFFERENT floor than the bare pooled-50
    used for repeated_firing (the 'generic pooled50 conflict' this round
    fixes): 44 pooled fire ticks would already be < the repeated_firing
    floor of 50 too, so this test specifically uses `count_support_floor`
    to get the correct single_firing-shaped floor (45, not 50) and checks
    the boundary against THAT."""
    floor = metrics.count_support_floor("single_firing", n_seeds_total=50)
    assert floor == 45

    karr_44 = [_timeline("P", s, [2], n_ticks=10) for s in range(44)] + [
        _timeline("P", s, [], n_ticks=10) for s in range(44, 50)
    ]
    oc_44 = [_timeline("P", s, [2], n_ticks=10) for s in range(44)] + [
        _timeline("P", s, [], n_ticks=10) for s in range(44, 50)
    ]
    result_44 = metrics.count_gate(karr_44, oc_44, rng=_rng(), min_karr_support=floor)
    assert result_44.verdict == "INSUFFICIENT_KARR_SUPPORT"
    assert result_44.extra["t_karr"] == 44

    karr_45 = [_timeline("P", s, [2], n_ticks=10) for s in range(45)] + [
        _timeline("P", s, [], n_ticks=10) for s in range(45, 50)
    ]
    oc_45 = [_timeline("P", s, [2], n_ticks=10) for s in range(45)] + [
        _timeline("P", s, [], n_ticks=10) for s in range(45, 50)
    ]
    result_45 = metrics.count_gate(karr_45, oc_45, rng=_rng(), min_karr_support=floor)
    assert result_45.verdict != "INSUFFICIENT_KARR_SUPPORT"


# ---------------------------------------------------------------------------
# Opus5 review round 3: k_eng_provenance schema field (item #6)
# ---------------------------------------------------------------------------


def test_channel_result_carries_k_eng_provenance_schema_field():
    """Opus5 review round 3, item #6/#7: `k_eng_provenance` must be a real
    schema field on every `GateChannelResult` this module produces (it
    previously only ever lived inside `extra`, which STATUS.md falsely
    claimed was already a real field)."""
    karr = [_timeline("P", s, [2]) for s in range(5)]
    oc = [_timeline("P", s, [2]) for s in range(5)]
    result = metrics.count_gate(karr, oc, rng=_rng(), min_karr_support=1)
    assert result.k_eng_provenance == metrics.K_ENG_PROVENANCE
    assert "provisional" in result.k_eng_provenance.lower()
