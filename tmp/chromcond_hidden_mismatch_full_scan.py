from __future__ import annotations

# ruff: noqa: E402
import sys
from pathlib import Path

import h5py
import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
TESTS = REPO / "tests" / "vivarium"
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from l2_2_replay_common_v2 import (
    _PROCESS_SPECS,
    _build_context,
    _inject_hidden_read_surface,
    _project_trace_vector,
    _trace_cell_payload,
)
from l2_replay_common import (
    apply_count_update,
    build_state_template,
    overlay_observable_into_state,
    refresh_allocator_views,
    resolve_trace_path,
)

from opencell.state.chromosome_store import ChromosomeStore


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


def _triplets_from_state(node: dict[str, object]) -> np.ndarray:
    positions = np.asarray(node.get("positions", []), dtype=np.int64).reshape(-1)
    strands = np.asarray(node.get("strands", []), dtype=np.int64).reshape(-1)
    values = np.asarray(node.get("values", []), dtype=np.int64).reshape(-1)
    if positions.size == 0:
        return np.zeros((0, 3), dtype=np.int64)
    arr = np.column_stack((positions, strands, values))
    order = np.lexsort((arr[:, 2], arr[:, 1], arr[:, 0]))
    return arr[order]


def main() -> int:
    # Full 100-tick scan variant of chromcond_hidden_mismatch_probe.py that does
    # NOT stop at the first mismatch -- it re-injects Karr's ground-truth
    # chromosome state fresh every tick (per STATUS_L21_CHROMCOND_TICK1.md /
    # STATUS_L21_CHROMCOND_SEPT2.md methodology), so a mismatch at tick N does
    # not invalidate the independent check at tick N+1. Used to establish
    # whether the known tick-7 SMC site shift is an isolated single-tick event
    # or part of a recurring pattern across the full 100-tick trace.
    name = "ChromosomeCondensation"
    spec = _PROCESS_SPECS[name]
    mismatched_ticks: list[int] = []
    with h5py.File(resolve_trace_path(name), "r") as handle:
        ctx = _build_context(name=name, rng_seed=0, handle=handle)
        process = ctx.process

        for tick in range(ctx.n_ticks):
            state = build_state_template(process)
            for obs in spec.observables:
                before = _project_trace_vector(ctx, "states_before", obs, tick)
                overlay_observable_into_state(
                    process=process,
                    state=state,
                    observable=obs,
                    vector=before,
                    wids=ctx.wids_by_observable[obs],
                    store_path_override=spec.store_path_override,
                )
            _inject_hidden_read_surface(ctx=ctx, state=state, tick=tick)
            refresh_allocator_views(process, state)
            update = process.next_update(1.0, state)
            apply_count_update(state, update)

            after_payload = _trace_cell_payload(ctx=ctx, group="states_after", name="chromosome", tick=tick)
            if after_payload is None:
                raise RuntimeError("chromosome payload missing")
            after_store = ChromosomeStore.from_hdf5_group(after_payload)
            karr_complex = _triplets(after_store, "complexBoundSites")
            oc_complex = _triplets_from_state(state.get("chromosome", {}).get("complexBoundSites", {}))
            if not np.array_equal(oc_complex, karr_complex):
                karr_set = {tuple(row.tolist()) for row in karr_complex}
                oc_set = {tuple(row.tolist()) for row in oc_complex}
                missing = sorted(karr_set - oc_set)
                extra = sorted(oc_set - karr_set)
                print(f"MISMATCH tick={tick} karr_len={len(karr_complex)} oc_len={len(oc_complex)} missing={missing[:10]} extra={extra[:10]}")
                mismatched_ticks.append(tick)

    print(f"=== SCAN COMPLETE: {len(mismatched_ticks)} mismatched tick(s) of {ctx.n_ticks}: {mismatched_ticks}")
    return 0 if not mismatched_ticks else 1


if __name__ == "__main__":
    raise SystemExit(main())
