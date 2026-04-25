"""Vivarium Process wrapper for Karr-native M2 transcription."""
from __future__ import annotations

from typing import Any

import numpy as np
from vivarium.core.process import Process

from opencell.m2 import transcription as tx


class KarrTranscriptionProcess(Process):
    """1-second-tick analytical integrator of Karr-prescribed RNA dynamics.

    For every 525 genes:  dRNA_i/dt = s_i - k_i * RNA_i, integrated in
    closed form per tick.  Writes:
      - rna.counts (525-dict by WCM ID, 'set' updater)
      - substrates.{ATP,CTP,GTP,UTP} (deltas, 'accumulate', negative)

    `condition` parameter (0/1/2) selects synthesis-rate column.  Default
    1 (Karr's mean condition).  Substrate writeback is a placeholder that
    will be reconciled against M1's NTP production once the cross-process
    substrate-state mapping ships (currently uses 1:1 dict keys ATP/CTP/
    GTP/UTP, not Karr's 1686 metabolite-x-compartment count vector).
    """

    name = "karr_transcription"
    defaults: dict[str, Any] = {
        "model": None,
        "time_step": 1.0,
        "condition": 1,
        "write_substrate_deltas": True,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        model = self.parameters.get("model")
        if model is None:
            model = tx.load_default()
        self.model: tx.KarrTranscriptionModel = model
        self.condition = int(self.parameters["condition"])
        self.gene_ids = self.model.gene_wcm_ids

    def ports_schema(self) -> dict[str, Any]:
        # Initial RNA counts: use Karr's stored steady-state (expression
        # column 1) so the chassis starts coherent with M1 even before
        # M2 has ticked once.
        ss = self.model.expression[:, self.condition]
        rna_schema = {
            gid: {
                "_default": float(ss[i]),
                "_updater": "set",
                "_emit": True,
            }
            for i, gid in enumerate(self.gene_ids)
        }
        substrates_schema = {
            ntp: {
                "_default": 0.0,
                "_updater": "accumulate",
                "_emit": True,
            }
            for ntp in ("ATP", "CTP", "GTP", "UTP")
        }
        return {
            "rna": {"counts": rna_schema},
            "substrates": substrates_schema,
        }

    def next_update(self, timestep: float, states: dict) -> dict:
        rna = np.array(
            [float(states["rna"]["counts"][g]) for g in self.gene_ids],
            dtype=float,
        )
        rna_next = tx.step_analytical(
            self.model, rna, timestep, condition=self.condition
        )
        rna_set = {g: float(rna_next[i]) for i, g in enumerate(self.gene_ids)}

        update: dict[str, Any] = {"rna": {"counts": rna_set}}
        if self.parameters["write_substrate_deltas"]:
            ntp = tx.ntp_consumption_per_s(self.model, condition=self.condition)
            update["substrates"] = {
                "ATP": -ntp["ATP"] * timestep,
                "CTP": -ntp["CTP"] * timestep,
                "GTP": -ntp["GTP"] * timestep,
                "UTP": -ntp["UTP"] * timestep,
            }
        return update


def build_karr_m2_engine(
    *,
    model: tx.KarrTranscriptionModel | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    initial_rna_counts: np.ndarray | None = None,
):
    """Build a Vivarium Engine running just M2 (transcription)."""
    from vivarium.core.engine import Engine

    if model is None:
        model = tx.load_default()
    proc = KarrTranscriptionProcess({"model": model, "time_step": time_step_s})
    schema = proc.ports_schema()

    if initial_rna_counts is None:
        rna_init = {g: schema["rna"]["counts"][g]["_default"]
                    for g in model.gene_wcm_ids}
    else:
        rna_init = {g: float(initial_rna_counts[i])
                    for i, g in enumerate(model.gene_wcm_ids)}

    engine = Engine(
        processes={"m2_karr": proc},
        topology={
            "m2_karr": {
                "rna": ("rna",),
                "substrates": ("substrates",),
            }
        },
        initial_state={
            "rna": {"counts": rna_init},
            "substrates": {"ATP": 0.0, "CTP": 0.0, "GTP": 0.0, "UTP": 0.0},
        },
        emit_step=emit_step_s or time_step_s,
    )
    return engine
