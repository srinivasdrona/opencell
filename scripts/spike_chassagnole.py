"""Glucose-spike perturbation: Chassagnole 2002 + step injection at t=180s.

Splits the 300-second simulation into two phases:
  Phase 1 (0 to 180s): standard integration from initial conditions
  Phase 2 (180 to 300s): cglcex is doubled from its initial value (2.0 -> 4.0 mM)
                         then the system is integrated forward

This is biologically meaningful: it mimics a substrate pulse of fresh glucose
delivered into a near-exhausted bioreactor and shows how the glycolytic
network responds (recovery of upper-glycolysis pools, PEP/pyruvate transients).

OpenCell handles this trivially because the solver state is plain NumPy.
For libroadrunner, we use rr.reset() + setValue + simulate from current state.

Outputs (in artifacts/):
  chassagnole_spike_overlay_300s.png   - overlay + residual panel
  chassagnole_spike_residuals_300s.json - per-species max relative error
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


T_END = 300.0
T_SPIKE = 180.0
SPIKE_MULTIPLIER = 2.0  # double the initial cglcex
N_POINTS = 3001
HIGHLIGHT = ["cglcex", "cg6p", "cf6p", "cfdp", "cgap", "cpep", "cpyr"]
COLORS = plt.cm.tab10.colors  # type: ignore[attr-defined]


def run_opencell_with_spike(
    model: MetabolismModel,
    t_eval: np.ndarray,
    spike_time: float,
    spike_value: float,
) -> dict[str, np.ndarray]:
    """Integrate two phases, applying the perturbation between them.

    The output dict maps species_id -> trajectory sampled at t_eval.
    """
    cfg = ScipySolverConfig(method="LSODA", rtol=1e-9, atol=1e-12)
    cglcex_idx = model.species_index()["cglcex"]

    # Phase 1: 0 -> spike_time
    t_eval_phase1 = t_eval[t_eval <= spike_time]
    res1 = solve_ode_scipy(
        model.rhs, model.initial_y, (0.0, spike_time),
        config=cfg, t_eval=t_eval_phase1,
    )
    if not res1.success:
        raise SystemExit(f"OpenCell phase 1 failed: {res1.message}")

    # Apply spike: y at end of phase 1 with cglcex doubled
    y_after_spike = res1.ys[:, -1].copy()
    y_after_spike[cglcex_idx] = spike_value

    # Phase 2: spike_time -> T_END  (continue from spiked state)
    t_eval_phase2 = t_eval[t_eval > spike_time]
    res2 = solve_ode_scipy(
        model.rhs, y_after_spike, (spike_time, t_eval[-1]),
        config=cfg, t_eval=t_eval_phase2,
    )
    if not res2.success:
        raise SystemExit(f"OpenCell phase 2 failed: {res2.message}")

    print(f"  OpenCell: phase1 {res1.n_rhs_evals} evals, phase2 {res2.n_rhs_evals} evals")

    # Stitch back together at the original t_eval grid
    out: dict[str, np.ndarray] = {}
    for i, sid in enumerate(model.species_ids):
        out[sid] = np.concatenate([res1.ys[i], res2.ys[i]])
    return out


def run_roadrunner_with_spike(
    sbml_path: Path,
    t_eval: np.ndarray,
    spike_time: float,
    spike_value: float,
) -> dict[str, np.ndarray]:
    rr = roadrunner.RoadRunner(str(sbml_path))
    rr.integrator.relative_tolerance = 1e-10
    rr.integrator.absolute_tolerance = 1e-12

    t_phase1 = t_eval[t_eval <= spike_time]   # ..., 179.9, 180.0
    t_phase2 = t_eval[t_eval > spike_time]    # 180.1, ..., 300.0

    # Phase 1: sample at exactly t_phase1
    res1 = rr.simulate(0.0, spike_time, len(t_phase1))
    cols = list(res1.colnames)

    # Apply spike to live state at t=spike_time
    rr["[cglcex]"] = spike_value

    # Phase 2: ask for N+1 points spanning [spike_time, t_end] so the
    # internal grid lands on the SAME values as t_phase2.  We then drop
    # the first row (which is the duplicate spike_time sample) to align.
    res2_full = rr.simulate(spike_time, t_eval[-1], len(t_phase2) + 1)
    res2 = np.asarray(res2_full)[1:, :]  # drop the spike_time row

    # Sanity: confirm the time grids actually match
    grid_oc = np.concatenate([t_phase1, t_phase2])
    grid_rr = np.concatenate([np.asarray(res1[:, 0]), res2[:, 0]])
    if not np.allclose(grid_oc, grid_rr, atol=1e-9):
        max_diff = float(np.max(np.abs(grid_oc - grid_rr)))
        raise AssertionError(
            f"Time grids misaligned between OC and RR (max diff = {max_diff:.3e} s)"
        )

    out: dict[str, np.ndarray] = {}
    for col in cols[1:]:
        sid = col.strip("[]")
        j = cols.index(col)
        out[sid] = np.concatenate([np.asarray(res1[:, j]), res2[:, j]])
    return out


def main() -> None:
    out_dir = Path("artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)

    model = MetabolismModel.load()
    sha_short = model.sbml.sbml_sha256[:12]
    cglcex_init = float(model.initial_y[model.species_index()["cglcex"]])
    spike_value = cglcex_init * SPIKE_MULTIPLIER

    t_eval = np.linspace(0.0, T_END, N_POINTS)
    label = f"300s, cglcex spike {cglcex_init:.1f}->{spike_value:.1f} mM at t={int(T_SPIKE)}s"

    print(f"Running OpenCell ({label}) ...")
    ours = run_opencell_with_spike(model, t_eval, T_SPIKE, spike_value)
    print(f"Running libroadrunner ({label}) ...")
    rr_full = run_roadrunner_with_spike(model.sbml.sbml_path, t_eval, T_SPIKE, spike_value)

    # Overlay plot with spike marker
    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, figsize=(10, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 2]},
    )
    for k, sid in enumerate(HIGHLIGHT):
        c = COLORS[k]
        ax_top.plot(t_eval, rr_full[sid], color=c, linewidth=2.5, alpha=0.35,
                    label=f"{sid} (RR)")
        ax_top.plot(t_eval, ours[sid], color=c, linewidth=1.0, linestyle="--",
                    label=f"{sid} (OpenCell)")
    ax_top.axvline(T_SPIKE, color="black", linestyle=":", linewidth=1.5,
                   label=f"glucose spike (x{SPIKE_MULTIPLIER:.0f})")
    ax_top.set_ylabel("concentration (mM)")
    ax_top.set_title(
        f"OpenCell (dashed) vs libroadrunner (thick) - Chassagnole 2002 with glucose spike\n"
        f"{label} | BIOMD0000000051 SHA-256 {sha_short}"
    )
    ax_top.grid(alpha=0.3)
    ax_top.legend(loc="upper right", ncol=2, fontsize=7)

    for k, sid in enumerate(HIGHLIGHT):
        denom = np.abs(rr_full[sid]) + 1e-9
        rel_err = np.abs(ours[sid] - rr_full[sid]) / denom
        ax_bot.semilogy(t_eval, rel_err, color=COLORS[k], linewidth=1.2, label=sid)
    ax_bot.axvline(T_SPIKE, color="black", linestyle=":", linewidth=1.5)
    ax_bot.axhline(1e-3, color="red", linestyle=":", linewidth=1, label="test rtol=1e-3")
    ax_bot.set_xlabel("time (s)")
    ax_bot.set_ylabel("|OpenCell - RR| / |RR|")
    ax_bot.set_title("Relative residual per species (log scale)")
    ax_bot.grid(alpha=0.3, which="both")
    ax_bot.legend(loc="upper right", ncol=2, fontsize=7)

    fig.tight_layout()
    overlay_path = out_dir / "chassagnole_spike_overlay_300s.png"
    fig.savefig(overlay_path, dpi=150)
    plt.close(fig)
    print(f"  wrote {overlay_path}")

    # Numeric summary
    summary: dict[str, float] = {}
    print("\nMax relative difference per species (across full 300s, including spike):")
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

    # Pre/post-spike comparison for cglcex and downstream pools
    sp_idx = model.species_index()
    print("\nKey metabolites just before vs just after spike (OpenCell):")
    pre_idx = int(np.searchsorted(t_eval, T_SPIKE) - 1)
    post_idx = int(np.searchsorted(t_eval, T_SPIKE) + 5)  # ~0.5s after
    end_idx = -1
    print(f"  {'species':>8s}  {'t<180s':>10s}  {'t=180+':>10s}  {'t=300s':>10s}")
    for sid in ["cglcex", "cg6p", "cf6p", "cfdp", "cpep", "cpyr"]:
        i = sp_idx[sid]
        print(
            f"  {sid:>8s}  {ours[sid][pre_idx]:>10.4f}  "
            f"{ours[sid][post_idx]:>10.4f}  {ours[sid][end_idx]:>10.4f}"
        )

    json_path = out_dir / "chassagnole_spike_residuals_300s.json"
    json_path.write_text(
        json.dumps(
            {
                "sbml_sha256": model.sbml.sbml_sha256,
                "biomodels_id": model.biomodels_id,
                "t_end_seconds": T_END,
                "spike_time_seconds": T_SPIKE,
                "spike_species": "cglcex",
                "spike_initial_value_mM": cglcex_init,
                "spike_post_value_mM": spike_value,
                "n_points": N_POINTS,
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
