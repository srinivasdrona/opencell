from __future__ import annotations

from typing import Any

from opencell.vivarium.karr_rna_processing import KarrRNAProcessingProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wids: list[str]) -> None:
        super().__init__(values)
        self._blocked_wids = set(blocked_wids)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._blocked_wids:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def test_karr_rna_processing_strict_zero_no_global_fallback() -> None:
    process = KarrRNAProcessingProcess({"rng_seed": 0, "max_stochastic_iterations": 0})
    target_idx = int(process.unprocessed_rna_wids.index("TU_088"))

    substrate_values = {wid: 10_000.0 for wid in process.substrate_wids}
    guarded_substrates = _GuardedSubstrates(substrate_values, process.substrate_wids)

    state = {
        "substrates": guarded_substrates,
        "rna": {"counts": {wid: 0.0 for wid in process.rna_wids}},
        "protein": {"counts": {wid: 0.0 for wid in process.enzyme_wids}},
        "complex": {"counts": {wid: 0.0 for wid in process.complex_enzyme_wids}},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }
    state["rna"]["counts"][process.unprocessed_rna_wids[target_idx]] = 10.0

    for enzyme_idx, coeff in enumerate(process.reaction_catalysis[target_idx]):
        if coeff > 0:
            state["protein"]["counts"][process.enzyme_wids[enzyme_idx]] = 100.0

    update = process.next_update(1.0, state)

    substrate_delta = update.get("substrates", {})
    for wid in process.substrate_wids:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12
