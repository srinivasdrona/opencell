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

from opencell.state.chromosome_store import ChromosomeStore
from opencell.vivarium.karr_chromosome_segregation import KarrChromosomeSegregationProcess

_TRACE_PROCESS_NAME = "ChromosomeSegregation"
# `segregated` is the literal Karr field this process writes (Chromosome.m
# `segregated` property, ChromosomeSegregation.m:evolveState). It is a
# top-level trace observable (states_before/after/segregated), not part of
# the `chromosome` sparse-triple group. It is present only on traces
# extracted with the anchor/event-window signal config (see
# STATUS_L21_CHROMSEG_ACTIVE_FIX.md); the standard canonical trace does not
# carry it, so the observable set is computed per-trace via
# `_observables_for_trace` below.
_BASE_OBSERVABLES = ('substrates', 'enzymes', 'boundEnzymes')

# Observables Karr records but `next_update` does not write into. Their
# `oc_after` MUST be rebuilt from `states_before` (Rule 7 pass-through
# provenance).
_PASS_THROUGH = frozenset({'boundEnzymes', 'enzymes'})

# Rule 4b manifest (declared for mechanical lint coverage).
_SCRATCH_RESET = {}

# Optional explicit observable->WID attribute mapping. Any missing or unknown
# attr falls back to heuristic inference from process attrs / state schema.
_OBSERVABLE_TO_WIDS_ATTR = {'substrates': 'substrate_wids', 'enzymes': 'enzyme_wids', 'boundEnzymes': 'enzyme_wids'}

# `segregated` is a scalar boolean-as-float observable (length-1 vector),
# not a WID-indexed vector. It is stored directly under
# `state["chromosome"]["segregated"]`, so it gets a fixed single-element WID
# list and a store-path override rather than WID inference.
_SEGREGATED_WIDS = ["segregated"]
_STORE_PATH_OVERRIDE = {"segregated": ("chromosome",)}


def _observables_for_trace(trace: h5py.File) -> tuple[str, ...]:
    if "states_before/segregated" in trace and "states_after/segregated" in trace:
        return (*_BASE_OBSERVABLES, "segregated")
    return _BASE_OBSERVABLES


def _inject_hidden_chromosome_state(trace: h5py.File, state: dict[str, object], tick: int) -> None:
    """Read-only hidden-state injection: overlay the real Chromosome
    `polymerizedRegions`/`linkingNumbers` sparse fields (plus the other 9
    CHROMOSOME_FIELDS) from `states_before/chromosome` at this tick.

    This is a genuine hidden-INPUT read (the process's gates depend on the
    chromosome's actual replication/supercoiling state), not an oracle-answer
    read: production code never opens this trace file (Rule 8); only the
    test harness does, exactly like the established
    `_inject_hidden_chromosome_state` helper in l2_2_replay_common_v2.py for
    the other chromosome-coupled processes (ChromosomeCondensation, DNARepair,
    DNADamage).
    """
    chrom_state = state.get("chromosome")
    if not isinstance(chrom_state, dict):
        return
    ds = trace["states_before/chromosome"]
    ref = ds[0, tick] if ds.shape[0] == 1 else ds[tick, 0]
    payload = trace[ref]
    if not isinstance(payload, h5py.Group):
        return
    injected = ChromosomeStore.from_hdf5_group(payload).to_state()
    chrom_state.update(injected)


def _assert_delta_integral(label: str, deltas: dict[str, float]) -> None:
    _assert_delta_integral_shared(label, deltas)


