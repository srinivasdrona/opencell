from __future__ import annotations

from typing import Any

from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wid: str) -> None:
        super().__init__(values)
        self._blocked_wid = blocked_wid

    def get(self, key: str, default: Any = None) -> Any:
        if key == self._blocked_wid:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def test_karr_protein_translocation_strict_zero_no_global_fallback() -> None:
    process = KarrProteinTranslocationProcess({"rng_seed": 3})
    target_wid = process.integral_membrane_wids[0]

    substrate_values = {wid: 0.0 for wid in process.substrate_wids}
    substrate_values[process.atp_wid] = 10_000.0
    guarded_substrates = _GuardedSubstrates(substrate_values, process.atp_wid)

    state = {
        "substrates": guarded_substrates,
        "protein": {
            "counts": {wid: 0.0 for wid in process.protein_count_wids},
            "location": {wid: "cytoplasm" for wid in process.translocatable_wids},
        },
        "requests": {process.name: {process.atp_wid: 0.0}},
        "substrates_allocated": {process.name: {process.atp_wid: 0.0}},
    }
    state["protein"]["counts"][target_wid] = 1.0
    state["protein"]["counts"][process.srp_wid] = 1.0
    state["protein"]["counts"][process.srp_receptor_wid] = 1.0
    state["protein"]["counts"][process.translocase_atpase_wid] = 1.0
    state["protein"]["counts"][process.translocase_pore_wid] = 1.0

    update = process.next_update(1.0, state)
    assert update == {}
