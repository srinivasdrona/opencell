from __future__ import annotations

from typing import Any, Iterable

from opencell.vivarium.karr_chromosome_segregation import KarrChromosomeSegregationProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wids: Iterable[str]) -> None:
        super().__init__(values)
        self._blocked_wids = set(blocked_wids)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._blocked_wids:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def _assert_zero_or_absent_substrate_delta(update: dict[str, Any], wids: Iterable[str]) -> None:
    substrate_delta = update.get("substrates", {})
    for wid in wids:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12


def test_karr_chromosome_segregation_strict_zero_no_global_fallback() -> None:
    process = KarrChromosomeSegregationProcess({"segregation_rate_per_s": 0.3})
    blocked_wids = [process.gtp_wid, process.h2o_wid]

    substrate_values = {wid: 0.0 for wid in process.substrate_wids}
    substrate_values[process.gtp_wid] = 10_000.0
    substrate_values[process.h2o_wid] = 10_000.0
    guarded_substrates = _GuardedSubstrates(substrate_values, blocked_wids)

    protein_counts = {wid: 0.0 for wid in process.enzyme_wids}
    for wid in process.required_enzyme_wids:
        protein_counts[wid] = 10.0

    state = {
        "chromosome": {
            "replication_state": "complete",
            "supercoiled": True,
            "segregation_progress": 0.0,
            "daughter_pole_positions": {"left": 0.0, "right": 0.0},
            "segregation_complete": False,
            "cell_cycle_event": "none",
        },
        "protein": {"counts": protein_counts},
        "substrates": guarded_substrates,
        "requests": {process.name: {process.gtp_wid: 0.0, process.h2o_wid: 0.0}},
        "substrates_allocated": {process.name: {process.gtp_wid: 0.0, process.h2o_wid: 0.0}},
    }

    update = process.next_update(1.0, state)

    assert abs(float(update.get("chromosome", {}).get("segregation_progress", 0.0))) <= 1.0e-12
    _assert_zero_or_absent_substrate_delta(update, blocked_wids)
