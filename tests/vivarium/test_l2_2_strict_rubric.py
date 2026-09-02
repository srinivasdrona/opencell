"""L2.2 strict-rubric test — integrity/audit gate over the mechanically
generated evidence index (see docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md).

This replaces the old hand-written `EXPECTED_L2_2_VERDICTS` pin (22
hand-asserted per-process verdict strings cross-referenced against a second
hand-written `EMPIRICAL_VERDICTS` dict in scripts/probe_l2_2_strict_audit.py).
That design was circular: both "expected" and "actual" were hand-typed by a
human, so the test could never catch a wrong claim -- it could only detect
disagreement between two opinions, neither of which was measured.

This test is the INTEGRITY/AUDIT gate (stage A), not the ACCEPTANCE gate
(stage B):
  - Stage A (this file): passes when the tracked `evidence_index.json` is a
    truthful, untampered, byte-for-byte-reproducible (minus `generated_at`)
    reflection of the current catalog + evidence tree. It is expected and
  REQUIRED to pass even when today's aggregate verdict is NON_GREEN. A real
  Design-A runner sweep populated evidence for 16/18 in-scope
  design_a_per_tick processes earlier (2026-07-28), but that evidence
  predates the provenance-hardening requirement (see
  docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md Section 13) that every
  row carry a `sweep_provenance.json` completion sentinel written
  atomically by `sweep.py run_job`. Since none of it was launched through
  that sentinel-writing path, it is unprovable and honestly reads
  MISSING_EVIDENCE for all 22 rows today, pending a hardened sweep rerun
  (Phase B). Faking a green -- or a fabricated mixed -- result here would
  be exactly the kind of fabrication this rewrite exists to prevent.
  - Stage B (NOT this file): `scripts/l22_evidence/generator.py audit
    --require-all-pass` / `scripts/probe_l2_2_strict_audit.py
    --require-all-pass` returns nonzero until every in-scope process is
    mechanically GREEN. It is deliberately NOT wired into pytest/CI yet --
    that wiring is a follow-up activation commit after process closure, not
    a silently-skipped or xfail'd test today.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import generator as gen  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402


def test_committed_evidence_index_exists():
    assert schema.INDEX_PATH.is_file(), (
        f"{schema.INDEX_PATH} is missing. It is a generator-only tracked artifact -- "
        "regenerate it with `bin\\oc-py scripts/l22_evidence/generator.py generate` "
        "and commit the result; never hand-edit it."
    )


def test_committed_evidence_index_passes_integrity_audit():
    """The tracked index must be exactly what a fresh regeneration produces.

    `audit()` never trusts anything already written to disk (stored verdict
    strings, stored content_hash, stored row set) as ground truth -- it
    rebuilds the index from scratch from the catalog + evidence tree and
    diffs. This is the sole tamper/staleness defense; see generator.audit's
    docstring.
    """
    result = gen.audit()
    assert result.ok, f"evidence_index.json failed integrity audit: {result.problems}"


def test_committed_evidence_index_is_honestly_non_green_today():
    """This task MUST report a truthful non-green index, never a fabricated
    PASS. The tally hardcoded here has moved three times since this test was
    first written (see the historical narrative that used to live in this
    docstring, now superseded -- the full evaluator-only re-derivation
    history for the earlier moves is
    docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md Section 13.14, and for
    this move Section 13.15):

    As of this commit (DNADamage's Sept-2 genuine literal-rate-law closure,
    joining PPII's already-closed main-branch PASS) the tally is
    PASS: 18, FAIL: 2, MISSING_EVIDENCE: 2, n_in_scope: 22:
      - PASS (18): DNADamage, DNARepair, Metabolism, ProteinDecay,
        ProteinFolding, ProteinModification, ProteinProcessingI,
        ProteinProcessingII, ProteinTranslocation, RNADecay,
        RNAModification, RNAProcessing, Replication, ReplicationInitiation,
        RibosomeAssembly, Transcription, Translation, tRNAAminoacylation.
      - FAIL (2): MacromolecularComplexation, DNASupercoiling.
      - MISSING_EVIDENCE (2): Cytokinesis, FtsZPolymerization.

    This is a deliberate, evidence-driven set of mechanical re-derivations
    (per this task's "if not provable, mark stale/non-green; if the raw
    metrics support it, mark PASS -- never infer, never hand-edit" rule),
    not a regression or a fabrication. If this test ever needs to change
    again, that change must be driven by real evidence (a sweep rerun
    populating/changing rows under the evidence tree, or a further
    evaluator correctness fix with cited raw-metric evidence), not by
    editing this assertion to make it pass."""
    result = gen.audit()
    assert result.aggregate_verdict == "NON_GREEN"
    assert result.tally == {
        schema.STATUS_PASS: 18,
        schema.STATUS_FAIL: 2,
        schema.STATUS_MISSING_EVIDENCE: 2,
    }


def test_committed_evidence_index_covers_scope_exactly_once():
    """One row per in_scope_L2_2 catalog process, exactly once, no extras."""
    payload = gen.build_evidence_index()
    entries = cat.in_scope_processes()
    process_names = [row["process"] for row in payload["rows"]]

    assert len(process_names) == len(set(process_names)), "duplicate rows in evidence index"
    assert set(process_names) == set(entries.keys())
    assert payload["n_in_scope"] == len(entries) == 22


def test_require_all_pass_acceptance_gate_is_not_yet_wired_into_ci():
    """Documents (does not silently skip) that stage B is intentionally not
    active. This is not a fake/xfail acceptance test -- it asserts the CLI
    machinery for stage B exists and correctly refuses to claim acceptance
    today, without pytest itself gating CI on `--require-all-pass`."""
    payload = gen.build_evidence_index()
    assert payload["aggregate_verdict"] != "GREEN", (
        "Acceptance gate would need explicit activation (a follow-up commit wiring "
        "`--require-all-pass` into CI) once this flips to GREEN -- do not wire it "
        "preemptively while it is still non-green."
    )
