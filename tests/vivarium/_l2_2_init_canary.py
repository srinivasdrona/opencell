"""L2.2 Translation init-parity canary (single seed).

Goal: measure how much of the v1 cold-start drift is attributable to
state-initialization mismatch vs intrinsic dynamics drift.

For seed_000 only, run v1 KarrTranslationProcess three ways and compare
per-tick aggregate (np.sum) per observable against Karr seed_000:

  * KARR        — ground truth (states_after from MAT)
  * OC_COLD     — current build_state_template defaults (already on disk)
  * OC_FITTED   — inject states_before[tick=0] from MAT for substrates,
                  enzymes, boundEnzymes (monomers already fitted via
                  counts_mature default).

Report per-tick (0, 1, 5, 25, 50, 75, 100) absolute totals + abs-diff
table. Three takeaways we want:

  1. tick-0 OC_FITTED vs Karr: should be ~0 (sanity check).
  2. tick-100 OC_FITTED vs Karr: residual dynamics gap.
  3. tick-100 OC_COLD vs Karr minus OC_FITTED vs Karr: contribution of
     init alone.

Run from worktree root via:
  bin/oc-py.cmd tests/vivarium/_l2_2_init_canary.py --seed 0
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import h5py
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import (  # noqa: E402
    build_state_template,
    project_observable_from_state,
    refresh_allocator_views,
)
from opencell.vivarium.karr_translation import KarrTranslationProcess  # noqa: E402

_KARR_ROOT = Path(
    "/mnt/e/opencell-worktrees/l22-translation/data/m1_sources/karr_native/ensembles/translation"
)

OBSERVABLES = ("substrates", "enzymes", "boundEnzymes", "monomers")
TICK_SAMPLES = (0, 1, 5, 25, 50, 75, 99)
N_TICKS = 100


def _mat_cell_vector(handle: h5py.File, group: str, name: str, tick: int) -> np.ndarray:
    ds = handle[f"{group}/{name}"]
    rows, cols = int(ds.shape[0]), int(ds.shape[1])
    if rows == 1 and cols >= (tick + 1):
        ref = ds[0, tick]
    elif cols == 1 and rows >= (tick + 1):
        ref = ds[tick, 0]
    else:
        raise IndexError(f"Tick {tick} out of range for {group}/{name} shape={ds.shape}")
    return np.asarray(handle[ref][()], dtype=np.float64).reshape(-1)


def _load_karr_trajectory(seed: int) -> dict[str, np.ndarray]:
    """Return dict obs -> [N_TICKS, n_wid] from states_after."""
    out: dict[str, np.ndarray] = {}
    path = _KARR_ROOT / f"seed_{seed:03d}" / "Translation_100ticks.mat"
    with h5py.File(path, "r") as handle:
        for obs in OBSERVABLES:
            rows: list[np.ndarray] = []
            for t in range(N_TICKS):
                rows.append(_mat_cell_vector(handle, "states_after", obs, t))
            out[obs] = np.vstack(rows)
    return out


def _load_karr_tick0_before(seed: int) -> dict[str, np.ndarray]:
    """Return dict obs -> length-n_wid vector from states_before tick 0."""
    out: dict[str, np.ndarray] = {}
    path = _KARR_ROOT / f"seed_{seed:03d}" / "Translation_100ticks.mat"
    with h5py.File(path, "r") as handle:
        for obs in OBSERVABLES:
            out[obs] = _mat_cell_vector(handle, "states_before", obs, 0)
    return out


def _observable_wids(process: KarrTranslationProcess) -> dict[str, list[str]]:
    sub_wids = list(getattr(process, "allocation_substrate_wids", ()))
    if not sub_wids:
        sub_wids = list(getattr(process, "aa_ids", ()))
    return {
        "substrates": sub_wids[:20],
        "enzymes": list(process.enzyme_wids),
        "boundEnzymes": list(process.enzyme_wids),
        "monomers": list(process.protein_ids),
    }


def _set_dict_from_vector(target: dict, wids: list[str], vector: np.ndarray) -> None:
    if len(wids) != len(vector):
        raise ValueError(f"len mismatch: wids={len(wids)} vec={len(vector)}")
    for w, v in zip(wids, vector):
        target[w] = float(v)


def _inject_fitted_state(state: dict, wids: dict, fitted: dict) -> None:
    """Inject Karr tick-0 fitted state into the state template.

    substrates, enzymes, boundEnzymes only — monomers (protein.counts) is
    already initialized from counts_mature in the v1 schema default.
    """
    for obs in ("substrates", "enzymes", "boundEnzymes"):
        karr_vec = fitted[obs]
        oc_wids = wids[obs]
        if len(karr_vec) != len(oc_wids):
            print(
                f"[canary] SKIP injection {obs}: oc_wids={len(oc_wids)} "
                f"karr={len(karr_vec)} — WID-width mismatch (out of scope for canary).",
                flush=True,
            )
            continue
        _set_dict_from_vector(state[obs], oc_wids, karr_vec)


def _apply_translation_v1_update(state: dict, update: dict) -> None:
    """Mirror runner's protein.counts 'set' updater handling."""
    protein_update = update.get("protein", {})
    if isinstance(protein_update, dict):
        counts_update = protein_update.get("counts")
        if isinstance(counts_update, dict):
            protein_state = state.setdefault("protein", {})
            counts_state = protein_state.setdefault("counts", {})
            for wid, val in counts_update.items():
                counts_state[str(wid)] = float(val)
    # accumulate substrates etc.
    sub_update = update.get("substrates")
    if isinstance(sub_update, dict):
        for wid, delta in sub_update.items():
            state.setdefault("substrates", {})[wid] = float(
                state.get("substrates", {}).get(wid, 0.0)
            ) + float(delta)


