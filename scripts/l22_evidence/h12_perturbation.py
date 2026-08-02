"""H12 perturbation evidence: pre-registered state perturbations against the
real vendored Karr MacromolecularComplexation/ProteinProcessingII source,
executed via GNU Octave (see scripts/octave_h12_perturbation/README.md),
to exercise the two H12 required branches that never occur in the accepted
natural 50-seed catalog-domain oracle trace:

    - MacromolecularComplexation: network_ge2_fires
    - ProteinProcessingII:        transferase_fires

This module is SEPARATE from and does not modify scripts/l22_evidence/h12.py
or its CATALOG_N_M-gated artifacts (docs/phase_f/l2_2_design_a/h12/
<Process>_h12.json stay byte-for-byte as accepted). It produces its own,
clearly non-gating "perturbation evidence" artifacts under
docs/phase_f/l2_2_design_a/h12/perturbation/, and is NOT consumed by
verdict.py / the H12_CONFIRMED evidence gate. Any promotion of a process's
primary verdict on the strength of this evidence is a reviewer decision,
not something this module or its artifacts perform automatically.

======================================================================
ANTI-LAUNDERING CONTRACT (same two-phase discipline as h12.py)
======================================================================
    PREDICT phase: `predict_protein_processing_ii` (imported, unmodified,
        from scripts/l22_evidence/h12.py) is called with ONLY the
        pre-registered perturbed `states_before` + static fixture params.
        `compute_macromol_network2_bound` below computes the network-2 `ub`
        bound from the pre-registered pool + stoichiometry ONLY -- neither
        function is given the Octave-executed `after` arrays.
    COMPARE / INVARIANT-CHECK phase: only after the above are frozen does
    this module read the Octave-produced raw CSV `after` outputs
    (`ingest_ppii_scenario_a`, `check_macromol_invariants`).
This module is scanned by tests/scripts/test_h12_perturbation.py for the
same forbidden-import/no-early-after-access pattern as h12.py's
predict_* functions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import h12  # noqa: E402

SPEC_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "perturbation" / "PERTURBATION_SPEC.json"
OUT_DIR = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "perturbation"
RAW_DIR = REPO_ROOT / "data" / "m1_sources" / "karr_native" / "h12_perturbation_traces"
OCTAVE_DIR = REPO_ROOT / "scripts" / "octave_h12_perturbation"

HARNESS_FILES = [
    "evolveState_ppii.m",
    "stochasticRoundStub.m",
    "mnrndStub.m",
    "buildProteinComplexs_bounds.m",
    "buildProteinComplexs_rates_collisionTheory.m",
    "buildProteinComplexs_montecarlokinetic.m",
    "run_ppii_scenario_a.m",
    "run_macromol_network2.m",
    "run_ppii_scenario_b.m",
]

N_SEEDS = 50

# Pre-registered scenario values (see PERTURBATION_SPEC.json -- this module
# reads the tracked spec file at runtime, but the literal numbers are also
# duplicated here as plain constants so this module has no silent runtime
# dependency on the JSON's exact key layout for the arithmetic itself; a
# consistency check in generate_inputs() asserts the two agree).
PPII_SCENARIO_A = {
    "enzymes_signalPeptidase": 58.0,
    "enzymes_diacylglycerylTransferase": 372.0,
    "substrates_water": 1000.0,
    "substrates_PG160": 100.0,
    "lipoprotein_first_value": 4.0,
    "secreted_first_value": 1.0,
    "passthrough_first_three_values": [3.0, 2.0, 1.0],
}

MACROMOL_NETWORK2 = {
    "substrate_indices_0b": [23, 37, 42, 192],
    "complex_indices_0b": [22, 23],
    "stoichiometry_block": [[1, 1], [2, 0], [0, 2], [2, 2]],
    "pool_values": [51.0, 34.0, 31.0, 40.0],
}

# Scenario B: multi-state scarcity/mnrnd matrix (see PERTURBATION_SPEC.json
# protein_processing_ii_scenario_b_scarcity_matrix for full derivations).
# Each state deliberately fails exactly one named guard (or, for the
# "simultaneous" state, two guards at once) of predict_protein_processing_
# ii's own regime_valid formula, activating evolveState's dormant scarcity
# branch (stochasticRound capacity scaling and/or mnrnd pool re-allocation)
# -- reusing the SAME fixture-real lipoprotein/secreted index arrays as
# Scenario A, populating only the first 3 (lipoprotein) / 4 (secreted)
# slots per state; passthrough is never perturbed here (already covered by
# the natural trace and Scenario A). Order matters: this is also the
# canary-then-full execution order (water_scarce is the designated canary).
PPII_SCENARIO_B_STATE_NAMES = (
    "water_scarce",
    "pg160_scarce",
    "peptidase_capacity_scarce",
    "transferase_capacity_scarce",
    "simultaneous_peptidase_capacity_and_water_scarce",
)

PPII_SCENARIO_B_STATES = {
    "water_scarce": {
        "enzymes_signalPeptidase": 58.0,
        "enzymes_diacylglycerylTransferase": 372.0,
        "lipoprotein_first3": [0.0, 0.0, 0.0],
        "secreted_first4": [20.0, 15.0, 10.0, 5.0],
        "substrates_water": 30.0,
        "substrates_PG160": 100.0,
        "guard_failure": "water_only",
    },
    "pg160_scarce": {
        "enzymes_signalPeptidase": 58.0,
        "enzymes_diacylglycerylTransferase": 372.0,
        "lipoprotein_first3": [3.0, 1.0, 1.0],
        "secreted_first4": [0.0, 0.0, 0.0, 0.0],
        "substrates_water": 1000.0,
        "substrates_PG160": 3.0,
        "guard_failure": "pg160_only",
    },
    "peptidase_capacity_scarce": {
        "enzymes_signalPeptidase": 1.0,
        "enzymes_diacylglycerylTransferase": 372.0,
        "lipoprotein_first3": [0.0, 0.0, 0.0],
        "secreted_first4": [6.0, 6.0, 4.0, 0.0],
        "substrates_water": 141888.0,
        "substrates_PG160": 100.0,
        "guard_failure": "peptidase_limit_only",
    },
    "transferase_capacity_scarce": {
        "enzymes_signalPeptidase": 58.0,
        "enzymes_diacylglycerylTransferase": 152.0,
        "lipoprotein_first3": [2.0, 2.0, 1.0],
        "secreted_first4": [0.0, 0.0, 0.0, 0.0],
        "substrates_water": 1000.0,
        "substrates_PG160": 100.0,
        "guard_failure": "transferase_limit_only",
    },
    "simultaneous_peptidase_capacity_and_water_scarce": {
        "enzymes_signalPeptidase": 2.0,
        "enzymes_diacylglycerylTransferase": 372.0,
        "lipoprotein_first3": [0.0, 0.0, 0.0],
        "secreted_first4": [15.0, 12.0, 9.0, 6.0],
        "substrates_water": 10.0,
        "substrates_PG160": 100.0,
        "guard_failure": "peptidase_limit_and_water",
    },
}

PPII_SCENARIO_B_CANARY = {"states": ["water_scarce"], "n_seeds": 5}
PPII_SCENARIO_B_FULL = {"states": list(PPII_SCENARIO_B_STATE_NAMES), "n_seeds": 50}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_lf_normalized(path: Path) -> str:
    data = path.read_bytes()
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _load_spec() -> dict:
    if not SPEC_PATH.is_file():
        raise FileNotFoundError(f"perturbation spec missing: {SPEC_PATH} (must be committed before any execution)")
    with open(SPEC_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _harness_hashes() -> dict:
    out = {}
    for name in HARNESS_FILES:
        path = OCTAVE_DIR / name
        if not path.is_file():
            raise FileNotFoundError(f"expected Octave harness file missing: {path}")
        out[name] = _sha256_lf_normalized(path)
    return out


# ---------------------------------------------------------------------------
# Input generation (deterministic, no Octave/oracle involved -- pure
# construction of the pre-registered perturbed initial state from the spec
# constants + static fixture index/rate metadata).
# ---------------------------------------------------------------------------


def build_ppii_scenario_a_state(fixture: dict) -> dict:
    """Construct the full-width perturbed ProteinProcessingII initial state
    described by PERTURBATION_SPEC.json's `protein_processing_ii_scenario_a_
    full_saturating`. Uses ONLY static fixture index/rate metadata (same
    inputs h12.predict_protein_processing_ii itself uses) -- no oracle trace
    data, no Octave/after data.
    """
    lipo_idx = fixture["lipoproteinMonomerIndexs_0b"]
    secr_idx = fixture["secretedMonomerIndexs_0b"]
    passthrough_idx = fixture["unprocessedMonomerIndexs_0b"]
    n_mono = int(lipo_idx.max()) + 1
    n_mono = max(n_mono, int(secr_idx.max()) + 1, int(passthrough_idx.max()) + 1) + 1

    unprocessed = np.zeros(n_mono, dtype=np.float64)
    unprocessed[passthrough_idx[0]] = PPII_SCENARIO_A["passthrough_first_three_values"][0]
    unprocessed[passthrough_idx[1]] = PPII_SCENARIO_A["passthrough_first_three_values"][1]
    unprocessed[passthrough_idx[2]] = PPII_SCENARIO_A["passthrough_first_three_values"][2]
    unprocessed[lipo_idx[0]] = PPII_SCENARIO_A["lipoprotein_first_value"]
    unprocessed[secr_idx[0]] = PPII_SCENARIO_A["secreted_first_value"]

    enzymes = np.zeros(2, dtype=np.float64)
    enzymes[fixture["enzymeIndexs_signalPeptidase_0b"]] = PPII_SCENARIO_A["enzymes_signalPeptidase"]
    enzymes[fixture["enzymeIndexs_diacylglycerylTransferase_0b"]] = PPII_SCENARIO_A[
        "enzymes_diacylglycerylTransferase"
    ]

    substrates = np.zeros(5, dtype=np.float64)
    substrates[fixture["substrateIndexs_water_0b"]] = PPII_SCENARIO_A["substrates_water"]
    substrates[fixture["substrateIndexs_PG160_0b"]] = PPII_SCENARIO_A["substrates_PG160"]

    return {
        "unprocessedMonomers": unprocessed,
        "processedMonomers": np.zeros(n_mono, dtype=np.float64),
        "signalSequenceMonomers": np.zeros(n_mono, dtype=np.float64),
        "enzymes": enzymes,
        "substrates": substrates,
    }


def _ppii_octave_state_lines(state: dict, fixture: dict) -> list[str]:
    """Shared line-builder for a ProteinProcessingII Octave `this0` input
    struct -- factored out so Scenario A and Scenario B input-writers stay
    byte-for-byte consistent in field layout/ordering without duplicating
    the field list. Pure string formatting, no file I/O.
    """
    lines = ["% GENERATED by scripts/l22_evidence/h12_perturbation.py -- do not hand-edit."]
    lines.append(f"this0.unprocessedMonomers = {_octave_col(state['unprocessedMonomers'])};")
    lines.append(f"this0.processedMonomers = {_octave_col(state['processedMonomers'])};")
    lines.append(f"this0.signalSequenceMonomers = {_octave_col(state['signalSequenceMonomers'])};")
    lines.append(f"this0.enzymes = {_octave_col(state['enzymes'])};")
    lines.append(f"this0.substrates = {_octave_col(state['substrates'])};")
    lines.append(f"this0.unprocessedMonomerIndexs = {_octave_col_1b(fixture['unprocessedMonomerIndexs_0b'])};")
    lines.append(f"this0.lipoproteinMonomerIndexs = {_octave_col_1b(fixture['lipoproteinMonomerIndexs_0b'])};")
    lines.append(f"this0.secretedMonomerIndexs = {_octave_col_1b(fixture['secretedMonomerIndexs_0b'])};")
    lines.append(f"this0.enzymeIndexs_signalPeptidase = {fixture['enzymeIndexs_signalPeptidase_0b'] + 1};")
    lines.append(
        f"this0.enzymeIndexs_diacylglycerylTransferase = {fixture['enzymeIndexs_diacylglycerylTransferase_0b'] + 1};"
    )
    lines.append(
        f"this0.lipoproteinSignalPeptidaseSpecificRate = {fixture['lipoproteinSignalPeptidaseSpecificRate']!r};"
    )
    lines.append(
        "this0.lipoproteinDiacylglycerylTransferaseSpecificRate = "
        f"{fixture['lipoproteinDiacylglycerylTransferaseSpecificRate']!r};"
    )
    lines.append(f"this0.stepSizeSec = {fixture['stepSizeSec']!r};")
    lines.append(f"this0.substrateIndexs_water = {fixture['substrateIndexs_water_0b'] + 1};")
    lines.append(f"this0.substrateIndexs_PG160 = {fixture['substrateIndexs_PG160_0b'] + 1};")
    lines.append(f"this0.substrateIndexs_SNGLYP = {fixture['substrateIndexs_SNGLYP_0b'] + 1};")
    lines.append(f"this0.substrateIndexs_hydrogen = {fixture['substrateIndexs_hydrogen_0b'] + 1};")
    return lines


def _write_ppii_octave_state(state: dict, fixture: dict) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    lines = _ppii_octave_state_lines(state, fixture)
    out_path = RAW_DIR / "ppii_scenario_a_state.m"
    out_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return out_path


def _octave_col(arr: np.ndarray) -> str:
    return "[" + "; ".join(repr(float(x)) for x in np.asarray(arr).ravel()) + "]"


def _octave_col_1b(idx0b: np.ndarray) -> str:
    return "[" + "; ".join(str(int(i) + 1) for i in np.asarray(idx0b).ravel()) + "]"


def build_ppii_scenario_b_states(fixture: dict) -> dict:
    """Construct the 5 full-width perturbed ProteinProcessingII initial
    states described by PERTURBATION_SPEC.json's
    `protein_processing_ii_scenario_b_scarcity_matrix`. Uses ONLY static
    fixture index/rate metadata (same inputs h12.predict_protein_
    processing_ii itself uses) plus the PPII_SCENARIO_B_STATES constants
    above -- no oracle trace data, no Octave/after data. Mirrors
    build_ppii_scenario_a_state's index-reuse convention (same fixture
    lipoprotein/secreted arrays, first-N slots populated).
    """
    lipo_idx = fixture["lipoproteinMonomerIndexs_0b"]
    secr_idx = fixture["secretedMonomerIndexs_0b"]
    passthrough_idx = fixture["unprocessedMonomerIndexs_0b"]
    n_mono = int(lipo_idx.max()) + 1
    n_mono = max(n_mono, int(secr_idx.max()) + 1, int(passthrough_idx.max()) + 1) + 1

    states = {}
    for name in PPII_SCENARIO_B_STATE_NAMES:
        spec = PPII_SCENARIO_B_STATES[name]
        unprocessed = np.zeros(n_mono, dtype=np.float64)
        unprocessed[lipo_idx[0]] = spec["lipoprotein_first3"][0]
        unprocessed[lipo_idx[1]] = spec["lipoprotein_first3"][1]
        unprocessed[lipo_idx[2]] = spec["lipoprotein_first3"][2]
        unprocessed[secr_idx[0]] = spec["secreted_first4"][0]
        unprocessed[secr_idx[1]] = spec["secreted_first4"][1]
        unprocessed[secr_idx[2]] = spec["secreted_first4"][2]
        unprocessed[secr_idx[3]] = spec["secreted_first4"][3]

        enzymes = np.zeros(2, dtype=np.float64)
        enzymes[fixture["enzymeIndexs_signalPeptidase_0b"]] = spec["enzymes_signalPeptidase"]
        enzymes[fixture["enzymeIndexs_diacylglycerylTransferase_0b"]] = spec["enzymes_diacylglycerylTransferase"]

        substrates = np.zeros(5, dtype=np.float64)
        substrates[fixture["substrateIndexs_water_0b"]] = spec["substrates_water"]
        substrates[fixture["substrateIndexs_PG160_0b"]] = spec["substrates_PG160"]

        states[name] = {
            "name": name,
            "guard_failure": spec["guard_failure"],
            "unprocessedMonomers": unprocessed,
            "processedMonomers": np.zeros(n_mono, dtype=np.float64),
            "signalSequenceMonomers": np.zeros(n_mono, dtype=np.float64),
            "enzymes": enzymes,
            "substrates": substrates,
        }
    return states


def _write_ppii_scenario_b_octave_states(states: dict, fixture: dict) -> dict:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_paths = {}
    for name, state in states.items():
        lines = _ppii_octave_state_lines(state, fixture)
        out_path = RAW_DIR / f"ppii_scenario_b_{name}_state.m"
        out_path.write_text("\n".join(lines) + "\n", encoding="ascii")
        out_paths[name] = out_path
    return out_paths


def build_macromol_network2_state() -> dict:
    return {
        "pool": np.array(MACROMOL_NETWORK2["pool_values"], dtype=np.float64),
        "block": np.array(MACROMOL_NETWORK2["stoichiometry_block"], dtype=np.float64),
    }


def _write_macromol_octave_state(state: dict) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    pool_str = "[" + "; ".join(repr(float(x)) for x in state["pool"]) + "]"
    block_rows = ["[" + " ".join(repr(float(x)) for x in row) + "]" for row in state["block"]]
    block_str = "[" + "; ".join(block_rows) + "]"
    lines = [
        "% GENERATED by scripts/l22_evidence/h12_perturbation.py generate-inputs -- do not hand-edit.",
        f"pool = {pool_str};",
        f"block = {block_str};",
    ]
    out_path = RAW_DIR / "macromol_network2_state.m"
    out_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return out_path


def generate_inputs() -> dict:
    """PREDICT-phase-adjacent input generation: pure function of the
    pre-registered spec + static fixture metadata. Never touches any
    Octave-produced output (those files, if present from a prior run, are
    not read here).
    """
    spec = _load_spec()
    ppii_fixture = h12.load_fixture("ProteinProcessingII")
    ppii_state = build_ppii_scenario_a_state(ppii_fixture)
    ppii_path = _write_ppii_octave_state(ppii_state, ppii_fixture)

    macromol_fixture = h12.load_fixture("MacromolecularComplexation")
    # Cross-check the spec's claimed network-2 substrate/complex indices
    # against the real fixture's own network assignment (fail loudly if the
    # tracked spec ever drifts from the fixture it claims to describe).
    comp = macromol_fixture["complexComposition"]
    sub_net = macromol_fixture["substrates2complexNetworks"]
    cx_net = macromol_fixture["complexs2complexNetworks"]
    sub_idx = np.where(sub_net == 2)[0].tolist()
    cx_idx = np.where(cx_net == 2)[0].tolist()
    spec_scn = spec["scenarios"]["macromolecular_complexation_network2_competition"]
    if sub_idx != spec_scn["substrate_indices_0b"] or cx_idx != spec_scn["complex_indices_0b"]:
        raise ValueError(
            f"PERTURBATION_SPEC.json network-2 indices {spec_scn['substrate_indices_0b']!r}/"
            f"{spec_scn['complex_indices_0b']!r} no longer match the real fixture's "
            f"({sub_idx!r}/{cx_idx!r}) -- fixture drift, spec must be re-derived, not silently trusted"
        )
    block_real = comp[np.ix_(sub_idx, cx_idx)].astype(np.float64).tolist()
    if block_real != spec_scn["stoichiometry_block"]:
        raise ValueError("PERTURBATION_SPEC.json stoichiometry_block no longer matches the real fixture")

    macromol_state = build_macromol_network2_state()
    macromol_path = _write_macromol_octave_state(macromol_state)

    return {
        "ppii_state_path": ppii_path,
        "macromol_state_path": macromol_path,
        "ppii_state_sha256": _sha256_file(ppii_path),
        "macromol_state_sha256": _sha256_file(macromol_path),
    }


def generate_inputs_scenario_b() -> dict:
    """PREDICT-phase-adjacent input generation for Scenario B (the scarcity
    matrix) ONLY -- pure function of the pre-registered spec + static
    fixture metadata, entirely separate from generate_inputs() (Scenario A
    / macromol network2), which this function does not call or modify.
    Never touches any Octave-produced output.
    """
    spec = _load_spec()
    ppii_fixture = h12.load_fixture("ProteinProcessingII")
    spec_states = spec["scenarios"]["protein_processing_ii_scenario_b_scarcity_matrix"]["states"]
    for name in PPII_SCENARIO_B_STATE_NAMES:
        spec_state = spec_states[name]
        module_state = PPII_SCENARIO_B_STATES[name]
        if spec_state["guard_failure"] != module_state["guard_failure"]:
            raise ValueError(
                f"PERTURBATION_SPEC.json scenario B state {name!r} guard_failure "
                f"{spec_state['guard_failure']!r} no longer matches module constant "
                f"{module_state['guard_failure']!r} -- spec/module drift, must be re-derived, not silently trusted"
            )
        for key in (
            "enzymes_signalPeptidase",
            "enzymes_diacylglycerylTransferase",
            "substrates_water",
            "substrates_PG160",
        ):
            if float(spec_state[key]) != float(module_state[key]):
                raise ValueError(f"PERTURBATION_SPEC.json scenario B state {name!r} field {key!r} drifted from module constant")
        if list(spec_state["unprocessedMonomers_lipoprotein_first3"]) != list(module_state["lipoprotein_first3"]):
            raise ValueError(f"PERTURBATION_SPEC.json scenario B state {name!r} lipoprotein_first3 drifted from module constant")
        if list(spec_state["unprocessedMonomers_secreted_first4"]) != list(module_state["secreted_first4"]):
            raise ValueError(f"PERTURBATION_SPEC.json scenario B state {name!r} secreted_first4 drifted from module constant")

    states = build_ppii_scenario_b_states(ppii_fixture)
    paths = _write_ppii_scenario_b_octave_states(states, ppii_fixture)
    return {
        "ppii_scenario_b_state_paths": {name: str(p) for name, p in paths.items()},
        "ppii_scenario_b_state_sha256": {name: _sha256_file(p) for name, p in paths.items()},
    }


# ---------------------------------------------------------------------------
# Octave invocation
# ---------------------------------------------------------------------------


def run_octave_scenario(script_name: str) -> None:
    result = subprocess.run(
        ["octave", "--no-gui", "--quiet", script_name],
        cwd=str(OCTAVE_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    sys.stderr.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"octave {script_name} failed with exit code {result.returncode}")


def run_octave_scenario_b(canary: bool) -> None:
    """Invoke run_ppii_scenario_b.m in either canary mode (1 state x 5
    seeds) or full mode (5 states x 50 seeds), selected via the
    PPII_SCENARIO_B_MODE environment variable the .m driver reads.

    NOT CALLED by anything in this commit -- implemented so canary/full
    execution is a single, reviewable, pre-registered code path ready for
    invocation only after explicit GPT-5.6 Sol authorization following
    Opus5 review (see PERTURBATION_SPEC.json scenario_b_execution_status).
    """
    env = dict(os.environ)
    env["PPII_SCENARIO_B_MODE"] = "canary" if canary else "full"
    result = subprocess.run(
        ["octave", "--no-gui", "--quiet", "run_ppii_scenario_b.m"],
        cwd=str(OCTAVE_DIR),
        capture_output=True,
        text=True,
        timeout=120 if canary else 900,
        env=env,
    )
    sys.stderr.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"octave run_ppii_scenario_b.m ({env['PPII_SCENARIO_B_MODE']}) failed with exit code {result.returncode}")


# ---------------------------------------------------------------------------
# Ingest + compare (COMPARE phase: reads Octave `after` output; must run
# strictly after generate_inputs()/run_octave_scenario() and never feeds
# `after` data back into a predict_* call).
# ---------------------------------------------------------------------------


def ingest_ppii_scenario_a(fixture: dict) -> dict:
    state = build_ppii_scenario_a_state(fixture)  # PREDICT phase: before-only
    n_mono = state["unprocessedMonomers"].shape[0]
    n_sub = state["substrates"].shape[0]

    before = {
        "unprocessedMonomers": np.tile(state["unprocessedMonomers"], (N_SEEDS, 1)),
        "enzymes": np.tile(state["enzymes"], (N_SEEDS, 1)),
        "substrates": np.tile(state["substrates"], (N_SEEDS, 1)),
    }
    predictions = h12.predict_protein_processing_ii(seed=0, before=before, fixture=fixture)
    # ---- predictions are now FROZEN; only now do we read Octave's after ----

    csv_path = RAW_DIR / "ppii_scenario_a_after.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"Octave output missing: {csv_path} (run run_ppii_scenario_a.m first)")
    raw = np.loadtxt(csv_path, delimiter=",")
    if raw.ndim == 1:
        raw = raw.reshape(1, -1)
    if raw.shape != (N_SEEDS, 3 * n_mono + n_sub):
        raise ValueError(f"unexpected Octave output shape {raw.shape}, expected {(N_SEEDS, 3 * n_mono + n_sub)}")

    after = {
        "unprocessedMonomers": raw[:, 0:n_mono],
        "processedMonomers": raw[:, n_mono : 2 * n_mono],
        "signalSequenceMonomers": raw[:, 2 * n_mono : 3 * n_mono],
        "substrates": raw[:, 3 * n_mono : 3 * n_mono + n_sub],
        # evolveState never mutates enzymes in this process; the Octave
        # harness's `this` struct carries the SAME (unperturbed) enzyme
        # vector through unchanged, matching the predictor's own
        # all-zero-delta "enzymes" channel.
        "enzymes": before["enzymes"],
    }
    before_full = {
        "unprocessedMonomers": before["unprocessedMonomers"],
        "processedMonomers": np.tile(state["processedMonomers"], (N_SEEDS, 1)),
        "signalSequenceMonomers": np.tile(state["signalSequenceMonomers"], (N_SEEDS, 1)),
        "substrates": before["substrates"],
        "enzymes": before["enzymes"],
    }
    result = h12.compare_predictions("ProteinProcessingII", predictions, after, before_full)
    result["raw_csv_sha256"] = _sha256_file(csv_path)
    return result


# ---------------------------------------------------------------------------
# Scenario B: scarcity/mnrnd matrix -- PREDICT-phase bound computation and
# COMPARE-phase invariant checking. Unlike Scenario A (which reuses h12's
# closed-form predict_protein_processing_ii directly, since that branch's
# regime_valid is True and the deltas are exact point predictions),
# Scenario B's states are all regime_valid=False by construction, so
# predict_protein_processing_ii itself only asserts "nothing predicted"
# (empty predicted_delta) -- it does not model the scarcity/mnrnd math at
# all. The functions below independently compute the ALGEBRAIC BOUNDS that
# must hold regardless of which stochastic path is realized (see
# PERTURBATION_SPEC.json evidence_contract), which is a strictly weaker
# but exact (zero-tolerance) claim than a point prediction.
# ---------------------------------------------------------------------------


def guard_diagnostics_ppii(unprocessed: np.ndarray, enzymes: np.ndarray, water: float, pg160: float, fixture: dict) -> dict:
    """Pure per-guard boolean breakdown of predict_protein_processing_ii's
    own `regime_valid` formula (h12.py, lines ~684-690) -- replicated here
    (not imported) ONLY to expose which of the four guard components
    (peptidase_limit, transferase_limit, water, pg160) failed, since the
    accepted predictor collapses all four into a single boolean. Used both
    to compute Scenario B's frozen bound-prediction and, independently, by
    tests/scripts/test_h12_perturbation.py to cross-check each
    pre-registered state's declared single-cause (or dual-cause) failure
    label against this same formula. Before-state (+fixture) only; never
    touches after/Octave/oracle data.
    """
    lipoprotein_idx = fixture["lipoproteinMonomerIndexs_0b"]
    secreted_idx = fixture["secretedMonomerIndexs_0b"]
    peptidase_idx = np.concatenate([lipoprotein_idx, secreted_idx])
    transferase_idx = lipoprotein_idx

    peptidase_demand = float(unprocessed[peptidase_idx].sum())
    transferase_demand = float(unprocessed[transferase_idx].sum())
    peptidase_limit = float(
        enzymes[fixture["enzymeIndexs_signalPeptidase_0b"]]
        * fixture["lipoproteinSignalPeptidaseSpecificRate"]
        * fixture["stepSizeSec"]
    )
    transferase_limit = float(
        enzymes[fixture["enzymeIndexs_diacylglycerylTransferase_0b"]]
        * fixture["lipoproteinDiacylglycerylTransferaseSpecificRate"]
        * fixture["stepSizeSec"]
    )

    peptidase_ok = peptidase_limit >= peptidase_demand
    transferase_ok = transferase_demand == 0.0 or transferase_limit >= transferase_demand
    water_ok = water >= peptidase_demand
    pg160_ok = transferase_demand == 0.0 or pg160 >= transferase_demand
    regime_valid = peptidase_ok and transferase_ok and water_ok and pg160_ok
    failed_guards = [
        name
        for name, ok in (
            ("peptidase_limit", peptidase_ok),
            ("transferase_limit", transferase_ok),
            ("water", water_ok),
            ("pg160", pg160_ok),
        )
        if not ok
    ]
    return {
        "regime_valid": regime_valid,
        "failed_guards": failed_guards,
        "peptidase_demand": peptidase_demand,
        "transferase_demand": transferase_demand,
        "peptidase_limit": peptidase_limit,
        "transferase_limit": transferase_limit,
        "water_before": water,
        "pg160_before": pg160,
    }


def _guard_failure_label(failed_guards: list) -> str:
    failed = set(failed_guards)
    if failed == {"water"}:
        return "water_only"
    if failed == {"pg160"}:
        return "pg160_only"
    if failed == {"peptidase_limit"}:
        return "peptidase_limit_only"
    if failed == {"transferase_limit"}:
        return "transferase_limit_only"
    if failed == {"peptidase_limit", "water"}:
        return "peptidase_limit_and_water"
    if not failed:
        return "none"
    return "+".join(sorted(failed))


def predict_ppii_scarcity_bounds(state: dict, fixture: dict) -> dict:
    """PREDICT phase (before-only): for ONE pre-registered Scenario B
    state, compute the algebraically-guaranteed exact BOUNDS on
    evolveState_ppii's output (mass conservation, non-negativity,
    per-species cap, pool caps) -- NOT point predictions (species-level
    allocation under stochasticRound/mnrnd is a distributional-only claim,
    checked separately by evaluate_ppii_scarcity_invariants's cross-seed-
    variation check). Never reads any Octave/after output.
    """
    unprocessed = state["unprocessedMonomers"]
    enzymes = state["enzymes"]
    water = float(state["substrates"][fixture["substrateIndexs_water_0b"]])
    pg160 = float(state["substrates"][fixture["substrateIndexs_PG160_0b"]])
    diag = guard_diagnostics_ppii(unprocessed, enzymes, water, pg160, fixture)

    lipoprotein_idx = fixture["lipoproteinMonomerIndexs_0b"]
    secreted_idx = fixture["secretedMonomerIndexs_0b"]
    peptidase_idx = np.concatenate([lipoprotein_idx, secreted_idx])
    transferase_idx = lipoprotein_idx

    return {
        "state_name": state.get("name"),
        "guard_diagnostics": diag,
        "guard_failure_label": _guard_failure_label(diag["failed_guards"]),
        "peptidase_idx": peptidase_idx.tolist(),
        "transferase_idx": transferase_idx.tolist(),
        "total_unprocessed_mass_before": float(unprocessed.sum()),
        "water_before": water,
        "pg160_before": pg160,
        "bounds": {
            "mass_conservation_exact": True,
            "non_negativity_exact": True,
            "per_species_cap_exact": True,
            "pool_cap_peptidase_exact_bound": water,
            "pool_cap_transferase_exact_bound": pg160,
        },
    }


def evaluate_ppii_scarcity_invariants(before: dict, raw: np.ndarray, fixture: dict) -> dict:
    """Pure invariant-check (no file I/O) over an already-loaded `raw`
    (n_seeds x (3*n_mono + n_sub)) after-state matrix for ONE Scenario B
    state, given its frozen `before` state. Checks the four exact zero-
    tolerance bound claims from PERTURBATION_SPEC.json's evidence_contract
    (mass_conservation, non_negativity, per_species_cap, pool_cap_*) plus
    the distributional-only cross-seed species_allocation variation check
    (mnrnd/stochasticRound must not degenerate into a no-op). Directly
    unit-testable with synthetic clean/violating/degenerate `raw` arrays.
    """
    unproc0 = before["unprocessedMonomers"]
    n_mono = unproc0.shape[0]
    n_sub = before["substrates"].shape[0]
    n_seeds = raw.shape[0]
    water_0b = fixture["substrateIndexs_water_0b"]
    pg160_0b = fixture["substrateIndexs_PG160_0b"]
    lipoprotein_idx = fixture["lipoproteinMonomerIndexs_0b"]
    secreted_idx = fixture["secretedMonomerIndexs_0b"]
    peptidase_idx = np.concatenate([lipoprotein_idx, secreted_idx])
    transferase_idx = lipoprotein_idx

    water_before = float(before["substrates"][water_0b])
    pg160_before = float(before["substrates"][pg160_0b])
    mass_before = float(unproc0.sum())

    violations = []
    for seed in range(n_seeds):
        row = raw[seed]
        unproc_after = row[0:n_mono]
        processed_after = row[n_mono : 2 * n_mono]
        signal_after = row[2 * n_mono : 3 * n_mono]
        substrates_after = row[3 * n_mono : 3 * n_mono + n_sub]

        mass_after = float(unproc_after.sum() + processed_after.sum())
        if mass_after != mass_before:
            violations.append(
                {"seed": seed, "reason": "mass_conservation", "mass_before": mass_before, "mass_after": mass_after}
            )
        if (
            np.any(unproc_after < 0)
            or np.any(processed_after < 0)
            or np.any(signal_after < 0)
            or np.any(substrates_after < 0)
        ):
            violations.append({"seed": seed, "reason": "non_negativity"})
        if np.any(processed_after > unproc0):
            violations.append({"seed": seed, "reason": "per_species_cap"})
        peptidase_processed_sum = float(processed_after[peptidase_idx].sum())
        transferase_processed_sum = float(processed_after[transferase_idx].sum())
        if peptidase_processed_sum > water_before:
            violations.append(
                {
                    "seed": seed,
                    "reason": "pool_cap_peptidase",
                    "sum": peptidase_processed_sum,
                    "water_before": water_before,
                }
            )
        if transferase_processed_sum > pg160_before:
            violations.append(
                {
                    "seed": seed,
                    "reason": "pool_cap_transferase",
                    "sum": transferase_processed_sum,
                    "pg160_before": pg160_before,
                }
            )

    per_species_processed = raw[:, n_mono : 2 * n_mono]
    distinct_outcomes = {tuple(row.tolist()) for row in per_species_processed}
    return {
        "n_seeds": n_seeds,
        "violations": violations,
        "seeds_vary": len(distinct_outcomes) > 1,
        "distinct_outcome_count": len(distinct_outcomes),
        "mass_before": mass_before,
        "water_before": water_before,
        "pg160_before": pg160_before,
    }


def ingest_ppii_scenario_b(fixture: dict) -> dict:
    """COMPARE phase for all 5 Scenario B states: freezes each state's
    predict_ppii_scarcity_bounds prediction BEFORE reading that state's
    Octave-produced `after` CSV (ppii_scenario_b_<name>_after.csv). Raises
    FileNotFoundError per-state if that state's Octave run has not been
    executed yet (expected/required in this turn -- no Octave run has
    occurred).
    """
    states = build_ppii_scenario_b_states(fixture)  # PREDICT phase: before-only
    results = {}
    for name, state in states.items():
        n_mono = state["unprocessedMonomers"].shape[0]
        n_sub = state["substrates"].shape[0]
        prediction = predict_ppii_scarcity_bounds(state, fixture)
        # ---- prediction now FROZEN; only now do we read Octave's after ----

        csv_path = RAW_DIR / f"ppii_scenario_b_{name}_after.csv"
        if not csv_path.is_file():
            raise FileNotFoundError(
                f"Octave output missing: {csv_path} (run run_ppii_scenario_b.m first -- "
                "NOT YET AUTHORIZED this turn, see PERTURBATION_SPEC.json scenario_b_execution_status)"
            )
        raw = np.loadtxt(csv_path, delimiter=",")
        if raw.ndim == 1:
            raw = raw.reshape(1, -1)
        if raw.shape[1] != 3 * n_mono + n_sub:
            raise ValueError(
                f"unexpected Octave output shape {raw.shape} for state {name!r}, "
                f"expected (*, {3 * n_mono + n_sub})"
            )

        before = {
            "unprocessedMonomers": state["unprocessedMonomers"],
            "substrates": state["substrates"],
        }
        invariant_result = evaluate_ppii_scarcity_invariants(before, raw, fixture)
        invariant_result["raw_csv_sha256"] = _sha256_file(csv_path)
        results[name] = {"prediction": prediction, "invariants": invariant_result}
    return results


def compute_macromol_network2_ub(pool: np.ndarray, block: np.ndarray) -> np.ndarray:
    """Pure `ub = floor(min(pool/block))` bound computation (verbatim
    `buildProteinComplexs_bounds` formula, MacromolecularComplexation.m
    lines 390-392) -- takes ONLY the pre-registered pool/stoichiometry, no
    Octave/after data. Factored out for direct unit testing.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(block > 0, pool[:, None] / np.where(block > 0, block, 1.0), np.inf)
    ub = np.floor(np.min(ratio, axis=0))
    ub = np.where(np.isfinite(ub), ub, 0.0)
    return np.maximum(ub, 0.0).astype(np.int64)


def evaluate_macromol_invariants(pool: np.ndarray, block: np.ndarray, ub: np.ndarray, raw: np.ndarray) -> dict:
    """Pure invariant evaluation over an already-loaded `raw` (n_seeds x
    n_complexes) built-complex-count matrix: non-negative integer, <= ub,
    mass-balance (remaining pool >= 0), and cross-seed variation. Factored
    out (no file I/O) for direct unit testing with synthetic `raw` arrays,
    including deliberately-violating ones.
    """
    n_seeds = raw.shape[0]
    violations = []
    remaining_negative = []
    for seed in range(n_seeds):
        built = raw[seed]
        if np.any(built < 0) or np.any(built != np.round(built)):
            violations.append({"seed": seed, "reason": "non_nonneg_integer", "built": built.tolist()})
            continue
        if np.any(built > ub):
            violations.append({"seed": seed, "reason": "exceeds_ub", "built": built.tolist(), "ub": ub.tolist()})
        remaining = pool - block @ built
        if np.any(remaining < 0):
            remaining_negative.append({"seed": seed, "remaining": remaining.tolist()})

    distinct_outcomes = {tuple(row.tolist()) for row in raw}
    return {
        "ub": ub.tolist(),
        "n_seeds": n_seeds,
        "bound_violations": violations,
        "mass_balance_violations": remaining_negative,
        "distinct_outcome_count": len(distinct_outcomes),
        "seeds_vary": len(distinct_outcomes) > 1,
        "min_built_per_complex": raw.min(axis=0).tolist(),
        "max_built_per_complex": raw.max(axis=0).tolist(),
        "mean_built_per_complex": raw.mean(axis=0).tolist(),
    }


def check_macromol_invariants() -> dict:
    state = build_macromol_network2_state()  # PREDICT/bound phase: before-only
    pool = state["pool"]
    block = state["block"]
    ub = compute_macromol_network2_ub(pool, block)
    # ---- ub is now FROZEN (computed from pre-registered pool/block only) ----

    csv_path = RAW_DIR / "macromol_network2_after.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"Octave output missing: {csv_path} (run run_macromol_network2.m first)")
    raw = np.loadtxt(csv_path, delimiter=",")
    if raw.ndim == 1:
        raw = raw.reshape(1, -1)
    n_complexes = block.shape[1]
    if raw.shape != (N_SEEDS, n_complexes):
        raise ValueError(f"unexpected Octave output shape {raw.shape}, expected {(N_SEEDS, n_complexes)}")

    result = evaluate_macromol_invariants(pool, block, ub, raw)
    result["raw_csv_sha256"] = _sha256_file(csv_path)
    return result


# ---------------------------------------------------------------------------
# Artifact building
# ---------------------------------------------------------------------------


def build_ppii_perturbation_artifact(compare_result: dict, ppii_fixture: dict, generated: dict) -> dict:
    nontrivial = compare_result["nontrivial_sample_count"]
    exact = compare_result["exact_match_count"]
    verdict = (
        "H12_PERTURBATION_CONFIRMED"
        if (nontrivial > 0 and exact == nontrivial and compare_result["trivial_mismatch_count"] == 0)
        else "H12_PERTURBATION_FAIL"
    )
    return {
        "artifact_kind": "h12_perturbation_evidence",
        "gating": "NON_GATING -- not consumed by verdict.py / the H12_CONFIRMED evidence gate; a "
        "reviewer decision is required to fold this into the primary H12 artifact/catalog.",
        "process": "ProteinProcessingII",
        "scenario": "protein_processing_ii_scenario_a_full_saturating",
        "perturbation_spec_path": SPEC_PATH.relative_to(REPO_ROOT).as_posix(),
        "perturbation_spec_sha256_lf_normalized": _sha256_lf_normalized(SPEC_PATH),
        "execution_engine": "GNU Octave 6.4.0 (see scripts/octave_h12_perturbation/README.md RNG-fidelity "
        "caveat -- this scenario is constructed so stochasticRound/mnrnd are provable no-ops regardless of "
        "RNG algorithm/seed, so the harness stub's RNG behavior is irrelevant here)",
        "harness_source_hashes": _harness_hashes(),
        "evidence_scope_caveats": [
            "effective N=1 distinct pre-registered before-state: all 50 seeds are independent RNG "
            "realizations of the SAME frozen initial state (PERTURBATION_SPEC.json), not 50 distinct "
            "states -- this is sufficient to demonstrate the branch fires and exact-matches under this one "
            "constructed regime, not general robustness across arbitrary states.",
            "the regime is provably RNG-invariant by construction (frac(x)==0 for every transformed "
            "quantity), so this scenario provides no evidence about RNG/enzyme-kinetics interaction in any "
            "other (non-saturating) regime of this process -- enzyme-kinetics stochasticity itself is "
            "unmeasured here.",
            "the scarcity-guard branch (insufficient peptidase/transferase capacity or water/PG160) is "
            "validated only by a synthetic Python unit test against the predictor's own guard arithmetic "
            "(tests/scripts/test_h12_perturbation.py), not by this or any Octave execution -- see "
            "PERTURBATION_SPEC.json explicitly_out_of_scope_for_octave_execution.",
            "this artifact is OBSERVED evidence for one constructed regime, not a general confirmation "
            "claim; it remains NON_GATING regardless.",
        ],
        "predictor_source_path": "scripts/l22_evidence/h12.py",
        "predictor_source_sha256_lf_normalized": _sha256_lf_normalized(REPO_ROOT / "scripts" / "l22_evidence" / "h12.py"),
        "karr_source_citation": h12.karr_source_citation("ProteinProcessingII"),
        "fixture_path": ppii_fixture["__fixture_path__"],
        "fixture_sha256": ppii_fixture["__fixture_sha256__"],
        "generated_input_sha256": {
            "ppii_scenario_a_state.m": generated["ppii_state_sha256"],
        },
        "n_seeds": N_SEEDS,
        "seeds": list(range(N_SEEDS)),
        "total_sample_count": compare_result["total_sample_count"],
        "nontrivial_sample_count": nontrivial,
        "exact_match_count": exact,
        "exact_match_rate": (exact / nontrivial) if nontrivial > 0 else None,
        "trivial_checked_count": compare_result["trivial_checked_count"],
        "trivial_mismatch_count": compare_result["trivial_mismatch_count"],
        "mismatch_examples": compare_result["mismatch_examples"],
        "branches_confirmed": sorted(compare_result["branches_confirmed"]),
        "target_branch": "transferase_fires",
        "target_branch_confirmed": "transferase_fires" in compare_result["branches_confirmed"],
        "raw_octave_output_sha256": compare_result["raw_csv_sha256"],
        "verdict": verdict,
        "verdict_reason": (
            f"{exact}/{nontrivial} nontrivial samples exact-matched across {N_SEEDS} independent RNG seeds "
            f"of the SAME pre-registered perturbed initial state (regime is provably RNG-independent by "
            f"construction -- see PERTURBATION_SPEC.json); trivial_mismatch_count="
            f"{compare_result['trivial_mismatch_count']}."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anti_laundering_attestation": {
            "predictor_inputs": ["states_before", "static_fixture_params", "perturbation_spec_constants"],
            "states_after_access": "compare_phase_only",
            "no_sut_import": True,
            "no_result_json_access": True,
        },
    }


def build_ppii_scarcity_perturbation_artifact(results: dict, ppii_fixture: dict, generated: dict) -> dict:
    """Build the Scenario B (scarcity matrix) artifact from
    ingest_ppii_scenario_b's per-state {prediction, invariants} results.

    Verdict vocabulary is DISJOINT from both h12.py's H12_CONFIRMED and
    Scenario A's H12_PERTURBATION_CONFIRMED, since Scenario B never claims
    an exact point-match -- only bound invariants (exact) plus genuine
    cross-seed stochastic variation (distributional, non-degenerate):
        H12_PERTURBATION_SCARCITY_OBSERVED_STOCHASTIC: all invariants held
            in every state, AND every state exercising a real stochastic
            mechanism (per its guard_diagnostics) showed genuine cross-
            seed variation (mnrnd/stochasticRound did not degenerate into
            a no-op).
        H12_PERTURBATION_SCARCITY_NO_VARIATION: all invariants held, but at
            least one state's stochastic mechanism produced IDENTICAL
            output across all seeds -- this is the anti-laundering catch
            for a mutated/reused/global RNG stream or a state that
            silently failed to reach the intended branch.
        H12_PERTURBATION_SCARCITY_INVARIANT_VIOLATION: any exact bound
            (mass/non-negativity/per-species-cap/pool-cap) was violated in
            any seed of any state -- hard fail regardless of variation.
    """
    any_violation = False
    any_degenerate = False
    per_state_summary = {}
    for name, r in results.items():
        pred = r["prediction"]
        inv = r["invariants"]
        violated = len(inv["violations"]) > 0
        # A state's stochastic mechanism is expected to fire (per its
        # hand-traced mechanics, see PERTURBATION_SPEC.json) whenever its
        # guard failed at all (every Scenario B state fails at least one
        # guard by construction, so every state is expected to show
        # variation -- a flat/no-variation result on ANY of them is a
        # laundering red flag, not an acceptable "this state happens not
        # to be stochastic" case).
        expected_to_vary = len(pred["guard_diagnostics"]["failed_guards"]) > 0
        degenerate = expected_to_vary and not inv["seeds_vary"]
        any_violation = any_violation or violated
        any_degenerate = any_degenerate or degenerate
        per_state_summary[name] = {
            "guard_failure_label": pred["guard_failure_label"],
            "expected_guard_failure_label": PPII_SCENARIO_B_STATES[name]["guard_failure"],
            "guard_failure_label_matches_prereg": (
                pred["guard_failure_label"] == PPII_SCENARIO_B_STATES[name]["guard_failure"]
            ),
            "regime_valid": pred["guard_diagnostics"]["regime_valid"],
            "n_seeds": inv["n_seeds"],
            "violations": inv["violations"],
            "seeds_vary": inv["seeds_vary"],
            "distinct_outcome_count": inv["distinct_outcome_count"],
            "expected_to_vary": expected_to_vary,
            "no_variation_flag": degenerate,
            "raw_octave_output_sha256": inv["raw_csv_sha256"],
        }

    label_mismatch = any(
        not s["guard_failure_label_matches_prereg"] for s in per_state_summary.values()
    )
    if any_violation or label_mismatch:
        verdict = "H12_PERTURBATION_SCARCITY_INVARIANT_VIOLATION"
    elif any_degenerate:
        verdict = "H12_PERTURBATION_SCARCITY_NO_VARIATION"
    else:
        verdict = "H12_PERTURBATION_SCARCITY_OBSERVED_STOCHASTIC"

    return {
        "artifact_kind": "h12_perturbation_evidence",
        "gating": "NON_GATING -- distributional/bound evidence only; NEVER claims H12_CONFIRMED or "
        "H12_PERTURBATION_CONFIRMED (Scenario A's exact-match vocabulary). Not consumed by verdict.py / "
        "the H12_CONFIRMED evidence gate. Recommends (does not enact) a condition-gated terminal profile "
        "-- see PROTEINPROCESSINGII_SCENARIO_B_PROPOSAL.md.",
        "process": "ProteinProcessingII",
        "scenario": "protein_processing_ii_scenario_b_scarcity_matrix",
        "perturbation_spec_path": SPEC_PATH.relative_to(REPO_ROOT).as_posix(),
        "perturbation_spec_sha256_lf_normalized": _sha256_lf_normalized(SPEC_PATH),
        "execution_engine": "GNU Octave 6.4.0 (see scripts/octave_h12_perturbation/README.md RNG-fidelity "
        "caveat -- this scenario deliberately EXERCISES stochasticRound/mnrnd, so no bit-exact-RNG claim is "
        "made; evidence is bound-exact (algebraic invariants) plus distributional (genuine cross-seed "
        "variation), never point-exact-match.)",
        "harness_source_hashes": _harness_hashes(),
        "evidence_scope_caveats": [
            "5 distinct pre-registered before-states (not 1 state x 50 seeds like Scenario A) -- each "
            "isolates one guard-failure cause (or, for the simultaneous state, two at once); this is "
            "still a finite, hand-selected matrix, not exhaustive coverage of the scarcity regime's "
            "input space.",
            "species-level allocation under stochasticRound/mnrnd is NOT claimed as an exact point "
            "prediction anywhere in this artifact -- only the four algebraic bound invariants (exact, "
            "zero tolerance) and non-degenerate cross-seed variation (distributional) are claimed.",
            "this artifact is OBSERVED_STOCHASTIC/NO_VARIATION/INVARIANT_VIOLATION evidence only; it "
            "NEVER claims H12_CONFIRMED or H12_PERTURBATION_CONFIRMED and remains NON_GATING regardless "
            "of its verdict.",
        ],
        "predictor_source_path": "scripts/l22_evidence/h12_perturbation.py",
        "predictor_source_sha256_lf_normalized": _sha256_lf_normalized(
            REPO_ROOT / "scripts" / "l22_evidence" / "h12_perturbation.py"
        ),
        "karr_source_citation": h12.karr_source_citation("ProteinProcessingII"),
        "fixture_path": ppii_fixture["__fixture_path__"],
        "fixture_sha256": ppii_fixture["__fixture_sha256__"],
        "generated_input_sha256": generated.get("ppii_scenario_b_state_sha256", {}),
        "states": per_state_summary,
        "target_branch": "transferase_fires_scarcity_regime (and peptidase-side mnrnd/stochasticRound)",
        "verdict": verdict,
        "verdict_reason": (
            f"{len(per_state_summary)} pre-registered scarcity states checked; "
            f"any_bound_violation={any_violation}; any_no_variation={any_degenerate}; "
            f"any_guard_label_mismatch={label_mismatch}."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anti_laundering_attestation": {
            "predictor_inputs": ["states_before", "static_fixture_params", "perturbation_spec_constants"],
            "states_after_access": "compare_phase_only",
            "no_sut_import": True,
            "no_result_json_access": True,
            "no_global_rng": "each seed is an independent rand('seed', k) reseed in the Octave driver, "
            "never an ambient/shared stream",
        },
    }


def build_macromol_perturbation_artifact(invariant_result: dict, macromol_fixture: dict) -> dict:
    ok = (
        not invariant_result["bound_violations"]
        and not invariant_result["mass_balance_violations"]
        and invariant_result["seeds_vary"]
    )
    return {
        "artifact_kind": "h12_perturbation_evidence",
        "gating": "NON_GATING -- distributional/structural evidence only; NEVER claims H12_CONFIRMED "
        "or exact-match. Not consumed by verdict.py / the H12_CONFIRMED evidence gate.",
        "process": "MacromolecularComplexation",
        "scenario": "macromolecular_complexation_network2_competition",
        "perturbation_spec_path": SPEC_PATH.relative_to(REPO_ROOT).as_posix(),
        "perturbation_spec_sha256_lf_normalized": _sha256_lf_normalized(SPEC_PATH),
        "execution_engine": "GNU Octave 6.4.0 (see scripts/octave_h12_perturbation/README.md RNG-fidelity caveat "
        "-- RNG draws are genuinely consumed by this scenario; the driver seeds via Octave/MATLAB's legacy "
        "rand('seed', k) API, which is NOT asserted to reproduce MATLAB's RandStream algorithm bit-for-bit, "
        "so results are structural/distributional, never exact-match)",
        "harness_source_hashes": _harness_hashes(),
        "evidence_scope_caveats": [
            "invariants checked (non-negative integer builds, built<=ub, mass-balance, termination, "
            "seed-to-seed variation) are STRUCTURAL only -- they confirm the branch executes correctly and "
            "is genuinely stochastic, not that any specific per-seed complex-build distribution matches "
            "MATLAB.",
            "matching the actual split distribution across (complex0, complex1) to MATLAB ground truth "
            "would require running the real edu.stanford.covert.util.RandStream (E:\\opencell-mirrors\\"
            "WholeCell) with the same seeding convention WholeCell itself uses -- not available from this "
            "Octave harness -- so no distributional-fidelity claim is made, only structural correctness.",
            "this artifact is OBSERVED_STOCHASTIC evidence only; it NEVER claims H12_CONFIRMED and remains "
            "NON_GATING regardless.",
        ],
        "karr_source_citation": {
            # Overrides h12.karr_source_citation("MacromolecularComplexation")'s narrower
            # evolveState/buildProteinComplexs_bounds citation (that citation is scoped to
            # what the CLOSED-FORM predict_macromolecular_complexation needs). This
            # perturbation harness additionally executes the free-standing Monte Carlo
            # functions verbatim (lines 334-388), so all four symbols are cited here.
            **h12.karr_source_citation("MacromolecularComplexation"),
            "line_ranges": [[290, 314], [334, 392]],
            "symbols": [
                "evolveState",
                "buildProteinComplexs_montecarlokinetic",
                "buildProteinComplexs_rates_collisionTheory",
                "buildProteinComplexs_bounds",
            ],
        },
        "fixture_path": macromol_fixture["__fixture_path__"],
        "fixture_sha256": macromol_fixture["__fixture_sha256__"],
        "network": 2,
        "substrate_indices_0b": MACROMOL_NETWORK2["substrate_indices_0b"],
        "complex_indices_0b": MACROMOL_NETWORK2["complex_indices_0b"],
        "pool_values": MACROMOL_NETWORK2["pool_values"],
        "stoichiometry_block": MACROMOL_NETWORK2["stoichiometry_block"],
        "ub": invariant_result["ub"],
        "n_seeds": invariant_result["n_seeds"],
        "bound_violations": invariant_result["bound_violations"],
        "mass_balance_violations": invariant_result["mass_balance_violations"],
        "distinct_outcome_count": invariant_result["distinct_outcome_count"],
        "seeds_vary": invariant_result["seeds_vary"],
        "min_built_per_complex": invariant_result["min_built_per_complex"],
        "max_built_per_complex": invariant_result["max_built_per_complex"],
        "mean_built_per_complex": invariant_result["mean_built_per_complex"],
        "raw_octave_output_sha256": invariant_result["raw_csv_sha256"],
        "target_branch": "network_ge2_fires",
        "target_branch_exercised": bool(np.any(np.array(invariant_result["ub"]) > 0)),
        "verdict": "H12_PERTURBATION_OBSERVED_STOCHASTIC" if ok else "H12_PERTURBATION_INVARIANT_VIOLATION",
        "verdict_reason": (
            "network_ge2's Monte Carlo competition branch was genuinely exercised (ub>0 for both complexes) "
            f"across {invariant_result['n_seeds']} independent seeds; all structural invariants held "
            f"(bound, mass-balance, termination) and outcomes varied across "
            f"{invariant_result['distinct_outcome_count']} distinct (complex0,complex1) tuples, confirming "
            "genuine RNG-dependence -- this is DISTRIBUTIONAL evidence for branch behavior, not H12 exact-"
            "match evidence, and does NOT confirm H12 for this process/branch."
            if ok
            else "one or more structural invariants were violated -- see bound_violations/"
            "mass_balance_violations."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anti_laundering_attestation": {
            "predictor_inputs": ["pre_registered_pool_and_stoichiometry_only"],
            "states_after_access": "invariant_check_phase_only",
            "no_sut_import": True,
            "no_result_json_access": True,
        },
    }


def write_artifact(name: str, artifact: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=False)
        fh.write("\n")
    return path


def ingest_and_compare() -> dict:
    ppii_fixture = h12.load_fixture("ProteinProcessingII")
    ppii_result = ingest_ppii_scenario_a(ppii_fixture)
    generated = {
        "ppii_state_sha256": _sha256_file(RAW_DIR / "ppii_scenario_a_state.m"),
    }
    ppii_artifact = build_ppii_perturbation_artifact(ppii_result, ppii_fixture, generated)
    ppii_path = write_artifact("ProteinProcessingII_h12_perturbation.json", ppii_artifact)

    macromol_fixture = h12.load_fixture("MacromolecularComplexation")
    macromol_result = check_macromol_invariants()
    macromol_artifact = build_macromol_perturbation_artifact(macromol_result, macromol_fixture)
    macromol_path = write_artifact("MacromolecularComplexation_h12_perturbation.json", macromol_artifact)

    return {
        "ProteinProcessingII": {"path": str(ppii_path), "verdict": ppii_artifact["verdict"]},
        "MacromolecularComplexation": {"path": str(macromol_path), "verdict": macromol_artifact["verdict"]},
    }


def ingest_and_compare_scenario_b() -> dict:
    """Scenario B (scarcity matrix) equivalent of ingest_and_compare() --
    entirely separate artifact/output path (ProteinProcessingII_h12_
    scenario_b_perturbation.json), never touches Scenario A's or
    macromol's artifacts. Will raise FileNotFoundError per-state until the
    corresponding Octave run (canary or full, per PERTURBATION_SPEC.json
    scenario_b_execution_status) has actually been executed and
    authorized -- NOT invoked by this commit.
    """
    ppii_fixture = h12.load_fixture("ProteinProcessingII")
    results = ingest_ppii_scenario_b(ppii_fixture)
    generated = {
        "ppii_scenario_b_state_sha256": {
            name: _sha256_file(RAW_DIR / f"ppii_scenario_b_{name}_state.m") for name in PPII_SCENARIO_B_STATE_NAMES
        },
    }
    artifact = build_ppii_scarcity_perturbation_artifact(results, ppii_fixture, generated)
    path = write_artifact("ProteinProcessingII_h12_scenario_b_perturbation.json", artifact)
    return {"ProteinProcessingII_scenario_b": {"path": str(path), "verdict": artifact["verdict"]}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "generate-inputs",
            "run-octave",
            "ingest-and-compare",
            "generate-inputs-scenario-b",
            "run-octave-scenario-b-canary",
            "run-octave-scenario-b-full",
            "ingest-and-compare-scenario-b",
        ],
    )
    args = parser.parse_args()

    if args.command == "generate-inputs":
        result = generate_inputs()
        print(json.dumps({k: (str(v) if isinstance(v, Path) else v) for k, v in result.items()}, indent=2))
    elif args.command == "run-octave":
        run_octave_scenario("run_ppii_scenario_a.m")
        run_octave_scenario("run_macromol_network2.m")
        print("octave scenarios executed")
    elif args.command == "ingest-and-compare":
        result = ingest_and_compare()
        print(json.dumps(result, indent=2))
    elif args.command == "generate-inputs-scenario-b":
        result = generate_inputs_scenario_b()
        print(json.dumps(result, indent=2))
    elif args.command == "run-octave-scenario-b-canary":
        # NOT authorized/invoked this turn -- see PERTURBATION_SPEC.json
        # scenario_b_execution_status; requires explicit GPT-5.6 Sol
        # authorization following Opus5 review of the code/spec commit.
        run_octave_scenario_b(canary=True)
        print("octave scenario B canary executed (1 state x 5 seeds)")
    elif args.command == "run-octave-scenario-b-full":
        # NOT authorized/invoked this turn -- same gate as canary above.
        run_octave_scenario_b(canary=False)
        print("octave scenario B full matrix executed (5 states x 50 seeds)")
    elif args.command == "ingest-and-compare-scenario-b":
        result = ingest_and_compare_scenario_b()
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
