"""Day-42 multi-sample probe v2: do the 4 substitution-pair WIDs dominate
Karr's recorded substrate movement across all 20 samples, not just (s=0, t=1)?

Loads Karr's recorded substrate state (3, 585) at each of seeds 0-9 × ticks 1, 5
from per_process_traces_v2_s{seed:03d}/Metabolism_100ticks.mat. Computes Karr's
substrate delta (post - pre) per sample and decomposes by substrate row.

Key question: are substrate rows {300, 439, 469, 470, 536, 537, 541, 542}
(the 8 columns of the 4 substitution pairs) always in the top contributors,
or do other rows (H2O, ATP, O2, etc.) dominate at some samples?

If 4-pair rows dominate at all samples: Day-42 root-cause story generalizes.
If not: there are other mechanisms at non-(0,1) samples, and the story is
incomplete for closing the W1=161 gate across 500 audit samples.
"""
import json
import sys
from pathlib import Path

import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent

# 4 biological-substitution pair substrate rows (from Day-42 root-cause probe)
PAIR_ROWS = {
    "PHE": 469, "PhePhe": 470,
    "TRP": 541, "TrpTrp": 542,
    "HDCA": 300, "OCDCEA": 439,
    "TRIOLEIN": 536, "TRIPALMITIN": 537,
}
PAIR_ROW_IDS = set(PAIR_ROWS.values())

# GAP_MAP 17 WIDs from Day-40 work (rough mapping; using observed Day-42 names)
# Top GAP_MAP rows include H2O (297), ATP (29), O2 (420), H2O2 (298), etc.
GAP_MAP_ROW_IDS = {297, 29, 420, 298, 18, 557, 560, 547, 488, 513, 515, 527, 16, 26, 28, 29, 211, 395, 406, 407, 413, 415, 488}


def load_substrate_states(mat_path: Path):
    """Returns (pre_state[100, 585, 3], post_state[100, 585, 3]) from a Metabolism_100ticks.mat file.

    states_before/substrates is a (1, 100) array of object refs;
    each ref points to a (3, 585) array in #refs#.
    """
    with h5py.File(str(mat_path), "r") as f:
        pre_refs = f["states_before/substrates"]
        post_refs = f["states_after/substrates"]
        n_ticks = pre_refs.shape[1]

        pre = np.zeros((n_ticks, 585, 3), dtype=np.float64)
        post = np.zeros((n_ticks, 585, 3), dtype=np.float64)

        for t in range(n_ticks):
            pre_obj = pre_refs[0, t]
            post_obj = post_refs[0, t]
            pre_arr = np.array(f[pre_obj]).T  # (585, 3) after transpose
            post_arr = np.array(f[post_obj]).T
            pre[t] = pre_arr
            post[t] = post_arr
    return pre, post


