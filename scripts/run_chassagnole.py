"""Run the Chassagnole 2002 E. coli central carbon metabolism for 60s.

Produces a PNG of the major glycolytic intermediates so a reader can
sanity-check trajectories at a glance.

Usage:
    python scripts/run_chassagnole.py [--out path/to/figure.png] [--seconds 60]

Outputs (alongside the PNG):
    * stdout JSON with the full provenance record (SBML SHA-256, BioModels ID,
      paper DOI, paper PMID) — pipe to a file to keep an audit trail of the run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from opencell.models.metabolism import MetabolismModel
from opencell.solvers.ode_scipy import ScipySolverConfig, solve_ode_scipy


HIGHLIGHT_SPECIES = ["cglcex", "cg6p", "cf6p", "cfdp", "cgap", "cpep", "cpyr"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/chassagnole_60s.png"),
        help="Path for the output PNG figure",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=60.0,
        help="Simulated end time in seconds",
    )
    parser.add_argument(
        "--points",
        type=int,
        default=601,
        help="Number of output time points",
    )
    args = parser.parse_args()

    model = MetabolismModel.load()
    t_eval = np.linspace(0.0, args.seconds, args.points)
    res = solve_ode_scipy(
        model.rhs,
        model.initial_y,
        (0.0, args.seconds),
        config=ScipySolverConfig(method="LSODA", rtol=1e-9, atol=1e-12),
        t_eval=t_eval,
    )
    if not res.success:
        raise SystemExit(f"Integration failed: {res.message}")

    print(json.dumps(model.provenance(), indent=2, sort_keys=True))
    print(f"\nIntegration: {res.n_rhs_evals} RHS evals, {len(t_eval)} time points")
    sp_idx = model.species_index()
    for sid in HIGHLIGHT_SPECIES:
        i = sp_idx[sid]
        print(
            f"  {sid:8s}  init={model.initial_y[i]:.4f}  "
            f"final={res.ys[i, -1]:.4f}  "
            f"min={res.ys[i].min():.4f}  max={res.ys[i].max():.4f}"
        )

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\nmatplotlib not installed - skipping figure.")
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for sid in HIGHLIGHT_SPECIES:
        i = sp_idx[sid]
        ax.plot(t_eval, res.ys[i], label=sid, linewidth=1.6)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("concentration (mM)")
    ax.set_title(
        "Chassagnole 2002 / BIOMD0000000051 - E. coli central carbon metabolism\n"
        f"OpenCell SBML to ODE, SHA-256 {model.sbml.sbml_sha256[:12]}..."
    )
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.out, dpi=150)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
