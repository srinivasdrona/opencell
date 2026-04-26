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
    its initial state (which the composer populated from m2.expression),
    and compare the SUM to m2.expression.sum() computed independently.
    Catches bugs where the composer drops/duplicates genes or mis-maps
    indices. NOT a biology prediction -- becomes one once M2 v2 lands."""
    engine = _run_engine_for(0)
    state = engine.state.get_value()
    chassis_total = float(sum(state["rna"]["counts"].values()))
    model_total = float(m2.expression[:, condition].sum())
    return PhenotypeMeasurement(
        name="p5_mrna_total_chassis_wiring",
        predicted=chassis_total,
        target=model_total,
        unit="molecules",
        extra={
            "n_genes_in_chassis": len(state["rna"]["counts"]),
            "n_genes_in_model": int(m2.expression.shape[0]),
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
]
