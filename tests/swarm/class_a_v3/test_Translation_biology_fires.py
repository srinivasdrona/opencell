"""Biology-firing canary for Translation v3 (swarm pilot Class A)."""

from __future__ import annotations

import numpy as np
import pytest
from vivarium.core.composition import simulate_process

from opencell.m3 import translation_v2 as tl_v2
from opencell.validation.predicates import (
    all_nonnegative,
    monotonically_decreasing,
    monotonically_increasing,
)
from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process


def test_Translation_fires() -> None:
    proc = KarrTranslationV3Process({})
    total_time = 30
    n_active = float(proc._fallback_n_active_ribosomes)

    initial = {
        "protein": {"unprocessed_counts": {pid: 0.0 for pid in proc.protein_ids}},
        "substrates": {aa: 1_000_000.0 for aa in proc.aa_ids},
        "complex": {"counts": {"RIBOSOME_70S": n_active}},
    }
    data = simulate_process(proc, {"total_time": total_time, "initial_state": initial})

    protein_matrix = np.array(
        [np.asarray(data["protein"]["unprocessed_counts"][pid], dtype=float) for pid in proc.protein_ids]
    )
    total_protein_series = protein_matrix.sum(axis=0)

    # Biology: active translation should increase newly synthesized polypeptide counts.
    assert total_protein_series[-1] > total_protein_series[0]
    assert monotonically_increasing(total_protein_series)

    # Biology: molecule counts are physical copy numbers and must stay non-negative.
    assert all_nonnegative(protein_matrix)

    synth_per_s = tl_v2.predict_synthesis_per_s(proc.mechanism_inputs, n_active=n_active)
    per_metabolite_per_s = (synth_per_s[:, None] * proc.kinetics_model.base_counts).sum(axis=0)
    for aa, col in zip(proc.aa_ids, proc.kinetics_model.aa_col_indices, strict=False):
        series = np.asarray(data["substrates"][aa], dtype=float)

        # Biology: amino-acid pools should decrease while translation is active.
        assert monotonically_decreasing(series)

        # Biology: with abundant starting pools, counts should not go negative in this window.
        assert all_nonnegative(series)

        # Stoichiometry: emitted AA deltas are deterministic in v3 and should integrate exactly.
        expected_final = initial["substrates"][aa] - float(per_metabolite_per_s[col]) * total_time
        assert series[-1] == pytest.approx(expected_final, rel=1e-9, abs=1e-6)

