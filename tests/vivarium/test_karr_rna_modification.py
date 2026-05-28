from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.engine import Engine

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
from opencell.vivarium.karr_rna_modification import KarrRNAModificationProcess

_FIXTURE_PATH = "data/karr_fixtures/per_process/RNAModification_flat.mat"


def _set_enzyme_count(
    state: dict[str, Any],
    process: KarrRNAModificationProcess,
    wid: str,
    value: float,
) -> None:
    if wid in process.complex_enzyme_wids:
        state["complex"]["counts"][wid] = float(value)
        return
    state["protein"]["counts"][wid] = float(value)


def _enzyme_vector_from_state(
    state: dict[str, Any], process: KarrRNAModificationProcess
) -> np.ndarray:
    protein_counts = state.get("protein", {}).get("counts", {})
    complex_counts = state.get("complex", {}).get("counts", {})
    return np.asarray(
        [
            float(complex_counts[wid])
            if wid in process.complex_enzyme_wids
            else float(protein_counts[wid])
            for wid in process.enzyme_wids
        ],
        dtype=np.float64,
    )


def _load_snapshot_state(process: KarrRNAModificationProcess) -> dict[str, Any]:
    fixture = loadmat(_FIXTURE_PATH)["data"]["fixture"][0, 0]

    try:
        substrates = np.asarray(fixture["substrates"][0, 0], dtype=np.float64).reshape(-1)
        unmodified_all = np.asarray(fixture["unmodifiedRNAs"][0, 0], dtype=np.float64).reshape(-1)
        modified_all = np.asarray(fixture["modifiedRNAs"][0, 0], dtype=np.float64).reshape(-1)
        enzymes = np.asarray(fixture["enzymes"][0, 0], dtype=np.float64).reshape(-1)

        unmodified = unmodified_all[process._active_rna_indices]
        modified = modified_all[process._active_rna_indices]
        if (
            substrates.size != len(process.substrate_wids)
            or unmodified.size != len(process.unmodified_rna_wids)
            or modified.size != len(process.modified_rna_wids)
            or enzymes.size != len(process.enzyme_wids)
        ):
            raise ValueError("fixture vector length mismatch")
    except Exception:
        rng = np.random.default_rng(20260522)
        substrates = rng.integers(1_000, 10_000, size=len(process.substrate_wids)).astype(float)
        unmodified = rng.integers(0, 20, size=len(process.unmodified_rna_wids)).astype(float)
        modified = rng.integers(0, 20, size=len(process.modified_rna_wids)).astype(float)
        enzymes = rng.integers(1, 100, size=len(process.enzyme_wids)).astype(float)

    protein_counts: dict[str, float] = {}
    complex_counts: dict[str, float] = {}
    for idx, wid in enumerate(process.enzyme_wids):
        if wid in process.complex_enzyme_wids:
            complex_counts[wid] = float(enzymes[idx])
        else:
            protein_counts[wid] = float(enzymes[idx])

    return {
        "substrates": {
            wid: float(substrates[idx]) for idx, wid in enumerate(process.substrate_wids)
        },
        "rna": {
            "counts": {
                wid: float(unmodified[idx]) for idx, wid in enumerate(process.unmodified_rna_wids)
            },
            "modified_counts": {
                wid: float(modified[idx]) for idx, wid in enumerate(process.modified_rna_wids)
            },
        },
        "protein": {"counts": protein_counts},
        "complex": {"counts": complex_counts},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {
            process.name: {
                wid: float(substrates[idx]) for idx, wid in enumerate(process.substrate_wids)
            }
        },
    }


def _apply_update(
    state: dict[str, Any],
    update: dict[str, Any],
    process: KarrRNAModificationProcess,
) -> None:
    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"][wid] + float(delta))
        state["substrates_allocated"][process.name][wid] = float(state["substrates"][wid])

    for wid, delta in update.get("rna", {}).get("counts", {}).items():
        state["rna"]["counts"][wid] = float(state["rna"]["counts"][wid] + float(delta))

    for wid, delta in update.get("rna", {}).get("modified_counts", {}).items():
        state["rna"]["modified_counts"][wid] = float(
            state["rna"]["modified_counts"][wid] + float(delta)
        )


