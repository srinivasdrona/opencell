"""Probe: inspect Replication oracle trace shape + confirm the idle-gate bug.

Two purposes:
1. Confirm how many seeds live in the canonical (unsuffixed) v2 trace file,
   since the L2.2 catalog wants N_seeds=50 but this worktree only has
   ``per_process_traces_v2`` (canonical) + ``per_process_traces_v2_s001``
   junctioned locally.
2. Empirically confirm the root cause: with Karr's real chromosome/
   boundEnzymes/substrates state overlaid exactly like the L2.2 Design-A
   runner does, ``KarrReplicationProcess.next_update`` never left its
   synthetic ``chromosome.replication_state == "idle"`` default in the
   per-process replay harness (which runs no `ReplicationInitiation`
   coordinator), so it no-op'd on every sampled tick even while Karr's
   own polymerizedRegions were being actively rewritten underneath it.
   After the fix (real-data idle-gate fallback in `next_update`), this
   probe should show the gate opening whenever Karr shows helicase-bound
   or fork-started activity, matching Karr's per-tick deltas.

Read-only; does not touch catalog/thresholds/production code.
"""
from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.state.chromosome_store import ChromosomeStore  # noqa: E402
from opencell.vivarium.karr_replication import KarrReplicationProcess  # noqa: E402

TRACE = REPO / "data/m1_sources/karr_native/per_process_traces_v2/Replication_100ticks.mat"


def _store_at(trace: h5py.File, group: str, tick: int) -> ChromosomeStore:
    ds = trace[f"{group}/chromosome"]
    ref = ds[0, tick] if ds.shape[0] == 1 else ds[tick, 0]
    return ChromosomeStore.from_hdf5_group(trace[ref])


def _vector_at(trace: h5py.File, group: str, observable: str, tick: int) -> np.ndarray:
    ds = trace[f"{group}/{observable}"]
    row = ds[0, tick] if ds.shape[0] == 1 else ds[tick, 0]
    if isinstance(row, h5py.h5r.Reference):
        row = trace[row][()]
    return np.asarray(row, dtype=np.float64).reshape(-1)


def main() -> None:
    print(f"Trace: {TRACE}")
    print(f"  exists={TRACE.exists()} size={TRACE.stat().st_size / 1e6:.1f} MB")

    with h5py.File(TRACE, "r") as h:
        print(f"  top keys: {list(h.keys())}")
        print(f"  metadata keys: {list(h['metadata'].keys())}")
        n_ticks = int(np.asarray(h["metadata/n_ticks"][()]).reshape(-1)[0])
        print(f"  n_ticks: {n_ticks}")
        if "seed" in h["metadata"]:
            print(f"  seed: {np.asarray(h['metadata/seed'][()]).reshape(-1)}")
        chrom_ds = h["states_before/chromosome"]
        print(f"  states_before/chromosome shape: {chrom_ds.shape} (seed-dim, tick-dim)")

        process = KarrReplicationProcess({"rng_seed": 0})

        n_idle_gate_fires = 0
        n_ticks_checked = min(20, n_ticks)
        for tick in range(n_ticks_checked):
            before = _store_at(h, "states_before", tick)
            after = _store_at(h, "states_after", tick)
            poly_before = before.get_field("polymerizedRegions")
            poly_after = after.get_field("polymerizedRegions")
            delta_nnz = poly_after.calc_num_edges() - poly_before.calc_num_edges()
            delta_val = float(poly_after.values.sum() - poly_before.values.sum())

            # Build the exact runtime state the L2.2 Design-A runner builds:
            # schema defaults, then overlay Karr's REAL before-chromosome
            # (mirrors `build_state_template` + `_overlay_chromosome_into_state`
            # in tests/vivarium/_l2_2_design_a_runner_helpers.py).
            runtime_state = {
                "chromosome": {},
                "substrates": {},
                "enzymes": {},
                "boundEnzymes": {},
            }
            chrom_state = runtime_state["chromosome"]
            chrom_state.update(before.to_state())
            replication_state_seen = chrom_state.get("replication_state", "<absent, defaults to idle>")

            bound_vec = _vector_at(h, "states_before", "boundEnzymes", tick)
            bound_now = {wid: float(bound_vec[i]) for i, wid in enumerate(process.enzyme_wids)}
            helicase_bound = bound_now.get(process.enzyme_wid_helicase, 0.0)
            left_pos_bp, right_pos_bp = process._infer_fork_positions_from_polymerized(poly_before)

            # Overlay Karr's real substrate counts and treat them as fully
            # allocated (mirrors `refresh_allocator_views` in
            # tests/vivarium/l2_replay_common.py, which the real L2.2/L2.1
            # harness uses to cap a process's allocation at the true
            # available count each tick). Without this, an empty
            # `substrates_allocated` starves every dNTP/H2O/NAD demand to
            # zero and `next_update` silently no-ops on the
            # elongation-substrate check further down -- a probe-harness
            # artifact, not evidence of an idle-gate failure.
            substrate_vec = _vector_at(h, "states_before", "substrates", tick)
            substrates_now = {wid: float(substrate_vec[i]) for i, wid in enumerate(process.substrate_wids)}

            update = process.next_update(
                1.0,
                {
                    "chromosome": chrom_state,
                    "substrates": substrates_now,
                    "enzymes": {},
                    "boundEnzymes": bound_now,
                    "substrates_allocated": {process.name: dict(substrates_now)},
                },
            )
            chrom_update = update.get("chromosome", {})
            oc_touched_polymerized = "polymerizedRegions" in chrom_update
            if not oc_touched_polymerized:
                n_idle_gate_fires += 1
            print(
                f"  tick={tick:3d} karr_delta_nnz={delta_nnz:+d} karr_delta_val={delta_val:+.1f} "
                f"helicase_bound={helicase_bound:.0f} left_pos_bp={left_pos_bp} right_pos_bp={right_pos_bp} "
                f"replication_state_in_overlay={replication_state_seen!r} "
                f"oc_touched_polymerizedRegions={oc_touched_polymerized}"
            )

        print(
            f"\n  idle-gate fired (no polymerizedRegions update emitted) on "
            f"{n_idle_gate_fires}/{n_ticks_checked} sampled ticks."
        )


if __name__ == "__main__":
    main()
