"""Side-by-side validation: OpenCell vs libroadrunner on Vilar 2002.

Produces three PNGs in artifacts/ (suffixed with the simulated duration):
    vilar_opencell_{tu}tu.png    — our trajectories alone
    vilar_roadrunner_{tu}tu.png  — libroadrunner trajectories (oracle)
    vilar_overlay_{tu}tu.png     — both overlaid + residual panel below
    vilar_residuals_{tu}tu.json  — per-species max relative error

Visual proof that the libsbml+sympy translator in opencell.models.sbml_model
matches the de facto SBML simulator on a count-based gene-expression model
(all species hasOnlySubstanceUnits=true) over multiple oscillation periods.

Usage:
    python scripts/compare_vilar.py [--time-units 200] [--points 2001]

Time units are dimensionless in the Vilar SBML (interpreted as hours per
the source paper). Default 200 covers ~3 limit-cycle periods.
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

from opencell.models.transcription import TranscriptionModel
from opencell.solvers.ode_scipy import ScipySolverConfig, solve_ode_scipy


# Highlight the proteins + repressor mRNA — these carry the oscillation signal.
HIGHLIGHT = ["A", "R", "C", "MA", "MR"]
COLORS = plt.cm.tab10.colors  # type: ignore[attr-defined]


def run_opencell(
    model: TranscriptionModel, t_eval: np.ndarray, t_end: float
) -> dict[str, np.ndarray]:
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
    sbml_path: Path, species_ids: list[str], t_end: float, n_points: int
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    rr = roadrunner.RoadRunner(str(sbml_path))
    rr.integrator.relative_tolerance = 1e-10
    rr.integrator.absolute_tolerance = 1e-12
    # Request amounts (Vilar's species are hasOnlySubstanceUnits=true).
    rr.selections = ["time"] + species_ids
    result = rr.simulate(0.0, t_end, n_points)
    cols = result.colnames
    t = np.asarray(result[:, 0])
    out: dict[str, np.ndarray] = {}
    for sid in species_ids:
        j = cols.index(sid)
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
    ax.set_xlabel("time (h)")
    ax.set_ylabel("molecule count")
    ax.set_title(
        f"{title} — {duration_label} simulation\n"
        f"BIOMD0000000035 SHA-256 {sha_short}"
    )
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
        2, 1, figsize=(10, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 2]},
    )
    for k, sid in enumerate(HIGHLIGHT):
        c = COLORS[k]
        ax_top.plot(t, rr[sid], color=c, linewidth=2.5, alpha=0.35, label=f"{sid} (RR)")
        ax_top.plot(t, ours[sid], color=c, linewidth=1.0, linestyle="--",
                    label=f"{sid} (OpenCell)")
    ax_top.set_ylabel("molecule count")
    ax_top.set_title(
        f"OpenCell (dashed) vs libroadrunner (thick translucent) — Vilar 2002 "
        f"— {duration_label} simulation\n"
        f"BIOMD0000000035 SHA-256 {sha_short}"
    )
    ax_top.grid(alpha=0.3)
    ax_top.legend(loc="upper right", ncol=2, fontsize=7)

    for k, sid in enumerate(HIGHLIGHT):
        denom = np.abs(rr[sid]) + 1e-3  # absolute floor for low-count species
        rel_err = np.abs(ours[sid] - rr[sid]) / denom
        ax_bot.semilogy(t, rel_err, color=COLORS[k], linewidth=1.2, label=sid)
    ax_bot.set_xlabel("time (h)")
    ax_bot.set_ylabel("|OpenCell - RR| / (|RR| + 1e-3)")
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
    parser.add_argument("--time-units", type=float, default=200.0,
                        help="Simulated end time (hours per Vilar 2002)")
    parser.add_argument("--points", type=int, default=None,
                        help="Number of output time points (default: 10*time_units + 1)")
    args = parser.parse_args()

    t_end = float(args.time_units)
    n_points = int(args.points) if args.points else int(10 * t_end) + 1
    tu_label = f"{int(t_end)}tu"
    duration_label = f"{int(t_end)} time-units (~{int(t_end)} h)"

    out_dir = Path("artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)

    model = TranscriptionModel.load()
    sha_short = model.sbml.sbml_sha256[:12]
    t_eval = np.linspace(0.0, t_end, n_points)

    print(f"Running OpenCell ({duration_label}, {n_points} points) ...")
    ours = run_opencell(model, t_eval, t_end)
    print(f"Running libroadrunner ({duration_label}, {n_points} points) ...")
    t_rr, rr_full = run_roadrunner(model.sbml.sbml_path, model.species_ids, t_end, n_points)

    assert np.allclose(t_eval, t_rr, atol=1e-9), "Time grids do not match"

    plot_one(
        "OpenCell (libsbml + sympy + LSODA)",
        out_dir / f"vilar_opencell_{tu_label}.png",
        t_eval, ours, sha_short, duration_label,
    )
    plot_one(
        "libroadrunner (CVODE)",
        out_dir / f"vilar_roadrunner_{tu_label}.png",
        t_rr, rr_full, sha_short, duration_label,
    )
    plot_overlay(
        out_dir / f"vilar_overlay_{tu_label}.png",
        t_eval, ours, rr_full, sha_short, duration_label,
    )

    print("\nMax relative difference per species (denom = |RR| + 1e-3):")
    summary: dict[str, float] = {}
    for sid in HIGHLIGHT + [s for s in model.species_ids if s not in HIGHLIGHT]:
        denom = np.abs(rr_full[sid]) + 1e-3
        rel = np.abs(ours[sid] - rr_full[sid]) / denom
        max_rel = float(rel.max())
        summary[sid] = max_rel
        print(f"  {sid:6s}  max_rel_err = {max_rel:.3e}")

    vals = np.array(list(summary.values()))
    print("\nSummary stats:")
    print(f"  worst species:  max_rel = {vals.max():.3e}")
    print(f"  median species: max_rel = {np.median(vals):.3e}")
    print(f"  mean species:   max_rel = {vals.mean():.3e}")

    json_path = out_dir / f"vilar_residuals_{tu_label}.json"
    json_path.write_text(
        json.dumps(
            {
                "sbml_sha256": model.sbml.sbml_sha256,
                "biomodels_id": model.biomodels_id,
                "paper_doi": model.paper_doi,
                "paper_pubmed_id": model.paper_pubmed_id,
                "t_end": t_end,
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
