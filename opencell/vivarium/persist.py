"""M0-A: Persistent LSODA Process for the metabolism block.

Why this exists
---------------
M0.5 profiling found per-Process LSODA spin-up = 15.6 s flat regardless
of N processes. The Vivarium scheduler is not the bottleneck; the cost
is `solve_ivp(method='LSODA', t_span=(0, dt))` re-instantiating the
LSODA integrator on every macro step.

This module provides ``PersistentMetabolismProcess`` which holds a
``scipy.integrate.ode`` instance on the Process object across
``next_update`` calls. The integrator advances from absolute time ``t``
to ``t + dt`` without reinitialising — eliminating spin-up.

Time semantics (rubber-duck-flagged blind spot)
-----------------------------------------------
Unlike the non-persistent path which restarts at ``t=0`` each macro
step, the persistent path advances at *absolute* simulation time. If
the SBML kinetic laws reference ``t`` symbol (Chassagnole 2002 does
not, but generally any SBML can), the trajectory will differ.
``opencell.models.sbml_model.SbmlModel._build_env`` does inject ``t``
into the symbol environment, so this is a real concern in principle.
We currently rely on Chassagnole being autonomous and assert it via
the ``test_persistent_lsoda_matches_single_shot`` regression test.

External-write detection (resync semantics)
-------------------------------------------
If a downstream Process writes to ``('metabolites', s)`` between our
calls, the cached state on the integrator no longer matches the store
and we must reset. We detect this by comparing the incoming
``states['metabolites']`` to a cached snapshot. On mismatch
(``np.allclose`` with a tight tolerance) we call ``set_initial_value``
to resync — equivalent to the old per-step restart for that one step,
then back to incremental for subsequent steps.

A6 amendment: The "LSODA-restart rule" (~0.1 mM drift per 8h) applies
only at *resync boundaries*. Pure one-way coupling never resyncs and
should match a single full-horizon LSODA solve to LSODA tolerance.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.integrate import ode
from vivarium.core.process import Process

from opencell.models.coupled import (
    PTS_REACTION_INDEX,
    CoupledMetabolismTranscription,
)


# Tolerance for "did the store change vs my cached state" check.
# Tighter than LSODA's own tolerances: any change of size > rel 1e-12
# is treated as an external write requiring resync.
_RESYNC_RTOL = 1e-12
_RESYNC_ATOL = 1e-15


class PersistentMetabolismProcess(Process):
    """Chassagnole metabolism with a persistent LSODA integrator.

    API-compatible drop-in for ``MetabolismProcess``: same ports, same
    updater semantics, same parameters dict shape (with two extras for
    benchmark/audit).

    Extra parameters:
        ``track_resyncs`` (bool, default True) — count resyncs for the
            audit log accessible via ``self.resync_count``.
    """

    name = "metabolism_persistent"
    defaults: dict[str, Any] = {
        "coupled": None,
        "atol": 1e-9,
        "rtol": 1e-6,
        "track_resyncs": True,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        coupled: CoupledMetabolismTranscription = self.parameters["coupled"]
        if coupled is None:
            raise ValueError("PersistentMetabolismProcess requires a 'coupled' parameter")
        self.coupled = coupled
        self.met = coupled.met
        self._species_idx = self.met.species_index()
        self.species = list(self._species_idx.keys())
        self._cglcex_idx = self._species_idx["cglcex"]

        # Build the persistent integrator, primed at t=0 with initial state.
        # nsteps: scipy.integrate.ode's lsoda default of 500 is per-call but
        # in long-running engine contexts (many short integrate() calls back
        # to back) we sometimes hit the limit on a single call when the
        # solver chooses very small internal steps. Bump generously; this
        # is a safety bound, not a target.
        y0 = self.met.initial_y.copy()
        self._integrator = ode(self.met.rhs).set_integrator(
            "lsoda",
            atol=self.parameters["atol"],
            rtol=self.parameters["rtol"],
            nsteps=10000,
        )
        self._integrator.set_initial_value(y0, 0.0)
        self._t = 0.0
        self._cached_y = y0.copy()
        self.resync_count = 0
        self.step_count = 0

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

    def _resync_if_needed(self, store_y: np.ndarray) -> bool:
        if np.allclose(store_y, self._cached_y, rtol=_RESYNC_RTOL, atol=_RESYNC_ATOL):
            return False
        self._integrator.set_initial_value(store_y.copy(), self._t)
        self._cached_y = store_y.copy()
        if self.parameters["track_resyncs"]:
            self.resync_count += 1
        return True

    def next_update(self, timestep: float, states: dict) -> dict:
        store_y = np.array(
            [states["metabolites"][s] for s in self.species],
            dtype=np.float64,
        )
        self._resync_if_needed(store_y)

        t_target = self._t + timestep
        y_end = self._integrator.integrate(t_target)
        if not self._integrator.successful():
            raise RuntimeError(
                f"PersistentMetabolismProcess LSODA failed at t={t_target}"
            )

        self._t = t_target
        self._cached_y = y_end.copy()
        self.step_count += 1

        v_pts_end = float(self.met.sbml.fluxes(t_target, y_end)[PTS_REACTION_INDEX])
        return {
            "metabolites": {s: float(y_end[i]) for s, i in self._species_idx.items()},
            "signal": {
                "cglcex": float(y_end[self._cglcex_idx]),
                "v_pts": v_pts_end,
            },
        }
