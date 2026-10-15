"""PM replay with source-before inputs only and one persistent stochastic owner.

ProteinModification.m:227-287 reads/writes folded and mature monomer forms;
331-393 evolves those forms and free mature monomer/complex enzymes. The
fixture supplies WIDs, routes and remapped biological compartments. No
states-after value is supplied to the process, including through trace hints.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest
from scipy.io import loadmat

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
from opencell.vivarium.protein_state import COMPARTMENTS, MIGRATED_WIDS

_TRACE_PROCESS_NAME = "ProteinModification"
_TRACE_PATH = (
    _REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2"
    / "ProteinModification_100ticks.mat"
)
_OBSERVABLES = ("substrates", "enzymes", "boundEnzymes", "modifiedMonomers", "unmodifiedMonomers")
_PASS_THROUGH = frozenset({"boundEnzymes", "enzymes"})
_SCRATCH_RESET = {
    "_rng": "karr-persistent",
    "_n_completed": "per-tick-scratch",  # overwritten by production before use; not an RNG reset
}
_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
    "modifiedMonomers": "all_modified_monomer_wids",
    "unmodifiedMonomers": "all_unmodified_monomer_wids",
}


@dataclass(frozen=True)
class _Layout:
    unmodified: tuple[str, ...]
    modified: tuple[str, ...]
    substrates: tuple[str, ...]
    enzymes: tuple[str, ...]
    compartments: tuple[str, ...]
    active: np.ndarray
    monomer_enzymes: frozenset[int]
    complex_enzymes: frozenset[int]


@cache
def _layout() -> _Layout:
    fixture = loadmat(
        str(_REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "ProteinModification_flat.mat"),
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture
    compartments = [COMPARTMENTS[int(i) - 1] for i in fixture.monomerCompartments]
    return _Layout(
        unmodified=tuple(map(str, fixture.unmodifiedMonomerWholeCellModelIDs)),
        modified=tuple(map(str, fixture.modifiedMonomerWholeCellModelIDs)),
        substrates=tuple(map(str, fixture.substrateWholeCellModelIDs)),
        enzymes=tuple(map(str, fixture.enzymeWholeCellModelIDs)),
        compartments=tuple({"tc": "c", "tm": "m"}.get(c, c) for c in compartments),
        active=np.asarray(fixture.monomerIndexs_modified, dtype=int).reshape(-1) - 1,
        monomer_enzymes=frozenset(
            np.asarray(fixture.enzymeMonomerLocalIndexs, dtype=int).reshape(-1) - 1
        ),
        complex_enzymes=frozenset(
            np.asarray(fixture.enzymeComplexLocalIndexs, dtype=int).reshape(-1) - 1
        ),
    )


def _vector(trace: h5py.File, group: str, observable: str, tick: int) -> np.ndarray:
    reference = trace[group][observable][0, tick]
    vector = np.asarray(trace[reference][()]).reshape(-1)
    assert np.array_equal(vector, np.rint(vector)), (tick, group, observable, "non-integral")
    return vector


def _before_vectors(trace: h5py.File, tick: int) -> dict[str, np.ndarray]:
    return {obs: _vector(trace, "states_before", obs, tick) for obs in _OBSERVABLES}


def _source_state(
    process: KarrProteinModificationProcess, before: dict[str, np.ndarray]
) -> dict[str, Any]:
    """Project captured-before vectors into the SAME live forms production reads."""
    layout = _layout()
    for obs, attr in _OBSERVABLE_TO_WIDS_ATTR.items():
        assert before[obs].shape == (len(getattr(process, attr)),), (obs, before[obs].shape)
    assert tuple(process.all_unmodified_monomer_wids) == layout.unmodified
    assert tuple(process.all_modified_monomer_wids) == layout.modified
    assert tuple(process.substrate_wids) == layout.substrates
    assert tuple(process.enzyme_wids) == layout.enzymes
    np.testing.assert_array_equal(process.active_protein_indices, layout.active)
    assert layout.monomer_enzymes | layout.complex_enzymes == set(range(len(layout.enzymes)))
    assert not layout.monomer_enzymes & layout.complex_enzymes
    state: dict[str, Any] = {
        "substrates": dict(zip(layout.substrates, before["substrates"], strict=True)),
        "substrates_allocated": {
            process.name: dict(zip(layout.substrates, before["substrates"], strict=True))
        },
        "protein": {
            "counts": {},
            "unmodified_counts": {},
            "modified_counts": {},
            "compartment_counts": {
                form: {wid: dict.fromkeys(COMPARTMENTS, 0.0) for wid in MIGRATED_WIDS}
                for form in ("folded", "mature")
            },
        },
        "complex": {"counts": {}},
        "boundEnzymes": dict(zip(layout.enzymes, before["boundEnzymes"], strict=True)),
    }
    for i, wid in enumerate(layout.enzymes):
        port = "protein" if i in layout.monomer_enzymes else "complex"
        state[port]["counts"][wid] = float(before["enzymes"][i])
    for observable, form, branch, wids in (
        ("unmodifiedMonomers", "folded", "unmodified_counts", layout.unmodified),
        ("modifiedMonomers", "mature", "modified_counts", layout.modified),
    ):
        for i, wid in enumerate(wids):
            count = float(before[observable][i])
            if wid in MIGRATED_WIDS:
                state["protein"]["compartment_counts"][form][wid][layout.compartments[i]] = count
            else:
                state["protein"][branch][wid] = count
    return state


def _project(
    process: KarrProteinModificationProcess, state: dict[str, Any], observable: str
) -> np.ndarray:
    layout = _layout()
    if observable == "substrates":
        return np.array([state["substrates"][wid] for wid in layout.substrates])
    if observable == "enzymes":
        return process.live_inputs(state)[1]
    if observable == "boundEnzymes":
        return np.array([state["boundEnzymes"][wid] for wid in layout.enzymes])
    form, branch, wids = (
        ("folded", "unmodified_counts", layout.unmodified)
        if observable == "unmodifiedMonomers"
        else ("mature", "modified_counts", layout.modified)
    )
    return np.array(
        [
            state["protein"]["compartment_counts"][form][wid][layout.compartments[i]]
            if wid in MIGRATED_WIDS
            else state["protein"][branch][wid]
            for i, wid in enumerate(wids)
        ]
    )


def _assert_source_inputs(
    process: KarrProteinModificationProcess,
    state: dict[str, Any],
    before: dict[str, np.ndarray],
    tick: int,
) -> None:
    rng_before = deepcopy(process._rng.get_state())
    unmodified, enzymes = process.live_inputs(state)
    np.testing.assert_array_equal(
        unmodified,
        before["unmodifiedMonomers"][_layout().active],
        err_msg=f"tick={tick}: production live folded reader",
    )
    np.testing.assert_array_equal(enzymes, before["enzymes"], err_msg=f"tick={tick}: live enzymes")
    for obs in _OBSERVABLES:
        np.testing.assert_array_equal(
            _project(process, state, obs), before[obs], err_msg=f"{tick}:{obs}"
        )
    np.testing.assert_array_equal(
        [state["substrates_allocated"][process.name][wid] for wid in _layout().substrates],
        before["substrates"],
    )
    for old, new in zip(rng_before, process._rng.get_state(), strict=True):
        np.testing.assert_array_equal(old, new)


def _apply_update(
    state: dict[str, Any], update: dict[str, Any], process: KarrProteinModificationProcess
) -> None:
    del process
    assert set(update) <= {"substrates", "protein"}

    def accumulate(branch, deltas):
        for key, value in deltas.items():
            assert key in branch, f"Undeclared replay write: {key}"
            if isinstance(value, dict):
                accumulate(branch[key], value)
            else:
                assert np.isfinite(value) and value == np.rint(value), (key, value)
                branch[key] += value

    accumulate(state, update)


def _assert_identity_or_tolerance(*, tick, observable, oc_after, karr_after) -> None:
    # Despite the historical entry-point name, every count comparison is exact.
    assert oc_after.shape == karr_after.shape, (tick, observable, oc_after.shape, karr_after.shape)
    assert np.array_equal(oc_after, np.rint(oc_after)), (tick, observable, "OC non-integral")
    assert np.array_equal(karr_after, np.rint(karr_after)), (
        tick,
        observable,
        "oracle non-integral",
    )
    mismatch = np.flatnonzero(oc_after != karr_after)
    if mismatch.size:
        i = int(mismatch[0])
        pytest.fail(
            f"L2a first-mismatch tuple=({tick}, {observable!r}, {i}, "
            f"{oc_after[i]}, {karr_after[i]}, {oc_after[i] - karr_after[i]})"
        )


def test_pm_captured_before_inputs_roundtrip_for_all_ticks_with_persistent_execution() -> None:
    """Input regression, not an output-fidelity verdict; reads states_before ONLY."""
    process = KarrProteinModificationProcess({"rng_seed": 0})
    with h5py.File(_TRACE_PATH, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).item())
        assert n_ticks == 100
        for tick in range(n_ticks):
            before = _before_vectors(trace, tick)
            state = _source_state(process, before)
            _assert_source_inputs(process, state, before, tick)
            update = process.next_update(1.0, state)
            _apply_update(state, update, process)


@pytest.mark.parametrize(
    "wid",
    [
        wid
        for wid in _layout().unmodified
        if wid in MIGRATED_WIDS and wid in {_layout().unmodified[i] for i in _layout().active}
    ],
)
def test_pm_input_roundtrip_rejects_migrated_legacy_queue_shadow(wid: str) -> None:
    process = KarrProteinModificationProcess({})
    with h5py.File(_TRACE_PATH, "r") as trace:
        before = _before_vectors(trace, 0)
    i = _layout().unmodified.index(wid)
    before["unmodifiedMonomers"][i] = 1
    state = _source_state(process, before)
    _assert_source_inputs(process, state, before, 0)
    state["protein"]["compartment_counts"]["folded"][wid][_layout().compartments[i]] = 0
    state["protein"]["unmodified_counts"][wid] = 1
    state["unmodifiedMonomers"] = before["unmodifiedMonomers"].copy()
    with pytest.raises(AssertionError, match="production live folded reader"):
        _assert_source_inputs(process, state, before, 0)


@pytest.mark.parametrize("i", range(len(_layout().enzymes)), ids=_layout().enzymes)
def test_pm_input_roundtrip_rejects_wrong_live_enzyme_store(i: int) -> None:
    process = KarrProteinModificationProcess({})
    with h5py.File(_TRACE_PATH, "r") as trace:
        before = _before_vectors(trace, 0)
    before["enzymes"][i] = max(1, before["enzymes"][i])
    state = _source_state(process, before)
    _assert_source_inputs(process, state, before, 0)
    right, wrong = (
        ("protein", "complex") if i in _layout().monomer_enzymes else ("complex", "protein")
    )
    wid = _layout().enzymes[i]
    state[right]["counts"][wid] = 0
    state[wrong]["counts"][wid] = before["enzymes"][i]
    state["enzymes"] = dict(zip(_layout().enzymes, before["enzymes"], strict=True))
    with pytest.raises(AssertionError, match="live enzymes"):
        _assert_source_inputs(process, state, before, 0)


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_karr_protein_modification_l2_replay_identity_per_tick(rng_seed: int) -> None:
    process = KarrProteinModificationProcess({"rng_seed": int(rng_seed)})
    with h5py.File(_TRACE_PATH, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).item())
        assert n_ticks == 100
        assert int(np.asarray(trace["metadata/rng_seed"][()]).item()) == rng_seed
        assert set(trace["states_before"]) == set(trace["states_after"]) == set(_OBSERVABLES)
        mutated = dict.fromkeys(set(_OBSERVABLES) - _PASS_THROUGH, 0)
        for tick in range(n_ticks):
            before = _before_vectors(trace, tick)
            state = _source_state(process, before)
            _assert_source_inputs(process, state, before, tick)
            update = process.next_update(1.0, state)
            _apply_update(state, update, process)
            for observable in _OBSERVABLES:
                oc_after = _project(process, state, observable)
                if observable in mutated and np.any(oc_after != before[observable]):
                    mutated[observable] += 1
                karr_after = _vector(trace, "states_after", observable, tick)
                _assert_identity_or_tolerance(
                    tick=tick, observable=observable, oc_after=oc_after, karr_after=karr_after
                )
        assert all(mutated.values()), f"Replay failed to exercise every mutated output: {mutated}"
