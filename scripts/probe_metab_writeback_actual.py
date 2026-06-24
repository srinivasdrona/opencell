"""Probe what the L2.2 Metabolism runner actually produced vs Karr's recorded delta.

W1=168.39 vs expected drop to <5 means substrate delta magnitudes are wrong.
Diagnose by: instantiate the exact process the L2.2 runner uses, run tick 0
at Karr's pre-state, inspect the delta returned, compare to Karr's recorded delta.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "vivarium"))

# Use the exact L2.2 runner factory
from _l2_2_design_a_runner_helpers import _metabolism_process

proc = _metabolism_process(0)
print(f"Process: dynamic_bounds={proc.dynamic_bounds}, "
      f"enable_karr_substrate_writeback={proc.enable_karr_substrate_writeback}, "
      f"enable_lp_writeback={proc.enable_lp_writeback}")
print(f"  _karr_writeback_fixture is None: {proc._karr_writeback_fixture is None}")
print(f"  _karr_writeback_rng is None: {proc._karr_writeback_rng is None}")
print(f"  _sub_state shape: {None if proc._sub_state is None else proc._sub_state.shape}")

# Load Karr's tick-0 pre/post substrate state
trace_path = REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    def get3d(p, t):
        ds = h[p]
        ref = ds[0, t] if ds.shape[0] == 1 else ds[t, 0]
        return np.asarray(h[ref][()], dtype=np.float64)
    karr_pre = get3d("states_before/substrates", 0).T   # (585, 3)
    karr_post = get3d("states_after/substrates", 0).T
karr_delta = karr_post - karr_pre
print(f"\nKarr delta sum_abs: {np.abs(karr_delta).sum():.0f}")
print(f"  cytosol nonzero: {(karr_delta[:,0]!=0).sum()}, sum_abs={np.abs(karr_delta[:,0]).sum():.0f}")
print(f"  extracellular nonzero: {(karr_delta[:,1]!=0).sum()}, sum_abs={np.abs(karr_delta[:,1]).sum():.0f}")

# Build a states dict that mimics what the L2.2 runner feeds (cytosol values only on shared port)
sub_ids = list(proc._sub_ids)
states = {
    "substrates": {sid: float(karr_pre[i, 0]) for i, sid in enumerate(sub_ids)},
    "enzymes": {ewid: 0.0 for ewid in proc.enzyme_wids},
    "boundEnzymes": {ewid: 0.0 for ewid in proc.enzyme_wids},
    "metabolic_reaction": {},
    "m1_pools": {},
    "trace_hint": {},
}
# Seed enzymes from the trace too
with h5py.File(trace_path, "r") as h:
    enz_before = get3d("states_before/enzymes", 0)
print(f"\nenz_before shape: {enz_before.shape}, enzyme_wids count: {len(proc.enzyme_wids)}")
if enz_before.size and len(proc.enzyme_wids) == enz_before.size:
    enz_flat = enz_before.ravel()
    for i, ewid in enumerate(proc.enzyme_wids):
        states["enzymes"][ewid] = float(enz_flat[i])

# Seed _sub_state from Karr pre (replace bootstrapped fixture)
proc._sub_state = karr_pre.copy()
proc._enz_state = enz_before.reshape(-1).astype(float) if proc._enz_state is not None else proc._enz_state
print(f"After overlay: _sub_state.sum_abs={np.abs(proc._sub_state).sum():.0f}")

# Call next_update — same code path as L2.2 runner
update = proc.next_update(1.0, states)
print(f"\nUpdate keys: {sorted(update.keys())}")
sub_delta = update.get("substrates", {})
print(f"substrates delta: keys={len(sub_delta)}, sum_abs={sum(abs(v) for v in sub_delta.values()):.0f}")
if sub_delta:
    # Top 10 by magnitude
    top = sorted(sub_delta.items(), key=lambda kv: -abs(kv[1]))[:10]
    print("Top 10 substrate deltas:")
    for wid, v in top:
        try:
            i = sub_ids.index(wid)
            karr_total = karr_delta[i, :].sum()
            print(f"  {wid}: OC={v:+.1f} vs Karr total_per_wid={karr_total:+.1f}")
        except ValueError:
            print(f"  {wid}: OC={v:+.1f} (not in sub_ids)")

# Karr per-WID totals
karr_per_wid = karr_delta.sum(axis=1)
karr_per_wid_nz = (karr_per_wid != 0).sum()
karr_per_wid_sum_abs = np.abs(karr_per_wid).sum()
print(f"\nKarr per-WID delta (summed across compartments):")
print(f"  nonzero WIDs: {karr_per_wid_nz}")
print(f"  sum_abs: {karr_per_wid_sum_abs:.0f}")
print(f"  top 10:")
top_karr = sorted([(sub_ids[i], karr_per_wid[i]) for i in range(585) if karr_per_wid[i] != 0],
                   key=lambda kv: -abs(kv[1]))[:10]
for wid, v in top_karr:
    oc_v = sub_delta.get(wid, 0.0)
    print(f"  {wid}: Karr={v:+.0f} vs OC={oc_v:+.1f}")

# Diagnose: what fraction of the delta is being produced?
oc_sum_abs = sum(abs(v) for v in sub_delta.values())
print(f"\n=== W1 BUDGET ===")
print(f"Karr per-WID sum_abs: {karr_per_wid_sum_abs:.0f}")
print(f"OC sum_abs: {oc_sum_abs:.1f}")
print(f"Recovery ratio: {oc_sum_abs / max(karr_per_wid_sum_abs, 1):.3f}")
print(f"Per-WID expected at right magnitude if writeback works correctly")

# Diagnose: what is the FBA growth at the L2.2-runner call (compare against Karr's growth)
mr = update.get("metabolic_reaction", {})
oc_growth = mr.get("growth_per_s", None) if isinstance(mr, dict) else None
print(f"\nOC FBA growth_per_s: {oc_growth}")
print("(Karr's growth must be probed from the trace state if recorded)")
