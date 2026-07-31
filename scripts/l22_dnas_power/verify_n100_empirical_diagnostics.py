"""Empirical support/verification for the N=100 power-diagnostic report's
Wilson i.i.d.-tick discussion and W1-insensitivity bound (Opus5 review,
`docs/phase_f/l2_2_design_a/L22_DNAS_POWER_N100_REPORT.md` sections 3/5).

Reuses the existing, unmodified `load_chromosome_oracle_for_process` /
`chromosome_projection_matrix` helpers from the Design-A runner to pull the
per-(seed, tick) `linkingNumbers.delta_nnz` scalar for the Karr oracle side
(no reimplementation of the metric). Pure math (testable without real trace
data) lives in the functions below; `main()` does the real 100-seed x
100-tick load and prints the figures cited in the report.

Read-only / diagnostic-support only: not part of `build_report.py`'s
pipeline and does not write to `evidence_bundle/` or any tracked artifact.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]

SEEDS = list(range(100))
M_TICKS = 100
TOKEN = "linkingNumbers.delta_nnz"


def per_seed_event_counts(nonzero_mask: np.ndarray) -> np.ndarray:
    """Given an (n_seeds, m_ticks) boolean nonzero mask, count events/seed."""
    return nonzero_mask.sum(axis=1)


def iid_tick_clustering_expectation(
    n_seeds: int, m_ticks: int, total_events: int
) -> tuple[float, float]:
    """Expected # seeds with >=1 and >=2 events under an i.i.d.-per-tick
    Bernoulli(p) null, p = total_events / (n_seeds * m_ticks) -- the same
    assumption the analytic Wilson-score CI (power_decision.py) relies on.

    Returns (expected_seeds_with_ge1, expected_seeds_with_ge2).
    """
    p = total_events / (n_seeds * m_ticks)
    p_eq0 = (1.0 - p) ** m_ticks
    p_eq1 = m_ticks * p * (1.0 - p) ** (m_ticks - 1)
    p_ge1 = 1.0 - p_eq0
    p_ge2 = 1.0 - p_eq0 - p_eq1
    return n_seeds * p_ge1, n_seeds * p_ge2


def hypothetical_zero_side_w1(values: np.ndarray) -> float:
    """Exact W1 distance if one side were identically zero.

    For two equal-size (N) 1D empirical distributions, sorted-to-sorted
    (quantile) coupling is W1-optimal. If one side is all zeros (its sorted
    array is also all zeros), pairing rank-for-rank against the other
    side's sorted array gives cost sum(|0 - sorted_other_i|) = sum(|other|)
    -- independent of sort order, so this reduces to mean absolute value.
    """
    return float(np.abs(values).sum()) / values.size


def rate_ratio_stats(n_a: int, n_b: int) -> dict[str, float]:
    """Log-rate-ratio Wald test/CI for two Poisson-like event counts drawn
    over the same number of trials (so the trial count cancels in the
    ratio). H0: rate_a / rate_b = 1.
    """
    ratio = n_a / n_b
    log_ratio = math.log(ratio)
    se = math.sqrt(1.0 / n_a + 1.0 / n_b)
    z = log_ratio / se
    # two-sided normal p-value without importing scipy
    p_value = math.erfc(abs(z) / math.sqrt(2.0))
    z975 = 1.959963985
    ci_lo = math.exp(log_ratio - z975 * se)
    ci_hi = math.exp(log_ratio + z975 * se)
    return {
        "ratio": ratio,
        "z": z,
        "p_value": p_value,
        "ci95_lo": ci_lo,
        "ci95_hi": ci_hi,
    }


def main() -> None:
    sys.path.insert(0, str(REPO_ROOT / "tests" / "vivarium"))
    from _l2_2_design_a_runner_helpers import (
        load_chromosome_oracle_for_process,
        chromosome_projection_matrix,
    )

    oracle = load_chromosome_oracle_for_process("DNASupercoiling", SEEDS, M_TICKS)
    matrix = chromosome_projection_matrix(
        before_stores=oracle["before_stores"],
        after_stores=oracle["after_stores"],
        projection_spec=(TOKEN,),
    )
    values = matrix[:, :, 0]
    nonzero_mask = values != 0.0
    per_seed = per_seed_event_counts(nonzero_mask)
    total_events = int(per_seed.sum())
    seeds_with_events = int((per_seed > 0).sum())
    seeds_with_ge2 = int((per_seed >= 2).sum())
    exp_ge1, exp_ge2 = iid_tick_clustering_expectation(
        n_seeds=values.shape[0], m_ticks=values.shape[1], total_events=total_events
    )
    print(f"total_events={total_events}")
    print(f"seeds_with_events={seeds_with_events} (i.i.d.-tick expectation: {exp_ge1:.2f})")
    print(f"seeds_with_ge2_events={seeds_with_ge2} (i.i.d.-tick expectation: {exp_ge2:.2f})")
    print(f"half_a_total={int(per_seed[:50].sum())} half_b_total={int(per_seed[50:].sum())}")

    hyp_w1 = hypothetical_zero_side_w1(values)
    print(f"hypothetical_w1_if_oc_all_zero={hyp_w1:.6f} (raw threshold = 2.0)")

    rr = rate_ratio_stats(31, 42)
    print(
        "rate_ratio(oc=31,karr=42)="
        f" {rr['ratio']:.4f} 95% CI [{rr['ci95_lo']:.4f}, {rr['ci95_hi']:.4f}]"
        f" z={rr['z']:.4f} p={rr['p_value']:.4f}"
    )


if __name__ == "__main__":
    main()
