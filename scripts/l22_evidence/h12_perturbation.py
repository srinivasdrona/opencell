"""H12 perturbation evidence: pre-registered state perturbations against the
real vendored Karr MacromolecularComplexation/ProteinProcessingII source.

Scenario A (ProteinProcessingII full-saturating) and the macromol
network2-competition scenario are executed via GNU Octave (see
scripts/octave_h12_perturbation/README.md) -- both are RNG-invariant-by-
construction or distributional-only, so the Octave harness's
stochasticRoundStub.m/mnrndStub.m scaffolds (a documented non-Karr
approximation) are an acceptable substitute for Karr's real RandStream.

Scenario B (ProteinProcessingII scarcity/mnrnd matrix) is executed via
genuine local MATLAB plus the Statistics Toolbox and Karr's real
`edu.stanford.covert.util.RandStream` class (see
scripts/matlab_h12_perturbation/README.md) -- NOT Octave. This is because
Scenario B's entire purpose is to exercise the dormant transferase/
scarcity mnrnd/stochasticRound branch with genuinely Karr-faithful
stochastic behavior; Octave has no RandStream class of that shape and no
Statistics-Toolbox mnrnd/binornd, so the Octave stub scaffolds cannot
serve as evidence for that branch's real behavior (this corrects an
earlier, Opus5-rejected, Octave-stub-based Scenario B design).

This module is SEPARATE from and does not modify scripts/l22_evidence/h12.py
or its CATALOG_N_M-gated artifacts (docs/phase_f/l2_2_design_a/h12/
<Process>_h12.json stay byte-for-byte as accepted). It produces its own,
clearly non-gating "perturbation evidence" artifacts under
docs/phase_f/l2_2_design_a/h12/perturbation/, and is NOT consumed by
verdict.py / the H12_CONFIRMED evidence gate. Any promotion of a process's
primary verdict on the strength of this evidence is a reviewer decision,
not something this module or its artifacts perform automatically. Even at
full execution, Scenario B evidence supports at most a future
CONDITION_GATED classification proposal -- it cannot close or remove the
natural regime's `missing_required_branches=['transferase_fires']` finding,
change ProteinProcessingII H12's H12_OBSERVED_REGIME verdict, or unblock
L2.5.

======================================================================
ANTI-LAUNDERING CONTRACT (same two-phase discipline as h12.py)
======================================================================
    PREDICT phase: `predict_protein_processing_ii` (imported, unmodified,
        from scripts/l22_evidence/h12.py) is called with ONLY the
        pre-registered perturbed `states_before` + static fixture params.
        `compute_macromol_network2_bound` below computes the network-2 `ub`
        bound from the pre-registered pool + stoichiometry ONLY -- neither
        function is given the Octave-executed `after` arrays. Scenario B's
        `predict_ppii_scarcity_bounds` is likewise before-only, and its
        output is PERSISTED TO DISK (freeze_ppii_scenario_b_predictions)
        BEFORE any MATLAB process is invoked -- the frozen file, not a
        fresh recomputation, is what `ingest_ppii_scenario_b` loads and
        compares against MATLAB's `states_after` output.
    COMPARE / INVARIANT-CHECK phase: only after the above are frozen does
    this module read the Octave- or MATLAB-produced raw CSV `after`
    outputs (`ingest_ppii_scenario_a`, `check_macromol_invariants`,
    `ingest_ppii_scenario_b`).
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
MATLAB_DIR = REPO_ROOT / "scripts" / "matlab_h12_perturbation"
VENDORED_RANDSTREAM_PATH = REPO_ROOT / "data" / "karr_vendored_source" / "RandStream.m"

# Named environment variable Python/MATLAB use to explicitly resolve the
# WholeCell `src/` root containing `+edu/+stanford/+covert/+util/
# RandStream.m` -- there is NO ambient/hardcoded fallback path (Opus5
# turn-4 correction 2: the prior probe/driver silently assumed
# data/m1_sources/WholeCell/src, a path that does not exist in this repo,
# which would have made "class not found" indistinguishable from "wrong/
# missing root"). Callers must pass --wholecell-src-root explicitly or set
# this environment variable; there is no other resolution path.
WHOLECELL_SRC_ROOT_ENV_VAR = "OPENCELL_WHOLECELL_SRC_ROOT"

# Path Python writes the MATLAB preflight probe's structured JSON result to
# (and the same path is passed to MATLAB via PPII_PROBE_RESULT_JSON so both
# sides agree on the location without a second hardcoded constant in the
# .m file). Also the file run_matlab_scenario_b() reads back to decide
# whether full-mode execution is permitted (Opus5 turn-4 correction 1).
PROBE_RESULT_PATH = RAW_DIR / "matlab_probe_result.json"

HARNESS_FILES = [
    "evolveState_ppii.m",
    "stochasticRoundStub.m",
    "mnrndStub.m",
    "buildProteinComplexs_bounds.m",
    "buildProteinComplexs_rates_collisionTheory.m",
    "buildProteinComplexs_montecarlokinetic.m",
    "run_ppii_scenario_a.m",
    "run_macromol_network2.m",
]

# Genuine-MATLAB Scenario B harness files -- hashed separately from
# HARNESS_FILES/OCTAVE_DIR above (different directory, different engine,
# different execution-evidence tier). See scripts/matlab_h12_perturbation/README.md.
MATLAB_HARNESS_FILES = [
    "evolveState_ppii_matlab.m",
    "run_ppii_scenario_b_matlab.m",
    "probe_matlab_environment.m",
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
# the natural trace and Scenario A). Dict iteration order below is NOT
# execution order -- the canary/full seed schedule (PPII_SCENARIO_B_SEED_
# BLOCKS, PPII_SCENARIO_B_CANARY_STATE below) is the single source of truth
# for which state is the canary; it is transferase_capacity_scarce, NOT
# water_scarce (corrected per Opus5 turn-3 review: water_scarce never
# reaches block1/the transferase branch at all, since its
# transferase_demand is 0, so it cannot serve as canary evidence that the
# transferase branch fires).
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

PPII_SCENARIO_B_CANARY_STATE = "transferase_capacity_scarce"
# Widened 5 -> 20 (Opus5 turn-4 correction 5, adopted): still an explicit
# PREFIX/SUBSET of the canary state's own 50-seed block (1000-1019 of
# 1000-1049), never a separate range. A canary run that shows
# seeds_vary=False over these 20 seeds is NOT treated as a canary failure
# (see build_ppii_scarcity_perturbation_artifact's canary-mode verdict
# branch) -- canary mode makes no distributional claim; widening merely
# gives the plumbing run a somewhat better chance of also incidentally
# showing variation, which is informative but not required.
PPII_SCENARIO_B_CANARY_SEED_COUNT = 20
PPII_SCENARIO_B_FULL_SEED_COUNT = 50

# Disjoint, pre-registered per-state MATLAB RandStream seed blocks. NEVER
# overlapping across states, and NEVER overlapping Scenario A / macromol-
# network2's own seed ids (0..49, see N_SEEDS/`seeds` above) -- this is a
# hard requirement (Opus5 turn-3 correction 5), mechanically asserted by
# tests/scripts/test_h12_perturbation.py::
# test_scenario_b_seed_blocks_are_pairwise_disjoint_and_avoid_scenario_a_macromol_ids.
# The canary seed list for a state is an explicit PREFIX/SUBSET of that
# same state's own full block (never a separate range) -- see
# PPII_SCENARIO_B_CANARY_SEEDS below.
PPII_SCENARIO_B_SEED_BLOCKS = {
    "transferase_capacity_scarce": tuple(range(1000, 1050)),
    "pg160_scarce": tuple(range(1050, 1100)),
    "peptidase_capacity_scarce": tuple(range(1100, 1150)),
    "water_scarce": tuple(range(1150, 1200)),
    "simultaneous_peptidase_capacity_and_water_scarce": tuple(range(1200, 1250)),
}
PPII_SCENARIO_B_CANARY_SEEDS = PPII_SCENARIO_B_SEED_BLOCKS[PPII_SCENARIO_B_CANARY_STATE][
    :PPII_SCENARIO_B_CANARY_SEED_COUNT
]


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


def _hash_canonical(obj: dict) -> str:
    """SHA-256 over a canonical (sorted-key) JSON serialization of `obj` --
    used to self-bind a frozen prediction record's `before_state` block
    (see freeze_ppii_scenario_b_predictions/ingest_ppii_scenario_b) so a
    hand-edited/corrupted before-state array is detectable even though it
    lives inside the same JSON file as its own hash.
    """
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()


def _resolve_wholecell_src_root(explicit: str | None = None) -> Path:
    """Explicitly resolve the WholeCell MATLAB `src/` root that must
    contain `+edu/+stanford/+covert/+util/RandStream.m` (Karr's real
    RandStream class). Resolution order:
      1. `explicit` (e.g. from --wholecell-src-root)
      2. the OPENCELL_WHOLECELL_SRC_ROOT environment variable
    There is NO ambient/default candidate path guessed here -- this
    corrects the prior probe/driver behavior of silently assuming
    data/m1_sources/WholeCell/src (a path that does not exist in this
    repo), per Opus5 turn-4 correction 2. Raises FileNotFoundError if
    neither is given, or if the resolved root does not contain
    RandStream.m at the expected package-qualified relative path.
    """
    candidate = explicit or os.environ.get(WHOLECELL_SRC_ROOT_ENV_VAR)
    if not candidate:
        raise FileNotFoundError(
            "WholeCell src root not resolved: pass --wholecell-src-root explicitly or set the "
            f"{WHOLECELL_SRC_ROOT_ENV_VAR} environment variable. No ambient/default path is assumed "
            "(Opus5 turn-4 correction 2)."
        )
    root = Path(candidate)
    randstream_rel = Path("+edu") / "+stanford" / "+covert" / "+util" / "RandStream.m"
    if not (root / randstream_rel).is_file():
        raise FileNotFoundError(
            f"WholeCell src root {root} does not contain the expected "
            f"{randstream_rel.as_posix()} (edu.stanford.covert.util.RandStream) -- resolution failed."
        )
    return root


def _validate_randstream_provenance(record: dict, context: str) -> None:
    """Cross-checks a MATLAB-reported RandStream runtime path/hash (from
    either a probe-result JSON or a per-state run-manifest) against the
    vendored data/karr_vendored_source/RandStream.m hash. This is an
    INDEPENDENT Python-side re-verification -- it never trusts MATLAB's own
    self-reported pass/fail alone (Opus5 turn-4 corrections 2 and 3).
    Raises ValueError on any missing field or hash mismatch.
    """
    vendored_hash = _sha256_lf_normalized(VENDORED_RANDSTREAM_PATH)
    runtime_path = record.get("randstream_runtime_path")
    runtime_hash = record.get("randstream_runtime_sha256_lf_normalized")
    if not runtime_path:
        raise ValueError(f"{context}: randstream_runtime_path missing/empty -- RandStream class not resolved")
    if not runtime_hash:
        raise ValueError(f"{context}: randstream_runtime_sha256_lf_normalized missing/empty")
    if runtime_hash != vendored_hash:
        raise ValueError(
            f"{context}: runtime RandStream source hash {runtime_hash!r} at {runtime_path!r} does not "
            f"match the vendored data/karr_vendored_source/RandStream.m hash {vendored_hash!r} -- refusing "
            "to trust this as genuine-Karr-RandStream evidence"
        )


_REQUIRED_PROBE_RESULT_FIELDS = (
    "is_octave",
    "overall_pass",
    "statistics_toolbox_licensed",
    "statistics_toolbox_installed",
    "randstream_class_found",
    "randstream_constructs",
    "randstream_runtime_path",
    "randstream_runtime_sha256_lf_normalized",
    "mnrnd_shape_test_status",
    "mnrnd_shape_test_result",
    "wholecell_src_root_used",
)


def _validate_matlab_probe_result(probe_result: dict) -> dict:
    """Independently re-validates an already-parsed MATLAB probe-result
    JSON dict -- never trusts MATLAB's own overall_pass alone (Opus5
    turn-4 correction 3). Raises ValueError on any missing required field,
    is_octave=true, overall_pass=false, or a RandStream runtime hash/path
    mismatch against the vendored RandStream.m. Mutates and returns
    `probe_result` with an added `full_mode_permitted` flag: True only if
    overall_pass AND the mnrnd column-vector shape test status is 'pass'.
    A 'error' mnrnd_shape_test_status is a genuine Karr dormant-source
    defect (verbatim evolveState_ppii_matlab.m calls
    this.randStream.mnrnd(n, columnVector) unmodified) that hard-blocks
    full mode ONLY -- it does not, by itself, fail canary-mode readiness
    (Opus5 turn-4 correction 1).
    """
    missing = [f for f in _REQUIRED_PROBE_RESULT_FIELDS if f not in probe_result]
    if missing:
        raise ValueError(f"MATLAB probe result missing required field(s): {missing!r}")
    if probe_result["is_octave"]:
        raise ValueError("MATLAB probe result reports is_octave=true -- Octave is never acceptable for Scenario B")
    if not probe_result["overall_pass"]:
        raise ValueError(f"MATLAB probe result reports overall_pass=false: {probe_result!r}")
    if probe_result["mnrnd_shape_test_status"] not in ("pass", "error", "not_run"):
        raise ValueError(f"unexpected mnrnd_shape_test_status {probe_result['mnrnd_shape_test_status']!r}")
    if probe_result["mnrnd_shape_test_status"] == "pass":
        mnrnd_result = probe_result["mnrnd_shape_test_result"]
        if (
            not isinstance(mnrnd_result, list)
            or len(mnrnd_result) != 2
            or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in mnrnd_result)
            or any(not np.isfinite(value) or value < 0 or float(value).is_integer() is False for value in mnrnd_result)
            or sum(mnrnd_result) != 3
        ):
            raise ValueError(
                "mnrnd_shape_test_status='pass' requires a finite, nonnegative integer 1x2 result summing to 3; "
                f"got {mnrnd_result!r}"
            )
    _validate_randstream_provenance(probe_result, context="probe_matlab_environment result")
    probe_result["full_mode_permitted"] = (
        bool(probe_result["overall_pass"])
        and bool(probe_result["statistics_toolbox_licensed"])
        and bool(probe_result["statistics_toolbox_installed"])
        and probe_result["mnrnd_shape_test_status"] == "pass"
    )
    if not probe_result["full_mode_permitted"]:
        probe_result["full_mode_hard_blocked_reason"] = (
            "Full mode requires Statistics Toolbox/mnrnd plus a valid 1x2 mnrnd column-vector probe result; "
            f"licensed={probe_result['statistics_toolbox_licensed']!r}, "
            f"installed={probe_result['statistics_toolbox_installed']!r}, "
            f"mnrnd_shape_test_status={probe_result['mnrnd_shape_test_status']!r}. "
            "The preregistered canary state never reaches mnrnd, so canary-mode plumbing remains permitted."
        )
    return probe_result


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


def _matlab_harness_hashes() -> dict:
    """Same as _harness_hashes() but for the genuine-MATLAB Scenario B
    harness files (scripts/matlab_h12_perturbation/), hashed separately
    since they are a distinct engine/evidence tier.
    """
    out = {}
    for name in MATLAB_HARNESS_FILES:
        path = MATLAB_DIR / name
        if not path.is_file():
            raise FileNotFoundError(f"expected MATLAB harness file missing: {path}")
        out[name] = _sha256_lf_normalized(path)
    return out


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=False)
        fh.write("\n")


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


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


def _write_ppii_scenario_b_state_files(states: dict, fixture: dict) -> dict:
    """Writes each Scenario B state's `this0` struct to a plain MATLAB-
    syntax .m file (assignment statements only -- valid input to both the
    Octave harness convention this repo otherwise uses and the genuine-
    MATLAB Scenario B driver, scripts/matlab_h12_perturbation/
    run_ppii_scenario_b_matlab.m, which is what actually consumes these
    files; the file format itself is not Octave-specific).
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_paths = {}
    for name, state in states.items():
        lines = _ppii_octave_state_lines(state, fixture)
        out_path = RAW_DIR / f"ppii_scenario_b_{name}_state.m"
        out_path.write_text("\n".join(lines) + "\n", encoding="ascii")
        out_paths[name] = out_path
    return out_paths


