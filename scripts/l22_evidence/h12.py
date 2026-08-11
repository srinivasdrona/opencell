"""H12 machine evidence framework for PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE rows.

Produces genuine, independently-derived machine evidence that a process's OC
closed-form path converges on Karr's stochastic algorithm *because the Karr
algorithm itself becomes provably deterministic in the observed regime*, not
because of oracle leakage ("laundering").

======================================================================
ANTI-LAUNDERING CONTRACT — READ BEFORE EDITING THIS FILE
======================================================================
Every ``predict_<process>`` function in this module implements the PREDICT
phase of a strict two-phase protocol:

    PREDICT phase (this file, ``predict_*`` functions):
        Inputs:  ``states_before`` (one tick's pre-tick state vectors, read
                 from the raw Karr oracle trace) and ``fixture`` (static,
                 versioned Karr knowledge-base parameters: stoichiometry
                 matrices, rate constants, index maps — loaded once from
                 ``data/karr_fixtures/per_process/<Process>_flat.mat``).
        Forbidden: importing any ``opencell.vivarium.*`` SUT module, calling
                 ``next_update``/``run_oc_tick``, reading ``states_after``,
                 reading any ``result.json``/evidence-bundle output, or
                 otherwise touching anything derived from an OC run or a
                 previously-computed verdict. Formulas here are transcribed
                 directly from the Karr MATLAB source (citations recorded in
                 each predictor's docstring) — never reverse-engineered from
                 observed outcomes.

    COMPARE phase (``compare_predictions`` below, called strictly after
    ``predict_*`` has returned and its output has been frozen):
        Inputs: the frozen predictions plus ``states_after`` (read only
                 here, never inside a ``predict_*`` function).

This module is scanned by ``tests/scripts/test_h12_anticheat.py`` for
forbidden imports/identifiers inside ``predict_*`` function bodies. Do not
work around that test; if a formula genuinely cannot be derived without
consulting ``states_after``/the SUT, that process should be reported
H12_FAIL, not laundered.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import h5py
import numpy as np
from scipy.io import loadmat

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "data" / "karr_fixtures" / "per_process"
ORACLE_ROOT = REPO_ROOT / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2"
OUT_ROOT = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12"
KARR_SOURCE_ROOT = REPO_ROOT / "data" / "karr_vendored_source"
ORACLE_MANIFEST_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "oracle_population_manifest.json"

# H12 v2 (post-Opus5-repair): bumped from 1.0.0 because of the compare-phase
# scoping fix, the ProteinFolding chaperone-guard fix, and the introduction of
# H12_OBSERVED_REGIME. See docs/phase_f/l2_2_design_a/h12/H12_REPORT.md.
FORMULA_VERSION = "2.0.0"

# This module IS the predictor source artifact. Its path is pinned (not just
# discovered via __file__) so that verdict.py can hard-fail if an artifact
# claims support from a module at any other path -- a dangling/wrong
# predictor_source_path is a tamper signal, not a soft-trust case.
EXPECTED_PREDICTOR_SOURCE_PATH = "scripts/l22_evidence/h12.py"
TRACE_WINDOW_MANIFEST_SCHEMA_VERSION = "h12_trace_window_manifest_v1"

# Catalog N_seeds/M_ticks for the 5 target processes (docs/phase_f/l2_2_design_a/
# PROCESS_CATALOG.yaml, read-only citation — do not edit that file from here).
CATALOG_N_M = {
    "tRNAAminoacylation": (50, 50),
    "ProteinProcessingII": (50, 20),
    "ProteinFolding": (50, 100),
    "MacromolecularComplexation": (50, 100),
    "ProteinProcessingI": (50, 20),
}

# Highest-risk-first run order mandated by the task.
RISK_ORDER = [
    "tRNAAminoacylation",
    "ProteinProcessingII",
    "ProteinFolding",
    "MacromolecularComplexation",
    "ProteinProcessingI",
]

# Karr WholeCell MATLAB source citations. The gitignored clone target
# (data/m1_sources/WholeCell/) is NOT a reproducible provenance root (a fresh
# clone of THIS repo does not populate it) -- these 5 files are vendored
# verbatim (MIT license, see data/karr_vendored_source/README.md) under a
# tracked path instead, from the real upstream mirror.
KARR_UPSTREAM_REPO = "https://github.com/CovertLab/WholeCell"
KARR_UPSTREAM_COMMIT = "6cdee6b355aa0f5ff2953b1ab356eea049108e07"
KARR_SOURCE_CITATIONS = {
    "MacromolecularComplexation": {
        "file": "MacromolecularComplexation.m",
        "line_ranges": [[290, 314], [390, 392]],
        "symbols": ["evolveState", "buildProteinComplexs_bounds"],
    },
    "ProteinProcessingI": {
        "file": "ProteinProcessingI.m",
        "line_ranges": [[236, 320]],
        "symbols": ["evolveState"],
    },
    "ProteinProcessingII": {
        "file": "ProteinProcessingII.m",
        "line_ranges": [[348, 446]],
        "symbols": ["evolveState"],
    },
    "ProteinFolding": {
        "file": "ProteinFolding.m",
        "line_ranges": [[507, 517], [519, 581]],
        "symbols": ["calcResourceRequirements_Current", "evolveState"],
    },
    "tRNAAminoacylation": {
        "file": "tRNAAminoacylation.m",
        "line_ranges": [[387, 464]],
        "symbols": ["evolveState"],
    },
}

# Required branch-coverage tags per process. A process may only reach
# H12_CONFIRMED if, across all (seed, tick, unit) samples that are
# regime_valid AND nontrivial AND exact-matched, the UNION of branch_tags
# covers every tag in this set. This is derived from the Karr source's own
# documented dynamical regimes (not fit to observed pass/fail outcomes):
# MacromolecularComplexation's "network_ge2_fires" tag is structurally
# unreachable under this predictor design (see predict_macromolecular_
# complexation docstring) -- that process can therefore never leave
# H12_OBSERVED_REGIME, honestly, without laundering the requirement away.
REQUIRED_BRANCHES = {
    "MacromolecularComplexation": frozenset({"network_1_fires", "network_ge2_fires"}),
    "ProteinProcessingI": frozenset({"deformylase_fires", "metap_cleavage_fires"}),
    "ProteinProcessingII": frozenset({"passthrough_fires", "peptidase_fires", "transferase_fires"}),
    "ProteinFolding": frozenset({"monomer_folding_fires", "complex_folding_fires"}),
    "tRNAAminoacylation": frozenset({"aminoacylation_fires"}),
}

# Well-formed lowercase-hex SHA256 (64 hex chars). Used to reject a forged/
# truncated/non-hex `raw_prediction_hash` (or any other claimed hash field)
# without needing to recompute it -- a cheap structural check, distinct
# from the freshness re-hashes below which DO recompute against on-disk
# files.
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def _is_plain_nonneg_int(value) -> bool:
    """True iff `value` is a real (non-bool) int and is >= 0.

    `bool` is a subtype of `int` in Python (`isinstance(True, int) is
    True`, `True == 1`, `False == 0`) -- every count/rate field an H12
    artifact carries must reject a boolean masquerading as a numeric count,
    or a hand-tampered payload could pass `trivial_mismatch_count == 0` by
    writing `False`, or `exact_match_rate == 1.0` by writing `True`.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_plain_number(value) -> bool:
    """True iff `value` is a real (non-bool) int or float."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _sha256_file(path: Path) -> str:
    """Raw-byte SHA256. Appropriate ONLY for binary artifacts (fixture .mat
    files) where CRLF/LF normalization is meaningless/harmful. Do not use
    this for text source files -- use `_sha256_lf_normalized` instead so
    hashes are stable across a Windows (CRLF-checkout) vs. Linux (LF-checkout)
    clone of the same git blob.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_lf_normalized(path: Path) -> str:
    """SHA256 of a text file's content after CRLF/CR -> LF normalization.

    This matches what `git hash-object` would see for a blob checked out
    under this repo's `* text=auto eol=lf` attribute (see .gitattributes),
    without shelling out to git at verification time -- so hashes are
    reproducible on a fresh clone regardless of the checkout's line-ending
    conversion, and independent of whether git itself is available/configured
    identically in the verifying environment.
    """
    data = path.read_bytes()
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_array(arr: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()


def karr_source_citation(process: str) -> dict:
    """Build the vendored-Karr-source citation record for `process`,
    hard-failing (no soft-trust) if the vendored file is missing. Never
    claim a source hash for a file we cannot actually read.
    """
    spec = KARR_SOURCE_CITATIONS[process]
    path = KARR_SOURCE_ROOT / spec["file"]
    if not path.is_file():
        raise FileNotFoundError(
            f"vendored Karr source missing for {process!r}: {path} "
            "(H12 must not claim a source hash for a file it cannot read)"
        )
    return {
        "vendored_path": path.relative_to(REPO_ROOT).as_posix(),
        "vendored_sha256_lf_normalized": _sha256_lf_normalized(path),
        "upstream_repo": KARR_UPSTREAM_REPO,
        "upstream_commit": KARR_UPSTREAM_COMMIT,
        "upstream_original_path": spec["file"],
        "line_ranges": spec["line_ranges"],
        "symbols": spec["symbols"],
    }


def _path_for_artifact(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _load_oracle_manifest() -> dict:
    if not ORACLE_MANIFEST_PATH.is_file():
        return {}
    with open(ORACLE_MANIFEST_PATH, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    lookup: dict[tuple[str, str], str] = {}
    for process, entry in manifest.get("processes", {}).items():
        for f in entry.get("files", []):
            lookup[(process, f["relative_path"])] = f["sha256"]
    return lookup


def cross_check_oracle_manifest(process: str, relative_path: str, computed_sha256: str, manifest_lookup: dict) -> str:
    """Cross-check a freshly-computed oracle trace hash against the existing,
    mechanically-generated `oracle_population_manifest.json` (built by
    populate.py). Returns "match" | "mismatch" | "not_in_manifest". This is a
    cross-check, not blind trust: H12 always computes its OWN hash from the
    file it actually read; the manifest is corroborating evidence only.
    """
    expected = manifest_lookup.get((process, relative_path))
    if expected is None:
        return "not_in_manifest"
    return "match" if expected == computed_sha256 else "mismatch"


# ---------------------------------------------------------------------------
# Fixture loading (static Karr knowledge-base parameters; scipy.io.loadmat
# only — these .mat files are NOT MATLAB v7.3/HDF5). No SUT imports.
# ---------------------------------------------------------------------------


def _mat_struct(process: str):
    path = FIXTURE_ROOT / f"{process}_flat.mat"
    return loadmat(str(path))["data"]["fixture"][0, 0], path


def _field(struct, name: str) -> np.ndarray:
    return np.asarray(struct[name][0, 0])


def load_fixture(process: str) -> dict:
    """Load the static Karr fixture parameters this process's predictor needs.

    Returns a dict with a reserved ``__fixture_path__``/``__fixture_sha256__``
    pair (provenance) plus process-specific numpy arrays. 1-based MATLAB
    indices are converted to 0-based on load, clearly suffixed ``_0b``.
    """
    struct, path = _mat_struct(process)
    sha = _sha256_file(path)
    out: dict = {"__fixture_path__": path.relative_to(REPO_ROOT).as_posix(), "__fixture_sha256__": sha}

    if process == "MacromolecularComplexation":
        out["complexComposition"] = _field(struct, "complexComposition").astype(np.int64)
        out["substrates2complexNetworks"] = _field(struct, "substrates2complexNetworks").astype(np.int64).ravel()
        out["complexs2complexNetworks"] = _field(struct, "complexs2complexNetworks").astype(np.int64).ravel()

    elif process == "ProteinProcessingI":
        out["substrateIndexs_water_0b"] = int(_field(struct, "substrateIndexs_water").ravel()[0]) - 1
        out["substrateIndexs_hydrogen_0b"] = int(_field(struct, "substrateIndexs_hydrogen").ravel()[0]) - 1
        out["substrateIndexs_methionine_0b"] = int(_field(struct, "substrateIndexs_methionine").ravel()[0]) - 1
        out["substrateIndexs_formate_0b"] = int(_field(struct, "substrateIndexs_formate").ravel()[0]) - 1
        out["enzymeIndexs_deformylase_0b"] = int(_field(struct, "enzymeIndexs_deformylase").ravel()[0]) - 1
        out["enzymeIndexs_methionineAminoPeptidase_0b"] = (
            int(_field(struct, "enzymeIndexs_methionineAminoPeptidase").ravel()[0]) - 1
        )
        out["deformylaseSpecificRate"] = float(_field(struct, "deformylaseSpecificRate").ravel()[0])
        out["methionineAminoPeptidaseSpecificRate"] = float(
            _field(struct, "methionineAminoPeptidaseSpecificRate").ravel()[0]
        )
        out["stepSizeSec"] = float(_field(struct, "stepSizeSec").ravel()[0])
        out["cleavage_mask"] = _field(struct, "nascentMonomerNTerminalMethionineCleavages").astype(bool).ravel()

    elif process == "ProteinProcessingII":
        out["substrateIndexs_water_0b"] = int(_field(struct, "substrateIndexs_water").ravel()[0]) - 1
        out["substrateIndexs_hydrogen_0b"] = int(_field(struct, "substrateIndexs_hydrogen").ravel()[0]) - 1
        out["substrateIndexs_PG160_0b"] = int(_field(struct, "substrateIndexs_PG160").ravel()[0]) - 1
        out["substrateIndexs_SNGLYP_0b"] = int(_field(struct, "substrateIndexs_SNGLYP").ravel()[0]) - 1
        out["enzymeIndexs_signalPeptidase_0b"] = int(_field(struct, "enzymeIndexs_signalPeptidase").ravel()[0]) - 1
        out["enzymeIndexs_diacylglycerylTransferase_0b"] = (
            int(_field(struct, "enzymeIndexs_diacylglycerylTransferase").ravel()[0]) - 1
        )
        out["lipoproteinSignalPeptidaseSpecificRate"] = float(
            _field(struct, "lipoproteinSignalPeptidaseSpecificRate").ravel()[0]
        )
        out["lipoproteinDiacylglycerylTransferaseSpecificRate"] = float(
            _field(struct, "lipoproteinDiacylglycerylTransferaseSpecificRate").ravel()[0]
        )
        out["stepSizeSec"] = float(_field(struct, "stepSizeSec").ravel()[0])
        out["unprocessedMonomerIndexs_0b"] = _field(struct, "unprocessedMonomerIndexs").astype(np.int64).ravel() - 1
        out["lipoproteinMonomerIndexs_0b"] = _field(struct, "lipoproteinMonomerIndexs").astype(np.int64).ravel() - 1
        out["secretedMonomerIndexs_0b"] = _field(struct, "secretedMonomerIndexs").astype(np.int64).ravel() - 1

    elif process == "ProteinFolding":
        out["substrateIndexs_water_0b"] = int(_field(struct, "substrateIndexs_water").ravel()[0]) - 1
        out["substrateIndexs_hydrogen_0b"] = int(_field(struct, "substrateIndexs_hydrogen").ravel()[0]) - 1
        out["proteinProstheticGroupMatrix"] = _field(struct, "proteinProstheticGroupMatrix").astype(np.float64)
        out["proteinChaperoneMatrix"] = _field(struct, "proteinChaperoneMatrix").astype(np.float64)
        out["monomerComplexIndexs_folded_0b"] = (
            _field(struct, "monomerComplexIndexs_folded").astype(np.int64).ravel() - 1
        )
        out["complexIndexs_folding_0b"] = _field(struct, "complexIndexs_folding").astype(np.int64).ravel() - 1
        out["complexIndexs_notFolding_0b"] = _field(struct, "complexIndexs_notFolding").astype(np.int64).ravel() - 1
        out["speciesIndexs_monomers_0b"] = _field(struct, "speciesIndexs_monomers").astype(np.int64).ravel() - 1
        out["speciesIndexs_complexs_0b"] = _field(struct, "speciesIndexs_complexs").astype(np.int64).ravel() - 1

    elif process == "tRNAAminoacylation":
        out["substrateIndexs_water_0b"] = int(_field(struct, "substrateIndexs_water").ravel()[0]) - 1
        out["substrateIndexs_hydrogen_0b"] = int(_field(struct, "substrateIndexs_hydrogen").ravel()[0]) - 1
        out["speciesIndexs_enzymes_0b"] = _field(struct, "speciesIndexs_enzymes").astype(np.int64).ravel() - 1
        out["speciesReactantByproductMatrix"] = _field(struct, "speciesReactantByproductMatrix").astype(np.float64)
        out["reactionStoichiometryMatrix"] = _field(struct, "reactionStoichiometryMatrix").astype(np.float64)
        out["reactionModificationMatrix"] = _field(struct, "reactionModificationMatrix").astype(np.float64)

    else:
        raise ValueError(f"unknown process {process!r}")

    return out


# ---------------------------------------------------------------------------
# Oracle trace loading (raw Karr per-tick traces; MATLAB v7.3/HDF5 -> h5py
# only). We deliberately do NOT import tests/vivarium/_l2_2_design_a_runner_
# helpers.py (the harness's own oracle loader) to keep this reading path
# independent, even though it means re-deriving the same HDF5-dereference
# pattern here.
# ---------------------------------------------------------------------------


def _resolve_oracle_path(process: str, seed: int) -> Path:
    if seed == 0:
        candidate = ORACLE_ROOT / f"{process}_100ticks.mat"
        if candidate.exists():
            return candidate
    candidate = ORACLE_ROOT.parent / f"per_process_traces_v2_s{seed:03d}" / f"{process}_100ticks.mat"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"no oracle trace for process={process} seed={seed}")


@dataclass(frozen=True)
class TraceWindowEntry:
    seed: int
    process: str
    trace_path: Path
    trace_sha256: str
    trace_schema: str
    trace_tick_start: int
    trace_tick_end: int
    window_tick_start: int
    window_tick_end: int
    window_length_ticks: int

    @property
    def slice_start_0b(self) -> int:
        return self.window_tick_start - self.trace_tick_start

    @property
    def slice_stop_0b(self) -> int:
        return self.slice_start_0b + self.window_length_ticks


def load_trace_window_manifest(
    manifest_path: Path,
    *,
    expected_process: str | None = None,
    expected_window_ticks: int | None = None,
) -> tuple[dict[int, TraceWindowEntry], dict]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != TRACE_WINDOW_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"trace-window manifest schema_version must be {TRACE_WINDOW_MANIFEST_SCHEMA_VERSION!r} "
            f"(got {payload.get('schema_version')!r})"
        )
    process = payload.get("process")
    if not isinstance(process, str) or not process:
        raise ValueError("trace-window manifest process must be a non-empty string")
    if expected_process is not None and process != expected_process:
        raise ValueError(
            f"trace-window manifest process {process!r} does not match expected process {expected_process!r}"
        )
    entries_payload = payload.get("entries")
    if not isinstance(entries_payload, dict) or not entries_payload:
        raise ValueError("trace-window manifest entries must be a non-empty dict keyed by seed")
    manifest_window_ticks = payload.get("window_length_ticks")
    if expected_window_ticks is not None:
        if manifest_window_ticks is not None and manifest_window_ticks != expected_window_ticks:
            raise ValueError(
                f"trace-window manifest window_length_ticks={manifest_window_ticks!r} "
                f"does not match expected {expected_window_ticks}"
            )

    entries: dict[int, TraceWindowEntry] = {}
    for seed_key, entry_payload in entries_payload.items():
        if not isinstance(entry_payload, dict):
            raise ValueError(f"trace-window entry for seed key {seed_key!r} is not an object")
        seed = entry_payload.get("seed")
        entry_process = entry_payload.get("process")
        trace_path_value = entry_payload.get("trace_path")
        trace_sha256 = entry_payload.get("trace_sha256")
        trace_schema = entry_payload.get("trace_schema")
        trace_tick_start = entry_payload.get("trace_tick_start")
        trace_tick_end = entry_payload.get("trace_tick_end")
        window_tick_start = entry_payload.get("window_tick_start")
        window_tick_end = entry_payload.get("window_tick_end")
        window_length_ticks = entry_payload.get("window_length_ticks")

        if not _is_plain_nonneg_int(seed):
            raise ValueError(f"trace-window entry {seed_key!r} has invalid seed {seed!r}")
        if str(seed) != str(seed_key):
            raise ValueError(
                f"trace-window entry key/seed mismatch: key={seed_key!r} seed={seed!r}"
            )
        if entry_process != process:
            raise ValueError(
                f"trace-window entry seed={seed} process {entry_process!r} does not match manifest process {process!r}"
            )
        if not isinstance(trace_path_value, str) or not trace_path_value:
            raise ValueError(f"trace-window entry seed={seed} trace_path must be a non-empty string")
        if not (isinstance(trace_sha256, str) and _SHA256_HEX_RE.fullmatch(trace_sha256)):
            raise ValueError(f"trace-window entry seed={seed} trace_sha256 is not a lowercase hex sha256")
        if not isinstance(trace_schema, str) or not trace_schema:
            raise ValueError(f"trace-window entry seed={seed} trace_schema must be a non-empty string")
        if not (
            _is_plain_nonneg_int(trace_tick_start)
            and _is_plain_nonneg_int(trace_tick_end)
            and _is_plain_nonneg_int(window_tick_start)
            and _is_plain_nonneg_int(window_tick_end)
            and _is_plain_nonneg_int(window_length_ticks)
        ):
            raise ValueError(f"trace-window entry seed={seed} has invalid tick metadata")
        if trace_tick_start < 1 or window_tick_start < 1:
            raise ValueError(f"trace-window entry seed={seed} tick ranges must be 1-based positive integers")
        if trace_tick_end < trace_tick_start:
            raise ValueError(f"trace-window entry seed={seed} trace_tick_end precedes trace_tick_start")
        if window_tick_end < window_tick_start:
            raise ValueError(f"trace-window entry seed={seed} window_tick_end precedes window_tick_start")
        if window_length_ticks != window_tick_end - window_tick_start + 1:
            raise ValueError(
                f"trace-window entry seed={seed} window_length_ticks does not match window_tick range"
            )
        if expected_window_ticks is not None and window_length_ticks != expected_window_ticks:
            raise ValueError(
                f"trace-window entry seed={seed} window_length_ticks={window_length_ticks} "
                f"does not match expected {expected_window_ticks}"
            )
        if window_tick_start < trace_tick_start or window_tick_end > trace_tick_end:
            raise ValueError(
                f"trace-window entry seed={seed} window [{window_tick_start}, {window_tick_end}] "
                f"is outside source trace [{trace_tick_start}, {trace_tick_end}]"
            )

        trace_path = Path(trace_path_value)
        if not trace_path.is_absolute():
            trace_path = (manifest_path.parent / trace_path).resolve()
        if not trace_path.is_file():
            raise FileNotFoundError(f"trace-window entry seed={seed} source trace missing: {trace_path}")

        if seed in entries:
            raise ValueError(f"trace-window manifest contains duplicate seed entry {seed}")
        entries[seed] = TraceWindowEntry(
            seed=seed,
            process=process,
            trace_path=trace_path,
            trace_sha256=trace_sha256,
            trace_schema=trace_schema,
            trace_tick_start=trace_tick_start,
            trace_tick_end=trace_tick_end,
            window_tick_start=window_tick_start,
            window_tick_end=window_tick_end,
            window_length_ticks=window_length_ticks,
        )
    return entries, payload


def _load_oracle_slice(path: Path, start_0b: int, n_ticks: int) -> tuple[dict, dict]:
    before: dict = {}
    after: dict = {}
    with h5py.File(path, "r") as handle:
        avail_ticks = int(np.asarray(handle["metadata"]["n_ticks"][()]).ravel()[0])
        if start_0b < 0 or n_ticks < 0 or start_0b + n_ticks > avail_ticks:
            raise ValueError(
                f"requested trace slice [{start_0b}, {start_0b + n_ticks}) is outside available tick range "
                f"0..{avail_ticks}"
            )
        for phase_name, phase_dict in (("states_before", before), ("states_after", after)):
            group = handle[phase_name]
            for channel in group.keys():
                refs = group[channel][0, start_0b : start_0b + n_ticks]
                rows = [np.asarray(handle[ref][()]).ravel() for ref in refs]
                phase_dict[channel] = np.stack(rows, axis=0)
    return before, after


def load_oracle_seed(
    process: str,
    seed: int,
    n_ticks: int,
    *,
    trace_window: TraceWindowEntry | None = None,
) -> tuple[dict, dict, str]:
    """Load ``states_before``/``states_after`` channel arrays for one seed.

    Returns ``(before, after, file_sha256)`` where ``before``/``after`` map
    channel name -> array of shape (n_ticks, width). Only the first
    ``n_ticks`` ticks (catalog M) are loaded.
    """
    if trace_window is not None:
        if trace_window.process != process:
            raise ValueError(
                f"trace-window entry process {trace_window.process!r} does not match requested process {process!r}"
            )
        if trace_window.seed != seed:
            raise ValueError(
                f"trace-window entry seed {trace_window.seed} does not match requested seed {seed}"
            )
        if trace_window.window_length_ticks != n_ticks:
            raise ValueError(
                f"trace-window entry seed={seed} window_length_ticks={trace_window.window_length_ticks} "
                f"does not match requested n_ticks={n_ticks}"
            )
        sha = _sha256_file(trace_window.trace_path)
        if sha != trace_window.trace_sha256:
            raise ValueError(
                f"trace-window entry seed={seed} source hash mismatch: manifest={trace_window.trace_sha256} "
                f"disk={sha}"
            )
        before, after = _load_oracle_slice(trace_window.trace_path, trace_window.slice_start_0b, n_ticks)
        return before, after, sha

    path = _resolve_oracle_path(process, seed)
    sha = _sha256_file(path)
    before: dict = {}
    after: dict = {}
    with h5py.File(path, "r") as handle:
        avail_ticks = int(np.asarray(handle["metadata"]["n_ticks"][()]).ravel()[0])
        use_ticks = min(n_ticks, avail_ticks)
        for phase_name, phase_dict in (("states_before", before), ("states_after", after)):
            group = handle[phase_name]
            for channel in group.keys():
                refs = group[channel][0, :use_ticks]
                rows = [np.asarray(handle[ref][()]).ravel() for ref in refs]
                phase_dict[channel] = np.stack(rows, axis=0)
    return before, after, sha


# ---------------------------------------------------------------------------
# Prediction result container
# ---------------------------------------------------------------------------


@dataclass
class UnitPrediction:
    """One independently-verifiable (seed, tick, unit) prediction.

    `index_mask` scopes the comparison: for a channel present in
    `index_mask`, ONLY those indices of `predicted_delta[channel]` are
    diffed against `states_after`; indices this unit does not claim to
    predict are simply not this unit's business (a DIFFERENT unit, e.g. a
    different MacromolecularComplexation network active in the same tick,
    may legitimately have produced a nonzero actual delta there). A channel
    absent from `index_mask` is compared full-width (this is correct for
    every process except MacromolecularComplexation, where each unit's
    `predicted_delta` arrays are already zero-elsewhere-scoped to its own
    network but the ACTUAL delta array is not).
    """

    seed: int
    tick: int
    unit: str
    regime_valid: bool
    regime_reason: str
    nontrivial: bool
    predicted_delta: dict = field(default_factory=dict)  # channel -> np.ndarray (full-width delta)
    index_mask: dict = field(default_factory=dict)  # channel -> np.ndarray of indices this unit owns
    branch_tags: frozenset = field(default_factory=frozenset)  # named sub-mechanisms exercised this sample


# ---------------------------------------------------------------------------
# Predictors
#
# Each predict_<process> function:
#   - receives `before`: dict[channel] -> np.ndarray shape (n_ticks, width) for
#     ONE seed (states_before only)
#   - receives `fixture`: dict from load_fixture(process)
#   - returns a list[UnitPrediction], one (or more) entries per tick
#
# No predict_* function may reference `after`/states_after/any SUT module.
# ---------------------------------------------------------------------------


def predict_macromolecular_complexation(seed: int, before: dict, fixture: dict) -> list[UnitPrediction]:
    """MacromolecularComplexation.m evolveState (source lines 290-314) +
    buildProteinComplexs_bounds (lines 390-392, vendored at
    data/karr_vendored_source/MacromolecularComplexation.m):

        newComplexs(complexs2complexNetworks==1) = buildProteinComplexs_bounds(
            substrates(substrates2complexNetworks==1), complexNetworks{1})
        ub = floor(min(totalProteinMonomers ./ proteinComplexMatrix, [], 1))

    Network 1 ("no competition") is Karr's OWN deterministic ground truth —
    not an approximation of a stochastic process. For network>=2 (genuine
    Monte Carlo competition, buildProteinComplexs_montecarlokinetic, lines
    334-357), the same upper-bound formula applies; per-tick substrate
    consumption for a network's rows can only shrink `ub` monotonically
    within a tick (never grow it), so if pre-tick `ub[c]==0` for every
    complex in a connected network component, that component is *provably*
    guaranteed to build 0 new complexes this tick, regardless of RNG path.
    If any `ub[c]>0` in a network>=2 component, the outcome is genuinely
    stochastic and that component's samples are excluded (regime_valid=False).

    STRUCTURAL LIMIT (see H12_REPORT.md): for network>=2, `nontrivial=True`
    can only co-occur with `regime_valid=False` (the "genuine competition"
    case) -- the `regime_valid=True` branch for network>=2 is BY
    CONSTRUCTION the all-`ub==0` (trivial) case. So a network>=2 unit can
    NEVER be simultaneously regime_valid, nontrivial, and therefore never
    contributes to `branches_confirmed`; "network_ge2_fires" is a required
    branch (REQUIRED_BRANCHES) that is structurally unreachable under this
    predictor design, which is why this process is capped at
    H12_OBSERVED_REGIME, not a temporary gap to be closed later without a
    genuinely new Monte-Carlo-aware predictor extraction.

    Each unit's `index_mask` scopes comparison to ONLY this network's own
    substrate/complex indices -- a different network active in the same
    tick must not cause a false mismatch here (the bug that produced "814
    false failures" under a naive full-width compare).
    """
    comp = fixture["complexComposition"]  # (n_substrates, n_complexes)
    sub_net = fixture["substrates2complexNetworks"]  # (n_substrates,)
    cx_net = fixture["complexs2complexNetworks"]  # (n_complexes,)
    n_ticks = before["substrates"].shape[0]
    n_complexes = comp.shape[1]

    networks = sorted(set(int(n) for n in cx_net if n > 0))
    out: list[UnitPrediction] = []

    for tick in range(n_ticks):
        substrates_before = before["substrates"][tick].astype(np.float64)
        for net in networks:
            cx_mask = cx_net == net
            sub_mask = sub_net == net
            sub_idx = np.where(sub_mask)[0]
            cx_idx = np.where(cx_mask)[0]
            if sub_idx.size == 0 or cx_idx.size == 0:
                continue
            block = comp[np.ix_(sub_idx, cx_idx)].astype(np.float64)
            pool = substrates_before[sub_idx]
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = np.where(block > 0, pool[:, None] / np.where(block > 0, block, 1.0), np.inf)
            ub = np.floor(np.min(ratio, axis=0))
            ub = np.where(np.isfinite(ub), ub, 0.0)
            ub = np.maximum(ub, 0.0)

            complexs_delta = np.zeros(n_complexes, dtype=np.float64)
            substrates_delta = np.zeros(comp.shape[0], dtype=np.float64)

            if net == 1:
                # Karr's own literal ground truth for this network — always valid.
                complexs_delta[cx_idx] = ub
                substrates_delta[sub_idx] = -(block @ ub)
                nontrivial = bool(np.any(ub > 0))
                out.append(
                    UnitPrediction(
                        seed=seed,
                        tick=tick,
                        unit=f"network_{net}",
                        regime_valid=True,
                        regime_reason="network_1_karr_ground_truth_no_competition",
                        nontrivial=nontrivial,
                        predicted_delta={"complexs": complexs_delta, "substrates": substrates_delta},
                        index_mask={"complexs": cx_idx, "substrates": sub_idx},
                        branch_tags=frozenset({"network_1_fires"}) if nontrivial else frozenset(),
                    )
                )
            else:
                if np.all(ub == 0):
                    out.append(
                        UnitPrediction(
                            seed=seed,
                            tick=tick,
                            unit=f"network_{net}",
                            regime_valid=True,
                            regime_reason="network_ge2_all_bounds_zero_monotonic_guarantee",
                            nontrivial=False,
                            predicted_delta={"complexs": complexs_delta, "substrates": substrates_delta},
                            index_mask={"complexs": cx_idx, "substrates": sub_idx},
                            branch_tags=frozenset(),
                        )
                    )
                else:
                    out.append(
                        UnitPrediction(
                            seed=seed,
                            tick=tick,
                            unit=f"network_{net}",
                            regime_valid=False,
                            regime_reason="network_ge2_nonzero_bound_genuine_monte_carlo_competition",
                            nontrivial=False,
                            predicted_delta={},
                            index_mask={},
                            branch_tags=frozenset({"network_ge2_fires"}),
                        )
                    )
    return out


def predict_protein_processing_i(seed: int, before: dict, fixture: dict) -> list[UnitPrediction]:
    """ProteinProcessingI.m evolveState (source lines 236-320).

    deformylaseLimit = enzymes[deformylase] * deformylaseSpecificRate * stepSizeSec
    cleavageLimit     = enzymes[metAP]       * methionineAminoPeptidaseSpecificRate * stepSizeSec

    If deformylaseLimit >= sum(unprocessedMonomers) AND
       cleavageLimit    >= sum(unprocessedMonomers[cleavage_mask]) (or that
       sum is 0) AND water >= sum(all) + sum(cleavage_mask):
    then block 1's per-species scale factors are both exactly 1, so
    stochasticRound() acts on already-integer values (no-op, p=1), the water
    mnrnd-rationing branch's `if` guard is false (skipped), and ALL
    unprocessedMonomers are processed this tick — deterministically,
    regardless of RNG. Block 2 (lines 298-318) then sees an all-zero
    remainder and is a no-op.
    """
    water_0b = fixture["substrateIndexs_water_0b"]
    hydrogen_0b = fixture["substrateIndexs_hydrogen_0b"]
    methionine_0b = fixture["substrateIndexs_methionine_0b"]
    formate_0b = fixture["substrateIndexs_formate_0b"]
    deform_0b = fixture["enzymeIndexs_deformylase_0b"]
    metap_0b = fixture["enzymeIndexs_methionineAminoPeptidase_0b"]
    rate_deform = fixture["deformylaseSpecificRate"]
    rate_metap = fixture["methionineAminoPeptidaseSpecificRate"]
    dt = fixture["stepSizeSec"]
    cleavage_mask = fixture["cleavage_mask"]

    n_ticks = before["unprocessedMonomers"].shape[0]
    out: list[UnitPrediction] = []
    for tick in range(n_ticks):
        unproc = before["unprocessedMonomers"][tick].astype(np.float64)
        enzymes = before["enzymes"][tick].astype(np.float64)
        water = float(before["substrates"][tick][water_0b])

        total = float(unproc.sum())
        cleave_sum = float(unproc[cleavage_mask].sum())
        deform_limit = float(enzymes[deform_0b] * rate_deform * dt)
        cleave_limit = float(enzymes[metap_0b] * rate_metap * dt)

        regime_valid = (
            deform_limit >= total
            and (cleave_sum == 0.0 or cleave_limit >= cleave_sum)
            and water >= (total + cleave_sum)
        )
        nontrivial = total > 0.0
        if not regime_valid:
            out.append(
                UnitPrediction(
                    seed=seed,
                    tick=tick,
                    unit="all",
                    regime_valid=False,
                    regime_reason="capacity_or_water_guard_failed",
                    nontrivial=False,
                    predicted_delta={},
                )
            )
            continue

        n_substrates = before["substrates"].shape[1]
        substrates_delta = np.zeros(n_substrates, dtype=np.float64)
        substrates_delta[water_0b] -= total + cleave_sum
        substrates_delta[formate_0b] += total
        substrates_delta[hydrogen_0b] += total
        substrates_delta[methionine_0b] += cleave_sum

        out.append(
            UnitPrediction(
                seed=seed,
                tick=tick,
                unit="all",
                regime_valid=True,
                regime_reason="full_saturating_closed_form",
                nontrivial=nontrivial,
                predicted_delta={
                    "unprocessedMonomers": -unproc,
                    "processedMonomers": unproc.copy(),
                    "substrates": substrates_delta,
                    "enzymes": np.zeros_like(enzymes),
                },
                branch_tags=frozenset(
                    tag
                    for tag, active in (
                        ("deformylase_fires", total > 0.0),
                        ("metap_cleavage_fires", cleave_sum > 0.0),
                    )
                    if active
                ),
            )
        )
    return out


def predict_protein_processing_ii(seed: int, before: dict, fixture: dict) -> list[UnitPrediction]:
    """ProteinProcessingII.m evolveState (source lines 348-446).

    Unconditional pass-through of `unprocessedMonomerIndexs` (no processing
    needed) always happens first, deterministically. The remaining
    lipoprotein (`transferaseIndexs`) + secreted (`peptidaseIndexs`) pools
    are then processed via two sequential blocks gated by
    peptidaseLimit/transferaseLimit + water/PG160. If the aggregate
    peptidase and transferase capacities meet or exceed the aggregate
    demand from BOTH indices sets, and water/PG160 both meet or exceed
    consumption, block 1's scale factors are exactly 1 (stochasticRound
    no-op) and block 1 fully processes everything; block 2 then sees an
    all-zero remainder (no-op).
    """
    water_0b = fixture["substrateIndexs_water_0b"]
    hydrogen_0b = fixture["substrateIndexs_hydrogen_0b"]
    pg160_0b = fixture["substrateIndexs_PG160_0b"]
    snglyp_0b = fixture["substrateIndexs_SNGLYP_0b"]
    peptidase_enz_0b = fixture["enzymeIndexs_signalPeptidase_0b"]
    transferase_enz_0b = fixture["enzymeIndexs_diacylglycerylTransferase_0b"]
    rate_peptidase = fixture["lipoproteinSignalPeptidaseSpecificRate"]
    rate_transferase = fixture["lipoproteinDiacylglycerylTransferaseSpecificRate"]
    dt = fixture["stepSizeSec"]
    passthrough_idx = fixture["unprocessedMonomerIndexs_0b"]
    lipoprotein_idx = fixture["lipoproteinMonomerIndexs_0b"]
    secreted_idx = fixture["secretedMonomerIndexs_0b"]
    peptidase_idx = np.concatenate([lipoprotein_idx, secreted_idx])
    transferase_idx = lipoprotein_idx

    n_ticks = before["unprocessedMonomers"].shape[0]
    out: list[UnitPrediction] = []
    for tick in range(n_ticks):
        unproc = before["unprocessedMonomers"][tick].astype(np.float64)
        enzymes = before["enzymes"][tick].astype(np.float64)
        water = float(before["substrates"][tick][water_0b])
        pg160 = float(before["substrates"][tick][pg160_0b])

        # unconditional pass-through is always deterministic, independent of guard
        passthrough_delta = np.zeros_like(unproc)
        passthrough_delta[passthrough_idx] = unproc[passthrough_idx]

        peptidase_demand = float(unproc[peptidase_idx].sum())
        transferase_demand = float(unproc[transferase_idx].sum())
        peptidase_limit = float(enzymes[peptidase_enz_0b] * rate_peptidase * dt)
        transferase_limit = float(enzymes[transferase_enz_0b] * rate_transferase * dt)

        regime_valid = (
            peptidase_limit >= peptidase_demand
            and (transferase_demand == 0.0 or transferase_limit >= transferase_demand)
            and water >= peptidase_demand
            and (transferase_demand == 0.0 or pg160 >= transferase_demand)
        )
        nontrivial = (peptidase_demand + float(unproc[passthrough_idx].sum())) > 0.0

        if not regime_valid:
            out.append(
                UnitPrediction(
                    seed=seed,
                    tick=tick,
                    unit="all",
                    regime_valid=False,
                    regime_reason="capacity_or_metabolite_guard_failed",
                    nontrivial=False,
                    predicted_delta={},
                )
            )
            continue

        n_substrates = before["substrates"].shape[1]
        substrates_delta = np.zeros(n_substrates, dtype=np.float64)
        substrates_delta[water_0b] -= peptidase_demand
        substrates_delta[pg160_0b] -= transferase_demand
        substrates_delta[snglyp_0b] += transferase_demand
        substrates_delta[hydrogen_0b] += transferase_demand

        unproc_delta = -unproc.copy()
        processed_delta = unproc.copy()
        signal_delta = np.zeros_like(unproc)
        signal_delta[peptidase_idx] = unproc[peptidase_idx]
        # passthrough species are not signal-cleaved
        signal_delta[passthrough_idx] = 0.0

        out.append(
            UnitPrediction(
                seed=seed,
                tick=tick,
                unit="all",
                regime_valid=True,
                regime_reason="full_saturating_closed_form",
                nontrivial=nontrivial,
                predicted_delta={
                    "unprocessedMonomers": unproc_delta,
                    "processedMonomers": processed_delta,
                    "signalSequenceMonomers": signal_delta,
                    "substrates": substrates_delta,
                    "enzymes": np.zeros_like(enzymes),
                },
                branch_tags=frozenset(
                    tag
                    for tag, active in (
                        ("passthrough_fires", float(unproc[passthrough_idx].sum()) > 0.0),
                        ("peptidase_fires", peptidase_demand > 0.0),
                        ("transferase_fires", transferase_demand > 0.0),
                    )
                    if active
                ),
            )
        )
    return out


def predict_protein_folding(seed: int, before: dict, fixture: dict) -> list[UnitPrediction]:
    """ProteinFolding.m evolveState (source lines 519-575), species vector
    construction at line ~535 (vendored, data/karr_vendored_source/
    ProteinFolding.m):

        species = max(0, [substrates; enzymes*Inf; unfoldedMonomers;
                           unfoldedComplexs(complexIndexs_folding)]')

    CORRECTED chaperone-guard semantics (this was WRONG in H12 v1, which
    claimed chaperones are unconditionally non-limiting -- Opus5 review):
    `enzymes * Inf` gives `Inf` for a chaperone present in nonzero count
    (non-limiting, matches v1's assumption) but `0 * Inf == NaN` (IEEE 754)
    for a chaperone at EXACTLY zero count, and MATLAB's `max(0, NaN)` returns
    the non-NaN operand, i.e. `0` -- NOT `Inf`/non-limiting. A species row
    `i` whose `substrateLimits(i, c)` ratio touches a zero-count required
    chaperone column `c` (`proteinChaperoneMatrix(i,c) > 0`) therefore gets
    `species(c)/proteinChaperoneMatrix(i,c) == 0/positive == 0`, which
    dominates that row's `min()` and is then floored to exactly 0 by the
    `substrateLimits<1 -> 0` clamp (line ~543) -- so species `i` can NEVER
    be selected by the `randsample` loop this tick, deterministically. This
    is a PER-SPECIES exclusion (`chaperone_ok[i]`), not a whole-tick guard
    failure: species that do not require the zero-count chaperone are
    unaffected and may still fold fully.

    `complexIndexs_notFolding` complexes pass through unconditionally
    (lines 520-523, always deterministic, independent of chaperones/
    substrates). For the chaperone-ELIGIBLE subset of the 487
    folding-eligible species (all 482 monomers + 5 folding complexes), if,
    for every prosthetic-group substrate column (excl. water/hydrogen,
    non-limiting per lines 546-547), the aggregate demand from folding ALL
    chaperone-eligible unfolded species this tick does not exceed the
    pre-tick available amount, every eligible species folds fully this
    tick, deterministically, regardless of RNG path (the same invariant
    argument as v1, now correctly scoped to the eligible subset only).
    Chaperone-blocked species are asserted to NOT fold (delta=0) regardless
    of the substrate guard, since that exclusion is unconditional.

    On real oracle data (chaperones are constitutively-expressed enzymes,
    virtually never at exactly zero count), this fix is expected to be a
    no-op relative to v1's predictions; it is required for correctness and
    is exercised by synthetic zero-chaperone/prosthetic-scarcity unit tests
    (tests/scripts/test_h12_formulas.py) that v1 could not have passed.
    """
    water_0b = fixture["substrateIndexs_water_0b"]
    hydrogen_0b = fixture["substrateIndexs_hydrogen_0b"]
    ppg = fixture["proteinProstheticGroupMatrix"]  # (683, 11) rows = ALL monomers+complexes
    pcm = fixture["proteinChaperoneMatrix"]  # (683, 5) rows = ALL monomers+complexes
    folded_rows = fixture["monomerComplexIndexs_folded_0b"]  # (487,) into the 683-row space
    complex_folding_0b = fixture["complexIndexs_folding_0b"]  # (5,) into 201-complex space
    complex_notfolding_0b = fixture["complexIndexs_notFolding_0b"]  # (196,)
    species_idx_monomers = fixture["speciesIndexs_monomers_0b"]  # (482,) positions within the 487-row block
    species_idx_complexs = fixture["speciesIndexs_complexs_0b"]  # (5,)

    ppg_folded = ppg[folded_rows, :]  # (487, 11)
    pcm_folded = pcm[folded_rows, :]  # (487, 5)
    n_substrate_cols = ppg.shape[1]
    n_enz_cols = pcm.shape[1]
    guard_cols = [c for c in range(n_substrate_cols) if c not in (water_0b, hydrogen_0b)]

    n_ticks = before["unfoldedMonomers"].shape[0]
    out: list[UnitPrediction] = []
    for tick in range(n_ticks):
        unfolded_monomers = before["unfoldedMonomers"][tick].astype(np.float64)
        unfolded_complexs = before["unfoldedComplexs"][tick].astype(np.float64)
        substrates_before = before["substrates"][tick].astype(np.float64)
        enzymes_before = before["enzymes"][tick].astype(np.float64)

        flux_upper = np.zeros(len(folded_rows), dtype=np.float64)
        flux_upper[species_idx_monomers] = unfolded_monomers
        flux_upper[species_idx_complexs] = unfolded_complexs[complex_folding_0b]

        # max(0, enzymes*Inf) == 0 iff enzymes[c]==0 (see docstring): any
        # species requiring a zero-count chaperone is unconditionally
        # excluded from folding this tick, regardless of substrate supply.
        zero_chaperones = enzymes_before[:n_enz_cols] == 0.0
        if np.any(zero_chaperones):
            chaperone_blocked = np.any(pcm_folded[:, zero_chaperones] > 0.0, axis=1)
        else:
            chaperone_blocked = np.zeros(len(folded_rows), dtype=bool)
        chaperone_ok = ~chaperone_blocked

        eligible_flux = np.where(chaperone_ok, flux_upper, 0.0)

        demand = ppg_folded.T @ eligible_flux  # (11,)
        regime_valid = all(demand[c] <= substrates_before[c] for c in guard_cols)
        nontrivial = bool(np.any(eligible_flux > 0))

        if not regime_valid:
            out.append(
                UnitPrediction(
                    seed=seed,
                    tick=tick,
                    unit="all",
                    regime_valid=False,
                    regime_reason="prosthetic_group_guard_failed",
                    nontrivial=False,
                    predicted_delta={
                        # only the unconditional not-folding passthrough is safe to assert
                        "unfoldedComplexs_notfolding_only": complex_notfolding_0b,
                    },
                )
            )
            continue

        substrates_delta = np.zeros_like(substrates_before)
        substrates_delta[:] = -demand

        eligible_monomers = eligible_flux[species_idx_monomers]
        eligible_complexs = eligible_flux[species_idx_complexs]

        unfolded_monomers_delta = -eligible_monomers
        folded_monomers_delta = eligible_monomers.copy()

        unfolded_complexs_delta = np.zeros_like(unfolded_complexs)
        unfolded_complexs_delta[complex_folding_0b] = -eligible_complexs
        unfolded_complexs_delta[complex_notfolding_0b] = -unfolded_complexs[complex_notfolding_0b]

        folded_complexs_delta = np.zeros_like(unfolded_complexs)
        folded_complexs_delta[complex_folding_0b] = eligible_complexs
        folded_complexs_delta[complex_notfolding_0b] = unfolded_complexs[complex_notfolding_0b]

        out.append(
            UnitPrediction(
                seed=seed,
                tick=tick,
                unit="all",
                regime_valid=True,
                regime_reason="full_saturating_closed_form_chaperone_gated",
                nontrivial=nontrivial,
                predicted_delta={
                    "unfoldedMonomers": unfolded_monomers_delta,
                    "foldedMonomers": folded_monomers_delta,
                    "unfoldedComplexs": unfolded_complexs_delta,
                    "foldedComplexs": folded_complexs_delta,
                    "substrates": substrates_delta,
                    "enzymes": np.zeros_like(enzymes_before),
                },
                branch_tags=frozenset(
                    tag
                    for tag, active in (
                        ("monomer_folding_fires", bool(np.any(eligible_monomers > 0))),
                        ("complex_folding_fires", bool(np.any(eligible_complexs > 0))),
                    )
                    if active
                ),
            )
        )
    return out


def predict_trna_aminoacylation(seed: int, before: dict, fixture: dict) -> list[UnitPrediction]:
    """tRNAAminoacylation.m evolveState (source lines 387-460).

    species = [substrates; enzymes[speciesIndexs_enzymes]; freeRNAs]
    Per-tick loop repeatedly consumes `speciesReactantByproductMatrix` rows
    (one row per tRNA) until `reactionLimits` (capacity ratios, water/H
    exempted) hit zero. Because the tRNA's own free-count column is itself
    one of the ratio columns (identity-like diagonal), a resource other
    than the tRNA's own free-count can only zero out `reactionLimits[j]`
    prematurely if that OTHER resource's total pre-tick supply is smaller
    than the aggregate demand summed across every tRNA/enzyme-budget column
    (substrates, and enzyme "budget" -- enzymes are consumed as a
    within-tick throughput budget, not physically depleted; see citation).
    If, for every non-(water/hydrogen) column, aggregate demand
    (sum_j byproduct[j, c] * freeRNAs_before[j]) does not exceed pre-tick
    supply, every freeRNA gets aminoacylated this tick deterministically
    (empirically spot-verified against real oracle data: seed 0 tick 0).
    Substrate deltas then follow the (separately documented, non-loop)
    bookkeeping formula at lines 458-462:
        substrates += reactionStoichiometryMatrix @ reactionModificationMatrix @ reactionFluxes
    with reactionFluxes == freeRNAs_before (full saturation).
    """
    water_0b = fixture["substrateIndexs_water_0b"]
    hydrogen_0b = fixture["substrateIndexs_hydrogen_0b"]
    enz_cols_0b = fixture["speciesIndexs_enzymes_0b"]  # (21,) column positions in the 88-col species space
    byproduct = fixture["speciesReactantByproductMatrix"]  # (37, 88)
    reaction_stoich = fixture["reactionStoichiometryMatrix"]  # (30, 39)
    reaction_mod = fixture["reactionModificationMatrix"]  # (39, 37)

    n_substrates = reaction_stoich.shape[0]
    n_enz = len(enz_cols_0b)
    enz_col_start = n_substrates  # substrates block occupies cols [0, n_substrates)
    freerna_col_start = n_substrates + n_enz

    guard_cols = [c for c in range(byproduct.shape[1]) if c not in (water_0b, hydrogen_0b, *range(freerna_col_start, byproduct.shape[1]))]

    n_ticks = before["freeRNAs"].shape[0]
    out: list[UnitPrediction] = []
    for tick in range(n_ticks):
        free_rnas = before["freeRNAs"][tick].astype(np.float64)
        aminoacylated = before["aminoacylatedRNAs"][tick].astype(np.float64)
        substrates_before = before["substrates"][tick].astype(np.float64)
        enzymes_before = before["enzymes"][tick].astype(np.float64)

        species_before = np.concatenate([substrates_before, enzymes_before[: n_enz], np.zeros(0)])
        # column-wise available supply for the guard: substrates + enzyme-budget columns
        supply = np.concatenate([substrates_before, enzymes_before[:n_enz]])

        demand = byproduct[:, : freerna_col_start].T @ free_rnas  # (n_substrates+n_enz,)
        regime_valid = all(demand[c] <= supply[c] for c in guard_cols)
        nontrivial = bool(np.any(free_rnas > 0))

        if not regime_valid:
            out.append(
                UnitPrediction(
                    seed=seed,
                    tick=tick,
                    unit="all",
                    regime_valid=False,
                    regime_reason="resource_guard_failed",
                    nontrivial=False,
                    predicted_delta={},
                )
            )
            continue

        reaction_fluxes = free_rnas.copy()  # (37,) per-RNA meta-reaction fluxes
        substrates_delta = reaction_stoich @ (reaction_mod @ reaction_fluxes)

        out.append(
            UnitPrediction(
                seed=seed,
                tick=tick,
                unit="all",
                regime_valid=True,
                regime_reason="full_saturating_closed_form",
                nontrivial=nontrivial,
                predicted_delta={
                    "freeRNAs": -free_rnas,
                    "aminoacylatedRNAs": free_rnas.copy(),
                    "substrates": substrates_delta,
                    "enzymes": np.zeros_like(enzymes_before),
                },
                branch_tags=frozenset({"aminoacylation_fires"}) if nontrivial else frozenset(),
            )
        )
    return out


PREDICTORS: dict[str, Callable[[int, dict, dict], list]] = {
    "MacromolecularComplexation": predict_macromolecular_complexation,
    "ProteinProcessingI": predict_protein_processing_i,
    "ProteinProcessingII": predict_protein_processing_ii,
    "ProteinFolding": predict_protein_folding,
    "tRNAAminoacylation": predict_trna_aminoacylation,
}


# ---------------------------------------------------------------------------
# Compare phase — the ONLY place states_after is read.
# ---------------------------------------------------------------------------


def compare_predictions(process: str, predictions: list[UnitPrediction], after: dict, before: dict) -> dict:
    """Compare frozen predictions against states_after. Never called before
    predictions are fully computed; states_after must not leak into predict_*.

    Each unit's comparison is scoped by its `index_mask` (per-channel index
    subset it actually claims to predict); a channel with no mask entry is
    compared full-width. This fixes the MacromolecularComplexation cross-
    network false-failure bug: a network's unit no longer sees a different,
    simultaneously-active network's real contribution at indices it never
    claimed.

    ANY mismatch on a trivial (regime_valid AND NOT nontrivial, i.e.
    predicted-no-op) sample is tracked as a `trivial_mismatch`, separate
    from `mismatch` (nontrivial prediction mismatches) -- a trivial mismatch
    means the guard logic itself is wrong (it thought nothing would happen,
    but something did), which is a harder failure than a nontrivial exact-
    match miss and must hard-fail the verdict regardless of the nontrivial
    match rate.
    """
    total = 0
    nontrivial = 0
    exact_match = 0
    trivial_checked = 0
    trivial_mismatch_count = 0
    mismatches = []
    trivial_mismatches = []
    branches_confirmed: set = set()
    branches_observed: set = set()

    by_tick: dict[int, list[UnitPrediction]] = {}
    for p in predictions:
        by_tick.setdefault(p.tick, []).append(p)

    def _scoped(channel: str, arr: np.ndarray, unit: UnitPrediction) -> np.ndarray:
        mask = unit.index_mask.get(channel)
        return arr if mask is None else arr[mask]

    for tick, units in by_tick.items():
        for u in units:
            total += 1
            branches_observed |= u.branch_tags
            if not u.regime_valid:
                continue
            if not u.nontrivial:
                # still verify trivial (all-zero) predictions to catch guard bugs,
                # but exclude from the headline nontrivial_sample_count.
                trivial_checked += 1
                ok = True
                for channel, delta in u.predicted_delta.items():
                    if channel.endswith("_only"):
                        continue
                    actual = _scoped(channel, after[channel][tick] - before[channel][tick], u)
                    delta_scoped = _scoped(channel, delta, u)
                    if not np.array_equal(actual, delta_scoped):
                        ok = False
                        break
                if not ok:
                    trivial_mismatch_count += 1
                    if len(trivial_mismatches) < 10:
                        trivial_mismatches.append({"seed": u.seed, "tick": tick, "unit": u.unit})
                continue

            nontrivial += 1
            ok = True
            for channel, delta in u.predicted_delta.items():
                if channel.endswith("_only"):
                    continue
                actual = _scoped(channel, after[channel][tick] - before[channel][tick], u)
                delta_scoped = _scoped(channel, delta, u)
                if not np.array_equal(actual, delta_scoped):
                    ok = False
                    if len(mismatches) < 10:
                        mismatch_mask = actual != delta_scoped
                        idx = np.where(mismatch_mask)[0][:5]
                        mismatches.append(
                            {
                                "seed": u.seed,
                                "tick": tick,
                                "unit": u.unit,
                                "channel": channel,
                                "mismatch_indices": idx.tolist(),
                                "predicted": delta_scoped[idx].tolist(),
                                "actual": actual[idx].tolist(),
                            }
                        )
                    break
            if ok:
                exact_match += 1
                branches_confirmed |= u.branch_tags

    return {
        "total_sample_count": total,
        "nontrivial_sample_count": nontrivial,
        "exact_match_count": exact_match,
        "exact_match_rate": (exact_match / nontrivial) if nontrivial > 0 else None,
        "trivial_checked_count": trivial_checked,
        "trivial_mismatch_count": trivial_mismatch_count,
        "mismatch_examples": mismatches,
        "trivial_mismatch_examples": trivial_mismatches,
        "branches_confirmed": branches_confirmed,
        "branches_observed": branches_observed,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def decide_verdict(
    nontrivial: int,
    exact_match: int,
    exact_match_rate: float | None,
    trivial_mismatch_count: int,
    branches_confirmed: set,
    required_branches: frozenset,
) -> tuple[str, str]:
    """Pure H12 verdict decision, factored out of `run_h12` so it is
    independently unit-testable without oracle/fixture I/O (see
    `tests/scripts/test_h12_artifact.py`).

    H12_CONFIRMED requires ALL of:
      - `trivial_mismatch_count == 0` (the guard logic never wrongly
        predicted "nothing happens" when something did -- ANY such mismatch
        is a harder failure than a nontrivial miss and hard-fails outright).
      - `nontrivial_sample_count > 0` AND a 100% exact match on those
        nontrivial samples -- no tolerance, per the task's "no tolerance
        unless source defines integer/float tolerance pre-registered" rule
        (no process here defines one).
      - full required branch coverage (`REQUIRED_BRANCHES[process]` subset
        of `branches_confirmed`) -- otherwise H12_OBSERVED_REGIME: the
        predictor is 100% correct on every sample it could evaluate, but has
        not exercised every dynamical regime the Karr source defines for
        this process, so it may not be used to clear the evidence gate.
    """
    if trivial_mismatch_count > 0:
        return (
            "H12_FAIL",
            f"trivial_mismatch_count={trivial_mismatch_count} > 0 "
            "(guard logic predicted a no-op but states_after shows nonzero activity)",
        )
    if nontrivial == 0:
        return "H12_FAIL", "nontrivial_sample_count==0 (no samples exercised the guard-satisfied regime)"
    if exact_match != nontrivial:
        return "H12_FAIL", f"exact_match_rate={exact_match_rate:.6f} < 1.0"
    missing = sorted(required_branches - branches_confirmed)
    if missing:
        return (
            "H12_OBSERVED_REGIME",
            f"100% exact match on {nontrivial} nontrivial samples but required branch coverage "
            f"incomplete: missing={missing} (this process may not be used to clear H12_CONFIRMED-gated "
            "sentinels until every required regime is independently confirmed)",
        )
    return "H12_CONFIRMED", "nontrivial_sample_count>0, 100% exact match, full required branch coverage"



def run_h12(process: str, n_seeds: int, m_ticks: int, *, trace_window_manifest_path: Path | None = None) -> dict:
    fixture = load_fixture(process)
    predictor = PREDICTORS[process]
    manifest_lookup = _load_oracle_manifest()
    trace_windows_by_seed: dict[int, TraceWindowEntry] | None = None
    trace_window_manifest_ref: dict | None = None
    if trace_window_manifest_path is not None:
        trace_windows_by_seed, manifest_payload = load_trace_window_manifest(
            trace_window_manifest_path,
            expected_process=process,
            expected_window_ticks=m_ticks,
        )
        expected_seed_set = set(range(n_seeds))
        actual_seed_set = set(trace_windows_by_seed.keys())
        if actual_seed_set != expected_seed_set:
            raise ValueError(
                f"trace-window manifest seeds {sorted(actual_seed_set)} do not match expected "
                f"0..{n_seeds - 1}"
            )
        trace_window_manifest_ref = {
            "path": _path_for_artifact(trace_window_manifest_path),
            "sha256_lf_normalized": _sha256_lf_normalized(trace_window_manifest_path),
            "schema_version": manifest_payload["schema_version"],
        }

    all_predictions: list[UnitPrediction] = []
    oracle_hashes: dict[str, str] = {}
    oracle_manifest_cross_check: dict[str, str] = {}
    prediction_hash_parts = []

    for seed in range(n_seeds):
        trace_window = None if trace_windows_by_seed is None else trace_windows_by_seed[seed]
        before, after, sha = load_oracle_seed(process, seed, m_ticks, trace_window=trace_window)
        oracle_hashes[str(seed)] = sha
        if trace_window is None:
            rel_path = _resolve_oracle_path(process, seed).relative_to(ORACLE_ROOT.parent).as_posix()
            oracle_manifest_cross_check[str(seed)] = cross_check_oracle_manifest(process, rel_path, sha, manifest_lookup)
        else:
            oracle_manifest_cross_check[str(seed)] = "match"
        preds = predictor(seed, before, fixture)
        all_predictions.extend(preds)
        for p in preds:
            prediction_hash_parts.append(
                f"{p.seed}:{p.tick}:{p.unit}:{p.regime_valid}:{p.nontrivial}:"
                + ",".join(f"{k}={_sha256_array(v)}" for k, v in sorted(p.predicted_delta.items()) if isinstance(v, np.ndarray))
            )
        # release `after` reference for this seed; comparisons happen below,
        # re-loading is avoided by comparing per-seed immediately instead.

    raw_prediction_hash = _sha256_bytes("\n".join(prediction_hash_parts).encode("utf-8"))

    # Compare phase: reload per-seed (states_after untouched until here)
    total = nontrivial = exact_match = trivial_checked = trivial_mismatch_count = 0
    mismatches: list = []
    trivial_mismatches: list = []
    branches_confirmed: set = set()
    branches_observed: set = set()
    preds_by_seed: dict[int, list[UnitPrediction]] = {}
    for p in all_predictions:
        preds_by_seed.setdefault(p.seed, []).append(p)

    for seed in range(n_seeds):
        trace_window = None if trace_windows_by_seed is None else trace_windows_by_seed[seed]
        before, after, _sha = load_oracle_seed(process, seed, m_ticks, trace_window=trace_window)
        result = compare_predictions(process, preds_by_seed.get(seed, []), after, before)
        total += result["total_sample_count"]
        nontrivial += result["nontrivial_sample_count"]
        exact_match += result["exact_match_count"]
        trivial_checked += result["trivial_checked_count"]
        trivial_mismatch_count += result["trivial_mismatch_count"]
        branches_confirmed |= result["branches_confirmed"]
        branches_observed |= result["branches_observed"]
        if len(mismatches) < 10:
            mismatches.extend(result["mismatch_examples"][: 10 - len(mismatches)])
        if len(trivial_mismatches) < 10:
            trivial_mismatches.extend(result["trivial_mismatch_examples"][: 10 - len(trivial_mismatches)])

    exact_match_rate = (exact_match / nontrivial) if nontrivial > 0 else None
    required_branches = REQUIRED_BRANCHES[process]
    verdict, verdict_reason = decide_verdict(
        nontrivial, exact_match, exact_match_rate, trivial_mismatch_count, branches_confirmed, required_branches
    )

    module_path = Path(__file__).resolve()
    module_rel_path = module_path.relative_to(REPO_ROOT).as_posix()
    if module_rel_path != EXPECTED_PREDICTOR_SOURCE_PATH:
        raise RuntimeError(
            f"predictor_source_path mismatch: running module resolved to {module_rel_path!r}, "
            f"expected {EXPECTED_PREDICTOR_SOURCE_PATH!r} -- refusing to emit an artifact that "
            "would claim support from the wrong pinned module path"
        )

    artifact = {
        "process": process,
        "formula_version": FORMULA_VERSION,
        "predictor_source_path": module_rel_path,
        "predictor_source_sha256_lf_normalized": _sha256_lf_normalized(module_path),
        "karr_source_citation": karr_source_citation(process),
        "fixture_path": fixture["__fixture_path__"],
        "fixture_sha256": fixture["__fixture_sha256__"],
        "oracle_seed_file_sha256": oracle_hashes,
        "oracle_manifest_cross_check": oracle_manifest_cross_check,
        "n_seeds": n_seeds,
        "m_ticks": m_ticks,
        "catalog_n_seeds": CATALOG_N_M[process][0],
        "catalog_m_ticks": CATALOG_N_M[process][1],
        "total_sample_count": total,
        "nontrivial_sample_count": nontrivial,
        "exact_match_count": exact_match,
        "exact_match_rate": exact_match_rate,
        "trivial_checked_count": trivial_checked,
        "trivial_mismatch_count": trivial_mismatch_count,
        "mismatch_examples": mismatches,
        "trivial_mismatch_examples": trivial_mismatches,
        "required_branches": sorted(required_branches),
        "branches_confirmed": sorted(branches_confirmed),
        "branches_observed": sorted(branches_observed),
        "missing_required_branches": sorted(required_branches - branches_confirmed),
        "raw_prediction_hash": raw_prediction_hash,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anti_laundering_attestation": {
            "predictor_inputs": ["states_before", "static_fixture_params"],
            "states_after_access": "compare_phase_only",
            "no_sut_import": True,
            "no_result_json_access": True,
        },
    }
    if trace_window_manifest_ref is not None:
        artifact["oracle_trace_window_manifest_ref"] = trace_window_manifest_ref
    return artifact


def validate_h12_support(payload: dict, *, expected_process: str | None = None, repo_root: Path = REPO_ROOT) -> str | None:
    """Centralized H12-artifact acceptance gate. Returns None if `payload`
    (an already-loaded H12 artifact JSON dict) is valid, fresh, machine-
    checked support for clearing a PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE
    sentinel; otherwise a short rejection reason string.

    This is the single source of truth for "what does a valid H12 artifact
    look like" -- verdict.py's `h12_support_reason` delegates here rather
    than re-implementing the schema/hash checks, so the producer (this
    module) and the consumer (the evidence gate) cannot drift apart.

    `expected_process`, when given (verdict.py always supplies it: the
    process name under which the row's `h12_evidence_ref` was resolved,
    whether directly or via the `h12_evidence_index.json` side-index), is
    cross-checked against the artifact's own `process` field. Without this
    check, a side-index entry could point one process's key at a
    DIFFERENT process's real, valid H12_CONFIRMED artifact (cross-process
    substitution) and the gate would incorrectly accept it, since every
    other check here only validates that the artifact is internally
    self-consistent -- never that it is evidence for the row actually
    being scored.

    Hard requirements (no soft-trust for any of these -- all 3 referenced
    source files are git-tracked, so a missing file is a hard fail, not an
    attestation-only pass):
      1. ``verdict == "H12_CONFIRMED"`` (never "H12_OBSERVED_REGIME" or a
         FAIL variant -- observed-regime artifacts are honest, non-laundered
         evidence that a process's non-required-branch coverage exists, but
         they must never clear the gate).
      2. ``process`` is a real `REQUIRED_BRANCHES` key AND (if supplied)
         equals `expected_process` exactly -- rejects cross-process
         substitution via a mis-keyed or tampered side-index entry.
      3. ``nontrivial_sample_count > 0`` and ``exact_match_rate == 1.0``
         (no tolerance), both real (non-bool) numeric types.
      4. ``trivial_mismatch_count == 0``, a real (non-bool) int (a
         guard-logic mismatch on a predicted no-op is disqualifying
         regardless of the nontrivial rate).
      5. Count consistency: ``exact_match_count``/``total_sample_count``/
         ``trivial_checked_count`` are all real nonnegative ints, with
         ``exact_match_count == nontrivial_sample_count`` (required for a
         genuine 100% rate) and ``nontrivial_sample_count +
         trivial_checked_count <= total_sample_count``.
      6. Coverage floor: ``n_seeds``/``m_ticks`` equal the catalog's real
         `CATALOG_N_M[process]` -- a degenerate artifact regenerated with
         e.g. ``--n-seeds 1 --m-ticks 1`` must not pass even if 100%
         "matched" on that shrunken domain.
      7. Full required branch coverage: ``REQUIRED_BRANCHES[process]``
         subset of ``branches_confirmed``.
      8. ``predictor_source_path`` is EXACTLY ``EXPECTED_PREDICTOR_SOURCE_PATH``
         (a dangling/substituted path hard-fails).
      9. Fresh-clone-stable hashes: LF-normalized SHA256 for the predictor
         module and vendored Karr source, raw-byte SHA256 for the fixture,
         each re-computed from the CURRENT on-disk file and compared to the
         value recorded in the artifact -- any mismatch, or any referenced
         file missing on disk, is a hard fail (stale/tampered evidence).
      10. ``oracle_manifest_cross_check`` is a nonempty dict whose every
          value is ``"match"``/``"accepted"`` -- any ``"mismatch"``,
          ``"not_in_manifest"``, or an empty/missing cross-check record is
          a hard fail.
      11. ``oracle_seed_file_sha256`` is a nonempty dict with per-seed
          coverage equal to ``n_seeds`` (every seed hashed; no gaps).
      12. ``raw_prediction_hash`` is a well-formed lowercase-hex SHA256
          string.
      13. ``formula_version`` and the ``karr_source_citation``'s
          ``upstream_repo``/``upstream_commit``/``line_ranges`` are pinned
          to this module's own `FORMULA_VERSION`/`KARR_UPSTREAM_REPO`/
          `KARR_UPSTREAM_COMMIT`/`KARR_SOURCE_CITATIONS` registry values --
          any forged/mismatched value is a hard fail, independent of
          whether the vendored file's hash happens to still match.
      14. ``anti_laundering_attestation`` fields must be their literal
          expected (non-negated, non-false) values -- ``no_sut_import``
          and ``no_result_json_access`` must be exactly ``True``, and
          ``states_after_access`` must be exactly ``"compare_phase_only"``.
    """
    process = payload.get("process")
    if process not in REQUIRED_BRANCHES:
        return f"h12 artifact process {process!r} unknown to REQUIRED_BRANCHES registry"

    if expected_process is not None and process != expected_process:
        return (
            f"h12 artifact process {process!r} does not match the process this evidence is being "
            f"consulted for ({expected_process!r}) -- cross-process substitution via a mis-keyed "
            "side-index entry or tampered artifact"
        )

    if payload.get("verdict") != "H12_CONFIRMED":
        return f"h12 artifact verdict != H12_CONFIRMED (got {payload.get('verdict')!r})"

    nontrivial = payload.get("nontrivial_sample_count")
    if not (_is_plain_nonneg_int(nontrivial) and nontrivial > 0):
        return f"h12 artifact nontrivial_sample_count invalid/zero (got {nontrivial!r})"

    match_rate = payload.get("exact_match_rate")
    if not (_is_plain_number(match_rate) and match_rate == 1.0):
        return f"h12 artifact exact_match_rate is not a real number ==1.0 (got {match_rate!r})"

    trivial_mismatch_count = payload.get("trivial_mismatch_count")
    if not (_is_plain_nonneg_int(trivial_mismatch_count) and trivial_mismatch_count == 0):
        return f"h12 artifact trivial_mismatch_count is not a real nonnegative int ==0 (got {trivial_mismatch_count!r})"

    exact_match_count = payload.get("exact_match_count")
    total_sample_count = payload.get("total_sample_count")
    trivial_checked_count = payload.get("trivial_checked_count")
    for field_name, value in (
        ("exact_match_count", exact_match_count),
        ("total_sample_count", total_sample_count),
        ("trivial_checked_count", trivial_checked_count),
    ):
        if not _is_plain_nonneg_int(value):
            return f"h12 artifact {field_name} is not a real nonnegative int (got {value!r})"
    if exact_match_count != nontrivial:
        return (
            f"h12 artifact exact_match_count ({exact_match_count!r}) != nontrivial_sample_count "
            f"({nontrivial!r}) despite claimed exact_match_rate==1.0"
        )
    if nontrivial + trivial_checked_count > total_sample_count:
        return (
            f"h12 artifact nontrivial_sample_count+trivial_checked_count "
            f"({nontrivial!r}+{trivial_checked_count!r}) exceeds total_sample_count ({total_sample_count!r})"
        )

    catalog_n_seeds, catalog_m_ticks = CATALOG_N_M[process]
    n_seeds = payload.get("n_seeds")
    m_ticks = payload.get("m_ticks")
    if not (_is_plain_nonneg_int(n_seeds) and n_seeds == catalog_n_seeds):
        return (
            f"h12 artifact n_seeds ({n_seeds!r}) does not cover the catalog's real N_seeds "
            f"({catalog_n_seeds!r}) for {process!r} -- a shrunken/degenerate sample domain is not "
            "sufficient evidence even at 100% match"
        )
    if not (_is_plain_nonneg_int(m_ticks) and m_ticks == catalog_m_ticks):
        return (
            f"h12 artifact m_ticks ({m_ticks!r}) does not cover the catalog's real M_ticks "
            f"({catalog_m_ticks!r}) for {process!r} -- a shrunken/degenerate sample domain is not "
            "sufficient evidence even at 100% match"
        )

    branches_confirmed = set(payload.get("branches_confirmed") or [])
    missing = sorted(REQUIRED_BRANCHES[process] - branches_confirmed)
    if missing:
        return f"h12 artifact missing required branch coverage: {missing}"

    predictor_source_path = payload.get("predictor_source_path")
    if predictor_source_path != EXPECTED_PREDICTOR_SOURCE_PATH:
        return (
            "h12 artifact predictor_source_path != expected pinned path "
            f"(got {predictor_source_path!r}, expected {EXPECTED_PREDICTOR_SOURCE_PATH!r})"
        )

    recorded_predictor_hash = payload.get("predictor_source_sha256_lf_normalized")
    if not recorded_predictor_hash:
        return "h12 artifact missing predictor_source_sha256_lf_normalized"
    predictor_path_on_disk = repo_root / predictor_source_path
    if not predictor_path_on_disk.is_file():
        return f"h12 artifact predictor_source_path does not exist on disk: {predictor_source_path!r}"
    current_predictor_hash = _sha256_lf_normalized(predictor_path_on_disk)
    if current_predictor_hash != recorded_predictor_hash:
        return (
            "h12 artifact is STALE: predictor_source_sha256_lf_normalized "
            f"recorded={recorded_predictor_hash} current={current_predictor_hash}"
        )

    recorded_fixture_hash = payload.get("fixture_sha256")
    recorded_fixture_path = payload.get("fixture_path")
    if not recorded_fixture_hash or not recorded_fixture_path:
        return "h12 artifact missing fixture_sha256/fixture_path"
    fixture_path_on_disk = repo_root / recorded_fixture_path
    if not fixture_path_on_disk.is_file():
        return f"h12 artifact fixture_path does not exist on disk: {recorded_fixture_path!r}"
    current_fixture_hash = _sha256_file(fixture_path_on_disk)
    if current_fixture_hash != recorded_fixture_hash:
        return f"h12 artifact is STALE: fixture_sha256 recorded={recorded_fixture_hash} current={current_fixture_hash}"

    karr_citation = payload.get("karr_source_citation") or {}
    recorded_karr_hash = karr_citation.get("vendored_sha256_lf_normalized")
    recorded_karr_path = karr_citation.get("vendored_path")
    if not recorded_karr_hash or not recorded_karr_path:
        return "h12 artifact missing karr_source_citation vendored hash/path"
    expected_karr_path = f"data/karr_vendored_source/{KARR_SOURCE_CITATIONS[process]['file']}"
    if recorded_karr_path != expected_karr_path:
        return (
            "h12 artifact karr_source_citation.vendored_path != expected pinned path "
            f"(got {recorded_karr_path!r}, expected {expected_karr_path!r})"
        )
    karr_path_on_disk = repo_root / recorded_karr_path
    if not karr_path_on_disk.is_file():
        return f"h12 artifact vendored Karr source does not exist on disk: {recorded_karr_path!r}"
    current_karr_hash = _sha256_lf_normalized(karr_path_on_disk)
    if current_karr_hash != recorded_karr_hash:
        return f"h12 artifact is STALE: karr_source_citation hash recorded={recorded_karr_hash} current={current_karr_hash}"

    # --- Pin formula_version and Karr citation metadata to THIS module's own
    # predictor-registry expected values -- a forged/edited artifact could
    # otherwise claim an arbitrary formula_version or citation line range
    # while its hashes still happen to match (the hashes only prove the
    # FILES weren't tampered, not that the artifact's CLAIMS about them are
    # honest).
    recorded_formula_version = payload.get("formula_version")
    if recorded_formula_version != FORMULA_VERSION:
        return (
            f"h12 artifact formula_version ({recorded_formula_version!r}) does not match the predictor "
            f"registry's current FORMULA_VERSION ({FORMULA_VERSION!r})"
        )
    expected_citation = KARR_SOURCE_CITATIONS[process]
    if karr_citation.get("upstream_repo") != KARR_UPSTREAM_REPO:
        return (
            f"h12 artifact karr_source_citation.upstream_repo ({karr_citation.get('upstream_repo')!r}) "
            f"!= expected {KARR_UPSTREAM_REPO!r}"
        )
    if karr_citation.get("upstream_commit") != KARR_UPSTREAM_COMMIT:
        return (
            f"h12 artifact karr_source_citation.upstream_commit ({karr_citation.get('upstream_commit')!r}) "
            f"!= expected {KARR_UPSTREAM_COMMIT!r}"
        )
    recorded_line_ranges = karr_citation.get("line_ranges")
    expected_line_ranges = [list(r) for r in expected_citation["line_ranges"]]
    if recorded_line_ranges != expected_line_ranges:
        return (
            f"h12 artifact karr_source_citation.line_ranges ({recorded_line_ranges!r}) != predictor "
            f"registry's pinned citation ({expected_line_ranges!r}) for {process!r}"
        )

    # --- oracle_manifest_cross_check: reject empty/missing, or any entry
    # that is not an accepted status.
    cross_check = payload.get("oracle_manifest_cross_check")
    if not isinstance(cross_check, dict) or not cross_check:
        return "h12 artifact oracle_manifest_cross_check missing/empty (no cross-checked oracle provenance)"
    bad_entries = {seed: status for seed, status in cross_check.items() if status not in ("match", "accepted")}
    if bad_entries:
        return f"h12 artifact oracle_manifest_cross_check has non-accepted entries: {bad_entries}"

    # --- Per-seed raw oracle hash coverage: every seed in [0, n_seeds) must
    # have been hashed -- no gaps, no soft-trust for an unhashed seed.
    seed_hashes = payload.get("oracle_seed_file_sha256")
    if not isinstance(seed_hashes, dict) or not seed_hashes:
        return "h12 artifact oracle_seed_file_sha256 missing/empty (no per-seed raw oracle hash coverage)"
    if len(seed_hashes) != n_seeds:
        return (
            f"h12 artifact oracle_seed_file_sha256 covers {len(seed_hashes)} seed(s), expected {n_seeds!r} "
            "(gap in per-seed raw oracle hash coverage)"
        )

    # --- raw_prediction_hash: cheap structural well-formedness check (a
    # full recomputation would require reloading every seed's oracle trace
    # and rerunning the predictor, which is exercised by the dedicated
    # regeneration-determinism test, not by this gate-time validator).
    raw_prediction_hash = payload.get("raw_prediction_hash")
    if not isinstance(raw_prediction_hash, str) or not _SHA256_HEX_RE.match(raw_prediction_hash):
        return f"h12 artifact raw_prediction_hash is not a well-formed sha256 hex string (got {raw_prediction_hash!r})"

    # --- anti_laundering_attestation: fields must be their literal expected
    # (non-negated, non-false) values -- a negated attestation must fail
    # closed, not be treated as a soft/optional field.
    attestation = payload.get("anti_laundering_attestation") or {}
    if attestation.get("no_sut_import") is not True:
        return f"h12 artifact anti_laundering_attestation.no_sut_import is not True (got {attestation.get('no_sut_import')!r})"
    if attestation.get("no_result_json_access") is not True:
        return (
            "h12 artifact anti_laundering_attestation.no_result_json_access is not True "
            f"(got {attestation.get('no_result_json_access')!r})"
        )
    if attestation.get("states_after_access") != "compare_phase_only":
        return (
            "h12 artifact anti_laundering_attestation.states_after_access != 'compare_phase_only' "
            f"(got {attestation.get('states_after_access')!r})"
        )

    return None


def write_artifact(artifact: dict, out_dir: Path = OUT_ROOT) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{artifact['process']}_h12.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=False)
        fh.write("\n")
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run H12 machine evidence for a process")
    parser.add_argument("process", choices=list(PREDICTORS.keys()) + ["all"])
    parser.add_argument("--n-seeds", type=int, default=None)
    parser.add_argument("--m-ticks", type=int, default=None)
    parser.add_argument(
        "--trace-window-manifest",
        type=Path,
        default=None,
        help="Optional per-seed trace-window manifest (opt-in; default loader behavior stays unchanged when omitted)",
    )
    args = parser.parse_args(argv)

    processes = RISK_ORDER if args.process == "all" else [args.process]
    for process in processes:
        cat_n, cat_m = CATALOG_N_M[process]
        n_seeds = args.n_seeds or cat_n
        m_ticks = args.m_ticks or cat_m
        print(f"[h12] running {process} n_seeds={n_seeds} m_ticks={m_ticks}", file=sys.stderr)
        artifact = run_h12(process, n_seeds, m_ticks, trace_window_manifest_path=args.trace_window_manifest)
        path = write_artifact(artifact)
        print(
            f"[h12] {process}: verdict={artifact['verdict']} "
            f"nontrivial={artifact['nontrivial_sample_count']} "
            f"match_rate={artifact['exact_match_rate']} -> {path}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
