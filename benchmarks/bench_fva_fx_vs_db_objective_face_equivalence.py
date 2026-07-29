"""C2 correction (2026-07-29 review pass): FX-vs-DB objective-face equivalence
and window-sweep-inertness benchmark.

Opus 5's review rejected the ORIGINAL justification for the objective-face
GLP_DB epsilon window (it wrongly called 1e-9 "relative" and wrongly claimed
it was "3-9 orders below every tolerance" -- both corrected in fva.py's
docstring/comments). This script independently measures the REAL numbers the
corrected justification is allowed to cite -- nothing here is copied from
Opus's own investigation (which cited 102 samples / 150,930 pairs; that
figure does not reconcile with this repo's known 1755-pairs-per-sample
structure -- 150,930 / 1755 = 86, not 102 -- so it is deliberately NOT reused
here).

Pre-registered sample set (fixed BEFORE running this script, not chosen after
seeing results): ALL 50 seeds x ticks {0, 1} of the actual N50xM20 oracle grid
used by the production L2.2 Metabolism FVA-feasibility gate = 100 samples.
This spans the full seed dimension and two ticks, drawn directly from
production data (not synthetic), while keeping runtime practical.

Measures, using ONLY the shipped production code path (`opencell.m1.fva
.fva_range`, including the reaction_subset reduction and the fallback
cascade -- so this is an apples-to-apples comparison, not a reimplementation):

1. |internal "FVA primary" objective value - biomass_value_star| mismatch,
   across all 100 samples (this is the actual quantity the epsilon window
   must cover).
2. Exact GLP_FX (`_face_mode="fx"`, no window at all) convergence: does every
   required (column, direction) solve reach GLP_OPT? Sample-level and
   column*direction-level failure rates are both reported.
3. For every sample where exact FX converges on EVERY required column: v_min/
   v_max agreement vs. the current GLP_DB(eps=1e-9 floor) window, and any
   downstream feasibility-classification ("in_range") flips (target: 0).
4. Epsilon-window sweep on a subset of samples: re-run DB mode with
   epsilon_obj in {1e-9 (floor; matches shipped default), 1e-8, 1e-7, 1e-6,
   1e-5} and confirm v_min/v_max and feasibility classification are identical
   across every swept value (0 flips) -- i.e. the shipped window's exact size
   is not something the pass/fail outcome is sensitive to.

Persists a JSON artifact with per-sample and aggregate results, and prints a
human-readable summary table.

Run via: bin\\oc-py benchmarks\\bench_fva_fx_vs_db_objective_face_equivalence.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "tests" / "vivarium"))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402

from opencell.m1 import calc_flux_bounds as cfb  # noqa: E402
from opencell.m1 import fva as fva_module  # noqa: E402
from opencell.m1.fva import fva_range, substrate_delta_range_from_fva  # noqa: E402
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture  # noqa: E402

_METABOLISM_FVA_BIG = 1e6
_METABOLISM_FVA_TOL = 2.0
_WRITEBACK_FIXTURE_MAT = (
    _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
)

# Pre-registered sample set: all 50 seeds x ticks {0, 1}. Fixed before running.
_PREREGISTERED_SAMPLES: list[tuple[int, int]] = [
    (seed, tick) for seed in range(50) for tick in (0, 1)
]

# Pre-registered epsilon sweep values (includes the shipped floor, 1e-9) and
# the subset of samples swept over (kept smaller for practicality: every 5th
# sample of the full 100, i.e. 20 samples).
_EPSILON_SWEEP_VALUES: list[float] = [1e-9, 1e-8, 1e-7, 1e-6, 1e-5]
_EPSILON_SWEEP_SAMPLES: list[tuple[int, int]] = _PREREGISTERED_SAMPLES[::5]

_OUT_PATH = _REPO_ROOT / "benchmarks" / "artifacts" / "fva_fx_vs_db_objective_face_equivalence.json"


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


def _sample_inputs(oracle, fixture, seed, tick):
    before_sub = np.asarray(oracle["before_substrates_cube"], dtype=np.float64)
    before_enz = np.asarray(oracle["before_enzymes"], dtype=np.float64)
    after_sub = np.asarray(oracle["after_substrates_cube"], dtype=np.float64)
    pre_sub = before_sub[seed, tick]
    pre_enz = before_enz[seed, tick]
    post_sub = after_sub[seed, tick]

    model = runner_helpers._metabolism_model()
    lb, ub = _bounds_for_sample(pre_sub, pre_enz)
    _v_star, info = runner_helpers.m1_karr_metabolism.solve_fba(
        model,
        use_full_objective=True,
        sense="max",
        big=_METABOLISM_FVA_BIG,
        lb_override=lb,
        ub_override=ub,
        solver="glpk",
    )
    biomass_value_star = float(info["objective_value"])
    growth_per_s = float(info["biomass_flux_per_s"])
    reaction_subset = np.union1d(
        np.asarray(fixture.fba_idx_external, dtype=np.int64),
        np.asarray(fixture.fba_idx_internal, dtype=np.int64),
    )
    return model, lb, ub, biomass_value_star, growth_per_s, pre_sub, post_sub, reaction_subset


def _feasibility(v_min, v_max, fixture, growth_per_s, pre_sub, post_sub):
    d_min, d_max = substrate_delta_range_from_fva(
        v_min=v_min,
        v_max=v_max,
        fixture=fixture,
        growth_per_s=growth_per_s,
        step_size_sec=float(fixture.step_size_sec),
        pre_state_585x3=pre_sub,
    )
    karr_delta = post_sub - pre_sub
    in_range = (
        np.isfinite(d_min)
        & np.isfinite(d_max)
        & (karr_delta >= (d_min - _METABOLISM_FVA_TOL))
        & (karr_delta <= (d_max + _METABOLISM_FVA_TOL))
    )
    return d_min, d_max, in_range


def main() -> None:
    fixture = KarrWritebackFixture.from_mat(_WRITEBACK_FIXTURE_MAT)
    oracle = runner_helpers.load_karr_oracle("Metabolism")

    per_sample_results: list[dict] = []
    obj_mismatches: list[float] = []
    fx_sample_failures = 0
    fx_col_dir_failures = 0
    fx_col_dir_total = 0
    flip_count = 0
    total_pairs_compared = 0
    max_v_diff = 0.0
    max_d_diff = 0.0

    t_start = time.perf_counter()
    for i, (seed, tick) in enumerate(_PREREGISTERED_SAMPLES):
        (
            model, lb, ub, biomass_value_star, growth_per_s, pre_sub, post_sub, reaction_subset,
        ) = _sample_inputs(oracle, fixture, seed, tick)
        S = np.asarray(model.S, dtype=np.float64)
        rhs = np.asarray(model.RHS, dtype=np.float64)
        c = np.asarray(model.obj, dtype=np.float64)

        # (1) + current production DB-window result.
        db_telemetry = fva_module.new_fva_solver_telemetry()
        v_min_db, v_max_db = fva_range(
            S, rhs, c, lb, ub, biomass_value_star=biomass_value_star,
            reaction_subset=reaction_subset, telemetry=db_telemetry,
        )
        obj_mismatch = abs(db_telemetry["fva_primary_objective_value"] - biomass_value_star)
        obj_mismatches.append(obj_mismatch)
        d_min_db, d_max_db, in_range_db = _feasibility(
            v_min_db, v_max_db, fixture, growth_per_s, pre_sub, post_sub
        )

        # (2) exact FX attempt, same code path (_face_mode="fx").
        fx_ok = True
        fx_error = None
        try:
            v_min_fx, v_max_fx = fva_range(
                S, rhs, c, lb, ub, biomass_value_star=biomass_value_star,
                reaction_subset=reaction_subset, _face_mode="fx",
            )
        except RuntimeError as exc:
            fx_ok = False
            fx_error = str(exc)
            v_min_fx = v_max_fx = None

        fx_col_dir_total += 2 * int(reaction_subset.size)
        sample_record: dict = {
            "seed": seed,
            "tick": tick,
            "obj_mismatch_abs": obj_mismatch,
            "fx_converged": fx_ok,
        }
        if not fx_ok:
            fx_sample_failures += 1
            # We don't have a clean per-column failure count without
            # retrying column-by-column (the fallback cascade already tried
            # everything it has for the first failing column before
            # raising); record this whole sample's columns as failed for the
            # conservative column*direction failure-rate denominator.
            fx_col_dir_failures += 2 * int(reaction_subset.size)
            sample_record["fx_error"] = fx_error
        else:
            # (3) compare FX vs DB on relevant reactions.
            sub = reaction_subset
            v_diff = np.nanmax(
                np.abs(
                    np.concatenate([v_min_fx[sub] - v_min_db[sub], v_max_fx[sub] - v_max_db[sub]])
                )
            )
            max_v_diff = max(max_v_diff, float(v_diff))
            d_min_fx, d_max_fx, in_range_fx = _feasibility(
                v_min_fx, v_max_fx, fixture, growth_per_s, pre_sub, post_sub
            )
            d_diff = np.nanmax(
                np.abs(np.concatenate([d_min_fx - d_min_db, d_max_fx - d_max_db]))
            )
            max_d_diff = max(max_d_diff, float(d_diff))
            flips = int(np.count_nonzero(in_range_fx != in_range_db))
            flip_count += flips
            total_pairs_compared += int(in_range_db.size)
            sample_record["v_max_abs_diff_fx_vs_db"] = float(v_diff)
            sample_record["d_max_abs_diff_fx_vs_db"] = float(d_diff)
            sample_record["feasibility_flips_fx_vs_db"] = flips
            sample_record["pairs_compared"] = int(in_range_db.size)

        per_sample_results.append(sample_record)
        if (i + 1) % 20 == 0:
            elapsed = time.perf_counter() - t_start
            print(f"  ... {i + 1}/{len(_PREREGISTERED_SAMPLES)} samples done ({elapsed:.1f}s)")

    # (4) epsilon-window sweep, DB mode only, on the smaller pre-registered subset.
    sweep_results: list[dict] = []
    sweep_flip_total = 0
    sweep_v_max_diff = 0.0
    for seed, tick in _EPSILON_SWEEP_SAMPLES:
        (
            model, lb, ub, biomass_value_star, growth_per_s, pre_sub, post_sub, reaction_subset,
        ) = _sample_inputs(oracle, fixture, seed, tick)
        S = np.asarray(model.S, dtype=np.float64)
        rhs = np.asarray(model.RHS, dtype=np.float64)
        c = np.asarray(model.obj, dtype=np.float64)
        per_eps: dict[str, dict] = {}
        for eps in _EPSILON_SWEEP_VALUES:
            v_min, v_max = fva_range(
                S, rhs, c, lb, ub, biomass_value_star=biomass_value_star,
                epsilon_obj=eps, reaction_subset=reaction_subset,
            )
            _, _, in_range = _feasibility(v_min, v_max, fixture, growth_per_s, pre_sub, post_sub)
            per_eps[repr(eps)] = {"v_min": v_min, "v_max": v_max, "in_range": in_range}
        baseline_eps = repr(_EPSILON_SWEEP_VALUES[0])
        base = per_eps[baseline_eps]
        max_diff_this_sample = 0.0
        flips_this_sample = 0
        for eps in _EPSILON_SWEEP_VALUES[1:]:
            other = per_eps[repr(eps)]
            sub = reaction_subset
            d = np.nanmax(np.abs(np.concatenate([
                other["v_min"][sub] - base["v_min"][sub], other["v_max"][sub] - base["v_max"][sub],
            ])))
            max_diff_this_sample = max(max_diff_this_sample, float(d))
            flips_this_sample += int(np.count_nonzero(other["in_range"] != base["in_range"]))
        sweep_v_max_diff = max(sweep_v_max_diff, max_diff_this_sample)
        sweep_flip_total += flips_this_sample
        sweep_results.append(
            {
                "seed": seed,
                "tick": tick,
                "epsilon_values_swept": _EPSILON_SWEEP_VALUES,
                "max_v_diff_vs_floor": max_diff_this_sample,
                "feasibility_flips_vs_floor": flips_this_sample,
            }
        )

    total_elapsed = time.perf_counter() - t_start
    summary = {
        "n_samples": len(_PREREGISTERED_SAMPLES),
        "sample_set": "all 50 seeds x ticks {0,1}, pre-registered",
        "obj_mismatch_abs_max": float(np.max(obj_mismatches)),
        "obj_mismatch_abs_mean": float(np.mean(obj_mismatches)),
        "obj_face_window_abs": fva_module._FVA_OBJ_FACE_NUMERIC_EPS_ABS,
        "window_margin_over_max_mismatch_orders_of_magnitude": (
            float(np.log10(fva_module._FVA_OBJ_FACE_NUMERIC_EPS_ABS / np.max(obj_mismatches)))
            if np.max(obj_mismatches) > 0
            else None
        ),
        "fx_sample_failure_count": fx_sample_failures,
        "fx_sample_failure_rate": fx_sample_failures / len(_PREREGISTERED_SAMPLES),
        "fx_col_dir_failure_count_conservative": fx_col_dir_failures,
        "fx_col_dir_total": fx_col_dir_total,
        "fx_vs_db_feasibility_flips": flip_count,
        "fx_vs_db_pairs_compared": total_pairs_compared,
        "fx_vs_db_max_v_diff": max_v_diff,
        "fx_vs_db_max_d_diff": max_d_diff,
        "epsilon_sweep_samples": len(_EPSILON_SWEEP_SAMPLES),
        "epsilon_sweep_values": _EPSILON_SWEEP_VALUES,
        "epsilon_sweep_feasibility_flips_total": sweep_flip_total,
        "epsilon_sweep_max_v_diff": sweep_v_max_diff,
        "total_wall_time_s": total_elapsed,
    }

    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUT_PATH.write_text(
        json.dumps(
            {"summary": summary, "per_sample": per_sample_results, "epsilon_sweep": sweep_results},
            indent=2,
        )
    )

    print()
    print("=" * 78)
    print("FX-vs-DB objective-face equivalence + window-sweep benchmark: SUMMARY")
    print("=" * 78)
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print(f"\nArtifact written to: {_OUT_PATH}")


if __name__ == "__main__":
    main()
