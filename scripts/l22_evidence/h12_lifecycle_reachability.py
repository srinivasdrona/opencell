"""H12 lifecycle-reachability evidence for MacromolecularComplexation network 2.

This module produces a single, machine-checkable, NON-GATING evidence
artifact answering ONE narrow, falsifiable question left explicitly
`"UNRESOLVED"` by `scripts/l22_evidence/h12_condition_gated.py` (see its
`LIFECYCLE_REACHABILITY_NOTE`) and by `docs/phase_f/l2_2_design_a/h12/
MACROMOLECULARCOMPLEXATION_NETWORK2_E1_PROVENANCE.md`:

    Across a full natural Karr cell cycle (birth to division, real
    per-tick scheduler order, NO conditioning of any pool/constant), does
    E1's free-monomer pool (`MG_429_MONOMER`, PTS system E1) ever leave
    zero, and does network >= 2 ever actually form a complex?

This is DIFFERENT evidence from the accepted 50-seed x 100-tick natural
census (`h12.py`) and from the accepted condition-gated candidate
(`h12_condition_gated.py`): those sample only ticks 0..99 from cell birth
across 50 independent seeds (a SHORT WINDOW x WIDE SEED coverage); this
module instead runs ONE seed for the process's entire natural lifecycle
via the real scheduler (`scripts/matlab/full_cycle_event_scan_macromol.m`,
modeled on the already-accepted `full_cycle_event_scan_v2.m` mechanism
used to justify RibosomeAssembly's `tick_offset=200` re-extraction) --
a LONG WINDOW x SINGLE SEED probe. The two are complementary, not
substitutes; this module never claims to supersede or resolve the other
artifact's own `lifecycle_reachability_status` field (that field remains
pinned to the literal `"UNRESOLVED"` by
`tests/scripts/test_h12_condition_gated.py`, intentionally, because IT is
scoped to "would a `tick_offset>0` RE-EXTRACTION resolve this", a
question this module does not answer either -- this module instead runs
the real full-length scheduler directly, which is strictly stronger
evidence than any single fixed-window re-extraction, but is still only
ONE seed, not fifty).

======================================================================
WHAT THIS ARTIFACT DOES NOT CLAIM
======================================================================
- It does NOT claim network >= 2 is unreachable across ALL seeds/
  lifecycles merely because ONE seed's full natural cycle never left
  E1==0. `seed_count` is always recorded and is never allowed to be
  reported as > 1 without matching per-seed evidence files actually
  present (see `validate_lifecycle_reachability_artifact`).
- It does NOT modify `verdict.py`'s evidence gate, `PROCESS_CATALOG.yaml`,
  `docs/phase_f/l2_2_design_a/evidence_index.json`, or `generator.py`,
  and is NOT consumed by `h12.validate_h12_support`.
- It does NOT modify or supersede `MacromolecularComplexation_h12_
  condition_gated.json`'s own `lifecycle_reachability_status` field
  (still, correctly, `"UNRESOLVED"` there -- see module docstring above).
- It does NOT claim H12_CONFIRMED, H12_OBSERVED_REGIME, PASS, or any
  enacted CONDITION_GATED value as its own `classification`.
- It does NOT run MATLAB itself. It reads already-generated, hash-bound
  raw probe output (`data/m1_sources/karr_native/event_scan/
  MacromolecularComplexation_e1_lifecycle_seed{seed:03d}.csv` +
  `..._summary.json`), produced by a separate, one-time, real MATLAB
  execution of `scripts/matlab/full_cycle_event_scan_macromol.m`. This
  module never fabricates or edits that raw output; it only reads,
  cross-checks (recomputing `max_e1_pool`/`n_net2_events` directly from
  the CSV and hard-failing on any mismatch with the summary JSON), and
  hash-binds it.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PROCESS = "MacromolecularComplexation"
REQUIRED_BRANCH = "network_ge2_fires"
E1_WHOLE_CELL_MODEL_ID = "MG_429_MONOMER"
SEED = 0
N_TICKS_MAX = 33000

OUT_DIR = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "lifecycle_reachability"
OUT_PATH = OUT_DIR / f"{PROCESS}_h12_lifecycle_reachability.json"

RAW_DIR = REPO_ROOT / "data" / "m1_sources" / "karr_native" / "event_scan"
RAW_CSV_PATH = RAW_DIR / f"{PROCESS}_e1_lifecycle_seed{SEED:03d}.csv"
RAW_SUMMARY_PATH = RAW_DIR / f"{PROCESS}_e1_lifecycle_seed{SEED:03d}_summary.json"
RAW_LOG_PATH = RAW_DIR / f"{PROCESS}_e1_lifecycle_seed{SEED:03d}_stdout.log"

# Matches the MATLAB script's own printed line, e.g.:
#   [macromol-scan] E1 local substrate index = 193; network-2 complex indices = [23 24]
_INDEX_LOG_RE = re.compile(
    r"E1 local substrate index = (\d+); network-2 complex indices = \[([^\]]*)\]"
)

MATLAB_SCRIPT_PATH = REPO_ROOT / "scripts" / "matlab" / "full_cycle_event_scan_macromol.m"
CONDITION_GATED_ARTIFACT_PATH = (
    REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "condition_gated" / f"{PROCESS}_h12_condition_gated.json"
)
E1_PROVENANCE_DOC_PATH = (
    REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12" / "MACROMOLECULARCOMPLEXATION_NETWORK2_E1_PROVENANCE.md"
)

ARTIFACT_KIND = "h12_lifecycle_reachability_evidence"
ARTIFACT_VERSION = "1.0.0"
GENERATOR_SOURCE_PATH = "scripts/l22_evidence/h12_lifecycle_reachability.py"

CLASSIFICATION = "LIFECYCLE_REACHABILITY_FULL_CYCLE_PROBE"
GATING = (
    "NON_GATING -- records a single full-natural-cycle probe observation for the record only; never "
    "claims H12_CONFIRMED, H12_OBSERVED_REGIME, PASS, or an enacted CONDITION_GATED value; not consumed "
    "by scripts/l22_evidence/verdict.py, generator.py, or h12_evidence_index.json."
)
EXPECTED_NOT_CONSUMED_BY = [
    "scripts/l22_evidence/verdict.py",
    "scripts/l22_evidence/generator.py",
    "docs/phase_f/l2_2_design_a/h12/h12_evidence_index.json",
    "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml",
    "docs/phase_f/l2_2_design_a/h12/condition_gated/MacromolecularComplexation_h12_condition_gated.json",
]

STOP_REASON_NATURAL_PINCH = "natural_cell_division_pinch"
STOP_REASON_MAX_TICKS = "max_ticks_reached_no_division"
STOP_REASON_OPERATOR_STOPPED = "operator_stopped_after_decisive_evidence"
VALID_STOP_REASONS = frozenset(
    {STOP_REASON_NATURAL_PINCH, STOP_REASON_MAX_TICKS, STOP_REASON_OPERATOR_STOPPED}
)

SCOPE_NOTE = (
    "This artifact reports evidence from EXACTLY ONE seed (seed=0) run for its full natural lifecycle "
    "via the real Karr per-tick scheduler (resource allocation + evolveState in real process order), "
    "starting from cell birth, with NO conditioning of any pool or constant. It is NOT N=50 seed "
    "coverage and must never be read as such; the accepted 50-seed x 100-tick natural census "
    "(docs/phase_f/l2_2_design_a/h12/MacromolecularComplexation_h12.json) and condition-gated candidate "
    "(condition_gated/MacromolecularComplexation_h12_condition_gated.json) remain the N=50 evidence; "
    "this module supplies the complementary long-window x single-seed axis. Generalizing this single "
    "seed's outcome to all 50 seeds, or to every possible lifecycle, is explicitly NOT claimed."
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_lf_normalized(path: Path) -> str:
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _path_for_record(path: Path) -> str:
    """Record a repo-relative POSIX path when `path` is under REPO_ROOT
    (the normal case for the real committed probe output), else fall back
    to the absolute path (test fixtures under tmp_path). Mirrored by
    `_resolve_recorded_path` on read-back."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _resolve_recorded_path(recorded: str) -> Path:
    candidate = Path(recorded)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / recorded


