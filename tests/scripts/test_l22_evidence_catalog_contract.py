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
from scripts.l22_evidence import generator as gen  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402
from tests.scripts._l22_evidence_fixtures import write_full_valid_evidence  # noqa: E402

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
    joint_check: true                     # cross-complex Spearman correlation (non-gating)
    notes: "v1 notes"
  - name: Replication
    oc_module: opencell/vivarium/karr_replication.py
    bucket: ALGORITHMIC_DEEP
    in_scope_L2_2: true
    M_ticks: 300
    N_seeds: 50
    primary_channel: chromosome
    primary_distance: per_component_scaled
    primary_projection: [polymerizedRegions.delta_value_sum_strand_1, polymerizedRegions.delta_value_sum_strand_2, polymerizedRegions.delta_nnz]
    output_channels: [substrates, chromosome]
    input_channels: [substrates, enzymes]
    notes: "v1 notes"
  - name: DNARepair
    oc_module: opencell/vivarium/karr_dna_repair.py
    bucket: ALGORITHMIC_DEEP
    in_scope_L2_2: true
    M_ticks: 150
    N_seeds: 50
    primary_channel: chromosome
    primary_distance: per_component_scaled
    primary_projection: [repair_event_present, damagedBases.delta_nnz, strandBreaks.delta_nnz]
    output_channels: [substrates, chromosome]
    input_channels: [substrates, enzymes, chromosome]
    notes: "v1 notes"
  - name: DNADamage
    oc_module: opencell/vivarium/karr_dna_damage.py
    bucket: EVENT_CLASS
    harness_type: event_class
    in_scope_L2_2: true
    M_ticks: 20
    N_seeds: 50
    primary_channel: chromosome
    primary_distance: hurdle_event_rate_plus_conditional_scaled_distance
    primary_projection: [damage_event_present, damagedBases.delta_nnz, abasicSites.delta_nnz]
    output_channels: [substrates, chromosome]
    input_channels: [substrates, chromosome]
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
    seed_window:
      tick_range_from_division: [-4999, 0]
      rationale: "division-anchored window"
  - name: FtsZPolymerization
    oc_module: opencell/vivarium/karr_ftsz_polymerization.py
    bucket: EVENT_CLASS
    harness_type: event_class
    in_scope_L2_2: true
    M_ticks: 200
    N_seeds: 50
    primary_channel: monomers
    output_channels: [substrates, monomers]
    input_channels: [substrates, enzymes, monomers]
    notes: "v1 notes"
    seed_window:
      tick_range_from_division: [-200, 0]
      rationale: "pre-division window only"
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


# --- R6 correction (2026-09-05, Opus re-review): primary_projection/joint_check/
# --- seed_window.tick_range_from_division -- omitted by the first cut of this fix ---


def test_primary_projection_edit_stales_only_that_process(tmp_path):
    """DNARepair's own `primary_projection` changing (a new channel
    appended) must stale ONLY DNARepair -- Replication/DNADamage/
    Translation (which never declare/read this field, or declare a
    different one) must be untouched."""
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    before = {
        name: schema.catalog_entry_hash(name, path_before)
        for name in ("DNARepair", "Replication", "DNADamage", "Translation")
    }

    edited = _BASE_CATALOG_YAML.replace(
        "primary_projection: [repair_event_present, damagedBases.delta_nnz, strandBreaks.delta_nnz]",
        "primary_projection: [repair_event_present, damagedBases.delta_nnz, strandBreaks.delta_nnz, gapSites.delta_nnz]",
    )
    assert edited != _BASE_CATALOG_YAML
    path_after = _write_catalog(tmp_path, edited, name="PROCESS_CATALOG_v2.yaml")
    after = {name: schema.catalog_entry_hash(name, path_after) for name in before}

    assert after["DNARepair"] != before["DNARepair"]
    assert after["Replication"] == before["Replication"]
    assert after["DNADamage"] == before["DNADamage"]
    assert after["Translation"] == before["Translation"]


