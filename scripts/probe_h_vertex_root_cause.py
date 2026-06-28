"""Day-42 deep probe: WHY do OC and Karr pick different LP vertices?

Examines the 17 external-exchange flux differences from probe_h_writeback_oc_vs_karr_flux.
For each diff:
  1. Look up the reaction WID and the substrate WID it exchanges.
  2. Check if differing reactions are alternative routes for the SAME metabolite.
  3. Inspect S-matrix structure around the difference.
  4. Report which mechanism dominates: routing-equivalence vs alternative-precursor.

Goal: tell us whether the vertex difference is:
  A. Substitutable routes for the same metabolite (mitigable via bound tightening
     or column-ordering choice)
  B. Genuinely alternative biology (different precursors consumed for same biomass,
     would require a Karr-vertex-specific oracle).
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


def main():
    sample_path = REPO / "data" / "karr_fixtures" / "matlab_ground_truth" / "metab_flux_allocated_state_s000_tick1.mat"
    fixture_path = REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
    lp_path = REPO / "data" / "karr_fixtures" / "karr_native_m1.npz"

    with h5py.File(sample_path, "r") as f:
        karr_flux = np.array(f["flux"]).ravel().astype(np.float64)
        bounds = np.array(f["bounds"]).T

    npz = np.load(lp_path, allow_pickle=False)
    S = npz["S"].astype(np.float64)  # (376, 504) FBA S matrix
    rhs = npz["RHS"].astype(np.float64)
    c = npz["obj"].astype(np.float64)
    print(f"S shape: {S.shape}  (rows=FBA metabolites, cols=FBA reactions)")

    BIG = 1e6
    lb = np.clip(bounds[:, 0], -BIG, BIG)
    ub = np.clip(bounds[:, 1], -BIG, BIG)

    # Solve OC's LP with production config
    model = SimpleNamespace(S=S, RHS=rhs)
    oc_flux, oc_obj, status = km._solve_fba_glpk(model, c=c, lb=lb, ub=ub, sense="max")

    fixture = KarrWritebackFixture.from_mat(fixture_path)

    # Load reaction WID strings + substrate WID strings from fixture
    mat = loadmat(str(fixture_path), squeeze_me=True, struct_as_record=False)
    fix = mat["data"].fixture
    fba_wids = [str(s) for s in np.asarray(fix.reactionWholeCellModelIDs).ravel()]
    sub_wids = [str(s) for s in np.asarray(fix.substrateWholeCellModelIDs).ravel()]
    print(f"  {len(fba_wids)} (model) reactions, {len(sub_wids)} substrates")
    # Also try to find an fbaReaction-indexed list. The 504-element FBA reactions are a permutation/subset of model reactions.
    try:
        fba_in_model = np.asarray(fix.reactionIndexs_fba).astype(int) - 1
        print(f"  reactionIndexs_fba present, len={len(fba_in_model)}")
        # If we have it, fba_col -> model_col -> wid
        def fba_col_to_wid(fba_col):
            if 0 <= fba_col < len(fba_in_model):
                m = fba_in_model[fba_col]
                if 0 <= m < len(fba_wids):
                    return fba_wids[m]
            return f"fba_col_{fba_col}"
    except AttributeError:
        # Maybe the fixture has fbaReactionWholeCellModelIDs under a different attribute path
        print(f"  WARN: no reactionIndexs_fba; falling back to fba_col index as label")
        def fba_col_to_wid(fba_col):
            return f"fba_col_{fba_col}"

    # 17 external exchange reactions with flux diff > 1e-9
    ext_idx = fixture.fba_idx_external
    flux_diff_ext = oc_flux[ext_idx] - karr_flux[ext_idx]
    nz_ext_mask = np.abs(flux_diff_ext) > 1e-9
    differing_ext_positions = np.where(nz_ext_mask)[0]
    print(f"\n  {len(differing_ext_positions)} of {len(ext_idx)} external exchange reactions differ")

    # For each differing exchange reaction:
    #  - reaction WID (e.g. 'EX_glc__D_e')
    #  - which substrate row it exchanges (sub_idx_external[i])
    #  - karr flux value, oc flux value, diff
    print()
    print("Per-differing external exchange reaction:")
    print(f"{'rxn_pos':>8s} {'fba_col':>8s} {'rxn_wid':>20s} {'sub_row':>8s} {'sub_wid':>14s} {'karr_flux':>14s} {'oc_flux':>14s} {'diff':>14s}")
    findings = []
    for pos in differing_ext_positions:
        fba_col = int(ext_idx[pos])
        sub_row = int(fixture.sub_idx_external[pos])
        rxn_wid = fba_col_to_wid(fba_col)
        sub_wid = sub_wids[sub_row] if sub_row < len(sub_wids) else "?"
        kv = karr_flux[fba_col]
        ov = oc_flux[fba_col]
        d = ov - kv
        print(f"{pos:>8d} {fba_col:>8d} {rxn_wid:>20s} {sub_row:>8d} {sub_wid:>14s} {kv:>14.4e} {ov:>14.4e} {d:>14.4e}")
        findings.append({
            "rxn_pos": int(pos), "fba_col": fba_col, "rxn_wid": rxn_wid,
            "sub_row": sub_row, "sub_wid": sub_wid,
            "karr_flux": float(kv), "oc_flux": float(ov), "diff": float(d),
        })

    # For each differing exchange reaction, look at which S column has nonzero entries.
    # If multiple exchange reactions touch the SAME substrate row, that's a routing
    # equivalence — they're alternative routes.
    print()
    print("S-column structure for differing exchanges:")
    sub_to_rxns = {}
    for f in findings:
        col = f["fba_col"]
        col_nz_rows = np.where(np.abs(S[:, col]) > 1e-12)[0]
        sign = float(np.sign(S[col_nz_rows[0], col])) if len(col_nz_rows) else 0
        print(f"  rxn {f['rxn_wid']:<18s} (col {col}): touches FBA-S rows {col_nz_rows.tolist()}, primary sign {sign:+.0f}")
        for r in col_nz_rows:
            sub_to_rxns.setdefault(int(r), []).append((f["rxn_wid"], col, float(S[r, col])))

    # Find substrate rows touched by multiple differing reactions
    multi_touched = {r: rxns for r, rxns in sub_to_rxns.items() if len(rxns) > 1}
    print()
    print(f"Substrate (FBA-S row) indices touched by multiple differing exchange reactions: {sorted(multi_touched.keys())}")
    for r, rxns in sorted(multi_touched.items()):
        print(f"  FBA-S row {r}: {[(w, c, s) for w, c, s in rxns]}")

    # Look at the substrate writeback row WIDs for the top mismatches
    top_writeback_wids = [541, 469, 542, 470, 439, 300, 536, 537, 298, 420, 557, 18, 29, 560, 297]
    print()
    print("Top-mismatch substrate row WIDs (from previous probe):")
    for r in top_writeback_wids:
        wid = sub_wids[r] if r < len(sub_wids) else "?"
        print(f"  row {r}: {wid}")

    out = {
        "differing_exchange_count": int(len(differing_ext_positions)),
        "total_exchange_count": int(len(ext_idx)),
        "differing_exchanges": findings,
        "multi_touched_S_rows": {
            str(r): [{"rxn_wid": w, "fba_col": c, "stoich": s} for w, c, s in rxns]
            for r, rxns in sorted(multi_touched.items())
        },
        "top_mismatch_substrate_wids": {
            str(r): (sub_wids[r] if r < len(sub_wids) else "?")
            for r in top_writeback_wids
        },
    }
    out_path = REPO / "tmp" / "h_vertex_root_cause.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
