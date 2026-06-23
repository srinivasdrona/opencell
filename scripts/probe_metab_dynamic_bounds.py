"""Test if dynamic_bounds=True closes the Metabolism L2.2 gap.

Hypothesis: the current L2.2 runner uses Metabolism with static FBA bounds,
which produces underpowered fluxes. Enabling dynamic_bounds=True triggers
calcFluxBounds-equivalent + LP writeback to cytosol substrates.

This is a one-tick probe (not full ensemble) to check if the algorithm changes
get OC closer to Karr's substrate delta.
"""
from __future__ import annotations
import sys
from pathlib import Path

import h5py
import numpy as np

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tests" / "vivarium"))

from opencell.vivarium.karr_metabolism import KarrMetabolismProcess
from opencell.m1 import karr_metabolism as km
from l2_replay_common import (  # type: ignore
    build_state_template,
    overlay_observable_into_state,
    refresh_allocator_views,
)

# Load Karr trace
trace_path = _REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat"

with h5py.File(trace_path, "r") as handle:
    def get_3d(group_path: str, tick: int) -> np.ndarray:
        ds = handle[group_path]
        rows, cols = int(ds.shape[0]), int(ds.shape[1])
        if rows == 1 and cols >= (tick + 1):
            ref = ds[0, tick]
        elif cols == 1 and rows >= (tick + 1):
            ref = ds[tick, 0]
        else:
            ref = ds[tick, 0] if rows >= (tick + 1) else ds[0, tick]
        return np.asarray(handle[ref][()], dtype=np.float64)

    karr_sub_before = get_3d("states_before/substrates", 0).T   # (585, 3)
    karr_sub_after = get_3d("states_after/substrates", 0).T
    karr_enz_before = get_3d("states_before/enzymes", 0)
    karr_bound_before = get_3d("states_before/boundEnzymes", 0)

karr_delta = karr_sub_after - karr_sub_before
print(f"Karr substrate delta at tick 0: nonzero={np.count_nonzero(karr_delta)}, sum_abs={np.abs(karr_delta).sum():.1f}")
karr_cyto_delta = karr_delta[:, 0]
print(f"  Cytosol-only nonzero: {np.count_nonzero(karr_cyto_delta)}, sum_abs={np.abs(karr_cyto_delta).sum():.1f}")
print(f"  Extracellular-only nonzero: {np.count_nonzero(karr_delta[:, 1])}, sum_abs={np.abs(karr_delta[:, 1]).sum():.1f}")

for mode_name, dyn in [("static_bounds (current L2.2)", False), ("dynamic_bounds=True", True)]:
    print(f"\n=== Mode: {mode_name} ===")
    model = km.load_default()
    proc = KarrMetabolismProcess({"rng_seed": 0, "model": model, "dynamic_bounds": dyn})
    state = build_state_template(proc)

    # Overlay substrates (cytosol-only since OC uses single compartment per substrate)
    sub_wids = list(proc._sub_ids)
    cyto_vec = karr_sub_before[:, 0]  # cytosol slice
    overlay_observable_into_state(
        process=proc, state=state, observable="substrates",
        vector=cyto_vec, wids=sub_wids,
    )
    enz_wids = list(proc.enzyme_wids)
    if len(enz_wids) == karr_enz_before.shape[0] or (karr_enz_before.ndim == 2 and len(enz_wids) == karr_enz_before.shape[1]):
        enz_vec = karr_enz_before.ravel()[: len(enz_wids)]
        overlay_observable_into_state(
            process=proc, state=state, observable="enzymes",
            vector=enz_vec, wids=enz_wids,
        )

    refresh_allocator_views(proc, state)
    update = proc.next_update(1.0, state)

    sub_update = update.get("substrates", {}) if isinstance(update, dict) else {}
    print(f"  OC produced substrate delta: nonzero={sum(1 for v in sub_update.values() if v)} keys")
    print(f"  OC sum_abs: {sum(abs(v) for v in sub_update.values()):.1f}")
    print(f"  Karr cytosol sum_abs: {np.abs(karr_cyto_delta).sum():.1f}")
    # Compute per-WID diff
    wid_to_idx = {wid: i for i, wid in enumerate(sub_wids)}
    diff_total = 0.0
    diff_count = 0
    for wid, oc_d in sub_update.items():
        if wid in wid_to_idx:
            k_d = karr_cyto_delta[wid_to_idx[wid]]
            d = abs(oc_d - k_d)
            if d > 0.5:
                diff_total += d
                diff_count += 1
    for wid, idx in wid_to_idx.items():
        if wid not in sub_update and abs(karr_cyto_delta[idx]) > 0.5:
            diff_total += abs(karr_cyto_delta[idx])
            diff_count += 1
    print(f"  OC-vs-Karr cytosol diff: count={diff_count}, total_abs={diff_total:.1f}")
    if "metabolic_reaction" in update:
        print(f"  Growth: {update['metabolic_reaction'].get('growth_per_s', None)}")