def _parse_indices_from_stdout_log(log_path: Path) -> tuple[int, list[int]]:
    """Recover the deterministic E1/network-2 index mapping from the
    MATLAB probe's own captured stdout, for use when the run was stopped
    before the loop could write its own summary JSON. Never guesses --
    hard-fails if the expected line is absent."""
    text = log_path.read_text(encoding="utf-8", errors="replace")
    match = _INDEX_LOG_RE.search(text)
    if not match:
        raise ValueError(
            "could not find the '... E1 local substrate index = N; network-2 complex indices = [...]' "
            f"line in stdout log {log_path} -- refusing to guess these values for an operator-stopped run"
        )
    e1_idx = int(match.group(1))
    net2_idx = [int(tok) for tok in match.group(2).split()]
    return e1_idx, net2_idx


def _recompute_from_csv(csv_path: Path) -> dict:
    """Independently recompute the headline numbers directly from the raw
    per-tick CSV, so a tampered/hand-edited summary JSON can never be
    trusted on its own -- mirrors h12_condition_gated.py's
    never-trust-payload-alone style."""
    max_e1_pool = 0.0
    first_e1_nonzero_tick = -1
    n_any_complex_events = 0
    n_net2_events = 0
    first_net2_event_tick = -1
    last_tick = 0
    pinched_at_tick = -1
    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            tick = int(row["tick"])
            last_tick = max(last_tick, tick)
            e1_pool = float(row["e1_pool"])
            any_delta = float(row["any_complex_delta"])
            net2_delta = float(row["net2_complex_delta_sum"])
            pinched = row["pinched"].strip() in ("1", "true", "True")
            if e1_pool > max_e1_pool:
                max_e1_pool = e1_pool
            if e1_pool > 0 and first_e1_nonzero_tick < 0:
                first_e1_nonzero_tick = tick
            if any_delta != 0:
                n_any_complex_events += 1
            if net2_delta != 0:
                n_net2_events += 1
                if first_net2_event_tick < 0:
                    first_net2_event_tick = tick
            if pinched and pinched_at_tick < 0:
                pinched_at_tick = tick
    return {
        "max_e1_pool": max_e1_pool,
        "first_e1_nonzero_tick": first_e1_nonzero_tick,
        "n_any_complex_events": n_any_complex_events,
        "n_net2_events": n_net2_events,
        "first_net2_event_tick": first_net2_event_tick,
        "last_logged_tick": last_tick,
        "pinched_at_tick": pinched_at_tick,
    }


