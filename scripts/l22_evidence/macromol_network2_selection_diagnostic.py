"""Preregistered index-aware network-2 complex-selection diagnostic for
MacromolecularComplexation.

## Why this exists

The Design-A per-tick harness's primary-channel metric for
MacromolecularComplexation (`primary_channel=complexs`,
`primary_distance=per_tick_vector_w1_mean`) computes a per-COMPONENT
Wasserstein-1 distance between OC's and Karr's `complexs` delta
distributions, independently for each of the 28 complex indices, then
averages across components. This is **index-aware in the sense that each
component gets its own W1 statistic**, but it is NOT aware of which SEED
produced which component's nonzero value: the statistic is computed from
the marginal distribution of each component's value across the 50-seed
ensemble, never from the joint (seed, index) pairing.

For network-2's two competitively-formed complexes (indices 22/23, 0-based
-- `NETWORK2_COMPLEX_INDICES_0B` in `scripts/l22_extraction/
macromol_active_window.py`), this creates exactly the blind spot the Opus
review flagged: if OC and Karr select index 22 vs 23 at EXACTLY the same
population-level rate (e.g. each fires 22 on roughly half the seeds and 23
on the other half) but with the WRONG SEED-BY-SEED PAIRING -- i.e. OC picks
23 on seeds where Karr picked 22 and vice versa, a literal "vector
permutation" of the same underlying multiset -- the per-component marginal
W1 distance for BOTH components would read approximately 0 (each
component's marginal distribution looks the same whether or not the
seed-pairing is right), silently passing a real selection-fidelity bug.

## What this diagnostic actually checks

For each of the 50 real active-window seeds (each already validated by
`scripts.l22_extraction.macromol_active_window.validate_seed_window` to
have a genuine, source-faithful network-2 formation event at the window's
first captured tick -- see that module's docstring for the full
preregistration contract), this diagnostic:

1. reads Karr's ACTUAL recorded selection at the trigger tick (which of
   {22, 23} has a positive `complexs` delta -- already hash-bound,
   validated data, no re-computation needed);
2. runs ONE OpenCell MacromolecularComplexation tick, fed with Karr's own
   recorded before-state at that exact tick (the same technique the
   shared Design-A per-tick harness already uses for every process --
   `_run_macromol_tick`), and reads OC's selection from the resulting
   `complexs` delta; then
3. compares the two selections PER INDEX (22 and 23 separately, never
   pooled into one "network-2 fired" indicator), building a 2x2
   contingency table per index across the 50-seed ensemble, and flags any
   seed where OC selects the index-22/23 COMPLEMENT of what Karr selected
   (a literal per-seed index swap -- the direct "vector permutation"
   signature).

## Preregistered verdict rule (fixed BEFORE this diagnostic was ever run
against real data; never adjusted after seeing results)

FAIL (reject literal network-2 selection fidelity) if EITHER:

  (a) `n_clean_index_swaps > 0` for either index -- i.e. at least one seed
      where OC's selection is the EXACT complement of Karr's real
      selection (OC picks 23 when Karr picked 22 alone, or vice versa).
      This is the direct, zero-tolerance "vector permutation" detector: a
      structurally faithful port has no mechanism to produce this pattern
      even under genuine stochastic competition, since OC is fed Karr's
      own before-state and the competition is resource-driven, not a coin
      flip independent of that state.

  (b) `abs(oc_marginal_rate[idx] - karr_marginal_rate[idx]) > 0.10` for
      either index -- a 10-percentage-point a priori tolerance on N=50
      (chosen for genuine sampling noise at this ensemble size; a real
      index-mapping/mislabeling bug would be expected to produce a much
      larger swing, not a borderline one).

PASS otherwise.

This diagnostic is NON-GATING for the shared `evidence_index.json` row
(never consumed by `scripts/l22_evidence/verdict.py` or `generator.py`)
but IS authoritative for any claim of literal network-2 selection
fidelity -- see this closeout's STATUS doc for how the two are reconciled
honestly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction import macromol_active_window as maw  # noqa: E402
from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
from tests.vivarium import l2_2_design_a_runner as runner  # noqa: E402

PROCESS = maw.PROCESS_NAME
GENERATOR_SOURCE_PATH = "scripts/l22_evidence/macromol_network2_selection_diagnostic.py"
ARTIFACT_KIND = "macromol_network2_selection_diagnostic"
ARTIFACT_VERSION = "1.0.0"
NETWORK2_INDICES_0B = maw.NETWORK2_COMPLEX_INDICES_0B  # (22, 23)
# Preregistered thresholds -- see module docstring. Do not change these after
# looking at real diagnostic output; a change requires a NEW artifact_version
# and an explicit note of why, exactly like any other preregistered gate.
MAX_MARGINAL_RATE_ABS_DIFF = 0.10
MAX_CLEAN_INDEX_SWAPS = 0
DEFAULT_OUT_PATH = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "active_windows"
    / "MacromolecularComplexation_network2_selection_diagnostic.json"
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_lf_normalized(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def _path_for_record(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


@dataclass(frozen=True)
class SeedSelectionRecord:
    seed: int
    trigger_tick: int
    karr_selected_indices: tuple[int, ...]
    oc_selected_indices: tuple[int, ...]
    oc_after_complexs_at_indices: dict[int, float]
    karr_after_complexs_at_indices: dict[int, float]

    @property
    def exact_identity_match(self) -> bool:
        return set(self.karr_selected_indices) == set(self.oc_selected_indices)

    def clean_swap_for(self, idx: int, other_idx: int) -> bool:
        """True iff Karr selected EXACTLY {idx} and OC selected EXACTLY
        {other_idx} -- a literal index swap, not merely "OC also selected
        something else" or "OC selected both"."""
        return set(self.karr_selected_indices) == {idx} and set(self.oc_selected_indices) == {other_idx}

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "trigger_tick": self.trigger_tick,
            "karr_selected_indices": list(self.karr_selected_indices),
            "oc_selected_indices": list(self.oc_selected_indices),
            "oc_after_complexs_at_indices": {str(k): v for k, v in self.oc_after_complexs_at_indices.items()},
            "karr_after_complexs_at_indices": {str(k): v for k, v in self.karr_after_complexs_at_indices.items()},
            "exact_identity_match": self.exact_identity_match,
        }


