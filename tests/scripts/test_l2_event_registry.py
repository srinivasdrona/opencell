"""Unit tests for `scripts/l2_event/registry.py` and
`docs/phase_f/l2_event/event_registry.yaml` (requirement 1: versioned
event registry, derived/validated against PROCESS_CATALOG.yaml, never
editing the catalog itself)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.evidence import MANDATORY_FILES, TRACKED_BUNDLE_ROOT
from scripts.l2_event.launcher import KARR_NATIVE_ROOT, event_window_mat_path
from scripts.l2_event.registry import (
    REGISTRY_PATH,
    RegistryError,
    load_registry,
    registry_sha256,
    resolve_process_entry,
    validate_against_catalog,
)
from scripts.l2_event.ribosome_assembly_seed_audit import (
    DEFAULT_SPECS_PATH,
    REQUIRED_N_SEEDS,
    audit_ribosome_assembly_n50_seeds,
)
from scripts.l2_event.schema import REGISTRY_SCHEMA_VERSION

_TARGET_PROCESSES = ("Cytokinesis", "RibosomeAssembly", "DNADamage", "FtsZPolymerization")


def _all_50_real_seeds_present() -> bool:
    """Existence-only pre-check for skipif -- mirrors the identical helper
    in ``test_l2_event_ribosome_assembly_n50.py``. The truthfulness-guard
    test below does the REAL validation; this only decides whether that
    real validation can run at all in this environment (e.g. skipped on a
    fresh clone where the gitignored 50-seed cohort was never extracted)."""
    if not DEFAULT_SPECS_PATH.exists():
        return False
    for seed in range(REQUIRED_N_SEEDS):
        path = event_window_mat_path("RibosomeAssembly", seed, n_ticks=100, karr_native_root=KARR_NATIVE_ROOT)
        if not path.exists():
            return False
    return True


_ALL_50_PRESENT = _all_50_real_seeds_present()
_missing_reason = "Full 50-seed RibosomeAssembly event-window cohort not present locally"


def test_registry_covers_exactly_the_four_target_processes():
    registry = load_registry()
    assert set(registry) == set(_TARGET_PROCESSES)


def test_registry_v4_scope_matches_spec_section_8():
    """Only Cytokinesis + RibosomeAssembly are in v4 scope; DNADamage and
    FtsZPolymerization are explicitly deferred (spec §8)."""
    registry = load_registry()
    assert registry["Cytokinesis"].in_scope_v4 is True
    assert registry["RibosomeAssembly"].in_scope_v4 is True
    assert registry["DNADamage"].in_scope_v4 is False
    assert registry["FtsZPolymerization"].in_scope_v4 is False
    assert registry["DNADamage"].deferred_reason
    assert registry["FtsZPolymerization"].deferred_reason


def test_registry_reflects_actual_adapter_availability_not_aspirational_claims():
    """Ground-truth audit of the two implemented adapters.

    RibosomeAssembly is gating-ready because its N=50 bundle is audited
    below. Cytokinesis has only a structural-smoke adapter and remains
    non-gating pending the full span survey and OC-vs-Karr evidence.
    DNADamage and FtsZPolymerization have no event adapters."""
    registry = load_registry()
    assert registry["RibosomeAssembly"].adapter_status == "gating_ready"
    assert registry["RibosomeAssembly"].adapter_id == "ribosome_assembly.gate.v1"
    assert registry["Cytokinesis"].adapter_status == "structural_smoke_only"
    assert registry["Cytokinesis"].adapter_id == "cytokinesis.pinched_diameter_completion.v1"
    for name in ("DNADamage", "FtsZPolymerization"):
        assert registry[name].adapter_status == "not_implemented"
        assert registry[name].adapter_id is None


def test_no_process_other_than_ribosome_assembly_claims_gating_ready():
    """Narrowed truthfulness guard: RibosomeAssembly's gating_ready claim
    is independently justified below (real N=50 bundle, audited clean).
    No OTHER process may claim gating_ready without equivalent backing
    evidence -- none currently has any adapter at all, so none may claim
    it. This replaces the earlier blanket 'no entry may ever claim
    gating_ready in this foundation task' assumption, which the real
    2026-08-05 RibosomeAssembly promotion correctly falsified."""
    registry = load_registry()
    for name, entry in registry.items():
        if name == "RibosomeAssembly":
            continue
        assert entry.adapter_status != "gating_ready", (
            f"{name}: no adapter/evidence exists to back a gating_ready claim."
        )


@pytest.mark.skipif(not _ALL_50_PRESENT, reason=_missing_reason)
def test_ribosome_assembly_gating_ready_claim_is_backed_by_a_complete_hash_bound_n50_bundle():
    """The actual truthfulness guard (Opus review, 2026-08-05): a
    ``gating_ready`` claim in the live registry must never be
    aspirational or stale. This independently re-derives, from the real
    on-disk seed cohort and the tracked evidence bundle -- NOT merely by
    re-reading the registry's own prose -- that RibosomeAssembly's claim
    is currently true:

    1. the seed audit (the same one `ribosome_assembly_n50_gate` itself
       refuses to compute without) reports all 50 seeds valid,
       hash-bound, and non-aliased;
    2. the tracked evidence bundle
       (``docs/phase_f/l2_event/evidence_bundle/RibosomeAssembly/``) has
       all 5 mandatory files, with a real PASS verdict computed in
       ``mode: gate`` (never ``structural_smoke``/``NOT_APPLICABLE``)
       over exactly 50 seeds on both sides;
    3. the bundle's own recorded input hashes are exactly the 50 real,
       distinct, currently-on-disk seed hashes the audit just
       independently confirmed -- catching the case where the bundle was
       promoted from a stale or different (e.g. partially aliased) seed
       set than what is on disk today.

    If a future change flips ``adapter_status`` back without also
    reverting/regenerating this evidence, or the bundle silently
    regresses (fewer seeds, hash drift, verdict overwritten), this test
    fails."""
    registry = load_registry()
    assert registry["RibosomeAssembly"].adapter_status == "gating_ready"

    audit_report = audit_ribosome_assembly_n50_seeds()
    assert audit_report["all_seeds_valid"] is True, audit_report
    assert audit_report["duplicated_hashes"] == {}, audit_report
    assert audit_report["n_seeds_valid"] == REQUIRED_N_SEEDS
    audit_hashes = {row["seed"]: row["sha256"] for row in audit_report["per_seed"]}
    assert len(audit_hashes) == REQUIRED_N_SEEDS
    assert all(h is not None for h in audit_hashes.values())

    bundle_dir = TRACKED_BUNDLE_ROOT / "RibosomeAssembly"
    on_disk = {p.name for p in bundle_dir.iterdir() if p.is_file()}
    assert set(MANDATORY_FILES) <= on_disk, f"missing mandatory evidence file(s): {set(MANDATORY_FILES) - on_disk}"

    result = json.loads((bundle_dir / "result.json").read_text(encoding="utf-8"))
    assert result["mode"] == "gate"
    assert result["verdict"] == "PASS"
    assert result["n_seeds_karr"] == REQUIRED_N_SEEDS
    assert result["n_seeds_oc"] == REQUIRED_N_SEEDS

    input_manifest = json.loads((bundle_dir / "input_manifest.json").read_text(encoding="utf-8"))
    manifest_entries = input_manifest["inputs"]
    assert len(manifest_entries) == REQUIRED_N_SEEDS
    manifest_hashes = {entry["seed"]: entry["sha256"] for entry in manifest_entries}
    assert set(manifest_hashes) == set(range(REQUIRED_N_SEEDS))
    assert len(set(manifest_hashes.values())) == REQUIRED_N_SEEDS, "bundle input_manifest hashes must be 50 DISTINCT values"

    # The bundle's recorded hashes must match the CURRENT on-disk seed
    # cohort the audit just re-validated -- not merely be internally
    # self-consistent -- so a bundle promoted from stale/aliased seeds
    # (and never regenerated after real seeds replaced them) cannot pass
    # silently.
    assert manifest_hashes == audit_hashes, (
        "evidence bundle input_manifest hashes disagree with the live, "
        "freshly-audited on-disk seed cohort -- the bundle is stale "
        "relative to the seeds now on disk."
    )
def test_registry_cytokinesis_adapter_id_resolves_to_the_real_adapter():
    """Opus review (2026-08-05, post-Canary-D): the registry must never
    invent a bespoke adapter_id string for a process that already has a
    real, registered adapter class -- it must name that adapter's own
    `adapter_id` class attribute exactly, so `adapter_id` always resolves
    to real, importable code (never a dangling label some future reader
    could mistake for a distinct adapter that doesn't exist)."""
    from scripts.l2_event.adapters.cytokinesis import CytokinesisEventAdapter

    registry = load_registry()
    assert registry["Cytokinesis"].adapter_id == CytokinesisEventAdapter.adapter_id
    assert registry["Cytokinesis"].adapter_id == CytokinesisEventAdapter().adapter_id


def test_registry_ribosome_assembly_adapter_id_resolves_to_the_real_adapter():
    """Same binding check as the Cytokinesis test above, applied to the
    other real adapter this registry names -- both rows must resolve to
    real code, not just Cytokinesis."""
    from scripts.l2_event.adapters.ribosome_assembly_gate import RibosomeAssemblyGateAdapter

    registry = load_registry()
    assert registry["RibosomeAssembly"].adapter_id == RibosomeAssemblyGateAdapter.adapter_id


def test_validate_against_catalog_is_clean_for_the_shipped_registry():
    registry = load_registry()
    problems = validate_against_catalog(registry)
    assert problems == [], f"registry/catalog cross-check found unexpected problems: {problems}"


def test_validate_against_catalog_flags_harness_type_mismatch(tmp_path):
    registry = load_registry()
    # Corrupt one entry's implied catalog cross-check by asserting against a
    # process name that the real catalog does not carry as event_class.
    # M5 (Opus5 review): the harness_type=="event_class" check is only
    # enforced for `in_scope_v4: true` rows (so an out-of-scope catalog
    # reclassification -- e.g. FtsZ -- can never brick unrelated in-scope
    # rows). This synthetic row must therefore set `in_scope_v4=True` to
    # still exercise the check.
    bad_registry = dict(registry)
    from scripts.l2_event.registry import EventRegistryEntry

    bad_registry["Translation"] = EventRegistryEntry(
        process="Translation",
        in_scope_v4=True,
        adapter_id=None,
        adapter_status="not_implemented",
        event_timing_model=None,
        magnitude_gateable=False,
        required_n_seeds=50,
        deferred_reason=None,
    )
    problems = validate_against_catalog(bad_registry)
    assert any("Translation" in p for p in problems)


def test_validate_against_catalog_does_not_enforce_harness_type_for_out_of_scope_rows():
    """M5: an `in_scope_v4=False` row whose catalog harness_type is NOT
    'event_class' must never itself be flagged -- the check is scoped to
    in-scope rows only."""
    registry = load_registry()
    bad_registry = dict(registry)
    from scripts.l2_event.registry import EventRegistryEntry

    bad_registry["Translation"] = EventRegistryEntry(
        process="Translation",
        in_scope_v4=False,
        adapter_id=None,
        adapter_status="not_implemented",
        event_timing_model=None,
        magnitude_gateable=False,
        required_n_seeds=50,
        deferred_reason="synthetic test row, deliberately out of v4 scope",
    )
    problems = validate_against_catalog(bad_registry)
    assert not any("Translation" in p for p in problems)


def test_validate_against_catalog_ftsz_reclassification_does_not_brick_ribosome_assembly():
    """M5 (Opus5 review): reclassifying FtsZPolymerization (e.g. flipping
    its catalog harness_type away from 'event_class', simulating a future
    pending decision to remove it from the event profile) must never
    cause validate_against_catalog() to refuse/flag unrelated in-scope
    rows such as RibosomeAssembly -- this is the exact 'bricking' failure
    mode M5 was raised to fix."""
    registry = load_registry()
    from scripts.l2_event.registry import EventRegistryEntry

    reclassified = dict(registry)
    # FtsZ stays out of v4 scope (in_scope_v4=False) regardless of the
    # catalog-side reclassification -- the harness_type check simply does
    # not apply to it.
    reclassified["FtsZPolymerization"] = EventRegistryEntry(
        process="FtsZPolymerization",
        in_scope_v4=False,
        adapter_id=None,
        adapter_status="not_implemented",
        event_timing_model=None,
        magnitude_gateable=False,
        required_n_seeds=50,
        deferred_reason="pending reclassification decision (M5): may leave the event profile entirely",
    )
    problems = validate_against_catalog(reclassified)
    assert not any("RibosomeAssembly" in p for p in problems)


def test_validate_against_catalog_flags_unknown_process(tmp_path):
    from scripts.l2_event.registry import EventRegistryEntry

    fake_registry = {
        "NotARealProcess": EventRegistryEntry(
            process="NotARealProcess",
            in_scope_v4=False,
            adapter_id=None,
            adapter_status="not_implemented",
            event_timing_model=None,
            magnitude_gateable=False,
            required_n_seeds=50,
            deferred_reason=None,
        )
    }
    problems = validate_against_catalog(fake_registry)
    assert any("NotARealProcess" in p and "not found" in p for p in problems)


def test_load_registry_rejects_wrong_schema_version(tmp_path):
    bad_path = tmp_path / "bad_registry.yaml"
    bad_path.write_text(yaml.safe_dump({"schema_version": 999, "processes": []}), encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(bad_path)


def test_load_registry_rejects_unknown_event_timing_model(tmp_path):
    bad_path = tmp_path / "bad_timing.yaml"
    bad_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": REGISTRY_SCHEMA_VERSION,
                "processes": [{"process": "Foo", "event_timing_model": "not_a_real_model"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RegistryError):
        load_registry(bad_path)


def test_load_registry_rejects_empty_processes_list(tmp_path):
    empty_path = tmp_path / "empty.yaml"
    empty_path.write_text(yaml.safe_dump({"schema_version": REGISTRY_SCHEMA_VERSION, "processes": []}), encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(empty_path)


def test_resolve_process_entry_raises_for_unknown_process():
    with pytest.raises(RegistryError):
        resolve_process_entry("TotallyMadeUpProcess")


def test_resolve_process_entry_returns_correct_entry():
    entry = resolve_process_entry("RibosomeAssembly")
    assert entry.process == "RibosomeAssembly"


def test_registry_sha256_is_stable_and_changes_on_content_edit(tmp_path):
    original = REGISTRY_PATH.read_bytes()
    copy_path = tmp_path / "copy.yaml"
    copy_path.write_bytes(original)
    assert registry_sha256(copy_path) == registry_sha256(REGISTRY_PATH)

    mutated_path = tmp_path / "mutated.yaml"
    mutated_path.write_bytes(original + b"\n# a harmless trailing comment\n")
    assert registry_sha256(mutated_path) != registry_sha256(REGISTRY_PATH)


def test_registry_sha256_is_stable_across_crlf_vs_lf_line_endings(tmp_path):
    """Opus5 review round 3, item #4: 'registry hash computed LF/git-blob-
    normalized consistently fresh clone'. A CRLF checkout (the Windows git
    default absent `core.autocrlf`/`.gitattributes` forcing LF) must hash
    IDENTICALLY to an LF checkout of the byte-for-byte same content --
    otherwise a `registry_sha256` recorded on one machine/clone would
    never reproduce on another, breaking the provenance binding this hash
    exists for."""
    original_text = REGISTRY_PATH.read_text(encoding="utf-8")
    # Normalize to a known baseline first (the real file may already be
    # either style depending on this machine's git config), then write out
    # two deliberately different-line-ending copies of the SAME content.
    lf_text = original_text.replace("\r\n", "\n").replace("\r", "\n")
    crlf_text = lf_text.replace("\n", "\r\n")

    lf_path = tmp_path / "lf.yaml"
    crlf_path = tmp_path / "crlf.yaml"
    lf_path.write_bytes(lf_text.encode("utf-8"))
    crlf_path.write_bytes(crlf_text.encode("utf-8"))

    assert lf_path.read_bytes() != crlf_path.read_bytes(), "precondition: the two files must differ byte-for-byte"
    assert registry_sha256(lf_path) == registry_sha256(crlf_path)
