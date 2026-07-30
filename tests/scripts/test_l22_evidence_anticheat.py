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
import dataclasses
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import generator as gen  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402

from tests.scripts._l22_evidence_fixtures import (  # noqa: E402
    default_input_records,
    write_mandatory_sidecars,
    write_valid_sweep_provenance,
)

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
        {"inputs": default_input_records() if inputs is None else inputs, "resolved_seeds": result["seeds"], "m_ticks": entry.m_ticks},
    )
    _write_json(evidence_dir / "provenance.json", {"generated_at": "2026-07-28T00:00:00+00:00", "git_sha": "deadbeef"})
    write_mandatory_sidecars(evidence_dir)
    write_valid_sweep_provenance(
        evidence_dir,
        process=process_name,
        n_seeds=entry.n_seeds,
        m_ticks=entry.m_ticks,
        oc_module=entry.oc_module,
        harness_type=entry.harness_type,
    )
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


def test_asymmetric_zero_primary_channel_is_non_green(tmp_path):
    """P2 zero-activity guard, end-to-end: OC shows zero activity on the
    primary channel while Karr shows real activity. This is NOT the
    symmetric both-zero PRIMARY_CHANNEL_VACUOUS case (that would silently
    hide an equally serious problem -- OC never exhibiting behavior Karr
    genuinely has) and must not be laundered into a passing/insufficient
    verdict via any per-channel scale/threshold."""
    _write_evidence_dir(tmp_path, "Metabolism", channel_overrides={"n_nonzero_oc": 0, "n_nonzero_karr": 5000})
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is False
    assert any(schema.STATUS_PRIMARY_ACTIVITY_MISSING in reason for reason in row["reasons"])


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


def test_audit_rejects_content_hash_tampered_alone_with_everything_else_untouched(tmp_path):
    """A payload hand-tampered ONLY in its `content_hash` field (every other
    field, including every row, still equal to a fresh regeneration) must
    still be caught. Before the Phase-A audit-hash fix, this check was
    nested inside the `_strip_volatile(stored) != _strip_volatile(fresh)`
    branch and would never fire when the rest of the payload still matched
    a fresh regeneration -- silently accepting an isolated forged/removed
    content_hash. See generator.audit()'s docstring."""
    index_path = tmp_path / "evidence_index.json"
    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "Metabolism")
    payload = gen.build_evidence_index(evidence_root=evidence_root)
    gen.write_index(payload, index_path)

    tampered = json.loads(index_path.read_text(encoding="utf-8"))
    tampered["content_hash"] = "0" * 64  # forged; nothing else in the payload changed
    index_path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")

    result = gen.audit(index_path=index_path, evidence_root=evidence_root)
    assert result.ok is False
    assert any("content_hash does not match" in problem for problem in result.problems)


def test_audit_rejects_content_hash_field_entirely_removed(tmp_path):
    """The degenerate case of the same bug: dropping `content_hash` outright
    (rather than forging it) must also be caught, not silently treated as
    "nothing to check"."""
    index_path = tmp_path / "evidence_index.json"
    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "Metabolism")
    payload = gen.build_evidence_index(evidence_root=evidence_root)
    gen.write_index(payload, index_path)

    tampered = json.loads(index_path.read_text(encoding="utf-8"))
    del tampered["content_hash"]
    index_path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")

    result = gen.audit(index_path=index_path, evidence_root=evidence_root)
    assert result.ok is False
    assert any("content_hash does not match" in problem for problem in result.problems)


# --- Warnings are carried verbatim into the row, gating or not -----------------


def test_non_gating_warning_is_carried_verbatim_into_the_row(tmp_path):
    """A warning that does not match any hard-fail/H12-demotion sentinel
    prefix (e.g. Translation's non-gating seed-shift note) must still be
    visible on the row -- `rederive_process` only ever *acts* on sentinel
    warnings, but ALL warnings result.json records must remain inspectable,
    never silently dropped."""
    non_gating_note = "SEED_SHIFT_NOTE: seed 7 realigned by 1 tick for this process; non-gating"
    _write_evidence_dir(tmp_path, "Metabolism", warnings=[non_gating_note])
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["warnings"] == [non_gating_note]
    # Non-gating: still green, since this warning matches no hard-fail sentinel.
    assert row["green"] is True


def test_no_warnings_yields_empty_warnings_list(tmp_path):
    _write_evidence_dir(tmp_path, "Metabolism")
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["warnings"] == []


# --- sweep_provenance staleness surfaced through the generator -----------------


def test_unknown_git_sha_alone_does_not_demote_when_hashes_match(tmp_path):
    """git SHA is informational only, not gating (scope-corrected): an
    unknown git_sha with otherwise-current source hashes/evaluator schema
    version must remain green, and `row["sweep_provenance"]["git_sha"]`
    still surfaces the unknown value for human inspection."""
    evidence_dir = _write_evidence_dir(tmp_path, "Metabolism")
    prov_path = evidence_dir / schema.SWEEP_PROVENANCE_FILE
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    prov["git_sha"] = "unknown"
    prov_path.write_text(json.dumps(prov), encoding="utf-8")

    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is True
    assert not any(schema.STATUS_STALE_PROVENANCE in reason for reason in row["reasons"])
    assert row["sweep_provenance"]["git_sha"] == "unknown"


def test_stale_sweep_provenance_source_hash_mismatch_is_non_green(tmp_path):
    evidence_dir = _write_evidence_dir(tmp_path, "Metabolism")
    prov_path = evidence_dir / schema.SWEEP_PROVENANCE_FILE
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    prov["source_hashes"]["runner"] = "f" * 64
    prov_path.write_text(json.dumps(prov), encoding="utf-8")

    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is False
    assert any(schema.STATUS_STALE_PROVENANCE in reason and "runner" in reason for reason in row["reasons"])


def test_evaluator_schema_version_mismatch_alone_does_not_demote(tmp_path):
    """v3 policy change (staleness-vs-ceremonial-rerun fix): a
    `sweep_provenance.json` recorded under an OLDER `evaluator_schema_version`
    (e.g. the real v2 sentinels on disk today) must NOT be treated as stale
    provenance by itself -- gating on this field would force a full sweep
    rerun any time `verdict.py`'s mechanical re-derivation logic is fixed,
    even though no process/oracle/threshold changed and the stored raw
    result.json already has every field the new logic needs. The value is
    still recorded/surfaced on the row informationally."""
    evidence_dir = _write_evidence_dir(tmp_path, "Metabolism")
    prov_path = evidence_dir / schema.SWEEP_PROVENANCE_FILE
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    assert prov["evaluator_schema_version"] != -1
    prov["evaluator_schema_version"] = -1
    prov_path.write_text(json.dumps(prov), encoding="utf-8")

    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is True
    assert not any(schema.STATUS_STALE_PROVENANCE in reason for reason in row["reasons"])
    assert row["sweep_provenance"]["evaluator_schema_version"] == -1


