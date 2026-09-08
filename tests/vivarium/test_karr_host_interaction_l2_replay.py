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
from l21_evidence_common import skip_or_fail_missing_artifact

from opencell.vivarium.karr_host_interaction import KarrHostInteractionProcess

_TRACE_PROCESS_NAME = "HostInteraction"
_OBSERVABLES = ('substrates', 'enzymes', 'boundEnzymes')

# Host boolean surface (event-window traces only -- see
# _resolve_event_trace_path/test_karr_host_interaction_l2_event_replay
# below). HostInteraction.evolveState() recomputes these 4 Host booleans
# (isBacteriumAdherent flattened as-is; isTLRActivated flattened into its
# 3 tlrIndexs_1/2/6 components) fresh every tick purely from the CURRENT
# enzyme copy numbers -- see HostInteraction.m:266-303 and Host.m's
# tlrIndexs_1=1/tlrIndexs_2=2/tlrIndexs_6=3. Compared bit-exact (never
# tolerance), matching Karr's own boolean semantics.
_HOST_BOOLEAN_OBSERVABLES = (
    "isBacteriumAdherent",
    "isTLRActivated_1",
    "isTLRActivated_2",
    "isTLRActivated_3",
    "isNFkBActivated",
    "isInflammatoryResponseActivated",
)
_HOST_BOOLEAN_CELL_KEY = {
    "isBacteriumAdherent": "host_attached",
    "isTLRActivated_1": "host_tlr1_activated",
    "isTLRActivated_2": "host_tlr2_activated",
    "isTLRActivated_3": "host_tlr6_activated",
    "isNFkBActivated": "host_nfkb_activated",
    "isInflammatoryResponseActivated": "host_inflammatory_response_activated",
}

# Observables Karr records but `next_update` does not write into. Their
# `oc_after` MUST be rebuilt from `states_before` (Rule 7 pass-through
# provenance).
_PASS_THROUGH = frozenset({'boundEnzymes', 'enzymes'})

# Rule 4b manifest (declared for mechanical lint coverage).
_SCRATCH_RESET = {}

# Optional explicit observable->WID attribute mapping. Any missing or unknown
# attr falls back to heuristic inference from process attrs / state schema.
_OBSERVABLE_TO_WIDS_ATTR = {'substrates': 'substrate_wids', 'enzymes': 'enzyme_wids', 'boundEnzymes': 'enzyme_wids'}


def _assert_delta_integral(label: str, deltas: dict[str, float]) -> None:
    _assert_delta_integral_shared(label, deltas)


def _apply_update(
    state: dict[str, object],
    update: dict[str, object],
    process: KarrHostInteractionProcess,
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
def test_karr_host_interaction_l2_replay_identity_per_tick(rng_seed: int) -> None:
    trace_path = resolve_trace_path(_TRACE_PROCESS_NAME)
    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        if "metadata" in trace and "rng_seed" in trace["metadata"]:
            recorded_seed = int(np.asarray(trace["metadata/rng_seed"][()]).reshape(-1)[0])
            assert int(rng_seed) == recorded_seed

        # Quiet-process guard: do not skip. Karr trace may be no-op across all
        # mutated observables, but we still want to assert OC's next_update is
        # also no-op (else OC silently drifting would never be caught).
        mutated_obs = tuple(o for o in _OBSERVABLES if o not in _PASS_THROUGH)
        _ = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)

        _run_replay(trace, n_ticks, int(rng_seed))


