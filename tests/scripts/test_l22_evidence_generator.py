"""Coverage + determinism tests for scripts/l22_evidence/generator.py against
the REAL PROCESS_CATALOG.yaml and the real evidence tree (partially
populated by a real Design-A runner sweep as of this commit -- see
docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md Section 11).

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


def test_real_sweep_evidence_today_yields_honest_mixed_non_green_index():
    """As of this commit, a real Design-A runner sweep has populated evidence
    for 16/18 in-scope design_a_per_tick processes (see
    docs/phase_f/l2_2_design_a/sweep_status.json): DNASupercoiling and
    Replication were re-run after the 29749df evaluator cherry-pick so their
    result.json carries the additive raw fields
    (scaled_distance_threshold/component_n_nonzero_oc/karr) the real
    per_component_scaled evaluator needs, and both are now real mechanical
    PASS instead of MISSING_EVALUATOR. DNARepair, ProteinDecay, and
    ReplicationInitiation hit a real oracle-data-insufficiency (catalog
    M_ticks=200 but the populated oracle only has 100 ticks); Metabolism is
    still executing (FVA is a severe cost outlier); the 4 event_class
    processes are explicitly out of scope for this sweep. No row may ever be
    fabricated PASS -- every PASS/FAIL below is a real mechanical
    re-derivation from raw channel metrics, and the aggregate remains
    NON_GREEN because not every in-scope process is real-PASS yet."""
    payload = gen.build_evidence_index()
    assert payload["aggregate_verdict"] == "NON_GREEN"
    for row in payload["rows"]:
        if row["green"]:
            assert row["mechanical_verdict"] == schema.STATUS_PASS
        else:
            assert row["mechanical_verdict"] != schema.STATUS_PASS
    assert payload["tally"] == {schema.STATUS_PASS: 9, schema.STATUS_FAIL: 5, schema.STATUS_MISSING_EVIDENCE: 8}


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
    assert result.tally == {schema.STATUS_PASS: 9, schema.STATUS_FAIL: 5, schema.STATUS_MISSING_EVIDENCE: 8}


def test_audit_reports_failure_when_index_file_absent(tmp_path):
    result = gen.audit(index_path=tmp_path / "does_not_exist.json")
    assert result.ok is False
    assert result.problems
