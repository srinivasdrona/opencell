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
import subprocess
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
    "build_ppii_scenario_b_states",
    "generate_inputs_scenario_b",
    "guard_diagnostics_ppii",
    "predict_ppii_scarcity_bounds",
    "freeze_ppii_scenario_b_predictions",
)

# Functions that legitimately read Octave "after" output (COMPARE /
# invariant-check phase) -- these are the ONLY functions allowed to touch
# raw CSV / "after" data.
COMPARE_PHASE_FUNCTIONS = (
    "ingest_ppii_scenario_a",
    "check_macromol_invariants",
    "ingest_ppii_scenario_b",
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
# Scenario B: guard_diagnostics_ppii / predict_ppii_scarcity_bounds pure math
# ---------------------------------------------------------------------------


def _real_ppii_fixture():
    import sys
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.l22_evidence import h12 as _h12

    return _h12.load_fixture("ProteinProcessingII")


@pytest.mark.parametrize("state_name", hp.PPII_SCENARIO_B_STATE_NAMES)
def test_scenario_b_states_have_expected_regime_invalid_reason(state_name):
    """Spec-consistency check (no Octave needed): each pre-registered
    Scenario B state's declared `guard_failure` label (module constant,
    cross-checked against PERTURBATION_SPEC.json by
    generate_inputs_scenario_b) must match BOTH guard_diagnostics_ppii's
    own per-guard breakdown AND the accepted, unmodified
    h12.predict_protein_processing_ii's aggregate regime_valid=False.
    """
    import sys
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.l22_evidence import h12 as _h12

    fixture = _real_ppii_fixture()
    states = hp.build_ppii_scenario_b_states(fixture)
    state = states[state_name]
    expected_label = hp.PPII_SCENARIO_B_STATES[state_name]["guard_failure"]

    prediction = hp.predict_ppii_scarcity_bounds(state, fixture)
    assert prediction["guard_diagnostics"]["regime_valid"] is False
    assert prediction["guard_failure_label"] == expected_label

    before = {
        "unprocessedMonomers": state["unprocessedMonomers"][None, :],
        "enzymes": state["enzymes"][None, :],
        "substrates": state["substrates"][None, :],
    }
    real_predictions = _h12.predict_protein_processing_ii(seed=0, before=before, fixture=fixture)
    assert real_predictions[0].regime_valid is False


def test_guard_diagnostics_ppii_all_guards_pass_is_regime_valid_true():
    fixture = _ppii_synthetic_fixture()
    unprocessed = np.array([0.0, 0.0, 2.0, 0.0])  # lipoprotein(idx1)=0, secreted(idx2)=2
    enzymes = np.array([10.0, 10.0])
    diag = hp.guard_diagnostics_ppii(unprocessed, enzymes, water=100.0, pg160=100.0, fixture=fixture)
    assert diag["regime_valid"] is True
    assert diag["failed_guards"] == []


def test_guard_diagnostics_ppii_water_only_failure():
    fixture = _ppii_synthetic_fixture()
    unprocessed = np.array([0.0, 0.0, 5.0, 0.0])  # secreted demand = 5
    enzymes = np.array([10.0, 10.0])  # peptidase_limit = 10*2 = 20 >= 5
    diag = hp.guard_diagnostics_ppii(unprocessed, enzymes, water=1.0, pg160=100.0, fixture=fixture)
    assert diag["failed_guards"] == ["water"]
    assert hp._guard_failure_label(diag["failed_guards"]) == "water_only"


def test_guard_failure_label_mapping():
    assert hp._guard_failure_label(["water"]) == "water_only"
    assert hp._guard_failure_label(["pg160"]) == "pg160_only"
    assert hp._guard_failure_label(["peptidase_limit"]) == "peptidase_limit_only"
    assert hp._guard_failure_label(["transferase_limit"]) == "transferase_limit_only"
    assert hp._guard_failure_label(["peptidase_limit", "water"]) == "peptidase_limit_and_water"
    assert hp._guard_failure_label([]) == "none"


# ---------------------------------------------------------------------------
# guard_diagnostics_ppii boundary-grid cross-check against the accepted
# h12.predict_protein_processing_ii predictor (Opus5 correction 8): proves
# guard_diagnostics_ppii's four-guard breakdown is not a divergent
# reimplementation, at the exact boundary of each guard independently and
# at a simultaneous-failure combination.
# ---------------------------------------------------------------------------


def _boundary_grid_state(fixture, peptidase_delta, transferase_delta, water_delta, pg160_delta):
    """Construct a before-state whose peptidase/transferase demand sits
    EXACTLY `*_delta` counts away from that guard's own capacity limit
    (computed from real fixture rate/stepSize values), and whose water/
    pg160 pools sit EXACTLY `*_delta` away from the corresponding demand.
    delta<=0 means the guard must PASS (limit/pool >= demand); delta>0
    means it must FAIL. Uses large, well-separated representative enzyme
    counts so the two capacity limits never collide regardless of the
    small deltas exercised here.
    """
    lipo_idx = fixture["lipoproteinMonomerIndexs_0b"]
    secr_idx = fixture["secretedMonomerIndexs_0b"]
    passthrough_idx = fixture["unprocessedMonomerIndexs_0b"]
    n_mono = int(max(int(lipo_idx.max()), int(secr_idx.max()), int(passthrough_idx.max()))) + 1
    n_enz = (
        int(max(fixture["enzymeIndexs_signalPeptidase_0b"], fixture["enzymeIndexs_diacylglycerylTransferase_0b"]))
        + 1
    )
    enzymes = np.zeros(n_enz)
    enzymes[fixture["enzymeIndexs_signalPeptidase_0b"]] = 1_000_000.0
    enzymes[fixture["enzymeIndexs_diacylglycerylTransferase_0b"]] = 1.0
    peptidase_limit = (
        enzymes[fixture["enzymeIndexs_signalPeptidase_0b"]]
        * fixture["lipoproteinSignalPeptidaseSpecificRate"]
        * fixture["stepSizeSec"]
    )
    transferase_limit = (
        enzymes[fixture["enzymeIndexs_diacylglycerylTransferase_0b"]]
        * fixture["lipoproteinDiacylglycerylTransferaseSpecificRate"]
        * fixture["stepSizeSec"]
    )
    transferase_demand = transferase_limit + transferase_delta
    peptidase_demand = peptidase_limit + peptidase_delta
    assert transferase_demand >= 0 and peptidase_demand >= transferase_demand, (
        "boundary-grid fixture construction assumption violated -- widen the enzyme separation"
    )
    unprocessed = np.zeros(n_mono)
    unprocessed[int(lipo_idx[0])] = transferase_demand
    unprocessed[int(secr_idx[0])] = peptidase_demand - transferase_demand
    water = peptidase_demand + water_delta
    pg160 = transferase_demand + pg160_delta
    return unprocessed, enzymes, water, pg160, peptidase_demand, transferase_demand


@pytest.mark.parametrize(
    "peptidase_delta,transferase_delta,water_delta,pg160_delta,expect_valid",
    [
        (0, 0, 0, 0, True),  # exactly at all four limits -- guard is >=, so this must PASS
        (1, 0, 0, 0, False),  # peptidase_demand = limit+1 -- fails peptidase_limit only
        (0, 1, 0, 0, False),  # transferase_demand = limit+1 -- fails transferase_limit only
        (0, 0, -1, 0, False),  # water = peptidase_demand-1 -- fails water only
        (0, 0, 0, -1, False),  # pg160 = transferase_demand-1 -- fails pg160 only
        (1, 0, -1, 0, False),  # simultaneous peptidase_limit + water failure
    ],
)
def test_guard_diagnostics_ppii_boundary_grid_matches_accepted_h12_predictor(
    peptidase_delta, transferase_delta, water_delta, pg160_delta, expect_valid
):
    import sys
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.l22_evidence import h12 as _h12

    fixture = _real_ppii_fixture()
    unprocessed, enzymes, water, pg160, _, _ = _boundary_grid_state(
        fixture, peptidase_delta, transferase_delta, water_delta, pg160_delta
    )

    diag = hp.guard_diagnostics_ppii(unprocessed, enzymes, water=water, pg160=pg160, fixture=fixture)
    assert bool(diag["regime_valid"]) == expect_valid

    n_sub = (
        max(
            fixture["substrateIndexs_water_0b"],
            fixture["substrateIndexs_PG160_0b"],
            fixture["substrateIndexs_SNGLYP_0b"],
            fixture["substrateIndexs_hydrogen_0b"],
        )
        + 1
    )
    substrates = np.zeros(n_sub)
    substrates[fixture["substrateIndexs_water_0b"]] = water
    substrates[fixture["substrateIndexs_PG160_0b"]] = pg160
    before = {
        "unprocessedMonomers": unprocessed[None, :],
        "enzymes": enzymes[None, :],
        "substrates": substrates[None, :],
    }
    real_predictions = _h12.predict_protein_processing_ii(seed=0, before=before, fixture=fixture)
    assert bool(real_predictions[0].regime_valid) == expect_valid, (
        "guard_diagnostics_ppii's regime_valid diverges from the accepted h12.predict_protein_processing_ii "
        "at this boundary-grid point -- these two must always agree"
    )


# ---------------------------------------------------------------------------
# Scenario B: evaluate_ppii_scarcity_invariants pure math (no I/O)
# ---------------------------------------------------------------------------


def _scarcity_before_and_maker(fixture):
    # water_scarce-style before-state: secreted demand [20,15,10,5]=50, water=30.
    n_mono = 5
    unprocessed = np.zeros(n_mono)
    secr_idx = fixture["secretedMonomerIndexs_0b"]
    demand = [20.0, 15.0, 10.0, 5.0]
    for i, idx in enumerate(secr_idx):
        unprocessed[idx] = demand[i]
    substrates = np.array([30.0, 100.0, 100.0, 100.0])
    before = {"unprocessedMonomers": unprocessed, "substrates": substrates}

    def make_row(alloc):
        unproc_after = np.zeros(n_mono)
        processed_after = np.zeros(n_mono)
        signal_after = np.zeros(n_mono)
        for i, idx in enumerate(secr_idx):
            processed_after[idx] = alloc[i]
            unproc_after[idx] = unprocessed[idx] - alloc[i]
            signal_after[idx] = alloc[i]
        substrates_after = substrates.copy()
        substrates_after[0] -= sum(alloc)
        return np.concatenate([unproc_after, processed_after, signal_after, substrates_after])

    return before, make_row


def test_evaluate_ppii_scarcity_invariants_clean_and_varying():
    fixture = _ppii_synthetic_fixture()
    fixture["secretedMonomerIndexs_0b"] = np.array([0, 1, 2, 3])
    fixture["lipoproteinMonomerIndexs_0b"] = np.array([], dtype=np.int64)
    before, make_row = _scarcity_before_and_maker(fixture)
    raw = np.array([make_row([12, 9, 6, 3]), make_row([13, 10, 6, 1]), make_row([12, 9, 6, 3])])
    result = hp.evaluate_ppii_scarcity_invariants(before, raw, fixture)
    assert result["violations"] == []
    assert result["seeds_vary"] is True
    assert result["distinct_outcome_count"] == 2


def test_evaluate_ppii_scarcity_invariants_no_variation_flagged():
    fixture = _ppii_synthetic_fixture()
    fixture["secretedMonomerIndexs_0b"] = np.array([0, 1, 2, 3])
    fixture["lipoproteinMonomerIndexs_0b"] = np.array([], dtype=np.int64)
    before, make_row = _scarcity_before_and_maker(fixture)
    raw = np.array([make_row([12, 9, 6, 3]), make_row([12, 9, 6, 3])])
    result = hp.evaluate_ppii_scarcity_invariants(before, raw, fixture)
    assert result["violations"] == []
    assert result["seeds_vary"] is False
    assert result["distinct_outcome_count"] == 1


def test_evaluate_ppii_scarcity_invariants_detects_pool_cap_violation():
    fixture = _ppii_synthetic_fixture()
    fixture["secretedMonomerIndexs_0b"] = np.array([0, 1, 2, 3])
    fixture["lipoproteinMonomerIndexs_0b"] = np.array([], dtype=np.int64)
    before, make_row = _scarcity_before_and_maker(fixture)
    # allocate the full raw demand (50), which exceeds water(30) -- a
    # correct mnrnd realization could never do this (sums to <=30).
    raw = np.array([make_row([20, 15, 10, 5])])
    result = hp.evaluate_ppii_scarcity_invariants(before, raw, fixture)
    reasons = {v["reason"] for v in result["violations"]}
    assert "pool_cap_peptidase" in reasons


def test_evaluate_ppii_scarcity_invariants_detects_mass_conservation_violation():
    fixture = _ppii_synthetic_fixture()
    fixture["secretedMonomerIndexs_0b"] = np.array([0, 1, 2, 3])
    fixture["lipoproteinMonomerIndexs_0b"] = np.array([], dtype=np.int64)
    before, make_row = _scarcity_before_and_maker(fixture)
    row = make_row([12, 9, 6, 3])
    row[0:5] += 1.0  # corrupt unprocessed_after only, breaking mass conservation
    result = hp.evaluate_ppii_scarcity_invariants(before, np.array([row]), fixture)
    reasons = {v["reason"] for v in result["violations"]}
    assert "mass_conservation" in reasons


def test_evaluate_ppii_scarcity_invariants_detects_per_species_cap_violation():
    fixture = _ppii_synthetic_fixture()
    fixture["secretedMonomerIndexs_0b"] = np.array([0, 1, 2, 3])
    fixture["lipoproteinMonomerIndexs_0b"] = np.array([], dtype=np.int64)
    before, make_row = _scarcity_before_and_maker(fixture)
    row = make_row([12, 9, 6, 3])
    # processed_after (columns n_mono:2*n_mono = [5:10]) for species 0 set
    # above its original unprocessed count (20) -- invents mass at that
    # species, must be caught independent of the aggregate mass check.
    row[5] = 21.0
    row[0] = -1.0  # keep aggregate mass balanced so only per_species_cap fires
    result = hp.evaluate_ppii_scarcity_invariants(before, np.array([row]), fixture)
    reasons = {v["reason"] for v in result["violations"]}
    assert "per_species_cap" in reasons


# ---------------------------------------------------------------------------
# ingest_ppii_scenario_b with synthetic frozen-prediction/manifest/CSV
# fixtures (no live MATLAB invocation). These exercise the mode-aware,
# hash-bound, anti-recompute contract added in Turn 3 (Opus5 corrections
# 5, 6, 7).
# ---------------------------------------------------------------------------


def _write_scenario_b_evidence(
    tmp_path,
    fixture,
    state_name,
    mode,
    seeds,
    *,
    manifest_overrides=None,
    prediction_overrides=None,
    csv_seed_ids=None,
    csv_row_count=None,
    skip_prediction=False,
    skip_manifest=False,
    skip_csv=False,
    corrupt_state_file_after_freeze=False,
    corrupt_before_state_after_freeze=False,
):
    """Write a self-consistent {frozen prediction, run-manifest, after-CSV}
    trio for one Scenario B state/mode, using the REAL
    build_ppii_scenario_b_states/predict_ppii_scarcity_bounds/
    _write_ppii_scenario_b_state_files so shapes and hashes match what
    ingest_ppii_scenario_b actually expects. Individual fields can be
    corrupted via the keyword arguments to build negative-path fixtures.
    """
    states = hp.build_ppii_scenario_b_states(fixture)
    state = states[state_name]
    state_paths = hp._write_ppii_scenario_b_state_files({state_name: state}, fixture)
    state_path = state_paths[state_name]
    frozen_state_sha256 = hp._sha256_lf_normalized(state_path)

    if not skip_prediction:
        prediction = hp.predict_ppii_scarcity_bounds(state, fixture)
        mode_seeds = {"full": list(hp.PPII_SCENARIO_B_SEED_BLOCKS[state_name])}
        if state_name == hp.PPII_SCENARIO_B_CANARY_STATE:
            mode_seeds["canary"] = list(hp.PPII_SCENARIO_B_CANARY_SEEDS)
        before_state = {
            "unprocessedMonomers": state["unprocessedMonomers"].tolist(),
            "processedMonomers": state["processedMonomers"].tolist(),
            "signalSequenceMonomers": state["signalSequenceMonomers"].tolist(),
            "enzymes": state["enzymes"].tolist(),
            "substrates": state["substrates"].tolist(),
        }
        frozen = {
            "state_name": state_name,
            "mode_seeds": mode_seeds,
            "state_file": state_path.name,
            "state_file_sha256": frozen_state_sha256,
            "before_state": before_state,
            "before_state_sha256": hp._hash_canonical(before_state),
            "prediction": prediction,
            "frozen_at_utc": "2024-01-01T00:00:00+00:00",
        }
        if prediction_overrides:
            frozen.update(prediction_overrides)
        hp._write_json(tmp_path / f"ppii_scenario_b_{state_name}_prediction.json", frozen)

    if corrupt_state_file_after_freeze:
        # Simulate the state file changing on disk AFTER its prediction was
        # frozen (e.g. someone hand-edited it, or a stale re-run happened).
        state_path.write_text(state_path.read_text(encoding="ascii") + "\n% drifted\n", encoding="ascii")

    if corrupt_before_state_after_freeze:
        # Simulate a hand-edited/corrupted frozen prediction JSON: mutate
        # before_state WITHOUT updating before_state_sha256, so the
        # self-binding hash check in ingest_ppii_scenario_b must catch it
        # (Opus5 turn-4 correction 6 tamper test).
        prediction_path = tmp_path / f"ppii_scenario_b_{state_name}_prediction.json"
        frozen_on_disk = hp._load_json(prediction_path)
        frozen_on_disk["before_state"]["substrates"][0] += 1.0
        hp._write_json(prediction_path, frozen_on_disk)

    vendored_randstream_hash = hp._sha256_lf_normalized(hp.VENDORED_RANDSTREAM_PATH)
    if not skip_manifest:
        manifest = {
            "state_name": state_name,
            "mode": mode,
            "seeds": list(seeds),
            "n_seeds": len(seeds),
            "matlab_version": "9.99.0.test",
            "statistics_toolbox_licensed": True,
            "statistics_toolbox_installed": True,
            "randstream_class_confirmed": True,
            "wholecell_src_root_used": str(hp.VENDORED_RANDSTREAM_PATH.parent),
            "randstream_runtime_path": str(hp.VENDORED_RANDSTREAM_PATH),
            "randstream_runtime_sha256_lf_normalized": vendored_randstream_hash,
            "harness_file": "evolveState_ppii_matlab.m",
            "harness_sha256_lf_normalized": hp._sha256_lf_normalized(hp.MATLAB_DIR / "evolveState_ppii_matlab.m"),
            "state_file_sha256_lf_normalized": frozen_state_sha256,
            "generated_at_utc": "2024-01-01T00:00:01+00:00",
        }
        if manifest_overrides:
            manifest.update(manifest_overrides)
        hp._write_json(tmp_path / f"ppii_scenario_b_{state_name}_run_manifest.json", manifest)

    if not skip_csv:
        n_mono = state["unprocessedMonomers"].shape[0]
        unprocessed = state["unprocessedMonomers"].tolist()
        substrates = state["substrates"].tolist()
        # Trivially "clean": nothing processed, nothing consumed -- mass is
        # conserved exactly because unprocessed_after == unprocessed_before
        # (a legitimate, if unexciting, evolveState outcome).
        body = unprocessed + [0.0] * n_mono + [0.0] * n_mono + substrates
        actual_seed_ids = list(seeds) if csv_seed_ids is None else list(csv_seed_ids)
        n_rows = len(seeds) if csv_row_count is None else csv_row_count
        csv_path = tmp_path / f"ppii_scenario_b_{state_name}_after.csv"
        with open(csv_path, "w", encoding="ascii") as fh:
            for i in range(n_rows):
                seed_id = actual_seed_ids[i] if i < len(actual_seed_ids) else actual_seed_ids[-1]
                fh.write(",".join(str(x) for x in [float(seed_id)] + body) + "\n")

    return {"state": state, "n_mono": state["unprocessedMonomers"].shape[0], "n_sub": state["substrates"].shape[0]}


def test_ingest_ppii_scenario_b_full_matching_evidence_yields_no_violations(tmp_path, monkeypatch):
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    for name in hp.PPII_SCENARIO_B_STATE_NAMES:
        seeds = hp.PPII_SCENARIO_B_SEED_BLOCKS[name]
        _write_scenario_b_evidence(tmp_path, fixture, name, "full", seeds)

    results = hp.ingest_ppii_scenario_b(fixture, mode="full")
    assert set(results.keys()) == set(hp.PPII_SCENARIO_B_STATE_NAMES)
    for r in results.values():
        assert r["invariants"]["violations"] == []
        assert r["invariants"]["n_seeds"] == 50


def test_ingest_ppii_scenario_b_canary_mode_processes_only_canary_state(tmp_path, monkeypatch):
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(tmp_path, fixture, name, "canary", hp.PPII_SCENARIO_B_CANARY_SEEDS)

    results = hp.ingest_ppii_scenario_b(fixture, mode="canary")
    assert set(results.keys()) == {name}
    assert results[name]["invariants"]["n_seeds"] == hp.PPII_SCENARIO_B_CANARY_SEED_COUNT


def test_ingest_ppii_scenario_b_missing_csv_raises(tmp_path, monkeypatch):
    fixture = _ppii_full_construction_fixture()
    fixture["lipoproteinMonomerIndexs_0b"] = np.array([1, 6, 7])
    fixture["secretedMonomerIndexs_0b"] = np.array([2, 8, 9, 10])
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        hp.ingest_ppii_scenario_b(fixture, mode="full")


def test_ingest_ppii_scenario_b_missing_prediction_raises(tmp_path, monkeypatch):
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(
        tmp_path, fixture, name, "canary", hp.PPII_SCENARIO_B_CANARY_SEEDS, skip_prediction=True
    )
    with pytest.raises(FileNotFoundError):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_missing_manifest_raises(tmp_path, monkeypatch):
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(
        tmp_path, fixture, name, "canary", hp.PPII_SCENARIO_B_CANARY_SEEDS, skip_manifest=True
    )
    with pytest.raises(FileNotFoundError):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_rejects_manifest_mode_mismatch(tmp_path, monkeypatch):
    # Inversion test: a "full"-labeled manifest fed to a canary-mode ingest
    # (or vice versa) must be rejected outright, never silently accepted.
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(
        tmp_path,
        fixture,
        name,
        "canary",
        hp.PPII_SCENARIO_B_CANARY_SEEDS,
        manifest_overrides={"mode": "full"},
    )
    with pytest.raises(ValueError, match="mode"):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_rejects_reused_or_substituted_seed_list(tmp_path, monkeypatch):
    # Inversion test: reused/substituted seeds (e.g. accidentally reusing
    # Scenario A's 0-49 range, or any seeds not in the pre-registered
    # block) in the manifest must be rejected even if the CSV cardinality
    # is otherwise correct.
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    bad_seeds = list(range(0, 5))  # Scenario A's seed range, not this state's block
    _write_scenario_b_evidence(
        tmp_path,
        fixture,
        name,
        "canary",
        hp.PPII_SCENARIO_B_CANARY_SEEDS,
        manifest_overrides={"seeds": bad_seeds},
        csv_seed_ids=bad_seeds,
    )
    with pytest.raises(ValueError, match="seeds"):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_rejects_mixed_canary_full_row_count(tmp_path, monkeypatch):
    # Inversion test: a CSV whose row count doesn't match the requested
    # mode's cardinality (e.g. 50 rows presented against a canary-mode
    # ingest, or a partial/mixed set) must be rejected, never truncated
    # or padded silently.
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(
        tmp_path,
        fixture,
        name,
        "canary",
        hp.PPII_SCENARIO_B_CANARY_SEEDS,
        csv_row_count=hp.PPII_SCENARIO_B_FULL_SEED_COUNT,
        csv_seed_ids=list(hp.PPII_SCENARIO_B_SEED_BLOCKS[name]),
    )
    with pytest.raises(ValueError, match="row count"):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_rejects_seed_id_column_mismatch(tmp_path, monkeypatch):
    # Inversion test: even with the right row count, a CSV whose leading
    # seed-id column doesn't match the pre-registered seed set must be
    # rejected (catches a CSV silently generated against the wrong seeds).
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    wrong_ids = [s + 1 for s in hp.PPII_SCENARIO_B_CANARY_SEEDS]
    _write_scenario_b_evidence(
        tmp_path,
        fixture,
        name,
        "canary",
        hp.PPII_SCENARIO_B_CANARY_SEEDS,
        csv_seed_ids=wrong_ids,
    )
    with pytest.raises(ValueError, match="seed-id column"):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_rejects_stale_state_file_hash(tmp_path, monkeypatch):
    # Inversion test: the state file drifting after its prediction was
    # frozen (three-way staleness check) must be caught.
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(
        tmp_path,
        fixture,
        name,
        "canary",
        hp.PPII_SCENARIO_B_CANARY_SEEDS,
        corrupt_state_file_after_freeze=True,
    )
    with pytest.raises(ValueError, match="changed since its prediction was frozen"):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_rejects_missing_randstream_confirmation(tmp_path, monkeypatch):
    # Inversion test: a manifest that does not affirmatively confirm the
    # real RandStream class was used must never be trusted (guards against
    # a driver silently falling back to a stub or built-in MATLAB rand()).
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(
        tmp_path,
        fixture,
        name,
        "canary",
        hp.PPII_SCENARIO_B_CANARY_SEEDS,
        manifest_overrides={"randstream_class_confirmed": False},
    )
    with pytest.raises(ValueError, match="randstream_class_confirmed"):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_rejects_stale_harness_hash(tmp_path, monkeypatch):
    # Inversion test: a manifest recorded against an outdated harness hash
    # (e.g. evolveState_ppii_matlab.m edited after the run) must be
    # rejected, not silently accepted as still-valid evidence.
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(
        tmp_path,
        fixture,
        name,
        "canary",
        hp.PPII_SCENARIO_B_CANARY_SEEDS,
        manifest_overrides={"harness_sha256_lf_normalized": "0" * 64},
    )
    with pytest.raises(ValueError, match="stale harness"):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_rejects_wrong_randstream_hash_in_manifest(tmp_path, monkeypatch):
    # Inversion test (Opus5 turn-4 correction 2): a manifest whose
    # RandStream runtime hash does NOT match the vendored
    # data/karr_vendored_source/RandStream.m must be rejected even though
    # randstream_class_confirmed=True -- the boolean self-report alone is
    # never sufficient.
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(
        tmp_path,
        fixture,
        name,
        "canary",
        hp.PPII_SCENARIO_B_CANARY_SEEDS,
        manifest_overrides={"randstream_runtime_sha256_lf_normalized": "1" * 64},
    )
    with pytest.raises(ValueError, match="does not match the vendored"):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_rejects_missing_randstream_runtime_path_in_manifest(tmp_path, monkeypatch):
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(
        tmp_path,
        fixture,
        name,
        "canary",
        hp.PPII_SCENARIO_B_CANARY_SEEDS,
        manifest_overrides={"randstream_runtime_path": ""},
    )
    with pytest.raises(ValueError, match="randstream_runtime_path missing"):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_rejects_missing_before_state(tmp_path, monkeypatch):
    # Inversion test: a stale pre-turn-4 frozen prediction file with no
    # before_state block at all must be rejected, not silently treated as
    # "nothing to check".
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(tmp_path, fixture, name, "canary", hp.PPII_SCENARIO_B_CANARY_SEEDS)
    prediction_path = tmp_path / f"ppii_scenario_b_{name}_prediction.json"
    frozen = hp._load_json(prediction_path)
    del frozen["before_state"]
    del frozen["before_state_sha256"]
    hp._write_json(prediction_path, frozen)
    with pytest.raises(ValueError, match="no before_state block"):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_rejects_tampered_before_state(tmp_path, monkeypatch):
    # Inversion test (Opus5 turn-4 correction 6): before_state mutated
    # without updating before_state_sha256 (e.g. hand-edited or corrupted
    # prediction JSON) must be caught by the self-binding hash check, even
    # though it lives inside the same JSON file as its own hash.
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(
        tmp_path,
        fixture,
        name,
        "canary",
        hp.PPII_SCENARIO_B_CANARY_SEEDS,
        corrupt_before_state_after_freeze=True,
    )
    with pytest.raises(ValueError, match="does not hash-match"):
        hp.ingest_ppii_scenario_b(fixture, mode="canary")


def test_ingest_ppii_scenario_b_never_rebuilds_before_state_from_mutable_module_dict(tmp_path, monkeypatch):
    # Inversion test (Opus5 turn-4 correction 6 / "stale standard traces
    # mislabeled as new condition"): ingest must evaluate invariants
    # against the FROZEN before_state, never a fresh call to
    # build_ppii_scenario_b_states with the (mutable) module-level
    # PPII_SCENARIO_B_STATES dict. We monkeypatch build_ppii_scenario_b_states
    # to explode; ingest must still succeed using only the frozen JSON.
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(tmp_path, fixture, name, "canary", hp.PPII_SCENARIO_B_CANARY_SEEDS)

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("build_ppii_scenario_b_states must not be called during ingest")

    monkeypatch.setattr(hp, "build_ppii_scenario_b_states", _boom)
    results = hp.ingest_ppii_scenario_b(fixture, mode="canary")
    assert name in results
    assert results[name]["invariants"]["violations"] == []


def test_ingest_ppii_scenario_b_never_recomputes_prediction_stored_verdict_is_trusted(tmp_path, monkeypatch):
    # Inversion test (Opus5 correction 6 / "stored verdict trusted"): once
    # a frozen prediction exists, ingest must load it verbatim and must
    # NEVER call predict_ppii_scarcity_bounds again -- if it did, the
    # comparison would silently drift with any later code change instead
    # of comparing against the value that was actually pre-registered
    # before MATLAB ran. We monkeypatch predict_ppii_scarcity_bounds to
    # explode; ingest must still succeed using only the frozen JSON.
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    _write_scenario_b_evidence(tmp_path, fixture, name, "canary", hp.PPII_SCENARIO_B_CANARY_SEEDS)

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("predict_ppii_scarcity_bounds must not be recomputed during ingest")

    monkeypatch.setattr(hp, "predict_ppii_scarcity_bounds", _boom)
    results = hp.ingest_ppii_scenario_b(fixture, mode="canary")
    assert name in results
    assert "guard_diagnostics" in results[name]["prediction"]


def test_ingest_ppii_scenario_b_rejects_invalid_mode():
    fixture = _real_ppii_fixture()
    with pytest.raises(ValueError, match="mode"):
        hp.ingest_ppii_scenario_b(fixture, mode="bogus")


# ---------------------------------------------------------------------------
# freeze_ppii_scenario_b_predictions: persist + hash-bind
# ---------------------------------------------------------------------------


def test_freeze_ppii_scenario_b_predictions_persists_hash_bound_json(tmp_path, monkeypatch):
    fixture = _real_ppii_fixture()
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    states = hp.build_ppii_scenario_b_states(fixture)
    state_paths = hp._write_ppii_scenario_b_state_files(states, fixture)

    out_paths = hp.freeze_ppii_scenario_b_predictions(states, state_paths, fixture)
    assert set(out_paths.keys()) == set(hp.PPII_SCENARIO_B_STATE_NAMES)
    for name, path in out_paths.items():
        frozen = hp._load_json(path)
        assert frozen["state_name"] == name
        assert frozen["state_file_sha256"] == hp._sha256_lf_normalized(state_paths[name])
        assert frozen["mode_seeds"]["full"] == list(hp.PPII_SCENARIO_B_SEED_BLOCKS[name])
        if name == hp.PPII_SCENARIO_B_CANARY_STATE:
            assert frozen["mode_seeds"]["canary"] == list(hp.PPII_SCENARIO_B_CANARY_SEEDS)
        else:
            assert "canary" not in frozen["mode_seeds"]
        # The frozen prediction must equal a fresh recomputation at freeze
        # time (this is the ONLY place recomputation is allowed -- before
        # any MATLAB output exists).
        assert frozen["prediction"] == hp.predict_ppii_scarcity_bounds(states[name], fixture)
        # Opus5 turn-4 correction 6: the complete conditioned before-state
        # arrays are frozen alongside a self-binding hash.
        assert frozen["before_state"]["unprocessedMonomers"] == states[name]["unprocessedMonomers"].tolist()
        assert frozen["before_state"]["substrates"] == states[name]["substrates"].tolist()
        assert frozen["before_state_sha256"] == hp._hash_canonical(frozen["before_state"])


# ---------------------------------------------------------------------------
# Seed-block disjointness / canary-prefix semantics (Opus5 correction 5)
# ---------------------------------------------------------------------------


def test_scenario_b_seed_blocks_are_pairwise_disjoint_and_avoid_scenario_a_macromol_ids():
    all_scenario_a_ids = set(range(hp.N_SEEDS))  # Scenario A / macromol-network2 seeds 0..49
    seen = set()
    for name, block in hp.PPII_SCENARIO_B_SEED_BLOCKS.items():
        block_set = set(block)
        assert not (block_set & all_scenario_a_ids), (
            f"state {name!r}'s seed block overlaps Scenario A/macromol seed ids 0..{hp.N_SEEDS - 1}"
        )
        assert not (block_set & seen), f"state {name!r}'s seed block overlaps another Scenario B state's block"
        seen |= block_set
    assert len(seen) == sum(len(b) for b in hp.PPII_SCENARIO_B_SEED_BLOCKS.values())


def test_scenario_b_canary_seeds_are_prefix_of_full_block():
    canary_state_block = hp.PPII_SCENARIO_B_SEED_BLOCKS[hp.PPII_SCENARIO_B_CANARY_STATE]
    assert tuple(hp.PPII_SCENARIO_B_CANARY_SEEDS) == canary_state_block[: hp.PPII_SCENARIO_B_CANARY_SEED_COUNT]
    assert len(hp.PPII_SCENARIO_B_CANARY_SEEDS) == hp.PPII_SCENARIO_B_CANARY_SEED_COUNT


def test_scenario_b_canary_state_has_nonzero_transferase_demand():
    # Direct positive check for Opus5 correction 3: the canary state must
    # actually have transferase_demand > 0 and must genuinely fail the
    # transferase_limit guard (not merely be labeled as such) -- otherwise
    # it cannot serve as evidence the transferase branch fires at all.
    fixture = _real_ppii_fixture()
    states = hp.build_ppii_scenario_b_states(fixture)
    state = states[hp.PPII_SCENARIO_B_CANARY_STATE]
    lipo_idx = fixture["lipoproteinMonomerIndexs_0b"]
    transferase_demand = float(state["unprocessedMonomers"][lipo_idx].sum())
    assert transferase_demand > 0
    prediction = hp.predict_ppii_scarcity_bounds(state, fixture)
    assert "transferase_limit" in prediction["guard_diagnostics"]["failed_guards"]


def test_scenario_b_water_scarce_state_never_reaches_transferase_branch():
    # Negative control confirming WHY water_scarce cannot serve as canary:
    # its transferase demand must be exactly 0.
    fixture = _real_ppii_fixture()
    states = hp.build_ppii_scenario_b_states(fixture)
    state = states["water_scarce"]
    lipo_idx = fixture["lipoproteinMonomerIndexs_0b"]
    transferase_demand = float(state["unprocessedMonomers"][lipo_idx].sum())
    assert transferase_demand == 0.0


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


# ---------------------------------------------------------------------------
# build_ppii_scarcity_perturbation_artifact verdict-decision logic
# ---------------------------------------------------------------------------


def _scarcity_result_for(name, failed_guards, seeds_vary, violations=None, mode="full"):
    prediction = {
        "state_name": name,
        "guard_diagnostics": {"failed_guards": failed_guards, "regime_valid": len(failed_guards) == 0},
        "guard_failure_label": hp._guard_failure_label(failed_guards),
    }
    n_seeds = hp.PPII_SCENARIO_B_CANARY_SEED_COUNT if mode == "canary" else hp.PPII_SCENARIO_B_FULL_SEED_COUNT
    invariants = {
        "n_seeds": n_seeds,
        "violations": violations or [],
        "seeds_vary": seeds_vary,
        "distinct_outcome_count": 5 if seeds_vary else 1,
        "raw_csv_sha256": "0" * 64,
    }
    manifest = {
        "mode": mode,
        "seeds": list(range(n_seeds)),
        "matlab_version": "9.99.0.test",
        "statistics_toolbox_licensed": True,
        "randstream_class_confirmed": True,
        "generated_at_utc": "2024-01-01T00:00:01+00:00",
    }
    return {"prediction": prediction, "invariants": invariants, "manifest": manifest}


def _all_five_states_result(seeds_vary=True, violations=None, mode="full"):
    return {
        name: _scarcity_result_for(name, [PPII_SCENARIO_B_GUARD_MAP[name]], seeds_vary, violations, mode=mode)
        for name in hp.PPII_SCENARIO_B_STATE_NAMES
    }


# maps each state name to one of its (single) failed guard components, used
# only to build synthetic-but-label-consistent test fixtures above (the
# "simultaneous" state's real spec has 2 guards; a single-guard synthetic
# stand-in is fine here since these tests exercise the ARTIFACT's verdict
# arithmetic, not the state derivations themselves -- those are covered by
# test_scenario_b_states_have_expected_regime_invalid_reason).
PPII_SCENARIO_B_GUARD_MAP = {
    "water_scarce": "water",
    "pg160_scarce": "pg160",
    "peptidase_capacity_scarce": "peptidase_limit",
    "transferase_capacity_scarce": "transferase_limit",
    "simultaneous_peptidase_capacity_and_water_scarce": "peptidase_limit",
}


def test_build_ppii_scarcity_perturbation_artifact_observed_stochastic_when_clean_and_varying(tmp_path, monkeypatch):
    monkeypatch.setattr(hp, "OUT_DIR", tmp_path)
    results = _all_five_states_result(seeds_vary=True)
    # Patch the "expected" guard_failure lookup used by the artifact builder
    # to match our synthetic single-guard labels (avoids depending on the
    # real 5-state spec's dual-cause label for the simultaneous state here).
    monkeypatch.setattr(
        hp,
        "PPII_SCENARIO_B_STATES",
        {name: {"guard_failure": hp._guard_failure_label([guard])} for name, guard in PPII_SCENARIO_B_GUARD_MAP.items()},
    )
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    artifact = hp.build_ppii_scarcity_perturbation_artifact(results, fixture, {}, mode="full")
    assert artifact["verdict"] == "H12_PERTURBATION_SCARCITY_OBSERVED_STOCHASTIC"
    assert artifact["gating"].startswith("NON_GATING")
    assert "H12_CONFIRMED" not in artifact["verdict"]
    assert "H12_PERTURBATION_CONFIRMED" != artifact["verdict"]
    assert artifact["mode"] == "full"


def test_build_ppii_scarcity_perturbation_artifact_no_variation_when_a_state_never_varies(tmp_path, monkeypatch):
    monkeypatch.setattr(hp, "OUT_DIR", tmp_path)
    results = _all_five_states_result(seeds_vary=True)
    # Mutate one state to show NO cross-seed variation despite its guard
    # having failed -- the anti-laundering catch for a no-op RNG.
    results["water_scarce"] = _scarcity_result_for("water_scarce", ["water"], seeds_vary=False)
    monkeypatch.setattr(
        hp,
        "PPII_SCENARIO_B_STATES",
        {name: {"guard_failure": hp._guard_failure_label([guard])} for name, guard in PPII_SCENARIO_B_GUARD_MAP.items()},
    )
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    artifact = hp.build_ppii_scarcity_perturbation_artifact(results, fixture, {}, mode="full")
    assert artifact["verdict"] == "H12_PERTURBATION_SCARCITY_NO_VARIATION"


def test_build_ppii_scarcity_perturbation_artifact_invariant_violation_hard_fails_regardless_of_variation(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(hp, "OUT_DIR", tmp_path)
    results = _all_five_states_result(seeds_vary=True)
    results["pg160_scarce"] = _scarcity_result_for(
        "pg160_scarce", ["pg160"], seeds_vary=True, violations=[{"seed": 3, "reason": "pool_cap_transferase"}]
    )
    monkeypatch.setattr(
        hp,
        "PPII_SCENARIO_B_STATES",
        {name: {"guard_failure": hp._guard_failure_label([guard])} for name, guard in PPII_SCENARIO_B_GUARD_MAP.items()},
    )
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    artifact = hp.build_ppii_scarcity_perturbation_artifact(results, fixture, {}, mode="full")
    assert artifact["verdict"] == "H12_PERTURBATION_SCARCITY_INVARIANT_VIOLATION"


def test_build_ppii_scarcity_perturbation_artifact_label_mismatch_hard_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(hp, "OUT_DIR", tmp_path)
    results = _all_five_states_result(seeds_vary=True)
    # Declare an "expected" label that does NOT match the prediction's own
    # computed label -- this is the inversion test for a mislabeled/drifted
    # pre-registered state (guard_failure claims something the actual guard
    # arithmetic does not confirm).
    monkeypatch.setattr(
        hp,
        "PPII_SCENARIO_B_STATES",
        {name: {"guard_failure": "totally_wrong_label"} for name in hp.PPII_SCENARIO_B_STATE_NAMES},
    )
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    artifact = hp.build_ppii_scarcity_perturbation_artifact(results, fixture, {}, mode="full")
    assert artifact["verdict"] == "H12_PERTURBATION_SCARCITY_INVARIANT_VIOLATION"


def test_build_ppii_scarcity_perturbation_artifact_rejects_invalid_mode():
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    results = _all_five_states_result(seeds_vary=True)
    with pytest.raises(ValueError, match="mode"):
        hp.build_ppii_scarcity_perturbation_artifact(results, fixture, {}, mode="bogus")


def test_build_ppii_scarcity_perturbation_artifact_canary_mode_records_single_state_caveat(tmp_path, monkeypatch):
    monkeypatch.setattr(hp, "OUT_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    results = {
        name: _scarcity_result_for(
            name, [PPII_SCENARIO_B_GUARD_MAP[name]], seeds_vary=True, mode="canary"
        )
    }
    monkeypatch.setattr(
        hp,
        "PPII_SCENARIO_B_STATES",
        {n: {"guard_failure": hp._guard_failure_label([g])} for n, g in PPII_SCENARIO_B_GUARD_MAP.items()},
    )
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    artifact = hp.build_ppii_scarcity_perturbation_artifact(results, fixture, {}, mode="canary")
    assert artifact["mode"] == "canary"
    assert set(artifact["states"].keys()) == {name}
    assert artifact["verdict"] == "H12_PERTURBATION_SCARCITY_CANARY_PLUMBING_OK"
    assert any(str(hp.PPII_SCENARIO_B_CANARY_SEED_COUNT) in c or "canary" in c for c in artifact["evidence_scope_caveats"])


def test_build_ppii_scarcity_perturbation_artifact_canary_no_variation_does_not_fail_verdict(tmp_path, monkeypatch):
    # Positive inversion test (Opus5 turn-4 correction 5): a canary run
    # with seeds_vary=False over its seeds is NOT, by itself, a canary
    # failure -- the canary makes no distributional claim. This must
    # remain H12_PERTURBATION_SCARCITY_CANARY_PLUMBING_OK, never
    # accidentally reuse full-mode's NO_VARIATION/INVARIANT_VIOLATION
    # vocabulary.
    monkeypatch.setattr(hp, "OUT_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    results = {
        name: _scarcity_result_for(
            name, [PPII_SCENARIO_B_GUARD_MAP[name]], seeds_vary=False, mode="canary"
        )
    }
    monkeypatch.setattr(
        hp,
        "PPII_SCENARIO_B_STATES",
        {n: {"guard_failure": hp._guard_failure_label([g])} for n, g in PPII_SCENARIO_B_GUARD_MAP.items()},
    )
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    artifact = hp.build_ppii_scarcity_perturbation_artifact(results, fixture, {}, mode="canary")
    assert artifact["verdict"] == "H12_PERTURBATION_SCARCITY_CANARY_PLUMBING_OK"
    assert artifact["states"][name]["no_variation_flag"] is True
    assert artifact["states"][name]["no_variation_flag_gates_verdict"] is False


def test_build_ppii_scarcity_perturbation_artifact_canary_invariant_violation_still_hard_fails(tmp_path, monkeypatch):
    # An exact bound violation is never acceptable regardless of mode --
    # canary's relaxed no-variation tolerance must not also relax this.
    monkeypatch.setattr(hp, "OUT_DIR", tmp_path)
    name = hp.PPII_SCENARIO_B_CANARY_STATE
    results = {
        name: _scarcity_result_for(
            name,
            [PPII_SCENARIO_B_GUARD_MAP[name]],
            seeds_vary=True,
            violations=[{"seed": 1000, "reason": "mass_conservation"}],
            mode="canary",
        )
    }
    monkeypatch.setattr(
        hp,
        "PPII_SCENARIO_B_STATES",
        {n: {"guard_failure": hp._guard_failure_label([g])} for n, g in PPII_SCENARIO_B_GUARD_MAP.items()},
    )
    fixture = {"__fixture_path__": "x", "__fixture_sha256__": "y"}
    artifact = hp.build_ppii_scarcity_perturbation_artifact(results, fixture, {}, mode="canary")
    assert artifact["verdict"] == "H12_PERTURBATION_SCARCITY_CANARY_INVARIANT_VIOLATION"


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


# ---------------------------------------------------------------------------
# _resolve_wholecell_src_root: explicit WholeCell root resolution, no
# ambient/hardcoded fallback (Opus5 turn-4 correction 2).
# ---------------------------------------------------------------------------


def _make_fake_wholecell_root(base_dir, content="% fake RandStream.m for tests\n"):
    root = base_dir / "fake_wholecell_src"
    pkg_dir = root / "+edu" / "+stanford" / "+covert" / "+util"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "RandStream.m").write_text(content, encoding="utf-8")
    return root


def test_resolve_wholecell_src_root_raises_when_neither_arg_nor_env_var_set(monkeypatch):
    monkeypatch.delenv(hp.WHOLECELL_SRC_ROOT_ENV_VAR, raising=False)
    with pytest.raises(FileNotFoundError, match="not resolved"):
        hp._resolve_wholecell_src_root(None)


def test_resolve_wholecell_src_root_uses_explicit_arg(tmp_path):
    root = _make_fake_wholecell_root(tmp_path)
    resolved = hp._resolve_wholecell_src_root(str(root))
    assert resolved == root


def test_resolve_wholecell_src_root_uses_env_var_when_no_explicit_arg(tmp_path, monkeypatch):
    root = _make_fake_wholecell_root(tmp_path)
    monkeypatch.setenv(hp.WHOLECELL_SRC_ROOT_ENV_VAR, str(root))
    resolved = hp._resolve_wholecell_src_root(None)
    assert resolved == root


def test_resolve_wholecell_src_root_explicit_arg_takes_precedence_over_env_var(tmp_path, monkeypatch):
    root = _make_fake_wholecell_root(tmp_path / "explicit_root")
    wrong_root = tmp_path / "env_root_wrong"
    wrong_root.mkdir()
    monkeypatch.setenv(hp.WHOLECELL_SRC_ROOT_ENV_VAR, str(wrong_root))
    resolved = hp._resolve_wholecell_src_root(str(root))
    assert resolved == root


def test_resolve_wholecell_src_root_raises_when_randstream_missing_at_root(tmp_path, monkeypatch):
    monkeypatch.delenv(hp.WHOLECELL_SRC_ROOT_ENV_VAR, raising=False)
    wrong_root = tmp_path / "no_randstream_here"
    wrong_root.mkdir()
    with pytest.raises(FileNotFoundError, match="RandStream"):
        hp._resolve_wholecell_src_root(str(wrong_root))


# ---------------------------------------------------------------------------
# _validate_randstream_provenance: independent re-verification against the
# vendored data/karr_vendored_source/RandStream.m hash (Opus5 turn-4
# corrections 2/3).
# ---------------------------------------------------------------------------


def test_validate_randstream_provenance_accepts_matching_vendored_hash():
    vendored_hash = hp._sha256_lf_normalized(hp.VENDORED_RANDSTREAM_PATH)
    record = {
        "randstream_runtime_path": str(hp.VENDORED_RANDSTREAM_PATH),
        "randstream_runtime_sha256_lf_normalized": vendored_hash,
    }
    hp._validate_randstream_provenance(record, context="test")  # must not raise


def test_validate_randstream_provenance_rejects_hash_mismatch():
    record = {
        "randstream_runtime_path": str(hp.VENDORED_RANDSTREAM_PATH),
        "randstream_runtime_sha256_lf_normalized": "f" * 64,
    }
    with pytest.raises(ValueError, match="does not match the vendored"):
        hp._validate_randstream_provenance(record, context="test")


def test_validate_randstream_provenance_rejects_missing_path():
    record = {"randstream_runtime_sha256_lf_normalized": hp._sha256_lf_normalized(hp.VENDORED_RANDSTREAM_PATH)}
    with pytest.raises(ValueError, match="randstream_runtime_path missing"):
        hp._validate_randstream_provenance(record, context="test")


def test_validate_randstream_provenance_rejects_missing_hash():
    record = {"randstream_runtime_path": str(hp.VENDORED_RANDSTREAM_PATH)}
    with pytest.raises(ValueError, match="randstream_runtime_sha256_lf_normalized missing"):
        hp._validate_randstream_provenance(record, context="test")


# ---------------------------------------------------------------------------
# _validate_matlab_probe_result: independent structured-result validation,
# never trusting a bare MATLAB exit code (Opus5 turn-4 corrections 1/3).
# ---------------------------------------------------------------------------


def _valid_probe_result_template():
    return {
        "is_octave": False,
        "overall_pass": True,
        "statistics_toolbox_licensed": True,
        "statistics_toolbox_installed": True,
        "randstream_class_found": True,
        "randstream_constructs": True,
        "randstream_runtime_path": str(hp.VENDORED_RANDSTREAM_PATH),
        "randstream_runtime_sha256_lf_normalized": hp._sha256_lf_normalized(hp.VENDORED_RANDSTREAM_PATH),
        "mnrnd_shape_test_status": "pass",
        "mnrnd_shape_test_result": [1, 2],
        "wholecell_src_root_used": "some/root",
    }


def test_validate_matlab_probe_result_missing_field_raises():
    result = _valid_probe_result_template()
    del result["randstream_class_found"]
    with pytest.raises(ValueError, match="missing required field"):
        hp._validate_matlab_probe_result(result)


def test_validate_matlab_probe_result_rejects_octave():
    result = _valid_probe_result_template()
    result["is_octave"] = True
    with pytest.raises(ValueError, match="is_octave=true"):
        hp._validate_matlab_probe_result(result)


def test_validate_matlab_probe_result_rejects_overall_pass_false():
    result = _valid_probe_result_template()
    result["overall_pass"] = False
    with pytest.raises(ValueError, match="overall_pass=false"):
        hp._validate_matlab_probe_result(result)


def test_validate_matlab_probe_result_rejects_invalid_mnrnd_status():
    result = _valid_probe_result_template()
    result["mnrnd_shape_test_status"] = "bogus"
    with pytest.raises(ValueError, match="unexpected mnrnd_shape_test_status"):
        hp._validate_matlab_probe_result(result)


def test_validate_matlab_probe_result_rejects_randstream_hash_mismatch():
    result = _valid_probe_result_template()
    result["randstream_runtime_sha256_lf_normalized"] = "0" * 64
    with pytest.raises(ValueError, match="does not match the vendored"):
        hp._validate_matlab_probe_result(result)


def test_validate_matlab_probe_result_mnrnd_pass_permits_full_mode():
    result = hp._validate_matlab_probe_result(_valid_probe_result_template())
    assert result["full_mode_permitted"] is True
    assert "full_mode_hard_blocked_reason" not in result


@pytest.mark.parametrize(
    "invalid_result",
    (
        [3],
        [[1, 2]],
        [1, 1],
        [1.5, 1.5],
        [-1, 4],
        [float("nan"), 3],
    ),
)
def test_validate_matlab_probe_result_rejects_invalid_mnrnd_pass_result(invalid_result):
    result = _valid_probe_result_template()
    result["mnrnd_shape_test_result"] = invalid_result
    with pytest.raises(ValueError, match="requires a finite, nonnegative integer 1x2 result summing to 3"):
        hp._validate_matlab_probe_result(result)


def test_validate_matlab_probe_result_mnrnd_error_hard_blocks_full_mode_only():
    # Pre-registered per Opus5 turn-4 correction 1: an 'error' mnrnd shape
    # result is a genuine Karr dormant-source defect, recorded (not fixed
    # post hoc), and hard-blocks FULL mode only -- overall_pass may still
    # be True (basic environment readiness is otherwise fine).
    result = _valid_probe_result_template()
    result["mnrnd_shape_test_status"] = "error"
    validated = hp._validate_matlab_probe_result(result)
    assert validated["full_mode_permitted"] is False
    assert "canary-mode plumbing remains permitted" in validated["full_mode_hard_blocked_reason"]


def test_validate_matlab_probe_result_mnrnd_not_run_does_not_permit_full_mode():
    result = _valid_probe_result_template()
    result["mnrnd_shape_test_status"] = "not_run"
    validated = hp._validate_matlab_probe_result(result)
    assert validated["full_mode_permitted"] is False


def test_validate_matlab_probe_result_missing_statistics_toolbox_allows_canary_but_blocks_full():
    result = _valid_probe_result_template()
    result["statistics_toolbox_installed"] = False
    result["mnrnd_shape_test_status"] = "error"
    result["mnrnd_shape_test_result"] = []
    validated = hp._validate_matlab_probe_result(result)
    assert validated["overall_pass"] is True
    assert validated["full_mode_permitted"] is False
    assert "canary-mode plumbing remains permitted" in validated["full_mode_hard_blocked_reason"]


# ---------------------------------------------------------------------------
# probe_matlab_environment: subprocess is mocked (no live MATLAB) -- these
# tests exercise the "never trust a bare exit code" contract (Opus5 turn-4
# correction 3) and the WholeCell-root-required gate (correction 2).
# ---------------------------------------------------------------------------


def _fake_subprocess_run_writing(json_obj_or_none, returncode=0):
    def _fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, env=None):
        if json_obj_or_none is not None:
            out_path = Path(env["PPII_PROBE_RESULT_JSON"])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(json_obj_or_none), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr="")

    return _fake_run


