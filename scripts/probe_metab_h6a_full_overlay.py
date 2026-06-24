"""Test H6a refined: only 24 of 585 cytosol slots get updated from shared substrates.

This means compute_bounds runs with STALE extracellular/membrane values + 561 stale
cytosol values. Test by manually overlaying ALL 585 substrate values and re-running
compute_bounds.

If the LP flux distribution moves toward Karr's, this is the root cause.
"""
import sys
from pathlib import Path
import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "vivarium"))

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb
from opencell.vivarium.karr_metabolism import _KARR_DEMAND_KEYS

print(f"_KARR_DEMAND_KEYS count: {len(_KARR_DEMAND_KEYS)}")
print(f"  Keys: {_KARR_DEMAND_KEYS[:10]}...")
print()

model = km.load_default()
dyn = cfb.load_default_dynamics()
sub_ids = list(model.raw["ids"]["substrate_wcm_585"])

# Load Karr tick-0 pre
trace_path = REPO / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s000" / "Metabolism_100ticks.mat"
with h5py.File(trace_path, "r") as h:
    def get3d(p, t):
        ds = h[p]
        ref = ds[0, t] if ds.shape[0] == 1 else ds[t, 0]
        return np.asarray(h[ref][()], dtype=np.float64)
    karr_pre = get3d("states_before/substrates", 0).T   # (585, 3)
    karr_enz = get3d("states_before/enzymes", 0).ravel()

# What's the diff between fixture initial and Karr tick-0?
diff = karr_pre - dyn.substrates_snapshot
print(f"=== Where does dyn.substrates_snapshot differ from Karr tick-0? ===")
print(f"Per-compartment sum_abs of diff:")
for c, name in enumerate(["cytosol", "extracellular", "membrane"]):
    print(f"  {name}: sum_abs={np.abs(diff[:, c]).sum():.0f}, "
          f"n_diff(>1)={int((np.abs(diff[:, c]) > 1).sum())}")
# Top 10 diffs
print(f"\nTop 10 diffs (Karr - fixture):")
flat_idx = np.argsort(-np.abs(diff).ravel())[:10]
for fi in flat_idx:
    r, c = np.unravel_index(fi, diff.shape)
    cname = ["cyt", "ext", "mem"][c]
    print(f"  {sub_ids[r]}[{cname}]: Karr={karr_pre[r,c]:.0f}, "
          f"fixture={dyn.substrates_snapshot[r,c]:.0f}, diff={diff[r,c]:+.0f}")

# Now test: run compute_bounds with FULL Karr pre vs fixture-only
print()
print("="*70)
print("Test: compute_bounds with Karr-full pre vs fixture-only pre")
print("="*70)

fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(float)
enz_to_use = karr_enz.copy()  # use karr enzymes either way

for label, sub_state in [("FIXTURE (current)", dyn.substrates_snapshot.copy()),
                          ("KARR-FULL OVERLAY", karr_pre.copy())]:
    bounds = cfb.compute_bounds(
        substrates=sub_state, enzymes=enz_to_use,
        cell_dry_mass=dyn.cell_dry_mass, step_size_sec=dyn.step_size_sec,
        catalysis=model.catalysis, enz_bounds=model.enz_bounds,
        fba_reaction_bounds=fba_reaction_bounds, dyn=dyn,
        apply_protein_bounds=False,
    )
    v_504, info = km.solve_fba(
        model, use_full_objective=True, sense="max",
        lb_override=bounds[:, 0], ub_override=bounds[:, 1],
    )
    print(f"\n--- {label} ---")
    print(f"  growth_per_s: {info['biomass_flux_per_s']:.6e}")
    # Check fatty acid fluxes
    from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture
    fix2 = KarrWritebackFixture.from_mat(str(REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"))
    targets = [("HDCA", 300), ("HDCEA", 301), ("OCDCEA", 439)]
    for wid, row in targets:
        k_arr = np.where(fix2.sub_idx_external == row)[0]
        if len(k_arr) == 0:
            continue
        k = int(k_arr[0])
        col = int(fix2.fba_idx_external[k])
        print(f"  {wid} (col={col}): flux={v_504[col]:+.2f}, "
              f"lb={bounds[col, 0]:+.2f}, ub={bounds[col, 1]:+.2f}")
    # How many exchange reactions at bounds?
    ext_cols = fix2.fba_idx_external
    at_ub = (np.abs(v_504[ext_cols] - bounds[ext_cols, 1]) < 1e-3).sum()
    at_lb = (np.abs(v_504[ext_cols] - bounds[ext_cols, 0]) < 1e-3).sum()
    zero = (np.abs(v_504[ext_cols]) < 1e-6).sum()
    print(f"  External exchanges: at_lb={at_lb}, at_ub={at_ub}, zero={zero}, interior={124-at_lb-at_ub}")
