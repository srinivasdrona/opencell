"""M0.5 — Multi-Process scaling profiler.

Question: how does Vivarium per-macro-step overhead scale with N
processes? Does the M0-C macro_dt knob still buy us enough at 16
processes (Karr-scale) or do we need M0-A (persist solver state) /
fused-ODE scheduler before M1?

Method:
  * **Synthetic rig**: N no-op Processes sharing a small store. Each
    Process reads K floats, writes K floats. Isolates pure
    scheduler + state-marshalling cost.
  * **Realistic rig**: N copies of MetabolismProcess each integrating
    Chassagnole on its own state (independent realisations sharing
    nothing biological). Captures LSODA spin-up cost × N.

Both swept over N ∈ {1, 2, 4, 8, 16, 32}; fixed horizon 600s, macro_dt 60s
(10 macro steps). We measure wall time and derive overhead per Process.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from vivarium.core.engine import Engine
from vivarium.core.process import Process

from opencell.models.coupled import CoupledMetabolismTranscription
from opencell.vivarium.processes import MetabolismProcess

HORIZON_S = 600.0
MACRO_DT_S = 60.0
N_VALUES_NOOP = [1, 2, 4, 8, 16, 32]
N_VALUES_METAB = [1, 2, 4, 8, 16]  # n=32 takes >10 min; the curve is clear by 16
K_PORTS = 4  # floats read+written per noop Process


class NoopProcess(Process):
    """Reads K floats, writes K back. No biology, no solver."""

    name = "noop"
    defaults: dict[str, Any] = {"k": K_PORTS, "idx": 0}

    def ports_schema(self) -> dict:
        k = self.parameters["k"]
        return {
            "store": {
                f"x{i}": {"_default": 0.0, "_updater": "set", "_emit": False} for i in range(k)
            }
        }

    def next_update(self, timestep: float, states: dict) -> dict:
        # Trivial dependency on inputs so dispatcher cannot eliminate.
        s = states["store"]
        return {"store": {f"x{i}": float(s[f"x{i}"] + 1.0) for i in range(self.parameters["k"])}}


def build_noop_engine(n: int) -> Engine:
    procs = {f"noop_{i}": NoopProcess({"k": K_PORTS, "idx": i}) for i in range(n)}
    topo = {f"noop_{i}": {"store": ("shared",)} for i in range(n)}
    return Engine(processes=procs, topology=topo)


def build_metab_engine(n: int) -> Engine:
    coupled = CoupledMetabolismTranscription.build(signal="uptake_flux")
    procs: dict = {}
    topo: dict = {}
    for i in range(n):
        procs[f"metab_{i}"] = MetabolismProcess({"coupled": coupled})
        topo[f"metab_{i}"] = {
            "metabolites": (f"met_{i}",),
            "signal": (f"sig_{i}",),
        }
    return Engine(processes=procs, topology=topo)


def time_engine(builder, n: int) -> float:
    eng = builder(n)
    t0 = time.perf_counter()
    eng.update(HORIZON_S)
    return time.perf_counter() - t0


def main() -> int:
    rows = []
    for label, builder, ns in (
        ("noop", build_noop_engine, N_VALUES_NOOP),
        ("metab", build_metab_engine, N_VALUES_METAB),
    ):
        for n in ns:
            try:
                wall = time_engine(builder, n)
            except Exception as e:
                rows.append({"rig": label, "n": n, "wall_s": None, "error": str(e)[:200]})
                print(f"[{label} n={n:>3}] FAILED: {e}")
                continue
            per_proc = wall / n
            per_step_per_proc = per_proc / (HORIZON_S / MACRO_DT_S)
            row = {
                "rig": label,
                "n": n,
                "wall_s": round(wall, 3),
                "per_process_s": round(per_proc, 4),
                "per_macro_step_per_process_ms": round(per_step_per_proc * 1000, 3),
            }
            rows.append(row)
            print(
                f"[{label} n={n:>3}] wall={wall:7.3f}s  per_proc={per_proc:7.4f}s  "
                f"per_step_per_proc={per_step_per_proc * 1000:6.2f}ms"
            )

    # Compute scaling exponent (log-log fit) for each rig
    summary = {}
    for label in ("noop", "metab"):
        ns = np.array([r["n"] for r in rows if r["rig"] == label and r["wall_s"] is not None])
        ws = np.array([r["wall_s"] for r in rows if r["rig"] == label and r["wall_s"] is not None])
        if len(ns) >= 3:
            # wall = a * n^b
            b, log_a = np.polyfit(np.log(ns), np.log(ws), 1)
            summary[label] = {
                "scaling_exponent_b": round(float(b), 3),
                "intercept_a_s": round(float(np.exp(log_a)), 4),
                "fit": "wall_s ≈ a * N^b",
            }

    out = Path("artifacts/M05_multiproc_scaling.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "horizon_s": HORIZON_S,
                "macro_dt_s": MACRO_DT_S,
                "k_ports": K_PORTS,
                "rows": rows,
                "summary": summary,
            },
            indent=2,
        )
    )
    print(f"\n{json.dumps(summary, indent=2)}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
