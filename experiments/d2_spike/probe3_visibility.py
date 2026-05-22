"""Probe 3: Same-tick visibility and insertion-order dependence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vivarium.core.engine import Engine
from vivarium.core.process import Process


ARTIFACT_DIR = Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)
OUT = ARTIFACT_DIR / "d2_probe3_results.json"


class Writer(Process):
    name = "writer"

    def ports_schema(self):
        return {"protein": {"counts": {"A": {"_default": 100, "_updater": "set", "_emit": True}}}}

    def next_update(self, timestep, states):
        return {"protein": {"counts": {"A": 200}}}


class Reader(Process):
    name = "reader"
    defaults = {"observed": None}

    def ports_schema(self):
        return {"protein": {"counts": {"A": {"_default": 100, "_updater": "set", "_emit": True}}}}

    def next_update(self, timestep, states):
        if self.parameters.get("observed") is not None:
            self.parameters["observed"].append(float(states["protein"]["counts"]["A"]))
        return {}


def run(order: str) -> dict[str, Any]:
    observed: list[float] = []
    w = Writer()
    r = Reader({"observed": observed})
    if order == "writer_then_reader":
        processes = {"writer": w, "reader": r}
    else:
        processes = {"reader": r, "writer": w}
    topology = {
        "writer": {"protein": ("protein",)},
        "reader": {"protein": ("protein",)},
    }
    engine = Engine(
        processes=processes,
        topology=topology,
        initial_state={"protein": {"counts": {"A": 100}}},
        emit_step=1.0,
        display_info=False,
    )
    for _ in range(5):
        engine.update(1.0)
    ts = engine.emitter.get_timeseries()
    return {
        "order": order,
        "reader_observed_per_tick": observed,
        "final_protein_A": float(ts["protein"]["counts"]["A"][-1]),
    }


def main() -> None:
    result = {
        "probe": "probe3_visibility",
        "writer_then_reader": run("writer_then_reader"),
        "reader_then_writer": run("reader_then_writer"),
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
