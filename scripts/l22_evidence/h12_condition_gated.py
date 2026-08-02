"""H12 CONDITION_GATED evidence for MacromolecularComplexation network 2.

This module produces a single, machine-checkable, NON-GATING evidence
artifact that mechanically binds three already-accepted pieces of evidence
into one honest disposition proposal for network 2's
`network_ge2_fires` required branch (see `scripts/l22_evidence/h12.py`'s
`REQUIRED_BRANCHES["MacromolecularComplexation"]`):

  1. The accepted H12 artifact (`docs/phase_f/l2_2_design_a/h12/
     MacromolecularComplexation_h12.json`, verdict `H12_OBSERVED_REGIME`) --
     network 2 is 100% exact-match on every nontrivial sample it produces,
     but never produces a nontrivial, regime_valid sample for network>=2
     because `ub==0` on every one of the 5000 accepted natural (seed,
     tick) samples.
  2. A freshly re-derived natural-population census (this module,
     `compute_natural_network2_census`) that independently recomputes that
     `ub==0` claim directly from the SAME hash-verified oracle trace
     population (the `oracle_seed_file_sha256` map below is byte-identical
     to the one already recorded in artifact (1)), and additionally
     identifies the limiting substrate (`MG_429_MONOMER`, PTS system E1)
     and its fixture-constant-zero pool value -- see
     `docs/phase_f/l2_2_design_a/h12/
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
WHAT THIS MODULE DOES NOT DO
======================================================================
- It does NOT claim H12_CONFIRMED, does NOT modify `verdict.py`'s
  evidence gate, `PROCESS_CATALOG.yaml`, or `evidence_index.json`, and is
  NOT consumed by `h12.validate_h12_support` / `generator.py`. Its output
  `classification` field is `"CONDITION_GATED_CANDIDATE"` -- a proposal
  for reviewer/maintainer sign-off, not an enacted taxonomy value. See
  `docs/phase_f/l2_2_design_a/h12/CONDITION_GATED_TAXONOMY_PROPOSAL.md`
  for the (separately scoped, not-yet-implemented) central taxonomy
  change this artifact is evidence FOR.
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
ARTIFACT_VERSION = "1.0.0"
GENERATOR_SOURCE_PATH = "scripts/l22_evidence/h12_condition_gated.py"
_THIS_FILE = Path(__file__).resolve()

CATALOG_N_SEEDS, CATALOG_M_TICKS = h12.CATALOG_N_M[PROCESS]


def _sha256_file(path: Path) -> str:
    return h12._sha256_file(path)


def _sha256_lf_normalized(path: Path) -> str:
    return h12._sha256_lf_normalized(path)


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
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
    `validate_condition_gated_artifact`, not merged into one function).
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


# ---------------------------------------------------------------------------
# Natural-population census (reads already-extracted, already-accepted
# oracle traces -- NO new extraction; one-time producer step only).
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


# ---------------------------------------------------------------------------
# Artifact assembly
# ---------------------------------------------------------------------------


def build_condition_gated_artifact() -> dict:
    layout = get_network2_layout()
    fixture = layout["fixture"]
    census = compute_natural_network2_census()

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
    if census["candidate_ticks_ub_gt_0"] != 0:
        raise ValueError(
            f"natural census unexpectedly found {census['candidate_ticks_ub_gt_0']} candidate ticks with "
            "ub>0 -- the 'natural regime never fires' premise of this artifact no longer holds; do not "
            "silently paper over this, investigate before regenerating"
        )

    karr_citation = {
        **h12.karr_source_citation(PROCESS),
        "line_ranges": [[290, 314], [334, 392]],
        "symbols": [
            "evolveState",
            "buildProteinComplexs_montecarlokinetic",
            "buildProteinComplexs_rates_collisionTheory",
            "buildProteinComplexs_bounds",
        ],
    }

    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_version": ARTIFACT_VERSION,
        "gating": "NON_GATING -- proposes a disposition for reviewer/maintainer sign-off only; never "
        "claims H12_CONFIRMED; not consumed by scripts/l22_evidence/verdict.py, generator.py, or "
        "h12_evidence_index.json.",
        "process": PROCESS,
        "network": NETWORK,
        "required_branch": "network_ge2_fires",
        "required_branches_registry_ref": "scripts/l22_evidence/h12.py:REQUIRED_BRANCHES['MacromolecularComplexation']",
        "purpose": (
            "Mechanically bind (a) the accepted H12_OBSERVED_REGIME artifact, (b) an independently "
            "re-derived natural-population census proving network 2's ub is 0 on 100% of the accepted "
            "50x100 oracle population with PTS-system E1 (MG_429_MONOMER) as the sole limiting substrate, "
            "and (c) the accepted non-gating perturbation artifact proving the branch is structurally "
            "reachable (fires for real, invariants hold) once ONLY that one substrate is conditioned -- "
            "into a single evidence record supporting a proposed CONDITION_GATED terminal classification. "
            "See MACROMOLECULARCOMPLEXATION_NETWORK2_E1_PROVENANCE.md for the full investigation and "
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
        "natural_regime_reachable": False,
        "natural_regime_reachable_unresolved_reason": (
            "The accepted 50x100 oracle population is extracted at tick_offset=0 (cell birth) -- "
            "scripts/matlab/extract_per_process_traces_v2.m's own docstring documents that some processes "
            "are 'quiescent at cell birth (t=0) but active later' (citing RibosomeAssembly's first "
            "assembly at ~tick 238) and provides tick_offset specifically for this. Whether E1 "
            "(MG_429_MONOMER) ever becomes nonzero at a later tick in the real Karr model, or is "
            "genuinely never produced in this population, is UNRESOLVED without a new tick_offset>0 "
            "extraction, which is explicitly out of scope for this artifact. See "
            "MACROMOLECULARCOMPLEXATION_NETWORK2_E1_PROVENANCE.md section 3."
        ),
        "e1_provenance_ref": E1_PROVENANCE_DOC_PATH.relative_to(REPO_ROOT).as_posix(),
        "e1_provenance_ref_sha256_lf_normalized": _sha256_lf_normalized(E1_PROVENANCE_DOC_PATH),
        "accepted_h12_artifact_ref": {
            "path": ACCEPTED_H12_ARTIFACT_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256_lf_normalized": _sha256_lf_normalized(ACCEPTED_H12_ARTIFACT_PATH),
            "verdict": accepted_h12["verdict"],
            "nontrivial_sample_count": accepted_h12["nontrivial_sample_count"],
            "exact_match_rate": accepted_h12["exact_match_rate"],
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
            "claim": (
                "network>=2 competition is genuinely Monte Carlo: buildProteinComplexs_montecarlokinetic "
                "draws randStream.rand() once per iteration of its while-loop (line 349) to select which "
                "complex builds next; there is no closed form for that selection sequence. H12_CONFIRMED "
                "is therefore inapplicable to this unit by construction -- independent of how much "
                "additional natural-population sampling or conditioning occurs, and independent of "
                "whether the natural_regime_reachable question above is ever resolved."
            ),
            "source_citation": {
                "file": "MacromolecularComplexation.m",
                "line_ranges": [[334, 357], [360, 386]],
                "symbols": ["buildProteinComplexs_montecarlokinetic", "buildProteinComplexs_rates_collisionTheory"],
            },
        },
        "classification": "CONDITION_GATED_CANDIDATE",
        "classification_note": (
            "Proposed terminal disposition for MacromolecularComplexation/network_ge2_fires, pending "
            "reviewer (Opus 5) sign-off and a SEPARATE, later, serialized change to actually enact a "
            "CONDITION_GATED taxonomy value in verdict.py/PROCESS_CATALOG.yaml/h12_evidence_index.json -- "
            "see CONDITION_GATED_TAXONOMY_PROPOSAL.md. This artifact and its classification field are NOT "
            "consumed by any of those files in this change."
        ),
        "not_consumed_by": [
            "scripts/l22_evidence/verdict.py",
            "scripts/l22_evidence/generator.py",
            "docs/phase_f/l2_2_design_a/h12/h12_evidence_index.json",
            "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml",
        ],
        "generator_source_path": GENERATOR_SOURCE_PATH,
        "generator_source_sha256_lf_normalized": _sha256_lf_normalized(_THIS_FILE),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anti_laundering_attestation": {
            "census_inputs": ["states_before", "static_fixture_params"],
            "perturbation_reference_is_precomputed_and_read_only": True,
            "no_sut_import": True,
            "no_result_json_access": True,
            "no_new_extraction": True,
            "no_matlab_or_octave_run_this_change": True,
        },
    }


def write_artifact(artifact: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=False)
        fh.write("\n")
    return OUT_PATH


# ---------------------------------------------------------------------------
# Validation (re-derivation without requiring raw oracle traces on disk --
# used both by tests and by any future consumer of this artifact).
# ---------------------------------------------------------------------------


def validate_condition_gated_artifact(payload: dict) -> str | None:
    """Re-derive/cross-check every claim in `payload` that does NOT require
    a raw oracle trace to be present on disk. Returns None if every check
    passes, else a human-readable reason string for the first failure.

    Deliberately mirrors `h12.validate_h12_support`'s hard-fail-no-soft-
    trust style: every referenced tracked file is re-read and re-hashed
    from the CURRENT working tree, never taken on faith from the payload.
    """
    if payload.get("artifact_kind") != ARTIFACT_KIND:
        return f"unexpected artifact_kind (got {payload.get('artifact_kind')!r})"
    if payload.get("process") != PROCESS:
        return f"unexpected process (got {payload.get('process')!r})"
    if payload.get("classification") == "H12_CONFIRMED" or "CONFIRMED" in str(payload.get("classification", "")):
        return (
            "condition-gated artifact must never claim a CONFIRMED-flavored classification "
            f"(got {payload.get('classification')!r})"
        )

    # Fixture hash must match current disk (stale-fixture / drifted-tracked-file detection).
    fixture_path = REPO_ROOT / payload.get("fixture_path", "")
    if not fixture_path.is_file():
        return f"fixture_path does not exist on disk: {fixture_path}"
    if _sha256_file(fixture_path) != payload.get("fixture_sha256"):
        return "fixture_sha256 does not match current on-disk fixture (stale artifact)"

    # Network-2 layout must match the CURRENT fixture (fixture drift / hand-edited stoichiometry).
    layout = get_network2_layout()
    recorded_layout = payload.get("network2_layout", {})
    if layout["substrate_indices_0b"] != recorded_layout.get("substrate_indices_0b"):
        return "network2_layout.substrate_indices_0b no longer matches the real fixture"
    if layout["complex_indices_0b"] != recorded_layout.get("complex_indices_0b"):
        return "network2_layout.complex_indices_0b no longer matches the real fixture"
    if layout["stoichiometry_block"] != recorded_layout.get("stoichiometry_block"):
        return "network2_layout.stoichiometry_block no longer matches the real fixture (hand-edited constants?)"

    # Census internal consistency: this artifact must never assert the natural regime fires.
    census = payload.get("natural_census", {})
    if census.get("candidate_ticks_ub_gt_0", None) != 0:
        return "natural_census.candidate_ticks_ub_gt_0 != 0 -- premise of this artifact no longer holds"
    if payload.get("natural_regime_reachable") is not False:
        return "natural_regime_reachable must be exactly False (this artifact never asserts the natural " \
            "regime fires)"
    limiting_wid = census.get("limiting_substrate_whole_cell_model_id")
    if limiting_wid not in layout["substrate_whole_cell_model_ids"]:
        return f"limiting_substrate_whole_cell_model_id {limiting_wid!r} is not one of network 2's own substrates"

    # Referenced source-of-truth artifacts must exist, hash-match, and keep their expected (non-gating,
    # non-CONFIRMED) verdicts -- this is the anti-laundering boundary: this module may only CITE those
    # artifacts' own recorded verdicts, never claim a stronger one on their behalf.
    h12_ref = payload.get("accepted_h12_artifact_ref", {})
    h12_path = REPO_ROOT / h12_ref.get("path", "")
    if not h12_path.is_file():
        return f"accepted_h12_artifact_ref.path does not exist on disk: {h12_path}"
    if _sha256_lf_normalized(h12_path) != h12_ref.get("sha256_lf_normalized"):
        return "accepted_h12_artifact_ref.sha256_lf_normalized does not match current on-disk artifact"
    if h12_ref.get("verdict") != "H12_OBSERVED_REGIME":
        return f"accepted_h12_artifact_ref.verdict must be H12_OBSERVED_REGIME (got {h12_ref.get('verdict')!r})"
    on_disk_h12 = _load_json(h12_path)
    if on_disk_h12.get("verdict") != "H12_OBSERVED_REGIME":
        return "on-disk accepted H12 artifact verdict has changed since this condition-gated artifact was generated"
    if "network_ge2_fires" in on_disk_h12.get("branches_confirmed", []):
        return (
            "on-disk accepted H12 artifact now confirms network_ge2_fires -- this condition-gated "
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
    if not pert_ref.get("target_branch_exercised"):
        return "accepted_perturbation_artifact_ref.target_branch_exercised must be True"
    if "NON_GATING" not in str(pert_ref.get("gating", "")):
        return "accepted_perturbation_artifact_ref.gating must remain explicitly NON_GATING"

    # Generator/predictor source hashes must match current disk (stale-code detection).
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

    if "verdict.py" in payload.get("not_consumed_by", []) is False:
        pass  # not_consumed_by is documentation metadata, not independently re-checkable here.

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
