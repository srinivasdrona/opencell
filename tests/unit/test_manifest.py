"""Tests for opencell.manifest (SBML -> manifest emitter).

Uses a synthetic SBML fixture that mimics the structure of BioModels
curated entries (Chassagnole 2002 in particular): user-defined unit
definitions, global parameters, local kinetic-law parameters, and
species with initial concentrations.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from opencell.manifest import (
    ManifestHeader,
    SbmlUnit,
    SbmlUnitDefinition,
    build_manifest,
    extract_metadata,
    parse_sbml,
    resolve_unit,
    stringify_unit,
    write_manifest_yaml,
)
from opencell.manifest.sbml import _format_unit_token


# ---------------------------------------------------------------------------
# Synthetic fixture (mimics Chassagnole BIOMD0000000051 style)
# ---------------------------------------------------------------------------

SYNTHETIC_SBML = b"""<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2" level="2" version="1">
  <model id="chassagnole_test" name="Test model">
    <listOfUnitDefinitions>
      <unitDefinition id="substance">
        <listOfUnits>
          <unit kind="mole" scale="-3"/>
        </listOfUnits>
      </unitDefinition>
      <unitDefinition id="substance_per_volume_per_time">
        <listOfUnits>
          <unit kind="mole" scale="-3"/>
          <unit kind="litre" exponent="-1"/>
          <unit kind="second" exponent="-1"/>
        </listOfUnits>
      </unitDefinition>
      <unitDefinition id="time">
        <listOfUnits>
          <unit kind="second"/>
        </listOfUnits>
      </unitDefinition>
    </listOfUnitDefinitions>

    <listOfCompartments>
      <compartment id="cytoplasm" size="1.0"/>
    </listOfCompartments>

    <listOfSpecies>
      <species id="g6p" name="Glucose-6-phosphate" compartment="cytoplasm"
               initialConcentration="3.48" substanceUnits="substance"/>
      <species id="f6p" name="Fructose-6-phosphate" compartment="cytoplasm"
               initialConcentration="0.6" substanceUnits="substance"/>
    </listOfSpecies>

    <listOfParameters>
      <parameter id="rmaxPGI" name="PGI Vmax" value="650.988"
                 units="substance_per_volume_per_time"/>
      <parameter id="KPGIeqG6P" name="PGI Keq G6P" value="0.1725"/>
    </listOfParameters>

    <listOfReactions>
      <reaction id="PGI">
        <kineticLaw>
          <listOfParameters>
            <parameter id="kcat_local" value="100.0" units="time"/>
            <parameter id="Km_local" value="0.5"/>
          </listOfParameters>
        </kineticLaw>
      </reaction>
      <reaction id="PFK">
        <kineticLaw>
          <listOfParameters>
            <parameter id="kcat_local" value="50.0" units="time"/>
          </listOfParameters>
        </kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>
