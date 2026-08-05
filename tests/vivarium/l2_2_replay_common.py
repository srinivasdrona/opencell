from __future__ import annotations

import sys
from contextlib import ExitStack
from dataclasses import dataclass
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
    apply_count_update,
    assert_delta_integral,
    audit_trace_mutated_ticks,
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
    assert_identity_or_tolerance as _assert_identity_or_tolerance_shared,
)

from opencell.vivarium.karr_rna_processing import KarrRNAProcessingProcess
from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process

_COMPOSITION_ORDER = ("Translation", "RNAProcessing")
# Oracle-injection policy for observables that are not uniquely "owned":
# pick the first under-test process in composition order that exposes the
# observable in its trace manifest.
_ORACLE_INJECTION_POLICY = "first-process-with-observable"


@dataclass(frozen=True)
class _ProcessSpec:
    process_cls: type
    observables: tuple[str, ...]
    pass_through: frozenset[str]
    observable_to_wids_attr: dict[str, str]
    index_projection_literal: dict[str, Any] | None = None
    trace_after_hint_observables: tuple[str, ...] = ()


@dataclass
class _ProcessContext:
    name: str
    spec: _ProcessSpec
    process: Any
    trace: h5py.File
    n_ticks: int
    wids_by_observable: dict[str, list[str]]


_PROCESS_SPECS: dict[str, _ProcessSpec] = {
    "Translation": _ProcessSpec(
        process_cls=KarrTranslationV3Process,
        observables=("substrates", "enzymes", "boundEnzymes", "monomers"),
        pass_through=frozenset(),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "monomers": "protein_ids",
        },
        index_projection_literal={"substrates": np.arange(20)},
        trace_after_hint_observables=("enzymes", "boundEnzymes"),
    ),
    "RNAProcessing": _ProcessSpec(
        process_cls=KarrRNAProcessingProcess,
        observables=("substrates", "enzymes", "boundEnzymes", "processedRNAs", "unprocessedRNAs"),
        pass_through=frozenset({"boundEnzymes", "enzymes"}),
        observable_to_wids_attr={
            "substrates": "substrate_wids",
            "enzymes": "enzyme_wids",
            "boundEnzymes": "enzyme_wids",
            "processedRNAs": "processed_rna_wids",
            "unprocessedRNAs": "unprocessed_rna_wids",
        },
    ),
}


def _ordered_under_test(under_test_processes: list[str]) -> list[str]:
    unknown = [name for name in under_test_processes if name not in _PROCESS_SPECS]
    if unknown:
        pytest.fail(f"L2.2 unsupported process name(s): {unknown}")
    under_test_set = set(under_test_processes)
    ordered = [name for name in _COMPOSITION_ORDER if name in under_test_set]
    if len(ordered) != len(under_test_set):
        missing = sorted(under_test_set.difference(ordered))
        pytest.fail(f"L2.2 composition-order map missing process(es): {missing}")
    return ordered


def _project_trace_vector(ctx: _ProcessContext, group: str, observable: str, tick: int) -> np.ndarray:
    return project_karr_vector(
        ctx.process,
        observable,
        cell_vector(ctx.trace, group, observable, tick),
        index_projection_literal=ctx.spec.index_projection_literal,
    )


def _owned_observables(spec: _ProcessSpec) -> tuple[str, ...]:
    return tuple(obs for obs in spec.observables if obs not in spec.pass_through)


def _matches_oracle(
    *,
    tick: int,
    process_name: str,
    observable: str,
    oc_after: np.ndarray,
    karr_after: np.ndarray,
) -> bool:
    try:
        _assert_identity_or_tolerance_shared(
            tick=tick,
            observable=observable,
            oc_after=oc_after,
            karr_after=karr_after,
            process_name=process_name,
        )
    except BaseException:
        return False
    return True


def _first_mismatch_detail(oc_after: np.ndarray, karr_after: np.ndarray) -> tuple[int, float, float, float]:
    if oc_after.shape != karr_after.shape:
        return (-1, float("nan"), float("nan"), float("nan"))
    mismatch = oc_after != karr_after
    if not np.any(mismatch):
        return (-1, 0.0, 0.0, 0.0)
    idx = int(np.flatnonzero(mismatch)[0])
    oc_val = float(oc_after[idx])
    karr_val = float(karr_after[idx])
    return (idx, oc_val, karr_val, float(oc_val - karr_val))


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    for label, deltas in collect_count_delta_dicts(update):
        assert_delta_integral(label, deltas)
    apply_count_update(state, update)


