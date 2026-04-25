"""Vivarium Process wrapper for Karr-native M1 metabolism.

Two operating modes (selected by the ``dynamic_bounds`` parameter):

* **Static (default)** — solves Karr's fitted FBA exactly each tick using
  the snapshot bounds from the fixture.  Schema and emitted timeseries
  are byte-for-byte unchanged from the original M0 wrapper.  Preserves
  back-compat with the central-dogma demo and the existing 502-test
  baseline.

* **Dynamic (Phase B, opt-in)** — recomputes Karr's
  :func:`opencell.m1.calc_flux_bounds.compute_bounds` (rules 1-5) each
  tick from a private compartmented substrate state ``(585, 3)``.  M2
  and M3 demand entering the shared ``substrates`` store is *read*
  into the cytosol slice of that internal state every tick, so flux
  bounds shrink as pools drain — the first piece of real intra-cell
  feedback.  Honest scope:

    - Demand coupling is ONE-WAY: M2/M3 write to the shared store and
      M1 reads.  M1 does NOT mirror its FBA flux back to the shared
      store (S @ v == 0 by LP construction so a write-back would be a
      no-op anyway), and M2/M3 still do not read substrate counts.
    - Enzyme counts are FROZEN at the snapshot (104,) vector; dynamic
      enzyme counts from M3 protein counts are Phase C.
    - Rule 6 (protein-bound zeroing) is Phase C; we only run rules 1-5.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
from vivarium.core.process import Process

from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1 import karr_metabolism as km


# Substrate WCM IDs that the central-dogma chassis writes into the
# shared `substrates` store and that M1 must drain into its internal
# cytosol slice every tick.  Pulled from the Karr 585-ID space at runtime
# so we never hard-code the set; ``AA_total`` is intentionally NOT here
# (it is M3's placeholder bulk key, not in Karr's ID space).
_KARR_DEMAND_KEYS: tuple[str, ...] = (
    "ATP", "CTP", "GTP", "UTP",
    "ALA", "ARG", "ASN", "ASP", "CYS",
    "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO",
    "SER", "THR", "TRP", "TYR", "VAL",
)
_CYTOSOL_COMPARTMENT_0 = 0


class KarrMetabolismProcess(Process):
    """1-second FBA tick of Karr's fitted snapshot.

    See module docstring for static vs dynamic bound semantics.
    """

    name = "karr_metabolism"
    defaults: dict[str, Any] = {
        "model": None,
        "time_step": 1.0,
        "big": km.DEFAULT_BIG,
        "use_full_objective": True,
        "dynamic_bounds": False,
        "dynamics_inputs": None,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        model = self.parameters.get("model")
        if model is None:
            model = km.load_default()
        self.model: km.KarrMetabolismModel = model
        self._rxn_ids = self.model.rxn_wcm_ids_645
        self._sub_ids = self.model.raw["ids"]["substrate_wcm_585"]

        self.dynamic_bounds: bool = bool(self.parameters["dynamic_bounds"])
        self._sub_state: np.ndarray | None = None
        self._enz_state: np.ndarray | None = None
        self._prev_shared: dict[str, float] | None = None
        self._dyn: cfb.M1DynamicsInputs | None = None
        self._sub_id_to_idx: dict[str, int] | None = None
        self._fba_reaction_bounds: np.ndarray | None = None
        self._demand_idx_pairs: list[tuple[str, int]] = []

        if self.dynamic_bounds:
            dyn = self.parameters.get("dynamics_inputs")
            if dyn is None:
                dyn = cfb.load_default_dynamics()
            self._dyn = dyn
            self._sub_state = dyn.substrates_snapshot.copy()
            self._enz_state = dyn.enzymes_snapshot.copy()
            self._sub_id_to_idx = {sid: i for i, sid in enumerate(self._sub_ids)}
            self._fba_reaction_bounds = np.column_stack([
                self.model.lb, self.model.ub,
            ]).astype(float)
            self._demand_idx_pairs = [
                (sid, self._sub_id_to_idx[sid])
                for sid in _KARR_DEMAND_KEYS
                if sid in self._sub_id_to_idx
            ]
            # Initialise tracker against the schema default (1.0) rather
            # than first-observed shared state, so the first tick already
            # picks up the M2/M3 deltas accumulated during the first
            # boundary application.
            self._prev_shared = {sid: 1.0 for sid in self._sub_ids}

    # ------------------------------------------------------------------
    def ports_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {
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
                sid: {
                    "_default": 1.0,
                    "_updater": "accumulate",
                    "_emit": False,
                }
                for sid in self._sub_ids
            },
        }
        if self.dynamic_bounds:
            schema["m1_dynamic_diagnostics"] = self._diagnostics_schema()
        return schema

    def _diagnostics_schema(self) -> dict[str, Any]:
        keys = [
            "growth_per_s",
            "biomass_flux_per_s",
            "n_active_bounds_changed",
            "min_lb",
            "max_ub",
        ]
        for sid, _ in self._demand_idx_pairs:
            keys.append(f"cyt_{sid}")
        return {
            k: {"_default": 0.0, "_updater": "set", "_emit": True}
            for k in keys
        }

    # ------------------------------------------------------------------
    def next_update(self, timestep: float, states: dict) -> dict:
        if not self.dynamic_bounds:
            return self._static_update(timestep, states)
        return self._dynamic_update(timestep, states)

    def _static_update(self, timestep: float, states: dict) -> dict:
        v, info = km.solve_fba(
            self.model,
            use_full_objective=self.parameters["use_full_objective"],
            sense="max",
            big=self.parameters["big"],
        )
        flux_update = {rid: 0.0 for rid in self._rxn_ids}
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

    def _dynamic_update(self, timestep: float, states: dict) -> dict:
        assert self._dyn is not None
        assert self._sub_state is not None
        assert self._enz_state is not None
        assert self._fba_reaction_bounds is not None

        shared = states.get("substrates", {})
        for sid, idx in self._demand_idx_pairs:
            cur = float(shared.get(sid, self._prev_shared[sid]))
            delta = cur - self._prev_shared[sid]
            self._prev_shared[sid] = cur
            new_val = self._sub_state[idx, _CYTOSOL_COMPARTMENT_0] + delta
            self._sub_state[idx, _CYTOSOL_COMPARTMENT_0] = max(0.0, new_val)

        bounds = cfb.compute_bounds(
            substrates=self._sub_state,
            enzymes=self._enz_state,
            cell_dry_mass=self._dyn.cell_dry_mass,
            step_size_sec=self._dyn.step_size_sec,
            catalysis=self.model.catalysis,
            enz_bounds=self.model.enz_bounds,
            fba_reaction_bounds=self._fba_reaction_bounds,
            dyn=self._dyn,
            apply_protein_bounds=False,
        )
        if not np.all(np.isfinite(bounds) | np.isinf(bounds)):
            raise RuntimeError("dynamic bounds contain NaN")
        if np.any(bounds[:, 0] > bounds[:, 1] + 1e-9):
            raise RuntimeError("dynamic bounds: lower > upper")

        v, info = km.solve_fba(
            self.model,
            use_full_objective=self.parameters["use_full_objective"],
            sense="max",
            big=self.parameters["big"],
            lb_override=bounds[:, 0],
            ub_override=bounds[:, 1],
        )

        flux_update = {rid: 0.0 for rid in self._rxn_ids}
        for col, rid in enumerate(self.model.fba_col_rxn_wcm):
            if rid is not None:
                flux_update[rid] = float(v[col])

        # Count bounds that differ from static fixture, NaN-safely
        # (both sides may be -inf/+inf where no rule applies).
        bnd_lb_diff = np.not_equal(bounds[:, 0], self.model.lb)
        bnd_ub_diff = np.not_equal(bounds[:, 1], self.model.ub)
        n_changed = int(bnd_lb_diff.sum() + bnd_ub_diff.sum())
        diag: dict[str, float] = {
            "growth_per_s": float(info["biomass_flux_per_s"]),
            "biomass_flux_per_s": float(info["biomass_flux_per_s"]),
            "n_active_bounds_changed": float(n_changed),
            "min_lb": float(np.min(bounds[:, 0][np.isfinite(bounds[:, 0])])
                            if np.any(np.isfinite(bounds[:, 0])) else 0.0),
            "max_ub": float(np.max(bounds[:, 1][np.isfinite(bounds[:, 1])])
                            if np.any(np.isfinite(bounds[:, 1])) else 0.0),
        }
        for sid, idx in self._demand_idx_pairs:
            diag[f"cyt_{sid}"] = float(self._sub_state[idx, _CYTOSOL_COMPARTMENT_0])

        return {
            "metabolic_reaction": {
                "fluxs": flux_update,
                "growth_per_s": float(info["biomass_flux_per_s"]),
                "growth_per_h": float(info["biomass_flux_per_h"]),
            },
            "m1_dynamic_diagnostics": diag,
        }


def build_karr_m1_engine(
    *,
    model: km.KarrMetabolismModel | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    dynamic_bounds: bool = False,
):
    """Build a Vivarium Engine running just M1 (Karr metabolism).

    This is the chassis-tick smoke harness.  No other processes -
    metabolism runs in vacuo.  Use to prove the chassis is healthy
    before composing M2..M7.
    """
    from vivarium.core.engine import Engine

    if model is None:
        model = km.load_default()

    proc = KarrMetabolismProcess({
        "model": model,
        "time_step": time_step_s,
        "dynamic_bounds": dynamic_bounds,
    })
    processes = {"m1_karr": proc}
    topology = {
        "m1_karr": {
            "metabolic_reaction": ("metabolic_reaction",),
            "substrates": ("substrates",),
        }
    }
    if dynamic_bounds:
        topology["m1_karr"]["m1_dynamic_diagnostics"] = (
            "m1_dynamic_diagnostics",
        )

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
    if dynamic_bounds:
        initial_state["m1_dynamic_diagnostics"] = {
            k: 0.0 for k in proc._diagnostics_schema()
        }

    engine = Engine(
        processes=processes,
        topology=topology,
        initial_state=initial_state,
        emit_step=emit_step_s or time_step_s,
    )
    return engine
