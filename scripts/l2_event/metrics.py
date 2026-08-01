"""Count / timing / payload metrics, Karr-only clustered null bootstrap, and
spurious-firing detection for the L2.event gate (D2, D3, D4, C6).

Every statistic here is computed the same way regardless of which process
supplies the timelines -- process-specific behavior lives entirely in the
adapter layer (``scripts/l2_event/adapters``), not here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import wasserstein_distance

from scripts.l2_event.schema import EventTimeline, GateChannelResult, PayloadComponentResult

# Default Karr-only two-sample cluster-bootstrap replicate count (D4).
DEFAULT_B_RESAMPLES = 1000

# Default engineering multiplier on the null ceiling (spec's `k_eng`).
#
# Opus5 review: this constant is a **provisional engineering placeholder**,
# not a ratified statistical threshold -- it has never been calibrated
# against a real power/false-positive study. Every GateChannelResult that
# uses it carries `K_ENG_PROVENANCE` in its own `k_eng_provenance` schema
# field (Opus5 review round 3, item #6 -- promoted from an ad-hoc `extra`
# dict key to a real typed field) so no downstream consumer can mistake it
# for a derived/ratified value.
DEFAULT_K_ENG = 3.0

K_ENG_PROVENANCE = (
    "DEFAULT_K_ENG=3.0 is a provisional engineering placeholder pending "
    "statistical ratification (Opus5 review, M-metric-correctness item); it "
    "is not derived from any calibration/power study and must not be cited "
    "as a ratified statistical threshold."
)


def _channel_result(**kwargs) -> GateChannelResult:
    """Construct a :class:`GateChannelResult`, always attaching the
    current :data:`K_ENG_PROVENANCE` string to the schema's own
    ``k_eng_provenance`` field (Opus5 review round 3, item #6). Every
    metrics-produced channel result carries this consistently -- callers
    no longer need to remember to merge it into ``extra`` themselves, and
    it can no longer be silently omitted since it is a real dataclass
    field bound into ``result.json``'s own tracked sha256."""
    kwargs.setdefault("k_eng_provenance", K_ENG_PROVENANCE)
    return GateChannelResult(**kwargs)


# M1 (Opus5 review round 2) + M-support-floor-correctness (Opus5 review
# round 3, item #3): Karr support floors are ADAPTER/TIMING-MODEL
# SPECIFIC, not one shared generic constant. Before this round, both
# `count_gate` and `timing_gate_repeated_firing` defaulted to the exact
# same `DEFAULT_MIN_KARR_FIRE_TICKS = 50` constant -- which happened to be
# the right floor for repeated-firing processes (RA: pooled fire ticks
# naturally accumulate across many seeds), but silently reused as the
# SAME raw-pooled-count number for `count_gate` regardless of which
# process/timing-model called it. For a single-firing process
# (Cytokinesis), a seed contributes at most 1 to a pooled count, so a bare
# "pooled count >= 50" floor secretly demands "every one of the 50 seeds
# fired" -- a materially stricter (and different) requirement than spec
# C2's declared >=45/50 (fraction 0.9) floor used by
# `timing_gate_single_firing`. That silent semantic drift between two
# channels of the SAME process is exactly the "generic pooled50 conflict"
# Opus5 flagged. The two floors below are now named for the timing model
# they actually apply to, and `count_support_floor()` is the single place
# that converts a process's `event_timing_model` into the correct
# pooled-count floor for `count_gate` -- never a bare shared constant.
DEFAULT_MIN_KARR_POOLED_FIRE_COUNT_REPEATED_FIRING = 50
DEFAULT_MIN_KARR_FIRED_SEED_FRACTION_SINGLE_FIRING = 0.9


def count_support_floor(
    event_timing_model: str,
    n_seeds_total: int,
    *,
    min_karr_pooled_fire_count_repeated_firing: int = DEFAULT_MIN_KARR_POOLED_FIRE_COUNT_REPEATED_FIRING,
    min_karr_fired_seed_fraction_single_firing: float = DEFAULT_MIN_KARR_FIRED_SEED_FRACTION_SINGLE_FIRING,
) -> int:
    """The correct `count_gate` pooled-count support floor for a given
    process's `event_timing_model` (Opus5 review round 3, item #3).

    * ``repeated_firing`` (RA-style): the floor IS a bare pooled fire/count
      total (spec: >=50) -- a single seed can legitimately contribute many
      counts, so pooling across the whole cohort is the natural unit.
    * ``single_firing`` (Cytokinesis-style): the floor is expressed as a
      FRACTION of the whole ensemble (spec C2: >=45/50, i.e. 0.9), then
      converted here to the equivalent pooled-count number
      (``ceil(0.9 * n_seeds_total)``) so `count_gate` can still be called
      with one `min_karr_support` integer parameter -- but the number it
      receives now means the SAME thing `timing_gate_single_firing`'s own
      seed-fraction floor means, instead of colliding with the unrelated
      repeated-firing semantics.
    """
    if event_timing_model == "repeated_firing":
        return min_karr_pooled_fire_count_repeated_firing
    if event_timing_model == "single_firing":
        return math.ceil(min_karr_fired_seed_fraction_single_firing * n_seeds_total)
    raise ValueError(f"Unknown event_timing_model: {event_timing_model!r}")


def _extra(extra: dict | None = None) -> dict:
    """Return ``extra`` (or an empty dict) as a fresh copy. This used to
    also merge in the k_eng provenance note; that note is now attached via
    `_channel_result`'s own `k_eng_provenance` schema field instead (Opus5
    review round 3, item #6), so this helper is purely a defensive copy
    for call-site consistency -- it is not a mandatory step."""
    return dict(extra) if extra else {}


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------


def per_seed_total_counts(timelines: list[EventTimeline]) -> np.ndarray:
    return np.array([t.total_fire_count for t in timelines], dtype=float)


def pooled_fire_ticks(timelines: list[EventTimeline]) -> np.ndarray:
    """Bag of all fire-tick indices across every seed's timeline (D2
    addendum semantics: one entry per (seed, tick) firing, not
    deduplicated)."""
    out: list[int] = []
    for timeline in timelines:
        out.extend(timeline.fire_ticks)
    return np.array(out, dtype=float)


def _safe_wasserstein(a: np.ndarray, b: np.ndarray, *, max_support: float) -> float:
    """Wasserstein-1 distance that degrades gracefully on empty inputs
    instead of raising, so bootstrap resamples that happen to draw an
    all-zero-fire cohort don't crash the calibration loop.

    Both empty -> 0.0 (identical "no events" distributions). Exactly one
    empty -> ``max_support`` (maximal disagreement, bounded by the window
    length so it does not blow up the null ceiling to infinity).
    """
    if len(a) == 0 and len(b) == 0:
        return 0.0
    if len(a) == 0 or len(b) == 0:
        return float(max_support)
    return float(wasserstein_distance(a, b))


@dataclass(frozen=True)
class CountSupportGuard:
    """D3's explicit count-guard bounds: ``T_oc`` must land in
    ``[floor, ceiling]`` around ``T_karr`` for the count gate to even be
    eligible for a statistical PASS (independent of the W1 comparison)."""

    t_karr: int
    t_oc: int
    floor: int
    ceiling: int
    ok: bool


def count_support_guard(t_karr: int, t_oc: int) -> CountSupportGuard:
    floor = max(1, math.floor(0.5 * t_karr))
    ceiling = math.ceil(2.0 * t_karr)
    return CountSupportGuard(t_karr=t_karr, t_oc=t_oc, floor=floor, ceiling=ceiling, ok=floor <= t_oc <= ceiling)


# ---------------------------------------------------------------------------
# Karr-only clustered null bootstrap (D4)
# ---------------------------------------------------------------------------


def clustered_bootstrap_scalar(
    pool: np.ndarray,
    *,
    n: int | None = None,
    b: int = DEFAULT_B_RESAMPLES,
    rng: np.random.Generator,
) -> float:
    """Two-sample Karr-only cluster bootstrap for a per-seed scalar
    statistic (used by the count gate). Resamples two independent cohorts
    of size ``n`` (default: ``len(pool)``) from ``pool`` with the seed as
    the cluster unit, computes W1 between the cohorts, repeats ``b`` times,
    and returns the 95th percentile (``q95_null``)."""
    n = n if n is not None else len(pool)
    if n == 0:
        return 0.0
    stats = np.empty(b)
    max_support = float(max(1.0, pool.max() - pool.min())) if len(pool) else 1.0
    for i in range(b):
        cohort_a = pool[rng.integers(0, len(pool), size=n)]
        cohort_b = pool[rng.integers(0, len(pool), size=n)]
        stats[i] = _safe_wasserstein(cohort_a, cohort_b, max_support=max_support)
    return float(np.quantile(stats, 0.95))


def clustered_bootstrap_bag(
    seed_bags: list[np.ndarray],
    *,
    max_support: float,
    n: int | None = None,
    b: int = DEFAULT_B_RESAMPLES,
    rng: np.random.Generator,
) -> float:
    """Two-sample Karr-only cluster bootstrap for a pooled-bag statistic
    (used by the timing gate). Resamples whole per-seed fire-tick bags
    (the cluster unit) with replacement into two independent cohorts of
    ``n`` seeds each, pools each cohort's ticks, computes W1 between the
    two pooled bags, repeats ``b`` times, returns the 95th percentile."""
    n = n if n is not None else len(seed_bags)
    if n == 0:
        return 0.0
    stats = np.empty(b)
    for i in range(b):
        idx_a = rng.integers(0, len(seed_bags), size=n)
        idx_b = rng.integers(0, len(seed_bags), size=n)
        bag_a = np.concatenate([seed_bags[j] for j in idx_a]) if len(idx_a) else np.array([])
        bag_b = np.concatenate([seed_bags[j] for j in idx_b]) if len(idx_b) else np.array([])
        stats[i] = _safe_wasserstein(bag_a, bag_b, max_support=max_support)
    return float(np.quantile(stats, 0.95))


# ---------------------------------------------------------------------------
# Spurious OC-only firing detection (C6)
# ---------------------------------------------------------------------------


def oc_only_fire_ticks(karr_timeline: EventTimeline, oc_timeline: EventTimeline) -> list[int]:
    """Ticks where OC fired but Karr did not, for one (process, seed) pair.

    This is the check a firing-tick-only design can never produce (spec
    claim C6): OC-only firings between Karr firing ticks must be visible
    and able to fail the run, not silently dropped between sampled ticks.
    """
    karr_fired_ticks = {o.tick for o in karr_timeline.observations if o.fired}
    return sorted(
        {
            o.tick
            for o in oc_timeline.observations
            if o.fired and o.tick not in karr_fired_ticks
        }
    )


# ---------------------------------------------------------------------------
# Count gate (D3)
# ---------------------------------------------------------------------------


def count_gate(
    karr_timelines: list[EventTimeline],
    oc_timelines: list[EventTimeline],
    *,
    rng: np.random.Generator,
    b_resamples: int = DEFAULT_B_RESAMPLES,
    k_eng: float = DEFAULT_K_ENG,
    # M-support-floor-correctness (Opus5 review round 3, item #3): this
    # bare default is only correct for repeated_firing-style processes.
    # Any caller gating a single_firing process MUST pass an explicit
    # `min_karr_support` computed via `count_support_floor(event_timing_model,
    # n_seeds_total)` instead of relying on this default -- `evaluate_gate`
    # always does so. The default exists only so this function remains
    # directly callable (e.g. from tests) without requiring every caller to
    # thread a timing model through first.
    min_karr_support: int = DEFAULT_MIN_KARR_POOLED_FIRE_COUNT_REPEATED_FIRING,
) -> GateChannelResult:
    t_karr = int(per_seed_total_counts(karr_timelines).sum())
    t_oc = int(per_seed_total_counts(oc_timelines).sum())
    n_nonzero_karr = int(np.count_nonzero(per_seed_total_counts(karr_timelines)))
    n_nonzero_oc = int(np.count_nonzero(per_seed_total_counts(oc_timelines)))

    if t_karr == 0:
        if t_oc == 0:
            return _channel_result(
                channel="count",
                verdict="NO_KARR_SUPPORT",
                statistic_name="w1_per_seed_count",
                statistic_value=None,
                q95_null=None,
                k_eng=k_eng,
                threshold=None,
                n_nonzero_oc=n_nonzero_oc,
                n_nonzero_karr=n_nonzero_karr,
                reasons=["T_karr == 0 and T_oc == 0: no Karr event support in this window (D3 precedence)."],
                extra=_extra(),
            )
        return _channel_result(
            channel="count",
            verdict="FAIL",
            statistic_name="w1_per_seed_count",
            statistic_value=None,
            q95_null=None,
            k_eng=k_eng,
            threshold=None,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=[f"T_karr == 0 but T_oc == {t_oc} > 0: hard FAIL per D3 precedence (no zero==zero PASS)."],
            extra=_extra(),
        )

    # M1 (Opus5 review): a nonzero-but-under-powered Karr baseline must
    # refuse before spending any bootstrap compute on it, not silently
    # compute a "PASS" from too few pooled observations.
    if t_karr < min_karr_support:
        return _channel_result(
            channel="count",
            verdict="INSUFFICIENT_KARR_SUPPORT",
            statistic_name="w1_per_seed_count",
            statistic_value=None,
            q95_null=None,
            k_eng=k_eng,
            threshold=None,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=[
                f"T_karr={t_karr} is below the required support floor of "
                f"{min_karr_support} pooled Karr event counts; refusing to "
                "compute a gate statistic from an under-powered cohort (M1)."
            ],
            extra=_extra({"t_karr": t_karr, "t_oc": t_oc, "min_karr_support": min_karr_support}),
        )

    # M-metric-correctness (one-sided empty behavior): Karr has support but
    # OC produced nothing at all -- the mirror image of the T_karr==0 hard
    # FAIL above. Must never be reachable as a numeric "close enough" PASS.
    if t_oc == 0:
        return _channel_result(
            channel="count",
            verdict="NO_OC_SUPPORT",
            statistic_name="w1_per_seed_count",
            statistic_value=None,
            q95_null=None,
            k_eng=k_eng,
            threshold=None,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=[
                f"OC produced zero events across the cohort while Karr fired "
                f"T_karr={t_karr} time(s): hard NO_OC_SUPPORT (no capped-"
                "silence green)."
            ],
            extra=_extra({"t_karr": t_karr, "t_oc": t_oc}),
        )

    guard = count_support_guard(t_karr, t_oc)
    karr_counts = per_seed_total_counts(karr_timelines)
    oc_counts = per_seed_total_counts(oc_timelines)
    max_support = float(max(1.0, karr_counts.max() if len(karr_counts) else 1.0))
    w1 = _safe_wasserstein(karr_counts, oc_counts, max_support=max_support)

    # D3's support guard is a hard, non-statistical bound (T_oc must land
    # in [floor(0.5*T_karr), ceil(2*T_karr)]) -- a violation is a clear-cut
    # FAIL regardless of what the null bootstrap would say, so it is
    # checked BEFORE the null-degeneracy check below. This also matches
    # the metric-correctness fix (Opus5 review): a DEGENERATE_NULL must
    # never be allowed to mask/replace an outright guard-violation FAIL
    # (e.g. a constant-count Karr pool that also happens to be wildly
    # outside the OC support guard must still report FAIL, not
    # DEGENERATE_NULL).
    if not guard.ok:
        return _channel_result(
            channel="count",
            verdict="FAIL",
            statistic_name="w1_per_seed_count",
            statistic_value=w1,
            q95_null=None,
            k_eng=k_eng,
            threshold=None,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=[
                f"T_oc={t_oc} outside D3 support guard [{guard.floor}, {guard.ceiling}] "
                f"around T_karr={t_karr}."
            ],
            extra=_extra(
                {"t_karr": t_karr, "t_oc": t_oc, "guard_floor": guard.floor, "guard_ceiling": guard.ceiling}
            ),
        )

    q95_null = clustered_bootstrap_scalar(karr_counts, b=b_resamples, rng=rng)

    # M1 (Opus5 review): a zero-width null means the bootstrap could not
    # establish any noise floor at all -- SEED_NOISE (or PASS) can never be
    # derived from it.
    if q95_null == 0.0:
        return _channel_result(
            channel="count",
            verdict="DEGENERATE_NULL",
            statistic_name="w1_per_seed_count",
            statistic_value=w1,
            q95_null=q95_null,
            k_eng=k_eng,
            threshold=0.0,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=[
                "Karr-only clustered null bootstrap collapsed to q95_null=0 "
                "(zero-width null); a SEED_NOISE/PASS verdict cannot be "
                "derived from a degenerate null (M1)."
            ],
            extra=_extra({"t_karr": t_karr, "t_oc": t_oc}),
        )

    threshold = k_eng * q95_null

    reasons = []
    if w1 <= q95_null:
        verdict = "SEED_NOISE"
    elif w1 <= threshold:
        verdict = "PASS"
    else:
        verdict = "FAIL"
        reasons.append(f"w1={w1:.4g} exceeds threshold={threshold:.4g} (k_eng * q95_null).")

    return _channel_result(
        channel="count",
        verdict=verdict,
        statistic_name="w1_per_seed_count",
        statistic_value=w1,
        q95_null=q95_null,
        k_eng=k_eng,
        threshold=threshold,
        n_nonzero_oc=n_nonzero_oc,
        n_nonzero_karr=n_nonzero_karr,
        reasons=reasons,
        extra=_extra(
            {"t_karr": t_karr, "t_oc": t_oc, "guard_floor": guard.floor, "guard_ceiling": guard.ceiling}
        ),
    )


# ---------------------------------------------------------------------------
# Timing gate (D2 + addendum)
# ---------------------------------------------------------------------------


def timing_gate_repeated_firing(
    karr_timelines: list[EventTimeline],
    oc_timelines: list[EventTimeline],
    *,
    rng: np.random.Generator,
    b_resamples: int = DEFAULT_B_RESAMPLES,
    k_eng: float = DEFAULT_K_ENG,
    min_karr_support: int = DEFAULT_MIN_KARR_POOLED_FIRE_COUNT_REPEATED_FIRING,
) -> GateChannelResult:
    """RibosomeAssembly-style timing statistic: W1 on the pooled
    firing-tick bag (NOT hazard, NOT inter-arrival -- see D2 addendum)."""
    karr_seed_bags = [np.array(t.fire_ticks, dtype=float) for t in karr_timelines]
    oc_seed_bags = [np.array(t.fire_ticks, dtype=float) for t in oc_timelines]
    karr_bag = pooled_fire_ticks(karr_timelines)
    oc_bag = pooled_fire_ticks(oc_timelines)
    n_nonzero_karr = int(sum(1 for b in karr_seed_bags if len(b)))
    n_nonzero_oc = int(sum(1 for b in oc_seed_bags if len(b)))

    if len(karr_bag) == 0:
        if len(oc_bag) == 0:
            return _channel_result(
                channel="timing",
                verdict="NO_KARR_SUPPORT",
                statistic_name="w1_pooled_fire_tick_bag",
                statistic_value=None,
                q95_null=None,
                k_eng=k_eng,
                threshold=None,
                n_nonzero_oc=n_nonzero_oc,
                n_nonzero_karr=n_nonzero_karr,
                reasons=["No Karr fire ticks in window: timing statistic is undefined (D3 precedence applied to timing)."],
                extra=_extra(),
            )
        return _channel_result(
            channel="timing",
            verdict="FAIL",
            statistic_name="w1_pooled_fire_tick_bag",
            statistic_value=None,
            q95_null=None,
            k_eng=k_eng,
            threshold=None,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=["Karr has zero fire ticks but OC fired: hard FAIL, no zero==zero PASS."],
            extra=_extra(),
        )

    # M1 (Opus5 review): RA-style repeated firing requires >=50 pooled Karr
    # fire ticks before any bootstrap is trustworthy.
    if len(karr_bag) < min_karr_support:
        return _channel_result(
            channel="timing",
            verdict="INSUFFICIENT_KARR_SUPPORT",
            statistic_name="w1_pooled_fire_tick_bag",
            statistic_value=None,
            q95_null=None,
            k_eng=k_eng,
            threshold=None,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=[
                f"Pooled Karr fire-tick count={len(karr_bag)} is below the "
                f"required support floor of {min_karr_support}; refusing to "
                "compute a timing gate statistic from an under-powered "
                "cohort (M1)."
            ],
            extra=_extra(
                {"n_karr_fire_ticks": int(len(karr_bag)), "min_karr_support": min_karr_support}
            ),
        )

    if len(oc_bag) == 0:
        return _channel_result(
            channel="timing",
            verdict="NO_OC_SUPPORT",
            statistic_name="w1_pooled_fire_tick_bag",
            statistic_value=None,
            q95_null=None,
            k_eng=k_eng,
            threshold=None,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=[
                f"OC produced zero fire ticks while Karr pooled fire-tick "
                f"count={len(karr_bag)}: hard NO_OC_SUPPORT (no capped-"
                "silence green)."
            ],
            extra=_extra({"n_karr_fire_ticks": int(len(karr_bag))}),
        )

    max_support = float(max(1.0, karr_bag.max() - karr_bag.min())) if len(karr_bag) > 1 else 1.0
    w1 = _safe_wasserstein(karr_bag, oc_bag, max_support=max_support)
    q95_null = clustered_bootstrap_bag(karr_seed_bags, max_support=max_support, b=b_resamples, rng=rng)

    if q95_null == 0.0:
        return _channel_result(
            channel="timing",
            verdict="DEGENERATE_NULL",
            statistic_name="w1_pooled_fire_tick_bag",
            statistic_value=w1,
            q95_null=q95_null,
            k_eng=k_eng,
            threshold=0.0,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=[
                "Karr-only clustered null bootstrap collapsed to q95_null=0 "
                "(zero-width null); a SEED_NOISE/PASS verdict cannot be "
                "derived from a degenerate null (M1)."
            ],
            extra=_extra({"n_karr_fire_ticks": int(len(karr_bag)), "n_oc_fire_ticks": int(len(oc_bag))}),
        )

    threshold = k_eng * q95_null

    if w1 <= q95_null:
        verdict = "SEED_NOISE"
    elif w1 <= threshold:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    return _channel_result(
        channel="timing",
        verdict=verdict,
        statistic_name="w1_pooled_fire_tick_bag",
        statistic_value=w1,
        q95_null=q95_null,
        k_eng=k_eng,
        threshold=threshold,
        n_nonzero_oc=n_nonzero_oc,
        n_nonzero_karr=n_nonzero_karr,
        reasons=[] if verdict != "FAIL" else [f"w1={w1:.4g} exceeds threshold={threshold:.4g}."],
        extra=_extra({"n_karr_fire_ticks": int(len(karr_bag)), "n_oc_fire_ticks": int(len(oc_bag))}),
    )


def timing_gate_single_firing(
    karr_offsets: np.ndarray,
    oc_offsets: np.ndarray,
    *,
    rng: np.random.Generator,
    b_resamples: int = DEFAULT_B_RESAMPLES,
    k_eng: float = DEFAULT_K_ENG,
    n_seeds_total: int | None = None,
    min_karr_fired_seed_fraction: float = DEFAULT_MIN_KARR_FIRED_SEED_FRACTION_SINGLE_FIRING,
) -> GateChannelResult:
    """Cytokinesis-style timing statistic: W1 on pooled relative
    firing-tick offsets (``t_fire - t_reference``), one observation per
    seed that fired (D2 addendum).

    ``n_seeds_total`` is the *whole ensemble* size (fired + not-fired
    seeds); when supplied, the M1 support floor (spec C2: >=45/50 seeds
    fired) is enforced. It is optional so low-level statistic-only tests
    can still exercise this function without an ensemble context; the core
    evaluator (``evaluate_gate``) always supplies it.
    """
    n_nonzero_karr = int(len(karr_offsets))
    n_nonzero_oc = int(len(oc_offsets))

    if n_nonzero_karr == 0:
        if n_nonzero_oc == 0:
            verdict = "NO_KARR_SUPPORT"
            reasons = ["No Karr firing offsets available: timing statistic is undefined."]
        else:
            verdict = "FAIL"
            reasons = ["Karr has zero firing offsets but OC fired: hard FAIL."]
        return _channel_result(
            channel="timing",
            verdict=verdict,
            statistic_name="w1_relative_firing_offset",
            statistic_value=None,
            q95_null=None,
            k_eng=k_eng,
            threshold=None,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=reasons,
            extra=_extra(),
        )

    # M1 (Opus5 review): Cytokinesis-style single_firing requires >=45/50
    # (fraction 0.9) of the *whole ensemble* to have Karr-fired, not merely
    # "at least one seed fired".
    if n_seeds_total is not None and n_seeds_total > 0:
        fired_fraction = n_nonzero_karr / n_seeds_total
        if fired_fraction < min_karr_fired_seed_fraction:
            return _channel_result(
                channel="timing",
                verdict="INSUFFICIENT_KARR_SUPPORT",
                statistic_name="w1_relative_firing_offset",
                statistic_value=None,
                q95_null=None,
                k_eng=k_eng,
                threshold=None,
                n_nonzero_oc=n_nonzero_oc,
                n_nonzero_karr=n_nonzero_karr,
                reasons=[
                    f"Only {n_nonzero_karr}/{n_seeds_total} seeds "
                    f"({fired_fraction:.2%}) Karr-fired, below the required "
                    f"floor of {min_karr_fired_seed_fraction:.0%} (spec C2, M1)."
                ],
                extra=_extra(
                    {
                        "n_seeds_total": n_seeds_total,
                        "n_karr_fired_seeds": n_nonzero_karr,
                        "min_karr_fired_seed_fraction": min_karr_fired_seed_fraction,
                    }
                ),
            )

    if n_nonzero_oc == 0:
        return _channel_result(
            channel="timing",
            verdict="NO_OC_SUPPORT",
            statistic_name="w1_relative_firing_offset",
            statistic_value=None,
            q95_null=None,
            k_eng=k_eng,
            threshold=None,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=[
                f"OC produced zero firing offsets while Karr fired on "
                f"{n_nonzero_karr} seed(s): hard NO_OC_SUPPORT (no capped-"
                "silence green)."
            ],
            extra=_extra(),
        )

    max_support = float(max(1.0, karr_offsets.max() - karr_offsets.min())) if len(karr_offsets) > 1 else 1.0
    w1 = _safe_wasserstein(karr_offsets, oc_offsets, max_support=max_support)
    # Single-firing null: resample individual seed-offsets (each offset IS
    # already the cluster unit here, since one seed contributes one offset).
    q95_null = clustered_bootstrap_scalar(karr_offsets, b=b_resamples, rng=rng)

    if q95_null == 0.0:
        return _channel_result(
            channel="timing",
            verdict="DEGENERATE_NULL",
            statistic_name="w1_relative_firing_offset",
            statistic_value=w1,
            q95_null=q95_null,
            k_eng=k_eng,
            threshold=0.0,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=[
                "Karr-only clustered null bootstrap collapsed to q95_null=0 "
                "(zero-width null); a SEED_NOISE/PASS verdict cannot be "
                "derived from a degenerate null (M1)."
            ],
            extra=_extra(),
        )

    threshold = k_eng * q95_null

    if w1 <= q95_null:
        verdict = "SEED_NOISE"
    elif w1 <= threshold:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    return _channel_result(
        channel="timing",
        verdict=verdict,
        statistic_name="w1_relative_firing_offset",
        statistic_value=w1,
        q95_null=q95_null,
        k_eng=k_eng,
        threshold=threshold,
        n_nonzero_oc=n_nonzero_oc,
        n_nonzero_karr=n_nonzero_karr,
        reasons=[] if verdict != "FAIL" else [f"w1={w1:.4g} exceeds threshold={threshold:.4g}."],
        extra=_extra(),
    )


# ---------------------------------------------------------------------------
# Payload gate (D6 -- generic; process-specific gateability is a registry
# flag, not something this module decides)
# ---------------------------------------------------------------------------


# Worst-to-best severity ordering used to aggregate `payload_gate`'s
# per-component verdicts into ONE channel verdict (Opus5 review round 3,
# item #1): the channel verdict is the WORST verdict across every
# component, never derived from whichever component happens to have the
# largest raw W1 (that silently let a component with a large-but-
# proportionally-noisy W1 mask a small-but-many-times-its-own-null
# divergence in a different component). FAIL-class verdicts (including the
# two component-keyspace verdicts, item #2) always outrank a refusal
# (DEGENERATE_NULL), which always outranks a clean PASS/SEED_NOISE.
_PAYLOAD_VERDICT_PRIORITY: tuple[str, ...] = (
    "FAIL",
    "NO_OC_COMPONENT",
    "SPURIOUS_OC_COMPONENT",
    "DEGENERATE_NULL",
    "SEED_NOISE",
    "PASS",
)


def _worst_payload_verdict(verdicts: set[str]) -> str:
    for candidate in _PAYLOAD_VERDICT_PRIORITY:
        if candidate in verdicts:
            return candidate
    raise ValueError(f"payload_gate: no recognized verdict among {sorted(verdicts)!r}")


def _payload_component_result(
    component: str,
    karr_vals: np.ndarray,
    oc_vals: np.ndarray,
    *,
    b_resamples: int,
    k_eng: float,
    rng: np.random.Generator,
) -> PayloadComponentResult:
    """One payload component's own W1 + own seed-cluster-bootstrapped null
    + own PASS/SEED_NOISE/FAIL/DEGENERATE_NULL verdict (Opus5 review round
    3, item #1) -- mirrors `count_gate`/`timing_gate_*`'s decision logic
    exactly, applied per-component instead of once globally over whichever
    component has the largest raw statistic."""
    max_support = float(max(1.0, karr_vals.max() - karr_vals.min())) if len(karr_vals) > 1 else 1.0
    w1 = _safe_wasserstein(karr_vals, oc_vals, max_support=max_support)
    # M-metric-correctness: bootstrap THIS component's own null,
    # seed-cluster preserved (karr_vals is already one entry per
    # seed/cluster, matching count_gate's clustered_bootstrap_scalar
    # convention) -- never pool heterogeneous components together, and
    # never resample individual fires (which would pseudo-replicate within
    # a seed and understate the null's spread).
    q95_null = clustered_bootstrap_scalar(karr_vals, b=b_resamples, rng=rng)
    if q95_null == 0.0:
        return PayloadComponentResult(
            component=component,
            verdict="DEGENERATE_NULL",
            statistic_value=w1,
            q95_null=0.0,
            threshold=0.0,
            standardized_ratio=None,
            reasons=[
                f"Component '{component}': Karr-only clustered null bootstrap "
                "collapsed to q95_null=0 (zero-width null); a SEED_NOISE/PASS "
                "verdict cannot be derived from a degenerate null (M1)."
            ],
        )
    threshold = k_eng * q95_null
    standardized_ratio = w1 / q95_null
    if w1 <= q95_null:
        verdict, reasons = "SEED_NOISE", []
    elif w1 <= threshold:
        verdict, reasons = "PASS", []
    else:
        verdict = "FAIL"
        reasons = [
            f"Component '{component}': w1={w1:.4g} exceeds threshold={threshold:.4g} "
            f"(standardized_ratio={standardized_ratio:.2f}x its own null)."
        ]
    return PayloadComponentResult(
        component=component,
        verdict=verdict,
        statistic_value=w1,
        q95_null=q95_null,
        threshold=threshold,
        standardized_ratio=standardized_ratio,
        reasons=reasons,
    )


def payload_gate(
    karr_payloads: list[dict[str, float]],
    oc_payloads: list[dict[str, float]],
    *,
    rng: np.random.Generator,
    b_resamples: int = DEFAULT_B_RESAMPLES,
    k_eng: float = DEFAULT_K_ENG,
    required_components: frozenset[str] | None = None,
) -> GateChannelResult:
    """W1 per payload component at matched firings, with a PER-COMPONENT
    verdict/null (Opus5 review round 3, item #1) aggregated as the WORST
    verdict across components, over the UNION of Karr's and OC's
    normalized component keyspaces (item #2).

    Callers for a process whose registry entry declares
    ``magnitude_gateable: false`` (e.g. Cytokinesis per D6) must not call
    this and should instead emit a ``NOT_GATEABLE_REDUNDANT``
    :class:`GateChannelResult` directly.

    Positional convention: entry ``i`` of ``karr_payloads``/``oc_payloads``
    corresponds to seed/cluster ``i`` (matching ``count_gate``'s
    per-seed-array convention) -- this is what lets the per-component
    bootstrap below treat each list as already seed-clustered.

    ``required_components``, when supplied by an adapter (e.g. RA's exact
    2-WID payload keyspace), is enforced BEFORE any metric is computed:
    the observed component keyspace (union of Karr's and OC's normalized
    keys) must match it EXACTLY, or this refuses with a hard FAIL rather
    than silently zero-filling a missing/extra component into the
    comparison.
    """
    if not karr_payloads:
        n_nonzero_karr = 0
        n_nonzero_oc = int(len(oc_payloads))
        verdict = "NO_KARR_SUPPORT" if n_nonzero_oc == 0 else "FAIL"
        return _channel_result(
            channel="payload",
            verdict=verdict,
            statistic_name="w1_per_component_at_matched_firings",
            statistic_value=None,
            q95_null=None,
            k_eng=k_eng,
            threshold=None,
            n_nonzero_oc=n_nonzero_oc,
            n_nonzero_karr=n_nonzero_karr,
            reasons=["No matched Karr firings with payload to compare."],
            extra=_extra(),
        )

    karr_components = sorted({key for payload in karr_payloads for key in payload})
    oc_components = sorted({key for payload in oc_payloads for key in payload})

    # M-metric-correctness (one-sided empty behavior): Karr has payload but
    # OC produced none at all -- checked against `oc_components` (not just
    # `len(oc_payloads)`) so a cohort of structurally-present-but-empty OC
    # payload dicts (e.g. `[{}] * n`, exactly what an allocation-starved OC
    # tick produces per spec §4 fact 5) is caught here too, rather than
    # falling through to a per-component bootstrap that would report a
    # misleadingly-generic DEGENERATE_NULL instead of the more informative
    # NO_OC_SUPPORT. Must never silently zero-fill into a numeric
    # "close enough" PASS.
    if not oc_payloads or not oc_components:
        return _channel_result(
            channel="payload",
            verdict="NO_OC_SUPPORT",
            statistic_name="w1_per_component_at_matched_firings",
            statistic_value=None,
            q95_null=None,
            k_eng=k_eng,
            threshold=None,
            n_nonzero_oc=0,
            n_nonzero_karr=int(len(karr_payloads)),
            reasons=["OC produced zero matched-firing payloads while Karr had payload: hard NO_OC_SUPPORT."],
            extra=_extra(),
        )

    karr_set = set(karr_components)
    oc_set = set(oc_components)
    component_union = sorted(karr_set | oc_set)

    # Opus5 review round 3, item #2: enforce the adapter's exact required
    # keyspace BEFORE computing anything, if one is declared. This catches
    # a broken adapter mapping (e.g. still-positional `complex_0` Karr keys
    # that were never mapped onto OC's real wid-keyed names) even when
    # Karr's and OC's observed keys happen to partially intersect -- the
    # generic union-based checks below only catch a mismatch BETWEEN the
    # two sides, not a mismatch against what the adapter itself declares is
    # required. No zero-fill silent pass either way.
    if required_components is not None and set(component_union) != set(required_components):
        return _channel_result(
            channel="payload",
            verdict="FAIL",
            statistic_name="w1_per_component_at_matched_firings",
            statistic_value=None,
            q95_null=None,
            k_eng=k_eng,
            threshold=None,
            n_nonzero_oc=int(len(oc_payloads)),
            n_nonzero_karr=int(len(karr_payloads)),
            reasons=[
                f"Observed payload component keyspace {component_union} does not "
                "exactly match the adapter's required keyspace "
                f"{sorted(required_components)}; refusing to compute a payload "
                "metric on a mismatched keyspace (no zero-fill)."
            ],
            extra=_extra(
                {
                    "karr_components": karr_components,
                    "oc_components": oc_components,
                    "required_components": sorted(required_components),
                }
            ),
        )

    # Opus5 review round 3, item #2: components = UNION of Karr's and OC's
    # normalized keys, not Karr's alone (the pre-round-3 bug: a component
    # OC never produced at all -- as opposed to producing with value 0 --
    # was simply never iterated, so a dropped OC component was invisible).
    # A component present in Karr but missing from OC entirely is
    # `NO_OC_COMPONENT`; the mirror image (OC invents a component Karr
    # never produced) is `SPURIOUS_OC_COMPONENT`. Both are FAIL-class and
    # decided BEFORE any metric is computed for that component, never
    # zero-filled into a numeric comparison.
    per_component_results: list[PayloadComponentResult] = []
    for component in component_union:
        karr_has = component in karr_set
        oc_has = component in oc_set
        if karr_has and not oc_has:
            per_component_results.append(
                PayloadComponentResult(
                    component=component,
                    verdict="NO_OC_COMPONENT",
                    statistic_value=None,
                    q95_null=None,
                    threshold=None,
                    standardized_ratio=None,
                    reasons=[
                        f"Component '{component}' appears in Karr's payload but "
                        "never appears in any OC payload across the cohort -- an "
                        "adapter mapping gap, not a numeric divergence."
                    ],
                )
            )
            continue
        if oc_has and not karr_has:
            per_component_results.append(
                PayloadComponentResult(
                    component=component,
                    verdict="SPURIOUS_OC_COMPONENT",
                    statistic_value=None,
                    q95_null=None,
                    threshold=None,
                    standardized_ratio=None,
                    reasons=[
                        f"Component '{component}' appears in OC's payload but "
                        "never appears in any Karr payload across the cohort -- "
                        "OC is reporting a component Karr's own normalization "
                        "never produced."
                    ],
                )
            )
            continue
        karr_vals = np.array([p.get(component, 0.0) for p in karr_payloads], dtype=float)
        oc_vals = np.array([p.get(component, 0.0) for p in oc_payloads], dtype=float)
        per_component_results.append(
            _payload_component_result(component, karr_vals, oc_vals, b_resamples=b_resamples, k_eng=k_eng, rng=rng)
        )

    verdict = _worst_payload_verdict({r.verdict for r in per_component_results})

    # Representative summary: among the components that share the
    # aggregated worst verdict, surface the one with the most extreme
    # standardized_ratio (falling back to the first if none have a ratio,
    # e.g. every tied component is NO_OC_COMPONENT/SPURIOUS_OC_COMPONENT/
    # DEGENERATE_NULL) as the channel's top-level statistic_value/q95_null/
    # threshold/standardized_ratio. `per_component` below always carries
    # every component's own full result regardless of which one is picked
    # here for the summary.
    tied = [r for r in per_component_results if r.verdict == verdict]
    representative = max(tied, key=lambda r: (r.standardized_ratio is not None, r.standardized_ratio or float("-inf")))

    reasons: list[str] = []
    for r in per_component_results:
        reasons.extend(r.reasons)

    return _channel_result(
        channel="payload",
        verdict=verdict,
        statistic_name="w1_per_component_at_matched_firings",
        statistic_value=representative.statistic_value,
        q95_null=representative.q95_null,
        k_eng=k_eng,
        threshold=representative.threshold,
        n_nonzero_oc=int(len(oc_payloads)),
        n_nonzero_karr=int(len(karr_payloads)),
        reasons=reasons,
        per_component=per_component_results,
        standardized_ratio=representative.standardized_ratio,
        extra=_extra(
            {
                "karr_components": karr_components,
                "oc_components": oc_components,
                "component_union": component_union,
                "representative_component": representative.component,
            }
        ),
    )