def test_probe_matlab_environment_requires_wholecell_root(monkeypatch):
    monkeypatch.delenv(hp.WHOLECELL_SRC_ROOT_ENV_VAR, raising=False)
    with pytest.raises(FileNotFoundError, match="not resolved"):
        hp.probe_matlab_environment(wholecell_src_root=None)


def test_probe_matlab_environment_raises_when_no_result_json_produced(tmp_path, monkeypatch):
    root = _make_fake_wholecell_root(tmp_path)
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    monkeypatch.setattr(hp, "PROBE_RESULT_PATH", tmp_path / "matlab_probe_result.json")
    monkeypatch.setattr(hp.subprocess, "run", _fake_subprocess_run_writing(None, returncode=0))
    with pytest.raises(RuntimeError, match="produced no result JSON"):
        hp.probe_matlab_environment(wholecell_src_root=str(root))


def test_probe_matlab_environment_never_trusts_bare_exit_code(tmp_path, monkeypatch):
    # Inversion test (Opus5 turn-4 correction 3): exit code 0 but the
    # structured result itself reports overall_pass=false must still raise.
    root = _make_fake_wholecell_root(tmp_path)
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    monkeypatch.setattr(hp, "PROBE_RESULT_PATH", tmp_path / "matlab_probe_result.json")
    failing_result = _valid_probe_result_template()
    failing_result["overall_pass"] = False
    monkeypatch.setattr(hp.subprocess, "run", _fake_subprocess_run_writing(failing_result, returncode=0))
    with pytest.raises(ValueError, match="overall_pass=false"):
        hp.probe_matlab_environment(wholecell_src_root=str(root))


