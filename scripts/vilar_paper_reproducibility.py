"""Measure Vilar 2002 deterministic-limit-cycle period and amplitude.

Compares against published values from Vilar et al. 2002 (PNAS 99:5988):
  - Period of deterministic oscillations: ~24 h (paper text, deterministic case)
  - R protein peak: ~1500 molecules
  - A protein peak: ~few hundred molecules
  - Damped fast transient before settling onto limit cycle.

Detects period via zero-crossings of (R - mean) on the limit-cycle portion
of the trajectory (after dropping initial transient).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from opencell.models.transcription import TranscriptionModel
from opencell.solvers.ode_scipy import ScipySolverConfig, solve_ode_scipy


T_END = 1000.0  # cover many oscillation periods to measure period reliably
N = 100001  # fine grid (10 pts / time-unit)


def measure_period(t: np.ndarray, x: np.ndarray, drop_first: float) -> float | None:
    mask = t >= drop_first
    tt, xx = t[mask], x[mask]
    mean = xx.mean()
    centered = xx - mean
    # Up-going zero crossings
    sign = np.sign(centered)
    crossings = np.where((sign[:-1] < 0) & (sign[1:] >= 0))[0]
    if len(crossings) < 3:
        return None
    # Linear-interpolate exact crossing times
    cross_t = []
    for i in crossings:
        x0, x1 = centered[i], centered[i + 1]
        if x1 == x0:
            cross_t.append(tt[i])
        else:
            cross_t.append(tt[i] + (0 - x0) / (x1 - x0) * (tt[i + 1] - tt[i]))
    diffs = np.diff(cross_t)
    return float(np.median(diffs))


def main() -> None:
    out_dir = Path("artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)

    model = TranscriptionModel.load()
    t_eval = np.linspace(0.0, T_END, N)

    print(f"Integrating Vilar for {T_END} time-units, {N} points...")
    res = solve_ode_scipy(
        model.rhs,
        model.initial_y,
        (0.0, T_END),
        config=ScipySolverConfig(method="LSODA", rtol=1e-9, atol=1e-12),
        t_eval=t_eval,
    )
    if not res.success:
        raise SystemExit(res.message)
    print(f"  done in {res.n_rhs_evals} RHS evals")

    idx = {sid: i for i, sid in enumerate(model.species_ids)}
    R = res.ys[idx["R"]]
    A = res.ys[idx["A"]]
    MR = res.ys[idx["MR"]]
    MA = res.ys[idx["MA"]]

    # Drop the first 100 time-units as transient
    period = measure_period(t_eval, R, drop_first=100.0)

    mask = t_eval >= 100.0
    R_lc = R[mask]
    A_lc = A[mask]
    measured = {
        "period_hours": period,
        "R_min": float(R_lc.min()),
        "R_max": float(R_lc.max()),
        "R_amplitude": float(R_lc.max() - R_lc.min()),
        "A_min": float(A_lc.min()),
        "A_max": float(A_lc.max()),
        "A_amplitude": float(A_lc.max() - A_lc.min()),
        "MR_max": float(MR[mask].max()),
        "MA_max": float(MA[mask].max()),
    }

    # Reference values: Vilar et al. 2002 PNAS, Figure 2A (deterministic).
    # Period in the original paper ~24 hours; R amplitude ~1400-1600 molecules.
    # We capture exact paper numbers by digitizing the figure if needed; the
    # main qualitative checks are: oscillation period O(10s of hours), R
    # amplitude O(1000s) molecules, A amplitude smaller than R.
    paper_targets = {
        "period_hours": (15.0, 35.0),
        "R_amplitude": (800.0, 2500.0),
        "A_amplitude_lt_R_amplitude": True,
        "MR_max_lt_R_max": True,  # mRNA pool is small
    }

    checks = {
        "period_hours_in_range": (
            paper_targets["period_hours"][0]
            <= (measured["period_hours"] or -1)
            <= paper_targets["period_hours"][1]
        ),
        "R_amplitude_in_range": (
            paper_targets["R_amplitude"][0]
            <= measured["R_amplitude"]
            <= paper_targets["R_amplitude"][1]
        ),
        "A_amplitude_lt_R_amplitude": (
            measured["A_amplitude"] < measured["R_amplitude"]
        ),
        "MR_max_lt_R_max": measured["MR_max"] < measured["R_max"],
    }

    print("\nMeasured limit-cycle quantities (after t>100 transient):")
    for k, v in measured.items():
        print(f"  {k:25s} = {v}")
    print("\nPaper-reproducibility checks:")
    for k, v in checks.items():
        marker = "PASS" if v else "FAIL"
        print(f"  [{marker}] {k}")

    # Plot the limit cycle and time trace
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    ax1.plot(t_eval, R, "b-", linewidth=0.7, label="R (repressor)")
    ax1.plot(t_eval, A, "r-", linewidth=0.7, label="A (activator)")
    ax1.set_xlim(0, 200)
    ax1.set_xlabel("time (h)")
    ax1.set_ylabel("molecule count")
    ax1.set_title(
        f"Vilar 2002 deterministic limit cycle\n"
        f"Measured period = {measured['period_hours']:.1f} h"
        if measured["period_hours"] else "Vilar 2002 (no period detected)"
    )
    ax1.legend()
    ax1.grid(alpha=0.3)

    # Phase portrait (R vs A) on limit cycle
    ax2.plot(A[mask], R[mask], "k-", linewidth=0.4, alpha=0.5)
    ax2.plot(A[~mask], R[~mask], "g-", linewidth=0.7, alpha=0.7, label="transient")
    ax2.set_xlabel("A (molecules)")
    ax2.set_ylabel("R (molecules)")
    ax2.set_title("Phase portrait (limit cycle in black)")
    ax2.legend()
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    out = out_dir / "vilar_paper_reproducibility.png"
    fig.savefig(out, dpi=150)
    print(f"\nWrote {out}")

    summary = {
        "biomodels_id": model.biomodels_id,
        "paper_doi": model.paper_doi,
        "paper_pubmed_id": model.paper_pubmed_id,
        "sbml_sha256": model.sbml.sbml_sha256,
        "t_end": T_END,
        "transient_dropped_until": 100.0,
        "measured": measured,
        "paper_targets": paper_targets,
        "checks": checks,
        "all_checks_pass": all(checks.values()),
    }
    json_out = out_dir / "vilar_paper_reproducibility.json"
    json_out.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(f"Wrote {json_out}")
    print(f"\nALL CHECKS PASS: {summary['all_checks_pass']}")


if __name__ == "__main__":
    main()
