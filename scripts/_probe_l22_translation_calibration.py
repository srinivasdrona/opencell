from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_DIR = REPO_ROOT / "tests" / "vivarium"
if str(HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(HELPER_DIR))

from l2_replay_common import load_fixture_channel_wids  # noqa: E402
from opencell.m3 import translation as tl  # noqa: E402

KARR_ENSEMBLE_ROOT = (
    REPO_ROOT / "data" / "m1_sources" / "karr_native" / "ensembles" / "translation"
)
N_SEEDS = 50
N_TICKS = 100
KNOWN_TIME_FACTORS = (60.0, 3600.0, 32400.0)


def _tick_cell(raw: object, tick: int) -> np.ndarray:
    arr = np.asarray(raw, dtype=object)
    flat = arr.reshape(-1)
    if tick >= flat.size:
        raise IndexError(f"tick {tick} out of range for cell array with size {flat.size}")
    return np.asarray(flat[tick], dtype=np.float64).reshape(-1)


def _all_tick_cells(raw: object) -> np.ndarray:
    arr = np.asarray(raw, dtype=object)
    flat = arr.reshape(-1)
    return np.stack([np.asarray(item, dtype=np.float64).reshape(-1) for item in flat], axis=0)


def _h5_tick_cell(handle: h5py.File, group: str, name: str, tick: int) -> np.ndarray:
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
        raise IndexError(f"tick {tick} out of range for {group}/{name} with shape={ds.shape}")
    return np.asarray(handle[ref][()], dtype=np.float64).reshape(-1)


def _h5_all_tick_cells(handle: h5py.File, group: str, name: str) -> np.ndarray:
    ds = handle[f"{group}/{name}"]
    n_ticks = max(int(ds.shape[0]), int(ds.shape[1]))
    return np.stack([_h5_tick_cell(handle, group, name, tick) for tick in range(n_ticks)], axis=0)


def _top_items(rate_map: dict[str, float], n: int = 5) -> list[tuple[str, float]]:
    return sorted(rate_map.items(), key=lambda item: (-item[1], item[0]))[:n]


def _fmt_table(rows: list[tuple[str, float, float, float]]) -> str:
    header = f"{'AA':<6} {'Karr_per_tick':>16} {'v1_per_tick':>16} {'Karr/v1':>12}"
    body = [
        f"{aa:<6} {karr:16.6f} {v1:16.6f} {ratio:12.6f}"
        for aa, karr, v1, ratio in rows
    ]
    return "\n".join([header, *body])


def load_karr_seed(seed: int) -> tuple[np.ndarray, np.ndarray]:
    path = KARR_ENSEMBLE_ROOT / f"seed_{seed:03d}" / "Translation_100ticks.mat"
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        mat = loadmat(path, squeeze_me=True, struct_as_record=False)
        states_before = mat["states_before"]
        states_after = mat["states_after"]
        before = _all_tick_cells(getattr(states_before, "substrates"))
        after = _all_tick_cells(getattr(states_after, "substrates"))
        return before, after
    except NotImplementedError:
        with h5py.File(path, "r") as handle:
            before = _h5_all_tick_cells(handle, "states_before", "substrates")
            after = _h5_all_tick_cells(handle, "states_after", "substrates")
        return before, after


def build_v1_report() -> dict[str, object]:
    model = tl.load_default()
    aa_rates = tl.aa_consumption_per_s(model)
    aa_only = {aa: float(aa_rates[aa]) for aa in model.aa_wcm_ids}
    total_aa_per_s = float(sum(aa_only.values()))
    total_synth_per_s = float(np.sum(model.synth_rate_per_s))
    return {
        "model": model,
        "aa_only": aa_only,
        "total_aa_per_s": total_aa_per_s,
        "total_synth_per_s": total_synth_per_s,
        "bulk_total_aa_per_s": float(aa_rates["_total_aa_per_s"]),
        "top5": _top_items(aa_only, n=5),
    }