def _build_counterfactual_step_vector(
    *,
    ctx: _ProcessContext,
    tick: int,
    observable: str,
) -> np.ndarray:
    state = build_state_template(ctx.process)
    before_vectors: dict[str, np.ndarray] = {}
    for obs in ctx.spec.observables:
        before_vectors[obs] = _project_trace_vector(ctx, "states_before", obs, tick)
        overlay_observable_into_state(
            process=ctx.process,
            state=state,
            observable=obs,
            vector=before_vectors[obs],
            wids=ctx.wids_by_observable[obs],
        )
    for obs in ctx.spec.trace_after_hint_observables:
        after_vec = _project_trace_vector(ctx, "states_after", obs, tick)
        overlay_trace_after_hint(
            state=state,
            observable=obs,
            vector=after_vec,
            wids=ctx.wids_by_observable[obs],
        )
    refresh_allocator_views(ctx.process, state)
    update = ctx.process.next_update(1.0, state)
    _apply_update(state, update)
    return project_observable_from_state(
        process=ctx.process,
        state=state,
        observable=observable,
        wids=ctx.wids_by_observable[observable],
        bound_enzymes_before=before_vectors.get("boundEnzymes"),
    )


def _build_context(name: str, rng_seed: int, handle: h5py.File) -> _ProcessContext:
    spec = _PROCESS_SPECS[name]
    n_ticks = int(np.asarray(handle["metadata/n_ticks"][()]).reshape(-1)[0])
    if "metadata" in handle and "rng_seed" in handle["metadata"]:
        recorded_seed = int(np.asarray(handle["metadata/rng_seed"][()]).reshape(-1)[0])
        assert int(rng_seed) == recorded_seed

    process = spec.process_cls({"rng_seed": int(rng_seed)})
    state_template = build_state_template(process)
    probe_ctx = _ProcessContext(
        name=name,
        spec=spec,
        process=process,
        trace=handle,
        n_ticks=n_ticks,
        wids_by_observable={},
    )

    wids_by_observable: dict[str, list[str]] = {}
    for observable in spec.observables:
        karr_before = _project_trace_vector(probe_ctx, "states_before", observable, 0)
        wids_by_observable[observable] = infer_wids_for_observable(
            process,
            state_template,
            observable,
            karr_len=int(karr_before.shape[0]),
            explicit_attr=spec.observable_to_wids_attr.get(observable),
        )

    return _ProcessContext(
        name=name,
        spec=spec,
        process=process,
        trace=handle,
        n_ticks=n_ticks,
        wids_by_observable=wids_by_observable,
    )