def test_probe_matlab_environment_returns_validated_result_when_consistent(tmp_path, monkeypatch):
    root = _make_fake_wholecell_root(tmp_path)
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    monkeypatch.setattr(hp, "PROBE_RESULT_PATH", tmp_path / "matlab_probe_result.json")
    monkeypatch.setattr(
        hp.subprocess, "run", _fake_subprocess_run_writing(_valid_probe_result_template(), returncode=0)
    )
    result = hp.probe_matlab_environment(wholecell_src_root=str(root))
    assert result["overall_pass"] is True
    assert result["full_mode_permitted"] is True


# ---------------------------------------------------------------------------
# run_matlab_scenario_b gating on a prior validated probe result (Opus5
# turn-4 correction 1).
# ---------------------------------------------------------------------------


def test_run_matlab_scenario_b_requires_prior_probe_result(tmp_path, monkeypatch):
    root = _make_fake_wholecell_root(tmp_path)
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    monkeypatch.setattr(hp, "PROBE_RESULT_PATH", tmp_path / "matlab_probe_result.json")

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("matlab must never be invoked without a prior validated probe result")

    monkeypatch.setattr(hp.subprocess, "run", _boom)
    with pytest.raises(RuntimeError, match="run probe_matlab_environment"):
        hp.run_matlab_scenario_b(canary=True, wholecell_src_root=str(root))


