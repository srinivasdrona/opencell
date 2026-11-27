from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pytest

from opencell.vivarium.karr_protein_modification import KarrProteinModificationProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wids: list[str]) -> None:
        super().__init__(values)
        self._blocked_wids = set(blocked_wids)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._blocked_wids:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


@pytest.mark.parametrize("missing_grant", [False, True], ids=["zero-grant", "missing-grant"])
def test_karr_protein_modification_strict_zero_no_global_fallback(missing_grant: bool) -> None:
    process = KarrProteinModificationProcess({"rng_seed": 7})
    blocked_wids = list(process.substrate_wids)
    target_wid = process.unmodified_monomer_wids[0]

    substrate_values = {wid: 10_000.0 for wid in process.substrate_wids}
    guarded_substrates = _GuardedSubstrates(substrate_values, blocked_wids)

    state = {
        "substrates": guarded_substrates,
        "protein": {
            "counts": {wid: 2_000.0 for wid in process.monomer_enzyme_wids},
            "unmodified_counts": {wid: 0.0 for wid in process.unmodified_monomer_wids},
            "modified_counts": {wid: 0.0 for wid in process.modified_monomer_wids},
        },
        "complex": {"counts": {wid: 2_000.0 for wid in process.complex_enzyme_wids}},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }
    state["protein"]["unmodified_counts"][target_wid] = 1.0
    if missing_grant:
        del state["substrates_allocated"]
    before = deepcopy(state)

    update = process.next_update(1.0, state)

    substrate_delta = update.get("substrates", {})
    for wid in process.substrate_wids:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12
    assert update == {}
    assert state == before


@pytest.mark.parametrize("live_count", [None, 0.0, 3.0], ids=["missing-live", "zero-live", "live"])
def test_karr_protein_modification_live_folded_input_ignores_replay_shadow(live_count) -> None:
    """MATLAB copyFromState reads folded counts, never an independent replay shadow."""
    process = KarrProteinModificationProcess({"rng_seed": 13})
    target_idx = 0
    legacy_unmodified = np.zeros(len(process.unmodified_monomer_wids), dtype=np.float64)
    legacy_unmodified[target_idx] = 11.0

    state = {
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "protein": {
            "counts": {wid: 1_000.0 for wid in process.monomer_enzyme_wids},
            "modified_counts": {wid: 0.0 for wid in process.modified_monomer_wids},
        },
        "complex": {"counts": {wid: 1_000.0 for wid in process.complex_enzyme_wids}},
        "unmodifiedMonomers": legacy_unmodified,
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }
    if live_count is not None:
        state["protein"]["unmodified_counts"] = {
            process.unmodified_monomer_wids[target_idx]: live_count
        }
    before = deepcopy(state)
    unmodified, _ = process.live_inputs(state)
    expected = np.zeros(len(process.unmodified_monomer_wids))
    expected[target_idx] = live_count or 0
    np.testing.assert_array_equal(unmodified, expected)

    update = process.next_update(1.0, state)

    assert update == {}
    for key in state:
        if key == "unmodifiedMonomers":
            np.testing.assert_array_equal(state[key], before[key])
        else:
            assert state[key] == before[key]
