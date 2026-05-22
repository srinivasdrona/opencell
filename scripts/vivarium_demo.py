"""Vivarium-hosted equivalent of scripts/demo_first_run.py.

Runs the same 8-hour, 12-realisation Chassagnole+Vilar coupled simulation
through a Vivarium ``Engine`` (three Processes: Metabolism, Signal,
GeneNetwork composed via shared ``signal`` store) instead of through
``hybrid_run``. Produces:

  artifacts/vivarium_demo.png           multi-panel figure (same layout)
  artifacts/vivarium_demo.json          numerical summary
  artifacts/vivarium_vs_hybrid_diff.json   key-quantity diff vs hybrid_run

This is the A1 acceptance artefact for Phase 4. The diff json is the
seed of A5 (multi-level diff tool) — it currently records only Level 4
(scalar phenotype-like quantities). Levels 1-3 (state mapping, invariants,
trajectory norms) are A5 scope.

Known semantics differences between this Engine and ``hybrid_run``,
documented in ``data/semantics/A6_semantics_contract.md``:

  * f_met lag: hybrid_run uses end-of-step f_met for the gene segment;
    Vivarium uses start-of-step f_met (one macro_dt_s lag).
  * Tau-leap RNG draws are identical in count and stoichiometry, but
    slightly different sequence due to f_met lag affecting propensities.
  * Metabolism trajectory is identical (one-way coupling, no feedback).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from opencell.models.coupled import SECONDS_PER_HOUR, CoupledMetabolismTranscription
from opencell.solvers.hybrid import hybrid_ensemble
from opencell.vivarium import build_coupled_engine

ARTIFACT_DIR = Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)

T_END_HOURS = 8.0
T_END_SECONDS = T_END_HOURS * SECONDS_PER_HOUR
MACRO_DT_S = 60.0
N_REALISATIONS = 12
BASE_SEED = 20260423


def _ensemble_stats(values: np.ndarray) -> dict:
    return {
        "mean": values.mean(axis=0),
        "p10": np.percentile(values, 10, axis=0),
        "p90": np.percentile(values, 90, axis=0),
        "final_mean": float(values[:, -1].mean()),
        "final_std": float(values[:, -1].std()),
    }


def _run_vivarium_ensemble(coupled, n: int, base_seed: int):
    """N independent Vivarium engines with spawned RNGs (same hygiene
    as ``hybrid_ensemble``). Returns a list of per-realisation timeseries
    dicts plus a list of wall times."""
    seq = np.random.SeedSequence(base_seed)
    children = seq.spawn(n)
    runs = []
    walls = []
    for child in children:
        rng = np.random.default_rng(child)
        eng = build_coupled_engine(
            coupled=coupled,
            macro_dt_s=MACRO_DT_S,
            rng=rng,
        )
        t0 = time.perf_counter()
        eng.update(T_END_SECONDS)
        walls.append(time.perf_counter() - t0)
        runs.append(eng.emitter.get_timeseries())
    return runs, walls


def _stack(runs, port_path):
    """Stack a per-run scalar timeseries into a (n_runs, n_t) array."""
    return np.array([_pluck(r, port_path) for r in runs])


def _pluck(timeseries: dict, path: tuple):
    node = timeseries
    for k in path:
        node = node[k]
    return np.asarray(node, dtype=np.float64)


def main() -> None:
    print("Building coupled model (signal=uptake_flux)...")
    coupled = CoupledMetabolismTranscription.build(signal="uptake_flux")
    gidx = coupled.gene.species_index()
    midx = coupled.met.species_index()

    # ---- Vivarium ensemble ------------------------------------------------
    print(
        f"Running {N_REALISATIONS} Vivarium realisations over {T_END_HOURS} h "
        f"(macro_dt={MACRO_DT_S}s, base_seed={BASE_SEED})..."
    )
    t_wall0 = time.perf_counter()
    viv_runs, viv_walls = _run_vivarium_ensemble(coupled, N_REALISATIONS, BASE_SEED)
    viv_total = time.perf_counter() - t_wall0
    print(f"Done in {viv_total:.2f}s wall ({viv_total / N_REALISATIONS:.2f}s per realisation)")

    ts_s = np.asarray(viv_runs[0]["time"], dtype=np.float64)
    ts_h = ts_s / SECONDS_PER_HOUR

    cglcex_v = _stack(viv_runs, ("metabolites", "cglcex"))
    f_met_v = _stack(viv_runs, ("signal", "f_met"))
    series_v = {s: _stack(viv_runs, ("gene_state", s)) for s in ("MA", "MR", "A", "R", "C")}

    cg_stats_v = _ensemble_stats(cglcex_v)
    fm_stats_v = _ensemble_stats(f_met_v)
    stats_v = {s: _ensemble_stats(v) for s, v in series_v.items()}

    # ---- hybrid_run reference --------------------------------------------
    print(f"Running {N_REALISATIONS} hybrid_run realisations for diff...")
    t_wall0 = time.perf_counter()
    hyb_runs = hybrid_ensemble(
        coupled,
        t_end_s=T_END_SECONDS,
        macro_dt_s=MACRO_DT_S,
        n_realisations=N_REALISATIONS,
        base_seed=BASE_SEED,
    )
    hyb_total = time.perf_counter() - t_wall0
    print(f"Done in {hyb_total:.2f}s wall ({hyb_total / N_REALISATIONS:.2f}s per realisation)")

    cglcex_h = np.array([r.y_met[:, midx["cglcex"]] for r in hyb_runs])
    f_met_h = np.array([r.f_met_history for r in hyb_runs])
    series_h = {
        s: np.array([r.y_gene[:, gidx[s]] for r in hyb_runs]) for s in ("MA", "MR", "A", "R", "C")
    }
    cg_stats_h = _ensemble_stats(cglcex_h)
    fm_stats_h = _ensemble_stats(f_met_h)
    stats_h = {s: _ensemble_stats(v) for s, v in series_h.items()}

    # ---- Figure -----------------------------------------------------------
    f_mean = fm_stats_v["mean"]
    below = np.where(f_mean < 0.5)[0]
    t_throttle_h = float(ts_h[below[0]]) if len(below) else None

    fig, axes = plt.subplots(3, 1, figsize=(10.0, 10.5), sharex=True)

    ax = axes[0]
    ax.plot(ts_h, cg_stats_v["mean"], color="tab:blue", lw=1.8, label="external glucose (vivarium)")
    ax.plot(
        ts_h,
        cg_stats_h["mean"],
        color="tab:blue",
        lw=1.0,
        ls=":",
        alpha=0.7,
        label="hybrid_run reference",
    )
    ax.set_ylabel("glucose cglcex (mM)", color="tab:blue")
    ax.tick_params(axis="y", labelcolor="tab:blue")
    ax.set_ylim(bottom=0)
    ax2 = ax.twinx()
    ax2.plot(ts_h, fm_stats_v["mean"], color="tab:red", lw=1.8, ls="--", label="f_met (vivarium)")
    ax2.plot(
        ts_h,
        fm_stats_h["mean"],
        color="tab:red",
        lw=1.0,
        ls=":",
        alpha=0.7,
        label="f_met (hybrid_run)",
    )
    ax2.set_ylabel("f_met (dimensionless)", color="tab:red")
    ax2.tick_params(axis="y", labelcolor="tab:red")
    ax2.set_ylim(0, 1.05)
    if t_throttle_h is not None:
        ax.axvline(t_throttle_h, color="black", lw=0.8, ls=":", alpha=0.6)
    ax.set_title(
        "Metabolism through Vivarium engine (solid) vs hybrid_run (dotted) — should overlap exactly"
    )
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)

    ax = axes[1]
    for s, color in [("MA", "tab:green"), ("MR", "tab:purple")]:
        st_v = stats_v[s]
        ax.plot(ts_h, st_v["mean"], color=color, lw=1.6, label=f"{s} vivarium mean")
        ax.fill_between(ts_h, st_v["p10"], st_v["p90"], color=color, alpha=0.15)
        ax.plot(
            ts_h,
            stats_h[s]["mean"],
            color=color,
            lw=1.0,
            ls=":",
            alpha=0.7,
            label=f"{s} hybrid_run mean",
        )
    ax.set_ylabel("mRNA molecules / cell")
    ax.set_title(
        f"Vilar mRNA: vivarium ensemble (n={N_REALISATIONS}) vs hybrid_run "
        f"(small differences expected — see f_met-lag note)"
    )
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    ax.set_ylim(bottom=0)

    ax = axes[2]
    for s, color in [("A", "tab:orange"), ("R", "tab:brown"), ("C", "tab:gray")]:
        st_v = stats_v[s]
        ax.plot(ts_h, st_v["mean"], color=color, lw=1.6, label=f"{s} vivarium mean")
        ax.fill_between(ts_h, st_v["p10"], st_v["p90"], color=color, alpha=0.15)
        ax.plot(
            ts_h,
            stats_h[s]["mean"],
            color=color,
            lw=1.0,
            ls=":",
            alpha=0.7,
            label=f"{s} hybrid_run mean",
        )
    ax.set_xlabel("time (cellular hours)")
    ax.set_ylabel("protein molecules / cell  (symlog)")
    ax.set_yscale("symlog", linthresh=1.0)
    ax.set_title("Vilar proteins: vivarium vs hybrid_run")
    ax.legend(loc="upper left", fontsize=8, ncol=3)
    ax.grid(alpha=0.3, which="both")

    fig.suptitle(
        "OpenCell Phase-4 A1 spike: same coupled cell hosted by Vivarium-core",
        fontsize=12,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    fig_path = ARTIFACT_DIR / "vivarium_demo.png"
    fig.savefig(fig_path, dpi=130)
    plt.close(fig)
    print(f"Wrote {fig_path}")

    # ---- JSON summary -----------------------------------------------------
    summary = {
        "config": {
            "t_end_hours": T_END_HOURS,
            "macro_dt_s": MACRO_DT_S,
            "n_realisations": N_REALISATIONS,
            "base_seed": BASE_SEED,
            "signal": coupled.signal,
            "engine": "vivarium-core",
        },
        "wall_seconds_total": viv_total,
        "wall_seconds_per_realisation": viv_total / N_REALISATIONS,
        "hybrid_wall_seconds_total": hyb_total,
        "hybrid_wall_seconds_per_realisation": hyb_total / N_REALISATIONS,
        "vivarium_overhead_ratio": viv_total / hyb_total if hyb_total else None,
        "f_met_initial": float(fm_stats_v["mean"][0]),
        "f_met_final_mean": fm_stats_v["final_mean"],
        "f_met_below_0p5_at_hours": t_throttle_h,
        "cglcex_initial_mM": float(cg_stats_v["mean"][0]),
        "cglcex_final_mean_mM": cg_stats_v["final_mean"],
        "coupled_final_mean": {s: stats_v[s]["final_mean"] for s in series_v},
        "coupled_final_std": {s: stats_v[s]["final_std"] for s in series_v},
    }
    json_path = ARTIFACT_DIR / "vivarium_demo.json"
    json_path.write_text(json.dumps(summary, indent=2, default=float))
    print(f"Wrote {json_path}")

    # ---- Diff vs hybrid_run (Level-4 only; A5 will extend) ---------------
    def _scalar_diff(a, b):
        return {
            "vivarium": float(a),
            "hybrid_run": float(b),
            "abs_diff": float(abs(a - b)),
            "rel_diff": float(abs(a - b) / max(abs(b), 1e-12)),
        }

    diff = {
        "metabolism_should_match_exactly": {
            "cglcex_final": _scalar_diff(cg_stats_v["final_mean"], cg_stats_h["final_mean"]),
            "f_met_final": _scalar_diff(fm_stats_v["final_mean"], fm_stats_h["final_mean"]),
            "max_abs_cglcex_diff_over_traj": float(
                np.max(np.abs(cg_stats_v["mean"] - cg_stats_h["mean"]))
            ),
        },
        "gene_expected_close_not_identical": {
            s: _scalar_diff(stats_v[s]["final_mean"], stats_h[s]["final_mean"]) for s in series_v
        },
        "notes": [
            "Metabolism trajectory must agree to LSODA tolerance (one-way coupling).",
            "Gene quantities will differ slightly: vivarium has 1-step f_met lag.",
            "If gene final-mean rel_diff is > ~0.5 for low counts, investigate.",
            "Wall-time 'vivarium_overhead_ratio' tracked under A8 perf budget.",
        ],
    }
    diff_path = ARTIFACT_DIR / "vivarium_vs_hybrid_diff.json"
    diff_path.write_text(json.dumps(diff, indent=2, default=float))
    print(f"Wrote {diff_path}")

    print("")
    print("Headline:")
    print(f"  Vivarium wall:  {viv_total:.2f}s ({viv_total / N_REALISATIONS:.2f}s/run)")
    print(f"  hybrid_run wall:{hyb_total:.2f}s ({hyb_total / N_REALISATIONS:.2f}s/run)")
    print(f"  Overhead ratio: {viv_total / hyb_total:.2f}x")
    print(
        f"  cglcex final:   vivarium={cg_stats_v['final_mean']:.4f}  "
        f"hybrid={cg_stats_h['final_mean']:.4f}"
    )
    print(
        f"  f_met final:    vivarium={fm_stats_v['final_mean']:.4f}  "
        f"hybrid={fm_stats_h['final_mean']:.4f}"
    )
    print(
        f"  R final:        vivarium={stats_v['R']['final_mean']:.1f}  "
        f"hybrid={stats_h['R']['final_mean']:.1f}"
    )


if __name__ == "__main__":
    main()
