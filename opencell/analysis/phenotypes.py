"""Phase E phenotype extractors.

Pure functions that take chassis state / models and compute one
phenotype value. Used by the validation harness in tests/phaseE/.

Each extractor returns a single float plus optional metadata (units,
provenance) so the harness can render a uniform report.

Categories:
  fba_prediction    -- predicted by M1 LP; non-circular vs Karr stored.
  chassis_invariant -- round-trip / stability checks; circular today,
                       become real once M2/M3 v2 mechanics land.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl


@dataclass(frozen=True)
class PhenotypeMeasurement:
    """Result of one extractor: (value, target, status_message)."""
    name: str
    predicted: float
    target: float | None
    unit: str
    extra: dict[str, Any]


# ---------- FBA prediction phenotypes ----------

def measure_growth_per_s(m1: km.KarrMetabolismModel) -> PhenotypeMeasurement:
    v, info = km.solve_fba(m1)
    return PhenotypeMeasurement(
        name="p1_growth_per_s",
        predicted=float(info["biomass_flux_per_s"]),
        target=float(m1.stored_runtime["growth_per_s"]),
        unit="1/s",
        extra={"objective_value": info["objective_value"], "n_nonzero": info["n_nonzero"]},
    )


def measure_doubling_time_h(m1: km.KarrMetabolismModel) -> PhenotypeMeasurement:
    v, info = km.solve_fba(m1)
    g = info["biomass_flux_per_s"]
    pred_h = (math.log(2) / g / 3600.0) if g > 0 else float("inf")
    return PhenotypeMeasurement(
        name="p2_doubling_time_h",
        predicted=pred_h,
        target=float(m1.stored_runtime["doublingTime_h"]),
        unit="h",
        extra={"growth_per_s": g},
    )


def measure_fba_oracle_median_log2(m1: km.KarrMetabolismModel) -> PhenotypeMeasurement:
    v, _ = km.solve_fba(m1)
    rows = km.per_reaction_comparison(m1, v, nonzero_only=False)
    log2_abs = []
    for r in rows:
        p, k = r["predicted"], r["karr_stored"]
        if p == 0 or k == 0 or not math.isfinite(p) or not math.isfinite(k):
            continue
        log2_abs.append(abs(math.log2(abs(p) / abs(k))))
    median = float(np.median(log2_abs)) if log2_abs else float("nan")
    return PhenotypeMeasurement(
        name="p3_fba_oracle_median_log2_ratio",
        predicted=median,
        target=0.0,
        unit="log2_ratio",
        extra={"n_compared": len(log2_abs), "n_total_rxns": len(rows)},
    )


def measure_glucose_uptake(m1: km.KarrMetabolismModel) -> PhenotypeMeasurement:
    v, _ = km.solve_fba(m1)
    glc_col = m1.fba_col_for_wcm_id("TX_GLCPTS")
    if glc_col is None:
        raise RuntimeError("TX_GLCPTS not in FBA col mapping")
    pred = float(v[glc_col])
    i_full = m1.reaction_wcm_id_to_645_index("TX_GLCPTS")
    stored = float(m1.fluxs_stored[i_full])
    return PhenotypeMeasurement(
        name="p4_glucose_uptake_TX_GLCPTS",
        predicted=pred,
        target=stored,
        unit="molecules_per_s",
        extra={"fba_col": glc_col, "rxn_645_idx": i_full},
    )


# ---------- chassis composition invariants ----------

def _run_engine_for(horizon_s: int):
    """Helper: build chassis engine and run for horizon_s; return engine."""
    from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine
    engine = build_karr_m1_m2_m3_engine(time_step_s=1.0, emit_step_s=1.0)
    if horizon_s > 0:
        engine.update(horizon_s)
    return engine


def measure_mrna_total_chassis_wiring(
    m2: tx.KarrTranscriptionModel, condition: int = 1,
) -> PhenotypeMeasurement:
    """Wiring fidelity: build the chassis engine, read mRNA counts from
    its initial state (which the composer populates from
    m2.counts_mature -- Karr State_Rna mature cytosol counts), and
    compare the SUM to m2.counts_mature[:, condition].sum() computed
    independently.  Catches bugs where the composer drops/duplicates
    genes or mis-maps indices. NOT a biology prediction -- becomes one
    once M2 v2 lands.

    ``counts_mature`` is per-condition (low/mean/high) since the
    m2-per-condition-snapshots fixture; this measurement compares the
    ``condition`` column against the chassis state populated at the
    same condition by ``build_karr_m1_m2_m3_engine``."""
    engine = _run_engine_for(0)
    state = engine.state.get_value()
    chassis_total = float(sum(state["rna"]["counts"].values()))
    target_col = m2.counts_mature[:, condition]
    model_total = float(target_col.sum())
    return PhenotypeMeasurement(
        name="p5_mrna_total_chassis_wiring",
        predicted=chassis_total,
        target=model_total,
        unit="molecules",
        extra={
            "n_genes_in_chassis": len(state["rna"]["counts"]),
            "n_genes_in_model": int(target_col.shape[0]),
            "condition": condition,
        },
    )


def measure_protein_total_chassis_wiring(
    m3: tl.KarrTranslationModel,
) -> PhenotypeMeasurement:
    """Wiring fidelity for M3: same shape as p5."""
    engine = _run_engine_for(0)
    state = engine.state.get_value()
    chassis_total = float(sum(state["protein"]["counts"].values()))
    model_total = float(m3.counts_mature.sum())
    return PhenotypeMeasurement(
        name="p6_protein_total_chassis_wiring",
        predicted=chassis_total,
        target=model_total,
        unit="molecules",
        extra={
            "n_proteins_in_chassis": len(state["protein"]["counts"]),
            "n_proteins_in_model": int(m3.counts_mature.shape[0]),
        },
    )


def measure_mrna_stability(horizon_s: int = 20) -> PhenotypeMeasurement:
    """Run M1+M2+M3 chassis for `horizon_s` seconds at default config and
    measure relative drift in total mRNA count."""
    from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine
    engine = build_karr_m1_m2_m3_engine(time_step_s=1.0, emit_step_s=1.0)
    engine.update(horizon_s)
    ts = engine.emitter.get_timeseries()
    rna_counts = ts["rna"]["counts"]  # dict gene -> [vals over time]
    total = np.array([sum(vals[t] for vals in rna_counts.values())
                      for t in range(len(next(iter(rna_counts.values()))))])
    drift = float(abs(total[-1] - total[0]) / total[0]) if total[0] > 0 else float("inf")
    return PhenotypeMeasurement(
        name="p7_mrna_stability_over_20s",
        predicted=drift,
        target=0.0,
        unit="fraction",
        extra={
            "horizon_s": horizon_s,
            "n_emit_steps": len(total),
            "total_t0": float(total[0]),
            "total_tN": float(total[-1]),
        },
    )


def measure_aa_pool_stability(horizon_s: int = 20) -> PhenotypeMeasurement:
    """Phase E phenotype #14: per-AA cytosol pool stability.

    Build the chassis with the full Phase C closed loop (dynamic
    bounds + throttle + calibrated pool replenishment), seed each of
    the 20 AA pools at Karr's snapshot SS, run for ``horizon_s``, and
    measure the maximum |delta_pool|/pool over the 20 amino acids.

    Under the calibrated replenishment, M3 drain ~= M1 source so pools
    should hold at SS to within numerical/throttle noise.  This exercises
    the M1 read-back, M3 per-AA delta write, M1 pool-replenishment
    source, and the throttle interlock together.

    A failing test here flags either (a) M1/M3 stoichiometric mismatch,
    (b) replenishment-rate calibration drift relative to drain, or
    (c) throttle clamping the synthesis below SS.
    """
    from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine
    from opencell.m3.translation import AA_WCM_IDS

    engine = build_karr_m1_m2_m3_engine(
        time_step_s=1.0, emit_step_s=1.0,
        dynamic_bounds=True,
        enable_throttle=True,
        enable_pool_replenishment=True,
    )
    init = dict(engine.state.get_value()["m1_pools"])
    engine.update(horizon_s)
    final = dict(engine.state.get_value()["m1_pools"])

    drifts: dict[str, float] = {}
    for aa in AA_WCM_IDS:
        i = float(init[aa])
        f = float(final[aa])
        drifts[aa] = abs(f - i) / i if i > 0 else float("inf")
    max_drift = max(drifts.values())
    worst_aa = max(drifts, key=lambda k: drifts[k])
    return PhenotypeMeasurement(
        name="p9_aa_pool_stability_over_20s",
        predicted=max_drift,
        target=0.0,
        unit="fraction",
        extra={
            "horizon_s": horizon_s,
            "n_aa": len(drifts),
            "worst_aa": worst_aa,
            "worst_drift": max_drift,
            "drift_by_aa": drifts,
            "init_pool_by_aa": {aa: float(init[aa]) for aa in AA_WCM_IDS},
        },
    )


def measure_protein_stability(horizon_s: int = 20) -> PhenotypeMeasurement:
    from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine
    engine = build_karr_m1_m2_m3_engine(time_step_s=1.0, emit_step_s=1.0)
    engine.update(horizon_s)
    ts = engine.emitter.get_timeseries()
    prot_counts = ts["protein"]["counts"]
    total = np.array([sum(vals[t] for vals in prot_counts.values())
                      for t in range(len(next(iter(prot_counts.values()))))])
    drift = float(abs(total[-1] - total[0]) / total[0]) if total[0] > 0 else float("inf")
    return PhenotypeMeasurement(
        name="p8_protein_stability_over_20s",
        predicted=drift,
        target=0.0,
        unit="fraction",
        extra={
            "horizon_s": horizon_s,
            "n_emit_steps": len(total),
            "total_t0": float(total[0]),
            "total_tN": float(total[-1]),
        },
    )


def _build_chassis_mass_breakdown(
    m1: km.KarrMetabolismModel,
    m2: tx.KarrTranscriptionModel,
    m3: tl.KarrTranslationModel,
):
    """Helper: build the Phase C closed-loop chassis at t=0 and return
    the per-class CellMassBreakdown.  Centralised so p10/p10a/p10b/p10c
    extractors share one engine-construction code path.
    """
    from opencell.analysis.cell_mass import compute_cell_mass
    from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine

    engine = build_karr_m1_m2_m3_engine(
        time_step_s=1.0, emit_step_s=1.0,
        dynamic_bounds=True,
        enable_throttle=True,
        enable_pool_replenishment=True,
    )
    state = engine.state.get_value()
    return compute_cell_mass(state, m1, m2, m3)


def _karr_archive_protein_monomer_dry_mass_g() -> float:
    """Derive Karr's State_ProteinMonomer total dry mass (grams) from
    the raw archive arrays.

    Formula:
        sum_p (sum_c proteins_targeted.counts[p, c]) * proteins_targeted.molecularWeights[p] / N_A

    Sums across all 4820 monomer rows (10 forms x 482 genes x 6 compartments
    flattened) and across all 6 compartment columns.  Karr's archive does
    NOT publish a State_Mass.proteinMonomerWt subtotal directly, so we
    recompute it from the same counts + MW arrays State_Mass.calcMass()
    consumes in MATLAB.

    No hard-coded value: the result is purely a function of the archive
    arrays, computed at runtime.
    """
    from pathlib import Path
    npz_path = (
        Path(__file__).resolve().parents[2]
        / "data" / "karr_archive" / "karr_archive.npz"
    )
    z = np.load(npz_path, allow_pickle=True)
    counts = np.asarray(z["proteins_targeted__counts"], dtype=np.float64)
    mw = np.asarray(z["proteins_targeted__molecularWeights"], dtype=np.float64)
    AVOGADRO = 6.02214076e23
    return float((counts.sum(axis=1) * mw).sum() / AVOGADRO)


def measure_cell_dry_mass(
    m1: km.KarrMetabolismModel,
    m2: tx.KarrTranscriptionModel,
    m3: tl.KarrTranslationModel,
) -> PhenotypeMeasurement:
    """Phase E phenotype #10 (total): chassis total cell dry mass vs
    Karr's State_Mass.cellDry total (~3.945e-15 g).

    Currently expected to FAIL on the aggregate -- the per-class
    sub-targets p10a/p10b/p10c provide a fine-grained breakdown
    (Phase E.1c partition) showing which classes the chassis already
    matches and which still need D.2/M5/substrate-pool-init to close.
    """
    breakdown = _build_chassis_mass_breakdown(m1, m2, m3)
    target = float(m1.stored_runtime["cell_dry_total_mass_g"])
    return PhenotypeMeasurement(
        name="p10_cell_dry_mass_g",
        predicted=breakdown.total_g,
        target=target,
        unit="g",
        extra={
            "substrate_mass_g": breakdown.substrate_mass_g,
            "rna_mass_g": breakdown.rna_mass_g,
            "protein_mass_g": breakdown.protein_mass_g,
            **breakdown.extra,
        },
    )


def measure_dry_mass_rna_g(
    m1: km.KarrMetabolismModel,
    m2: tx.KarrTranscriptionModel,
    m3: tl.KarrTranslationModel,
) -> PhenotypeMeasurement:
    """Phase E.1c sub-target p10a: chassis RNA-class dry mass vs
    Karr's State_Mass.rnaWt total (~1.715e-16 g, ~4.35% of cellDry).

    Target source: stored_runtime.rna_wt_total_g, which the m1 ingest
    pipeline derives from sim.state.State_Mass.dump.rnaWt (sum across
    6 compartments) and which equals
    sum(rnas_targeted.counts x rnas_targeted.molecularWeights) / N_A
    over the 2428-entry full RNA state matrix (verified at fixture-build
    time).  No hard-coded value.

    Chassis predicted: aggregator's RNA contribution -- breakdown.rna_mass_g
    over the M2 mature-only state (525 genes, ~784 mol post-E.1b m2-counts-fix).
    Because chassis tracks only mature mRNA forms (no nascent/processed/...,
    rRNA/tRNA aggregated under mature pseudo-counts), predicted is ~41% of
    Karr's total RNA mass at t=0 -- below the [0.50, 1.50] tolerance band
    -> xfail until M2 v2 / RNA-form coverage lands.
    """
    breakdown = _build_chassis_mass_breakdown(m1, m2, m3)
    target = float(m1.stored_runtime["rna_wt_total_g"])
    return PhenotypeMeasurement(
        name="p10a_dry_mass_rna_g",
        predicted=breakdown.rna_mass_g,
        target=target,
        unit="g",
        extra={
            "n_rnas_with_mw": breakdown.extra["n_rnas_with_mw"],
            "n_rnas_total": breakdown.extra["n_rnas_total"],
            "rna_da": breakdown.extra["rna_da"],
        },
    )


def measure_dry_mass_protein_monomer_g(
    m1: km.KarrMetabolismModel,
    m2: tx.KarrTranscriptionModel,
    m3: tl.KarrTranslationModel,
) -> PhenotypeMeasurement:
    """Phase E.1c sub-target p10b: chassis ProteinMonomer-class dry mass
    vs Karr's State_ProteinMonomer total (~1.093e-15 g, ~27.70% of cellDry).

    Target source: derived at runtime from the archive arrays
    proteins_targeted.counts (4820 x 6) x proteins_targeted.molecularWeights (4820)
    summed across all forms / compartments and divided by Avogadro
    (see _karr_archive_protein_monomer_dry_mass_g).  Karr's archive
    does not publish a State_Mass.proteinWt subtotal; we recompute it
    from the same arrays State_Mass.calcMass() consumes in MATLAB.
    No hard-coded value.

    Chassis predicted: aggregator's protein contribution --
    breakdown.protein_mass_g over m3.counts_mature (16177 mol).  At
    t=0 chassis hits ~70% of Karr's monomer total, well within the
    [0.50, 1.50] tolerance band -> green.  This is the largest Phase
    E.1c win: a previously-opaque xfail becomes a green sub-target.
    """
    breakdown = _build_chassis_mass_breakdown(m1, m2, m3)
    target = _karr_archive_protein_monomer_dry_mass_g()
    return PhenotypeMeasurement(
        name="p10b_dry_mass_protein_monomer_g",
        predicted=breakdown.protein_mass_g,
        target=target,
        unit="g",
        extra={
            "n_proteins_with_mw": breakdown.extra["n_proteins_with_mw"],
            "n_proteins_total": breakdown.extra["n_proteins_total"],
            "protein_da": breakdown.extra["protein_da"],
        },
    )


def measure_dry_mass_other_residual_g(
    m1: km.KarrMetabolismModel,
    m2: tx.KarrTranscriptionModel,
    m3: tl.KarrTranslationModel,
) -> PhenotypeMeasurement:
    """Phase E.1c sub-target p10c: 'everything else' dry mass --
    Karr's cellDry total minus the RNA and ProteinMonomer subtotals.

    Target = cell_dry_total_mass_g - rna_wt_total_g - protein_monomer_dry_mass_g
           ~= 2.68e-15 g, ~67.95% of cellDry.

    This residual aggregates every mass class the archive does NOT
    expose as a clean per-class subtotal:
      * State_ProteinComplex (ribosomes, RNAP, replisome, ATP synthase, ...)
      * State_Chromosome / DNA polymer
      * State_Metabolite intracellular pool (ions, NTPs, AAs, lipid IDs,
        polysaccharide IDs) at Karr's snapshot counts
      * lipid membrane mass, polysaccharide cell-wall mass

    Why a residual rather than per-class targets?  The archive's
    snapshot_substrates (3 x 585) is in MATLAB-FBA-input units (mixed
    counts/concentration-x-volume; cytosol H2O at 1.4e14 'count') --
    not directly interpretable as cellular molecule counts -- and there
    are no archive arrays for DNA, lipid, polysaccharide, or
    ProteinComplex counts/MW.  Until D.2 (complex assembly), M5 (DNA),
    and a substrate-pool-init pass land, this residual stays ~0 from
    the chassis side and the test is pinned xfail as a single bucket
    rather than fabricating per-class numbers.

    Chassis predicted: breakdown.substrate_mass_g (the only chassis
    contribution outside RNA / ProteinMonomer; today equals
    sum(placeholder=1.0 x substrate MW) / N_A ~= 1e-19 g).
    """
    breakdown = _build_chassis_mass_breakdown(m1, m2, m3)
    total = float(m1.stored_runtime["cell_dry_total_mass_g"])
    rna = float(m1.stored_runtime["rna_wt_total_g"])
    prot_mon = _karr_archive_protein_monomer_dry_mass_g()
    target = total - rna - prot_mon
    return PhenotypeMeasurement(
        name="p10c_dry_mass_other_residual_g",
        predicted=breakdown.substrate_mass_g,
        target=target,
        unit="g",
        extra={
            "cell_dry_total_g": total,
            "rna_target_g": rna,
            "protein_monomer_target_g": prot_mon,
            "n_substrates_with_mw": breakdown.extra["n_substrates_with_mw"],
            "n_substrates_total": breakdown.extra["n_substrates_total"],
        },
    )


__all__ = [
    "PhenotypeMeasurement",
    "measure_growth_per_s",
    "measure_doubling_time_h",
    "measure_fba_oracle_median_log2",
    "measure_glucose_uptake",
    "measure_mrna_total_chassis_wiring",
    "measure_protein_total_chassis_wiring",
    "measure_mrna_stability",
    "measure_protein_stability",
    "measure_aa_pool_stability",
    "measure_cell_dry_mass",
    "measure_dry_mass_rna_g",
    "measure_dry_mass_protein_monomer_g",
    "measure_dry_mass_other_residual_g",
]
