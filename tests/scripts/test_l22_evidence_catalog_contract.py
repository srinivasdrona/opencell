"""Tests for the R6 catalog-provenance fix: per-process resolved-contract
hashes (`schema.resolve_catalog_process_contract`/
`resolve_event_registry_process_contract`/`catalog_entry_hash`/
`event_registry_entry_hash`/`process_contract_hashes`) that replace the old
whole-file `"catalog"`/`"l2_event_registry"` shared source-hash keys.

Context: the accepted Cytokinesis-only `M_ticks: 4000 -> 5000` catalog edit
made every one of the other 21 in-scope processes' `sweep_provenance.json`
look stale, because `source_hashes["catalog"]` hashed the ENTIRE
`PROCESS_CATALOG.yaml` file. These tests prove the fix is genuinely
per-process (an edit to ONE process's row never stales another's), still
catches every REAL change that can affect a process's evidence/verdict/
scope (its own row, the bucket/universal default it falls back to), is
immune to non-semantic edits (YAML key-order/formatting/comments), and
fails closed for an unknown/missing process -- using synthetic, throwaway
temp-file catalogs/registries throughout (never mutating the real tracked
`PROCESS_CATALOG.yaml`/`event_registry.yaml`).

Run via `bin\\oc-pytest tests/scripts/test_l22_evidence_catalog_contract.py -v`.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402

# --- Synthetic catalog fixture (never the real tracked PROCESS_CATALOG.yaml) ---

_BASE_CATALOG_YAML = """
universals:
  N_seeds: 50
  min_events_for_distribution: 30
buckets:
  ALGORITHMIC_DEEP:
    in_scope_L2_2: true
    harness_type: design_a_per_tick
  EVENT_CLASS:
    in_scope_L2_2: true
    harness_type: event_class
processes:
  - name: Translation
    oc_module: opencell/vivarium/karr_translation.py
    bucket: ALGORITHMIC_DEEP
    in_scope_L2_2: true
    M_ticks: 100
    N_seeds: 50
    primary_channel: monomers
    output_channels: [substrates, monomers]
    input_channels: [substrates, enzymes]
    notes: "v1 notes"
    rationale_M: "free samples already extracted"
  - name: MacromolecularComplexation
    oc_module: opencell/vivarium/karr_macromolecular_complexation.py
    bucket: ALGORITHMIC_DEEP
    in_scope_L2_2: true
    M_ticks: 100
    N_seeds: 50
    primary_channel: complexs
    output_channels: [substrates, monomers, complexs]
    input_channels: [substrates, monomers]
    closed_form_dominant: candidate
    notes: "v1 notes"
  - name: Cytokinesis
    oc_module: opencell/vivarium/karr_cytokinesis.py
    bucket: EVENT_CLASS
    harness_type: event_class
    in_scope_L2_2: true
    M_ticks: 4000
    N_seeds: 50
    primary_channel: substrates
    event_channels: [chromosome]
    output_channels: [substrates, chromosome]
    input_channels: [substrates, enzymes, chromosome]
    notes: "v1 notes"
  - name: NoSeedsOverride
    oc_module: ""
    bucket: ALGORITHMIC_DEEP
    in_scope_L2_2: true
    M_ticks: 50
    primary_channel: substrates
    output_channels: [substrates]
"""

_BASE_REGISTRY_YAML = """
schema_version: 1
processes:
  - process: Cytokinesis
    in_scope_v4: true
    adapter_id: cytokinesis.pinched_diameter_completion.v1
    adapter_status: structural_smoke_only
    event_timing_model: single_firing
    magnitude_gateable: false
    required_n_seeds: 50
    notes: "registry v1 notes"
  - process: RibosomeAssembly
    in_scope_v4: true
    adapter_id: ribosome_assembly.gate.v1
    adapter_status: gating_ready
    event_timing_model: repeated_firing
    magnitude_gateable: true
    required_n_seeds: 50
    notes: "registry v1 notes"
