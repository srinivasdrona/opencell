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
    Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "karr_phenotype_targets.json"
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


def test_p1_growth_per_s(m1_model, targets) -> None:
    spec = targets["p1_growth_per_s"]
    m = ph.measure_growth_per_s(m1_model)
    ratio = m.predicted / m.target
    assert spec["tol_rel_min"] <= ratio <= spec["tol_rel_max"], (
        f"growth_per_s pred={m.predicted:.4e} target={m.target:.4e} "
        f"ratio={ratio:.4f} outside [{spec['tol_rel_min']}, {spec['tol_rel_max']}]"
    )


def test_p2_doubling_time_h(m1_model, targets) -> None:
    spec = targets["p2_doubling_time_h"]
    m = ph.measure_doubling_time_h(m1_model)
    ratio = m.predicted / m.target
    assert spec["tol_rel_min"] <= ratio <= spec["tol_rel_max"], (
        f"doubling_time_h pred={m.predicted:.4f}h target={m.target:.4f}h "
        f"ratio={ratio:.4f} outside [{spec['tol_rel_min']}, {spec['tol_rel_max']}]"
    )


def test_p3_fba_oracle_median_log2(m1_model, targets) -> None:
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
def test_p4_glucose_uptake_TX_GLCPTS(m1_model, targets) -> None:
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


def test_p5_mrna_total_chassis_wiring(m2_model, targets) -> None:
    spec = targets["p5_mrna_total_chassis_wiring"]
    m = ph.measure_mrna_total_chassis_wiring(m2_model)
    rel_err = abs(m.predicted - m.target) / m.target
    assert rel_err < spec["tol_rel"], (
        f"mRNA wiring rel_err={rel_err:.4e} > tol {spec['tol_rel']} "
        f"(chassis={m.predicted:.1f}, model={m.target:.1f}, "
        f"genes_chassis={m.extra['n_genes_in_chassis']}, "
        f"genes_model={m.extra['n_genes_in_model']})"
    )


def test_p6_protein_total_chassis_wiring(m3_model, targets) -> None:
    spec = targets["p6_protein_total_chassis_wiring"]
    m = ph.measure_protein_total_chassis_wiring(m3_model)
    rel_err = abs(m.predicted - m.target) / m.target
    assert rel_err < spec["tol_rel"], (
        f"protein wiring rel_err={rel_err:.4e} > tol {spec['tol_rel']} "
        f"(chassis={m.predicted:.1f}, model={m.target:.1f})"
    )


def test_p7_mrna_stability_over_20s(targets) -> None:
    spec = targets["p7_mrna_stability_over_20s"]
    m = ph.measure_mrna_stability(horizon_s=spec["horizon_s"])
    assert m.predicted < spec["tol_rel"], (
        f"mRNA drift over {spec['horizon_s']}s = {m.predicted:.4e} "
        f"> tol {spec['tol_rel']} (t0={m.extra['total_t0']:.1f}, "
        f"tN={m.extra['total_tN']:.1f})"
    )


def test_p8_protein_stability_over_20s(targets) -> None:
    spec = targets["p8_protein_stability_over_20s"]
    m = ph.measure_protein_stability(horizon_s=spec["horizon_s"])
    assert m.predicted < spec["tol_rel"], (
        f"protein drift over {spec['horizon_s']}s = {m.predicted:.4e} "
        f"> tol {spec['tol_rel']} (t0={m.extra['total_t0']:.1f}, "
        f"tN={m.extra['total_tN']:.1f})"
    )


# ---------- closed-loop tests (#9) ----------


def test_p9_aa_pool_stability_over_20s(targets) -> None:
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
    "init close the gap.  Phase E.1c partitions this into p10a/p10b/p10c "
    "for fine-grained green/red tracking.",
    strict=True,
)
def test_p10_cell_dry_mass_g(m1_model, m2_model, m3_model, targets) -> None:
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


# ---------- Phase E.1c per-class sub-targets (#10a/b/c) ----------
#
# Partition phenotype p10 (cell dry mass) into per-class sub-targets so
# that previously-opaque single-xfail bucket surfaces fine-grained
# green / red status by mass class.  See top of
# data/karr_fixtures/karr_phenotype_targets.json p10a/p10b/p10c entries
# for the source of each target (all derived from the Karr archive
# arrays at fixture-build time -- no hard-coded values).
#
# Karr archive-derived breakdown of cell_dry_total_mass_g (3.945e-15 g):
#   p10a RNA-class             1.715e-16 g  ( 4.35%)  xfail (mature-only chassis)
#   p10b ProteinMonomer-class  1.093e-15 g  (27.70%)  pass
#   p10c residual (everything  2.680e-15 g  (67.95%)  xfail (D.2 + M5 + lipid + pool init)
#         else: complexes, DNA, lipid, polysaccharide, true substrate pool)