def test_evaluator_schema_version_mismatch_with_missing_raw_field_is_still_non_green(tmp_path):
    """The staleness gate being removed does NOT mean a genuinely
    insufficient raw payload is silently accepted: if the stored
    result.json is missing a raw field the CURRENT evaluator logic
    requires, the affected channel/process must still come back non-green
    (`MISSING_EVALUATOR`), independent of whatever `evaluator_schema_version`
    the sentinel happens to record."""
    evidence_dir = _write_evidence_dir(tmp_path, "Metabolism")
    prov_path = evidence_dir / schema.SWEEP_PROVENANCE_FILE
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    prov["evaluator_schema_version"] = -1
    prov_path.write_text(json.dumps(prov), encoding="utf-8")

    result_path = evidence_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    primary_name = next(iter(result["channels"]))
    del result["channels"][primary_name]["n_nonzero_oc"]
    result_path.write_text(json.dumps(result), encoding="utf-8")

    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is False
    assert any(schema.STATUS_MISSING_EVALUATOR in reason for reason in row["reasons"])


def test_missing_sweep_provenance_file_is_missing_evidence(tmp_path):
    """Evidence dating from before the provenance hardening (no
    sweep_provenance.json at all) is honestly MISSING_EVIDENCE, never
    silently grandfathered in as PASS."""
    evidence_dir = _write_evidence_dir(tmp_path, "Metabolism")
    (evidence_dir / schema.SWEEP_PROVENANCE_FILE).unlink()

    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is False
    assert row["mechanical_verdict"] == schema.STATUS_MISSING_EVIDENCE


# --- R1 sentinel binding: cross-process copy / sidecar tamper ------------------


def test_sentinel_copied_from_a_different_process_is_rejected(tmp_path):
    """Copying ReplicationInitiation's `sweep_provenance.json` verbatim onto
    Transcription's evidence dir -- the exact R1 attack this hardening
    exists to prevent -- must be rejected: the sentinel's own `process`
    field immediately disagrees with the evidence directory it now sits in."""
    _write_evidence_dir(tmp_path, "ReplicationInitiation")
    _write_evidence_dir(tmp_path, "Transcription")
    donor_prov_path = tmp_path / "ReplicationInitiation" / schema.DESIGN_A_SUBDIR / schema.SWEEP_PROVENANCE_FILE
    donor_prov = json.loads(donor_prov_path.read_text(encoding="utf-8"))
    victim_dir = tmp_path / "Transcription" / schema.DESIGN_A_SUBDIR
    (victim_dir / schema.SWEEP_PROVENANCE_FILE).write_text(json.dumps(donor_prov), encoding="utf-8")

    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Transcription")
    assert row["green"] is False
    assert any(
        "process=" in reason and "ReplicationInitiation" in reason and "Transcription" in reason
        for reason in row["reasons"]
    )


def test_sentinel_hand_edited_process_field_still_rejected_via_sidecar_hash(tmp_path):
    """Even if an attacker hand-edits the copied sentinel's `process`/
    `n_seeds`/`m_ticks` fields to match Transcription (defeating the naive
    field-equality check alone), its `sidecar_hashes` still record
    ReplicationInitiation's actual result.json/input_manifest.json bytes,
    which do not match Transcription's real files -- the sentinel can never
    be laundered onto a different process's evidence this way."""
    _write_evidence_dir(tmp_path, "ReplicationInitiation")
    transcription_entry = _ENTRIES["Transcription"]
    _write_evidence_dir(tmp_path, "Transcription")
    donor_prov_path = tmp_path / "ReplicationInitiation" / schema.DESIGN_A_SUBDIR / schema.SWEEP_PROVENANCE_FILE
    donor_prov = json.loads(donor_prov_path.read_text(encoding="utf-8"))
    donor_prov["process"] = "Transcription"
    donor_prov["n_seeds"] = transcription_entry.n_seeds
    donor_prov["m_ticks"] = transcription_entry.m_ticks
    victim_dir = tmp_path / "Transcription" / schema.DESIGN_A_SUBDIR
    (victim_dir / schema.SWEEP_PROVENANCE_FILE).write_text(json.dumps(donor_prov), encoding="utf-8")

    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Transcription")
    assert row["green"] is False
    assert not any("process=" in reason for reason in row["reasons"])  # the naive check alone now agrees
    assert any("sidecar_hashes" in reason for reason in row["reasons"])


def test_sidecar_tamper_after_generation_invalidates_the_sentinel_binding(tmp_path):
    """Mutating a mandatory sidecar file's bytes (e.g. thresholds.json) AFTER
    the sentinel was written, without regenerating the sentinel, must be
    caught -- the sentinel's recorded `sidecar_hashes[fname]` no longer
    matches what is actually on disk."""
    evidence_dir = _write_evidence_dir(tmp_path, "Metabolism")
    (evidence_dir / "thresholds.json").write_text(json.dumps({"channels": {"tampered": True}}), encoding="utf-8")

    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is False
    assert any("sidecar_hashes" in reason and "thresholds.json" in reason for reason in row["reasons"])


# --- R2 SUT hash: a code change to one process's karr_<process>.py --------------


def test_sut_oc_module_change_stales_only_that_process(tmp_path):
    """A code change to ONE process's own `karr_<process>.py` implementation
    must stale only that process's row -- not any other process, even
    though both share the same fixed runner/helpers/projections/catalog
    source hashes (R2). Uses synthetic throwaway modules (never the real
    tracked `opencell/vivarium/karr_*.py` files) so this test never mutates
    real production biology code."""
    module_a = tmp_path / "src" / "karr_fake_a.py"
    module_b = tmp_path / "src" / "karr_fake_b.py"
    module_a.parent.mkdir(parents=True, exist_ok=True)
    module_a.write_text("# fake SUT A v1\n", encoding="utf-8")
    module_b.write_text("# fake SUT B v1\n", encoding="utf-8")

    base = _ENTRIES["Metabolism"]
    entry_a = dataclasses.replace(base, name="FakeProcA", oc_module=str(module_a))
    entry_b = dataclasses.replace(base, name="FakeProcB", oc_module=str(module_b))

    evidence_root = tmp_path / "evidence"
    for entry in (entry_a, entry_b):
        evidence_dir = evidence_root / entry.name / schema.DESIGN_A_SUBDIR
        evidence_dir.mkdir(parents=True, exist_ok=True)
        expected_seeds = list(range(entry.n_seeds))
        _write_json(
            evidence_dir / "result.json",
            {
                "process": entry.name,
                "verdict": "PASS",
                "seeds": expected_seeds,
                "ticks": entry.m_ticks,
                "channels": {entry.primary_channel or "substrates": _baseline_channel()},
                "warnings": [],
            },
        )
        _write_json(
            evidence_dir / "input_manifest.json",
            {"inputs": default_input_records(), "resolved_seeds": expected_seeds, "m_ticks": entry.m_ticks},
        )
        _write_json(
            evidence_dir / "provenance.json", {"generated_at": "2026-01-01T00:00:00+00:00", "git_sha": "deadbeef"}
        )
        write_mandatory_sidecars(evidence_dir)
        write_valid_sweep_provenance(
            evidence_dir, process=entry.name, n_seeds=entry.n_seeds, m_ticks=entry.m_ticks, oc_module=entry.oc_module
        )

    row_a_before = gen.build_process_row(entry_a, evidence_root)
    row_b_before = gen.build_process_row(entry_b, evidence_root)
    assert row_a_before["green"] is True, row_a_before["reasons"]
    assert row_b_before["green"] is True, row_b_before["reasons"]

    # Simulate a code change to process A's own SUT only.
    module_a.write_text("# fake SUT A v2 -- behavior changed\n", encoding="utf-8")

    row_a_after = gen.build_process_row(entry_a, evidence_root)
    row_b_after = gen.build_process_row(entry_b, evidence_root)
    assert row_a_after["green"] is False
    assert any("oc_module" in reason for reason in row_a_after["reasons"])
    assert row_b_after["green"] is True, row_b_after["reasons"]  # untouched process B remains green


