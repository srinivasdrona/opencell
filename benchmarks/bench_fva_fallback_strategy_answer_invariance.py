"""D5 correction (2026-07-29, Opus5 narrow REJECT #2): direct same-LP
cross-fallback-strategy answer-invariance benchmark.

The previous provenance record (superseded by this round's correction, see
`opencell/provenance/llm_interactions.jsonl`) incorrectly cited the
FX-vs-DB objective-face-equivalence benchmark
(`bench_fva_fx_vs_db_objective_face_equivalence.py`) as proof that the
fallback-cascade reordering (af67307) "changed zero answers". That is a
category error: FX-vs-DB compares two DIFFERENT LP constructions (exact
equality face vs windowed face). It says nothing about whether DIFFERENT
FALLBACK STRATEGIES solving the IDENTICAL LP (same face, same window, same
everything) can disagree. This script directly measures that, instead of
relying solely on the LP-strong-duality argument (which only guarantees the
shared OBJECTIVE VALUE is identical across GLP_OPT-terminating strategies,
not that every individual variable's optimum on a possibly-degenerate face
is unique).

IMPORTANT FINDING (see tests/m1/test_fva_perf.py::
test_different_fallback_strategies_agree_on_identical_lp_feasibility_outcome
for the single-sample discovery that motivated this script): on the
standard regression fixture sample (seed=0, tick=1), forcing `adv_pse`
(primary, current shipped first attempt) vs `adv_pse_presolve` (current
shipped last-resort strategy) to run ALONE on the IDENTICAL production LP
found 2/1755 substrate*compartment pairs where the resulting feasibility
classification actually DIFFERS. This directly falsifies the previous,
overclaimed "cascade reordering cannot change the mathematical answer" text
in fva.py's CASCADE ORDERING comment (also corrected in this round) --
strong duality guarantees the objective VALUE, not every basic variable's
value, is invariant across alternate optima on a degenerate LP face.

Pre-registered sample set (fixed BEFORE running this script): a systematic,
bounded SUBSET of the full 250-sample N50xM20 grid used by
`bench_fva_fx_vs_db_objective_face_equivalence.py` -- every 5th seed
(0, 5, 10, ..., 45; 10 seeds) x the same predeclared 5 ticks {0, 1, 5, 9,
16} = 50 samples. This is 1/5 the size of the full FX-vs-DB benchmark
because this script performs up to 5x the solver work per sample (each of
the 5 `_FVA_FALLBACK_STRATEGIES` entries is forced to run ALONE, with no
fallback, so a slow/degenerate column can consume the full `tm_lim` budget
under EVERY strategy rather than succeeding on the first or second
attempt as the production cascade does) -- kept bounded/practical per the
task's "keep test runtime practical" instruction rather than attempting a
5x-cost full sweep.

For each sample and each of the 5 strategies (forced alone via a
monkeypatched `_FVA_FALLBACK_STRATEGIES = (strategy,)`, exactly like the
unit test), this script:
  1. Solves the IDENTICAL production DB-windowed LP/reaction_subset.
  2. Records whether that strategy alone reaches GLP_OPT for every required
     column, or raises (skipped from comparison, tallied separately -- not
     evidence against invariance, since the shipped cascade never accepts a
     failing strategy).
  3. Projects v_min/v_max through `substrate_delta_range_from_fva` +
     the exact in-range tolerance check the L2.2 gate uses, using the SAME
     real pre/post substrate states as the oracle for that (seed, tick).
  4. Compares the resulting feasibility mask across every PAIRWISE
     combination of strategies that converged alone on this sample
     (C(n,2) pairs, not merely each vs a single reference strategy) --
     this way a disagreement between two non-reference strategies cannot
     be silently missed.

Reports, per sample and in aggregate: which strategies converged alone,
every pairwise strategy-pair flip count, total pairs compared, and the max
per-sample flip count/rate. Persists a full per-sample JSON artifact under
`benchmarks/artifacts/` (gitignored) plus a compact tracked summary under
`docs/phase_f/l2_2_design_a/evidence/` (D4 pattern).

Run via:
    bin\\oc-py benchmarks\\bench_fva_fallback_strategy_answer_invariance.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "tests" / "vivarium"))
sys.path.insert(0, str(_REPO_ROOT / "benchmarks"))

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
from bench_fva_fx_vs_db_objective_face_equivalence import (  # noqa: E402
    _feasibility,
    _sample_inputs,
    _sha256_lf,
)

from opencell.m1 import fva as fva_module  # noqa: E402
from opencell.m1.fva import fva_range  # noqa: E402
from opencell.m1.karr_metabolism_writeback import KarrWritebackFixture  # noqa: E402

_WRITEBACK_FIXTURE_MAT = (
    _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
)

# Pre-registered, bounded subset (see module docstring): every 5th seed x the
# same 5 predeclared ticks used by the FX-vs-DB benchmark = 50 samples.
_TICKS: tuple[int, ...] = (0, 1, 5, 9, 16)
_PREREGISTERED_SAMPLES: list[tuple[int, int]] = [
    (seed, tick) for seed in range(0, 50, 5) for tick in _TICKS
]

_OUT_PATH = (
    _REPO_ROOT / "benchmarks" / "artifacts" / "fva_fallback_strategy_answer_invariance.json"
)
_TRACKED_SUMMARY_PATH = (
    _REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "evidence"
    / "fva_fallback_strategy_answer_invariance_summary.json"
)


def _strategy_masks(S, rhs, c, lb, ub, biomass_value_star, reaction_subset):
    """Force each `_FVA_FALLBACK_STRATEGIES` entry to run ALONE on the
    identical production LP; return {name: (v_min, v_max)} for strategies
    that converge, plus {name: error} for those that don't."""
    v_ranges: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    skipped: dict[str, str] = {}
    original_strategies = fva_module._FVA_FALLBACK_STRATEGIES
    try:
        for strategy in original_strategies:
            fva_module._FVA_FALLBACK_STRATEGIES = (strategy,)
            try:
                v_min, v_max = fva_range(
                    S, rhs, c, lb, ub, biomass_value_star=biomass_value_star,
                    reaction_subset=reaction_subset,
                )
            except RuntimeError as exc:
                skipped[strategy[0]] = str(exc)
                continue
            v_ranges[strategy[0]] = (v_min, v_max)
    finally:
        fva_module._FVA_FALLBACK_STRATEGIES = original_strategies
    return v_ranges, skipped


