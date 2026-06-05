from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest
from scipy.stats import ks_2samp, wasserstein_distance
from scipy.io import loadmat

# Ensure imports resolve to this worktree.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import load_fixture_channel_wids, wasserstein_over_wid_intersection  # noqa: E402

_KARR_ROOT = (
    _REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "ensembles"
    / "transcription"
)
_OC_ROOT = _REPO_ROOT / "data" / "opencell_ensembles" / "transcription"
_OC_MANIFEST_PATH = _OC_ROOT / "MANIFEST.json"
_REPORT_PATH = _OC_ROOT / "comparison_report.json"
_KS_FAILURES_PATH = _OC_ROOT / "ks_failures.csv"
_W1_FAILURES_PATH = _OC_ROOT / "wasserstein_failures.csv"
_TRANSCRIPTION_FIXTURE_PATH = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Transcription_flat.mat"

_SEEDS = tuple(range(50))
_N_TICKS = 100
_GLOBAL_ALPHA = 0.01
_BOOTSTRAP_ITERS = 200
_BOOTSTRAP_Q = 0.95
_BOOTSTRAP_MARGIN = 1.10

_OBSERVABLES = ("substrates", "enzymes", "boundEnzymes", "RNAs")
_EXPECTED_OC_PROCESS_CLASS = "KarrTranscriptionProcess"


def _karr_seed_path(seed: int) -> Path:
    return _KARR_ROOT / f"seed_{seed:03d}" / "Transcription_100ticks.mat"


def _oc_seed_path(seed: int) -> Path:
    return _OC_ROOT / f"seed_{seed:03d}" / "Transcription_100ticks.npz"


def _oc_seed_metadata_path(seed: int) -> Path:
    return _OC_ROOT / f"seed_{seed:03d}" / "metadata.json"


def _mat_cell_vector(handle: h5py.File, group: str, name: str, tick: int) -> np.ndarray:
    ds = handle[f"{group}/{name}"]
    rows, cols = int(ds.shape[0]), int(ds.shape[1])
    if rows == 1 and cols >= (tick + 1):
        ref = ds[0, tick]
    elif cols == 1 and rows >= (tick + 1):
        ref = ds[tick, 0]
    elif rows >= (tick + 1):
        ref = ds[tick, 0]
    elif cols >= (tick + 1):
        ref = ds[0, tick]
    else:
        raise IndexError(
            f"Tick index {tick} out of range for {group}/{name} shape={ds.shape}"
        )
    return np.asarray(handle[ref][()], dtype=np.float64).reshape(-1)