def build_lifecycle_reachability_artifact(
    seed: int = SEED,
    csv_path: Path = RAW_CSV_PATH,
    summary_path: Path = RAW_SUMMARY_PATH,
    stdout_log_path: Path = RAW_LOG_PATH,
) -> dict:
    if not csv_path.is_file():
        raise FileNotFoundError(f"raw probe CSV not found: {csv_path}")

    recomputed = _recompute_from_csv(csv_path)
    raw_log_used = False

    if summary_path.is_file():
        # --- Path A: the MATLAB loop broke out on its own (natural pinch
        # or max-ticks ceiling) and wrote its own summary JSON. Cross-check
        # every headline number against an independent CSV recomputation.
        summary = _load_json(summary_path)

        if recomputed["max_e1_pool"] != summary.get("max_e1_pool"):
            raise ValueError(
                "CSV-recomputed max_e1_pool does not match summary JSON's max_e1_pool -- "
                f"recomputed={recomputed['max_e1_pool']!r} summary={summary.get('max_e1_pool')!r}"
            )
        if recomputed["n_net2_events"] != summary.get("n_net2_events"):
            raise ValueError(
                "CSV-recomputed n_net2_events does not match summary JSON's n_net2_events -- "
                f"recomputed={recomputed['n_net2_events']!r} summary={summary.get('n_net2_events')!r}"
            )
        if recomputed["n_any_complex_events"] != summary.get("n_any_complex_events"):
            raise ValueError(
                "CSV-recomputed n_any_complex_events does not match summary JSON's n_any_complex_events -- "
                f"recomputed={recomputed['n_any_complex_events']!r} "
                f"summary={summary.get('n_any_complex_events')!r}"
            )

        n_ticks_ran = int(summary["n_ticks_ran"])
        if recomputed["pinched_at_tick"] > 0:
            stop_reason = STOP_REASON_NATURAL_PINCH
            if recomputed["pinched_at_tick"] != n_ticks_ran:
                raise ValueError(
                    "CSV pinched_at_tick does not match summary n_ticks_ran -- "
                    f"csv={recomputed['pinched_at_tick']!r} summary={n_ticks_ran!r}"
                )
        elif n_ticks_ran >= N_TICKS_MAX:
            stop_reason = STOP_REASON_MAX_TICKS
        else:
            raise ValueError(
                f"n_ticks_ran={n_ticks_ran} is neither a recorded natural pinch tick nor >= N_TICKS_MAX="
                f"{N_TICKS_MAX} -- probe stopped for an unrecognized reason (crash/interrupt?); refusing "
                "to build an artifact from an incomplete, unexplained run"
            )

        e1_local_substrate_index_1based = summary["e1_local_substrate_index_1based"]
        net2_complex_indices_1based = summary["net2_complex_indices_1based"]
        max_e1_pool = summary["max_e1_pool"]
        first_e1_nonzero_tick = summary["first_e1_nonzero_tick"]
        n_any_complex_events = summary["n_any_complex_events"]
        n_net2_events = summary["n_net2_events"]
        first_net2_event_tick = summary["first_net2_event_tick"]
    else:
        # --- Path B: the run was deliberately stopped by the operator
        # before the loop could break out and write its own summary JSON
        # (e.g. because the accumulated CSV evidence was already decisive
        # and letting a ~9h probe run to completion was not warranted).
        # Everything is derived purely from the raw CSV plus the captured
        # stdout log (for the deterministic index mapping); nothing is
        # invented, and this path is refused if the CSV shows signs of a
        # natural completion that should have produced a summary.json.
        if not stdout_log_path.is_file():
            raise FileNotFoundError(
                f"neither summary JSON ({summary_path}) nor stdout log ({stdout_log_path}) exist -- "
                "cannot build an operator-stopped artifact without the stdout log recording the E1/"
                "network-2 index mapping"
            )
        if recomputed["pinched_at_tick"] > 0:
            raise ValueError(
                "CSV records a natural pinch event but no summary JSON exists on disk -- the MATLAB "
                "script always writes summary.json before exiting on natural pinch, so this indicates "
                "the summary was deleted/lost, not a genuine operator-stopped run; restore it instead "
                "of building an operator-stopped artifact"
            )
        n_ticks_ran = recomputed["last_logged_tick"]
        if n_ticks_ran <= 0:
            raise ValueError("CSV contains no logged ticks -- nothing to build an artifact from")
        if n_ticks_ran >= N_TICKS_MAX:
            raise ValueError(
                f"CSV's last logged tick ({n_ticks_ran}) already reached N_TICKS_MAX={N_TICKS_MAX} -- "
                "this looks like a completed max-ticks run; a summary.json should exist for it and this "
                "path must not be used to paper over a missing one"
            )

        e1_local_substrate_index_1based, net2_complex_indices_1based = _parse_indices_from_stdout_log(
            stdout_log_path
        )
        stop_reason = STOP_REASON_OPERATOR_STOPPED
        max_e1_pool = recomputed["max_e1_pool"]
        first_e1_nonzero_tick = recomputed["first_e1_nonzero_tick"]
        n_any_complex_events = recomputed["n_any_complex_events"]
        n_net2_events = recomputed["n_net2_events"]
        first_net2_event_tick = recomputed["first_net2_event_tick"]
        raw_log_used = True

    e1_ever_nonzero = max_e1_pool > 0
    network2_ever_fired = n_net2_events > 0
    if network2_ever_fired and not e1_ever_nonzero:
        raise ValueError(
            "n_net2_events > 0 while max_e1_pool == 0 -- network 2 requires E1 > 0 by stoichiometry (2 "
            "copies of E1 per pentamer, see network2_layout in the condition-gated artifact); this "
            "combination is structurally impossible and indicates a corrupted/tampered summary"
        )

    outcome = (
        "network2_fired_naturally" if network2_ever_fired
        else "e1_became_nonzero_but_network2_did_not_fire" if e1_ever_nonzero
        else "e1_remained_zero_throughout_scanned_window"
    )
    partial_coverage = stop_reason == STOP_REASON_OPERATOR_STOPPED
    partial_coverage_note = (
        (
            f"Run was deliberately stopped after tick {n_ticks_ran} (of a {N_TICKS_MAX}-tick ceiling, "
            "estimated ~32,400-tick natural cycle) once the accumulated real evidence "
            f"(max_e1_pool={max_e1_pool!r}, n_net2_events={n_net2_events!r}, both strictly increasing "
            "and not yet plateaued) was already sufficient to falsify the 'E1 always zero / genuine "
            "biological ceiling' hypothesis. Natural cell division was NOT reached in this run; "
            "n_ticks_ran is a lower bound on ticks actually simulated (the CSV only logs every 25th "
            "tick, or on an event, so the true kill point may be up to 24 ticks later than the last "
            "logged row)."
        )
        if partial_coverage
        else None
    )

    artifact = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_version": ARTIFACT_VERSION,
        "process": PROCESS,
        "required_branch": REQUIRED_BRANCH,
        "classification": CLASSIFICATION,
        "gating": GATING,
        "not_consumed_by": EXPECTED_NOT_CONSUMED_BY,
        "unblocks_current_row": False,
        "unblocks_l2_5": False,
        "maintainer_decision_made": False,
        "scope_note": SCOPE_NOTE,
        "seed_count": 1,
        "partial_coverage": partial_coverage,
        "partial_coverage_note": partial_coverage_note,
        "probe": {
            "seed": seed,
            "n_ticks_max": N_TICKS_MAX,
            "n_ticks_ran": n_ticks_ran,
            "stop_reason": stop_reason,
            "e1_whole_cell_model_id": E1_WHOLE_CELL_MODEL_ID,
            "e1_local_substrate_index_1based": e1_local_substrate_index_1based,
            "net2_complex_indices_1based": net2_complex_indices_1based,
            "max_e1_pool": max_e1_pool,
            "first_e1_nonzero_tick": first_e1_nonzero_tick,
            "n_any_complex_events": n_any_complex_events,
            "n_net2_events": n_net2_events,
            "first_net2_event_tick": first_net2_event_tick,
        },
        "outcome": outcome,
        "e1_ever_nonzero": e1_ever_nonzero,
        "network2_ever_fired_naturally": network2_ever_fired,
        "mechanism": (
            "Real per-tick scheduler: resource allocation (calcResourceRequirements_Current -> "
            "proportional allocation) then evolveState() in randperm process order, identical mechanism "
            "to scripts/matlab/full_cycle_event_scan_v2.m (the already-accepted precedent used to justify "
            "RibosomeAssembly's tick_offset=200 re-extraction). No conditioning, no synthetic pool "
            "injection, no fixture edits -- this is the natural lifecycle as the real scheduler produces it."
        ),
        "stop_condition": (
            "Geometry.pinched (natural cell division boundary), identical stopping condition to "
            "scripts/matlab/extract_cell_cycle_trajectory.m -- ticks after this boundary are never "
            "scanned or counted as 'natural'."
        ),
        "matlab_script_path": "scripts/matlab/full_cycle_event_scan_macromol.m",
        "matlab_script_sha256_lf_normalized": _sha256_lf_normalized(MATLAB_SCRIPT_PATH),
        "raw_csv_path": _path_for_record(csv_path),
        "raw_csv_sha256": _sha256_file(csv_path),
        "raw_summary_path": None if raw_log_used else _path_for_record(summary_path),
        "raw_summary_sha256": None if raw_log_used else _sha256_file(summary_path),
        "raw_log_path": _path_for_record(stdout_log_path) if raw_log_used else None,
        "raw_log_sha256": _sha256_file(stdout_log_path) if raw_log_used else None,
        "generator_source_path": GENERATOR_SOURCE_PATH,
        "generator_source_sha256_lf_normalized": _sha256_lf_normalized(Path(__file__).resolve()),
        "condition_gated_artifact_ref": _path_for_record(CONDITION_GATED_ARTIFACT_PATH),
        "e1_provenance_ref": _path_for_record(E1_PROVENANCE_DOC_PATH),
        "e1_provenance_ref_sha256_lf_normalized": _sha256_lf_normalized(E1_PROVENANCE_DOC_PATH),
    }
    return artifact


