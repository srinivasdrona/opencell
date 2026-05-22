"""Process adapters for the Chassagnole + Vilar coupled cell.

Three processes, composed via shared stores:

  MetabolismProcess  --writes--> ('metabolites', species)
                     --writes--> ('signal', 'cglcex')
                     --writes--> ('signal', 'v_pts')
  SignalProcess      --reads-->  ('signal', 'cglcex' or 'v_pts')
                     --writes--> ('signal', 'f_met')
  GeneNetworkProcess --reads-->  ('signal', 'f_met')
                     --writes--> ('gene_state', species)  (integer counts)

Why split out SignalProcess? Because the f_met derivation is the single
place where the coupling semantics live. M0's bidirectional coupling
will replace this Process (or add a back-coupling Process), without
touching MetabolismProcess or GeneNetworkProcess. That separation is
the architectural payoff of using Vivarium for this work.

Ports schema is intentionally verbose. Implicit defaults are a known
foot-gun for whole-cell composition; the A6 semantics contract requires
every variable's units, default, updater, and emit policy to be stated.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp
from vivarium.core.process import Process

from opencell.models.coupled import (
    PTS_REACTION_INDEX,
    SECONDS_PER_HOUR,
    SYNTHESIS_REACTION_INDICES,
    CoupledMetabolismTranscription,
)
from opencell.solvers.stochastic import TauLeapConfig, tau_leap


class MetabolismProcess(Process):
    """Chassagnole 2002 metabolism, integrated by LSODA over each timestep.

    Updater is ``'set'`` because we replace concentrations rather than
    accumulating deltas. Time unit on the port is seconds, matching the
    Vivarium engine clock we will use throughout.
    """

    name = "metabolism"
    defaults: dict[str, Any] = {
        "coupled": None,
        "atol": 1e-9,
        "rtol": 1e-6,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        coupled: CoupledMetabolismTranscription = self.parameters["coupled"]
        if coupled is None:
            raise ValueError("MetabolismProcess requires a 'coupled' parameter")
        self.coupled = coupled
        self.met = coupled.met
        self._species_idx = self.met.species_index()
        self.species = list(self._species_idx.keys())
        self._cglcex_idx = self._species_idx["cglcex"]

    def ports_schema(self) -> dict[str, Any]:
        y0 = self.met.initial_y
        return {
            "metabolites": {
                s: {
                    "_default": float(y0[i]),
                    "_updater": "set",
                    "_emit": True,
                }
                for s, i in self._species_idx.items()
            },
            "signal": {
                "cglcex": {
                    "_default": float(y0[self._cglcex_idx]),
                    "_updater": "set",
                    "_emit": True,
                },
                "v_pts": {
                    "_default": 0.0,
                    "_updater": "set",
                    "_emit": True,
                },
            },
        }

    def next_update(self, timestep: float, states: dict) -> dict:
        y0 = np.array(
            [states["metabolites"][s] for s in self.species],
            dtype=np.float64,
        )
        sol = solve_ivp(
            self.met.rhs,
            (0.0, timestep),
            y0,
            method="LSODA",
            atol=self.parameters["atol"],
            rtol=self.parameters["rtol"],
        )
        if not sol.success:
            raise RuntimeError(f"Metabolism LSODA failed: {sol.message}")
        y_end = sol.y[:, -1]
        v_pts_end = float(self.met.sbml.fluxes(timestep, y_end)[PTS_REACTION_INDEX])
        return {
            "metabolites": {s: float(y_end[i]) for s, i in self._species_idx.items()},
            "signal": {
                "cglcex": float(y_end[self._cglcex_idx]),
                "v_pts": v_pts_end,
            },
        }


class SignalProcess(Process):
    """Derive ``f_met`` from a metabolic observable.

    Pure function; no internal state. Exists as a separate Process so
    that swapping coupling semantics (one-way -> bidirectional, or
    different observable) is a topology change, not a code change.
    """

    name = "signal"
    defaults: dict[str, Any] = {
        "coupled": None,
        "signal_type": "uptake_flux",
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        coupled: CoupledMetabolismTranscription = self.parameters["coupled"]
        if coupled is None:
            raise ValueError("SignalProcess requires a 'coupled' parameter")
        self.coupled = coupled
        self.signal_type = self.parameters["signal_type"]
        self.f_met_fn = coupled.f_met_fn
        self.cglcex_init = coupled.cglcex_init
        self.v_pts_init = coupled.v_pts_init

    def ports_schema(self) -> dict[str, Any]:
        return {
            "signal": {
                "f_met": {
                    "_default": 1.0,
                    "_updater": "set",
                    "_emit": True,
                },
                "cglcex": {
                    "_default": float(self.cglcex_init),
                    "_updater": "set",
                    "_emit": True,
                },
                "v_pts": {
                    "_default": float(self.v_pts_init),
                    "_updater": "set",
                    "_emit": True,
                },
            }
        }

    def next_update(self, timestep: float, states: dict) -> dict:
        sig = states["signal"]
        if self.signal_type == "uptake_flux":
            f = self.f_met_fn(float(sig["v_pts"]), self.v_pts_init)
        else:
            f = self.f_met_fn(float(sig["cglcex"]), self.cglcex_init)
        return {"signal": {"f_met": float(f)}}


class GeneNetworkProcess(Process):
    """Vilar 2002 gene network, advanced by tau-leaping over each timestep.

    Counts are integers; updater is ``'accumulate'`` and the increment
    we emit is the integer delta over the timestep. RNG is supplied via
    parameters and never replaced inside ``next_update`` — same hygiene
    as ``hybrid_run``.
    """

    name = "gene_network"
    defaults: dict[str, Any] = {
        "coupled": None,
        "rng": None,
        "epsilon": 0.03,
        "tau_dt_max": None,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        coupled: CoupledMetabolismTranscription = self.parameters["coupled"]
        rng = self.parameters["rng"]
        if coupled is None:
            raise ValueError("GeneNetworkProcess requires a 'coupled' parameter")
        if rng is None:
            raise ValueError(
                "GeneNetworkProcess requires an explicit 'rng' "
                "(np.random.Generator). Bare seeds are forbidden by the "
                "stochastic RNG discipline."
            )
        self.coupled = coupled
        self.gene = coupled.gene
        self.rng = rng
        self._species_idx = self.gene.species_index()
        self.species = list(self._species_idx.keys())
        self._stoich = self.gene.sbml.stoich
        self._synth_set = set(SYNTHESIS_REACTION_INDICES)
        self._n_r = self.gene.n_reactions
        self._inv_seconds_per_hour = 1.0 / SECONDS_PER_HOUR

    def ports_schema(self) -> dict[str, Any]:
        y0 = self.gene.initial_y
        return {
            "gene_state": {
                s: {
                    "_default": float(y0[i]),
                    "_updater": "accumulate",
                    "_emit": True,
                }
                for s, i in self._species_idx.items()
            },
            "signal": {
                "f_met": {
                    "_default": 1.0,
                    "_updater": "set",
                    "_emit": True,
                }
            },
        }

    def _propensity_factory(self, f_met: float) -> Callable[[np.ndarray], np.ndarray]:
        synth_set = self._synth_set
        n_r = self._n_r
        inv_sph = self._inv_seconds_per_hour
        gene = self.gene

        def propensity(y_arr: np.ndarray) -> np.ndarray:
            v_per_h = gene.fluxes(0.0, np.asarray(y_arr, dtype=np.float64))
            v_per_s = v_per_h * inv_sph
            scaled = v_per_s.copy()
            for j in range(n_r):
                if j in synth_set:
                    scaled[j] = scaled[j] * f_met
            return np.maximum(scaled, 0.0)

        return propensity

    def next_update(self, timestep: float, states: dict) -> dict:
        y0 = np.array(
            [states["gene_state"][s] for s in self.species],
            dtype=np.float64,
        )
        f_met = float(states["signal"]["f_met"])
        tau_dt_max = self.parameters["tau_dt_max"] or timestep
        config = TauLeapConfig(
            epsilon=self.parameters["epsilon"],
            dt_max=tau_dt_max,
        )
        seg = tau_leap(
            propensity_fn=self._propensity_factory(f_met),
            stoich_matrix=self._stoich,
            y0=y0,
            t_span=(0.0, timestep),
            rng=self.rng,
            config=config,
            save_every=10**9,
        )
        y_end = seg.ys[-1]
        return {"gene_state": {s: float(y_end[i] - y0[i]) for s, i in self._species_idx.items()}}
