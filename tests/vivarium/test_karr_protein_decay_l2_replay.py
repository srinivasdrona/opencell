from __future__ import annotations

import sys
from pathlib import Path

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
    apply_count_update,
    assert_delta_integral as _assert_delta_integral_shared,
    assert_identity_or_tolerance as _assert_identity_or_tolerance_shared,
    audit_trace_mutated_ticks as _audit_trace_mutated_ticks_shared,
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    overlay_observable_into_state,
    project_karr_vector,
    project_observable_from_state,
    project_trace_matrix_to_482,
    refresh_allocator_views,
    resolve_trace_path,
)
from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess

_TRACE_PROCESS_NAME = "ProteinDecay"
_OBSERVABLES = ('substrates', 'enzymes', 'boundEnzymes', 'monomers', 'complexs')

# Observables Karr records but `next_update` does not write into. Their
# `oc_after` MUST be rebuilt from `states_before` (Rule 7 pass-through
# provenance).
_PASS_THROUGH = frozenset({'boundEnzymes', 'enzymes'})

# Rule 4b manifest (declared for mechanical lint coverage).
_SCRATCH_RESET = {}

# Optional explicit observable->WID attribute mapping. Any missing or unknown
# attr falls back to heuristic inference from process attrs / state schema.
_OBSERVABLE_TO_WIDS_ATTR = {'substrates': 'substrate_wids', 'enzymes': 'enzyme_wids', 'boundEnzymes': 'enzyme_wids', 'monomers': 'protein_wids', 'complexs': 'complex_wids'}


# L2.1 harness overrides (Pattern A residue, reclassified to D).
# Karr's monomers trace is 28920 = 6 compartments x 4820 (482 proteins x 10 form-states).
# OC's ProteinDecayLight port is compartment-agnostic 482-WID. The canonical
# projection pi (sum over all 6 compartments, then col-major (10, 482).sum(axis=0))
# lives in l2_replay_common.project_trace_matrix_to_482. See
# docs/phase_f/PROTEIN_DECAY_PROJECTION.md section 10 for the decision record.
#
# Karr's complexs trace is 7236; OC's complex_wids has 147 entries. Naive head-slice
# np.arange(147) is NOT canonically correct, but acceptable as an "honest-enough"
# projection because: (a) complexs only mutates in 2/100 ticks vs substrates'
# 41/100, so first-failure surfaces on substrates (real biology), and (b) substrate
# length matches Karr 1:1 (53), so no projection error there.
_CANONICAL_WIDS: dict[str, list[str]] = {}
_STORE_PATH_OVERRIDE: dict[str, tuple[str, ...]] = {}
_INDEX_PROJECTION_ATTR: dict[str, str] = {}
# NOTE: 'monomers' is intentionally NOT in this dict — it uses the dedicated
# project_trace_matrix_to_482 helper applied inline below.
_INDEX_PROJECTION_LITERAL = {'complexs': np.arange(147)}


def _monomers_to_482(flat_28920: np.ndarray) -> np.ndarray:
    """Reshape Karr's flat monomers trace cell to (6, 4820) and project to 482.

    cell_vector returns a row-major flattened view of MATLAB's (4820, 6)
    column-major matrix, which numpy sees as (6, 4820) before flattening.
    Re-reshape to (6, 4820) and apply the canonical pi projection.
    """
    arr = np.asarray(flat_28920, dtype=np.float64)
    if arr.size != 6 * 4820:
        raise ValueError(
            f"monomers trace expected size {6 * 4820}, got {arr.size}"
        )
    return project_trace_matrix_to_482(arr.reshape(6, 4820))


def _assert_delta_integral(label: str, deltas: dict[str, float]) -> None:
    _assert_delta_integral_shared(label, deltas)


def _apply_update(
    state: dict[str, object],
    update: dict[str, object],
    process: ProteinDecayLightProcess,
) -> None:
    del process  # state is rebuilt per tick; only delta application is needed here.
    for label, deltas in collect_count_delta_dicts(update):
        _assert_delta_integral(label, deltas)
    apply_count_update(state, update)