def _run_oc_trajectory(seed: int, fitted_init: bool) -> dict[str, np.ndarray]:
    """Run v1 process for N_TICKS, return obs -> [N_TICKS, n_wid] (states_after)."""
    process = KarrTranslationProcess({"rng_seed": int(seed)})
    state = build_state_template(process)
    wids = _observable_wids(process)

    if fitted_init:
        fitted = _load_karr_tick0_before(seed)
        _inject_fitted_state(state, wids, fitted)

    trajectories = {obs: np.zeros((N_TICKS, len(wids[obs]))) for obs in OBSERVABLES}

    for tick in range(N_TICKS):
        refresh_allocator_views(process, state)
        update = process.next_update(1.0, state)
        _apply_translation_v1_update(state, update)
        for obs in OBSERVABLES:
            vec = project_observable_from_state(
                process=process,
                state=state,
                observable=obs,
                wids=wids[obs],
                bound_enzymes_before=None,
            )
            trajectories[obs][tick, :] = np.asarray(vec, dtype=np.float64)
    return trajectories


def _summary_table(
    karr: dict[str, np.ndarray],
    oc_cold: dict[str, np.ndarray],
    oc_fitted: dict[str, np.ndarray],
) -> list[dict]:
    """Per-observable, per-sampled-tick: sums + abs(sum-diff) + max-abs elementwise diff."""
    rows: list[dict] = []
    for obs in OBSERVABLES:
        K = karr[obs]
        C = oc_cold[obs]
        F = oc_fitted[obs]
        # align widths if v1 returned different length than Karr
        n = min(K.shape[1], C.shape[1], F.shape[1])
        width_note = ""
        if K.shape[1] != C.shape[1]:
            width_note = f" [width mismatch K={K.shape[1]} OC={C.shape[1]}; truncated to {n}]"
        for tick in TICK_SAMPLES:
            k_sum = float(K[tick, :n].sum())
            c_sum = float(C[tick, :n].sum())
            f_sum = float(F[tick, :n].sum())
            max_c = float(np.max(np.abs(C[tick, :n] - K[tick, :n])))
            max_f = float(np.max(np.abs(F[tick, :n] - K[tick, :n])))
            rows.append({
                "observable": obs,
                "tick": tick,
                "karr_sum": k_sum,
                "cold_sum": c_sum,
                "fitted_sum": f_sum,
                "cold_sum_absdiff": abs(c_sum - k_sum),
                "fitted_sum_absdiff": abs(f_sum - k_sum),
                "cold_max_elem_absdiff": max_c,
                "fitted_max_elem_absdiff": max_f,
                "init_contribution_sum": abs(c_sum - k_sum) - abs(f_sum - k_sum),
            })
    return rows


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=Path("data") / "init_canary" / "translation_seed000.json")
    args = parser.parse_args(argv)

    print(f"[canary] seed={args.seed}", flush=True)
    print("[canary] loading Karr trajectory...", flush=True)
    karr = _load_karr_trajectory(args.seed)
    for obs, arr in karr.items():
        print(f"  karr.{obs}: shape={arr.shape}", flush=True)

    print("[canary] running OC cold...", flush=True)
    oc_cold = _run_oc_trajectory(args.seed, fitted_init=False)
    for obs, arr in oc_cold.items():
        print(f"  oc_cold.{obs}: shape={arr.shape}", flush=True)

    print("[canary] running OC fitted-init...", flush=True)
    oc_fitted = _run_oc_trajectory(args.seed, fitted_init=True)
    for obs, arr in oc_fitted.items():
        print(f"  oc_fitted.{obs}: shape={arr.shape}", flush=True)

    print("[canary] building summary table...", flush=True)
    rows = _summary_table(karr, oc_cold, oc_fitted)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seed": args.seed,
        "n_ticks": N_TICKS,
        "tick_samples": list(TICK_SAMPLES),
        "observables": list(OBSERVABLES),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "rows": rows,
    }
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[canary] wrote {args.out}", flush=True)

    # Pretty print
    print()
    print(f"{'observable':<14} {'tick':>4} {'karr_sum':>14} {'cold_sum':>14} {'fitted_sum':>14}"
          f" {'|cold-K|':>12} {'|fit-K|':>12} {'init_contrib':>14}")
    for r in rows:
        print(f"{r['observable']:<14} {r['tick']:>4d}"
              f" {r['karr_sum']:>14.3e} {r['cold_sum']:>14.3e} {r['fitted_sum']:>14.3e}"
              f" {r['cold_sum_absdiff']:>12.3e} {r['fitted_sum_absdiff']:>12.3e}"
              f" {r['init_contribution_sum']:>14.3e}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
