"""Coverage + determinism tests for scripts/l22_evidence/generator.py against
the REAL PROCESS_CATALOG.yaml and the real evidence tree.

As of this commit the real, mechanically re-derived tally is
PASS=18 / FAIL=2 / MISSING_EVIDENCE=2: DNADamage now joins RibosomeAssembly
and the (already-closed on main) ProteinProcessingII with a tracked
`latest_event`/H12 authority bundle, and Replication's corrected no-hint
port remains green. Cytokinesis/FtsZ remain honest MISSING_EVIDENCE. See
`test_real_sweep_evidence_today_reflects_evaluator_v3_rederivation` below
for the row-level provenance, plus
docs/phase_f/l2_2_design_a/h12/H12_REPORT.md for the earlier H12
machine-evidence changes that produced the other PASS rows.

Run via `bin\\oc-pytest tests/scripts/test_l22_evidence_generator.py -v`.
"""

from __future__ import annotations

import copy
import json
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

    Replication and DNASupercoiling were untouched by that H12 delivery.
    Replication later moved FAIL -> PASS through a current-tree N=50 rerun
    after its no-hint source semantics were corrected. This commit makes one
    further evidence-driven move:

    - RibosomeAssembly moves MISSING_EVIDENCE -> PASS, not by touching the
      shared tracked `evidence_index.json`, but by materializing a valid
      `docs/phase_f/l2_2_design_a/evidence_bundle/RibosomeAssembly/
      latest_event/` authority bundle from the already-hash-bound
      `docs/phase_f/l2_event/evidence_bundle/RibosomeAssembly/` source
      bundle. The generator still re-derives the verdict mechanically from
      raw metric fields only; the source bundle's stored PASS strings are
      never trusted.

    - DNADamage moves MISSING_EVIDENCE -> PASS through the tracked genuine
      corpus verifier in `scripts/l22_evidence/dna_damage_event_verifier.py`.
      That verifier replays the fixed OC process (the Sept-2 literal
      per-reaction Karr rate law in `opencell/vivarium/karr_dna_damage.py`)
      against the accepted local genuine UVB cohort, validates the cohort
      identity contract against `scripts/l2_event/dna_damage_stimulus_cohort.py`,
      requires and confirms every trace carries full
      `dnadamage_source_original/patched/resolved_sha256`/`_resolved_path`
      overlay-hash provenance (fail-closed -- a missing field raises rather
      than being tolerated as a legacy-corpus caveat), and writes a valid
      `docs/phase_f/l2_2_design_a/evidence_bundle/DNADamage/latest_event/`
      authority bundle plus tracked canary/full verifier JSONs. The
      generator again trusts only the raw hurdle metric fields, never the
      stored PASS string.

    - ProteinProcessingII's PASS (already closed on `main` prior to this
      branch's DNADamage work) is preserved unchanged through this branch's
      merge with `main`.

    A FIFTH change (MacromolecularComplexation's active-window closure; see
    STATUS_L22_MACROMOL_AUTHORITY_PROMOTION.md) moves
    MacromolecularComplexation FAIL -> PASS: the old row's
    `SENTINEL_FAIL: PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE`/
    `H12_OBSERVED_REGIME` FAIL was generated against the canonical EARLY
    100-tick oracle cohort, whose `tick_offset=0` windows never reach the
    naturally-occurring network-2 competitive branch at all (see
    `decisions/dec-004-macromol-network2-closed-form-dominant-withdrawn.md`).
    A new, source-faithful 50-seed ACTIVE-WINDOW cohort (each seed's real
    scheduler-discovered first network-2-formation tick, captured same-pass,
    genuine Statistics Toolbox provider) was extracted, validated, and
    mirrored byte-for-byte into the canonical
    `per_process_traces_v2_sNNN/` layout every other `design_a_per_tick`
    process already uses (see
    `scripts/l22_extraction/populate_canonical_macromol_traces.py`) -- the
    shared runner/helpers/catalog files are completely unmodified. The
    ordinary sweep against this cohort now reports a real mechanical
    `PASS` (all 3 channels `SEED_NOISE`), replacing the old stale
    SENTINEL_FAIL. NOTE: a separate, preregistered index-aware diagnostic
    (`scripts/l22_evidence/macromol_network2_selection_diagnostic.py`,
    NON-GATING for this row) found that literal per-seed network-2
    selection identity (which of the two competing complexes 22/23 forms)
    is NOT established -- see STATUS_L22_MACROMOL_AUTHORITY_PROMOTION.md
    for the full, honest caveat; it does not affect this mechanical,
    aggregate-distributional PASS.

    A SIXTH change (R11, this commit): ReplicationInitiation moves
    FAIL -> PASS. An independent integration review rejected an earlier
    candidate that placed genuine 200-tick data at the legacy hardcoded
    `_100ticks.mat` path; this closure instead stores all 50 genuine seeds
    honestly named `_200ticks.mat` (no seed-0 special case, no collision,
    no swap) and extracts ReplicationInitiation's own trace-path
    resolution/identity validation into a process-specific sibling module
    (`_l2_2_repinit_runner_helpers.py`, mirroring R7's DNASupercoiling
    tick-runner extraction), requiring only a two-line redirect in each of
    `_v2_seed_mat_path`/`load_karr_oracle` -- proven to leave the shared
    `"helpers"` provenance hash unchanged for every other process (see
    `tests/vivarium/test_l2_2_repinit_trace_identity.py`), with the other
    19 rows' `input_manifest.json` whole-file hash mechanically migrated
    forward (never rerun) by `scripts/l22_evidence/
    migrate_r11_repinit_provenance.py`. A genuine, fresh N=50/M=200 sweep
    was run to produce this row's own evidence.

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
        schema.STATUS_PASS: 20,
        schema.STATUS_MISSING_EVIDENCE: 2,
    }
    fail_rows = {
        row["process"]: row["reasons"]
        for row in payload["rows"]
        if row["mechanical_verdict"] == schema.STATUS_FAIL
    }
    assert set(fail_rows) == set(), (
        "R11: ReplicationInitiation's genuine N=50/M=200 sweep closed its row to PASS; "
        f"unexpected FAIL row(s): {set(fail_rows)!r}"
    )
    pass_rows = {row["process"] for row in payload["rows"] if row["mechanical_verdict"] == schema.STATUS_PASS}
    for process in ("ProteinFolding", "ProteinProcessingI", "ProteinProcessingII", "tRNAAminoacylation"):
        assert process in pass_rows, f"{process} expected real H12_CONFIRMED PASS"
    assert "DNADamage" in pass_rows, "DNADamage expected verified genuine-corpus PASS"
    assert "RibosomeAssembly" in pass_rows, "RibosomeAssembly expected bridged event-class PASS"
    assert "Replication" in pass_rows, "Replication expected current-tree N=50 PASS"
    assert "DNASupercoiling" in pass_rows, "DNASupercoiling expected accepted N=200 two-sided sparse-gate PASS"
    assert "MacromolecularComplexation" in pass_rows, (
        "MacromolecularComplexation expected active-window-cohort mechanical PASS"
    )
    assert "ReplicationInitiation" in pass_rows, "ReplicationInitiation expected R11 genuine N=50/M=200 PASS"


