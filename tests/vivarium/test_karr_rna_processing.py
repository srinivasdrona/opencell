from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.vivarium.karr_composite import build_karr_chassis_v6
from opencell.vivarium.karr_rna_processing import KarrRNAProcessingProcess


def _blank_state(process: KarrRNAProcessingProcess) -> dict[str, Any]:
    return {
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "rna": {"counts": {wid: 0.0 for wid in process.rna_wids}},
        "protein": {"counts": {wid: 0.0 for wid in process.monomer_enzyme_wids}},
        "complex": {"counts": {wid: 0.0 for wid in process.complex_enzyme_wids}},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }


def _set_enzyme_count(
    process: KarrRNAProcessingProcess,
    state: dict[str, Any],
    wid: str,
    count: float,
) -> None:
    if wid in process.complex_enzyme_wids:
        state["complex"]["counts"][wid] = float(count)
        return
    state["protein"]["counts"][wid] = float(count)


def _enzyme_vector_from_state(
    process: KarrRNAProcessingProcess,
    state: dict[str, Any],
) -> np.ndarray:
    return process._enzyme_counts_from_stores(
        protein_count_store=state.get("protein", {}).get("counts", {}),
        complex_count_store=state.get("complex", {}).get("counts", {}),
    )


def _seed_reaction_inputs(
    process: KarrRNAProcessingProcess,
    state: dict[str, Any],
    ridx: int,
    substrate_scale: float = 100.0,
    enzyme_scale: float = 100.0,
) -> None:
    state["rna"]["counts"][process.unprocessed_rna_wids[ridx]] = 100.0

    for sidx, coeff in enumerate(process.reaction_stoich[:, ridx]):
        if coeff < 0:
            need = float(abs(coeff) * substrate_scale)
            wid = process.substrate_wids[sidx]
            state["substrates"][wid] = need
            state["substrates_allocated"][process.name][wid] = need

    req = process.reaction_catalysis[ridx]
    for eidx, coeff in enumerate(req):
        if coeff > 0:
            _set_enzyme_count(process, state, process.enzyme_wids[eidx], float(enzyme_scale))


def test_fixture_loads() -> None:
    p = KarrRNAProcessingProcess({})
    assert p.name == "karr_rna_processing"
    assert len(p.substrate_wids) == 7
    assert len(p.unprocessed_rna_wids) == 335
    assert len(p.processed_rna_wids) == 347
    assert len(p.enzyme_wids) == 5

    assert p.reaction_stoich.shape == (7, 335)
    assert p.reaction_stoich.dtype == np.int64
    assert p.reaction_catalysis.shape == (335, 5)
    assert p.reaction_catalysis.dtype == np.float64
    assert p.processed_output_matrix.shape == (347, 335)
    assert p.processed_output_matrix.dtype == np.int64


def test_no_unprocessed_no_action() -> None:
    p = KarrRNAProcessingProcess({})
    state = _blank_state(p)
    update = p.next_update(1.0, state)
    assert update == {}


def test_mass_conservation() -> None:
    p = KarrRNAProcessingProcess({"rng_seed": 7, "max_stochastic_iterations": 0})
    state = _blank_state(p)
    ridx = int(np.flatnonzero(np.any(p.reaction_catalysis > 0.0, axis=1))[0])
    _seed_reaction_inputs(p, state, ridx)

    unprocessed = np.array([state["rna"]["counts"][w] for w in p.unprocessed_rna_wids], dtype=float)
    substrates = np.array([state["substrates"][w] for w in p.substrate_wids], dtype=float)
    enzymes = _enzyme_vector_from_state(p, state)
    flux = p._compute_reaction_fluxes(
        unprocessed=unprocessed, substrates=substrates, enzymes=enzymes, dt=1.0
    )

    update = p.next_update(1.0, state)
    observed_sub = np.array(
        [int(update["substrates"].get(w, 0.0)) for w in p.substrate_wids], dtype=np.int64
    )
    expected_sub = p.reaction_stoich @ flux
    np.testing.assert_array_equal(observed_sub, expected_sub)


def test_enzyme_kinetics_limit() -> None:
    p = KarrRNAProcessingProcess({"rng_seed": 1, "max_stochastic_iterations": 0})
    state = _blank_state(p)
    ridx = int(p.unprocessed_rna_wids.index("TU_088"))
    _seed_reaction_inputs(p, state, ridx, substrate_scale=50.0, enzyme_scale=0.0)

    update_starved = p.next_update(1.0, state)
    assert update_starved == {}

    req = p.reaction_catalysis[ridx]
    for eidx, coeff in enumerate(req):
        if coeff > 0:
            _set_enzyme_count(p, state, p.enzyme_wids[eidx], 100.0)
    limiting_eidx = int(np.flatnonzero(req > 0)[0])
    _set_enzyme_count(p, state, p.enzyme_wids[limiting_eidx], 1.0)

    update = p.next_update(1.0, state)
    consumed = -int(update["rna"]["counts"].get(p.unprocessed_rna_wids[ridx], 0.0))
    enz = _enzyme_vector_from_state(p, state)
    max_from_enz = int(p._enzyme_limit(enz, dt=1.0)[ridx])

    assert consumed > 0
    assert consumed <= max_from_enz


