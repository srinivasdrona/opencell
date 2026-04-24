"""Tests for opencell.m1.central_carbon (M1 sourced FBA module)."""
from __future__ import annotations

import json
import math

import numpy as np
import pytest

from opencell.m1 import CentralCarbonModel, load_default, pfba
from opencell.m1.central_carbon import reaction_summary, DEFAULT_FIXTURE_PATH


@pytest.fixture(scope="module")
def model() -> CentralCarbonModel:
    return load_default()


# --- Sourcing / structural integrity --------------------------------------

def test_fixture_exists():
    assert DEFAULT_FIXTURE_PATH.exists(), DEFAULT_FIXTURE_PATH


def test_fixture_has_full_provenance():
    data = json.loads(DEFAULT_FIXTURE_PATH.read_text())
    for src in ("iPS189_sbml", "wholecellkb_xlsx", "karr_parameters_json"):
        assert src in data["sources"], src
        for k in ("path", "sha256", "size_bytes", "citation"):
            assert data["sources"][src].get(k), (src, k)


def test_model_loads_central_carbon_subnetwork(model):
    must_have = {
        "R_PGI", "R_PFK", "R_FBA", "R_TPI", "R_GAPD",
        "R_PGK", "R_PGM", "R_ENO", "R_PYK", "R_GLCpts",
        "R_LDH_L", "R_PTAr", "R_ACKr",
        "R_ADK1", "R_ATPS4r", "R_ATPM",
        "R_EX_glc_D_e_", "R_EX_lac_L_e_", "R_EX_ac_e_",
    }
    assert must_have.issubset(set(model.reactions)), (
        must_have - set(model.reactions))


def test_atp_in_species(model):
    assert "M_atp_c" in model.species
    assert "M_adp_c" in model.species
    assert "M_amp_c" in model.species


# --- Karr-sourced bounds applied -----------------------------------------

def test_glucose_uptake_bound_is_karr_sourced(model):
    expected = float(
        model.karr_bounds["exchangeRateUpperBound_carbon"]["value"])
    idx = model.reaction_index("R_EX_glc_D_e_")
    assert math.isclose(model.lb[idx], -expected)
    assert math.isclose(model.ub[idx],  expected)


def test_ngam_lb_applied(model):
    expected = float(
        model.karr_bounds["nonGrowthAssociatedMaintenance"]["value"])
    idx = model.reaction_index("R_ATPM")
    assert math.isclose(model.lb[idx], expected)


# --- Stoichiometric integrity (atom balance via ATP row) -----------------

def test_atp_row_signs_match_biology(model):
    atp_row = model.atp_balance_coefficients()
    for rid in ["R_PFK", "R_ATPM"]:
        assert atp_row[model.reaction_index(rid)] < 0, rid
    # GLCpts uses PEP, not ATP, so coefficient is exactly 0.
    assert atp_row[model.reaction_index("R_GLCpts")] == 0.0
    for rid in ["R_PGK", "R_PYK"]:
        assert atp_row[model.reaction_index(rid)] > 0, rid


# --- pFBA feasibility ----------------------------------------------------

def test_atpm_feasibility_meets_ngam(model):
    v, info = pfba(model, objective_reaction="R_ATPM", sense="max")
    assert info["pfba_status"] in ("ok", "lp2_failed_returning_lp1"), info
    ngam = float(model.karr_bounds["nonGrowthAssociatedMaintenance"]["value"])
    atpm_flux = v[model.reaction_index("R_ATPM")]
    assert atpm_flux >= ngam - 1e-6, (atpm_flux, ngam)


def test_steady_state_mass_balance(model):
    v, _ = pfba(model, objective_reaction="R_ATPM", sense="max")
    # Steady-state must hold for non-boundary species only.
    bal_mask = model.balanced_species_mask
    residual = (model.S[bal_mask]) @ v
    assert np.max(np.abs(residual)) < 1e-6, np.max(np.abs(residual))


def test_glycolytic_flux_is_finite_and_directional(model):
    v, _ = pfba(model, objective_reaction="R_ATPM", sense="max")
    summary = dict(reaction_summary(model, v))
    assert summary.get("R_EX_glc_D_e_", 0.0) < 0.0
    assert v[model.reaction_index("R_PFK")] >= -1e-9


def test_total_flux_is_finite(model):
    v, info = pfba(model, objective_reaction="R_ATPM", sense="max")
    assert np.all(np.isfinite(v))
    assert info["total_flux_l1"] < float("inf")
    assert info["total_flux_l1"] > 0.0


# --- No-synthesis guard --------------------------------------------------

def test_no_hardcoded_numerics_in_module():
    """Module must not embed Karr-sourced numeric constants directly."""
    import opencell.m1.central_carbon as mod
    src = mod.__file__
    text = open(src, encoding="utf-8").read()
    forbidden = ["12.0", "8.39", "59.81"]
    for tok in forbidden:
        assert tok not in text, f"Hardcoded numeric {tok!r} in {src}"