# --- Per-process runtime dependency modules beyond oc_module (F5: explicit
# --- registry `schema.PROCESS_DEPENDENCY_FILES`, e.g. Metabolism's
# --- opencell/m1/fva.py) --------------------------------------------------------


def test_metric_dependency_module_change_stales_only_that_process(tmp_path, monkeypatch):
    """A change to a process's registered runtime dependency module
    (`schema.PROCESS_DEPENDENCY_FILES`, e.g. Metabolism's
    `opencell/m1/fva.py`/`calc_flux_bounds.py`/`karr_metabolism.py`, none of
    which are hashed by any other existing key) must stale only that
    process's row, mirroring the R2 `oc_module` property -- exercised here
    via a synthetic throwaway dependency module (never the real
    `opencell/m1/fva.py`) monkeypatched into the registry under
    "Metabolism", so this test never mutates real production biology/metric
    code. A second, untouched process (DNARepair, which has no entry in
    `PROCESS_DEPENDENCY_FILES`) must remain unaffected -- proving this is not
    a generic "hash everything" check but genuinely process-scoped."""
    dep_module = tmp_path / "src" / "fake_fva.py"
    dep_module.parent.mkdir(parents=True, exist_ok=True)
    dep_module.write_text("# fake fva dependency v1\n", encoding="utf-8")

    monkeypatch.setitem(schema.PROCESS_DEPENDENCY_FILES, "Metabolism", {"fake_metric_dep": dep_module})

    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "Metabolism")
    _write_evidence_dir(evidence_root, "DNARepair")

    row_metab_before = gen.build_process_row(_ENTRIES["Metabolism"], evidence_root)
    row_dna_before = gen.build_process_row(_ENTRIES["DNARepair"], evidence_root)
    assert row_metab_before["green"] is True, row_metab_before["reasons"]
    assert row_dna_before["green"] is True, row_dna_before["reasons"]

    # Simulate a code change to Metabolism's registered metric dependency module.
    dep_module.write_text("# fake fva dependency v2 -- behavior changed\n", encoding="utf-8")

    row_metab_after = gen.build_process_row(_ENTRIES["Metabolism"], evidence_root)
    row_dna_after = gen.build_process_row(_ENTRIES["DNARepair"], evidence_root)
    assert row_metab_after["green"] is False
    assert any("fake_metric_dep" in reason for reason in row_metab_after["reasons"])
    assert row_dna_after["green"] is True, row_dna_after["reasons"]  # untouched process remains green


