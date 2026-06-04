"""Extended CAUSE_4 probe for L2.5 ProteinProcessingI + ProteinProcessingII.

This script reproduces the L2.5 harness state build and per-process stepping
for the first 5 ticks, then logs:

1. Tick-0 bootstrap `protein.counts` nonzero WIDs.
2. Their PPI/PPII processed-monomer positions and master indices.
3. Per tick and per watched WID:
   - PPI emitted `protein.processed_counts[wid]`
   - PPII emitted `protein.processed_counts[wid]`
   - Harness-projected `processedMonomers[wid]`
   - Oracle `processedMonomers[wid]` at same master index
4. The literal `master_wids[174]`.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_VIVARIUM = REPO_ROOT / "tests" / "vivarium"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(TESTS_VIVARIUM) not in sys.path:
    sys.path.insert(0, str(TESTS_VIVARIUM))
os.chdir(REPO_ROOT)

from l2_2_replay_common_v2 import (  # noqa: E402
    _PROCESS_SPECS,
    _apply_update,
    _assign_master_maps,
    _build_context,
    _build_owner_manifest,
    _build_union_master_wids,
    _ordered_under_test,
    _project_trace_vector,
    _validate_owner_manifest,
)
from l2_replay_common import (  # noqa: E402
    build_state_template,
    overlay_observable_into_state,
    project_observable_from_state,
    refresh_allocator_views,
    resolve_trace_path,
)

PAIR = ["ProteinProcessingI", "ProteinProcessingII"]
MAX_TICKS = 5


def _build_shared_state_for_tick(
    *,
    tick: int,
    ordered: list[str],
    contexts: dict[str, Any],
    all_observables: list[str],
    owner_manifest: dict[str, str],
    master_wids_by_observable: dict[str, list[str]],
) -> tuple[dict[str, Any], dict[str, dict[str, np.ndarray]], dict[str, dict[str, np.ndarray]]]:
    shared_state = build_state_template(contexts[ordered[0]].process)
    before_vectors: dict[str, dict[str, np.ndarray]] = {}
    after_vectors: dict[str, dict[str, np.ndarray]] = {}

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

    for obs in all_observables:
        owner_name = owner_manifest[obs]
        owner_ctx = contexts[owner_name]
        source_vec = before_vectors[owner_name][obs]
        owner_wids = owner_ctx.wids_by_observable[obs]
        master_vec = np.zeros(len(master_wids_by_observable[obs]), dtype=np.float64)
        for owner_idx, owner_wid in enumerate(owner_wids):
            master_idx = owner_ctx.process_wid_to_master_idx[obs][owner_wid]
            master_vec[master_idx] = float(source_vec[owner_idx])
        overlay_observable_into_state(
            process=owner_ctx.process,
            state=shared_state,
            observable=obs,
            vector=master_vec,
            wids=master_wids_by_observable[obs],
        )

    return shared_state, before_vectors, after_vectors


def _oracle_master_vector_for_ppii_processed(
    *,
    ppii_ctx: Any,
    ppii_after_vec: np.ndarray,
    n_master: int,
) -> np.ndarray:
    out = np.zeros(n_master, dtype=np.float64)
    idx_map = ppii_ctx.process_idx_to_master_idx["processedMonomers"]
    for proc_idx in range(ppii_after_vec.shape[0]):
        master_idx = idx_map[proc_idx]
        out[master_idx] = float(ppii_after_vec[proc_idx])
    return out


def main() -> int:
    ordered = _ordered_under_test(PAIR)
    with ExitStack() as stack:
        contexts: dict[str, Any] = {}
        for name in ordered:
            trace_handle = stack.enter_context(h5py.File(resolve_trace_path(name), "r"))
            contexts[name] = _build_context(name, 0, trace_handle)

        n_ticks_values = {contexts[name].n_ticks for name in ordered}
        if len(n_ticks_values) != 1:
            raise RuntimeError(f"n_ticks mismatch across traces: {sorted(n_ticks_values)}")
        n_ticks = int(next(iter(n_ticks_values)))
        max_ticks = min(MAX_TICKS, n_ticks)

        all_observables, master_wids_by_observable = _build_union_master_wids(
            ordered=ordered,
            contexts=contexts,
        )
        _assign_master_maps(
            ordered=ordered,
            contexts=contexts,
            all_observables=all_observables,
            master_wids_by_observable=master_wids_by_observable,
        )
        owner_manifest = _build_owner_manifest(
            ordered=ordered,
            contexts=contexts,
            all_observables=all_observables,
        )
        _validate_owner_manifest(
            ordered=ordered,
            contexts=contexts,
            all_observables=all_observables,
            owner_manifest=owner_manifest,
        )

        ppi_ctx = contexts["ProteinProcessingI"]
        ppii_ctx = contexts["ProteinProcessingII"]

        processed_master_wids = master_wids_by_observable["processedMonomers"]
        if len(processed_master_wids) <= 174:
            raise RuntimeError(
                f"processedMonomers master list too short for index 174: len={len(processed_master_wids)}"
            )
        print(f"master_wids[174] = {processed_master_wids[174]}")

        tick0_state, tick0_before, _tick0_after = _build_shared_state_for_tick(
            tick=0,
            ordered=ordered,
            contexts=contexts,
            all_observables=all_observables,
            owner_manifest=owner_manifest,
            master_wids_by_observable=master_wids_by_observable,
        )
        bootstrap_counts = tick0_state.get("protein", {}).get("counts", {})
        if not isinstance(bootstrap_counts, dict):
            bootstrap_counts = {}
        bootstrap_nonzero = {
            str(wid): float(val)
            for wid, val in bootstrap_counts.items()
            if float(val) != 0.0
        }
        watched_wids = sorted(bootstrap_nonzero.keys())
        print("tick0 bootstrap protein.counts nonzero:")
        print(json.dumps(bootstrap_nonzero, sort_keys=True))

        ppi_proc_idx = {wid: idx for idx, wid in enumerate(ppi_ctx.wids_by_observable["processedMonomers"])}
        ppii_proc_idx = {
            wid: idx for idx, wid in enumerate(ppii_ctx.wids_by_observable["processedMonomers"])
        }
        ppi_master_idx = ppi_ctx.process_wid_to_master_idx["processedMonomers"]
        ppii_master_idx = ppii_ctx.process_wid_to_master_idx["processedMonomers"]

        print("watched wid index map:")
        for wid in watched_wids:
            row = {
                "wid": wid,
                "ppi_processed_idx": ppi_proc_idx.get(wid, -1),
                "ppii_processed_idx": ppii_proc_idx.get(wid, -1),
                "master_idx_via_ppi": ppi_master_idx.get(wid, -1),
                "master_idx_via_ppii": ppii_master_idx.get(wid, -1),
            }
            print(json.dumps(row, sort_keys=True))

        print(f"running per-tick probe for ticks 0..{max_ticks - 1}")
        for tick in range(max_ticks):
            shared_state, before_vectors, after_vectors = _build_shared_state_for_tick(
                tick=tick,
                ordered=ordered,
                contexts=contexts,
                all_observables=all_observables,
                owner_manifest=owner_manifest,
                master_wids_by_observable=master_wids_by_observable,
            )

            refresh_allocator_views(ppi_ctx.process, shared_state)
            ppi_update = ppi_ctx.process.next_update(1.0, shared_state)
            _apply_update(shared_state, ppi_update)

            refresh_allocator_views(ppii_ctx.process, shared_state)
            ppii_update = ppii_ctx.process.next_update(1.0, shared_state)
            _apply_update(shared_state, ppii_update)

            harness_processed_vec = project_observable_from_state(
                process=ppii_ctx.process,
                state=shared_state,
                observable="processedMonomers",
                wids=ppii_ctx.wids_by_observable["processedMonomers"],
                bound_enzymes_before=before_vectors["ProteinProcessingII"].get("boundEnzymes"),
            )
            oracle_master_vec = _oracle_master_vector_for_ppii_processed(
                ppii_ctx=ppii_ctx,
                ppii_after_vec=after_vectors["ProteinProcessingII"]["processedMonomers"],
                n_master=len(processed_master_wids),
            )

            ppi_processed = (ppi_update.get("protein", {}) or {}).get("processed_counts", {})
            ppii_processed = (ppii_update.get("protein", {}) or {}).get("processed_counts", {})
            if not isinstance(ppi_processed, dict):
                ppi_processed = {}
            if not isinstance(ppii_processed, dict):
                ppii_processed = {}

            for wid in watched_wids:
                proc_idx = ppii_proc_idx.get(wid, -1)
                master_idx = ppii_master_idx.get(wid, -1)
                harness_val = (
                    float(harness_processed_vec[proc_idx])
                    if 0 <= proc_idx < harness_processed_vec.shape[0]
                    else float("nan")
                )
                oracle_val = (
                    float(oracle_master_vec[master_idx])
                    if 0 <= master_idx < oracle_master_vec.shape[0]
                    else float("nan")
                )
                row = {
                    "tick": tick,
                    "wid": wid,
                    "master_idx": master_idx,
                    "ppi_emit_protein.processed_counts": float(ppi_processed.get(wid, 0.0)),
                    "ppii_emit_protein.processed_counts": float(ppii_processed.get(wid, 0.0)),
                    "harness_processedMonomers": harness_val,
                    "oracle_processedMonomers": oracle_val,
                    "diff_harness_minus_oracle": harness_val - oracle_val,
                }
                print(json.dumps(row, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
