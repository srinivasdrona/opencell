"""Probe 2: Step/Deriver reconciliation semantics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vivarium.core.engine import Engine
from vivarium.core.process import Deriver, Process, Step


ARTIFACT_DIR = Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)
OUT = ARTIFACT_DIR / "d2_probe2_results.json"


class M3StubSet(Process):
    name = "m3_stub_set"
    defaults = {"execution_log": None}

    def ports_schema(self):
        return {
            "protein": {"counts": {"A": {"_default": 100, "_updater": "set", "_emit": True}}},
            "d2_consumed": {"A": {"_default": 0, "_updater": "accumulate", "_emit": True}},
        }

    def next_update(self, timestep, states):
        if self.parameters.get("execution_log") is not None:
            self.parameters["execution_log"].append("m3")
        return {"protein": {"counts": {"A": 200}}}


class D2StubConsumer(Process):
    name = "d2_stub_consumer"
    defaults = {"observed": None, "execution_log": None}

    def ports_schema(self):
        return {
            "protein": {"counts": {"A": {"_default": 100, "_updater": "set", "_emit": True}}},
            "d2_consumed": {"A": {"_default": 0, "_updater": "accumulate", "_emit": True}},
        }

    def next_update(self, timestep, states):
        if self.parameters.get("execution_log") is not None:
            self.parameters["execution_log"].append("d2")
        if self.parameters.get("observed") is not None:
            self.parameters["observed"].append(float(states["protein"]["counts"]["A"]))
        return {"d2_consumed": {"A": 10}}


class _ReconcileBase:
    defaults = {"observed": None, "execution_log": None}

    def ports_schema(self):
        return {
            "protein": {"counts": {"A": {"_default": 100, "_updater": "set", "_emit": True}},
            },
            "d2_consumed": {"A": {"_default": 0, "_updater": "set", "_emit": True}},
        }

    def next_update(self, timestep, states):
        if self.parameters.get("execution_log") is not None:
            self.parameters["execution_log"].append(self.name)
        current = float(states["protein"]["counts"]["A"])
        consumed = float(states["d2_consumed"]["A"])
        if self.parameters.get("observed") is not None:
            self.parameters["observed"].append({"protein": current, "consumed": consumed})
        return {
            "protein": {"counts": {"A": current - consumed}},
            "d2_consumed": {"A": 0},
        }


class ReconcileStep(_ReconcileBase, Step):
    name = "reconcile_step"


class ReconcileDeriver(_ReconcileBase, Deriver):
    name = "reconcile_deriver"


def run(kind: str) -> dict[str, Any]:
    observed_d2: list[float] = []
    observed_reconcile: list[dict[str, float]] = []
    execution_log: list[str] = []
    m3 = M3StubSet({"execution_log": execution_log})
    d2 = D2StubConsumer({"observed": observed_d2, "execution_log": execution_log})
    if kind == "step":
        rec = ReconcileStep({"observed": observed_reconcile, "execution_log": execution_log})
    else:
        rec = ReconcileDeriver({"observed": observed_reconcile, "execution_log": execution_log})

    engine = Engine(
        processes={"m3": m3, "d2": d2},
        steps={"reconcile": rec},
        flow={"reconcile": []},
        topology={
            "m3": {"protein": ("protein",), "d2_consumed": ("d2_consumed",)},
            "d2": {"protein": ("protein",), "d2_consumed": ("d2_consumed",)},
            "reconcile": {"protein": ("protein",), "d2_consumed": ("d2_consumed",)},
        },
        initial_state={"protein": {"counts": {"A": 100}}, "d2_consumed": {"A": 0}},
        emit_step=1.0,
        display_info=False,
    )
    for _ in range(5):
        engine.update(1.0)
    ts = engine.emitter.get_timeseries()
    final_a = float(ts["protein"]["counts"]["A"][-1])
    return {
        "kind": kind,
        "d2_observed_protein_per_tick": observed_d2,
        "reconcile_observed_per_tick": observed_reconcile,
        "execution_log": execution_log,
        "final_protein_A": final_a,
        "final_d2_consumed_A": float(ts["d2_consumed"]["A"][-1]),
    }


def main() -> None:
    result = {
        "probe": "probe2_step",
        "step": run("step"),
        "deriver": run("deriver"),
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