def test_metabolism_source_hashes_include_real_fva_dependency_modules(tmp_path):
    """Sanity check against the REAL (non-monkeypatched) registry: a fresh
    Metabolism `sweep_provenance.json["source_hashes"]` must actually
    contain `fva_module`/`calc_flux_bounds_module`/`m1_karr_metabolism_module`
    keys (not just the four shared + oc_module), and the row must read
    green today, proving the real `opencell/m1/fva.py` et al. are being
    hashed for Metabolism right now, not merely in a synthetic test
    double."""
    evidence_dir = _write_evidence_dir(tmp_path, "Metabolism")
    prov = json.loads((evidence_dir / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    for key in ("fva_module", "calc_flux_bounds_module", "m1_karr_metabolism_module"):
        assert key in prov["source_hashes"], f"missing {key!r} in Metabolism source_hashes"
        assert prov["source_hashes"][key], f"{key!r} hash is empty/None"

    row = gen.build_process_row(_ENTRIES["Metabolism"], tmp_path)
    assert row["green"] is True, row["reasons"]


def test_karr_metabolism_writeback_and_m3_translation_are_registered_and_hashed(tmp_path):
    """Sanity check against the REAL (non-monkeypatched) registry for the F1
    additions: Metabolism's sentinel must carry
    `karr_metabolism_writeback_module` (its own `karr_metabolism.py` imports
    `opencell.m1.karr_metabolism_writeback` at module scope) and
    Translation's sentinel must carry `m3_translation_module` (its own
    `karr_translation.py` imports `opencell.m3.translation` at module
    scope) -- both rows must still read green today."""
    metab_dir = _write_evidence_dir(tmp_path, "Metabolism")
    metab_prov = json.loads((metab_dir / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    assert metab_prov["source_hashes"].get("karr_metabolism_writeback_module"), (
        "Metabolism source_hashes missing karr_metabolism_writeback_module"
    )
    row_metab = gen.build_process_row(_ENTRIES["Metabolism"], tmp_path)
    assert row_metab["green"] is True, row_metab["reasons"]

    translation_dir = _write_evidence_dir(tmp_path, "Translation")
    translation_prov = json.loads((translation_dir / schema.SWEEP_PROVENANCE_FILE).read_text(encoding="utf-8"))
    assert translation_prov["source_hashes"].get("m3_translation_module"), (
        "Translation source_hashes missing m3_translation_module"
    )
    row_translation = gen.build_process_row(_ENTRIES["Translation"], tmp_path)
    assert row_translation["green"] is True, row_translation["reasons"]


# --- F1: l2_replay_common.py is a harness-scoped shared dependency of every
# --- design_a_per_tick process, never event_class ------------------------------


def test_l2_replay_common_change_stales_every_design_a_process_but_not_event_class(tmp_path, monkeypatch):
    """A change to `l2_replay_common.py` (imported by
    `_l2_2_design_a_runner_helpers.py`, which every `design_a_per_tick`
    process's evidence generation runs through) must stale every
    `design_a_per_tick` row -- but never an `event_class` row, since that
    harness does not go through this runner/helpers module at all. Uses a
    synthetic throwaway file monkeypatched into
    `schema.HARNESS_DEPENDENCY_FILES["design_a_per_tick"]` (never the real
    tracked `tests/vivarium/l2_replay_common.py`) so this test never
    mutates real production code."""
    fake_common = tmp_path / "src" / "fake_l2_replay_common.py"
    fake_common.parent.mkdir(parents=True, exist_ok=True)
    fake_common.write_text("# fake l2_replay_common v1\n", encoding="utf-8")
    monkeypatch.setitem(schema.HARNESS_DEPENDENCY_FILES, "design_a_per_tick", {"l2_replay_common": fake_common})

    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "DNARepair")  # design_a_per_tick
    _write_evidence_dir(evidence_root, "DNADamage")  # event_class

    row_design_a_before = gen.build_process_row(_ENTRIES["DNARepair"], evidence_root)
    row_event_before = gen.build_process_row(_ENTRIES["DNADamage"], evidence_root)
    assert row_design_a_before["green"] is True, row_design_a_before["reasons"]
    assert row_event_before["green"] is True, row_event_before["reasons"]

    # Simulate a change to the shared l2_replay_common.py dependency.
    fake_common.write_text("# fake l2_replay_common v2 -- behavior changed\n", encoding="utf-8")

    row_design_a_after = gen.build_process_row(_ENTRIES["DNARepair"], evidence_root)
    row_event_after = gen.build_process_row(_ENTRIES["DNADamage"], evidence_root)
    assert row_design_a_after["green"] is False
    assert any("l2_replay_common" in reason for reason in row_design_a_after["reasons"])
    assert row_event_after["green"] is True, row_event_after["reasons"]  # event_class never bound this key


# --- Final zero-cost delta (Opus5 ACCEPT bbc6aa6 conditional follow-up):
# --- `opencell/vivarium/__init__.py` is a genuinely PROCESS-AGNOSTIC
# --- shared dependency (registered in `SWEEP_PROVENANCE_SOURCE_FILES`,
# --- not the harness-scoped `HARNESS_DEPENDENCY_FILES`) since EVERY
# --- in-scope process's `oc_module` lives under `opencell/vivarium/` and
# --- therefore always executes this package's `__init__.py` first -------------


def test_vivarium_init_change_stales_every_design_a_process(tmp_path, monkeypatch):
    """A change to `opencell/vivarium/__init__.py` (executed by Python's
    ordinary package-import semantics whenever ANY of the 18
    `design_a_per_tick` processes' `opencell/vivarium/karr_<process>.py`
    `oc_module` is imported) must stale ALL 18 `design_a_per_tick` rows --
    not a subset, since this dependency is registered in the always-
    applies `schema.SWEEP_PROVENANCE_SOURCE_FILES` dict (like `runner`/
    `helpers`/`projections`/`catalog`), not the per-process
    `PROCESS_DEPENDENCY_FILES` registry or the harness-scoped
    `HARNESS_DEPENDENCY_FILES` one. Uses a synthetic throwaway file
    monkeypatched into `schema.SWEEP_PROVENANCE_SOURCE_FILES["vivarium_init"]`
    (never the real tracked `opencell/vivarium/__init__.py`) so this test
    never mutates real production code."""
    fake_init = tmp_path / "src" / "fake_vivarium_init.py"
    fake_init.parent.mkdir(parents=True, exist_ok=True)
    fake_init.write_text("# fake vivarium __init__ v1\n", encoding="utf-8")
    monkeypatch.setitem(schema.SWEEP_PROVENANCE_SOURCE_FILES, "vivarium_init", fake_init)

    design_a_names = [name for name, entry in _ENTRIES.items() if entry.harness_type == "design_a_per_tick"]
    assert len(design_a_names) == 18, f"expected exactly 18 design_a_per_tick processes, got {len(design_a_names)}"

    evidence_root = tmp_path / "evidence"
    for name in design_a_names:
        _write_evidence_dir(evidence_root, name)

    rows_before = {name: gen.build_process_row(_ENTRIES[name], evidence_root) for name in design_a_names}
    for name, row in rows_before.items():
        assert row["green"] is True, (name, row["reasons"])

    # Simulate a change to the shared opencell/vivarium/__init__.py dependency.
    fake_init.write_text("# fake vivarium __init__ v2 -- behavior changed\n", encoding="utf-8")

    rows_after = {name: gen.build_process_row(_ENTRIES[name], evidence_root) for name in design_a_names}
    for name, row in rows_after.items():
        assert row["green"] is False, f"{name} should have gone stale after vivarium_init change"
        assert any("vivarium_init" in reason for reason in row["reasons"]), (name, row["reasons"])


def test_vivarium_init_is_registered_process_agnostically_not_per_harness(tmp_path, monkeypatch):
    """`vivarium_init` must live in the always-applies
    `schema.SWEEP_PROVENANCE_SOURCE_FILES` dict, not scoped by
    `harness_type` -- since EVERY in-scope oc_module (all 22, `event_class`
    included) lives under `opencell/vivarium/`, this dependency is not
    narrower than "always", unlike `l2_replay_common.py` (which only
    `design_a_per_tick` processes route through). This is a structural
    regression guard: it fails if a future edit accidentally moves
    `vivarium_init` into `HARNESS_DEPENDENCY_FILES` instead."""
    assert "vivarium_init" in schema.SWEEP_PROVENANCE_SOURCE_FILES
    assert schema.SWEEP_PROVENANCE_SOURCE_FILES["vivarium_init"] == schema.VIVARIUM_INIT_MODULE
    for harness_deps in schema.HARNESS_DEPENDENCY_FILES.values():
        assert "vivarium_init" not in harness_deps


# --- F5: chromosome_store.py / chromosome_views.py are EXPLICIT per-process
# --- registry entries (correcting F1's mechanical AST-derivation, which
# --- Opus5 rejected as a runtime trust surface) --------------------------------


def test_chromosome_store_change_stales_only_registered_processes(tmp_path, monkeypatch):
    """`chromosome_store.py` is an EXPLICIT `schema.PROCESS_DEPENDENCY_FILES`
    entry for DNARepair/DNASupercoiling/Replication/ReplicationInitiation --
    never mechanically re-derived at hash time (F5 correction of the
    rejected F1 design). Monkeypatching ONLY DNARepair's registered
    `chromosome_store_module` entry to a synthetic throwaway file and
    changing that file must stale DNARepair alone: Replication (whose own
    registry entry still points at the REAL, untouched
    `schema.CHROMOSOME_STORE_MODULE`) and Transcription (which has no
    `chromosome_store_module` entry at all) must both remain green --
    proving this is a genuinely per-process explicit registry, not a
    single shared global key that would stale every chromosome-adjacent
    process at once."""
    fake_store = tmp_path / "src" / "fake_chromosome_store.py"
    fake_store.parent.mkdir(parents=True, exist_ok=True)
    fake_store.write_text("# fake chromosome_store v1\n", encoding="utf-8")
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES,
        "DNARepair",
        {**schema.PROCESS_DEPENDENCY_FILES["DNARepair"], "chromosome_store_module": fake_store},
    )

    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "DNARepair")
    _write_evidence_dir(evidence_root, "Replication")
    _write_evidence_dir(evidence_root, "Transcription")

    row_dnarepair_before = gen.build_process_row(_ENTRIES["DNARepair"], evidence_root)
    row_replication_before = gen.build_process_row(_ENTRIES["Replication"], evidence_root)
    row_transcription_before = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    assert row_dnarepair_before["green"] is True, row_dnarepair_before["reasons"]
    assert row_replication_before["green"] is True, row_replication_before["reasons"]
    assert row_transcription_before["green"] is True, row_transcription_before["reasons"]

    fake_store.write_text("# fake chromosome_store v2 -- behavior changed\n", encoding="utf-8")

    row_dnarepair_after = gen.build_process_row(_ENTRIES["DNARepair"], evidence_root)
    row_replication_after = gen.build_process_row(_ENTRIES["Replication"], evidence_root)
    row_transcription_after = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    assert row_dnarepair_after["green"] is False
    assert any("chromosome_store_module" in reason for reason in row_dnarepair_after["reasons"])
    assert row_replication_after["green"] is True, row_replication_after["reasons"]
    assert row_transcription_after["green"] is True, row_transcription_after["reasons"]


def test_chromosome_views_change_stales_only_dnarepair_not_dnasupercoiling(tmp_path, monkeypatch):
    """DNARepair's EXPLICIT registry entry carries BOTH
    `chromosome_store_module` and `chromosome_views_module`;
    DNASupercoiling's entry carries only `chromosome_store_module` (no
    `chromosome_views_module` key at all) -- reflecting each process's OWN
    real import graph, verified by direct inspection when this registry
    was written (see `schema.py`). Monkeypatching DNARepair's
    `chromosome_views_module` entry alone and changing that file must
    stale DNARepair while leaving DNASupercoiling untouched (it never
    bound that key in the first place)."""
    fake_views = tmp_path / "src" / "fake_chromosome_views.py"
    fake_views.parent.mkdir(parents=True, exist_ok=True)
    fake_views.write_text("# fake chromosome_views v1\n", encoding="utf-8")
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES,
        "DNARepair",
        {**schema.PROCESS_DEPENDENCY_FILES["DNARepair"], "chromosome_views_module": fake_views},
    )

    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "DNARepair")  # registry includes chromosome_views_module
    _write_evidence_dir(evidence_root, "DNASupercoiling")  # registry does not

    row_dnarepair_before = gen.build_process_row(_ENTRIES["DNARepair"], evidence_root)
    row_supercoiling_before = gen.build_process_row(_ENTRIES["DNASupercoiling"], evidence_root)
    assert row_dnarepair_before["green"] is True, row_dnarepair_before["reasons"]
    assert row_supercoiling_before["green"] is True, row_supercoiling_before["reasons"]

    fake_views.write_text("# fake chromosome_views v2 -- behavior changed\n", encoding="utf-8")

    row_dnarepair_after = gen.build_process_row(_ENTRIES["DNARepair"], evidence_root)
    row_supercoiling_after = gen.build_process_row(_ENTRIES["DNASupercoiling"], evidence_root)
    assert row_dnarepair_after["green"] is False
    assert any("chromosome_views_module" in reason for reason in row_dnarepair_after["reasons"])
    assert row_supercoiling_after["green"] is True, row_supercoiling_after["reasons"]


