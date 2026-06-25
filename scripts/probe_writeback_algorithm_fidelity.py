"""Diagnose the algorithm-fidelity gap.

WIDs where my writeback gives ~0 even with Karr's exact flux, but Karr's
recorded delta is large:
  PHE (+3778), TRIOLEIN (+2247), PhePhe (-1889), TyrTyr, TRIPALMITIN, etc.

These are amino acid products + tripeptides. Are they in my index arrays?
Or does Karr have a SIXTH step I missed?
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import h5py
from scipy.io import loadmat

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture

fbf = KarrWritebackFixture.from_mat(str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat"))
model = km.load_default()
sub_ids = list(model.raw["ids"]["substrate_wcm_585"])

# Where are the "missing" WIDs?
targets = ["PHE", "TYR", "TRIOLEIN", "PhePhe", "TyrTyr", "TRIPALMITIN", "TRI_HDCEA_IN"]
print("=== Index membership audit ===")
for wid in targets:
    if wid not in sub_ids:
        print(f"  {wid}: NOT in sub_ids 585-list")
        continue
    row = sub_ids.index(wid)
    in_ext = row in fbf.sub_idx_external
    in_int = row in fbf.sub_idx_internal
    in_atp = row in fbf.sub_idx_atp_hydrolysis
    in_metab = row in fbf.metabolite_row_idx
    # metabolismNewProduction values at this row
    mnp_row = fbf.metabolism_new_production[row, :]
    print(f"  {wid:18s} (row={row:3d}): in_ext={in_ext} in_int={in_int} in_atp={in_atp} in_metab={in_metab}")
    print(f"    metabolismNewProduction[row, :]: {mnp_row} (sum={mnp_row.sum():.4e})")

# Direct comparison: load Karr's full fixture and check what else exists in evolveState
print("\n=== Look for OTHER fields that affect substrates in Metabolism.m ===")
mat = loadmat(str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat"),
              squeeze_me=True, struct_as_record=False)
fix = mat["data"].fixture
all_fields = sorted(fix._fieldnames)
print(f"Total fixture fields: {len(all_fields)}")
# Look for anything related to TRIOLEIN, PHE, tripeptide
relevant_keywords = ["aminoacyl", "tripeptide", "biomassExchange", "metabolismRecycling", 
                     "biomassExchangeFluxs", "atp_hydrolysis", "newProduction"]
for kw in relevant_keywords:
    matches = [f for f in all_fields if kw.lower() in f.lower()]
    if matches:
        print(f"  '{kw}' matches: {matches[:5]}")

# Check metabolismRecyclingProduction
if "metabolismRecyclingProduction" in fix._fieldnames:
    mrp = np.asarray(fix.metabolismRecyclingProduction)
    print(f"\nmetabolismRecyclingProduction shape: {mrp.shape}")
    print(f"  sum_abs: {np.abs(mrp).sum():.4e}")
    print(f"  nonzero count: {int((mrp != 0).sum())}")
    # Which substrates have nonzero?
    if mrp.ndim == 1:
        nz_rows = np.where(mrp != 0)[0]
        for r in nz_rows[:10]:
            print(f"  row {r} ({sub_ids[r]}): {mrp[r]}")

# Also check biomassExchangeFluxs - Karr might have additional biomass exchange logic
# Look at line 838-843 of Metabolism.m for the LP solution dispatch
