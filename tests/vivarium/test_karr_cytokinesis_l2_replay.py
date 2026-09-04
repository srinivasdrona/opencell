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

from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess

_TRACE_PROCESS_NAME = "Cytokinesis"
_OBSERVABLES = ('substrates', 'enzymes', 'boundEnzymes')

# Observables Karr records but `next_update` does not write into. Their
# `oc_after` MUST be rebuilt from `states_before` (Rule 7 pass-through
# provenance).
_PASS_THROUGH = frozenset({'boundEnzymes', 'enzymes'})

# Rule 4b manifest (declared for mechanical lint coverage).
_SCRATCH_RESET = {}

# Optional explicit observable->WID attribute mapping. Any missing or unknown
# attr falls back to heuristic inference from process attrs / state schema.
_OBSERVABLE_TO_WIDS_ATTR = {'substrates': 'substrate_wids', 'enzymes': 'enzyme_wids', 'boundEnzymes': 'enzyme_wids'}

# L2.1 harness overrides. Three optional dicts that close the
# Karr-trace-vs-OC-state schema gap discovered during the Pattern A audit.
#
#   canonical_wids:       Override the heuristic wid inference. Use when OC's
#                         process exposes wids in a different set/order than
#                         Karr's MATLAB-source declaration.
#   store_path_override:  Override the harness's default (state-key, sub-key)
#                         path for an observable. Use when OC's ports_schema
#                         puts an observable in a non-standard nested store.
#   index_projection_attr: Map observable -> process attr name whose value is
#                         an integer-array slice into Karr's full-compartment
#                         vector. Use when Karr dumps the whole proteome /
#                         metabolome but OC only tracks an active subset.
#
# Source: data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/
#         +process/Cytokinesis.m (lines 77-87)
_CANONICAL_WIDS = {
    'substrates': ['PI', 'H2O', 'H'],
    'enzymes': ['MG_224_9MER_GTP', 'MG_224_9MER_GDP', 'MG_224_MONOMER_GDP', 'MG_224_MONOMER_GTP'],
    'boundEnzymes': ['MG_224_9MER_GTP', 'MG_224_9MER_GDP', 'MG_224_MONOMER_GDP', 'MG_224_MONOMER_GTP'],
}
_STORE_PATH_OVERRIDE: dict[str, tuple[str, ...]] = {}
_INDEX_PROJECTION_ATTR: dict[str, str] = {}

# Ring/geometry/chromosome witness scalars recorded ONLY by anchor-window
# event traces (window_contract='anchor', signal_kind='diameter_decrease';
# see extract_per_process_traces_v2.m:merge_event_observables). Absent from
# the standard 100-tick trace, whose states_before/after only carry
# substrates/enzymes/boundEnzymes/chromosome(full-object) -- Cytokinesis is
# genuinely quiescent (chromosome never segregates) for the whole
# cell-birth window, so the ports_schema() defaults (segregated=False,
# ring at its initial cell-birth geometry) happen to already be correct
# there and no overlay was ever needed. The event window is centered on the
# real ring-assembly/pinch transition, so replaying it correctly requires
# feeding Karr's own recorded per-tick ring/geometry/chromosome snapshot
# into `next_update`'s input state -- without this, `state` is rebuilt
# fresh from `build_state_template` every tick (chromosome.segregated
# always defaults to False), the `if segregated:` gate in `next_update`
# never fires, and every tick silently no-ops regardless of what Karr's
# trace shows really happened.
_RING_WITNESS_FIELDS: dict[str, tuple[str, str, type]] = {
    "chromosome_segregated": ("chromosome", "segregated", bool),
    "pinchedDiameter": ("geometry", "pinchedDiameter", float),
    "ftsZRing_numEdgesOneStraight": ("ftsZRing", "numEdgesOneStraight", int),
    "ftsZRing_numEdgesTwoStraight": ("ftsZRing", "numEdgesTwoStraight", int),
    "ftsZRing_numEdgesTwoBent": ("ftsZRing", "numEdgesTwoBent", int),
    "ftsZRing_numResidualBent": ("ftsZRing", "numResidualBent", int),
}


def _has_ring_witnesses(trace: h5py.File) -> bool:
    return "chromosome_segregated" in trace["states_before"]