"""


def _write_catalog(tmp_path: Path, yaml_text: str, *, name: str = "PROCESS_CATALOG.yaml") -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(yaml_text), encoding="utf-8")
    return path


def _write_registry(tmp_path: Path, yaml_text: str, *, name: str = "event_registry.yaml") -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(yaml_text), encoding="utf-8")
    return path


# --- Cross-process isolation: editing ONE process never stales another --------


def test_editing_cytokinesis_m_ticks_does_not_change_translation_or_macromol_hash(tmp_path):
    """The exact regression this fix targets: a Cytokinesis-only M_ticks
    edit must leave every OTHER process's `catalog_entry_hash` unchanged."""
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    translation_before = schema.catalog_entry_hash("Translation", path_before)
    macromol_before = schema.catalog_entry_hash("MacromolecularComplexation", path_before)
    cytokinesis_before = schema.catalog_entry_hash("Cytokinesis", path_before)

    edited = _BASE_CATALOG_YAML.replace("M_ticks: 4000", "M_ticks: 5000")
    assert edited != _BASE_CATALOG_YAML
    path_after = _write_catalog(tmp_path, edited, name="PROCESS_CATALOG_v2.yaml")

    translation_after = schema.catalog_entry_hash("Translation", path_after)
    macromol_after = schema.catalog_entry_hash("MacromolecularComplexation", path_after)
    cytokinesis_after = schema.catalog_entry_hash("Cytokinesis", path_after)

    assert translation_after == translation_before
    assert macromol_after == macromol_before
    assert cytokinesis_after != cytokinesis_before


@pytest.mark.parametrize(
    "field_edit",
    [
        ("M_ticks: 100\n    N_seeds: 50\n    primary_channel: monomers", "M_ticks: 200\n    N_seeds: 50\n    primary_channel: monomers"),
        ("primary_channel: monomers", "primary_channel: substrates"),
        ("N_seeds: 50\n    primary_channel: monomers", "N_seeds: 25\n    primary_channel: monomers"),
    ],
)
def test_editing_translations_own_row_stales_only_translation(tmp_path, field_edit):
    """Changing Translation's own M/N/primary_channel must stale ONLY
    Translation's contract hash -- Macromol/Cytokinesis (and every other
    process) must be untouched."""
    old_fragment, new_fragment = field_edit
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    before = {
        name: schema.catalog_entry_hash(name, path_before)
        for name in ("Translation", "MacromolecularComplexation", "Cytokinesis")
    }

    edited = _BASE_CATALOG_YAML.replace(old_fragment, new_fragment, 1)
    assert edited != _BASE_CATALOG_YAML
    path_after = _write_catalog(tmp_path, edited, name="PROCESS_CATALOG_v2.yaml")
    after = {
        name: schema.catalog_entry_hash(name, path_after)
        for name in ("Translation", "MacromolecularComplexation", "Cytokinesis")
    }

    assert after["Translation"] != before["Translation"]
    assert after["MacromolecularComplexation"] == before["MacromolecularComplexation"]
    assert after["Cytokinesis"] == before["Cytokinesis"]


def test_harness_type_change_stales_only_that_process(tmp_path):
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    before = schema.catalog_entry_hash("Translation", path_before)
    other_before = schema.catalog_entry_hash("MacromolecularComplexation", path_before)

    edited = _BASE_CATALOG_YAML.replace(
        "  - name: Translation\n    oc_module: opencell/vivarium/karr_translation.py\n    bucket: ALGORITHMIC_DEEP\n"
        "    in_scope_L2_2: true\n    M_ticks: 100",
        "  - name: Translation\n    oc_module: opencell/vivarium/karr_translation.py\n    bucket: ALGORITHMIC_DEEP\n"
        "    harness_type: event_class\n    in_scope_L2_2: true\n    M_ticks: 100",
    )
    assert edited != _BASE_CATALOG_YAML
    path_after = _write_catalog(tmp_path, edited, name="PROCESS_CATALOG_v2.yaml")
    after = schema.catalog_entry_hash("Translation", path_after)
    other_after = schema.catalog_entry_hash("MacromolecularComplexation", path_after)

    assert after != before
    assert other_after == other_before


# --- Universal/bucket-default resolution: a process relying on a default ------


