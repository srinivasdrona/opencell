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

from opencell.util.mcg16807_state_codec import draw_and_advance as _draw_and_advance
from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess
from scripts.l2_event.analyze_cytokinesis_randstream_probe import (  # noqa: E402
    scalar_state as _rand_scalar_state,
)
from scripts.l2_event.analyze_cytokinesis_randstream_probe import (  # noqa: E402
    steps_between as _rand_steps_between,
)

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


def _has_randstream_capture(trace: h5py.File) -> bool:
    """True for a trace produced by the hash-bound, randStream-state-
    capturing extractor (extract_per_process_traces_v2.m, commit
    `153d726` -- see STATUS_L21_CYTOKINESIS_ACTIVE_FIX.md Update 3).
    Absent from every pre-existing trace (including the accepted
    seed-0 M_ticks=4000 event trace this repo currently ships), so every
    randStream-ledger check below is strictly additive and never runs
    against a trace that cannot support it."""
    return "randStreamState" in trace["states_before"]


def _karr_randstream_state(trace: h5py.File, group: str, tick: int) -> int:
    """Read Karr's real captured `this.randStream.state` (a scalar
    Lehmer/mcg16807 state) for one tap point of one tick, as a plain
    Python int -- the exact representation `_Mcg16807.get_state()`/
    `.set_state()` use (see karr_protein_decay_light.py)."""
    return _rand_scalar_state(cell_vector(trace, group, "randStreamState", tick)[0])


def _assert_randstream_ledger(
    trace: h5py.File,
    tick: int,
    process: KarrCytokinesisProcess,
    draw_count_before_tick: int,
    oc_state_before_tick: int,
) -> None:
    """First-divergence ledger (task step 3): verify OC's isolated replay
    consumed EXACTLY the same number of real Lehmer-recurrence draws Karr's
    own process consumed during this tick's evolveState() call, and that
    OC's RNG state entering the NEXT tick matches Karr's own recorded exit
    state exactly -- never inferred, always independently re-derived from
    Karr's own captured entry/exit states via forward-stepping the SAME
    recurrence (see `_rand_steps_between`, duplicated from
    `analyze_cytokinesis_randstream_probe.py`'s vetted, oracle-independent
    implementation). No-op if the trace predates randStream-state capture.

    `oc_state_before_tick`/`draw_count_before_tick` MUST both be captured by
    the caller BEFORE this tick's `next_update()` runs (the entry state and
    draw-count baseline) -- this function itself is called AFTER
    `next_update()`, so it can only compare against a caller-captured
    baseline, never re-read `process._rng.get_state()` as if it were still
    the entry state.

    Fails loudly with the full ledger (tick, Karr's real draw count, OC's
    actual draw count, both entry/exit states) at the FIRST tick where
    these diverge -- this IS the first-divergence ledger the task
    requires, not a downstream symptom of it (an observable mismatch could
    lag the true RNG-consumption divergence by one or more ticks; this
    check is exact and immediate).
    """
    if not _has_randstream_capture(trace):
        return

    karr_entry = _karr_randstream_state(trace, "states_before", tick)
    karr_exit = _karr_randstream_state(trace, "states_after", tick)

    if oc_state_before_tick != karr_entry:
        pytest.fail(
            "L2a randStream-ledger mismatch (entry state): "
            f"tick={tick}, oc_entry_state={oc_state_before_tick}, karr_entry_state={karr_entry}"
        )

    oc_draws = process._rng.draw_count - draw_count_before_tick  # noqa: SLF001
    try:
        karr_draws = _rand_steps_between(karr_entry, karr_exit)
    except ValueError as exc:
        pytest.fail(f"L2a randStream-ledger: could not derive Karr's real draw count at tick={tick}: {exc}")
        return

    if oc_draws != karr_draws:
        pytest.fail(
            "L2a randStream-ledger mismatch (draw count): "
            f"tick={tick}, oc_draws={oc_draws}, karr_draws={karr_draws}, "
            f"karr_entry_state={karr_entry}, karr_exit_state={karr_exit}, "
            f"oc_exit_state={process._rng.get_state()}"  # noqa: SLF001
        )

    oc_exit = process._rng.get_state()  # noqa: SLF001
    if oc_exit != karr_exit:
        pytest.fail(
            "L2a randStream-ledger mismatch (exit state, despite matching draw "
            f"count): tick={tick}, oc_exit_state={oc_exit}, karr_exit_state={karr_exit} "
            "-- the two streams drew the same NUMBER of values but landed on "
            "different states, which is impossible for the same deterministic "
            "recurrence from the same entry state unless oc_entry_state was "
            "already wrong (checked above) or a non-Cytokinesis draw source "
            "silently shares this process's stream"
        )


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

    # Task step 3: restore the exact per-tick process stream state in the
    # isolated OC replay -- never assume a fresh construction-time seed
    # coincidentally equals Karr's real state at the window's start tick
    # (true here only because Cytokinesis draws zero times while
    # quiescent, per Cytokinesis.m's `if ~this.chromosome.segregated;
    # return; end` early return -- but this restoration makes the replay
    # correct unconditionally, not by relying on that coincidence).
    if _has_randstream_capture(trace):
        process._rng.set_state(_karr_randstream_state(trace, "states_before", 0))  # noqa: SLF001

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

        draw_count_before_tick = process._rng.draw_count  # noqa: SLF001
        oc_state_before_tick = process._rng.get_state()  # noqa: SLF001
        update = process.next_update(1.0, state)
        _assert_randstream_ledger(trace, tick, process, draw_count_before_tick, oc_state_before_tick)
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