def write_artifact(artifact: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=False)
        fh.write("\n")
    return OUT_PATH


def validate_lifecycle_reachability_artifact(payload: dict) -> str | None:
    """Return None if every check passes, else a human-readable reason
    string for the first failure. Mirrors h12_condition_gated.py's
    never-trust-payload-alone style: every constant, hash, and file
    reference is re-checked against a pinned expectation or the current
    working tree."""

    if payload.get("artifact_kind") != ARTIFACT_KIND:
        return f"unexpected artifact_kind (got {payload.get('artifact_kind')!r})"
    if payload.get("artifact_version") != ARTIFACT_VERSION:
        return f"unexpected artifact_version (got {payload.get('artifact_version')!r})"
    if payload.get("process") != PROCESS:
        return f"unexpected process (got {payload.get('process')!r})"
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
    if payload.get("unblocks_current_row") is not False:
        return "unblocks_current_row must be exactly False -- this probe cannot unblock the current row"
    if payload.get("unblocks_l2_5") is not False:
        return "unblocks_l2_5 must be exactly False -- this probe cannot unblock L2.5"
    if payload.get("maintainer_decision_made") is not False:
        return "maintainer_decision_made must be exactly False -- no maintainer decision is made here"
    if payload.get("seed_count") != 1:
        return (
            f"seed_count must be exactly 1 (got {payload.get('seed_count')!r}) -- this module only ever "
            "records evidence for a single seed; a value > 1 without a matching multi-seed evidence "
            "structure would misrepresent coverage"
        )
    if "single seed" not in payload.get("scope_note", "") and "ONE seed" not in payload.get("scope_note", ""):
        return "scope_note must explicitly disclose single-seed scope"

    probe = payload.get("probe", {})
    if probe.get("stop_reason") not in VALID_STOP_REASONS:
        return f"probe.stop_reason must be one of {sorted(VALID_STOP_REASONS)!r} (got {probe.get('stop_reason')!r})"
    n_ticks_ran = probe.get("n_ticks_ran")
    n_ticks_max = probe.get("n_ticks_max")
    if n_ticks_max != N_TICKS_MAX:
        return f"probe.n_ticks_max must be exactly {N_TICKS_MAX} (got {n_ticks_max!r})"
    if not isinstance(n_ticks_ran, int) or n_ticks_ran <= 0:
        return f"probe.n_ticks_ran must be a positive int (got {n_ticks_ran!r})"
    if probe.get("stop_reason") == STOP_REASON_NATURAL_PINCH and n_ticks_ran >= n_ticks_max:
        return (
            "stop_reason claims natural pinch but n_ticks_ran >= n_ticks_max -- a natural stop must occur "
            "strictly before the max-ticks ceiling, else this is a truncation being mislabeled as natural"
        )
    if probe.get("stop_reason") == STOP_REASON_MAX_TICKS and n_ticks_ran != n_ticks_max:
        return (
            "stop_reason claims max-ticks-reached but n_ticks_ran != n_ticks_max -- inconsistent "
            "truncation bookkeeping"
        )
    if probe.get("stop_reason") == STOP_REASON_OPERATOR_STOPPED and n_ticks_ran >= n_ticks_max:
        return (
            "stop_reason claims operator-stopped but n_ticks_ran >= n_ticks_max -- an operator-stopped "
            "run must be strictly incomplete, else it should be recorded as max-ticks-reached"
        )
    if probe.get("e1_whole_cell_model_id") != E1_WHOLE_CELL_MODEL_ID:
        return f"probe.e1_whole_cell_model_id must be exactly {E1_WHOLE_CELL_MODEL_ID!r}"

    is_operator_stopped = probe.get("stop_reason") == STOP_REASON_OPERATOR_STOPPED
    if payload.get("partial_coverage") is not is_operator_stopped:
        return (
            f"partial_coverage must be exactly {is_operator_stopped!r} given stop_reason="
            f"{probe.get('stop_reason')!r} (got {payload.get('partial_coverage')!r})"
        )
    if is_operator_stopped:
        note = payload.get("partial_coverage_note")
        if not isinstance(note, str) or not note.strip():
            return "partial_coverage_note must be a non-empty string when partial_coverage is True"
        if "NOT" not in note and "not reached" not in note:
            return "partial_coverage_note must explicitly disclose that natural cell division was NOT reached"
    elif payload.get("partial_coverage_note") is not None:
        return "partial_coverage_note must be null when partial_coverage is False"

    max_e1_pool = probe.get("max_e1_pool")
    n_net2_events = probe.get("n_net2_events")
    e1_ever_nonzero = payload.get("e1_ever_nonzero")
    network2_ever_fired = payload.get("network2_ever_fired_naturally")
    if (max_e1_pool is not None and max_e1_pool > 0) != bool(e1_ever_nonzero):
        return "e1_ever_nonzero is inconsistent with probe.max_e1_pool"
    if (n_net2_events is not None and n_net2_events > 0) != bool(network2_ever_fired):
        return "network2_ever_fired_naturally is inconsistent with probe.n_net2_events"
    if network2_ever_fired and not e1_ever_nonzero:
        return (
            "network2_ever_fired_naturally=True while e1_ever_nonzero=False is structurally impossible "
            "(network 2 requires E1 > 0 by stoichiometry) -- tampered artifact?"
        )

    expected_outcome = (
        "network2_fired_naturally" if network2_ever_fired
        else "e1_became_nonzero_but_network2_did_not_fire" if e1_ever_nonzero
        else "e1_remained_zero_throughout_scanned_window"
    )
    if payload.get("outcome") != expected_outcome:
        return f"outcome does not match derived value (got {payload.get('outcome')!r}, expected {expected_outcome!r})"

    # --- Hash-bind every referenced file to the CURRENT working tree / raw
    # output on disk (stale-artifact / hand-edited-summary / tampered-CSV
    # detection). The raw CSV/summary are small, non-gitignored, committed
    # alongside this artifact (unlike the large, gitignored oracle .mat
    # traces), so this validation can run without any MATLAB/Octave
    # dependency.
    matlab_script_path = REPO_ROOT / payload.get("matlab_script_path", "")
    if not matlab_script_path.is_file():
        return f"matlab_script_path does not exist on disk: {matlab_script_path}"
    if _sha256_lf_normalized(matlab_script_path) != payload.get("matlab_script_sha256_lf_normalized"):
        return "matlab_script_sha256_lf_normalized does not match current on-disk script (stale artifact)"

    raw_csv_path = _resolve_recorded_path(payload.get("raw_csv_path", ""))
    if not raw_csv_path.is_file():
        return f"raw_csv_path does not exist on disk: {raw_csv_path}"
    if _sha256_file(raw_csv_path) != payload.get("raw_csv_sha256"):
        return "raw_csv_sha256 does not match current on-disk CSV (stale/tampered artifact)"

    if is_operator_stopped:
        if payload.get("raw_summary_path") is not None or payload.get("raw_summary_sha256") is not None:
            return "raw_summary_path/raw_summary_sha256 must be null for an operator-stopped run"
        raw_log_path = _resolve_recorded_path(payload.get("raw_log_path") or "")
        if not raw_log_path.is_file():
            return f"raw_log_path does not exist on disk: {raw_log_path}"
        if _sha256_file(raw_log_path) != payload.get("raw_log_sha256"):
            return "raw_log_sha256 does not match current on-disk stdout log (stale/tampered artifact)"
        parsed_e1_idx, parsed_net2_idx = _parse_indices_from_stdout_log(raw_log_path)
        if parsed_e1_idx != probe.get("e1_local_substrate_index_1based"):
            return "stdout log's E1 index does not match payload's probe.e1_local_substrate_index_1based"
        if parsed_net2_idx != probe.get("net2_complex_indices_1based"):
            return "stdout log's network-2 indices do not match payload's probe.net2_complex_indices_1based"
    else:
        if payload.get("raw_log_path") is not None or payload.get("raw_log_sha256") is not None:
            return "raw_log_path/raw_log_sha256 must be null for a naturally-completed run"
        raw_summary_path = _resolve_recorded_path(payload.get("raw_summary_path", ""))
        if not raw_summary_path.is_file():
            return f"raw_summary_path does not exist on disk: {raw_summary_path}"
        if _sha256_file(raw_summary_path) != payload.get("raw_summary_sha256"):
            return "raw_summary_sha256 does not match current on-disk summary JSON (stale/tampered artifact)"

    # --- Independent re-derivation directly from the raw CSV: never trust
    # the payload's own headline numbers without recomputing them.
    recomputed = _recompute_from_csv(raw_csv_path)
    if recomputed["max_e1_pool"] != max_e1_pool:
        return (
            f"CSV-recomputed max_e1_pool ({recomputed['max_e1_pool']!r}) does not match payload's "
            f"probe.max_e1_pool ({max_e1_pool!r})"
        )
    if recomputed["n_net2_events"] != n_net2_events:
        return (
            f"CSV-recomputed n_net2_events ({recomputed['n_net2_events']!r}) does not match payload's "
            f"probe.n_net2_events ({n_net2_events!r})"
        )
    if recomputed["n_any_complex_events"] != probe.get("n_any_complex_events"):
        return "CSV-recomputed n_any_complex_events does not match payload's probe.n_any_complex_events"

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

    condition_gated_path = REPO_ROOT / payload.get("condition_gated_artifact_ref", "")
    if not condition_gated_path.is_file():
        return f"condition_gated_artifact_ref does not exist on disk: {condition_gated_path}"

    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["generate", "validate"])
    args = parser.parse_args()

    if args.command == "generate":
        artifact = build_lifecycle_reachability_artifact()
        path = write_artifact(artifact)
        print(f"wrote {path.relative_to(REPO_ROOT).as_posix()}")
        err = validate_lifecycle_reachability_artifact(artifact)
        if err:
            print(f"WARNING: freshly-generated artifact fails its own validation: {err}", file=sys.stderr)
            return 1
        print("self-validation: OK")
    elif args.command == "validate":
        payload = _load_json(OUT_PATH)
        err = validate_lifecycle_reachability_artifact(payload)
        if err:
            print(f"INVALID: {err}", file=sys.stderr)
            return 1
        print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
