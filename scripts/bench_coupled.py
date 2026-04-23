"""Performance benchmark for the metabolism->transcription coupling.

Measures:
  1. RHS evaluation cost (per call, both signals)
  2. Wall-clock time for an 8-hour cellular integration
  3. RHS-call count and step count (LSODA reports neither directly via
     solve_ivp; we use a counter wrapper)
  4. Comparison vs uncoupled baselines (metabolism alone, gene alone)

Notes:
  * Pure Python loop over 48 (Chassagnole) + 16 (Vilar) reactions per
    RHS call; no JAX/JIT. This is the reference SciPy/NumPy path.
  * The uptake_flux signal saves one fluxes() call per RHS by reusing
    the metabolism flux vector, so it is slightly cheaper than the
    concentration signal (which still calls met.rhs which internally
    calls met.fluxes).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

from opencell.models.coupled import (
    SECONDS_PER_HOUR,
    CoupledMetabolismTranscription,
)
from opencell.models.metabolism import MetabolismModel
from opencell.models.transcription import TranscriptionModel

ARTIFACT_DIR = Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)
T_END_HOURS = 8.0
T_END_SECONDS = T_END_HOURS * SECONDS_PER_HOUR
N_RHS_TIMING_CALLS = 2000


def time_rhs(rhs_fn, y0, n=N_RHS_TIMING_CALLS) -> float:
    """Return mean wall-clock seconds per RHS call."""
    # warmup
    for _ in range(20):
        rhs_fn(0.0, y0)
    t0 = time.perf_counter()
    for _ in range(n):
        rhs_fn(0.0, y0)
    return (time.perf_counter() - t0) / n


class CountingRHS:
    """Wraps a RHS to count invocations during integration."""

    def __init__(self, rhs):
        self.rhs = rhs
        self.calls = 0

    def __call__(self, t, y):
        self.calls += 1
        return self.rhs(t, y)


def integrate(rhs_fn, y0, atol, t_end_s, max_step=60.0):
    counter = CountingRHS(rhs_fn)
    t0 = time.perf_counter()
    sol = solve_ivp(
        counter, (0.0, t_end_s), y0,
        method="LSODA", atol=atol, rtol=1e-6, max_step=max_step,
    )
    wall = time.perf_counter() - t0
    return sol, wall, counter.calls


def main() -> None:
    print("Building models...")
    met = MetabolismModel.load()
    gene = TranscriptionModel.load()
    cb_conc = CoupledMetabolismTranscription.build(met=met, gene=gene, signal="concentration")
    cb_flux = CoupledMetabolismTranscription.build(met=met, gene=gene, signal="uptake_flux")

    y0_coupled = cb_conc.initial_y
    atol_coupled = cb_conc.vector_atols()

    # ----- RHS evaluation timing -----
    print("\n[1] RHS evaluation cost (mean of {:,} calls)".format(N_RHS_TIMING_CALLS))
    t_met = time_rhs(met.rhs, met.initial_y)
    t_gene = time_rhs(gene.rhs, gene.initial_y)
    t_conc = time_rhs(cb_conc.rhs, y0_coupled)
    t_flux = time_rhs(cb_flux.rhs, y0_coupled)
    print(f"  metabolism alone   : {t_met*1e6:7.2f} us/call")
    print(f"  gene alone         : {t_gene*1e6:7.2f} us/call")
    print(f"  coupled (conc)     : {t_conc*1e6:7.2f} us/call  ({t_conc/(t_met+t_gene):.2f}x sum)")
    print(f"  coupled (uptake)   : {t_flux*1e6:7.2f} us/call  ({t_flux/(t_met+t_gene):.2f}x sum)")

    # ----- 8-hour integration timing -----
    print(f"\n[2] LSODA integration to {T_END_HOURS:.0f} h cellular ({T_END_SECONDS:.0f} s)")
    sol_m, w_m, c_m = integrate(met.rhs, met.initial_y,
                                np.full(met.n_species, 1e-9), T_END_SECONDS)
    sol_g, w_g, c_g = integrate(gene.rhs, gene.initial_y,
                                np.full(gene.n_species, 1e-3), T_END_HOURS,
                                max_step=0.05)
    sol_c, w_c, c_c = integrate(cb_conc.rhs, y0_coupled, atol_coupled, T_END_SECONDS)
    sol_f, w_f, c_f = integrate(cb_flux.rhs, y0_coupled, atol_coupled, T_END_SECONDS)

    for name, sol, wall, calls in [
        ("metabolism alone (s)", sol_m, w_m, c_m),
        ("gene alone (h)      ", sol_g, w_g, c_g),
        ("coupled (conc)      ", sol_c, w_c, c_c),
        ("coupled (uptake)    ", sol_f, w_f, c_f),
    ]:
        n_steps = len(sol.t) - 1
        ok = "OK " if sol.success else "FAIL"
        print(f"  {name}  wall={wall:6.2f}s  steps={n_steps:5d}  rhs_calls={calls:6d}  {ok}")

    # ----- biology summary: which signal bites harder? -----
    print("\n[3] Biology comparison at t=8h cellular")
    midx = met.species_index()
    gidx = gene.species_index()

    def end_y(sol, kind):
        if kind == "met":
            return {s: sol.y[midx[s], -1] for s in ("cglcex", "cpep", "cg6p")}
        if kind == "gene":
            return {s: sol.y[gidx[s], -1] for s in ("R", "A", "MA", "MR")}
        if kind == "coupled":
            n = cb_conc.n_met
            d = {s: sol.y[midx[s], -1] for s in ("cglcex", "cpep", "cg6p")}
            d.update({s: sol.y[n + gidx[s], -1] for s in ("R", "A", "MA", "MR")})
            return d
        raise ValueError(kind)

    print("  uncoupled met end :", {k: f"{v:.4g}" for k, v in end_y(sol_m, "met").items()})
    print("  uncoupled gene end:", {k: f"{v:.4g}" for k, v in end_y(sol_g, "gene").items()})
    print("  coupled (conc) end:", {k: f"{v:.4g}" for k, v in end_y(sol_c, "coupled").items()})
    print("  coupled (flux) end:", {k: f"{v:.4g}" for k, v in end_y(sol_f, "coupled").items()})

    # ----- summary JSON -----
    summary = {
        "horizon_hours": T_END_HOURS,
        "n_rhs_timing_calls": N_RHS_TIMING_CALLS,
        "rhs_us_per_call": {
            "metabolism_alone": t_met * 1e6,
            "gene_alone": t_gene * 1e6,
            "coupled_concentration": t_conc * 1e6,
            "coupled_uptake_flux": t_flux * 1e6,
        },
        "integration": {
            "metabolism_alone": {"wall_s": w_m, "rhs_calls": c_m, "steps": len(sol_m.t) - 1},
            "gene_alone": {"wall_s": w_g, "rhs_calls": c_g, "steps": len(sol_g.t) - 1},
            "coupled_concentration": {"wall_s": w_c, "rhs_calls": c_c, "steps": len(sol_c.t) - 1},
            "coupled_uptake_flux": {"wall_s": w_f, "rhs_calls": c_f, "steps": len(sol_f.t) - 1},
        },
        "end_state": {
            "uncoupled_met": {k: float(v) for k, v in end_y(sol_m, "met").items()},
            "uncoupled_gene": {k: float(v) for k, v in end_y(sol_g, "gene").items()},
            "coupled_concentration": {k: float(v) for k, v in end_y(sol_c, "coupled").items()},
            "coupled_uptake_flux": {k: float(v) for k, v in end_y(sol_f, "coupled").items()},
        },
    }
    out = ARTIFACT_DIR / "coupled_perf_benchmark.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
