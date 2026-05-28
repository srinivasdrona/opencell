from __future__ import annotations

from typing import Any

import numpy as np

from opencell.vivarium.karr_protein_modification import KarrProteinModificationProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wids: list[str]) -> None:
        super().__init__(values)
        self._blocked_wids = set(blocked_wids)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._blocked_wids:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def test_karr_protein_modification_strict_zero_no_global_fallback() -> None:
    process = KarrProteinModificationProcess({"rng_seed": 7})
    blocked_wids = list(process.substrate_wids)
    target_wid = process.unmodified_monomer_wids[0]

    substrate_values = {wid: 10_000.0 for wid in process.substrate_wids}
    guarded_substrates = _GuardedSubstrates(substrate_values, blocked_wids)

    state = {
        "substrates": guarded_substrates,
        "protein": {
            "counts": {wid: 2_000.0 for wid in process.enzyme_wids},
            "unmodified_counts": {wid: 0.0 for wid in process.unmodified_monomer_wids},
            "modified_counts": {wid: 0.0 for wid in process.modified_monomer_wids},
        },
        "complex": {"counts": {wid: 0.0 for wid in process.complex_enzyme_wids}},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }
    state["protein"]["unmodified_counts"][target_wid] = 1.0

    update = process.next_update(1.0, state)

    substrate_delta = update.get("substrates", {})
    for wid in process.substrate_wids:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12


def test_karr_protein_modification_accepts_unmodified_monomers_replay_key() -> None:
    process = KarrProteinModificationProcess({"rng_seed": 13})
    target_idx = 0
    legacy_unmodified = np.zeros(len(process.unmodified_monomer_wids), dtype=np.float64)
    legacy_unmodified[target_idx] = 3.0

    seen: dict[str, np.ndarray] = {}

    def _fake_sample_reaction_fluxes(
        *,
        unmodified: np.ndarray,
        substrates: np.ndarray,
        enzymes: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        _ = substrates, enzymes, dt
        seen["unmodified"] = np.asarray(unmodified, dtype=np.float64)
        return np.zeros(process.reaction_stoich.shape[1], dtype=np.int64)

    process._sample_reaction_fluxes = _fake_sample_reaction_fluxes  # type: ignore[method-assign]

    state = {
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "protein": {
            "counts": {wid: 1_000.0 for wid in process.enzyme_wids},
            "modified_counts": {wid: 0.0 for wid in process.modified_monomer_wids},
        },
        "complex": {"counts": {wid: 0.0 for wid in process.complex_enzyme_wids}},
        "unmodifiedMonomers": legacy_unmodified,
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }

    update = process.next_update(1.0, state)

    assert update == {}
    assert "unmodified" in seen
    assert float(seen["unmodified"][target_idx]) == 3.0
