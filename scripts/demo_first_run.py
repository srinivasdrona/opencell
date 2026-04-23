"""End-to-end first-run demo of the OpenCell hybrid coupled simulator.

Story we want the artifact to tell, in a single figure:

  1. External glucose (cglcex) is depleted by Chassagnole metabolism.
  2. The PTS uptake flux drops as glucose runs out, dragging the
     dimensionless coupling signal f_met from ~1 down toward 0.
  3. The Vilar gene network's 6 synthesis fluxes are scaled by f_met,
     so transcript / protein production throttles down with metabolism.
  4. Compared against the uncoupled baseline (deterministic Vilar with
     f_met identically 1), the coupled stochastic ensemble shows the
     gene network failing to start because metabolism starves it before
     the autoregulatory feedback can engage.

Run:
  python scripts/demo_first_run.py

Outputs (overwritten):
  artifacts/first_run_demo.png      multi-panel figure
  artifacts/first_run_demo.json     numerical summary

This is a demo, not a benchmark. Fixed base_seed=20260423 so the figure
is byte-stable between runs.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp

from opencell.models.coupled import SECONDS_PER_HOUR, CoupledMetabolismTranscription
from opencell.models.transcription import TranscriptionModel
from opencell.solvers.hybrid import hybrid_ensemble


ARTIFACT_DIR = Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)

T_END_HOURS = 8.0
T_END_SECONDS = T_END_HOURS * SECONDS_PER_HOUR
MACRO_DT_S = 60.0
N_REALISATIONS = 12
BASE_SEED = 20260423


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, timeout=2,
        )
        return out.stdout.strip()
    except Exception:
        return None


def _ensemble_stats(values: np.ndarray) -> dict:
    return {
        "mean": values.mean(axis=0),
        "p10": np.percentile(values, 10, axis=0),
        "p90": np.percentile(values, 90, axis=0),
        "final_mean": float(values[:, -1].mean()),
        "final_std": float(values[:, -1].std()),
    }


def _uncoupled_baseline(ts_h: np.ndarray) -> dict[str, np.ndarray]:
    """Deterministic Vilar reference: what the gene network would do if
    metabolism never throttled it (f_met == 1 always)."""
    gene = TranscriptionModel.load()
    sol = solve_ivp(
        gene.rhs, (0.0, ts_h[-1]), gene.initial_y,
        method="LSODA", t_eval=ts_h, atol=1e-3, rtol=1e-6, max_step=0.05,
    )
    if not sol.success:
        raise RuntimeError(f"baseline solve failed: {sol.message}")
    gidx = gene.species_index()
    return {s: sol.y[gidx[s]] for s in ("MA", "MR", "A", "R", "C")}


def main() -> None:
    print("Building coupled model (signal=uptake_flux)...")
    coupled = CoupledMetabolismTranscription.build(signal="uptake_flux")
    gidx = coupled.gene.species_index()
    midx = coupled.met.species_index()

    print(f"Running {N_REALISATIONS} hybrid realisations over {T_END_HOURS} h "
          f"(macro_dt={MACRO_DT_S}s, base_seed={BASE_SEED})...")
    wall_start = time.perf_counter()
    runs = hybrid_ensemble(
        coupled,
        t_end_s=T_END_SECONDS,
        macro_dt_s=MACRO_DT_S,
        n_realisations=N_REALISATIONS,
        base_seed=BASE_SEED,
    )
    wall_s = time.perf_counter() - wall_start
    print(f"Done in {wall_s:.2f}s wall ({wall_s / N_REALISATIONS:.2f}s per realisation)")

    ts_h = runs[0].ts / SECONDS_PER_HOUR
    cglcex = np.array([r.y_met[:, midx["cglcex"]] for r in runs])
    f_met = np.array([r.f_met_history for r in runs])
    series = {
        s: np.array([r.y_gene[:, gidx[s]] for r in runs])
        for s in ("MA", "MR", "A", "R", "C")
    }

    cglcex_stats = _ensemble_stats(cglcex)
    f_met_stats = _ensemble_stats(f_met)
    stats = {s: _ensemble_stats(v) for s, v in series.items()}

    print("Computing uncoupled (f_met=1) baseline for comparison...")
    baseline = _uncoupled_baseline(ts_h)

    f_mean = f_met_stats["mean"]
    below = np.where(f_mean < 0.5)[0]
    t_throttle_h = float(ts_h[below[0]]) if len(below) else None

    fig, axes = plt.subplots(3, 1, figsize=(10.0, 10.5), sharex=True)

    ax = axes[0]
    ax.plot(ts_h, cglcex_stats["mean"], color="tab:blue", lw=1.8,
            label="external glucose")
    ax.set_ylabel("glucose cglcex (mM)", color="tab:blue")
    ax.tick_params(axis="y", labelcolor="tab:blue")
    ax.set_ylim(bottom=0)
    ax2 = ax.twinx()
    ax2.plot(ts_h, f_met_stats["mean"], color="tab:red", lw=1.8, ls="--",
             label="f_met (PTS / PTS_init)")
    ax2.set_ylabel("f_met (dimensionless)", color="tab:red")
    ax2.tick_params(axis="y", labelcolor="tab:red")
    ax2.set_ylim(0, 1.05)
    if t_throttle_h is not None:
        ax.axvline(t_throttle_h, color="black", lw=0.8, ls=":", alpha=0.6)
        ax.text(t_throttle_h, ax.get_ylim()[1] * 0.95,
                f" f_met<0.5\n at t={t_throttle_h:.2f}h",
                fontsize=8, va="top")
    ax.set_title("Metabolism: glucose depletion drags the coupling signal toward zero")
    ax.grid(alpha=0.3)

    ax = axes[1]
    for s, color in [("MA", "tab:green"), ("MR", "tab:purple")]:
        st = stats[s]
        ax.plot(ts_h, st["mean"], color=color, lw=1.6,
                label=f"{s} coupled mean")
        ax.fill_between(ts_h, st["p10"], st["p90"], color=color, alpha=0.18)
        ax.plot(ts_h, baseline[s], color=color, lw=1.4, ls=":",
                label=f"{s} uncoupled (det.)")
    ax.set_ylabel("mRNA molecules / cell")
    ax.set_title(
        f"Vilar mRNA: {N_REALISATIONS} stochastic realisations vs "
        f"uncoupled deterministic baseline (dotted)"
    )
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    ax.set_ylim(bottom=0)

    ax = axes[2]
    for s, color in [("A", "tab:orange"), ("R", "tab:brown"), ("C", "tab:gray")]:
        st = stats[s]
        ax.plot(ts_h, st["mean"], color=color, lw=1.6,
                label=f"{s} coupled mean")
        ax.fill_between(ts_h, st["p10"], st["p90"], color=color, alpha=0.18)
        ax.plot(ts_h, baseline[s], color=color, lw=1.4, ls=":",
                label=f"{s} uncoupled (det.)")
    ax.set_xlabel("time (cellular hours)")
    ax.set_ylabel("protein molecules / cell  (symlog)")
    ax.set_yscale("symlog", linthresh=1.0)
    ax.set_title(
        "Vilar proteins: coupled cell barely accumulates the activator;"
        " uncoupled cell builds R into the hundreds"
    )
    ax.legend(loc="upper left", fontsize=8, ncol=3)
    ax.grid(alpha=0.3, which="both")

    fig.suptitle(
        "OpenCell first-run: coupled Chassagnole metabolism + Vilar gene network",
        fontsize=12,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    fig_path = ARTIFACT_DIR / "first_run_demo.png"
    fig.savefig(fig_path, dpi=130)
    plt.close(fig)
    print(f"Wrote {fig_path}")

    summary = {
        "config": {
            "t_end_hours": T_END_HOURS,
            "macro_dt_s": MACRO_DT_S,
            "n_realisations": N_REALISATIONS,
            "base_seed": BASE_SEED,
            "signal": coupled.signal,
        },
        "git_sha": _git_sha(),
        "wall_seconds_total": wall_s,
        "wall_seconds_per_realisation": wall_s / N_REALISATIONS,
        "tau_steps_per_realisation_mean": float(
            np.mean([r.n_tau_steps for r in runs])
        ),
        "f_met_initial": float(f_met_stats["mean"][0]),
        "f_met_final_mean": f_met_stats["final_mean"],
        "f_met_below_0p5_at_hours": t_throttle_h,
        "cglcex_initial_mM": float(cglcex_stats["mean"][0]),
        "cglcex_final_mean_mM": cglcex_stats["final_mean"],
        "coupled_final_mean": {s: stats[s]["final_mean"] for s in series},
        "coupled_final_std": {s: stats[s]["final_std"] for s in series},
        "uncoupled_final_baseline": {s: float(baseline[s][-1]) for s in series},
    }
    json_path = ARTIFACT_DIR / "first_run_demo.json"
    json_path.write_text(json.dumps(summary, indent=2, default=float))
    print(f"Wrote {json_path}")

    print("")
    print("Headline:")
    print(f"  f_met:          {summary['f_met_initial']:.3f}  ->  "
          f"{summary['f_met_final_mean']:.3f}")
    print(f"  glucose (mM):   {summary['cglcex_initial_mM']:.3f}  ->  "
          f"{summary['cglcex_final_mean_mM']:.3f}")
    print(f"  R coupled:      mean {summary['coupled_final_mean']['R']:.1f}  "
          f"vs uncoupled baseline {summary['uncoupled_final_baseline']['R']:.1f}")
    print(f"  A coupled:      mean {summary['coupled_final_mean']['A']:.1f}  "
          f"vs uncoupled baseline {summary['uncoupled_final_baseline']['A']:.1f}")


if __name__ == "__main__":
    main()
