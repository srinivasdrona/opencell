"""Phase E.0 — Karr 2012 phenotype validation harness.

First validation report against Karr's published / extracted ground
truth. Eight phenotypes split into two categories:

  fba_prediction (#1-4)    -- M1 LP solves; honestly comparable to
                              Karr stored fluxes / runtime scalars.
                              #4 is an EXPECTED FAIL (xfail) flagging
                              the structural gap that PTS glucose
                              uptake lives in non-FBA submodels.
  chassis_wiring (#5-8)    -- builds the engine and reads its state
                              vs the underlying model arrays. Catches
                              composer / integrator bugs, NOT biology.
                              Become real predictive tests once M2/M3
                              v2 mechanics replace prescribed rates.
  closed_loop  (#9)        -- runs the full Phase C loop (dynamic
                              bounds + throttle + calibrated pool
                              replenishment) and tests that the M1
                              source / M3 drain stoichiometry holds
                              the 20 AA cytosol pools at SS.

Targets and tolerances live in
    data/karr_fixtures/karr_phenotype_targets.json

The harness is designed so that adding new phenotypes (e.g. #9 cell
mass, #14 per-AA pool stability in E.1a/E.1b) is a one-line
parametrize entry plus an extractor.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencell.analysis import phenotypes as ph
from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl

TARGETS_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "karr_fixtures" / "karr_phenotype_targets.json"
)


@pytest.fixture(scope="module")
def targets() -> dict:
    with TARGETS_PATH.open() as f:
        j = json.load(f)
    assert j["schema_version"] == "karr_phenotype_targets__v1"
    return j["phenotypes"]


@pytest.fixture(scope="module")
def m1_model():
    return km.load_default()


@pytest.fixture(scope="module")
def m2_model():
    return tx.load_default()


@pytest.fixture(scope="module")
def m3_model():
    return tl.load_default()


# ---------- FBA prediction tests (#1-4) ----------

def test_p1_growth_per_s(m1_model, targets):
    spec = targets["p1_growth_per_s"]
    m = ph.measure_growth_per_s(m1_model)
    ratio = m.predicted / m.target
    assert spec["tol_rel_min"] <= ratio <= spec["tol_rel_max"], (
        f"growth_per_s pred={m.predicted:.4e} target={m.target:.4e} "
        f"ratio={ratio:.4f} outside [{spec['tol_rel_min']}, {spec['tol_rel_max']}]"
    )


def test_p2_doubling_time_h(m1_model, targets):
    spec = targets["p2_doubling_time_h"]
    m = ph.measure_doubling_time_h(m1_model)
    ratio = m.predicted / m.target
    assert spec["tol_rel_min"] <= ratio <= spec["tol_rel_max"], (
        f"doubling_time_h pred={m.predicted:.4f}h target={m.target:.4f}h "
        f"ratio={ratio:.4f} outside [{spec['tol_rel_min']}, {spec['tol_rel_max']}]"
    )


def test_p3_fba_oracle_median_log2(m1_model, targets):
    spec = targets["p3_fba_oracle_median_log2_ratio"]
    m = ph.measure_fba_oracle_median_log2(m1_model)
    assert m.predicted <= spec["tol_abs_max"], (
        f"FBA oracle median |log2(pred/stored)| = {m.predicted:.4f} > "
        f"tolerance {spec['tol_abs_max']} over {m.extra['n_compared']} rxns"
    )


@pytest.mark.xfail(
    reason="STRUCTURAL GAP: TX_GLCPTS is in the FBA col set but Karr "
    "routes glucose uptake through non-FBA submodels (PTS sugar "
    "phosphotransferase). LP solves to 0 under snapshot bounds. "
    "Will pass once M4-M28 wire up the non-FBA PTS process.",
    strict=True,
)
def test_p4_glucose_uptake_TX_GLCPTS(m1_model, targets):
    spec = targets["p4_glucose_uptake_TX_GLCPTS"]
    m = ph.measure_glucose_uptake(m1_model)
    if m.target == 0:
        pytest.skip("stored target is 0; can't compute ratio")
    ratio = m.predicted / m.target
    assert spec["tol_rel_min"] <= ratio <= spec["tol_rel_max"], (
        f"TX_GLCPTS pred={m.predicted:.4e} stored={m.target:.4e} "
        f"ratio={ratio:.4f} outside tolerance"
    )


# ---------- chassis composition invariants (#5-8) ----------

def test_p5_mrna_total_chassis_wiring(m2_model, targets):
    spec = targets["p5_mrna_total_chassis_wiring"]
    m = ph.measure_mrna_total_chassis_wiring(m2_model)
    rel_err = abs(m.predicted - m.target) / m.target
    assert rel_err < spec["tol_rel"], (
        f"mRNA wiring rel_err={rel_err:.4e} > tol {spec['tol_rel']} "
        f"(chassis={m.predicted:.1f}, model={m.target:.1f}, "
        f"genes_chassis={m.extra['n_genes_in_chassis']}, "
        f"genes_model={m.extra['n_genes_in_model']})"
    )


def test_p6_protein_total_chassis_wiring(m3_model, targets):
    spec = targets["p6_protein_total_chassis_wiring"]
    m = ph.measure_protein_total_chassis_wiring(m3_model)
    rel_err = abs(m.predicted - m.target) / m.target
    assert rel_err < spec["tol_rel"], (
        f"protein wiring rel_err={rel_err:.4e} > tol {spec['tol_rel']} "
        f"(chassis={m.predicted:.1f}, model={m.target:.1f})"
    )


def test_p7_mrna_stability_over_20s(targets):
    spec = targets["p7_mrna_stability_over_20s"]
    m = ph.measure_mrna_stability(horizon_s=spec["horizon_s"])
    assert m.predicted < spec["tol_rel"], (
        f"mRNA drift over {spec['horizon_s']}s = {m.predicted:.4e} "
        f"> tol {spec['tol_rel']} (t0={m.extra['total_t0']:.1f}, "
        f"tN={m.extra['total_tN']:.1f})"
    )


def test_p8_protein_stability_over_20s(targets):
    spec = targets["p8_protein_stability_over_20s"]
    m = ph.measure_protein_stability(horizon_s=spec["horizon_s"])
    assert m.predicted < spec["tol_rel"], (
        f"protein drift over {spec['horizon_s']}s = {m.predicted:.4e} "
        f"> tol {spec['tol_rel']} (t0={m.extra['total_t0']:.1f}, "
        f"tN={m.extra['total_tN']:.1f})"
    )


# ---------- closed-loop tests (#9) ----------

def test_p9_aa_pool_stability_over_20s(targets):
    spec = targets["p9_aa_pool_stability_over_20s"]
    m = ph.measure_aa_pool_stability(horizon_s=spec["horizon_s"])
    assert m.predicted < spec["tol_rel"], (
        f"max AA pool drift over {spec['horizon_s']}s = {m.predicted:.4e} "
        f"> tol {spec['tol_rel']} "
        f"(worst={m.extra['worst_aa']} drift={m.extra['worst_drift']:.4e}, "
        f"n_aa={m.extra['n_aa']})"
    )


@pytest.mark.xfail(
    reason="STRUCTURAL GAP -- chassis content incomplete: after the "
    "E.1b m2-counts-fix the aggregator gives chassis total ~8.4e-16 g "
    "(21% of Karr's 3.94e-15 g cell dry).  The missing ~79% lives in "
    "ProteinComplex (ribosomes, RNAP, ~1e-15 g), DNA (chromosome, "
    "~6e-16 g), lipid membrane, polysaccharides, and per-substrate "
    "snapshot counts (chassis seeds 561 non-demand substrates at 1.0 "
    "placeholder).  Pinned xfail until D.2 + M5 + substrate snapshot "
    "init close the gap (or until p10 is partitioned into per-class "
    "targets p10a/p10b/p10c).",
    strict=True,
)
def test_p10_cell_dry_mass_g(m1_model, m2_model, m3_model, targets):
    spec = targets["p10_cell_dry_mass_g"]
    m = ph.measure_cell_dry_mass(m1_model, m2_model, m3_model)
    ratio = m.predicted / m.target
    assert spec["tol_rel_min"] <= ratio <= spec["tol_rel_max"], (
        f"cell dry mass pred={m.predicted:.4e} g target={m.target:.4e} g "
        f"ratio={ratio:.4f} outside [{spec['tol_rel_min']}, {spec['tol_rel_max']}] "
        f"(sub={m.extra['substrate_mass_g']:.4e} g, "
        f"rna={m.extra['rna_mass_g']:.4e} g, "
        f"prot={m.extra['protein_mass_g']:.4e} g)"
    )