"""


# ---------------------------------------------------------------------------
# Unit formatting
# ---------------------------------------------------------------------------

class TestUnitFormatting:
    def test_format_simple_mole(self):
        # mole with scale -3 = millimole
        assert _format_unit_token(SbmlUnit(kind="mole", scale=-3)) == "mmol"

    def test_format_litre(self):
        assert _format_unit_token(SbmlUnit(kind="litre")) == "L"

    def test_format_second_inverse(self):
        assert _format_unit_token(SbmlUnit(kind="second", exponent=-1)) == "s^-1"

    def test_stringify_mmol_per_L_per_s(self):
        ud = SbmlUnitDefinition(
            id="substance_per_volume_per_time",
            units=[
                SbmlUnit(kind="mole", scale=-3),
                SbmlUnit(kind="litre", exponent=-1),
                SbmlUnit(kind="second", exponent=-1),
            ],
        )
        s = stringify_unit(ud)
        # Should contain mmol in numerator and L*s in denominator
        assert "mmol" in s
        assert "L" in s
        assert "s" in s
        # Two negative-exponent units => denominator group with parens
        assert s == "mmol/(L*s)"

    def test_stringify_single_denom_no_parens(self):
        ud = SbmlUnitDefinition(
            id="conc_per_time",
            units=[SbmlUnit(kind="mole", scale=-3), SbmlUnit(kind="second", exponent=-1)],
        )
        # Single denom -> "mmol/s" not "mmol/(s)"
        assert stringify_unit(ud) == "mmol/s"

    def test_stringify_dimensionless(self):
        ud = SbmlUnitDefinition(id="dim", units=[SbmlUnit(kind="dimensionless")])
        assert stringify_unit(ud) == "1"

    def test_stringify_empty_falls_back_to_id(self):
        ud = SbmlUnitDefinition(id="weird")
        assert stringify_unit(ud) == "weird"


class TestUnitResolution:
    def test_resolve_user_defined(self):
        ud = SbmlUnitDefinition(
            id="x", units=[SbmlUnit(kind="second", exponent=-1)]
        )
        # Single denominator-only unit renders as "1/s"
        assert resolve_unit("x", {"x": ud}) == "1/s"

    def test_resolve_builtin_kind(self):
        assert resolve_unit("mole", {}) == "mol"
        assert resolve_unit("second", {}) == "s"

    def test_resolve_unknown_falls_back(self):
        assert resolve_unit("mystery_unit", {}) == "mystery_unit"

    def test_resolve_empty(self):
        assert resolve_unit("", {}) == ""


# ---------------------------------------------------------------------------
# SBML parsing
# ---------------------------------------------------------------------------

class TestSbmlParsing:
    @pytest.fixture(scope="class")
    def parsed(self):
        return parse_sbml(SYNTHETIC_SBML)

    def test_parse_returns_entities_and_units(self, parsed):
        entities, udefs = parsed
        assert entities
        assert "substance_per_volume_per_time" in udefs
        assert udefs["substance_per_volume_per_time"].units

    def test_global_parameters_extracted(self, parsed):
        entities, _ = parsed
        globals_ = [e for e in entities if e.kind == "global_parameter"]
        ids = {e.sbml_id for e in globals_}
        assert ids == {"rmaxPGI", "KPGIeqG6P"}

    def test_global_parameter_value_and_unit(self, parsed):
        entities, _ = parsed
        rmax = next(e for e in entities if e.sbml_id == "rmaxPGI")
        assert rmax.value == pytest.approx(650.988)
        assert rmax.units_resolved == "mmol/(L*s)"
        assert rmax.kind == "global_parameter"

    def test_local_parameters_extracted(self, parsed):
        entities, _ = parsed
        locals_ = [e for e in entities if e.kind == "local_parameter"]
        # 3 local params total: 2 in PGI, 1 in PFK
        assert len(locals_) == 3
        # And they carry their parent reaction id
        assert {e.parent_reaction for e in locals_} == {"PGI", "PFK"}

    def test_local_kcat_value(self, parsed):
        entities, _ = parsed
        kcats = [e for e in entities if e.sbml_id == "kcat_local"]
        # Two kcat_local entries, one per reaction
        assert len(kcats) == 2
        values = sorted(e.value for e in kcats)
        assert values == [50.0, 100.0]

    def test_species_initials_extracted_by_default(self, parsed):
        entities, _ = parsed
        species = [e for e in entities if e.kind == "species_initial"]
        ids = {e.sbml_id for e in species}
        assert ids == {"g6p", "f6p"}
        g6p = next(e for e in species if e.sbml_id == "g6p")
        assert g6p.value == pytest.approx(3.48)
        assert g6p.compartment == "cytoplasm"

    def test_species_skipped_when_disabled(self):
        entities, _ = parse_sbml(SYNTHETIC_SBML, include_species=False)
        assert all(e.kind != "species_initial" for e in entities)


# ---------------------------------------------------------------------------
# Manifest emission
# ---------------------------------------------------------------------------

class TestManifestEmission:
    @pytest.fixture
    def manifest(self):
        entities, _ = parse_sbml(SYNTHETIC_SBML)
        header = ManifestHeader(
            doi="10.1002/bit.10288",
            biomodels_id="BIOMD0000000051",
            organism="E. coli K-12",
            condition="glucose-limited continuous culture",
        )
        return build_manifest(entities, header=header, model_slug="chassagnole_test")

    def test_manifest_has_metadata(self, manifest):
        assert manifest["model_slug"] == "chassagnole_test"
        assert manifest["paper"]["doi"] == "10.1002/bit.10288"
        assert manifest["paper"]["biomodels_id"] == "BIOMD0000000051"
        assert manifest["manifest_version"] == "0.1"
        assert "generated_on" in manifest

    def test_manifest_entries_count(self, manifest):
        # 2 global + 3 local + 2 species = 7
        assert len(manifest["parameters"]) == 7

    def test_parameter_id_slugified(self, manifest):
        ids = {p["parameter_id"] for p in manifest["parameters"]}
        assert "chassagnole_test-rmaxpgi" in ids

    def test_local_param_id_disambiguated_by_reaction(self, manifest):
        # kcat_local appears in two reactions; ids must collide-resolve
        ids = [p["parameter_id"] for p in manifest["parameters"]
               if "kcat_local" in p["parameter_id"]]
        assert len(ids) == 2
        assert len(set(ids)) == 2  # all unique
        # At least one should have a reaction suffix
        assert any("pgi" in i or "pfk" in i for i in ids)

    def test_target_unit_carried_through(self, manifest):
        rmax = next(p for p in manifest["parameters"]
                    if p["sbml_id"] == "rmaxPGI")
        assert rmax["target_unit"] == "mmol/(L*s)"
        assert rmax["sbml_value"] == pytest.approx(650.988)

    def test_yaml_round_trip(self, manifest, tmp_path):
        out = tmp_path / "test_manifest.yaml"
        write_manifest_yaml(manifest, out)
        assert out.exists()
        loaded = yaml.safe_load(out.read_text())
        assert loaded["model_slug"] == manifest["model_slug"]
        assert len(loaded["parameters"]) == len(manifest["parameters"])

    def test_required_fields_always_present(self, manifest):
        for p in manifest["parameters"]:
            assert "parameter_id" in p
            assert "symbol" in p
            assert "target_unit" in p


# ---------------------------------------------------------------------------
# CLI smoke-ish test (import only — full subprocess in integration)
# ---------------------------------------------------------------------------

class TestCliEntryPoint:
    def test_cli_module_importable(self):
        # Make sure the CLI script imports cleanly without side effects
        spec_path = Path(__file__).resolve().parents[2] / "tools" / "biomodels_manifest.py"
        assert spec_path.exists()


# ---------------------------------------------------------------------------
# Metadata extraction (MIRIAM annotations)
# ---------------------------------------------------------------------------

ANNOTATED_SBML = b"""<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2" level="2" version="1">
  <model id="Chassagnole2002_test" name="Chassagnole 2002 test">
    <notes>
      <body xmlns="http://www.w3.org/1999/xhtml">
        <p>This is a short notes block describing the model.</p>
      </body>
    </notes>
    <annotation>
      <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:bqmodel="http://biomodels.net/model-qualifiers/"
               xmlns:bqbiol="http://biomodels.net/biology-qualifiers/"
               xmlns:vCard="http://www.w3.org/2001/vcard-rdf/3.0#">
        <rdf:Description rdf:about="#metaid">
          <dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">
            <rdf:Bag>
              <rdf:li rdf:parseType="Resource">
                <vCard:N rdf:parseType="Resource">
                  <vCard:Family>Snoep</vCard:Family>
                  <vCard:Given>Jacky</vCard:Given>
                </vCard:N>
              </rdf:li>
            </rdf:Bag>
          </dc:creator>
          <bqmodel:is>
            <rdf:Bag>
              <rdf:li rdf:resource="http://identifiers.org/biomodels.db/BIOMD0000000051"/>
            </rdf:Bag>
          </bqmodel:is>
          <bqmodel:isDescribedBy>
            <rdf:Bag>
              <rdf:li rdf:resource="http://identifiers.org/pubmed/12082140"/>
            </rdf:Bag>
          </bqmodel:isDescribedBy>
          <bqbiol:hasTaxon>
            <rdf:Bag>
              <rdf:li rdf:resource="http://identifiers.org/taxonomy/562"/>
            </rdf:Bag>
          </bqbiol:hasTaxon>
        </rdf:Description>
      </rdf:RDF>
    </annotation>
    <listOfParameters>
      <parameter id="k1" value="1.0"/>
    </listOfParameters>
  </model>
