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

import os
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
    "ATP",
    "CTP",
    "GTP",
    "UTP",
    "ALA",
    "ARG",
    "ASN",
    "ASP",
    "CYS",
    "GLN",
    "GLU",
    "GLY",
    "HIS",
    "ILE",
    "LEU",
    "LYS",
    "MET",
    "PHE",
    "PRO",
    "SER",
    "THR",
    "TRP",
    "TYR",
    "VAL",
)
_CYTOSOL_COMPARTMENT_0 = 0


def _read_env_bool(name: str) -> bool | None:
    val = os.getenv(name)
    if val is None:
        return None
    norm = val.strip().lower()
    if norm in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if norm in {"0", "false", "f", "no", "n", "off"}:
        return False
    return None


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
        "use_allocator_budget": False,
        "dynamics_inputs": None,
        "enable_lp_writeback": True,
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
        self.enzyme_wids = tuple(self.model.raw.get("ids", {}).get("enzyme_wcm_104", []))

        self.dynamic_bounds: bool = bool(self.parameters["dynamic_bounds"])
        self.use_allocator_budget: bool = bool(self.parameters["use_allocator_budget"])
        env_lp_writeback = _read_env_bool("OPENCELL_ENABLE_LP_WRITEBACK")
        self.enable_lp_writeback: bool = (
            env_lp_writeback
            if env_lp_writeback is not None
            else bool(self.parameters["enable_lp_writeback"])
        )
        self.enable_pool_replenishment: bool = bool(self.parameters["enable_pool_replenishment"])
        self._sub_state: np.ndarray | None = None
        self._enz_state: np.ndarray | None = None
        self._prev_shared: dict[str, float] | None = None
        self._dyn: cfb.M1DynamicsInputs | None = None
        self._sub_id_to_idx: dict[str, int] | None = None
        self._fba_reaction_bounds: np.ndarray | None = None
        self._demand_idx_pairs: list[tuple[str, int]] = []
        self._fba_row_sub: np.ndarray | None = None
        self._fba_row_cmp: np.ndarray | None = None
        self._demand_writeback_rows: dict[int, np.ndarray] = {}
        self._demand_sub_ids: dict[int, str] = {}
        self._cytosol_rows: np.ndarray = np.empty(0, dtype=np.int64)
        self._cyt_row_to_sid: dict[int, str] = {}
        self.allocation_substrate_wids: tuple[str, ...] = tuple()
        self._last_allocation_demand: dict[str, float] = {}
        self._baseline_demand_per_s: dict[str, float] | None = None
        self._bug6b_clamped_reactions_total: int = 0

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
            self._fba_reaction_bounds = np.column_stack(
                [
                    self.model.lb,
                    self.model.ub,
                ]
            ).astype(float)
            self._demand_idx_pairs = [
                (sid, self._sub_id_to_idx[sid])
                for sid in _KARR_DEMAND_KEYS
                if sid in self._sub_id_to_idx
            ]
            # Cache FBA row lookups once.
            self._fba_row_sub = self._dyn.substrate_idx_fba_sub0
            self._fba_row_cmp = self._dyn.substrate_idx_fba_cmp0
            self._demand_sub_ids = {sid_idx: sid for sid, sid_idx in self._demand_idx_pairs}
            for sid_idx in self._demand_sub_ids:
                rows = np.where(
                    (self._fba_row_sub == sid_idx)
                    & (self._fba_row_cmp == _CYTOSOL_COMPARTMENT_0)
                )[0]
                if rows.size:
                    self._demand_writeback_rows[sid_idx] = rows
            # Bug 6a Stage 2: LP writeback now spans all mapped cytosol rows.
            self._cytosol_rows = np.where(self._fba_row_cmp == _CYTOSOL_COMPARTMENT_0)[0]
            self._cyt_row_to_sid = {}
            for r in self._cytosol_rows:
                sid_idx = int(self._fba_row_sub[r])
                if sid_idx < 0 or sid_idx >= len(self._sub_ids):
                    continue
                self._cyt_row_to_sid[int(r)] = self._sub_ids[sid_idx]
            self.allocation_substrate_wids = tuple(sorted(set(self._cyt_row_to_sid.values())))
            self._last_allocation_demand = {
                sid: 0.0 for sid in self.allocation_substrate_wids
            }
            # Bug 6c: lazy init.  Setting _prev_shared eagerly here (e.g.
            # to the schema default 1.0) relies on the snapshot happening
            # to equal the schema default, and silently corrupts the
            # tick-0 delta if any process has already written a non-default
            # value to ``substrates`` before M1's first update.  Defer
            # population to the first ``_dynamic_update`` call where we
            # have an authoritative view of ``shared`` -> delta is
            # structurally zero on the first tick.
            self._prev_shared: dict | None = None

            if self.enable_pool_replenishment:
                bd = self.parameters["baseline_demand_per_s"]
                if bd is None:
                    raise ValueError(
                        "enable_pool_replenishment=True requires "
                        "baseline_demand_per_s={sid: rate_per_s, ...} "
                        "(typically built by the composer from the actual "
                        "attached M2/M3 models at synth_scale=1.0)"
                    )
                missing = [sid for sid, _ in self._demand_idx_pairs if sid not in bd]
                if missing:
                    raise ValueError(f"baseline_demand_per_s missing demand keys: {missing}")
                self._baseline_demand_per_s = {
                    sid: float(bd[sid]) for sid, _ in self._demand_idx_pairs
                }
                for sid, rate in self._baseline_demand_per_s.items():
                    if not np.isfinite(rate) or rate < 0.0:
                        raise ValueError(
                            f"baseline_demand_per_s[{sid}]={rate} must be finite and non-negative"
                        )

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
            "enzymes": {
                wid: {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": False,
                }
                for wid in self.enzyme_wids
            },
            "boundEnzymes": {
                wid: {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": False,
                }
                for wid in self.enzyme_wids
            },
        }
        if self.dynamic_bounds:
            schema["m1_dynamic_diagnostics"] = self._diagnostics_schema()
            schema["m1_pools"] = self._m1_pools_schema()
        if self.use_allocator_budget:
            schema["substrates_allocated"] = {
                self.name: {
                    sid: {"_default": 0.0, "_emit": False}
                    for sid in self.allocation_substrate_wids
                }
            }
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
            "bug6b_clamped_reactions",
            "bug6a_writeback_total_positive",
            "bug6a_s2_atp_lp_delta",
            "bug6a_s2_total_neg_writeback",
            "bug6a_s2_total_pos_writeback",
        ]
        schema = {k: {"_default": 0.0, "_updater": "set", "_emit": True} for k in keys}
        schema["bug6a_writeback_keys"] = {"_default": [], "_updater": "set", "_emit": True}
        for sid, _ in self._demand_idx_pairs:
            schema[f"cyt_{sid}"] = {"_default": 0.0, "_updater": "set", "_emit": True}
        return schema

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
        if self._prev_shared is None:
            # First tick: seed tracker from observed shared state so
            # delta is exactly zero by construction.  Fall back to the
            # M1 sub_state for any sid missing from ``shared`` (should
            # not happen in practice but keeps the invariant total).
            self._prev_shared = {
                sid: float(
                    shared.get(
                        sid,
                        self._sub_state[
                            self._sub_id_to_idx[sid], _CYTOSOL_COMPARTMENT_0
                        ],
                    )
                )
                for sid in self._sub_ids
            }
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
        # Bug 6b: stoichiometric demand-pool headroom caps.
        # compute_bounds only constrains exchange-index reactions; demand pools
        # can still be driven negative by non-exchange consumers/producers.
        S = self.model.S
        assert self._fba_row_sub is not None
        assert self._fba_row_cmp is not None
        clamped = 0

        for sid_idx, rows in self._demand_writeback_rows.items():
            pool_f = float(self._sub_state[sid_idx, _CYTOSOL_COMPARTMENT_0])
            if pool_f <= 0.0:
                continue
            for r in rows:
                sto = S[r, :]
                consume_j = np.where(sto < 0.0)[0]
                produce_j = np.where(sto > 0.0)[0]
                if consume_j.size:
                    cap_ub = pool_f / (-sto[consume_j] * timestep)
                    bounds[consume_j, 1] = np.minimum(bounds[consume_j, 1], cap_ub)
                if produce_j.size:
                    cap_lb = -pool_f / (sto[produce_j] * timestep)
                    bounds[produce_j, 0] = np.maximum(bounds[produce_j, 0], cap_lb)

        infeasible = bounds[:, 0] > bounds[:, 1]
        if infeasible.any():
            mid = 0.5 * (bounds[infeasible, 0] + bounds[infeasible, 1])
            bounds[infeasible, 0] = mid
            bounds[infeasible, 1] = mid
            clamped = int(infeasible.sum())
        if clamped:
            self._bug6b_clamped_reactions_total += clamped

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

        # Bug 6a Stage 2: signed writeback across all mapped cytosol rows.
        substrate_delta: dict[str, float] = {}
        if self.enable_lp_writeback:
            rates = S[self._cytosol_rows, :] @ v
            for r_idx, rate in zip(self._cytosol_rows, rates, strict=False):
                sid = self._cyt_row_to_sid.get(int(r_idx))
                if sid is None:
                    continue
                delta = float(rate) * float(timestep)
                if abs(delta) > 0.0:
                    substrate_delta[sid] = substrate_delta.get(sid, 0.0) + delta

        raw_negative_demand = {sid: -delta for sid, delta in substrate_delta.items() if delta < 0.0}
        if self._last_allocation_demand:
            for sid in self._last_allocation_demand:
                self._last_allocation_demand[sid] = max(0.0, float(raw_negative_demand.get(sid, 0.0)))

        if self.use_allocator_budget:
            allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
            allocated_delta: dict[str, float] = {}
            for sid, delta in substrate_delta.items():
                if delta >= 0.0:
                    allocated_delta[sid] = delta
                    continue
                alloc_budget = max(0.0, float(allocated_state.get(sid, 0.0)))
                consumed = min(-delta, alloc_budget)
                if consumed > 0.0:
                    allocated_delta[sid] = -consumed
            substrate_delta = allocated_delta

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
        writeback_pos = float(sum(d for d in substrate_delta.values() if d > 0.0))
        writeback_neg = float(sum(d for d in substrate_delta.values() if d < 0.0))
        diag: dict[str, Any] = {
            "growth_per_s": float(info["biomass_flux_per_s"]),
            "biomass_flux_per_s": float(info["biomass_flux_per_s"]),
            "n_active_bounds_changed": float(n_changed),
            "min_lb": float(
                np.min(bounds[:, 0][np.isfinite(bounds[:, 0])])
                if np.any(np.isfinite(bounds[:, 0]))
                else 0.0
            ),
            "max_ub": float(
                np.max(bounds[:, 1][np.isfinite(bounds[:, 1])])
                if np.any(np.isfinite(bounds[:, 1]))
                else 0.0
            ),
            "bug6b_clamped_reactions": float(self._bug6b_clamped_reactions_total),
            "bug6a_writeback_total_positive": writeback_pos,
            "bug6a_writeback_keys": list(substrate_delta.keys()),
            "bug6a_s2_atp_lp_delta": float(substrate_delta.get("ATP", 0.0)),
            "bug6a_s2_total_neg_writeback": writeback_neg,
            "bug6a_s2_total_pos_writeback": writeback_pos,
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
            "substrates": substrate_delta,
        }


