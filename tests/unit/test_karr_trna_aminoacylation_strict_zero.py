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

    monomer_enzyme_counts = {wid: 0.0 for wid in process.monomer_enzyme_wids}
    complex_enzyme_counts = {wid: 0.0 for wid in process.complex_enzyme_wids}
    for enzyme_wid in process.catalytic_enzyme_wids:
        if enzyme_wid in process.complex_enzyme_wids:
            complex_enzyme_counts[enzyme_wid] = 100.0
        else:
            monomer_enzyme_counts[enzyme_wid] = 100.0

    state = {
        "substrates": guarded_substrates,
        "rna": {
            "counts": {wid: 0.0 for wid in process.free_rna_wids},
            "aminoacylated_counts": {wid: 0.0 for wid in process.aminoacylated_rna_wids},
        },
        "protein": {"counts": monomer_enzyme_counts},
        "complex": {"counts": complex_enzyme_counts},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }
    state["rna"]["counts"][target_wid] = 10.0

    update = process.next_update(1.0, state)

    substrate_delta = update.get("substrates", {})
    for wid in process.substrate_wids:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12


def test_karr_trna_aminoacylation_accepts_legacy_rna_replay_keys() -> None:
    process = KarrTRNAAminoacylationProcess({"rng_seed": 1, "max_stochastic_iterations": 0})
    target_idx = 0

    legacy_free = np.zeros(len(process.free_rna_wids), dtype=np.float64)
    legacy_free[target_idx] = 4.0
    legacy_amino = np.zeros(len(process.aminoacylated_rna_wids), dtype=np.float64)
    seen: dict[str, np.ndarray] = {}

    def _fake_compute_rna_fluxes(
        *,
        free_rna: np.ndarray,
        substrates: np.ndarray,
        enzymes: np.ndarray,
    ) -> np.ndarray:
        _ = substrates, enzymes
        seen["free_rna"] = np.asarray(free_rna, dtype=np.float64)
        return np.zeros(len(process.free_rna_wids), dtype=np.int64)

    process._compute_rna_fluxes = _fake_compute_rna_fluxes  # type: ignore[method-assign]

    state = {
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "freeRNAs": legacy_free,
        "aminoacylatedRNAs": legacy_amino,
        "protein": {"counts": {wid: 100.0 for wid in process.monomer_enzyme_wids}},
        "complex": {"counts": {wid: 100.0 for wid in process.complex_enzyme_wids}},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }

    update = process.next_update(1.0, state)

    assert update == {}
    assert "free_rna" in seen
    assert float(seen["free_rna"][target_idx]) == 4.0
