"""H12 CONDITION_GATED evidence for MacromolecularComplexation network 2.

This module produces a single, machine-checkable, NON-GATING evidence
artifact that mechanically binds three already-accepted pieces of evidence
into one honest, PORTABLE, NON-OPERATIVE disposition CANDIDATE for network
2's `network_ge2_fires` required branch (see `scripts/l22_evidence/h12.py`'s
`REQUIRED_BRANCHES["MacromolecularComplexation"]`):

  1. The accepted H12 artifact (`docs/phase_f/l2_2_design_a/h12/
     MacromolecularComplexation_h12.json`, verdict `H12_OBSERVED_REGIME`,
     814/814 nontrivial exact-match, `exact_match_rate == 1.0`). These two
     figures are **NETWORK-1-ONLY**: network 2 (`network_ge2_fires`)
     contributes exactly ZERO nontrivial samples to that count, by the
     predictor's own construction (a network>=2 sample can only be
     `regime_valid=True` in the all-`ub==0` trivial case -- see
     `h12.predict_macromolecular_complexation`'s docstring). This module
     never lets that 100% figure be read as exact-match evidence for
     network 2's own behavior; every reference to it below is explicitly
     annotated with a pinned network-1-only scope string, and
     `validate_condition_gated_artifact` hard-rejects an artifact that
     drops or alters that annotation.
  2. A freshly re-derived natural-population census (this module,
     `compute_natural_network2_census`) that independently recomputes the
     `ub==0` claim directly from the SAME hash-verified oracle trace
     population (the `oracle_seed_file_sha256` map is required to be
     byte-identical, key-for-key, to the one already recorded in artifact
     (1)), and additionally identifies the limiting substrate
     (`MG_429_MONOMER`, PTS system E1, fixture index 192) as the UNIQUE
     limiting substrate across all 10,000 (complex x sample) evaluations
     -- see `docs/phase_f/l2_2_design_a/h12/
     MACROMOLECULARCOMPLEXATION_NETWORK2_E1_PROVENANCE.md` for the full
     provenance investigation.
  3. The accepted, non-gating perturbation artifact
     (`docs/phase_f/l2_2_design_a/h12/perturbation/
     MacromolecularComplexation_h12_perturbation.json`, verdict
     `H12_PERTURBATION_OBSERVED_STOCHASTIC`) -- conditioning ONLY the E1
     pool value (0 -> 40, no stoichiometry/constant changes) makes
     network 2's genuine Monte Carlo competition loop
     (`buildProteinComplexs_montecarlokinetic`) fire for real, across 50
     independent seeds, with all structural invariants holding.

======================================================================
WHAT THIS ARTIFACT DOES NOT CLAIM (turn-3 hardening, post Opus-5 rejection)
======================================================================
- It does NOT claim the natural-window absence of `ub>0` proves the
  branch is unreachable at any lifecycle stage. `lifecycle_reachability_
  status` is pinned to the literal string `"UNRESOLVED"` -- never
  `"REACHABLE"`/`"UNREACHABLE"`/a boolean -- because whether E1 ever
  becomes nonzero at a LATER tick (a `tick_offset>0` extraction, out of
  scope here) is genuinely unknown from evidence available in this
  worktree. "Unobserved in the sampled window" ALONE is explicitly
  insufficient for a terminal disposition
  (`unobserved_in_window_alone_is_insufficient: true`) -- what makes this
  branch permanently non-`H12_CONFIRMED`-eligible, independent of the
  lifecycle question, is the SEPARATE, independently-verified structural
  fact that its underlying mechanism is genuine Monte Carlo (see
  `structural_argument`). Both conditions are recorded; neither alone
  is treated as sufficient.
- It does NOT unblock the current row. `unblocks_current_row` and
  `unblocks_l2_5` are both pinned `false`. `maintainer_decision_made` is
  pinned `false`. `classification` is pinned to the literal
  `"CONDITION_GATED_CANDIDATE"` string -- never `"CONDITION_GATED"`
  (enacted), `"H12_CONFIRMED"`, `"H12_OBSERVED_REGIME"`, or `"PASS"`.
- It does NOT modify `verdict.py`'s evidence gate, `PROCESS_CATALOG.yaml`,
  `h12_evidence_index.json`, or `generator.py`, and is NOT consumed by
  `h12.validate_h12_support`. See
  `docs/phase_f/l2_2_design_a/h12/CONDITION_GATED_TAXONOMY_PROPOSAL.md`
  for the (separately scoped, not-yet-implemented, not-enacted) future
  taxonomy change this artifact is evidence FOR.
- It does NOT run MATLAB/Octave/any extraction launcher. The natural
  census reads already-extracted, already-accepted oracle `.mat` traces
  (the same ones `scripts/l22_evidence/h12.py` already reads for the
  accepted H12 artifact); the perturbation reference reads only the
  already-committed, already-accepted perturbation JSON produced by a
  prior task's real Octave execution.

The oracle `.mat` trace files themselves remain gitignored (like all raw
Karr trace data in this repo, see `.gitignore`); this module's output
artifact (docs/phase_f/l2_2_design_a/h12/condition_gated/
MacromolecularComplexation_h12_condition_gated.json) is the tracked,
portable evidence -- the raw traces need not be present on disk to
validate that committed artifact (`validate_condition_gated_artifact`
below never reads a raw oracle trace; only `compute_natural_network2_census`,
the one-time producer step, does).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import h12, h12_perturbation  # noqa: E402

PROCESS = "MacromolecularComplexation"
NETWORK = 2
REQUIRED_BRANCH = "network_ge2_fires"

OUT_DIR = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "condition_gated"
OUT_PATH = OUT_DIR / f"{PROCESS}_h12_condition_gated.json"

ACCEPTED_H12_ARTIFACT_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / f"{PROCESS}_h12.json"
ACCEPTED_PERTURBATION_ARTIFACT_PATH = (
    REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "perturbation" / f"{PROCESS}_h12_perturbation.json"
)
E1_PROVENANCE_DOC_PATH = (
    REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "MACROMOLECULARCOMPLEXATION_NETWORK2_E1_PROVENANCE.md"
)
TAXONOMY_PROPOSAL_DOC_PATH = (
    REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "CONDITION_GATED_TAXONOMY_PROPOSAL.md"
)

ARTIFACT_KIND = "h12_condition_gated_evidence"
ARTIFACT_VERSION = "2.0.0"
GENERATOR_SOURCE_PATH = "scripts/l22_evidence/h12_condition_gated.py"
_THIS_FILE = Path(__file__).resolve()

# Hard-pinned catalog N/M (turn-3: independent of h12.CATALOG_N_M so that a
# silent upstream catalog change cannot silently widen/shrink what this
# artifact accepts -- this module's own expectation must ALSO hold).
EXPECTED_CATALOG_N_SEEDS = 50
EXPECTED_CATALOG_M_TICKS = 100
CATALOG_N_SEEDS, CATALOG_M_TICKS = h12.CATALOG_N_M[PROCESS]
if (CATALOG_N_SEEDS, CATALOG_M_TICKS) != (EXPECTED_CATALOG_N_SEEDS, EXPECTED_CATALOG_M_TICKS):
    raise RuntimeError(
        f"h12.CATALOG_N_M[{PROCESS!r}] changed to {(CATALOG_N_SEEDS, CATALOG_M_TICKS)!r}, no longer "
        f"({EXPECTED_CATALOG_N_SEEDS}, {EXPECTED_CATALOG_M_TICKS}) -- this module's hard-pinned natural "
        "census claims assume the catalog's original N/M; re-derive by hand before trusting this module"
    )

# --- Pinned taxonomy/metadata constants -------------------------------------
CLASSIFICATION = "CONDITION_GATED_CANDIDATE"
GATING = (
    "NON_GATING -- proposes a disposition for reviewer/maintainer sign-off only; never claims "
    "H12_CONFIRMED; not consumed by scripts/l22_evidence/verdict.py, generator.py, or "
    "h12_evidence_index.json."
)
EXPECTED_NOT_CONSUMED_BY = [
    "scripts/l22_evidence/verdict.py",
    "scripts/l22_evidence/generator.py",
    "docs/phase_f/l2_2_design_a/h12/h12_evidence_index.json",
    "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml",
]
EXPECTED_ANTI_LAUNDERING_ATTESTATION = {
    "census_inputs": ["states_before", "static_fixture_params"],
    "perturbation_reference_is_precomputed_and_read_only": True,
    "no_sut_import": True,
    "no_result_json_access": True,
    "no_new_extraction": True,
    "no_matlab_or_octave_run_this_change": True,
}

# --- Pinned network-2 layout constants (independently hardcoded; the fixture-
# derived layout below is cross-checked against these, and any drift -- fixture
# change OR tampered payload -- is a hard fail, never a soft-trusted value).
EXPECTED_SUBSTRATE_INDICES_0B = [23, 37, 42, 192]
EXPECTED_COMPLEX_INDICES_0B = [22, 23]
EXPECTED_STOICH_BLOCK = [[1, 1], [2, 0], [0, 2], [2, 2]]
EXPECTED_SUBSTRATE_WIDS = ["MG_041_MONOMER", "MG_062_MONOMER", "MG_069_MONOMER", "MG_429_MONOMER"]
EXPECTED_COMPLEX_WIDS = ["MG_041_062_429_PENTAMER", "MG_041_069_429_PENTAMER"]
EXPECTED_E1_INDEX_0B = 192
EXPECTED_E1_WID = "MG_429_MONOMER"
EXPECTED_E1_LOCAL_INDEX = EXPECTED_SUBSTRATE_WIDS.index(EXPECTED_E1_WID)  # == 3

# --- Pinned natural-census claim values (the actual empirical claim this
# artifact makes about the accepted 50x100 oracle population).
EXPECTED_UB_ALL_ZERO = [0, 0]
EXPECTED_CANDIDATE_TICKS = 0

CENSUS_REQUIRED_FIELDS = frozenset(
    {
        "n_seeds",
        "m_ticks",
        "total_samples",
        "candidate_ticks_ub_gt_0",
        "ub_min",
        "ub_max",
        "ub_mean",
        "pool_min",
        "pool_max",
        "pool_mean",
        "pool_fraction_zero",
        "limiting_substrate_argmin_counts",
        "limiting_substrate_0b",
        "limiting_substrate_whole_cell_model_id",
        "oracle_seed_file_sha256",
        "oracle_manifest_cross_check",
    }
)

# --- Pinned Karr source citation (superset of h12.KARR_SOURCE_CITATIONS[PROCESS]
# because this artifact additionally cites the Monte Carlo functions the
# structural argument depends on).
EXPECTED_KARR_LINE_RANGES = [[290, 314], [334, 392]]
EXPECTED_KARR_SYMBOLS = [
    "evolveState",
    "buildProteinComplexs_montecarlokinetic",
    "buildProteinComplexs_rates_collisionTheory",
    "buildProteinComplexs_bounds",
]

# --- Pinned structural-argument citation (the Monte Carlo functions alone).
EXPECTED_STRUCTURAL_ARG_LINE_RANGES = [[334, 357], [360, 386]]
EXPECTED_STRUCTURAL_ARG_SYMBOLS = [
    "buildProteinComplexs_montecarlokinetic",
    "buildProteinComplexs_rates_collisionTheory",
]
STRUCTURAL_ARGUMENT_CLAIM = (
    "network>=2 competition is genuinely Monte Carlo: buildProteinComplexs_montecarlokinetic "
    "draws randStream.rand() once per iteration of its while-loop (line 349) to select which "
    "complex builds next; there is no closed form for that selection sequence. H12_CONFIRMED "
    "is therefore inapplicable to this unit by construction -- independent of how much "
    "additional natural-population sampling or conditioning occurs, and independent of "
    "whether the lifecycle_reachability_status question below is ever resolved. This is a "
    "SEPARATE, independently-sufficient reason for non-H12_CONFIRMED-eligibility from the "
    "natural-window observation above -- neither the natural-window absence of ub>0 alone, nor "
    "this structural fact alone, is being conflated with the other; both are recorded because "
    "the taxonomy proposal this artifact supports requires both."
)

# --- Pinned network-1-only annotation strings for the accepted H12 artifact's
# process-wide 814/814 exact-match figures (turn-3: these numbers must never
# be read, even implicitly, as network-2 exact-match evidence).
NONTRIVIAL_SAMPLE_COUNT_SCOPE = (
    "network_1_fires ONLY -- network 2 (network_ge2_fires) contributes exactly 0 nontrivial "
    "samples to this count by predictor construction (see structural_argument); this figure is "
    "NOT exact-match evidence for network 2's own behavior."
)
EXACT_MATCH_RATE_SCOPE = (
    "network_1_fires ONLY -- see nontrivial_sample_count_scope; network 2 has zero exact-match "
    "evidence of its own in the natural population."
)

# --- Pinned lifecycle/proposal-semantics constants (turn-3 hardening).
LIFECYCLE_REACHABILITY_STATUS = "UNRESOLVED"
LIFECYCLE_REACHABILITY_NOTE = (
    "Whether E1 (MG_429_MONOMER) ever becomes nonzero at a later tick / different lifecycle stage "
    "in the real Karr model is UNRESOLVED -- not determined false, not determined true -- from "
    "evidence available in this worktree. scripts/matlab/extract_per_process_traces_v2.m's own "
    "docstring documents a tick_offset mechanism precisely for late-activating species (citing "
    "RibosomeAssembly's first assembly at ~tick 238); the accepted trace here was extracted at "
    "tick_offset=0. A tick_offset>0 re-extraction is the only way to resolve this and is explicitly "
    "out of scope for this artifact (no new extraction authorized). This artifact makes NO claim of "
    "structural or lifecycle unreachability in either direction; 'unobserved in the sampled window' "
    "is recorded as an observed FACT (see natural_census), not as a resolution of this question."
)

CLASSIFICATION_NOTE = (
    "Proposed CANDIDATE disposition for MacromolecularComplexation/network_ge2_fires, pending "
    "reviewer (Opus 5) sign-off and a SEPARATE, later, serialized change to actually enact a "
    "CONDITION_GATED taxonomy value in verdict.py/PROCESS_CATALOG.yaml/h12_evidence_index.json -- "
    "see CONDITION_GATED_TAXONOMY_PROPOSAL.md. No maintainer decision is being made in this branch. "
    "This artifact and its classification field are NOT consumed by any of those files in this "
    "change, and do NOT unblock the current row or L2.5 -- see unblocks_current_row/unblocks_l2_5."
)


def _sha256_file(path: Path) -> str:
    return h12._sha256_file(path)


def _sha256_lf_normalized(path: Path) -> str:
    return h12._sha256_lf_normalized(path)


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Network-2 layout (derived purely from the tracked fixture -- always
# available, no oracle trace required).
# ---------------------------------------------------------------------------


def get_network2_layout() -> dict:
    """Derive network 2's substrate/complex indices, stoichiometry block,
    and WholeCellModelIDs directly from the tracked fixture. This is the
    SAME derivation `h12.predict_macromolecular_complexation` performs
    (filtering `complexs2complexNetworks`/`substrates2complexNetworks` on
    the network id) -- re-implemented here, independently, rather than
    imported, so a future accidental edit to the predictor's filtering
    logic cannot silently drag this evidence module's claims along with it
    unnoticed (the two are cross-checked against each other in
    `tests/scripts/test_h12_condition_gated.py`, not merged into one
    function). This function does NOT enforce the EXPECTED_* pins itself
    (kept pure/testable); `_assert_pinned_layout` does that.
    """
    fixture = h12.load_fixture(PROCESS)
    struct, fixture_path = h12._mat_struct(PROCESS)
    sub_wids = h12._field(struct, "substrateWholeCellModelIDs").ravel()
    cx_wids = h12._field(struct, "complexWholeCellModelIDs").ravel()

    comp = fixture["complexComposition"]
    sub_net = fixture["substrates2complexNetworks"]
    cx_net = fixture["complexs2complexNetworks"]
    sub_idx = np.where(sub_net == NETWORK)[0]
    cx_idx = np.where(cx_net == NETWORK)[0]
    block = comp[np.ix_(sub_idx, cx_idx)].astype(np.float64)

    def _wid(arr, i: int) -> str:
        v = arr[i]
        return str(v[0]) if hasattr(v, "__len__") and not isinstance(v, str) else str(v)

    return {
        "fixture": fixture,
        "substrate_indices_0b": sub_idx.tolist(),
        "complex_indices_0b": cx_idx.tolist(),
        "stoichiometry_block": block.astype(np.int64).tolist(),
        "block": block,
        "substrate_whole_cell_model_ids": [_wid(sub_wids, i) for i in sub_idx.tolist()],
        "complex_whole_cell_model_ids": [_wid(cx_wids, i) for i in cx_idx.tolist()],
    }


def _assert_pinned_layout(layout: dict) -> None:
    """Producer-side hard pin: raise (never silently proceed) if the live
    fixture-derived layout has drifted from this module's independently
    hardcoded expectations. Mirrors the tamper-detection the validator
    performs on an already-written artifact, but at generation time.
    """
    checks = {
        "substrate_indices_0b": (layout["substrate_indices_0b"], EXPECTED_SUBSTRATE_INDICES_0B),
        "complex_indices_0b": (layout["complex_indices_0b"], EXPECTED_COMPLEX_INDICES_0B),
        "stoichiometry_block": (layout["stoichiometry_block"], EXPECTED_STOICH_BLOCK),
        "substrate_whole_cell_model_ids": (layout["substrate_whole_cell_model_ids"], EXPECTED_SUBSTRATE_WIDS),
        "complex_whole_cell_model_ids": (layout["complex_whole_cell_model_ids"], EXPECTED_COMPLEX_WIDS),
    }
    for name, (actual, expected) in checks.items():
        if actual != expected:
            raise ValueError(
                f"network2 layout {name} drifted from the pinned expected value: got {actual!r}, "
                f"expected {expected!r} -- fixture changed, or this module's pins are stale; "
                "investigate before regenerating"
            )


# ---------------------------------------------------------------------------
# Natural-population census (reads already-extracted, already-accepted
# oracle traces -- NO new extraction; one-time producer step only). This
# function never reads ACCEPTED_H12_ARTIFACT_PATH -- every hash/count below
# is independently recomputed from the raw oracle traces, not copied from
# the accepted artifact (no canonical-only reuse).
# ---------------------------------------------------------------------------


def compute_natural_network2_census(n_seeds: int = CATALOG_N_SEEDS, m_ticks: int = CATALOG_M_TICKS) -> dict:
    layout = get_network2_layout()
    sub_idx = np.array(layout["substrate_indices_0b"])
    block = layout["block"]
    n_complexes = block.shape[1]

    manifest_lookup = h12._load_oracle_manifest()
    oracle_seed_file_sha256: dict[str, str] = {}
    oracle_manifest_cross_check: dict[str, str] = {}

    all_ub = []
    all_pool = []
    limiting_counts = {i: 0 for i in range(len(sub_idx))}
    candidate_ticks = 0
    total_ticks = 0

    for seed in range(n_seeds):
        oracle_path = h12._resolve_oracle_path(PROCESS, seed)
        seed_sha = _sha256_file(oracle_path)
        oracle_seed_file_sha256[str(seed)] = seed_sha
        # Matches h12.run_h12's own relative-path convention exactly (relative to
        # ORACLE_ROOT.parent, NOT REPO_ROOT) -- required for manifest_lookup keys to match.
        rel_path = oracle_path.relative_to(h12.ORACLE_ROOT.parent).as_posix()
        oracle_manifest_cross_check[str(seed)] = h12.cross_check_oracle_manifest(
            PROCESS, rel_path, seed_sha, manifest_lookup
        )

        before, _after, _sha = h12.load_oracle_seed(PROCESS, seed, m_ticks)
        subs = before["substrates"].astype(np.float64)
        for t in range(subs.shape[0]):
            total_ticks += 1
            pool = subs[t, sub_idx]
            all_pool.append(pool)
            ub = h12_perturbation.compute_macromol_network2_ub(pool, block)
            all_ub.append(ub)
            if np.any(ub > 0):
                candidate_ticks += 1
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = np.where(block > 0, pool[:, None] / np.where(block > 0, block, 1.0), np.inf)
            argmin_idx = np.argmin(ratio, axis=0)
            for c in range(n_complexes):
                limiting_counts[int(argmin_idx[c])] += 1

    all_ub_arr = np.array(all_ub)
    all_pool_arr = np.array(all_pool)

    limiting_substrate_local = max(limiting_counts, key=lambda k: limiting_counts[k])
    limiting_substrate_0b = int(sub_idx[limiting_substrate_local])

    return {
        "n_seeds": n_seeds,
        "m_ticks": m_ticks,
        "total_samples": total_ticks,
        "candidate_ticks_ub_gt_0": int(candidate_ticks),
        "ub_min": all_ub_arr.min(axis=0).tolist(),
        "ub_max": all_ub_arr.max(axis=0).tolist(),
        "ub_mean": all_ub_arr.mean(axis=0).tolist(),
        "pool_min": all_pool_arr.min(axis=0).tolist(),
        "pool_max": all_pool_arr.max(axis=0).tolist(),
        "pool_mean": all_pool_arr.mean(axis=0).tolist(),
        "pool_fraction_zero": (all_pool_arr == 0).mean(axis=0).tolist(),
        "limiting_substrate_argmin_counts": {str(k): v for k, v in limiting_counts.items()},
        "limiting_substrate_0b": limiting_substrate_0b,
        "limiting_substrate_whole_cell_model_id": layout["substrate_whole_cell_model_ids"][limiting_substrate_local],
        "oracle_seed_file_sha256": oracle_seed_file_sha256,
        "oracle_manifest_cross_check": oracle_manifest_cross_check,
    }


def _assert_pinned_census_claims(census: dict) -> None:
    """Producer-side hard pin over the natural-census EMPIRICAL CLAIM this
    artifact makes -- raise if the freshly-recomputed census no longer
    supports it (never silently narrate around a changed reality)."""
    if census["n_seeds"] != EXPECTED_CATALOG_N_SEEDS or census["m_ticks"] != EXPECTED_CATALOG_M_TICKS:
        raise ValueError(
            f"natural census n_seeds/m_ticks ({census['n_seeds']!r}/{census['m_ticks']!r}) does not "
            f"cover the pinned catalog domain ({EXPECTED_CATALOG_N_SEEDS}/{EXPECTED_CATALOG_M_TICKS})"
        )
    if census["candidate_ticks_ub_gt_0"] != EXPECTED_CANDIDATE_TICKS:
        raise ValueError(
            f"natural census found {census['candidate_ticks_ub_gt_0']} candidate ticks with ub>0 -- the "
            "'natural regime never fires' premise of this artifact no longer holds; do not silently "
            "paper over this, investigate before regenerating"
        )
    if census["ub_min"] != EXPECTED_UB_ALL_ZERO or census["ub_max"] != EXPECTED_UB_ALL_ZERO:
        raise ValueError(f"natural census ub_min/ub_max no longer [0, 0]: {census['ub_min']!r}/{census['ub_max']!r}")
    if census["limiting_substrate_0b"] != EXPECTED_E1_INDEX_0B:
        raise ValueError(
            f"natural census limiting_substrate_0b ({census['limiting_substrate_0b']!r}) is no longer E1's "
            f"index ({EXPECTED_E1_INDEX_0B!r})"
        )
    if census["limiting_substrate_whole_cell_model_id"] != EXPECTED_E1_WID:
        raise ValueError("natural census limiting_substrate_whole_cell_model_id is no longer E1")
    e1_key = str(EXPECTED_E1_LOCAL_INDEX)
    argmin_counts = census["limiting_substrate_argmin_counts"]
    total_evaluations = census["n_seeds"] * census["m_ticks"] * len(EXPECTED_COMPLEX_INDICES_0B)
    if argmin_counts.get(e1_key) != total_evaluations:
        raise ValueError("E1 is no longer the UNIQUE limiting substrate in every (seed, tick, complex) evaluation")
    for key, count in argmin_counts.items():
        if key != e1_key and count != 0:
            raise ValueError(f"substrate local index {key!r} is limiting in {count} evaluations -- E1 not unique")
    if census["pool_fraction_zero"][EXPECTED_E1_LOCAL_INDEX] != 1.0:
        raise ValueError("natural census pool_fraction_zero at E1's index is no longer 1.0")
    if set(census["oracle_seed_file_sha256"].keys()) != {str(i) for i in range(EXPECTED_CATALOG_N_SEEDS)}:
        raise ValueError("natural census oracle_seed_file_sha256 does not cover exactly seeds 0..49")


# ---------------------------------------------------------------------------
# Artifact assembly
# ---------------------------------------------------------------------------


def build_condition_gated_artifact() -> dict:
    layout = get_network2_layout()
    _assert_pinned_layout(layout)
    fixture = layout["fixture"]
    census = compute_natural_network2_census(n_seeds=EXPECTED_CATALOG_N_SEEDS, m_ticks=EXPECTED_CATALOG_M_TICKS)
    _assert_pinned_census_claims(census)

    accepted_h12 = _load_json(ACCEPTED_H12_ARTIFACT_PATH)
    accepted_pert = _load_json(ACCEPTED_PERTURBATION_ARTIFACT_PATH)

    if accepted_h12.get("verdict") != "H12_OBSERVED_REGIME":
        raise ValueError(
            f"accepted H12 artifact verdict changed unexpectedly (got {accepted_h12.get('verdict')!r}); "
            "this condition-gated artifact's narrative assumes H12_OBSERVED_REGIME -- re-derive by hand "
            "before regenerating"
        )
    if accepted_pert.get("verdict") != "H12_PERTURBATION_OBSERVED_STOCHASTIC":
        raise ValueError(
            f"accepted perturbation artifact verdict changed unexpectedly "
            f"(got {accepted_pert.get('verdict')!r}); re-derive by hand before regenerating"
        )
    if census["oracle_seed_file_sha256"] != accepted_h12.get("oracle_seed_file_sha256"):
        raise ValueError(
            "freshly-recomputed natural census oracle hashes do not exactly match the accepted H12 "
            "artifact's oracle_seed_file_sha256 map -- different/re-extracted population; investigate "
            "before regenerating (this is NOT a canonical-only copy -- both are independently derived "
            "and must agree)"
        )

    karr_citation = {
        **h12.karr_source_citation(PROCESS),
        "line_ranges": EXPECTED_KARR_LINE_RANGES,
        "symbols": EXPECTED_KARR_SYMBOLS,
    }

    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_version": ARTIFACT_VERSION,
        "gating": GATING,
        "process": PROCESS,
        "network": NETWORK,
        "required_branch": REQUIRED_BRANCH,
        "required_branches_registry_ref": "scripts/l22_evidence/h12.py:REQUIRED_BRANCHES['MacromolecularComplexation']",
        "purpose": (
            "Mechanically bind (a) the accepted H12_OBSERVED_REGIME artifact's network-1-ONLY exact-match "
            "evidence (814/814, rate 1.0 -- see nontrivial_sample_count_scope/exact_match_rate_scope; "
            "network 2 contributes ZERO to these counts), (b) an independently re-derived "
            "natural-population census proving network 2's ub is [0, 0] on all 5000 accepted (seed, tick) "
            "samples with PTS-system E1 (MG_429_MONOMER, fixture index 192) as the UNIQUE limiting "
            "substrate, and (c) the accepted non-gating perturbation artifact proving the branch is "
            "structurally reachable (fires for real, invariants hold) once ONLY that one substrate is "
            "conditioned -- into a single, portable, NON-OPERATIVE evidence record supporting a proposed "
            "CONDITION_GATED_CANDIDATE disposition. This artifact does not resolve whether the natural "
            "branch could fire at a later lifecycle stage (lifecycle_reachability_status: UNRESOLVED) and "
            "does not, by itself, unblock the current row or L2.5. See "
            "MACROMOLECULARCOMPLEXATION_NETWORK2_E1_PROVENANCE.md for the full investigation and "
            "CONDITION_GATED_TAXONOMY_PROPOSAL.md for the (not-yet-implemented) taxonomy change this is "
            "evidence for."
        ),
        "karr_source_citation": karr_citation,
        "predictor_source_path": h12.EXPECTED_PREDICTOR_SOURCE_PATH,
        "predictor_source_sha256_lf_normalized": _sha256_lf_normalized(REPO_ROOT / h12.EXPECTED_PREDICTOR_SOURCE_PATH),
        "fixture_path": fixture["__fixture_path__"],
        "fixture_sha256": fixture["__fixture_sha256__"],
        "network2_layout": {
            "substrate_indices_0b": layout["substrate_indices_0b"],
            "complex_indices_0b": layout["complex_indices_0b"],
            "stoichiometry_block": layout["stoichiometry_block"],
            "substrate_whole_cell_model_ids": layout["substrate_whole_cell_model_ids"],
            "complex_whole_cell_model_ids": layout["complex_whole_cell_model_ids"],
        },
        "natural_census": census,
        "lifecycle_reachability_status": LIFECYCLE_REACHABILITY_STATUS,
        "lifecycle_reachability_note": LIFECYCLE_REACHABILITY_NOTE,
        "unobserved_in_window_alone_is_insufficient": True,
        "unblocks_current_row": False,
        "unblocks_l2_5": False,
        "maintainer_decision_made": False,
        "e1_provenance_ref": E1_PROVENANCE_DOC_PATH.relative_to(REPO_ROOT).as_posix(),
        "e1_provenance_ref_sha256_lf_normalized": _sha256_lf_normalized(E1_PROVENANCE_DOC_PATH),
        "accepted_h12_artifact_ref": {
            "path": ACCEPTED_H12_ARTIFACT_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256_lf_normalized": _sha256_lf_normalized(ACCEPTED_H12_ARTIFACT_PATH),
            "verdict": accepted_h12["verdict"],
            "nontrivial_sample_count": accepted_h12["nontrivial_sample_count"],
            "nontrivial_sample_count_scope": NONTRIVIAL_SAMPLE_COUNT_SCOPE,
            "exact_match_rate": accepted_h12["exact_match_rate"],
            "exact_match_rate_scope": EXACT_MATCH_RATE_SCOPE,
            "branches_confirmed": accepted_h12["branches_confirmed"],
            "missing_required_branches": accepted_h12["missing_required_branches"],
            "oracle_seed_file_sha256": accepted_h12["oracle_seed_file_sha256"],
        },
        "accepted_perturbation_artifact_ref": {
            "path": ACCEPTED_PERTURBATION_ARTIFACT_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256_lf_normalized": _sha256_lf_normalized(ACCEPTED_PERTURBATION_ARTIFACT_PATH),
            "verdict": accepted_pert["verdict"],
            "gating": accepted_pert["gating"],
            "target_branch": accepted_pert["target_branch"],
            "target_branch_exercised": accepted_pert["target_branch_exercised"],
            "ub": accepted_pert["ub"],
            "seeds_vary": accepted_pert["seeds_vary"],
            "distinct_outcome_count": accepted_pert["distinct_outcome_count"],
            "bound_violations": accepted_pert["bound_violations"],
            "mass_balance_violations": accepted_pert["mass_balance_violations"],
        },
        "structural_argument": {
            "claim": STRUCTURAL_ARGUMENT_CLAIM,
            "source_citation": {
                "file": f"{PROCESS}.m",
                "line_ranges": EXPECTED_STRUCTURAL_ARG_LINE_RANGES,
                "symbols": EXPECTED_STRUCTURAL_ARG_SYMBOLS,
            },
        },
        "classification": CLASSIFICATION,
        "classification_note": CLASSIFICATION_NOTE,
        "not_consumed_by": list(EXPECTED_NOT_CONSUMED_BY),
        "generator_source_path": GENERATOR_SOURCE_PATH,
        "generator_source_sha256_lf_normalized": _sha256_lf_normalized(_THIS_FILE),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anti_laundering_attestation": dict(EXPECTED_ANTI_LAUNDERING_ATTESTATION),
    }


def write_artifact(artifact: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=False)
        fh.write("\n")
    return OUT_PATH


# ---------------------------------------------------------------------------
# Validation (re-derivation without requiring raw oracle traces on disk --
# used both by tests and by any future consumer of this artifact). Mirrors
# `h12.validate_h12_support`'s hard-fail-no-soft-trust style: every claim,
# constant, and referenced tracked file is re-checked against a PINNED
# expectation or the CURRENT working tree, never taken on faith from the
# payload itself.
# ---------------------------------------------------------------------------


def validate_condition_gated_artifact(payload: dict) -> str | None:
    """Return None if every check passes, else a human-readable reason
    string for the first failure."""

    # --- Exact-pinned taxonomy/metadata (turn-3: hard exact-equality checks,
    # not substring/heuristic checks -- these alone reject PASS, an enacted
    # CONDITION_GATED, H12_OBSERVED_REGIME/H12_CONFIRMED masquerading as this
    # artifact's own classification, a network-1 substitution, a changed
    # required branch, a relaxed/omitted gating label, a false attestation,
    # or a missing/incomplete consumer list.)
    if payload.get("artifact_kind") != ARTIFACT_KIND:
        return f"unexpected artifact_kind (got {payload.get('artifact_kind')!r})"
    if payload.get("artifact_version") != ARTIFACT_VERSION:
        return f"unexpected artifact_version (got {payload.get('artifact_version')!r})"
    if payload.get("process") != PROCESS:
        return f"unexpected process (got {payload.get('process')!r})"
    if payload.get("network") != NETWORK:
        return f"network must be exactly {NETWORK!r} (got {payload.get('network')!r}) -- network1 substitution?"
    if payload.get("required_branch") != REQUIRED_BRANCH:
        return f"required_branch must be exactly {REQUIRED_BRANCH!r} (got {payload.get('required_branch')!r})"
    if payload.get("classification") != CLASSIFICATION:
        return (
            f"classification must be exactly {CLASSIFICATION!r} (got {payload.get('classification')!r}) -- "
            "this artifact must never claim PASS, an ENACTED CONDITION_GATED value, H12_CONFIRMED, or "
            "H12_OBSERVED_REGIME as its own classification"
        )
    if not str(payload.get("gating", "")).startswith("NON_GATING"):
        return f"gating must start with 'NON_GATING' (got {payload.get('gating')!r})"
    if payload.get("not_consumed_by") != EXPECTED_NOT_CONSUMED_BY:
        return (
            f"not_consumed_by must exactly equal the expected consumer list {EXPECTED_NOT_CONSUMED_BY!r} "
            f"(got {payload.get('not_consumed_by')!r})"
        )
    if payload.get("anti_laundering_attestation") != EXPECTED_ANTI_LAUNDERING_ATTESTATION:
        return (
            "anti_laundering_attestation does not exactly match the expected attestation "
            f"(got {payload.get('anti_laundering_attestation')!r}, "
            f"expected {EXPECTED_ANTI_LAUNDERING_ATTESTATION!r})"
        )

    # --- Lifecycle/proposal-semantics pins (turn-3: reject any attempt to
    # resolve the lifecycle question either way, or to claim this candidate
    # unblocks anything, or that a maintainer decision has been made here).
    if payload.get("lifecycle_reachability_status") != "UNRESOLVED":
        return (
            "lifecycle_reachability_status must be exactly 'UNRESOLVED' "
            f"(got {payload.get('lifecycle_reachability_status')!r}) -- this artifact must never resolve "
            "the natural-lifecycle-reachability question in either direction"
        )
    if payload.get("unobserved_in_window_alone_is_insufficient") is not True:
        return "unobserved_in_window_alone_is_insufficient must be exactly True"
    if payload.get("unblocks_current_row") is not False:
        return "unblocks_current_row must be exactly False -- this candidate cannot unblock the current row"
    if payload.get("unblocks_l2_5") is not False:
        return "unblocks_l2_5 must be exactly False -- this candidate cannot unblock L2.5"
    if payload.get("maintainer_decision_made") is not False:
        return "maintainer_decision_made must be exactly False -- no maintainer decision is made in this branch"

    # --- Fixture hash must match current disk (stale-fixture / drifted-tracked-file detection).
    fixture_path = REPO_ROOT / payload.get("fixture_path", "")
    if not fixture_path.is_file():
        return f"fixture_path does not exist on disk: {fixture_path}"
    if _sha256_file(fixture_path) != payload.get("fixture_sha256"):
        return "fixture_sha256 does not match current on-disk fixture (stale artifact)"

    # --- Network-2 layout must match BOTH the pinned expected constants (tamper/
    # network1-leakage detection) AND the current live fixture (staleness detection).
    recorded_layout = payload.get("network2_layout", {})
    pinned_layout_checks = {
        "substrate_indices_0b": EXPECTED_SUBSTRATE_INDICES_0B,
        "complex_indices_0b": EXPECTED_COMPLEX_INDICES_0B,
        "stoichiometry_block": EXPECTED_STOICH_BLOCK,
        "substrate_whole_cell_model_ids": EXPECTED_SUBSTRATE_WIDS,
        "complex_whole_cell_model_ids": EXPECTED_COMPLEX_WIDS,
    }
    for key, expected_value in pinned_layout_checks.items():
        if recorded_layout.get(key) != expected_value:
            return (
                f"network2_layout.{key} does not match the pinned expected value "
                f"(got {recorded_layout.get(key)!r}, expected {expected_value!r}) -- network1 leakage, "
                "tampered index mask, or hand-edited constants?"
            )
    layout = get_network2_layout()
    if layout["substrate_indices_0b"] != recorded_layout.get("substrate_indices_0b"):
        return "network2_layout.substrate_indices_0b no longer matches the real fixture"
    if layout["complex_indices_0b"] != recorded_layout.get("complex_indices_0b"):
        return "network2_layout.complex_indices_0b no longer matches the real fixture"
    if layout["stoichiometry_block"] != recorded_layout.get("stoichiometry_block"):
        return "network2_layout.stoichiometry_block no longer matches the real fixture (hand-edited constants?)"

    # --- Natural census: exact field/key schema (rejects a fabricated/stub census
    # with missing or extra fields), catalog N/M coverage, per-seed hash coverage/
    # uniqueness, manifest cross-check, and the pinned empirical claim values.
    census = payload.get("natural_census", {})
    if not isinstance(census, dict):
        return "natural_census missing or not a dict"
    if set(census.keys()) != CENSUS_REQUIRED_FIELDS:
        missing = CENSUS_REQUIRED_FIELDS - set(census.keys())
        extra = set(census.keys()) - CENSUS_REQUIRED_FIELDS
        return f"natural_census field schema mismatch (missing={sorted(missing)!r}, extra={sorted(extra)!r})"

    n_seeds = census.get("n_seeds")
    m_ticks = census.get("m_ticks")
    if not isinstance(n_seeds, int) or isinstance(n_seeds, bool) or n_seeds != EXPECTED_CATALOG_N_SEEDS:
        return (
            f"natural_census.n_seeds must equal the pinned catalog N ({EXPECTED_CATALOG_N_SEEDS!r}), "
            f"got {n_seeds!r} -- a shrunken/degenerate sample domain is not sufficient evidence"
        )
    if not isinstance(m_ticks, int) or isinstance(m_ticks, bool) or m_ticks != EXPECTED_CATALOG_M_TICKS:
        return (
            f"natural_census.m_ticks must equal the pinned catalog M ({EXPECTED_CATALOG_M_TICKS!r}), "
            f"got {m_ticks!r} -- a shrunken/degenerate sample domain is not sufficient evidence"
        )
    total_samples = census.get("total_samples")
    if (
        not isinstance(total_samples, int)
        or isinstance(total_samples, bool)
        or total_samples != n_seeds * m_ticks
    ):
        return f"natural_census.total_samples ({total_samples!r}) != n_seeds*m_ticks ({n_seeds * m_ticks!r})"

    seed_hashes = census.get("oracle_seed_file_sha256")
    cross_check = census.get("oracle_manifest_cross_check")
    expected_seed_keys = {str(i) for i in range(EXPECTED_CATALOG_N_SEEDS)}
    if not isinstance(seed_hashes, dict) or set(seed_hashes.keys()) != expected_seed_keys:
        return (
            "natural_census.oracle_seed_file_sha256 must cover exactly seeds "
            f"0..{EXPECTED_CATALOG_N_SEEDS - 1} (got keys {sorted((seed_hashes or {}).keys())!r})"
        )
    for seed_key, seed_hash in seed_hashes.items():
        if not isinstance(seed_hash, str) or not h12._SHA256_HEX_RE.match(seed_hash):
            return f"natural_census.oracle_seed_file_sha256[{seed_key!r}] is not a well-formed sha256 hex string"
    if len(set(seed_hashes.values())) != len(seed_hashes):
        return (
            "natural_census.oracle_seed_file_sha256 has duplicate hash values across distinct seed keys "
            "-- reused/stubbed trace, not 50 independent seeds"
        )
    if not isinstance(cross_check, dict) or set(cross_check.keys()) != expected_seed_keys:
        return (
            "natural_census.oracle_manifest_cross_check must cover exactly seeds "
            f"0..{EXPECTED_CATALOG_N_SEEDS - 1} (got keys {sorted((cross_check or {}).keys())!r})"
        )
    bad_cross_check = {k: v for k, v in cross_check.items() if v != "match"}
    if bad_cross_check:
        return f"natural_census.oracle_manifest_cross_check has non-'match' entries: {bad_cross_check}"

    # --- Exact equality of the census's oracle hash map to the on-disk accepted
    # H12 artifact's own map -- same 50-seed population, not a re-extraction, and
    # not a "canonical-only" reference that skips independent recomputation.
    on_disk_h12 = _load_json(ACCEPTED_H12_ARTIFACT_PATH) if ACCEPTED_H12_ARTIFACT_PATH.is_file() else {}
    if seed_hashes != on_disk_h12.get("oracle_seed_file_sha256"):
        return (
            "natural_census.oracle_seed_file_sha256 is not exactly equal to the on-disk accepted H12 "
            "artifact's oracle_seed_file_sha256 map (different/re-extracted population)"
        )

    # --- Pinned empirical claim values: nonzero E1/ub substitution or a wrong
    # limiter must fail, not silently pass through as "close enough".
    if census.get("candidate_ticks_ub_gt_0") != EXPECTED_CANDIDATE_TICKS:
        return (
            f"natural_census.candidate_ticks_ub_gt_0 ({census.get('candidate_ticks_ub_gt_0')!r}) != "
            f"{EXPECTED_CANDIDATE_TICKS!r} -- the natural-regime-never-fires premise no longer holds"
        )
    if census.get("ub_min") != EXPECTED_UB_ALL_ZERO or census.get("ub_max") != EXPECTED_UB_ALL_ZERO:
        return (
            f"natural_census.ub_min/ub_max ({census.get('ub_min')!r}/{census.get('ub_max')!r}) != "
            f"{EXPECTED_UB_ALL_ZERO!r} -- nonzero ub substitution?"
        )
    if census.get("limiting_substrate_0b") != EXPECTED_E1_INDEX_0B:
        return (
            f"natural_census.limiting_substrate_0b ({census.get('limiting_substrate_0b')!r}) != E1's index "
            f"({EXPECTED_E1_INDEX_0B!r}) -- wrong limiter?"
        )
    if census.get("limiting_substrate_whole_cell_model_id") != EXPECTED_E1_WID:
        return (
            "natural_census.limiting_substrate_whole_cell_model_id != "
            f"{EXPECTED_E1_WID!r} (got {census.get('limiting_substrate_whole_cell_model_id')!r})"
        )
    argmin_counts = census.get("limiting_substrate_argmin_counts", {})
    e1_key = str(EXPECTED_E1_LOCAL_INDEX)
    total_evaluations = n_seeds * m_ticks * len(EXPECTED_COMPLEX_INDICES_0B)
    if argmin_counts.get(e1_key) != total_evaluations:
        return (
            f"natural_census.limiting_substrate_argmin_counts[{e1_key!r}] != {total_evaluations!r} -- E1 is "
            "not the unique limiting substrate in every evaluation"
        )
    for key, count in argmin_counts.items():
        if key != e1_key and count != 0:
            return f"natural_census.limiting_substrate_argmin_counts[{key!r}] != 0 -- E1 is not uniquely limiting"
    if census.get("pool_fraction_zero", [None] * 4)[EXPECTED_E1_LOCAL_INDEX] != 1.0:
        return "natural_census.pool_fraction_zero at E1's index is not exactly 1.0"

    # --- Referenced source-of-truth artifacts must exist, hash-match, and keep their
    # expected (non-gating, non-CONFIRMED) verdicts, INCLUDING the pinned network-1-only
    # annotation strings -- this is the anti-laundering boundary: this module may only
    # CITE those artifacts' own recorded verdicts, never claim a stronger one, and never
    # let the 814/814 network-wide figure imply network-2 exact-match evidence.
    h12_ref = payload.get("accepted_h12_artifact_ref", {})
    h12_path = REPO_ROOT / h12_ref.get("path", "")
    if not h12_path.is_file():
        return f"accepted_h12_artifact_ref.path does not exist on disk: {h12_path}"
    if _sha256_lf_normalized(h12_path) != h12_ref.get("sha256_lf_normalized"):
        return "accepted_h12_artifact_ref.sha256_lf_normalized does not match current on-disk artifact"
    if h12_ref.get("verdict") != "H12_OBSERVED_REGIME":
        return f"accepted_h12_artifact_ref.verdict must be H12_OBSERVED_REGIME (got {h12_ref.get('verdict')!r})"
    if h12_ref.get("nontrivial_sample_count_scope") != NONTRIVIAL_SAMPLE_COUNT_SCOPE:
        return (
            "accepted_h12_artifact_ref.nontrivial_sample_count_scope missing/altered -- the network-1-only "
            "annotation on the 814/814 figure must be intact"
        )
    if h12_ref.get("exact_match_rate_scope") != EXACT_MATCH_RATE_SCOPE:
        return (
            "accepted_h12_artifact_ref.exact_match_rate_scope missing/altered -- the network-1-only "
            "annotation on exact_match_rate must be intact"
        )
    if on_disk_h12.get("verdict") != "H12_OBSERVED_REGIME":
        return "on-disk accepted H12 artifact verdict has changed since this condition-gated artifact was generated"
    if REQUIRED_BRANCH in on_disk_h12.get("branches_confirmed", []):
        return (
            f"on-disk accepted H12 artifact now confirms {REQUIRED_BRANCH!r} -- this condition-gated "
            "artifact's premise (natural regime never fires) is stale; must be regenerated, not trusted"
        )

    pert_ref = payload.get("accepted_perturbation_artifact_ref", {})
    pert_path = REPO_ROOT / pert_ref.get("path", "")
    if not pert_path.is_file():
        return f"accepted_perturbation_artifact_ref.path does not exist on disk: {pert_path}"
    if _sha256_lf_normalized(pert_path) != pert_ref.get("sha256_lf_normalized"):
        return "accepted_perturbation_artifact_ref.sha256_lf_normalized does not match current on-disk artifact"
    if pert_ref.get("verdict") != "H12_PERTURBATION_OBSERVED_STOCHASTIC":
        return (
            "accepted_perturbation_artifact_ref.verdict must be H12_PERTURBATION_OBSERVED_STOCHASTIC "
            f"(got {pert_ref.get('verdict')!r}) -- this artifact must never treat the perturbation "
            "evidence as a natural-regime PASS"
        )
    on_disk_pert = _load_json(pert_path)
    if on_disk_pert.get("verdict") != "H12_PERTURBATION_OBSERVED_STOCHASTIC":
        return "on-disk accepted perturbation artifact verdict has changed since this artifact was generated"
    if pert_ref.get("target_branch") != REQUIRED_BRANCH:
        return f"accepted_perturbation_artifact_ref.target_branch must be {REQUIRED_BRANCH!r}"
    if pert_ref.get("target_branch_exercised") is not True:
        return "accepted_perturbation_artifact_ref.target_branch_exercised must be exactly True"
    if "NON_GATING" not in str(pert_ref.get("gating", "")):
        return "accepted_perturbation_artifact_ref.gating must remain explicitly NON_GATING"

    # --- Karr source citation: tracked vendored path, LF-normalized hash rederived
    # from disk, upstream repo/commit constants, symbols/line ranges all pinned to
    # the registered source citation -- reject missing/forged citation.
    citation = payload.get("karr_source_citation")
    if not isinstance(citation, dict):
        return "karr_source_citation missing or not a dict"
    if citation.get("upstream_repo") != h12.KARR_UPSTREAM_REPO:
        return f"karr_source_citation.upstream_repo forged/missing (got {citation.get('upstream_repo')!r})"
    if citation.get("upstream_commit") != h12.KARR_UPSTREAM_COMMIT:
        return f"karr_source_citation.upstream_commit forged/missing (got {citation.get('upstream_commit')!r})"
    if citation.get("line_ranges") != EXPECTED_KARR_LINE_RANGES:
        return f"karr_source_citation.line_ranges does not match the pinned expected ranges (got {citation.get('line_ranges')!r})"
    if citation.get("symbols") != EXPECTED_KARR_SYMBOLS:
        return f"karr_source_citation.symbols does not match the pinned expected symbols (got {citation.get('symbols')!r})"
    expected_vendored_path = f"data/karr_vendored_source/{h12.KARR_SOURCE_CITATIONS[PROCESS]['file']}"
    if citation.get("vendored_path") != expected_vendored_path:
        return f"karr_source_citation.vendored_path != expected pinned path (got {citation.get('vendored_path')!r})"
    if citation.get("upstream_original_path") != h12.KARR_SOURCE_CITATIONS[PROCESS]["file"]:
        return "karr_source_citation.upstream_original_path forged/missing"
    vendored_path_on_disk = REPO_ROOT / expected_vendored_path
    if not vendored_path_on_disk.is_file():
        return f"karr_source_citation vendored source missing on disk: {vendored_path_on_disk}"
    if _sha256_lf_normalized(vendored_path_on_disk) != citation.get("vendored_sha256_lf_normalized"):
        return "karr_source_citation.vendored_sha256_lf_normalized is stale (does not match current on-disk vendored source)"

    # --- Structural argument: must cite the Monte Carlo functions exactly; missing
    # or forged citation/claim is a hard fail (this is the ONLY thing that makes
    # H12_CONFIRMED permanently inapplicable here, independent of lifecycle status).
    struct_arg = payload.get("structural_argument")
    if not isinstance(struct_arg, dict) or not struct_arg.get("claim"):
        return "structural_argument missing or has no claim"
    if "buildProteinComplexs_montecarlokinetic" not in struct_arg["claim"]:
        return "structural_argument.claim no longer cites buildProteinComplexs_montecarlokinetic"
    struct_citation = struct_arg.get("source_citation")
    if not isinstance(struct_citation, dict):
        return "structural_argument.source_citation missing"
    if struct_citation.get("file") != f"{PROCESS}.m":
        return f"structural_argument.source_citation.file forged/missing (got {struct_citation.get('file')!r})"
    if struct_citation.get("line_ranges") != EXPECTED_STRUCTURAL_ARG_LINE_RANGES:
        return "structural_argument.source_citation.line_ranges forged/missing"
    if struct_citation.get("symbols") != EXPECTED_STRUCTURAL_ARG_SYMBOLS:
        return "structural_argument.source_citation.symbols forged/missing"

    # --- Generator/predictor/E1-doc source hashes must match current disk
    # (stale-code/stale-doc detection).
    predictor_path = REPO_ROOT / payload.get("predictor_source_path", "")
    if not predictor_path.is_file():
        return f"predictor_source_path does not exist on disk: {predictor_path}"
    if _sha256_lf_normalized(predictor_path) != payload.get("predictor_source_sha256_lf_normalized"):
        return "predictor_source_sha256_lf_normalized does not match current on-disk h12.py (stale artifact)"

    generator_path = REPO_ROOT / payload.get("generator_source_path", "")
    if not generator_path.is_file():
        return f"generator_source_path does not exist on disk: {generator_path}"
    if _sha256_lf_normalized(generator_path) != payload.get("generator_source_sha256_lf_normalized"):
        return "generator_source_sha256_lf_normalized does not match current on-disk generator (stale artifact)"

    e1_doc_path = REPO_ROOT / payload.get("e1_provenance_ref", "")
    if not e1_doc_path.is_file():
        return f"e1_provenance_ref does not exist on disk: {e1_doc_path}"
    if _sha256_lf_normalized(e1_doc_path) != payload.get("e1_provenance_ref_sha256_lf_normalized"):
        return "e1_provenance_ref_sha256_lf_normalized does not match current on-disk doc (stale artifact)"

    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["generate", "validate"])
    args = parser.parse_args()

    if args.command == "generate":
        artifact = build_condition_gated_artifact()
        path = write_artifact(artifact)
        print(f"wrote {path.relative_to(REPO_ROOT).as_posix()}")
        err = validate_condition_gated_artifact(artifact)
        if err:
            print(f"WARNING: freshly-generated artifact fails its own validation: {err}", file=sys.stderr)
            return 1
        print("self-validation: OK")
    elif args.command == "validate":
        payload = _load_json(OUT_PATH)
        err = validate_condition_gated_artifact(payload)
        if err:
            print(f"INVALID: {err}", file=sys.stderr)
            return 1
        print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
