from __future__ import annotations

from typing import Any

import numpy as np

from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wids: list[str]) -> None:
        super().__init__(values)
        self._blocked_wids = set(blocked_wids)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._blocked_wids:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def test_karr_protein_folding_strict_zero_no_global_fallback() -> None:
    process = KarrProteinFoldingProcess({"rng_seed": 3})
    blocked_wids = list(process.substrate_wids)

    target_idx = int(np.flatnonzero(process.chaperone_dependent_mask)[0])
    target_wid = process.unfolded_monomer_wids[target_idx]
    count_wids = list(dict.fromkeys([*process.folded_monomer_wids, *process.enzyme_wids]))

    substrate_values = {wid: 10_000.0 for wid in process.substrate_wids}
    guarded_substrates = _GuardedSubstrates(substrate_values, blocked_wids)

    state = {
        "substrates": guarded_substrates,
        "protein": {
            "counts": {wid: 100.0 for wid in count_wids},
            "unfolded_counts": {wid: 0.0 for wid in process.unfolded_monomer_wids},
        },
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }
    state["protein"]["unfolded_counts"][target_wid] = 1.0

    update = process.next_update(1.0, state)

    substrate_delta = update.get("substrates", {})
    for wid in process.substrate_wids:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12
