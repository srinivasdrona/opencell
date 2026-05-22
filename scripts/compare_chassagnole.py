"""Side-by-side validation: OpenCell vs libroadrunner on Chassagnole 2002.

Produces three PNGs in artifacts/ (suffixed with the simulated duration):
    chassagnole_opencell_{secs}s.png   — our trajectories alone
    chassagnole_roadrunner_{secs}s.png — libroadrunner trajectories alone (oracle)
    chassagnole_overlay_{secs}s.png    — both overlaid + residual panel below
    chassagnole_residuals_{secs}s.json — per-species max relative error

Visual proof that the libsbml+sympy translator in opencell.models.sbml_model
matches the de facto SBML simulator to within solver tolerance.

Usage:
    python scripts/compare_chassagnole.py [--seconds 60] [--points 601]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import roadrunner

from opencell.models.metabolism import MetabolismModel
from opencell.solvers.ode_scipy import ScipySolverConfig, solve_ode_scipy

HIGHLIGHT = ["cglcex", "cg6p", "cf6p", "cfdp", "cgap", "cpep", "cpyr"]
COLORS = plt.cm.tab10.colors  # type: ignore[attr-defined]


def run_opencell(model: MetabolismModel, t_eval: np.ndarray, t_end: float) -> dict[str, np.ndarray]:
    res = solve_ode_scipy(
        model.rhs,
        model.initial_y,
        (0.0, t_end),
        config=ScipySolverConfig(method="LSODA", rtol=1e-9, atol=1e-12),
        t_eval=t_eval,
    )
    if not res.success:
        raise SystemExit(f"OpenCell integration failed: {res.message}")
    print(f"  OpenCell: {res.n_rhs_evals} RHS evaluations")
    return {sid: res.ys[i] for i, sid in enumerate(model.species_ids)}


def run_roadrunner(
    sbml_path: Path, t_end: float, n_points: int
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    rr = roadrunner.RoadRunner(str(sbml_path))
    rr.integrator.relative_tolerance = 1e-10
    rr.integrator.absolute_tolerance = 1e-12
    result = rr.simulate(0.0, t_end, n_points)
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
    duration_label: str,
) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for k, sid in enumerate(HIGHLIGHT):
        ax.plot(t, series[sid], color=COLORS[k], linewidth=1.6, label=sid)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("concentration (mM)")
    ax.set_title(f"{title} — {duration_label} simulation\nBIOMD0000000051 SHA-256 {sha_short}")
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
    duration_label: str,
) -> None:
    fig, (ax_top, ax_bot) = plt.subplots(
        2,
        1,
        figsize=(10, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 2]},
    )
    for k, sid in enumerate(HIGHLIGHT):
        c = COLORS[k]
        ax_top.plot(t, rr[sid], color=c, linewidth=2.5, alpha=0.35, label=f"{sid} (RR)")
        ax_top.plot(t, ours[sid], color=c, linewidth=1.0, linestyle="--", label=f"{sid} (OpenCell)")
    ax_top.set_ylabel("concentration (mM)")
    ax_top.set_title(
        f"OpenCell (dashed) vs libroadrunner (thick translucent) — Chassagnole 2002 "
        f"— {duration_label} simulation\n"
        f"BIOMD0000000051 SHA-256 {sha_short}"
    )
    ax_top.grid(alpha=0.3)
    ax_top.legend(loc="upper right", ncol=2, fontsize=7)

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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=60.0, help="Simulated end time in seconds")
    parser.add_argument(
        "--points",
        type=int,
        default=None,
        help="Number of output time points (default: 10*seconds + 1)",
    )
    args = parser.parse_args()

    t_end = float(args.seconds)
    n_points = int(args.points) if args.points else int(10 * t_end) + 1
    secs_label = f"{int(t_end)}s"
    duration_label = f"{int(t_end)} s ({t_end / 60:.1f} min)"

    out_dir = Path("artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)

    model = MetabolismModel.load()
    sha_short = model.sbml.sbml_sha256[:12]
    t_eval = np.linspace(0.0, t_end, n_points)

    print(f"Running OpenCell ({duration_label}, {n_points} points) ...")
    ours = run_opencell(model, t_eval, t_end)
    print(f"Running libroadrunner ({duration_label}, {n_points} points) ...")
    t_rr, rr_full = run_roadrunner(model.sbml.sbml_path, t_end, n_points)

    assert np.allclose(t_eval, t_rr, atol=1e-9), "Time grids do not match"

    plot_one(
        "OpenCell (libsbml + sympy + LSODA)",
        out_dir / f"chassagnole_opencell_{secs_label}.png",
        t_eval,
        ours,
        sha_short,
        duration_label,
    )
    plot_one(
        "libroadrunner (CVODE)",
        out_dir / f"chassagnole_roadrunner_{secs_label}.png",
        t_rr,
        rr_full,
        sha_short,
        duration_label,
    )
    plot_overlay(
        out_dir / f"chassagnole_overlay_{secs_label}.png",
        t_eval,
        ours,
        rr_full,
        sha_short,
        duration_label,
    )

    print("\nMax relative difference per species:")
    summary: dict[str, float] = {}
    for sid in HIGHLIGHT + [s for s in model.species_ids if s not in HIGHLIGHT]:
        denom = np.abs(rr_full[sid]) + 1e-12
        rel = np.abs(ours[sid] - rr_full[sid]) / denom
        max_rel = float(rel.max())
        summary[sid] = max_rel
        print(f"  {sid:10s}  max_rel_err = {max_rel:.3e}")

    vals = np.array(list(summary.values()))
    print("\nSummary stats:")
    print(f"  worst species:  max_rel = {vals.max():.3e}")
    print(f"  median species: max_rel = {np.median(vals):.3e}")
    print(f"  mean species:   max_rel = {vals.mean():.3e}")

    json_path = out_dir / f"chassagnole_residuals_{secs_label}.json"
    json_path.write_text(
        json.dumps(
            {
                "sbml_sha256": model.sbml.sbml_sha256,
                "biomodels_id": model.biomodels_id,
                "t_end_seconds": t_end,
                "n_points": n_points,
                "max_rel_err_per_species": summary,
                "worst_species_max_rel": float(vals.max()),
                "median_species_max_rel": float(np.median(vals)),
                "mean_species_max_rel": float(vals.mean()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(f"\nwrote {json_path}")


if __name__ == "__main__":
    main()
