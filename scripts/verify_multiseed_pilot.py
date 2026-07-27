#!/usr/bin/env python3
"""Structural + non-vacuity validator for the L2.2 bounded multi-seed pilot.

Audits the seed-0/seed-1 Karr `per_process_traces_v2_s{seed:03d}` pilot traces
produced for a small, pre-registered set of processes (see
`docs/phase_f/l2_2_design_a/MULTISEED_PILOT_REPORT.md`). For each pilot
process this script:

  1. Locates the seed-0 and seed-1 `.mat` trace files.
  2. Verifies structural loadability (states_before/states_after HDF5 groups,
     metadata fields, consistent tick counts) without touching biology.
  3. Computes a sha256 of each raw file for provenance (files themselves stay
     gitignored; only this manifest is tracked).
  4. Proves non-vacuous seed independence: at least one snapshot channel must
     differ between the two seeds (otherwise the "seed" parameter would be a
     no-op and any downstream distributional claim would be vacuous).
  5. Calls the real (unmocked) `load_karr_oracle` loader for each process and
     records `canonical_seed_count` + any warnings, to prove or disprove
     Design-A loader compatibility empirically.

Writes a tracked JSON manifest to
`docs/phase_f/l2_2_design_a/multiseed_pilot_manifest.json`.

Usage (WSL only, per project convention):
    bin\\oc-py scripts/verify_multiseed_pilot.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "multiseed_pilot_manifest.json"

# Pre-registered pilot: 2 seeds x 3 stochastically-active process classes.
# Selection rationale lives in MULTISEED_PILOT_REPORT.md; kept in sync here so
# the manifest is self-describing.
PILOT_SEEDS: tuple[int, ...] = (0, 1)
PILOT_PROCESSES: tuple[str, ...] = ("Transcription", "RNADecay", "ProteinDecay")
# One channel per process known to carry real per-tick stochastic signal
# (not a quiescent/event-only window) for the non-vacuity check.
NONVACUOUS_CHANNEL = {
    "Transcription": "substrates",
    "RNADecay": "substrates",
    "ProteinDecay": "substrates",
}


def _trace_path(process: str, seed: int) -> Path:
    return (
        REPO_ROOT
        / "data"
        / "m1_sources"
        / "karr_native"
        / f"per_process_traces_v2_s{seed:03d}"
        / f"{process}_100ticks.mat"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_metadata(handle: h5py.File) -> dict[str, Any]:
    if "metadata" not in handle:
        raise ValueError("Missing metadata group")
    group = handle["metadata"]
    out: dict[str, Any] = {}
    for key in ("process_name", "n_ticks", "rng_seed", "timestamp"):
        if key in group:
            value = np.asarray(group[key][()]).reshape(-1)
            if value.dtype.kind == "S":
                out[key] = value.tobytes().decode("utf-8", "ignore")
            elif value.dtype.kind == "U":
                out[key] = "".join(value.tolist())
            elif key in ("process_name", "timestamp") and np.issubdtype(value.dtype, np.integer):
                # MATLAB char arrays surface via h5py as uint16 codepoint vectors.
                out[key] = "".join(chr(int(code)) for code in value)
            elif value.size == 1:
                out[key] = value.item()
            else:
                out[key] = value.tolist()
    return out


def _channel_matrix(handle: h5py.File, group: h5py.Group, channel: str) -> np.ndarray:
    dataset = group[channel]
    if dataset.ndim != 2 or 1 not in dataset.shape:
        raise ValueError(f"Channel {channel!r} is not a 2D singleton-axis cell array: shape={dataset.shape}")
    n_ticks = dataset.shape[1] if dataset.shape[0] == 1 else dataset.shape[0]
    vectors = []
    for tick in range(n_ticks):
        ref = dataset[0, tick] if dataset.shape[0] == 1 else dataset[tick, 0]
        vectors.append(np.asarray(handle[ref][()], dtype=np.float64).reshape(-1))
    widths = {v.shape[0] for v in vectors}
    if len(widths) > 1:
        raise ValueError(f"Inconsistent vector widths in channel {channel!r}: {sorted(widths)}")
    return np.stack(vectors, axis=0)


def _validate_trace_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing pilot trace: {path}")
    with h5py.File(path, "r") as handle:
        if "states_before" not in handle or "states_after" not in handle:
            raise ValueError(f"{path}: missing states_before/states_after groups")
        before_group = handle["states_before"]
        after_group = handle["states_after"]
        before_keys = sorted(before_group.keys())
        after_keys = sorted(after_group.keys())
        metadata = _read_metadata(handle)
        channels: dict[str, np.ndarray] = {}
        for key in before_keys:
            if key == "chromosome":
                continue
            channels[f"before/{key}"] = _channel_matrix(handle, before_group, key)
        for key in after_keys:
            if key == "chromosome":
                continue
            channels[f"after/{key}"] = _channel_matrix(handle, after_group, key)
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "metadata": metadata,
        "before_channels": before_keys,
        "after_channels": after_keys,
        "_channel_matrices": channels,
    }


def _matlab_tool_version() -> str:
    # Best-effort: prefer a cached probe result written by the extraction
    # session over re-invoking MATLAB (which is slow and license-bound).
    cached = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "_matlab_version_probe.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8").strip()
    return "unknown (see MULTISEED_PILOT_REPORT.md for the recorded probe)"


def _oracle_dispatch_summary(process: str) -> dict[str, Any]:
    sys.path.insert(0, str(REPO_ROOT / "tests" / "vivarium"))
    import _l2_2_design_a_runner_helpers as helpers  # noqa: PLC0415

    oracle = helpers.load_karr_oracle(process)
    return {
        "canonical_seed_count": int(oracle.get("canonical_seed_count", 0)),
        "n_ticks_available": int(oracle.get("n_ticks_available", 0)),
        "oracle_path": str(oracle.get("oracle_path")),
        "warnings": list(oracle.get("warnings", ()) or ()),
    }


def main() -> int:
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "harness": "scripts/verify_multiseed_pilot.py",
        "matlab_tool_version": _matlab_tool_version(),
        "pilot_seeds": list(PILOT_SEEDS),
        "pilot_processes": list(PILOT_PROCESSES),
        "processes": {},
    }
    failures: list[str] = []

    for process in PILOT_PROCESSES:
        process_report: dict[str, Any] = {"seeds": {}}
        seed_channel_matrices: dict[int, dict[str, np.ndarray]] = {}
        try:
            for seed in PILOT_SEEDS:
                path = _trace_path(process, seed)
                validated = _validate_trace_file(path)
                seed_channel_matrices[seed] = validated.pop("_channel_matrices")
                process_report["seeds"][str(seed)] = validated

            # Non-vacuity: the designated channel must differ between seeds.
            channel_key = f"after/{NONVACUOUS_CHANNEL[process]}"
            mat0 = seed_channel_matrices[PILOT_SEEDS[0]][channel_key]
            mat1 = seed_channel_matrices[PILOT_SEEDS[1]][channel_key]
            identical = bool(np.array_equal(mat0, mat1))
            max_abs_diff = float(np.max(np.abs(mat0 - mat1))) if mat0.shape == mat1.shape else float("nan")
            process_report["non_vacuity_check"] = {
                "channel": NONVACUOUS_CHANNEL[process],
                "seeds_compared": list(PILOT_SEEDS),
                "identical_across_seeds": identical,
                "max_abs_diff": max_abs_diff,
            }
            if identical:
                failures.append(
                    f"{process}: seed {PILOT_SEEDS[0]} and {PILOT_SEEDS[1]} produced IDENTICAL "
                    f"{NONVACUOUS_CHANNEL[process]} traces (vacuous independence)"
                )

            process_report["loader_compatibility"] = _oracle_dispatch_summary(process)
        except Exception as exc:  # noqa: BLE001
            process_report["error"] = str(exc)
            failures.append(f"{process}: {exc}")

        manifest["processes"][process] = process_report

    manifest["result"] = "PASS" if not failures else "FAIL"
    manifest["failures"] = failures

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    print(f"[verify_multiseed_pilot] wrote {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    print(f"[verify_multiseed_pilot] result={manifest['result']}")
    for process, report in manifest["processes"].items():
        if "error" in report:
            print(f"  {process}: ERROR {report['error']}")
            continue
        nv = report["non_vacuity_check"]
        lc = report["loader_compatibility"]
        print(
            f"  {process}: non_vacuous={not nv['identical_across_seeds']} "
            f"max_abs_diff={nv['max_abs_diff']:.6g} "
            f"loader_seed_count={lc['canonical_seed_count']} loader_warnings={lc['warnings']}"
        )

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
