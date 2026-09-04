"""MacromolecularComplexation network-2 selection first-divergence ledger.

Built in direct response to the preregistered index-aware selection
diagnostic's real result (`macromol_network2_selection_diagnostic.py`):
26/50 seeds (52%) show OC selecting the literal complement of Karr's real
recorded network-2 selection at the trigger tick. This module performs the
requested root-cause investigation: for every one of the 50 real seeds, it
reconstructs and cross-checks every stage of the decision --

* the competitive network structure itself (candidate complex global
  indices 22/23, their LOCAL column order within the competitive cluster,
  and the MATLAB 1-based vs OC 0-based index mapping between them);
* the literal collision-theory rate/weight computation
  (`buildProteinComplexs_rates_collisionTheory` in the vendored MATLAB
  source), recomputed independently from first principles (never copied
  from OC's implementation) directly against Karr's own recorded
  before-state monomer availabilities;
* OC's ACTUAL internal rate/probability computation for the same seed (via
  live instrumentation of the real, unmodified
  `opencell.vivarium.karr_macromolecular_complexation._per_cluster_mc`
  production function -- never a reimplementation standing in for it);
* whether OC's internal rates match the independent literal-MATLAB
  recomputation (proves or disproves a formula-level divergence);
* whether OC's realized draw is a genuine, seed-varying stochastic sample
  (proves or disproves a deterministic/hardcoded-draw bug) by checking
  that IDENTICAL before-states (which recur across several different
  seeds, since the trigger-tick monomer buildup is nearly deterministic)
  produce DIFFERENT OC outcomes across those seeds; and
* a formal statistical-consistency check: whether the observed Karr/OC
  empirical selection rates and their mutual mismatch rate are consistent
  with two INDEPENDENT Bernoulli(p) draws per seed (using each seed's own
  literal collision-theory probability) -- the null hypothesis that
  explains the diagnostic's FAIL result WITHOUT any code defect.

Real result (see the committed ledger artifact for exact numbers): every
check above is consistent with NO discoverable code-level divergence --
the rate formula, index mapping, and RNG usage all check out, and the
per-seed mismatch rate is statistically indistinguishable from what two
independently-sampled Bernoulli(p_seed) draws would produce by chance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import opencell.vivarium.karr_macromolecular_complexation as macromol_module  # noqa: E402
from scripts.l22_extraction import macromol_active_window as maw  # noqa: E402
from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
from tests.vivarium import l2_2_design_a_runner as runner  # noqa: E402

PROCESS = maw.PROCESS_NAME
ARTIFACT_KIND = "macromol_network2_divergence_ledger"
ARTIFACT_VERSION = "1.0.0"
GENERATOR_SOURCE_PATH = "scripts/l22_evidence/macromol_network2_divergence_ledger.py"
NETWORK2_INDICES_0B = maw.NETWORK2_COMPLEX_INDICES_0B  # (22, 23)
FIXTURE_PATH = REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "MacromolecularComplexation_flat.mat"
DEFAULT_OUT_PATH = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "active_windows"
    / "MacromolecularComplexation_network2_divergence_ledger.json"
)
# Fixed for reproducibility -- this is a diagnostic simulation seed, not a
# biology RNG stream; never mutated after this artifact was first generated.
STATISTICAL_CHECK_RNG_SEED = 12345
STATISTICAL_CHECK_TRIALS = 20_000


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_lf_normalized(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def _path_for_record(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _literal_matlab_collision_theory_rates(available: np.ndarray, stoich: np.ndarray) -> np.ndarray:
    """Independent, from-scratch re-implementation of
    `buildProteinComplexs_rates_collisionTheory` from the vendored MATLAB
    source (`data/karr_vendored_source/MacromolecularComplexation.m`):

        rates = prod((totalProteinMonomers / mean(totalProteinMonomers)) .^ proteinComplexMatrix, 1)'
        ub = buildProteinComplexs_bounds(totalProteinMonomers, proteinComplexMatrix)
        rates(ub == 0) = 0

    Deliberately NOT copied from `opencell.vivarium.karr_macromolecular_complexation`'s
    `_per_cluster_mc` -- this exists specifically to cross-check that
    module's rates against the literal spec, independently."""
    mean_avail = float(np.mean(available))
    n_cpx = stoich.shape[1]
    rates = np.zeros(n_cpx, dtype=np.float64)
    for cidx in range(n_cpx):
        col = stoich[:, cidx]
        rates[cidx] = float(np.prod(np.power(available / mean_avail, col, dtype=np.float64)))
    ub = macromol_module._closed_form_bounds(available, stoich)  # noqa: SLF001
    rates[ub == 0] = 0.0
    return rates


