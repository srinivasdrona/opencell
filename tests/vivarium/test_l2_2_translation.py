from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest
from scipy.stats import ks_2samp, wasserstein_distance

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import load_fixture_channel_wids, wasserstein_over_wid_intersection

_KARR_ROOT = (
    _REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "ensembles"
    / "translation"
)
_OC_ROOT = _REPO_ROOT / "data" / "opencell_ensembles" / "translation"
_OC_MANIFEST_PATH = _OC_ROOT / "MANIFEST.json"
_REPORT_PATH = _OC_ROOT / "comparison_report.json"
_KS_FAILURES_PATH = _OC_ROOT / "ks_failures.csv"
_W1_FAILURES_PATH = _OC_ROOT / "wasserstein_failures.csv"

_SEEDS = tuple(range(50))
_N_TICKS = 100
_GLOBAL_ALPHA = 0.01
_BOOTSTRAP_ITERS = 200
_BOOTSTRAP_Q = 0.95
_BOOTSTRAP_MARGIN = 1.10

_OBSERVABLES = (
    "substrates",
    "enzymes",
    "boundEnzymes",
    "monomers",
    "ribosome_state_active_count",
    "ribosome_bound_mrnas_nonzero_count",
    "ribosome_mrna_positions_sum",
)
_CORE_OBSERVABLES = {"substrates", "enzymes", "boundEnzymes", "monomers"}
_SUMMARY_OBSERVABLES = set(_OBSERVABLES).difference(_CORE_OBSERVABLES)
_EXPECTED_OC_PROCESS_CLASS = "KarrTranslationProcess"


def _karr_seed_path(seed: int) -> Path:
    return _KARR_ROOT / f"seed_{seed:03d}" / "Translation_100ticks.mat"


def _oc_seed_path(seed: int) -> Path:
    return _OC_ROOT / f"seed_{seed:03d}" / "Translation_100ticks.npz"


def _oc_seed_metadata_path(seed: int) -> Path:
    return _OC_ROOT / f"seed_{seed:03d}" / "metadata.json"


def _mat_cell_vector(handle: h5py.File, group: str, name: str, tick: int) -> np.ndarray:
    ds = handle[f"{group}/{name}"]
    rows, cols = int(ds.shape[0]), int(ds.shape[1])
    if rows == 1 and cols >= (tick + 1):
        ref = ds[0, tick]
    elif cols == 1 and rows >= (tick + 1) or rows >= (tick + 1):
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


def _load_karr_observable(seed: int, observable: str) -> np.ndarray:
    path = _karr_seed_path(seed)
    with h5py.File(path, "r") as handle:
        out = np.zeros(_N_TICKS, dtype=np.float64)
        for tick in range(_N_TICKS):
            vec = _mat_cell_vector(handle, "states_after", observable, tick)
            out[tick] = _aggregate_vector(vec)
    return out


def _load_oc_observable(seed: int, observable: str) -> np.ndarray:
    path = _oc_seed_path(seed)
    with np.load(path, allow_pickle=False) as data:
        key = f"obs__{observable}" if observable in _CORE_OBSERVABLES else f"summary__{observable}"
        if key not in data:
            raise KeyError(f"Missing observable key {key} in {path}")
        arr = np.asarray(data[key], dtype=np.float64)
        if arr.ndim == 1:
            return arr.reshape(-1)
        if arr.ndim == 2:
            return np.sum(arr, axis=1, dtype=np.float64).reshape(-1)
        raise ValueError(f"Unsupported array rank for {key}: {arr.ndim}")


def _load_karr_observable_matrix(seed: int, observable: str) -> np.ndarray:
    path = _karr_seed_path(seed)
    with h5py.File(path, "r") as handle:
        rows = [_mat_cell_vector(handle, "states_after", observable, tick) for tick in range(_N_TICKS)]
    if not rows:
        return np.zeros((_N_TICKS, 0), dtype=np.float64)
    width = int(rows[0].shape[0])
    out = np.zeros((_N_TICKS, width), dtype=np.float64)
    for tick, row in enumerate(rows):
        if int(row.shape[0]) != width:
            pytest.fail(
                f"Karr width drift: seed={seed}, observable={observable}, tick={tick}, "
                f"tick_width={int(row.shape[0])}, expected_width={width}"
            )
        out[tick, :] = row
    return out