def test_universal_n_seeds_default_change_stales_process_relying_on_it(tmp_path):
    """`NoSeedsOverride` declares no `N_seeds` of its own, so it inherits
    `universals.N_seeds` -- changing that universal must stale ITS
    contract hash even though its own row's bytes never changed, but must
    NOT stale Translation (which declares its own explicit N_seeds: 50)."""
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    before_default = schema.catalog_entry_hash("NoSeedsOverride", path_before)
    before_explicit = schema.catalog_entry_hash("Translation", path_before)

    edited = _BASE_CATALOG_YAML.replace("N_seeds: 50\n  min_events_for_distribution", "N_seeds: 25\n  min_events_for_distribution")
    assert edited != _BASE_CATALOG_YAML
    path_after = _write_catalog(tmp_path, edited, name="PROCESS_CATALOG_v2.yaml")
    after_default = schema.catalog_entry_hash("NoSeedsOverride", path_after)
    after_explicit = schema.catalog_entry_hash("Translation", path_after)

    assert after_default != before_default
    assert after_explicit == before_explicit


def test_bucket_harness_type_default_change_stales_process_relying_on_it(tmp_path):
    """`NoSeedsOverride` declares no `harness_type` of its own, so it
    inherits `buckets.ALGORITHMIC_DEEP.harness_type` -- changing that
    bucket default must stale its contract hash, but must NOT stale
    Cytokinesis (EVENT_CLASS bucket, unaffected)."""
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    before_deep = schema.catalog_entry_hash("NoSeedsOverride", path_before)
    before_event = schema.catalog_entry_hash("Cytokinesis", path_before)

    edited = _BASE_CATALOG_YAML.replace(
        "  ALGORITHMIC_DEEP:\n    in_scope_L2_2: true\n    harness_type: design_a_per_tick",
        "  ALGORITHMIC_DEEP:\n    in_scope_L2_2: true\n    harness_type: event_class",
    )
    assert edited != _BASE_CATALOG_YAML
    path_after = _write_catalog(tmp_path, edited, name="PROCESS_CATALOG_v2.yaml")
    after_deep = schema.catalog_entry_hash("NoSeedsOverride", path_after)
    after_event = schema.catalog_entry_hash("Cytokinesis", path_after)

    assert after_deep != before_deep
    assert after_event == before_event


# --- Comments/formatting/key-order invariance ----------------------------------


def test_comment_only_edit_does_not_change_any_hash(tmp_path):
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    before = {
        name: schema.catalog_entry_hash(name, path_before)
        for name in ("Translation", "MacromolecularComplexation", "Cytokinesis", "NoSeedsOverride")
    }

    commented = "# a brand new top-of-file comment explaining nothing\n" + _BASE_CATALOG_YAML.replace(
        "  - name: Translation", "  # inline comment before Translation's row\n  - name: Translation"
    )
    path_after = _write_catalog(tmp_path, commented, name="PROCESS_CATALOG_v2.yaml")
    after = {
        name: schema.catalog_entry_hash(name, path_after)
        for name in ("Translation", "MacromolecularComplexation", "Cytokinesis", "NoSeedsOverride")
    }
    assert after == before


def test_yaml_formatting_and_key_order_do_not_change_any_hash(tmp_path):
    """Re-serializing the SAME parsed catalog with completely different key
    order/flow style/whitespace must produce IDENTICAL contract hashes --
    canonicalization is over the RESOLVED VALUES, not the YAML bytes."""
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    parsed = yaml.safe_load(Path(path_before).read_text(encoding="utf-8"))
    before = {
        name: schema.catalog_entry_hash(name, path_before)
        for name in ("Translation", "MacromolecularComplexation", "Cytokinesis", "NoSeedsOverride")
    }

    reformatted_text = yaml.safe_dump(parsed, default_flow_style=True, sort_keys=False)
    path_after = tmp_path / "PROCESS_CATALOG_reformatted.yaml"
    path_after.write_text(reformatted_text, encoding="utf-8")
    after = {name: schema.catalog_entry_hash(name, path_after) for name in before}

    assert after == before


# --- Fail-closed: unknown/missing/duplicated process ---------------------------


def test_unknown_process_raises(tmp_path):
    path = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    with pytest.raises(ValueError, match="not found"):
        schema.catalog_entry_hash("TotallyUnknownProcess", path)


