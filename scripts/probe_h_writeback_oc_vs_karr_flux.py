"""Day-42 follow-up: writeback fed OC's flux vs writeback fed Karr's flux.

Day-41 said: flux differences live in null(S), so substrate-deltas are
unchanged. But the writeback doesn't compute S*v — it reads specific
subsets of v (fba_ext_idx, fba_int_idx, biomass_col). Test directly:

  delta_A = writeback(Karr_flux)
  delta_B = writeback(OC_flux_with_pricing_STD)
  diff = ||delta_A - delta_B||_1

If diff is small (~50 L1 RNG noise), then OC's flux matches Karr's at the
exchange/biomass indices, and the W1=161 gap is elsewhere.

If diff is large, the W1 gap comes from OC's flux differing at exchange
indices — even though it agrees on S*v.
"""
import json
import sys
from pathlib import Path

import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807
from types import SimpleNamespace


class _DetRng:
    def stochastic_round(self, values):
        return np.rint(np.asarray(values, dtype=np.float64)).astype(np.int64)


def main():
    sample_path = REPO / "data" / "karr_fixtures" / "matlab_ground_truth" / "metab_flux_allocated_state_s000_tick1.mat"
    fixture_path = REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
    lp_path = REPO / "data" / "karr_fixtures" / "karr_native_m1.npz"

    # Karr ground truth
    with h5py.File(sample_path, "r") as f:
        karr_flux = np.array(f["flux"]).ravel().astype(np.float64)
        karr_growth = float(np.array(f["growth"]).ravel()[0])
        pre_sub = np.array(f["pre_sub"]).T  # (585, 3)
        karr_delta = np.array(f["delta"]).T  # (585, 3)
        bounds = np.array(f["bounds"]).T  # (504, 2)

    # OC LP fixture
    npz = np.load(lp_path, allow_pickle=False)
    S = npz["S"].astype(np.float64)
    rhs = npz["RHS"].astype(np.float64)
    c = npz["obj"].astype(np.float64)

    BIG = 1e6
    lb = np.clip(bounds[:, 0], -BIG, BIG)
    ub = np.clip(bounds[:, 1], -BIG, BIG)

    # Solve OC LP with current production config (pricing=STD)
    model = SimpleNamespace(S=S, RHS=rhs)
    oc_flux, oc_obj, status = km._solve_fba_glpk(model, c=c, lb=lb, ub=ub, sense="max")
    oc_growth = float(oc_obj)  # objective value at this LP IS the biomass coefficient * growth

    # Actually growth is fluxs[biomass_col]; find biomass col from objective vector
    biomass_col = int(np.argmax(np.abs(c)))
    oc_growth_via_biomass = float(oc_flux[biomass_col])

    fixture = KarrWritebackFixture.from_mat(fixture_path)
    step = fixture.step_size_sec

    print(f"Karr flux: shape={karr_flux.shape}, L1={np.abs(karr_flux).sum():.4e}, growth={karr_growth:.6e}")
    print(f"  OC flux: shape={oc_flux.shape}, L1={np.abs(oc_flux).sum():.4e}, growth(via_obj)={oc_growth:.6e}, growth(via_biomass_col[{biomass_col}])={oc_growth_via_biomass:.6e}")
    print(f"  Flux L1 diff (full): {np.abs(oc_flux - karr_flux).sum():.4e}")
    print()

    # Flux diff at the EXCHANGE indices
    ext_idx = fixture.fba_idx_external
    int_idx = fixture.fba_idx_internal
    flux_diff_ext = np.abs(oc_flux[ext_idx] - karr_flux[ext_idx])
    flux_diff_int = np.abs(oc_flux[int_idx] - karr_flux[int_idx])
    flux_diff_biomass = abs(oc_flux[biomass_col] - karr_flux[biomass_col])
    other_mask = np.ones(504, dtype=bool)
    other_mask[ext_idx] = False
    other_mask[int_idx] = False
    other_mask[biomass_col] = False
    flux_diff_other = np.abs(oc_flux[other_mask] - karr_flux[other_mask])

    print("Flux diff decomposition (OC pricing=STD vs Karr):")
    print(f"  external exchange (124 cols):  L1={flux_diff_ext.sum():.4e}  Linf={flux_diff_ext.max():.4e}  nnz_gt_1e-9={int((flux_diff_ext > 1e-9).sum())}")
    print(f"  internal exchange (42 cols):   L1={flux_diff_int.sum():.4e}  Linf={flux_diff_int.max():.4e}  nnz_gt_1e-9={int((flux_diff_int > 1e-9).sum())}")
    print(f"  biomass col {biomass_col}:                   diff={flux_diff_biomass:.4e}")
    print(f"  all other cols ({int(other_mask.sum())}):           L1={flux_diff_other.sum():.4e}  Linf={flux_diff_other.max():.4e}  nnz_gt_1e-9={int((flux_diff_other > 1e-9).sum())}")
    print()

    # Run writeback with each flux (deterministic, isolates algorithm + flux choice)
    rng_a = _DetRng()
    delta_using_karr = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub.copy(), v_504=karr_flux, growth_per_s=karr_growth,
        fixture=fixture, rng=rng_a, step_size_sec=step,
    )
    rng_b = _DetRng()
    delta_using_oc = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub.copy(), v_504=oc_flux, growth_per_s=oc_growth_via_biomass,
        fixture=fixture, rng=rng_b, step_size_sec=step,
    )

    # Compare each to Karr's recorded delta
    def stats(label, oc, karr):
        diff = oc.astype(np.int64) - karr.astype(np.int64)
        return {
            "label": label,
            "oc_l1": int(np.abs(oc).sum()),
            "diff_vs_karr_l1": int(np.abs(diff).sum()),
            "diff_vs_karr_linf": int(np.abs(diff).max()),
            "diff_vs_karr_nnz": int(np.sum(diff != 0)),
        }

    a = stats("writeback(Karr_flux)", delta_using_karr, karr_delta)
    b = stats("writeback(OC_flux STD)", delta_using_oc, karr_delta)
    cross_diff = (delta_using_oc - delta_using_karr).astype(np.int64)

    print("Writeback outputs vs Karr's recorded delta:")
    print(f"  Karr recorded delta L1:                 {int(np.abs(karr_delta).sum())}")
    for r in [a, b]:
        print(f"  {r['label']:<35s} OC_L1={r['oc_l1']:>7d}  diff_vs_Karr_L1={r['diff_vs_karr_l1']:>7d}  Linf={r['diff_vs_karr_linf']:>4d}  nnz={r['diff_vs_karr_nnz']:>4d}")
    print()
    print(f"Cross-diff writeback(OC) - writeback(Karr):")
    print(f"  L1={int(np.abs(cross_diff).sum())}  Linf={int(np.abs(cross_diff).max())}  nnz={int(np.sum(cross_diff != 0))}")
    print(f"  per-compartment L1: {[int(np.abs(cross_diff[:, ci]).sum()) for ci in range(3)]}")

    # Where does the OC-vs-Karr writeback diff live? Top WIDs.
    abs_cross = np.abs(cross_diff).sum(axis=1)
    top = np.argsort(-abs_cross)[:15]
    print()
    print("Top-15 per-WID writeback diff (OC pricing=STD vs Karr-flux baseline):")
    print(f"{'wid_row':>10s} {'cross_diff':>30s} {'oc_using_OC':>30s} {'oc_using_Karr':>30s}")
    for idx in top:
        if abs_cross[idx] == 0:
            break
        print(f"{idx:>10d} {str(cross_diff[idx, :].tolist()):>30s} {str(delta_using_oc[idx, :].astype(int).tolist()):>30s} {str(delta_using_karr[idx, :].astype(int).tolist()):>30s}")

    out_path = REPO / "tmp" / "h_writeback_oc_vs_karr_flux.json"
    out = {
        "sample": {"seed": 0, "tick": 1},
        "lp_solver_status": status,
        "karr_growth": karr_growth,
        "oc_growth_via_obj": oc_growth,
        "oc_growth_via_biomass_col": oc_growth_via_biomass,
        "biomass_col": biomass_col,
        "flux_diff": {
            "full_l1": float(np.abs(oc_flux - karr_flux).sum()),
            "external_exchange_l1": float(flux_diff_ext.sum()),
            "external_exchange_linf": float(flux_diff_ext.max()),
            "external_exchange_nnz_gt_1e_9": int((flux_diff_ext > 1e-9).sum()),
            "internal_exchange_l1": float(flux_diff_int.sum()),
            "internal_exchange_linf": float(flux_diff_int.max()),
            "internal_exchange_nnz_gt_1e_9": int((flux_diff_int > 1e-9).sum()),
            "biomass_col_diff": float(flux_diff_biomass),
            "other_l1": float(flux_diff_other.sum()),
            "other_linf": float(flux_diff_other.max()),
            "other_nnz_gt_1e_9": int((flux_diff_other > 1e-9).sum()),
        },
        "writeback_vs_karr_recorded": [a, b],
        "cross_diff": {
            "l1": int(np.abs(cross_diff).sum()),
            "linf": int(np.abs(cross_diff).max()),
            "nnz": int(np.sum(cross_diff != 0)),
            "per_compartment_l1": [int(np.abs(cross_diff[:, ci]).sum()) for ci in range(3)],
        },
        "top15_wid_cross_diff": [
            {"wid_row": int(i), "cross_diff": cross_diff[i, :].tolist(),
             "writeback_using_OC_flux": delta_using_oc[i, :].astype(int).tolist(),
             "writeback_using_Karr_flux": delta_using_karr[i, :].astype(int).tolist()}
            for i in top if abs_cross[i] > 0
        ],
    }
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
