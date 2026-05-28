from __future__ import annotations

from typing import Any

from opencell.vivarium.karr_protein_processing_i import KarrProteinProcessingIProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wids: list[str]) -> None:
        super().__init__(values)
        self._blocked_wids = set(blocked_wids)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._blocked_wids:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def test_karr_protein_processing_i_strict_zero_no_global_fallback() -> None:
    process = KarrProteinProcessingIProcess({"rng_seed": 11})

    substrate_values = {wid: 10_000.0 for wid in process.substrate_wids}
    guarded_substrates = _GuardedSubstrates(substrate_values, process.substrate_wids)
    target_wid = process.unprocessed_monomer_wids[0]

    state = {
        "substrates": guarded_substrates,
        "protein": {
            "unprocessed_counts": {wid: 0.0 for wid in process.unprocessed_monomer_wids},
            "processed_counts": {wid: 0.0 for wid in process.processed_monomer_wids},
            "counts": {wid: 100.0 for wid in process.enzyme_wids},
        },
        "complex": {"counts": {wid: 0.0 for wid in process.complex_enzyme_wids}},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }
    state["protein"]["unprocessed_counts"][target_wid] = 10.0

    update = process.next_update(1.0, state)

    substrate_delta = update.get("substrates", {})
    for wid in process.substrate_wids:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12