def _aggregate_vector(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size == 0:
        return 0.0
    return float(np.sum(arr))


def _parse_object_ids(values: object) -> list[str]:
    arr = np.asarray(values, dtype=object).reshape(-1)
    out: list[str] = []
    for raw in arr:
        item: object = raw
        while isinstance(item, np.ndarray):
            if item.size == 0:
                item = ""
                break
            item = item.flat[0]
        out.append(str(item))
    return out


def _load_karr_rna_wids() -> tuple[str, ...]:
    fixture_mat = loadmat(str(_TRANSCRIPTION_FIXTURE_PATH), squeeze_me=True, struct_as_record=False)
    data = fixture_mat.get("data")
    fixture = getattr(data, "fixture", None)
    if fixture is None:
        return tuple()
    states = np.asarray(getattr(fixture, "states", []), dtype=object).reshape(-1)
    for state in states:
        if hasattr(state, "transcriptionUnitWholeCellModelIDs"):
            ids = _parse_object_ids(getattr(state, "transcriptionUnitWholeCellModelIDs"))
            if ids:
                return tuple(ids)
    return tuple()


def _load_oc_observable_wids(seed: int, observable: str) -> tuple[str, ...]:
    metadata_path = _oc_seed_metadata_path(seed)
    if not metadata_path.exists():
        pytest.fail(f"Missing OpenCell metadata for seed {seed}: {metadata_path}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        pytest.fail(f"Failed to parse OpenCell metadata {metadata_path}: {exc}")
    wids_by_observable = metadata.get("wids_by_observable", {})
    if not isinstance(wids_by_observable, dict):
        pytest.fail(f"Invalid wids_by_observable in {metadata_path}")
    raw = wids_by_observable.get(observable, [])
    if not isinstance(raw, list):
        pytest.fail(f"Invalid WID list for observable={observable} in {metadata_path}")
    return tuple(str(x) for x in raw)


def _seed_coverage_check() -> None:
    missing_karr = [seed for seed in _SEEDS if not _karr_seed_path(seed).exists()]
    missing_oc = [seed for seed in _SEEDS if not _oc_seed_path(seed).exists()]
    missing_oc_metadata = [seed for seed in _SEEDS if not _oc_seed_metadata_path(seed).exists()]
    if missing_karr:
        pytest.fail(f"Missing Karr ensemble seeds: {missing_karr}")
    if missing_oc:
        pytest.fail(f"Missing OpenCell ensemble seeds: {missing_oc}")
    if missing_oc_metadata:
        pytest.fail(f"Missing OpenCell seed metadata files: {missing_oc_metadata}")


def _oc_process_class_check() -> str:
    if not _OC_MANIFEST_PATH.exists():
        pytest.fail(f"Missing OpenCell manifest: {_OC_MANIFEST_PATH}")
    try:
        manifest = json.loads(_OC_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive parse failure path
        pytest.fail(f"Failed to parse OpenCell manifest {_OC_MANIFEST_PATH}: {exc}")
    process_class = str(manifest.get("process_class", ""))
    if process_class != _EXPECTED_OC_PROCESS_CLASS:
        pytest.fail(
            f"OpenCell ensemble process_class mismatch: "
            f"got={process_class!r}, expected={_EXPECTED_OC_PROCESS_CLASS!r}"
        )
    return process_class


def _schema_check() -> None:
    with h5py.File(_karr_seed_path(_SEEDS[0]), "r") as handle:
        karr_keys = set(handle["states_after"].keys())
    with np.load(_oc_seed_path(_SEEDS[0]), allow_pickle=False) as data:
        oc_obs_keys = {k[len("obs__"): ] for k in data.files if k.startswith("obs__")}

    missing_karr_fields = sorted(set(_OBSERVABLES).difference(karr_keys))
    missing_oc_fields = sorted(set(_OBSERVABLES).difference(oc_obs_keys))
    if missing_karr_fields:
        pytest.fail(f"Karr schema missing observables: {missing_karr_fields}")
    if missing_oc_fields:
        pytest.fail(f"OpenCell schema missing observables: {missing_oc_fields}")


def _load_oc_observable_vector(seed: int, observable: str, tick: int) -> np.ndarray:
    path = _oc_seed_path(seed)
    with np.load(path, allow_pickle=False) as data:
        key = f"obs__{observable}"
        if key not in data:
            raise KeyError(f"Missing observable key {key} in {path}")
        arr = np.asarray(data[key], dtype=np.float64)
        if arr.ndim == 1:
            if tick != 0:
                raise IndexError(f"1D observable {observable} only has one element at seed={seed}")
            return arr.reshape(-1)
        if arr.ndim == 2:
            return arr[tick, :].reshape(-1)
        raise ValueError(f"Unsupported array rank for {key}: {arr.ndim}")


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(",".join(columns) + "\n")
        for row in rows:
            fh.write(",".join(str(row.get(col, "")) for col in columns) + "\n")


def _bootstrap_w1_threshold(
    karr_values: np.ndarray,
    *,
    rng: np.random.Generator,
) -> float:
    n = int(karr_values.shape[0])
    distances = np.zeros(_BOOTSTRAP_ITERS, dtype=np.float64)
    for b in range(_BOOTSTRAP_ITERS):
        idx_a = rng.integers(0, n, size=n, endpoint=False)
        idx_b = rng.integers(0, n, size=n, endpoint=False)
        distances[b] = wasserstein_distance(karr_values[idx_a], karr_values[idx_b])
    return float(np.quantile(distances, _BOOTSTRAP_Q) * _BOOTSTRAP_MARGIN)


def _build_sample_cube() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, Any], dict[str, Any]]:
    karr_samples: dict[str, np.ndarray] = {}
    oc_samples: dict[str, np.ndarray] = {}

    substrate_karr_wids = tuple(load_fixture_channel_wids("Transcription", "substrates"))
    with np.load(_oc_seed_path(_SEEDS[0]), allow_pickle=False):
        # OC substrate WIDs are fixed by process definition in C3 (ATP/CTP/GTP/UTP).
        substrate_oc_wids = ("ATP", "CTP", "GTP", "UTP")

    substrate_projection_meta: dict[str, Any] = {
        "karr_wids": list(substrate_karr_wids),
        "oc_wids": list(substrate_oc_wids),
        "intersection_wids": [],
        "dropped_karr_wids": [],
        "dropped_oc_wids": [],
        "tick0_intersection_w1_seed0": float("nan"),
    }
    rna_karr_wids = _load_karr_rna_wids()
    if not rna_karr_wids:
        pytest.fail("Missing Karr RNA WIDs (transcriptionUnitWholeCellModelIDs) for Transcription")
    rna_oc_wids = _load_oc_observable_wids(_SEEDS[0], "RNAs")
    rna_projection_meta: dict[str, Any] = {
        "karr_wids": list(rna_karr_wids),
        "oc_wids": list(rna_oc_wids),
        "intersection_wids": [],
        "dropped_karr_wids": [],
        "dropped_oc_wids": [],
        "tick0_intersection_w1_seed0": float("nan"),
    }

    for observable in _OBSERVABLES:
        karr_matrix = np.zeros((len(_SEEDS), _N_TICKS), dtype=np.float64)
        oc_matrix = np.zeros((len(_SEEDS), _N_TICKS), dtype=np.float64)
        for i, seed in enumerate(_SEEDS):
            with h5py.File(_karr_seed_path(seed), "r") as handle:
                for tick in range(_N_TICKS):
                    karr_vec = _mat_cell_vector(handle, "states_after", observable, tick)
                    oc_vec = _load_oc_observable_vector(seed, observable, tick)

                    if observable == "substrates":
                        w1_intersection, projected = wasserstein_over_wid_intersection(
                            karr_vector=karr_vec,
                            oc_vector=oc_vec,
                            karr_wids=substrate_karr_wids,
                            oc_wids=substrate_oc_wids,
                        )
                        if seed == _SEEDS[0] and tick == 0:
                            substrate_projection_meta["intersection_wids"] = list(projected.intersection_wids)
                            substrate_projection_meta["dropped_karr_wids"] = list(projected.dropped_karr_wids)
                            substrate_projection_meta["dropped_oc_wids"] = list(projected.dropped_oc_wids)
                            substrate_projection_meta["tick0_intersection_w1_seed0"] = float(w1_intersection)
                        karr_matrix[i, tick] = _aggregate_vector(projected.karr_projected)
                        oc_matrix[i, tick] = _aggregate_vector(projected.oc_projected)
                    elif observable == "RNAs":
                        w1_intersection, projected = wasserstein_over_wid_intersection(
                            karr_vector=karr_vec,
                            oc_vector=oc_vec,
                            karr_wids=rna_karr_wids,
                            oc_wids=rna_oc_wids,
                        )
                        if not np.isfinite(w1_intersection):
                            pytest.fail(
                                "Non-finite RNA W1 after WID intersection "
                                f"(seed={seed}, tick={tick}); "
                                "Transcription RNAs Karr/OC WID sets may have empty intersection."
                            )
                        if seed == _SEEDS[0] and tick == 0:
                            rna_projection_meta["intersection_wids"] = list(projected.intersection_wids)
                            rna_projection_meta["dropped_karr_wids"] = list(projected.dropped_karr_wids)
                            rna_projection_meta["dropped_oc_wids"] = list(projected.dropped_oc_wids)
                            rna_projection_meta["tick0_intersection_w1_seed0"] = float(w1_intersection)
                        karr_matrix[i, tick] = _aggregate_vector(projected.karr_projected)
                        oc_matrix[i, tick] = _aggregate_vector(projected.oc_projected)
                    else:
                        karr_matrix[i, tick] = _aggregate_vector(karr_vec)
                        oc_matrix[i, tick] = _aggregate_vector(oc_vec)

        karr_samples[observable] = karr_matrix
        oc_samples[observable] = oc_matrix
    return karr_samples, oc_samples, substrate_projection_meta, rna_projection_meta


def _run_comparison() -> dict[str, Any]:
    _seed_coverage_check()
    oc_process_class = _oc_process_class_check()
    _schema_check()
    karr_samples, oc_samples, substrate_projection_meta, rna_projection_meta = _build_sample_cube()

    family_size = len(_OBSERVABLES) * _N_TICKS
    corrected_alpha = _GLOBAL_ALPHA / family_size
    rng = np.random.default_rng(20260605)

    ks_failures: list[dict[str, Any]] = []
    w1_failures: list[dict[str, Any]] = []
    observable_rollup: dict[str, dict[str, float]] = {}

    for observable in _OBSERVABLES:
        ks_d_max = 0.0
        ks_p_corr_min = 1.0
        w1_max = 0.0
        w1_threshold_max = 0.0

        for tick in range(_N_TICKS):
            k_vals = karr_samples[observable][:, tick]
            o_vals = oc_samples[observable][:, tick]

            ks_res = ks_2samp(k_vals, o_vals, alternative="two-sided", method="auto")
            p_corr = min(1.0, float(ks_res.pvalue) * family_size)
            d_val = float(ks_res.statistic)
            if p_corr <= _GLOBAL_ALPHA:
                ks_failures.append(
                    {
                        "observable": observable,
                        "tick": tick,
                        "ks_d": d_val,
                        "p_value": float(ks_res.pvalue),
                        "p_value_bonferroni": p_corr,
                        "alpha_global": _GLOBAL_ALPHA,
                        "alpha_corrected": corrected_alpha,
                    }
                )

            w1_val = float(wasserstein_distance(k_vals, o_vals))
            threshold = _bootstrap_w1_threshold(k_vals, rng=rng)
            if w1_val > threshold:
                w1_failures.append(
                    {
                        "observable": observable,
                        "tick": tick,
                        "w1": w1_val,
                        "threshold": threshold,
                        "excess": w1_val - threshold,
                    }
                )

            ks_d_max = max(ks_d_max, d_val)
            ks_p_corr_min = min(ks_p_corr_min, p_corr)
            w1_max = max(w1_max, w1_val)
            w1_threshold_max = max(w1_threshold_max, threshold)

        observable_rollup[observable] = {
            "ks_d_max": ks_d_max,
            "ks_p_bonferroni_min": ks_p_corr_min,
            "w1_max": w1_max,
            "w1_threshold_max": w1_threshold_max,
        }

    _write_csv(
        _KS_FAILURES_PATH,
        ks_failures,
        (
            "observable",
            "tick",
            "ks_d",
            "p_value",
            "p_value_bonferroni",
            "alpha_global",
            "alpha_corrected",
        ),
    )
    _write_csv(
        _W1_FAILURES_PATH,
        w1_failures,
        ("observable", "tick", "w1", "threshold", "excess"),
    )

    report = {
        "process_name": "Transcription",
        "process_class": oc_process_class,
        "expected_process_class": _EXPECTED_OC_PROCESS_CLASS,
        "seed_list": list(_SEEDS),
        "n_ticks": _N_TICKS,
        "n_observables": len(_OBSERVABLES),
        "observables": list(_OBSERVABLES),
        "global_alpha": _GLOBAL_ALPHA,
        "family_size": family_size,
        "bonferroni_alpha": corrected_alpha,
        "bootstrap_iterations": _BOOTSTRAP_ITERS,
        "bootstrap_quantile": _BOOTSTRAP_Q,
        "bootstrap_margin": _BOOTSTRAP_MARGIN,
        "ks_failure_count": len(ks_failures),
        "wasserstein_failure_count": len(w1_failures),
        "observable_rollup": observable_rollup,
        "ks_failures_path": _KS_FAILURES_PATH.as_posix(),
        "wasserstein_failures_path": _W1_FAILURES_PATH.as_posix(),
        "substrate_projection": substrate_projection_meta,
        "rna_projection": rna_projection_meta,
        "overall_pass": len(ks_failures) == 0 and len(w1_failures) == 0,
    }
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def test_l2_2_transcription_distributional_fidelity() -> None:
    report = _run_comparison()
    assert report["overall_pass"], (
        "L2.2 Transcription distributional mismatch. "
        f"ks_failure_count={report['ks_failure_count']}, "
        f"wasserstein_failure_count={report['wasserstein_failure_count']}, "
        f"report={_REPORT_PATH}"
    )
