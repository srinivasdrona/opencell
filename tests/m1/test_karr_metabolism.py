"""Smoke tests for the Karr-native M1 metabolism module."""
from __future__ import annotations

import math

import numpy as np
import pytest

from opencell.m1 import karr_metabolism as km


@pytest.fixture(scope="module")
def model() -> km.KarrMetabolismModel:
    return km.load_default()


def test_fixture_shapes(model: km.KarrMetabolismModel) -> None:
    assert model.S.shape == (376, 504)
    assert model.RHS.shape == (376,)
    assert model.lb.shape == (504,) and model.ub.shape == (504,)
    assert model.obj.shape == (504,)
    assert model.enz_bounds.shape == (504, 2)
    assert model.fluxs_stored.shape == (645,)
    assert len(model.rxn_wcm_ids_645) == 645
    assert len(model.fba_col_rxn_wcm) == 504


def test_biomass_column_is_502(model: km.KarrMetabolismModel) -> None:
    assert model.biomass_col == 502
    assert model.obj[502] == pytest.approx(1000.0)


def test_metabolic_conversion_ids_present(model: km.KarrMetabolismModel) -> None:
    n_named = sum(1 for x in model.fba_col_rxn_wcm if x is not None)
    assert n_named == 336, f"expected 336 metabolicConversion cols, got {n_named}"


def test_stored_runtime_growth(model: km.KarrMetabolismModel) -> None:
    g = model.stored_runtime["growth_per_h"]
    # Karr-published target ~0.077; stored snapshot value 0.0763.
    assert 0.07 < g < 0.08


def test_lp_solves_and_biomass_within_2x_of_stored(
    model: km.KarrMetabolismModel,
) -> None:
    v, info = km.solve_fba(model, use_full_objective=True, sense="max")
    assert info["status"] == "ok"
    pred_h = info["biomass_flux_per_h"]
    stored_h = model.stored_runtime["growth_per_h"]
    ratio = pred_h / stored_h
    assert 0.45 < ratio < 0.6, (
        f"expected static-snapshot ceiling around 0.51x, got {ratio:.3f}x"
    )


def test_per_reaction_oracle_passes(model: km.KarrMetabolismModel) -> None:
    """median |log2(predicted/karr_stored)| < 1.0 over comparable reactions.

    This is the Karr-native M1 acceptance criterion (Mode E oracle).
    """
    v, _ = km.solve_fba(model, use_full_objective=True, sense="max")
    rows = km.per_reaction_comparison(model, v, nonzero_only=False)

    log2_abs = []
    for r in rows:
        p, k = r["predicted"], r["karr_stored"]
        if p == 0 or k == 0 or not math.isfinite(p) or not math.isfinite(k):
            continue
        log2_abs.append(abs(math.log2(abs(p) / abs(k))))

    assert len(log2_abs) >= 100, f"too few comparable rxns: {len(log2_abs)}"
    median = float(np.median(log2_abs))
    assert median < 1.0, (
        f"per-reaction median |log2 ratio|={median:.3f} exceeds 1.0 threshold"
    )


def test_lookup_helpers(model: km.KarrMetabolismModel) -> None:
    # round-trip a known WCM id through the helpers
    sample = next(x for x in model.fba_col_rxn_wcm if x is not None)
    col = model.fba_col_for_wcm_id(sample)
    assert col is not None and model.fba_col_rxn_wcm[col] == sample
    idx = model.reaction_wcm_id_to_645_index(sample)
    assert 0 <= idx < 645 and model.rxn_wcm_ids_645[idx] == sample
