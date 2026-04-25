"""Vivarium Process wrapper for Karr-native M1 metabolism.

Wraps :class:`opencell.m1.karr_metabolism.KarrMetabolismModel` as a
1-second-tick Process so M1 plugs into the dynamic loop chassis
that M2..M7 will share.

Scope of THIS wrapper (deliberately narrow):
  * Solves Karr's fitted FBA exactly at each tick (snapshot-based;
    no calcFluxBounds re-derivation - that comes when we port Karr's
    MATLAB Metabolism.calcFluxBounds()).
  * Writes the 645-vec flux solution (keyed by reactionWholeCellModelID)
    and the scalar biomass flux per hour to the shared ``metabolic_reaction``
    store.
  * Reads ``substrates`` (a placeholder shared store keyed by
    substrateWholeCellModelID) but does NOT yet write substrate deltas -
    that requires the row->585->1686 metabolite-count mapping which is
    M2/integrator territory.  Documented as a known gap.

This is the 'chassis tick' proof: M1 runs inside Vivarium, every
second, deterministically, without crashing.  Future PRs add real
shared-state I/O.
"""
from __future__ import annotations

from typing import Any

from vivarium.core.process import Process

from opencell.m1 import karr_metabolism as km


class KarrMetabolismProcess(Process):
    """1-second FBA tick of Karr's fitted snapshot.

    Defaults follow Karr's WCM convention: ``time_step=1.0`` second,
    biomass-max objective, Karr's full 36-nonzero objective vector.
    """

    name = "karr_metabolism"
    defaults: dict[str, Any] = {
        "model": None,
        "time_step": 1.0,
        "big": km.DEFAULT_BIG,
        "use_full_objective": True,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        model = self.parameters.get("model")
        if model is None:
            model = km.load_default()
        self.model: km.KarrMetabolismModel = model
        self._rxn_ids = self.model.rxn_wcm_ids_645
        self._sub_ids = self.model.raw["ids"]["substrate_wcm_585"]

    def ports_schema(self) -> dict[str, Any]:
        return {
            "metabolic_reaction": {
                "fluxs": {
                    rid: {
                        "_default": float(self.model.fluxs_stored[i]),
                        "_updater": "set",
                        "_emit": True,
                    }
                    for i, rid in enumerate(self._rxn_ids)
                },
                "growth_per_s": {
                    "_default": float(self.model.stored_runtime["growth_per_s"]),
                    "_updater": "set",
                    "_emit": True,
                },
                "growth_per_h": {
                    "_default": float(self.model.stored_runtime["growth_per_h"]),
                    "_updater": "set",
                    "_emit": True,
                },
            },
            "substrates": {
                # Placeholder: read-only for now.  Default to 1.0 so the
                # store exists and other processes can write to it; M1
                # does NOT consume substrate counts in this snapshot
                # tick (Karr's calcFluxBounds() derivation is deferred).
                sid: {
                    "_default": 1.0,
                    "_updater": "accumulate",
                    "_emit": False,
                }
                for sid in self._sub_ids
            },
        }

    def next_update(self, timestep: float, states: dict) -> dict:
        # `timestep` is in seconds; Karr's FBA is per-cell-per-second so
        # the LP solution itself is a 1-s flux already.  If timestep != 1
        # the resulting Delta-substrate would scale linearly, but since
        # we don't yet write substrate deltas, timestep != 1 is a no-op.
        v, info = km.solve_fba(
            self.model,
            use_full_objective=self.parameters["use_full_objective"],
            sense="max",
            big=self.parameters["big"],
        )

        flux_update = {rid: 0.0 for rid in self._rxn_ids}
        # Map 504-vec FBA solution back into 645-vec flux store via the
        # per-FBA-column WCM IDs (only metabolicConversion cols carry one;
        # exchange cols write to nothing in this minimal chassis tick).
        for col, rid in enumerate(self.model.fba_col_rxn_wcm):
            if rid is not None:
                flux_update[rid] = float(v[col])

        return {
            "metabolic_reaction": {
                "fluxs": flux_update,
                "growth_per_s": float(info["biomass_flux_per_s"]),
                "growth_per_h": float(info["biomass_flux_per_h"]),
            },
        }


def build_karr_m1_engine(
    *,
    model: km.KarrMetabolismModel | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
):
    """Build a Vivarium Engine running just M1 (Karr metabolism).

    This is the chassis-tick smoke harness.  No other processes -
    metabolism runs in vacuo.  Use to prove the chassis is healthy
    before composing M2..M7.
    """
    from vivarium.core.engine import Engine

    if model is None:
        model = km.load_default()

    proc = KarrMetabolismProcess({"model": model, "time_step": time_step_s})
    processes = {"m1_karr": proc}
    topology = {
        "m1_karr": {
            "metabolic_reaction": ("metabolic_reaction",),
            "substrates": ("substrates",),
        }
    }

    rxn_ids = model.rxn_wcm_ids_645
    sub_ids = model.raw["ids"]["substrate_wcm_585"]
    initial_state: dict[str, Any] = {
        "metabolic_reaction": {
            "fluxs": {
                rid: float(model.fluxs_stored[i])
                for i, rid in enumerate(rxn_ids)
            },
            "growth_per_s": float(model.stored_runtime["growth_per_s"]),
            "growth_per_h": float(model.stored_runtime["growth_per_h"]),
        },
        "substrates": {sid: 1.0 for sid in sub_ids},
    }

    engine = Engine(
        processes=processes,
        topology=topology,
        initial_state=initial_state,
        emit_step=emit_step_s or time_step_s,
    )
    return engine