@pytest.mark.xfail(
    reason="STRUCTURAL GAP: chassis tracks only mature mRNA / RNA forms "
    "(525 genes, ~784 mol, ~7.0e-17 g, ~41% of Karr's full RNA-class "
    "total of 1.72e-16 g). Karr's State_Rna spans nascent / processed / "
    "aminoacylated / bound / misfolded / damaged forms across "
    "cytosol+membrane+terminal-organelle for all 4820 entries; chassis "
    "collapses these into mature-only at gene level. Predicted/target "
    "ratio ~0.41 < tol_rel_min=0.50.  Pinned xfail until M2 v2 lands "
    "per-form RNA tracking.",
    strict=True,
)
def test_p10a_dry_mass_rna_g(m1_model, m2_model, m3_model, targets) -> None:
    spec = targets["p10a_dry_mass_rna_g"]
    m = ph.measure_dry_mass_rna_g(m1_model, m2_model, m3_model)
    ratio = m.predicted / m.target if m.target > 0 else float("inf")
    assert spec["tol_rel_min"] <= ratio <= spec["tol_rel_max"], (
        f"p10a RNA dry mass pred={m.predicted:.4e} g target={m.target:.4e} g "
        f"ratio={ratio:.4f} outside [{spec['tol_rel_min']}, {spec['tol_rel_max']}] "
        f"(n_rnas_with_mw={m.extra['n_rnas_with_mw']}, "
        f"n_rnas_total={m.extra['n_rnas_total']})"
    )


def test_p10b_dry_mass_protein_monomer_g(m1_model, m2_model, m3_model, targets) -> None:
    spec = targets["p10b_dry_mass_protein_monomer_g"]
    m = ph.measure_dry_mass_protein_monomer_g(m1_model, m2_model, m3_model)
    ratio = m.predicted / m.target if m.target > 0 else float("inf")
    assert spec["tol_rel_min"] <= ratio <= spec["tol_rel_max"], (
        f"p10b protein monomer dry mass pred={m.predicted:.4e} g "
        f"target={m.target:.4e} g ratio={ratio:.4f} outside "
        f"[{spec['tol_rel_min']}, {spec['tol_rel_max']}] "
        f"(n_proteins_with_mw={m.extra['n_proteins_with_mw']}, "
        f"n_proteins_total={m.extra['n_proteins_total']})"
    )


@pytest.mark.xfail(
    reason="AGGREGATE STRUCTURAL GAP: residual bucket = cellDry - RNA - "
    "ProteinMonomer (~2.68e-15 g, ~68% of cellDry) covers every class "
    "the archive does NOT expose as a clean per-class subtotal: "
    "ProteinComplex (ribosomes, RNAP, replisome), DNA chromosome, "
    "lipid membrane, polysaccharide cell-wall, true substrate pool at "
    "Karr-snapshot counts.  Chassis predicted = breakdown.substrate_mass_g "
    "(placeholder substrate counts 1.0 -> ~1e-19 g) << target.  Pinned "
    "xfail until D.2 + M5 + substrate-pool init land.",
    strict=True,
)
def test_p10c_dry_mass_other_residual_g(m1_model, m2_model, m3_model, targets) -> None:
    spec = targets["p10c_dry_mass_other_residual_g"]
    m = ph.measure_dry_mass_other_residual_g(m1_model, m2_model, m3_model)
    ratio = m.predicted / m.target if m.target > 0 else float("inf")
    assert spec["tol_rel_min"] <= ratio <= spec["tol_rel_max"], (
        f"p10c other-residual dry mass pred={m.predicted:.4e} g "
        f"target={m.target:.4e} g ratio={ratio:.4f} outside "
        f"[{spec['tol_rel_min']}, {spec['tol_rel_max']}] "
        f"(cell_dry_total={m.extra['cell_dry_total_g']:.4e}, "
        f"rna_target={m.extra['rna_target_g']:.4e}, "
        f"prot_monomer_target={m.extra['protein_monomer_target_g']:.4e})"
    )


def test_p10c_other_residual_target_consistency(m1_model, targets) -> None:
    """Anti-fabrication guard: prove the JSON p10a/p10b/p10c targets are
    archive-derived and consistent with cell_dry_total_mass_g (= p10).

    Asserts:
      * p10a target == stored_runtime.rna_wt_total_g (exactly).
      * p10b target == sum(proteins_targeted__counts x molecularWeights) / N_A
        recomputed live from data/karr_archive/karr_archive.npz.
      * p10c target == p10_total - p10a - p10b (within float tolerance).

    A drift here means somebody hand-edited a target without re-running
    the archive derivation; the test fails loudly and points at the
    offending field.
    """
    p10 = targets["p10_cell_dry_mass_g"]["target"]
    p10a = targets["p10a_dry_mass_rna_g"]["target"]
    p10b = targets["p10b_dry_mass_protein_monomer_g"]["target"]
    p10c = targets["p10c_dry_mass_other_residual_g"]["target"]

    rna_stored = float(m1_model.stored_runtime["rna_wt_total_g"])
    assert p10a == rna_stored, (
        f"p10a target {p10a!r} != stored_runtime.rna_wt_total_g {rna_stored!r}"
    )

    derived_prot = ph._karr_archive_protein_monomer_dry_mass_g()
    assert abs(p10b - derived_prot) < 1e-25, (
        f"p10b target {p10b!r} != archive-derived protein monomer "
        f"{derived_prot!r} (diff={p10b - derived_prot:.3e})"
    )

    expected_p10c = p10 - p10a - p10b
    assert abs(p10c - expected_p10c) < 1e-22, (
        f"p10c target {p10c!r} != p10 - p10a - p10b = {expected_p10c!r} "
        f"(diff={p10c - expected_p10c:.3e})"
    )
