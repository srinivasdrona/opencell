"""Anti-cheat tests for the L2.2 evidence-index generator and audit.

Each test builds a synthetic-but-realistic evidence directory (using a real
in-scope catalog process's actual N_seeds/M_ticks/primary_channel so the
mechanical checks are exercised against genuine catalog values, not made-up
ones) under a throwaway `tmp_path` evidence root, then asserts the generator
and/or `audit()` correctly refuses to launder the tampered/incomplete/stale
input into a green verdict.

Covers the anti-cheat checklist from the evidence-gate task:
  - tampered stored PASS cannot override failing raw metrics (see also
    test_l22_evidence_verdict.py at the channel/process-function level)
  - missing process / extra row in a hand-edited index
  - stale input hash (current-tree staleness)
  - single-seed reuse warning / oracle-laundering warning (sentinels)
  - N/M mismatch, including the M=10-vs-catalog-M lie
  - zero/insufficient primary channel
  - hand-edited index / content hash
  - DEFERRED without decision_ref/alternate_evidence_ref
  - closed_form_dominant confirmed without H12 support
  - missing evaluator (projection-distance primary channel)

Run via `bin\\oc-pytest tests/scripts/test_l22_evidence_anticheat.py -v`.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import generator as gen  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402

_ENTRIES = cat.in_scope_processes()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _baseline_channel(**overrides) -> dict:
    base = dict(
        verdict="PASS",
        aggregation="per_tick_vector_w1_mean",
        is_primary=True,
        is_event_channel=False,
        w1_oc_vs_karr=0.1,
        threshold=1.0,
        q95_null=0.05,
        n_nonzero_oc=100,
        n_nonzero_karr=100,
    )
    base.update(overrides)
    return base


def _write_evidence_dir(
    evidence_root: Path,
    process_name: str,
    *,
    channel_overrides: dict | None = None,
    warnings: list | None = None,
    result_overrides: dict | None = None,
    inputs: list | None = None,
) -> Path:
    """Write a minimally-valid evidence directory for a REAL catalog process."""
    entry = _ENTRIES[process_name]
    subdir = schema.EVENT_CLASS_SUBDIR if entry.harness_type == "event_class" else schema.DESIGN_A_SUBDIR
    evidence_dir = evidence_root / process_name / subdir
    evidence_dir.mkdir(parents=True, exist_ok=True)

    channel_payload = _baseline_channel()
    if channel_overrides:
        channel_payload.update(channel_overrides)
    primary_name = entry.primary_channel or "substrates"

    result = {
        "process": process_name,
        "verdict": "PASS",
        "seeds": list(range(entry.n_seeds)),
        "ticks": entry.m_ticks,
        "channels": {primary_name: channel_payload},
        "warnings": warnings or [],
    }
    if result_overrides:
        result.update(result_overrides)
    _write_json(evidence_dir / "result.json", result)

    _write_json(
        evidence_dir / "input_manifest.json",
        {"inputs": inputs or [], "resolved_seeds": result["seeds"], "m_ticks": entry.m_ticks},
    )
    _write_json(evidence_dir / "provenance.json", {"generated_at": "2026-07-28T00:00:00+00:00", "git_sha": "deadbeef"})
    return evidence_dir


def _row_for(payload: dict, process_name: str) -> dict:
    matches = [row for row in payload["rows"] if row["process"] == process_name]
    assert len(matches) == 1, f"expected exactly one row for {process_name}, found {len(matches)}"
    return matches[0]


# --- Clean baseline sanity check (proves the fixtures are actually valid) -----


def test_clean_baseline_evidence_is_green(tmp_path):
    _write_evidence_dir(tmp_path, "Metabolism")
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is True
    assert row["mechanical_verdict"] == schema.STATUS_PASS


# --- N/M mismatch, including the M=10-vs-catalog-M lie ------------------------


def test_nm_mismatch_old_m10_evidence_vs_current_catalog_m(tmp_path):
    entry = _ENTRIES["Transcription"]
    assert entry.m_ticks == 100, "fixture assumes Transcription's catalog M_ticks is 100"
    _write_evidence_dir(tmp_path, "Transcription", result_overrides={"ticks": 10})
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Transcription")
    assert row["green"] is False
    assert any("NM_MISMATCH" in reason and "100" in reason and "10" in reason for reason in row["reasons"])


# --- Sentinel warnings: single-seed reuse / oracle laundering -----------------


def test_single_seed_reuse_sentinel_forces_non_green(tmp_path):
    _write_evidence_dir(
        tmp_path,
        "Metabolism",
        warnings=["KARR_SINGLE_SEED_REUSED: Metabolism.npz contains one canonical Karr seed"],
    )
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is False
    assert any("SENTINEL_FAIL" in reason for reason in row["reasons"])


def test_primary_channel_oracle_laundering_sentinel_forces_non_green(tmp_path):
    _write_evidence_dir(
        tmp_path,
        "Metabolism",
        warnings=["PRIMARY_CHANNEL_ORACLE_LAUNDERING: OC matched the Karr oracle exactly"],
    )
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is False
    assert any("SENTINEL_FAIL" in reason for reason in row["reasons"])


# --- Zero/insufficient primary channel -----------------------------------------


def test_zero_primary_channel_is_non_green(tmp_path):
    _write_evidence_dir(tmp_path, "Metabolism", channel_overrides={"n_nonzero_oc": 0, "n_nonzero_karr": 0})
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is False
    assert any("PRIMARY_CHANNEL_VACUOUS" in reason for reason in row["reasons"])


def test_insufficient_primary_samples_is_non_green(tmp_path):
    _write_evidence_dir(tmp_path, "Metabolism", channel_overrides={"n_nonzero_oc": 3, "n_nonzero_karr": 3})
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    # Only channel is INSUFFICIENT_SAMPLES -> no gateable channels -> non-green.
    assert row["green"] is False
    assert row["mechanical_verdict"] == schema.STATUS_NO_GATEABLE_CHANNELS


# --- Missing evaluator: projection-distance primary channel -------------------


def test_projection_distance_primary_channel_is_missing_evaluator(tmp_path):
    entry = _ENTRIES["DNARepair"]
    assert entry.uses_projection_distance
    _write_evidence_dir(
        tmp_path,
        "DNARepair",
        channel_overrides={"aggregation": entry.primary_distance},
    )
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "DNARepair")
    assert row["green"] is False
    assert any(schema.STATUS_MISSING_EVALUATOR in reason for reason in row["reasons"])


# --- closed_form_dominant confirmed without H12 support -----------------------


def test_closed_form_confirmed_without_h12_support_is_non_green(tmp_path):
    entry = _ENTRIES["tRNAAminoacylation"]
    assert entry.closed_form_dominant == "confirmed_biology_validated"
    _write_evidence_dir(
        tmp_path,
        "tRNAAminoacylation",
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched the Karr oracle exactly"],
    )
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "tRNAAminoacylation")
    assert row["green"] is False
    assert any("h12_evidence_ref" in reason for reason in row["reasons"])


def test_closed_form_confirmed_with_valid_h12_support_is_green(tmp_path):
    entry = _ENTRIES["tRNAAminoacylation"]
    h12_path = tmp_path / "h12_evidence.json"
    _write_json(h12_path, {"nontrivial_sample_count": 7})
    _write_evidence_dir(
        tmp_path,
        "tRNAAminoacylation",
        warnings=["PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE: OC matched the Karr oracle exactly"],
        result_overrides={"h12_evidence_ref": str(h12_path)},
    )
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "tRNAAminoacylation")
    assert row["green"] is True


# --- DEFERRED without decision_ref/alternate_evidence_ref ---------------------


def test_deferred_without_decision_or_evidence_is_non_green(tmp_path):
    _write_evidence_dir(tmp_path, "Metabolism", result_overrides={"verdict": "DEFERRED"})
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is False
    assert any(reason.startswith(schema.STATUS_DEFERRED) for reason in row["reasons"])
    assert any("never GREEN" in reason for reason in row["reasons"])


def test_deferred_with_decision_and_evidence_is_still_non_green(tmp_path):
    alt_path = tmp_path / "alternate.json"
    _write_json(alt_path, {"note": "alternate evidence"})
    _write_evidence_dir(
        tmp_path,
        "Metabolism",
        result_overrides={
            "verdict": "DEFERRED",
            "decision_ref": "decisions/some-defer-decision.yaml",
            "alternate_evidence_ref": str(alt_path),
        },
    )
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is False, "no DEFERRED counts as PASS, decision/evidence notwithstanding"


# --- Current-tree staleness (stale hash) ---------------------------------------


def test_stale_input_hash_is_flagged_after_source_file_changes(tmp_path):
    source_file = tmp_path / "fake_oracle_source.mat"
    source_file.write_bytes(b"original-bytes")
    original_sha = gen._sha256_file(source_file)

    _write_evidence_dir(
        tmp_path,
        "Metabolism",
        inputs=[{"path": str(source_file), "sha256": original_sha}],
    )
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    assert _row_for(payload, "Metabolism")["green"] is True

    # Mutate the "input" after evidence generation -- this must be caught.
    source_file.write_bytes(b"mutated-bytes-oracle-swapped")
    payload_after = gen.build_evidence_index(evidence_root=tmp_path)
    row_after = _row_for(payload_after, "Metabolism")
    assert row_after["green"] is False
    assert any("STALE_VS_TREE" in reason for reason in row_after["reasons"])


# --- Hand-edited index / forged content hash -----------------------------------


def test_audit_rejects_hand_edited_row_with_forged_content_hash(tmp_path):
    index_path = tmp_path / "evidence_index.json"
    evidence_root = tmp_path / "evidence"
    payload = gen.build_evidence_index(evidence_root=evidence_root)
    gen.write_index(payload, index_path)

    # No real evidence exists anywhere -> Transcription is truthfully MISSING_EVIDENCE.
    # Tamper: flip it to a fake PASS and forge a self-consistent content_hash.
    tampered = json.loads(index_path.read_text(encoding="utf-8"))
    for row in tampered["rows"]:
        if row["process"] == "Transcription":
            row["green"] = True
            row["mechanical_verdict"] = schema.STATUS_PASS
            row["reasons"] = []
    tampered["aggregate_verdict"] = tampered["aggregate_verdict"]  # unchanged on purpose
    tampered["content_hash"] = gen.content_hash(tampered)
    index_path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")

    result = gen.audit(index_path=index_path, evidence_root=evidence_root)
    assert result.ok is False
    assert any("does not match a fresh regeneration" in problem for problem in result.problems)


def test_audit_detects_missing_and_extra_rows(tmp_path):
    index_path = tmp_path / "evidence_index.json"
    evidence_root = tmp_path / "evidence"
    payload = gen.build_evidence_index(evidence_root=evidence_root)
    gen.write_index(payload, index_path)

    tampered = json.loads(index_path.read_text(encoding="utf-8"))
    tampered["rows"] = [row for row in tampered["rows"] if row["process"] != "DNADamage"]
    fake_row = copy.deepcopy(tampered["rows"][0])
    fake_row["process"] = "NotARealProcess"
    tampered["rows"].append(fake_row)
    index_path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")

    result = gen.audit(index_path=index_path, evidence_root=evidence_root)
    assert result.ok is False
    assert any("NotARealProcess" in problem for problem in result.problems)
    assert any("DNADamage" in problem for problem in result.problems)


def test_audit_passes_on_untampered_freshly_generated_index(tmp_path):
    index_path = tmp_path / "evidence_index.json"
    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "Metabolism")
    payload = gen.build_evidence_index(evidence_root=evidence_root)
    gen.write_index(payload, index_path)

    result = gen.audit(index_path=index_path, evidence_root=evidence_root)
    assert result.ok is True
    assert result.aggregate_verdict == "NON_GREEN"  # 21/22 still MISSING_EVIDENCE
    assert result.tally.get(schema.STATUS_PASS) == 1
