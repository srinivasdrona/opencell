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
from opencell.vivarium.protein_state import MIGRATED_WIDS


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
    """Synthetic small counts/saturating enzymes; rates and compartments come from fixture."""
    substrates = {wid: 100.0 for wid in process.substrate_wids}
    substrates[process.substrate_wids[process.substrate_index_dag]] = float(dag_available)
    substrates[process.substrate_wids[process.substrate_index_water]] = float(water_available)

    processed = {wid: 0.0 for wid in process.processed_monomer_wids}
    unfolded = {wid: 0.0 for wid in process.processed_monomer_wids}
    signal = {wid: 0.0 for wid in process.signal_sequence_monomer_wids}
    enzymes = {wid: 0.0 for wid in process.enzyme_wids}

    target_idx = int(process.lipoprotein_indices[0])
    target_wid = process.processed_monomer_wids[target_idx]

    non_lipo_idx = int(process.non_lipo_non_cleaved_indices[0])
    non_lipo_wid = process.processed_monomer_wids[non_lipo_idx]
    counts: dict[str, float] = {}
    authority: dict[str, Any] = {
        "processed_i": {},
        "processed_ii": {},
        "signal_sequence": {},
        "mature": {},
    }
    # ProteinProcessingII.m:205-217 reads processed-I at monomerCompartments.
    for wid, count in (
        (target_wid, target_lipoprotein_count),
        (non_lipo_wid, non_lipoprotein_count),
    ):
        if wid in MIGRATED_WIDS:
            comp = process.migrated_compartment_by_wid[wid]
            authority["processed_i"][wid] = {comp: float(count)}
        else:
            counts[wid] = float(count)

    enzymes[process.enzyme_wids[process.enzyme_index_dag_transferase]] = float(dag_enzyme)
    enzymes[process.enzyme_wids[process.enzyme_index_signal_peptidase]] = float(cleavage_enzyme)
    for wid, count in enzymes.items():
        counts[wid] = count
        authority["mature"][wid] = {process.migrated_compartment_by_wid[wid]: count}

    return {
        "substrates": substrates,
        "protein": {
            "processed_counts": processed,
            "unfolded_counts": unfolded,
            "signal_sequence_counts": signal,
            "enzyme_counts": enzymes,
            "counts": counts,
            "compartment_counts": authority,
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

    for store_name in ("counts", "processed_counts", "unfolded_counts", "signal_sequence_counts"):
        for wid, delta in update.get("protein", {}).get(store_name, {}).items():
            state["protein"][store_name][wid] = float(
                state["protein"][store_name].get(wid, 0.0) + float(delta)
            )
    for form, rows in update.get("protein", {}).get("compartment_counts", {}).items():
        for wid, compartments in rows.items():
            row = state["protein"]["compartment_counts"].setdefault(form, {}).setdefault(wid, {})
            for comp, delta in compartments.items():
                row[comp] = row.get(comp, 0.0) + delta


def _pool(state: dict[str, Any], p: KarrProteinProcessingIIProcess, form: str, wid: str) -> float:
    if wid in MIGRATED_WIDS:
        return float(
            state["protein"]["compartment_counts"].get(form, {}).get(wid, {}).get(
                p.migrated_compartment_by_wid[wid], 0.0
            )
        )
    legacy = "counts" if form == "processed_i" else "processed_counts"
    return float(state["protein"][legacy].get(wid, 0.0))


def test_fixture_loads() -> None:
    p = KarrProteinProcessingIIProcess({})
    assert p.name == "karr_protein_processing_ii"
    assert len(p.substrate_wids) == 5
    assert len(p.enzyme_wids) == 2
    assert len(p.lipoprotein_indices) > 0
    assert p.reaction_stoich.shape == (len(p.substrate_wids), 2 * len(p.lipoprotein_indices))
    assert set(p.lipoprotein_indices).isdisjoint(p.secreted_indices)
    assert set(p.peptidase_indices) | set(p.non_lipo_non_cleaved_indices) == set(
        range(len(p.unprocessed_monomer_wids))
    )


def test_non_lipoprotein_pass_through_to_processed_ii() -> None:
    p = KarrProteinProcessingIIProcess({"rng_seed": 7})
    state = _build_state(p, target_lipoprotein_count=0.0, non_lipoprotein_count=7.0)

    non_lipo_idx = int(p.non_lipo_non_cleaved_indices[0])
    non_lipo_wid = p.processed_monomer_wids[non_lipo_idx]

    update = p.next_update(1.0, state)
    _apply_update(state, update, p)

    assert _pool(state, p, "processed_i", non_lipo_wid) == 0.0
    assert _pool(state, p, "processed_ii", non_lipo_wid) == 7.0
    assert update.get("substrates", {}) == {}
    assert update.get("protein", {}).get("signal_sequence_counts", {}) == {}


def test_dag_transfer_then_cleave() -> None:
    p = KarrProteinProcessingIIProcess({"rng_seed": 11})
    state = _build_state(
        p, target_lipoprotein_count=1.0, dag_enzyme=20_000.0, cleavage_enzyme=20_000.0
    )
    target_idx = int(p.lipoprotein_indices[0])
    target_wid = p.processed_monomer_wids[target_idx]

    update = p.next_update(1.0, state)
    _apply_update(state, update, p)
    assert _pool(state, p, "processed_i", target_wid) == 0.0
    assert _pool(state, p, "processed_ii", target_wid) == 1.0
    expected = np.zeros(len(p.substrate_wids))
    expected[p.substrate_index_water] = -1
    expected[p.substrate_index_pg160] = -1
    expected[p.substrate_index_snglyp] = 1
    expected[p.substrate_index_hydrogen] = 1
    np.testing.assert_array_equal(
        [update.get("substrates", {}).get(wid, 0.0) for wid in p.substrate_wids], expected
    )


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

    # MATLAB Representation and evolveState: no anchoring-only intermediate.
    assert update == {}
    assert _pool(state, p, "processed_i", target_wid) == 1.0
    assert _pool(state, p, "processed_ii", target_wid) == 0.0


def test_mass_conservation() -> None:
    p = KarrProteinProcessingIIProcess({"rng_seed": 9})
    state = _build_state(
        p,
        target_lipoprotein_count=3.0,
        dag_available=100.0,
        water_available=100.0,
        dag_enzyme=40_000.0,
        cleavage_enzyme=40_000.0,
    )

    update = p.next_update(1.0, state)
    observed_sub = np.array(
        [update.get("substrates", {}).get(wid, 0.0) for wid in p.substrate_wids],
    )
    # Independent stoichiometry: ProteinProcessingII.m:409-415, not a private flux helper.
    expected_sub = np.zeros(len(p.substrate_wids))
    expected_sub[p.substrate_index_water] = -3
    expected_sub[p.substrate_index_pg160] = -3
    expected_sub[p.substrate_index_snglyp] = 3
    expected_sub[p.substrate_index_hydrogen] = 3
    np.testing.assert_array_equal(observed_sub, expected_sub)
    _apply_update(state, update, p)
    wid = p.unprocessed_monomer_wids[int(p.lipoprotein_indices[0])]
    assert _pool(state, p, "processed_i", wid) == 0
    assert _pool(state, p, "processed_ii", wid) == 3
    signal_wid = p.signal_sequence_monomer_wids[int(p.lipoprotein_indices[0])]
    # copyToState: signal peptides are released in cytosol, including migrated WIDs.
    signal = state["protein"]["compartment_counts"]["signal_sequence"].get(
        signal_wid, {}
    ).get("c", 0.0) + state["protein"]["signal_sequence_counts"].get(signal_wid, 0.0)
    assert signal == 3, (
        "MATLAB copyToState:250-252 requires one cytosolic signal peptide per cleavage"
    )


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
