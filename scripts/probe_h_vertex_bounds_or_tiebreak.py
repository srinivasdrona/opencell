"""Day-42 follow-up: are Karr's bounds preventing the substitution we're making?

For each of the 17 differing external-exchange reactions, look at:
  - lb, ub at sample (s=0, t=1)
  - karr_flux value (does it sit at a bound, mid-range, or zero?)
  - oc_flux value (does it sit at a bound, mid-range, or zero?)

If karr_flux = ub or karr_flux = lb, Karr's choice is bound-forced — we
should match his bounds.

If karr_flux is interior (not at a bound), Karr's choice is a tie-break
— we should match column order / pricing tie-break.
"""
import json
import sys
from pathlib import Path

import numpy as np
import h5py
from scipy.io import loadmat
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture


def classify_at_bound(v, lb, ub, tol=1e-6):
    if abs(v - lb) < tol * max(1.0, abs(lb)) and not np.isinf(lb):
        return "AT_LB"
    if abs(v - ub) < tol * max(1.0, abs(ub)) and not np.isinf(ub):
        return "AT_UB"
    if abs(v) < tol:
        return "AT_ZERO"
    return "INTERIOR"


def main():
    sample_path = REPO / "data" / "karr_fixtures" / "matlab_ground_truth" / "metab_flux_allocated_state_s000_tick1.mat"
    fixture_path = REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
    lp_path = REPO / "data" / "karr_fixtures" / "karr_native_m1.npz"

    with h5py.File(sample_path, "r") as f:
        karr_flux = np.array(f["flux"]).ravel().astype(np.float64)
        bounds = np.array(f["bounds"]).T  # (504, 2)

    npz = np.load(lp_path, allow_pickle=False)
    S = npz["S"].astype(np.float64)
    rhs = npz["RHS"].astype(np.float64)
    c = npz["obj"].astype(np.float64)

    BIG = 1e6
    lb_clipped = np.clip(bounds[:, 0], -BIG, BIG)
    ub_clipped = np.clip(bounds[:, 1], -BIG, BIG)

    model = SimpleNamespace(S=S, RHS=rhs)
    oc_flux, _, _ = km._solve_fba_glpk(model, c=c, lb=lb_clipped, ub=ub_clipped, sense="max")

    fixture = KarrWritebackFixture.from_mat(fixture_path)
    mat = loadmat(str(fixture_path), squeeze_me=True, struct_as_record=False)
    fix = mat["data"].fixture
    sub_wids = [str(s) for s in np.asarray(fix.substrateWholeCellModelIDs).ravel()]

    # 17 differing external exchange reactions
    ext_idx = fixture.fba_idx_external
    diff = oc_flux[ext_idx] - karr_flux[ext_idx]
    differing = np.where(np.abs(diff) > 1.0)[0]  # only "real" diffs, not 1e-9 noise

    print(f"{'rxn_pos':>7s} {'fba_col':>7s} {'sub_wid':>14s} {'lb_raw':>12s} {'ub_raw':>12s} {'karr_v':>12s} {'oc_v':>12s} {'karr_status':>10s} {'oc_status':>10s}")
    print("-" * 115)

    out = []
    for pos in differing:
        fba_col = int(ext_idx[pos])
        sub_row = int(fixture.sub_idx_external[pos])
        sub_wid = sub_wids[sub_row] if sub_row < len(sub_wids) else "?"
        lb_r = float(bounds[fba_col, 0])  # raw, may be inf
        ub_r = float(bounds[fba_col, 1])
        kv = float(karr_flux[fba_col])
        ov = float(oc_flux[fba_col])

        karr_status = classify_at_bound(kv, lb_clipped[fba_col], ub_clipped[fba_col])
        oc_status = classify_at_bound(ov, lb_clipped[fba_col], ub_clipped[fba_col])

        lb_disp = f"{lb_r:.3e}" if not np.isinf(lb_r) else f"{'-inf' if lb_r < 0 else '+inf':>12s}"
        ub_disp = f"{ub_r:.3e}" if not np.isinf(ub_r) else f"{'-inf' if ub_r < 0 else '+inf':>12s}"
        print(f"{pos:>7d} {fba_col:>7d} {sub_wid:>14s} {lb_disp:>12s} {ub_disp:>12s} {kv:>12.4e} {ov:>12.4e} {karr_status:>10s} {oc_status:>10s}")
        out.append({
            "rxn_pos": int(pos), "fba_col": fba_col, "sub_row": sub_row, "sub_wid": sub_wid,
            "lb_raw": lb_r if not np.isinf(lb_r) else ("+inf" if lb_r > 0 else "-inf"),
            "ub_raw": ub_r if not np.isinf(ub_r) else ("+inf" if ub_r > 0 else "-inf"),
            "karr_flux": kv, "oc_flux": ov, "diff": ov - kv,
            "karr_status": karr_status, "oc_status": oc_status,
        })

    # Summary
    print()
    karr_status_counts = {}
    oc_status_counts = {}
    for r in out:
        karr_status_counts[r["karr_status"]] = karr_status_counts.get(r["karr_status"], 0) + 1
        oc_status_counts[r["oc_status"]] = oc_status_counts.get(r["oc_status"], 0) + 1
    print(f"Karr vertex bound-status distribution: {karr_status_counts}")
    print(f"OC   vertex bound-status distribution: {oc_status_counts}")

    out_path = REPO / "tmp" / "h_vertex_bounds_or_tiebreak.json"
    out_path.write_text(json.dumps({"differing_reactions": out,
                                    "karr_status_counts": karr_status_counts,
                                    "oc_status_counts": oc_status_counts}, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
