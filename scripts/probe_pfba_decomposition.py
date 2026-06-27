"""Verify pFBA closes the LP-degeneracy gap at the allocated state.

Compares:
  HiGHS                  - baseline (Day-37)
  GLPK                   - Day-40 solver swap
  GLPK + pFBA            - Day-40 with parsimony
  Karr recorded          - ground truth
"""
from __future__ import annotations

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

GT_PATH = (
    REPO
    / "data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat"
)


def main():
    with h5py.File(GT_PATH, "r") as h:
        flux_karr = np.asarray(h["flux"][()], dtype=np.float64).reshape(-1)
        growth_karr = float(np.asarray(h["growth"][()]).reshape(-1)[0])
        bounds_karr = np.asarray(h["bounds"][()], dtype=np.float64)
        pre_sub_alloc = np.asarray(h["pre_sub"][()], dtype=np.float64)
        delta_karr = np.asarray(h["delta"][()], dtype=np.float64)

    if bounds_karr.shape == (2, 504):
        bounds_karr = bounds_karr.T
    if pre_sub_alloc.shape == (3, 585):
        pre_sub_alloc = pre_sub_alloc.T
    if delta_karr.shape == (3, 585):
        delta_karr = delta_karr.T

    model = km.load_default()
    lb, ub = bounds_karr[:, 0], bounds_karr[:, 1]

    print(f"Karr ref: growth={growth_karr:.6e}  flux sum_abs={np.abs(flux_karr).sum():.4e}  nnz={(flux_karr != 0).sum()}/504")
    print()

    results = []
    for label, kwargs in [
        ("HiGHS",        dict(solver="highs")),
        ("GLPK",         dict(solver="glpk")),
        ("GLPK+pFBA",    dict(solver="glpk", pfba=True)),
    ]:
        v, info = km.solve_fba(
            model,
            use_full_objective=True,
            sense="max",
            big=1e6,
            lb_override=lb,
            ub_override=ub,
            **kwargs,
        )
        growth = info["biomass_flux_per_s"]
        d = v - flux_karr
        L1 = float(np.abs(d).sum())
        max_d = float(np.abs(d).max())
        gt100 = int((np.abs(d) > 100).sum())
        gt1e4 = int((np.abs(d) > 1e4).sum())
        gt5e5 = int((np.abs(d) > 5e5).sum())
        sumabs = float(np.abs(v).sum())
        results.append((label, v, growth, L1, max_d, gt100, gt1e4, gt5e5, sumabs))

    print(f"{'variant':14s}  {'growth':>14s}  {'flux L1 vs Karr':>17s}  {'max diff':>10s}  {'>100':>5s}  {'>1e4':>5s}  {'>5e5':>5s}  {'sum_abs(v)':>12s}")
    print("-" * 110)
    for label, v, growth, L1, max_d, gt100, gt1e4, gt5e5, sumabs in results:
        print(f"{label:14s}  {growth:14.6e}  {L1:17.4e}  {max_d:10.4e}  {gt100:5d}  {gt1e4:5d}  {gt5e5:5d}  {sumabs:12.4e}")
    print(f"{'Karr recorded':14s}  {growth_karr:14.6e}  {0.0:17.4e}  {0.0:10.4e}  {0:5d}  {0:5d}  {0:5d}  {np.abs(flux_karr).sum():12.4e}")

    # Writeback comparison
    print()
    print("Writeback L1 vs Karr recorded delta (matches L2.2 substrates W1 metric semantically):")
    fbf = KarrWritebackFixture.from_mat(
        str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat")
    )
    C_recorded = delta_karr.astype(np.int64)
    C_flat = C_recorded.sum(axis=1).astype(np.float64)
    for label, v, growth, *_ in results:
        A = apply_karr_substrate_writeback(
            pre_state_585x3=pre_sub_alloc,
            v_504=v, growth_per_s=growth,
            fixture=fbf,
            rng=_Mcg16807(seed=12345),
            step_size_sec=1.0,
        )
        A_flat = A.sum(axis=1).astype(np.float64)
        L1 = float(np.abs(A_flat - C_flat).sum())
        print(f"  {label:14s}: writeback L1 = {L1:.0f}")
    # And Karr-flux writeback for ground truth (should be ~40)
    B = apply_karr_substrate_writeback(
        pre_state_585x3=pre_sub_alloc,
        v_504=flux_karr, growth_per_s=growth_karr,
        fixture=fbf,
        rng=_Mcg16807(seed=12345),
        step_size_sec=1.0,
    )
    B_flat = B.sum(axis=1).astype(np.float64)
    Lkarr = float(np.abs(B_flat - C_flat).sum())
    print(f"  {'Karr-flux WB':14s}: writeback L1 = {Lkarr:.0f}  (RNG + algorithm fidelity floor)")


if __name__ == "__main__":
    main()
