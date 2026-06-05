"""
Investigate the tick-0 Translation::substrates W1=318 residual.

Goal: find WHICH substrate WIDs disagree between Karr and OC at tick 0,
and by how much. Compute three views:

  1. comparison_report.json substrate_intersection_audit dump
     (intersection WIDs + dropped sides — context).
  2. Per-WID Karr_seed_000 tick-0 vs OC_seed_000 tick-0 (single-seed diff;
     pinpoints the largest disagreeing WIDs).
  3. Per-WID 50-seed median (Karr) vs 50-seed median (OC) at tick 0
     (distributional view; same WIDs, but across seeds).

Output ranks WIDs by absolute |median(OC) - median(Karr)| descending.
"""
import json, sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path("/mnt/e/opencell")
OC_ROOT = REPO / "data/opencell_ensembles/translation"
KARR_ROOT = REPO / "data/m1_sources/karr_native/ensembles/translation"
N_SEEDS = 50


def _load_audit():
    d = json.load(open(OC_ROOT / "comparison_report.json"))
    return d.get("substrates_intersection_audit", {})


def _load_oc_tick0(seed, intersect_wids):
    """OC stores substrates in npz; project to intersection WIDs."""
    meta = json.load(open(OC_ROOT / f"seed_{seed:03d}" / "metadata.json"))
    wids_by_obs = meta.get("wids_by_observable", {})
    oc_wids = list(wids_by_obs.get("substrates") or [])
    if not oc_wids:
        return None, None
    npz = np.load(OC_ROOT / f"seed_{seed:03d}" / "Translation_100ticks.npz")
    arr = npz["obs__substrates"]  # (n_ticks, n_wids)
    v = arr[0, :] if arr.shape[0] == 100 else arr[:, 0]
    wid_to_val = dict(zip(oc_wids, v))
    proj = np.array([wid_to_val.get(w, 0.0) for w in intersect_wids], dtype=np.float64)
    return proj, oc_wids


def _load_karr_tick0(seed, intersect_wids, karr_wids):
    """Karr MAT cell array; load states_after tick 0 substrates and project."""
    p = KARR_ROOT / f"seed_{seed:03d}" / "Translation_100ticks.mat"
    with h5py.File(p, 'r') as f:
        ds = f["states_after"]["substrates"]
        v = np.asarray(f[ds[0, 0]][()]).flatten()
    if len(v) != len(karr_wids):
        raise ValueError(f"Karr substrates length {len(v)} != karr_wids {len(karr_wids)}")
    wid_to_val = dict(zip(karr_wids, v))
    proj = np.array([wid_to_val.get(w, 0.0) for w in intersect_wids], dtype=np.float64)
    return proj


def main():
    audit = _load_audit()
    intersect = audit.get("intersection_wids") or []
    dropped_karr = audit.get("dropped_karr_wids") or []
    dropped_oc = audit.get("dropped_oc_wids") or []
    print("=== substrate intersection audit ===")
    print(f"  karr_n        : {audit.get('karr_wid_count')}")
    print(f"  oc_n          : {audit.get('oc_wid_count')}")
    print(f"  intersect_n   : {audit.get('intersection_wid_count')}")
    print(f"  dropped_karr  : {dropped_karr}")
    print(f"  dropped_oc[:5]: {dropped_oc[:5]}")
    print(f"  total dropped_oc: {len(dropped_oc)}")
    print(f"  tick0_seed0_w1: {audit.get('tick0_seed0_w1_over_intersection')}")

    if not intersect:
        print("No intersection WIDs in audit; bailing.")
        return

    # Need Karr WID order to load Karr vectors — load from fixture
    sys.path.insert(0, str(REPO / "tests/vivarium"))
    from l2_replay_common import load_fixture_channel_wids
    karr_wids = list(load_fixture_channel_wids("Translation", "substrates"))
    print(f"  karr_wids (from fixture, n={len(karr_wids)}): {karr_wids[:5]}...")

    # Per-WID Karr vs OC for seed_000 tick 0
    print()
    print("=== seed_000 tick 0: per-WID Karr vs OC (intersection WIDs only) ===")
    k0 = _load_karr_tick0(0, intersect, karr_wids)
    o0, oc_wids = _load_oc_tick0(0, intersect)
    deltas = o0 - k0
    rank = np.argsort(-np.abs(deltas))
    print(f"  {'WID':<14} {'Karr':>14} {'OC':>14} {'delta=OC-K':>14}")
    for i in rank[:15]:
        print(f"  {intersect[i]:<14} {k0[i]:>14.1f} {o0[i]:>14.1f} {deltas[i]:>14.1f}")
    print(f"  ... ({len(intersect)} total WIDs)")
    print(f"  sum(Karr) = {k0.sum():>14.1f}    sum(OC) = {o0.sum():>14.1f}    sum_delta = {deltas.sum():>14.1f}")
    print(f"  ||delta||_1 = {np.abs(deltas).sum():>14.1f}    L1/seed-0 ~ tick-0 W1 in scalar sense")

    # 50-seed median per WID at tick 0
    print()
    print("=== Across 50 seeds, tick 0: median(Karr) vs median(OC) per WID ===")
    k_all = np.stack([_load_karr_tick0(s, intersect, karr_wids) for s in range(N_SEEDS)], axis=0)
    o_all = np.stack([_load_oc_tick0(s, intersect)[0] for s in range(N_SEEDS)], axis=0)
    k_med = np.median(k_all, axis=0)
    o_med = np.median(o_all, axis=0)
    k_std = np.std(k_all, axis=0)
    o_std = np.std(o_all, axis=0)
    delta_med = o_med - k_med
    rank2 = np.argsort(-np.abs(delta_med))
    print(f"  {'WID':<14} {'med(K)':>12} {'med(OC)':>12} {'delta':>12} {'std(K)':>10} {'std(OC)':>10}")
    for i in rank2[:15]:
        print(f"  {intersect[i]:<14} {k_med[i]:>12.1f} {o_med[i]:>12.1f} {delta_med[i]:>12.1f} {k_std[i]:>10.1f} {o_std[i]:>10.1f}")

    # Summary scalar deltas across all seeds
    k_sum = k_all.sum(axis=1)  # per-seed scalar sums (50,)
    o_sum = o_all.sum(axis=1)
    print()
    print("=== Per-seed tick-0 scalar sums (50 seeds) ===")
    print(f"  Karr sum: mean {k_sum.mean():.1f} std {k_sum.std():.1f} min {k_sum.min():.1f} max {k_sum.max():.1f}")
    print(f"  OC   sum: mean {o_sum.mean():.1f} std {o_sum.std():.1f} min {o_sum.min():.1f} max {o_sum.max():.1f}")
    print(f"  mean(OC) - mean(Karr) = {o_sum.mean() - k_sum.mean():.1f}")


if __name__ == '__main__':
    main()
