"""
Probe sweep: enumerate all channels per process MAT for the 5 remaining
L2.2 DEEP processes. For each channel report:
  - length (WID width)
  - sum at tick 0 (so we can spot product-accumulation channels at 0)
  - snapshot-equality rate (states_before[t+1] == states_after[t]) over 20 ticks

Output triages each channel:
  SNAPSHOT  : safe to put in F1 fitted-init tuple as-is
  DELTA     : channel is per-tick delta (reset semantics) -- extractor bug
  MIXED     : partially snapshot / partially delta -- needs investigation
"""
import sys, h5py, numpy as np, glob
from pathlib import Path

BASE = "/mnt/e/opencell/data/m1_sources/karr_native/per_process_traces_v2"

# 5 remaining DEEP processes (Translation + Transcription already gated)
PROCESSES = [
    "ReplicationInitiation",
    "Replication",
    "DNARepair",
    "MacromolecularComplexation",
    "Cytokinesis",
]

def classify_mat(path, label):
    print(f"\n=== {label} ===")
    p = Path(path)
    if not p.exists():
        print(f"  MISSING: {path}")
        return
    try:
        with h5py.File(path, 'r') as f:
            sb = f.get('states_before')
            sa = f.get('states_after')
            if sb is None or sa is None:
                print(f"  TOP: {list(f.keys())} (no states_before/after)")
                return
            channels = sorted(set(sb.keys()) & set(sa.keys()))
            n_ticks = next(iter(sb.values())).shape[1]
            print(f"  channels: {len(channels)}   n_ticks: {n_ticks}")
            print(f"  {'channel':<32} {'len':>6} {'sum_t0':>14} {'snap_eq':>8}  verdict")
            for ch in channels:
                ds_b = sb[ch]; ds_a = sa[ch]
                try:
                    v_b0 = np.asarray(f[ds_b[0,0]][()]).flatten()
                except Exception as e:
                    print(f"  {ch:<32} ERR tick-0 read: {e}")
                    continue
                eq = 0; total = 0
                for t in range(min(n_ticks - 1, 20)):
                    try:
                        a = np.asarray(f[ds_a[0,t]][()]).flatten()
                        b = np.asarray(f[ds_b[0,t+1]][()]).flatten()
                        if a.shape == b.shape:
                            eq += int(np.array_equal(a, b))
                            total += 1
                    except Exception:
                        continue
                rate = eq/total if total else float('nan')
                if rate >= 0.95: verdict = "SNAPSHOT"
                elif rate <= 0.05: verdict = "DELTA"
                else: verdict = f"MIXED({eq}/{total})"
                t0_sum = float(v_b0.sum()) if v_b0.size else 0.0
                print(f"  {ch:<32} {len(v_b0):>6d} {t0_sum:>14.3e} {rate:>7.0%}  {verdict}")
    except Exception as e:
        print(f"  ERR opening {path}: {e}")

if __name__ == '__main__':
    for proc in PROCESSES:
        classify_mat(f"{BASE}/{proc}_100ticks.mat", proc)
