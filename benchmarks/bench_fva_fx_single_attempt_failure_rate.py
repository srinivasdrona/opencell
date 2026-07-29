"""Supplementary measurement for C2: does exact GLP_FX fail more often WITHOUT
the fallback cascade (i.e. a single PSE+fresh-advanced-basis attempt, matching
the solver configuration in place before the fallback-cascade robustness fix)?

`bench_fva_fx_vs_db_objective_face_equivalence.py` measured 0/100 sample
failures for exact FX WITH the shipped fallback cascade -- a materially
different number from Opus 5's cited ~15.7%. Before concluding "the window
isn't actually necessary", this script isolates whether the cascade itself
(not the window) is what's suppressing FX failures, by forcing
`_solve_direction_with_fallback` to try only its FIRST strategy (adv basis +
PSE pricing) per direction, on the SAME pre-registered 100-sample set. This
directly tests exact FX under the ORIGINAL (pre-cascade) solver
configuration, isolating the window's own marginal contribution from the
cascade's.

Run via: bin\\oc-py benchmarks\\bench_fva_fx_single_attempt_failure_rate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "tests" / "vivarium"))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402

from opencell.m1 import fva as fva_module  # noqa: E402
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture  # noqa: E402

# Reuse the exact sample-input plumbing from the main equivalence benchmark.
sys.path.insert(0, str(_REPO_ROOT / "benchmarks"))
from bench_fva_fx_vs_db_objective_face_equivalence import (  # noqa: E402
    _PREREGISTERED_SAMPLES,
    _sample_inputs,
)

_WRITEBACK_FIXTURE_MAT = (
    _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
)


def main() -> None:
    fixture = KarrWritebackFixture.from_mat(_WRITEBACK_FIXTURE_MAT)
    oracle = runner_helpers.load_karr_oracle("Metabolism")

    # Force single-attempt (no fallback) by truncating the module-level
    # strategy list to just the first entry for the duration of this script.
    original_strategies = fva_module._FVA_FALLBACK_STRATEGIES
    fva_module._FVA_FALLBACK_STRATEGIES = original_strategies[:1]
    try:
        sample_failures = 0
        col_dir_failures = 0
        col_dir_total = 0
        failing_samples: list[tuple[int, int]] = []
        for seed, tick in _PREREGISTERED_SAMPLES:
            (
                model, lb, ub, biomass_value_star, growth_per_s, pre_sub, post_sub, reaction_subset,
            ) = _sample_inputs(oracle, fixture, seed, tick)
            S = np.asarray(model.S, dtype=np.float64)
            rhs = np.asarray(model.RHS, dtype=np.float64)
            c = np.asarray(model.obj, dtype=np.float64)
            col_dir_total += 2 * int(reaction_subset.size)
            try:
                fva_module.fva_range(
                    S, rhs, c, lb, ub, biomass_value_star=biomass_value_star,
                    reaction_subset=reaction_subset, _face_mode="fx",
                )
            except RuntimeError:
                sample_failures += 1
                col_dir_failures += 2 * int(reaction_subset.size)
                failing_samples.append((seed, tick))
        print("Single-attempt (no fallback cascade) exact-FX failure rate:")
        print(
            f"  sample_failures = {sample_failures}/{len(_PREREGISTERED_SAMPLES)} "
            f"({100.0 * sample_failures / len(_PREREGISTERED_SAMPLES):.1f}%)"
        )
        print(
            f"  col*dir failures (conservative) = {col_dir_failures}/{col_dir_total} "
            f"({100.0 * col_dir_failures / col_dir_total:.1f}%)"
        )
        print(f"  failing samples: {failing_samples}")
    finally:
        fva_module._FVA_FALLBACK_STRATEGIES = original_strategies


if __name__ == "__main__":
    main()
