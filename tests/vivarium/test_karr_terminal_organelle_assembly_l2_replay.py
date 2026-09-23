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
    assert_delta_integral as _assert_delta_integral_shared,
)
from l2_replay_common import (
    assert_identity_or_tolerance as _assert_identity_or_tolerance_shared,
)
from l2_replay_common import (
    audit_trace_mutated_ticks as _audit_trace_mutated_ticks_shared,
)
from l2_replay_common import (
    cell_vector,
    collect_count_delta_dicts,
    resolve_trace_path,
)

from opencell.vivarium.karr_terminal_organelle_assembly import KarrTerminalOrganelleAssemblyProcess

_TRACE_PROCESS_NAME = "TerminalOrganelleAssembly"
_OBSERVABLES = ("substrates", "enzymes", "boundEnzymes")

# Observables Karr records but `next_update` does not write into. Their
# `oc_after` MUST be rebuilt from `states_before` (Rule 7 pass-through provenance).
_PASS_THROUGH = frozenset({"boundEnzymes", "enzymes"})

# Rule 4b manifest (declared for mechanical lint coverage).
_SCRATCH_RESET = {}

# Explicit observable->WID attribute mapping.
_OBSERVABLE_TO_WIDS_ATTR = {
    "substrates": "substrate_wids",
    "enzymes": "enzyme_wids",
    "boundEnzymes": "enzyme_wids",
}

TOA_MONOMERS = (
    "MG_191_MONOMER",
    "MG_192_MONOMER",
    "MG_217_MONOMER",
    "MG_218_MONOMER",
    "MG_312_MONOMER",
    "MG_317_MONOMER",
    "MG_318_MONOMER",
    "MG_386_MONOMER",
)
COMPARTMENTS = ("c", "d", "e", "m", "tc", "tm")
TOA_COMPARTMENTS_INC = ("tm", "tm", "tc", "tc", "tc", "tc", "tm", "tc")
TOA_COMPARTMENTS_UNINC = ("m", "m", "c", "c", "c", "c", "m", "c")


def _build_initial_replay_state() -> dict[str, Any]:
    """Build clean state containing the compartmental ProteinMonomer authority."""
    return {
        "protein": {
            "compartment_counts": {
                "mature": {
                    wid: {c: 0.0 for c in COMPARTMENTS}
                    for wid in TOA_MONOMERS
                }
            }
        },
        "enzymes": {},
        "boundEnzymes": {},
    }


def _overlay_substrates_into_authority(
    state: dict[str, Any],
    karr_substrates_vec: np.ndarray,
) -> None:
    """Overlay 16-element (8x2 Fortran order) substrate vector into authority."""
    mat_8x2 = karr_substrates_vec.reshape((8, 2), order="F")
    mature_store = state["protein"]["compartment_counts"]["mature"]
    for i, wid in enumerate(TOA_MONOMERS):
        inc_comp = TOA_COMPARTMENTS_INC[i]
        uninc_comp = TOA_COMPARTMENTS_UNINC[i]
        mature_store[wid][inc_comp] = float(mat_8x2[i, 0])
        mature_store[wid][uninc_comp] = float(mat_8x2[i, 1])


def _project_substrates_from_authority(state: dict[str, Any]) -> np.ndarray:
    """Project 16-element (8x2 Fortran order) substrate vector from authority."""
    mature_store = state["protein"]["compartment_counts"]["mature"]
    mat_8x2 = np.zeros((8, 2), dtype=np.float64)
    for i, wid in enumerate(TOA_MONOMERS):
        inc_comp = TOA_COMPARTMENTS_INC[i]
        uninc_comp = TOA_COMPARTMENTS_UNINC[i]
        mat_8x2[i, 0] = mature_store.get(wid, {}).get(inc_comp, 0.0)
        mat_8x2[i, 1] = mature_store.get(wid, {}).get(uninc_comp, 0.0)
    return mat_8x2.reshape(16, order="F")


def _apply_update(
    state: dict[str, Any],
    update: dict[str, Any],
) -> None:
    """Apply delta updates to authority store with delta-integrality check."""
    for label, deltas in collect_count_delta_dicts(update):
        _assert_delta_integral_shared(label, deltas)

    # Apply to compartment_counts
    protein_update = update.get("protein", {})
    comp_counts = protein_update.get("compartment_counts", protein_update)
    mature_update = comp_counts.get("mature", comp_counts)

    target_mature = state["protein"]["compartment_counts"]["mature"]
    for wid, comp_deltas in mature_update.items():
        if isinstance(comp_deltas, dict) and wid in target_mature:
            for comp, delta in comp_deltas.items():
                if comp in target_mature[wid]:
                    target_mature[wid][comp] = float(target_mature[wid][comp] + float(delta))


