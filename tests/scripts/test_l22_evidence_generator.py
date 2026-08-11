"""Coverage + determinism tests for scripts/l22_evidence/generator.py against
the REAL PROCESS_CATALOG.yaml and the real evidence tree.

As of this commit the real, mechanically re-derived tally is
PASS=15 / FAIL=4 / MISSING_EVIDENCE=3: RibosomeAssembly now bridges its
existing tracked L2.event N=50 PASS bundle into a valid `latest_event/`
L2.2 authority row, while Cytokinesis/DNADamage/FtsZ remain honest
MISSING_EVIDENCE. See
`test_real_sweep_evidence_today_reflects_evaluator_v3_rederivation` below
for the row-level provenance, plus
docs/phase_f/l2_2_design_a/h12/H12_REPORT.md for the earlier H12
machine-evidence changes that produced the other PASS rows.

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

    A THIRD, later evaluator correctness fix (the Opus5 follow-up review
    closing the "primary low-sample false-green" gap) changed one more row:

    - P5 (primary insufficient-samples guard): DNASupercoiling moved
      PASS -> FAIL. Its stored `chromosome` channel's primary per_component
      comparison on component `linkingNumbers.delta_nnz` has
      n_oc=17, n_karr=24 -- both nonzero (so neither VACUOUS nor
      ACTIVITY_MISSING applies) but both below `MIN_NONZERO_EVENTS=30`. The
      pre-fix evaluator still computed and passed a W1 statistic
      (scaled_w1=0.007) on this component despite the sample size being far
      too small to trust that statistic -- a false green. Fixed via the new
      `PRIMARY_INSUFFICIENT_SAMPLES` guard (gating, unlike the pre-existing
      generic non-primary `INSUFFICIENT_SAMPLES` fallback) added to
      `_rederive_w1_channel`, `_rederive_per_component_scaled_channel`, and
      `_rederive_hurdle_channel`.

    A FOURTH change (the H12 machine-evidence delivery, see
    docs/phase_f/l2_2_design_a/h12/H12_REPORT.md) moved 3 of the 5
    pre-existing `SENTINEL_FAIL: PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE`
    rows to real, machine-checked PASS by supplying an independently
    derived (Karr-source + fixture + states_before only, never touching
    SUT/runner/states_after during prediction) H12_CONFIRMED predictor
    artifact with 100% exact match on a nontrivial sample domain:
    ProteinFolding, ProteinProcessingI, tRNAAminoacylation. The remaining 2
    of those 5 rows -- MacromolecularComplexation, ProteinProcessingII --
    have real H12 artifacts too, but the machine-checked verdict for both
    is `H12_OBSERVED_REGIME` (not `H12_CONFIRMED`): MacromolecularComplexation's
    network2 branch and ProteinProcessingII's transferase branch are never
    exercised by the accepted raw oracle sample population, so full branch
    coverage cannot be claimed and the SENTINEL_FAIL demotion is correctly
    rejected -- they remain FAIL, non-green, pending either a broader
    sample population or a maintainer-reviewed catalog demotion.

    The 2 unrelated FAIL rows (Replication, DNASupercoiling) were untouched
    by that H12 delivery. This commit makes one further evidence-driven move:

    - RibosomeAssembly moves MISSING_EVIDENCE -> PASS, not by touching the
      shared tracked `evidence_index.json`, but by materializing a valid
      `docs/phase_f/l2_2_design_a/evidence_bundle/RibosomeAssembly/
      latest_event/` authority bundle from the already-hash-bound
      `docs/phase_f/l2_event/evidence_bundle/RibosomeAssembly/` source
      bundle. The generator still re-derives the verdict mechanically from
      raw metric fields only; the source bundle's stored PASS strings are
      never trusted.

    If this test ever needs to change again, that change must be driven by
    real evidence (a sweep rerun populating/changing rows under the evidence
    tree, a broader H12 artifact regeneration, or a further cited evaluator
    correctness fix), not by editing this assertion to make it pass."""
    payload = gen.build_evidence_index()
    assert payload["aggregate_verdict"] == "NON_GREEN"
    for row in payload["rows"]:
        if row["green"]:
            assert row["mechanical_verdict"] == schema.STATUS_PASS
        else:
            assert row["mechanical_verdict"] != schema.STATUS_PASS
    assert payload["tally"] == {
        schema.STATUS_PASS: 15,
        schema.STATUS_FAIL: 4,
        schema.STATUS_MISSING_EVIDENCE: 3,
    }
    fail_rows = {
        row["process"]: row["reasons"]
        for row in payload["rows"]
        if row["mechanical_verdict"] == schema.STATUS_FAIL
    }
    assert set(fail_rows) == {
        "MacromolecularComplexation",
        "ProteinProcessingII",
        "Replication",
        "DNASupercoiling",
    }
    assert any(
        "PRIMARY_ACTIVITY_MISSING" in reason for reason in fail_rows["Replication"]
    )
    assert any(
        "PRIMARY_INSUFFICIENT_SAMPLES" in reason for reason in fail_rows["DNASupercoiling"]
    )
    for process in (
        "MacromolecularComplexation",
        "ProteinProcessingII",
    ):
        assert any(
            "PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE" in reason
            for reason in fail_rows[process]
        )
        assert any(
            "H12_OBSERVED_REGIME" in reason for reason in fail_rows[process]
        )
    pass_rows = {row["process"] for row in payload["rows"] if row["mechanical_verdict"] == schema.STATUS_PASS}
    for process in ("ProteinFolding", "ProteinProcessingI", "tRNAAminoacylation"):
        assert process in pass_rows, f"{process} expected real H12_CONFIRMED PASS"
    assert "RibosomeAssembly" in pass_rows, "RibosomeAssembly expected bridged event-class PASS"


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

    # `evidence_root=None` mirrors the default `build_evidence_index()` call
    # above: both resolve via `schema.default_evidence_root()` (live
    # sweep-output tree if mounted locally, otherwise the tracked portable
    # bundle). Hardcoding `evidence_root=schema.EVIDENCE_ROOT` here is wrong
    # on a fresh clone / any worktree that has never run the live sweep --
    # EVIDENCE_ROOT is gitignored machine-local state, so `audit` would see
    # an empty/missing tree and every row would spuriously read
    # MISSING_EVIDENCE regardless of what the tracked portable bundle says.
    result = gen.audit(index_path=index_path, evidence_root=None)
    assert result.ok is True
    assert result.aggregate_verdict == "NON_GREEN"
    assert result.tally == {
        schema.STATUS_PASS: 15,
        schema.STATUS_FAIL: 4,
        schema.STATUS_MISSING_EVIDENCE: 3,
    }


def test_audit_reports_failure_when_index_file_absent(tmp_path):
    result = gen.audit(index_path=tmp_path / "does_not_exist.json")
    assert result.ok is False
    assert result.problems
