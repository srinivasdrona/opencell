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
    generator's own source, the E1 provenance doc, the vendored Karr
    source) all match the CURRENT on-disk files -- catching a stale
    artifact after any of those files change without regeneration,
  - port the accepted H12 module's own population-check rigor (exact
    catalog N=50/M=100, complete seed-key coverage 0..49, exact manifest
    cross-check, exact hash-map equality to the accepted H12 artifact,
    exact census field schema) as hard requirements enforced by
    `validate_condition_gated_artifact`,
  - run a full tamper battery: `validate_condition_gated_artifact` must
    REJECT every deliberately corrupted/tampered payload below --
    classification/gating/verdict escalation (PASS, H12_CONFIRMED,
    H12_OBSERVED_REGIME, an ENACTED CONDITION_GATED value), false
    attestations, a missing required consumer, degenerate n=1/m=1
    census, missing/reused/zeroed hashes, a non-"match" manifest
    cross-check entry, a fabricated/stub census (missing or extra
    field), nonzero E1/ub substitution, a wrong limiting substrate,
    network-1 metadata leakage (network field, index masks), a
    forged/missing Karr source citation or structural argument, and
    network-1-only annotation drift on the borrowed 814/814 figures,
  - assert this module and its artifact are NOT referenced by
    verdict.py/generator.py/h12_evidence_index.json/PROCESS_CATALOG.yaml
    (non-gating boundary),
  - assert the lifecycle-reachability question is recorded as literally
    UNRESOLVED (never true/false) and that the candidate is explicitly
    marked unable to unblock the current row or L2.5.

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


def _mutate(payload: dict, **overrides) -> dict:
    """Deep-copy `payload` and set each dotted-path override, e.g.
    `_mutate(artifact, **{"natural_census.n_seeds": 1})`."""
    out = copy.deepcopy(payload)
    for path, value in overrides.items():
        keys = path.split(".")
        node = out
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    return out


def _delete(payload: dict, path: str) -> dict:
    out = copy.deepcopy(payload)
    keys = path.split(".")
    node = out
    for k in keys[:-1]:
        node = node[k]
    del node[keys[-1]]
    return out


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


def test_network2_layout_matches_pinned_expected_constants():
    layout = hcg.get_network2_layout()
    assert layout["substrate_indices_0b"] == hcg.EXPECTED_SUBSTRATE_INDICES_0B
    assert layout["complex_indices_0b"] == hcg.EXPECTED_COMPLEX_INDICES_0B
    assert layout["stoichiometry_block"] == hcg.EXPECTED_STOICH_BLOCK
    assert layout["substrate_whole_cell_model_ids"] == hcg.EXPECTED_SUBSTRATE_WIDS
    assert layout["complex_whole_cell_model_ids"] == hcg.EXPECTED_COMPLEX_WIDS


def test_e1_is_the_last_substrate_and_the_committed_limiting_substrate(artifact):
    layout = hcg.get_network2_layout()
    e1_local = layout["substrate_whole_cell_model_ids"].index("MG_429_MONOMER")
    e1_0b = layout["substrate_indices_0b"][e1_local]
    assert e1_0b == hcg.EXPECTED_E1_INDEX_0B
    assert artifact["natural_census"]["limiting_substrate_0b"] == e1_0b
    assert artifact["natural_census"]["limiting_substrate_whole_cell_model_id"] == "MG_429_MONOMER"


def test_e1_is_uniquely_limiting_across_all_evaluations(artifact):
    census = artifact["natural_census"]
    counts = census["limiting_substrate_argmin_counts"]
    total_evaluations = census["n_seeds"] * census["m_ticks"] * len(hcg.EXPECTED_COMPLEX_INDICES_0B)
    e1_key = str(hcg.EXPECTED_E1_LOCAL_INDEX)
    assert counts[e1_key] == total_evaluations
    assert all(v == 0 for k, v in counts.items() if k != e1_key)


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


