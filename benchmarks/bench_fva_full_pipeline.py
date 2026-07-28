"""Task 5 success-gate benchmark: run the REAL post-fix `_metabolism_fva_sample_feasibility`
computation path (opencell/m1/fva.py's actual `fva_range`, with the PSE-pricing fix
+ safety net + reaction_subset reduction, exactly as tests/vivarium/l2_2_design_a_runner.py
calls it) across a diverse set of samples spanning the full 50-seed x 20-tick oracle
grid, and project full N50xM20 runtime.

Run via: bin\\oc-py benchmarks\\bench_fva_full_pipeline.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "tests" / "vivarium"))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
from opencell.m1 import calc_flux_bounds as cfb  # noqa: E402
from opencell.m1.fva import fva_range, substrate_delta_range_from_fva  # noqa: E402

_METABOLISM_FVA_BIG = 1e6
_METABOLISM_FVA_TOL = 2.0


def _bounds_for_sample(pre_sub_585x3, pre_enz_104):
    model = runner_helpers._metabolism_model()
    dyn = runner_helpers._metabolism_dynamics()
    fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(np.float64)
    bounds = cfb.compute_bounds(
        substrates=np.asarray(pre_sub_585x3, dtype=np.float64),
        enzymes=np.asarray(pre_enz_104, dtype=np.float64),
        cell_dry_mass=dyn.cell_dry_mass,
        step_size_sec=dyn.step_size_sec,
        catalysis=model.catalysis,
        enz_bounds=model.enz_bounds,
        fba_reaction_bounds=fba_reaction_bounds,
        dyn=dyn,
        apply_protein_bounds=False,
    )
    lb = np.where(np.isfinite(bounds[:, 0]), bounds[:, 0], -_METABOLISM_FVA_BIG)
    ub = np.where(np.isfinite(bounds[:, 1]), bounds[:, 1], _METABOLISM_FVA_BIG)
    lb = np.clip(lb, -_METABOLISM_FVA_BIG, _METABOLISM_FVA_BIG).astype(np.float64)
    ub = np.clip(ub, -_METABOLISM_FVA_BIG, _METABOLISM_FVA_BIG).astype(np.float64)
    infeasible = lb > ub
    if np.any(infeasible):
        midpoint = 0.5 * (lb[infeasible] + ub[infeasible])
        lb[infeasible] = midpoint
        ub[infeasible] = midpoint
    return lb, ub


def run_one_sample(seed: int, tick: int, fixture, fva_reaction_subset) -> tuple[float, int, int]:
    oracle = runner_helpers.load_karr_oracle("Metabolism")
    before_sub = np.asarray(oracle["before_substrates_cube"], dtype=np.float64)
    before_enz = np.asarray(oracle["before_enzymes"], dtype=np.float64)
    after_sub = np.asarray(oracle["after_substrates_cube"], dtype=np.float64)
    pre_sub = before_sub[seed, tick]
    pre_enz = before_enz[seed, tick]
    post_sub = after_sub[seed, tick]

    model = runner_helpers._metabolism_model()
    t0 = time.perf_counter()
    lb, ub = _bounds_for_sample(pre_sub, pre_enz)
    _v_star, info = runner_helpers.m1_karr_metabolism.solve_fba(
        model, use_full_objective=True, sense="max", big=_METABOLISM_FVA_BIG,
        lb_override=lb, ub_override=ub, solver="glpk",
    )
    biomass_value_star = float(info["objective_value"])
    growth_per_s = float(info["biomass_flux_per_s"])
    v_min, v_max = fva_range(
        np.asarray(model.S, dtype=np.float64),
        np.asarray(model.RHS, dtype=np.float64),
        np.asarray(model.obj, dtype=np.float64),
        lb, ub,
        biomass_value_star=biomass_value_star,
        reaction_subset=fva_reaction_subset,
    )
    d_min, d_max = substrate_delta_range_from_fva(
        v_min=v_min, v_max=v_max, fixture=fixture,
        growth_per_s=growth_per_s, step_size_sec=float(fixture.step_size_sec),
        pre_state_585x3=pre_sub,
    )
    elapsed = time.perf_counter() - t0

    karr_delta = post_sub - pre_sub
    in_range = (
        np.isfinite(d_min) & np.isfinite(d_max)
        & (karr_delta >= (d_min - _METABOLISM_FVA_TOL))
        & (karr_delta <= (d_max + _METABOLISM_FVA_TOL))
    )
    return elapsed, int(np.count_nonzero(in_range)), int(in_range.size)


def main() -> None:
    from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture

    fixture = KarrWritebackFixture.from_mat(
        _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
    )
    fva_reaction_subset = np.union1d(
        np.asarray(fixture.fba_idx_external, dtype=np.int64),
        np.asarray(fixture.fba_idx_internal, dtype=np.int64),
    )

    # Diverse sample selection: spans full seed range (0-49) and full tick
    # range (0-19), deterministic RNG so this is reproducible, not cherry-picked.
    rng = np.random.default_rng(20260729)
    seeds = rng.choice(50, size=12, replace=False).tolist()
    ticks = rng.choice(20, size=12, replace=False).tolist()
    samples = list(zip(seeds, ticks))
    # Also always include the previously-identified pathological sample to
    # prove the fix holds on the worst known case.
    samples.append((0, 5))

    total_wall = 0.0
    worst = []
    for seed, tick in samples:
        elapsed, feasible, total = run_one_sample(int(seed), int(tick), fixture, fva_reaction_subset)
        total_wall += elapsed
        worst.append((elapsed, seed, tick))
        print(f"sample(seed={seed},tick={tick}): {elapsed:.4f}s  feasible={feasible}/{total}")
        sys.stdout.flush()

    worst.sort(reverse=True)
    n = len(samples)
    mean_s = total_wall / n
    projected_s = mean_s * 50 * 20
    print("=== SUMMARY ===")
    print(f"n_samples={n} total_wall={total_wall:.4f}s mean_per_sample={mean_s:.4f}s")
    print("worst 5 by wall time:")
    for elapsed, seed, tick in worst[:5]:
        print(f"  seed={seed} tick={tick}: {elapsed:.4f}s")
    print(f"Projected N50xM20=1000-sample runtime: {projected_s:.1f}s ({projected_s / 3600:.4f} hours)")
    print(f"Success gate (<=2 hours): {'PASS' if projected_s <= 2 * 3600 else 'FAIL'}")


if __name__ == "__main__":
    main()
