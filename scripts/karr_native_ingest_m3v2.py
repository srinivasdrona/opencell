"""Karr-native M3 v2: ribosome-mechanics translation prediction.

Reads `data/m1_sources/karr_flat/translation_v2_targeted.mat` (gitignored,
produced by `scripts/matlab/extract_karr_m3v2.m`) plus the existing M3 v1
fixture and writes `data/karr_fixtures/karr_native_m3_v2.{json,npz}`.

Per Karr's `Translation.m::evolveState` (line 665, ``bndProbs = this.mRNAs``)
ribosomes pick mRNAs proportional to their copy count.  The same
analysis as M2 v2 then gives

    synth_protein_i = N_active * elong * mRNA_i / sum_k(mRNA_k * length_k)

Each protein has exactly one mRNA species (no operons at the translation
stage), so the predictor is gene-aligned 482-vec.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

REPO = Path(__file__).resolve().parents[1]
MAT = REPO / "data" / "m1_sources" / "karr_flat" / "translation_v2_targeted.mat"
M3_FIXTURE_JSON = REPO / "data" / "karr_fixtures" / "karr_native_m3.json"
M3_FIXTURE_NPZ = REPO / "data" / "karr_fixtures" / "karr_native_m3.npz"
OUT_JSON = REPO / "data" / "karr_fixtures" / "karr_native_m3_v2.json"
OUT_NPZ = REPO / "data" / "karr_fixtures" / "karr_native_m3_v2.npz"


def main():
    if not MAT.exists():
        raise SystemExit(f"missing {MAT}; run scripts/matlab/extract_karr_m3v2.m first")

    print(f"loading {MAT.name}")
    raw = loadmat(MAT, squeeze_me=True, struct_as_record=False)
    d = raw["data"]

    n_active = int(d.rib_nActive)
    n_stalled = int(getattr(d, "rib_nStalled", 0))
    n_not_exist = int(getattr(d, "rib_nNotExist", 0))
    n_total = n_active + n_stalled + n_not_exist
    state_occ = np.asarray(d.rib_stateOccupancies, dtype=float).ravel()
    elong_aa_per_s = float(d.pt_ribosomeElongationRate)
    mrna_counts = np.asarray(d.pt_mRNAs, dtype=float).ravel()      # (482,)
    length_aa = np.asarray(d.pt_polypeptide_monomerLengths, dtype=float).ravel()  # (482,)
    n_mrnas_bound = np.asarray(d.rib_nMRNAsBound, dtype=int).ravel()  # (482,)

    print(f"  N_active_ribosomes={n_active} (stalled={n_stalled} notExist={n_not_exist} total={n_total})")
    print(f"  state_occupancies[active,notExist,stalled]={state_occ}")
    print(f"  elongation={elong_aa_per_s} aa/s, n_proteins={mrna_counts.size}")
    print(f"  total mRNAs in cell = {int(mrna_counts.sum())}")
    print(f"  total ribosomes bound to mRNAs = {int(n_mrnas_bound.sum())} (sanity vs nActive={n_active})")

    # M3 v1 oracle target: synth_rate_per_s = counts_mature * decay
    z3 = np.load(M3_FIXTURE_NPZ)
    karr_synth = z3["synth_rate_per_s"]  # (482,)
    counts_mature = z3["counts_mature"]
    length_aa_v1 = z3["length_aa"]
    if not np.array_equal(length_aa.astype(int), length_aa_v1.astype(int)):
        # cross-check: lengths from process and state should match
        n_diff = int(np.sum(length_aa.astype(int) != length_aa_v1.astype(int)))
        print(f"  [warn] lengths differ in {n_diff}/482 entries; using process lengths")

    # === Mechanism prediction ===
    denom = float(np.sum(mrna_counts * length_aa))
    if denom <= 0:
        raise SystemExit("denominator (sum mRNA*length) is non-positive")
    synth_predicted = n_active * elong_aa_per_s * mrna_counts / denom  # (482,)
    total_aa_polym_predicted = float(np.sum(synth_predicted * length_aa))

    # Oracle
    valid = (karr_synth > 0) & (synth_predicted > 0) & np.isfinite(karr_synth) & np.isfinite(synth_predicted)
    log2r = np.log2(synth_predicted[valid] / karr_synth[valid])
    print()
    print("=== M3 v2 oracle: ribosome mechanism vs Karr fitted ===")
    print(f"  comparable proteins: {int(valid.sum())} (excludes {int((~valid).sum())} with zero rate)")
    print(f"  log2 ratio: median={np.median(log2r):+.3f}  mean={np.mean(log2r):+.3f}  std={np.std(log2r):.3f}")
    print(f"  log2 ratio: 10pct={np.percentile(log2r,10):+.3f}  90pct={np.percentile(log2r,90):+.3f}")
    print(f"  median |log2 ratio| = {np.median(np.abs(log2r)):.3f}")
    print(f"  total synth (mech) = {np.sum(synth_predicted):.4f} per s")
    print(f"  total synth (Karr) = {np.sum(karr_synth):.4f} per s")
    print(f"  total AA polym (mech) = {total_aa_polym_predicted:.2f} aa/s "
          f"(invariant: N_active*elong = {n_active*elong_aa_per_s:.0f})")

    # Cell-cycle averaging exploration (analog of M2 v2)
    for scale in [1.0, 1.5, 2.0]:
        s = synth_predicted * scale
        valid_s = (karr_synth > 0) & (s > 0)
        log2r_s = np.log2(s[valid_s] / karr_synth[valid_s])
        print(f"  scale={scale:.2f}: median={np.median(log2r_s):+.3f}  median|log2|={np.median(np.abs(log2r_s)):.3f}")

    # Save fixture
    out_meta = {
        "schema_version": 1,
        "source_mat": str(MAT.relative_to(REPO).as_posix()),
        "matrix_npz": OUT_NPZ.name,
        "scalars": {
            "n_active_ribosomes": n_active,
            "n_stalled_ribosomes": n_stalled,
            "n_not_exist_ribosomes": n_not_exist,
            "n_total_ribosomes": n_total,
            "ribosome_elongation_rate_aa_per_s": elong_aa_per_s,
            "denom_sum_mrna_x_length": denom,
            "total_aa_polym_per_s_predicted": total_aa_polym_predicted,
        },
        "shapes": {
            "mrna_counts": [482],
            "length_aa": [482],
            "synth_predicted_per_s": [482],
            "synth_karr_per_s": [482],
            "ribosome_state_occupancies_3": [3],
            "n_ribosomes_bound_per_mrna": [482],
        },
        "interpretation": {
            "synth_protein_i": "N_active * elong * mRNA_i / sum_k(mRNA_k * length_k)",
            "ribosome_state_occupancies_index": ["active", "notExist", "stalled"],
            "snapshot_vs_average": "Karr's fitted s = counts_mature * decay is cell-cycle averaged; snapshot N_active is half-cycle. Multiply by ~1.5-2.0 for fair comparison.",
        },
    }
    OUT_JSON.write_text(json.dumps(out_meta, indent=2))
    np.savez_compressed(
        OUT_NPZ,
        mrna_counts=mrna_counts,
        length_aa=length_aa,
        synth_predicted_per_s=synth_predicted,
        synth_karr_per_s=karr_synth,
        ribosome_state_occupancies=state_occ,
        n_ribosomes_bound_per_mrna=n_mrnas_bound,
    )
    print(f"\n[OK] wrote {OUT_JSON.name} + {OUT_NPZ.name}")


if __name__ == "__main__":
    main()
