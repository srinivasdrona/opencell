from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from opencell.state.chromosome_store import ChromosomeStore


REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESS_NAME = "DNASupercoiling"
SEEDS = (0, 1, 2)


def _trace_path(seed: int) -> Path:
    candidates = (
        REPO_ROOT
        / "data"
        / "m1_sources"
        / "karr_native"
        / f"per_process_traces_v2_s{int(seed):03d}"
        / f"{PROCESS_NAME}_100ticks.mat",
        REPO_ROOT
        / "data"
        / "m1_sources"
        / "karr_native"
        / "per_process_traces_v2"
        / f"{PROCESS_NAME}_100ticks.mat",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Missing trace for seed {seed}: {candidates!r}")


def _chromosome_store(trace: h5py.File, group_name: str, tick: int) -> ChromosomeStore:
    dataset = trace[f"{group_name}/chromosome"]
    ref = dataset[0, tick] if dataset.shape[0] == 1 else dataset[tick, 0]
    return ChromosomeStore.from_hdf5_group(trace[ref])


def _projection_components(
    before_store: ChromosomeStore,
    after_store: ChromosomeStore,
) -> tuple[float, int]:
    before_linking = before_store.get_field("linkingNumbers")
    after_linking = after_store.get_field("linkingNumbers")
    delta_value_sum = float(after_linking.values.sum() - before_linking.values.sum())
    delta_nnz = int(len(after_linking.positions) - len(before_linking.positions))
    return delta_value_sum, delta_nnz


def main() -> int:
    projection_rows: list[np.ndarray] = []
    examples: list[tuple[int, int, float, int]] = []

    for seed in SEEDS:
        path = _trace_path(seed)
        with h5py.File(path, "r") as trace:
            n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
            seed_matrix = np.zeros((n_ticks, 2), dtype=np.float64)
            for tick in range(n_ticks):
                before_store = _chromosome_store(trace, "states_before", tick)
                after_store = _chromosome_store(trace, "states_after", tick)
                delta_value_sum, delta_nnz = _projection_components(before_store, after_store)
                seed_matrix[tick, 0] = delta_value_sum
                seed_matrix[tick, 1] = float(delta_nnz)
                if len(examples) < 8 and (tick < 3 or delta_value_sum != 0.0 or delta_nnz != 0):
                    examples.append((seed, tick, delta_value_sum, delta_nnz))
            projection_rows.append(seed_matrix)

    projection = np.stack(projection_rows, axis=0)
    value_sum = projection[:, :, 0]
    delta_nnz = projection[:, :, 1]

    print(f"Process: {PROCESS_NAME}")
    print(f"Seeds: {list(SEEDS)}")
    print(f"Projection shape: {projection.shape}")
    print(
        "delta_value_sum stats: "
        f"min={value_sum.min():.1f} max={value_sum.max():.1f} "
        f"nonzero={int(np.count_nonzero(value_sum))}/{value_sum.size}"
    )
    print(
        "delta_nnz stats: "
        f"min={int(delta_nnz.min())} max={int(delta_nnz.max())} "
        f"nonzero={int(np.count_nonzero(delta_nnz))}/{delta_nnz.size}"
    )
    print("Examples:")
    for seed, tick, delta_value_sum, nnz in examples:
        print(
            f"  seed={seed} tick={tick} "
            f"linkingNumbers.delta_value_sum={delta_value_sum:.1f} "
            f"linkingNumbers.delta_nnz={nnz}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