def test_dnas_canonical_bundle_uses_accepted_two_sided_sparse_gate_not_standard_per_component():
    """Regression for a real incident (2026-09-10): a subsequent standard
    `sweep.py run --processes DNASupercoiling --force` (needed to refresh
    provenance after an unrelated L1b oc-anchor fix touched
    `karr_dna_supercoiling.py`) silently reverted the canonical
    `evidence_bundle/DNASupercoiling/latest/result.json`'s `chromosome`
    channel from the accepted `dnas_two_sided_sparse_gate` promotion back to
    the standard sweep's own `per_component_scaled` aggregation --
    `scripts/l22_dnas_promote_n200_evidence.py` must be rerun with
    `--apply` after every standard-sweep refresh of this row, since the
    standard sweep only knows how to write its own generic aggregation.
    Opus's integration review caught this because it is a real methodology
    regression even though the process-level `mechanical_verdict` can still
    read PASS under either aggregation -- this test binds directly to the
    tracked `result.json` bytes so a future silent revert fails loudly here,
    not only in a human review.

    The exact three axes below are the Opus-accepted, frozen numbers from
    the `sept2_two_sided_rerun` evaluation (oric-join-closure fix
    included; see `STATUS_L22_DNAS_SEPT2.md` "Session 6" / commit
    `29f8f5f` upstream): pooled_nonzero_ticks 64 (OC) vs 65 (Karr),
    active_seeds 58 vs 58, clustered_seeds 6 vs 7, all BALANCED."""
    payload = gen.build_evidence_index()
    dnas_row = next(row for row in payload["rows"] if row["process"] == "DNASupercoiling")
    assert dnas_row["mechanical_verdict"] == schema.STATUS_PASS, (
        f"DNASupercoiling expected PASS, got {dnas_row['mechanical_verdict']!r}: {dnas_row.get('reasons')!r}"
    )

    result_path = REPO_ROOT / dnas_row["evidence_dir"] / "result.json"
    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    chromosome_channel = result_payload["channels"]["chromosome"]

    assert chromosome_channel.get("aggregation") == "dnas_two_sided_sparse_gate", (
        "DNASupercoiling's canonical chromosome channel must use the accepted "
        "dnas_two_sided_sparse_gate aggregation, never the standard sweep's "
        f"per_component_scaled -- got {chromosome_channel.get('aggregation')!r}. "
        "Rerun `python scripts/l22_dnas_promote_n200_evidence.py --apply` after "
        "any standard-sweep refresh of this row."
    )

    sparse_axes = {
        axis["axis"]: (axis["oc_count"], axis["karr_count"])
        for axis in chromosome_channel["sparse_component"]["axes"]
    }
    assert sparse_axes == {
        "pooled_nonzero_ticks": (64, 65),
        "active_seeds": (58, 58),
        "clustered_seeds": (6, 7),
    }, f"unexpected sparse_component axes: {sparse_axes!r}"


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
        schema.STATUS_PASS: 20,
        schema.STATUS_MISSING_EVIDENCE: 2,
    }


