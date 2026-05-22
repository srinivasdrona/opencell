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

from opencell.vivarium.karr_protein_modification import KarrProteinModificationProcess


def _build_state(process: KarrProteinModificationProcess) -> dict[str, Any]:
    return {
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "protein": {
            "counts": {wid: 0.0 for wid in process.enzyme_wids},
            "unmodified_counts": {wid: 0.0 for wid in process.unmodified_monomer_wids},
            "modified_counts": {wid: 0.0 for wid in process.modified_monomer_wids},
        },
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }


def _set_substrates(
    state: dict[str, Any],
    process: KarrProteinModificationProcess,
    value: float,
) -> None:
    for wid in process.substrate_wids:
        state["substrates"][wid] = float(value)
        state["substrates_allocated"][process.name][wid] = float(value)


def _apply_update(
    state: dict[str, Any],
    update: dict[str, Any],
    process: KarrProteinModificationProcess,
) -> None:
    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"][wid] + float(delta))
        state["substrates_allocated"][process.name][wid] = float(state["substrates"][wid])
    for wid, delta in update.get("protein", {}).get("unmodified_counts", {}).items():
        state["protein"]["unmodified_counts"][wid] = float(
            state["protein"]["unmodified_counts"][wid] + float(delta)
        )
    for wid, delta in update.get("protein", {}).get("modified_counts", {}).items():
        state["protein"]["modified_counts"][wid] = float(
            state["protein"]["modified_counts"][wid] + float(delta)
        )


def test_fixture_loads() -> None:
    process = KarrProteinModificationProcess({})
    assert process.name == "karr_protein_modification"
    assert len(process.enzyme_wids) == 3
    assert len(process.unmodified_monomer_wids) == 20
    assert len(process.modified_monomer_wids) == 20
    assert process.reaction_stoich.shape == (15, 63)
    assert process.reaction_catalysis.shape == (63, 3)
    assert process.reaction_modification.shape == (63, 20)
    assert process.required_modifications.min() == 1
    assert process.required_modifications.max() == 11
    np.testing.assert_array_equal(np.sum(process.reaction_modification, axis=1), np.ones(63))


def test_no_unmodified_no_action() -> None:
    process = KarrProteinModificationProcess({"rng_seed": 2})
    state = _build_state(process)
    _set_substrates(state, process, value=10_000.0)
    for wid in process.enzyme_wids:
        state["protein"]["counts"][wid] = 1_000.0

    update = process.next_update(1.0, state)
    assert update == {}


def test_required_modifications_per_protein() -> None:
    process = KarrProteinModificationProcess({})
    required = process.required_modifications
    assert required.min() >= 1
    assert required.max() <= 11
    assert set(required.tolist()) == {1, 2, 3, 5, 9, 11}
    assert int(required.sum()) == 63


def test_full_modification_transitions() -> None:
    process = KarrProteinModificationProcess({"rng_seed": 7})
    state = _build_state(process)
    _set_substrates(state, process, value=10_000.0)
    for wid in process.enzyme_wids:
        state["protein"]["counts"][wid] = 2_000.0

    target_idx = int(np.flatnonzero(process.required_modifications == 3)[0])
    target_unmod = process.unmodified_monomer_wids[target_idx]
    target_mod = process.modified_monomer_wids[target_idx]
    state["protein"]["unmodified_counts"][target_unmod] = 1.0

    transitioned = False
    for _ in range(10):
        update = process.next_update(1.0, state)
        _apply_update(state, update, process)
        if state["protein"]["modified_counts"][target_mod] >= 1.0:
            transitioned = True
            break

    assert transitioned
    assert state["protein"]["unmodified_counts"][target_unmod] == 0.0
    assert state["protein"]["modified_counts"][target_mod] == 1.0
    assert process._n_completed[target_idx] == 0


def test_partial_modification_no_transition() -> None:
    process = KarrProteinModificationProcess({"rng_seed": 8})
    state = _build_state(process)
    _set_substrates(state, process, value=10_000.0)
    for wid in process.enzyme_wids:
        state["protein"]["counts"][wid] = 2_000.0

    target_idx = int(np.argmax(process.required_modifications))
    target_unmod = process.unmodified_monomer_wids[target_idx]
    target_mod = process.modified_monomer_wids[target_idx]
    state["protein"]["unmodified_counts"][target_unmod] = 1.0

    atp_idx = process.substrate_wids.index("ATP")
    target_rxn_idx = np.flatnonzero(process.reaction_modification[:, target_idx] > 0)
    atp_required_total = int(
        np.sum(-np.minimum(0, process.reaction_stoich[atp_idx, target_rxn_idx]))
    )
    limited_atp = float(max(1, atp_required_total - 1))
    state["substrates"]["ATP"] = limited_atp
    state["substrates_allocated"][process.name]["ATP"] = limited_atp

    update = process.next_update(1.0, state)
    assert target_unmod not in update.get("protein", {}).get("unmodified_counts", {})
    assert target_mod not in update.get("protein", {}).get("modified_counts", {})
    assert 0 < process._n_completed[target_idx] < process.required_modifications[target_idx]


def test_mass_conservation() -> None:
    expected_process = KarrProteinModificationProcess({"rng_seed": 21})
    observed_process = KarrProteinModificationProcess({"rng_seed": 21})

    state = _build_state(expected_process)
    _set_substrates(state, expected_process, value=5_000.0)
    for wid in expected_process.enzyme_wids:
        state["protein"]["counts"][wid] = 2_000.0
    for wid in expected_process.unmodified_monomer_wids[:5]:
        state["protein"]["unmodified_counts"][wid] = 1.0

    unmodified = np.asarray(
        [
            state["protein"]["unmodified_counts"][wid]
            for wid in expected_process.unmodified_monomer_wids
        ],
        dtype=np.float64,
    )
    substrates = np.asarray(
        [state["substrates"][wid] for wid in expected_process.substrate_wids], dtype=np.float64
    )
    enzymes = np.asarray(
        [state["protein"]["counts"][wid] for wid in expected_process.enzyme_wids], dtype=np.float64
    )
    expected_flux = expected_process._sample_reaction_fluxes(
        unmodified=unmodified,
        substrates=substrates,
        enzymes=enzymes,
        dt=1.0,
    )
    expected_substrate_delta = expected_process.reaction_stoich @ expected_flux

    observed_update = observed_process.next_update(1.0, deepcopy(state))
    observed_substrate_delta = np.asarray(
        [
            int(observed_update.get("substrates", {}).get(wid, 0.0))
            for wid in observed_process.substrate_wids
        ],
        dtype=np.int64,
    )
    np.testing.assert_array_equal(observed_substrate_delta, expected_substrate_delta)


def test_deterministic_with_seed() -> None:
    process_1 = KarrProteinModificationProcess({"rng_seed": 999})
    process_2 = KarrProteinModificationProcess({"rng_seed": 999})

    state = _build_state(process_1)
    _set_substrates(state, process_1, value=8_000.0)
    for wid in process_1.enzyme_wids:
        state["protein"]["counts"][wid] = 2_500.0
    for wid in process_1.unmodified_monomer_wids[:4]:
        state["protein"]["unmodified_counts"][wid] = 1.0

    update_1 = process_1.next_update(1.0, deepcopy(state))
    update_2 = process_2.next_update(1.0, deepcopy(state))
    assert update_1 == update_2
    np.testing.assert_array_equal(process_1._n_completed, process_2._n_completed)