def _selected_indices(delta: np.ndarray, indices: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(int(idx) for idx in indices if idx < delta.size and delta[idx] > 0)


def compute_seed_selection_record(
    seed: int,
    *,
    data_root: Path,
    oracle: dict[str, Any],
    seed_index: int,
    wids_by_channel: dict[str, list[str]],
) -> SeedSelectionRecord:
    """Compute one seed's Karr-vs-OC network-2 selection pair.

    Karr's selection is read directly from the already-validated,
    hash-bound trace file (never recomputed/derived) via
    `validate_seed_window`, which ALSO re-verifies the full active-window
    preregistration contract for this seed as a side effect -- so a
    tampered or drifted trace fails here, not silently.

    OC's selection is computed by running exactly ONE real
    MacromolecularComplexation tick (`_run_macromol_tick`, the same
    function the shared Design-A per-tick harness itself calls), fed with
    Karr's own recorded before-state at the trigger tick -- never OC's own
    prior output, never a synthetic/derived state.
    """
    path = maw._seed_trace_path(seed, data_root)  # noqa: SLF001
    window = maw.validate_seed_window(seed, path)

    sample_state = {
        "substrate_wids": wids_by_channel["substrates"],
        "monomer_wids": wids_by_channel["monomers"],
        "complex_wids": wids_by_channel["complexs"],
        "oracle_before_substrates": np.asarray(oracle["before_substrates"][seed_index, 0], dtype=np.float64),
        "oracle_before_monomers": np.asarray(oracle["before_monomers"][seed_index, 0], dtype=np.float64),
        "oracle_before_complexs": np.asarray(oracle["before_complexs"][seed_index, 0], dtype=np.float64),
    }
    oc_result = runner_helpers._run_macromol_tick(seed, 0, sample_state)  # noqa: SLF001
    oc_after_complexs = np.asarray(oc_result["complexs"], dtype=np.float64)
    oc_before_complexs = sample_state["oracle_before_complexs"]
    oc_delta = oc_after_complexs - oc_before_complexs

    karr_before_complexs = np.asarray(oracle["before_complexs"][seed_index, 0], dtype=np.float64)
    karr_after_complexs = np.asarray(oracle["after_complexs"][seed_index, 0], dtype=np.float64)
    karr_delta = karr_after_complexs - karr_before_complexs

    oc_selected = _selected_indices(oc_delta, NETWORK2_INDICES_0B)
    karr_selected = _selected_indices(karr_delta, NETWORK2_INDICES_0B)
    if set(window.trigger_complex_indices_0b) != set(karr_selected):
        raise ValueError(
            f"seed {seed}: recomputed Karr network-2 selection {karr_selected} does not match "
            f"the validated trace metadata's trigger_complex_indices_0b={window.trigger_complex_indices_0b} "
            "-- refusing to proceed with an internally inconsistent oracle read."
        )

    return SeedSelectionRecord(
        seed=seed,
        trigger_tick=window.trigger_tick,
        karr_selected_indices=karr_selected,
        oc_selected_indices=oc_selected,
        oc_after_complexs_at_indices={idx: float(oc_after_complexs[idx]) for idx in NETWORK2_INDICES_0B},
        karr_after_complexs_at_indices={idx: float(karr_after_complexs[idx]) for idx in NETWORK2_INDICES_0B},
    )


@dataclass
class PerIndexStats:
    index: int
    n_true_positive: int = 0  # both OC and Karr select this index
    n_false_positive: int = 0  # OC selects, Karr does not
    n_false_negative: int = 0  # Karr selects, OC does not
    n_true_negative: int = 0  # neither selects
    n_clean_swap: int = 0  # Karr selects ONLY this index, OC selects ONLY the other

    @property
    def n(self) -> int:
        return self.n_true_positive + self.n_false_positive + self.n_false_negative + self.n_true_negative

    @property
    def oc_marginal_rate(self) -> float:
        return (self.n_true_positive + self.n_false_positive) / self.n if self.n else 0.0

    @property
    def karr_marginal_rate(self) -> float:
        return (self.n_true_positive + self.n_false_negative) / self.n if self.n else 0.0

    @property
    def marginal_rate_abs_diff(self) -> float:
        return abs(self.oc_marginal_rate - self.karr_marginal_rate)

    @property
    def per_index_match_rate(self) -> float:
        return (self.n_true_positive + self.n_true_negative) / self.n if self.n else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "n": self.n,
            "n_true_positive": self.n_true_positive,
            "n_false_positive": self.n_false_positive,
            "n_false_negative": self.n_false_negative,
            "n_true_negative": self.n_true_negative,
            "n_clean_swap": self.n_clean_swap,
            "oc_marginal_rate": self.oc_marginal_rate,
            "karr_marginal_rate": self.karr_marginal_rate,
            "marginal_rate_abs_diff": self.marginal_rate_abs_diff,
            "per_index_match_rate": self.per_index_match_rate,
        }