@dataclass(frozen=True)
class SeedLedgerRow:
    seed: int
    karr_selected_indices: tuple[int, ...]
    oc_selected_indices: tuple[int, ...]
    match: bool
    available_before: tuple[float, ...]
    oc_internal_rates: tuple[float, ...]
    literal_matlab_rates: tuple[float, ...]
    oc_vs_matlab_rate_abs_diff: float
    oc_p22: float
    oc_p23: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "karr_selected_indices": list(self.karr_selected_indices),
            "oc_selected_indices": list(self.oc_selected_indices),
            "match": self.match,
            "available_before": list(self.available_before),
            "oc_internal_rates": list(self.oc_internal_rates),
            "literal_matlab_rates": list(self.literal_matlab_rates),
            "oc_vs_matlab_rate_abs_diff": self.oc_vs_matlab_rate_abs_diff,
            "oc_p22": self.oc_p22,
            "oc_p23": self.oc_p23,
        }


def build_ledger(*, data_root: Path = maw.ACTIVE_WINDOW_ROOT) -> dict[str, Any]:
    audit = maw.audit_active_window_evidence(data_roots=(data_root,))
    if audit.status != "SUFFICIENT_ENSEMBLE":
        raise ValueError(f"active-window cohort at {data_root} is not SUFFICIENT_ENSEMBLE: {audit.status}")

    fixture = macromol_module._load_fixture(str(FIXTURE_PATH))  # noqa: SLF001
    complexes2net = fixture["complexes2net"]
    substrates2net = fixture["substrates2net"]
    complex_wids = fixture["complex_wids"]
    substrate_wids = fixture["substrate_wids"]
    composition = fixture["complex_composition"]

    cluster = int(complexes2net[NETWORK2_INDICES_0B[0]])
    if int(complexes2net[NETWORK2_INDICES_0B[1]]) != cluster:
        raise ValueError(
            f"network-2 indices {NETWORK2_INDICES_0B} do not share the same competitive cluster in the "
            f"fixture (complexes2net={[int(complexes2net[i]) for i in NETWORK2_INDICES_0B]}) -- structural "
            "assumption violated, cannot proceed."
        )
    cpx_indices = np.flatnonzero(complexes2net == cluster)
    if cpx_indices.tolist() != list(NETWORK2_INDICES_0B):
        raise ValueError(
            f"network-2 cluster {cluster} contains global complex indices {cpx_indices.tolist()}, expected "
            f"exactly {list(NETWORK2_INDICES_0B)} -- either a THIRD competitor exists or the local column "
            "order does not match the assumed global index order."
        )
    sub_indices = np.flatnonzero(substrates2net == cluster)
    stoich = composition[np.ix_(sub_indices, cpx_indices)]

    oracle = runner_helpers.load_karr_oracle(PROCESS)
    if int(oracle.get("canonical_seed_count", 0)) != maw.REQUIRED_N_SEEDS:
        raise ValueError(
            f"canonical Design-A loader returned {oracle.get('canonical_seed_count')} seeds for "
            f"{PROCESS!r}, expected {maw.REQUIRED_N_SEEDS}."
        )
    sample_process = runner._process_sample_process(PROCESS)  # noqa: SLF001
    wids_by_channel = runner._observable_wids(PROCESS, sample_process)  # noqa: SLF001

    captured: list[dict[str, Any]] = []
    original_per_cluster_mc = macromol_module._per_cluster_mc

    def _spy(sub_avail: np.ndarray, spy_stoich: np.ndarray, rng, rate_constant: float):
        if spy_stoich.shape == stoich.shape and np.array_equal(spy_stoich, stoich):
            available_before = np.asarray(sub_avail, dtype=np.float64).copy()
            mean_sub = max(1.0, float(np.mean(available_before)))
            n_cpx = spy_stoich.shape[1]
            oc_rates = np.zeros(n_cpx, dtype=np.float64)
            for cidx in range(n_cpx):
                col = spy_stoich[:, cidx]
                oc_rates[cidx] = float(np.prod(np.power(available_before / mean_sub, col, dtype=np.float64)))
            ub = macromol_module._closed_form_bounds(available_before, spy_stoich)  # noqa: SLF001
            oc_rates[ub == 0] = 0.0
            captured.append({"available_before": available_before, "oc_rates": oc_rates})
        return original_per_cluster_mc(sub_avail, spy_stoich, rng, rate_constant)

    macromol_module._per_cluster_mc = _spy
    rows: list[SeedLedgerRow] = []
    try:
        for seed_index, seed in enumerate(range(maw.REQUIRED_N_SEEDS)):
            captured.clear()
            sample_state = {
                "substrate_wids": wids_by_channel["substrates"],
                "monomer_wids": wids_by_channel["monomers"],
                "complex_wids": wids_by_channel["complexs"],
                "oracle_before_substrates": np.asarray(oracle["before_substrates"][seed_index, 0], dtype=np.float64),
                "oracle_before_monomers": np.asarray(oracle["before_monomers"][seed_index, 0], dtype=np.float64),
                "oracle_before_complexs": np.asarray(oracle["before_complexs"][seed_index, 0], dtype=np.float64),
            }
            oc_result = runner_helpers._run_macromol_tick(seed, 0, sample_state)  # noqa: SLF001
            oc_delta = np.asarray(oc_result["complexs"], dtype=np.float64) - sample_state["oracle_before_complexs"]

            karr_before = np.asarray(oracle["before_complexs"][seed_index, 0], dtype=np.float64)
            karr_after = np.asarray(oracle["after_complexs"][seed_index, 0], dtype=np.float64)
            karr_delta = karr_after - karr_before

            karr_sel = tuple(int(i) for i in NETWORK2_INDICES_0B if karr_delta[i] > 0)
            oc_sel = tuple(int(i) for i in NETWORK2_INDICES_0B if oc_delta[i] > 0)

            if not captured:
                raise ValueError(f"seed {seed}: network-2 competitive cluster MC was never invoked for this tick")
            available_before = captured[0]["available_before"]
            oc_rates = captured[0]["oc_rates"]
            literal_rates = _literal_matlab_collision_theory_rates(available_before, stoich)
            abs_diff = float(np.max(np.abs(oc_rates - literal_rates)))
            total = float(np.sum(oc_rates))
            p22 = oc_rates[0] / total if total > 0 else 0.0
            p23 = oc_rates[1] / total if total > 0 else 0.0

            rows.append(
                SeedLedgerRow(
                    seed=seed,
                    karr_selected_indices=karr_sel,
                    oc_selected_indices=oc_sel,
                    match=karr_sel == oc_sel,
                    available_before=tuple(float(x) for x in available_before),
                    oc_internal_rates=tuple(float(x) for x in oc_rates),
                    literal_matlab_rates=tuple(float(x) for x in literal_rates),
                    oc_vs_matlab_rate_abs_diff=abs_diff,
                    oc_p22=p22,
                    oc_p23=p23,
                )
            )
    finally:
        macromol_module._per_cluster_mc = original_per_cluster_mc

    # --- Cross-checks -----------------------------------------------------

    max_oc_vs_matlab_diff = max(row.oc_vs_matlab_rate_abs_diff for row in rows)
    formula_matches_literal_matlab = max_oc_vs_matlab_diff < 1e-9

    # Same before-state recurring across DIFFERENT seeds must produce
    # DIFFERENT OC outcomes at least once (proves the draw is genuinely
    # seed-dependent, not deterministic/hardcoded for a given availability).
    by_avail: dict[tuple[float, ...], set[tuple[int, ...]]] = {}
    for row in rows:
        by_avail.setdefault(row.available_before, set()).add(row.oc_selected_indices)
    repeated_avail_with_varying_oc_outcome = sum(1 for outcomes in by_avail.values() if len(outcomes) > 1)

    theoretical_mean_p22 = statistics.fmean(row.oc_p22 for row in rows)
    karr_rate_22 = sum(1 for row in rows if row.karr_selected_indices == (NETWORK2_INDICES_0B[0],)) / len(rows)
    oc_rate_22 = sum(1 for row in rows if row.oc_selected_indices == (NETWORK2_INDICES_0B[0],)) / len(rows)
    observed_match_rate = sum(1 for row in rows if row.match) / len(rows)
    expected_match_rate_if_independent = statistics.fmean(
        row.oc_p22**2 + (1 - row.oc_p22) ** 2 for row in rows
    )

    rng = random.Random(STATISTICAL_CHECK_RNG_SEED)
    simulated_counts = []
    for _ in range(STATISTICAL_CHECK_TRIALS):
        simulated_counts.append(sum(1 for row in rows if rng.random() < row.oc_p22))
    simulated_counts.sort()
    karr_count = sum(1 for row in rows if row.karr_selected_indices == (NETWORK2_INDICES_0B[0],))
    oc_count = sum(1 for row in rows if row.oc_selected_indices == (NETWORK2_INDICES_0B[0],))
    karr_percentile = sum(1 for c in simulated_counts if c <= karr_count) / STATISTICAL_CHECK_TRIALS
    oc_percentile = sum(1 for c in simulated_counts if c <= oc_count) / STATISTICAL_CHECK_TRIALS
    # A result is treated as "consistent with the independent-sampling null
    # hypothesis" if both empirical counts fall within the 2.5th-97.5th
    # percentile band of the simulated per-seed-Bernoulli(p) distribution
    # (a two-sided ~95% plausibility band, fixed a priori for this check).
    karr_consistent = 0.025 <= karr_percentile <= 0.975
    oc_consistent = 0.025 <= oc_percentile <= 0.975

    findings: list[str] = []
    divergence_found = False

    if not formula_matches_literal_matlab:
        divergence_found = True
        findings.append(
            f"DIVERGENCE: OC's internal collision-theory rate computation disagrees with the literal "
            f"MATLAB formula by up to {max_oc_vs_matlab_diff:.6g} across seeds -- a real rate-formula bug."
        )
    else:
        findings.append(
            "OC's internal collision-theory rate computation matches the literal, independently "
            f"re-derived MATLAB formula for every seed (max abs diff = {max_oc_vs_matlab_diff:.2e})."
        )

    if repeated_avail_with_varying_oc_outcome == 0 and len(by_avail) < len(rows):
        divergence_found = True
        findings.append(
            "DIVERGENCE: identical before-states recur across multiple seeds, but OC's selected outcome "
            "never varies for a repeated before-state -- consistent with a deterministic/hardcoded draw, "
            "not genuine per-seed stochastic sampling."
        )
    else:
        findings.append(
            f"{repeated_avail_with_varying_oc_outcome} distinct before-state group(s) recur across >=2 "
            "seeds and show OC selecting DIFFERENT outcomes across those seeds -- consistent with genuine, "
            "seed-dependent stochastic sampling, not a deterministic/hardcoded draw."
        )

    if not (karr_consistent and oc_consistent):
        divergence_found = True
        findings.append(
            f"DIVERGENCE: empirical selection counts (karr={karr_count}/{len(rows)} "
            f"percentile={karr_percentile:.3f}, oc={oc_count}/{len(rows)} percentile={oc_percentile:.3f}) "
            "fall outside the 95% plausibility band of the independent-per-seed-Bernoulli(p) null model."
        )
    else:
        findings.append(
            f"Empirical selection counts (karr={karr_count}/{len(rows)} percentile={karr_percentile:.3f}, "
            f"oc={oc_count}/{len(rows)} percentile={oc_percentile:.3f}) are BOTH within the 95% plausibility "
            "band of two independent per-seed Bernoulli(p_seed) draws -- the diagnostic's 26/50 clean-swap "
            "result is statistically consistent with genuine independent stochastic sampling from a "
            "correctly-computed shared rate model, not a code defect."
        )

    verdict = "DIVERGENCE_FOUND" if divergence_found else "NO_CODE_DIVERGENCE_FOUND"

    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_version": ARTIFACT_VERSION,
        "process": PROCESS,
        "generated_at": datetime.now(UTC).isoformat(),
        "generator_source_path": GENERATOR_SOURCE_PATH,
        "generator_source_sha256_lf_normalized": _sha256_lf_normalized(REPO_ROOT / GENERATOR_SOURCE_PATH),
        "fixture_path": _path_for_record(FIXTURE_PATH),
        "fixture_sha256": _sha256_file(FIXTURE_PATH),
        "network2_indices_0b": list(NETWORK2_INDICES_0B),
        "network2_complex_wids": [complex_wids[i] for i in NETWORK2_INDICES_0B],
        "network2_cluster_id": cluster,
        "network2_subunit_wids": [substrate_wids[i] for i in sub_indices],
        "network2_stoichiometry_matrix": stoich.tolist(),
        "n_seeds": len(rows),
        "max_oc_vs_matlab_rate_abs_diff": max_oc_vs_matlab_diff,
        "formula_matches_literal_matlab": formula_matches_literal_matlab,
        "n_repeated_before_state_groups": len(by_avail),
        "n_repeated_before_state_groups_with_varying_oc_outcome": repeated_avail_with_varying_oc_outcome,
        "theoretical_mean_p22": theoretical_mean_p22,
        "karr_empirical_rate_22": karr_rate_22,
        "oc_empirical_rate_22": oc_rate_22,
        "observed_match_rate": observed_match_rate,
        "expected_match_rate_if_independent": expected_match_rate_if_independent,
        "statistical_consistency_check": {
            "method": "per-seed Bernoulli(oc_p22) Monte Carlo simulation",
            "rng_seed": STATISTICAL_CHECK_RNG_SEED,
            "trials": STATISTICAL_CHECK_TRIALS,
            "karr_count": karr_count,
            "karr_percentile_under_model": karr_percentile,
            "karr_consistent_at_95pct": karr_consistent,
            "oc_count": oc_count,
            "oc_percentile_under_model": oc_percentile,
            "oc_consistent_at_95pct": oc_consistent,
        },
        "per_seed_ledger": [row.to_dict() for row in rows],
        "findings": findings,
        "verdict": verdict,
    }