</sbml>
"""


class TestModelMetadata:
    @pytest.fixture(scope="class")
    def md(self):
        return extract_metadata(ANNOTATED_SBML)

    def test_model_id_and_name(self, md):
        assert md.model_id == "Chassagnole2002_test"
        assert md.model_name == "Chassagnole 2002 test"

    def test_biomodels_id_extracted(self, md):
        assert md.biomodels_id == "BIOMD0000000051"

    def test_pubmed_extracted(self, md):
        assert md.pubmed_id == "12082140"

    def test_taxonomy_to_organism(self, md):
        assert md.taxonomy_id == "562"
        assert md.organism == "Escherichia coli"

    def test_creators_extracted(self, md):
        assert "Jacky Snoep" in md.creators

    def test_notes_excerpt(self, md):
        assert "short notes block" in md.notes_excerpt

    def test_no_doi_when_absent(self, md):
        # This SBML has no identifiers.org/doi/ resource, so doi must be empty
        assert md.doi == ""

    def test_handles_unparseable_sbml(self):
        # Malformed XML must NOT raise; returns empty metadata
        md = extract_metadata(b"<not really xml")
        assert md.biomodels_id == ""
        assert md.organism == ""

    def test_handles_minimal_sbml(self):
        # SBML with no annotations at all
        minimal = b"""<?xml version="1.0"?>
<sbml xmlns="http://www.sbml.org/sbml/level2" level="2" version="1">
  <model id="x"/>
</sbml>
"""
        md = extract_metadata(minimal)
        assert md.model_id == "x"
        assert md.biomodels_id == ""
        assert md.pubmed_id == ""

    def test_unmapped_taxonomy_leaves_organism_empty(self):
        # Unknown taxon id stays as empty organism (note added in CLI layer)
        sbml = ANNOTATED_SBML.replace(b"taxonomy/562", b"taxonomy/9999999")
        md = extract_metadata(sbml)
        assert md.taxonomy_id == "9999999"
        assert md.organism == ""