def test_removed_registry_key_stales_evidence_generated_against_larger_set(tmp_path, monkeypatch):
    """F5 requirement 4 (bidirectional staleness) at the `generator`
    audit-path level (mirrors `test_evidence_is_valid_rejects_extra_source_
    hash_key` in `test_l22_evidence_sweep.py`, which covers the SAME check
    in `sweep.evidence_is_valid`): evidence generated while a process had
    an EXTRA registry entry (simulated here as a synthetic dependency key)
    must go stale once that key is removed from the registry, even though
    every remaining (smaller) expected key set still matches -- otherwise a
    shrunk/renamed registry could silently "de-stale" old evidence that
    was never actually re-validated against the smaller dependency set."""
    fake_dep = tmp_path / "src" / "fake_dep.py"
    fake_dep.parent.mkdir(parents=True, exist_ok=True)
    fake_dep.write_text("# fake dependency\n", encoding="utf-8")

    original_dnarepair_deps = dict(schema.PROCESS_DEPENDENCY_FILES["DNARepair"])
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES, "DNARepair", {**original_dnarepair_deps, "fake_extra_dep": fake_dep}
    )
    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "DNARepair")
    row_before = gen.build_process_row(_ENTRIES["DNARepair"], evidence_root)
    assert row_before["green"] is True, row_before["reasons"]

    # Now simulate the registry entry being removed/renamed (never
    # re-running the sweep): the recorded sentinel still has the old
    # "fake_extra_dep" key, but the CURRENT expected set no longer
    # includes it.
    monkeypatch.setitem(schema.PROCESS_DEPENDENCY_FILES, "DNARepair", original_dnarepair_deps)
    row_after = gen.build_process_row(_ENTRIES["DNARepair"], evidence_root)
    assert row_after["green"] is False
    assert any("extra" in reason and "fake_extra_dep" in reason for reason in row_after["reasons"]), row_after["reasons"]


def test_process_dependency_registry_matches_real_current_import_graph():
    """Sanity check against the REAL (non-monkeypatched) explicit registry:
    verifies today's `schema.PROCESS_DEPENDENCY_FILES` matches the actual
    current import graph (verified by direct AST inspection when F5 wrote
    this registry, and B1/C2 extended it -- see `schema.py`'s per-constant
    comments), so a future edit to any `karr_*.py` file that adds/removes
    a first-party import is forced to be a deliberate, visible change to
    this test (and, more importantly, will fail
    `test_l22_evidence_ast_completeness.py::test_zero_uncovered_first_party_
    imports_across_real_in_scope_processes`) rather than silently drifting
    unnoticed."""
    assert set(schema.PROCESS_DEPENDENCY_FILES["DNARepair"]) == {
        "chromosome_store_module",
        "chromosome_views_module",
        "m_gen_constants_module",
        "state_init_module",
    }
    for name in ("DNASupercoiling", "Replication", "ReplicationInitiation"):
        assert "chromosome_store_module" in schema.PROCESS_DEPENDENCY_FILES[name], name
        # B1: `chromosome_store.py` itself has a one-hop class-body
        # dependency on `m_gen_constants.py` (the default chromosome
        # shape), so EVERY chromosome_store consumer registers it now,
        # not only DNASupercoiling/DNADamage (whose OWN `oc_module` also
        # imports it directly).
        assert "m_gen_constants_module" in schema.PROCESS_DEPENDENCY_FILES[name], name
        # C2: every chromosome_store consumer also registers
        # `opencell/state/__init__.py` (executed by importing any
        # `opencell.state.*` submodule).
        assert "state_init_module" in schema.PROCESS_DEPENDENCY_FILES[name], name
    assert "chromosome_views_module" not in schema.PROCESS_DEPENDENCY_FILES.get("DNASupercoiling", {})
    assert "chromosome_views_module" not in schema.PROCESS_DEPENDENCY_FILES.get("Replication", {})
    assert "chromosome_views_module" not in schema.PROCESS_DEPENDENCY_FILES.get("ReplicationInitiation", {})

    assert set(schema.PROCESS_DEPENDENCY_FILES["Metabolism"]) == {
        "fva_module",
        "calc_flux_bounds_module",
        "m1_karr_metabolism_module",
        "karr_metabolism_writeback_module",
        "karr_protein_decay_light_module",
        "m1_init_module",
    }
    assert set(schema.PROCESS_DEPENDENCY_FILES["Translation"]) == {
        "m3_translation_module",
        "karr_translation_v3_module",
        "m3_init_module",
    }
    assert set(schema.PROCESS_DEPENDENCY_FILES["Transcription"]) == {"m2_transcription_module", "m2_init_module"}
    for name in ("ProteinProcessingI", "RNAProcessing"):
        assert schema.PROCESS_DEPENDENCY_FILES[name] == {
            "karr_trna_aminoacylation_module": schema.KARR_TRNA_AMINOACYLATION_MODULE
        }, name
    assert set(schema.PROCESS_DEPENDENCY_FILES["ProteinTranslocation"]) == {"util_module", "util_matlab_rng_module"}
    assert set(schema.PROCESS_DEPENDENCY_FILES["DNASupercoiling"]) == {
        "chromosome_store_module",
        "m_gen_constants_module",
        "state_init_module",
    }
    assert set(schema.PROCESS_DEPENDENCY_FILES["DNADamage"]) == {
        "chromosome_store_module",
        "chromosome_views_module",
        "m_gen_constants_module",
        "state_init_module",
    }

    for name, deps in schema.PROCESS_DEPENDENCY_FILES.items():
        for key, path in deps.items():
            assert path.is_file(), f"{name}.{key} -> {path} does not exist on disk"


