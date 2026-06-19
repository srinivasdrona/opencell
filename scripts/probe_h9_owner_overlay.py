"""Probe H9: owner-based substrate seeding/overlay before DNASupercoiling step.

Investigation-only probe. Does not modify harness behavior.
"""

from __future__ import annotations

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
TRACE_ROOT = _REPO_ROOT / "data/m1_sources/karr_native/per_process_traces_v2"


def _pick_values(vec: np.ndarray, wids: list[str], targets: list[str]) -> dict[str, float | None]:
    idx_by_wid = {wid: idx for idx, wid in enumerate(wids)}
    out: dict[str, float | None] = {}
    for wid in targets:
        idx = idx_by_wid.get(wid)
        out[wid] = None if idx is None else float(vec[idx])
    return out


def _fmt_scalar(value: float | None) -> str:
    if value is None:
        return "NA"
    return str(int(round(float(value))))


def _run_probe() -> dict[str, Any]:
    ordered = h._ordered_under_test(PROCESS_PAIR)
    order_idx = {name: idx for idx, name in enumerate(ordered)}

    with ExitStack() as stack:
        contexts: dict[str, Any] = {}
        trace_paths: dict[str, str] = {}
        for name in ordered:
            trace_path = TRACE_ROOT / f"{name}_100ticks.mat"
            trace_paths[name] = str(trace_path)
            trace_handle = stack.enter_context(h5py.File(str(trace_path), "r"))
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

        # Owner-init pass (l2_2_replay_common_v2.py:1236-1252)
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

        capture_shared_values: dict[str, float | None] | None = None
        capture_shared_master_values: dict[str, float | None] | None = None
        capture_tick_before_target_step: dict[str, float | None] | None = None

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

            # Per-process pre-step overlay loop (l2_2_replay_common_v2.py:1268-1302)
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

            # Capture immediately after overlay loop and before TARGET_PROCESS.next_update.
            if name == TARGET_PROCESS:
                target_wids = list(ctx.wids_by_observable[OBS])
                shared_projected = h.project_observable_from_state(
                    process=ctx.process,
                    state=shared_state,
                    observable=OBS,
                    wids=target_wids,
                    bound_enzymes_before=before_vectors[name].get("boundEnzymes"),
                    store_path_override=ctx.spec.store_path_override,
                )
                capture_shared_values = _pick_values(shared_projected, target_wids, TARGET_WIDS)
                _, master_before_target = h._projection_via_master(
                    process_name=name,
                    observable=OBS,
                    state=shared_state,
                    contexts=contexts,
                    owner_manifest=owner_manifest,
                    master_wids_by_observable=master_wids_by_observable,
                )
                capture_shared_master_values = _pick_values(
                    master_before_target,
                    master_wids_by_observable[OBS],
                    TARGET_WIDS,
                )
                capture_tick_before_target_step = _pick_values(
                    before_vectors[name][OBS],
                    list(ctx.wids_by_observable[OBS]),
                    TARGET_WIDS,
                )
                break

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

            h.refresh_allocator_views(ctx.process, shared_state)
            update = ctx.process.next_update(1.0, shared_state)
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

        if capture_shared_values is None or capture_shared_master_values is None:
            raise RuntimeError("Did not reach target pre-step capture point.")

        per_process_before = {}
        per_process_after = {}
        for name in ordered:
            process_wids = list(contexts[name].wids_by_observable[OBS])
            per_process_before[name] = _pick_values(before_vectors[name][OBS], process_wids, TARGET_WIDS)
            per_process_after[name] = _pick_values(after_vectors[name][OBS], process_wids, TARGET_WIDS)

        owner = owner_manifest[OBS]
        target_before_atp = per_process_before[TARGET_PROCESS]["ATP"]
        owner_before_atp = per_process_before[owner]["ATP"]
        shared_pre_target_atp = capture_shared_values["ATP"]

        if (
            owner != TARGET_PROCESS
            and owner_before_atp is not None
            and target_before_atp is not None
            and shared_pre_target_atp is not None
            and owner_before_atp != target_before_atp
            and shared_pre_target_atp != target_before_atp
        ):
            verdict = "CONFIRMED"
        elif (
            owner_before_atp is not None
            and target_before_atp is not None
            and shared_pre_target_atp is not None
            and owner_before_atp == target_before_atp
            and shared_pre_target_atp != target_before_atp
        ):
            if owner_before_atp == 907.0 and shared_pre_target_atp == 72.0:
                verdict = "REJECTED"
            else:
                verdict = "REDIRECTED"
        else:
            verdict = "REDIRECTED"

        return {
            "ordered": ordered,
            "trace_paths": trace_paths,
            "owner_manifest_substrates": owner,
            "before_vectors_substrates": per_process_before,
            "after_vectors_substrates": per_process_after,
            "shared_state_pre_target_projected": capture_shared_values,
            "shared_state_pre_target_master": capture_shared_master_values,
            "target_tick0_before": capture_tick_before_target_step,
            "verdict": verdict,
        }


def main() -> None:
    data = _run_probe()
    print("=== H9 owner-overlay probe: ChromosomeCondensation + DNASupercoiling ===")
    print(f"ordered={data['ordered']}")
    print(f"trace_paths={data['trace_paths']}")
    print(f"owner_manifest['substrates']={data['owner_manifest_substrates']}")
    print("")
    print("per_process before_vectors['substrates'] (tick 0):")
    for name in data["ordered"]:
        vals = data["before_vectors_substrates"][name]
        atoms = [f"{wid}={_fmt_scalar(vals.get(wid))}" for wid in TARGET_WIDS]
        print(f"  {name}: " + ", ".join(atoms))
    print("")
    print("per_process after_vectors['substrates'] (tick 0):")
    for name in data["ordered"]:
        vals = data["after_vectors_substrates"][name]
        atoms = [f"{wid}={_fmt_scalar(vals.get(wid))}" for wid in TARGET_WIDS]
        print(f"  {name}: " + ", ".join(atoms))
    print("")
    projected = data["shared_state_pre_target_projected"]
    master = data["shared_state_pre_target_master"]
    print("shared_state['substrates'] immediately after pre-step overlay and before DNASupercoiling.next_update:")
    print("  projected_to_DNASupercoiling_wids: " + ", ".join(f"{wid}={_fmt_scalar(projected.get(wid))}" for wid in TARGET_WIDS))
    print("  projected_to_master_wids: " + ", ".join(f"{wid}={_fmt_scalar(master.get(wid))}" for wid in TARGET_WIDS))
    print("")
    print(f"VERDICT={data['verdict']}")


if __name__ == "__main__":
    main()
