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
  bounds shrink as pools drain.

  Phase C.2 added the read-side share: M1 publishes the current
  cytosol pool counts for the 24 demand-side substrates into a shared
  ``m1_pools`` store after every tick (set updater, M1 sole writer).
  Phase C.3 added the M2/M3 throttle that consumes that store.

  Phase C.4 (opt-in, ``enable_pool_replenishment=True``) closes the
  chassis loop with a CALIBRATED-TO-STEADY-STATE source term: at the
  end of every tick M1 adds a fixed per-second replenishment to its
  internal cytosol slice for each demand key.  The replenishment rate
  must be supplied by the caller (composer) via ``baseline_demand_per_s``
  - typically the un-throttled M2/M3 consumption rate, so under f=1
  drain == replenish and the pool stays at Karr's snapshot SS.
  Under throttle-induced starvation drain falls below replenish and
  pools recover, allowing the throttle to unfreeze on subsequent ticks.

  This is NOT LP-derived: standard FBA enforces ``S @ v == 0`` for
  internal substrates by construction, so net production is always
  zero from the LP itself.  Real LP-derived replenishment requires the
  compartmented (1686, 645) stoichiometry + a unit conversion path
  (mmol/gDW/h <-> molecules/s); both are deferred to Phase D.

  Honest scope (still):

    - Replenishment is uncapped; under prolonged f<<1 the pool grows
      unboundedly (documented heuristic, not a true conservation law).
    - Replenishment is decoupled from FBA growth_per_s; if growth
      crashes, replenishment does not slow.  Phase D will change this.
    - Enzyme counts are FROZEN at the snapshot (104,) vector.
    - Rule 6 (protein-bound zeroing) is not run.
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
        "enable_pool_replenishment": False,
        "baseline_demand_per_s": None,
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
        self.enable_pool_replenishment: bool = bool(
            self.parameters["enable_pool_replenishment"]
        )
        self._sub_state: np.ndarray | None = None
        self._enz_state: np.ndarray | None = None
        self._prev_shared: dict[str, float] | None = None
        self._dyn: cfb.M1DynamicsInputs | None = None
        self._sub_id_to_idx: dict[str, int] | None = None
        self._fba_reaction_bounds: np.ndarray | None = None
        self._demand_idx_pairs: list[tuple[str, int]] = []
        self._baseline_demand_per_s: dict[str, float] | None = None

        if self.enable_pool_replenishment and not self.dynamic_bounds:
            raise ValueError(
                "enable_pool_replenishment=True requires dynamic_bounds=True "
                "(replenishment writes to the dynamic-bounds internal state)"
            )

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

            if self.enable_pool_replenishment:
                bd = self.parameters["baseline_demand_per_s"]
                if bd is None:
                    raise ValueError(
                        "enable_pool_replenishment=True requires "
                        "baseline_demand_per_s={sid: rate_per_s, ...} "
                        "(typically built by the composer from the actual "
                        "attached M2/M3 models at synth_scale=1.0)"
                    )
                missing = [
                    sid for sid, _ in self._demand_idx_pairs if sid not in bd
                ]
                if missing:
                    raise ValueError(
                        f"baseline_demand_per_s missing demand keys: {missing}"
                    )
                self._baseline_demand_per_s = {
                    sid: float(bd[sid]) for sid, _ in self._demand_idx_pairs
                }
                for sid, rate in self._baseline_demand_per_s.items():
                    if not np.isfinite(rate) or rate < 0.0:
                        raise ValueError(
                            f"baseline_demand_per_s[{sid}]={rate} must be "
                            f"finite and non-negative")

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
            schema["m1_pools"] = self._m1_pools_schema()
        return schema

    def _m1_pools_schema(self) -> dict[str, Any]:
        """Authoritative schema for the shared ``m1_pools`` store.

        M1 declares all 24 demand keys with the snapshot cytosol value
        as the default.  M2/M3 may declare a subset (the substrates they
        actually consume) with matching leaf settings; Vivarium merges
        same-path subset schemas across processes.
        """
        assert self._sub_state is not None
        return {
            sid: {
                "_default": float(self._sub_state[idx, _CYTOSOL_COMPARTMENT_0]),
                "_updater": "set",
                "_emit": True,
            }
            for sid, idx in self._demand_idx_pairs
        }

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

        # Phase C.4 — calibrated source-term replenishment (opt-in).
        # Order: drain (above) -> solve FBA (above) -> replenish (here)
        # -> publish diagnostics + m1_pools (below).  Means FBA bounds
        # this tick saw the post-drain pool, while m1_pools published
        # this tick reflects post-replenish — explicitly documented.
        if self.enable_pool_replenishment:
            assert self._baseline_demand_per_s is not None
            for sid, idx in self._demand_idx_pairs:
                self._sub_state[idx, _CYTOSOL_COMPARTMENT_0] += (
                    self._baseline_demand_per_s[sid] * timestep
                )

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
        m1_pools_update: dict[str, float] = {}
        for sid, idx in self._demand_idx_pairs:
            cur_cyt = float(self._sub_state[idx, _CYTOSOL_COMPARTMENT_0])
            diag[f"cyt_{sid}"] = cur_cyt
            m1_pools_update[sid] = cur_cyt

        return {
            "metabolic_reaction": {
                "fluxs": flux_update,
                "growth_per_s": float(info["biomass_flux_per_s"]),
                "growth_per_h": float(info["biomass_flux_per_h"]),
            },
            "m1_dynamic_diagnostics": diag,
            "m1_pools": m1_pools_update,
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
        topology["m1_karr"]["m1_pools"] = ("m1_pools",)

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
        initial_state["m1_pools"] = {
            sid: float(proc._sub_state[idx, _CYTOSOL_COMPARTMENT_0])
            for sid, idx in proc._demand_idx_pairs
        }

    engine = Engine(
        processes=processes,
        topology=topology,
        initial_state=initial_state,
        emit_step=emit_step_s or time_step_s,
    )
    return engine
