from __future__ import annotations

from typing import Any, Iterable

from opencell.vivarium.karr_chromosome_condensation import KarrChromosomeCondensationProcess


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


def test_karr_chromosome_condensation_strict_zero_no_global_fallback() -> None:
    process = KarrChromosomeCondensationProcess(
        {
            "rng_seed": 5,
            "binding_relaxation_time_s": 0.5,
            "trace_gap_tolerance_for_binding": 0.0,
            "fork_pause_probability": 0.0,
            "displacement_rate_per_s": 0.0,
        }
    )
    blocked_wids = [process.atp_wid, process.water_wid]

    substrate_values = {wid: 0.0 for wid in process.substrate_wids}
    substrate_values[process.atp_wid] = 50_000.0
    substrate_values[process.water_wid] = 50_000.0
    guarded_substrates = _GuardedSubstrates(substrate_values, blocked_wids)

    state = {
        "chromosome": {
            "smc_bound_count": 0.0,
            "condensation_level": 0.0,
            "replication_state": "idle",
            "forks_passing": False,
        },
        "substrates": guarded_substrates,
        "requests": {process.name: {process.atp_wid: 0.0, process.water_wid: 0.0}},
        "substrates_allocated": {process.name: {process.atp_wid: 0.0, process.water_wid: 0.0}},
    }

    update = process.next_update(1.0, state)

    assert abs(float(update.get("chromosome", {}).get("smc_bound_count", 0.0))) <= 1.0e-12
    _assert_zero_or_absent_substrate_delta(update, blocked_wids)