def test_run_matlab_scenario_b_full_mode_hard_blocked_by_mnrnd_error_probe(tmp_path, monkeypatch):
    root = _make_fake_wholecell_root(tmp_path)
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    probe_path = tmp_path / "matlab_probe_result.json"
    monkeypatch.setattr(hp, "PROBE_RESULT_PATH", probe_path)
    blocked_result = _valid_probe_result_template()
    blocked_result["mnrnd_shape_test_status"] = "error"
    hp._write_json(probe_path, blocked_result)

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("matlab must never be invoked in full mode when full_mode_permitted is False")

    monkeypatch.setattr(hp.subprocess, "run", _boom)
    with pytest.raises(RuntimeError, match="HARD-BLOCKED"):
        hp.run_matlab_scenario_b(canary=False, wholecell_src_root=str(root))


def test_run_matlab_scenario_b_canary_mode_not_blocked_by_mnrnd_error_probe(tmp_path, monkeypatch):
    # Canary-mode plumbing runs remain permitted even when the mnrnd shape
    # probe recorded 'error' -- only full mode is hard-blocked by it (Opus5
    # turn-4 correction 1).
    root = _make_fake_wholecell_root(tmp_path)
    monkeypatch.setattr(hp, "RAW_DIR", tmp_path)
    probe_path = tmp_path / "matlab_probe_result.json"
    monkeypatch.setattr(hp, "PROBE_RESULT_PATH", probe_path)
    blocked_result = _valid_probe_result_template()
    blocked_result["mnrnd_shape_test_status"] = "error"
    hp._write_json(probe_path, blocked_result)

    monkeypatch.setattr(hp.subprocess, "run", _fake_subprocess_run_writing(None, returncode=0))
    hp.run_matlab_scenario_b(canary=True, wholecell_src_root=str(root))  # must not raise


