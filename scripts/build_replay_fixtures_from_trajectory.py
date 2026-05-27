"""Build per-process replay fixtures from the cell-cycle trajectory snapshot file.

Warning: for Replication and ReplicationInitiation, chromosome-internal state is not captured in trajectory deltas; use <Process>_from_flat.npz as the primary oracle.

Usage:
    py -3.12 scripts/build_replay_fixtures_from_trajectory.py --all-truncated
    py -3.12 scripts/build_replay_fixtures_from_trajectory.py --process Transcription
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat

_REPO_ROOT = Path(__file__).resolve().parents[1]

_DEFAULT_TRAJECTORY_PATH = _REPO_ROOT / "data" / "m1_sources" / "karr_native" / "cell_cycle_trajectory.mat"
_DEFAULT_FLAT_ROOT = _REPO_ROOT / "data" / "karr_fixtures" / "per_process"
_DEFAULT_OUTPUT_ROOT = _REPO_ROOT / "data" / "karr_fixtures" / "per_process_replay"

_FALLBACK_KARR_NATIVE_ROOT = Path("E:/opencell/data/m1_sources/karr_native")
_FALLBACK_TRAJECTORY_PATH = _FALLBACK_KARR_NATIVE_ROOT / "cell_cycle_trajectory.mat"

TRUNCATED_PROCESSES = (
    "Transcription",
    "Translation",
    "RNADecay",
    "Replication",
    "ReplicationInitiation",
)

_TRAJECTORY_DATASET_BY_STATE = {
    "Metabolite": "Metabolite_counts",
    "RNA": "Rna_counts",
    "Monomer": "ProteinMonomer_counts",
    "Complex": "ProteinComplex_counts",
}

_PROPERTY_TO_STATES = {
    "substrates": ("Metabolite", "RNA", "Monomer", "Complex"),
    "enzymes": ("Metabolite", "RNA", "Monomer", "Complex"),
    "boundEnzymes": ("RNA", "Monomer", "Complex"),
}


@dataclass(frozen=True)
class TrajectoryData:
    """Loaded trajectory channels needed for replay fixture extraction."""

    source_path: Path
    tick: np.ndarray
    time_s: np.ndarray
    state_series: dict[str, np.ndarray]


@dataclass(frozen=True)
class BuildResult:
    """Per-process extraction result for CLI/status reporting."""

    process_name: str
    n_snapshots: int
    n_pairs: int
    output_path: Path
    properties: tuple[str, ...]
    anomalies: tuple[str, ...]
    effective_dt_sec: tuple[float, ...]


def _resolve_trajectory_path(path: Path | None) -> Path:
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"Trajectory path not found: {path}")
        return path
    if _DEFAULT_TRAJECTORY_PATH.exists():
        return _DEFAULT_TRAJECTORY_PATH
    if _FALLBACK_TRAJECTORY_PATH.exists():
        return _FALLBACK_TRAJECTORY_PATH
    raise FileNotFoundError(
        f"Trajectory file not found in either '{_DEFAULT_TRAJECTORY_PATH}' or '{_FALLBACK_TRAJECTORY_PATH}'."
    )


def _read_cell_matrix_series(handle: h5py.File, dataset: h5py.Dataset) -> np.ndarray:
    n_snapshots = int(dataset.shape[0])
    first = np.asarray(handle[dataset[0, 0]], dtype=np.float64)
    series = np.empty((n_snapshots, *first.shape), dtype=np.float64)
    series[0] = first
    for i in range(1, n_snapshots):
        series[i] = np.asarray(handle[dataset[i, 0]], dtype=np.float64)
    return series


def _read_scalar_cell_series(handle: h5py.File, dataset: h5py.Dataset) -> np.ndarray:
    n_snapshots = int(dataset.shape[0])
    out = np.empty(n_snapshots, dtype=np.float64)
    for i in range(n_snapshots):
        raw = np.asarray(handle[dataset[i, 0]], dtype=np.float64).reshape(-1)
        out[i] = float(raw[0]) if raw.size else np.nan
    return out


def load_trajectory(path: Path) -> TrajectoryData:
    with h5py.File(path, "r") as handle:
        snapshots = handle["snapshots"]
        tick = np.asarray(snapshots["tick"][()], dtype=np.float64).reshape(-1)
        time_s = _read_scalar_cell_series(handle, snapshots["Time_values"])

        state_series: dict[str, np.ndarray] = {}
        for state_name, dataset_name in _TRAJECTORY_DATASET_BY_STATE.items():
            if dataset_name not in snapshots:
                continue
            dataset = snapshots[dataset_name]
            if dataset.dtype != object:
                arr = np.asarray(dataset[()], dtype=np.float64)
                state_series[state_name] = arr.reshape((arr.shape[0], 1, arr.shape[-1]))
                continue
            state_series[state_name] = _read_cell_matrix_series(handle, dataset)

    return TrajectoryData(source_path=path, tick=tick, time_s=time_s, state_series=state_series)


def _load_flat_fixture(path: Path) -> Any:
    mat = loadmat(path, squeeze_me=False, struct_as_record=False)
    if "data" not in mat:
        raise KeyError(f"Expected top-level 'data' in fixture file: {path}")
    root = mat["data"]
    if not isinstance(root, np.ndarray) or root.size == 0:
        raise ValueError(f"Invalid 'data' payload in fixture file: {path}")
    data_struct = root[0, 0]
    fixture = getattr(data_struct, "fixture", None)
    if not isinstance(fixture, np.ndarray) or fixture.size == 0:
        raise ValueError(f"Missing fixture struct in: {path}")
    return fixture[0, 0]


def _as_int_vector(raw: Any) -> np.ndarray:
    arr = np.asarray(raw).reshape(-1)
    if arr.size == 0:
        return np.zeros(0, dtype=np.int64)
    if not np.issubdtype(arr.dtype, np.number):
        return np.zeros(0, dtype=np.int64)
    return np.rint(arr.astype(np.float64)).astype(np.int64)


def _as_float_vector(raw: Any) -> np.ndarray:
    arr = np.asarray(raw).reshape(-1)
    if arr.size == 0:
        return np.zeros(0, dtype=np.float64)
    return arr.astype(np.float64)


def _infer_properties(fixture: Any) -> tuple[str, ...]:
    props: list[str] = []
    for prop in ("substrates", "enzymes", "boundEnzymes", "monomers"):
        if not hasattr(fixture, prop):
            continue
        if _as_float_vector(getattr(fixture, prop)).size == 0:
            continue
        props.append(prop)
    return tuple(props)


def _extract_indexed_values(series: np.ndarray, global_compartment_indexes: np.ndarray) -> np.ndarray:
    """Extract values by MATLAB-style 1-based global-compartment indexes.

    We support two layouts:
    1) direct first-compartment indexing where index <= n_cols (common here);
    2) linear indexing into MATLAB column-major original matrix.
    """

    idx = np.asarray(global_compartment_indexes, dtype=np.int64).reshape(-1)
    if idx.size == 0:
        return np.zeros((series.shape[0], 0), dtype=np.float64)
    if np.any(idx <= 0):
        raise ValueError("Global-compartment indexes must be 1-based positive integers.")

    idx0 = idx - 1
    n_snapshots, n_rows, n_cols = series.shape
    if idx0.max(initial=-1) < n_cols:
        return series[:, 0, idx0]

    n_linear = n_rows * n_cols
    if idx0.max(initial=-1) >= n_linear:
        raise IndexError(
            f"Global-compartment index {int(idx.max())} exceeds available linear size {n_linear}."
        )

    row_original = idx0 % n_cols
    col_original = idx0 // n_cols
    if col_original.max(initial=-1) >= n_rows:
        raise IndexError("Computed compartment axis exceeds available trajectory matrix rows.")
    return series[:, col_original, row_original]


def _mapping_fields_for_property(prop: str, state: str) -> tuple[str, str]:
    if prop == "boundEnzymes":
        local_field = f"enzyme{state}LocalIndexs"
        global_field = f"enzymeBound{state}GlobalCompartmentIndexs"
        return local_field, global_field

    prefix = "substrate" if prop == "substrates" else "enzyme"
    local_field = f"{prefix}{state}LocalIndexs"
    global_field = f"{prefix}{state}GlobalCompartmentIndexs"
    return local_field, global_field


def _build_property_series(
    fixture: Any,
    prop: str,
    trajectory: TrajectoryData,
) -> tuple[np.ndarray, tuple[str, ...]]:
    n_snapshots = int(trajectory.tick.size)
    baseline = _as_float_vector(getattr(fixture, prop))
    if baseline.size == 0:
        raise ValueError(f"Process fixture field '{prop}' is empty.")

    series = np.repeat(baseline.reshape(1, -1), n_snapshots, axis=0)
    anomalies: list[str] = []

    if prop not in _PROPERTY_TO_STATES:
        anomalies.append(
            f"{prop}: no trajectory mapping rule; using static baseline from flat fixture."
        )
        return series, tuple(anomalies)

    for state in _PROPERTY_TO_STATES[prop]:
        local_field, global_field = _mapping_fields_for_property(prop, state)
        if not hasattr(fixture, local_field) or not hasattr(fixture, global_field):
            continue

        local_idx = _as_int_vector(getattr(fixture, local_field))
        global_idx = _as_int_vector(getattr(fixture, global_field))
        if local_idx.size == 0 or global_idx.size == 0:
            continue

        n = min(local_idx.size, global_idx.size)
        if local_idx.size != global_idx.size:
            anomalies.append(
                f"{prop}/{state}: local-index len {local_idx.size} != global-index len {global_idx.size}; truncating to {n}."
            )
        local_idx = local_idx[:n]
        global_idx = global_idx[:n]
        valid = (local_idx > 0) & (global_idx > 0) & (local_idx <= baseline.size)
        local_idx = local_idx[valid]
        global_idx = global_idx[valid]
        if local_idx.size == 0:
            continue

        state_series = trajectory.state_series.get(state)
        if state_series is None:
            anomalies.append(
                f"{prop}/{state}: trajectory dataset missing ({_TRAJECTORY_DATASET_BY_STATE[state]}), using flat baseline."
            )
            continue

        extracted = _extract_indexed_values(state_series, global_idx)
        series[:, local_idx - 1] = extracted

    return series, tuple(anomalies)


def _build_metadata(
    process_name: str,
    n_snapshots: int,
    effective_dt_sec: np.ndarray,
) -> dict[str, Any]:
    return {
        "source": "trajectory",
        "n_snapshots": int(n_snapshots),
        "effective_dt_sec": [float(v) for v in effective_dt_sec.tolist()],
        "process_name": process_name,
        "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_process_fixture_from_trajectory(
    *,
    process_name: str,
    trajectory: TrajectoryData,
    flat_root: Path,
    output_root: Path,
) -> BuildResult:
    flat_path = flat_root / f"{process_name}_flat.mat"
    if not flat_path.exists():
        raise FileNotFoundError(f"Flat fixture not found: {flat_path}")
    fixture = _load_flat_fixture(flat_path)

    properties = _infer_properties(fixture)
    if not properties:
        raise ValueError(f"No replay properties found in flat fixture: {flat_path}")

    n_snapshots = int(trajectory.tick.size)
    if n_snapshots < 2:
        raise ValueError("Need at least 2 snapshots to build (state_t, state_t+1) pairs.")
    n_pairs = n_snapshots - 1
    effective_dt = np.diff(trajectory.time_s).astype(np.float64)

    arrays: dict[str, np.ndarray] = {}
    anomalies: list[str] = []
    for prop in properties:
        prop_series, prop_anomalies = _build_property_series(fixture, prop, trajectory)
        before = prop_series[:-1, np.newaxis, :]
        after = prop_series[1:, np.newaxis, :]
        arrays[f"state_before__{prop}"] = before.astype(np.float64, copy=False)
        arrays[f"states_after__{prop}"] = after.astype(np.float64, copy=False)
        anomalies.extend(prop_anomalies)

    metadata = _build_metadata(process_name, n_snapshots, effective_dt)
    arrays["metadata"] = np.array([metadata], dtype=object)

    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / f"{process_name}_from_trajectory.npz"
    np.savez_compressed(output_path, **arrays)

    return BuildResult(
        process_name=process_name,
        n_snapshots=n_snapshots,
        n_pairs=n_pairs,
        output_path=output_path,
        properties=properties,
        anomalies=tuple(anomalies),
        effective_dt_sec=tuple(float(v) for v in effective_dt.tolist()),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--process",
        action="append",
        help=f"Process name to extract (repeatable). Allowed: {', '.join(TRUNCATED_PROCESSES)}.",
    )
    parser.add_argument(
        "--all-truncated",
        action="store_true",
        help="Build fixtures for all known truncated processes.",
    )
    parser.add_argument(
        "--trajectory-path",
        type=Path,
        default=None,
        help="Optional explicit path to cell_cycle_trajectory.mat.",
    )
    parser.add_argument(
        "--flat-root",
        type=Path,
        default=_DEFAULT_FLAT_ROOT,
        help="Directory containing <Process>_flat.mat files.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_DEFAULT_OUTPUT_ROOT,
        help="Directory to write replay fixture npz files.",
    )
    return parser.parse_args()


def _resolve_processes(args: argparse.Namespace) -> tuple[str, ...]:
    requested = tuple(name.strip() for name in (args.process or []) if name and name.strip())
    if args.all_truncated or not requested:
        return TRUNCATED_PROCESSES

    unknown = sorted(set(requested) - set(TRUNCATED_PROCESSES))
    if unknown:
        raise ValueError(
            f"Unsupported process name(s): {', '.join(unknown)}. "
            f"Allowed: {', '.join(TRUNCATED_PROCESSES)}."
        )
    return requested


def main() -> int:
    args = _parse_args()
    processes = _resolve_processes(args)
    trajectory_path = _resolve_trajectory_path(args.trajectory_path)
    trajectory = load_trajectory(trajectory_path)

    rc = 0
    for process_name in processes:
        try:
            result = build_process_fixture_from_trajectory(
                process_name=process_name,
                trajectory=trajectory,
                flat_root=args.flat_root,
                output_root=args.output_root,
            )
        except Exception as exc:  # pragma: no cover - surfaced in CLI output
            print(f"[fail] {process_name}: {exc}")
            rc = 1
            continue

        unique_dt = sorted({round(v, 9) for v in result.effective_dt_sec})
        print(
            f"[ok] {result.process_name}: "
            f"n_snapshots={result.n_snapshots}, n_pairs={result.n_pairs}, "
            f"properties={list(result.properties)}, unique_dt={unique_dt}, output={result.output_path}"
        )
        for anomaly in result.anomalies:
            print(f"[note] {result.process_name}: {anomaly}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