def test_30s_cleavage_cascade() -> None:
    p = KarrRNAProcessingProcess({"rng_seed": 0, "max_stochastic_iterations": 0})
    state = _blank_state(p)
    ridx = int(p.unprocessed_rna_wids.index("TU_088"))
    _seed_reaction_inputs(p, state, ridx, substrate_scale=10.0, enzyme_scale=100.0)
    state["rna"]["counts"][p.unprocessed_rna_wids[ridx]] = 1.0

    update = p.next_update(1.0, state)
    assert update["rna"]["counts"].get("TU_088", 0.0) < 0.0
    assert update["rna"]["counts"].get("MGrrnA16S", 0.0) > 0.0
    assert update["rna"]["counts"].get("MGrrnA23S", 0.0) > 0.0
    assert update["rna"]["counts"].get("MGrrnA5S", 0.0) > 0.0


def test_deterministic_with_seed() -> None:
    p1 = KarrRNAProcessingProcess({"rng_seed": 42})
    p2 = KarrRNAProcessingProcess({"rng_seed": 42})

    state_1 = _blank_state(p1)
    active = np.flatnonzero(np.any(p1.reaction_catalysis > 0.0, axis=1))
    _seed_reaction_inputs(p1, state_1, int(active[0]), substrate_scale=20.0, enzyme_scale=50.0)
    _seed_reaction_inputs(p1, state_1, int(active[1]), substrate_scale=20.0, enzyme_scale=50.0)
    state_1["rna"]["counts"][p1.unprocessed_rna_wids[int(active[0])]] = 40.0
    state_1["rna"]["counts"][p1.unprocessed_rna_wids[int(active[1])]] = 40.0
    state_2 = deepcopy(state_1)

    update_1 = p1.next_update(1.0, state_1)
    update_2 = p2.next_update(1.0, state_2)
    assert update_1 == update_2


def test_no_substrate_no_action() -> None:
    p = KarrRNAProcessingProcess({"rng_seed": 0, "max_stochastic_iterations": 0})
    state = _blank_state(p)
    ridx = int(p.unprocessed_rna_wids.index("TU_088"))
    state["rna"]["counts"][p.unprocessed_rna_wids[ridx]] = 10.0

    req = p.reaction_catalysis[ridx]
    for eidx, coeff in enumerate(req):
        if coeff > 0:
            _set_enzyme_count(p, state, p.enzyme_wids[eidx], 100.0)

    update = p.next_update(1.0, state)
    assert update == {}


def test_chassis_seeded_complex_enzyme_controls_reaction_flux() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    process = composite["processes"]["karr_rna_processing"]
    state = composite["state"]

    complex_wid = "MG_367_DIMER"
    assert state["complex"]["counts"][complex_wid] > 0.0

    enzyme_idx = int(process.enzyme_wids.index(complex_wid))
    single_enzyme_mask = np.count_nonzero(process.reaction_catalysis > 0.0, axis=1) == 1
    ridx = int(
        np.flatnonzero(single_enzyme_mask & (process.reaction_catalysis[:, enzyme_idx] > 0.0))[0]
    )

    unprocessed = np.zeros(len(process.unprocessed_rna_wids), dtype=np.float64)
    unprocessed[ridx] = 1.0
    substrates = np.zeros(len(process.substrate_wids), dtype=np.float64)
    for sidx, coeff in enumerate(process.reaction_stoich[:, ridx]):
        if coeff < 0:
            substrates[sidx] = float(abs(coeff))

    enzymes = process._enzyme_counts_from_stores(
        protein_count_store=state["protein"]["counts"],
        complex_count_store=state["complex"]["counts"],
    )
    flux_with_complex = process._compute_reaction_fluxes(
        unprocessed=unprocessed,
        substrates=substrates,
        enzymes=enzymes,
        dt=1.0,
    )

    enzymes_without_complex = enzymes.copy()
    enzymes_without_complex[enzyme_idx] = 0.0
    flux_without_complex = process._compute_reaction_fluxes(
        unprocessed=unprocessed,
        substrates=substrates,
        enzymes=enzymes_without_complex,
        dt=1.0,
    )

    assert int(flux_with_complex[ridx]) == 1
    assert int(flux_without_complex[ridx]) == 0