def test_m2_transcription_module_change_stales_only_transcription(tmp_path, monkeypatch):
    """F5 addition: Transcription's `karr_transcription.py` imports
    `opencell.m2.transcription` at module scope -- verified by direct
    inspection. A change to it must stale only Transcription."""
    fake_module = tmp_path / "src" / "fake_m2_transcription.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.write_text("# fake m2 transcription v1\n", encoding="utf-8")
    monkeypatch.setitem(schema.PROCESS_DEPENDENCY_FILES, "Transcription", {"m2_transcription_module": fake_module})

    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "Transcription")
    _write_evidence_dir(evidence_root, "RNAProcessing")

    row_before = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    row_other_before = gen.build_process_row(_ENTRIES["RNAProcessing"], evidence_root)
    assert row_before["green"] is True, row_before["reasons"]
    assert row_other_before["green"] is True, row_other_before["reasons"]

    fake_module.write_text("# fake m2 transcription v2 -- behavior changed\n", encoding="utf-8")

    row_after = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    row_other_after = gen.build_process_row(_ENTRIES["RNAProcessing"], evidence_root)
    assert row_after["green"] is False
    assert any("m2_transcription_module" in reason for reason in row_after["reasons"])
    assert row_other_after["green"] is True, row_other_after["reasons"]


def test_karr_protein_decay_light_change_stales_metabolism(tmp_path, monkeypatch):
    """F5 addition: Metabolism's `karr_metabolism.py` imports `_Mcg16807`
    (the MCG RNG) from `opencell/vivarium/karr_protein_decay_light.py` --
    verified by direct inspection. A change to it must stale Metabolism
    (which registers it as an extra dependency) but not ProteinDecay
    (whose OWN `oc_module` IS this same file, hashed there under the
    `"oc_module"` key -- a separate, already-covered code path, exercised
    here via a synthetic throwaway file so this test never touches
    ProteinDecay's real `oc_module` hash)."""
    fake_module = tmp_path / "src" / "fake_karr_protein_decay_light.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.write_text("# fake karr_protein_decay_light v1\n", encoding="utf-8")
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES,
        "Metabolism",
        {**schema.PROCESS_DEPENDENCY_FILES["Metabolism"], "karr_protein_decay_light_module": fake_module},
    )

    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "Metabolism")
    _write_evidence_dir(evidence_root, "ProteinDecay")

    row_before = gen.build_process_row(_ENTRIES["Metabolism"], evidence_root)
    row_decay_before = gen.build_process_row(_ENTRIES["ProteinDecay"], evidence_root)
    assert row_before["green"] is True, row_before["reasons"]
    assert row_decay_before["green"] is True, row_decay_before["reasons"]

    fake_module.write_text("# fake karr_protein_decay_light v2 -- behavior changed\n", encoding="utf-8")

    row_after = gen.build_process_row(_ENTRIES["Metabolism"], evidence_root)
    row_decay_after = gen.build_process_row(_ENTRIES["ProteinDecay"], evidence_root)
    assert row_after["green"] is False
    assert any("karr_protein_decay_light_module" in reason for reason in row_after["reasons"])
    assert row_decay_after["green"] is True, row_decay_after["reasons"]  # unaffected: fake file, not its real oc_module


def test_karr_trna_aminoacylation_change_stales_both_registered_processes(tmp_path, monkeypatch):
    """F5 addition: BOTH ProteinProcessingI's and RNAProcessing's
    `oc_module` files import helper functions from
    `opencell/vivarium/karr_trna_aminoacylation.py` -- verified by direct
    inspection. A change to it must stale both, but not an unrelated
    process (ProteinTranslocation, which has no such entry)."""
    fake_module = tmp_path / "src" / "fake_karr_trna_aminoacylation.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.write_text("# fake karr_trna_aminoacylation v1\n", encoding="utf-8")
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES, "ProteinProcessingI", {"karr_trna_aminoacylation_module": fake_module}
    )
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES, "RNAProcessing", {"karr_trna_aminoacylation_module": fake_module}
    )

    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "ProteinProcessingI")
    _write_evidence_dir(evidence_root, "RNAProcessing")
    _write_evidence_dir(evidence_root, "ProteinTranslocation")

    row_i_before = gen.build_process_row(_ENTRIES["ProteinProcessingI"], evidence_root)
    row_rna_before = gen.build_process_row(_ENTRIES["RNAProcessing"], evidence_root)
    row_translocation_before = gen.build_process_row(_ENTRIES["ProteinTranslocation"], evidence_root)
    assert row_i_before["green"] is True, row_i_before["reasons"]
    assert row_rna_before["green"] is True, row_rna_before["reasons"]
    assert row_translocation_before["green"] is True, row_translocation_before["reasons"]

    fake_module.write_text("# fake karr_trna_aminoacylation v2 -- behavior changed\n", encoding="utf-8")

    row_i_after = gen.build_process_row(_ENTRIES["ProteinProcessingI"], evidence_root)
    row_rna_after = gen.build_process_row(_ENTRIES["RNAProcessing"], evidence_root)
    row_translocation_after = gen.build_process_row(_ENTRIES["ProteinTranslocation"], evidence_root)
    assert row_i_after["green"] is False
    assert any("karr_trna_aminoacylation_module" in reason for reason in row_i_after["reasons"])
    assert row_rna_after["green"] is False
    assert any("karr_trna_aminoacylation_module" in reason for reason in row_rna_after["reasons"])
    assert row_translocation_after["green"] is True, row_translocation_after["reasons"]


def test_util_matlab_rng_change_stales_only_protein_translocation(tmp_path, monkeypatch):
    """F5 addition: ProteinTranslocation's `oc_module` does `from
    opencell.util import MatlabRandStream` -- `opencell.util` is a
    PACKAGE, so both the direct import target (`util_module` ->
    `opencell/util/__init__.py`) and the file that actually defines the
    RNG logic it re-exports (`util_matlab_rng_module` ->
    `opencell/util/matlab_rng.py`) are registered. A change to the RNG
    implementation file alone must stale ProteinTranslocation."""
    fake_module = tmp_path / "src" / "fake_matlab_rng.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.write_text("# fake matlab_rng v1\n", encoding="utf-8")
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES,
        "ProteinTranslocation",
        {**schema.PROCESS_DEPENDENCY_FILES["ProteinTranslocation"], "util_matlab_rng_module": fake_module},
    )

    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "ProteinTranslocation")
    _write_evidence_dir(evidence_root, "ProteinFolding")

    row_before = gen.build_process_row(_ENTRIES["ProteinTranslocation"], evidence_root)
    row_other_before = gen.build_process_row(_ENTRIES["ProteinFolding"], evidence_root)
    assert row_before["green"] is True, row_before["reasons"]
    assert row_other_before["green"] is True, row_other_before["reasons"]

    fake_module.write_text("# fake matlab_rng v2 -- behavior changed\n", encoding="utf-8")

    row_after = gen.build_process_row(_ENTRIES["ProteinTranslocation"], evidence_root)
    row_other_after = gen.build_process_row(_ENTRIES["ProteinFolding"], evidence_root)
    assert row_after["green"] is False
    assert any("util_matlab_rng_module" in reason for reason in row_after["reasons"])
    assert row_other_after["green"] is True, row_other_after["reasons"]


