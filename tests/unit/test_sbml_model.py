"""Unit tests for opencell.models.sbml_model.

Covers:

* Formula compilation (sympy → numpy callable)
* Loading on the real Chassagnole BIOMD0000000051 file
* RHS shape and finiteness
* Provenance fields (SHA-256, level/version, structure)
* Loud failure on unsupported SBML features (events, function defs, rate rules)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

libsbml = pytest.importorskip("libsbml")

from opencell.models.sbml_model import (  # noqa: E402
    SbmlOdeModel,
    _compile_formula,
)


CHASSAGNOLE_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "biomodels_reference"
    / "BIOMD0000000051_chassagnole2002.xml"
)


# ---------------------------------------------------------------------------
# Formula compilation
# ---------------------------------------------------------------------------


class TestCompileFormula:
    def test_simple_arithmetic(self):
        cf = _compile_formula("a + b * c")
        assert set(cf.symbols) == {"a", "b", "c"}
        # symbols are sorted; pass values in that order
        vals = {"a": 1.0, "b": 2.0, "c": 3.0}
        assert cf.fn(*[vals[s] for s in cf.symbols]) == pytest.approx(7.0)

    def test_pow_function(self):
        cf = _compile_formula("pow(x, n)")
        vals = {"x": 2.0, "n": 3.0}
        assert cf.fn(*[vals[s] for s in cf.symbols]) == pytest.approx(8.0)

    def test_michaelis_menten(self):
        # NB: 'S' would collide with sympy.S singleton without local_dict
        cf = _compile_formula("Vmax * S / (Km + S)")
        vals = {"Vmax": 10.0, "Km": 1.0, "S": 1.0}
        assert cf.fn(*[vals[s] for s in cf.symbols]) == pytest.approx(5.0)

    def test_sympy_singleton_names_not_shadowed(self):
        # All of S, E, I, Q, O, N would silently become sympy singletons
        # (S→Singleton, E→exp(1), I→sqrt(-1), Q→Rationals) without protection.
        cf = _compile_formula("S + E + I + N + O + Q")
        # With local_dict in place, every name should be a free symbol
        assert set(cf.symbols) == {"S", "E", "I", "N", "O", "Q"}
        vals = {"S": 1.0, "E": 2.0, "I": 3.0, "N": 4.0, "O": 5.0, "Q": 6.0}
        assert cf.fn(*[vals[s] for s in cf.symbols]) == pytest.approx(21.0)

    def test_invalid_formula_raises(self):
        with pytest.raises(ValueError, match="Failed to parse"):
            _compile_formula("a +/ b", context="test")


# ---------------------------------------------------------------------------
# Loading the Chassagnole reference SBML
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not CHASSAGNOLE_PATH.exists(),
    reason="Chassagnole reference SBML not present",
)
class TestLoadChassagnole:
    @pytest.fixture(scope="class")
    def model(self) -> SbmlOdeModel:
        return SbmlOdeModel.from_file(CHASSAGNOLE_PATH)

    def test_topology(self, model: SbmlOdeModel):
        # Chassagnole 2002 BIOMD0000000051 ground truth
        assert model.n_species == 18
        assert model.n_reactions == 48
        assert len(model.rules) == 7  # cofactor forcing functions
        assert set(model.compartment_volumes) == {"extracellular", "cytosol"}

    def test_provenance_includes_sha256(self, model: SbmlOdeModel):
        prov = model.provenance()
        assert len(prov["sbml_sha256"]) == 64
        assert prov["sbml_level"] == 2
        assert prov["n_dynamic_species"] == 18
        assert prov["n_reactions"] == 48
        assert prov["n_assignment_rules"] == 7

    def test_initial_y_shape(self, model: SbmlOdeModel):
        assert model.initial_y.shape == (18,)
        assert model.initial_y.dtype == np.float64
        assert np.all(model.initial_y > 0)

    def test_species_index_round_trip(self, model: SbmlOdeModel):
        idx = model.species_index()
        assert len(idx) == 18
        for sid in model.species_ids:
            assert idx[sid] == model.species_ids.index(sid)

    def test_rhs_finite_at_initial(self, model: SbmlOdeModel):
        dy = model.rhs(0.0, model.initial_y)
        assert dy.shape == (18,)
        assert np.all(np.isfinite(dy))

    def test_fluxes_shape(self, model: SbmlOdeModel):
        f = model.fluxes(0.0, model.initial_y)
        assert f.shape == (48,)
        assert np.all(np.isfinite(f))

    def test_assignment_rules_evaluated(self, model: SbmlOdeModel):
        # The 7 cofactors should be present in env (catp, cadp, ...)
        env = model._build_env(0.0, model.initial_y)
        for cofactor in ("catp", "cadp", "camp", "cnadp", "cnadph", "cnad", "cnadh"):
            assert cofactor in env
            assert np.isfinite(env[cofactor])

    def test_rhs_changes_with_time(self, model: SbmlOdeModel):
        # Cofactors are time-driven, so RHS at t=0 vs t=10 should differ
        dy0 = model.rhs(0.0, model.initial_y)
        dy10 = model.rhs(10.0, model.initial_y)
        assert not np.allclose(dy0, dy10)


# ---------------------------------------------------------------------------
# Loud-failure guarantees on unsupported features
# ---------------------------------------------------------------------------


class TestUnsupportedFeatures:
    """Ensure we never silently degrade on SBML features we cannot translate."""

    def _write_sbml(self, tmp_path: Path, body: str) -> Path:
        sbml = f"""<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2" level="2" version="1">
  <model id="m">
    <listOfCompartments><compartment id="c" size="1"/></listOfCompartments>
    {body}
  </model>
