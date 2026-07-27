"""Structural validation helpers for `per_process_traces_v2_s{NNN}` MAT files.

Deliberately lightweight (does not stack/read full per-tick channel data --
that is the loader's job, reused via `_l2_2_design_a_runner_helpers`) so it
is cheap enough to run before/after every one of the ~800 files a full
16-process x 49-seed extraction produces.

This module has no MATLAB dependency and no `opencell` package dependency
beyond `h5py`/`numpy`, but per project convention it must still be invoked
via the WSL wrappers (`bin\\oc-py`, `bin\\oc-pytest`) since that is where
`h5py` is installed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import h5py
import numpy as np


@dataclass
class ValidationResult:
    path: Path
    ok: bool
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    sha256: str | None = None
    size_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "ok": self.ok,
            "errors": list(self.errors),
            "metadata": self.metadata,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_metadata_value(value: np.ndarray, key: str) -> Any:
    if value.dtype.kind == "S":
        return value.tobytes().decode("utf-8", "ignore")
    if value.dtype.kind == "U":
        return "".join(value.tolist())
    if key in ("process_name", "timestamp") and np.issubdtype(value.dtype, np.integer):
        # MATLAB char arrays surface via h5py as uint16 codepoint vectors.
        return "".join(chr(int(code)) for code in value)
    if value.size == 1:
        return value.item()
    return value.tolist()


def read_metadata(handle: h5py.File) -> dict[str, Any]:
    if "metadata" not in handle:
        raise ValueError("Missing metadata group")
    group = handle["metadata"]
    out: dict[str, Any] = {}
    for key in ("process_name", "n_ticks", "rng_seed", "tick_offset", "timestamp"):
        if key in group:
            value = np.asarray(group[key][()]).reshape(-1)
            out[key] = _decode_metadata_value(value, key)
    return out


def _first_channel_tick_count(handle: h5py.File, section: str) -> int | None:
    if section not in handle:
        return None
    group = handle[section]
    for key in sorted(group.keys()):
        if key == "chromosome":
            continue
        dataset = group[key]
        if dataset.ndim == 2 and 1 in dataset.shape:
            return int(dataset.shape[1] if dataset.shape[0] == 1 else dataset.shape[0])
    return None


def validate_structural(
    path: Path,
    *,
    expected_process: str | None = None,
    expected_seed: int | None = None,
    expected_n_ticks: int | None = None,
    compute_hash: bool = True,
) -> ValidationResult:
    """Cheap structural validity check for one extracted trace file.

    Does NOT validate schema drift against another seed (see
    `_l2_2_design_a_runner_helpers._seed_schema_preflight` for that, reused
    directly by `preflight.py`) and does NOT stack full per-tick channel
    data (see the loader for that). This only proves the file is a
    well-formed, complete trace for the (process, seed) it claims to be.
    """
    result = ValidationResult(path=path, ok=False)
    if not path.exists():
        result.errors.append("file does not exist")
        return result

    try:
        result.size_bytes = path.stat().st_size
        if compute_hash:
            result.sha256 = sha256_file(path)
        with h5py.File(path, "r") as handle:
            if "states_before" not in handle:
                result.errors.append("missing states_before group")
            if "states_after" not in handle:
                result.errors.append("missing states_after group")
            try:
                metadata = read_metadata(handle)
                result.metadata = metadata
            except ValueError as exc:
                result.errors.append(str(exc))
                metadata = {}

            if expected_process is not None and metadata.get("process_name") != expected_process:
                result.errors.append(
                    f"metadata.process_name={metadata.get('process_name')!r} "
                    f"!= expected {expected_process!r}"
                )
            if expected_seed is not None and int(metadata.get("rng_seed", -1)) != int(expected_seed):
                result.errors.append(
                    f"metadata.rng_seed={metadata.get('rng_seed')!r} != expected {expected_seed!r}"
                )
            if expected_n_ticks is not None and int(metadata.get("n_ticks", -1)) != int(expected_n_ticks):
                result.errors.append(
                    f"metadata.n_ticks={metadata.get('n_ticks')!r} != expected {expected_n_ticks!r}"
                )

            for section in ("states_before", "states_after"):
                tick_count = _first_channel_tick_count(handle, section)
                if tick_count is None:
                    continue
                if expected_n_ticks is not None and tick_count != expected_n_ticks:
                    result.errors.append(
                        f"{section} tick count {tick_count} != expected {expected_n_ticks}"
                    )
    except OSError as exc:
        result.errors.append(f"unreadable/corrupt HDF5 file: {exc}")
    except Exception as exc:  # noqa: BLE001 - any structural surprise is a validation failure, not a crash
        result.errors.append(f"unexpected validation error: {exc}")

    result.ok = not result.errors
    return result
