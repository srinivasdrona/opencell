"""Tests for `scripts/l22_evidence/macromol_network2_divergence_ledger.py`.

Run via `bin\\oc-pytest tests/scripts/test_macromol_network2_divergence_ledger.py -v`.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.l22_evidence import macromol_network2_divergence_ledger as ledger  # noqa: E402
from scripts.l22_extraction import macromol_active_window as maw  # noqa: E402


@pytest.fixture(scope="module")
def real_ledger_payload():
    """One real, full 50-seed divergence-ledger build against the tracked
    active-window cohort (via the canonical, unmodified Design-A loader --
    no env var, no override)."""
    return ledger.build_ledger()


def test_network2_structure_matches_the_active_window_contract(real_ledger_payload):
    payload = real_ledger_payload
    assert payload["network2_indices_0b"] == list(maw.NETWORK2_COMPLEX_INDICES_0B) == [22, 23]
    assert payload["network2_complex_wids"] == ["MG_041_062_429_PENTAMER", "MG_041_069_429_PENTAMER"]
    assert payload["network2_subunit_wids"] == [
        "MG_041_MONOMER",
        "MG_062_MONOMER",
        "MG_069_MONOMER",
        "MG_429_MONOMER",
    ]
    assert payload["network2_stoichiometry_matrix"] == [[1, 1], [2, 0], [0, 2], [2, 2]]


def test_real_ledger_covers_all_50_seeds(real_ledger_payload):
    payload = real_ledger_payload
    assert payload["n_seeds"] == 50
    assert len(payload["per_seed_ledger"]) == 50
    assert {row["seed"] for row in payload["per_seed_ledger"]} == set(range(50))


def test_real_ledger_self_validates(real_ledger_payload):
    assert ledger.validate_ledger_artifact(real_ledger_payload) is None


def test_real_ledger_oc_rates_match_literal_matlab_formula_exactly(real_ledger_payload):
    """The central cross-check: OC's ACTUAL internal collision-theory rate
    computation (captured via live instrumentation of the real, unmodified
    production `_per_cluster_mc` function) must match an INDEPENDENT,
    from-scratch re-derivation of the literal MATLAB formula, for every
    seed. This is the direct evidence that there is no rate-formula-level
    divergence between OC and the vendored MATLAB source."""
    payload = real_ledger_payload
    assert payload["formula_matches_literal_matlab"] is True
    assert payload["max_oc_vs_matlab_rate_abs_diff"] < 1e-9
    for row in payload["per_seed_ledger"]:
        for oc_rate, matlab_rate in zip(row["oc_internal_rates"], row["literal_matlab_rates"], strict=True):
            assert abs(oc_rate - matlab_rate) < 1e-9


def test_real_ledger_shows_genuine_seed_dependent_stochasticity(real_ledger_payload):
    """Repeated identical before-states (the trigger-tick monomer buildup
    is nearly deterministic, so several different seeds land on the exact
    same availability) must NOT always produce the same OC outcome -- that
    would indicate a deterministic/hardcoded draw rather than genuine
    per-seed stochastic sampling."""
    payload = real_ledger_payload
    assert payload["n_repeated_before_state_groups"] < payload["n_seeds"]  # duplicates really exist
    assert payload["n_repeated_before_state_groups_with_varying_oc_outcome"] > 0


def test_real_ledger_statistical_consistency_check_is_reproducible(real_ledger_payload):
    """Re-running the ledger must produce IDENTICAL statistical-check
    numbers (fixed RNG seed, fixed trial count) -- proves the consistency
    check itself is not silently randomized/unreproducible."""
    second = ledger.build_ledger()
    assert second["statistical_consistency_check"] == real_ledger_payload["statistical_consistency_check"]
    assert second["theoretical_mean_p22"] == real_ledger_payload["theoretical_mean_p22"]


def test_real_ledger_verdict_is_no_code_divergence_found(real_ledger_payload):
    """The actual, current, honest finding: no proven code-level divergence
    exists. If a future code change to `karr_macromolecular_complexation.py`
    or the fixture introduces a real divergence, this test will fail and
    must be re-investigated, not silently updated to match."""
    payload = real_ledger_payload
    assert payload["verdict"] == "NO_CODE_DIVERGENCE_FOUND"
    assert payload["formula_matches_literal_matlab"] is True
    assert payload["statistical_consistency_check"]["karr_consistent_at_95pct"] is True
    assert payload["statistical_consistency_check"]["oc_consistent_at_95pct"] is True


def test_tampered_generator_source_hash_fails_validation(real_ledger_payload):
    tampered = copy.deepcopy(real_ledger_payload)
    tampered["generator_source_sha256_lf_normalized"] = "0" * 64
    assert ledger.validate_ledger_artifact(tampered) is not None


def test_tampered_fixture_hash_fails_validation(real_ledger_payload):
    tampered = copy.deepcopy(real_ledger_payload)
    tampered["fixture_sha256"] = "0" * 64
    assert ledger.validate_ledger_artifact(tampered) is not None


def test_incomplete_cohort_raises(tmp_path):
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    with pytest.raises(ValueError, match="not SUFFICIENT_ENSEMBLE"):
        ledger.build_ledger(data_root=empty_root)


def test_missing_seed_rows_fail_validation(real_ledger_payload):
    tampered = copy.deepcopy(real_ledger_payload)
    tampered["per_seed_ledger"] = tampered["per_seed_ledger"][:49]
    tampered["n_seeds"] = 49
    assert ledger.validate_ledger_artifact(tampered) is not None