def _single_target_state(process: KarrRNAModificationProcess, target_idx: int) -> dict[str, Any]:
    state = _load_snapshot_state(process)
    target_wid = process.unmodified_rna_wids[target_idx]
    for wid in process.unmodified_rna_wids:
        state["rna"]["counts"][wid] = 0.0
    for wid in process.modified_rna_wids:
        state["rna"]["modified_counts"][wid] = 0.0
    state["rna"]["counts"][target_wid] = 1.0
    return state


def test_fixture_loads() -> None:
    p = KarrRNAModificationProcess({})
    assert p.name == "karr_rna_modification"
    assert len(p.substrate_wids) == 29
    assert len(p.unmodified_rna_wids) == 38
    assert len(p.modified_rna_wids) == 38
    assert len(p.enzyme_wids) == 13

    assert p.reaction_stoich.shape == (29, 91)
    assert p.reaction_stoich.dtype == np.int64
    assert p.reaction_catalysis.shape == (91, 13)
    assert p.reaction_catalysis.dtype == np.uint8
    assert p.reaction_modification.shape == (91, 38)
    assert p.reaction_modification.dtype == np.uint8
    assert p.enzyme_bounds.shape == (91, 2)
    assert p.enzyme_bounds.dtype == np.float64

    assert p._n_completed.shape == (38,)
    assert np.all(p._n_completed == 0)


def test_no_unmodified_no_action() -> None:
    p = KarrRNAModificationProcess({})
    state = _load_snapshot_state(p)
    for wid in p.unmodified_rna_wids:
        state["rna"]["counts"][wid] = 0.0

    update = p.next_update(1.0, state)
    assert update == {}
    assert np.all(p._n_completed == 0)


def test_required_reactions_per_rna() -> None:
    p = KarrRNAModificationProcess({})
    required = p.required_reactions_per_rna
    np.testing.assert_array_equal(required, np.sum(p.reaction_modification, axis=0))
    assert int(required.min()) >= 1
    assert int(required.max()) <= 7