def test_primary_projection_order_matters(tmp_path):
    """Reordering (never adding/removing) Replication's `primary_projection`
    components must still change the hash -- which dotted-path channel
    occupies which projection-vector slot is real content, never
    incidental formatting, so list order is deliberately preserved (never
    sorted) by `resolve_catalog_process_contract`."""
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    before = schema.catalog_entry_hash("Replication", path_before)
    other_before = schema.catalog_entry_hash("DNARepair", path_before)

    original = (
        "primary_projection: [polymerizedRegions.delta_value_sum_strand_1, "
        "polymerizedRegions.delta_value_sum_strand_2, polymerizedRegions.delta_nnz]"
    )
    reordered = (
        "primary_projection: [polymerizedRegions.delta_value_sum_strand_2, "
        "polymerizedRegions.delta_value_sum_strand_1, polymerizedRegions.delta_nnz]"
    )
    assert original in _BASE_CATALOG_YAML
    edited = _BASE_CATALOG_YAML.replace(original, reordered)
    assert edited != _BASE_CATALOG_YAML
    path_after = _write_catalog(tmp_path, edited, name="PROCESS_CATALOG_v2.yaml")
    after = schema.catalog_entry_hash("Replication", path_after)
    other_after = schema.catalog_entry_hash("DNARepair", path_after)

    assert after != before  # same 3 components, same length -- ONLY order changed
    assert other_after == other_before


def test_primary_projection_omitted_resolves_same_as_explicit_empty_list(tmp_path):
    """Translation declares no `primary_projection` at all -- adding an
    explicit `primary_projection: []` to its row must resolve to the
    IDENTICAL contract hash (both resolve to `[]`), proving the omitted
    and explicit-empty forms are consistent, never merely coincidentally
    equal-looking."""
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    before = schema.catalog_entry_hash("Translation", path_before)

    anchor = (
        '    input_channels: [substrates, enzymes]\n    notes: "v1 notes"\n'
        '    rationale_M: "free samples already extracted"'
    )
    assert anchor in _BASE_CATALOG_YAML
    edited = _BASE_CATALOG_YAML.replace(
        anchor,
        '    input_channels: [substrates, enzymes]\n    primary_projection: []\n    notes: "v1 notes"\n'
        '    rationale_M: "free samples already extracted"',
    )
    assert edited != _BASE_CATALOG_YAML
    path_after = _write_catalog(tmp_path, edited, name="PROCESS_CATALOG_v2.yaml")
    after = schema.catalog_entry_hash("Translation", path_after)

    assert after == before


def test_joint_check_edit_stales_only_that_process(tmp_path):
    """MacromolecularComplexation's own `joint_check` flipping must stale
    ONLY its contract hash -- Translation (which never declares this
    field) must be untouched."""
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    before_macromol = schema.catalog_entry_hash("MacromolecularComplexation", path_before)
    before_translation = schema.catalog_entry_hash("Translation", path_before)

    edited = _BASE_CATALOG_YAML.replace("joint_check: true", "joint_check: false")
    assert edited != _BASE_CATALOG_YAML
    path_after = _write_catalog(tmp_path, edited, name="PROCESS_CATALOG_v2.yaml")
    after_macromol = schema.catalog_entry_hash("MacromolecularComplexation", path_after)
    after_translation = schema.catalog_entry_hash("Translation", path_after)

    assert after_macromol != before_macromol
    assert after_translation == before_translation


def test_joint_check_omitted_defaults_to_false_consistently(tmp_path):
    """Translation omits `joint_check` entirely -- adding an explicit
    `joint_check: false` line must resolve to the IDENTICAL contract hash
    (both resolve to `False`), matching the runner's own
    `entry.get("joint_check", False)` fallback exactly."""
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    before = schema.catalog_entry_hash("Translation", path_before)

    anchor = (
        '    input_channels: [substrates, enzymes]\n    notes: "v1 notes"\n'
        '    rationale_M: "free samples already extracted"'
    )
    assert anchor in _BASE_CATALOG_YAML
    edited = _BASE_CATALOG_YAML.replace(
        anchor,
        '    input_channels: [substrates, enzymes]\n    joint_check: false\n    notes: "v1 notes"\n'
        '    rationale_M: "free samples already extracted"',
    )
    assert edited != _BASE_CATALOG_YAML
    path_after = _write_catalog(tmp_path, edited, name="PROCESS_CATALOG_v2.yaml")
    after = schema.catalog_entry_hash("Translation", path_after)

    assert after == before