</sbml>
"""
        p = tmp_path / "model.xml"
        p.write_text(sbml)
        return p

    def test_event_raises(self, tmp_path: Path):
        body = """
    <listOfSpecies><species id="s" compartment="c" initialConcentration="1"/></listOfSpecies>
    <listOfEvents>
      <event id="e">
        <trigger><math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><gt/><csymbol encoding="text" definitionURL="http://www.sbml.org/sbml/symbols/time">t</csymbol><cn>1</cn></apply>
        </math></trigger>
        <listOfEventAssignments>
          <eventAssignment variable="s">
            <math xmlns="http://www.w3.org/1998/Math/MathML"><cn>2</cn></math>
          </eventAssignment>
        </listOfEventAssignments>
      </event>
    </listOfEvents>
        """
        p = self._write_sbml(tmp_path, body)
        with pytest.raises(NotImplementedError, match="event"):
            SbmlOdeModel.from_file(p)

    def _write_sbml_with_funcdef(self, tmp_path: Path) -> Path:
        # SBML L2 requires a strict child-element order: functionDefinitions
        # MUST appear before compartments.  Override _write_sbml here.
        sbml = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2" level="2" version="1">
  <model id="m">
    <listOfFunctionDefinitions>
      <functionDefinition id="f">
        <math xmlns="http://www.w3.org/1998/Math/MathML">
          <lambda><bvar><ci>x</ci></bvar><apply><times/><ci>x</ci><cn>2</cn></apply></lambda>
        </math>
      </functionDefinition>
    </listOfFunctionDefinitions>
    <listOfCompartments><compartment id="c" size="1"/></listOfCompartments>
    <listOfSpecies><species id="s" compartment="c" initialConcentration="1"/></listOfSpecies>
  </model>
</sbml>
"""
        p = tmp_path / "model.xml"
        p.write_text(sbml)
        return p

    def test_function_definition_raises(self, tmp_path: Path):
        p = self._write_sbml_with_funcdef(tmp_path)
        with pytest.raises(NotImplementedError, match="functionDefinition"):
            SbmlOdeModel.from_file(p)

    def test_rate_rule_raises(self, tmp_path: Path):
        body = """
    <listOfSpecies><species id="s" compartment="c" initialConcentration="1"/></listOfSpecies>
    <listOfRules>
      <rateRule variable="s">
        <math xmlns="http://www.w3.org/1998/Math/MathML"><cn>1</cn></math>
      </rateRule>
    </listOfRules>
        """
        p = self._write_sbml(tmp_path, body)
        with pytest.raises(NotImplementedError, match="rule type"):
            SbmlOdeModel.from_file(p)

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            SbmlOdeModel.from_file(tmp_path / "does_not_exist.xml")
