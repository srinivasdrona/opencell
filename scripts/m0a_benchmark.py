"""M0-A benchmark: persistent vs restart LSODA in a Vivarium engine.

Quantifies the speedup at multiple horizons and macro_dt values, and
extrapolates to the M0.5 Karr-scale workload to answer the user's
question: "is the runtime spike addressed?"

Outputs:
    artifacts/M0A_persistent_lsoda.json — full results
    artifacts/M0A_persistent_lsoda.png  — speedup plot

Usage:
    python scripts/m0a_benchmark.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from opencell.models.coupled import CoupledMetabolismTranscription
from opencell.solvers.hybrid import hybrid_run
from opencell.vivarium.composite import build_coupled_engine


def time_engine_run(coupled, t_end_s: float, macro_dt_s: float, persistent: bool, seed: int = 7) -> float:
    rng = np.random.default_rng(seed)
    engine = build_coupled_engine(
        coupled=coupled,
        macro_dt_s=macro_dt_s,
        rng=rng,
        persistent_metabolism=persistent,
    )
    t0 = time.perf_counter()
    engine.update(t_end_s)
    return time.perf_counter() - t0


def time_hybrid(coupled, t_end_s: float, macro_dt_s: float, seed: int = 7) -> float:
    t0 = time.perf_counter()
    hybrid_run(coupled, t_end_s, macro_dt_s, seed=seed)
    return time.perf_counter() - t0


def main() -> int:
    coupled = CoupledMetabolismTranscription.build(signal="uptake_flux")

    # Two horizons × multiple macro_dt to span the regime.
    configs = [
        (600.0, 10.0),
        (600.0, 60.0),
        (3600.0, 60.0),
        (3600.0, 120.0),
    ]

    results = []
    print(f"{'t_end':>7} {'macro_dt':>9} {'hybrid_s':>10} {'restart_s':>11} {'persist_s':>11} {'restart_x':>10} {'persist_x':>10} {'speedup':>9}")
    print("-" * 95)
    for t_end, macro_dt in configs:
        # Warm-up: hybrid first
        _ = time_hybrid(coupled, 60.0, 60.0)
        t_hybrid = time_hybrid(coupled, t_end, macro_dt)
        t_restart = time_engine_run(coupled, t_end, macro_dt, persistent=False)
        t_persist = time_engine_run(coupled, t_end, macro_dt, persistent=True)
        restart_overhead = t_restart / t_hybrid
        persist_overhead = t_persist / t_hybrid
        speedup = t_restart / t_persist
        results.append({
            "t_end_s": t_end,
            "macro_dt_s": macro_dt,
            "n_macro_steps": int(round(t_end / macro_dt)),
            "hybrid_wall_s": t_hybrid,
            "restart_wall_s": t_restart,
            "persistent_wall_s": t_persist,
            "restart_overhead_x": restart_overhead,
            "persistent_overhead_x": persist_overhead,
            "speedup_persist_vs_restart": speedup,
        })
        print(f"{t_end:>7.0f} {macro_dt:>9.0f} {t_hybrid:>10.3f} {t_restart:>11.3f} {t_persist:>11.3f} {restart_overhead:>9.2f}x {persist_overhead:>9.2f}x {speedup:>8.2f}x")

    # Extrapolate to Karr-scale ensemble (100 realisations × 8h sim)
    # Per M0.5: per-Process LSODA spin-up dominates.
    # Use the 3600s/60s data point as our scaling reference.
    ref = next(r for r in results if r["t_end_s"] == 3600.0 and r["macro_dt_s"] == 60.0)
    karr_8h = 8.0 * 3600.0 / 3600.0  # ratio to 1h run
    karr_single_persist_h = ref["persistent_wall_s"] * karr_8h / 3600.0
    karr_single_restart_h = ref["restart_wall_s"] * karr_8h / 3600.0
    karr_ensemble_persist_h = karr_single_persist_h * 100
    karr_ensemble_restart_h = karr_single_restart_h * 100
    extrap = {
        "ref_config": "1h horizon, 60s macro_dt",
        "karr_single_realisation_8h_persistent_h": karr_single_persist_h,
        "karr_single_realisation_8h_restart_h": karr_single_restart_h,
        "karr_ensemble_100_runs_persistent_h": karr_ensemble_persist_h,
        "karr_ensemble_100_runs_restart_h": karr_ensemble_restart_h,
        "comment": "Linear extrapolation; assumes spin-up cost is amortised. M0.5 found per-Process spin-up dominates; persistent path eliminates it.",
    }
    print("\n=== Extrapolation to Karr-scale (single metabolism Process) ===")
    print(f"  8h single realisation, restart    : {karr_single_restart_h:>6.2f} h")
    print(f"  8h single realisation, persistent : {karr_single_persist_h:>6.2f} h")
    print(f"  100-run ensemble, restart         : {karr_ensemble_restart_h:>6.1f} h ({karr_ensemble_restart_h/24:.1f} days)")
    print(f"  100-run ensemble, persistent      : {karr_ensemble_persist_h:>6.1f} h ({karr_ensemble_persist_h/24:.1f} days)")

    # Persist results
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    out_path = artifacts / "M0A_persistent_lsoda.json"
    out_path.write_text(json.dumps({
        "configs": results,
        "karr_extrapolation": extrap,
    }, indent=2))
    print(f"\nWrote {out_path}")

    # Plot if matplotlib is available
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        labels = [f"{int(r['t_end_s'])}s/{int(r['macro_dt_s'])}s" for r in results]
        x = np.arange(len(labels))
        rest = [r["restart_overhead_x"] for r in results]
        per = [r["persistent_overhead_x"] for r in results]
        fig, ax = plt.subplots(figsize=(8, 4.5))
        w = 0.35
        ax.bar(x - w/2, rest, w, label="restart (current)", color="tab:red", alpha=0.85)
        ax.bar(x + w/2, per, w, label="persistent (M0-A)", color="tab:green", alpha=0.85)
        ax.axhline(1.0, color="black", linestyle="--", alpha=0.5, label="hybrid baseline (1×)")
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_xlabel("horizon / macro_dt")
        ax.set_ylabel("Vivarium overhead (× hybrid_run wall time)")
        ax.set_title("M0-A: persistent LSODA collapses Vivarium overhead toward hybrid baseline")
        ax.set_yscale("log")
        ax.legend()
        ax.grid(axis="y", alpha=0.3, which="both")
        fig.tight_layout()
        png_path = artifacts / "M0A_persistent_lsoda.png"
        fig.savefig(png_path, dpi=120)
        print(f"Wrote {png_path}")
    except Exception as exc:
        print(f"(plot skipped: {exc})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