def test_seed_window_tick_range_edit_stales_only_that_process(tmp_path):
    """Cytokinesis's own `seed_window.tick_range_from_division` changing
    (the EXACT real-world regression: `[-3999, 0] -> [-4999, 0]`) must
    stale ONLY Cytokinesis -- FtsZPolymerization (the other
    division-anchored EVENT_CLASS process, with its own distinct window)
    must be untouched."""
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    before_cyt = schema.catalog_entry_hash("Cytokinesis", path_before)
    before_ftsz = schema.catalog_entry_hash("FtsZPolymerization", path_before)

    edited = _BASE_CATALOG_YAML.replace(
        "tick_range_from_division: [-4999, 0]", "tick_range_from_division: [-3999, 0]"
    )
    assert edited != _BASE_CATALOG_YAML
    path_after = _write_catalog(tmp_path, edited, name="PROCESS_CATALOG_v2.yaml")
    after_cyt = schema.catalog_entry_hash("Cytokinesis", path_after)
    after_ftsz = schema.catalog_entry_hash("FtsZPolymerization", path_after)

    assert after_cyt != before_cyt
    assert after_ftsz == before_ftsz


def test_seed_window_rationale_edit_does_not_change_hash(tmp_path):
    """`seed_window.rationale` is free text -- deliberately excluded from
    the resolved contract, same as `notes`/`rationale_M`. A documentation-
    only rewrite of Cytokinesis's rationale must never stale its evidence."""
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    before = schema.catalog_entry_hash("Cytokinesis", path_before)

    edited = _BASE_CATALOG_YAML.replace(
        'rationale: "division-anchored window"',
        'rationale: "a completely different, much longer, retconned rationale text"',
    )
    assert edited != _BASE_CATALOG_YAML
    path_after = _write_catalog(tmp_path, edited, name="PROCESS_CATALOG_v2.yaml")
    after = schema.catalog_entry_hash("Cytokinesis", path_after)

    assert after == before


def test_seed_window_omitted_resolves_to_none(tmp_path):
    """A process with no `seed_window` at all (every process except the
    two division-anchored EVENT_CLASS rows) resolves the contract's
    `seed_window` field to `None` -- never a guessed/fabricated window."""
    path = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    catalog = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    contract = schema.resolve_catalog_process_contract("Translation", catalog)
    assert contract["seed_window"] is None


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
        for name in (
            "Translation", "MacromolecularComplexation", "Replication", "DNARepair", "DNADamage",
            "Cytokinesis", "FtsZPolymerization", "NoSeedsOverride",
        )
    }

    commented = "# a brand new top-of-file comment explaining nothing\n" + _BASE_CATALOG_YAML.replace(
        "  - name: Translation", "  # inline comment before Translation's row\n  - name: Translation"
    )
    path_after = _write_catalog(tmp_path, commented, name="PROCESS_CATALOG_v2.yaml")
    after = {name: schema.catalog_entry_hash(name, path_after) for name in before}
    assert after == before