def _load_oc_observable_matrix(seed: int, observable: str) -> np.ndarray:
    path = _oc_seed_path(seed)
    with np.load(path, allow_pickle=False) as data:
        key = f"obs__{observable}" if observable in _CORE_OBSERVABLES else f"summary__{observable}"
        if key not in data:
            raise KeyError(f"Missing observable key {key} in {path}")
        arr = np.asarray(data[key], dtype=np.float64)
        if arr.ndim == 1:
            return arr.reshape(-1, 1)
        if arr.ndim == 2:
            return arr
        raise ValueError(f"Unsupported array rank for {key}: {arr.ndim}")


def _load_oc_substrate_wids(seed: int) -> tuple[str, ...]:
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
    raw = wids_by_observable.get("substrates", [])
    if not isinstance(raw, list):
        pytest.fail(f"Invalid substrate WID list in {metadata_path}")
    return tuple(str(x) for x in raw)


def _build_substrates_intersection_samples() -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    karr_wids = tuple(str(x) for x in load_fixture_channel_wids("Translation", "substrates"))
    if not karr_wids:
        pytest.fail("Missing fixture-derived Karr substrate WIDs for Translation")
    oc_wids = _load_oc_substrate_wids(_SEEDS[0])
    if not oc_wids:
        pytest.fail("Missing OpenCell substrate WIDs in seed metadata")

    karr_matrix = np.zeros((len(_SEEDS), _N_TICKS), dtype=np.float64)
    oc_matrix = np.zeros((len(_SEEDS), _N_TICKS), dtype=np.float64)

    reference_intersection: tuple[str, ...] | None = None
    reference_dropped_karr: tuple[str, ...] | None = None
    reference_dropped_oc: tuple[str, ...] | None = None
    tick0_seed0_w1: float | None = None

    for i, seed in enumerate(_SEEDS):
        karr_tick_vectors = _load_karr_observable_matrix(seed, "substrates")
        oc_tick_vectors = _load_oc_observable_matrix(seed, "substrates")
        if karr_tick_vectors.shape[0] != _N_TICKS:
            pytest.fail(
                f"Karr n_ticks mismatch: seed={seed}, observable=substrates, "
                f"got={karr_tick_vectors.shape[0]}, expected={_N_TICKS}"
            )
        if oc_tick_vectors.shape[0] != _N_TICKS:
            pytest.fail(
                f"OpenCell n_ticks mismatch: seed={seed}, observable=substrates, "
                f"got={oc_tick_vectors.shape[0]}, expected={_N_TICKS}"
            )
        for tick in range(_N_TICKS):
            w1_val, projected = wasserstein_over_wid_intersection(
                karr_vector=karr_tick_vectors[tick, :],
                oc_vector=oc_tick_vectors[tick, :],
                karr_wids=karr_wids,
                oc_wids=oc_wids,
            )
            if not np.isfinite(w1_val):
                pytest.fail(
                    f"Non-finite substrate W1 after WID intersection: seed={seed}, tick={tick}"
                )
            if reference_intersection is None:
                reference_intersection = tuple(projected.intersection_wids)
                reference_dropped_karr = tuple(projected.dropped_karr_wids)
                reference_dropped_oc = tuple(projected.dropped_oc_wids)
            else:
                if tuple(projected.intersection_wids) != reference_intersection:
                    pytest.fail(
                        f"Substrate intersection WIDs drifted at seed={seed}, tick={tick}"
                    )
                if tuple(projected.dropped_karr_wids) != reference_dropped_karr:
                    pytest.fail(
                        f"Dropped Karr substrate WIDs drifted at seed={seed}, tick={tick}"
                    )
                if tuple(projected.dropped_oc_wids) != reference_dropped_oc:
                    pytest.fail(
                        f"Dropped OC substrate WIDs drifted at seed={seed}, tick={tick}"
                    )

            if seed == _SEEDS[0] and tick == 0:
                tick0_seed0_w1 = float(w1_val)
            karr_matrix[i, tick] = _aggregate_vector(projected.karr_projected)
            oc_matrix[i, tick] = _aggregate_vector(projected.oc_projected)

    assert reference_intersection is not None
    assert reference_dropped_karr is not None
    assert reference_dropped_oc is not None
    assert tick0_seed0_w1 is not None

    audit = {
        "karr_wid_count": len(karr_wids),
        "oc_wid_count": len(oc_wids),
        "intersection_wid_count": len(reference_intersection),
        "intersection_wids": list(reference_intersection),
        "dropped_karr_wids": list(reference_dropped_karr),
        "dropped_oc_wids": list(reference_dropped_oc),
        "tick0_seed0_w1_over_intersection": float(tick0_seed0_w1),
    }
    return karr_matrix, oc_matrix, audit


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
        oc_obs_keys = {k[len("obs__") :] for k in data.files if k.startswith("obs__")}
        oc_summary_keys = {k[len("summary__") :] for k in data.files if k.startswith("summary__")}
        oc_keys = oc_obs_keys.union(oc_summary_keys)

    missing_karr_fields = sorted(set(_OBSERVABLES).difference(karr_keys))
    missing_oc_fields = sorted(set(_OBSERVABLES).difference(oc_keys))
    if missing_karr_fields:
        pytest.fail(f"Karr schema missing observables: {missing_karr_fields}")
    if missing_oc_fields:
        pytest.fail(f"OpenCell schema missing observables: {missing_oc_fields}")


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(",".join(columns) + "\n")
        for row in rows:
            fh.write(",".join(str(row.get(col, "")) for col in columns) + "\n")


