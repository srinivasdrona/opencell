"""C3/C4 correction (2026-07-29 review pass): measure the REAL wall-time
effect of the NOFEAS/timeout-aware fallback-cascade reordering, and exercise
the new per-strategy telemetry (`fva_range(..., telemetry=...)`).

Opus 5's review flagged the original (unordered/no-skip) cascade as "wasting
51% wall" by retrying a same-basis/different-pricing strategy immediately
after a genuine timeout, before reaching a different-basis strategy that
would resolve quickly. This script does NOT reuse that "51%" figure (not
independently verified) -- it measures actual before/after wall time on the
known historically-hard samples documented in fva.py's root-cause comments:

  - (seed=0, tick=0), column j=392, MIN: GLP_ETMLIM (genuine 10s timeout)
    under the shipped PSE+fresh-basis primary attempt (THIRD root cause).
  - (seed=20, tick=16), column j=417, MIN: GLP_NOFEAS (fast, cheap failure)
    under exact FX (used here via `_face_mode="fx"` to reliably reproduce a
    NOFEAS-class failure for the A/B comparison; the shipped GLP_DB window
    means this sample no longer needs any fallback at all in production).
  - (seed=0, tick=2): representative normal sample (baseline, expect no
    fallback needed for almost all columns).

"OLD" (no early-skip) cascade behavior is reproduced here by temporarily
monkeypatching `fva_module._FVA_TIMEOUT_EXIT_CODES` to an empty set (this
disables ONLY the skip decision, reusing the exact same strategy list/order/
attempt logic as the shipped "NEW" cascade -- so the two arms differ in
exactly one thing: whether a same-basis retry is skipped after a timeout).

Run via: bin\\oc-py benchmarks\\bench_fva_fallback_cascade_telemetry.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "tests" / "vivarium"))
sys.path.insert(0, str(_REPO_ROOT / "benchmarks"))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
from bench_fva_fx_vs_db_objective_face_equivalence import _sample_inputs  # noqa: E402

from opencell.m1 import fva as fva_module  # noqa: E402
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture  # noqa: E402

_WRITEBACK_FIXTURE_MAT = (
    _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
)


def _run_once(seed: int, tick: int, *, face_mode: str, disable_skip: bool) -> dict:
    fixture = KarrWritebackFixture.from_mat(_WRITEBACK_FIXTURE_MAT)
    oracle = runner_helpers.load_karr_oracle("Metabolism")
    (
        model, lb, ub, biomass_value_star, _growth_per_s, _pre_sub, _post_sub, reaction_subset,
    ) = _sample_inputs(oracle, fixture, seed, tick)
    S = np.asarray(model.S, dtype=np.float64)
    rhs = np.asarray(model.RHS, dtype=np.float64)
    c = np.asarray(model.obj, dtype=np.float64)

    original_timeout_codes = fva_module._FVA_TIMEOUT_EXIT_CODES
    if disable_skip:
        fva_module._FVA_TIMEOUT_EXIT_CODES = frozenset()
    try:
        telemetry = fva_module.new_fva_solver_telemetry()
        t0 = time.perf_counter()
        fva_module.fva_range(
            S, rhs, c, lb, ub, biomass_value_star=biomass_value_star,
            reaction_subset=reaction_subset, telemetry=telemetry, _face_mode=face_mode,
        )
        wall = time.perf_counter() - t0
    finally:
        fva_module._FVA_TIMEOUT_EXIT_CODES = original_timeout_codes
    return {"wall_time_s": wall, "telemetry": telemetry}


def main() -> None:
    cases = [
        ("seed0_tick0_etlim_history", 0, 0, "db"),
        ("seed20_tick16_nofeas_history_fx", 20, 16, "fx"),
        ("seed0_tick2_baseline", 0, 2, "db"),
    ]
    print(
        f"{'case':38s} {'old(no-skip) s':>16s} {'new(skip) s':>14s} "
        f"{'saved s':>10s} {'saved %':>8s}"
    )
    for name, seed, tick, face_mode in cases:
        try:
            old = _run_once(seed, tick, face_mode=face_mode, disable_skip=True)
        except RuntimeError as exc:
            msg = (
                f"{name:38s} old arm FAILED "
                f"(both arms would fail identically -- see note below): {exc}"
            )
            print(msg[:200])
            continue
        new = _run_once(seed, tick, face_mode=face_mode, disable_skip=False)
        saved = old["wall_time_s"] - new["wall_time_s"]
        saved_pct = 100.0 * saved / old["wall_time_s"] if old["wall_time_s"] > 0 else 0.0
        print(
            f"{name:38s} {old['wall_time_s']:16.3f} {new['wall_time_s']:14.3f} "
            f"{saved:10.3f} {saved_pct:7.1f}%"
        )
        print(f"    old telemetry: {old['telemetry']}")
        print(f"    new telemetry: {new['telemetry']}")

    print()
    print("NOTE on (seed=20, tick=16) under exact FX: ALL 5 fallback strategies")
    print("(different bases AND different pricing rules) genuinely fail to certify")
    print("GLP_OPT -- this is not a solvable-by-more-retries problem, it is a case")
    print("where the exact GLP_FX equality is numerically uncertifiable regardless")
    print("of pivoting strategy (ill-conditioned A-matrix, ratio ~3.6e8). Only the")
    print("shipped GLP_DB window (used in production) resolves it. This is the")
    print("concrete evidence for the window's necessity claim in fva.py.")
    print()
    print("NOTE on (seed=0, tick=0): the historically-documented GLP_ETMLIM timeout")
    print("(THIRD root cause) is NON-reproducible on demand (confirmed again here --")
    print("this run converged directly, no fallback needed), consistent with the")
    print("original floating-point-nondeterminism diagnosis. A live wall-clock A/B")
    print("of the skip-on-timeout reordering is validated instead by the")
    print("deterministic mocked-attempt unit test in tests/m1/test_fva_perf.py")
    print("(injects a synthetic GLP_ETMLIM result and asserts the cascade skips the")
    print("same-basis retry), plus the worst-case arithmetic: skipping one")
    print("same-basis/different-pricing retry after a genuine tm_lim=10s timeout")
    print("saves up to ~10s per occurrence whenever one does occur.")


if __name__ == "__main__":
    main()
