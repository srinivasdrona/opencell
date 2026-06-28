"""Day-42 probe (a): epsilon-objective penalty to break LP tie on substitution pairs.

Two modes:
  a-fit:        epsilon penalties derived from Karr's flux signal (upper bound
                of what objective perturbation can achieve)
  a-principled: epsilon penalties from biological parsimony priors only
                (prefer free AA over dipeptide; no prior on lipid pairs)

For each mode, solve LP with epsilon=1e-9 perturbation on the 8 substitution-pair
columns, then run writeback. Compare delta vs Karr's recorded delta.

Headline: did epsilon close (a) the flux exchange-subset L1, (b) the writeback
delta L1?
"""
import json
import sys
from pathlib import Path

import numpy as np
import h5py
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from opencell.m1 import karr_metabolism as km
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
)


class _DetRng:
    def stochastic_round(self, values):
        return np.rint(np.asarray(values, dtype=np.float64)).astype(np.int64)


# Substitution-pair columns (from probe_h_vertex_root_cause.py)
PAIR_COLS = {
    "HDCA": 393,
    "OCDCEA": 422,
    "PHE": 423,
    "PhePhe": 424,
    "TRIOLEIN": 444,
    "TRIPALMITIN": 445,
    "TRP": 449,
    "TrpTrp": 450,
}


def build_epsilon_penalties_fit_to_karr(c_base, karr_flux, epsilon=1e-9):
    """Penalty signs derived from Karr's flux: push OC's v[j] toward Karr's v[j]."""
    c = c_base.copy()
    # Want OC v[j] LARGER -> add +epsilon
    # Want OC v[j] SMALLER -> add -epsilon
    pushes = {}
    for name, col in PAIR_COLS.items():
        kv = karr_flux[col]
        # If Karr's flux is more positive than we'd default to, push positive (encourage larger)
        # If Karr's flux is more negative, push negative
        # Heuristic: sign(karr_flux) * epsilon, with magnitude=1 unit
        # Actually we want to nudge toward kv:
        # If kv > 0: prefer v[j] positive. coef += +eps
        # If kv < 0: prefer v[j] negative. coef += -eps  (so maximizing c'v rewards more-negative v)
        # If kv ~ 0: discourage motion either way. Use small penalty on absolute size. But LP doesn't do |v|.
        #   Simplest: skip if kv ~ 0.
        if abs(kv) < 1e-3:
            push = 0.0
        else:
            push = epsilon * np.sign(kv)
        c[col] += push
        pushes[name] = (col, float(kv), float(push))
    return c, pushes


def build_epsilon_penalties_principled(c_base, epsilon=1e-9):
    """Penalty signs from biological parsimony only: prefer free monomers
    over dipeptides; no prior on lipid pairs (HDCA/OCDCEA/TRIOLEIN/TRIPALMITIN)."""
    c = c_base.copy()
    # For PHE vs PhePhe pair: prefer PHE import (negative flux). add -eps to c[PHE].
    # For TRP vs TrpTrp pair: prefer TRP (but Karr has TRP=0!). So discourage TrpTrp import.
    # Simplest: penalize dipeptide imports. Dipeptide cols are PhePhe and TrpTrp.
    # If v[PhePhe] is import (negative), discourage by making large positive flux more attractive.
    # Equivalently: add +eps to c[PhePhe] so maximizing rewards larger v (less negative -> less import).
    pushes = {}
    c[PAIR_COLS["PhePhe"]] += epsilon
    pushes["PhePhe"] = (PAIR_COLS["PhePhe"], None, epsilon)
    c[PAIR_COLS["TrpTrp"]] += epsilon
    pushes["TrpTrp"] = (PAIR_COLS["TrpTrp"], None, epsilon)
    return c, pushes


