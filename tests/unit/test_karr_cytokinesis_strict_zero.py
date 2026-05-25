from __future__ import annotations

from typing import Any

from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wid: str) -> None:
        super().__init__(values)
        self._blocked_wid = blocked_wid

    def get(self, key: str, default: Any = None) -> Any:
        if key == self._blocked_wid:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def test_karr_cytokinesis_strict_zero_no_global_fallback() -> None:
    process = KarrCytokinesisProcess({"active_division_rate_per_s": 0.2, "progress_per_gtp": 0.1})

    substrate_values = {wid: 0.0 for wid in process._substrate_wids}
    substrate_values[process.gtp_wid] = 10_000.0
    guarded_substrates = _GuardedSubstrates(substrate_values, process.gtp_wid)

    state = {
        "cell": {
            "ftsz_ring_complete": True,
            "division_progress": 0.0,
            "division_complete": False,
        },
        "chromosome": {"segregation_progress": 1.0},
        "substrates": guarded_substrates,
        "requests": {process.name: {process.gtp_wid: 0.0}},
        "substrates_allocated": {process.name: {process.gtp_wid: 0.0}},
    }

    update = process.next_update(1.0, state)

    assert abs(float(update.get("cell", {}).get("division_progress", 0.0))) <= 1.0e-12
    assert abs(float(update.get("substrates", {}).get(process.gtp_wid, 0.0))) <= 1.0e-12
