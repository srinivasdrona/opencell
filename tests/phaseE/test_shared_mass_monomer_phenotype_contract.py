"""P10b consumes the source ProteinMonomer class, not all protein material.

Its raw archive target matches ProteinMonomer.m's ten forms/six compartments.
Physical ProteinComplex particles still belong in full cell protein/total;
changing only complex stock must not change this monomer-class extractor.
"""

import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from scipy.constants import Avogadro

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/vivarium"))

import test_cohort1_shared_mass_projection_contract as source

from opencell.analysis import phenotypes
from opencell.analysis.cell_mass import compute_cell_mass


def test_monomer_phenotype_uses_source_forms_and_is_complex_insensitive(monkeypatch, record_property):
    c = source.contract.__wrapped__()
    state = deepcopy(c["base"])
    state["rna"] = deepcopy(c["cases"]["mixed_forms"])
    wid = next(wid for wid in sorted(c["enrolled"])
               if c["protein_forms"]["processed_i"][wid] != c["protein_forms"]["mature"][wid])
    state["protein"]["compartment_counts"]["processed_i"][wid]["c"] += 1.0
    state["protein"]["counts"][wid] = float("nan")  # stale derived view, not another authority
    complex_wid = "MG_072_DIMER"
    source_delta = c["complex_forms"]["mature"][complex_wid] / Avogadro
    assert state["complex"]["counts"][complex_wid] > 0 and source_delta > 0

    # This is a read-only class reference, never the state passed to production.
    # Every real caller below receives the complete unchanged mixed basket.
    expected_monomer = source._expected({"protein": state["protein"]}, c)["protein"]
    expected_full = source._expected(state, c)
    with np.load(ROOT / "data/karr_archive/karr_archive.npz") as archive:
        raw_counts = np.asarray(archive["proteins_targeted__counts"], dtype=float)
        raw_mw = np.asarray(archive["proteins_targeted__molecularWeights"], dtype=float)
    expected_target = float(np.sum(raw_counts * raw_mw[:, None]) / Avogadro)
    before = deepcopy(state)

    def live_full_breakdown(*models):
        return compute_cell_mass(state, *models)

    monkeypatch.setattr(phenotypes, "_build_chassis_mass_breakdown", live_full_breakdown)
    full_before = compute_cell_mass(state, *c["models"])
    measurement_before = phenotypes.measure_dry_mass_protein_monomer_g(*c["models"])
    np.testing.assert_equal(state, before)
    state["complex"]["counts"][complex_wid] += 1.0  # UNIT particle increment, not trajectory proof
    after = deepcopy(state)
    full_after = compute_cell_mass(state, *c["models"])
    measurement_after = phenotypes.measure_dry_mass_protein_monomer_g(*c["models"])
    np.testing.assert_equal(state, after)
    assert full_before.protein_mass_g == pytest.approx(expected_full["protein"], rel=1e-12, abs=0)
    assert full_before.protein_mass_g > expected_monomer
    assert full_after.total_g - full_before.total_g == pytest.approx(source_delta, rel=1e-9, abs=0)
    assert measurement_before.target == pytest.approx(expected_target, rel=1e-12, abs=0)
    assert measurement_after.target == measurement_before.target
    record_property("source_monomer_g", expected_monomer)
    record_property("actual_monomer_extractor_before_g", measurement_before.predicted)
    record_property("actual_monomer_extractor_after_g", measurement_after.predicted)
    record_property("full_protein_before_g", full_before.protein_mass_g)
    record_property("source_complex_increment_g", source_delta)
    assert measurement_before.predicted == pytest.approx(expected_monomer, rel=1e-12, abs=0)
    assert measurement_after.predicted == pytest.approx(expected_monomer, rel=1e-12, abs=0)