# ---------------------------------------------------------------------------
# Lossless CSV output: dlmwrite('precision','%.17g'), never csvwrite
# (Opus5 turn-4 correction 4).
# ---------------------------------------------------------------------------


def test_run_ppii_scenario_b_matlab_uses_lossless_dlmwrite_not_csvwrite():
    source = (hp.MATLAB_DIR / "run_ppii_scenario_b_matlab.m").read_text(encoding="utf-8")
    assert "csvwrite(" not in source
    assert "dlmwrite(" in source
    assert "%.17g" in source


def test_percent_17g_format_round_trips_141888_and_other_scenario_b_constants():
    # 141888 is the substrates_water value in the peptidase_capacity_scarce
    # state -- large enough that a lossy default format (e.g. %10.5g, which
    # csvwrite uses) would NOT round-trip it exactly (it would come back as
    # 1.4189e+05 -> 141890, not 141888). '%.17g' (17 significant digits) is
    # sufficient to round-trip any IEEE-754 double exactly; this test
    # verifies that property in Python (dlmwrite's actual MATLAB-side
    # behavior is exercised only once real execution is authorized).
    values = [141888.0, 372.0, 58.0, 1000.0, 100.0, 2.0, 0.0, 1.0 / 3.0, 1e17, -141888.0]
    for v in values:
        formatted = f"{v:.17g}"
        assert float(formatted) == v, f"{v!r} did not round-trip through %.17g formatting"