def main() -> None:
    fixture = KarrWritebackFixture.from_mat(_WRITEBACK_FIXTURE_MAT)
    oracle = runner_helpers.load_karr_oracle("Metabolism")

    per_sample_results: list[dict] = []
    total_pairs_compared = 0
    total_flips = 0
    max_sample_flips = 0
    max_sample_flip_key = None
    strategy_convergence_counts: dict[str, int] = {}
    strategy_skip_counts: dict[str, int] = {}

    t_start = time.perf_counter()
    for seed, tick in _PREREGISTERED_SAMPLES:
        (
            model, lb, ub, biomass_value_star, growth_per_s, pre_sub, post_sub, reaction_subset,
        ) = _sample_inputs(oracle, fixture, seed, tick)
        S = np.asarray(model.S, dtype=np.float64)
        rhs = np.asarray(model.RHS, dtype=np.float64)
        c = np.asarray(model.obj, dtype=np.float64)

        v_ranges, skipped = _strategy_masks(
            S, rhs, c, lb, ub, biomass_value_star, reaction_subset
        )
        for name in v_ranges:
            strategy_convergence_counts[name] = strategy_convergence_counts.get(name, 0) + 1
        for name in skipped:
            strategy_skip_counts[name] = strategy_skip_counts.get(name, 0) + 1

        masks: dict[str, np.ndarray] = {}
        for name, (v_min, v_max) in v_ranges.items():
            _d_min, _d_max, in_range = _feasibility(
                v_min, v_max, fixture, growth_per_s, pre_sub, post_sub
            )
            masks[name] = in_range

        sample_flip_pairs: dict[str, int] = {}
        sample_max_flips = 0
        if len(masks) >= 2:
            # True all-pairs comparison (C(n,2) pairs, n = strategies
            # converged alone on this sample), matching the module
            # docstring's claim and the harder GT-fixture unit test in
            # tests/m1/test_fva_perf.py -- NOT merely reference-vs-others,
            # which would silently miss a disagreement between two
            # non-reference strategies.
            names = sorted(masks)
            for i, name_a in enumerate(names):
                for name_b in names[i + 1 :]:
                    n_diff = int(np.count_nonzero(masks[name_a] != masks[name_b]))
                    sample_flip_pairs[f"{name_a}_vs_{name_b}"] = n_diff
                    total_pairs_compared += int(masks[name_a].size)
                    total_flips += n_diff
                    sample_max_flips = max(sample_max_flips, n_diff)

        per_sample_results.append(
            {
                "seed": seed,
                "tick": tick,
                "converged_strategies": sorted(v_ranges),
                "skipped_strategies": sorted(skipped),
                "flip_pairs": sample_flip_pairs,
                "sample_max_flips": sample_max_flips,
            }
        )
        if sample_max_flips > max_sample_flips:
            max_sample_flips = sample_max_flips
            max_sample_flip_key = f"seed={seed},tick={tick}"

    wall_s = time.perf_counter() - t_start

    summary = {
        "n_samples": len(_PREREGISTERED_SAMPLES),
        "ticks": list(_TICKS),
        "seeds": sorted({s for s, _t in _PREREGISTERED_SAMPLES}),
        "total_pairs_compared": total_pairs_compared,
        "total_flips": total_flips,
        "flip_rate": (total_flips / total_pairs_compared) if total_pairs_compared else None,
        "max_sample_flips": max_sample_flips,
        "max_sample_flip_key": max_sample_flip_key,
        "strategy_convergence_counts": strategy_convergence_counts,
        "strategy_skip_counts": strategy_skip_counts,
        "wall_time_s": wall_s,
    }

    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    full_artifact = {"summary": summary, "per_sample": per_sample_results}
    full_text = json.dumps(full_artifact, indent=2, default=str)
    _OUT_PATH.write_text(full_text)
    # Hash the in-memory text (always LF, since json.dumps never emits CRLF)
    # rather than reading the file back from disk: Path.write_text() on
    # Windows translates '\n' -> os.linesep ('\r\n') in text mode, which
    # would make this hash depend on the local platform/checkout rather
    # than being a stable function of the artifact's logical content.
    full_sha256 = hashlib.sha256(full_text.encode("utf-8")).hexdigest()

    script_sha256 = _sha256_lf(Path(__file__))
    tracked_summary = {
        "summary": summary,
        "full_artifact_path": str(_OUT_PATH.relative_to(_REPO_ROOT)).replace("\\", "/"),
        "full_artifact_sha256": full_sha256,
        "generated_by_script": str(Path(__file__).relative_to(_REPO_ROOT)).replace("\\", "/"),
        "generated_by_script_sha256": script_sha256,
        "reproduction_command": (
            "bin\\oc-py benchmarks\\bench_fva_fallback_strategy_answer_invariance.py"
        ),
    }
    _TRACKED_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TRACKED_SUMMARY_PATH.write_text(json.dumps(tracked_summary, indent=2, default=str))

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