def _overlay_ring_witness_state(trace: h5py.File, tick: int, state: dict[str, object]) -> None:
    """Overlay Karr's recorded ring/geometry/chromosome witnesses (see
    `_RING_WITNESS_FIELDS`) into `state`, mutating the relevant nested port
    dicts in place. No-op if the trace lacks these fields (standard trace)."""
    if not _has_ring_witnesses(trace):
        return
    for trace_key, (port, field, caster) in _RING_WITNESS_FIELDS.items():
        raw = cell_vector(trace, "states_before", trace_key, tick)[0]
        state.setdefault(port, {})[field] = caster(raw)


def _assert_ring_witness_after(
    trace: h5py.File,
    tick: int,
    update: dict[str, object],
) -> None:
    """Cross-check `next_update`'s emitted geometry/ftsZRing absolute values
    (Karr's real completion signal + the 4 ring-state witnesses that gate
    it -- see merge_event_observables's docstring) against Karr's own
    states_after snapshot for the same tick. `chromosome.segregated` is
    read-only input to this process (never written by `next_update`), so
    it has no after-state to compare."""
    if not _has_ring_witnesses(trace):
        return
    geometry_update = update.get("geometry")
    ring_update = update.get("ftsZRing")
    checks: list[tuple[str, str, object]] = [
        ("pinchedDiameter", "geometry", geometry_update),
        ("ftsZRing_numEdgesOneStraight", "ftsZRing", ring_update),
        ("ftsZRing_numEdgesTwoStraight", "ftsZRing", ring_update),
        ("ftsZRing_numEdgesTwoBent", "ftsZRing", ring_update),
        ("ftsZRing_numResidualBent", "ftsZRing", ring_update),
    ]
    for trace_key, port, port_update in checks:
        if not isinstance(port_update, dict):
            continue
        _, field, caster = _RING_WITNESS_FIELDS[trace_key]
        karr_val = caster(cell_vector(trace, "states_after", trace_key, tick)[0])
        if field not in port_update:
            continue
        oc_val = caster(port_update[field])
        if oc_val != karr_val:
            pytest.fail(
                "L2a ring-witness mismatch: "
                f"tick={tick}, field={port}.{field}, oc={oc_val}, karr={karr_val}"
            )


def _assert_delta_integral(label: str, deltas: dict[str, float]) -> None:
    _assert_delta_integral_shared(label, deltas)


def _apply_update(
    state: dict[str, object],
    update: dict[str, object],
    process: KarrCytokinesisProcess,
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
def test_karr_cytokinesis_l2_replay_identity_per_tick(rng_seed: int) -> None:
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
    process = KarrCytokinesisProcess({"rng_seed": int(rng_seed)})
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
        _overlay_ring_witness_state(trace, tick, state)
        before_vectors = {
            observable: project_karr_vector(
                process,
                observable,
                cell_vector(trace, "states_before", observable, tick),
                index_projection_attr=_INDEX_PROJECTION_ATTR,
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
        refresh_allocator_views(process, state)

        update = process.next_update(1.0, state)
        _assert_ring_witness_after(trace, tick, update)
        _apply_update(state, update, process)

        for observable in _OBSERVABLES:
            karr_after = project_karr_vector(
                process,
                observable,
                cell_vector(trace, "states_after", observable, tick),
                index_projection_attr=_INDEX_PROJECTION_ATTR,
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
    """Resolve the event-window trace path for Cytokinesis (anchor window on
    ftsZRing pinch-diameter decrease)."""
    rel = Path(
        f"data/m1_sources/karr_native/per_process_traces_v2_event_s{seed:03d}/Cytokinesis_4000ticks.mat"
    )
    candidates = [_REPO_ROOT / rel, Path("E:/opencell") / rel, Path("/mnt/e/opencell") / rel]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


@pytest.mark.parametrize("rng_seed", [0], ids=["event_seed_0"])
def test_karr_cytokinesis_l2_event_replay(rng_seed: int) -> None:
    """L2 replay on an event-window trace. Cytokinesis is quiescent at cell birth;
    the anchor-window trace (window_contract='anchor', signal_kind='diameter_decrease')
    captures the first ftsZ-ring pinch-diameter decrease event."""
    trace_path = _resolve_event_trace_path(rng_seed)
    if not trace_path.exists():
        pytest.skip(f"Event-window trace not found: {trace_path}")

    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 4000

        mutated_obs = tuple(o for o in _OBSERVABLES if o not in _PASS_THROUGH)
        mutated_tick_counts = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.skip(
                f"Event-window trace seed {rng_seed} has no events. "
                f"Per-observable counts: {mutated_tick_counts}."
            )

        _run_replay(trace, n_ticks, int(rng_seed))
