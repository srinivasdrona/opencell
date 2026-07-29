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
        evidence_dir, process=process_name, n_seeds=entry.n_seeds, m_ticks=entry.m_ticks, oc_module=entry.oc_module
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


def test_stale_sweep_provenance_evaluator_schema_version_mismatch_is_non_green(tmp_path):
    evidence_dir = _write_evidence_dir(tmp_path, "Metabolism")
    prov_path = evidence_dir / schema.SWEEP_PROVENANCE_FILE
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    prov["evaluator_schema_version"] = -1
    prov_path.write_text(json.dumps(prov), encoding="utf-8")

    payload = gen.build_evidence_index(evidence_root=tmp_path)
    row = _row_for(payload, "Metabolism")
    assert row["green"] is False
    assert any(
        schema.STATUS_STALE_PROVENANCE in reason and "evaluator_schema_version" in reason for reason in row["reasons"]
    )


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
