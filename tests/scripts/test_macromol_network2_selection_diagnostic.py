"""Tests for the preregistered MacromolecularComplexation network-2
selection diagnostic (`scripts/l22_evidence/macromol_network2_selection_diagnostic.py`).

Run via `bin\\oc-pytest tests/scripts/test_macromol_network2_selection_diagnostic.py -v`.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.l22_evidence import macromol_network2_selection_diagnostic as diag  # noqa: E402
from scripts.l22_extraction import macromol_active_window as maw  # noqa: E402


def test_preregistered_thresholds_are_pinned():
    """These values were fixed BEFORE the diagnostic was ever run against
    real data (see the module docstring) -- this test pins them so any
    future change is a visible, reviewed diff, never a silent edit."""
    assert diag.MAX_CLEAN_INDEX_SWAPS == 0
    assert diag.MAX_MARGINAL_RATE_ABS_DIFF == 0.10


def test_network2_indices_match_the_active_window_contract():
    assert diag.NETWORK2_INDICES_0B == maw.NETWORK2_COMPLEX_INDICES_0B == (22, 23)


@pytest.fixture(scope="module")
def real_diagnostic_payload():
    """One real, full 50-seed run against the tracked active-window cohort.
    Slow-ish (~50 single-tick OC evaluations) but not the ~20-minute full
    100-tick x 50-seed sweep the ordinary Design-A verdict runs -- this
    diagnostic only evaluates tick 0 (the trigger tick) per seed."""
    return diag.build_diagnostic()


def test_real_cohort_produces_a_complete_50_seed_diagnostic(real_diagnostic_payload):
    payload = real_diagnostic_payload
    assert payload["n_seeds"] == 50
    assert len(payload["seed_records"]) == 50
    assert {record["seed"] for record in payload["seed_records"]} == set(range(50))
    assert set(payload["per_index_stats"]) == {"22", "23"}
    for idx_key in ("22", "23"):
        stats = payload["per_index_stats"][idx_key]
        assert stats["n"] == 50
        total = (
            stats["n_true_positive"]
            + stats["n_false_positive"]
            + stats["n_false_negative"]
            + stats["n_true_negative"]
        )
        assert total == 50


def test_real_diagnostic_self_validates(real_diagnostic_payload):
    assert diag.validate_diagnostic_artifact(real_diagnostic_payload) is None


def test_real_diagnostic_verdict_is_mechanically_consistent_with_recorded_counts(real_diagnostic_payload):
    """Never trust the stored `verdict` string in isolation -- re-derive it
    from `n_clean_index_swaps_total` / `max_marginal_rate_abs_diff_observed`
    the same way `validate_diagnostic_artifact` does, and cross-check
    against the per-seed records independently."""
    payload = real_diagnostic_payload
    n_swaps_from_records = sum(
        1
        for record in payload["seed_records"]
        for idx, other in ((22, 23), (23, 22))
        if set(record["karr_selected_indices"]) == {idx} and set(record["oc_selected_indices"]) == {other}
    )
    assert payload["n_clean_index_swaps_total"] == n_swaps_from_records
    expected_verdict = (
        "FAIL"
        if (
            n_swaps_from_records > diag.MAX_CLEAN_INDEX_SWAPS
            or payload["max_marginal_rate_abs_diff_observed"] > diag.MAX_MARGINAL_RATE_ABS_DIFF
        )
        else "PASS"
    )
    assert payload["verdict"] == expected_verdict


def test_tampered_verdict_field_fails_validation(real_diagnostic_payload):
    """Proves `validate_diagnostic_artifact` re-derives the verdict rather
    than trusting the stored string: flipping a FAIL to a PASS (or vice
    versa) without changing the underlying counts must be caught."""
    tampered = copy.deepcopy(real_diagnostic_payload)
    tampered["verdict"] = "PASS" if tampered["verdict"] == "FAIL" else "FAIL"
    error = diag.validate_diagnostic_artifact(tampered)
    assert error is not None
    assert "does not match mechanically re-derived" in error


def test_tampered_generator_source_hash_fails_validation(real_diagnostic_payload):
    tampered = copy.deepcopy(real_diagnostic_payload)
    tampered["generator_source_sha256_lf_normalized"] = "0" * 64
    error = diag.validate_diagnostic_artifact(tampered)
    assert error is not None
    assert "stale/tampered" in error


def test_tampered_preregistered_threshold_fails_validation(real_diagnostic_payload):
    """A tampered/relaxed threshold (e.g. raising the swap tolerance after
    the fact to launder a FAIL into a PASS) must be caught, never silently
    accepted as if it were always the pinned value."""
    tampered = copy.deepcopy(real_diagnostic_payload)
    tampered["preregistered_thresholds"]["max_clean_index_swaps"] = 999
    error = diag.validate_diagnostic_artifact(tampered)
    assert error is not None
    assert "max_clean_index_swaps drifted" in error


def test_incomplete_cohort_raises(tmp_path):
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    with pytest.raises(ValueError, match="not a complete, valid 50-seed ensemble"):
        diag.build_diagnostic(data_root=empty_root)


def test_missing_seed_records_fails_validation(real_diagnostic_payload):
    tampered = copy.deepcopy(real_diagnostic_payload)
    tampered["seed_records"] = tampered["seed_records"][:49]  # drop one seed
    tampered["n_seeds"] = 49
    error = diag.validate_diagnostic_artifact(tampered)
    assert error is not None
