"""
Apples-to-apples noise-floor canary for Translation::substrates (v2).

Matches the test's aggregation: substrates is SUMMED across WIDs to a
scalar per (seed, tick), then W1 is computed between 50-seed Karr and
50-seed OC distributions at each tick.

Compares three quantities at each tick:
  1. Karr-vs-OC W1 (the actual gate value, from F4 csv)
  2. Karr-vs-Karr bootstrap-with-replacement W1 q95 * 1.1 (the test's
     current threshold)
  3. Karr-vs-Karr split-half W1 (independent halves: a sample-based
     noise floor that doesn't double-count)

If (1) >> (3), there's a real Karr-vs-OC distributional shift.
If (1) ~ (3) and (1) >> (2), then the test's threshold is too tight
because bootstrap-with-replacement under-estimates the true noise floor.
"""
import csv, h5py, numpy as np
from pathlib import Path
from scipy.stats import wasserstein_distance

ENS_KARR = Path("/mnt/e/opencell/data/m1_sources/karr_native/ensembles/translation")
ENS_OC   = Path("/mnt/e/opencell/data/opencell_ensembles/translation")
CSV_F4   = Path("/mnt/e/opencell/data/opencell_ensembles/translation/wasserstein_failures.csv")

N_SEEDS = 50
N_TICKS = 100
N_BOOT = 200
RNG = np.random.default_rng(20260605)


def _load_karr_substrates_scalar(seed):
    """Sum substrates vector across WIDs per tick. Returns (n_ticks,)."""
    p = ENS_KARR / f"seed_{seed:03d}" / "Translation_100ticks.mat"
    with h5py.File(p, 'r') as f:
        ds_a = f['states_after']['substrates']
        out = np.zeros(N_TICKS)
        for t in range(N_TICKS):
            v = np.asarray(f[ds_a[0, t]][()]).flatten()
            out[t] = float(v.sum())
        return out


def _load_oc_substrates_scalar(seed):
    """OC npz: load substrates per-tick vector, sum, but apply Karr-WID intersection.
    For canary purposes, we use the raw F4 csv numbers instead of recomputing
    intersection — see RAW MODE below.
    """
    raise NotImplementedError("use F4 csv for Karr-vs-OC value")


def main():
    # 1. Read F4 csv for the actual Karr-vs-OC W1 per tick.
    f4 = {}
    with open(CSV_F4) as fh:
        for row in csv.DictReader(fh):
            if row['observable'] == 'substrates':
                f4[int(row['tick'])] = (float(row['w1']), float(row['threshold']))

    # 2. Load all 50 Karr scalar trajectories.
    print(f"Loading {N_SEEDS} Karr seeds (substrates summed across WIDs)...")
    karr = np.stack([_load_karr_substrates_scalar(s) for s in range(N_SEEDS)], axis=0)
    print(f"  shape: {karr.shape}  (seeds, ticks)")

    # 3. Compute the two noise-floor estimates per tick.
    print()
    print(f"  {'tick':>4} {'K-vs-OC':>10} {'thresh_now':>12} {'boot_repl':>12} {'split_half':>12}  {'OC/SH':>6}")

    summary_rows = []
    for t in range(N_TICKS):
        kv = karr[:, t]
        # bootstrap-with-replacement (matches test exactly)
        boot_dists = np.zeros(N_BOOT)
        for b in range(N_BOOT):
            ia = RNG.integers(0, N_SEEDS, size=N_SEEDS)
            ib = RNG.integers(0, N_SEEDS, size=N_SEEDS)
            boot_dists[b] = wasserstein_distance(kv[ia], kv[ib])
        boot_thresh = float(np.quantile(boot_dists, 0.95) * 1.10)

        # split-half (independent halves of 25)
        sh_dists = np.zeros(N_BOOT)
        for b in range(N_BOOT):
            perm = RNG.permutation(N_SEEDS)
            half = N_SEEDS // 2
            sh_dists[b] = wasserstein_distance(kv[perm[:half]], kv[perm[half:half*2]])
        sh_q95 = float(np.quantile(sh_dists, 0.95) * 1.10)

        k_vs_oc, current_thresh = f4.get(t, (float('nan'), float('nan')))
        ratio_sh = (k_vs_oc / sh_q95) if sh_q95 > 0 else float('inf')
        summary_rows.append((t, k_vs_oc, current_thresh, boot_thresh, sh_q95, ratio_sh))
        if t in (0,1,2,5,10,25,50,75,99):
            print(f"  {t:>4d} {k_vs_oc:>10.1f} {current_thresh:>12.1f} {boot_thresh:>12.1f} {sh_q95:>12.1f}  {ratio_sh:>5.1f}x")

    # 4. Summary verdict.
    ratios = np.array([r[5] for r in summary_rows])
    n_pass_under_sh = sum(1 for r in summary_rows if r[1] <= r[4])
    n_pass_under_boot = sum(1 for r in summary_rows if r[1] <= r[3])

    print()
    print(f"=== SUMMARY ===")
    print(f"  ticks where K-vs-OC <= split-half threshold:     {n_pass_under_sh}/{N_TICKS}")
    print(f"  ticks where K-vs-OC <= bootstrap-repl threshold: {n_pass_under_boot}/{N_TICKS}")
    print(f"  K-vs-OC / split-half ratio:  median {np.median(ratios):.2f}x  max {ratios.max():.2f}x  min {ratios.min():.2f}x")
    print()
    if np.median(ratios) > 5:
        print("  -> K-vs-OC is far above split-half noise. REAL distributional shift.")
        print("     The threshold-recalibration fix WILL NOT make substrates pass.")
    elif np.median(ratios) > 2:
        print("  -> K-vs-OC is moderately above split-half noise. Borderline shift.")
        print("     Threshold recalibration MAY help but won't pass cleanly.")
    else:
        print("  -> K-vs-OC is within split-half noise. The test threshold is too tight.")
        print("     Threshold recalibration WILL make substrates pass.")

    # Save artifact
    out_path = Path("/mnt/e/opencell/data/opencell_ensembles/translation/noise_floor_canary_v2.csv")
    with open(out_path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(["tick","k_vs_oc_w1","current_threshold","bootstrap_repl_threshold","split_half_threshold","ratio_oc_over_sh"])
        for row in summary_rows:
            w.writerow(row)
    print(f"  artifact saved: {out_path}")


if __name__ == '__main__':
    main()
