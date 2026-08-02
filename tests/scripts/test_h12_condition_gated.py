"""Tests for scripts/l22_evidence/h12_condition_gated.py -- the NON-GATING
CONDITION_GATED_CANDIDATE evidence module for
MacromolecularComplexation/network_ge2_fires.

This module's committed artifact
(docs/phase_f/l2_2_design_a/h12/condition_gated/
MacromolecularComplexation_h12_condition_gated.json) mechanically binds
three already-accepted evidence sources into one proposal. These tests:

  - rederive the network-2 layout (indices/stoichiometry) directly from
    the tracked fixture and assert it matches both the predictor's own
    filtering AND the committed artifact -- catching fixture drift,
    hand-edited constants/stoichiometry, or a changed index mask,
  - assert the committed artifact's referenced hashes (fixture, the two
    accepted H12/perturbation artifacts, the predictor source, the
    generator's own source, the E1 provenance doc) all match the CURRENT
    on-disk files -- catching a stale artifact after any of those files
    change without regeneration,
  - assert `validate_condition_gated_artifact` fails (does not silently
    trust) a battery of deliberately corrupted/tampered payloads: stale
    hashes, network-1-leakage-flavored claims, altered index masks,
    stored-verdict trust without rederivation, and any attempt to treat
    the non-gating perturbation artifact as a natural-regime PASS or
    H12_CONFIRMED,
  - assert this module and its artifact are NOT referenced by
    verdict.py/generator.py/h12_evidence_index.json/PROCESS_CATALOG.yaml
    (non-gating boundary), and that its classification vocabulary never
    overlaps H12_CONFIRMED-flavored verdicts,
  - assert the committed artifact's own natural_census is internally
    consistent with the pre-existing accepted H12 artifact's oracle
    hash map (same 50-seed population, not a different/re-extracted one).

Run via `bin\\oc-pytest tests/scripts/test_h12_condition_gated.py -v`.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import h12  # noqa: E402
from scripts.l22_evidence import h12_condition_gated as hcg  # noqa: E402

VERDICT_PATH = REPO_ROOT / "scripts" / "l22_evidence" / "verdict.py"
GENERATOR_PATH = REPO_ROOT / "scripts" / "l22_evidence" / "generator.py"
EVIDENCE_INDEX_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "h12_evidence_index.json"
PROCESS_CATALOG_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "PROCESS_CATALOG.yaml"


@pytest.fixture(scope="module")
def artifact() -> dict:
    with open(hcg.OUT_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Layout rederivation (fixture drift / hand-edited constants / index masks)
# ---------------------------------------------------------------------------


def test_artifact_exists_and_is_committed():
    assert hcg.OUT_PATH.is_file(), f"missing committed artifact: {hcg.OUT_PATH}"


def test_network2_layout_matches_pre_registered_perturbation_constants():
    # Cross-checks against the OTHER already-accepted module's independently
    # hardcoded constants (h12_perturbation.MACROMOL_NETWORK2) -- two
    # independently-written sources must agree, not just self-consistency.
    from scripts.l22_evidence import h12_perturbation as hp

    layout = hcg.get_network2_layout()
    assert layout["substrate_indices_0b"] == hp.MACROMOL_NETWORK2["substrate_indices_0b"]
    assert layout["complex_indices_0b"] == hp.MACROMOL_NETWORK2["complex_indices_0b"]
    assert layout["stoichiometry_block"] == hp.MACROMOL_NETWORK2["stoichiometry_block"]


def test_network2_layout_whole_cell_model_ids_match_expected_biology():
    layout = hcg.get_network2_layout()
    assert layout["substrate_whole_cell_model_ids"] == [
        "MG_041_MONOMER",
        "MG_062_MONOMER",
        "MG_069_MONOMER",
        "MG_429_MONOMER",
    ]
    assert layout["complex_whole_cell_model_ids"] == [
        "MG_041_062_429_PENTAMER",
        "MG_041_069_429_PENTAMER",
    ]


def test_e1_is_the_last_substrate_and_the_committed_limiting_substrate(artifact):
    layout = hcg.get_network2_layout()
    e1_local = layout["substrate_whole_cell_model_ids"].index("MG_429_MONOMER")
    e1_0b = layout["substrate_indices_0b"][e1_local]
    assert artifact["natural_census"]["limiting_substrate_0b"] == e1_0b
    assert artifact["natural_census"]["limiting_substrate_whole_cell_model_id"] == "MG_429_MONOMER"


# ---------------------------------------------------------------------------
# Hash freshness (stale-artifact detection against CURRENT on-disk files)
# ---------------------------------------------------------------------------


def test_committed_artifact_fixture_hash_matches_current_fixture(artifact):
    fixture = h12.load_fixture(hcg.PROCESS)
    assert artifact["fixture_sha256"] == fixture["__fixture_sha256__"]
    assert artifact["fixture_path"] == fixture["__fixture_path__"]


def test_committed_artifact_predictor_hash_matches_current_h12py(artifact):
    expected = hcg._sha256_lf_normalized(REPO_ROOT / h12.EXPECTED_PREDICTOR_SOURCE_PATH)
    assert artifact["predictor_source_sha256_lf_normalized"] == expected


def test_committed_artifact_generator_hash_matches_current_generator_source(artifact):
    expected = hcg._sha256_lf_normalized(hcg._THIS_FILE)
    assert artifact["generator_source_sha256_lf_normalized"] == expected


def test_committed_artifact_e1_provenance_doc_hash_matches_current_doc(artifact):
    expected = hcg._sha256_lf_normalized(hcg.E1_PROVENANCE_DOC_PATH)
    assert artifact["e1_provenance_ref_sha256_lf_normalized"] == expected


def test_committed_artifact_references_accepted_h12_artifact_by_current_hash(artifact):
    ref = artifact["accepted_h12_artifact_ref"]
    on_disk = hcg._sha256_lf_normalized(hcg.ACCEPTED_H12_ARTIFACT_PATH)
    assert ref["sha256_lf_normalized"] == on_disk
    assert ref["verdict"] == "H12_OBSERVED_REGIME"
    assert "network_ge2_fires" not in ref["branches_confirmed"]
    assert "network_ge2_fires" in ref["missing_required_branches"]


def test_committed_artifact_references_accepted_perturbation_artifact_by_current_hash(artifact):
    ref = artifact["accepted_perturbation_artifact_ref"]
    on_disk = hcg._sha256_lf_normalized(hcg.ACCEPTED_PERTURBATION_ARTIFACT_PATH)
    assert ref["sha256_lf_normalized"] == on_disk
    assert ref["verdict"] == "H12_PERTURBATION_OBSERVED_STOCHASTIC"
    assert ref["target_branch_exercised"] is True


def test_committed_artifact_oracle_hashes_identical_to_accepted_h12_artifact(artifact):
    # This is the "same population, not a re-extraction" cross-check: the
    # per-seed oracle hashes in this artifact must be byte-identical to the
    # ones already recorded in the accepted H12 artifact.
    on_disk_h12 = json.loads(hcg.ACCEPTED_H12_ARTIFACT_PATH.read_text(encoding="utf-8"))
    assert artifact["natural_census"]["oracle_seed_file_sha256"] == on_disk_h12["oracle_seed_file_sha256"]
    assert artifact["accepted_h12_artifact_ref"]["oracle_seed_file_sha256"] == on_disk_h12["oracle_seed_file_sha256"]


def test_committed_artifact_passes_its_own_validator(artifact):
    assert hcg.validate_condition_gated_artifact(artifact) is None


# ---------------------------------------------------------------------------
# Anti-tampering / anti-laundering: validate_condition_gated_artifact must
# REJECT each of these corrupted payloads, never silently trust them.
# ---------------------------------------------------------------------------


def _mutate(artifact: dict, **overrides) -> dict:
    payload = copy.deepcopy(artifact)
    for path, value in overrides.items():
        keys = path.split(".")
        node = payload
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    return payload


def test_rejects_stale_fixture_hash(artifact):
    payload = _mutate(artifact, fixture_sha256="0" * 64)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "fixture_sha256" in err


def test_rejects_tampered_stoichiometry_block(artifact):
    tampered = copy.deepcopy(artifact["network2_layout"]["stoichiometry_block"])
    tampered[0][0] = 99
    payload = _mutate(artifact, **{"network2_layout.stoichiometry_block": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "stoichiometry_block" in err


def test_rejects_altered_substrate_index_mask(artifact):
    tampered = list(artifact["network2_layout"]["substrate_indices_0b"])
    tampered[0] = 0  # network-1-leakage-flavored tamper: point at an unrelated index
    payload = _mutate(artifact, **{"network2_layout.substrate_indices_0b": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "substrate_indices_0b" in err


def test_rejects_altered_complex_index_mask(artifact):
    tampered = list(artifact["network2_layout"]["complex_indices_0b"])
    tampered[0] = 0
    payload = _mutate(artifact, **{"network2_layout.complex_indices_0b": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "complex_indices_0b" in err


def test_rejects_natural_regime_reachable_flipped_to_true(artifact):
    payload = _mutate(artifact, natural_regime_reachable=True)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None


def test_rejects_nonzero_candidate_ticks_without_reinvestigation(artifact):
    payload = _mutate(artifact, **{"natural_census.candidate_ticks_ub_gt_0": 1})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "candidate_ticks_ub_gt_0" in err


def test_rejects_perturbation_artifact_masquerading_as_confirmed(artifact):
    # Anti-laundering: this artifact must never let the perturbation
    # artifact's verdict be upgraded to a natural-regime PASS / H12_CONFIRMED.
    payload = _mutate(artifact, **{"accepted_perturbation_artifact_ref.verdict": "H12_CONFIRMED"})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "H12_PERTURBATION_OBSERVED_STOCHASTIC" in err


def test_rejects_perturbation_artifact_gating_relabeled_gating(artifact):
    payload = _mutate(artifact, **{"accepted_perturbation_artifact_ref.gating": "GATING"})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "NON_GATING" in err


def test_rejects_h12_artifact_verdict_upgraded_without_rederivation(artifact):
    # Stored-verdict-trust guard: even if the payload CLAIMS
    # branches_confirmed now includes network_ge2_fires, the validator must
    # re-read the actual on-disk accepted artifact and catch the mismatch --
    # not trust the payload's own copy of the referenced verdict.
    payload = _mutate(
        artifact,
        **{
            "accepted_h12_artifact_ref.verdict": "H12_CONFIRMED",
            "accepted_h12_artifact_ref.branches_confirmed": ["network_1_fires", "network_ge2_fires"],
        },
    )
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None


def test_rejects_classification_upgraded_to_confirmed_flavored(artifact):
    payload = _mutate(artifact, classification="H12_CONFIRMED")
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "CONFIRMED" in err

    payload2 = _mutate(artifact, classification="CONDITION_GATED_CONFIRMED")
    err2 = hcg.validate_condition_gated_artifact(payload2)
    assert err2 is not None and "CONFIRMED" in err2


def test_rejects_missing_referenced_h12_artifact_path(artifact):
    payload = _mutate(artifact, **{"accepted_h12_artifact_ref.path": "does/not/exist.json"})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "does not exist" in err


def test_rejects_stale_generator_source_hash(artifact):
    payload = _mutate(artifact, generator_source_sha256_lf_normalized="0" * 64)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "generator_source" in err


def test_rejects_stale_predictor_source_hash(artifact):
    payload = _mutate(artifact, predictor_source_sha256_lf_normalized="0" * 64)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "predictor_source" in err


def test_rejects_stale_e1_provenance_hash(artifact):
    payload = _mutate(artifact, e1_provenance_ref_sha256_lf_normalized="0" * 64)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "e1_provenance_ref" in err


def test_rejects_wrong_artifact_kind(artifact):
    payload = _mutate(artifact, artifact_kind="something_else")
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "artifact_kind" in err


def test_rejects_wrong_process(artifact):
    payload = _mutate(artifact, process="SomeOtherProcess")
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "process" in err


# ---------------------------------------------------------------------------
# Non-gating boundary: this module/artifact must not be wired into the
# central verdict/generator/catalog machinery on this branch.
# ---------------------------------------------------------------------------


def test_verdict_module_never_references_condition_gated():
    source = VERDICT_PATH.read_text(encoding="utf-8")
    assert "h12_condition_gated" not in source
    assert "CONDITION_GATED" not in source


def test_generator_module_never_references_condition_gated():
    source = GENERATOR_PATH.read_text(encoding="utf-8")
    assert "h12_condition_gated" not in source
    assert "CONDITION_GATED" not in source


def test_evidence_index_never_references_condition_gated():
    if not EVIDENCE_INDEX_PATH.is_file():
        pytest.skip("h12_evidence_index.json not present")
    source = EVIDENCE_INDEX_PATH.read_text(encoding="utf-8")
    assert "h12_condition_gated" not in source
    assert "CONDITION_GATED" not in source


def test_process_catalog_never_references_condition_gated():
    if not PROCESS_CATALOG_PATH.is_file():
        pytest.skip("PROCESS_CATALOG.yaml not present")
    source = PROCESS_CATALOG_PATH.read_text(encoding="utf-8")
    assert "CONDITION_GATED" not in source


def test_artifact_classification_is_candidate_not_enacted(artifact):
    assert artifact["classification"] == "CONDITION_GATED_CANDIDATE"
    assert "H12_CONFIRMED" not in artifact["classification"]
    assert set(artifact["not_consumed_by"]) == {
        "scripts/l22_evidence/verdict.py",
        "scripts/l22_evidence/generator.py",
        "docs/phase_f/l2_2_design_a/h12/h12_evidence_index.json",
        "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml",
    }


def test_artifact_gating_is_explicitly_non_gating(artifact):
    assert "NON_GATING" in artifact["gating"]


def test_artifact_anti_laundering_attestation_flags_no_execution(artifact):
    attest = artifact["anti_laundering_attestation"]
    assert attest["no_sut_import"] is True
    assert attest["no_result_json_access"] is True
    assert attest["no_new_extraction"] is True
    assert attest["no_matlab_or_octave_run_this_change"] is True


# ---------------------------------------------------------------------------
# Structural/Monte-Carlo argument (H12_CONFIRMED inapplicable regardless of
# natural-regime-reachability resolution)
# ---------------------------------------------------------------------------


def test_structural_argument_cites_montecarlokinetic(artifact):
    citation = artifact["structural_argument"]["source_citation"]
    assert "buildProteinComplexs_montecarlokinetic" in citation["symbols"]
    assert [334, 357] in citation["line_ranges"]


def test_natural_census_shows_e1_fixture_constant_zero(artifact):
    census = artifact["natural_census"]
    layout = artifact["network2_layout"]
    e1_local = layout["substrate_whole_cell_model_ids"].index("MG_429_MONOMER")
    assert census["pool_min"][e1_local] == 0.0
    assert census["pool_max"][e1_local] == 0.0
    assert census["pool_fraction_zero"][e1_local] == 1.0
    assert census["candidate_ticks_ub_gt_0"] == 0
    assert census["total_samples"] == census["n_seeds"] * census["m_ticks"]


def test_compute_natural_network2_census_is_reproducible():
    # Re-running the census computation (reads the locally-present oracle
    # traces, same ones the accepted H12 artifact already reads) must
    # reproduce byte-identical oracle hashes and the same zero-candidate
    # conclusion -- guards against nondeterminism silently creeping in.
    census = hcg.compute_natural_network2_census()
    on_disk = json.loads(hcg.OUT_PATH.read_text(encoding="utf-8"))
    assert census["oracle_seed_file_sha256"] == on_disk["natural_census"]["oracle_seed_file_sha256"]
    assert census["candidate_ticks_ub_gt_0"] == 0
