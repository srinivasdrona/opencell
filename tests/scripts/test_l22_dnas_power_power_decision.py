"""Targeted tests for scripts/l22_dnas_power/power_decision.py.

Pure unit tests (no fixtures/IO) for the pre-registered decision rule
(`evaluate_power`) and the rate/CI helpers (`wilson_score_interval`,
`project_nonzero_count`) used to build the N=100 power diagnostic report.

Run via `bin\\oc-pytest tests/scripts/test_l22_dnas_power_power_decision.py -v`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from scripts.l22_dnas_power import power_decision  # noqa: E402


def test_evaluate_power_matches_frozen_n50_bundle_underpowered_case():
    """Reproduces the exact frozen N=50 evidence-bundle numbers
    (n_oc=17, n_karr=24) for `linkingNumbers.delta_nnz`: both below 30, so
    the decision must be STILL_UNDERPOWERED (this is the bug this whole
    diagnostic exists to investigate -- the rule must reject it, not pass it)."""
    result = power_decision.evaluate_power(n_nonzero_oc=17, n_nonzero_karr=24)
    assert result.powered is False
    assert result.decision == "STILL_UNDERPOWERED_AT_N100"
    assert result.min_nonzero_events == 30


def test_evaluate_power_requires_both_sides_above_threshold():
    only_oc_powered = power_decision.evaluate_power(n_nonzero_oc=40, n_nonzero_karr=10)
    assert only_oc_powered.powered is False

    only_karr_powered = power_decision.evaluate_power(n_nonzero_oc=10, n_nonzero_karr=40)
    assert only_karr_powered.powered is False

    both_powered = power_decision.evaluate_power(n_nonzero_oc=30, n_nonzero_karr=30)
    assert both_powered.powered is True
    assert both_powered.decision == "EVALUATE_METRIC"


def test_evaluate_power_boundary_is_inclusive_at_exactly_30():
    result = power_decision.evaluate_power(n_nonzero_oc=30, n_nonzero_karr=30)
    assert result.powered is True
    result_below = power_decision.evaluate_power(n_nonzero_oc=29, n_nonzero_karr=30)
    assert result_below.powered is False


def test_evaluate_power_result_is_json_shape_stable():
    payload = power_decision.evaluate_power(n_nonzero_oc=17, n_nonzero_karr=24).to_dict()
    assert payload == {
        "n_nonzero_oc": 17,
        "n_nonzero_karr": 24,
        "min_nonzero_events": 30,
        "powered": False,
        "decision": "STILL_UNDERPOWERED_AT_N100",
    }


def test_wilson_score_interval_contains_point_estimate():
    lo, hi = power_decision.wilson_score_interval(24, 5000)
    point = 24 / 5000
    assert lo < point < hi
    assert 0.0 <= lo < hi <= 1.0


def test_wilson_score_interval_narrows_with_more_trials():
    lo_small, hi_small = power_decision.wilson_score_interval(24, 5000)
    lo_large, hi_large = power_decision.wilson_score_interval(240, 50000)
    assert (hi_large - lo_large) < (hi_small - lo_small)


def test_wilson_score_interval_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        power_decision.wilson_score_interval(1, 0)
    with pytest.raises(ValueError):
        power_decision.wilson_score_interval(-1, 10)
    with pytest.raises(ValueError):
        power_decision.wilson_score_interval(11, 10)


def test_project_nonzero_count_doubling_trials_roughly_doubles_projection():
    projection = power_decision.project_nonzero_count(
        observed_n_nonzero=24, observed_n_trials=5000, target_n_trials=10000
    )
    assert projection["projected_count_point"] == pytest.approx(48.0)
    assert projection["projected_count_ci95"][0] < 48.0 < projection["projected_count_ci95"][1]


def test_project_nonzero_count_flags_actual_outside_ci_as_inconsistent():
    """If the real N=100 observed count falls far outside the range
    predicted from the N=50 rate, that is evidence against the i.i.d.-seed
    assumption (e.g. a schema drift or RNG-stream problem in the extension),
    and callers (build_report.py) must be able to detect it mechanically."""
    projection = power_decision.project_nonzero_count(
        observed_n_nonzero=24, observed_n_trials=5000, target_n_trials=10000
    )
    lo, hi = projection["projected_count_ci95"]
    surprising_actual = int(hi) + 1000
    assert not (lo <= surprising_actual <= hi)
