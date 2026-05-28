from __future__ import annotations

from typing import Any

import numpy as np

from opencell.vivarium.karr_rna_modification import KarrRNAModificationProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wids: list[str]) -> None:
        super().__init__(values)
        self._blocked_wids = set(blocked_wids)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._blocked_wids:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def _split_enzyme_counts(
    process: KarrRNAModificationProcess, values_by_wid: dict[str, float]
) -> tuple[dict[str, float], dict[str, float]]:
    protein_counts: dict[str, float] = {}
    complex_counts: dict[str, float] = {}
    for wid in process.enzyme_wids:
        value = float(values_by_wid.get(wid, 0.0))
        if wid in process.complex_enzyme_wids:
            complex_counts[wid] = value
        else:
            protein_counts[wid] = value
    return protein_counts, complex_counts


def test_karr_rna_modification_strict_zero_no_global_fallback() -> None:
    process = KarrRNAModificationProcess({"rng_seed": 7})

    target_idx = int(np.argmin(process.required_reactions_per_rna))
    target_wid = process.unmodified_rna_wids[target_idx]
    reaction_idx = int(np.flatnonzero(process.reaction_modification[:, target_idx] > 0)[0])

    substrate_values = {wid: 10_000.0 for wid in process.substrate_wids}
    guarded_substrates = _GuardedSubstrates(substrate_values, process.substrate_wids)

    enzyme_counts = {wid: 0.0 for wid in process.enzyme_wids}
    for enzyme_idx, flag in enumerate(process.reaction_catalysis[reaction_idx]):
        if flag > 0:
            enzyme_counts[process.enzyme_wids[enzyme_idx]] = 10_000.0
    protein_counts, complex_counts = _split_enzyme_counts(process, enzyme_counts)

    state = {
        "substrates": guarded_substrates,
        "rna": {
            "counts": {wid: 0.0 for wid in process.unmodified_rna_wids},
            "modified_counts": {wid: 0.0 for wid in process.modified_rna_wids},
        },
        "protein": {"counts": protein_counts},
        "complex": {"counts": complex_counts},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }
    state["rna"]["counts"][target_wid] = 1.0

    update = process.next_update(1.0, state)

    substrate_delta = update.get("substrates", {})
    for wid in process.substrate_wids:
        assert abs(float(substrate_delta.get(wid, 0.0))) <= 1.0e-12


def test_karr_rna_modification_accepts_legacy_rna_replay_keys() -> None:
    process = KarrRNAModificationProcess({"rng_seed": 9})
    target_idx = 0
    legacy_unmodified = np.zeros(len(process.unmodified_rna_wids), dtype=np.float64)
    legacy_unmodified[target_idx] = 2.0
    legacy_modified = np.zeros(len(process.modified_rna_wids), dtype=np.float64)

    seen: dict[str, np.ndarray] = {}

    def _fake_compute_reaction_fluxes(
        *,
        unmodified_rna: np.ndarray,
        substrates: np.ndarray,
        enzymes: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        _ = substrates, enzymes, dt
        seen["unmodified_rna"] = np.asarray(unmodified_rna, dtype=np.float64)
        return np.zeros(process.reaction_stoich.shape[1], dtype=np.int64)

    process._compute_reaction_fluxes = _fake_compute_reaction_fluxes  # type: ignore[method-assign]

    enzyme_counts = {wid: 1000.0 for wid in process.enzyme_wids}
    protein_counts, complex_counts = _split_enzyme_counts(process, enzyme_counts)

    state = {
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "unmodifiedRNAs": legacy_unmodified,
        "modifiedRNAs": legacy_modified,
        "protein": {"counts": protein_counts},
        "complex": {"counts": complex_counts},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }

    update = process.next_update(1.0, state)

    assert update == {}
    assert "unmodified_rna" in seen
    assert float(seen["unmodified_rna"][target_idx]) == 2.0
