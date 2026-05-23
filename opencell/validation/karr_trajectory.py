"""Load Karr's full cell-cycle trajectory and expose scaffold observables.

Notes
-----
- The trajectory file is MATLAB v7.3 (`-v7.3`), so it is HDF5-backed and read
  via `h5py`.
- The export script captures only numeric state properties with
  `numel(v) < 10000`. Some requested observables are therefore represented as
  timeline- or mass-based proxies in this Phase E.1 scaffold.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import numpy as np

DEFAULT_KARR_TRAJECTORY_PATH = "data/m1_sources/karr_native/cell_cycle_trajectory.mat"
AVOGADRO = 6.02214076e23

_REPLICATION_STATE_LABELS: dict[int, str] = {
    0: "idle",
    1: "initiating",
    2: "elongating",
    3: "complete",
}


def _resolve_trajectory_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate.resolve()

    repo_root = Path(__file__).resolve().parents[2]
    rel = Path(path)

    candidates = [
        repo_root / rel,
        repo_root.parent.parent / "opencell" / rel,
        Path("/mnt/e/opencell") / rel,
    ]
    for option in candidates:
        if option.exists():
            return option.resolve()

    raise FileNotFoundError(f"Karr trajectory not found: {path}")


def _decode_matlab_char(dataset: h5py.Dataset) -> str:
    codes = np.asarray(dataset[()], dtype=np.uint16).reshape(-1)
    return "".join(chr(int(code)) for code in codes if int(code) != 0)


def _cell_value(handle: h5py.File, dataset: h5py.Dataset, index: int) -> np.ndarray:
    if dataset.dtype != object:
        return np.asarray(dataset[()])
    ref = dataset[index, 0]
    return np.asarray(handle[ref][()])


def _first_cell_array(handle: h5py.File, group: h5py.Group, name: str) -> np.ndarray:
    ds = group[name]
    return _cell_value(handle, ds, 0)


def _scalar_series(
    handle: h5py.File,
    group: h5py.Group,
    name: str,
    *,
    reducer: str = "first",
) -> np.ndarray:
    ds = group[name]
    n = ds.shape[0]
    out = np.zeros(n, dtype=np.float64)
    for i in range(n):
        arr = np.asarray(_cell_value(handle, ds, i), dtype=np.float64).reshape(-1)
        if arr.size == 0:
            out[i] = np.nan
            continue
        if reducer == "sum":
            out[i] = float(arr.sum())
        else:
            out[i] = float(arr[0])
    return out


def _matrix_series(handle: h5py.File, group: h5py.Group, name: str) -> np.ndarray:
    ds = group[name]
    n = ds.shape[0]
    first = np.asarray(_cell_value(handle, ds, 0), dtype=np.float64)
    out = np.zeros((n, *first.shape), dtype=np.float64)
    out[0] = first
    for i in range(1, n):
        out[i] = np.asarray(_cell_value(handle, ds, i), dtype=np.float64)
    return out


def _weighted_mean(values: np.ndarray, weights: np.ndarray, idxs: np.ndarray) -> float:
    valid = idxs[(idxs >= 0) & (idxs < values.size)]
    if valid.size == 0:
        return float(np.mean(values))
    v = values[valid]
    w = weights[valid]
    w_sum = float(w.sum())
    if w_sum <= 0.0:
        return float(np.mean(v))
    return float(np.dot(v, w) / w_sum)


def _derive_replication_state_and_fork_progress(
    time_s: np.ndarray,
    initiation_time_s: np.ndarray,
    replication_duration_s: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    init = initiation_time_s
    duration = np.maximum(replication_duration_s, 1e-12)
    complete_time = init + duration

    state = np.zeros_like(time_s, dtype=np.int64)
    state[np.isclose(time_s, init, atol=1e-9)] = 1
    state[(time_s > init) & (time_s < complete_time)] = 2
    state[time_s >= complete_time] = 3

    fork_progress = np.clip((time_s - init) / duration, 0.0, 1.0)
    return state, fork_progress


def load_karr_trajectory(
    path: str | Path = DEFAULT_KARR_TRAJECTORY_PATH,
    *,
    max_time_s: float | None = None,
) -> dict[str, Any]:
    """Load Karr trajectory and expose Phase E.1 scaffold observables."""
    resolved = _resolve_trajectory_path(path)

    with h5py.File(resolved, "r") as h5:
        metadata_group = h5["metadata"]
        snapshots = h5["snapshots"]

        metadata = {
            "snapshot_interval": int(np.asarray(metadata_group["snapshot_interval"])[0, 0]),
            "n_total_steps_target": int(np.asarray(metadata_group["n_total_steps_target"])[0, 0]),
            "n_snapshots_captured": int(np.asarray(metadata_group["n_snapshots_captured"])[0, 0]),
            "rng_seed": int(np.asarray(metadata_group["rng_seed"])[0, 0]),
            "timestamp": _decode_matlab_char(metadata_group["timestamp"]),
        }

        tick = np.asarray(snapshots["tick"][()], dtype=np.float64).reshape(-1)
        time_s = _scalar_series(h5, snapshots, "Time_values")

        cell_dry_mass_g = _scalar_series(h5, snapshots, "Mass_cellDry", reducer="sum")

        rna_dry_mass_g = _scalar_series(h5, snapshots, "Rna_dryWeight", reducer="sum")
        rna_weight_fraction_mrna = _scalar_series(h5, snapshots, "Rna_weightFractionMRNA")
        mrna_mass_g = rna_dry_mass_g * rna_weight_fraction_mrna

        rna_expression = np.asarray(_first_cell_array(h5, snapshots, "Rna_expression"), dtype=np.float64)
        rna_expression = rna_expression.reshape(-1)
        rna_mw_da = np.asarray(_first_cell_array(h5, snapshots, "Rna_molecularWeights"), dtype=np.float64)
        rna_mw_da = rna_mw_da.reshape(-1)
        mature_mrna_idxs = (
            np.asarray(_first_cell_array(h5, snapshots, "Rna_matureMRNAIndexs"), dtype=np.int64).reshape(-1)
            - 1
        )
        mean_mrna_mw_da = _weighted_mean(rna_mw_da, rna_expression, mature_mrna_idxs)
        mrna_total_count_estimate = mrna_mass_g * AVOGADRO / max(mean_mrna_mw_da, 1e-12)

        protein_monomer_dry_mass_g = _scalar_series(h5, snapshots, "ProteinMonomer_dryWeight", reducer="sum")
        protein_mw_da = np.asarray(
            _first_cell_array(h5, snapshots, "ProteinMonomer_molecularWeights"), dtype=np.float64
        ).reshape(-1)
        protein_mature_idxs = (
            np.asarray(_first_cell_array(h5, snapshots, "ProteinMonomer_matureIndexs"), dtype=np.int64).reshape(-1)
            - 1
        )
        mean_protein_mw_da = _weighted_mean(
            protein_mw_da,
            np.ones_like(protein_mw_da, dtype=np.float64),
            protein_mature_idxs,
        )
        protein_total_count_estimate = protein_monomer_dry_mass_g * AVOGADRO / max(
            mean_protein_mw_da, 1e-12
        )

        metabolite_counts = _matrix_series(h5, snapshots, "Metabolite_counts")
        atp_idx = int(np.asarray(_first_cell_array(h5, snapshots, "Metabolite_atpIndexs")).reshape(-1)[0]) - 1
        ntp_idxs = (
            np.asarray(_first_cell_array(h5, snapshots, "Metabolite_ntpIndexs"), dtype=np.int64).reshape(-1) - 1
        )
        dntp_idxs = (
            np.asarray(_first_cell_array(h5, snapshots, "Metabolite_dntpIndexs"), dtype=np.int64).reshape(-1) - 1
        )
        gtp_idx = int(ntp_idxs[2]) if ntp_idxs.size >= 3 else int(ntp_idxs[-1])

        atp_pool = metabolite_counts[:, 0, atp_idx]
        gtp_pool = metabolite_counts[:, 0, gtp_idx]
        dntp_pool_total = np.sum(metabolite_counts[:, 0, dntp_idxs], axis=1)

        replication_initiation_s = _scalar_series(h5, snapshots, "Time_replicationInitiationDuration")
        replication_duration_s = _scalar_series(h5, snapshots, "Time_replicationDuration")
        cell_cycle_length_s = _scalar_series(h5, snapshots, "Time_cellCycleLength")
        replication_state_code, fork_position_norm = _derive_replication_state_and_fork_progress(
            time_s,
            replication_initiation_s,
            replication_duration_s,
        )

    mask = np.ones_like(time_s, dtype=bool)
    if max_time_s is not None:
        mask = time_s <= float(max_time_s)

    observables = {
        "cell_dry_mass_g": cell_dry_mass_g[mask],
        "replication_state_code": replication_state_code[mask].astype(np.float64),
        "fork_position_norm": fork_position_norm[mask],
        "mrna_total_count_estimate": mrna_total_count_estimate[mask],
        "protein_total_count_estimate": protein_total_count_estimate[mask],
        "atp_pool": atp_pool[mask],
        "gtp_pool": gtp_pool[mask],
        "dntp_pool_total": dntp_pool_total[mask],
        "division_event_timestamp_s": cell_cycle_length_s[mask],
    }

    labels = [_REPLICATION_STATE_LABELS[int(code)] for code in replication_state_code[mask]]
    return {
        "source_path": str(resolved),
        "metadata": metadata,
        "time_s": time_s[mask],
        "tick": tick[mask],
        "observables": observables,
        "replication_state_labels": labels,
        "phenotypes": {},
        "assumptions": {
            "gtp_index_from_ntp_order": int(gtp_idx),
            "mrna_count_is_mass_based_estimate": True,
            "protein_count_is_mass_based_estimate": True,
            "fork_position_is_normalized_progress": True,
        },
    }


__all__ = ["DEFAULT_KARR_TRAJECTORY_PATH", "load_karr_trajectory"]
