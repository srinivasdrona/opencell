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

from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess


def _build_state(
    process: KarrProteinProcessingIIProcess,
    *,
    target_lipoprotein_count: float = 0.0,
    non_lipoprotein_count: float = 0.0,
    dag_available: float = 1_000.0,
    water_available: float = 1_000.0,
    dag_enzyme: float = 10_000.0,
    cleavage_enzyme: float = 10_000.0,
) -> dict[str, Any]:
    substrates = {wid: 100.0 for wid in process.substrate_wids}
    substrates[process.substrate_wids[process.substrate_index_dag]] = float(dag_available)
    substrates[process.substrate_wids[process.substrate_index_water]] = float(water_available)

    processed = {wid: 0.0 for wid in process.processed_monomer_wids}
    unfolded = {wid: 0.0 for wid in process.processed_monomer_wids}
    signal = {wid: 0.0 for wid in process.signal_sequence_monomer_wids}
    enzymes = {wid: 0.0 for wid in process.enzyme_wids}

    target_idx = int(process.lipoprotein_indices[0])
    target_wid = process.processed_monomer_wids[target_idx]
    processed[target_wid] = float(target_lipoprotein_count)

    non_lipo_idx = int(process.non_lipo_non_cleaved_indices[0])
    non_lipo_wid = process.processed_monomer_wids[non_lipo_idx]
    processed[non_lipo_wid] = float(non_lipoprotein_count)

    enzymes[process.enzyme_wids[process.enzyme_index_dag_transferase]] = float(dag_enzyme)
    enzymes[process.enzyme_wids[process.enzyme_index_signal_peptidase]] = float(cleavage_enzyme)

    return {
        "substrates": substrates,
        "protein": {
            "processed_counts": processed,
            "unfolded_counts": unfolded,
            "signal_sequence_counts": signal,
            "enzyme_counts": enzymes,
        },
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: deepcopy(substrates)},
    }


def _apply_update(
    state: dict[str, Any],
    update: dict[str, Any],
    process: KarrProteinProcessingIIProcess,
) -> None:
    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0) + float(delta))
        state["substrates_allocated"][process.name][wid] = float(state["substrates"][wid])

    for store_name in ("processed_counts", "unfolded_counts", "signal_sequence_counts"):
        for wid, delta in update.get("protein", {}).get(store_name, {}).items():
            state["protein"][store_name][wid] = float(
                state["protein"][store_name].get(wid, 0.0) + float(delta)
            )


def test_fixture_loads() -> None:
    p = KarrProteinProcessingIIProcess({})
    assert p.name == "karr_protein_processing_ii"
    assert len(p.substrate_wids) == 5
    assert len(p.enzyme_wids) == 2
    assert len(p.lipoprotein_indices) > 0
    assert p.reaction_stoich.shape == (len(p.substrate_wids), 2 * len(p.lipoprotein_indices))
    assert p.reaction_catalysis.shape == (2 * len(p.lipoprotein_indices), len(p.enzyme_wids))
    assert p.reaction_modification.shape == (
        2 * len(p.lipoprotein_indices),
        len(p.lipoprotein_indices),
    )
    assert np.all(p.required_reactions == 2)


def test_non_lipoprotein_pass_through_to_unfolded() -> None:
    p = KarrProteinProcessingIIProcess({"rng_seed": 7})
    state = _build_state(p, target_lipoprotein_count=0.0, non_lipoprotein_count=7.0)

    non_lipo_idx = int(p.non_lipo_non_cleaved_indices[0])
    non_lipo_wid = p.processed_monomer_wids[non_lipo_idx]

    update = p.next_update(1.0, state)
    _apply_update(state, update, p)

    assert float(state["protein"]["processed_counts"][non_lipo_wid]) == 0.0
    assert float(state["protein"]["unfolded_counts"][non_lipo_wid]) == 7.0