def _resolve_event_trace_path(seed: int, n_ticks: int = 4000) -> Path:
    """Resolve the event-window trace path for Cytokinesis (anchor window on
    ftsZRing pinch-diameter decrease)."""
    rel = Path(
        f"data/m1_sources/karr_native/per_process_traces_v2_event_s{seed:03d}/Cytokinesis_{n_ticks}ticks.mat"
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
    trace_path = _resolve_event_trace_path(rng_seed, n_ticks=4000)
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


@pytest.mark.parametrize("rng_seed", [36], ids=["event_seed_36_m5000"])
def test_karr_cytokinesis_l2_event_replay_m5000_randstream_bound(rng_seed: int) -> None:
    """Task target: the source-bound, randStream-state-capturing M_ticks=5000
    seed-36 active-window trace (real onset=27918/completion=31993 per
    STATUS_L21_CYTOKINESIS_ACTIVE_FIX.md / dec-005). Skips cleanly until the
    background extraction (commit `153d726`'s extended extractor) completes
    and lands at the expected path -- this test activates automatically the
    moment it does, with NO further code changes needed, and is the
    promotion gate for GENUINE (bit-identity across the full active window,
    fail-closed, dnadamage-source-hash-bound)."""
    trace_path = _resolve_event_trace_path(rng_seed, n_ticks=5000)
    if not trace_path.exists():
        pytest.skip(f"M_ticks=5000 event-window trace not found (background extraction pending): {trace_path}")

    with h5py.File(trace_path, "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert n_ticks == 5000

        if "onset_tick" in trace["metadata"]:
            onset_tick = int(np.asarray(trace["metadata/onset_tick"][()]).reshape(-1)[0])
            assert onset_tick == 27918, (
                f"expected the task's specified onset_tick=27918 for seed 36, got {onset_tick}"
            )
        if "window_anchor" in trace["metadata"]:
            window_anchor = int(np.asarray(trace["metadata/window_anchor"][()]).reshape(-1)[0])
            assert window_anchor == 31993, (
                f"expected the task's specified window_anchor=31993 for seed 36, got {window_anchor}"
            )

        assert _has_randstream_capture(trace), (
            f"{trace_path} lacks metadata/states_before.randStreamState -- it predates the "
            "randStream-capturing extractor (commit 153d726) and cannot serve as the M5000 "
            "promotion-gate trace; re-extract with the current extract_per_process_traces_v2.m."
        )

        mutated_obs = tuple(o for o in _OBSERVABLES if o not in _PASS_THROUGH)
        mutated_tick_counts = _audit_trace_mutated_ticks(trace, mutated_obs, n_ticks)
        if sum(mutated_tick_counts.values()) == 0:
            pytest.skip(
                f"Event-window trace seed {rng_seed} has no events. "
                f"Per-observable counts: {mutated_tick_counts}."
            )

        _run_replay(trace, n_ticks, int(rng_seed))


# ---------------------------------------------------------------------------
# Isolated unit tests for the randStream-ledger mechanism itself (task step
# 3), using a small synthetic HDF5 fixture -- exercises `_assert_randstream_
# ledger`'s pass/fail logic directly without requiring a full valid Cytokinesis
# replay or the real (currently-extracting) M5000 seed-36 trace.
# ---------------------------------------------------------------------------

def _lehmer_step(state: int) -> int:
    """Advance one ENCODED (MATLAB-exposed-representation) mcg16807 state
    by exactly one real draw -- i.e. what a genuine ``randStream.state``
    capture would read after one draw. Delegates to the same live-MATLAB-
    verified codec `_MatlabCytokinesisRNG` itself now uses (see
    `opencell/util/mcg16807_state_codec.py`), rather than a plain
    ``16807*state mod (2**31-1)`` step directly on the encoded value --
    that direct-step shortcut IS the M5000 seed-36 tick=894 bug this
    ledger exists to catch, so these synthetic fixtures must not
    reintroduce it."""
    _, next_state = _draw_and_advance(state)
    return next_state


class _StubRNG:
    """Minimal stand-in for `_MatlabCytokinesisRNG` exposing only the two
    members `_assert_randstream_ledger` reads: `.get_state()` and
    `.draw_count`."""

    def __init__(self, state: int, draw_count: int = 0) -> None:
        self._state = int(state)
        self.draw_count = int(draw_count)

    def get_state(self) -> int:
        return self._state

    def advance(self, n: int) -> None:
        for _ in range(n):
            self._state = _lehmer_step(self._state)
        self.draw_count += n


class _StubProcess:
    def __init__(self, rng: _StubRNG) -> None:
        self._rng = rng


def _write_randstream_ledger_fixture(path: Path, *, entry_states: list[int], exit_states: list[int]) -> None:
    """Write a minimal synthetic trace with ONLY states_before/after.randStreamState
    populated (the one field `_has_randstream_capture`/`_karr_randstream_state`
    read) -- deliberately does not populate substrates/enzymes/ring witnesses
    since these unit tests call `_assert_randstream_ledger` directly, never
    `_run_replay`."""
    n_ticks = len(entry_states)
    assert len(exit_states) == n_ticks
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        before_ds = states_before.create_dataset(
            "randStreamState", shape=(1, n_ticks), dtype=h5py.special_dtype(ref=h5py.Reference)
        )
        after_ds = states_after.create_dataset(
            "randStreamState", shape=(1, n_ticks), dtype=h5py.special_dtype(ref=h5py.Reference)
        )
        for t in range(n_ticks):
            before_val = handle.create_dataset(f"_before_val_{t}", data=np.array([[float(entry_states[t])]]))
            after_val = handle.create_dataset(f"_after_val_{t}", data=np.array([[float(exit_states[t])]]))
            before_ds[0, t] = before_val.ref
            after_ds[0, t] = after_val.ref


def test_has_randstream_capture_false_for_legacy_trace(tmp_path: Path) -> None:
    path = tmp_path / "legacy.mat"
    with h5py.File(path, "w") as handle:
        handle.create_group("states_before")
    with h5py.File(path, "r") as trace:
        assert _has_randstream_capture(trace) is False


def test_randstream_ledger_passes_when_oc_matches_karr_exactly(tmp_path: Path) -> None:
    path = tmp_path / "ledger_ok.mat"
    seed0 = 12345
    # tick 0: 3 real Karr draws; tick 1: 0 draws (quiescent).
    s1 = seed0
    for _ in range(3):
        s1 = _lehmer_step(s1)
    s2 = s1  # zero draws at tick 1
    _write_randstream_ledger_fixture(path, entry_states=[seed0, s1], exit_states=[s1, s2])

    with h5py.File(path, "r") as trace:
        assert _has_randstream_capture(trace) is True
        rng = _StubRNG(seed0)
        process = _StubProcess(rng)

        draw_count_before = rng.draw_count
        oc_before = rng.get_state()
        rng.advance(3)  # OC also draws exactly 3 times at tick 0
        _assert_randstream_ledger(trace, 0, process, draw_count_before, oc_before)  # must not raise/fail

        draw_count_before = rng.draw_count
        oc_before = rng.get_state()
        rng.advance(0)
        _assert_randstream_ledger(trace, 1, process, draw_count_before, oc_before)  # must not raise/fail


def test_randstream_ledger_fails_on_entry_state_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "ledger_entry_mismatch.mat"
    seed0 = 999
    s1 = _lehmer_step(seed0)
    _write_randstream_ledger_fixture(path, entry_states=[seed0], exit_states=[s1])

    with h5py.File(path, "r") as trace:
        wrong_start = seed0 + 1  # OC's RNG was never restored to Karr's real entry state
        rng = _StubRNG(wrong_start)
        process = _StubProcess(rng)
        draw_count_before = rng.draw_count
        oc_before = rng.get_state()
        rng.advance(1)
        with pytest.raises(pytest.fail.Exception, match="entry state"):
            _assert_randstream_ledger(trace, 0, process, draw_count_before, oc_before)


def test_randstream_ledger_fails_on_draw_count_mismatch(tmp_path: Path) -> None:
    """The exact tick-228 bug class this ledger is built to catch: OC's
    stream entered the tick at the correct state but consumed a DIFFERENT
    number of draws than Karr's real recorded exit state implies."""
    path = tmp_path / "ledger_draw_mismatch.mat"
    seed0 = 42
    s1 = seed0
    for _ in range(3):  # Karr's real draw count this tick: 3
        s1 = _lehmer_step(s1)
    _write_randstream_ledger_fixture(path, entry_states=[seed0], exit_states=[s1])

    with h5py.File(path, "r") as trace:
        rng = _StubRNG(seed0)
        process = _StubProcess(rng)
        draw_count_before = rng.draw_count
        oc_before = rng.get_state()
        rng.advance(2)  # OC only drew 2 times -- draw-count divergence
        with pytest.raises(pytest.fail.Exception, match="draw count"):
            _assert_randstream_ledger(trace, 0, process, draw_count_before, oc_before)


def test_randstream_ledger_noop_for_trace_without_capture(tmp_path: Path) -> None:
    path = tmp_path / "no_capture.mat"
    with h5py.File(path, "w") as handle:
        handle.create_group("states_before")
        handle.create_group("states_after")
    with h5py.File(path, "r") as trace:
        rng = _StubRNG(1)
        process = _StubProcess(rng)
        # Deliberately wrong relative to nothing (no captured ground truth
        # exists) -- must not raise, since _has_randstream_capture is False.
        _assert_randstream_ledger(trace, 0, process, rng.draw_count, rng.get_state())
