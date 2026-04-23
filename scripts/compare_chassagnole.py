"""Side-by-side validation: OpenCell vs libroadrunner on Chassagnole 2002.

Produces three PNGs in artifacts/:
    chassagnole_opencell.png      — our trajectories alone
    chassagnole_roadrunner.png    — libroadrunner trajectories alone (oracle)
    chassagnole_overlay.png       — both overlaid + residual panel below

Visual proof that the libsbml+sympy translator in opencell.models.sbml_model
matches the de facto SBML simulator to within solver tolerance.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import roadrunner

from opencell.models.metabolism import MetabolismModel
from opencell.solvers.ode_scipy import ScipySolverConfig, solve_ode_scipy


T_END = 60.0
N_POINTS = 601
HIGHLIGHT = ["cglcex", "cg6p", "cf6p", "cfdp", "cgap", "cpep", "cpyr"]
COLORS = plt.cm.tab10.colors  # type: ignore[attr-defined]


def run_opencell(model: MetabolismModel, t_eval: np.ndarray) -> dict[str, np.ndarray]:
    res = solve_ode_scipy(
        model.rhs,
        model.initial_y,
        (0.0, T_END),
        config=ScipySolverConfig(method="LSODA", rtol=1e-9, atol=1e-12),
        t_eval=t_eval,
    )
    if not res.success:
        raise SystemExit(f"OpenCell integration failed: {res.message}")
    return {sid: res.ys[i] for i, sid in enumerate(model.species_ids)}


def run_roadrunner(sbml_path: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    rr = roadrunner.RoadRunner(str(sbml_path))
    rr.integrator.relative_tolerance = 1e-10
    rr.integrator.absolute_tolerance = 1e-12
    result = rr.simulate(0.0, T_END, N_POINTS)
    cols = result.colnames
    t = np.asarray(result[:, 0])
    out: dict[str, np.ndarray] = {}
    for col in cols[1:]:
        sid = col.strip("[]")
        j = cols.index(col)
        out[sid] = np.asarray(result[:, j])
    return t, out


def plot_one(
    title: str,
    out_path: Path,
    t: np.ndarray,
    series: dict[str, np.ndarray],
    sha_short: str,
) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for k, sid in enumerate(HIGHLIGHT):
        ax.plot(t, series[sid], color=COLORS[k], linewidth=1.6, label=sid)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("concentration (mM)")
    ax.set_title(f"{title}\nBIOMD0000000051 SHA-256 {sha_short}")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  wrote {out_path}")


def plot_overlay(
    out_path: Path,
    t: np.ndarray,
    ours: dict[str, np.ndarray],
    rr: dict[str, np.ndarray],
    sha_short: str,
) -> None:
    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, figsize=(10, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 2]},
    )
    for k, sid in enumerate(HIGHLIGHT):
        c = COLORS[k]
        ax_top.plot(t, rr[sid], color=c, linewidth=2.5, alpha=0.35, label=f"{sid} (RR)")
        ax_top.plot(t, ours[sid], color=c, linewidth=1.0, linestyle="--",
                    label=f"{sid} (OpenCell)")
    ax_top.set_ylabel("concentration (mM)")
    ax_top.set_title(
        f"OpenCell (dashed) vs libroadrunner (thick translucent) — Chassagnole 2002\n"
        f"BIOMD0000000051 SHA-256 {sha_short}"
    )
    ax_top.grid(alpha=0.3)
    ax_top.legend(loc="upper right", ncol=2, fontsize=7)

    # Relative residuals panel
    for k, sid in enumerate(HIGHLIGHT):
        denom = np.abs(rr[sid]) + 1e-9
        rel_err = np.abs(ours[sid] - rr[sid]) / denom
        ax_bot.semilogy(t, rel_err, color=COLORS[k], linewidth=1.2, label=sid)
    ax_bot.set_xlabel("time (s)")
    ax_bot.set_ylabel("|OpenCell - RR| / |RR|")
    ax_bot.set_title("Relative residual per species (log scale)")
    ax_bot.grid(alpha=0.3, which="both")
    ax_bot.axhline(1e-3, color="red", linestyle=":", linewidth=1, label="test rtol=1e-3")
    ax_bot.legend(loc="upper right", ncol=2, fontsize=7)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  wrote {out_path}")


def main() -> None:
    out_dir = Path("artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)

    model = MetabolismModel.load()
    sha_short = model.sbml.sbml_sha256[:12]

    t_eval = np.linspace(0.0, T_END, N_POINTS)
    print("Running OpenCell ...")
    ours = run_opencell(model, t_eval)
    print("Running libroadrunner ...")
    t_rr, rr_full = run_roadrunner(model.sbml.sbml_path)

    # Make sure both grids match (RR returns its own t array)
    assert np.allclose(t_eval, t_rr, atol=1e-9), "Time grids do not match"

    plot_one(
        "OpenCell (libsbml + sympy + LSODA)",
        out_dir / "chassagnole_opencell.png", t_eval, ours, sha_short,
    )
    plot_one(
        "libroadrunner (CVODE)",
        out_dir / "chassagnole_roadrunner.png", t_rr, rr_full, sha_short,
    )
    plot_overlay(out_dir / "chassagnole_overlay.png", t_eval, ours, rr_full, sha_short)

    # Numeric summary
    print("\nMax relative difference per species (across all 601 time points):")
    summary = {}
    for sid in HIGHLIGHT + [s for s in model.species_ids if s not in HIGHLIGHT]:
        denom = np.abs(rr_full[sid]) + 1e-12
        rel = np.abs(ours[sid] - rr_full[sid]) / denom
        max_rel = float(rel.max())
        summary[sid] = max_rel
        print(f"  {sid:10s}  max_rel_err = {max_rel:.3e}")

    print("\nSummary stats:")
    vals = np.array(list(summary.values()))
    print(f"  worst species: max_rel = {vals.max():.3e}")
    print(f"  median across species: max_rel = {np.median(vals):.3e}")
    print(f"  mean across species:   max_rel = {vals.mean():.3e}")

    (out_dir / "chassagnole_residuals.json").write_text(
        json.dumps(
            {
                "sbml_sha256": model.sbml.sbml_sha256,
                "biomodels_id": model.biomodels_id,
                "t_end_seconds": T_END,
                "n_points": N_POINTS,
                "max_rel_err_per_species": summary,
                "worst_species_max_rel": float(vals.max()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(f"\nwrote {out_dir / 'chassagnole_residuals.json'}")


if __name__ == "__main__":
    main()
