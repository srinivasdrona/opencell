"""Sampler initialization controls, not biological no-op fidelity evidence."""

import pickle

import _l2_2_design_a_runner_helpers as adapters
import numpy as np
import pytest

from opencell.vivarium.protein_state import COMPARTMENTS


@pytest.mark.parametrize("advance_metadata", [False, True], ids=["repeat", "advanced_metadata"])
def test_translocation_execution_owns_fresh_sample_rng(advance_metadata, monkeypatch):
    seed = adapters._sample_seed(0, 0)
    factory = adapters._protein_translocation_process
    reference = factory.__wrapped__(seed)
    expected_rng = pickle.dumps(reference._rng, protocol=pickle.HIGHEST_PROTOCOL)
    cached = factory(seed)
    if advance_metadata:
        cached._rng.rand()
    before = {
        "substrate_wids": list(reference.substrate_wids),
        "enzyme_wids": list(reference.enzyme_wids),
        "monomer_wids": list(reference.monomer_wids),
        "oracle_before_substrates": np.zeros(len(reference.substrate_wids)),
        "oracle_before_enzymes": np.zeros(len(reference.enzyme_wids)),
        "oracle_before_bound_enzymes": np.zeros(len(reference.enzyme_wids)),
        "oracle_before_monomers": np.zeros(
            len(COMPARTMENTS) * len(reference.monomer_wids)
        ),
    }
    seen = []
    process_class = type(reference)
    original = process_class.next_update

    def observe(owner, timestep, state):
        seen.append((owner, pickle.dumps(owner._rng, protocol=pickle.HIGHEST_PROTOCOL)))
        return original(owner, timestep, state)

    monkeypatch.setattr(process_class, "next_update", observe)
    first = adapters.run_oc_tick("ProteinTranslocation", 0, 0, before)
    second = adapters.run_oc_tick("ProteinTranslocation", 0, 0, before)
    assert len(seen) == 2, "check real public execution, not a metadata facade"
    assert seen[0][0] is not seen[1][0], "execution must not reuse a mutable cached owner"
    assert all(owner is not cached for owner, _ in seen)
    assert all(state == expected_rng for _, state in seen)
    for channel in ("substrates", "monomers"):
        np.testing.assert_array_equal(first[channel], second[channel])
    assert first["sample_seed"] == second["sample_seed"] == seed
