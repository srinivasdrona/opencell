from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

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

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import (
    assert_identity_or_tolerance,
    audit_trace_mutated_ticks,
    cell_vector,
    project_karr_vector,
    resolve_trace_path,
)

from opencell.vivarium.karr_protein_activation import KarrProteinActivationProcess

_TRACE_PROCESS_NAME = "ProteinActivation"
_OBSERVABLES = ("substrates", "enzymes", "boundEnzymes")
_PASS_THROUGH = frozenset({"boundEnzymes", "enzymes"})
_SCRATCH_RESET: dict[str, str] = {}
_INDEX_PROJECTION_LITERAL = {"substrates": np.arange(10)}
_ACTIVE_NONCYTOSOL_COUNTS = "activation_active_noncytosol_counts"
_INACTIVE_COUNTS = "activation_inactive_counts"


def _assert_integral_delta(path: str, value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if path == "protein" and key == "activity":
                continue
            _assert_integral_delta(f"{path}.{key}", child)
        return
    numeric = float(value)
    assert numeric == float(np.rint(numeric)), (
        f"L2a delta non-integral: path={path}, value={numeric}"
    )


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    _assert_integral_delta("", update)
    for wid, value in update.get("protein", {}).get("activity", {}).items():
        state["protein"]["activity"][wid] = int(value)
    for store_name in ("protein", "complex"):
        store_update = update.get(store_name, {})
        for wid, delta in store_update.get("counts", {}).items():
            state[store_name]["counts"][wid] += float(delta)
        for branch_name in (_ACTIVE_NONCYTOSOL_COUNTS, _INACTIVE_COUNTS):
            for wid, compartment_updates in store_update.get(branch_name, {}).items():
                for compartment, delta in compartment_updates.items():
                    state[store_name][branch_name][wid][compartment] += float(delta)


def _state_from_trace_substrates(
    process: KarrProteinActivationProcess,
    substrates_before: np.ndarray,
) -> dict[str, Any]:
    state = process.canonical_state()
    substrate_index = {wid: index for index, wid in enumerate(process.substrate_wids)}
    for wid in process.regulated_protein_wids:
        store = state[process.store_by_wid[wid]]
        store["counts"][wid] = float(substrates_before[substrate_index[wid]])
        for compartment in range(1, process.compartment_count):
            key = process.compartment_keys[compartment]
            store[_ACTIVE_NONCYTOSOL_COUNTS][wid][key] = 0.0
        for key in process.compartment_keys:
            store[_INACTIVE_COUNTS][wid][key] = 0.0
    return state


def _project_substrates_after(
    process: KarrProteinActivationProcess,
    state: dict[str, Any],
    substrates_before: np.ndarray,
) -> np.ndarray:
    projected = substrates_before.copy()
    active, _ = process.state_matrices(state)
    substrate_index = {wid: index for index, wid in enumerate(process.substrate_wids)}
    for row, wid in enumerate(process.regulated_protein_wids):
        projected[substrate_index[wid]] = active[row, 0]
    return projected


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_karr_protein_activation_l2_replay_identity_per_tick(rng_seed: int) -> None:
    trace_path = resolve_trace_path(_TRACE_PROCESS_NAME)
    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        if "metadata" in trace and "rng_seed" in trace["metadata"]:
            recorded_seed = int(np.asarray(trace["metadata/rng_seed"][()]).reshape(-1)[0])
            assert int(rng_seed) == recorded_seed

        mutated_tick_counts = audit_trace_mutated_ticks(trace, ("substrates",), n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.skip(
                "L2.1 N/A: no-op trace. substrates is identical between "
                f"states_before and states_after across all {n_ticks} ticks."
            )

        process = KarrProteinActivationProcess({"rng_seed": int(rng_seed)})
        for tick in range(n_ticks):
            before_vectors = {
                observable: project_karr_vector(
                    process,
                    observable,
                    cell_vector(trace, "states_before", observable, tick),
                    index_projection_literal=_INDEX_PROJECTION_LITERAL,
                )
                for observable in _OBSERVABLES
            }
            state = _state_from_trace_substrates(process, before_vectors["substrates"])
            update = process.next_update(1.0, state)
            _apply_update(state, update)

            for observable in _OBSERVABLES:
                karr_after = project_karr_vector(
                    process,
                    observable,
                    cell_vector(trace, "states_after", observable, tick),
                    index_projection_literal=_INDEX_PROJECTION_LITERAL,
                )
                expected_length = (
                    len(process.substrate_wids)
                    if observable == "substrates"
                    else before_vectors[observable].shape[0]
                )
                assert karr_after.shape[0] == expected_length, (
                    "L2a wid-length drift: "
                    f"tick={tick}, observable={observable}, "
                    f"karr_len={karr_after.shape[0]}, "
                    f"mapped_len={expected_length}"
                )

                if observable == "substrates":
                    oc_after = _project_substrates_after(
                        process,
                        state,
                        before_vectors["substrates"],
                    )
                else:
                    oc_after = before_vectors[observable].copy()
                assert_identity_or_tolerance(
                    tick=tick,
                    observable=observable,
                    oc_after=oc_after,
                    karr_after=karr_after,
                )
