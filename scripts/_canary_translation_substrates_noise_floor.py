"""
Canary: estimate intra-Karr noise-floor W1 for Translation::substrates.

Question (post-F4): the Karr-vs-OC W1max for Translation::substrates is
23,771 mean 12,509. Is this above the noise floor of 50-seed bootstrap
variation within Karr itself?

Method:
  - Load all 50 Karr Translation seeds' substrates trace from
    states_after (the SNAPSHOT-equivalent of states_before[t+1]).
  - For each tick t in [0..99], pick the substrates vector (len ~104).
  - Split 50 seeds into two random halves of 25 each (B=20 bootstrap reps).
  - For each WID dimension, compute 1-D W1 between the two halves' marginal
    distributions; sum across WIDs (or report top-3 / max), per the
    L2.2 Wasserstein-top-3 convention.
  - Report per-tick W1 stats: median across bootstraps, max across ticks.

Decision frame:
  intra-Karr W1max ~ Karr-vs-OC W1max  -> 23k is noise-floor; substrates
                                          gate is effectively passing.
  intra-Karr W1max << Karr-vs-OC       -> 23k is real mechanism/semantics
                                          gap; open F5-substrates.
"""
import sys, h5py, numpy as np
from pathlib import Path
from scipy.stats import wasserstein_distance

ENS = Path("/mnt/e/opencell/data/m1_sources/karr_native/ensembles/translation")
N_SEEDS = 50
N_TICKS = 100
N_BOOT = 20
RNG = np.random.default_rng(20260605)


def load_seed_substrates(seed):
    p = ENS / f"seed_{seed:03d}" / "Translation_100ticks.mat"
    with h5py.File(p, 'r') as f:
        ds_a = f['states_after']['substrates']
        # MATLAB cell array: ds_a[0,t] is a reference to a 1-D array
        n_ticks = ds_a.shape[1]
        wid_len = np.asarray(f[ds_a[0, 0]][()]).flatten().shape[0]
        out = np.zeros((n_ticks, wid_len), dtype=np.float64)
        for t in range(n_ticks):
            out[t] = np.asarray(f[ds_a[0, t]][()]).flatten()
        return out


def main():
    print(f"Loading {N_SEEDS} seeds...")
    seeds = []
    for s in range(N_SEEDS):
        try:
            seeds.append(load_seed_substrates(s))
        except Exception as e:
            print(f"  seed {s} FAIL: {e}")
    seeds = np.stack(seeds, axis=0)  # (50, n_ticks, n_wids)
    print(f"  shape: {seeds.shape}  (seeds, ticks, wids)")

    n_seeds, n_ticks, n_wids = seeds.shape

    w1_per_tick_max = []
    w1_per_tick_sum = []
    w1_per_tick_top3 = []

    for t in range(n_ticks):
        # Bootstrap: B random split-half W1 per tick
        per_boot_max = []
        per_boot_sum = []
        per_boot_top3 = []
        for b in range(N_BOOT):
            perm = RNG.permutation(n_seeds)
            half = n_seeds // 2
            A = seeds[perm[:half], t, :]  # (25, n_wids)
            B = seeds[perm[half:half * 2], t, :]
            w1s = np.zeros(n_wids)
            for w in range(n_wids):
                a = A[:, w]; b_ = B[:, w]
                # Skip channels with zero variance (W1=0 trivially)
                if a.std() == 0 and b_.std() == 0 and a.mean() == b_.mean():
                    continue
                w1s[w] = wasserstein_distance(a, b_)
            per_boot_max.append(float(w1s.max()))
            per_boot_sum.append(float(w1s.sum()))
            top3 = np.sort(w1s)[-3:]
            per_boot_top3.append(float(top3.sum()))
        w1_per_tick_max.append(np.median(per_boot_max))
        w1_per_tick_sum.append(np.median(per_boot_sum))
        w1_per_tick_top3.append(np.median(per_boot_top3))

    w1_per_tick_max = np.array(w1_per_tick_max)
    w1_per_tick_sum = np.array(w1_per_tick_sum)
    w1_per_tick_top3 = np.array(w1_per_tick_top3)

    print()
    print(f"=== INTRA-KARR NOISE FLOOR (Translation::substrates, {N_BOOT} bootstraps) ===")
    print(f"  W1 per-channel max:  median-across-ticks {np.median(w1_per_tick_max):>10.2f}   max-across-ticks {w1_per_tick_max.max():>10.2f}")
    print(f"  W1 top-3 sum:        median-across-ticks {np.median(w1_per_tick_top3):>10.2f}   max-across-ticks {w1_per_tick_top3.max():>10.2f}")
    print(f"  W1 full sum (all wids): median-across-ticks {np.median(w1_per_tick_sum):>10.2f}   max-across-ticks {w1_per_tick_sum.max():>10.2f}")
    print()
    print(f"Compare to F4 post-fix Karr-vs-OC:  W1max = 23771   mean = 12509")
    print()
    # Print per-tick max trajectory for first/last few ticks
    print("Per-tick W1max trajectory:")
    for t in [0, 1, 2, 5, 10, 25, 50, 75, 99]:
        print(f"  tick {t:>3d}:  W1max = {w1_per_tick_max[t]:>10.2f}   top3 = {w1_per_tick_top3[t]:>10.2f}")

    ratio = 23771.0 / max(w1_per_tick_max.max(), 1e-9)
    print()
    print(f"=== VERDICT ===")
    print(f"  Karr-vs-OC / intra-Karr noise-floor ratio: {ratio:.1f}x")
    if ratio < 2:
        print("  --> Karr-vs-OC is within ~2x of intra-Karr noise. 23k is likely NOISE-FLOOR.")
        print("      Substrates gate is effectively passing for this stochastic process.")
    elif ratio < 10:
        print("  --> Karr-vs-OC is 2-10x intra-Karr. Borderline; substrates has SOME mechanism drift.")
    else:
        print("  --> Karr-vs-OC is >10x intra-Karr. 23k is REAL mechanism or semantics gap.")
        print("      Open F5-substrates investigation.")


if __name__ == '__main__':
    main()
