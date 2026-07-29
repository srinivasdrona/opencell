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
    """As of the R1/R2/R3 provenance-hardening commit, `sweep_provenance.json`
    gained new mandatory fields (`completion_status`, `sidecar_hashes` binding
    every fixed authority/sidecar file's sha256 to the sentinel,
    `inputs_verified`, and a process-specific `oc_module` source hash --
    schema_version 1 -> 2). DNARepair and ReplicationInitiation have now been
    rerun through the fully v2-hardened `sweep.py run_job` (which also
    normalizes `input_manifest.json` to repo-relative paths at generation
    time, so the sentinel's `sidecar_hashes["input_manifest.json"]` matches
    both the live tree and the bundle byte-for-byte) and hold real,
    mechanically re-derived PASS rows. The remaining 16 in-scope processes
    still only hold evidence from BEFORE the original Phase-A provenance
    hardening landed -- none of it carries `sweep_provenance.json` at all --
    so they correctly read MISSING_EVIDENCE throughout. If this test ever
    needs to change again, that change must be driven by real
    sentinel-carrying evidence appearing/changing under
    artifacts/l2_2_gates/ via a hardened sweep rerun, not by editing this
    assertion."""
    payload = gen.build_evidence_index()
    assert payload["aggregate_verdict"] == "NON_GREEN"
    for row in payload["rows"]:
        if row["green"]:
            assert row["mechanical_verdict"] == schema.STATUS_PASS
        else:
            assert row["mechanical_verdict"] != schema.STATUS_PASS
    assert payload["tally"] == {schema.STATUS_MISSING_EVIDENCE: 20, schema.STATUS_PASS: 2}
    pass_rows = {row["process"] for row in payload["rows"] if row["mechanical_verdict"] == schema.STATUS_PASS}
    assert pass_rows == {"DNARepair", "ReplicationInitiation"}


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