def freeze_ppii_scenario_b_predictions(states: dict, state_paths: dict, fixture: dict) -> dict:
    """Persist ONE JSON file per Scenario B state
    (ppii_scenario_b_<name>_prediction.json) containing the FROZEN
    predict_ppii_scarcity_bounds output, that state's pre-registered
    mode-specific seed schedule, and an LF-normalized hash of the state
    file it was derived from -- called from generate_inputs_scenario_b(),
    strictly BEFORE any MATLAB process is invoked.

    This is the hash-bind / anti-recompute mechanism required by Opus5
    turn-3 correction 6: `ingest_ppii_scenario_b` LOADS this frozen file
    and never recomputes predict_ppii_scarcity_bounds after MATLAB raw
    output exists. The MATLAB driver (run_ppii_scenario_b_matlab.m) also
    reads this same file, but ONLY for its `mode_seeds`/`state_file_
    sha256` fields (never the `prediction` field, which it does not need
    and must not consult to produce its own output).

    Also freezes the COMPLETE conditioned before-state arrays
    (`before_state`) plus a self-binding hash (`before_state_sha256`) of
    that block, per Opus5 turn-4 correction 6: `ingest_ppii_scenario_b`
    must evaluate invariants against THIS frozen before-state, verified
    against its own recorded hash, and must never rebuild it from the
    mutable module-level PPII_SCENARIO_B_STATES dict after MATLAB raw
    output exists (that dict could, in principle, be edited between
    freeze time and ingest time).
    """
    out_paths = {}
    for name, state in states.items():
        prediction = predict_ppii_scarcity_bounds(state, fixture)  # PREDICT phase: before-only
        state_path = state_paths[name]
        mode_seeds = {"full": list(PPII_SCENARIO_B_SEED_BLOCKS[name])}
        if name == PPII_SCENARIO_B_CANARY_STATE:
            mode_seeds["canary"] = list(PPII_SCENARIO_B_CANARY_SEEDS)
        before_state = {
            "unprocessedMonomers": state["unprocessedMonomers"].tolist(),
            "processedMonomers": state["processedMonomers"].tolist(),
            "signalSequenceMonomers": state["signalSequenceMonomers"].tolist(),
            "enzymes": state["enzymes"].tolist(),
            "substrates": state["substrates"].tolist(),
        }
        frozen = {
            "state_name": name,
            "mode_seeds": mode_seeds,
            "state_file": state_path.name,
            "state_file_sha256": _sha256_lf_normalized(state_path),
            "before_state": before_state,
            "before_state_sha256": _hash_canonical(before_state),
            "prediction": prediction,
            "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        out_path = RAW_DIR / f"ppii_scenario_b_{name}_prediction.json"
        _write_json(out_path, frozen)
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
    paths = _write_ppii_scenario_b_state_files(states, ppii_fixture)
    prediction_paths = freeze_ppii_scenario_b_predictions(states, paths, ppii_fixture)
    return {
        "ppii_scenario_b_state_paths": {name: str(p) for name, p in paths.items()},
        "ppii_scenario_b_state_sha256": {name: _sha256_file(p) for name, p in paths.items()},
        "ppii_scenario_b_prediction_paths": {name: str(p) for name, p in prediction_paths.items()},
        "ppii_scenario_b_prediction_sha256": {
            name: _sha256_lf_normalized(p) for name, p in prediction_paths.items()
        },
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


def run_matlab_scenario_b(canary: bool, wholecell_src_root: str | None = None) -> None:
    """Invoke run_ppii_scenario_b_matlab.m (genuine local MATLAB, NOT
    Octave) in either canary mode (1 state x its 20-seed canary prefix) or
    full mode (5 states x 50 seeds), selected via the PPII_SCENARIO_B_MODE
    environment variable the .m driver reads. Uses MATLAB's `-batch` mode
    (no display, no desktop, non-interactive, nonzero exit code on any
    uncaught error) -- there is NO stub/fallback engine selection here; if
    `matlab` is not on PATH or the driver itself aborts (missing
    Statistics Toolbox/RandStream, see run_ppii_scenario_b_matlab.m), this
    raises.

    Requires (Opus5 turn-4 corrections 1 and 2):
      - an explicitly resolved WholeCell src root (see
        _resolve_wholecell_src_root) -- no ambient default path;
      - a PREVIOUSLY-RUN, independently-validated probe result at
        PROBE_RESULT_PATH (see probe_matlab_environment()/
        _validate_matlab_probe_result) -- this function refuses to run
        MATLAB at all if no probe result exists yet;
      - for full mode ONLY: the probe result's `full_mode_permitted` must
        be True (i.e. the mnrnd column-vector shape test must have
        reported 'pass', not 'error') -- an 'error' result is a genuine
        Karr dormant-source defect that HARD-BLOCKS full mode. Canary
        mode is not gated on this sub-result, only on overall_pass.

    NOT CALLED by anything in this commit -- implemented so canary/full
    execution is a single, reviewable, pre-registered code path ready for
    invocation only after explicit GPT-5.6 Sol authorization following
    Opus5 review (see PERTURBATION_SPEC.json scenario_b_execution_status).
    """
    root = _resolve_wholecell_src_root(wholecell_src_root)
    if not PROBE_RESULT_PATH.is_file():
        raise RuntimeError(
            f"no MATLAB probe result found at {PROBE_RESULT_PATH} -- run probe_matlab_environment() first; "
            "canary/full execution is gated on it (Opus5 turn-4 correction 1)"
        )
    probe_result = _validate_matlab_probe_result(_load_json(PROBE_RESULT_PATH))
    if not canary and not probe_result["full_mode_permitted"]:
        raise RuntimeError(
            "full-mode Scenario B execution is HARD-BLOCKED: the most recent probe result recorded "
            f"mnrnd_shape_test_status={probe_result.get('mnrnd_shape_test_status')!r} "
            f"(reason: {probe_result.get('full_mode_hard_blocked_reason', 'n/a')}). Canary-mode plumbing "
            "runs remain permitted; only full mode is blocked (Opus5 turn-4 correction 1)."
        )
    env = dict(os.environ)
    env["PPII_SCENARIO_B_MODE"] = "canary" if canary else "full"
    env["PPII_WHOLECELL_SRC_ROOT"] = str(root)
    result = subprocess.run(
        ["matlab", "-batch", "run_ppii_scenario_b_matlab"],
        cwd=str(MATLAB_DIR),
        capture_output=True,
        text=True,
        timeout=300 if canary else 1800,
        env=env,
    )
    sys.stderr.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"matlab run_ppii_scenario_b_matlab ({env['PPII_SCENARIO_B_MODE']}) failed with exit code "
            f"{result.returncode}"
        )


def probe_matlab_environment(wholecell_src_root: str | None = None) -> dict:
    """Invoke scripts/matlab_h12_perturbation/probe_matlab_environment.m
    (genuine MATLAB, read-only preflight diagnostic -- writes no
    evolveState/evidence output, only its own structured result JSON at
    PROBE_RESULT_PATH). NOT CALLED by anything in this commit; this is the
    "parse/license/toolbox probe" step authorized separately from (and
    strictly before) the canary run.

    Requires an explicitly resolved WholeCell src root (Opus5 turn-4
    correction 2 -- no ambient default). Per Opus5 turn-4 correction 3,
    this function NEVER trusts the subprocess exit code alone: it always
    loads and independently re-validates the structured JSON result (see
    _validate_matlab_probe_result), including cross-checking the
    MATLAB-reported RandStream runtime hash against the vendored
    RandStream.m, and raises if that JSON is missing/malformed/failing
    even if MATLAB happened to exit 0.
    """
    root = _resolve_wholecell_src_root(wholecell_src_root)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PPII_WHOLECELL_SRC_ROOT"] = str(root)
    env["PPII_PROBE_RESULT_JSON"] = str(PROBE_RESULT_PATH)
    result = subprocess.run(
        ["matlab", "-batch", "probe_matlab_environment"],
        cwd=str(MATLAB_DIR),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if not PROBE_RESULT_PATH.is_file():
        raise RuntimeError(
            f"matlab probe_matlab_environment produced no result JSON at {PROBE_RESULT_PATH} (exit code "
            f"{result.returncode}) -- refusing to trust a bare exit code (Opus5 turn-4 correction 3)"
        )
    probe_result = _validate_matlab_probe_result(_load_json(PROBE_RESULT_PATH))
    if result.returncode == 0 and not probe_result["overall_pass"]:
        raise RuntimeError(
            "matlab probe_matlab_environment exited 0 but its own JSON result reports overall_pass=false -- "
            "inconsistent; refusing to trust the exit code alone"
        )
    return probe_result


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


def ingest_ppii_scenario_b(fixture: dict, mode: str) -> dict:
    """COMPARE phase for Scenario B, mode-aware ("canary" or "full" --
    required, no default). Reads the FROZEN prediction (written by
    freeze_ppii_scenario_b_predictions during generate_inputs_scenario_b(),
    never recomputed here) plus the genuine-MATLAB driver's per-state run-
    manifest and `after` CSV. Never touches the OC SUT, any runner output,
    or any oracle-after value.

    In 'canary' mode, ONLY PPII_SCENARIO_B_CANARY_STATE is expected/
    processed (the other 4 states legitimately have no evidence yet -- this
    is not an error). In 'full' mode, all 5 states are required.

    Validation performed per state (raises ValueError/FileNotFoundError on
    any failure -- no silent leniency):
      - frozen prediction JSON exists (else: run generate-inputs-scenario-b
        first).
      - run-manifest JSON exists (else: MATLAB has not been run for this
        state/mode yet).
      - manifest['mode'] == mode (rejects a stale/mixed canary-vs-full
        manifest).
      - manifest['seeds'] == frozen prediction's mode_seeds[mode], exactly,
        in order (rejects reused/substituted/reordered seeds).
      - manifest['state_file_sha256_lf_normalized'] == the frozen
        prediction's own state_file_sha256 == the CURRENT on-disk state
        file's hash (three-way staleness check: catches a state file that
        changed after the prediction was frozen, or a manifest produced
        against a different state-file version).
      - manifest['randstream_class_confirmed'] is truthy (rejects any
        result the driver did not itself confirm came from a real
        RandStream instance).
      - manifest's RandStream runtime path/hash matches the vendored
        data/karr_vendored_source/RandStream.m (independent re-check, not
        merely trusting randstream_class_confirmed's boolean self-report
        -- Opus5 turn-4 correction 2).
      - manifest['harness_sha256_lf_normalized'] matches the CURRENT
        evolveState_ppii_matlab.m hash (rejects stale harness drift).
      - the frozen prediction's `before_state` block hashes to its own
        recorded `before_state_sha256` (tamper check -- Opus5 turn-4
        correction 6); invariants are evaluated against THIS frozen
        before-state, never a fresh call to build_ppii_scenario_b_states
        with the (mutable) module-level PPII_SCENARIO_B_STATES.
      - the `after` CSV has EXACTLY 1 + 3*n_mono + n_sub columns and
        EXACTLY len(seeds) rows (20 for canary, 50 for full -- never
        more/fewer, never a mix of canary-count and full-count rows).
      - the CSV's leading seed-id column, as a set, exactly equals the
        manifest's (and frozen prediction's) pre-registered seed set for
        this state/mode (rejects a CSV whose actual seed coverage doesn't
        match what was claimed).
    """
    if mode not in ("canary", "full"):
        raise ValueError(f"mode must be 'canary' or 'full', got {mode!r}")

    expected_state_names = [PPII_SCENARIO_B_CANARY_STATE] if mode == "canary" else list(PPII_SCENARIO_B_STATE_NAMES)

    current_harness_sha256 = _sha256_lf_normalized(MATLAB_DIR / "evolveState_ppii_matlab.m")

    results = {}
    for name in expected_state_names:
        prediction_path = RAW_DIR / f"ppii_scenario_b_{name}_prediction.json"
        if not prediction_path.is_file():
            raise FileNotFoundError(
                f"frozen prediction missing: {prediction_path} (run generate-inputs-scenario-b first)"
            )
        frozen = _load_json(prediction_path)
        prediction = frozen["prediction"]
        # ---- prediction is the FROZEN one loaded above; it is NEVER recomputed here ----

        before_state_raw = frozen.get("before_state")
        if before_state_raw is None:
            raise ValueError(
                f"state {name!r}: frozen prediction {prediction_path} has no before_state block (stale "
                "pre-turn-4 prediction file -- re-run generate-inputs-scenario-b)"
            )
        if _hash_canonical(before_state_raw) != frozen.get("before_state_sha256"):
            raise ValueError(
                f"state {name!r}: frozen before_state in {prediction_path} does not hash-match its own "
                "recorded before_state_sha256 -- tampered/corrupted prediction file, refusing to trust it"
            )
        before = {
            "unprocessedMonomers": np.array(before_state_raw["unprocessedMonomers"], dtype=np.float64),
            "substrates": np.array(before_state_raw["substrates"], dtype=np.float64),
        }
        n_mono = before["unprocessedMonomers"].shape[0]
        n_sub = before["substrates"].shape[0]

        if mode not in frozen["mode_seeds"]:
            raise ValueError(
                f"state {name!r} has no pre-registered {mode!r}-mode seed list in {prediction_path} "
                f"(only {sorted(frozen['mode_seeds'])!r} available)"
            )
        expected_seeds = list(frozen["mode_seeds"][mode])

        state_path = RAW_DIR / f"ppii_scenario_b_{name}_state.m"
        current_state_sha256 = _sha256_lf_normalized(state_path)
        if current_state_sha256 != frozen["state_file_sha256"]:
            raise ValueError(
                f"state {name!r}: current state file {state_path} (sha256 {current_state_sha256}) has "
                f"changed since its prediction was frozen (sha256 {frozen['state_file_sha256']}) -- "
                "re-run generate-inputs-scenario-b"
            )

        manifest_path = RAW_DIR / f"ppii_scenario_b_{name}_run_manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(
                f"MATLAB run-manifest missing: {manifest_path} (run run_ppii_scenario_b_matlab.m in "
                f"{mode!r} mode first -- NOT YET AUTHORIZED this turn, see PERTURBATION_SPEC.json "
                "scenario_b_execution_status)"
            )
        manifest = _load_json(manifest_path)

        if manifest.get("mode") != mode:
            raise ValueError(
                f"state {name!r}: run-manifest mode {manifest.get('mode')!r} does not match requested "
                f"ingest mode {mode!r} -- refusing to ingest mismatched canary/full evidence"
            )
        if list(manifest.get("seeds", [])) != expected_seeds:
            raise ValueError(
                f"state {name!r}: run-manifest seeds {manifest.get('seeds')!r} do not exactly match the "
                f"pre-registered {mode!r}-mode seed list {expected_seeds!r}"
            )
        if manifest.get("state_file_sha256_lf_normalized") != frozen["state_file_sha256"]:
            raise ValueError(
                f"state {name!r}: run-manifest state-file hash "
                f"{manifest.get('state_file_sha256_lf_normalized')!r} does not match the frozen "
                f"prediction's {frozen['state_file_sha256']!r} -- stale MATLAB run"
            )
        if not manifest.get("randstream_class_confirmed"):
            raise ValueError(
                f"state {name!r}: run-manifest does not confirm randstream_class_confirmed=true -- "
                "refusing to trust this as real-RandStream evidence"
            )
        _validate_randstream_provenance(manifest, context=f"state {name!r} run-manifest")
        if manifest.get("harness_sha256_lf_normalized") != current_harness_sha256:
            raise ValueError(
                f"state {name!r}: run-manifest harness hash "
                f"{manifest.get('harness_sha256_lf_normalized')!r} does not match the current "
                f"evolveState_ppii_matlab.m hash {current_harness_sha256!r} -- stale harness"
            )

        csv_path = RAW_DIR / f"ppii_scenario_b_{name}_after.csv"
        if not csv_path.is_file():
            raise FileNotFoundError(
                f"MATLAB output missing: {csv_path} (run run_ppii_scenario_b_matlab.m in {mode!r} mode "
                "first -- NOT YET AUTHORIZED this turn, see PERTURBATION_SPEC.json "
                "scenario_b_execution_status)"
            )
        raw_with_seed = np.loadtxt(csv_path, delimiter=",")
        if raw_with_seed.ndim == 1:
            raw_with_seed = raw_with_seed.reshape(1, -1)
        expected_cols = 1 + 3 * n_mono + n_sub
        if raw_with_seed.shape[1] != expected_cols:
            raise ValueError(
                f"unexpected MATLAB output column count {raw_with_seed.shape[1]} for state {name!r}, "
                f"expected exactly {expected_cols} (1 leading seed-id column + 3*{n_mono} monomer arrays "
                f"+ {n_sub} substrates)"
            )
        if raw_with_seed.shape[0] != len(expected_seeds):
            raise ValueError(
                f"unexpected MATLAB output row count {raw_with_seed.shape[0]} for state {name!r} in "
                f"{mode!r} mode, expected exactly {len(expected_seeds)} (rejects mixed canary/full or "
                "partial evidence)"
            )
        actual_seed_ids = sorted(int(round(x)) for x in raw_with_seed[:, 0])
        if actual_seed_ids != sorted(expected_seeds):
            raise ValueError(
                f"state {name!r}: CSV seed-id column {actual_seed_ids!r} does not exactly match the "
                f"pre-registered {mode!r}-mode seed set {sorted(expected_seeds)!r}"
            )
        raw = raw_with_seed[:, 1:]

        # `before` was already built above from the frozen, hash-verified
        # before_state block -- never rebuilt from the mutable module-level
        # PPII_SCENARIO_B_STATES/build_ppii_scenario_b_states here (Opus5
        # turn-4 correction 6).
        invariant_result = evaluate_ppii_scarcity_invariants(before, raw, fixture)
        invariant_result["raw_csv_sha256"] = _sha256_file(csv_path)
        results[name] = {
            "prediction": prediction,
            "invariants": invariant_result,
            "manifest": manifest,
        }
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


def build_ppii_scarcity_perturbation_artifact(
    results: dict, ppii_fixture: dict, generated: dict, mode: str
) -> dict:
    """Build the Scenario B (scarcity matrix) artifact from
    ingest_ppii_scenario_b's per-state {prediction, invariants, manifest}
    results. `mode` ('canary' or 'full') determines which states are
    expected (see ingest_ppii_scenario_b) and is recorded in the artifact
    so a canary-only artifact is never confusable with a full-matrix one.

    Verdict vocabulary is DISJOINT from both h12.py's H12_CONFIRMED and
    Scenario A's H12_PERTURBATION_CONFIRMED, since Scenario B never claims
    an exact point-match -- only bound invariants (exact) plus genuine
    cross-seed stochastic variation (distributional, non-degenerate):
        H12_PERTURBATION_SCARCITY_OBSERVED_STOCHASTIC: all invariants held
            in every state, AND every state exercising a real stochastic
            mechanism (per its guard_diagnostics) showed genuine cross-
            seed variation (mnrnd/stochasticRound did not degenerate into
            a no-op).
        H12_PERTURBATION_SCARCITY_NO_VARIATION: FULL MODE ONLY -- all
            invariants held, but at least one state's stochastic mechanism
            produced IDENTICAL output across all seeds -- this is the
            anti-laundering catch for a mutated/reused/global RNG stream
            or a state that silently failed to reach the intended branch.
        H12_PERTURBATION_SCARCITY_INVARIANT_VIOLATION: any exact bound
            (mass/non-negativity/per-species-cap/pool-cap) was violated in
            any seed of any state -- hard fail regardless of variation.
        H12_PERTURBATION_SCARCITY_CANARY_PLUMBING_OK: CANARY MODE ONLY --
            all invariants held for the single canary state. Canary mode
            makes NO distributional claim (Opus5 turn-4 correction 5): a
            canary run with seeds_vary=False over its 20 seeds is recorded
            (`no_variation_flag`) but does NOT fail the canary verdict --
            the canary's sole purpose is to prove the genuine-MATLAB
            execution plumbing (RandStream/mnrnd/stochasticRound/CSV/
            manifest) works end-to-end for one real branch-activating
            state, not to make a distributional claim (that is full mode's
            job).
        H12_PERTURBATION_SCARCITY_CANARY_INVARIANT_VIOLATION: CANARY MODE
            ONLY -- same hard-fail semantics as the full-mode invariant
            violation above, still applies in canary mode (an exact bound
            violation is never acceptable regardless of mode).

    Even H12_PERTURBATION_SCARCITY_OBSERVED_STOCHASTIC at full-matrix
    completion is NOT H12_CONFIRMED and does NOT close ProteinProcessingII
    H12's natural-regime `missing_required_branches=['transferase_fires']`
    finding -- see gating/evidence_scope_caveats below and
    PROTEINPROCESSINGII_SCENARIO_B_PROPOSAL.md.
    """
    if mode not in ("canary", "full"):
        raise ValueError(f"mode must be 'canary' or 'full', got {mode!r}")

    any_violation = False
    any_degenerate = False
    per_state_summary = {}
    for name, r in results.items():
        pred = r["prediction"]
        inv = r["invariants"]
        manifest = r["manifest"]
        violated = len(inv["violations"]) > 0
        # A state's stochastic mechanism is expected to fire (per its
        # hand-traced mechanics, see PERTURBATION_SPEC.json) whenever its
        # guard failed at all (every Scenario B state fails at least one
        # guard by construction, so every state is expected to show
        # variation -- a flat/no-variation result on ANY of them is a
        # laundering red flag in FULL mode, not an acceptable "this state
        # happens not to be stochastic" case). This is recorded regardless
        # of mode, but only gates the verdict in FULL mode (see below;
        # Opus5 turn-4 correction 5 -- canary mode makes no distributional
        # claim).
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
            "no_variation_flag_gates_verdict": mode == "full",
            "raw_output_sha256": inv["raw_csv_sha256"],
            "run_manifest": {
                "mode": manifest.get("mode"),
                "seeds": manifest.get("seeds"),
                "matlab_version": manifest.get("matlab_version"),
                "statistics_toolbox_licensed": manifest.get("statistics_toolbox_licensed"),
                "randstream_class_confirmed": manifest.get("randstream_class_confirmed"),
                "generated_at_utc": manifest.get("generated_at_utc"),
            },
        }

    label_mismatch = any(
        not s["guard_failure_label_matches_prereg"] for s in per_state_summary.values()
    )
    if mode == "canary":
        # Canary mode never fails on no_variation -- it makes no
        # distributional claim (Opus5 turn-4 correction 5). Its own,
        # disjoint verdict vocabulary makes this explicit rather than
        # silently reusing the full-mode OBSERVED_STOCHASTIC/NO_VARIATION
        # labels, which WOULD imply a distributional claim.
        if any_violation or label_mismatch:
            verdict = "H12_PERTURBATION_SCARCITY_CANARY_INVARIANT_VIOLATION"
        else:
            verdict = "H12_PERTURBATION_SCARCITY_CANARY_PLUMBING_OK"
    elif any_violation or label_mismatch:
        verdict = "H12_PERTURBATION_SCARCITY_INVARIANT_VIOLATION"
    elif any_degenerate:
        verdict = "H12_PERTURBATION_SCARCITY_NO_VARIATION"
    else:
        verdict = "H12_PERTURBATION_SCARCITY_OBSERVED_STOCHASTIC"

    return {
        "artifact_kind": "h12_perturbation_evidence",
        "gating": "NON_GATING -- distributional/bound evidence only; NEVER claims H12_CONFIRMED or "
        "H12_PERTURBATION_CONFIRMED (Scenario A's exact-match vocabulary). Not consumed by verdict.py / "
        "the H12_CONFIRMED evidence gate. Cannot close or remove ProteinProcessingII H12's natural-regime "
        "`missing_required_branches=['transferase_fires']` finding, cannot change H12_OBSERVED_REGIME, and "
        "cannot unblock L2.5. Recommends (does not enact) a condition-gated terminal profile -- see "
        "PROTEINPROCESSINGII_SCENARIO_B_PROPOSAL.md.",
        "process": "ProteinProcessingII",
        "scenario": "protein_processing_ii_scenario_b_scarcity_matrix",
        "mode": mode,
        "perturbation_spec_path": SPEC_PATH.relative_to(REPO_ROOT).as_posix(),
        "perturbation_spec_sha256_lf_normalized": _sha256_lf_normalized(SPEC_PATH),
        "execution_engine": "Genuine local MATLAB (NOT Octave) plus the Statistics Toolbox, using Karr's "
        "real edu.stanford.covert.util.RandStream class for every stochasticRound/mnrnd draw (see "
        "scripts/matlab_h12_perturbation/README.md and PERTURBATION_SPEC.json "
        "scenario_b_execution_engine). No stub/scaffold RNG of any kind is used; the driver aborts with no "
        "fallback if genuine MATLAB, the Statistics Toolbox, or RandStream construction is unavailable. "
        "This is a source-faithful stochastic-branch evidence tier, distinct from Scenario A/macromol's "
        "Octave-stub-based harnesses.",
        "matlab_harness_source_hashes": _matlab_harness_hashes(),
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
            "mode='canary' artifacts cover only "
            f"{PPII_SCENARIO_B_CANARY_STATE!r} ({PPII_SCENARIO_B_CANARY_SEED_COUNT} seeds) -- the other 4 "
            "states have no evidence yet in a canary artifact; this is expected, not a violation.",
            "mode='canary' verdicts (H12_PERTURBATION_SCARCITY_CANARY_PLUMBING_OK/"
            "_CANARY_INVARIANT_VIOLATION) make NO distributional claim -- a canary run with "
            "seeds_vary=False is recorded (no_variation_flag) but does not, by itself, fail the canary "
            "verdict (Opus5 turn-4 correction 5); the distributional NO_VARIATION/OBSERVED_STOCHASTIC "
            "vocabulary is reserved for mode='full' only.",
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
            f"mode={mode}; {len(per_state_summary)} pre-registered scarcity state(s) checked; "
            f"any_bound_violation={any_violation}; any_no_variation={any_degenerate}; "
            f"any_guard_label_mismatch={label_mismatch}."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anti_laundering_attestation": {
            "predictor_inputs": ["states_before", "static_fixture_params", "perturbation_spec_constants"],
            "prediction_frozen_before_matlab_execution": True,
            "states_after_access": "compare_phase_only",
            "no_sut_import": True,
            "no_result_json_access": True,
            "no_global_rng": "each seed is an independently-constructed real "
            "edu.stanford.covert.util.RandStream('mcg16807', 'Seed', k) instance in the MATLAB driver, "
            "never an ambient/shared/global stream",
            "no_stub_fallback": True,
            "disjoint_seed_blocks": True,
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


def ingest_and_compare_scenario_b(mode: str) -> dict:
    """Scenario B (scarcity matrix) equivalent of ingest_and_compare() --
    entirely separate artifact/output path, never touches Scenario A's or
    macromol's artifacts. `mode` ('canary' or 'full') is required (no
    default) and determines both which states are expected
    (ingest_ppii_scenario_b) and the output artifact filename:
    mode='canary' -> ProteinProcessingII_h12_scenario_b_perturbation_canary.json
    mode='full'   -> ProteinProcessingII_h12_scenario_b_perturbation.json
    (kept unsuffixed for 'full' for continuity with prior artifact naming).
    Will raise FileNotFoundError per-state until the corresponding genuine-
    MATLAB run (per PERTURBATION_SPEC.json scenario_b_execution_status) has
    actually been executed and authorized -- NOT invoked by this commit.
    """
    if mode not in ("canary", "full"):
        raise ValueError(f"mode must be 'canary' or 'full', got {mode!r}")
    ppii_fixture = h12.load_fixture("ProteinProcessingII")
    results = ingest_ppii_scenario_b(ppii_fixture, mode=mode)
    generated = {
        "ppii_scenario_b_state_sha256": {
            name: _sha256_file(RAW_DIR / f"ppii_scenario_b_{name}_state.m") for name in PPII_SCENARIO_B_STATE_NAMES
        },
    }
    artifact = build_ppii_scarcity_perturbation_artifact(results, ppii_fixture, generated, mode=mode)
    filename = (
        "ProteinProcessingII_h12_scenario_b_perturbation_canary.json"
        if mode == "canary"
        else "ProteinProcessingII_h12_scenario_b_perturbation.json"
    )
    path = write_artifact(filename, artifact)
    return {"ProteinProcessingII_scenario_b": {"path": str(path), "verdict": artifact["verdict"], "mode": mode}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "generate-inputs",
            "run-octave",
            "ingest-and-compare",
            "generate-inputs-scenario-b",
            "probe-matlab-environment",
            "run-matlab-scenario-b-canary",
            "run-matlab-scenario-b-full",
            "ingest-and-compare-scenario-b-canary",
            "ingest-and-compare-scenario-b-full",
        ],
    )
    parser.add_argument(
        "--wholecell-src-root",
        default=None,
        help=(
            "Explicit WholeCell src/ root containing +edu/+stanford/+covert/+util/RandStream.m, used by "
            "probe-matlab-environment/run-matlab-scenario-b-*. Falls back to the "
            f"{WHOLECELL_SRC_ROOT_ENV_VAR} environment variable if omitted; there is no other default "
            "(Opus5 turn-4 correction 2)."
        ),
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
    elif args.command == "probe-matlab-environment":
        # NOT invoked by anything else in this commit -- the parse/
        # license/toolbox/RandStream/mnrnd-shape preflight step, authorized
        # separately from (and before) the canary run.
        probe_result = probe_matlab_environment(wholecell_src_root=args.wholecell_src_root)
        print(json.dumps(probe_result, indent=2))
    elif args.command == "run-matlab-scenario-b-canary":
        # NOT authorized/invoked this turn -- see PERTURBATION_SPEC.json
        # scenario_b_execution_status; requires explicit GPT-5.6 Sol
        # authorization following Opus5 review of the code/spec commit,
        # and a prior probe-matlab-environment confirmation.
        run_matlab_scenario_b(canary=True, wholecell_src_root=args.wholecell_src_root)
        print(f"matlab scenario B canary executed (1 state x {PPII_SCENARIO_B_CANARY_SEED_COUNT} seeds)")
    elif args.command == "run-matlab-scenario-b-full":
        # NOT authorized/invoked this turn -- same gate as canary above,
        # plus the additional full-mode mnrnd-shape hard-block (see
        # run_matlab_scenario_b docstring).
        run_matlab_scenario_b(canary=False, wholecell_src_root=args.wholecell_src_root)
        print("matlab scenario B full matrix executed (5 states x 50 seeds)")
    elif args.command == "ingest-and-compare-scenario-b-canary":
        result = ingest_and_compare_scenario_b(mode="canary")
        print(json.dumps(result, indent=2))
    elif args.command == "ingest-and-compare-scenario-b-full":
        result = ingest_and_compare_scenario_b(mode="full")
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
