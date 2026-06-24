"""Direct check: what does OC's FBA v_504 contain at the columns for
HDCEA/HDCA/OCDCEA exchange reactions?
"""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "vivarium"))

from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture
from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb

fix = KarrWritebackFixture.from_mat(str(REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"))
model = km.load_default()
sub_ids = list(model.raw["ids"]["substrate_wcm_585"])

# Load Karr pre-state
trace_path = REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    def get3d(p, t):
        ds = h[p]
        ref = ds[0, t] if ds.shape[0] == 1 else ds[t, 0]
        return np.asarray(h[ref][()], dtype=np.float64)
    karr_pre = get3d("states_before/substrates", 0).T
    enz_before = get3d("states_before/enzymes", 0).ravel()

dyn = cfb.load_default_dynamics()

# Set dyn substrates/enzymes to Karr's tick-0 pre-state
sub_state = karr_pre.copy()
enz_state = enz_before.copy() if len(enz_before) == len(dyn.enzymes_snapshot) else dyn.enzymes_snapshot.copy()

fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(float)

bounds = cfb.compute_bounds(
    substrates=sub_state, enzymes=enz_state,
    cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
    catalysis=model.catalysis, enz_bounds=model.enz_bounds,
    fba_reaction_bounds=fba_reaction_bounds, dyn=dyn,
    apply_protein_bounds=False,
)
v_504, info = km.solve_fba(
    model, use_full_objective=True, sense="max",
    lb_override=bounds[:, 0], ub_override=bounds[:, 1],
)
print(f"FBA solved: status={info['status']}, growth_per_s={info['biomass_flux_per_s']:.4e}")

# Compare flux at the columns for our problem WIDs
print(f"\n=== v_504 at the 3 problem fatty-acid exchange columns ===")
targets = [("HDCA", 300), ("HDCEA", 301), ("OCDCEA", 439)]
for wid, row in targets:
    k_arr = np.where(fix.sub_idx_external == row)[0]
    k = int(k_arr[0])
    fba_col = int(fix.fba_idx_external[k])
    flux = v_504[fba_col]
    dyn_lb = bounds[fba_col, 0]
    dyn_ub = bounds[fba_col, 1]
    static_lb = model.lb[fba_col]
    static_ub = model.ub[fba_col]
    print(f"  {wid} (row={row}, fba_col={fba_col}):")
    print(f"    v_504={flux:+.4f}")
    print(f"    dynamic bounds: lb={dyn_lb:+.4f}, ub={dyn_ub:+.4f}")
    print(f"    static  bounds: lb={static_lb:+.2e}, ub={static_ub:+.2e}")
    # Karr's expected flux: delta_extracellular = -stochRound(flux * step) → flux = -delta_ext
    karr_ext_delta = {"HDCA": -7918, "HDCEA": -7919, "OCDCEA": -6741}[wid]
    expected_flux = -karr_ext_delta
    print(f"    KARR EXPECTED FLUX: {expected_flux:+d}")
    print(f"    OC IS {'AT LB' if abs(flux - dyn_lb) < 1e-3 else 'AT UB' if abs(flux - dyn_ub) < 1e-3 else 'INTERIOR'}")

# Also: how many of the 124 external exchange fluxes are at their dynamic bounds?
print(f"\n=== Bound-saturation across all 124 external exchange reactions ===")
ext_cols = fix.fba_idx_external
ext_flux = v_504[ext_cols]
ext_lb = bounds[ext_cols, 0]
ext_ub = bounds[ext_cols, 1]
at_lb = (np.abs(ext_flux - ext_lb) < 1e-3).sum()
at_ub = (np.abs(ext_flux - ext_ub) < 1e-3).sum()
zero = (np.abs(ext_flux) < 1e-6).sum()
print(f"  At lower bound: {at_lb}/124")
print(f"  At upper bound: {at_ub}/124")
print(f"  Exactly zero:   {zero}/124")
print(f"  Interior flux:  {124 - at_lb - at_ub}/124")

# Where do the ±1000 caps come from?
print(f"\n=== ±1000 fluxes: which columns hit them? ===")
mask = (np.abs(ext_flux) > 999) & (np.abs(ext_flux) < 1001)
hits = np.where(mask)[0]
print(f"Columns with |flux| in [999, 1001]: {len(hits)} of 124")
for h in hits[:10]:
    row = int(fix.sub_idx_external[h])
    wid = sub_ids[row]
    print(f"  {wid} (row={row}, fba_col={int(ext_cols[h])}): flux={ext_flux[h]:+.2f}, "
          f"lb={ext_lb[h]:+.2f}, ub={ext_ub[h]:+.2f}")
