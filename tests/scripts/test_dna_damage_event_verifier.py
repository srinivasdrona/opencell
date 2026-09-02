"""Focused tests for the tracked DNADamage latest_event verifier bundle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import dna_damage_event_verifier as verifier  # noqa: E402
from scripts.l22_evidence import generator as gen  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402


def _bundle_dir() -> Path:
    return schema.BUNDLE_ROOT / "DNADamage" / schema.EVENT_CLASS_SUBDIR


def test_tracked_dna_damage_bundle_scores_pass():
    row = gen.build_process_row(gen.cat.in_scope_processes()["DNADamage"], schema.BUNDLE_ROOT)
    assert row["mechanical_verdict"] == schema.STATUS_PASS
    assert row["green"] is True
    assert row["channel_verdicts"]["chromosome"] == schema.STATUS_PASS


def test_tracked_full_verify_discloses_overlay_hash_provenance():
    payload = json.loads((_bundle_dir() / "full_verify.json").read_text(encoding="utf-8"))
    provenance = payload["overlay_hash_metadata_provenance"]
    assert provenance["all_traces_carry_overlay_hashes"] is True
    assert provenance["required_fields"] == list(verifier.REQUIRED_OVERLAY_HASH_FIELDS)
    for field in verifier.REQUIRED_OVERLAY_HASH_FIELDS:
        assert provenance["present_counts_by_field"][field] == payload["identity_validation_total"]
    assert payload["mechanical_verdict"] == schema.STATUS_PASS


def test_verify_corpus_canary_condition_label_and_overlay_hashes():
    # Regression test: the corpus writes bare `condition_label` values (e.g.
    # "uvb_mechanism") with no colon suffix; verify_corpus() must accept
    # that literal format rather than expecting a "condition:suffix" shape
    # that the extractor never produces.
    payload = verifier.verify_corpus(root=verifier.CANARY_ROOT, expected_seed_labels=list(range(2000, 2005)))
    assert payload["identity_validation_failures"] == []
    assert payload["identity_validation_ok_count"] == payload["identity_validation_total"] == 5
    assert payload["condition_label_values"] == [verifier.CONDITION]
    assert payload["overlay_hash_metadata_provenance"]["all_traces_carry_overlay_hashes"] is True


def test_verify_corpus_fails_closed_on_missing_overlay_hash_field(tmp_path, monkeypatch):
    real_metadata_text = verifier._metadata_text

    def _patched(handle, key):  # noqa: ANN001
        if key == "dnadamage_source_resolved_sha256":
            return None
        return real_metadata_text(handle, key)

    monkeypatch.setattr(verifier, "_metadata_text", _patched)
    try:
        verifier.verify_corpus(root=verifier.CANARY_ROOT, expected_seed_labels=list(range(2000, 2005)))
    except verifier.VerifierError as exc:
        assert "dnadamage_source_resolved_sha256" in str(exc)
    else:
        raise AssertionError("verify_corpus should fail closed when an overlay hash field is missing")



    row_before = gen.build_process_row(gen.cat.in_scope_processes()["DNADamage"], schema.BUNDLE_ROOT)
    assert row_before["green"] is True, row_before["reasons"]

    fake_verifier = tmp_path / "src" / "fake_dna_damage_event_verifier.py"
    fake_verifier.parent.mkdir(parents=True, exist_ok=True)
    fake_verifier.write_text("# fake verifier drift v1\n", encoding="utf-8")
    monkeypatch.setitem(
        schema.PROCESS_DEPENDENCY_FILES,
        "DNADamage",
        {
            **schema.PROCESS_DEPENDENCY_FILES["DNADamage"],
            "dna_damage_event_verifier_module": fake_verifier,
        },
    )

    fake_verifier.write_text("# fake verifier drift v2\n", encoding="utf-8")
    row_after = gen.build_process_row(gen.cat.in_scope_processes()["DNADamage"], schema.BUNDLE_ROOT)
    assert row_after["green"] is False
    assert any("dna_damage_event_verifier_module" in reason for reason in row_after["reasons"])
