"""Demo: 3-trajectory comparison for the metabolism->transcription coupling.

Generates a comparison showing:
  - Vilar uncoupled (full synthesis, baseline limit cycle)
  - Coupled with cglcex-driven f_met (Chassagnole metabolism feeds into Vilar)
  - Coupling-off control (f_met == 1, must equal uncoupled)

Per critique: 1-hour horizon is too short for a 25h oscillator. We run for
8 cellular hours to make the limit-cycle topology visible. Composite time
is in seconds; the metabolism sub-model uses native seconds, the gene
sub-model is rescaled internally.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp

from opencell.models.coupled import (
    SECONDS_PER_HOUR,
    CoupledMetabolismTranscription,
)
from opencell.models.transcription import TranscriptionModel

ARTIFACT_DIR = Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)
T_END_HOURS = 8.0
T_END_SECONDS = T_END_HOURS * SECONDS_PER_HOUR


def _solve(rhs, y0, atols, t_end_s):
    return solve_ivp(
        rhs,
        (0.0, t_end_s),
        y0,
        method="LSODA",
        atol=atols,
        rtol=1e-6,
        max_step=60.0,
        dense_output=True,
    )


def main() -> None:
    coupled = CoupledMetabolismTranscription.build()
    coupled_flux = CoupledMetabolismTranscription.build(
        met=coupled.met, gene=coupled.gene, signal="uptake_flux"
    )
    coupled_off = CoupledMetabolismTranscription.build(
        met=coupled.met, gene=coupled.gene, f_met_fn=lambda c, c0: 1.0
    )

    y0 = coupled.initial_y
    atols = coupled.vector_atols()

    print(f"Integrating to {T_END_HOURS} h cellular time ({T_END_SECONDS:.0f} s)...")
    sol_coupled = _solve(coupled.rhs, y0, atols, T_END_SECONDS)
    sol_flux = _solve(coupled_flux.rhs, y0, atols, T_END_SECONDS)
    sol_off = _solve(coupled_off.rhs, y0, atols, T_END_SECONDS)
    assert sol_coupled.success and sol_off.success and sol_flux.success

    # Uncoupled Vilar reference (gene sub-model only, native hours)
    gene = TranscriptionModel.load()
    sol_unc = solve_ivp(
        gene.rhs,
        (0.0, T_END_HOURS),
        gene.initial_y,
        method="LSODA",
        atol=1e-3,
        rtol=1e-6,
        max_step=0.05,
        dense_output=True,
    )
    assert sol_unc.success

    # Plotting grid: shared cellular-time axis in hours
    t_plot_h = np.linspace(0.0, T_END_HOURS, 600)
    t_plot_s = t_plot_h * SECONDS_PER_HOUR

    gidx = gene.species_index()
    n_met = coupled.n_met
    midx = coupled.met.species_index()

    def gene_traj(sol, name, t_eval_s):
        y = sol.sol(t_eval_s)
        return y[n_met + gidx[name]]

    def gene_traj_unc(name, t_eval_h):
        return sol_unc.sol(t_eval_h)[gidx[name]]

    # Figure: 2x2 — A, R, MA+MR, cglcex+f_met
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))

    ax = axes[0, 0]
    ax.plot(t_plot_h, gene_traj_unc("A", t_plot_h), label="Vilar uncoupled", lw=2)
    ax.plot(t_plot_h, gene_traj(sol_off, "A", t_plot_s), label="coupled, f_met=1", lw=1, ls="--")
    ax.plot(t_plot_h, gene_traj(sol_coupled, "A", t_plot_s), label="coupled (concentration)", lw=2, alpha=0.8)
    ax.plot(t_plot_h, gene_traj(sol_flux, "A", t_plot_s), label="coupled (uptake_flux)", lw=2, alpha=0.8)
    ax.set_ylabel("A (activator, molecules)")
    ax.set_xlabel("time (h)")
    ax.legend(fontsize=8)

    ax = axes[0, 1]
    ax.plot(t_plot_h, gene_traj_unc("R", t_plot_h), label="Vilar uncoupled", lw=2)
    ax.plot(t_plot_h, gene_traj(sol_off, "R", t_plot_s), label="coupled, f_met=1", lw=1, ls="--")
    ax.plot(t_plot_h, gene_traj(sol_coupled, "R", t_plot_s), label="coupled (concentration)", lw=2, alpha=0.8)
    ax.plot(t_plot_h, gene_traj(sol_flux, "R", t_plot_s), label="coupled (uptake_flux)", lw=2, alpha=0.8)
    ax.set_ylabel("R (repressor, molecules)")
    ax.set_xlabel("time (h)")
    ax.legend(fontsize=8)

    ax = axes[1, 0]
    ax.plot(t_plot_h, gene_traj_unc("MA", t_plot_h), label="MA uncoupled", lw=2)
    ax.plot(t_plot_h, gene_traj(sol_coupled, "MA", t_plot_s), label="MA coupled", lw=2, alpha=0.8)
    ax.plot(t_plot_h, gene_traj_unc("MR", t_plot_h), label="MR uncoupled", lw=2, ls=":")
    ax.plot(t_plot_h, gene_traj(sol_coupled, "MR", t_plot_s), label="MR coupled", lw=2, ls=":", alpha=0.8)
    ax.set_ylabel("mRNA (molecules)")
    ax.set_xlabel("time (h)")
    ax.legend(fontsize=8)

    ax = axes[1, 1]
    cglcex = sol_coupled.sol(t_plot_s)[midx["cglcex"]]
    f_met_conc = np.clip(cglcex / coupled.cglcex_init, 0.0, 1.0)
    # Re-derive uptake-flux f_met along the trajectory of the flux-coupled run
    f_met_flux = np.empty_like(t_plot_s)
    for i, t in enumerate(t_plot_s):
        y = sol_flux.sol(t)
        f_met_flux[i] = coupled_flux.f_met(t, y)
    ax2 = ax.twinx()
    line0, = ax.plot(t_plot_h, cglcex, color="C3", label="cglcex (mM)")
    line1, = ax2.plot(t_plot_h, f_met_conc, color="C4", ls="--", label="f_met (concentration)")
    line2, = ax2.plot(t_plot_h, f_met_flux, color="C5", ls="-.", label="f_met (uptake_flux)")
    ax.set_ylabel("cglcex (mM)", color="C3")
    ax2.set_ylabel("f_met (synthesis modulation)")
    ax.set_xlabel("time (h)")
    ax.legend(handles=[line0, line1, line2], fontsize=8, loc="upper right")

    fig.suptitle(
        f"Metabolism -> transcription coupling (Chassagnole 2002 -> Vilar 2002), "
        f"{T_END_HOURS:.0f} h cellular time"
    )
    fig.tight_layout()
    out_png = ARTIFACT_DIR / "coupled_metabolism_transcription.png"
    fig.savefig(out_png, dpi=120)
    print(f"Wrote {out_png}")

    # Numerical summary
    summary = {
        "horizon_hours": T_END_HOURS,
        "f_met_min": float(f_met_vals.min()),
        "f_met_max": float(f_met_vals.max()),
        "f_met_final": float(f_met_vals[-1]),
        "cglcex_initial_mM": coupled.cglcex_init,
        "cglcex_final_mM": float(cglcex[-1]),
        "R_max_uncoupled": float(gene_traj_unc("R", t_plot_h).max()),
        "R_max_coupled": float(gene_traj(sol_coupled, "R", t_plot_s).max()),
        "R_max_off": float(gene_traj(sol_off, "R", t_plot_s).max()),
        "validation_off_minus_uncoupled_R_max_abs_diff": float(
            np.max(np.abs(gene_traj(sol_off, "R", t_plot_s) - gene_traj_unc("R", t_plot_h)))
        ),
    }
    out_json = ARTIFACT_DIR / "coupled_metabolism_transcription.json"
    out_json.write_text(json.dumps(summary, indent=2))
    print(f"Wrote {out_json}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