def test_m_gen_constants_change_stales_only_dnasupercoiling_direct_import(tmp_path, monkeypatch):
    """F5 addition (B1-updated docstring): DNASupercoiling's
    `karr_dna_supercoiling.py` imports `GENOME_LENGTH_BP` from
    `opencell/m_gen_constants.py` directly (module scope) -- verified by
    direct inspection. A change to it must stale DNASupercoiling but not
    Transcription (which has no `m_gen_constants_module` entry at all).
    NOTE: since B1, DNARepair/Replication/ReplicationInitiation ALSO
    register `m_gen_constants_module` (transitively, via
    `chromosome_store.py`'s own one-hop class-body dependency on it -- see
    `test_m_gen_constants_change_stales_all_chromosome_store_consumers`
    below for that coverage), so this test now uses Transcription (which
    shares NONE of the chromosome-coupled registry keys) as the genuinely
    unrelated control process instead."""
    fake_module = tmp_path / "src" / "fake_m_gen_constants.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.write_text("# fake m_gen_constants v1\n", encoding="utf-8")
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES,
        "DNASupercoiling",
        {**schema.PROCESS_DEPENDENCY_FILES["DNASupercoiling"], "m_gen_constants_module": fake_module},
    )

    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "DNASupercoiling")
    _write_evidence_dir(evidence_root, "Transcription")

    row_before = gen.build_process_row(_ENTRIES["DNASupercoiling"], evidence_root)
    row_other_before = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    assert row_before["green"] is True, row_before["reasons"]
    assert row_other_before["green"] is True, row_other_before["reasons"]

    fake_module.write_text("# fake m_gen_constants v2 -- behavior changed\n", encoding="utf-8")

    row_after = gen.build_process_row(_ENTRIES["DNASupercoiling"], evidence_root)
    row_other_after = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    assert row_after["green"] is False
    assert any("m_gen_constants_module" in reason for reason in row_after["reasons"])
    assert row_other_after["green"] is True, row_other_after["reasons"]


def test_m_gen_constants_change_stales_all_chromosome_store_consumers(tmp_path, monkeypatch):
    """B1 (Opus5 "explicit registry REJECT" follow-up): `chromosome_store.py`
    -- already registered as `chromosome_store_module` for EVERY process
    that imports it -- has its OWN one-hop, class-body-scope dependency on
    `opencell/m_gen_constants.py` (`GENOME_LENGTH_BP`/
    `N_CHROMOSOME_COMPARTMENTS`, consumed as `ChromosomeStore`'s default
    `shape`), verified by direct inspection. A change to
    `m_gen_constants.py` must therefore stale ALL FIVE
    chromosome_store-consuming processes -- DNARepair, DNASupercoiling,
    Replication, ReplicationInitiation, and (informationally) DNADamage --
    not just the two (DNASupercoiling/DNADamage) whose OWN `oc_module`
    happens to import it directly too, and must NOT stale an unrelated
    process (Transcription, which shares no chromosome-coupled registry
    keys at all)."""
    fake_module = tmp_path / "src" / "fake_m_gen_constants.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    fake_module.write_text("# fake m_gen_constants v1\n", encoding="utf-8")
    for name in ("DNARepair", "DNASupercoiling", "Replication", "ReplicationInitiation"):
        monkeypatch.setitem(
            schema.PROCESS_DEPENDENCY_FILES,
            name,
            {**schema.PROCESS_DEPENDENCY_FILES[name], "m_gen_constants_module": fake_module},
        )

    evidence_root = tmp_path / "evidence"
    consumers = ("DNARepair", "DNASupercoiling", "Replication", "ReplicationInitiation")
    for name in consumers:
        _write_evidence_dir(evidence_root, name)
    _write_evidence_dir(evidence_root, "Transcription")

    rows_before = {name: gen.build_process_row(_ENTRIES[name], evidence_root) for name in consumers}
    row_transcription_before = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    for name, row in rows_before.items():
        assert row["green"] is True, (name, row["reasons"])
    assert row_transcription_before["green"] is True, row_transcription_before["reasons"]

    fake_module.write_text("# fake m_gen_constants v2 -- behavior changed\n", encoding="utf-8")

    rows_after = {name: gen.build_process_row(_ENTRIES[name], evidence_root) for name in consumers}
    row_transcription_after = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    for name, row in rows_after.items():
        assert row["green"] is False, (name, row["reasons"])
        assert any("m_gen_constants_module" in reason for reason in row["reasons"]), (name, row["reasons"])
    assert row_transcription_after["green"] is True, row_transcription_after["reasons"]  # unrelated, unaffected


# --- C2: package `__init__.py` execution (m1/m2/m3/state) --------------------


def test_m1_init_change_stales_only_metabolism(tmp_path, monkeypatch):
    """C2: `opencell/m1/__init__.py` executes whenever Metabolism's
    `oc_module` imports any `opencell.m1` submodule (`from opencell.m1
    import calc_flux_bounds as cfb` / `from opencell.m1 import
    karr_metabolism as km`) -- real Python import-machinery behavior, not
    an artifact of static analysis. A change to it must stale Metabolism
    but not an unrelated process."""
    fake_init = tmp_path / "src" / "fake_m1_init.py"
    fake_init.parent.mkdir(parents=True, exist_ok=True)
    fake_init.write_text("# fake m1 __init__ v1\n", encoding="utf-8")
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES,
        "Metabolism",
        {**schema.PROCESS_DEPENDENCY_FILES["Metabolism"], "m1_init_module": fake_init},
    )

    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "Metabolism")
    _write_evidence_dir(evidence_root, "Transcription")

    row_before = gen.build_process_row(_ENTRIES["Metabolism"], evidence_root)
    row_other_before = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    assert row_before["green"] is True, row_before["reasons"]
    assert row_other_before["green"] is True, row_other_before["reasons"]

    fake_init.write_text("# fake m1 __init__ v2 -- behavior changed\n", encoding="utf-8")

    row_after = gen.build_process_row(_ENTRIES["Metabolism"], evidence_root)
    row_other_after = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    assert row_after["green"] is False
    assert any("m1_init_module" in reason for reason in row_after["reasons"])
    assert row_other_after["green"] is True, row_other_after["reasons"]