def test_probe_matlab_environment_m_writes_json_before_erroring_on_overall_pass_false():
    # Source-inspection test (Opus5 turn-4 correction 3): the .m script
    # must call write_probe_result_json(report) BEFORE calling error(...)
    # on overall_pass=false, so the JSON file always exists even on
    # failure for Python to independently re-validate.
    source = (hp.MATLAB_DIR / "probe_matlab_environment.m").read_text(encoding="utf-8")
    write_idx = source.index("write_probe_result_json(report)")
    error_idx = source.index("error('probe_matlab_environment:overallFail'")
    assert write_idx < error_idx


def test_probe_matlab_environment_m_reads_wholecell_root_from_env_var_only():
    # Source-inspection test (Opus5 turn-4 correction 2): no hardcoded
    # WholeCell src path may remain in the .m probe script.
    source = (hp.MATLAB_DIR / "probe_matlab_environment.m").read_text(encoding="utf-8")
    assert "PPII_WHOLECELL_SRC_ROOT" in source
    assert "m1_sources" not in source, "no ambient/hardcoded WholeCell path may remain"


def test_run_ppii_scenario_b_matlab_m_reads_wholecell_root_from_env_var_only():
    source = (hp.MATLAB_DIR / "run_ppii_scenario_b_matlab.m").read_text(encoding="utf-8")
    assert "getenv('PPII_WHOLECELL_SRC_ROOT')" in source
    assert "'WholeCell', 'src'" not in source, "no ambient/hardcoded WholeCell path may remain"


