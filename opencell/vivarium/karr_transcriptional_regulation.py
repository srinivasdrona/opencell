"""Vivarium Process for Karr transcriptional regulation binding + fold-changes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/TranscriptionalRegulation_flat.mat"
_DEFAULT_COMPLEX_FIXTURE_PATH = "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"
_FLOAT_TOL = 1e-12


def _resolve_fixture_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


def _extract_wids(cell_array: np.ndarray) -> list[str]:
    """Convert MATLAB cell-string arrays into plain Python string lists."""
    values = np.asarray(cell_array, dtype=object)
    if values.shape == (1, 1):
        values = np.asarray(values[0, 0], dtype=object)

    out: list[str] = []
    for raw in values.ravel():
        value: object = raw
        while isinstance(value, np.ndarray):
            if value.size == 0:
                value = ""
                break
            value = value.flat[0]
        out.append(str(value))
    return out


def _as_field_matrix(fx: np.ndarray, field: str) -> np.ndarray:
    """Load a MATLAB fixture field and unwrap flat-mat nesting."""
    value = fx[field]
    arr = np.asarray(value)
    if arr.shape == (1, 1):
        arr = np.asarray(arr[0, 0])
    return arr


def _orient_matrix(mat: np.ndarray, n_tf: int, n_tu: int) -> np.ndarray:
    matrix = np.asarray(mat, dtype=np.float64)
    if matrix.shape == (n_tf, n_tu):
        return matrix
    if matrix.shape == (n_tu, n_tf):
        return matrix.T
    raise ValueError(f"Cannot orient matrix of shape {matrix.shape} to ({n_tf}, {n_tu})")


def _orient_other_activities(mat: np.ndarray, n_tu: int, n_tf: int) -> np.ndarray:
    matrix = np.asarray(mat, dtype=np.float64)
    if matrix.shape == (n_tu, n_tf):
        return matrix.T
    if matrix.shape == (n_tf, n_tu):
        return matrix
    raise ValueError(f"Cannot orient otherActivities of shape {matrix.shape} to ({n_tf}, {n_tu})")


def _load_fixture(path: str | Path) -> dict[str, Any]:
    resolved = _resolve_fixture_path(path)
    mat = loadmat(str(resolved))
    fx = mat["data"]["fixture"][0, 0]
    names = set(fx.dtype.names or ())

    tf_field = (
        "transcriptionFactorWholeCellModelIDs"
        if "transcriptionFactorWholeCellModelIDs" in names
        else "enzymeWholeCellModelIDs"
    )
    if tf_field not in names:
        raise KeyError("Missing TF IDs field in TranscriptionalRegulation fixture")
    tf_wids = _extract_wids(_as_field_matrix(fx, tf_field))
    n_tf = len(tf_wids)

    if "transcriptionUnitWholeCellModelIDs" not in names:
        raise KeyError("Missing transcriptionUnitWholeCellModelIDs field in fixture")
    tu_all_wids = _extract_wids(_as_field_matrix(fx, "transcriptionUnitWholeCellModelIDs"))
    n_tu_all = len(tu_all_wids)

    if "tfPromoterAffinityMatrix" in names and "tfTuFoldChangeMatrix" in names:
        affinity_full = _orient_matrix(
            _as_field_matrix(fx, "tfPromoterAffinityMatrix"), n_tf=n_tf, n_tu=n_tu_all
        )
        fold_change_full = _orient_matrix(
            _as_field_matrix(fx, "tfTuFoldChangeMatrix"), n_tf=n_tf, n_tu=n_tu_all
        )
        other_activities_full = np.ones((n_tf, n_tu_all), dtype=np.float64)
        if "otherActivities" in names:
            other_activities_full = _orient_other_activities(
                _as_field_matrix(fx, "otherActivities"), n_tu=n_tu_all, n_tf=n_tf
            )
    else:
        required_sparse = {"tfIndexs", "tuIndexs", "tfAffinities", "tfActivities"}
        if not required_sparse.issubset(names):
            missing = sorted(required_sparse.difference(names))
            raise KeyError(f"Missing sparse TR fields: {missing}")

        tf_idx = np.asarray(_as_field_matrix(fx, "tfIndexs"), dtype=np.int64).reshape(-1)
        tu_idx = np.asarray(_as_field_matrix(fx, "tuIndexs"), dtype=np.int64).reshape(-1)
        tf_aff = np.asarray(_as_field_matrix(fx, "tfAffinities"), dtype=np.float64).reshape(-1)
        tf_act = np.asarray(_as_field_matrix(fx, "tfActivities"), dtype=np.float64).reshape(-1)
        if not (tf_idx.size == tu_idx.size == tf_aff.size == tf_act.size):
            raise ValueError("Sparse TF/TU arrays have mismatched lengths")

        affinity_full = np.zeros((n_tf, n_tu_all), dtype=np.float64)
        fold_change_full = np.ones((n_tf, n_tu_all), dtype=np.float64)
        for t_raw, u_raw, a_raw, c_raw in zip(tf_idx, tu_idx, tf_aff, tf_act, strict=False):
            tf_i = int(t_raw) - 1
            tu_i = int(u_raw) - 1
            if tf_i < 0 or tf_i >= n_tf or tu_i < 0 or tu_i >= n_tu_all:
                continue
            affinity_full[tf_i, tu_i] = max(affinity_full[tf_i, tu_i], float(a_raw))
            fold_change_full[tf_i, tu_i] = float(c_raw)

        other_activities_full = np.ones((n_tf, n_tu_all), dtype=np.float64)
        if "otherActivities" in names:
            other_activities_full = _orient_other_activities(
                _as_field_matrix(fx, "otherActivities"), n_tu=n_tu_all, n_tf=n_tf
            )

    overlap_mask = (affinity_full > 0.0) & (np.abs(other_activities_full - 1.0) > _FLOAT_TOL)
    if np.any(overlap_mask):
        overlap_indices = np.argwhere(overlap_mask)
        preview = ", ".join(
            f"(tf={int(tf_i)}, tu={int(tu_i)})"
            for tf_i, tu_i in overlap_indices[:10]
        )
        if overlap_indices.shape[0] > 10:
            preview = f"{preview}, ..."
        raise ValueError(
            "TranscriptionalRegulation fixture has overlapping binding and otherActivities entries; "
            f"expected disjoint matrices but found {overlap_indices.shape[0]} overlap(s): {preview}"
        )

    # Karr applies otherActivities for TF-presence effects that are distinct
    # from promoter-bound TF fold changes; keep this defensive zeroing as a belt-and-braces mask.
    other_activities_full = np.where(affinity_full > 0.0, 1.0, other_activities_full)

    relationship_mask = (
        (affinity_full > 0.0)
        | (np.abs(fold_change_full - 1.0) > _FLOAT_TOL)
        | (np.abs(other_activities_full - 1.0) > _FLOAT_TOL)
    )
    tu_keep = np.flatnonzero(np.any(relationship_mask, axis=0))
    if tu_keep.size == 0:
        raise ValueError("No regulated transcription units discovered in fixture")

    tu_wids = [tu_all_wids[idx] for idx in tu_keep.tolist()]
    affinity = affinity_full[:, tu_keep]
    fold_change = fold_change_full[:, tu_keep]
    other_activities = other_activities_full[:, tu_keep]

    return {
        "tf_wids": tf_wids,
        "tu_wids": tu_wids,
        "tf_promoter_affinity": affinity,
        "tf_tu_fold_change": fold_change,
        "tf_other_activities": other_activities,
        "n_relationships": int(
            np.count_nonzero(
                (affinity > 0.0)
                | (np.abs(fold_change - 1.0) > _FLOAT_TOL)
                | (np.abs(other_activities - 1.0) > _FLOAT_TOL)
            )
        ),
    }


def _load_canonical_complex_wids(path: str | Path) -> set[str]:
    try:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]
        names = set(fx.dtype.names or ())
        if "complexWholeCellModelIDs" not in names:
            return set()
        return set(_extract_wids(_as_field_matrix(fx, "complexWholeCellModelIDs")))
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
        return set()


class KarrTranscriptionalRegulationProcess(Process):
    """TF-promoter binding and transcription-rate fold-change modulation."""

    name = "karr_transcriptional_regulation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "complex_wids": None,
        "complex_fixture_path": _DEFAULT_COMPLEX_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        fixture = _load_fixture(self.parameters["fixture_path"])
        self.tf_wids: list[str] = fixture["tf_wids"]
        self.tu_wids: list[str] = fixture["tu_wids"]
        self.tf_promoter_affinity: np.ndarray = fixture["tf_promoter_affinity"]
        self.tf_tu_fold_change: np.ndarray = fixture["tf_tu_fold_change"]
        self.tf_other_activities: np.ndarray = fixture["tf_other_activities"]
        self.n_relationships: int = fixture["n_relationships"]

        self._n_tf = len(self.tf_wids)
        self._n_tu = len(self.tu_wids)
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        configured_complex_wids = self.parameters.get("complex_wids")
        if configured_complex_wids is None:
            complex_wids = _load_canonical_complex_wids(self.parameters["complex_fixture_path"])
        else:
            complex_wids = {str(wid) for wid in configured_complex_wids}
        self._tf_wid_source: dict[str, str] = {
            tf_wid: ("complex" if tf_wid in complex_wids else "protein") for tf_wid in self.tf_wids
        }
        self._tf_is_complex = np.asarray(
            [self._tf_wid_source[tf_wid] == "complex" for tf_wid in self.tf_wids],
            dtype=bool,
        )

    def ports_schema(self) -> dict[str, Any]:
        return {
            "protein": {
                "counts": {
                    tf_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for tf_wid in self.tf_wids
                }
            },
            "complex": {
                "counts": {
                    tf_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for tf_wid in self.tf_wids
                }
            },
            "tf_binding": {
                tf_wid: {
                    tu_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for tu_wid in self.tu_wids
                }
                for tf_wid in self.tf_wids
            },
            "tx_rate_fold_change": {
                tu_wid: {"_default": 1.0, "_updater": "set", "_emit": True}
                for tu_wid in self.tu_wids
            },
        }

    def _read_tf_counts(self, states: dict[str, Any]) -> np.ndarray:
        protein_counts = states.get("protein", {}).get("counts", {})
        if not isinstance(protein_counts, dict):
            protein_counts = {}
        complex_counts = states.get("complex", {}).get("counts", {})
        if not isinstance(complex_counts, dict):
            complex_counts = {}

        tf_counts = np.zeros(self._n_tf, dtype=np.float64)
        for tf_i, tf_wid in enumerate(self.tf_wids):
            source = self._tf_wid_source[tf_wid]
            source_counts = complex_counts if source == "complex" else protein_counts
            if tf_wid not in source_counts:
                raise KeyError(
                    f"Missing TF WID '{tf_wid}' in expected {source}.counts store "
                    "for karr_transcriptional_regulation"
                )
            tf_counts[tf_i] = max(0.0, float(source_counts[tf_wid]))
        return tf_counts

    def _read_binding(self, states: dict[str, Any]) -> np.ndarray:
        binding = np.zeros((self._n_tf, self._n_tu), dtype=np.int8)
        binding_store = states.get("tf_binding", {})
        for tf_i, tf_wid in enumerate(self.tf_wids):
            tf_state = binding_store.get(tf_wid, {})
            for tu_i, tu_wid in enumerate(self.tu_wids):
                if float(tf_state.get(tu_wid, 0.0)) > 0.5:
                    binding[tf_i, tu_i] = 1
        return binding

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        tf_counts = self._read_tf_counts(states)
        binding = self._read_binding(states)
        binding_delta = np.zeros((self._n_tf, self._n_tu), dtype=np.int64)

        for tf_i, tf_wid in enumerate(self.tf_wids):
            total_copies = max(0, int(np.floor(float(tf_counts[tf_i]))))
            row = binding[tf_i].copy()

            bound_idx = np.flatnonzero(row > 0)
            n_bound = int(bound_idx.size)
            if n_bound > total_copies:
                n_to_unbind = n_bound - total_copies
                affinities = self.tf_promoter_affinity[tf_i, bound_idx]
                # Prefer to retain higher-affinity bindings when TF copies drop.
                release = bound_idx[np.argsort(affinities)[:n_to_unbind]]
                row[release] = 0
                binding_delta[tf_i, release] -= 1
                n_bound -= n_to_unbind

            free_copies = total_copies - n_bound
            if free_copies > 0:
                available_idx = np.flatnonzero((row == 0) & (self.tf_promoter_affinity[tf_i] > 0.0))
                if available_idx.size > 0:
                    n_to_bind = min(free_copies, int(available_idx.size))
                    if n_to_bind == available_idx.size:
                        chosen = available_idx
                    else:
                        weights = self.tf_promoter_affinity[tf_i, available_idx].astype(np.float64)
                        weight_sum = float(np.sum(weights))
                        probs = (weights / weight_sum) if weight_sum > 0.0 else None
                        chosen = np.asarray(
                            self._rng.choice(available_idx, size=n_to_bind, replace=False, p=probs),
                            dtype=np.int64,
                        ).reshape(-1)
                    row[chosen] = 1
                    binding_delta[tf_i, chosen] += 1

            binding[tf_i] = row

        bound_effects = np.where(binding > 0, self.tf_tu_fold_change, 1.0)
        fold_change_total = np.prod(bound_effects, axis=0, dtype=np.float64)

        tf_present = tf_counts > 0.0
        if np.any(tf_present):
            other_effects = np.where(tf_present[:, np.newaxis], self.tf_other_activities, 1.0)
            fold_change_total = fold_change_total * np.prod(
                other_effects, axis=0, dtype=np.float64
            )

        tf_binding_update: dict[str, dict[str, float]] = {}
        for tf_i, tf_wid in enumerate(self.tf_wids):
            per_tf: dict[str, float] = {}
            for tu_i, tu_wid in enumerate(self.tu_wids):
                delta = int(binding_delta[tf_i, tu_i])
                if delta != 0:
                    per_tf[tu_wid] = float(delta)
            if per_tf:
                tf_binding_update[tf_wid] = per_tf

        return {
            "tf_binding": tf_binding_update,
            "tx_rate_fold_change": {
                tu_wid: float(fold_change_total[tu_i]) for tu_i, tu_wid in enumerate(self.tu_wids)
            },
        }


__all__ = ["KarrTranscriptionalRegulationProcess", "_load_fixture"]
