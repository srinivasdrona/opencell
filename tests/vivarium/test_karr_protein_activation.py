from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
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

from opencell.vivarium.karr_protein_activation import KarrProteinActivationProcess

_KARR_N_AVOGADRO = 6.0221417930e23
_ACTIVE_NONCYTOSOL_COUNTS = "activation_active_noncytosol_counts"
_INACTIVE_COUNTS = "activation_inactive_counts"

_REGULATED = (
    "MG_085_HEXAMER",
    "MG_101_MONOMER",
    "MG_127_MONOMER",
    "MG_205_DIMER",
    "MG_236_MONOMER",
    "MG_409_DIMER",
)
_EXPECTED_BASELINE_ACTIVE = np.asarray(
    [
        [0, 0, 0, 0, 0, 0],
        [35, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [16, 0, 0, 0, 0, 0],
    ],
    dtype=np.float64,
)
_EXPECTED_BASELINE_INACTIVE = np.asarray(
    [
        [14, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [73, 0, 0, 0, 0, 0],
        [23, 0, 0, 0, 0, 0],
        [215, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
    ],
    dtype=np.float64,
)


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    protein_update = update.get("protein", {})
    for wid, value in protein_update.get("activity", {}).items():
        state["protein"]["activity"][wid] = int(value)

    for store_name in ("protein", "complex"):
        store_update = update.get(store_name, {})
        for wid, delta in store_update.get("counts", {}).items():
            state[store_name]["counts"][wid] += float(delta)
        for branch_name in (_ACTIVE_NONCYTOSOL_COUNTS, _INACTIVE_COUNTS):
            for wid, compartment_updates in store_update.get(branch_name, {}).items():
                for compartment, delta in compartment_updates.items():
                    state[store_name][branch_name][wid][compartment] += float(delta)


def _set_matrices(
    process: KarrProteinActivationProcess,
    state: dict[str, Any],
    active: np.ndarray,
    inactive: np.ndarray,
) -> None:
    assert active.shape == inactive.shape == (
        len(process.regulated_protein_wids),
        process.compartment_count,
    )
    for row, wid in enumerate(process.regulated_protein_wids):
        store = state[process.store_by_wid[wid]]
        store["counts"][wid] = float(active[row, 0])
        for compartment in range(1, process.compartment_count):
            key = process.compartment_keys[compartment]
            store[_ACTIVE_NONCYTOSOL_COUNTS][wid][key] = float(active[row, compartment])
        for compartment, key in enumerate(process.compartment_keys):
            store[_INACTIVE_COUNTS][wid][key] = float(inactive[row, compartment])


def _run_engine(
    process: KarrProteinActivationProcess,
    initial_state: dict[str, Any],
) -> dict[str, Any]:
    topology = {
        process.name: {
            "protein": ("protein",),
            "complex": ("complex",),
            "stimuli": ("stimuli",),
            "geometry": ("geometry",),
        }
    }
    engine = Engine(
        processes={process.name: process},
        topology=topology,
        initial_state=initial_state,
        emit_step=1.0,
        display_info=False,
    )
    engine.update(1.0)
    return engine.state.get_value()


def _count_for_millimolar(process: KarrProteinActivationProcess, value: float) -> float:
    return (
        float(value)
        * (_KARR_N_AVOGADRO / 1000.0)
        * process.default_geometry_volume
    )


def test_fixture_projection_and_canonical_state_are_exact() -> None:
    process = KarrProteinActivationProcess({})
    state = process.canonical_state()
    active, inactive = process.state_matrices(state)

    assert process.name == "karr_protein_activation"
    assert tuple(process.regulated_protein_wids) == _REGULATED
    assert process.compartment_count == 6
    assert process.true_stimulus_wids == {
        "stimulus_gluconate",
        "stimulus_ironStress",
        "stimulus_thiolStress",
        "temperature",
    }
    np.testing.assert_array_equal(active, _EXPECTED_BASELINE_ACTIVE)
    np.testing.assert_array_equal(inactive, _EXPECTED_BASELINE_INACTIVE)
    assert state["geometry"]["volume"] == process.default_geometry_volume


def test_engine_baseline_initialization_and_transition_match_canonical_matrices() -> None:
    process = KarrProteinActivationProcess({})
    initial_state = process.canonical_state()
    total_before = sum(process.state_matrices(initial_state))

    final_state = _run_engine(process, deepcopy(initial_state))
    active_after, inactive_after = process.state_matrices(final_state)

    np.testing.assert_array_equal(active_after, _EXPECTED_BASELINE_ACTIVE)
    np.testing.assert_array_equal(inactive_after, _EXPECTED_BASELINE_INACTIVE)
    np.testing.assert_array_equal(active_after + inactive_after, total_before)
    assert final_state["protein"]["activity"] == {
        "MG_085_HEXAMER": 0,
        "MG_101_MONOMER": 1,
        "MG_127_MONOMER": 0,
        "MG_205_DIMER": 0,
        "MG_236_MONOMER": 0,
        "MG_409_DIMER": 1,
    }


@pytest.mark.parametrize(
    ("g6p_mm", "pi_mm", "gluconate", "iron", "thiol", "temperature", "expected"),
    (
        (6.0, 22.0, 1.0, 0.0, 1.0, 37.0, [1, 0, 1, 0, 0, 1]),
        (4.0, 18.0, 0.0, 1.0, 1.0, 43.0, [0, 1, 1, 1, 1, 0]),
    ),
)
def test_engine_matches_discriminating_karr_rules_in_every_compartment(
    g6p_mm: float,
    pi_mm: float,
    gluconate: float,
    iron: float,
    thiol: float,
    temperature: float,
    expected: list[int],
) -> None:
    process = KarrProteinActivationProcess({})
    state = process.canonical_state()
    active_before = np.ones((6, 6), dtype=np.float64)
    inactive_before = np.ones((6, 6), dtype=np.float64)
    _set_matrices(process, state, active_before, inactive_before)
    state["stimuli"].update(
        {
            "G6P": _count_for_millimolar(process, g6p_mm),
            "PI": _count_for_millimolar(process, pi_mm),
            "stimulus_gluconate": gluconate,
            "stimulus_ironStress": iron,
            "stimulus_thiolStress": thiol,
            "temperature": temperature,
        }
    )

    final_state = _run_engine(process, state)
    active_after, inactive_after = process.state_matrices(final_state)
    expected_mask = np.repeat(np.asarray(expected, dtype=bool)[:, None], 6, axis=1)

    np.testing.assert_array_equal(active_after, np.where(expected_mask, 2.0, 0.0))
    np.testing.assert_array_equal(inactive_after, np.where(expected_mask, 0.0, 2.0))
    np.testing.assert_array_equal(active_after + inactive_after, 2.0)


def test_engine_preserves_per_compartment_counts_and_raw_temperature() -> None:
    process = KarrProteinActivationProcess({})
    state = process.canonical_state()
    active_before = np.zeros((6, 6), dtype=np.float64)
    inactive_before = np.zeros((6, 6), dtype=np.float64)
    mg205_row = process.regulated_protein_wids.index("MG_205_DIMER")
    inactive_before[mg205_row, 1] = 2.0
    inactive_before[mg205_row, 4] = 7.0
    _set_matrices(process, state, active_before, inactive_before)
    state["stimuli"]["temperature"] = 43.0

    assert process.converted_signals(state)["temperature"] == 43.0
    final_state = _run_engine(process, state)
    active_after, inactive_after = process.state_matrices(final_state)
    expected_row = np.asarray([0, 2, 0, 0, 7, 0], dtype=np.float64)

    np.testing.assert_array_equal(active_after[mg205_row], expected_row)
    np.testing.assert_array_equal(inactive_after[mg205_row], 0.0)

    flat_compartment_fault = np.asarray([9, 0, 0, 0, 0, 0], dtype=np.float64)
    assert not np.array_equal(active_after[mg205_row], flat_compartment_fault)


def test_engine_count_to_concentration_inversion_defeats_raw_count_fault() -> None:
    process = KarrProteinActivationProcess({})
    state = process.canonical_state()
    active_before = np.zeros((6, 6), dtype=np.float64)
    inactive_before = np.zeros((6, 6), dtype=np.float64)
    mg409_row = process.regulated_protein_wids.index("MG_409_DIMER")
    active_before[mg409_row, 0] = 5.0
    active_before[mg409_row, 3] = 4.0
    _set_matrices(process, state, active_before, inactive_before)
    state["stimuli"]["PI"] = 1000.0

    converted_pi = process.converted_signals(state)["PI"]
    assert state["stimuli"]["PI"] > 20.0
    assert converted_pi == pytest.approx(0.1382689681128521, rel=1e-12)
    assert converted_pi < 20.0

    final_state = _run_engine(process, state)
    active_after, inactive_after = process.state_matrices(final_state)
    np.testing.assert_array_equal(active_after[mg409_row], 0.0)
    np.testing.assert_array_equal(
        inactive_after[mg409_row],
        np.asarray([5, 0, 0, 4, 0, 0], dtype=np.float64),
    )

    raw_count_fault_activates = bool(state["stimuli"]["PI"] > 20.0)
    assert raw_count_fault_activates
    assert not np.any(active_after[mg409_row])


def test_every_tuple_conserves_total_under_mixed_rule_outcomes() -> None:
    process = KarrProteinActivationProcess({})
    state = process.canonical_state()
    active_before = np.arange(1, 37, dtype=np.float64).reshape(6, 6)
    inactive_before = np.arange(101, 137, dtype=np.float64).reshape(6, 6)
    _set_matrices(process, state, active_before, inactive_before)
    state["stimuli"].update(
        {
            "G6P": _count_for_millimolar(process, 6.0),
            "PI": _count_for_millimolar(process, 18.0),
            "stimulus_gluconate": 0.0,
            "stimulus_ironStress": 1.0,
            "stimulus_thiolStress": 0.0,
            "temperature": 43.0,
        }
    )

    final_state = _run_engine(process, state)
    active_after, inactive_after = process.state_matrices(final_state)
    np.testing.assert_array_equal(
        active_after + inactive_after,
        active_before + inactive_before,
    )


def test_missing_authoritative_keys_fail_explicitly() -> None:
    process = KarrProteinActivationProcess({})
    missing_geometry = process.canonical_state()
    del missing_geometry["geometry"]["volume"]
    with pytest.raises(KeyError, match=r"geometry\.volume"):
        process.next_update(1.0, missing_geometry)

    missing_inactive = process.canonical_state()
    del missing_inactive["complex"][_INACTIVE_COUNTS]["MG_085_HEXAMER"]["0"]
    with pytest.raises(KeyError, match=r"activation_inactive_counts\.MG_085_HEXAMER\.0"):
        process.next_update(1.0, missing_inactive)


def test_activity_is_derived_compatibility_not_authority() -> None:
    process = KarrProteinActivationProcess({})
    state = process.canonical_state()
    state["protein"]["activity"] = {wid: 1 for wid in process.regulated_protein_wids}

    update = process.next_update(1.0, state)

    assert update["protein"]["activity"]["MG_085_HEXAMER"] == 0
    assert update["protein"]["activity"]["MG_101_MONOMER"] == 1