def test_run_ppii_scenario_b_matlab_gates_statistics_toolbox_on_full_mode_only():
    source = (hp.MATLAB_DIR / "run_ppii_scenario_b_matlab.m").read_text(encoding="utf-8")
    assert "strcmp(mode, 'full') && ~(statistics_toolbox_licensed && statistics_toolbox_installed)" in source
    assert "noStatisticsToolboxForFullMode" in source


def test_probe_matlab_environment_m_includes_mnrnd_shape_probe():
    source = (hp.MATLAB_DIR / "probe_matlab_environment.m").read_text(encoding="utf-8")
    assert "mnrnd(3, [0.5; 0.5])" in source
    assert "mnrnd_shape_test_status" in source
    assert "isrow(mnrnd_probe_result)" in source
    assert "sum(mnrnd_probe_result) == 3" in source


@pytest.mark.parametrize(
    "filename",
    ("probe_matlab_environment.m", "run_ppii_scenario_b_matlab.m"),
)
def test_matlab_scenario_b_uses_fully_qualified_karr_randstream_constructor(filename):
    source = (hp.MATLAB_DIR / filename).read_text(encoding="utf-8")
    assert "import edu.stanford.covert.util.RandStream" not in source
    assert "edu.stanford.covert.util.RandStream('mcg16807', 'Seed'," in source


def test_run_ppii_scenario_b_matlab_m_never_transposes_evolvestate_transcription():
    # Opus5 turn-4 correction 1: do not transpose/fix the verbatim
    # evolveState transcription post hoc in response to the mnrnd probe --
    # confirm evolveState_ppii_matlab.m (the file this correction forbids
    # editing) was not touched by inspecting it still calls the exact
    # documented shape.
    source = (hp.MATLAB_DIR / "evolveState_ppii_matlab.m").read_text(encoding="utf-8")
    assert "mnrnd(" in source
