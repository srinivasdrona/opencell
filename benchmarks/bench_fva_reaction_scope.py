"""Task 2: identify the exact reaction set required by
`substrate_delta_range_from_fva`, and confirm it is a small subset of the
full 504-reaction FVA sweep.

Run via: bin\\oc-py benchmarks\\bench_fva_reaction_scope.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "tests" / "vivarium"))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture  # noqa: E402

_WRITEBACK_FIXTURE_MAT = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"


def main() -> None:
    fixture = KarrWritebackFixture.from_mat(_WRITEBACK_FIXTURE_MAT)
    ext = np.asarray(fixture.fba_idx_external, dtype=np.int64)
    internal = np.asarray(fixture.fba_idx_internal, dtype=np.int64)
    print(f"fba_idx_external: n={ext.size}, unique={np.unique(ext).size}")
    print(f"fba_idx_internal: n={internal.size}, unique={np.unique(internal).size}")

    union = np.unique(np.concatenate([ext, internal]))
    print(f"union (external | internal): n={union.size}")
    overlap = np.intersect1d(ext, internal)
    print(f"overlap (external & internal): n={overlap.size} -> {overlap.tolist()}")

    model = runner_helpers._metabolism_model()
    n_rxn = int(np.asarray(model.obj).reshape(-1).shape[0])
    print(f"total reactions in model: n_rxn={n_rxn}")
    print(f"reduction: {union.size}/{n_rxn} = {100.0 * union.size / n_rxn:.1f}% of reactions actually used "
          f"by substrate_delta_range_from_fva")

    # Also report how many of the *union* reactions have lb==ub in a representative
    # sample's bounds (those don't need an LP solve at all: v_min=v_max=lb trivially).
    from opencell.m1 import calc_flux_bounds as cfb

    oracle = runner_helpers.load_karr_oracle("Metabolism")
    before_sub = np.asarray(oracle["before_substrates_cube"], dtype=np.float64)
    before_enz = np.asarray(oracle["before_enzymes"], dtype=np.float64)
    dyn = runner_helpers._metabolism_dynamics()
    fba_reaction_bounds = np.column_stack([model.lb, model.ub]).astype(np.float64)
    fixed_counts = []
    for seed, tick in [(0, 0), (0, 5), (1, 1), (5, 10), (25, 15)]:
        pre_sub = before_sub[seed, tick]
        pre_enz = before_enz[seed, tick]
        bounds = cfb.compute_bounds(
            substrates=pre_sub,
            enzymes=pre_enz,
            cell_dry_mass=dyn.cell_dry_mass,
            step_size_sec=dyn.step_size_sec,
            catalysis=model.catalysis,
            enz_bounds=model.enz_bounds,
            fba_reaction_bounds=fba_reaction_bounds,
            dyn=dyn,
            apply_protein_bounds=False,
        )
        lb = bounds[:, 0][union]
        ub = bounds[:, 1][union]
        n_fixed = int(np.count_nonzero(lb == ub))
        fixed_counts.append(n_fixed)
        print(f"  sample(seed={seed},tick={tick}): fixed (lb==ub) among union reactions = {n_fixed}/{union.size}")
    print(f"mean fixed fraction among union: {np.mean(fixed_counts) / union.size:.2%}")

    # Report where the pathological columns observed in bench_fva_profile.py
    # (j in {3, 6, 24, 66, 233, 384, 395, 396, ...}) fall relative to the union.
    pathological = [3, 6, 24, 66, 233, 384, 395, 396]
    in_union = [j for j in pathological if j in set(union.tolist())]
    print(f"pathological columns observed in profiling: {pathological}")
    print(f"  of these, in union (needed) set: {in_union}")
    print(f"  NOT in union (i.e. would be skipped by the reduced sweep): "
          f"{[j for j in pathological if j not in set(union.tolist())]}")


if __name__ == "__main__":
    main()