def main():
    sample_path = REPO / "data" / "karr_fixtures" / "matlab_ground_truth" / "metab_flux_allocated_state_s000_tick1.mat"
    fixture_path = REPO / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
    lp_path = REPO / "data" / "karr_fixtures" / "karr_native_m1.npz"

    with h5py.File(sample_path, "r") as f:
        karr_flux = np.array(f["flux"]).ravel().astype(np.float64)
        karr_growth = float(np.array(f["growth"]).ravel()[0])
        pre_sub = np.array(f["pre_sub"]).T
        karr_delta = np.array(f["delta"]).T
        bounds = np.array(f["bounds"]).T

    npz = np.load(lp_path, allow_pickle=False)
    S = npz["S"].astype(np.float64)
    rhs = npz["RHS"].astype(np.float64)
    c_base = npz["obj"].astype(np.float64)

    BIG = 1e6
    lb = np.clip(bounds[:, 0], -BIG, BIG)
    ub = np.clip(bounds[:, 1], -BIG, BIG)

    fixture = KarrWritebackFixture.from_mat(fixture_path)
    model = SimpleNamespace(S=S, RHS=rhs)
    ext_idx = fixture.fba_idx_external
    int_idx = fixture.fba_idx_internal

    def solve_and_writeback(c, label):
        oc_flux, oc_obj, status = km._solve_fba_glpk(model, c=c, lb=lb, ub=ub, sense="max")
        biomass_col = int(np.argmax(np.abs(c_base)))
        oc_growth = float(oc_flux[biomass_col])
        rng = _DetRng()
        oc_delta = apply_karr_substrate_writeback(
            pre_state_585x3=pre_sub.copy(),
            v_504=oc_flux, growth_per_s=oc_growth,
            fixture=fixture, rng=rng,
            step_size_sec=fixture.step_size_sec,
        )
        # Diagnostics
        full_l1_vs_karr = float(np.abs(oc_flux - karr_flux).sum())
        ext_l1_vs_karr = float(np.abs(oc_flux[ext_idx] - karr_flux[ext_idx]).sum())
        int_l1_vs_karr = float(np.abs(oc_flux[int_idx] - karr_flux[int_idx]).sum())
        delta_l1_vs_karr = int(np.abs(oc_delta - karr_delta.astype(np.int64)).sum())
        # Flux at the 8 substitution-pair cols
        pair_flux = {name: float(oc_flux[col]) for name, col in PAIR_COLS.items()}
        return {
            "label": label,
            "lp_obj": oc_obj,
            "lp_status": status,
            "biomass_growth": oc_growth,
            "full_flux_l1_vs_karr": full_l1_vs_karr,
            "ext_flux_l1_vs_karr": ext_l1_vs_karr,
            "int_flux_l1_vs_karr": int_l1_vs_karr,
            "writeback_delta_l1_vs_karr": delta_l1_vs_karr,
            "pair_flux": pair_flux,
        }

    # Karr's pair flux for reference
    karr_pair_flux = {name: float(karr_flux[col]) for name, col in PAIR_COLS.items()}

    print(f"Karr's pair-column flux at sample (0,1):")
    for name, kv in karr_pair_flux.items():
        print(f"  {name:>12s}: {kv:>+10.3e}")
    print()

    # Baseline (no epsilon)
    r0 = solve_and_writeback(c_base, "baseline (no penalty)")

    # a-fit
    c_fit, pushes_fit = build_epsilon_penalties_fit_to_karr(c_base, karr_flux, epsilon=1e-9)
    r_fit = solve_and_writeback(c_fit, "a-fit (eps=1e-9, signs from Karr)")

    # a-principled
    c_prn, pushes_prn = build_epsilon_penalties_principled(c_base, epsilon=1e-9)
    r_prn = solve_and_writeback(c_prn, "a-principled (eps=1e-9, dipeptide penalty only)")

    # Try larger epsilon for a-fit to see if magnitude matters
    c_fit_big, _ = build_epsilon_penalties_fit_to_karr(c_base, karr_flux, epsilon=1e-6)
    r_fit_big = solve_and_writeback(c_fit_big, "a-fit (eps=1e-6, signs from Karr)")

    # Report
    print(f"{'mode':<60s} {'obj':>14s} {'full_L1':>11s} {'ext_L1':>11s} {'int_L1':>11s} {'WB_diff_L1':>11s}")
    print("-" * 124)
    for r in [r0, r_fit, r_fit_big, r_prn]:
        print(f"{r['label']:<60s} {r['lp_obj']:>14.6e} {r['full_flux_l1_vs_karr']:>11.3e} {r['ext_flux_l1_vs_karr']:>11.3e} {r['int_flux_l1_vs_karr']:>11.3e} {r['writeback_delta_l1_vs_karr']:>11d}")

    print()
    print("Pair-column flux comparison:")
    print(f"{'name':>12s} {'Karr':>11s} {'baseline':>11s} {'a-fit-1e9':>11s} {'a-fit-1e6':>11s} {'a-prn-1e9':>11s}")
    for name in PAIR_COLS:
        print(f"{name:>12s}  {karr_pair_flux[name]:>+11.3e}  {r0['pair_flux'][name]:>+11.3e}  {r_fit['pair_flux'][name]:>+11.3e}  {r_fit_big['pair_flux'][name]:>+11.3e}  {r_prn['pair_flux'][name]:>+11.3e}")

    out = {
        "karr_pair_flux": karr_pair_flux,
        "baseline": r0, "a_fit_eps_1e9": r_fit, "a_fit_eps_1e6": r_fit_big,
        "a_principled_eps_1e9": r_prn,
        "epsilon_signs_fit": pushes_fit,
        "epsilon_signs_principled": pushes_prn,
    }
    out_path = REPO / "tmp" / "h_epsilon_objective.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