def _assert_identity_or_tolerance(
    *,
    tick: int,
    observable: str,
    oc_after: np.ndarray,
    karr_after: np.ndarray,
) -> None:
    _assert_identity_or_tolerance_shared(
        tick=tick,
        observable=observable,
        oc_after=oc_after,
        karr_after=karr_after,
    )


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_karr_terminal_organelle_assembly_l2_replay_identity_per_tick(rng_seed: int) -> None:
    trace_path = resolve_trace_path(_TRACE_PROCESS_NAME)
    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        if "metadata" in trace and "rng_seed" in trace["metadata"]:
            recorded_seed = int(np.asarray(trace["metadata/rng_seed"][()]).reshape(-1)[0])
            assert int(rng_seed) == recorded_seed

        mutated_obs = tuple(o for o in _OBSERVABLES if o not in _PASS_THROUGH)
        mutated_tick_counts = _audit_trace_mutated_ticks_shared(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.skip(
                "L2.1 N/A: no-op trace. Every mutated observable "
                f"({list(mutated_obs)}) is identical between states_before and "
                f"states_after across all {n_ticks} ticks. Per-observable "
                f"nonzero-delta counts: {mutated_tick_counts}."
            )

        # Construct process once outside the tick loop (Rule 5)
        process = KarrTerminalOrganelleAssemblyProcess({"rng_seed": int(rng_seed)})

        # WID-length alignment guard check (Rule 3)
        sample_substrates = cell_vector(trace, "states_before", "substrates", 0)
        assert sample_substrates.shape[0] == 16, f"Expected 16 substrate values (8x2), got {sample_substrates.shape[0]}"

        # Known mutated oracle ticks in TOA
        known_active_ticks = {6, 46, 68}

        for tick in range(n_ticks):
            # Per-tick state isolation (Rule 4)
            state = _build_initial_replay_state()

            before_vectors = {
                observable: cell_vector(trace, "states_before", observable, tick)
                for observable in _OBSERVABLES
            }

            # Overlay substrates into authority
            _overlay_substrates_into_authority(state, before_vectors["substrates"])

            # Rule 7: Pass-through observables (enzymes, boundEnzymes) rebuilt strictly from states_before
            for obs in _PASS_THROUGH:
                state[obs] = {
                    f"{obs}_{i}": float(v)
                    for i, v in enumerate(before_vectors[obs])
                }

            # Real public code path invocation (Rule 7)
            update = process.next_update(1.0, state)

            # Anti-identity and non-triviality guard (Rule 6 + Beat 4):
            # On active ticks, update must be non-empty and projected output must differ from input
            if tick in known_active_ticks:
                assert update, f"Tick {tick}: expected non-empty update on known active tick"

            _apply_update(state, update)

            # Project observable vectors after update
            projected_after: dict[str, np.ndarray] = {
                "substrates": _project_substrates_from_authority(state),
            }
            # Rule 7 pass-through provenance: pass-through observables come from states_before
            for obs in _PASS_THROUGH:
                projected_after[obs] = before_vectors[obs].copy()

            # Anti-identity assertion on active ticks: projected matrix MUST differ from input
            if tick in known_active_ticks:
                assert not np.array_equal(projected_after["substrates"], before_vectors["substrates"]), (
                    f"Tick {tick}: anti-identity violation: output equals input on known active tick"
                )

            # Integer exactness comparison across all observables (Rule 2)
            for observable in _OBSERVABLES:
                karr_after = cell_vector(trace, "states_after", observable, tick)
                oc_after = projected_after[observable]

                # Assert integrality
                assert np.array_equal(np.rint(karr_after), karr_after), f"Tick {tick}: Karr after non-integral"
                assert np.array_equal(np.rint(oc_after), oc_after), f"Tick {tick}: OC after non-integral"

                _assert_identity_or_tolerance(
                    tick=tick,
                    observable=observable,
                    oc_after=oc_after,
                    karr_after=karr_after,
                )