def build_diagnostic(*, data_root: Path = maw.ACTIVE_WINDOW_ROOT) -> dict[str, Any]:
    audit = maw.audit_active_window_evidence(data_roots=(data_root,))
    if audit.status != "SUFFICIENT_ENSEMBLE":
        raise ValueError(
            f"active-window cohort at {data_root} is not a complete, valid 50-seed ensemble: "
            f"status={audit.status} deficit={audit.deficit}"
        )

    env_var = runner_helpers.process_oracle_root_env_var(PROCESS)
    previous_env = os.environ.get(env_var)
    os.environ[env_var] = str(data_root)
    try:
        oracle = runner_helpers.load_karr_oracle(PROCESS)
    finally:
        if previous_env is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = previous_env

    sample_process = runner._process_sample_process(PROCESS)  # noqa: SLF001
    wids_by_channel = runner._observable_wids(PROCESS, sample_process)  # noqa: SLF001

    records: list[SeedSelectionRecord] = []
    for seed_index, seed in enumerate(range(maw.REQUIRED_N_SEEDS)):
        records.append(
            compute_seed_selection_record(
                seed,
                data_root=data_root,
                oracle=oracle,
                seed_index=seed_index,
                wids_by_channel=wids_by_channel,
            )
        )

    per_index_stats = {idx: PerIndexStats(index=idx) for idx in NETWORK2_INDICES_0B}
    other_index = {NETWORK2_INDICES_0B[0]: NETWORK2_INDICES_0B[1], NETWORK2_INDICES_0B[1]: NETWORK2_INDICES_0B[0]}
    for record in records:
        karr_set = set(record.karr_selected_indices)
        oc_set = set(record.oc_selected_indices)
        for idx in NETWORK2_INDICES_0B:
            stats = per_index_stats[idx]
            karr_has = idx in karr_set
            oc_has = idx in oc_set
            if karr_has and oc_has:
                stats.n_true_positive += 1
            elif oc_has and not karr_has:
                stats.n_false_positive += 1
            elif karr_has and not oc_has:
                stats.n_false_negative += 1
            else:
                stats.n_true_negative += 1
            if record.clean_swap_for(idx, other_index[idx]):
                stats.n_clean_swap += 1

    n_clean_index_swaps_total = sum(stats.n_clean_swap for stats in per_index_stats.values())
    max_marginal_rate_abs_diff = max(stats.marginal_rate_abs_diff for stats in per_index_stats.values())
    n_exact_identity_matches = sum(1 for record in records if record.exact_identity_match)

    fail_reasons: list[str] = []
    if n_clean_index_swaps_total > MAX_CLEAN_INDEX_SWAPS:
        swap_seeds = [
            record.seed
            for record in records
            if any(record.clean_swap_for(idx, other_index[idx]) for idx in NETWORK2_INDICES_0B)
        ]
        fail_reasons.append(
            f"n_clean_index_swaps_total={n_clean_index_swaps_total} > {MAX_CLEAN_INDEX_SWAPS} "
            f"(seeds exhibiting a literal index swap: {swap_seeds})"
        )
    for idx in NETWORK2_INDICES_0B:
        stats = per_index_stats[idx]
        if stats.marginal_rate_abs_diff > MAX_MARGINAL_RATE_ABS_DIFF:
            fail_reasons.append(
                f"index {idx}: marginal_rate_abs_diff={stats.marginal_rate_abs_diff:.4f} > "
                f"{MAX_MARGINAL_RATE_ABS_DIFF} (oc_rate={stats.oc_marginal_rate:.4f}, "
                f"karr_rate={stats.karr_marginal_rate:.4f})"
            )

    verdict = "FAIL" if fail_reasons else "PASS"

    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_version": ARTIFACT_VERSION,
        "process": PROCESS,
        "generated_at": datetime.now(UTC).isoformat(),
        "generator_source_path": GENERATOR_SOURCE_PATH,
        "generator_source_sha256_lf_normalized": _sha256_lf_normalized(REPO_ROOT / GENERATOR_SOURCE_PATH),
        "gating": (
            "NON_GATING for the shared L2.2 evidence_index.json row (never consumed by "
            "scripts/l22_evidence/verdict.py or generator.py); AUTHORITATIVE for any claim "
            "of literal network-2 (complexs indices 22/23) selection fidelity."
        ),
        "network2_indices_0b": list(NETWORK2_INDICES_0B),
        "preregistered_thresholds": {
            "max_clean_index_swaps": MAX_CLEAN_INDEX_SWAPS,
            "max_marginal_rate_abs_diff": MAX_MARGINAL_RATE_ABS_DIFF,
        },
        "active_window_root": _path_for_record(data_root),
        "n_seeds": len(records),
        "n_exact_identity_matches": n_exact_identity_matches,
        "exact_identity_match_rate": n_exact_identity_matches / len(records) if records else 0.0,
        "n_clean_index_swaps_total": n_clean_index_swaps_total,
        "max_marginal_rate_abs_diff_observed": max_marginal_rate_abs_diff,
        "per_index_stats": {str(idx): stats.to_dict() for idx, stats in per_index_stats.items()},
        "seed_records": [record.to_dict() for record in records],
        "verdict": verdict,
        "fail_reasons": fail_reasons,
    }


