from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import h5py
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from opencell.vivarium.karr_macromolecular_complexation import (  # noqa: E402
    MacromolecularComplexationProcess,
)
from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402


def _resolve_trace_path() -> Path:
    candidates = (
        REPO_ROOT
        / "data"
        / "m1_sources"
        / "karr_native"
        / "per_process_traces"
        / "MacromolecularComplexation_100ticks.mat",
        REPO_ROOT.parent.parent
        / "opencell"
        / "data"
        / "m1_sources"
        / "karr_native"
        / "per_process_traces"
        / "MacromolecularComplexation_100ticks.mat",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Unable to resolve MacromolecularComplexation_100ticks.mat")


def _resolve_replay_npz_path() -> Path:
    candidates = (
        REPO_ROOT
        / "data"
        / "karr_fixtures"
        / "per_process_replay"
        / "MacromolecularComplexation.npz",
        REPO_ROOT.parent.parent
        / "opencell"
        / "data"
        / "karr_fixtures"
        / "per_process_replay"
        / "MacromolecularComplexation.npz",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Unable to resolve MacromolecularComplexation.npz")


def _trace_datasets(trace_path: Path) -> dict[str, list[int]]:
    datasets: dict[str, list[int]] = {}
    with h5py.File(trace_path, "r") as handle:
        def _visitor(name: str, obj: h5py.Dataset | h5py.Group) -> None:
            if isinstance(obj, h5py.Dataset):
                datasets[name] = list(obj.shape)

        handle.visititems(_visitor)
    return dict(sorted(datasets.items()))


def _changed_tick_count(before: np.ndarray, after: np.ndarray) -> int:
    before_arr = np.asarray(before, dtype=np.float64)
    after_arr = np.asarray(after, dtype=np.float64)
    if before_arr.shape != after_arr.shape:
        raise ValueError(f"Shape mismatch: before={before_arr.shape} after={after_arr.shape}")
    return int(np.count_nonzero(np.any(before_arr != after_arr, axis=-1)))


def _normalize_replay_channel(value: np.ndarray) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if arr.ndim == 3:
        return arr[:, 0, :]
    if arr.ndim == 2:
        return arr
    raise ValueError(f"Unsupported replay channel shape: {arr.shape}")


def main() -> int:
    process = MacromolecularComplexationProcess({"rng_seed": 0})
    trace_path = _resolve_trace_path()
    replay_npz_path = _resolve_replay_npz_path()
    dataset_shapes = _trace_datasets(trace_path)
    with np.load(replay_npz_path, allow_pickle=False) as replay:
        replay_keys = sorted(replay.files)
        replay_shapes = {key: list(np.asarray(replay[key]).shape) for key in replay_keys}
        changed_ticks = {
            "substrates": _changed_tick_count(
                _normalize_replay_channel(replay["state_before__substrates"]),
                _normalize_replay_channel(replay["states_after__substrates"]),
            ),
            "complexs": _changed_tick_count(
                _normalize_replay_channel(replay["state_before__complexs"]),
                _normalize_replay_channel(replay["states_after__complexs"]),
            ),
            "enzymes": _changed_tick_count(
                _normalize_replay_channel(replay["state_before__enzymes"]),
                _normalize_replay_channel(replay["states_after__enzymes"]),
            ),
            "boundEnzymes": _changed_tick_count(
                _normalize_replay_channel(replay["state_before__boundEnzymes"]),
                _normalize_replay_channel(replay["states_after__boundEnzymes"]),
            ),
        }
        nonzero_elements = {
            "substrates_before": int(np.count_nonzero(_normalize_replay_channel(replay["state_before__substrates"]))),
            "substrates_after": int(np.count_nonzero(_normalize_replay_channel(replay["states_after__substrates"]))),
            "complexs_before": int(np.count_nonzero(_normalize_replay_channel(replay["state_before__complexs"]))),
            "complexs_after": int(np.count_nonzero(_normalize_replay_channel(replay["states_after__complexs"]))),
        }
        runtime_state = runner_helpers.build_state_template(process)
        substrate_wids = list(process.substrate_wids)
        complex_wids = list(process.complex_wids)
        runner_helpers.overlay_observable_into_state(
            process=process,
            state=runtime_state,
            observable="substrates",
            vector=_normalize_replay_channel(replay["state_before__substrates"])[0],
            wids=substrate_wids,
        )
        runner_helpers.overlay_observable_into_state(
            process=process,
            state=runtime_state,
            observable="complexs",
            vector=_normalize_replay_channel(replay["state_before__complexs"])[0],
            wids=complex_wids,
        )
        runner_helpers.refresh_allocator_views(process, runtime_state)
        allocated_snapshot = runtime_state.get("substrates_allocated", {}).get(process.name, {})
        allocated_vector = np.asarray(
            [float(allocated_snapshot.get(wid, 0.0)) for wid in substrate_wids],
            dtype=np.float64,
        )
        probe_update = process.next_update(1.0, runtime_state)

    observable_counts = {
        "substrates": {
            "n_wids_total": int(len(process.substrate_wids)),
            "n_wids_unique": int(len(set(map(str, process.substrate_wids)))),
            "duplicate_wids": int(sum(1 for count in Counter(map(str, process.substrate_wids)).values() if count > 1)),
        },
        "complexs": {
            "n_wids_total": int(len(process.complex_wids)),
            "n_wids_unique": int(len(set(map(str, process.complex_wids)))),
            "duplicate_wids": int(sum(1 for count in Counter(map(str, process.complex_wids)).values() if count > 1)),
        },
        "enzymes": {
            "n_wids_total": int(len(process.enzyme_wids)),
            "n_wids_unique": int(len(set(map(str, process.enzyme_wids)))),
            "duplicate_wids": int(sum(1 for count in Counter(map(str, process.enzyme_wids)).values() if count > 1)),
        },
    }

    update = process.next_update(
        1.0,
        {
            "substrates_allocated": {
                process.name: {
                    wid: 0.0 for wid in process.substrate_wids
                }
            }
        },
    )

    report = {
        "process": "MacromolecularComplexation",
        "replay_npz_path": str(replay_npz_path),
        "replay_npz_keys": replay_keys,
        "replay_npz_shapes": replay_shapes,
        "replay_changed_ticks": changed_ticks,
        "replay_nonzero_elements": nonzero_elements,
        "trace_path": str(trace_path),
        "trace_dataset_keys": list(dataset_shapes),
        "trace_before_channels": sorted(
            key.split("/", 1)[1]
            for key in dataset_shapes
            if key.startswith("states_before/")
        ),
        "trace_after_channels": sorted(
            key.split("/", 1)[1]
            for key in dataset_shapes
            if key.startswith("states_after/")
        ),
        "trace_shapes": {
            key: dataset_shapes[key]
            for key in dataset_shapes
            if key.startswith("states_before/") or key.startswith("states_after/")
        },
        "sut_next_update_top_level_keys": sorted(update.keys()),
        "sut_writes_complex_counts": "complex" in update and "counts" in update["complex"],
        "tick0_runner_probe": {
            "allocated_nonzero": int(np.count_nonzero(allocated_vector)),
            "allocated_sum": float(np.sum(allocated_vector)),
            "update_substrates_nonzero": int(len(probe_update.get("substrates", {}))),
            "update_complex_counts_nonzero": int(len(probe_update.get("complex", {}).get("counts", {}))),
        },
        "observable_counts": observable_counts,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
