"""Vivarium Process wrapper for Karr-native M3 translation."""
from __future__ import annotations

from typing import Any

import numpy as np
from vivarium.core.process import Process

from opencell.m3 import translation as tl


class KarrTranslationProcess(Process):
    """1-second-tick analytical integrator of Karr-prescribed protein dynamics.

    For 482 mature protein monomers:  dN_i/dt = s_i - k_i*N_i,
    integrated in closed form per tick.  Writes:
      - protein.counts (482-dict by protein WCM ID, 'set' updater)
      - substrates.{20 AA WCM IDs} (per-AA consumption deltas,
        'accumulate', negative).  The 20 IDs are the standard amino
        acids in Karr's metabolite vocabulary, resolved from
        :data:`opencell.m3.translation.AA_WCM_IDS` and
        ``model.aa_col_indices``.

    Per-AA consumption rate for AA ``a`` is

        rate_a = Sum_i ( synth_rate_per_s[i] * base_counts[i, col_a] )

    and the per-tick delta is ``-rate_a * timestep``.  This replaces
    the v1 ``AA_total`` placeholder and gives M1's dynamic-bounds mode
    real per-AA pool drains aligned with Karr's 585-substrate ID space.
    """

    name = "karr_translation"
    defaults: dict[str, Any] = {
        "model": None,
        "time_step": 1.0,
        "write_substrate_deltas": True,
        "substrate_default": 0.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        model = self.parameters.get("model")
        if model is None:
            model = tl.load_default()
        self.model: tl.KarrTranslationModel = model
        self.protein_ids = self.model.protein_wcm_ids
        self.aa_ids: tuple[str, ...] = self.model.aa_wcm_ids

    def ports_schema(self) -> dict[str, Any]:
        ss = self.model.counts_mature
        protein_schema = {
            pid: {
                "_default": float(ss[i]),
                "_updater": "set",
                "_emit": True,
            }
            for i, pid in enumerate(self.protein_ids)
        }
        substrates_schema = {
            aa: {
                "_default": float(self.parameters["substrate_default"]),
                "_updater": "accumulate",
                "_emit": True,
            }
            for aa in self.aa_ids
        }
        return {
            "protein": {"counts": protein_schema},
            "substrates": substrates_schema,
        }

    def next_update(self, timestep: float, states: dict) -> dict:
        n = np.array(
            [float(states["protein"]["counts"][p]) for p in self.protein_ids],
            dtype=float,
        )
        n_next = tl.step_analytical(self.model, n, timestep)
        n_set = {p: float(n_next[i]) for i, p in enumerate(self.protein_ids)}

        update: dict[str, Any] = {"protein": {"counts": n_set}}
        if self.parameters["write_substrate_deltas"]:
            aa = tl.aa_consumption_per_s(self.model)
            update["substrates"] = {
                a: -float(aa[a]) * timestep for a in self.aa_ids
            }
        return update


def build_karr_m3_engine(
    *,
    model: tl.KarrTranslationModel | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    initial_protein_counts: np.ndarray | None = None,
):
    """Build a Vivarium Engine running just M3 (translation)."""
    from vivarium.core.engine import Engine

    if model is None:
        model = tl.load_default()
    proc = KarrTranslationProcess({"model": model, "time_step": time_step_s})
    schema = proc.ports_schema()

    if initial_protein_counts is None:
        prot_init = {p: schema["protein"]["counts"][p]["_default"]
                     for p in model.protein_wcm_ids}
    else:
        prot_init = {p: float(initial_protein_counts[i])
                     for i, p in enumerate(model.protein_wcm_ids)}

    engine = Engine(
        processes={"m3_karr": proc},
        topology={
            "m3_karr": {
                "protein": ("protein",),
                "substrates": ("substrates",),
            }
        },
        initial_state={
            "protein": {"counts": prot_init},
            "substrates": {aa: 0.0 for aa in proc.aa_ids},
        },
        emit_step=emit_step_s or time_step_s,
    )
    return engine