def validate_diagnostic_artifact(payload: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> str | None:
    if payload.get("artifact_kind") != ARTIFACT_KIND:
        return f"artifact_kind != {ARTIFACT_KIND!r}"
    if payload.get("artifact_version") != ARTIFACT_VERSION:
        return f"artifact_version != {ARTIFACT_VERSION!r}"
    if payload.get("process") != PROCESS:
        return f"process != {PROCESS!r}"
    if payload.get("generator_source_path") != GENERATOR_SOURCE_PATH:
        return "generator_source_path drifted"
    if payload.get("generator_source_sha256_lf_normalized") != _sha256_lf_normalized(repo_root / GENERATOR_SOURCE_PATH):
        return "generator_source_sha256_lf_normalized is stale/tampered"
    thresholds = payload.get("preregistered_thresholds") or {}
    if thresholds.get("max_clean_index_swaps") != MAX_CLEAN_INDEX_SWAPS:
        return "preregistered_thresholds.max_clean_index_swaps drifted from the pinned value"
    if thresholds.get("max_marginal_rate_abs_diff") != MAX_MARGINAL_RATE_ABS_DIFF:
        return "preregistered_thresholds.max_marginal_rate_abs_diff drifted from the pinned value"
    if payload.get("n_seeds") != maw.REQUIRED_N_SEEDS:
        return f"n_seeds != {maw.REQUIRED_N_SEEDS}"
    seed_records = payload.get("seed_records") or []
    if len({record["seed"] for record in seed_records}) != maw.REQUIRED_N_SEEDS:
        return "seed_records does not cover exactly the required seed set"
    # Mechanically re-derive the verdict from the recorded per-index stats
    # rather than trusting the stored `verdict` string -- same "never trust
    # the stored verdict" discipline as scripts/l22_evidence/verdict.py.
    n_swaps = payload.get("n_clean_index_swaps_total")
    max_diff = payload.get("max_marginal_rate_abs_diff_observed")
    if not isinstance(n_swaps, int) or not isinstance(max_diff, (int, float)):
        return "n_clean_index_swaps_total / max_marginal_rate_abs_diff_observed missing or invalid"
    expected_verdict = "FAIL" if (n_swaps > MAX_CLEAN_INDEX_SWAPS or max_diff > MAX_MARGINAL_RATE_ABS_DIFF) else "PASS"
    if payload.get("verdict") != expected_verdict:
        return f"stored verdict {payload.get('verdict')!r} does not match mechanically re-derived {expected_verdict!r}"
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

    payload = build_diagnostic(data_root=args.data_root)
    write_artifact(payload, args.out)
    error = validate_diagnostic_artifact(payload)
    if error is not None:
        print(f"[macromol-network2-selection-diagnostic] self-validation failed: {error}", file=sys.stderr)
        return 2

    print(
        f"[macromol-network2-selection-diagnostic] verdict={payload['verdict']} "
        f"n_seeds={payload['n_seeds']} n_clean_index_swaps_total={payload['n_clean_index_swaps_total']} "
        f"max_marginal_rate_abs_diff_observed={payload['max_marginal_rate_abs_diff_observed']:.4f} "
        f"-> {args.out}",
        file=sys.stderr,
    )
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