def _apply_update(
    state: dict[str, object],
    update: dict[str, object],
    process: KarrChromosomeSegregationProcess,
) -> None:
    del process  # state is rebuilt per tick; only delta application is needed here.
    for label, deltas in collect_count_delta_dicts(update):
        _assert_delta_integral(label, deltas)
    apply_count_update(state, update)
    # `collect_count_delta_dicts`/`apply_count_update` only know the standard
    # count-delta ports (substrates/protein/rna/complex/boundEnzymes/enzymes).
    # `chromosome.segregated` is a boolean "set" field emitted alongside the
    # substrate deltas (ChromosomeSegregation.m:evolveState `c.segregated =
    # true`); apply it directly so the post-update projection sees it.
    chromosome_update = update.get("chromosome")
    if isinstance(chromosome_update, dict) and "segregated" in chromosome_update:
        chrom_state = state.setdefault("chromosome", {})
        if isinstance(chrom_state, dict):
            chrom_state["segregated"] = bool(chromosome_update["segregated"])


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
def test_karr_chromosome_segregation_l2_replay_identity_per_tick(rng_seed: int) -> None:
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
        observables = _observables_for_trace(trace)
        mutated_obs = tuple(o for o in observables if o not in _PASS_THROUGH)
        _ = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)

        _run_replay(trace, n_ticks, int(rng_seed))


def _run_replay(trace: h5py.File, n_ticks: int, rng_seed: int) -> None:
    """Shared per-tick L2.1 bit-identity replay body (used by the standard and
    event-window tests). Assumes the trace is open and has been audited as active."""
    process = KarrChromosomeSegregationProcess({"rng_seed": int(rng_seed)})
    state_template = build_state_template(process)
    observables = _observables_for_trace(trace)

    wids_by_observable: dict[str, list[str]] = {}
    for observable in observables:
        if observable == "segregated":
            wids_by_observable[observable] = list(_SEGREGATED_WIDS)
            continue
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
            for observable in observables
        }

        for observable in observables:
            overlay_observable_into_state(
                process=process,
                state=state,
                observable=observable,
                vector=before_vectors[observable],
                wids=wids_by_observable[observable],
                store_path_override=_STORE_PATH_OVERRIDE,
            )
        # Hidden read-surface: the real chromosome `polymerizedRegions` /
        # `linkingNumbers` this process's gates depend on (see module
        # docstring in karr_chromosome_segregation.py). Adds the 11
        # CHROMOSOME_FIELDS keys to state["chromosome"]; does not touch
        # "segregated" (already overlaid above from states_before).
        _inject_hidden_chromosome_state(trace, state, tick)
        refresh_allocator_views(process, state)

        update = process.next_update(1.0, state)
        _apply_update(state, update, process)

        for observable in observables:
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
                store_path_override=_STORE_PATH_OVERRIDE,
            )
            _assert_identity_or_tolerance(
                tick=tick,
                observable=observable,
                oc_after=oc_after,
                karr_after=karr_after,
            )


def _resolve_event_trace_path(seed: int) -> Path:
    """Resolve the event-window trace path for ChromosomeSegregation (anchor
    window on the real `chromosome.segregated` boolean transition)."""
    rel = Path(
        f"data/m1_sources/karr_native/per_process_traces_v2_event_s{seed:03d}/ChromosomeSegregation_100ticks.mat"
    )
    candidates = [_REPO_ROOT / rel, Path("E:/opencell") / rel, Path("/mnt/e/opencell") / rel]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


@pytest.mark.parametrize("rng_seed", [0], ids=["event_seed_0"])
def test_karr_chromosome_segregation_l2_event_replay(rng_seed: int) -> None:
    """L2 replay on an event-window trace. ChromosomeSegregation is quiescent in
    the standard 100-tick canonical trace; the anchor-window trace
    (window_contract='anchor', signal_kind='boolean_transition',
    signal_field='segregated') captures the real chromosome-segregation
    completion event."""
    trace_path = _resolve_event_trace_path(rng_seed)
    if not trace_path.exists():
        pytest.skip(f"Event-window trace not found: {trace_path}")

    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 100

        mutated_obs = tuple(o for o in _observables_for_trace(trace) if o not in _PASS_THROUGH)
        mutated_tick_counts = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.skip(
                f"Event-window trace seed {rng_seed} has no events. "
                f"Per-observable counts: {mutated_tick_counts}."
            )

        _run_replay(trace, n_ticks, int(rng_seed))
