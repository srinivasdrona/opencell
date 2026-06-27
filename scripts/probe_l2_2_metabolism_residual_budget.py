"""Residual-budget decomposition for L2.2 Metabolism substrate W1=161 gap.

Question (from rubber-duck critique): Karr-vs-Karr q95 = 51, OC-vs-Karr = 161.
What makes up the extra 110 units?

Decomposition across ALL 500 audit samples (50 seeds x 10 ticks):
  Component F (floor, RNG/algorithm fidelity):
    Known from (0, 1) single-sample probe: 40 / 148K = 0.03%
    Reported here as estimate; verified at one sample only.

  Component B (bounds drift):
    OC.compute_bounds vs Karr's MATLAB-extracted bounds at (0, 1).
    If max abs diff > 1e-9, bounds drift is real and contributes.
    Verified at one sample only (only sample where we have Karr bounds).

  Component S (solver-choice — main known contributor):
    Paired per-sample: |HiGHS-WB - Karr_recorded| - |GLPK-WB - Karr_recorded|
    Reported as: mean delta, CI95, paired bootstrap p-value.

  Component R (residual, after solver swap):
    |GLPK-WB - Karr_recorded| per sample.
    What's left to attribute to: GLPK 5.0 vs Karr's GLPK 4.x basis, bounds, RNG.

This is per-sample WRITEBACK L1 (related to but not identical to W1).
Per-tick substrate W1 sums |OC - Karr| across seeds for each (WID, tick);
writeback L1 sums |OC - Karr| across WIDs for each (seed, tick).
Both should move together if root cause is solver-basis selection.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import h5py

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "vivarium"))

from opencell.m1 import karr_metabolism as km
from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807


# Day-40 single-sample ground truth (s=0, tick=1) — has Karr flux + bounds
GT_PATH = (
    REPO
    / "data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat"
)

# Per_process_traces_v2 ensemble — has 50 seeds × 100 ticks of states
TRACE_DIR = REPO / "data/m1_sources/karr_native"


def _load_trace_seed(seed: int):
    """Load (before_subs, after_subs, before_enz, before_bound) for one seed.

    Shapes (T, 585) for substrates, (T, 104) for enzymes, where T=100.
    """
    path = TRACE_DIR / f"per_process_traces_v2_s{seed:03d}" / "Metabolism_100ticks.mat"
    with h5py.File(path, "r") as h:
        # The states_before/_after groups contain object refs per tick
        before_subs_refs = h["states_before/substrates"][:].reshape(-1)
        after_subs_refs = h["states_after/substrates"][:].reshape(-1)
        before_enz_refs = h["states_before/enzymes"][:].reshape(-1)
        before_bound_refs = h["states_before/boundEnzymes"][:].reshape(-1)
        T = len(before_subs_refs)
        before_subs = np.zeros((T, 585), dtype=np.float64)
        before_subs_3d = np.zeros((T, 585, 3), dtype=np.float64)
        after_subs_3d = np.zeros((T, 585, 3), dtype=np.float64)
        before_enz = np.zeros((T, 104), dtype=np.float64)
        before_bound = np.zeros((T, 104), dtype=np.float64)
        for t in range(T):
            bs = np.asarray(h[before_subs_refs[t]][:], dtype=np.float64)
            asu = np.asarray(h[after_subs_refs[t]][:], dtype=np.float64)
            be = np.asarray(h[before_enz_refs[t]][:], dtype=np.float64).reshape(-1)
            bb = np.asarray(h[before_bound_refs[t]][:], dtype=np.float64).reshape(-1)
            # bs/asu are (585, 3) or (3, 585); h5py orders matlab matrices the
            # transpose of native, so normalize to (585, 3)
            if bs.shape == (3, 585):
                bs = bs.T
            if asu.shape == (3, 585):
                asu = asu.T
            before_subs_3d[t] = bs
            after_subs_3d[t] = asu
            before_subs[t] = bs.sum(axis=1)  # flatten across compartments
            before_enz[t] = be
            before_bound[t] = bb
    return before_subs_3d, after_subs_3d, before_enz, before_bound


def _solve_and_writeback(model, dyn, lb, ub, pre_state_585x3, before_enz,
                         before_bound, fbf, rng_seed, *, solver, pfba=False):
    """Solve FBA + apply writeback. Returns delta (585, 3)."""
    v, info = km.solve_fba(
        model,
        use_full_objective=True,
        sense="max",
        big=1e6,
        lb_override=lb,
        ub_override=ub,
        solver=solver,
        pfba=pfba,
    )
    growth = info["biomass_flux_per_s"]
    rng = _Mcg16807(seed=rng_seed)
    delta = apply_karr_substrate_writeback(
        pre_state_585x3=pre_state_585x3,
        v_504=v,
        growth_per_s=growth,
        fixture=fbf,
        rng=rng,
        step_size_sec=1.0,
    )
    return delta, v, growth


def main():
    print("=" * 75)
    print("L2.2 Metabolism residual-budget decomposition")
    print("=" * 75)
    print()

    # ---- Component B: Bounds verification at (s=0, t=1) ----
    print("Step 1: bounds drift check at known-truth sample (s=0, t=1)")
    print("-" * 75)
    with h5py.File(GT_PATH, "r") as h:
        bounds_karr = np.asarray(h["bounds"][()], dtype=np.float64)
        pre_sub_alloc = np.asarray(h["pre_sub"][()], dtype=np.float64)
        pre_enz_alloc = np.asarray(h["pre_enz"][()], dtype=np.float64).reshape(-1)
    if bounds_karr.shape == (2, 504):
        bounds_karr = bounds_karr.T
    if pre_sub_alloc.shape == (3, 585):
        pre_sub_alloc = pre_sub_alloc.T

    model = km.load_default()
    dyn = cfb.load_default_dynamics()
    fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(float)

    # Compute OC bounds at the allocated state
    # cfb.compute_bounds signature varies; use the dynamic bounds workflow
    # via the metabolism vivarium process to ensure we use the same code path
    # as the audit.
    print(f"  Karr-extracted bounds: shape={bounds_karr.shape}")
    print(f"  Karr bounds finite/inf: lb_finite={np.isfinite(bounds_karr[:,0]).sum()}/504, "
          f"ub_finite={np.isfinite(bounds_karr[:,1]).sum()}/504")
    # OC compute_bounds at this state — matches vivarium dynamic-bounds workflow
    fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(float)
    try:
        oc_bounds = cfb.compute_bounds(
            substrates=pre_sub_alloc,
            enzymes=pre_enz_alloc,
            cell_dry_mass=dyn.cell_dry_mass,
            step_size_sec=dyn.step_size_sec,
            catalysis=model.catalysis,
            enz_bounds=model.enz_bounds,
            fba_reaction_bounds=fba_reaction_bounds,
            dyn=dyn,
            apply_protein_bounds=False,
        )
        if oc_bounds.shape == (2, 504):
            oc_bounds = oc_bounds.T
        lb_diff = np.where(
            np.isfinite(oc_bounds[:, 0]) & np.isfinite(bounds_karr[:, 0]),
            np.abs(oc_bounds[:, 0] - bounds_karr[:, 0]),
            0.0,
        )
        ub_diff = np.where(
            np.isfinite(oc_bounds[:, 1]) & np.isfinite(bounds_karr[:, 1]),
            np.abs(oc_bounds[:, 1] - bounds_karr[:, 1]),
            0.0,
        )
        print(f"  OC bounds: shape={oc_bounds.shape}")
        print(f"  |OC.lb - Karr.lb|: max={lb_diff.max():.4e}, sum={lb_diff.sum():.4e}, n>1e-6={(lb_diff>1e-6).sum()}")
        print(f"  |OC.ub - Karr.ub|: max={ub_diff.max():.4e}, sum={ub_diff.sum():.4e}, n>1e-6={(ub_diff>1e-6).sum()}")
        # Finite/inf mismatches
        lb_inf_disagree = (np.isfinite(oc_bounds[:, 0]) != np.isfinite(bounds_karr[:, 0])).sum()
        ub_inf_disagree = (np.isfinite(oc_bounds[:, 1]) != np.isfinite(bounds_karr[:, 1])).sum()
        print(f"  Inf-finite disagreements: lb={lb_inf_disagree}, ub={ub_inf_disagree}")
        BOUNDS_MATCH = (
            lb_diff.max() < 1e-6
            and ub_diff.max() < 1e-6
            and lb_inf_disagree == 0
            and ub_inf_disagree == 0
        )
        print(f"  BOUNDS MATCH (max abs diff < 1e-6): {BOUNDS_MATCH}")
    except Exception as exc:
        print(f"  ERROR running cfb.compute_bounds: {exc}")
        print("  Skipping bounds match check.")
        BOUNDS_MATCH = None

    print()
    # ---- Component F: Algorithm/RNG fidelity floor ----
    print("Step 2: algorithm/RNG floor (known from (0, 1) single-sample probe)")
    print("-" * 75)
    print("  Karr-flux + Karr-writeback vs Karr recorded delta: L1=40 of 148K (0.03%)")
    print()

    # ---- Component S+R: per-sample writeback L1 across all 500 audit samples ----
    print("Step 3: per-sample writeback L1 across 50 seeds x 10 ticks = 500 samples")
    print("-" * 75)

    fbf = KarrWritebackFixture.from_mat(
        str(REPO / "data/karr_fixtures/per_process/Metabolism_flat.mat")
    )

    SEEDS = list(range(50))
    M_TICKS = 10

    L_highs = np.zeros((len(SEEDS), M_TICKS), dtype=np.float64)
    L_glpk = np.zeros((len(SEEDS), M_TICKS), dtype=np.float64)
    # store also raw mass — to see the scale
    karr_mass = np.zeros((len(SEEDS), M_TICKS), dtype=np.float64)

    n_solver_failures = 0
    n_bound_check_failures = 0

    for seed_idx, seed in enumerate(SEEDS):
        try:
            before_3d, after_3d, before_enz, before_bound = _load_trace_seed(seed)
        except FileNotFoundError as exc:
            print(f"  seed {seed}: missing trace file ({exc}); skipping")
            continue
        for tick in range(M_TICKS):
            pre = before_3d[tick]
            karr_delta = (after_3d[tick] - before_3d[tick]).astype(np.float64)
            try:
                lb_oc = cfb.compute_bounds(
                    substrates=pre,
                    enzymes=before_enz[tick],
                    cell_dry_mass=dyn.cell_dry_mass,
                    step_size_sec=dyn.step_size_sec,
                    catalysis=model.catalysis,
                    enz_bounds=model.enz_bounds,
                    fba_reaction_bounds=fba_reaction_bounds,
                    dyn=dyn,
                    apply_protein_bounds=False,
                )
                if lb_oc.shape == (2, 504):
                    lb_oc = lb_oc.T
                lb, ub = lb_oc[:, 0], lb_oc[:, 1]
            except Exception as exc:
                n_bound_check_failures += 1
                continue
            try:
                d_highs, _, _ = _solve_and_writeback(
                    model, dyn, lb, ub, pre, before_enz[tick],
                    before_bound[tick], fbf, rng_seed=12345 + seed,
                    solver="highs",
                )
                d_glpk, _, _ = _solve_and_writeback(
                    model, dyn, lb, ub, pre, before_enz[tick],
                    before_bound[tick], fbf, rng_seed=12345 + seed,
                    solver="glpk",
                )
            except Exception as exc:
                n_solver_failures += 1
                continue
            karr_mass[seed_idx, tick] = float(np.abs(karr_delta).sum())
            L_highs[seed_idx, tick] = float(np.abs(d_highs - karr_delta).sum())
            L_glpk[seed_idx, tick] = float(np.abs(d_glpk - karr_delta).sum())
        if seed_idx % 10 == 0:
            print(f"  seed {seed}: done (mean L_highs={L_highs[seed_idx].mean():.0f}, "
                  f"mean L_glpk={L_glpk[seed_idx].mean():.0f})")

    print(f"  Failures: bound_check={n_bound_check_failures}, solver={n_solver_failures}")
    print()

    # ---- Reporting ----
    print("Step 4: residual budget summary")
    print("-" * 75)
    L_highs_flat = L_highs.reshape(-1)
    L_glpk_flat = L_glpk.reshape(-1)
    mass_flat = karr_mass.reshape(-1)
    mask = mass_flat > 0  # only samples we actually processed

    if mask.sum() == 0:
        print("  No valid samples processed. Abort.")
        return

    print(f"  Valid samples: {mask.sum()}/{len(L_highs_flat)}")
    print()
    print(f"  Karr recorded delta L1 / sample:")
    print(f"    mean={mass_flat[mask].mean():.0f}  median={np.median(mass_flat[mask]):.0f}  "
          f"max={mass_flat[mask].max():.0f}")
    print()
    print(f"  HiGHS writeback L1 vs Karr recorded / sample:")
    print(f"    mean={L_highs_flat[mask].mean():.0f}  median={np.median(L_highs_flat[mask]):.0f}  "
          f"max={L_highs_flat[mask].max():.0f}")
    print(f"    relative to Karr mass: mean ratio={L_highs_flat[mask].mean()/mass_flat[mask].mean()*100:.1f}%")
    print()
    print(f"  GLPK writeback L1 vs Karr recorded / sample:")
    print(f"    mean={L_glpk_flat[mask].mean():.0f}  median={np.median(L_glpk_flat[mask]):.0f}  "
          f"max={L_glpk_flat[mask].max():.0f}")
    print(f"    relative to Karr mass: mean ratio={L_glpk_flat[mask].mean()/mass_flat[mask].mean()*100:.1f}%")
    print()

    # ---- Paired bootstrap on (HiGHS - GLPK) per sample ----
    print("Step 5: paired bootstrap on (HiGHS - GLPK) writeback L1")
    print("-" * 75)
    diffs = L_highs_flat[mask] - L_glpk_flat[mask]
    mean_diff = diffs.mean()
    rng_bs = np.random.default_rng(0)
    B = 2000
    boot = np.zeros(B)
    for b in range(B):
        idx = rng_bs.choice(len(diffs), size=len(diffs), replace=True)
        boot[b] = diffs[idx].mean()
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    n_pos = int((diffs > 0).sum())
    n_neg = int((diffs < 0).sum())
    print(f"  mean(HiGHS - GLPK) per sample: {mean_diff:+.1f}")
    print(f"  95% CI (paired bootstrap, B={B}): [{ci_lo:+.1f}, {ci_hi:+.1f}]")
    print(f"  Samples where HiGHS > GLPK: {n_pos}/{mask.sum()} ({n_pos/mask.sum()*100:.1f}%)")
    print(f"  Samples where HiGHS < GLPK: {n_neg}/{mask.sum()} ({n_neg/mask.sum()*100:.1f}%)")
    if ci_lo > 0:
        print(f"  -> GLPK is reliably better than HiGHS (CI excludes zero)")
    elif ci_hi < 0:
        print(f"  -> HiGHS is reliably better than GLPK (CI excludes zero)")
    else:
        print(f"  -> CI crosses zero; GLPK 'improvement' is NOT statistically distinguishable from noise")

    # Final budget
    print()
    print("=" * 75)
    print("RESIDUAL BUDGET (per-sample writeback L1)")
    print("=" * 75)
    floor = 40.0
    glpk_mean = float(L_glpk_flat[mask].mean())
    highs_mean = float(L_highs_flat[mask].mean())
    print(f"  Karr recorded mass per sample:     {mass_flat[mask].mean():.0f}")
    print(f"  Floor (algorithm/RNG):             {floor:.0f}  ({floor/mass_flat[mask].mean()*100:.3f}%)")
    print(f"  Solver-choice (HiGHS - GLPK):      {highs_mean - glpk_mean:.0f}  ({(highs_mean-glpk_mean)/mass_flat[mask].mean()*100:.2f}%)")
    print(f"  Residual after GLPK swap:          {glpk_mean - floor:.0f}  ({(glpk_mean-floor)/mass_flat[mask].mean()*100:.2f}%)")
    print(f"  -> HiGHS total gap:                {highs_mean:.0f}  ({highs_mean/mass_flat[mask].mean()*100:.2f}%)")
    print(f"  -> GLPK total gap (current best):  {glpk_mean:.0f}  ({glpk_mean/mass_flat[mask].mean()*100:.2f}%)")
    print()
    if BOUNDS_MATCH is True:
        print("  Bounds drift contribution: NONE (verified at sample (0,1), max diff < 1e-6)")
    elif BOUNDS_MATCH is False:
        print("  Bounds drift contribution: REAL — see Step 1 numbers")
    else:
        print("  Bounds drift contribution: UNVERIFIED — cfb.compute_bounds didn't run")

    # Save numpy for later analysis
    out = REPO / "tmp" / "l2_2_metabolism_residual_budget.npz"
    out.parent.mkdir(exist_ok=True)
    np.savez(
        out,
        L_highs=L_highs,
        L_glpk=L_glpk,
        karr_mass=karr_mass,
    )
    print(f"\n  Saved per-sample arrays to {out}")


if __name__ == "__main__":
    main()