def _build_sample_cube() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, Any]]:
    karr_samples: dict[str, np.ndarray] = {}
    oc_samples: dict[str, np.ndarray] = {}
    substrate_intersection_audit: dict[str, Any] = {}
    for observable in _OBSERVABLES:
        if observable == "substrates":
            karr_matrix, oc_matrix, substrate_intersection_audit = _build_substrates_intersection_samples()
            karr_samples[observable] = karr_matrix
            oc_samples[observable] = oc_matrix
            continue
        karr_matrix = np.zeros((len(_SEEDS), _N_TICKS), dtype=np.float64)
        oc_matrix = np.zeros((len(_SEEDS), _N_TICKS), dtype=np.float64)
        for i, seed in enumerate(_SEEDS):
            karr_series = _load_karr_observable(seed, observable)
            oc_series = _load_oc_observable(seed, observable)
            if karr_series.shape[0] != _N_TICKS:
                pytest.fail(
                    f"Karr n_ticks mismatch: seed={seed}, observable={observable}, "
                    f"got={karr_series.shape[0]}, expected={_N_TICKS}"
                )
            if oc_series.shape[0] != _N_TICKS:
                pytest.fail(
                    f"OpenCell n_ticks mismatch: seed={seed}, observable={observable}, "
                    f"got={oc_series.shape[0]}, expected={_N_TICKS}"
                )
            karr_matrix[i, :] = karr_series
            oc_matrix[i, :] = oc_series
        karr_samples[observable] = karr_matrix
        oc_samples[observable] = oc_matrix
    return karr_samples, oc_samples, substrate_intersection_audit


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


def _run_comparison() -> dict[str, Any]:
    _seed_coverage_check()
    oc_process_class = _oc_process_class_check()
    _schema_check()
    karr_samples, oc_samples, substrate_intersection_audit = _build_sample_cube()

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
        "process_name": "Translation",
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
        "substrates_intersection_audit": substrate_intersection_audit,
        "observable_rollup": observable_rollup,
        "ks_failures_path": _KS_FAILURES_PATH.as_posix(),
        "wasserstein_failures_path": _W1_FAILURES_PATH.as_posix(),
        "overall_pass": len(ks_failures) == 0 and len(w1_failures) == 0,
    }
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def test_l2_2_translation_distributional_fidelity() -> None:
    report = _run_comparison()
    assert report["overall_pass"], (
        "L2.2 Translation distributional mismatch. "
        f"ks_failure_count={report['ks_failure_count']}, "
        f"wasserstein_failure_count={report['wasserstein_failure_count']}, "
        f"report={_REPORT_PATH}"
    )