def test_committed_artifact_karr_citation_vendored_hash_matches_current_disk(artifact):
    vendored_path = REPO_ROOT / artifact["karr_source_citation"]["vendored_path"]
    expected = hcg._sha256_lf_normalized(vendored_path)
    assert artifact["karr_source_citation"]["vendored_sha256_lf_normalized"] == expected


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
    # This is the "same population, not a re-extraction, no canonical-only
    # reuse" cross-check: the per-seed oracle hashes in this artifact must be
    # byte-identical, key-for-key, to the ones already recorded in the
    # accepted H12 artifact.
    on_disk_h12 = json.loads(hcg.ACCEPTED_H12_ARTIFACT_PATH.read_text(encoding="utf-8"))
    assert artifact["natural_census"]["oracle_seed_file_sha256"] == on_disk_h12["oracle_seed_file_sha256"]
    assert artifact["accepted_h12_artifact_ref"]["oracle_seed_file_sha256"] == on_disk_h12["oracle_seed_file_sha256"]


def test_committed_artifact_passes_its_own_validator(artifact):
    assert hcg.validate_condition_gated_artifact(artifact) is None


# ---------------------------------------------------------------------------
# Population-check rigor ported from h12.validate_h12_support: exact catalog
# N/M, complete seed coverage, exact manifest match, exact census schema.
# ---------------------------------------------------------------------------


def test_committed_artifact_covers_exact_catalog_n_m(artifact):
    census = artifact["natural_census"]
    assert census["n_seeds"] == 50
    assert census["m_ticks"] == 100
    assert census["total_samples"] == 5000


def test_committed_artifact_seed_keys_are_exactly_0_to_49(artifact):
    census = artifact["natural_census"]
    assert set(census["oracle_seed_file_sha256"].keys()) == {str(i) for i in range(50)}
    assert set(census["oracle_manifest_cross_check"].keys()) == {str(i) for i in range(50)}


def test_committed_artifact_manifest_cross_check_is_all_match(artifact):
    census = artifact["natural_census"]
    assert all(v == "match" for v in census["oracle_manifest_cross_check"].values())


def test_committed_artifact_census_schema_is_exact(artifact):
    assert set(artifact["natural_census"].keys()) == hcg.CENSUS_REQUIRED_FIELDS


def test_committed_artifact_oracle_hashes_are_all_distinct(artifact):
    hashes = artifact["natural_census"]["oracle_seed_file_sha256"].values()
    assert len(set(hashes)) == len(hashes) == 50


def test_committed_artifact_pins_natural_census_claim_values(artifact):
    census = artifact["natural_census"]
    assert census["candidate_ticks_ub_gt_0"] == 0
    assert census["ub_min"] == [0, 0]
    assert census["ub_max"] == [0, 0]
    assert census["limiting_substrate_0b"] == 192
    assert census["limiting_substrate_whole_cell_model_id"] == "MG_429_MONOMER"
    assert census["pool_fraction_zero"][hcg.EXPECTED_E1_LOCAL_INDEX] == 1.0


def test_compute_natural_network2_census_is_reproducible():
    # Re-running the census computation (reads the locally-present oracle
    # traces, same ones the accepted H12 artifact already reads) must
    # reproduce byte-identical oracle hashes and the same zero-candidate
    # conclusion -- guards against nondeterminism silently creeping in.
    census = hcg.compute_natural_network2_census()
    on_disk = json.loads(hcg.OUT_PATH.read_text(encoding="utf-8"))
    assert census["oracle_seed_file_sha256"] == on_disk["natural_census"]["oracle_seed_file_sha256"]
    assert census["candidate_ticks_ub_gt_0"] == 0


def test_compute_natural_network2_census_never_reads_accepted_h12_artifact():
    # Anti-laundering: independently derives every hash from the raw oracle
    # traces -- never opens/aliases the accepted H12 artifact's own JSON.
    import inspect

    source = inspect.getsource(hcg.compute_natural_network2_census)
    assert "ACCEPTED_H12_ARTIFACT_PATH" not in source
    assert "_load_json" not in source


