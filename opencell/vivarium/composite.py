"""Compose the three Processes into a runnable Vivarium engine.

Topology choice (A6 semantics input):

* All three Processes share a single ``signal`` store containing
  ``cglcex``, ``v_pts``, and ``f_met``. MetabolismProcess writes the
  observables, SignalProcess derives ``f_met``, GeneNetworkProcess reads
  ``f_met``. This is glass-box: every coupling variable is observable
  in the emitter and diff-able by A5.
* All three Processes use the same global timestep (the macro_dt of the
  hybrid solver). Vivarium's default scheduler advances all processes
  by ``timestep`` and applies updates simultaneously at the boundary,
  which matches the lockstep operator-split semantics of ``hybrid_run``
  for the one-way coupling case (gene reads the *previous* boundary's
  f_met, not the new one). See A6 contract for the formal statement
  and the f_met-of-record convention this engine relies on.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from vivarium.core.engine import Engine

from opencell.models.coupled import CoupledMetabolismTranscription
from opencell.vivarium.persist import PersistentMetabolismProcess
from opencell.vivarium.processes import (
    GeneNetworkProcess,
    MetabolismProcess,
    SignalProcess,
)


def build_coupled_engine(
    coupled: CoupledMetabolismTranscription | None = None,
    *,
    macro_dt_s: float = 60.0,
    rng: np.random.Generator | None = None,
    seed: int = 0,
    epsilon: float = 0.03,
    met_atol: float = 1e-9,
    met_rtol: float = 1e-6,
    emit_step: float | None = None,
    persistent_metabolism: bool = False,
) -> Engine:
    """Build a Vivarium ``Engine`` running the coupled cell.

    The returned Engine is unstarted; call ``engine.update(t_total_s)``
    to run for ``t_total_s`` seconds. Emitter is the in-memory ``ram``
    emitter — call ``engine.emitter.get_timeseries()`` after.

    ``persistent_metabolism`` (M0-A): when True, swaps in
    :class:`PersistentMetabolismProcess` which keeps a single LSODA
    integrator alive across macro steps. Eliminates the per-step
    spin-up that dominates the 73× wall-time overhead at small
    ``macro_dt``. See ``docs/phase4/M0A_persistent_lsoda.md``.
    """
    if coupled is None:
        coupled = CoupledMetabolismTranscription.build(signal="uptake_flux")
    if rng is None:
        rng = np.random.default_rng(seed)

    met_cls = PersistentMetabolismProcess if persistent_metabolism else MetabolismProcess
    met_proc = met_cls(
        {"coupled": coupled, "atol": met_atol, "rtol": met_rtol, "time_step": macro_dt_s}
    )
    sig_proc = SignalProcess(
        {"coupled": coupled, "signal_type": coupled.signal, "time_step": macro_dt_s}
    )
    gene_proc = GeneNetworkProcess(
        {
            "coupled": coupled,
            "rng": rng,
            "epsilon": epsilon,
            "tau_dt_max": macro_dt_s,
            "time_step": macro_dt_s,
        }
    )

    # Process keys must NOT collide with store paths; Vivarium places each
    # process at a store path equal to its key. Hence "_proc" suffix.
    processes = {
        "metabolism_proc": met_proc,
        "signal_proc": sig_proc,
        "gene_network_proc": gene_proc,
    }
    topology = {
        "metabolism_proc": {
            "metabolites": ("metabolites",),
            "signal": ("signal",),
        },
        "signal_proc": {"signal": ("signal",)},
        "gene_network_proc": {
            "gene_state": ("gene_state",),
            "signal": ("signal",),
        },
    }

    midx = coupled.met.species_index()
    gidx = coupled.gene.species_index()
    y_met0 = coupled.met.initial_y
    y_gene0 = coupled.gene.initial_y
    initial_state: dict[str, Any] = {
        "metabolites": {s: float(y_met0[i]) for s, i in midx.items()},
        "gene_state": {s: float(y_gene0[i]) for s, i in gidx.items()},
        "signal": {
            "cglcex": float(y_met0[midx["cglcex"]]),
            "v_pts": float(coupled.v_pts_init),
            "f_met": 1.0,
        },
    }

    engine = Engine(
        processes=processes,
        topology=topology,
        initial_state=initial_state,
        emit_step=emit_step or macro_dt_s,
    )
    return engine
