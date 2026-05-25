from __future__ import annotations

from typing import Any

import numpy as np

from opencell.vivarium.karr_trna_aminoacylation import KarrTRNAAminoacylationProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wids: list[str]) -> None:
        super().__init__(values)
        self._blocked_wids = set(blocked_wids)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._blocked_wids:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def test_karr_trna_aminoacylation_strict_zero_no_global_fallback() -> None:
    process = KarrTRNAAminoacylationProcess({"rng_seed": 0, "max_stochastic_iterations": 0})

    atp_idx = process.substrate_wids.index("ATP")
    reaction_idx = int(np.flatnonzero(process.reaction_stoich[atp_idx, :] < 0)[0])
    target_idx = int(np.argmax(process.reaction_modification[reaction_idx]))
    target_wid = process.free_rna_wids[target_idx]

    substrate_values = {wid: 10_000.0 for wid in process.substrate_wids}
    guarded_substrates = _GuardedSubstrates(substrate_values, process.substrate_wids)

    enzyme_counts = {wid: 0.0 for wid in process.enzyme_wids}
    for enzyme_idx, coeff in enumerate(process.reaction_catalysis[reaction_idx]):
        if coeff > 0:
            enzyme_counts[process.enzyme_wids[enzyme_idx]] = 100.0

    state = {
        "substrates": guarded_substrates,
        "rna": {
            "counts": {wid: 0.0 for wid in process.free_rna_wids},
            "aminoacylated_counts": {wid: 0.0 for wid in process.aminoacylated_rna_wids},
        },
        "protein": {"counts": enzyme_counts},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }
    state["rna"]["counts"][target_wid] = 10.0

    update = process.next_update(1.0, state)

    substrate_delta = update.get("substrates", {})
    for wid in process.substrate_wids:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12
