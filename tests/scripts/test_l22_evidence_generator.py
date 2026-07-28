"""Coverage + determinism tests for scripts/l22_evidence/generator.py against
the REAL PROCESS_CATALOG.yaml and the real evidence tree.

As of this commit the tree is honestly all MISSING_EVIDENCE: the Phase-A
provenance-hardening rules (mandatory `sweep_provenance.json` completion
sentinel) just landed, and the pre-hardening evidence on disk does not
carry that sentinel yet, so it is correctly demoted rather than
grandfathered in as compliant -- see
docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md.

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


def test_real_sweep_evidence_today_reflects_hardened_reruns_for_two_processes():
    """As of this commit, DNARepair and ReplicationInitiation have been
    rerun through the hardened `sweep.py run_job` at their catalog M=200
    (the depth200 oracle now provides real 200-tick per-seed traces for
    these two catalog M=200 processes; ProteinDecay -- also catalog M=200
    -- could not be completed in this pass because the Design-A harness's
    memory footprint at M=200 grows roughly linearly without plateauing and
    was terminated pre-OOM before completion, so it remains MISSING_EVIDENCE
    pending a follow-up). Their evidence now carries a real
    `sweep_provenance.json` completion sentinel with a real git SHA + source
    hashes matching the CURRENT runner/helpers/projections/catalog files, so
    they are the first two rows honestly promoted out of MISSING_EVIDENCE.
    The remaining 16 in-scope processes still only hold evidence from BEFORE
    the Phase-A provenance hardening landed -- none of it carries
    `sweep_provenance.json` yet, since those processes have not been rerun
    through the hardened `sweep.py run_job`. This is the honest, expected
    transitional state: every one of those previously "PASS"/"FAIL" rows is
    correctly demoted to MISSING_EVIDENCE rather than silently grandfathered
    in as compliant (see the evidence-gate task's explicit instruction:
    unprovable prior launches must be marked stale and scheduled for rerun,
    never inferred as valid). Further Phase-B reruns/migration will
    re-populate real PASS/FAIL rows behind this same test file; until then NO
    other row may ever be fabricated PASS."""
    payload = gen.build_evidence_index()
    assert payload["aggregate_verdict"] == "NON_GREEN"
    for row in payload["rows"]:
        if row["green"]:
            assert row["mechanical_verdict"] == schema.STATUS_PASS
        else:
            assert row["mechanical_verdict"] != schema.STATUS_PASS
    assert payload["tally"] == {schema.STATUS_MISSING_EVIDENCE: 20, schema.STATUS_PASS: 2}
    green_rows = {row["process"] for row in payload["rows"] if row["green"]}
    assert green_rows == {"DNARepair", "ReplicationInitiation"}


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
    # `evidence_root`/each row's `evidence_dir` are themselves excluded from
    # content_hash (see generator._scrub_environment_relative -- they record
    # ambient read-location, not durable evidence identity, since the
    # portable bundle is a byte-identical mirror of the live tree). This
    # still changes content_hash here because the *data* genuinely differs:
    # `l2_2_gates_alt` is empty, so every row becomes MISSING_EVIDENCE
    # instead of baseline's real mechanically re-derived verdicts.
    assert baseline["content_hash"] != alternate["content_hash"]
    assert baseline["evidence_root"] != alternate["evidence_root"]
    assert all(row["mechanical_verdict"] == schema.STATUS_MISSING_EVIDENCE for row in alternate["rows"])


def test_write_index_then_audit_round_trips_cleanly(tmp_path):
    payload = gen.build_evidence_index()
    index_path = tmp_path / "evidence_index.json"
    gen.write_index(payload, index_path)

    result = gen.audit(index_path=index_path, evidence_root=schema.EVIDENCE_ROOT)
    assert result.ok is True
    assert result.aggregate_verdict == "NON_GREEN"
    assert result.tally == {schema.STATUS_MISSING_EVIDENCE: 20, schema.STATUS_PASS: 2}


def test_audit_reports_failure_when_index_file_absent(tmp_path):
    result = gen.audit(index_path=tmp_path / "does_not_exist.json")
    assert result.ok is False
    assert result.problems
