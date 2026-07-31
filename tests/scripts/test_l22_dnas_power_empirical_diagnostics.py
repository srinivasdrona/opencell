"""Targeted tests for scripts/l22_dnas_power/verify_n100_empirical_diagnostics.py.

Pure unit tests (no real trace IO) for the report-correction support math:
i.i.d.-per-tick clustering expectation, the exact zero-side W1 bound, and
the log-rate-ratio Wald test/CI -- used to back the Opus5-requested
corrections in `L22_DNAS_POWER_N100_REPORT.md` sections 3/5 (empirical
42-events/37-seeds i.i.d.-tick support, rate ratio 0.738 CI [0.464,1.174]
z=-1.28 p=.20, and the hypothetical-zero-OC W1 insensitivity bound).

Run via `bin\\oc-pytest tests/scripts/test_l22_dnas_power_empirical_diagnostics.py -v`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_dnas_power import verify_n100_empirical_diagnostics as m  # noqa: E402


def test_per_seed_event_counts_sums_per_row():
    mask = np.array(
        [
            [True, False, True],
            [False, False, False],
            [True, True, True],
        ]
    )
    counts = m.per_seed_event_counts(mask)
    assert counts.tolist() == [2, 0, 3]


def test_iid_tick_clustering_expectation_matches_real_n100_figures():
    """Regression-pins the exact figures cited in the report: with
    n_seeds=100, m_ticks=100, total_events=42 (the real n100_combined Karr
    delta_nnz count), the i.i.d.-tick null expects ~34.35 seeds with >=1
    event and ~6.67 with >=2 -- vs. the observed 37 / 5."""
    exp_ge1, exp_ge2 = m.iid_tick_clustering_expectation(
        n_seeds=100, m_ticks=100, total_events=42
    )
    assert exp_ge1 == pytest.approx(34.353406632320315)
    assert exp_ge2 == pytest.approx(6.665548413375283)


def test_iid_tick_clustering_expectation_zero_events_is_zero():
    exp_ge1, exp_ge2 = m.iid_tick_clustering_expectation(
        n_seeds=100, m_ticks=100, total_events=0
    )
    assert exp_ge1 == 0.0
    assert exp_ge2 == 0.0


def test_hypothetical_zero_side_w1_is_mean_absolute_value():
    values = np.zeros((100, 100))
    values[0, 0] = 2.0
    values[1, 1] = -2.0
    # 4.0 total absolute mass over 10000 cells
    assert m.hypothetical_zero_side_w1(values) == pytest.approx(0.0004)


def test_hypothetical_zero_side_w1_matches_real_n100_karr_bound():
    """Regression-pins the exact bound cited in the report: sum(|karr
    delta_nnz|) = 84.0 over 10000 (seed, tick) trials -> W1 = 0.0084, far
    below the raw pass threshold of 2.0 (scale=2.0 x scaled threshold=1.0)."""
    values = np.zeros((100, 100))
    # 42 events totalling |value|=84 (i.e. every event has magnitude 2,
    # matching the real Karr-side delta_nnz trace for this component).
    flat = values.reshape(-1)
    flat[:42] = 2.0
    values = flat.reshape(100, 100)
    w1 = m.hypothetical_zero_side_w1(values)
    assert w1 == pytest.approx(0.0084)
    assert w1 < 2.0 / 200  # two orders of magnitude below raw threshold 2.0


def test_rate_ratio_stats_matches_real_n100_oc_vs_karr_delta_nnz():
    """Regression-pins the exact figures cited in the report for the
    n100_combined OC (31) vs Karr (42) delta_nnz nonzero-event counts."""
    stats = m.rate_ratio_stats(31, 42)
    assert stats["ratio"] == pytest.approx(0.7380952380952381)
    assert stats["z"] == pytest.approx(-1.2825186959694155)
    assert stats["p_value"] == pytest.approx(0.19966075078110598)
    assert stats["ci95_lo"] == pytest.approx(0.4640447176789613)
    assert stats["ci95_hi"] == pytest.approx(1.1739915567270027)
    # not statistically significant at alpha=0.05 -- consistent with the
    # sibling delta_value_sum channel's rate z~1.1 no-difference story
    assert abs(stats["z"]) < 1.96
    assert stats["p_value"] > 0.05


def test_rate_ratio_stats_symmetric_counts_gives_ratio_one():
    stats = m.rate_ratio_stats(30, 30)
    assert stats["ratio"] == 1.0
    assert stats["z"] == 0.0
    assert stats["p_value"] == pytest.approx(1.0)
