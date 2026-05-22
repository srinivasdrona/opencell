"""Unit and wiring tests for KarrAllocationStep."""
from __future__ import annotations

from typing import Any

from vivarium.core.engine import Engine
from vivarium.core.process import Process, Step

from opencell.vivarium.karr_allocation_step import KarrAllocationStep


def _make_step(consumer_wids: dict[str, list[str]]) -> KarrAllocationStep:
    consumer_processes = [(proc_name, wids) for proc_name, wids in consumer_wids.items()]
    all_wids = sorted({wid for wids in consumer_wids.values() for wid in wids})
    return KarrAllocationStep(
        {
            "consumer_processes": consumer_processes,
            "substrate_wids": all_wids,
        }
    )


def _run_allocation(
    *,
    substrates: dict[str, float],
    requests: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    consumer_wids = {proc: sorted(reqs.keys()) for proc, reqs in requests.items()}
    step = _make_step(consumer_wids)
    update = step.next_update(
        1.0,
        {
            "substrates": substrates,
            "requests": requests,
        },
    )
    return update["substrates_allocated"]


def test_under_demand_everyone_full() -> None:
    allocated = _run_allocation(
        substrates={"ATP": 100.0},
        requests={"consumer_a": {"ATP": 30.0}, "consumer_b": {"ATP": 50.0}},
    )
    assert allocated["consumer_a"]["ATP"] == 30.0
    assert allocated["consumer_b"]["ATP"] == 50.0


def test_over_demand_proportional_floor() -> None:
    allocated = _run_allocation(
        substrates={"ATP": 10.0},
        requests={"consumer_a": {"ATP": 30.0}, "consumer_b": {"ATP": 20.0}},
    )
    assert allocated["consumer_a"]["ATP"] == 6.0
    assert allocated["consumer_b"]["ATP"] == 4.0


def test_exact_supply() -> None:
    allocated = _run_allocation(
        substrates={"ATP": 50.0},
        requests={"consumer_a": {"ATP": 30.0}, "consumer_b": {"ATP": 20.0}},
    )
    assert allocated["consumer_a"]["ATP"] == 30.0
    assert allocated["consumer_b"]["ATP"] == 20.0


def test_zero_request_consumer() -> None:
    allocated = _run_allocation(
        substrates={"ATP": 100.0},
        requests={"consumer_a": {"ATP": 0.0}, "consumer_b": {"ATP": 50.0}},
    )
    assert allocated["consumer_a"]["ATP"] == 0.0
    assert allocated["consumer_b"]["ATP"] == 50.0


def test_zero_supply() -> None:
    allocated = _run_allocation(
        substrates={"ATP": 0.0},
        requests={"consumer_a": {"ATP": 30.0}, "consumer_b": {"ATP": 20.0}},
    )
    assert allocated["consumer_a"]["ATP"] == 0.0
    assert allocated["consumer_b"]["ATP"] == 0.0


def test_integer_floor_edge_case() -> None:
    allocated = _run_allocation(
        substrates={"ATP": 10.0},
        requests={"consumer_a": {"ATP": 7.0}, "consumer_b": {"ATP": 5.0}},
    )
    assert allocated["consumer_a"]["ATP"] == 5.0
    assert allocated["consumer_b"]["ATP"] == 4.0


def test_step_chain_propagation() -> None:
    class ToyRequestCalc(Step):
        """Writes a fixed request for one process + WID to requests.<proc>.<wid>."""

        defaults = {"proc_name": "consumer_a", "wid": "ATP", "value": 30}

        def ports_schema(self) -> dict[str, Any]:
            return {
                "requests": {
                    self.parameters["proc_name"]: {
                        self.parameters["wid"]: {
                            "_default": 0.0,
                            "_updater": "set",
                            "_emit": False,
                        }
                    }
                }
            }

        def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
            del timestep, states
            return {
                "requests": {
                    self.parameters["proc_name"]: {
                        self.parameters["wid"]: float(self.parameters["value"])
                    }
                }
            }

    class TickDriver(Process):
        defaults = {"time_step": 1.0}

        def ports_schema(self) -> dict[str, Any]:
            return {"driver": {"_default": 0.0, "_updater": "set", "_emit": False}}

        def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
            del timestep, states
            return {}

    engine = Engine(
        processes={"tick_driver": TickDriver()},
        steps={
            "request_a": ToyRequestCalc({"proc_name": "consumer_a", "wid": "ATP", "value": 30}),
            "request_b": ToyRequestCalc({"proc_name": "consumer_b", "wid": "ATP", "value": 50}),
            "allocation": KarrAllocationStep(
                {
                    "consumer_processes": [
                        ("consumer_a", ["ATP"]),
                        ("consumer_b", ["ATP"]),
                    ],
                    "substrate_wids": ["ATP"],
                }
            ),
        },
        flow={
            "request_a": [],
            "request_b": [],
            "allocation": [("request_a",), ("request_b",)],
        },
        topology={
            "tick_driver": {"driver": ("driver",)},
            "request_a": {"requests": ("requests",)},
            "request_b": {"requests": ("requests",)},
            "allocation": {
                "substrates": ("substrates",),
                "requests": ("requests",),
                "substrates_allocated": ("substrates_allocated",),
            },
        },
        initial_state={"substrates": {"ATP": 50.0}},
        emit_step=1.0,
        display_info=False,
    )
    engine.update(1.0)
    state = engine.state.get_value()
    assert state["substrates_allocated"]["consumer_a"]["ATP"] == 18.0
    assert state["substrates_allocated"]["consumer_b"]["ATP"] == 31.0


def test_multi_wid_independent_allocation() -> None:
    allocated = _run_allocation(
        substrates={"ATP": 10.0, "GTP": 9.0},
        requests={
            "consumer_a": {"ATP": 30.0, "GTP": 3.0},
            "consumer_b": {"ATP": 20.0, "GTP": 9.0},
        },
    )
    assert allocated["consumer_a"]["ATP"] == 6.0
    assert allocated["consumer_b"]["ATP"] == 4.0
    assert allocated["consumer_a"]["GTP"] == 2.0
    assert allocated["consumer_b"]["GTP"] == 6.0