def build_karr_report(v1_aa_order: tuple[str, ...]) -> dict[str, object]:
    karr_wids = tuple(str(x) for x in load_fixture_channel_wids("Translation", "substrates"))
    if not karr_wids:
        raise RuntimeError("Missing Translation substrate WIDs from fixture")
    intersection = tuple(aa for aa in v1_aa_order if aa in set(karr_wids))
    karr_idx = {wid: idx for idx, wid in enumerate(karr_wids)}

    per_seed_window_rates: list[np.ndarray] = []
    per_seed_mean_tick_rates: list[np.ndarray] = []
    for seed in range(N_SEEDS):
        before_ticks, after_ticks = load_karr_seed(seed)
        before0 = before_ticks[0, :]
        after99 = after_ticks[N_TICKS - 1, :]
        if before0.shape[0] != len(karr_wids) or after99.shape[0] != len(karr_wids):
            raise ValueError(
                f"seed {seed} width mismatch: before={before0.shape[0]} after={after99.shape[0]} "
                f"wids={len(karr_wids)}"
            )
        if before_ticks.shape != after_ticks.shape:
            raise ValueError(
                f"seed {seed} before/after shape mismatch: before={before_ticks.shape} after={after_ticks.shape}"
            )
        per_seed_window_rates.append(
            np.asarray(
                [
                    float(before0[karr_idx[aa]] - after99[karr_idx[aa]]) / float(N_TICKS)
                    for aa in intersection
                ],
                dtype=np.float64,
            )
        )
        per_seed_mean_tick_rates.append(
            np.asarray(
                [
                    float(np.mean(before_ticks[:, karr_idx[aa]] - after_ticks[:, karr_idx[aa]]))
                    for aa in intersection
                ],
                dtype=np.float64,
            )
        )

    per_seed_window = np.stack(per_seed_window_rates, axis=0)
    per_seed_mean_tick = np.stack(per_seed_mean_tick_rates, axis=0)
    mean_window_per_aa = per_seed_window.mean(axis=0)
    mean_tick_per_aa = per_seed_mean_tick.mean(axis=0)
    mean_window_total = float(mean_window_per_aa.sum())
    mean_tick_total = float(mean_tick_per_aa.sum())
    by_aa_window = {aa: float(mean_window_per_aa[i]) for i, aa in enumerate(intersection)}
    by_aa_tick = {aa: float(mean_tick_per_aa[i]) for i, aa in enumerate(intersection)}
    return {
        "karr_wids": karr_wids,
        "intersection": intersection,
        "per_seed_window": per_seed_window,
        "per_seed_mean_tick": per_seed_mean_tick,
        "mean_window_per_aa": mean_window_per_aa,
        "mean_tick_per_aa": mean_tick_per_aa,
        "mean_window_total_per_tick": mean_window_total,
        "mean_tick_total_per_tick": mean_tick_total,
        "by_aa_window": by_aa_window,
        "by_aa_tick": by_aa_tick,
        "top5_window": _top_items(by_aa_window, n=5),
        "top5_tick": _top_items(by_aa_tick, n=5),
    }


def build_comparison(
    v1_report: dict[str, object], karr_report: dict[str, object], by_aa_key: str, total_key: str
) -> dict[str, object]:
    v1_aa = v1_report["aa_only"]
    intersection = karr_report["intersection"]
    rows: list[tuple[str, float, float, float]] = []
    ratios: list[float] = []
    karr_vals: list[float] = []
    v1_vals: list[float] = []

    for aa in intersection:
        karr_rate = float(karr_report[by_aa_key][aa])
        v1_rate = float(v1_aa[aa])
        ratio = float(karr_rate / v1_rate) if v1_rate > 0 else float("inf")
        rows.append((aa, karr_rate, v1_rate, ratio))
        if np.isfinite(ratio):
            ratios.append(ratio)
        karr_vals.append(karr_rate)
        v1_vals.append(v1_rate)

    ratio_arr = np.asarray(ratios, dtype=np.float64)
    karr_arr = np.asarray(karr_vals, dtype=np.float64)
    v1_arr = np.asarray(v1_vals, dtype=np.float64)
    shape_corr = float(np.corrcoef(karr_arr, v1_arr)[0, 1])
    normalized_l1 = float(
        np.sum(
            np.abs(karr_arr / max(np.sum(karr_arr), 1e-12) - v1_arr / max(np.sum(v1_arr), 1e-12))
        )
    )
    nearest_time_factor = min(KNOWN_TIME_FACTORS, key=lambda x: abs(np.median(ratio_arr) - x))
    return {
        "rows": rows,
        "ratio_total": float(karr_report[total_key] / v1_report["total_aa_per_s"]),
        "ratio_stats": {
            "median": float(np.median(ratio_arr)),
            "mean": float(np.mean(ratio_arr)),
            "min": float(np.min(ratio_arr)),
            "max": float(np.max(ratio_arr)),
            "cv": float(np.std(ratio_arr) / max(np.mean(ratio_arr), 1e-12)),
        },
        "shape_corr": shape_corr,
        "normalized_l1": normalized_l1,
        "nearest_time_factor": float(nearest_time_factor),
        "nearest_time_factor_error": float(abs(np.median(ratio_arr) - nearest_time_factor)),
    }


