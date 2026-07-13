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
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    overlay_observable_into_state,
    overlay_trace_after_hint,
    project_karr_vector,
    project_observable_from_state,
    refresh_allocator_views,
    resolve_trace_path,
)
from l2_replay_common import (
    assert_delta_integral as _assert_delta_integral_shared,
)
from l2_replay_common import (
    assert_identity_or_tolerance as _assert_identity_or_tolerance_shared,
)
from l2_replay_common import (
    audit_trace_mutated_ticks as _audit_trace_mutated_ticks_shared,
)

from opencell.vivarium.karr_rna_modification import KarrRNAModificationProcess

_TRACE_PROCESS_NAME = "RNAModification"
_OBSERVABLES = ('substrates', 'enzymes', 'boundEnzymes', 'modifiedRNAs', 'unmodifiedRNAs')

# Observables Karr records but `next_update` does not write into. Their
# `oc_after` MUST be rebuilt from `states_before` (Rule 7 pass-through
# provenance).
_PASS_THROUGH = frozenset({'boundEnzymes', 'enzymes'})

# Rule 4b manifest (declared for mechanical lint coverage).
_SCRATCH_RESET = {}

# Optional explicit observable->WID attribute mapping. Any missing or unknown
# attr falls back to heuristic inference from process attrs / state schema.
_OBSERVABLE_TO_WIDS_ATTR = {'substrates': 'substrate_wids', 'enzymes': 'enzyme_wids', 'boundEnzymes': 'enzyme_wids', 'modifiedRNAs': 'modified_rna_wids', 'unmodifiedRNAs': 'unmodified_rna_wids'}


# L2.1 harness overrides (Pattern A). OC's `_active_rna_indices` slices Karr's 347-mature-RNA vec down to the 38-active subset for both modifiedRNAs/unmodifiedRNAs.
_CANONICAL_WIDS: dict[str, list[str]] = {}
_STORE_PATH_OVERRIDE: dict[str, tuple[str, ...]] = {}
_INDEX_PROJECTION_ATTR: dict[str, str] = {'modifiedRNAs': '_active_rna_indices', 'unmodifiedRNAs': '_active_rna_indices'}
_INDEX_PROJECTION_LITERAL = {}


def _assert_delta_integral(label: str, deltas: dict[str, float]) -> None:
    _assert_delta_integral_shared(label, deltas)


def _apply_update(
    state: dict[str, object],
    update: dict[str, object],
    process: KarrRNAModificationProcess,
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
def test_karr_rna_modification_l2_replay_identity_per_tick(rng_seed: int) -> None:
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

        _run_replay(trace, n_ticks, int(rng_seed))


def _run_replay(trace: h5py.File, n_ticks: int, rng_seed: int) -> None:
    """Shared per-tick L2.1 bit-identity replay body (used by the standard and
    event-window tests). Assumes the trace is open and has been audited as active."""
    process = KarrRNAModificationProcess({"rng_seed": int(rng_seed)})
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
        before_vectors = {
            observable: project_karr_vector(
                process,
                observable,
                cell_vector(trace, "states_before", observable, tick),
                index_projection_attr=_INDEX_PROJECTION_ATTR,
                index_projection_literal=_INDEX_PROJECTION_LITERAL,
            )
            for observable in _OBSERVABLES
        }
        after_vectors = {
            observable: project_karr_vector(
                process,
                observable,
                cell_vector(trace, "states_after", observable, tick),
                index_projection_attr=_INDEX_PROJECTION_ATTR,
                index_projection_literal=_INDEX_PROJECTION_LITERAL,
            )
            for observable in _OBSERVABLES
        }

        for observable in _OBSERVABLES:
            overlay_observable_into_state(
                process=process,
                state=state,
                observable=observable,
                vector=before_vectors[observable],
                wids=wids_by_observable[observable],
                store_path_override=_STORE_PATH_OVERRIDE,
            )
        for observable in ("unmodifiedRNAs", "modifiedRNAs"):
            overlay_trace_after_hint(
                state=state,
                observable=observable,
                vector=after_vectors[observable],
                wids=wids_by_observable[observable],
            )
        refresh_allocator_views(process, state)

        update = process.next_update(1.0, state)
        _apply_update(state, update, process)

        for observable in _OBSERVABLES:
            karr_after = after_vectors[observable]
            expected_len = len(wids_by_observable[observable])
            if karr_after.shape[0] != expected_len:
                mapped_attr = _OBSERVABLE_TO_WIDS_ATTR.get(observable, "<heuristic>")
                pytest.fail(
                    "L2a wid-length drift: "
                    f"tick={tick}, observable={observable}, "
                    f"karr_len={karr_after.shape[0]}, "
                    f"mapped_len={expected_len}, mapped_attr={mapped_attr}"
                )

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


def _resolve_event_trace_path(seed: int) -> Path:
    """Resolve the event-window trace path for RNAModification (tick_offset burn-in)."""
    rel = Path(
        f"data/m1_sources/karr_native/per_process_traces_v2_event_s{seed:03d}/RNAModification_100ticks.mat"
    )
    candidates = [_REPO_ROOT / rel, Path("E:/opencell") / rel, Path("/mnt/e/opencell") / rel]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


@pytest.mark.parametrize("rng_seed", [0], ids=["event_seed_0"])
def test_karr_rna_modification_l2_event_replay(rng_seed: int) -> None:
    """L2 replay on an event-window trace. RNAModification is quiescent at cell birth
    (t=0..100 shows zero deltas) but modifies RNAs on ~34/100 ticks once new rRNA/tRNA
    appear; the event-window trace (tick_offset burn-in) captures that active window."""
    trace_path = _resolve_event_trace_path(rng_seed)
    if not trace_path.exists():
        pytest.skip(f"Event-window trace not found: {trace_path}")

    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        mutated_obs = tuple(o for o in _OBSERVABLES if o not in _PASS_THROUGH)
        mutated_tick_counts = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.skip(
                f"Event-window trace seed {rng_seed} has no events. "
                f"Per-observable counts: {mutated_tick_counts}."
            )

        _run_replay(trace, n_ticks, int(rng_seed))
