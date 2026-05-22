"""M0 vertical slice — exercise the closed loop on Chassagnole+Vilar.

Closes Phase 4. Uses A5 (multi-level diff) and A7 (invariants) against
the vivarium-hosted coupled engine vs single-shot hybrid_run on the
A6-defined coupling torture rig. Resolves the LSODA-restart decision
(A8: M0-A persist | M0-B fixed-step | M0-C larger macro_dt).

Outcome: docs/phase4/M0_vertical_slice_findings.md.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from opencell.diff import DiffSpec, run_diff
from opencell.models.coupled import CoupledMetabolismTranscription
from opencell.solvers.hybrid import hybrid_run
from opencell.vivarium import build_coupled_engine

HORIZONS_S = [600.0, 3600.0]  # 10 min and 1 h
MACRO_DTS_S = [60.0, 300.0]  # M0-default vs M0-C "larger macro_dt"


def run_one(horizon_s: float, macro_dt_s: float, seed: int = 99) -> dict:
    coupled = CoupledMetabolismTranscription.build(signal="uptake_flux")

    rng = np.random.default_rng(seed)
    t0 = time.perf_counter()
    eng = build_coupled_engine(coupled=coupled, macro_dt_s=macro_dt_s, rng=rng)
    eng.update(horizon_s)
    viv_wall = time.perf_counter() - t0
    viv = eng.emitter.get_timeseries()

    rng2 = np.random.default_rng(seed)
    t0 = time.perf_counter()
    hyb = hybrid_run(coupled, t_end_s=horizon_s, macro_dt_s=macro_dt_s, rng=rng2)
    hyb_wall = time.perf_counter() - t0

    midx = coupled.met.species_index()
    gidx = coupled.gene.species_index()
    hyb_traj = {
        "time": list(hyb.ts),
        "metabolites": {"cglcex": hyb.y_met[:, midx["cglcex"]]},
        "signal": {"f_met": hyb.f_met_history},
        "gene_state": {"MA": hyb.y_gene[:, gidx["MA"]]},
    }

    spec = DiffSpec(
        engine_a_name="hybrid_run",
        engine_b_name="vivarium",
        comparable_variables={
            ("metabolites", "cglcex"): {"abs": 0.5, "rel": 0.5, "kind": "concentration"},
            ("signal", "f_met"): {"abs": 1.0, "rel": 1.0, "kind": "signal"},
            ("gene_state", "MA"): {"abs": 50, "rel": 5.0, "kind": "count"},
        },
        scalar_phenotypes=["cglcex_final", "f_met_final"],
    )
    rep = run_diff(hyb_traj, viv, spec=spec)

    return {
        "horizon_s": horizon_s,
        "macro_dt_s": macro_dt_s,
        "n_macro_steps": int(horizon_s / macro_dt_s),
        "wall_s": {"hybrid_run": round(hyb_wall, 3), "vivarium": round(viv_wall, 3)},
        "overhead_x": round(viv_wall / max(hyb_wall, 1e-6), 1),
        "diff_passed": rep.passed,
        "level1_fails": sum(1 for f in rep.level1_findings if f.severity == "fail"),
        "invariants_a_passed": (
            rep.level2_a_invariants.passed if rep.level2_a_invariants else None
        ),
        "invariants_b_passed": (
            rep.level2_b_invariants.passed if rep.level2_b_invariants else None
        ),
        "level3_failures": [
            {
                "path": list(f.detail.get("path", [])),
                "L_inf_abs": f.detail.get("L_inf_abs"),
                "tol_abs": f.detail.get("tol_abs"),
            }
            for f in rep.level3_findings
            if f.severity == "fail"
        ],
        "level4_failures": [
            {
                "name": f.detail.get("name"),
                "value_a": f.detail.get("value_a"),
                "value_b": f.detail.get("value_b"),
            }
            for f in rep.level4_findings
            if f.severity == "fail"
        ],
    }


def main() -> int:
    rows = []
    for horizon_s in HORIZONS_S:
        for macro_dt_s in MACRO_DTS_S:
            print(f"\n--- horizon={horizon_s}s macro_dt={macro_dt_s}s ---")
            row = run_one(horizon_s, macro_dt_s)
            rows.append(row)
            print(json.dumps(row, indent=2, default=str))

    out = Path("artifacts/M0_vertical_slice.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"rows": rows}, indent=2, default=str))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
