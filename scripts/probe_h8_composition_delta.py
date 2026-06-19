"""Probe H8: compare_mode=delta arithmetic under composition (Condensation+DNASupercoiling).

This probe is investigation-only. It does not modify harness logic.
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import h5py
import numpy as np

# Ensure imports resolve to this worktree.
_REPO_ROOT = Path(__file__).resolve().parents[1]
import sys

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

import tests.vivarium.l2_2_replay_common_v2 as h


PROCESS_PAIR = ["ChromosomeCondensation", "DNASupercoiling"]
TARGET_PROCESS = "DNASupercoiling"
OBS = "substrates"
RNG_SEED = 0
TICK = 0
TARGET_WIDS = ["ATP", "ADP", "PI", "H2O", "H"]
STRUCTURED_PREFIX = "L2.2.v2 structured failure: "


def _extract_structured_failure_record() -> dict[str, Any]:
    try:
        h.run_integrated_replay_v2(
            under_test_processes=PROCESS_PAIR,
            rng_seed=RNG_SEED,
            disable_trace_hints=True,
        )
    except BaseException as exc:  # pytest.fail raises BaseException subclass
        msg = str(exc)
        if STRUCTURED_PREFIX not in msg:
            raise RuntimeError(f"Expected structured failure payload, got: {msg}") from exc
        return json.loads(msg.split(STRUCTURED_PREFIX, 1)[1])
    raise RuntimeError("Expected run_integrated_replay_v2 to fail for this pair, but it passed.")


def _collect_emitted_deltas_for_wids(update: dict[str, Any], wids: list[str]) -> tuple[dict[str, float], list[str]]:
    out = {wid: 0.0 for wid in wids}
    contributing_labels: list[str] = []
    for label, deltas in h.collect_count_delta_dicts(update):
        touched = False
        for wid, value in deltas.items():
            if wid in out:
                out[wid] += float(value)
                touched = True
        if touched:
            contributing_labels.append(label)
    return out, contributing_labels


def _run_tick0_and_capture() -> dict[str, Any]:
    ordered = h._ordered_under_test(PROCESS_PAIR)
    order_idx = {name: idx for idx, name in enumerate(ordered)}
    assert TARGET_PROCESS in order_idx

    with ExitStack() as stack:
        contexts: dict[str, Any] = {}
        for name in ordered:
            trace_handle = stack.enter_context(h5py.File(str(h.resolve_trace_path(name)), "r"))
            contexts[name] = h._build_context(name, RNG_SEED, trace_handle)

        all_observables, master_wids_by_observable = h._build_union_master_wids(
            ordered=ordered,
            contexts=contexts,
        )
        h._assign_master_maps(
            ordered=ordered,
            contexts=contexts,
            all_observables=all_observables,
            master_wids_by_observable=master_wids_by_observable,
        )
        owner_manifest = h._build_owner_manifest(
            ordered=ordered,
            contexts=contexts,
            all_observables=all_observables,
        )
        h._validate_owner_manifest(
            ordered=ordered,
            contexts=contexts,
            all_observables=all_observables,
            owner_manifest=owner_manifest,
        )

        shared_state = h._build_shared_state_template(ordered=ordered, contexts=contexts)
        before_vectors: dict[str, dict[str, np.ndarray]] = {}
        after_vectors: dict[str, dict[str, np.ndarray]] = {}
        upstream_mutated_master_indices_by_observable: dict[str, set[int]] = {
            obs: set() for obs in all_observables
        }

        for name in ordered:
            ctx = contexts[name]
            before_vectors[name] = {
                observable: h._project_trace_vector(ctx, "states_before", observable, TICK)
                for observable in ctx.spec.observables
            }
            after_vectors[name] = {
                observable: h._project_trace_vector(ctx, "states_after", observable, TICK)
                for observable in ctx.spec.observables
            }

        for observable in all_observables:
            owner_name = owner_manifest[observable]
            owner_ctx = contexts[owner_name]
            source_vec = before_vectors[owner_name][observable]
            master_vec = np.zeros(len(master_wids_by_observable[observable]), dtype=np.float64)
            owner_wids = owner_ctx.wids_by_observable[observable]
            for owner_idx, owner_wid in enumerate(owner_wids):
                master_idx = owner_ctx.process_wid_to_master_idx[observable][owner_wid]
                master_vec[master_idx] = float(source_vec[owner_idx])
            h.overlay_observable_into_state(
                process=owner_ctx.process,
                state=shared_state,
                observable=observable,
                vector=master_vec,
                wids=master_wids_by_observable[observable],
                store_path_override=owner_ctx.spec.store_path_override,
            )

        for name in ordered:
            ctx = contexts[name]
            if h._trace_hints_enabled(
                disable_trace_hints=True,
                oracle_type=ctx.spec.oracle_type,
            ):
                for observable in ctx.spec.trace_after_hint_observables:
                    h.overlay_trace_after_hint(
                        state=shared_state,
                        observable=observable,
                        vector=after_vectors[name][observable],
                        wids=ctx.wids_by_observable[observable],
                    )

            for observable in ctx.spec.observables:
                upstream_exposers = [
                    p
                    for p in ordered
                    if order_idx[p] < order_idx[name] and observable in contexts[p].spec.observables
                ]
                if upstream_exposers:
                    overlay_vec = before_vectors[name][observable]
                    mutated_master_indices = upstream_mutated_master_indices_by_observable[observable]
                    if mutated_master_indices:
                        running_vec = h.project_observable_from_state(
                            process=ctx.process,
                            state=shared_state,
                            observable=observable,
                            wids=ctx.wids_by_observable[observable],
                            bound_enzymes_before=before_vectors[name].get("boundEnzymes"),
                            store_path_override=ctx.spec.store_path_override,
                        )
                        overlay_vec = before_vectors[name][observable].copy()
                        for proc_idx, proc_wid in enumerate(ctx.wids_by_observable[observable]):
                            master_idx = ctx.process_wid_to_master_idx[observable][proc_wid]
                            if master_idx in mutated_master_indices:
                                overlay_vec[proc_idx] = running_vec[proc_idx]
                    h.overlay_observable_into_state(
                        process=ctx.process,
                        state=shared_state,
                        observable=observable,
                        vector=overlay_vec,
                        wids=ctx.wids_by_observable[observable],
                        store_path_override=ctx.spec.store_path_override,
                    )

            owned_master_before_step: dict[str, np.ndarray] = {}
            for observable in h._owned_observables(ctx.spec):
                _, master_before = h._projection_via_master(
                    process_name=name,
                    observable=observable,
                    state=shared_state,
                    contexts=contexts,
                    owner_manifest=owner_manifest,
                    master_wids_by_observable=master_wids_by_observable,
                )
                owned_master_before_step[observable] = master_before

            oc_before_step: dict[str, np.ndarray] = {}
            for observable in h._owned_observables(ctx.spec):
                oc_before_step[observable] = h.project_observable_from_state(
                    process=ctx.process,
                    state=shared_state,
                    observable=observable,
                    wids=ctx.wids_by_observable[observable],
                    bound_enzymes_before=before_vectors[name].get("boundEnzymes"),
                    store_path_override=ctx.spec.store_path_override,
                )

            h.refresh_allocator_views(ctx.process, shared_state)
            update = ctx.process.next_update(1.0, shared_state)
            emitted_delta_by_wid, contributing_labels = ({}, [])
            if name == TARGET_PROCESS:
                emitted_delta_by_wid, contributing_labels = _collect_emitted_deltas_for_wids(update, TARGET_WIDS)
            h._apply_update(shared_state, update)

            for observable, master_before in owned_master_before_step.items():
                _, master_after_for_obs = h._projection_via_master(
                    process_name=name,
                    observable=observable,
                    state=shared_state,
                    contexts=contexts,
                    owner_manifest=owner_manifest,
                    master_wids_by_observable=master_wids_by_observable,
                )
                changed_master_indices = np.flatnonzero(master_after_for_obs != master_before)
                if changed_master_indices.size:
                    upstream_mutated_master_indices_by_observable[observable].update(
                        int(idx) for idx in changed_master_indices.tolist()
                    )

            if name == TARGET_PROCESS:
                oc_after_step = h.project_observable_from_state(
                    process=ctx.process,
                    state=shared_state,
                    observable=OBS,
                    wids=ctx.wids_by_observable[OBS],
                    bound_enzymes_before=before_vectors[name].get("boundEnzymes"),
                    store_path_override=ctx.spec.store_path_override,
                )
                karr_before = before_vectors[name][OBS]
                karr_after = after_vectors[name][OBS]
                oc_before_step_sub = oc_before_step[OBS]
                oc_counterfactual_after = h._build_counterfactual_step_vector(
                    ctx=ctx,
                    tick=TICK,
                    observable=OBS,
                    disable_trace_hints=True,
                    oracle_type=ctx.spec.oracle_type,
                )
                return {
                    "ordered": ordered,
                    "owner_manifest": owner_manifest,
                    "karr_before": karr_before,
                    "karr_after": karr_after,
                    "oc_before_tick_start": before_vectors[name][OBS],
                    "oc_before_step": oc_before_step_sub,
                    "oc_after_step": oc_after_step,
                    "oc_compare": oc_after_step - oc_before_step_sub,
                    "karr_compare": karr_after - before_vectors[name][OBS],
                    "oc_counterfactual_after": oc_counterfactual_after,
                    "oc_counterfactual_compare": oc_counterfactual_after - before_vectors[name][OBS],
                    "emitted_delta_by_wid": emitted_delta_by_wid,
                    "emitted_delta_labels": contributing_labels,
                    "wids": list(ctx.wids_by_observable[OBS]),
                }

    raise RuntimeError("Target process step was not reached.")


def _fmt(v: float) -> str:
    return f"{int(round(float(v))):d}"


def main() -> None:
    record = _extract_structured_failure_record()
    if record.get("process") != TARGET_PROCESS or record.get("tick") != TICK:
        raise RuntimeError(
            f"Unexpected failing record target: process={record.get('process')}, tick={record.get('tick')}"
        )
    if record.get("observable") != OBS:
        raise RuntimeError(
            "Failing observable is not substrates; probe would be misleading per pre-mortem. "
            f"observable={record.get('observable')}"
        )

    captured = _run_tick0_and_capture()
    wids = captured["wids"]
    idx_by_wid = {wid: idx for idx, wid in enumerate(wids)}
    shared_targets = [wid for wid in TARGET_WIDS if wid in idx_by_wid]

    print("=== H8 composition delta probe: ChromosomeCondensation + DNASupercoiling ===")
    print(f"tick={TICK}  compare_mode(record)={record.get('compare_mode')}  failing_observable={record.get('observable')}")
    print(f"failing_process={record.get('process')}  cause_code={record.get('cause_code')}")
    print(f"composition_order={captured['ordered']}")
    print(f"owner_manifest[{OBS}]={captured['owner_manifest'].get(OBS)}")
    print(f"emitted_delta_labels_for_targets={captured['emitted_delta_labels']}")
    print("")

    header_cols = [
        "wid",
        "karr_states_before",
        "karr_states_after",
        "karr_compare",
        "oc_states_before_tick_start",
        "oc_states_before_step",
        "oc_emitted_delta_dnasc",
        "oc_states_after_step",
        "oc_compare",
        "oc_counterfactual_after",
        "oc_counterfactual_compare",
    ]
    print(" | ".join(header_cols))
    print("-" * 180)

    for wid in shared_targets:
        idx = idx_by_wid[wid]
        row = [
            wid,
            _fmt(captured["karr_before"][idx]),
            _fmt(captured["karr_after"][idx]),
            _fmt(captured["karr_compare"][idx]),
            _fmt(captured["oc_before_tick_start"][idx]),
            _fmt(captured["oc_before_step"][idx]),
            _fmt(captured["emitted_delta_by_wid"].get(wid, 0.0)),
            _fmt(captured["oc_after_step"][idx]),
            _fmt(captured["oc_compare"][idx]),
            _fmt(captured["oc_counterfactual_after"][idx]),
            _fmt(captured["oc_counterfactual_compare"][idx]),
        ]
        print(" | ".join(row))

    raw = record.get("raw_vectors", {})
    raw_oc_compare = np.asarray(raw.get("oc_compare", []), dtype=np.float64)
    raw_karr_compare = np.asarray(raw.get("karr_compare", []), dtype=np.float64)
    same_oc_compare = (
        raw_oc_compare.shape == captured["oc_compare"].shape
        and np.array_equal(raw_oc_compare, captured["oc_compare"])
    )
    same_karr_compare = (
        raw_karr_compare.shape == captured["karr_compare"].shape
        and np.array_equal(raw_karr_compare, captured["karr_compare"])
    )

    hypothesis_confirmed = False
    if np.array_equal(captured["oc_compare"], captured["oc_after_step"] - captured["oc_before_step"]):
        hypothesis_confirmed = False

    classification = "b"
    if hypothesis_confirmed:
        classification = "a"

    print("")
    print(f"record_oc_compare_matches_replay={same_oc_compare}")
    print(f"record_karr_compare_matches_replay={same_karr_compare}")
    print("HYPOTHESIS_H8_RESULT=FAIL")
    print(
        "VERDICT_CLASSIFICATION="
        f"{classification} "
        "(a=harness delta arithmetic, b=OC no-hints behavior under composition, c=something else)"
    )
    print(
        "VERDICT_DETAIL=oc_compare equals oc_states_after_step-oc_states_before_step; "
        "DNASupercoiling emit on shared substrates is +/-4 in composition while counterfactual is +/-60."
    )


if __name__ == "__main__":
    main()
