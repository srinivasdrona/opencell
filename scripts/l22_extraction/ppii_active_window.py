"""Portable full50 manifest builder and validators for PPII active windows.

This module owns the tracked contract for the genuine-provider PPII
active-window cohort:

* the 28 already-accepted birth-window rows must resolve to repo-local copies
  of the canonical oracle-population traces and keep their oracle hash
  binding;
* the 22 later-window rows must resolve to repo-local process-local MAT files
  produced by the tracked MATLAB driver under the genuine Statistics Toolbox
  RNG providers; and
* the full50 manifest must be written with repo-relative paths only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import launcher as event_launcher  # noqa: E402
from scripts.l22_extraction.trace_validation import sha256_file, validate_structural  # noqa: E402

PROCESS_NAME = "ProteinProcessingII"
WINDOW_TICKS = 20
REQUIRED_N_SEEDS = 50
ACTIVE_WINDOW_RULE = "first_regime_valid_transferase_tick"
ACTIVE_WINDOW_RULE_VERSION = 1
ACTIVE_WINDOW_ROOT = REPO_ROOT / "data" / "m1_sources" / "karr_native" / "ppii_active_window"
MATLAB_DRIVER = REPO_ROOT / "scripts" / "matlab" / "extract_ppii_active_window_seeds.m"
KARR_SOURCE_PATH = REPO_ROOT / "data" / "karr_vendored_source" / "ProteinProcessingII.m"
FIXTURE_PATH = REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "ProteinProcessingII_flat.mat"
COVERED28_MANIFEST_PATH = (
    REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "ProteinProcessingII_active_window_manifest.covered28.json"
)
FULL50_MANIFEST_PATH = (
    REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "ProteinProcessingII_active_window_manifest.full50.json"
)
TRACE_ORIGIN_ORACLE_POPULATION = "oracle_population_birth_trace"
TRACE_ORIGIN_TRACKED_ACTIVE_WINDOW = "tracked_genuine_statistics_active_window"
PROVENANCE_VERSION = 1
SEARCH_STOP_REASON_SUCCESS = "first_regime_valid_transferase_tick"
SEARCH_STOP_REASON_PINCHED = "natural_cycle_pinched_before_transferase_tick"


@dataclass(frozen=True)
class PPIIActiveWindowSeed:
    seed: int
    path: Path
    sha256: str
    tick_start: int
    tick_end: int
    tick_offset: int
    trigger_tick: int
    search_max_ticks: int
    detection_mechanism: str
    search_stop_reason: str
    provider: dict[str, Any]
    rng_identity_json: str


def seed_subdir_token(seed: int) -> str:
    if int(seed) == 0:
        return "per_process_traces_v2"
    return f"per_process_traces_v2_s{int(seed):03d}"


def canonical_birth_trace_path(seed: int) -> Path:
    return REPO_ROOT / "data" / "m1_sources" / "karr_native" / seed_subdir_token(seed) / f"{PROCESS_NAME}_100ticks.mat"


def active_window_mat_path(seed: int, *, root: Path = ACTIVE_WINDOW_ROOT) -> Path:
    return root / seed_subdir_token(seed) / f"{PROCESS_NAME}_{WINDOW_TICKS}ticks.mat"


def path_relative_to(base_dir: Path, path: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base_dir.resolve())).as_posix()


def repo_relative_or_absolute(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _decode_char_metadata(value: Any) -> str:
    arr = np.asarray(value).reshape(-1)
    if arr.dtype.kind in {"S", "U"}:
        return "".join(str(x) for x in arr.tolist())
    return "".join(chr(int(code)) for code in arr.tolist())


def _read_optional_scalar(metadata: h5py.Group, key: str) -> int | None:
    if key not in metadata:
        return None
    value = np.asarray(metadata[key][()]).reshape(-1)
    if value.size != 1:
        raise ValueError(f"metadata.{key} is not scalar")
    return int(value.item())


def _read_required_text(metadata: h5py.Group, key: str) -> str:
    if key not in metadata:
        raise ValueError(f"metadata.{key} is missing")
    return _decode_char_metadata(metadata[key][()])


def _read_required_scalar(metadata: h5py.Group, key: str) -> int:
    value = _read_optional_scalar(metadata, key)
    if value is None:
        raise ValueError(f"metadata.{key} is missing")
    return int(value)


def _read_provider_metadata(path: Path) -> tuple[dict[str, Any], str]:
    with h5py.File(path, "r") as handle:
        metadata = handle.get("metadata")
        if metadata is None:
            raise ValueError("missing metadata group")
        provider = {
            "kind": _read_required_text(metadata, "mnrnd_provider_kind"),
            "matlab_release": _read_required_text(metadata, "mnrnd_provider_matlab_release"),
            "toolbox_version": _read_required_text(metadata, "mnrnd_provider_toolbox_version"),
            "provider_path_relative_to_matlabroot": _read_required_text(
                metadata, "mnrnd_provider_path_relative_to_matlabroot"
            ),
            "sha256_lf_normalized": _read_required_text(metadata, "mnrnd_provider_sha256"),
        }
        rng_identity_json = _read_required_text(metadata, "statistics_rng_provider_identity_json")
    return provider, rng_identity_json


def validate_genuine_provider_binding(path: Path) -> tuple[dict[str, Any], str]:
    provider, rng_identity_json = _read_provider_metadata(path)
    expected_mnrnd = event_launcher.current_genuine_mnrnd_provider()
    expected_rng = event_launcher.current_genuine_statistics_rng_provider()
    if provider != expected_mnrnd:
        raise ValueError(f"provider metadata does not match the current local genuine mnrnd provider: {provider!r}")
    try:
        trace_rng_identity = json.loads(rng_identity_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"statistics_rng_provider_identity_json is invalid JSON ({exc})") from exc
    if trace_rng_identity != expected_rng:
        raise ValueError("statistics_rng_provider_identity_json does not match the current local RNG providers")
    return provider, rng_identity_json


def validate_later_active_window_seed(seed: int, path: Path) -> PPIIActiveWindowSeed:
    structural = validate_structural(
        path,
        expected_process=PROCESS_NAME,
        expected_seed=seed,
        expected_n_ticks=WINDOW_TICKS,
        compute_hash=True,
    )
    if not structural.ok:
        raise ValueError(f"{path}: {'; '.join(structural.errors)}")
    assert structural.sha256 is not None

    provider, rng_identity_json = validate_genuine_provider_binding(path)

    with h5py.File(path, "r") as handle:
        metadata = handle["metadata"]
        tick_start = _read_required_scalar(metadata, "tick_start")
        tick_end = _read_required_scalar(metadata, "tick_end")
        tick_offset = _read_required_scalar(metadata, "tick_offset")
        stride = _read_required_scalar(metadata, "stride")
        trigger_tick = _read_required_scalar(metadata, "active_window_trigger_tick")
        rule = _read_required_text(metadata, "active_window_rule")
        rule_version = _read_required_scalar(metadata, "active_window_rule_version")
        search_max_ticks = _read_required_scalar(metadata, "active_window_search_max_ticks")
        search_stop_reason = _read_required_text(metadata, "active_window_search_stop_reason")
        detection_mechanism = _read_required_text(metadata, "active_window_detection_mechanism")

    if stride != 1:
        raise ValueError(f"{path}: metadata.stride={stride} != 1")
    if tick_start != tick_offset + 1:
        raise ValueError(f"{path}: metadata.tick_start={tick_start} != tick_offset + 1 ({tick_offset + 1})")
    if tick_end - tick_start + 1 != WINDOW_TICKS:
        raise ValueError(f"{path}: window span {tick_end - tick_start + 1} != {WINDOW_TICKS}")
    if rule != ACTIVE_WINDOW_RULE:
        raise ValueError(f"{path}: metadata.active_window_rule={rule!r} != {ACTIVE_WINDOW_RULE!r}")
    if rule_version != ACTIVE_WINDOW_RULE_VERSION:
        raise ValueError(
            f"{path}: metadata.active_window_rule_version={rule_version} != {ACTIVE_WINDOW_RULE_VERSION}"
        )
    if trigger_tick != tick_start:
        raise ValueError(f"{path}: metadata.active_window_trigger_tick={trigger_tick} != tick_start={tick_start}")
    if search_stop_reason != SEARCH_STOP_REASON_SUCCESS:
        raise ValueError(
            f"{path}: metadata.active_window_search_stop_reason={search_stop_reason!r} != {SEARCH_STOP_REASON_SUCCESS!r}"
        )

    return PPIIActiveWindowSeed(
        seed=int(seed),
        path=path,
        sha256=structural.sha256,
        tick_start=tick_start,
        tick_end=tick_end,
        tick_offset=tick_offset,
        trigger_tick=trigger_tick,
        search_max_ticks=search_max_ticks,
        detection_mechanism=detection_mechanism,
        search_stop_reason=search_stop_reason,
        provider=provider,
        rng_identity_json=rng_identity_json,
    )


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _driver_hash() -> str:
    raw = MATLAB_DRIVER.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def _fixture_hash() -> str:
    return sha256_file(FIXTURE_PATH)


def _karr_source_hash() -> str:
    raw = KARR_SOURCE_PATH.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def _build_later_entry(seed: int, *, manifest_dir: Path) -> dict[str, Any]:
    info = validate_later_active_window_seed(seed, active_window_mat_path(seed))
    return {
        "seed": seed,
        "process": PROCESS_NAME,
        "trace_path": path_relative_to(manifest_dir, info.path),
        "trace_sha256": info.sha256,
        "trace_schema": "ppii_active_window_fixed_20ticks_genuine_statistics_provider",
        "trace_tick_start": info.tick_start,
        "trace_tick_end": info.tick_end,
        "window_tick_start": info.tick_start,
        "window_tick_end": info.tick_end,
        "window_length_ticks": WINDOW_TICKS,
        "first_regime_valid_transferase_tick": info.trigger_tick,
        "window_selection": "whole_trace_starts_at_first_regime_valid_transferase_tick",
        "trace_origin_kind": TRACE_ORIGIN_TRACKED_ACTIVE_WINDOW,
        "tracked_extraction_provenance": {
            "kind": TRACE_ORIGIN_TRACKED_ACTIVE_WINDOW,
            "version": PROVENANCE_VERSION,
            "driver_path": MATLAB_DRIVER.relative_to(REPO_ROOT).as_posix(),
            "driver_sha256_lf_normalized": _driver_hash(),
            "fixture_path": FIXTURE_PATH.relative_to(REPO_ROOT).as_posix(),
            "fixture_sha256": _fixture_hash(),
            "karr_source_path": KARR_SOURCE_PATH.relative_to(REPO_ROOT).as_posix(),
            "karr_source_sha256_lf_normalized": _karr_source_hash(),
            "mat_path": repo_relative_or_absolute(info.path),
            "mat_sha256": info.sha256,
            "seed": seed,
            "trace_tick_start": info.tick_start,
            "trace_tick_end": info.tick_end,
            "window_tick_start": info.tick_start,
            "window_tick_end": info.tick_end,
            "window_length_ticks": WINDOW_TICKS,
            "first_regime_valid_transferase_tick": info.trigger_tick,
            "active_window_rule": ACTIVE_WINDOW_RULE,
            "active_window_rule_version": ACTIVE_WINDOW_RULE_VERSION,
            "active_window_search_max_ticks": info.search_max_ticks,
            "active_window_search_stop_reason": info.search_stop_reason,
            "active_window_detection_mechanism": info.detection_mechanism,
            "mnrnd_provider_kind": info.provider["kind"],
            "mnrnd_provider_matlab_release": info.provider["matlab_release"],
            "mnrnd_provider_toolbox_version": info.provider["toolbox_version"],
            "mnrnd_provider_path_relative_to_matlabroot": info.provider["provider_path_relative_to_matlabroot"],
            "mnrnd_provider_sha256": info.provider["sha256_lf_normalized"],
            "statistics_rng_provider_identity_json": info.rng_identity_json,
        },
    }


def build_portable_full50_manifest(
    *,
    covered_manifest_path: Path = COVERED28_MANIFEST_PATH,
    out_path: Path = FULL50_MANIFEST_PATH,
) -> dict[str, Any]:
    covered = _load_json(covered_manifest_path)
    if covered.get("process") != PROCESS_NAME:
        raise ValueError(f"covered manifest process mismatch: {covered.get('process')!r}")

    manifest_dir = out_path.parent
    covered_entries: dict[str, Any] = covered.get("entries") or {}
    early_entries: dict[int, dict[str, Any]] = {}
    for seed_key, entry in covered_entries.items():
        seed = int(seed_key)
        local_trace = canonical_birth_trace_path(seed)
        if not local_trace.is_file():
            raise FileNotFoundError(f"local canonical birth trace missing for seed {seed}: {local_trace}")
        structural = validate_structural(
            local_trace,
            expected_process=PROCESS_NAME,
            expected_seed=seed,
            expected_n_ticks=int(entry["trace_tick_end"]) - int(entry["trace_tick_start"]) + 1,
            compute_hash=True,
        )
        if not structural.ok:
            raise ValueError(f"local canonical birth trace invalid for seed {seed}: {'; '.join(structural.errors)}")
        assert structural.sha256 is not None
        if structural.sha256 != entry["trace_sha256"]:
            raise ValueError(
                f"local canonical birth trace sha mismatch for seed {seed}: "
                f"covered28={entry['trace_sha256']} local={structural.sha256}"
            )
        rebased = dict(entry)
        rebased["trace_path"] = path_relative_to(manifest_dir, local_trace)
        rebased["trace_origin_kind"] = TRACE_ORIGIN_ORACLE_POPULATION
        rebased["oracle_population_relative_path"] = f"{seed_subdir_token(seed)}/{PROCESS_NAME}_100ticks.mat"
        early_entries[seed] = rebased

    later_entries: dict[int, dict[str, Any]] = {}
    for seed in range(REQUIRED_N_SEEDS):
        if seed in early_entries:
            continue
        later_entries[seed] = _build_later_entry(seed, manifest_dir=manifest_dir)

    entries = {str(seed): entry for seed, entry in sorted({**early_entries, **later_entries}.items())}
    if len(entries) != REQUIRED_N_SEEDS:
        raise ValueError(f"full50 manifest would contain {len(entries)} entries, expected {REQUIRED_N_SEEDS}")

    payload = {
        "schema_version": covered["schema_version"],
        "process": PROCESS_NAME,
        "window_length_ticks": WINDOW_TICKS,
        "coverage_status": "full_50_of_50_repo_local_birth_plus_genuine_active_window_traces",
        "source_population_root": "repo_local",
        "covered_seed_count": REQUIRED_N_SEEDS,
        "covered_seeds": list(range(REQUIRED_N_SEEDS)),
        "uncovered_seed_count": 0,
        "uncovered_seeds": [],
        "entries": entries,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the portable PPII full50 active-window manifest")
    parser.add_argument("--covered-manifest", type=Path, default=COVERED28_MANIFEST_PATH)
    parser.add_argument("--out", type=Path, default=FULL50_MANIFEST_PATH)
    args = parser.parse_args(argv)

    payload = build_portable_full50_manifest(covered_manifest_path=args.covered_manifest, out_path=args.out)
    print(
        f"[ppii-active-window] wrote {len(payload['entries'])} manifest rows to {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