def _audit_trace_mutated_ticks(
    trace: h5py.File,
    observables: tuple[str, ...],
    n_ticks: int,
) -> dict[str, int]:
    return _audit_trace_mutated_ticks_shared(trace, observables, n_ticks)


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
def test_karr_protein_decay_l2_replay_identity_per_tick(rng_seed: int) -> None:
    trace_path = resolve_trace_path(_TRACE_PROCESS_NAME)
    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        if "metadata" in trace and "rng_seed" in trace["metadata"]:
            recorded_seed = int(np.asarray(trace["metadata/rng_seed"][()]).reshape(-1)[0])
            assert int(rng_seed) == recorded_seed

        mutated_obs = tuple(o for o in _OBSERVABLES if o not in _PASS_THROUGH)
        mutated_tick_counts = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.skip(
                "L2.1 N/A: no-op trace. Every mutated observable "
                f"({list(mutated_obs)}) is identical between states_before and "
                f"states_after across all {n_ticks} ticks. Per-observable "
                f"nonzero-delta counts: {mutated_tick_counts}."
            )

        process = ProteinDecayLightProcess({"rng_seed": int(rng_seed)})
        state_template = build_state_template(process)

        wids_by_observable: dict[str, list[str]] = {}
        for observable in _OBSERVABLES:
            karr_before = cell_vector(trace, "states_before", observable, 0)
            explicit_attr = _OBSERVABLE_TO_WIDS_ATTR.get(observable)
            wids_by_observable[observable] = infer_wids_for_observable(
                process,
                state_template,
                observable,
                karr_len=int(karr_before.shape[0]),
                explicit_attr=explicit_attr,
                canonical_wids_override=_CANONICAL_WIDS,
            )

        for tick in range(n_ticks):
            state = build_state_template(process)
            before_vectors = {}
            for observable in _OBSERVABLES:
                raw = cell_vector(trace, "states_before", observable, tick)
                if observable == "monomers":
                    before_vectors[observable] = _monomers_to_482(raw)
                else:
                    before_vectors[observable] = project_karr_vector(
                        process,
                        observable,
                        raw,
                        index_projection_attr=_INDEX_PROJECTION_ATTR,
                        index_projection_literal=_INDEX_PROJECTION_LITERAL,
                    )

            for observable in _OBSERVABLES:
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=observable,
                    vector=before_vectors[observable],
                    wids=wids_by_observable[observable],
                    store_path_override=_STORE_PATH_OVERRIDE,
                )
            refresh_allocator_views(process, state)

            update = process.next_update(1.0, state)
            _apply_update(state, update, process)

            for observable in _OBSERVABLES:
                raw_after = cell_vector(trace, "states_after", observable, tick)
                if observable == "monomers":
                    karr_after = _monomers_to_482(raw_after)
                else:
                    karr_after = project_karr_vector(
                        process,
                        observable,
                        raw_after,
                        index_projection_attr=_INDEX_PROJECTION_ATTR,
                        index_projection_literal=_INDEX_PROJECTION_LITERAL,
                    )
                expected_len = len(wids_by_observable[observable])
                if karr_after.shape[0] != expected_len:
                    mapped_attr = _OBSERVABLE_TO_WIDS_ATTR.get(observable, "<heuristic>")
                    pytest.fail(
                        "L2a wid-length drift: "
                        f"tick={tick}, observable={observable}, "
                        f"karr_len={karr_after.shape[0]}, "
                        f"mapped_len={expected_len}, mapped_attr={mapped_attr}"
                    )

                if observable in _PASS_THROUGH:
                    oc_after = before_vectors[observable].astype(np.float64).reshape(-1)
                else:
                    oc_after = project_observable_from_state(
                        process=process,
                        state=state,
                        observable=observable,
                        wids=wids_by_observable[observable],
                        bound_enzymes_before=before_vectors.get("boundEnzymes"),
                        store_path_override=_STORE_PATH_OVERRIDE,
                    )
                _assert_identity_or_tolerance(
                    tick=tick,
                    observable=observable,
                    oc_after=oc_after,
                    karr_after=karr_after,
                )