def _run_replay(trace: h5py.File, n_ticks: int, rng_seed: int) -> None:
    """Shared per-tick L2.1 bit-identity replay body (used by the standard and
    event-window tests). Assumes the trace is open and has been audited as active."""
    del rng_seed  # KarrHostInteractionProcess is deterministic (no RNG; see class docstring).
    process = KarrHostInteractionProcess({})
    state_template = build_state_template(process)

    has_host_boolean_surface = _HOST_BOOLEAN_OBSERVABLES[0] in trace["states_after"]

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
        )

    for tick in range(n_ticks):
        state = build_state_template(process)
        before_vectors = {
            observable: cell_vector(trace, "states_before", observable, tick)
            for observable in _OBSERVABLES
        }

        for observable in _OBSERVABLES:
            overlay_observable_into_state(
                process=process,
                state=state,
                observable=observable,
                vector=before_vectors[observable],
                wids=wids_by_observable[observable],
            )
        refresh_allocator_views(process, state)

        update = process.next_update(1.0, state)
        _apply_update(state, update, process)
        # _apply_update only merges the count-store observables
        # (substrates/enzymes/boundEnzymes); HostInteraction's real output
        # is a "set"-style `cell.*` boolean surface (see
        # KarrHostInteractionProcess.ports_schema), so merge it separately.
        cell_update = update.get("cell")
        if isinstance(cell_update, dict):
            state.setdefault("cell", {}).update(cell_update)

        for observable in _OBSERVABLES:
            karr_after = cell_vector(trace, "states_after", observable, tick)
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
            )
            _assert_identity_or_tolerance(
                tick=tick,
                observable=observable,
                oc_after=oc_after,
                karr_after=karr_after,
            )

        if has_host_boolean_surface:
            for observable in _HOST_BOOLEAN_OBSERVABLES:
                karr_after = cell_vector(trace, "states_after", observable, tick)
                cell_key = _HOST_BOOLEAN_CELL_KEY[observable]
                oc_value = bool(state.get("cell", {}).get(cell_key, False))
                karr_value = bool(float(karr_after[0]) != 0.0)
                if oc_value != karr_value:
                    pytest.fail(
                        "L2.1 host boolean cascade mismatch: "
                        f"tick={tick}, observable={observable} (cell.{cell_key}), "
                        f"oc={oc_value}, karr={karr_value}"
                    )


def _resolve_event_trace_path(seed: int) -> Path:
    """Resolve the event-window trace path for HostInteraction (a genuine
    fixed, host-conditioned window -- see
    tmp/l21_host_interaction_fixed_active_window.m and
    docs/phase_f/l2_1/HOSTINTERACTION_ACTIVE_WINDOW_DECISION.md. Karr's
    fitted seed-0 initial condition already carries nonzero copy numbers
    for every enzyme HostInteraction.m reads, so host.isBacteriumAdherent
    (and everything it gates) is TRUE from tick 1 onward -- a false->true
    anchor SEARCH can never terminate for this process, so this window is
    a plain fixed capture, not a discovered transition)."""
    rel = Path(
        f"data/m1_sources/karr_native/per_process_traces_v2_event_s{seed:03d}/HostInteraction_100ticks.mat"
    )
    candidates = [_REPO_ROOT / rel, Path("E:/opencell") / rel, Path("/mnt/e/opencell") / rel]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


@pytest.mark.parametrize("rng_seed", [0], ids=["event_seed_0"])
def test_karr_host_interaction_l2_event_replay(rng_seed: int) -> None:
    """L2 replay on a genuine host-conditioned window (fixed, not anchor --
    see _resolve_event_trace_path docstring). HostInteraction is quiescent
    on substrates/enzymes/boundEnzymes in EVERY trace (it never mutates
    them; see HostInteraction.m:266-303) -- its real "activity" signal is
    the host boolean surface (isBacteriumAdherent/isTLRActivated_1..3/
    isNFkBActivated/isInflammatoryResponseActivated) being non-degenerately
    True, a LEVEL signal recomputed fresh every tick, not a discrete event
    (see docs/phase_f/l2_1/HOSTINTERACTION_ACTIVE_WINDOW_DECISION.md)."""
    trace_path = _resolve_event_trace_path(rng_seed)
    if not trace_path.exists():
        skip_or_fail_missing_artifact(trace_path, "HostInteraction", "Event-window trace not found")

    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        has_host_boolean_surface = _HOST_BOOLEAN_OBSERVABLES[0] in trace["states_after"]
        host_active = False
        if has_host_boolean_surface:
            for observable in _HOST_BOOLEAN_OBSERVABLES:
                for tick in range(n_ticks):
                    if float(cell_vector(trace, "states_after", observable, tick)[0]) != 0.0:
                        host_active = True
                        break
                if host_active:
                    break

        mutated_obs = tuple(o for o in _OBSERVABLES if o not in _PASS_THROUGH)
        mutated_tick_counts = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0 and not host_active:
            pytest.skip(
                f"Event-window trace seed {rng_seed} has no events. "
                f"Per-observable counts: {mutated_tick_counts}, host_active={host_active}."
            )

        _run_replay(trace, n_ticks, int(rng_seed))
