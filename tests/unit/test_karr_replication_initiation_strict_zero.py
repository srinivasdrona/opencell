from __future__ import annotations

from typing import Any, Iterable

from opencell.vivarium.karr_replication_initiation import KarrReplicationInitiationProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wids: Iterable[str]) -> None:
        super().__init__(values)
        self._blocked_wids = set(blocked_wids)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._blocked_wids:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def test_karr_replication_initiation_strict_zero_no_global_fallback() -> None:
    process = KarrReplicationInitiationProcess(
        {
            "rng_seed": 1,
            "binding_rate_scale": 1.0e12,
            "polymerization_rate_scale": 1.0e12,
            "release_rate_scale": 1.0e12,
            "inactivation_rate_scale": 1.0e24,
            "regen_rate_scale": 1.0e12,
        }
    )
    blocked_wids = [process.atp_wid, process.water_wid]

    substrate_values = {wid: 0.0 for wid in process.substrate_wids}
    substrate_values[process.atp_wid] = 10_000.0
    substrate_values[process.water_wid] = 10_000.0
    guarded_substrates = _GuardedSubstrates(substrate_values, blocked_wids)

    state = {
        "chromosome": {
            "dnaa_complex_count": {site_id: 0 for site_id in process.all_dnaa_sites},
            "replication_state": "idle",
            "supercoiled": False,
        },
        "protein": {"counts": {process.dnaa_wid: 8.0}},
        "substrates": guarded_substrates,
        "requests": {process.name: {process.atp_wid: 0.0, process.water_wid: 0.0}},
        "substrates_allocated": {process.name: {process.atp_wid: 0.0, process.water_wid: 0.0}},
    }

    update = process.next_update(1.0, state)

    substrate_delta = update.get("substrates", {})
    for wid in blocked_wids:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12