def test_m2_init_change_stales_only_transcription(tmp_path, monkeypatch):
    """C2: `opencell/m2/__init__.py` executes whenever Transcription's
    `oc_module` does `from opencell.m2 import transcription as tx`."""
    fake_init = tmp_path / "src" / "fake_m2_init.py"
    fake_init.parent.mkdir(parents=True, exist_ok=True)
    fake_init.write_text("# fake m2 __init__ v1\n", encoding="utf-8")
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES,
        "Transcription",
        {**schema.PROCESS_DEPENDENCY_FILES["Transcription"], "m2_init_module": fake_init},
    )

    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "Transcription")
    _write_evidence_dir(evidence_root, "Translation")

    row_before = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    row_other_before = gen.build_process_row(_ENTRIES["Translation"], evidence_root)
    assert row_before["green"] is True, row_before["reasons"]
    assert row_other_before["green"] is True, row_other_before["reasons"]

    fake_init.write_text("# fake m2 __init__ v2 -- behavior changed\n", encoding="utf-8")

    row_after = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    row_other_after = gen.build_process_row(_ENTRIES["Translation"], evidence_root)
    assert row_after["green"] is False
    assert any("m2_init_module" in reason for reason in row_after["reasons"])
    assert row_other_after["green"] is True, row_other_after["reasons"]


def test_m3_init_change_stales_only_translation(tmp_path, monkeypatch):
    """C2: `opencell/m3/__init__.py` executes whenever Translation's
    `oc_module` does `from opencell.m3 import translation as tl`."""
    fake_init = tmp_path / "src" / "fake_m3_init.py"
    fake_init.parent.mkdir(parents=True, exist_ok=True)
    fake_init.write_text("# fake m3 __init__ v1\n", encoding="utf-8")
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES,
        "Translation",
        {**schema.PROCESS_DEPENDENCY_FILES["Translation"], "m3_init_module": fake_init},
    )

    evidence_root = tmp_path / "evidence"
    _write_evidence_dir(evidence_root, "Translation")
    _write_evidence_dir(evidence_root, "Transcription")

    row_before = gen.build_process_row(_ENTRIES["Translation"], evidence_root)
    row_other_before = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    assert row_before["green"] is True, row_before["reasons"]
    assert row_other_before["green"] is True, row_other_before["reasons"]

    fake_init.write_text("# fake m3 __init__ v2 -- behavior changed\n", encoding="utf-8")

    row_after = gen.build_process_row(_ENTRIES["Translation"], evidence_root)
    row_other_after = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    assert row_after["green"] is False
    assert any("m3_init_module" in reason for reason in row_after["reasons"])
    assert row_other_after["green"] is True, row_other_after["reasons"]


def test_state_init_change_stales_all_chromosome_store_consumers_not_unrelated(tmp_path, monkeypatch):
    """C2: `opencell/state/__init__.py` executes whenever ANY of
    DNARepair/DNASupercoiling/Replication/ReplicationInitiation's
    `oc_module` imports `opencell.state.chromosome_store` -- real Python
    import-machinery behavior. A change to it must stale all four (the
    same mechanically-evidenced set already registering
    `chromosome_store_module`) but not an unrelated process."""
    fake_init = tmp_path / "src" / "fake_state_init.py"
    fake_init.parent.mkdir(parents=True, exist_ok=True)
    fake_init.write_text("# fake state __init__ v1\n", encoding="utf-8")
    consumers = ("DNARepair", "DNASupercoiling", "Replication", "ReplicationInitiation")
    for name in consumers:
        monkeypatch.setitem(
            schema.PROCESS_DEPENDENCY_FILES,
            name,
            {**schema.PROCESS_DEPENDENCY_FILES[name], "state_init_module": fake_init},
        )

    evidence_root = tmp_path / "evidence"
    for name in consumers:
        _write_evidence_dir(evidence_root, name)
    _write_evidence_dir(evidence_root, "Transcription")

    rows_before = {name: gen.build_process_row(_ENTRIES[name], evidence_root) for name in consumers}
    row_transcription_before = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    for name, row in rows_before.items():
        assert row["green"] is True, (name, row["reasons"])
    assert row_transcription_before["green"] is True, row_transcription_before["reasons"]

    fake_init.write_text("# fake state __init__ v2 -- behavior changed\n", encoding="utf-8")

    rows_after = {name: gen.build_process_row(_ENTRIES[name], evidence_root) for name in consumers}
    row_transcription_after = gen.build_process_row(_ENTRIES["Transcription"], evidence_root)
    for name, row in rows_after.items():
        assert row["green"] is False, (name, row["reasons"])
        assert any("state_init_module" in reason for reason in row["reasons"]), (name, row["reasons"])
    assert row_transcription_after["green"] is True, row_transcription_after["reasons"]  # unrelated, unaffected


# --- R3 oracle input manifest: empty inputs / strict mounted-data rehash -------


def test_empty_input_manifest_inputs_is_non_green(tmp_path):
    _write_evidence_dir(tmp_path, "Metabolism", inputs=[])
    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is False
    assert any(schema.STATUS_EMPTY_INPUT_MANIFEST in reason for reason in row["reasons"])


def test_default_mode_tolerates_missing_oracle_data_but_strict_mode_requires_mounted_data(monkeypatch, tmp_path):
    """Default (portable/fresh-clone) mode trusts `sweep_provenance.json`'s
    `inputs_verified` attestation for a gitignored oracle-data input without
    requiring it to physically exist. `--verify-input-files`
    (`strict_input_files=True`) opts into requiring it be mounted."""
    monkeypatch.setattr(gen.cat, "REPO_ROOT", tmp_path)
    entry = _ENTRIES["Metabolism"]
    manifest = {
        "resolved_seeds": list(range(entry.n_seeds)),
        "inputs": [{"path": "data/_fixture_probe_oracle.mat", "sha256": "0" * 64}],
    }
    default_reasons = gen._check_current_tree_staleness(manifest, entry=entry, strict_input_files=False)
    assert not any(schema.STATUS_STALE_VS_TREE in reason for reason in default_reasons)

    strict_reasons = gen._check_current_tree_staleness(manifest, entry=entry, strict_input_files=True)
    assert any(
        schema.STATUS_STALE_VS_TREE in reason and "not mounted" in reason for reason in strict_reasons
    )


def test_strict_mode_rehashes_mounted_oracle_data_and_detects_mutation(monkeypatch, tmp_path):
    """When the oracle data genuinely IS mounted, strict mode must actually
    rehash it and catch a mutation -- an `inputs_verified: true` attestation
    alone is not sufficient once the caller opts into re-verification."""
    monkeypatch.setattr(gen.cat, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    oracle_file = tmp_path / "data" / "_fixture_probe_oracle.mat"
    oracle_file.write_bytes(b"mounted-oracle-bytes")
    original_sha = gen._sha256_file(oracle_file)
    entry = _ENTRIES["Metabolism"]
    manifest = {
        "resolved_seeds": list(range(entry.n_seeds)),
        "inputs": [{"path": "data/_fixture_probe_oracle.mat", "sha256": original_sha}],
    }
    assert gen._check_current_tree_staleness(manifest, entry=entry, strict_input_files=True) == []

    oracle_file.write_bytes(b"mutated-oracle-bytes-swapped")
    strict_reasons = gen._check_current_tree_staleness(manifest, entry=entry, strict_input_files=True)
    assert any(schema.STATUS_STALE_VS_TREE in reason and "sha256 changed" in reason for reason in strict_reasons)

    # Default (non-strict) mode never itself rehashes the oracle-data file,
    # so it stays silent about this same drift.
    default_reasons = gen._check_current_tree_staleness(manifest, entry=entry, strict_input_files=False)
    assert not any("_fixture_probe_oracle.mat" in reason for reason in default_reasons)