def run_integrated_replay(*, under_test_processes: list[str], rng_seed: int) -> None:
    ordered = _ordered_under_test(under_test_processes)

    with ExitStack() as stack:
        contexts: dict[str, _ProcessContext] = {}
        for name in ordered:
            trace_handle = stack.enter_context(h5py.File(resolve_trace_path(name), "r"))
            contexts[name] = _build_context(name, rng_seed, trace_handle)

        n_ticks_values = {contexts[name].n_ticks for name in ordered}
        if len(n_ticks_values) != 1:
            pytest.fail(f"L2.2 n_ticks mismatch across traces: {sorted(n_ticks_values)}")
        n_ticks = next(iter(n_ticks_values))

        no_op_messages: list[str] = []
        for name in ordered:
            ctx = contexts[name]
            mutated = _owned_observables(ctx.spec)
            mutated_tick_counts = audit_trace_mutated_ticks(ctx.trace, mutated, n_ticks)
            if sum(mutated_tick_counts.values()) == 0:
                no_op_messages.append(
                    f"{name}: all owned observables are no-op across {n_ticks} ticks: {mutated_tick_counts}"
                )
        if no_op_messages:
            pytest.skip("L2.2 N/A: no-op trace for at least one under-test process. " + " | ".join(no_op_messages))

        all_observables: list[str] = []
        for name in ordered:
            for obs in contexts[name].spec.observables:
                if obs not in all_observables:
                    all_observables.append(obs)

        source_by_observable: dict[str, str] = {}
        for obs in all_observables:
            for name in ordered:
                if obs in contexts[name].spec.observables:
                    source_by_observable[obs] = name
                    break

        for tick in range(n_ticks):
            shared_state = build_state_template(contexts[ordered[0]].process)
            before_vectors: dict[str, dict[str, np.ndarray]] = {}
            after_vectors: dict[str, dict[str, np.ndarray]] = {}
            step_vectors: dict[tuple[str, str], np.ndarray] = {}

            for name in ordered:
                ctx = contexts[name]
                before_vectors[name] = {
                    obs: _project_trace_vector(ctx, "states_before", obs, tick)
                    for obs in ctx.spec.observables
                }
                after_vectors[name] = {
                    obs: _project_trace_vector(ctx, "states_after", obs, tick)
                    for obs in ctx.spec.observables
                }

            for obs, source_name in source_by_observable.items():
                src = contexts[source_name]
                overlay_observable_into_state(
                    process=src.process,
                    state=shared_state,
                    observable=obs,
                    vector=before_vectors[source_name][obs],
                    wids=src.wids_by_observable[obs],
                )

            for name in ordered:
                ctx = contexts[name]
                for obs in ctx.spec.trace_after_hint_observables:
                    overlay_trace_after_hint(
                        state=shared_state,
                        observable=obs,
                        vector=after_vectors[name][obs],
                        wids=ctx.wids_by_observable[obs],
                    )

                refresh_allocator_views(ctx.process, shared_state)
                update = ctx.process.next_update(1.0, shared_state)
                _apply_update(shared_state, update)
                upstream = [p for p in ordered if ordered.index(p) < ordered.index(name)]

                for obs in _owned_observables(ctx.spec):
                    oc_after_step = project_observable_from_state(
                        process=ctx.process,
                        state=shared_state,
                        observable=obs,
                        wids=ctx.wids_by_observable[obs],
                        bound_enzymes_before=before_vectors[name].get("boundEnzymes"),
                    )
                    step_vectors[(name, obs)] = oc_after_step
                    karr_after = after_vectors[name][obs]
                    if not _matches_oracle(
                        tick=tick,
                        process_name=name,
                        observable=obs,
                        oc_after=oc_after_step,
                        karr_after=karr_after,
                    ):
                        idx, oc_val, karr_val, diff = _first_mismatch_detail(
                            oc_after_step, karr_after
                        )
                        oc_counterfactual = _build_counterfactual_step_vector(
                            ctx=ctx,
                            tick=tick,
                            observable=obs,
                        )
                        cause = (
                            "upstream pollution from earlier composed updates"
                            if _matches_oracle(
                                tick=tick,
                                process_name=name,
                                observable=obs,
                                oc_after=oc_counterfactual,
                                karr_after=karr_after,
                            )
                            else "intrinsic divergence in process replay (persists in isolated counterfactual)"
                        )
                        pytest.fail(
                            "L2.2 step mismatch: "
                            f"tick={tick}, process={name}, observable={obs}, cause={cause}, "
                            f"upstream_processes={upstream}, index={idx}, "
                            f"oc_val={oc_val}, karr_val={karr_val}, diff={diff}, "
                            f"composition_order={ordered}, oracle_injection_policy={_ORACLE_INJECTION_POLICY}"
                        )

            for name in ordered:
                ctx = contexts[name]
                for obs in _owned_observables(ctx.spec):
                    oc_after_final = project_observable_from_state(
                        process=ctx.process,
                        state=shared_state,
                        observable=obs,
                        wids=ctx.wids_by_observable[obs],
                        bound_enzymes_before=before_vectors[name].get("boundEnzymes"),
                    )
                    karr_after = after_vectors[name][obs]
                    if not _matches_oracle(
                        tick=tick,
                        process_name=name,
                        observable=obs,
                        oc_after=oc_after_final,
                        karr_after=karr_after,
                    ):
                        idx, oc_val, karr_val, diff = _first_mismatch_detail(
                            oc_after_final, karr_after
                        )
                        step_aligned = _matches_oracle(
                            tick=tick,
                            process_name=name,
                            observable=obs,
                            oc_after=step_vectors[(name, obs)],
                            karr_after=karr_after,
                        )
                        cause = (
                            "downstream pollution (process matched oracle immediately after its own step)"
                            if step_aligned
                            else "process already diverged at its own step"
                        )
                        pytest.fail(
                            "L2.2 final mismatch: "
                            f"tick={tick}, process={name}, observable={obs}, cause={cause}, "
                            f"index={idx}, oc_val={oc_val}, karr_val={karr_val}, diff={diff}, "
                            f"composition_order={ordered}, oracle_injection_policy={_ORACLE_INJECTION_POLICY}"
                        )


__all__ = ["_COMPOSITION_ORDER", "run_integrated_replay"]