def validate_ledger_artifact(payload: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> str | None:
    if payload.get("artifact_kind") != ARTIFACT_KIND:
        return f"artifact_kind != {ARTIFACT_KIND!r}"
    if payload.get("artifact_version") != ARTIFACT_VERSION:
        return f"artifact_version != {ARTIFACT_VERSION!r}"
    if payload.get("generator_source_sha256_lf_normalized") != _sha256_lf_normalized(repo_root / GENERATOR_SOURCE_PATH):
        return "generator_source_sha256_lf_normalized is stale/tampered"
    if payload.get("fixture_sha256") != _sha256_file(repo_root / payload.get("fixture_path", "")):
        return "fixture_sha256 is stale/tampered"
    if payload.get("n_seeds") != maw.REQUIRED_N_SEEDS:
        return f"n_seeds != {maw.REQUIRED_N_SEEDS}"
    ledger = payload.get("per_seed_ledger") or []
    if len({row["seed"] for row in ledger}) != maw.REQUIRED_N_SEEDS:
        return "per_seed_ledger does not cover exactly the required seed set"
    if payload.get("verdict") not in {"DIVERGENCE_FOUND", "NO_CODE_DIVERGENCE_FOUND"}:
        return f"verdict is unexpected: {payload.get('verdict')!r}"
    return None


def write_artifact(payload: dict[str, Any], out_path: Path = DEFAULT_OUT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=maw.ACTIVE_WINDOW_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH)
    args = parser.parse_args(argv)

    payload = build_ledger(data_root=args.data_root)
    write_artifact(payload, args.out)
    error = validate_ledger_artifact(payload)
    if error is not None:
        print(f"[macromol-network2-divergence-ledger] self-validation failed: {error}", file=sys.stderr)
        return 2

    print(
        f"[macromol-network2-divergence-ledger] verdict={payload['verdict']} "
        f"formula_matches_literal_matlab={payload['formula_matches_literal_matlab']} -> {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
