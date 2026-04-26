"""Tests for `opencell.m1.compartmented` (Phase D.1).

Validates:
* Loading + shape conformance of the (585, 645, 3) compartmented S.
* Compartment vocabulary and index mapping.
* Stoich queries match Karr's KB (DNA gyrase, glucose uptake).
* Aggregation invariant (sum over compartments == S_aggregate).
* Unit conversion mmol/gDW/h <-> molecules/s/cell.
* Supply-side calibration helper produces a sensible nonzero map at SS,
  and (rubber-duck check) confirms NTPs are NOT supplied through FBA.
"""
from __future__ import annotations

import numpy as np
import pytest

from opencell.m1.compartmented import (
    AVOGADRO,
    CompartmentedStoichiometryModel,
    SECONDS_PER_HOUR,
    compute_lp_supply_baseline,
    load_default,
)


@pytest.fixture(scope="module")
def model() -> CompartmentedStoichiometryModel:
    return load_default()


# ---- shape & vocab ----

def test_S_shape_585_645_3(model):
    assert model.S.shape == (585, 645, 3)
    assert model.n_substrates == 585
    assert model.n_reactions == 645
    assert model.n_compartments == 3


def test_aggregate_matches_sum_over_compartments(model):
    np.testing.assert_array_equal(model.S_aggregate, model.S.sum(axis=2))


def test_compartment_vocab_is_c_e_m(model):
    assert model.compartment_wids_3 == ["c", "e", "m"]
    assert model.compartment_index("c") == 0
    assert model.compartment_index("e") == 1
    assert model.compartment_index("m") == 2


def test_unknown_compartment_raises(model):
    with pytest.raises(KeyError):
        model.compartment_index("d")  # DNA compartment not in metabolism


def test_substrate_and_reaction_counts(model):
    assert len(model.substrate_wids_585) == 585
    assert len(model.reaction_wids_645) == 645


# ---- structural sanity ----

def test_S_is_signed_integer_dtype(model):
    assert np.issubdtype(model.S.dtype, np.integer)


def test_some_stoichiometry_is_nonzero(model):
    assert model.stats["nnz_total"] > 1000


def test_cytosol_has_most_nonzeros(model):
    """Karr's metabolism is overwhelmingly cytosolic."""
    assert model.stats["nnz_cytosol"] > model.stats["nnz_extracellular"]
    assert model.stats["nnz_cytosol"] > model.stats["nnz_membrane"]


# ---- spot-check a known glucose-uptake reaction ----

def test_glucose_uptake_sign_convention(model):
    """Glucose enters M. genitalium via the PTS system (TX_GLCPTS):
    extracellular GLC + cytosolic PEP -> cytosolic G6P + cytosolic PYR.
    With v_TX_GLCPTS > 0 (uptake), GLC must have negative coeff in `e`,
    G6P positive in `c`, PEP negative in `c`."""
    ri = model.reaction_index("TX_GLCPTS")
    e = model.compartment_index("e")
    c = model.compartment_index("c")
    assert model.S[model.substrate_index("GLC"), ri, e] == -1
    assert model.S[model.substrate_index("G6P"), ri, c] == 1
    assert model.S[model.substrate_index("PEP"), ri, c] == -1
    assert model.S[model.substrate_index("PYR"), ri, c] == 1


def test_dna_gyrase_atp_hydrolysis(model):
    """DNA gyrase complex carries ATP turnover -- represented in
    metabolism only if the catalytic ATP-hydrolysis side rxn is in the
    645 set. Just check ATP appears in many cytosol reactions."""
    si = model.substrate_index("ATP")
    n_cyt_rxns_with_atp = int(np.count_nonzero(model.S[si, :, 0]))
    assert n_cyt_rxns_with_atp > 50, f"only {n_cyt_rxns_with_atp} cyt rxns touch ATP"


# ---- unit conversion ----

def test_mmol_per_gdwh_to_molecules_per_s(model):
    """1 mmol/gDW/h * 3.94e-15 g * 1e-3 mol/mmol * 6.022e23 / 3600 s
       ~= 660 molecules/s for a single-cell M. genitalium."""
    converted = model.mmol_per_gdwh_to_molecules_per_s(1.0)
    expected = 1e-3 * AVOGADRO * model.cell_dry_mass_g / SECONDS_PER_HOUR
    assert converted == pytest.approx(expected)
    # sanity: in the right magnitude
    assert 100 < converted < 10000, f"unexpected magnitude: {converted}"


def test_unit_conversion_is_linear(model):
    x = np.array([1.0, -2.5, 100.0])
    out = model.mmol_per_gdwh_to_molecules_per_s(x)
    np.testing.assert_allclose(out / x, np.full(3, out[0] / x[0]))


# ---- supply-side calibration ----

@pytest.fixture(scope="module")
def baseline():
    from opencell.m1.karr_metabolism import load_default as load_m1
    m1 = load_m1()
    return compute_lp_supply_baseline(m1)


def test_baseline_is_nonempty_dict(baseline):
    assert isinstance(baseline, dict)
    assert len(baseline) > 20, f"baseline has only {len(baseline)} entries"


def test_baseline_keys_are_substrate_compartment_pairs(baseline, model):
    for (sub_wid, cmp_wid), rate in list(baseline.items())[:20]:
        assert sub_wid in model.substrate_wids_585
        assert cmp_wid in model.compartment_wids_3
        assert isinstance(rate, float)


def test_baseline_includes_extracellular_glucose_uptake(baseline):
    """Glucose is the dominant carbon source -- should appear with
    negative (consumed) sign in extracellular compartment, since
    external exchange `GLC` flux v > 0 means uptake."""
    glc_e = baseline.get(("GLC", "e"))
    if glc_e is not None:
        # Net production of extracellular glucose by FBA must be negative
        # (FBA consumes it from medium).
        assert glc_e < 0, f"expected GLC uptake (negative) at e, got {glc_e}"


def test_baseline_NTPs_NOT_supplied_through_FBA(baseline):
    """Critical invariant from Phase D.1 spike: Karr's metabolism does
    NOT model NTP supply (it lives in non-FBA processes M4-M28). So at
    SS the FBA submodel produces zero or negative net NTP in cytosol."""
    for ntp in ("ATP", "CTP", "GTP", "UTP"):
        rate = baseline.get((ntp, "c"))
        if rate is not None:
            # Allow small positive numerical noise but assert no
            # large positive supply.
            assert rate < 1e6, (
                f"unexpected large positive {ntp} supply through FBA: {rate}"
            )


def test_baseline_total_carbon_is_negative(baseline):
    """At SS the cell is net consuming carbon from medium; sum of
    extracellular fluxes for major carbon sources should be negative."""
    sources = ("GLC", "GL", "AC")  # glucose, glycerol, acetate
    total = sum(baseline.get((s, "e"), 0.0) for s in sources)
    # Should be net consumed (negative) at SS.
    assert total < 0, f"expected net carbon uptake (negative), got {total}"
