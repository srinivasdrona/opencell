"""Vivarium composer: M1 (Karr metabolism) + M2 (transcription) + M3 (translation).

This is the **chassis-composition proof**: M1, M2 and M3 tick together
inside a single Engine, share the ``substrates`` store, and run for
many seconds without crashing.

Topology (shared stores):
  * ``metabolic_reaction``  -- written by M1 only (645 fluxs + growth scalars)
  * ``substrates``          -- M1 declares all 585 substrate WCM IDs
                               (read-only placeholder, default 1.0);
                               M2 writes negative ATP/CTP/GTP/UTP deltas;
                               M3 writes a negative ``AA_total`` bulk delta.
                               All three processes share the same store.
  * ``rna``                 -- written by M2 only (525 RNA counts)
  * ``protein``             -- written by M3 only (482 protein counts)

Substrate writeback is still chassis-grade only:  M2/M3's per-tick
deltas are decremented from the placeholder counts; M1 does not yet
read them back into its FBA bounds (that requires Karr's
calcFluxBounds() port + the 585->1686 metabolite-x-compartment count
mapping, both deferred to the integrator pass).
"""
from __future__ import annotations

from typing import Any

from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.karr_m1 import KarrMetabolismProcess
from opencell.vivarium.karr_m2 import KarrTranscriptionProcess
from opencell.vivarium.karr_m3 import KarrTranslationProcess


_M1_SUBSTRATE_DEFAULT = 1.0


def build_karr_m1_m2_engine(
    *,
    m1_model: km.KarrMetabolismModel | None = None,
    m2_model: tx.KarrTranscriptionModel | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    condition: int = 1,
):
    """Build a Vivarium Engine running M1 and M2 in lockstep (1s tick)."""
    from vivarium.core.engine import Engine

    if m1_model is None:
        m1_model = km.load_default()
    if m2_model is None:
        m2_model = tx.load_default()

    m1_proc = KarrMetabolismProcess({
        "model": m1_model, "time_step": time_step_s,
    })
    m2_proc = KarrTranscriptionProcess({
        "model": m2_model,
        "time_step": time_step_s,
        "condition": condition,
        "substrate_default": _M1_SUBSTRATE_DEFAULT,
    })

    rxn_ids = m1_model.rxn_wcm_ids_645
    sub_ids = m1_model.raw["ids"]["substrate_wcm_585"]
    rna_init = {g: float(m2_model.expression[i, condition])
                for i, g in enumerate(m2_model.gene_wcm_ids)}

    engine = Engine(
        processes={"m1_karr": m1_proc, "m2_karr": m2_proc},
        topology={
            "m1_karr": {
                "metabolic_reaction": ("metabolic_reaction",),
                "substrates": ("substrates",),
            },
            "m2_karr": {
                "rna": ("rna",),
                "substrates": ("substrates",),
            },
        },
        initial_state={
            "metabolic_reaction": {
                "fluxs": {rid: float(m1_model.fluxs_stored[i])
                          for i, rid in enumerate(rxn_ids)},
                "growth_per_s": float(m1_model.stored_runtime["growth_per_s"]),
                "growth_per_h": float(m1_model.stored_runtime["growth_per_h"]),
            },
            "substrates": {sid: _M1_SUBSTRATE_DEFAULT for sid in sub_ids},
            "rna": {"counts": rna_init},
        },
        emit_step=emit_step_s or time_step_s,
    )
    return engine


def build_karr_m1_m2_m3_engine(
    *,
    m1_model: km.KarrMetabolismModel | None = None,
    m2_model: tx.KarrTranscriptionModel | None = None,
    m3_model: tl.KarrTranslationModel | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    condition: int = 1,
):
    """Build a Vivarium Engine running M1, M2 AND M3 in lockstep (1s tick)."""
    from vivarium.core.engine import Engine

    if m1_model is None:
        m1_model = km.load_default()
    if m2_model is None:
        m2_model = tx.load_default()
    if m3_model is None:
        m3_model = tl.load_default()

    m1_proc = KarrMetabolismProcess({
        "model": m1_model, "time_step": time_step_s,
    })
    m2_proc = KarrTranscriptionProcess({
        "model": m2_model,
        "time_step": time_step_s,
        "condition": condition,
        "substrate_default": _M1_SUBSTRATE_DEFAULT,
    })
    m3_proc = KarrTranslationProcess({
        "model": m3_model,
        "time_step": time_step_s,
        "substrate_default": _M1_SUBSTRATE_DEFAULT,
    })

    rxn_ids = m1_model.rxn_wcm_ids_645
    sub_ids = m1_model.raw["ids"]["substrate_wcm_585"]
    rna_init = {g: float(m2_model.expression[i, condition])
                for i, g in enumerate(m2_model.gene_wcm_ids)}
    prot_init = {p: float(m3_model.counts_mature[i])
                 for i, p in enumerate(m3_model.protein_wcm_ids)}

    initial_substrates: dict[str, float] = {
        sid: _M1_SUBSTRATE_DEFAULT for sid in sub_ids
    }
    # M3 declares an AA_total placeholder that's NOT in M1's 585; create it.
    initial_substrates["AA_total"] = _M1_SUBSTRATE_DEFAULT

    engine = Engine(
        processes={
            "m1_karr": m1_proc,
            "m2_karr": m2_proc,
            "m3_karr": m3_proc,
        },
        topology={
            "m1_karr": {
                "metabolic_reaction": ("metabolic_reaction",),
                "substrates": ("substrates",),
            },
            "m2_karr": {
                "rna": ("rna",),
                "substrates": ("substrates",),
            },
            "m3_karr": {
                "protein": ("protein",),
                "substrates": ("substrates",),
            },
        },
        initial_state={
            "metabolic_reaction": {
                "fluxs": {rid: float(m1_model.fluxs_stored[i])
                          for i, rid in enumerate(rxn_ids)},
                "growth_per_s": float(m1_model.stored_runtime["growth_per_s"]),
                "growth_per_h": float(m1_model.stored_runtime["growth_per_h"]),
            },
            "substrates": initial_substrates,
            "rna": {"counts": rna_init},
            "protein": {"counts": prot_init},
        },
        emit_step=emit_step_s or time_step_s,
    )
    return engine


__all__ = ["build_karr_m1_m2_engine", "build_karr_m1_m2_m3_engine"]

