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

from _chromcond_replay_apply import apply_chromcond_replay_update
from l2_2_replay_common_v2 import (
    _build_context as _build_hidden_context,
)
from l2_2_replay_common_v2 import (
    _inject_hidden_read_surface,
    _trace_cell_payload,
)
from l2_2_replay_common_v2 import (
    _project_trace_vector as _project_hidden_trace_vector,
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
from l2_replay_common import (
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    overlay_observable_into_state,
    overlay_trace_after_hint,
    project_observable_from_state,
    refresh_allocator_views,
    resolve_trace_path,
)

from opencell.state.chromosome_store import ChromosomeStore
from opencell.vivarium.karr_chromosome_condensation import KarrChromosomeCondensationProcess

_TRACE_PROCESS_NAME = "ChromosomeCondensation"
_OBSERVABLES = ('substrates', 'enzymes', 'boundEnzymes')

# Computed once at import time (repo-standard skip policy, e.g.
# tests/scripts/test_l2_event_adapters.py's `_RA_TRACE.exists()` pattern):
# `resolve_trace_path` raises `FileNotFoundError` rather than returning `None`
# when the local 100-tick oracle is absent (CI/fresh-clone environments have
# no sibling E:/opencell or /mnt/e/opencell checkout to fall back to). Tests
# that need the real trace skip cleanly instead of erroring.
try:
    _CHROMCOND_TRACE_PATH: Path | None = resolve_trace_path(_TRACE_PROCESS_NAME)
except FileNotFoundError:
    _CHROMCOND_TRACE_PATH = None

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
    process: KarrChromosomeCondensationProcess,
) -> None:
    del process  # state is rebuilt per tick; only delta application is needed here.
    for label, deltas in collect_count_delta_dicts(update):
        _assert_delta_integral(label, deltas)
    apply_chromcond_replay_update(state, update)


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


def _triplets(store: ChromosomeStore, field_name: str) -> np.ndarray:
    triplet = store.get_field(field_name)
    if triplet.calc_num_edges() == 0:
        return np.zeros((0, 3), dtype=np.int64)
    arr = np.column_stack(
        (
            triplet.positions.astype(np.int64, copy=False),
            triplet.strands.astype(np.int64, copy=False),
            triplet.values.astype(np.int64, copy=False),
        )
    )
    order = np.lexsort((arr[:, 2], arr[:, 1], arr[:, 0]))
    return arr[order]


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_karr_chromosome_condensation_l2_replay_identity_per_tick(rng_seed: int) -> None:
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

        process = KarrChromosomeCondensationProcess({"rng_seed": int(rng_seed)})
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
            )

        for tick in range(n_ticks):
            state = build_state_template(process)
            before_vectors = {
                observable: cell_vector(trace, "states_before", observable, tick)
                for observable in _OBSERVABLES
            }
            after_vectors = {
                observable: cell_vector(trace, "states_after", observable, tick)
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
            for observable in ("enzymes", "boundEnzymes"):
                if observable in _OBSERVABLES:
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
                )
                _assert_identity_or_tolerance(
                    tick=tick,
                    observable=observable,
                    oc_after=oc_after,
                    karr_after=karr_after,
                )