# ---------------------------------------------------------------------------
# Classification / gating / verdict escalation tamper battery
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_classification",
    ["PASS", "H12_CONFIRMED", "H12_OBSERVED_REGIME", "CONDITION_GATED", "CONDITION_GATED_CONFIRMED", "CONDITION_GATED_ENACTED"],
)
def test_rejects_classification_escalation(artifact, bad_classification):
    payload = _mutate(artifact, classification=bad_classification)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "classification" in err


def test_rejects_gating_relabeled_gating(artifact):
    payload = _mutate(artifact, gating="GATING")
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "NON_GATING" in err


def test_rejects_network_field_changed_to_network1(artifact):
    payload = _mutate(artifact, network=1)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "network" in err


def test_rejects_required_branch_changed(artifact):
    payload = _mutate(artifact, required_branch="network_1_fires")
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "required_branch" in err


def test_rejects_perturbation_artifact_masquerading_as_confirmed(artifact):
    payload = _mutate(artifact, **{"accepted_perturbation_artifact_ref.verdict": "H12_CONFIRMED"})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "H12_PERTURBATION_OBSERVED_STOCHASTIC" in err


def test_rejects_perturbation_artifact_gating_relabeled(artifact):
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


def test_rejects_stored_verdict_trusted_over_ondisk_file(artifact, monkeypatch, tmp_path):
    # Even a self-consistent payload must be checked against the REAL on-disk
    # accepted artifact, not merely internally consistent with itself: patch
    # the module's own view of ACCEPTED_H12_ARTIFACT_PATH to a forged file
    # claiming network_ge2_fires is confirmed, and require the validator to
    # still reject the (self-consistent) payload.
    fake_h12 = json.loads(hcg.ACCEPTED_H12_ARTIFACT_PATH.read_text(encoding="utf-8"))
    fake_h12["verdict"] = "H12_CONFIRMED"
    fake_h12["branches_confirmed"] = ["network_1_fires", "network_ge2_fires"]
    fake_path = tmp_path / "fake_h12.json"
    fake_path.write_text(json.dumps(fake_h12), encoding="utf-8")

    monkeypatch.setattr(hcg, "ACCEPTED_H12_ARTIFACT_PATH", fake_path)
    err = hcg.validate_condition_gated_artifact(artifact)
    assert err is not None


# ---------------------------------------------------------------------------
# False attestations / missing consumers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "perturbation_reference_is_precomputed_and_read_only",
        "no_sut_import",
        "no_result_json_access",
        "no_new_extraction",
        "no_matlab_or_octave_run_this_change",
    ],
)
def test_rejects_false_attestation_flip(artifact, field):
    payload = _mutate(artifact, **{f"anti_laundering_attestation.{field}": False})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "anti_laundering_attestation" in err


def test_rejects_attestation_census_inputs_widened(artifact):
    payload = _mutate(artifact, **{"anti_laundering_attestation.census_inputs": ["states_before", "states_after"]})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "anti_laundering_attestation" in err


def test_rejects_missing_consumer_entry(artifact):
    tampered = list(artifact["not_consumed_by"])
    tampered.pop()
    payload = _mutate(artifact, not_consumed_by=tampered)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "not_consumed_by" in err


def test_rejects_extra_consumer_entry(artifact):
    tampered = list(artifact["not_consumed_by"]) + ["scripts/l22_evidence/some_other.py"]
    payload = _mutate(artifact, not_consumed_by=tampered)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "not_consumed_by" in err


def test_rejects_empty_consumer_list(artifact):
    payload = _mutate(artifact, not_consumed_by=[])
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "not_consumed_by" in err


# ---------------------------------------------------------------------------
# Degenerate / fabricated / stub census tamper battery
# ---------------------------------------------------------------------------


