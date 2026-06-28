"""Day-42: verify whether OC's LP column order matches Karr's MATLAB column order.

Method:
  1. Load Karr's FBA S matrix directly from Metabolism_flat.mat (the runtime
     extract — preserves MATLAB's column order).
  2. Load OC's LP S matrix from karr_native_m1.npz.
  3. Compare column-by-column. If they match elementwise without permutation,
     column order is identical. If they only match after permutation, OC has
     reordered columns and the tie-break-driven vertex difference may be due
     to that reordering.

Conclusion path:
  - If columns match elementwise: column order is NOT the driver; need to
    look at starting basis or anti-cycling heuristics.
  - If columns match only under permutation: re-permute OC's LP to Karr's
    order, re-run the writeback probe, see if vertex converges.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.sparse import issparse

REPO = Path(__file__).resolve().parent.parent

def main():
    fixture_path = REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
    npz_path = REPO / "data" / "karr_fixtures" / "karr_native_m1.npz"

    # Karr's runtime S
    mat = loadmat(str(fixture_path), squeeze_me=True, struct_as_record=False)
    fix = mat["data"].fixture
    karr_S_attr = fix.fbaReactionStoichiometryMatrix
    if issparse(karr_S_attr):
        karr_S = karr_S_attr.toarray().astype(np.float64)
    else:
        karr_S = np.asarray(karr_S_attr, dtype=np.float64)
    karr_obj = np.asarray(fix.fbaObjective, dtype=np.float64).ravel()
    karr_rhs = np.asarray(fix.fbaRightHandSide, dtype=np.float64).ravel()
    print(f"Karr  S shape: {karr_S.shape}, obj shape: {karr_obj.shape}, rhs shape: {karr_rhs.shape}")

    # OC's LP
    npz = np.load(npz_path, allow_pickle=False)
    oc_S = npz["S"].astype(np.float64)
    oc_obj = npz["obj"].astype(np.float64).ravel()
    oc_rhs = npz["RHS"].astype(np.float64).ravel()
    print(f"OC    S shape: {oc_S.shape}, obj shape: {oc_obj.shape}, rhs shape: {oc_rhs.shape}")
    print(f"OC npz keys: {list(npz.files)}")
    print()

    # Direct elementwise comparison
    if karr_S.shape != oc_S.shape:
        print(f"SHAPE MISMATCH: cannot directly compare. Karr={karr_S.shape}, OC={oc_S.shape}")
        return

    s_diff = np.abs(karr_S - oc_S)
    print(f"S elementwise abs diff: max={s_diff.max():.3e}, sum={s_diff.sum():.3e}, nnz_gt_1e-12={int((s_diff > 1e-12).sum())}")
    obj_diff = np.abs(karr_obj - oc_obj)
    print(f"obj elementwise abs diff: max={obj_diff.max():.3e}, sum={obj_diff.sum():.3e}, nnz_gt_1e-12={int((obj_diff > 1e-12).sum())}")
    rhs_diff = np.abs(karr_rhs - oc_rhs)
    print(f"rhs elementwise abs diff: max={rhs_diff.max():.3e}, sum={rhs_diff.sum():.3e}, nnz_gt_1e-12={int((rhs_diff > 1e-12).sum())}")
    print()

    if s_diff.max() < 1e-12 and obj_diff.max() < 1e-12 and rhs_diff.max() < 1e-12:
        print("CONCLUSION: OC LP column order is IDENTICAL to Karr's runtime LP column order.")
        print("            Vertex divergence is NOT driven by column ordering.")
        verdict = "COLUMN_ORDER_IDENTICAL"
    else:
        # Try a permutation match: find oc_col -> karr_col mapping
        print("Elementwise mismatch detected. Searching for column permutation...")
        # For each OC column, find which Karr column matches (if any)
        mapping = []
        for j in range(oc_S.shape[1]):
            oc_col = oc_S[:, j]
            # Find matching Karr column
            matches = []
            for k in range(karr_S.shape[1]):
                if np.allclose(oc_col, karr_S[:, k], atol=1e-12):
                    matches.append(k)
            mapping.append(matches)
        unique_match = sum(1 for m in mapping if len(m) == 1)
        any_match = sum(1 for m in mapping if len(m) >= 1)
        no_match = sum(1 for m in mapping if len(m) == 0)
        print(f"Permutation search results:")
        print(f"  Unique-match cols: {unique_match}")
        print(f"  Any-match cols:    {any_match}")
        print(f"  No-match cols:     {no_match}")
        if no_match == 0 and unique_match == oc_S.shape[1]:
            perm = np.array([m[0] for m in mapping])
            is_identity = np.all(perm == np.arange(len(perm)))
            if is_identity:
                verdict = "COLUMN_ORDER_IDENTICAL"
            else:
                # Show first 20 permutation entries
                print(f"  Permutation oc_col -> karr_col (first 30 entries): {perm[:30].tolist()}")
                print(f"  Non-identity at positions: {[(i, p) for i, p in enumerate(perm[:50]) if i != p][:20]}")
                verdict = "COLUMN_ORDER_PERMUTED"
        else:
            verdict = "NON_TRIVIAL_DIFF"

    print(f"\nVERDICT: {verdict}")

    out = {
        "karr_S_shape": list(karr_S.shape),
        "oc_S_shape": list(oc_S.shape),
        "s_max_abs_diff": float(s_diff.max()),
        "obj_max_abs_diff": float(obj_diff.max()),
        "rhs_max_abs_diff": float(rhs_diff.max()),
        "verdict": verdict,
    }
    out_path = REPO / "tmp" / "h_column_order_check.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