def build_source_report() -> dict[str, object]:
    fixture_json = json.loads((REPO_ROOT / "data" / "karr_fixtures" / "karr_native_m3.json").read_text())
    return {
        "fixture_json": "data/karr_fixtures/karr_native_m3.json",
        "fixture_npz": fixture_json["matrix_npz"],
        "source_archive_files": fixture_json["source_archive_files"],
        "interpretation": fixture_json["interpretation"],
        "total_synth_rate_per_s_at_ss": fixture_json["scalars"]["total_synth_rate_per_s_at_ss"],
        "total_aa_polymerization_per_s_at_ss": fixture_json["scalars"][
            "total_aa_polymerization_per_s_at_ss"
        ],
        "ingest_script": "scripts/karr_native_ingest_m3.py",
    }


def print_report() -> None:
    v1 = build_v1_report()
    karr = build_karr_report(v1["model"].aa_wcm_ids)
    cmp_window = build_comparison(v1, karr, "by_aa_window", "mean_window_total_per_tick")
    cmp_tick = build_comparison(v1, karr, "by_aa_tick", "mean_tick_total_per_tick")
    src = build_source_report()

    print("=== L2.2 Translation Calibration Probe ===")
    print()
    print("v1 analytical rate (20 AA intersection / 1 s tick)")
    print(f"  total_aa_per_tick        = {v1['total_aa_per_s']:.12f}")
    print(f"  bulk_total_aa_per_s      = {v1['bulk_total_aa_per_s']:.12f}")
    print(f"  total_synth_per_s        = {v1['total_synth_per_s']:.12f}")
    print("  top5_aa_per_tick:")
    for aa, value in v1["top5"]:
        print(f"    {aa:<4} {value:.12f}")
    print()
    print("Karr ensemble mean net substrate depletion")
    print(f"  seeds                    = {N_SEEDS}")
    print(f"  prompt_window_rate       = {karr['mean_window_total_per_tick']:.12f}")
    print(f"  mean_within_tick_rate    = {karr['mean_tick_total_per_tick']:.12f}")
    print("  top5_aa_per_tick (within-tick mean):")
    for aa, value in karr["top5_tick"]:
        print(f"    {aa:<4} {value:.12f}")
    print()
    print("Top-5 by Karr within-tick rate with v1 comparison")
    top5_rows = []
    for aa, karr_rate in karr["top5_tick"]:
        v1_rate = float(v1["aa_only"][aa])
        top5_rows.append((aa, float(karr_rate), v1_rate, float(karr_rate / v1_rate)))
    print(_fmt_table(top5_rows))
    print()
    print("All-20 shape diagnostics (within-tick mean)")
    print(f"  total_ratio              = {cmp_tick['ratio_total']:.12f}")
    print(f"  per_aa_ratio_median      = {cmp_tick['ratio_stats']['median']:.12f}")
    print(f"  per_aa_ratio_mean        = {cmp_tick['ratio_stats']['mean']:.12f}")
    print(f"  per_aa_ratio_min         = {cmp_tick['ratio_stats']['min']:.12f}")
    print(f"  per_aa_ratio_max         = {cmp_tick['ratio_stats']['max']:.12f}")
    print(f"  per_aa_ratio_cv          = {cmp_tick['ratio_stats']['cv']:.12f}")
    print(f"  shape_correlation        = {cmp_tick['shape_corr']:.12f}")
    print(f"  normalized_shape_l1      = {cmp_tick['normalized_l1']:.12f}")
    print(
        "  nearest_known_time_factor"
        f" = {cmp_tick['nearest_time_factor']:.1f}"
        f" (abs_error={cmp_tick['nearest_time_factor_error']:.12f})"
    )
    print("  prompt_window_total_ratio"
          f" = {cmp_window['ratio_total']:.12f}")
    print()
    print("synth_rate_per_s provenance")
    print(f"  fixture_json             = {src['fixture_json']}")
    print(f"  fixture_npz              = {src['fixture_npz']}")
    print(f"  source_archive_files     = {src['source_archive_files']}")
    print(f"  ingest_script            = {src['ingest_script']}")
    print(f"  scalar_total_synth_at_ss = {src['total_synth_rate_per_s_at_ss']:.12f}")
    print(f"  scalar_total_aa_at_ss    = {src['total_aa_polymerization_per_s_at_ss']:.12f}")
    print(f"  interpretation           = {src['interpretation']}")


if __name__ == "__main__":
    print_report()
