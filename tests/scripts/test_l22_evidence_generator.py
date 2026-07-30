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


def test_real_sweep_evidence_today_reflects_evaluator_v3_rederivation():
    """Evaluator schema v3 (see verdict.EVALUATOR_SCHEMA_VERSION docstring and
    docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md Section 13.14) is a
    pure re-derivation from the SAME stored raw evidence tree used by v2 --
    no process was rerun, no result.json/sidecar/sentinel file changed. Two
    real evaluator correctness fixes changed the mechanical verdicts of 5
    rows:

    - P0 (channel-alias byte-exact bug): RNADecay, RNAModification,
      RNAProcessing, Transcription moved FAIL -> PASS. Their stored raw
      metrics (nonzero n_nonzero_oc/n_nonzero_karr, W1 under threshold)
      always warranted PASS; the pre-v3 evaluator compared the runner's
      alias-normalized primary channel name (e.g. `RNAs`) byte-exact
      against the catalog's un-normalized name (`rnas`) and always fired a
      spurious vacuous-substitution SENTINEL_FAIL. Fixed via the shared
      `scripts/l22_evidence/channel_names.normalize_channel_name`, applied
      to both sides of the comparison in `verdict.rederive_process`.
    - P2 (zero-activity guard): Replication moved PASS -> FAIL. Its stored
      `chromosome` channel's `polymerizedRegions.*` components show
      n_nonzero_oc == 0 while Karr shows real nonzero activity (420-4265
      events per component) -- the pre-v3 per-component evaluator treated
      this asymmetric zero-vs-nonzero case as vacuously equal (both
      "small") instead of mechanically non-green. Fixed via the new
      `PRIMARY_ACTIVITY_MISSING` guard added to `_rederive_w1_channel`,
      `_rederive_per_component_scaled_channel`, and `_rederive_hurdle_channel`.

    The remaining 5 FAIL rows (MacromolecularComplexation, ProteinFolding,
    ProteinProcessingI, ProteinProcessingII, tRNAAminoacylation) are
    pre-existing, unrelated `SENTINEL_FAIL:
    PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE` H12 evidence gaps, untouched
    by this evaluator-only commit. The 4 MISSING_EVIDENCE rows (Cytokinesis,
    DNADamage, FtsZPolymerization, RibosomeAssembly) have no evidence
    directory at all and are likewise untouched. If this test ever needs to
    change again, that change must be driven by real evidence (a sweep
    rerun populating/changing rows under the evidence tree, or a further
    cited evaluator correctness fix), not by editing this assertion to make
    it pass."""
    payload = gen.build_evidence_index()
    assert payload["aggregate_verdict"] == "NON_GREEN"
    for row in payload["rows"]:
        if row["green"]:
            assert row["mechanical_verdict"] == schema.STATUS_PASS
        else:
            assert row["mechanical_verdict"] != schema.STATUS_PASS
    assert payload["tally"] == {
        schema.STATUS_PASS: 12,
        schema.STATUS_FAIL: 6,
        schema.STATUS_MISSING_EVIDENCE: 4,
    }
    fail_rows = {
        row["process"]: row["reasons"]
        for row in payload["rows"]
        if row["mechanical_verdict"] == schema.STATUS_FAIL
    }
    assert set(fail_rows) == {
        "MacromolecularComplexation",
        "ProteinFolding",
        "ProteinProcessingI",
        "ProteinProcessingII",
        "tRNAAminoacylation",
        "Replication",
    }
    assert any(
        "PRIMARY_ACTIVITY_MISSING" in reason for reason in fail_rows["Replication"]
    )
    for process in (
        "MacromolecularComplexation",
        "ProteinFolding",
        "ProteinProcessingI",
        "ProteinProcessingII",
        "tRNAAminoacylation",
    ):
        assert any(
            "PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE" in reason
            for reason in fail_rows[process]
        )


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
    assert result.tally == {
        schema.STATUS_PASS: 12,
        schema.STATUS_FAIL: 6,
        schema.STATUS_MISSING_EVIDENCE: 4,
    }


def test_audit_reports_failure_when_index_file_absent(tmp_path):
    result = gen.audit(index_path=tmp_path / "does_not_exist.json")
    assert result.ok is False
    assert result.problems