def main():
    base = REPO / "data" / "m1_sources" / "karr_native"
    target_seeds = list(range(10))
    target_ticks = [1, 5]

    available = []
    missing = []
    samples = []

    for seed in target_seeds:
        path = base / f"per_process_traces_v2_s{seed:03d}" / "Metabolism_100ticks.mat"
        if not path.exists():
            for t in target_ticks:
                missing.append((seed, t))
            continue
        try:
            pre, post = load_substrate_states(path)
            for t in target_ticks:
                if t < pre.shape[0]:
                    delta = post[t] - pre[t]  # (585, 3)
                    samples.append({"seed": seed, "tick": t, "delta": delta, "pre": pre[t], "post": post[t]})
                    available.append((seed, t))
                else:
                    missing.append((seed, t))
        except Exception as e:
            print(f"  ERROR loading seed {seed}: {e}")
            for t in target_ticks:
                missing.append((seed, t))

    print(f"Available samples: {len(available)}/20")
    print(f"Missing: {missing if len(missing) < 25 else f'{len(missing)} samples'}")
    if not samples:
        print("No samples available — exiting")
        return

    # Per-sample analysis
    per_sample_data = []
    pair_top5_count = {name: 0 for name in PAIR_ROWS}
    pair_top1_count = {name: 0 for name in PAIR_ROWS}
    gap_map_top5_count = {row: 0 for row in GAP_MAP_ROW_IDS}
    pair_row_in_top5_count = 0  # any pair row in top-5
    other_row_dominates_count = 0  # top-1 is NOT a pair row

    karr_delta_l1_per_sample = []

    print()
    print(f"{'sample':>10s} {'L1':>12s} {'top5 substrate rows (with abs delta L1)':<70s}")
    print("-" * 105)

    for sample in samples:
        d = sample["delta"]
        abs_per_row = np.abs(d).sum(axis=1)  # (585,)
        top5 = np.argsort(-abs_per_row)[:5]
        top5_vals = abs_per_row[top5]
        karr_l1 = float(abs_per_row.sum())
        karr_delta_l1_per_sample.append(karr_l1)

        any_pair_in_top5 = any(int(r) in PAIR_ROW_IDS for r in top5)
        top1_is_pair = int(top5[0]) in PAIR_ROW_IDS

        if any_pair_in_top5:
            pair_row_in_top5_count += 1
        if not top1_is_pair:
            other_row_dominates_count += 1

        for name, row in PAIR_ROWS.items():
            if row in top5:
                pair_top5_count[name] += 1
            if row == top5[0]:
                pair_top1_count[name] += 1

        for row in GAP_MAP_ROW_IDS:
            if row in top5:
                gap_map_top5_count[row] += 1

        top5_str = ", ".join(f"r{int(r)}={int(top5_vals[i])}" for i, r in enumerate(top5))
        print(f"  s={sample['seed']},t={sample['tick']:>2d}   {karr_l1:>12.0f}   {top5_str:<70s}")

        per_sample_data.append({
            "seed": sample["seed"], "tick": sample["tick"],
            "karr_delta_l1": karr_l1,
            "top5_rows": top5.tolist(),
            "top5_abs_l1": top5_vals.tolist(),
            "any_pair_in_top5": bool(any_pair_in_top5),
            "top1_is_pair_row": bool(top1_is_pair),
        })

    n = len(samples)
    print()
    print(f"Aggregate across {n} samples:")
    print(f"  any-pair-row in top-5: {pair_row_in_top5_count}/{n} ({100*pair_row_in_top5_count/n:.0f}%)")
    print(f"  NON-pair row dominates (top-1): {other_row_dominates_count}/{n} ({100*other_row_dominates_count/n:.0f}%)")
    print(f"  Karr delta L1 distribution: mean={np.mean(karr_delta_l1_per_sample):.0f}, "
          f"min={np.min(karr_delta_l1_per_sample):.0f}, max={np.max(karr_delta_l1_per_sample):.0f}")
    print()
    print("Per-pair-WID top-5 frequency:")
    for name, row in PAIR_ROWS.items():
        c5 = pair_top5_count[name]
        c1 = pair_top1_count[name]
        print(f"  {name:>12s} (row {row:>3d}): top-5 {c5:>2d}/{n} ({100*c5/n:>3.0f}%)   top-1 {c1:>2d}/{n}")
    print()
    print("GAP_MAP row top-5 frequency (only those that appeared):")
    for row, c in sorted(gap_map_top5_count.items(), key=lambda x: -x[1]):
        if c > 0:
            print(f"  row {row:>3d}: {c:>2d}/{n} ({100*c/n:>3.0f}%)")

    verdict = ""
    if pair_row_in_top5_count == n:
        verdict = "PAIR_DOMINATES_ALL"
    elif pair_row_in_top5_count >= int(0.8 * n):
        verdict = "PAIR_DOMINATES_MOSTLY"
    else:
        verdict = "PAIR_DOES_NOT_DOMINATE"

    print()
    print(f"VERDICT: {verdict}")
    if verdict == "PAIR_DOMINATES_ALL":
        print("  4-substitution-pair root cause GENERALIZES across all samples.")
    elif verdict == "PAIR_DOMINATES_MOSTLY":
        print(f"  4-pair root cause holds at {pair_row_in_top5_count}/{n} samples; investigate the {n - pair_row_in_top5_count} where it doesn't.")
    else:
        print(f"  4-pair root cause does NOT generalize; other rows dominate at {n - pair_row_in_top5_count}/{n} samples.")

    out = {
        "available_samples": len(available),
        "missing_samples": [list(m) for m in missing],
        "verdict": verdict,
        "aggregate": {
            "any_pair_in_top5_count": pair_row_in_top5_count,
            "non_pair_dominates_count": other_row_dominates_count,
            "n_samples": n,
            "karr_delta_l1_mean": float(np.mean(karr_delta_l1_per_sample)),
            "karr_delta_l1_min": float(np.min(karr_delta_l1_per_sample)),
            "karr_delta_l1_max": float(np.max(karr_delta_l1_per_sample)),
        },
        "per_pair_top5_freq": pair_top5_count,
        "per_pair_top1_freq": pair_top1_count,
        "gap_map_top5_freq": {str(k): v for k, v in gap_map_top5_count.items() if v > 0},
        "per_sample": per_sample_data,
    }
    out_path = REPO / "tmp" / "h_multisample_v2.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
