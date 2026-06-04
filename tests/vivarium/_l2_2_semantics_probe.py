import sys, h5py, numpy as np
from pathlib import Path

def classify_mat(path):
    print(f"\n=== {path} ===")
    if not Path(path).exists():
        print("  (missing)")
        return
    try:
        with h5py.File(path,'r') as f:
            sb = f.get('states_before')
            sa = f.get('states_after')
            if sb is None or sa is None:
                print(f"  TOP: {list(f.keys())}  (no states_before/after groups)")
                return
            channels = sorted(set(sb.keys()) & set(sa.keys()))
            n_ticks = next(iter(sb.values())).shape[1]
            print(f"  channels: {len(channels)}  n_ticks: {n_ticks}")
            print(f"  {'channel':<32} {'len':>5} {'sum_t0':>14} {'snap_eq_rate':>13} {'verdict'}")
            for ch in channels:
                ds_b = sb[ch]; ds_a = sa[ch]
                # peek tick 0 length + sum
                try:
                    v_b0 = np.asarray(f[ds_b[0,0]][()]).flatten()
                except Exception:
                    continue
                # snapshot equality: compare states_before[t+1] to states_after[t]
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
                if rate >= 0.95:
                    verdict = "SNAPSHOT"
                elif rate <= 0.05:
                    verdict = "DELTA(reset-each-tick)"
                else:
                    verdict = f"MIXED ({eq}/{total})"
                print(f"  {ch:<32} {len(v_b0):>5d} {v_b0.sum():>14.3e} {rate:>13.2%} {verdict}")
    except Exception as e:
        print(f"  ERR {e}")

paths = [
    '/mnt/e/opencell-worktrees/l22-translation/data/m1_sources/karr_native/ensembles/translation/seed_000/Translation_100ticks.mat',
    '/mnt/e/opencell-worktrees/l2-matlab-reextract/data/m1_sources/karr_native/per_process_traces/Transcription_100ticks.mat',
]
# also find all per_process_traces MATs
import glob
for p in sorted(glob.glob('/mnt/e/opencell-worktrees/l2-matlab-reextract/data/m1_sources/karr_native/per_process_traces/*_100ticks.mat')):
    if p not in paths: paths.append(p)
for p in paths:
    classify_mat(p)