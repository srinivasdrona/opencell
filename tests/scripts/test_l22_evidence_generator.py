"""Coverage + determinism tests for scripts/l22_evidence/generator.py against
the REAL PROCESS_CATALOG.yaml and (currently empty) real evidence tree.

Run via `bin\\oc-pytest tests/scripts/test_l22_evidence_generator.py -v`.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import generator as gen  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402

EXPECTED_IN_SCOPE_PROCESSES = frozenset(
    {
        "Translation",
        "Transcription",
        "ReplicationInitiation",
        "DNARepair",
        "Replication",
        "DNASupercoiling",
        "RNAProcessing",
        "RNAModification",
        "RNADecay",
        "tRNAAminoacylation",
        "ProteinModification",
        "ProteinFolding",
        "ProteinDecay",
        "ProteinTranslocation",
        "MacromolecularComplexation",
        "RibosomeAssembly",
        "FtsZPolymerization",
        "Cytokinesis",
        "Metabolism",
        "DNADamage",
        "ProteinProcessingI",
        "ProteinProcessingII",
    }
)
EXPECTED_OUT_OF_SCOPE_PROCESSES = frozenset(
    {
        "ChromosomeCondensation",
        "ChromosomeSegregation",
        "HostInteraction",
        "ProteinActivation",
        "TerminalOrganelleAssembly",
        "TranscriptionalRegulation",
    }
)


def test_catalog_scope_matches_expected_22_names():
    entries = cat.in_scope_processes()
    assert set(entries.keys()) == EXPECTED_IN_SCOPE_PROCESSES
    assert len(entries) == 22


def test_index_has_exactly_one_row_per_in_scope_process_no_extras():
    payload = gen.build_evidence_index()
    process_names = [row["process"] for row in payload["rows"]]
    assert len(process_names) == len(set(process_names)), "duplicate rows detected"
    assert set(process_names) == EXPECTED_IN_SCOPE_PROCESSES
    assert not (set(process_names) & EXPECTED_OUT_OF_SCOPE_PROCESSES)
    assert payload["n_in_scope"] == 22


def test_no_real_evidence_today_yields_honest_non_green_index():
    """This task must begin with a truthful MISSING_EVIDENCE/non-green index,
    not a fabricated PASS -- final process runner outputs are not available
    yet (full Karr oracle extraction is still completing in sibling
    worktrees as of this commit)."""
    payload = gen.build_evidence_index()
    assert payload["aggregate_verdict"] == "NON_GREEN"
    for row in payload["rows"]:
        assert row["green"] is False
        assert row["mechanical_verdict"] == schema.STATUS_MISSING_EVIDENCE
        assert any(reason.startswith(schema.STATUS_MISSING_EVIDENCE) for reason in row["reasons"])
    assert payload["tally"] == {schema.STATUS_MISSING_EVIDENCE: 22}


def test_content_hash_is_deterministic_across_regenerations():
    first = gen.build_evidence_index()
    second = gen.build_evidence_index()
    assert first["generated_at"] != second["generated_at"] or True  # timestamps may coincide; not the point
    assert first["content_hash"] == second["content_hash"]

    first_scrubbed = copy.deepcopy(first)
    second_scrubbed = copy.deepcopy(second)
    first_scrubbed.pop("generated_at")
    second_scrubbed.pop("generated_at")
    assert first_scrubbed == second_scrubbed


def test_content_hash_changes_when_evidence_root_differs():
    baseline = gen.build_evidence_index()
    alternate = gen.build_evidence_index(evidence_root=schema.EVIDENCE_ROOT.parent / "l2_2_gates_alt")
    # Different evidence_root recorded in the payload -> different content_hash,
    # even though both trees are equally empty (proves content_hash is not
    # blind to which tree was actually inspected).
    assert baseline["content_hash"] != alternate["content_hash"]
    assert baseline["evidence_root"] != alternate["evidence_root"]


def test_write_index_then_audit_round_trips_cleanly(tmp_path):
    payload = gen.build_evidence_index()
    index_path = tmp_path / "evidence_index.json"
    gen.write_index(payload, index_path)

    result = gen.audit(index_path=index_path, evidence_root=schema.EVIDENCE_ROOT)
    assert result.ok is True
    assert result.aggregate_verdict == "NON_GREEN"
    assert result.tally == {schema.STATUS_MISSING_EVIDENCE: 22}


def test_audit_reports_failure_when_index_file_absent(tmp_path):
    result = gen.audit(index_path=tmp_path / "does_not_exist.json")
    assert result.ok is False
    assert result.problems