def test_audit_reports_failure_when_index_file_absent(tmp_path):
    result = gen.audit(index_path=tmp_path / "does_not_exist.json")
    assert result.ok is False
    assert result.problems


# --- Alternate --catalog/--registry threading (R6 follow-up, 2026-09-05) ------
#
# A narrower, pre-existing gap this task also closes: `_current_source_hashes`
# always hashed the DEFAULT `schema.CATALOG_PATH`/`schema.L2_EVENT_REGISTRY_PATH`
# for the `"catalog_entry"`/`"event_registry_entry"` keys regardless of the
# `catalog_path`/`registry_path` a caller passed to `build_evidence_index`/
# `build_process_row`/`audit` -- so an alternate-catalog audit (e.g. a
# staging/what-if copy) computed every row's contract-staleness hash against
# the REAL tracked file it was explicitly trying to bypass.


def test_current_source_hashes_honors_an_alternate_catalog_path(tmp_path):
    """`_current_source_hashes(entry, catalog_path=...)` must resolve
    `catalog_entry` against the GIVEN `catalog_path`, never silently fall
    back to the default `schema.CATALOG_PATH`."""
    real_entry = cat.in_scope_processes()["Translation"]
    real_hashes = gen._current_source_hashes(real_entry, catalog_path=schema.CATALOG_PATH)

    alt_catalog_path = tmp_path / "PROCESS_CATALOG_alt.yaml"
    original_text = Path(schema.CATALOG_PATH).read_text(encoding="utf-8")
    marker = "  - name: Translation\n    oc_module: opencell/vivarium/karr_translation.py\n"
    assert original_text.count(marker) == 1
    edited_text = original_text.replace(marker, marker + "    closed_form_dominant: candidate\n", 1)
    assert edited_text != original_text
    alt_catalog_path.write_text(edited_text, encoding="utf-8")

    alt_entry = cat.in_scope_processes(alt_catalog_path)["Translation"]
    alt_hashes = gen._current_source_hashes(alt_entry, catalog_path=alt_catalog_path)
    assert real_hashes["catalog_entry"] != alt_hashes["catalog_entry"]

    # Genuinely `catalog_path`-driven, not `entry`-driven: passing the ALT
    # entry but the REAL (default) `catalog_path` re-resolves the REAL
    # file's Translation row again (only `entry.name` matters for the
    # lookup) -- proving `catalog_path` selects the source, not which
    # `ProcessEntry` object happens to be passed alongside it.
    mixed_hashes = gen._current_source_hashes(alt_entry, catalog_path=schema.CATALOG_PATH)
    assert mixed_hashes["catalog_entry"] == real_hashes["catalog_entry"]


def test_build_process_row_honors_alternate_catalog_path_for_staleness(tmp_path):
    """End-to-end: `build_process_row(entry, evidence_root, catalog_path=alt)`
    must gate staleness against `alt`'s resolved contract, not the real
    tracked catalog. A real, currently-PASS row (Metabolism) recomputed
    against an ALTERED copy of the catalog (a `closed_form_dominant` field
    added to its own row) must now report the row STALE: the real tracked
    `sweep_provenance.json`'s recorded `catalog_entry` was generated
    against the REAL (unaltered) catalog, so it no longer matches the
    `alt`-resolved current hash -- proving `catalog_path` was actually
    threaded through to the staleness check, not silently ignored."""
    real_entry = cat.in_scope_processes()["Metabolism"]
    real_row = gen.build_process_row(real_entry, schema.BUNDLE_ROOT, catalog_path=schema.CATALOG_PATH)
    assert real_row["green"] is True, real_row["reasons"]

    alt_catalog_path = tmp_path / "PROCESS_CATALOG_alt.yaml"
    original_text = Path(schema.CATALOG_PATH).read_text(encoding="utf-8")
    marker = (
        "  - name: Metabolism\n    oc_module: opencell/vivarium/karr_metabolism.py\n"
        "    bucket: TRIVIAL_RNG\n    in_scope_L2_2: true\n    M_ticks: 20\n    N_seeds: 50\n"
    )
    assert original_text.count(marker) == 1
    edited_text = original_text.replace(marker, marker + "    closed_form_dominant: candidate\n", 1)
    assert edited_text != original_text
    alt_catalog_path.write_text(edited_text, encoding="utf-8")

    alt_entry = cat.in_scope_processes(alt_catalog_path)["Metabolism"]
    alt_row = gen.build_process_row(alt_entry, schema.BUNDLE_ROOT, catalog_path=alt_catalog_path)

    assert alt_row["green"] is False
    assert any(
        "catalog_entry" in reason and schema.STATUS_STALE_PROVENANCE in reason for reason in alt_row["reasons"]
    ), alt_row["reasons"]