def build_karr_m1_engine(
    *,
    model: km.KarrMetabolismModel | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    dynamic_bounds: bool = False,
) -> object:
    """Build a Vivarium Engine running just M1 (Karr metabolism).

    This is the chassis-tick smoke harness.  No other processes -
    metabolism runs in vacuo.  Use to prove the chassis is healthy
    before composing M2..M7.
    """
    from vivarium.core.engine import Engine

    if model is None:
        model = km.load_default()

    proc = KarrMetabolismProcess(
        {
            "model": model,
            "time_step": time_step_s,
            "dynamic_bounds": dynamic_bounds,
        }
    )
    processes = {"m1_karr": proc}
    topology = {
        "m1_karr": {
            "metabolic_reaction": ("metabolic_reaction",),
            "substrates": ("substrates",),
        }
    }
    if dynamic_bounds:
        topology["m1_karr"]["m1_dynamic_diagnostics"] = ("m1_dynamic_diagnostics",)
        topology["m1_karr"]["m1_pools"] = ("m1_pools",)

    rxn_ids = model.rxn_wcm_ids_645
    sub_ids = model.raw["ids"]["substrate_wcm_585"]
    initial_state: dict[str, Any] = {
        "metabolic_reaction": {
            "fluxs": {rid: float(model.fluxs_stored[i]) for i, rid in enumerate(rxn_ids)},
            "growth_per_s": float(model.stored_runtime["growth_per_s"]),
            "growth_per_h": float(model.stored_runtime["growth_per_h"]),
        },
        "substrates": {sid: 1.0 for sid in sub_ids},
    }
    if dynamic_bounds:
        initial_state["m1_dynamic_diagnostics"] = {k: 0.0 for k in proc._diagnostics_schema()}
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
