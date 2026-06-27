"""Step 3: name the high-diff reactions and identify what they do."""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km

GT_PATH = REPO / "data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat"

with h5py.File(GT_PATH, "r") as h:
    flux_karr = np.asarray(h["flux"][()], dtype=np.float64).reshape(-1)
    bounds_karr = np.asarray(h["bounds"][()], dtype=np.float64)
if bounds_karr.shape == (2, 504):
    bounds_karr = bounds_karr.T

model = km.load_default()
v_oc, _ = km.solve_fba(
    model, use_full_objective=True, sense="max", big=1e6,
    lb_override=bounds_karr[:, 0], ub_override=bounds_karr[:, 1],
    solver="glpk",
)

S = model.S
fba_col_to_rxn = model.raw["ids"]["fba_col_to_reaction_wcm"]
rxn_names = model.raw["ids"]["reaction_names_645"]
rxn_ids_645 = model.raw["ids"]["reaction_wcm_645"]

# Indices in the 645-WCM-reaction space
# fba_col_to_rxn[i] gives the WCM reaction ID (string or None) for FBA col i
def get_rxn_name(fba_col):
    rxn_id = fba_col_to_rxn[fba_col]
    if rxn_id is None:
        # Exchange or internal reaction (no biological name)
        if fba_col < 336:
            return "(metabolic, unmapped)"
        elif fba_col < 460:
            return "(external exchange)"
        else:
            return "(internal exchange)"
    if rxn_id in rxn_ids_645:
        idx = rxn_ids_645.index(rxn_id)
        return f"{rxn_id}: {rxn_names[idx]}"
    return f"{rxn_id}: (no name)"

# Find reactions where |OC - Karr| flux is largest
d = v_oc - flux_karr
order = np.argsort(-np.abs(d))

print("Top 30 differing reactions at sample (0,1):")
print(f"{'fba_col':>7s}  {'|diff|':>10s}  {'OC':>11s}  {'Karr':>11s}  {'lb':>10s}  {'ub':>10s}  Reaction")
print("-" * 130)
for r in order[:30]:
    name = get_rxn_name(r)
    print(f"{r:7d}  {abs(d[r]):10.2e}  {v_oc[r]:+11.2e}  {flux_karr[r]:+11.2e}  "
          f"{bounds_karr[r,0]:+10.2e}  {bounds_karr[r,1]:+10.2e}  {name[:80]}")

print()
print("="*100)
print("Now check the dipeptide reaction story specifically.")
print("="*100)

# Search reaction names for dipeptide and lipid keywords
keywords = ["TrpTrp", "TyrTyr", "PhePhe", "dipeptide", "TRP", "TYR", "PHE",
            "OCDCEA", "TRIOLEIN", "HDCA", "TRIPALMITIN", "HDCEA",
            "H2O2", "peroxide", "O2", "oxygen"]

for kw in keywords:
    matches = []
    for fba_col in range(504):
        rxn_id = fba_col_to_rxn[fba_col]
        if rxn_id is None:
            continue
        if rxn_id in rxn_ids_645:
            idx = rxn_ids_645.index(rxn_id)
            name = rxn_names[idx]
            if kw.lower() in name.lower() or kw == rxn_id:
                matches.append((fba_col, rxn_id, name))
    if matches:
        print(f"\nKeyword '{kw}' ({len(matches)} matches):")
        for fc, rxn_id, name in matches[:5]:
            print(f"  fba_col={fc:4d}  rxn={rxn_id:18s}  flux: OC={v_oc[fc]:+.2e}  Karr={flux_karr[fc]:+.2e}  bounds=[{bounds_karr[fc,0]:+.1e}, {bounds_karr[fc,1]:+.1e}]")
            if len(name) > 100:
                print(f"    Name: {name[:100]}...")
            else:
                print(f"    Name: {name}")