def test_mass_conservation() -> None:
    p = KarrRNAModificationProcess({"rng_seed": 42})
    state = _load_snapshot_state(p)

    unmodified = np.array(
        [state["rna"]["counts"][wid] for wid in p.unmodified_rna_wids], dtype=np.float64
    )
    substrates = np.array([state["substrates"][wid] for wid in p.substrate_wids], dtype=np.float64)
    enzymes = _enzyme_vector_from_state(state, p)
    flux = p._compute_reaction_fluxes(
        unmodified_rna=unmodified,
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

    unmodified_delta = np.array(
        [
            int(update.get("rna", {}).get("counts", {}).get(wid, 0.0))
            for wid in p.unmodified_rna_wids
        ],
        dtype=np.int64,
    )
    modified_delta = np.array(
        [
            int(update.get("rna", {}).get("modified_counts", {}).get(wid, 0.0))
            for wid in p.modified_rna_wids
        ],
        dtype=np.int64,
    )
    np.testing.assert_array_equal(
        unmodified_delta + modified_delta, np.zeros_like(unmodified_delta)
    )


def test_full_modification_transitions_state() -> None:
    p = KarrRNAModificationProcess({"rng_seed": 1})
    target_idx = int(np.argmin(p.required_reactions_per_rna))
    target_wid = p.unmodified_rna_wids[target_idx]
    state = _single_target_state(p, target_idx)

    for wid in p.substrate_wids:
        state["substrates"][wid] = 1_000_000.0
        state["substrates_allocated"][p.name][wid] = 1_000_000.0
    for wid in p.enzyme_wids:
        _set_enzyme_count(state, p, wid, 1_000_000.0)

    for _ in range(20):
        update = p.next_update(1.0, state)
        _apply_update(state, update, p)
        if state["rna"]["modified_counts"][target_wid] >= 1.0:
            break

    assert state["rna"]["counts"][target_wid] == 0.0
    assert state["rna"]["modified_counts"][target_wid] == 1.0
    assert p._n_completed[target_idx] == 0


def test_partial_modification_no_transition() -> None:
    p = KarrRNAModificationProcess({"rng_seed": 7})
    target_idx = int(np.argmax(p.required_reactions_per_rna))
    target_wid = p.unmodified_rna_wids[target_idx]
    state = _single_target_state(p, target_idx)

    for wid in p.substrate_wids:
        state["substrates"][wid] = 0.0
        state["substrates_allocated"][p.name][wid] = 0.0
    for wid in p.enzyme_wids:
        _set_enzyme_count(state, p, wid, 0.0)

    reaction_ids = np.flatnonzero(p.reaction_modification[:, target_idx] > 0)
    kept_reaction = int(reaction_ids[0])

    for sidx, coeff in enumerate(p.reaction_stoich[:, kept_reaction]):
        if coeff < 0:
            wid = p.substrate_wids[sidx]
            state["substrates"][wid] = 1.0
            state["substrates_allocated"][p.name][wid] = 1.0

    for eidx, flag in enumerate(p.reaction_catalysis[kept_reaction]):
        if flag > 0:
            _set_enzyme_count(state, p, p.enzyme_wids[eidx], 1_000_000.0)

    update = p.next_update(1.0, state)
    assert update.get("rna", {}).get("counts", {}).get(target_wid, 0.0) == 0.0
    assert update.get("rna", {}).get("modified_counts", {}).get(target_wid, 0.0) == 0.0
    assert 0 < p._n_completed[target_idx] < p.required_reactions_per_rna[target_idx]


def test_deterministic_with_seed() -> None:
    p1 = KarrRNAModificationProcess({"rng_seed": 11})
    p2 = KarrRNAModificationProcess({"rng_seed": 11})

    state_1 = _load_snapshot_state(p1)
    state_2 = deepcopy(state_1)

    update_1 = p1.next_update(1.0, state_1)
    update_2 = p2.next_update(1.0, state_2)
    assert update_1 == update_2
    np.testing.assert_array_equal(p1._n_completed, p2._n_completed)


def test_chassis_v6_wires_complex_port_for_rna_modification() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    assert composite["topology"]["karr_rna_modification"]["complex"] == ("complex",)


def test_complex_enzyme_is_read_from_complex_store() -> None:
    p = KarrRNAModificationProcess({"rng_seed": 0})
    assert p.complex_enzyme_wids

    complex_enzyme_wid = p.complex_enzyme_wids[0]
    complex_enzyme_idx = p.enzyme_wids.index(complex_enzyme_wid)
    reaction_candidates = np.flatnonzero(p.reaction_catalysis[:, complex_enzyme_idx] > 0)
    assert reaction_candidates.size > 0
    reaction_idx = int(reaction_candidates[0])
    target_idx = int(np.argmax(p.reaction_modification[reaction_idx]))
    target_wid = p.unmodified_rna_wids[target_idx]

    base_state = _single_target_state(p, target_idx)
    for wid in p.substrate_wids:
        base_state["substrates"][wid] = 0.0
        base_state["substrates_allocated"][p.name][wid] = 0.0
    for wid in p.enzyme_wids:
        _set_enzyme_count(base_state, p, wid, 0.0)
    base_state["rna"]["counts"][target_wid] = 1.0
    base_state["rna"]["modified_counts"][target_wid] = 0.0

    for sidx, coeff in enumerate(p.reaction_stoich[:, reaction_idx]):
        if coeff < 0:
            substrate_wid = p.substrate_wids[sidx]
            base_state["substrates"][substrate_wid] = float(-coeff)
            base_state["substrates_allocated"][p.name][substrate_wid] = float(-coeff)

    for eidx, flag in enumerate(p.reaction_catalysis[reaction_idx]):
        if flag > 0:
            _set_enzyme_count(base_state, p, p.enzyme_wids[eidx], 1_000_000.0)

    blocked_state = deepcopy(base_state)
    _set_enzyme_count(blocked_state, p, complex_enzyme_wid, 0.0)

    update_active = p.next_update(1.0, base_state)
    update_blocked = p.next_update(1.0, blocked_state)

    assert update_active != {}
    assert update_blocked == {}


def test_chassis_v6_has_rna_modification_complex_keys() -> None:
    p = KarrRNAModificationProcess({})
    engine = Engine(
        composite=build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0),
        emit_step=1.0,
        display_info=False,
    )
    state = engine.state.get_value()
    complex_counts = state.get("complex", {}).get("counts", {})

    for wid in p.complex_enzyme_wids:
        assert wid in complex_counts