def test_yaml_formatting_and_key_order_do_not_change_any_hash(tmp_path):
    """Re-serializing the SAME parsed catalog with completely different key
    order/flow style/whitespace must produce IDENTICAL contract hashes --
    canonicalization is over the RESOLVED VALUES, not the YAML bytes. This
    also covers `primary_projection` (an ORDERED list, but reformatting a
    YAML flow-style list never changes its element order), `joint_check`,
    and `seed_window.tick_range_from_division`."""
    path_before = _write_catalog(tmp_path, _BASE_CATALOG_YAML)
    parsed = yaml.safe_load(Path(path_before).read_text(encoding="utf-8"))
    before = {
        name: schema.catalog_entry_hash(name, path_before)
        for name in (
            "Translation", "MacromolecularComplexation", "Replication", "DNARepair", "DNADamage",
            "Cytokinesis", "FtsZPolymerization", "NoSeedsOverride",
        )
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


def test_real_catalog_replication_dnarepair_dnadamage_have_ordered_primary_projection():
    """Sanity check against the REAL (non-synthetic) tracked
    PROCESS_CATALOG.yaml: the three chromosome-primary processes this R6
    correction targets all resolve a non-empty, order-preserved
    `primary_projection`."""
    catalog = yaml.safe_load(Path(schema.CATALOG_PATH).read_text(encoding="utf-8"))
    for name in ("Replication", "DNARepair", "DNADamage"):
        contract = schema.resolve_catalog_process_contract(name, catalog)
        assert isinstance(contract["primary_projection"], list)
        assert len(contract["primary_projection"]) > 0, name
        assert all(isinstance(component, str) for component in contract["primary_projection"])


def test_real_catalog_macromolecularcomplexation_has_joint_check_true():
    catalog = yaml.safe_load(Path(schema.CATALOG_PATH).read_text(encoding="utf-8"))
    contract = schema.resolve_catalog_process_contract("MacromolecularComplexation", catalog)
    assert contract["joint_check"] is True


def test_real_catalog_cytokinesis_and_ftsz_have_seed_window_tick_range():
    catalog = yaml.safe_load(Path(schema.CATALOG_PATH).read_text(encoding="utf-8"))
    cytokinesis_contract = schema.resolve_catalog_process_contract("Cytokinesis", catalog)
    ftsz_contract = schema.resolve_catalog_process_contract("FtsZPolymerization", catalog)
    assert cytokinesis_contract["seed_window"] == {"tick_range_from_division": [-4999, 0]}
    assert ftsz_contract["seed_window"] == {"tick_range_from_division": [-200, 0]}


def test_real_catalog_translation_has_no_seed_window_empty_projection_false_joint_check():
    """A process outside the chromosome-primary/EVENT_CLASS-division set
    resolves all three new fields to their documented defaults."""
    catalog = yaml.safe_load(Path(schema.CATALOG_PATH).read_text(encoding="utf-8"))
    contract = schema.resolve_catalog_process_contract("Translation", catalog)
    assert contract["seed_window"] is None
    assert contract["primary_projection"] == []
    assert contract["joint_check"] is False


# --- Post-migration fail-closed: a leftover OLD whole-catalog key is rejected --


def test_old_style_whole_catalog_key_is_rejected_as_extra_unexpected(tmp_path):
    """A sentinel still carrying the pre-migration whole-file `"catalog"`
    key (instead of, or alongside, the new `"catalog_entry"` key) must be
    flagged non-green by the CURRENT generator/checker -- proving the F5
    bidirectional "recorded key not in current expected set" check (see
    `generator._check_sweep_provenance_staleness`) catches an un-migrated
    sentinel exactly like it catches any other stale/renamed dependency
    key, with zero new gating code. Uses the real `Metabolism` catalog
    entry (never a synthetic one) so this exercises the exact real
    checking code path a truly un-migrated tracked file would hit."""
    entry = cat.in_scope_processes()["Metabolism"]
    evidence_dir = tmp_path / "Metabolism" / schema.DESIGN_A_SUBDIR
    write_full_valid_evidence(
        evidence_dir,
        process="Metabolism",
        seeds=entry.n_seeds,
        m_ticks=entry.m_ticks,
        channels={entry.primary_channel or "substrates": {
            "verdict": "PASS", "aggregation": "per_tick_vector_w1_mean", "is_primary": True, "is_event_channel": False,
            "w1_oc_vs_karr": 0.1, "threshold": 1.0, "q95_null": 0.05, "n_nonzero_oc": 100, "n_nonzero_karr": 100,
        }},
        oc_module=entry.oc_module,
        harness_type=entry.harness_type,
    )

    # Sanity: freshly written (current-scheme) evidence is green.
    row_clean = gen.build_process_row(entry, tmp_path)
    assert row_clean["green"] is True, row_clean["reasons"]

    # Simulate an UN-MIGRATED sentinel: swap "catalog_entry" back to the
    # OLD "catalog" (whole-file) key, as every tracked sentinel looked
    # before the R6 migration.
    import json

    prov_path = evidence_dir / schema.SWEEP_PROVENANCE_FILE
    payload = json.loads(prov_path.read_text(encoding="utf-8"))
    assert "catalog_entry" in payload["source_hashes"]
    catalog_entry_value = payload["source_hashes"].pop("catalog_entry")
    payload["source_hashes"]["catalog"] = catalog_entry_value
    prov_path.write_text(json.dumps(payload), encoding="utf-8")

    row_stale = gen.build_process_row(entry, tmp_path)
    assert row_stale["green"] is False
    assert any("extra/unexpected" in reason and "catalog" in reason for reason in row_stale["reasons"])
    assert any("missing source hash for 'catalog_entry'" in reason for reason in row_stale["reasons"])

