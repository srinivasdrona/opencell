"""Regression tests pinning the ProteinProcessingII H12 SENTINEL_FAIL
determination (see
docs/phase_f/l2_2_design_a/h12/perturbation/
PROTEINPROCESSINGII_MNRND_SHIM_DETERMINATION_2026-08-05.md).

This file does NOT attempt to flip the verdict green. It mechanically
pins two things:

  1. The current `H12_OBSERVED_REGIME` sentinel for ProteinProcessingII is
     reproducible from on-disk artifacts (fresh hashes, `decide_verdict`
     re-derivation, `validate_h12_support` rejection reason) -- so a
     future reader can trust the SENTINEL_FAIL in `evidence_index.json` is
     mechanically justified, not stale or hand-edited.
  2. The repaired manual `mnrnd` compatibility shim
     (`scripts/matlab/mnrnd.m`, fixed for the Canary D duplicate-bin-edge
     crash) is never wired into the genuine-MATLAB H12 Scenario B pathway
     (`scripts/matlab_h12_perturbation/`, `scripts/l22_evidence/
     h12_perturbation.py`) as a substitute for the missing Statistics
     Toolbox `mnrnd` -- doing so would silently swap Karr's real
     conditional-binomial `mnrnd` algorithm for this shim's different
     per-trial categorical-sampling algorithm under the same seed, which is
     exactly the "distributionally different RNG" bypass this
     determination rules out.

Run via `bin\\oc-pytest tests/scripts/test_h12_protii_sentinel_determination.py -v`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import (
    h12,  # noqa: E402
    schema,  # noqa: E402
)

PROCESS = "ProteinProcessingII"
ARTIFACT_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / f"{PROCESS}_h12.json"
EVIDENCE_INDEX_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "evidence_index.json"
SCENARIO_B_DRIVER = REPO_ROOT / "scripts" / "matlab_h12_perturbation" / "run_ppii_scenario_b_matlab.m"
SCENARIO_B_PROBE = REPO_ROOT / "scripts" / "matlab_h12_perturbation" / "probe_matlab_environment.m"
H12_PERTURBATION_SOURCE = REPO_ROOT / "scripts" / "l22_evidence" / "h12_perturbation.py"
MANUAL_MNRND_SHIM = REPO_ROOT / "scripts" / "matlab" / "mnrnd.m"


def _load_artifact() -> dict:
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. Reproduce the current sentinel derivation mechanically.
# ---------------------------------------------------------------------------


def test_artifact_file_exists_and_is_the_primary_gating_artifact():
    assert ARTIFACT_PATH.is_file()
    payload = _load_artifact()
    assert payload["process"] == PROCESS


def test_predictor_source_hash_is_fresh_not_stale():
    """The artifact's recorded predictor hash must match a fresh re-hash of
    the on-disk `scripts/l22_evidence/h12.py` -- if this ever fails, the
    artifact is stale and must be regenerated before its verdict can be
    trusted at all (see h12.py's v4 evaluator-schema note)."""
    payload = _load_artifact()
    module_path = REPO_ROOT / h12.EXPECTED_PREDICTOR_SOURCE_PATH
    assert payload["predictor_source_sha256_lf_normalized"] == h12._sha256_lf_normalized(module_path)


def test_vendored_karr_source_hash_is_fresh_not_stale():
    payload = _load_artifact()
    citation = payload["karr_source_citation"]
    vendored_path = REPO_ROOT / citation["vendored_path"]
    assert citation["vendored_sha256_lf_normalized"] == h12._sha256_lf_normalized(vendored_path)


def test_fixture_hash_is_fresh_not_stale():
    payload = _load_artifact()
    fixture_path = REPO_ROOT / payload["fixture_path"]
    assert payload["fixture_sha256"] == h12._sha256_file(fixture_path)


def test_decide_verdict_recomputation_from_stored_metrics_matches_artifact_exactly():
    """Feed the artifact's OWN recorded nontrivial/exact-match/branch
    metrics back through the pure, independently-testable `decide_verdict`
    function and require an exact (verdict, verdict_reason) match -- this
    is the mechanical reproduction of the sentinel's derivation without
    needing the (locally unavailable) full 50-seed oracle trace."""
    payload = _load_artifact()
    verdict, reason = h12.decide_verdict(
        payload["nontrivial_sample_count"],
        payload["exact_match_count"],
        payload["exact_match_rate"],
        payload["trivial_mismatch_count"],
        set(payload["branches_confirmed"]),
        h12.REQUIRED_BRANCHES[PROCESS],
    )
    assert verdict == payload["verdict"] == "H12_OBSERVED_REGIME"
    assert reason == payload["verdict_reason"]


def test_missing_required_branch_is_exactly_transferase_fires():
    payload = _load_artifact()
    assert payload["missing_required_branches"] == ["transferase_fires"]
    assert set(payload["branches_confirmed"]) == {"passthrough_fires", "peptidase_fires"}
    assert h12.REQUIRED_BRANCHES[PROCESS] == frozenset(
        {"passthrough_fires", "peptidase_fires", "transferase_fires"}
    )


def test_validate_h12_support_rejects_real_artifact_today():
    """The central acceptance gate must mechanically reject this artifact
    right now, with a reason naming the actual stored (non-CONFIRMED)
    verdict -- this is the exact mechanism producing evidence_index.json's
    SENTINEL_FAIL for the ProteinProcessingII row."""
    payload = _load_artifact()
    reason = h12.validate_h12_support(payload, expected_process=PROCESS)
    assert reason is not None
    assert "H12_CONFIRMED" in reason
    assert "H12_OBSERVED_REGIME" in reason


def test_evidence_index_ppii_row_records_matching_sentinel_fail():
    """Read-only check of the shared evidence_index.json (never edited by
    this task): the ProteinProcessingII row's reasons must currently
    contain the exact SENTINEL_FAIL string this determination explains."""
    payload = json.loads(EVIDENCE_INDEX_PATH.read_text(encoding="utf-8"))
    rows = [row for row in payload["rows"] if row["process"] == PROCESS]
    assert len(rows) == 1
    row = rows[0]
    assert row["green"] is False
    assert row["mechanical_verdict"] == schema.STATUS_FAIL
    assert any(
        reason.startswith(schema.STATUS_SENTINEL_FAIL) and "H12_OBSERVED_REGIME" in reason
        for reason in row["reasons"]
    )


# ---------------------------------------------------------------------------
# 2. The repaired manual mnrnd shim must never be wired into Scenario B.
# ---------------------------------------------------------------------------


def test_manual_mnrnd_shim_file_exists_and_is_unrelated_subsystem():
    """Sanity: the shim this task investigated is a real, tracked file, so
    the "never wired in" checks below are checking against a real
    artifact, not a typo'd path that would vacuously pass."""
    assert MANUAL_MNRND_SHIM.is_file()
    source = MANUAL_MNRND_SHIM.read_text(encoding="utf-8")
    # The shim must keep disclosing it is a minimal fallback (not a
    # bit-identical reimplementation of the real Statistics Toolbox mnrnd).
    assert "Minimal multinomial RNG fallback" in source
    assert "bit-identical" not in source.lower()
    assert "Deliberately does NOT call histcounts" in source


@pytest.mark.parametrize("path", [SCENARIO_B_DRIVER, SCENARIO_B_PROBE])
def test_scenario_b_matlab_scripts_never_addpath_manual_mnrnd_shim_dir(path):
    """Regression guard: neither genuine-MATLAB Scenario B script may ever
    addpath the Octave/manual-shim directory (`scripts/matlab`) -- that
    would silently make MATLAB resolve `mnrnd` to the different-algorithm
    manual shim instead of the real Statistics Toolbox implementation (or
    instead of erroring honestly when the toolbox is absent)."""
    source = path.read_text(encoding="utf-8")
    assert "scripts/matlab'" not in source
    assert "scripts\\matlab'" not in source
    assert "scripts/matlab\"" not in source


def test_scenario_b_matlab_scripts_addpath_only_the_real_wholecell_src_root():
    """Positive control for the guard above: both scripts DO addpath the
    resolved WholeCell src root (containing the real RandStream/mnrnd),
    proving the absence check above is not vacuous."""
    for path in (SCENARIO_B_DRIVER, SCENARIO_B_PROBE):
        source = path.read_text(encoding="utf-8")
        assert "addpath(wholecell_src)" in source


def test_h12_perturbation_module_never_references_manual_mnrnd_shim():
    """The Python-side H12 perturbation module must never import, shell
    out to, or otherwise reference the manual mnrnd shim or its directory
    -- the Scenario B evidence pipeline is genuine-MATLAB-only end to
    end."""
    source = H12_PERTURBATION_SOURCE.read_text(encoding="utf-8")
    assert "scripts/matlab/mnrnd" not in source
    assert "scripts.matlab.mnrnd" not in source
    assert "scripts\\matlab\\mnrnd" not in source


def test_scenario_b_canary_artifact_honestly_records_missing_statistics_toolbox():
    """The already-executed canary artifact must keep recording the real,
    honest toolbox-availability gap -- not a laundered/assumed-available
    value."""
    canary_path = (
        REPO_ROOT
        / "docs"
        / "phase_f"
        / "l2_2_design_a"
        / "h12"
        / "perturbation"
        / f"{PROCESS}_h12_scenario_b_perturbation_canary.json"
    )
    payload = json.loads(canary_path.read_text(encoding="utf-8"))
    manifest = payload["states"]["transferase_capacity_scarce"]["run_manifest"]
    assert manifest["statistics_toolbox_installed"] is False
    assert payload["states"]["transferase_capacity_scarce"]["n_seeds"] == 20
    # This canary is stochasticRound-only evidence and must never be
    # relabeled/counted as N=50 catalog-domain evidence.
    assert payload["states"]["transferase_capacity_scarce"]["n_seeds"] != h12.CATALOG_N_M[PROCESS][0]
    assert payload["gating"].startswith("NON_GATING")


def test_scenario_a_perturbation_artifact_stays_non_gating_pending_reviewer_decision():
    """Scenario A (the RNG-invariant, already-`H12_PERTURBATION_CONFIRMED`
    evidence that actually targets the missing `transferase_fires` branch
    tag) must remain explicitly NON_GATING -- folding it into the primary
    artifact requires the separately-authorized CONDITION_GATED taxonomy
    decision, not a routine fix."""
    scenario_a_path = (
        REPO_ROOT
        / "docs"
        / "phase_f"
        / "l2_2_design_a"
        / "h12"
        / "perturbation"
        / f"{PROCESS}_h12_perturbation.json"
    )
    payload = json.loads(scenario_a_path.read_text(encoding="utf-8"))
    assert payload["gating"].startswith("NON_GATING")
    assert payload["verdict"] == "H12_PERTURBATION_CONFIRMED"
    assert payload["target_branch"] == "transferase_fires"


def test_condition_gated_taxonomy_proposal_still_not_implemented():
    """Guards against silent enactment: the CONDITION_GATED taxonomy
    remains PROPOSAL ONLY until a separately-authorized commit says
    otherwise. If this ever flips, `verdict.py`'s gate and this
    determination must be revisited together."""
    proposal_path = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "CONDITION_GATED_TAXONOMY_PROPOSAL.md"
    source = proposal_path.read_text(encoding="utf-8")
    assert "PROPOSAL ONLY" in source
    assert "NOT IMPLEMENTED ON THIS BRANCH" in source


def test_verdict_module_still_only_accepts_literal_h12_confirmed():
    """`_has_valid_h12_support`'s acceptance gate must still hard-require
    the literal string 'H12_CONFIRMED' -- no CONDITION_GATED/OBSERVED_REGIME
    synonym has been silently added to the accepted set."""
    verdict_path = REPO_ROOT / "scripts" / "l22_evidence" / "verdict.py"
    source = verdict_path.read_text(encoding="utf-8")
    assert '"H12_CONFIRMED"' in source
    h12_source = H12_PERTURBATION_SOURCE.parent / "h12.py"
    assert 'return "H12_CONFIRMED"' in h12_source.read_text(encoding="utf-8")
