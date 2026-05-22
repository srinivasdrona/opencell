"""Vivarium composer: M1 (Karr metabolism) + M2 (transcription) + M3 (translation).

This is the **chassis-composition proof**: M1, M2 and M3 tick together
inside a single Engine, share the ``substrates`` store, and run for
many seconds without crashing.

Topology (shared stores):
  * ``metabolic_reaction``  -- written by M1 only (645 fluxs + growth scalars)
  * ``substrates``          -- M1 declares all 585 substrate WCM IDs
                               (read-only placeholder, default 1.0);
                               M2 writes negative ATP/CTP/GTP/UTP deltas;
                               M3 writes per-AA negative deltas keyed by
                               the 20 standard amino-acid WCM IDs (these
                               IDs already live inside Karr's 585-substrate
                               vocabulary, so no extra placeholder key is
                               required).
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
from opencell.vivarium.karr_d2_stub import KarrD2StubProcess
from opencell.vivarium.karr_m1 import KarrMetabolismProcess
from opencell.vivarium.karr_m2 import KarrTranscriptionProcess
from opencell.vivarium.karr_m3 import KarrTranslationProcess


_M1_SUBSTRATE_DEFAULT = 1.0


def compute_baseline_demand_per_s(
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
    *,
    condition: int = 1,
) -> dict[str, float]:
    """Build the {sid: rate_per_s} map used by M1's pool-replenishment
    source term.

    Combines un-throttled M2 NTP demand (4 keys) and un-throttled M3
    per-AA demand (20 keys) at ``synth_scale=1.0``.  This is the rate
    at which M1 must produce each demand-side substrate to keep the
    Karr-snapshot pool flat under the actual M2/M3 models attached to
    the composer (so e.g. ``condition`` and custom models propagate).
    """
    ntp = tx.ntp_consumption_per_s(
        tx.calibrated_chassis_model(m2_model), condition=condition,
    )
    aa = tl.aa_consumption_per_s(m3_model)
    out: dict[str, float] = {
        s: float(ntp[s]) for s in ("ATP", "CTP", "GTP", "UTP")
    }
    for a in m3_model.aa_wcm_ids:
        out[a] = float(aa[a])
    return out


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
    rna_init = {g: float(m2_model.counts_mature[i, condition])
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
    dynamic_bounds: bool = False,
    enable_throttle: bool = False,
    enable_pool_replenishment: bool = False,
):
    """Build a Vivarium Engine running M1, M2 AND M3 in lockstep (1s tick).

    ``dynamic_bounds=True`` enables Phase B M1 dynamic-bounds mode:
    M1 reads M2/M3 NTP/AA demand from the shared ``substrates`` store
    into a private compartmented state, recomputes flux bounds via
    Karr's ``calcFluxBounds`` (rules 1-5) every tick, and emits a
    ``m1_dynamic_diagnostics`` port.

    ``enable_throttle=True`` (Phase C.3) wires the read side of the
    closed loop: M1 publishes its 24 demand-side cytosol pools into a
    shared ``m1_pools`` store every tick, and M2/M3 read it to clamp
    their analytical-integrator synthesis scale ``f`` to the per-tick
    pool head-room.  Requires ``dynamic_bounds=True``.  Default off
    keeps the 528-test baseline trajectory unchanged.

    ``enable_pool_replenishment=True`` (Phase C.4) closes the chassis
    loop: at the end of every tick M1 adds a calibrated source term
    (un-throttled M2/M3 demand at this composer's ``condition`` /
    models) to its internal cytosol slice.  Under f=1 drain == replenish
    so pools stay at Karr's snapshot SS; under throttle-induced
    starvation pools recover and the throttle eventually unfreezes.
    Requires ``dynamic_bounds=True``.  Default off keeps the prior
    pure-drain semantics intact.
    """
    from vivarium.core.engine import Engine

    if enable_throttle and not dynamic_bounds:
        raise ValueError(
            "enable_throttle=True requires dynamic_bounds=True "
            "(throttle reads m1_pools which only M1 dynamic mode publishes)"
        )
    if enable_pool_replenishment and not dynamic_bounds:
        raise ValueError(
            "enable_pool_replenishment=True requires dynamic_bounds=True"
        )

    if m1_model is None:
        m1_model = km.load_default()
    if m2_model is None:
        m2_model = tx.load_default()
    if m3_model is None:
        m3_model = tl.load_default()

    baseline_demand: dict[str, float] | None = None
    if enable_pool_replenishment:
        baseline_demand = compute_baseline_demand_per_s(
            m2_model, m3_model, condition=condition,
        )

    m1_proc = KarrMetabolismProcess({
        "model": m1_model,
        "time_step": time_step_s,
        "dynamic_bounds": dynamic_bounds,
        "enable_pool_replenishment": enable_pool_replenishment,
        "baseline_demand_per_s": baseline_demand,
    })
    m2_proc = KarrTranscriptionProcess({
        "model": m2_model,
        "time_step": time_step_s,
        "condition": condition,
        "substrate_default": _M1_SUBSTRATE_DEFAULT,
        "enable_throttle": enable_throttle,
    })
    m3_proc = KarrTranslationProcess({
        "model": m3_model,
        "time_step": time_step_s,
        "substrate_default": _M1_SUBSTRATE_DEFAULT,
        "enable_throttle": enable_throttle,
    })
    d2_proc = KarrD2StubProcess()

    rxn_ids = m1_model.rxn_wcm_ids_645
    sub_ids = m1_model.raw["ids"]["substrate_wcm_585"]
    rna_init = {g: float(m2_model.counts_mature[i, condition])
                for i, g in enumerate(m2_model.gene_wcm_ids)}
    prot_init = {p: float(m3_model.counts_mature[i])
                 for i, p in enumerate(m3_model.protein_wcm_ids)}

    initial_substrates: dict[str, float] = {
        sid: _M1_SUBSTRATE_DEFAULT for sid in sub_ids
    }
    # M3 now writes per-AA deltas using IDs that are already in M1's 585
    # substrate vocabulary; no extra placeholder key required.

    m1_topo = {
        "metabolic_reaction": ("metabolic_reaction",),
        "substrates": ("substrates",),
    }
    m2_topo: dict[str, tuple[str, ...]] = {
        "rna": ("rna",),
        "substrates": ("substrates",),
    }
    m3_topo: dict[str, tuple[str, ...]] = {
        "protein": ("protein",),
        "substrates": ("substrates",),
    }
    d2_topo: dict[str, tuple[str, ...]] = {
        "complex": ("complex",),
    }
    if dynamic_bounds:
        m1_topo["m1_dynamic_diagnostics"] = ("m1_dynamic_diagnostics",)
        m1_topo["m1_pools"] = ("m1_pools",)
    if enable_throttle:
        m2_topo["m1_pools"] = ("m1_pools",)
        m3_topo["m1_pools"] = ("m1_pools",)

    initial_state: dict[str, Any] = {
        "metabolic_reaction": {
            "fluxs": {rid: float(m1_model.fluxs_stored[i])
                      for i, rid in enumerate(rxn_ids)},
            "growth_per_s": float(m1_model.stored_runtime["growth_per_s"]),
            "growth_per_h": float(m1_model.stored_runtime["growth_per_h"]),
        },
        "substrates": initial_substrates,
        "rna": {"counts": rna_init},
        "protein": {"counts": prot_init},
        "complex": {
            "counts": {
                wid: float(d2_proc._complex_counts_schema[wid]["_default"])
                for wid in d2_proc.d2_owned_wids
            },
        },
    }
    if dynamic_bounds:
        initial_state["m1_dynamic_diagnostics"] = {
            k: 0.0 for k in m1_proc._diagnostics_schema()
        }
        from opencell.vivarium.karr_m1 import _CYTOSOL_COMPARTMENT_0
        initial_state["m1_pools"] = {
            sid: float(m1_proc._sub_state[idx, _CYTOSOL_COMPARTMENT_0])
            for sid, idx in m1_proc._demand_idx_pairs
        }

    engine = Engine(
        processes={
            "m1_karr": m1_proc,
            "m2_karr": m2_proc,
            "m3_karr": m3_proc,
            "d2_stub": d2_proc,
        },
        topology={
            "m1_karr": m1_topo,
            "m2_karr": m2_topo,
            "m3_karr": m3_topo,
            "d2_stub": d2_topo,
        },
        initial_state=initial_state,
        emit_step=emit_step_s or time_step_s,
    )
    return engine


__all__ = [
    "build_karr_m1_m2_engine",
    "build_karr_m1_m2_m3_engine",
    "compute_baseline_demand_per_s",
]