def test_duplicate_process_row_raises(tmp_path):
    """Append a second, differently-valued `Translation` row (extracted by
    slicing the ORIGINAL row's exact text out of the fixture, so
    indentation always matches the file's own style) -- two rows sharing
    one `name` must fail closed, never resolve to the first/last match."""
    start = _BASE_CATALOG_YAML.index("  - name: Translation")
    end = _BASE_CATALOG_YAML.index("  - name: MacromolecularComplexation")
    translation_block = _BASE_CATALOG_YAML[start:end]
    duplicated = _BASE_CATALOG_YAML + "\n" + translation_block.replace("M_ticks: 100", "M_ticks: 999")
    path = _write_catalog(tmp_path, duplicated, name="PROCESS_CATALOG_dup.yaml")
    with pytest.raises(ValueError, match="duplicate"):
        schema.catalog_entry_hash("Translation", path)


def test_process_contract_hashes_falls_through_to_empty_dict_for_falsy_process():
    assert schema.process_contract_hashes(None, "design_a_per_tick") == {}
    assert schema.process_contract_hashes("", "event_class") == {}


def test_process_contract_hashes_includes_event_registry_only_for_event_class(tmp_path, monkeypatch):
    catalog_path = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    registry_path = _write_registry(tmp_path, _BASE_REGISTRY_YAML)
    monkeypatch.setattr(schema, "CATALOG_PATH", catalog_path)
    monkeypatch.setattr(schema, "L2_EVENT_REGISTRY_PATH", registry_path)

    design_a_hashes = schema.process_contract_hashes("Translation", "design_a_per_tick")
    assert set(design_a_hashes) == {"catalog_entry"}

    event_hashes = schema.process_contract_hashes("Cytokinesis", "event_class")
    assert set(event_hashes) == {"catalog_entry", "event_registry_entry"}


# --- event_registry_entry: identical isolation/fail-closed properties ----------


def test_editing_cytokinesis_registry_row_does_not_stale_ribosome_assembly(tmp_path):
    path_before = _write_registry(tmp_path, _BASE_REGISTRY_YAML)
    ra_before = schema.event_registry_entry_hash("RibosomeAssembly", path_before)
    cyt_before = schema.event_registry_entry_hash("Cytokinesis", path_before)

    edited_gating = _BASE_REGISTRY_YAML.replace("adapter_status: structural_smoke_only", "adapter_status: gating_ready")
    assert edited_gating != _BASE_REGISTRY_YAML
    path_gating = _write_registry(tmp_path, edited_gating, name="event_registry_v2.yaml")
    ra_gating = schema.event_registry_entry_hash("RibosomeAssembly", path_gating)
    cyt_gating = schema.event_registry_entry_hash("Cytokinesis", path_gating)

    assert cyt_gating != cyt_before
    assert ra_gating == ra_before


def test_event_registry_notes_field_excluded_from_contract(tmp_path):
    """`notes` is never read by `scripts/l2_event/runner.py`'s gating
    logic -- excluded from the resolved contract, so a documentation-only
    edit never stales this (or any other) process's evidence."""
    path_before = _write_registry(tmp_path, _BASE_REGISTRY_YAML)
    before = schema.event_registry_entry_hash("Cytokinesis", path_before)
    edited = _BASE_REGISTRY_YAML.replace(
        'notes: "registry v1 notes"\n  - process: RibosomeAssembly',
        'notes: "a totally different, much longer provenance note"\n  - process: RibosomeAssembly',
    )
    assert edited != _BASE_REGISTRY_YAML
    path_after = _write_registry(tmp_path, edited, name="event_registry_v2.yaml")
    after = schema.event_registry_entry_hash("Cytokinesis", path_after)
    assert after == before


def test_unknown_process_in_registry_raises(tmp_path):
    path = _write_registry(tmp_path, _BASE_REGISTRY_YAML)
    with pytest.raises(ValueError, match="not found"):
        schema.event_registry_entry_hash("TotallyUnknownProcess", path)


# --- Real-catalog sanity: the actual PROCESS_CATALOG.yaml/event_registry.yaml --


def test_real_catalog_resolves_every_in_scope_process_without_raising():
    entries = cat.in_scope_processes()
    for name, entry in entries.items():
        digest = schema.catalog_entry_hash(name)
        assert isinstance(digest, str) and len(digest) == 64
        if entry.harness_type == "event_class":
            digest2 = schema.event_registry_entry_hash(name)
            assert isinstance(digest2, str) and len(digest2) == 64


def test_real_catalog_entry_hash_is_deterministic_across_repeated_calls():
    first = schema.catalog_entry_hash("Translation")
    second = schema.catalog_entry_hash("Translation")
    assert first == second
