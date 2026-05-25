"""Build replay-ready per-process fixtures from MATLAB per-tick trace files.

Usage:
    py -3.12 scripts/build_replay_fixtures.py --all
    py -3.12 scripts/build_replay_fixtures.py --process Cytokinesis
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SOURCE_ROOT = _REPO_ROOT / "data" / "m1_sources" / "karr_native" / "per_process_traces"
_DEFAULT_OUTPUT_ROOT = _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay"
_FALLBACK_SOURCE_ROOT = Path("E:/opencell/data/m1_sources/karr_native/per_process_traces")


def _h5_to_str(raw: np.ndarray) -> str:
    arr = np.asarray(raw).reshape(-1)
    return "".join(chr(int(v)) for v in arr if int(v) != 0)


def _h5_to_scalar(raw: np.ndarray | Any) -> Any:
    arr = np.asarray(raw)
    if arr.size == 1:
        return arr.reshape(-1)[0].item()
    return arr


def _load_v73(path: Path) -> dict[str, Any]:
    import h5py

    def read_cell_series(handle: h5py.File, dataset: h5py.Dataset) -> list[np.ndarray]:
        raw = np.asarray(dataset[()])
        if raw.dtype == object:
            refs = raw.reshape(-1)
            out: list[np.ndarray] = []
            for ref in refs:
                if not ref:
                    continue
                out.append(np.asarray(handle[ref]))
            return out
        if raw.ndim == 1 and raw.size == 2 and raw.dtype.kind in {"u", "i"} and np.all(raw == 0):
            # MATLAB v7.3 empty cell markers can appear as [0, 0].
            return []
        return [raw]

    with h5py.File(path, "r") as handle:
        states_before = {
            name: read_cell_series(handle, ds)
            for name, ds in handle["states_before"].items()
        }
        states_after = {
            name: read_cell_series(handle, ds)
            for name, ds in handle["states_after"].items()
        }
        md = handle["metadata"]
        snap_refs = np.asarray(md["snapshot_properties"][()]).reshape(-1)
        metadata = {
            "n_ticks": int(_h5_to_scalar(md["n_ticks"][()])),
            "process_name": _h5_to_str(md["process_name"][()]),
            "rng_seed": int(_h5_to_scalar(md["rng_seed"][()])),
            "snapshot_properties": [_h5_to_str(handle[ref][()]) for ref in snap_refs],
        }
        return {"states_before": states_before, "states_after": states_after, "metadata": metadata}


def load_trace_mat(path: Path) -> dict[str, Any]:
    try:
        return loadmat(path, simplify_cells=True, squeeze_me=True)
    except NotImplementedError:
        return _load_v73(path)


def _as_tick_list(value: Any) -> list[np.ndarray]:
    if isinstance(value, list):
        return [np.asarray(v) for v in value]
    if isinstance(value, tuple):
        return [np.asarray(v) for v in value]
    arr = np.asarray(value)
    if arr.ndim == 1 and arr.size == 2 and arr.dtype.kind in {"u", "i"} and np.all(arr == 0):
        return []
    if arr.dtype == object:
        return [np.asarray(v) for v in arr.reshape(-1)]
    if arr.ndim >= 1:
        return [np.asarray(v) for v in arr]
    return [arr]


def _stack_tick_series(
    tick_values: list[np.ndarray], *, key: str, process_name: str
) -> np.ndarray | None:
    if not tick_values:
        print(f"[warn] {process_name}: {key} empty, skipping")
        return None
    shapes = {tuple(np.asarray(v).shape) for v in tick_values}
    if len(shapes) != 1:
        shape_list = ", ".join(str(s) for s in sorted(shapes))
        print(f"[warn] {process_name}: {key} variable tick shapes ({shape_list}), skipping")
        return None
    try:
        return np.stack([np.asarray(v) for v in tick_values], axis=0)
    except ValueError as exc:
        print(f"[warn] {process_name}: {key} stack failed ({exc}), skipping")
        return None


def _align_tick_count(
    tick_values: list[np.ndarray],
    *,
    n_ticks: int,
    key: str,
    process_name: str,
) -> list[np.ndarray] | None:
    if len(tick_values) == n_ticks:
        return tick_values
    if len(tick_values) == 1 and n_ticks > 1:
        print(f"[warn] {process_name}: {key} has one tick, broadcasting to {n_ticks}")
        return tick_values * n_ticks
    if len(tick_values) == 0:
        print(f"[warn] {process_name}: {key} has no ticks, skipping")
        return None
    print(f"[warn] {process_name}: {key} tick-count {len(tick_values)} != {n_ticks}, skipping")
    return None


def _coerce_struct(mapping: Any) -> dict[str, Any]:
    if isinstance(mapping, dict):
        return {str(k): v for k, v in mapping.items()}
    return {}


def build_replay_fixture(
    source_mat: Path,
    output_root: Path = _DEFAULT_OUTPUT_ROOT,
) -> tuple[str, int, int, Path]:
    payload = load_trace_mat(source_mat)
    metadata = payload.get("metadata", {})
    before = _coerce_struct(payload.get("states_before", {}))
    after = _coerce_struct(payload.get("states_after", {}))

    process_name = str(
        metadata.get("process_name")
        or source_mat.name.replace("_100ticks.mat", "")
    )
    n_ticks = int(metadata.get("n_ticks", 0) or 0)
    if n_ticks <= 0:
        sample = next(iter(before.values()), None) or next(iter(after.values()), None)
        n_ticks = len(_as_tick_list(sample)) if sample is not None else 1

    arrays: dict[str, np.ndarray] = {}
    before_arrays: dict[str, np.ndarray] = {}
    kept = 0
    for prop, raw_values in sorted(before.items()):
        key = f"state_before__{prop}"
        ticks = _align_tick_count(_as_tick_list(raw_values), n_ticks=n_ticks, key=key, process_name=process_name)
        if ticks is None:
            continue
        stacked = _stack_tick_series(ticks, key=key, process_name=process_name)
        if stacked is None:
            continue
        arrays[key] = stacked
        before_arrays[prop] = stacked
        kept += 1

    for prop, raw_values in sorted(after.items()):
        key = f"states_after__{prop}"
        ticks = _align_tick_count(_as_tick_list(raw_values), n_ticks=n_ticks, key=key, process_name=process_name)
        if ticks is None:
            if prop in before_arrays:
                print(f"[warn] {process_name}: {key} missing, mirroring state_before__{prop}")
                arrays[key] = before_arrays[prop]
                kept += 1
            continue
        stacked = _stack_tick_series(ticks, key=key, process_name=process_name)
        if stacked is None:
            continue
        arrays[key] = stacked
        kept += 1

    output_root.mkdir(parents=True, exist_ok=True)
    npz_path = output_root / f"{process_name}.npz"
    json_path = output_root / f"{process_name}.json"
    np.savez_compressed(npz_path, **arrays)

    snapshot_properties_raw = metadata.get("snapshot_properties", [])
    if isinstance(snapshot_properties_raw, np.ndarray):
        snapshot_properties = [str(v) for v in snapshot_properties_raw.reshape(-1).tolist()]
    elif isinstance(snapshot_properties_raw, (list, tuple)):
        snapshot_properties = [str(v) for v in snapshot_properties_raw]
    elif snapshot_properties_raw:
        snapshot_properties = [str(snapshot_properties_raw)]
    else:
        snapshot_properties = []
    manifest = {
        "manifest": {
            "n_ticks": int(n_ticks),
            "process_name": process_name,
            "rng_seed": int(metadata.get("rng_seed", 0) or 0),
            "snapshot_properties": snapshot_properties,
            "source_mat": f"data/m1_sources/karr_native/per_process_traces/{process_name}_100ticks.mat",
            "schema_version": 1,
        }
    }
    json_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return process_name, kept, n_ticks, npz_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process", action="append", help="Single process name (repeatable)")
    parser.add_argument("--all", action="store_true", help="Convert all *_100ticks.mat files")
    parser.add_argument("--source-root", type=Path, default=None, help="Trace source directory")
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT_ROOT, help="Replay output directory")
    return parser.parse_args()


def _resolve_source_root(candidate: Path | None) -> Path:
    if candidate is not None:
        return candidate
    if _DEFAULT_SOURCE_ROOT.exists():
        return _DEFAULT_SOURCE_ROOT
    return _FALLBACK_SOURCE_ROOT


def main() -> int:
    args = _parse_args()
    source_root = _resolve_source_root(args.source_root)
    if not source_root.exists():
        print(f"[skip] no source root found: {source_root}")
        return 1

    process_names = [name.strip() for name in (args.process or []) if name and name.strip()]
    run_all = args.all or not process_names
    if run_all:
        mats = sorted(source_root.glob("*_100ticks.mat"))
    else:
        mats = [source_root / f"{name}_100ticks.mat" for name in process_names]

    if not mats:
        print(f"[skip] no trace .mat files found in {source_root}")
        return 1

    rc = 0
    for mat_path in mats:
        process_name = mat_path.name.replace("_100ticks.mat", "")
        if not mat_path.exists():
            print(f"[skip] {process_name}: missing source {mat_path}")
            rc = 1
            continue
        try:
            proc, n_props, n_ticks, out_path = build_replay_fixture(mat_path, output_root=args.output_root)
            print(f"[ok] {proc}: {n_props} properties, n_ticks={n_ticks}, output={out_path}")
        except Exception as exc:  # pragma: no cover - surfaced in CLI output
            print(f"[skip] {process_name}: {exc}")
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