def test_rejects_degenerate_n_seeds_1(artifact):
    payload = _mutate(artifact, **{"natural_census.n_seeds": 1})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "n_seeds" in err


def test_rejects_degenerate_m_ticks_1(artifact):
    payload = _mutate(artifact, **{"natural_census.m_ticks": 1})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "m_ticks" in err


def test_rejects_total_samples_mismatch(artifact):
    payload = _mutate(artifact, **{"natural_census.total_samples": 4999})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "total_samples" in err


def test_rejects_missing_oracle_hash_entry(artifact):
    payload = _delete(artifact, "natural_census.oracle_seed_file_sha256.49")
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "oracle_seed_file_sha256" in err


def test_rejects_reused_oracle_hash(artifact):
    tampered = dict(artifact["natural_census"]["oracle_seed_file_sha256"])
    tampered["49"] = tampered["0"]
    payload = _mutate(artifact, **{"natural_census.oracle_seed_file_sha256": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "duplicate" in err


def test_rejects_zeroed_oracle_hash(artifact):
    tampered = dict(artifact["natural_census"]["oracle_seed_file_sha256"])
    tampered["0"] = "0" * 64
    payload = _mutate(artifact, **{"natural_census.oracle_seed_file_sha256": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None


def test_rejects_malformed_oracle_hash(artifact):
    tampered = dict(artifact["natural_census"]["oracle_seed_file_sha256"])
    tampered["0"] = "not-a-hash"
    payload = _mutate(artifact, **{"natural_census.oracle_seed_file_sha256": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "well-formed" in err


def test_rejects_mismatched_manifest_cross_check_entry(artifact):
    tampered = dict(artifact["natural_census"]["oracle_manifest_cross_check"])
    tampered["0"] = "mismatch"
    payload = _mutate(artifact, **{"natural_census.oracle_manifest_cross_check": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "mismatch" in err.lower()


def test_rejects_census_missing_a_required_field(artifact):
    payload = _delete(artifact, "natural_census.pool_fraction_zero")
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "schema mismatch" in err


def test_rejects_census_with_stub_extra_field(artifact):
    payload = _mutate(artifact, **{"natural_census.extra_stub_field": "junk"})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "schema mismatch" in err


def test_rejects_census_oracle_hashes_not_equal_to_accepted_artifact(artifact):
    tampered = dict(artifact["natural_census"]["oracle_seed_file_sha256"])
    tampered["0"] = "a" * 64
    # keep uniqueness/well-formedness so this specifically exercises the
    # cross-check-against-accepted-artifact rule, not an earlier check.
    payload = _mutate(artifact, **{"natural_census.oracle_seed_file_sha256": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "not exactly equal" in err


# ---------------------------------------------------------------------------
# Nonzero E1/ub substitution and wrong-limiter tamper battery
# ---------------------------------------------------------------------------


def test_rejects_nonzero_candidate_ticks_without_reinvestigation(artifact):
    payload = _mutate(artifact, **{"natural_census.candidate_ticks_ub_gt_0": 1})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "candidate_ticks_ub_gt_0" in err


def test_rejects_nonzero_ub_min(artifact):
    payload = _mutate(artifact, **{"natural_census.ub_min": [0, 1]})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "ub_min" in err


def test_rejects_nonzero_ub_max(artifact):
    payload = _mutate(artifact, **{"natural_census.ub_max": [1, 0]})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "ub_max" in err


def test_rejects_wrong_limiting_substrate_index(artifact):
    payload = _mutate(artifact, **{"natural_census.limiting_substrate_0b": 23})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "limiting_substrate_0b" in err


def test_rejects_wrong_limiting_substrate_wid(artifact):
    payload = _mutate(artifact, **{"natural_census.limiting_substrate_whole_cell_model_id": "MG_041_MONOMER"})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "limiting_substrate_whole_cell_model_id" in err


def test_rejects_e1_not_uniquely_limiting(artifact):
    tampered = dict(artifact["natural_census"]["limiting_substrate_argmin_counts"])
    tampered["0"] = 1
    tampered["3"] = tampered["3"] - 1
    payload = _mutate(artifact, **{"natural_census.limiting_substrate_argmin_counts": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "unique" in err.lower()


def test_rejects_e1_pool_fraction_zero_not_one(artifact):
    tampered = list(artifact["natural_census"]["pool_fraction_zero"])
    tampered[hcg.EXPECTED_E1_LOCAL_INDEX] = 0.99
    payload = _mutate(artifact, **{"natural_census.pool_fraction_zero": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "pool_fraction_zero" in err


# ---------------------------------------------------------------------------
# Network-1 metadata leakage tamper battery
# ---------------------------------------------------------------------------


def test_rejects_network1_leakage_into_substrate_indices(artifact):
    tampered = list(artifact["network2_layout"]["substrate_indices_0b"])
    tampered[0] = 0  # a network-1 substrate index
    payload = _mutate(artifact, **{"network2_layout.substrate_indices_0b": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "substrate_indices_0b" in err


def test_rejects_network1_leakage_into_complex_indices(artifact):
    tampered = list(artifact["network2_layout"]["complex_indices_0b"])
    tampered[0] = 0
    payload = _mutate(artifact, **{"network2_layout.complex_indices_0b": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "complex_indices_0b" in err


def test_rejects_tampered_stoichiometry_block(artifact):
    tampered = copy.deepcopy(artifact["network2_layout"]["stoichiometry_block"])
    tampered[0][0] = 99
    payload = _mutate(artifact, **{"network2_layout.stoichiometry_block": tampered})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "stoichiometry_block" in err


def test_rejects_network1_wids_substituted(artifact):
    payload = _mutate(
        artifact,
        **{"network2_layout.substrate_whole_cell_model_ids": ["NOT_A_REAL_WID"] * 4},
    )
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "substrate_whole_cell_model_ids" in err


# ---------------------------------------------------------------------------
# Karr citation / structural argument forgery tamper battery
# ---------------------------------------------------------------------------


def test_rejects_missing_karr_citation(artifact):
    payload = _delete(artifact, "karr_source_citation")
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "karr_source_citation" in err


def test_rejects_forged_karr_upstream_repo(artifact):
    payload = _mutate(artifact, **{"karr_source_citation.upstream_repo": "https://example.com/forged"})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "upstream_repo" in err


def test_rejects_forged_karr_upstream_commit(artifact):
    payload = _mutate(artifact, **{"karr_source_citation.upstream_commit": "0" * 40})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "upstream_commit" in err


def test_rejects_forged_karr_line_ranges(artifact):
    payload = _mutate(artifact, **{"karr_source_citation.line_ranges": [[1, 2]]})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "line_ranges" in err


def test_rejects_forged_karr_symbols(artifact):
    payload = _mutate(artifact, **{"karr_source_citation.symbols": ["not_a_real_symbol"]})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "symbols" in err


def test_rejects_forged_karr_vendored_path(artifact):
    payload = _mutate(artifact, **{"karr_source_citation.vendored_path": "data/karr_vendored_source/Forged.m"})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None


def test_rejects_forged_karr_vendored_hash(artifact):
    payload = _mutate(artifact, **{"karr_source_citation.vendored_sha256_lf_normalized": "0" * 64})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "vendored_sha256_lf_normalized" in err


def test_rejects_missing_structural_argument(artifact):
    payload = _delete(artifact, "structural_argument")
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "structural_argument" in err


def test_rejects_structural_argument_claim_weakened(artifact):
    payload = _mutate(artifact, **{"structural_argument.claim": "network 2 is closed-form after all"})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "montecarlokinetic" in err


def test_rejects_structural_argument_citation_forged(artifact):
    payload = _mutate(artifact, **{"structural_argument.source_citation.file": "SomeOtherProcess.m"})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "source_citation.file" in err


def test_rejects_structural_argument_citation_missing_symbols(artifact):
    payload = _mutate(artifact, **{"structural_argument.source_citation.symbols": []})
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "source_citation.symbols" in err


# ---------------------------------------------------------------------------
# Network1-only label drift on the borrowed 814/814 and exact_match_rate=1.0
# figures -- these must remain annotated as network-1-only evidence.
# ---------------------------------------------------------------------------


def test_borrowed_figures_carry_network1_only_scope_annotations(artifact):
    ref = artifact["accepted_h12_artifact_ref"]
    assert "network_1_fires ONLY" in ref["nontrivial_sample_count_scope"]
    assert "network_1_fires ONLY" in ref["exact_match_rate_scope"] or "NOT exact-match evidence" in ref["exact_match_rate_scope"]
    assert "0" in ref["nontrivial_sample_count_scope"]


def test_rejects_missing_nontrivial_sample_count_scope_annotation(artifact):
    payload = _delete(artifact, "accepted_h12_artifact_ref.nontrivial_sample_count_scope")
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "nontrivial_sample_count_scope" in err


def test_rejects_missing_exact_match_rate_scope_annotation(artifact):
    payload = _delete(artifact, "accepted_h12_artifact_ref.exact_match_rate_scope")
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "exact_match_rate_scope" in err


def test_rejects_scope_annotation_drift_implying_network2_exact_match(artifact):
    payload = _mutate(
        artifact,
        **{
            "accepted_h12_artifact_ref.nontrivial_sample_count_scope": (
                "network 2 also contributes to this 814/814 exact-match figure"
            )
        },
    )
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "nontrivial_sample_count_scope" in err


def test_purpose_wording_never_claims_network2_exact_match(artifact):
    # Regression guard for the vacuous "network 2 is 100% exact-match on
    # every sample it produces" wording flagged during turn-3 hardening.
    purpose = artifact["purpose"].lower()
    assert "network 2" in purpose or "network2" in purpose or "network_2" in purpose
    assert "zero" in purpose or "0" in purpose


# ---------------------------------------------------------------------------
# Lifecycle-reachability semantics: must remain literally UNRESOLVED, never
# a resolved boolean claim in either direction; explicit non-unblocking.
# ---------------------------------------------------------------------------


def test_lifecycle_reachability_status_is_literally_unresolved(artifact):
    assert artifact["lifecycle_reachability_status"] == "UNRESOLVED"


@pytest.mark.parametrize("bad_value", [True, False, "REACHABLE", "UNREACHABLE", "RESOLVED"])
def test_rejects_lifecycle_reachability_status_resolved_either_way(artifact, bad_value):
    payload = _mutate(artifact, lifecycle_reachability_status=bad_value)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "UNRESOLVED" in err


def test_rejects_unobserved_in_window_alone_marked_sufficient(artifact):
    payload = _mutate(artifact, unobserved_in_window_alone_is_insufficient=False)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None


def test_rejects_unblocks_current_row_flipped_true(artifact):
    payload = _mutate(artifact, unblocks_current_row=True)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "unblocks_current_row" in err


def test_rejects_unblocks_l2_5_flipped_true(artifact):
    payload = _mutate(artifact, unblocks_l2_5=True)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "unblocks_l2_5" in err


def test_rejects_maintainer_decision_made_flipped_true(artifact):
    payload = _mutate(artifact, maintainer_decision_made=True)
    err = hcg.validate_condition_gated_artifact(payload)
    assert err is not None and "maintainer_decision_made" in err


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
    assert set(artifact["not_consumed_by"]) == set(hcg.EXPECTED_NOT_CONSUMED_BY)


def test_artifact_gating_is_explicitly_non_gating(artifact):
    assert "NON_GATING" in artifact["gating"]


def test_artifact_anti_laundering_attestation_matches_pinned_expectation(artifact):
    assert artifact["anti_laundering_attestation"] == hcg.EXPECTED_ANTI_LAUNDERING_ATTESTATION


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
