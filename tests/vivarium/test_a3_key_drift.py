from __future__ import annotations

import inspect
from typing import Any

import numpy as np
import pytest

from opencell.vivarium.karr_allocation_step import KarrAllocationStep
from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess


class _FixedPoissonRng:
    def __init__(self, draw: int) -> None:
        self._draw = int(draw)

    def poisson(self, lam: np.ndarray) -> np.ndarray:
        lam = np.asarray(lam, dtype=np.float64)
        return np.full(lam.shape, self._draw, dtype=np.int64)


def _build_pd_state(
    process: ProteinDecayLightProcess,
    complex_counts: dict[str, float],
) -> dict[str, Any]:
    return {
        "complex": {"counts": {wid: float(complex_counts.get(wid, 0.0)) for wid in process.complex_wids}},
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "protein": {"counts": {wid: 0.0 for wid in process.protein_wids}},
        "rna": {"counts": {wid: 0.0 for wid in process.rna_wids}},
        "requests": {"karr_protein_decay_light": {"ATP": 0.0, "H2O": 0.0}},
        "substrates_allocated": {"karr_protein_decay_light": {"ATP": 0.0, "H2O": 0.0}},
    }


def test_allocator_normalizes_legacy_consumer_keys_and_requests() -> None:
    if "opencell-worktrees/trackA-a3-keys" not in inspect.getfile(KarrAllocationStep):
        pytest.skip("environment imported allocator module from a non-worktree path")

    step = KarrAllocationStep(
        {
            "consumer_processes": [
                ("d2_real", ["ATP"]),
                ("karr_macromolecular_complexation", ["ATP", "H2O"]),
                ("protein_decay_light", ["ATP"]),
                ("karr_protein_decay_light", ["H2O"]),
            ],
            "substrate_wids": ["ATP", "H2O"],
        }
    )

    update = step.next_update(
        1.0,
        {
            "substrates": {"ATP": 10.0, "H2O": 10.0},
            "requests": {
                "d2_real": {"ATP": 3.0},
                "karr_macromolecular_complexation": {"ATP": 1.0},
                "protein_decay_light": {"ATP": 6.0},
                "karr_protein_decay_light": {"H2O": 7.0},
            },
        },
    )

    allocated = update["substrates_allocated"]
    assert allocated["karr_macromolecular_complexation"]["ATP"] == 4.0
    assert allocated["karr_protein_decay_light"]["ATP"] == 6.0
    assert allocated["karr_macromolecular_complexation"]["H2O"] == 0.0
    assert allocated["karr_protein_decay_light"]["H2O"] == 7.0


def test_protein_decay_zero_allocator_request_emits_no_negative_substrate_deltas() -> None:
    if "opencell-worktrees/trackA-a3-keys" not in inspect.getfile(ProteinDecayLightProcess):
        pytest.skip("environment imported protein-decay module from a non-worktree path")

    baseline = ProteinDecayLightProcess({})
    atp_row = baseline.complex_decay_reactions[baseline.substrate_index_atp, :]
    h2o_row = baseline.complex_decay_reactions[baseline.substrate_index_water, :]
    candidate_cols = np.flatnonzero((atp_row == 0) & (h2o_row == 0))
    assert candidate_cols.size > 0

    wid = baseline.complex_wids[int(candidate_cols[0])]
    process = ProteinDecayLightProcess({"complex_wid_filter": [wid]})
    process._rng = _FixedPoissonRng(10_000)
    update = process.next_update(1.0, _build_pd_state(process, {wid: 4.0}))

    assert update["requests"]["karr_protein_decay_light"]["ATP"] == 0.0
    assert update["requests"]["karr_protein_decay_light"]["H2O"] == 0.0
    assert all(delta >= 0.0 for delta in update.get("substrates", {}).values())
