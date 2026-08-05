from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from opencell.vivarium.karr_dna_repair import KarrDNARepairProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wids: Iterable[str]) -> None:
        super().__init__(values)
        self._blocked_wids = set(blocked_wids)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._blocked_wids:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def test_karr_dna_repair_strict_zero_no_global_fallback() -> None:
    process = KarrDNARepairProcess({"rng_seed": 11, "pathway_rate_scale": 500.0})
    blocked_wids = list(process.tracked_substrates)

    lesions = [{"site_id": f"x{i}", "damage_type": "double_strand_break"} for i in range(10)]
    substrate_values = {wid: 1.0e6 for wid in process.tracked_substrates}
    guarded_substrates = _GuardedSubstrates(substrate_values, blocked_wids)

    state = {
        "chromosome": {
            "damage_events_cumulative": lesions,
            "repair_events_cumulative": [],
            "repair_count": 0.0,
            "repair_count_by_pathway": {
                pathway: 0.0 for pathway in ("ber", "ner", "hr", "nhej_like")
            },
        },
        "protein": {"counts": {wid: float(cnt) for wid, cnt in process.enzyme_defaults.items()}},
        "complex": {"counts": {wid: 0.0 for wid in process.complex_enzyme_wids}},
        "substrates": guarded_substrates,
        "requests": {process.name: {wid: 0.0 for wid in process.tracked_substrates}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.tracked_substrates}},
    }

    update = process.next_update(1.0, state)

    substrate_delta = update.get("substrates", {})
    for wid in process.tracked_substrates:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12
