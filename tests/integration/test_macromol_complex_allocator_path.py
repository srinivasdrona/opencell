"""Integration checks for D2 allocation-gated substrate consumption."""

from __future__ import annotations

from typing import Any

import numpy as np

from opencell.vivarium.karr_macromolecular_complexation import MacromolecularComplexationProcess


def _snapshot_state(process: MacromolecularComplexationProcess) -> dict[str, Any]:
    rng = np.random.default_rng(20260525)
    substrate_counts = rng.integers(100, 1000, size=len(process.substrate_wids))
    return {
        "substrates": {
            wid: float(substrate_counts[idx]) for idx, wid in enumerate(process.substrate_wids)
        },
        "complex": {"counts": {wid: 0.0 for wid in process.complex_wids}},
    }


def test_macromol_complex_no_allocation_means_no_substrate_consumption() -> None:
    process = MacromolecularComplexationProcess({"rng_seed": 0})
    state = _snapshot_state(process)
    state["substrates_allocated"] = {
        process.name: {wid: 0.0 for wid in process.substrate_wids}
    }

    update = process.next_update(1.0, state)

    assert update["substrates"] == {}
    assert update["complex"]["counts"] == {}


def test_macromol_complex_consumption_is_bounded_by_allocated_budget() -> None:
    process = MacromolecularComplexationProcess({"rng_seed": 0})
    state = _snapshot_state(process)
    allocated = {
        wid: float(value) for wid, value in state["substrates"].items()
    }
    state["substrates_allocated"] = {process.name: allocated}

    update = process.next_update(1.0, state)
    consumed = {
        wid: max(0.0, -float(update["substrates"].get(wid, 0.0)))
        for wid in process.substrate_wids
    }

    assert sum(update["complex"]["counts"].values()) > 0.0
    assert all(consumed[wid] <= allocated[wid] for wid in process.substrate_wids)