def test_dag_transfer_then_cleave() -> None:
    p = KarrProteinProcessingIIProcess({"rng_seed": 11})
    state = _build_state(
        p, target_lipoprotein_count=1.0, dag_enzyme=20_000.0, cleavage_enzyme=20_000.0
    )
    target_idx = int(p.lipoprotein_indices[0])
    target_wid = p.processed_monomer_wids[target_idx]

    for _ in range(2):
        update = p.next_update(1.0, state)
        _apply_update(state, update, p)
        if float(state["protein"]["unfolded_counts"][target_wid]) >= 1.0:
            break

    assert float(state["protein"]["processed_counts"][target_wid]) == 0.0
    assert float(state["protein"]["unfolded_counts"][target_wid]) == 1.0
    assert int(p._n_completed[0]) == 0


def test_partial_progress_no_transition() -> None:
    p = KarrProteinProcessingIIProcess({"rng_seed": 5})
    state = _build_state(
        p,
        target_lipoprotein_count=1.0,
        dag_enzyme=20_000.0,
        cleavage_enzyme=0.0,
        dag_available=100.0,
        water_available=100.0,
    )
    target_idx = int(p.lipoprotein_indices[0])
    target_wid = p.processed_monomer_wids[target_idx]

    update = p.next_update(1.0, state)

    assert update.get("substrates", {}).get(p.substrate_wids[p.substrate_index_dag], 0.0) < 0.0
    assert update.get("protein", {}).get("processed_counts", {}).get(target_wid, 0.0) == 0.0
    assert update.get("protein", {}).get("unfolded_counts", {}).get(target_wid, 0.0) == 0.0
    assert int(p._n_completed[0]) == 1


def test_mass_conservation() -> None:
    p = KarrProteinProcessingIIProcess({"rng_seed": 9, "max_stochastic_iterations": 0})
    state = _build_state(
        p,
        target_lipoprotein_count=3.0,
        dag_available=100.0,
        water_available=100.0,
        dag_enzyme=40_000.0,
        cleavage_enzyme=40_000.0,
    )

    substrates = np.asarray(
        [state["substrates"][wid] for wid in p.substrate_wids], dtype=np.float64
    )
    processed_all = np.asarray(
        [state["protein"]["processed_counts"][wid] for wid in p.processed_monomer_wids],
        dtype=np.float64,
    )
    lipoprotein_processed = processed_all[p.lipoprotein_indices]
    enzymes = np.asarray(
        [state["protein"]["enzyme_counts"][wid] for wid in p.enzyme_wids],
        dtype=np.float64,
    )
    flux = p._compute_reaction_fluxes(
        processed_lipoproteins=lipoprotein_processed,
        substrates=substrates,
        enzymes=enzymes,
        dt=1.0,
    )

    update = p.next_update(1.0, state)
    observed_sub = np.array(
        [int(update.get("substrates", {}).get(wid, 0.0)) for wid in p.substrate_wids],
        dtype=np.int64,
    )
    expected_sub = p.reaction_stoich @ flux
    np.testing.assert_array_equal(observed_sub, expected_sub)

    unfolded = sum(float(v) for v in update.get("protein", {}).get("unfolded_counts", {}).values())
    signal = sum(
        float(v) for v in update.get("protein", {}).get("signal_sequence_counts", {}).values()
    )
    assert signal == unfolded


def test_no_dag_no_action() -> None:
    p = KarrProteinProcessingIIProcess({"rng_seed": 17})
    state = _build_state(
        p,
        target_lipoprotein_count=2.0,
        dag_available=0.0,
        water_available=100.0,
        dag_enzyme=20_000.0,
        cleavage_enzyme=20_000.0,
    )
    update = p.next_update(1.0, state)
    assert update == {}


def test_deterministic_with_seed() -> None:
    p1 = KarrProteinProcessingIIProcess({"rng_seed": 123})
    p2 = KarrProteinProcessingIIProcess({"rng_seed": 123})

    state = _build_state(
        p1,
        target_lipoprotein_count=4.0,
        dag_available=400.0,
        water_available=400.0,
        dag_enzyme=30_000.0,
        cleavage_enzyme=30_000.0,
    )
    state_1 = deepcopy(state)
    state_2 = deepcopy(state)

    update_1 = p1.next_update(1.0, state_1)
    update_2 = p2.next_update(1.0, state_2)
    assert update_1 == update_2
