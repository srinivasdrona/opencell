"""Vivarium Step implementing Karr's proportional fair-share allocation."""

from __future__ import annotations

import math
from typing import Any

from vivarium.core.process import Step

from opencell.m1 import karr_metabolism as km


def _default_substrate_wids() -> list[str]:
    """Return Karr's full substrate WID universe (585 IDs in M1 fixtures)."""
    model = km.load_default()
    return [str(wid) for wid in model.raw["ids"]["substrate_wcm_585"]]


def _default_consumer_processes() -> list[tuple[str, list[str]]]:
    """Default consumers expected for A3.3 allocation integration."""
    return [
        ("d2_real", ["ATP", "GTP", "H2O"]),
        ("protein_decay_light", ["ATP", "H2O"]),
        ("karr_rna_decay", ["H2O"]),
    ]


class KarrAllocationStep(Step):
    """Allocate shared substrates by Karr's per-WID proportional fair share."""

    name = "karr_allocation_step"
    defaults: dict[str, Any] = {
        "consumer_processes": _default_consumer_processes(),
        "substrate_wids": _default_substrate_wids(),
    }

    def ports_schema(self) -> dict[str, Any]:
        consumers = self.parameters["consumer_processes"]
        substrate_wids = self.parameters["substrate_wids"]
        return {
            "substrates": {
                wid: {
                    "_updater": "accumulate",
                    "_default": 0.0,
                    "_emit": False,
                }
                for wid in substrate_wids
            },
            "requests": {
                proc_name: {
                    wid: {
                        "_updater": "set",
                        "_default": 0.0,
                        "_emit": False,
                    }
                    for wid in wids
                }
                for proc_name, wids in consumers
            },
            # Sole-writer exception: this step exclusively writes allocations,
            # so set-updates are safe and replace each tick's values.
            "substrates_allocated": {
                proc_name: {
                    wid: {
                        "_updater": "set",
                        "_default": 0.0,
                        "_emit": False,
                    }
                    for wid in wids
                }
                for proc_name, wids in consumers
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        substrates = states.get("substrates", {})
        requests = states.get("requests", {})

        all_requested_wids: set[str] = set()
        for reqs_by_wid in requests.values():
            all_requested_wids.update(reqs_by_wid.keys())

        allocations: dict[str, dict[str, float]] = {}
        for wid in all_requested_wids:
            supply = max(0.0, float(substrates.get(wid, 0.0)))
            total_demand = sum(
                max(0.0, float(requests[proc_name].get(wid, 0.0))) for proc_name in requests
            )
            scale = min(1.0, supply / total_demand) if total_demand > 0.0 else 0.0

            for proc_name in requests:
                req = max(0.0, float(requests[proc_name].get(wid, 0.0)))
                allocated = math.floor(req * scale)
                allocations.setdefault(proc_name, {})[wid] = float(allocated)

        return {"substrates_allocated": allocations}
