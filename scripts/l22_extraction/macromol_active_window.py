"""Audit and validation helpers for MacromolecularComplexation active windows.

This module is the tracked, preregistered contract for the L22 Macromol
active-window cohort. It does not run MATLAB itself. Instead it:

* defines the authoritative on-disk layout for the active-window cohort;
* validates that one seed's MAT file really is a 100-tick window starting at
  that seed's first observed network-2 formation tick;
* audits the full N=50 cohort for completeness, duplicate-content aliasing,
  and resumable extraction planning.

Per task contract, the active-window population is isolated from the canonical
early-window traces under a process-local root:

    data/m1_sources/karr_native/macromol_active_window/
        per_process_traces_v2/MacromolecularComplexation_100ticks.mat
        per_process_traces_v2_s001/MacromolecularComplexation_100ticks.mat
        ...
        per_process_traces_v2_s049/MacromolecularComplexation_100ticks.mat

The existing Design-A runner consumes this cohort via the process-scoped
environment override documented in
`docs/phase_f/l2_2_design_a/MACROMOLECULARCOMPLEXATION_ACTIVE_WINDOW_PREREG.md`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction.trace_validation import (  # noqa: E402
    _decode_metadata_value,
    sha256_file,
    validate_structural,
)

PROCESS_NAME = "MacromolecularComplexation"
REQUIRED_M_TICKS = 100
REQUIRED_N_SEEDS = 50
SEARCH_MAX_TICKS = 33000
NETWORK2_COMPLEX_INDICES_0B = (22, 23)
ACTIVE_WINDOW_RULE = "first_network2_formation_tick"
ACTIVE_WINDOW_RULE_VERSION = 2
ACTIVE_WINDOW_ROOT = REPO_ROOT / "data" / "m1_sources" / "karr_native" / "macromol_active_window"
DEFAULT_DATA_ROOTS = (ACTIVE_WINDOW_ROOT,)
MATLAB_DRIVER = REPO_ROOT / "scripts" / "matlab" / "extract_macromol_active_window_seeds.m"
RUNNER_OVERRIDE_ENV_VAR = "OPENCELL_L22_PROCESS_ORACLE_ROOT__MACROMOLECULARCOMPLEXATION"
FIXTURE_PATH = REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "MacromolecularComplexation_flat.mat"
VENDORED_SOURCE_PATH = REPO_ROOT / "data" / "karr_vendored_source" / "MacromolecularComplexation.m"
ACTIVE_WINDOW_CAPTURE_MODE = "same_pass_tapped_scheduler_trigger_and_capture"

_REQUIRED_METADATA_KEYS = (
    "process_name",
    "n_ticks",
    "rng_seed",
    "tick_offset",
    "tick_start",
    "tick_end",
    "stride",
    "active_window_rule",
    "active_window_rule_version",
    "active_window_trigger_tick",
    "active_window_trigger_complex_indices_0b",
    "active_window_search_max_ticks",
    "active_window_search_stop_reason",
    "active_window_detection_mechanism",
    "active_window_capture_mode",
    "mnrnd_provider_kind",
    "mnrnd_provider_matlab_release",
    "mnrnd_provider_toolbox_version",
    "mnrnd_provider_path_relative_to_matlabroot",
    "mnrnd_provider_sha256",
    "statistics_rng_provider_identity_json",
    "active_window_driver_relpath",
    "active_window_driver_sha256_lf_normalized",
    "active_window_fixture_relpath",
    "active_window_fixture_sha256",
    "active_window_vendored_source_relpath",
    "active_window_vendored_source_sha256_lf_normalized",
)
_REQUIRED_CHANNELS = ("substrates", "complexs")
_STRING_METADATA_KEYS = {
    "process_name",
    "timestamp",
    "active_window_rule",
    "active_window_search_stop_reason",
    "active_window_detection_mechanism",
    "active_window_capture_mode",
    "mnrnd_provider_kind",
    "mnrnd_provider_matlab_release",
    "mnrnd_provider_toolbox_version",
    "mnrnd_provider_path_relative_to_matlabroot",
    "mnrnd_provider_sha256",
    "statistics_rng_provider_identity_json",
    "active_window_driver_relpath",
    "active_window_driver_sha256_lf_normalized",
    "active_window_fixture_relpath",
    "active_window_fixture_sha256",
    "active_window_vendored_source_relpath",
    "active_window_vendored_source_sha256_lf_normalized",
}


class MacromolActiveWindowError(ValueError):
    """Raised when one purported active-window seed file fails validation."""


def _sha256_lf_normalized(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


@dataclass(frozen=True)
class SeedWindow:
    process_name: str
    seed: int
    path: Path
    n_ticks: int
    tick_offset: int
    tick_start: int
    tick_end: int
    trigger_tick: int
    trigger_complex_indices_0b: tuple[int, ...]
    first_e1_nonzero_tick: int | None
    search_max_ticks: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_name": self.process_name,
            "seed": self.seed,
            "path": str(self.path),
            "n_ticks": self.n_ticks,
            "tick_offset": self.tick_offset,
            "tick_start": self.tick_start,
            "tick_end": self.tick_end,
            "trigger_tick": self.trigger_tick,
            "trigger_complex_indices_0b": list(self.trigger_complex_indices_0b),
            "first_e1_nonzero_tick": self.first_e1_nonzero_tick,
            "search_max_ticks": self.search_max_ticks,
            "sha256": self.sha256,
        }


@dataclass
class AuditReport:
    process: str
    status: str
    required_n_seeds: int
    required_m_ticks: int
    found_seeds: list[int]
    missing_seeds: list[int]
    invalid_seeds: list[int]
    duplicate_seeds: list[dict[str, Any]]
    rejected_windows: list[dict[str, Any]]
    deficit: int
    resumable_extraction_command: str
    data_roots: list[str]
    cohort_summary: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "process": self.process,
            "status": self.status,
            "required_n_seeds": self.required_n_seeds,
            "required_m_ticks": self.required_m_ticks,
            "found_seeds": list(self.found_seeds),
            "missing_seeds": list(self.missing_seeds),
            "invalid_seeds": list(self.invalid_seeds),
            "duplicate_seeds": list(self.duplicate_seeds),
            "rejected_windows": list(self.rejected_windows),
            "deficit": self.deficit,
            "resumable_extraction_command": self.resumable_extraction_command,
            "data_roots": list(self.data_roots),
            "cohort_summary": self.cohort_summary,
        }


def _seed_trace_path(seed: int, data_root: Path) -> Path:
    subdir = "per_process_traces_v2" if int(seed) == 0 else f"per_process_traces_v2_s{int(seed):03d}"
    return data_root / subdir / f"{PROCESS_NAME}_{REQUIRED_M_TICKS}ticks.mat"


def _relative_to_repo(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def _metadata_dict(handle: h5py.File) -> dict[str, Any]:
    if "metadata" not in handle:
        raise MacromolActiveWindowError("missing metadata group")
    group = handle["metadata"]
    metadata: dict[str, Any] = {}
    for key in group:
        value = np.asarray(group[key][()]).reshape(-1)
        if key in _STRING_METADATA_KEYS and np.issubdtype(value.dtype, np.integer):
            metadata[key] = "".join(chr(int(code)) for code in value.tolist())
            continue
        metadata[key] = _decode_metadata_value(value, str(key))
    return metadata


def _matlab_ref_to_vector(handle: h5py.File, ref: Any) -> np.ndarray:
    arr = np.asarray(handle[ref][()], dtype=np.float64)
    return np.asarray(arr.reshape(-1), dtype=np.float64)


def _cell_tick_vector(handle: h5py.File, section: str, channel: str, tick: int) -> np.ndarray:
    dataset = handle[f"{section}/{channel}"]
    if dataset.ndim != 2 or 1 not in dataset.shape:
        raise MacromolActiveWindowError(
            f"{section}/{channel} must be a MATLAB cell-array dataset with one singleton axis"
        )
    ref = dataset[0, tick] if dataset.shape[0] == 1 else dataset[tick, 0]
    return _matlab_ref_to_vector(handle, ref)


def _normalize_complex_indices(raw: Any) -> tuple[int, ...]:
    arr = np.asarray(raw, dtype=np.int64).reshape(-1)
    if arr.size == 0:
        raise MacromolActiveWindowError("metadata.active_window_trigger_complex_indices_0b is empty")
    return tuple(int(value) for value in arr.tolist())


def _require_metadata_keys(metadata: dict[str, Any]) -> None:
    missing = [key for key in _REQUIRED_METADATA_KEYS if key not in metadata]
    if missing:
        raise MacromolActiveWindowError(f"missing required metadata key(s): {missing}")


def validate_seed_window(seed: int, path: Path) -> SeedWindow:
    """Validate one extracted active-window seed trace.

    Acceptance requires all of the following:
    * structural MAT validity for this process/seed/M_ticks;
    * fixed-window contract integrity (`tick_start == tick_offset + 1`,
      `tick_end - tick_start + 1 == 100`, `stride == 1`);
    * Macromol-specific preregistration metadata;
    * the very first captured tick contains a positive network-2 complex delta,
      proving the window really starts at a real first-formation tick rather
      than being mislabeled.
    """
    structural = validate_structural(
        path,
        expected_process=PROCESS_NAME,
        expected_seed=seed,
        expected_n_ticks=REQUIRED_M_TICKS,
        compute_hash=True,
    )
    if not structural.ok:
        raise MacromolActiveWindowError("; ".join(structural.errors))
    assert structural.sha256 is not None
    expected_driver_relpath = _relative_to_repo(MATLAB_DRIVER)
    expected_fixture_relpath = _relative_to_repo(FIXTURE_PATH)
    expected_vendored_relpath = _relative_to_repo(VENDORED_SOURCE_PATH)
    expected_driver_hash = _sha256_lf_normalized(MATLAB_DRIVER)
    expected_fixture_hash = sha256_file(FIXTURE_PATH)
    expected_vendored_hash = _sha256_lf_normalized(VENDORED_SOURCE_PATH)

    with h5py.File(path, "r") as handle:
        metadata = _metadata_dict(handle)
        _require_metadata_keys(metadata)

        for channel in _REQUIRED_CHANNELS:
            if f"states_before/{channel}" not in handle or f"states_after/{channel}" not in handle:
                raise MacromolActiveWindowError(f"missing required channel {channel!r} in states_before/states_after")

        n_ticks = int(metadata["n_ticks"])
        tick_offset = int(float(metadata["tick_offset"]))
        tick_start = int(metadata["tick_start"])
        tick_end = int(metadata["tick_end"])
        stride = int(metadata["stride"])
        trigger_tick = int(metadata["active_window_trigger_tick"])
        trigger_complex_indices_0b = _normalize_complex_indices(metadata["active_window_trigger_complex_indices_0b"])
        first_e1_nonzero = metadata.get("active_window_first_e1_nonzero_tick")
        first_e1_nonzero_int = None if first_e1_nonzero is None else int(first_e1_nonzero)
        search_max_ticks = int(metadata["active_window_search_max_ticks"])

        if metadata["active_window_rule"] != ACTIVE_WINDOW_RULE:
            raise MacromolActiveWindowError(
                f"metadata.active_window_rule={metadata['active_window_rule']!r} != {ACTIVE_WINDOW_RULE!r}"
            )
        if int(metadata["active_window_rule_version"]) != ACTIVE_WINDOW_RULE_VERSION:
            raise MacromolActiveWindowError(
                "metadata.active_window_rule_version does not match preregistered version "
                f"{ACTIVE_WINDOW_RULE_VERSION}"
            )
        if search_max_ticks != SEARCH_MAX_TICKS:
            raise MacromolActiveWindowError(
                f"metadata.active_window_search_max_ticks={search_max_ticks} != {SEARCH_MAX_TICKS}"
            )
        if metadata["active_window_capture_mode"] != ACTIVE_WINDOW_CAPTURE_MODE:
            raise MacromolActiveWindowError(
                "metadata.active_window_capture_mode does not match the same-pass capture contract "
                f"({metadata['active_window_capture_mode']!r} != {ACTIVE_WINDOW_CAPTURE_MODE!r})"
            )
        if stride != 1:
            raise MacromolActiveWindowError(f"metadata.stride={stride} != 1")
        if tick_start != tick_offset + 1:
            raise MacromolActiveWindowError(
                f"metadata.tick_start={tick_start} does not equal tick_offset + 1 ({tick_offset + 1})"
            )
        if tick_end - tick_start + 1 != REQUIRED_M_TICKS:
            raise MacromolActiveWindowError(
                f"window span {tick_end - tick_start + 1} != required M_ticks={REQUIRED_M_TICKS}"
            )
        if trigger_tick != tick_start:
            raise MacromolActiveWindowError(
                f"metadata.active_window_trigger_tick={trigger_tick} != tick_start={tick_start}"
            )
        if not set(trigger_complex_indices_0b).issubset(NETWORK2_COMPLEX_INDICES_0B):
            raise MacromolActiveWindowError(
                "metadata.active_window_trigger_complex_indices_0b includes non-network2 indices "
                f"{trigger_complex_indices_0b}"
            )
        if metadata["mnrnd_provider_kind"] != "statistics_toolbox":
            raise MacromolActiveWindowError(
                "metadata.mnrnd_provider_kind is not the genuine Statistics Toolbox provider "
                f"({metadata['mnrnd_provider_kind']!r})"
            )
        if metadata["active_window_driver_relpath"] != expected_driver_relpath:
            raise MacromolActiveWindowError(
                "metadata.active_window_driver_relpath drifted from the tracked extractor path "
                f"({metadata['active_window_driver_relpath']!r} != {expected_driver_relpath!r})"
            )
        if metadata["active_window_driver_sha256_lf_normalized"] != expected_driver_hash:
            raise MacromolActiveWindowError("metadata.active_window_driver_sha256_lf_normalized is stale/tampered")
        if metadata["active_window_fixture_relpath"] != expected_fixture_relpath:
            raise MacromolActiveWindowError(
                "metadata.active_window_fixture_relpath drifted from the tracked fixture path "
                f"({metadata['active_window_fixture_relpath']!r} != {expected_fixture_relpath!r})"
            )
        if metadata["active_window_fixture_sha256"] != expected_fixture_hash:
            raise MacromolActiveWindowError("metadata.active_window_fixture_sha256 is stale/tampered")
        if metadata["active_window_vendored_source_relpath"] != expected_vendored_relpath:
            raise MacromolActiveWindowError(
                "metadata.active_window_vendored_source_relpath drifted from the tracked vendored-source path "
                f"({metadata['active_window_vendored_source_relpath']!r} != {expected_vendored_relpath!r})"
            )
        if metadata["active_window_vendored_source_sha256_lf_normalized"] != expected_vendored_hash:
            raise MacromolActiveWindowError(
                "metadata.active_window_vendored_source_sha256_lf_normalized is stale/tampered"
            )
        if first_e1_nonzero_int is not None and first_e1_nonzero_int > trigger_tick:
            raise MacromolActiveWindowError(
                "metadata.active_window_first_e1_nonzero_tick occurs after the trigger tick "
                f"({first_e1_nonzero_int} > {trigger_tick})"
            )

        before_complexs = _cell_tick_vector(handle, "states_before", "complexs", 0)
        after_complexs = _cell_tick_vector(handle, "states_after", "complexs", 0)
        first_delta = np.asarray(after_complexs - before_complexs, dtype=np.float64)
        positive_network2 = tuple(
            int(idx) for idx in NETWORK2_COMPLEX_INDICES_0B if idx < first_delta.size and first_delta[idx] > 0
        )
        if not positive_network2:
            raise MacromolActiveWindowError(
                "first captured tick does not contain a positive network2 complex delta"
            )
        if positive_network2 != trigger_complex_indices_0b:
            raise MacromolActiveWindowError(
                "metadata.active_window_trigger_complex_indices_0b does not match the first tick's "
                f"positive network2 deltas: metadata={trigger_complex_indices_0b} actual={positive_network2}"
            )

    return SeedWindow(
        process_name=PROCESS_NAME,
        seed=int(seed),
        path=path,
        n_ticks=n_ticks,
        tick_offset=tick_offset,
        tick_start=tick_start,
        tick_end=tick_end,
        trigger_tick=trigger_tick,
        trigger_complex_indices_0b=trigger_complex_indices_0b,
        first_e1_nonzero_tick=first_e1_nonzero_int,
        search_max_ticks=search_max_ticks,
        sha256=structural.sha256,
    )


def discover_candidate_paths(data_roots: tuple[Path, ...] = DEFAULT_DATA_ROOTS) -> dict[int, Path]:
    """Return the first-present candidate path for each required seed."""
    found: dict[int, Path] = {}
    for seed in range(REQUIRED_N_SEEDS):
        for root in data_roots:
            candidate = _seed_trace_path(seed, root)
            if candidate.exists():
                found[seed] = candidate
                break
    return found


def resumable_extraction_command(missing_seeds: list[int], invalid_seeds: list[int] | None = None) -> str:
    invalid = sorted(set(int(seed) for seed in (invalid_seeds or [])))
    missing = sorted(set(int(seed) for seed in missing_seeds))
    pending = sorted(set(missing) | set(invalid))
    if not pending:
        return ""

    force_vector = "[" + " ".join(str(seed) for seed in invalid) + "]" if invalid else "[]"
    start = pending[0]
    end = pending[-1]
    return (
        f"{len(missing)} seed(s) with NO output file at all, "
        f"{len(invalid)} seed(s) with present-but-invalid output. "
        f"Set `{RUNNER_OVERRIDE_ENV_VAR}` to `{ACTIVE_WINDOW_ROOT}` after extraction, then run:\n"
        f"matlab -batch \"addpath('scripts/matlab'); extract_macromol_active_window_seeds({start}, {end}, {force_vector});\""
    )


def audit_active_window_evidence(data_roots: tuple[Path, ...] = DEFAULT_DATA_ROOTS) -> AuditReport:
    """Audit the N=50 active-window cohort without mutating any files."""
    candidate_paths = discover_candidate_paths(data_roots)
    found_seeds: list[int] = []
    invalid_present_seeds: set[int] = set()
    duplicate_seeds: list[dict[str, Any]] = []
    rejected_windows: list[dict[str, Any]] = []
    accepted_windows: list[SeedWindow] = []

    hash_to_seed: dict[str, int] = {}
    for seed in sorted(candidate_paths):
        path = candidate_paths[seed]
        file_hash = sha256_file(path)
        if file_hash in hash_to_seed:
            duplicate_of = hash_to_seed[file_hash]
            duplicate_seeds.append(
                {
                    "seed": seed,
                    "duplicate_of_seed": duplicate_of,
                    "path": str(path),
                    "sha256": file_hash,
                }
            )
            invalid_present_seeds.add(seed)
            continue
        hash_to_seed[file_hash] = seed

        try:
            window = validate_seed_window(seed, path)
        except MacromolActiveWindowError as exc:
            rejected_windows.append({"seed": seed, "path": str(path), "reason": str(exc)})
            invalid_present_seeds.add(seed)
            continue

        found_seeds.append(seed)
        accepted_windows.append(window)

    missing_seeds = sorted(
        seed for seed in range(REQUIRED_N_SEEDS) if seed not in found_seeds and seed not in invalid_present_seeds
    )
    invalid_seeds = sorted(invalid_present_seeds)
    deficit = REQUIRED_N_SEEDS - len(found_seeds)
    status = "SUFFICIENT_ENSEMBLE" if deficit == 0 and not invalid_seeds and not duplicate_seeds else "INSUFFICIENT_ENSEMBLE"

    cohort_summary: dict[str, Any] | None = None
    if accepted_windows:
        trigger_counts = {
            str(idx): sum(1 for window in accepted_windows if idx in window.trigger_complex_indices_0b)
            for idx in NETWORK2_COMPLEX_INDICES_0B
        }
        cohort_summary = {
            "n_valid_seeds": len(accepted_windows),
            "tick_start_min": min(window.tick_start for window in accepted_windows),
            "tick_start_max": max(window.tick_start for window in accepted_windows),
            "first_e1_nonzero_tick_min": min(
                window.first_e1_nonzero_tick
                for window in accepted_windows
                if window.first_e1_nonzero_tick is not None
            )
            if any(window.first_e1_nonzero_tick is not None for window in accepted_windows)
            else None,
            "first_e1_nonzero_tick_max": max(
                window.first_e1_nonzero_tick
                for window in accepted_windows
                if window.first_e1_nonzero_tick is not None
            )
            if any(window.first_e1_nonzero_tick is not None for window in accepted_windows)
            else None,
            "trigger_complex_counts_0b": trigger_counts,
        }

    return AuditReport(
        process=PROCESS_NAME,
        status=status,
        required_n_seeds=REQUIRED_N_SEEDS,
        required_m_ticks=REQUIRED_M_TICKS,
        found_seeds=found_seeds,
        missing_seeds=missing_seeds,
        invalid_seeds=invalid_seeds,
        duplicate_seeds=duplicate_seeds,
        rejected_windows=rejected_windows,
        deficit=deficit,
        resumable_extraction_command=resumable_extraction_command(missing_seeds, invalid_seeds),
        data_roots=[str(root) for root in data_roots],
        cohort_summary=cohort_summary,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        action="append",
        default=None,
        help="Root containing the process-local per_process_traces_v2*/ layout. Repeatable.",
    )
    parser.add_argument("--out", default=None, help="Optional JSON output path for the audit report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    data_roots = tuple(Path(raw) for raw in args.data_root) if args.data_root else DEFAULT_DATA_ROOTS
    report = audit_active_window_evidence(data_roots=data_roots)
    payload = report.to_dict()

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report.status == "SUFFICIENT_ENSEMBLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
