"""Quick sanity check: GLPK route through new solve_fba API."""
import numpy as np
from opencell.m1 import karr_metabolism as km

model = km.load_default()

v_h, info_h = km.solve_fba(model, use_full_objective=True, sense="max")
print(f"HiGHS growth={info_h['biomass_flux_per_s']:.6e}  solver={info_h['solver']}")

v_g, info_g = km.solve_fba(model, use_full_objective=True, sense="max", solver="glpk", big=1e6)
print(f"GLPK  growth={info_g['biomass_flux_per_s']:.6e}  solver={info_g['solver']}")

lb = np.full(504, -1e6)
ub = np.full(504, 1e6)
v_o, info_o = km.solve_fba(model, lb_override=lb, ub_override=ub, big=1e6, solver="glpk")
print(f"GLPK+ov growth={info_o['biomass_flux_per_s']:.6e}")

# Should be identical with HiGHS at same bounds
v_oh, info_oh = km.solve_fba(model, lb_override=lb, ub_override=ub, big=1e6, solver="highs")
print(f"HiGHS+ov growth={info_oh['biomass_flux_per_s']:.6e}")

# Confirm GLPK API rejects bad arg
try:
    km.solve_fba(model, solver="foo")
except ValueError as e:
    print(f"Bad-solver guard: OK ({e})")
