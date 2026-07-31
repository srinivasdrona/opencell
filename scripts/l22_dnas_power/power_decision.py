"""Pre-registered power decision rule + rate/CI helpers for the
DNASupercoiling `linkingNumbers` primary-component N=100 diagnostic.

See `docs/phase_f/l2_2_design_a/L22_DNAS_POWER_PREREG.md` §4 for the
decision rule this module implements verbatim: it must not be edited to
change the outcome of an already-run diagnostic.

`MIN_NONZERO_EVENTS` mirrors (does not redefine) the gating threshold
documented in `docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md`
("`n_nonzero < 30` (either side) -> `PRIMARY_INSUFFICIENT_SAMPLES`"); it is
duplicated here as a plain constant (rather than imported) because the
evidence-index evaluator that owns that constant is not itself importable
as a library from outside `scripts/l22_evidence/`, and this diagnostic must
not import/modify anything under that path.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

MIN_NONZERO_EVENTS = 30


@dataclass
class PowerEvaluation:
    n_nonzero_oc: int
    n_nonzero_karr: int
    min_nonzero_events: int
    powered: bool
    decision: str  # "EVALUATE_METRIC" | "STILL_UNDERPOWERED_AT_N100"

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_power(n_nonzero_oc: int, n_nonzero_karr: int) -> PowerEvaluation:
    """Pre-registered decision rule step 1/2 (L22_DNAS_POWER_PREREG.md §4).

    Powered iff BOTH sides clear `MIN_NONZERO_EVENTS`. This is a mechanical,
    outcome-independent check -- it does not look at W1/threshold at all.
    """
    powered = n_nonzero_oc >= MIN_NONZERO_EVENTS and n_nonzero_karr >= MIN_NONZERO_EVENTS
    return PowerEvaluation(
        n_nonzero_oc=int(n_nonzero_oc),
        n_nonzero_karr=int(n_nonzero_karr),
        min_nonzero_events=MIN_NONZERO_EVENTS,
        powered=bool(powered),
        decision="EVALUATE_METRIC" if powered else "STILL_UNDERPOWERED_AT_N100",
    )


def wilson_score_interval(n_successes: int, n_trials: int, *, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score CI for a binomial proportion (default z -> 95%).

    Used here to characterize uncertainty on the per-tick nonzero rate
    (`n_nonzero / n_trials`, trials = n_seeds * m_ticks) underlying an
    observed nonzero count, and to project an expected count (with CI) at a
    different N from a rate observed at a smaller N. This is a standard
    analytic CI (no resampling/simulation needed) -- appropriate here
    because re-running the OC simulation per bootstrap replicate would be
    prohibitively slow, and the projection only needs the count/rate, not
    the full per-sample tensor.
    """
    if n_trials <= 0:
        raise ValueError(f"n_trials must be positive; got {n_trials}")
    if not (0 <= n_successes <= n_trials):
        raise ValueError(f"n_successes={n_successes} out of range [0, {n_trials}]")
    p = n_successes / n_trials
    denom = 1 + z**2 / n_trials
    centre = p + z**2 / (2 * n_trials)
    half_width = z * math.sqrt(p * (1 - p) / n_trials + z**2 / (4 * n_trials**2))
    lo = (centre - half_width) / denom
    hi = (centre + half_width) / denom
    return max(0.0, lo), min(1.0, hi)


def project_nonzero_count(
    *,
    observed_n_nonzero: int,
    observed_n_trials: int,
    target_n_trials: int,
) -> dict[str, float]:
    """Project an expected nonzero count (with 95% Wilson CI) at
    `target_n_trials`, from a rate observed at `observed_n_trials`.

    Used to sanity-check the seeds-50-99 extension: does the actual N=100
    nonzero count fall inside the range predicted by the N=50 rate (i.e. is
    growth consistent with i.i.d. seeds), or did something structurally
    change (e.g. a schema drift, a differently-seeded RNG stream)?
    """
    rate_lo, rate_hi = wilson_score_interval(observed_n_nonzero, observed_n_trials)
    rate_point = observed_n_nonzero / observed_n_trials
    return {
        "observed_n_nonzero": observed_n_nonzero,
        "observed_n_trials": observed_n_trials,
        "observed_rate": rate_point,
        "rate_ci95": [rate_lo, rate_hi],
        "target_n_trials": target_n_trials,
        "projected_count_point": rate_point * target_n_trials,
        "projected_count_ci95": [rate_lo * target_n_trials, rate_hi * target_n_trials],
    }