def _run_hidden_chromosome_replay_scan(
    ctx,
    *,
    reintroduce_spurious_post_bind_draw: bool,
) -> list[int]:
    """Run the full-trace hidden `complexBoundSites` replay scan and return the
    sorted list of mismatched tick indices.

    Rebuilds a fresh oracle-fed `state` every tick (never carries OC's own
    prior-tick output forward -- a mismatch at tick N must not invalidate the
    independent check at tick N+1), matching the promoted
    `tmp/chromcond_hidden_mismatch_full_scan.py` methodology this test
    formalizes. When `reintroduce_spurious_post_bind_draw` is True, this
    reinstates -- via a per-run monkeypatch, never a production-code edit --
    the exact extra `randsample(n_bound, n_bound, replace=False, ones)` draw
    removed by commit `a52a8c1` ("Fix ChromCond spurious extra RNG draw
    causing tick-7+ SMC bind desync"), proving this test actually detects that
    regression class rather than only passing vacuously.
    """
    process = ctx.process
    mismatched_ticks: list[int] = []

    if reintroduce_spurious_post_bind_draw:
        _original_bind_smc_sites_literal = process._bind_smc_sites_literal

        def _bind_smc_sites_literal_with_spurious_draw(*, bound_centroids, **kwargs):
            n_bound = len(bound_centroids)
            if n_bound > 0:
                process._rng.randsample(n_bound, n_bound, False, np.ones(n_bound, dtype=np.float64))
            return _original_bind_smc_sites_literal(bound_centroids=bound_centroids, **kwargs)

        process._bind_smc_sites_literal = _bind_smc_sites_literal_with_spurious_draw

    for tick in range(ctx.n_ticks):
        state = build_state_template(process)
        for observable in _OBSERVABLES:
            overlay_observable_into_state(
                process=process,
                state=state,
                observable=observable,
                vector=_project_hidden_trace_vector(ctx, "states_before", observable, tick),
                wids=ctx.wids_by_observable[observable],
            )
        _inject_hidden_read_surface(ctx=ctx, state=state, tick=tick)
        refresh_allocator_views(process, state)

        update = process.next_update(1.0, state)
        _apply_update(state, update, process)

        payload = _trace_cell_payload(ctx=ctx, group="states_after", name="chromosome", tick=tick)
        assert isinstance(payload, h5py.Group)
        expected_store = ChromosomeStore.from_hdf5_group(payload)
        actual_store = ChromosomeStore.from_state_mapping(
            state["chromosome"],
            shape=process.chromosome_shape,
        )
        if not np.array_equal(
            _triplets(actual_store, "complexBoundSites"),
            _triplets(expected_store, "complexBoundSites"),
        ):
            mismatched_ticks.append(tick)

    return mismatched_ticks


@pytest.mark.skipif(
    _CHROMCOND_TRACE_PATH is None,
    reason="ChromosomeCondensation 100-tick oracle trace not present locally "
    "(expected in a sibling E:/opencell or /mnt/e/opencell checkout; absent "
    "in CI/fresh-clone environments)",
)
def test_hidden_chromosome_replay_full_100tick_scan_zero_mismatches() -> None:
    """Promoted regression test for the accepted full 100-tick hidden
    `complexBoundSites` scan (STATUS_L21_CHROMCOND_SEPT2.md Sec. 4, commit
    `a52a8c1`). Proves the accepted 0/100 result on the committed L2.1 test
    surface, not just a `tmp/` diagnostic script. See
    `test_hidden_chromosome_replay_full_100tick_scan_inverts_to_38_mismatches_when_spurious_draw_reintroduced`
    below for proof this test is actually sensitive to the regression class
    it guards against.
    """
    with h5py.File(resolve_trace_path(_TRACE_PROCESS_NAME), "r") as trace:
        ctx = _build_hidden_context(name=_TRACE_PROCESS_NAME, rng_seed=0, handle=trace)
        assert ctx.n_ticks == 100
        mismatched_ticks = _run_hidden_chromosome_replay_scan(
            ctx, reintroduce_spurious_post_bind_draw=False
        )
        assert mismatched_ticks == [], (
            f"{len(mismatched_ticks)}/{ctx.n_ticks} ticks mismatched (expected 0/100): "
            f"{mismatched_ticks}"
        )


@pytest.mark.skipif(
    _CHROMCOND_TRACE_PATH is None,
    reason="ChromosomeCondensation 100-tick oracle trace not present locally "
    "(expected in a sibling E:/opencell or /mnt/e/opencell checkout; absent "
    "in CI/fresh-clone environments)",
)
def test_hidden_chromosome_replay_full_100tick_scan_inverts_to_38_mismatches_when_spurious_draw_reintroduced() -> (
    None
):
    """Inversion test: reintroducing the exact spurious extra RNG draw
    commit `a52a8c1` removed must reproduce the exact pre-fix failure
    signature (38/100 mismatched ticks, first divergence at tick 7) --
    proving the zero-mismatch result above is not a vacuous pass (e.g. from
    a harness that never actually exercises the SMC-binding RNG draw
    sequence)."""
    with h5py.File(resolve_trace_path(_TRACE_PROCESS_NAME), "r") as trace:
        ctx = _build_hidden_context(name=_TRACE_PROCESS_NAME, rng_seed=0, handle=trace)
        mismatched_ticks = _run_hidden_chromosome_replay_scan(
            ctx, reintroduce_spurious_post_bind_draw=True
        )
        assert mismatched_ticks[0] == 7, (
            f"expected first divergence at tick 7, got mismatched_ticks={mismatched_ticks}"
        )
        assert len(mismatched_ticks) == 38, (
            f"expected exactly 38/100 mismatched ticks with the spurious draw "
            f"reintroduced, got {len(mismatched_ticks)}: {mismatched_ticks}"
        )
