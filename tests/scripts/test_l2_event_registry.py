"""Unit tests for `scripts/l2_event/registry.py` and
`docs/phase_f/l2_event/event_registry.yaml` (requirement 1: versioned
event registry, derived/validated against PROCESS_CATALOG.yaml, never
editing the catalog itself)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.registry import (
    REGISTRY_PATH,
    RegistryError,
    load_registry,
    registry_sha256,
    resolve_process_entry,
    validate_against_catalog,
)
from scripts.l2_event.schema import REGISTRY_SCHEMA_VERSION

_TARGET_PROCESSES = ("Cytokinesis", "RibosomeAssembly", "DNADamage", "FtsZPolymerization")


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
    """Ground-truth audit: only RibosomeAssembly and Cytokinesis have any
    adapter at all (both explicitly smoke-only, never gating_ready).
    Cytokinesis gained a Karr-only structural-smoke adapter (2026-08-05,
    Canary D closeout: real seed-0 anchor trace at n_ticks=4000) but this
    is NOT a full OC-vs-Karr gate -- the anchor snapshot lacks the full
    geometry/ftsZRing/chromosome objects a real comparison needs."""
    registry = load_registry()
    assert registry["RibosomeAssembly"].adapter_status == "structural_smoke_only"
    assert registry["RibosomeAssembly"].adapter_id == "ribosome_assembly.smoke.v1"
    assert registry["Cytokinesis"].adapter_status == "structural_smoke_only"
    assert registry["Cytokinesis"].adapter_id == "cytokinesis.karr_only_smoke.v1"
    for name in ("DNADamage", "FtsZPolymerization"):
        assert registry[name].adapter_status == "not_implemented"
        assert registry[name].adapter_id is None
    for entry in registry.values():
        assert entry.adapter_status != "gating_ready", (
            f"{entry.process}: no process may claim gating_ready in this foundation task."
        )


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
