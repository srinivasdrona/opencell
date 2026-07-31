"""Tests for scripts/l22_evidence/h12_perturbation.py -- the SEPARATE,
NON-GATING perturbation-evidence pipeline that exercises the two H12
required branches (MacromolecularComplexation network_ge2_fires,
ProteinProcessingII transferase_fires) that never occur in the accepted
50-seed natural oracle trace.

Covers:
  - anti-laundering: no forbidden imports; state-construction (PREDICT
    phase) functions never touch Octave-produced "after" data; only the
    ingest/invariant-check (COMPARE phase) functions do,
  - pure-math unit tests (compute_macromol_network2_ub,
    evaluate_macromol_invariants) against hand-derived values and
    synthetic violating/clean data, with no file I/O and no Octave
    dependency (fresh-clone / no-Octave-installed safe),
  - a synthetic-CSV-based test of ingest_ppii_scenario_a's compare logic
    (both a matching and a deliberately mismatching case), via a
    monkeypatched RAW_DIR -- no live Octave invocation,
  - artifact-verdict-decision logic given constructed
    compare_result/invariant_result dicts,
  - a consistency check that the module's literal scenario constants
    match PERTURBATION_SPEC.json's documented derivation (guards against
    silent drift between the tracked spec and the executable constants),
  - a non-gating check that verdict.py/generator.py never reference this
    module or its artifact verdict vocabulary.

Note: the ProteinProcessingII "scarcity guard" branch (explicitly
descoped from Octave execution in PERTURBATION_SPEC.json's
`explicitly_out_of_scope_for_octave_execution`) is already covered by
the existing synthetic unit test
`test_protein_processing_ii_guard_fails_when_pg160_insufficient` in
tests/scripts/test_h12_formulas.py, which directly exercises
predict_protein_processing_ii's own regime_valid boundary arithmetic
with a hand-constructed insufficient-PG160 state. That test is not
duplicated here; it is the concrete artifact of the pre-registered
scoping decision.

Run via `bin\\oc-pytest tests/scripts/test_h12_perturbation.py -v`.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import h12_perturbation as hp  # noqa: E402

MODULE_PATH = REPO_ROOT / "scripts" / "l22_evidence" / "h12_perturbation.py"
VERDICT_PATH = REPO_ROOT / "scripts" / "l22_evidence" / "verdict.py"
GENERATOR_PATH = REPO_ROOT / "scripts" / "l22_evidence" / "generator.py"
TEST_FORMULAS_PATH = REPO_ROOT / "tests" / "scripts" / "test_h12_formulas.py"

FORBIDDEN_IMPORT_SUBSTRINGS = (
    "opencell.vivarium",
    "opencell.simulation",
    "runner_helpers",
    "_l2_2_design_a_runner_helpers",
    "karr_macromolecular_complexation",
    "karr_protein_folding",
    "karr_protein_processing_i",
    "karr_protein_processing_ii",
    "karr_trna_aminoacylation",
)

# Functions that must never reference Octave-produced "after" output --
# i.e. the PREDICT/bound-construction phase, analogous to h12.py's
# predict_* functions.
PREDICT_PHASE_FUNCTIONS = (
    "build_ppii_scenario_a_state",
    "build_macromol_network2_state",
    "generate_inputs",
)

# Functions that legitimately read Octave "after" output (COMPARE /
# invariant-check phase) -- these are the ONLY functions allowed to touch
# raw CSV / "after" data.
COMPARE_PHASE_FUNCTIONS = (
    "ingest_ppii_scenario_a",
    "check_macromol_invariants",
)

FORBIDDEN_TOKENS_IN_PREDICT_PHASE = {"after", "loadtxt", "np.loadtxt", "_after", "raw"}


def _module_ast() -> ast.Module:
    source = MODULE_PATH.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(MODULE_PATH))


def _all_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            yield mod
            for alias in node.names:
                yield f"{mod}.{alias.name}" if mod else alias.name


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name), None)
    assert fn is not None, f"{name} not found in h12_perturbation.py"
    return fn


def _names_used(fn: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


# ---------------------------------------------------------------------------
# Anti-laundering
# ---------------------------------------------------------------------------


def test_module_exists():
    assert MODULE_PATH.exists()


def test_no_forbidden_module_imports_anywhere():
    tree = _module_ast()
    imports = list(_all_imports(tree))
    for imp in imports:
        for forbidden in FORBIDDEN_IMPORT_SUBSTRINGS:
            assert forbidden not in imp, (
                f"h12_perturbation.py imports forbidden module/name {imp!r} "
                f"(matches forbidden substring {forbidden!r})"
            )


@pytest.mark.parametrize("fn_name", PREDICT_PHASE_FUNCTIONS)
def test_predict_phase_functions_never_touch_after_data(fn_name):
    tree = _module_ast()
    fn = _function_node(tree, fn_name)
    names = _names_used(fn)
    offending = names & FORBIDDEN_TOKENS_IN_PREDICT_PHASE
    assert not offending, (
        f"{fn_name} (a PREDICT/bound-construction-phase function) references "
        f"forbidden after-data token(s) {offending} -- must be before-only"
    )
    for node in ast.walk(fn):
        assert not (
            isinstance(node, ast.Attribute) and node.attr == "loadtxt"
        ), f"{fn_name} must never call loadtxt (reserved to COMPARE-phase functions)"


@pytest.mark.parametrize("fn_name", COMPARE_PHASE_FUNCTIONS)
def test_compare_phase_functions_are_the_ones_reading_raw_csv(fn_name):
    tree = _module_ast()
    fn = _function_node(tree, fn_name)
    found_loadtxt = any(
        isinstance(node, ast.Attribute) and node.attr == "loadtxt" for node in ast.walk(fn)
    )
    assert found_loadtxt, f"{fn_name} is expected to be the COMPARE-phase reader of Octave raw output"


def test_predict_phase_functions_have_no_local_imports():
    tree = _module_ast()
    for fn_name in PREDICT_PHASE_FUNCTIONS:
        fn = _function_node(tree, fn_name)
        for node in ast.walk(fn):
            assert not isinstance(node, (ast.Import, ast.ImportFrom)), (
                f"{fn_name} contains a local import -- forbidden for predict-phase functions"
            )


def test_module_docstring_states_two_phase_contract():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "ANTI-LAUNDERING CONTRACT" in source
    assert "PREDICT phase" in source
    assert "COMPARE" in source


# ---------------------------------------------------------------------------
# Pure-math unit tests (no file I/O, no Octave dependency)
# ---------------------------------------------------------------------------


def test_compute_macromol_network2_ub_matches_hand_derivation():
    # Pool/block taken verbatim from PERTURBATION_SPEC.json's
    # "resulting_ub_by_hand": ub[complex0]=17, ub[complex1]=15.
    pool = np.array([51.0, 34.0, 31.0, 40.0])
    block = np.array([[1, 1], [2, 0], [0, 2], [2, 2]], dtype=np.float64)
    ub = hp.compute_macromol_network2_ub(pool, block)
    assert ub.tolist() == [17, 15]


def test_compute_macromol_network2_ub_matches_module_constants():
    state = hp.build_macromol_network2_state()
    ub = hp.compute_macromol_network2_ub(state["pool"], state["block"])
    assert ub.tolist() == [17, 15]


def test_compute_macromol_network2_ub_handles_zero_pool_all_zero_ub():
    # Structural natural-trace regression case: if a required substrate is
    # 0, ratio=0/block=0 for any positive stoichiometry entry -> ub==0.
    pool = np.array([51.0, 34.0, 31.0, 0.0])
    block = np.array([[1, 1], [2, 0], [0, 2], [2, 2]], dtype=np.float64)
    ub = hp.compute_macromol_network2_ub(pool, block)
    assert ub.tolist() == [0, 0]


def test_evaluate_macromol_invariants_clean_varying_case():
    pool = np.array([51.0, 34.0, 31.0, 40.0])
    block = np.array([[1, 1], [2, 0], [0, 2], [2, 2]], dtype=np.float64)
    ub = np.array([17, 15])
    raw = np.array(
        [
            [12.0, 8.0],
            [9.0, 11.0],
            [11.0, 9.0],
        ]
    )
    result = hp.evaluate_macromol_invariants(pool, block, ub, raw)
    assert result["bound_violations"] == []
    assert result["mass_balance_violations"] == []
    assert result["seeds_vary"] is True
    assert result["distinct_outcome_count"] == 3


def test_evaluate_macromol_invariants_detects_bound_violation():
    pool = np.array([51.0, 34.0, 31.0, 40.0])
    block = np.array([[1, 1], [2, 0], [0, 2], [2, 2]], dtype=np.float64)
    ub = np.array([17, 15])
    raw = np.array([[18.0, 8.0]])  # 18 > ub[0]=17
    result = hp.evaluate_macromol_invariants(pool, block, ub, raw)
    assert len(result["bound_violations"]) == 1
    assert result["bound_violations"][0]["reason"] == "exceeds_ub"


def test_evaluate_macromol_invariants_detects_mass_balance_violation():
    pool = np.array([51.0, 34.0, 31.0, 40.0])
    block = np.array([[1, 1], [2, 0], [0, 2], [2, 2]], dtype=np.float64)
    ub = np.array([17, 15])
    # complex1 built=15 consumes 2*15=30 of substrate index2 (pool 31) --
    # fine -- but force an infeasible combination against substrate index3
    # (pool 40, block row [2,2]): built=[17,15] consumes 2*17+2*15=64 > 40.
    raw = np.array([[17.0, 15.0]])
    result = hp.evaluate_macromol_invariants(pool, block, ub, raw)
    assert len(result["mass_balance_violations"]) == 1


def test_evaluate_macromol_invariants_no_variation_flagged():
    pool = np.array([51.0, 34.0, 31.0, 40.0])
    block = np.array([[1, 1], [2, 0], [0, 2], [2, 2]], dtype=np.float64)
    ub = np.array([17, 15])
    raw = np.tile(np.array([[10.0, 10.0]]), (5, 1))
    result = hp.evaluate_macromol_invariants(pool, block, ub, raw)
    assert result["seeds_vary"] is False
    assert result["distinct_outcome_count"] == 1


# ---------------------------------------------------------------------------
# ingest_ppii_scenario_a with a synthetic CSV (no live Octave invocation)
# ---------------------------------------------------------------------------


def _ppii_synthetic_fixture() -> dict:
    return {
        "substrateIndexs_water_0b": 0,
        "substrateIndexs_PG160_0b": 1,
        "substrateIndexs_SNGLYP_0b": 2,
        "substrateIndexs_hydrogen_0b": 3,
        "enzymeIndexs_signalPeptidase_0b": 0,
        "enzymeIndexs_diacylglycerylTransferase_0b": 1,
        "lipoproteinSignalPeptidaseSpecificRate": 2.0,
        "lipoproteinDiacylglycerylTransferaseSpecificRate": 1.0,
        "stepSizeSec": 1.0,
        "unprocessedMonomerIndexs_0b": np.array([0]),
        "lipoproteinMonomerIndexs_0b": np.array([1]),
        "secretedMonomerIndexs_0b": np.array([2]),
    }


def _ppii_full_construction_fixture() -> dict:
    # For tests that exercise the REAL (unmocked) build_ppii_scenario_a_state,
    # which always writes 3 distinct passthrough indices -- needs a fixture
    # with 3 passthrough indices, unlike the smaller synthetic fixture above
    # (used only where build_ppii_scenario_a_state is monkeypatched away).
    fixture = _ppii_synthetic_fixture()
    fixture["unprocessedMonomerIndexs_0b"] = np.array([0, 4, 5])
    return fixture


def test_ingest_ppii_scenario_a_matching_csv_yields_full_exact_match(tmp_path, monkeypatch):
    fixture = _ppii_synthetic_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    monkeypatch.setattr(hp, "build_ppii_scenario_a_state", lambda f: {
        "unprocessedMonomers": np.array([2.0, 3.0, 4.0, 0.0]),
        "processedMonomers": np.zeros(4),
        "signalSequenceMonomers": np.zeros(4),
        "enzymes": np.array([10.0, 10.0]),
        "substrates": np.array([100.0, 100.0, 100.0, 100.0]),
    })
    monkeypatch.setattr(hp, "N_SEEDS", 2)
    # Hand-computed expected after-state for this before/fixture (peptidase
    # demand = unproc[lipoprotein(1)]+unproc[secreted(2)] = 3+4 = 7;
    # transferase demand = unproc[lipoprotein(1)] = 3; verified directly
    # against h12.predict_protein_processing_ii for this exact before/fixture):
    # unprocessed -> 0, processed=[2,3,4,0], signal=[0,3,4,0] (passthrough
    # idx0 excluded), substrates: water-7, pg160-3, snglyp+3, hydrogen+3.
    row = [0.0, 0.0, 0.0, 0.0] + [2.0, 3.0, 4.0, 0.0] + [0.0, 3.0, 4.0, 0.0] + [93.0, 97.0, 103.0, 103.0]
    csv_path = tmp_path / "ppii_scenario_a_after.csv"
    with open(csv_path, "w", encoding="ascii") as fh:
        fh.write(",".join(str(x) for x in row) + "\n")
        fh.write(",".join(str(x) for x in row) + "\n")
    result = hp.ingest_ppii_scenario_a(fixture)
    assert result["nontrivial_sample_count"] > 0
    assert result["exact_match_count"] == result["nontrivial_sample_count"]
    assert result["trivial_mismatch_count"] == 0


def test_ingest_ppii_scenario_a_mismatching_csv_yields_mismatch(tmp_path, monkeypatch):
    fixture = _ppii_synthetic_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    monkeypatch.setattr(hp, "build_ppii_scenario_a_state", lambda f: {
        "unprocessedMonomers": np.array([2.0, 3.0, 4.0, 0.0]),
        "processedMonomers": np.zeros(4),
        "signalSequenceMonomers": np.zeros(4),
        "enzymes": np.array([10.0, 10.0]),
        "substrates": np.array([100.0, 100.0, 100.0, 100.0]),
    })
    monkeypatch.setattr(hp, "N_SEEDS", 2)
    # Deliberately wrong: unprocessedMonomers left non-zero (should be all-0).
    row = [2.0, 3.0, 4.0, 0.0] + [2.0, 3.0, 4.0, 0.0] + [0.0, 3.0, 4.0, 0.0] + [93.0, 96.0, 104.0, 104.0]
    csv_path = tmp_path / "ppii_scenario_a_after.csv"
    with open(csv_path, "w", encoding="ascii") as fh:
        fh.write(",".join(str(x) for x in row) + "\n")
        fh.write(",".join(str(x) for x in row) + "\n")
    result = hp.ingest_ppii_scenario_a(fixture)
    assert result["exact_match_count"] < result["nontrivial_sample_count"]
    assert len(result["mismatch_examples"]) > 0


def test_ingest_ppii_scenario_a_missing_csv_raises(tmp_path, monkeypatch):
    fixture = _ppii_full_construction_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        hp.ingest_ppii_scenario_a(fixture)


# ---------------------------------------------------------------------------
# Artifact-verdict-decision logic
# ---------------------------------------------------------------------------


def test_build_ppii_perturbation_artifact_confirmed_on_full_exact_match(tmp_path, monkeypatch):
    monkeypatch.setattr(hp, "OUT_DIR", tmp_path)
    compare_result = {
        "nontrivial_sample_count": 50,
        "exact_match_count": 50,
        "trivial_mismatch_count": 0,
        "total_sample_count": 50,
        "trivial_checked_count": 0,
        "mismatch_examples": [],
        "branches_confirmed": {"transferase_fires", "peptidase_fires", "passthrough_fires"},
        "raw_csv_sha256": "0" * 64,
    }
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    generated = {"ppii_state_sha256": "z" * 64}
    artifact = hp.build_ppii_perturbation_artifact(compare_result, fixture, generated)
    assert artifact["verdict"] == "H12_PERTURBATION_CONFIRMED"
    assert artifact["target_branch_confirmed"] is True
    assert artifact["gating"].startswith("NON_GATING")


def test_build_ppii_perturbation_artifact_fails_on_any_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(hp, "OUT_DIR", tmp_path)
    compare_result = {
        "nontrivial_sample_count": 50,
        "exact_match_count": 49,
        "trivial_mismatch_count": 0,
        "total_sample_count": 50,
        "trivial_checked_count": 0,
        "mismatch_examples": [{"seed": 3}],
        "branches_confirmed": set(),
        "raw_csv_sha256": "0" * 64,
    }
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    generated = {"ppii_state_sha256": "z" * 64}
    artifact = hp.build_ppii_perturbation_artifact(compare_result, fixture, generated)
    assert artifact["verdict"] == "H12_PERTURBATION_FAIL"


def test_build_ppii_perturbation_artifact_fails_on_any_trivial_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(hp, "OUT_DIR", tmp_path)
    compare_result = {
        "nontrivial_sample_count": 50,
        "exact_match_count": 50,
        "trivial_mismatch_count": 1,
        "total_sample_count": 50,
        "trivial_checked_count": 10,
        "mismatch_examples": [],
        "branches_confirmed": set(),
        "raw_csv_sha256": "0" * 64,
    }
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    generated = {"ppii_state_sha256": "z" * 64}
    artifact = hp.build_ppii_perturbation_artifact(compare_result, fixture, generated)
    assert artifact["verdict"] == "H12_PERTURBATION_FAIL"


def test_build_macromol_perturbation_artifact_observed_stochastic_when_clean():
    invariant_result = {
        "ub": [17, 15],
        "n_seeds": 50,
        "bound_violations": [],
        "mass_balance_violations": [],
        "distinct_outcome_count": 6,
        "seeds_vary": True,
        "min_built_per_complex": [9, 8],
        "max_built_per_complex": [12, 11],
        "mean_built_per_complex": [10.5, 9.6],
        "raw_csv_sha256": "0" * 64,
    }
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    artifact = hp.build_macromol_perturbation_artifact(invariant_result, fixture)
    assert artifact["verdict"] == "H12_PERTURBATION_OBSERVED_STOCHASTIC"
    assert "H12_CONFIRMED" not in artifact["verdict"]
    assert artifact["gating"].startswith("NON_GATING")


def test_build_macromol_perturbation_artifact_invariant_violation_when_bound_exceeded():
    invariant_result = {
        "ub": [17, 15],
        "n_seeds": 50,
        "bound_violations": [{"seed": 4, "reason": "exceeds_ub"}],
        "mass_balance_violations": [],
        "distinct_outcome_count": 3,
        "seeds_vary": True,
        "min_built_per_complex": [9, 8],
        "max_built_per_complex": [18, 11],
        "mean_built_per_complex": [10.5, 9.6],
        "raw_csv_sha256": "0" * 64,
    }
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    artifact = hp.build_macromol_perturbation_artifact(invariant_result, fixture)
    assert artifact["verdict"] == "H12_PERTURBATION_INVARIANT_VIOLATION"


def test_build_macromol_perturbation_artifact_never_claims_h12_confirmed_even_if_flagged_ok():
    # Even in the "everything clean" case, the verdict vocabulary must
    # never overlap with the gated schema's H12_CONFIRMED.
    invariant_result = {
        "ub": [17, 15],
        "n_seeds": 50,
        "bound_violations": [],
        "mass_balance_violations": [],
        "distinct_outcome_count": 1,
        "seeds_vary": False,
        "min_built_per_complex": [10, 10],
        "max_built_per_complex": [10, 10],
        "mean_built_per_complex": [10.0, 10.0],
        "raw_csv_sha256": "0" * 64,
    }
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    artifact = hp.build_macromol_perturbation_artifact(invariant_result, fixture)
    assert artifact["verdict"] in {
        "H12_PERTURBATION_OBSERVED_STOCHASTIC",
        "H12_PERTURBATION_INVARIANT_VIOLATION",
    }
    assert artifact["verdict"] != "H12_CONFIRMED"


# ---------------------------------------------------------------------------
# Consistency: module constants vs. tracked pre-registered spec
# ---------------------------------------------------------------------------


def test_module_constants_match_pre_registered_spec():
    with open(hp.SPEC_PATH, "r", encoding="utf-8") as fh:
        spec = json.load(fh)
    scn_ppii = spec["scenarios"]["protein_processing_ii_scenario_a_full_saturating"]
    assert "58" in scn_ppii["derivation"]["enzymes_signalPeptidase"]
    assert hp.PPII_SCENARIO_A["enzymes_signalPeptidase"] == 58.0
    assert hp.PPII_SCENARIO_A["enzymes_diacylglycerylTransferase"] == 372.0
    assert hp.PPII_SCENARIO_A["substrates_water"] == 1000.0
    assert hp.PPII_SCENARIO_A["substrates_PG160"] == 100.0

    scn_macromol = spec["scenarios"]["macromolecular_complexation_network2_competition"]
    assert hp.MACROMOL_NETWORK2["substrate_indices_0b"] == scn_macromol["substrate_indices_0b"]
    assert hp.MACROMOL_NETWORK2["complex_indices_0b"] == scn_macromol["complex_indices_0b"]
    assert hp.MACROMOL_NETWORK2["stoichiometry_block"] == scn_macromol["stoichiometry_block"]
    assert hp.MACROMOL_NETWORK2["pool_values"] == [51.0, 34.0, 31.0, 40.0]


def test_spec_records_ppii_scarcity_guard_as_explicitly_out_of_scope():
    with open(hp.SPEC_PATH, "r", encoding="utf-8") as fh:
        spec = json.load(fh)
    assert "explicitly_out_of_scope_for_octave_execution" in spec
    assert "protein_processing_ii_scarcity_guard_branch" in spec["explicitly_out_of_scope_for_octave_execution"]


def test_descoped_scarcity_guard_is_actually_covered_by_existing_formula_test():
    # Confirms the artifact of the pre-registered scoping decision actually
    # exists (guards against the decision being recorded but never acted on).
    source = TEST_FORMULAS_PATH.read_text(encoding="utf-8")
    assert "def test_protein_processing_ii_guard_fails_when_pg160_insufficient" in source


def test_n_seeds_matches_spec_seed_count():
    with open(hp.SPEC_PATH, "r", encoding="utf-8") as fh:
        spec = json.load(fh)
    assert hp.N_SEEDS == spec["seeds"]["count"] == 50


# ---------------------------------------------------------------------------
# Non-gating verification
# ---------------------------------------------------------------------------


def test_verdict_module_never_references_perturbation():
    source = VERDICT_PATH.read_text(encoding="utf-8")
    assert "h12_perturbation" not in source
    assert "H12_PERTURBATION" not in source


def test_generator_module_never_references_perturbation():
    source = GENERATOR_PATH.read_text(encoding="utf-8")
    assert "h12_perturbation" not in source
    assert "H12_PERTURBATION" not in source


def test_perturbation_artifact_verdicts_disjoint_from_gated_schema_verdicts():
    gated_verdicts = {"H12_CONFIRMED", "H12_FAIL", "H12_OBSERVED_REGIME"}
    perturbation_verdicts = {
        "H12_PERTURBATION_CONFIRMED",
        "H12_PERTURBATION_FAIL",
        "H12_PERTURBATION_OBSERVED_STOCHASTIC",
        "H12_PERTURBATION_INVARIANT_VIOLATION",
    }
    assert gated_verdicts.isdisjoint(perturbation_verdicts)


def test_existing_gated_h12_artifacts_are_untouched_by_perturbation_module():
    # The two Round-3-accepted OBSERVED_REGIME artifacts must remain exactly
    # as accepted; this module writes only to the perturbation/ subdirectory.
    gated_dir = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12"
    assert hp.OUT_DIR == gated_dir / "perturbation"
    assert hp.OUT_DIR != gated_dir


# ---------------------------------------------------------------------------
# Fresh-clone / no-Octave-installed safety
# ---------------------------------------------------------------------------


def test_generate_inputs_and_construction_do_not_require_octave_binary(monkeypatch):
    # generate_inputs()/build_*_state() must not themselves invoke Octave --
    # only run_octave_scenario() does, and that is a distinct, separately
    # invoked CLI command ("run-octave").
    tree = _module_ast()
    for fn_name in PREDICT_PHASE_FUNCTIONS:
        fn = _function_node(tree, fn_name)
        names = _names_used(fn)
        assert "subprocess" not in names
        assert "octave" not in names


def test_harness_files_are_tracked_and_hashable():
    for name in hp.HARNESS_FILES:
        path = hp.OCTAVE_DIR / name
        assert path.is_file(), f"expected harness file missing: {path}"
    hashes = hp._harness_hashes()
    assert len(hashes) == len(hp.HARNESS_FILES)
    for v in hashes.values():
        assert len(v) == 64
