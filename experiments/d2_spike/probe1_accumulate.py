"""Probe 1: Vivarium accumulate semantics across ticks and writers."""

from __future__ import annotations

import json
from pathlib import Path

from vivarium.core.engine import Engine
from vivarium.core.process import Process


ARTIFACT_DIR = Path("artifacts")
ARTIFACT_DIR.mkdir(exist_ok=True)
OUT = ARTIFACT_DIR / "d2_probe1_results.json"


class SignedAccumulator(Process):
    name = "signed_accumulator"
    defaults = {"deltas_per_tick": []}

    def __init__(self, parameters=None):
        super().__init__(parameters)
        self.step_trace: list[int] = []
        self.persist_write_ok = True
        self.persist_error = ""

    def ports_schema(self):
        return {"store": {"x": {"_default": 100, "_updater": "accumulate", "_emit": True}}}

    def next_update(self, timestep, states):
        step = int(self.parameters.get("_step", 0))
        self.step_trace.append(step)
        deltas = self.parameters["deltas_per_tick"]
        d = int(deltas[step]) if step < len(deltas) else 0
        try:
            self.parameters["_step"] = step + 1
        except Exception as e:  # noqa: BLE001
            self.persist_write_ok = False
            self.persist_error = repr(e)
        return {"store": {"x": d}}


def final_x(engine: Engine) -> float:
    ts = engine.emitter.get_timeseries()
    xs = ts["store"]["x"]
    return float(xs[-1])


def run_single_writer():
    proc = SignedAccumulator({"deltas_per_tick": [5, -3, 0, -10, 20]})
    engine = Engine(
        processes={"acc": proc},
        topology={"acc": {"store": ("store",)}},
        emit_step=1.0,
        display_info=False,
    )
    for _ in range(5):
        engine.update(1.0)
    ts = engine.emitter.get_timeseries()
    return {
        "expected_final_x": 112,
        "observed_final_x": final_x(engine),
        "step_trace": proc.step_trace,
        "parameters_persist_write_ok": proc.persist_write_ok,
        "parameters_persist_error": proc.persist_error,
        "timeseries_len": len(ts["time"]),
    }


def run_two_writers():
    p1 = SignedAccumulator({"deltas_per_tick": [5, 0, 0, 0, 0]})
    p2 = SignedAccumulator({"deltas_per_tick": [7, 0, 0, 0, 0]})
    engine = Engine(
        processes={"acc1": p1, "acc2": p2},
        topology={"acc1": {"store": ("store",)}, "acc2": {"store": ("store",)}},
        emit_step=1.0,
        display_info=False,
    )
    for _ in range(5):
        engine.update(1.0)
    return {
        "expected_final_x_if_summed": 112,  # 100 + 5 + 7
        "observed_final_x": final_x(engine),
        "acc1_step_trace": p1.step_trace,
        "acc2_step_trace": p2.step_trace,
    }


def main() -> None:
    result = {
        "probe": "probe1_accumulate",
        "single_writer": run_single_writer(),
        "two_writers_same_port": run_two_writers(),
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
