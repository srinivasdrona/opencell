"""Probe 5 helper: explicit 4-process composer variant for chassis scaling."""

from __future__ import annotations

from vivarium.core.engine import Engine
from vivarium.core.process import Process

from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.karr_m1 import KarrMetabolismProcess
from opencell.vivarium.karr_m2 import KarrTranscriptionProcess
from opencell.vivarium.karr_m3 import KarrTranslationProcess


_M1_SUBSTRATE_DEFAULT = 1.0


class ProteinDecayStub(Process):
    name = "protein_decay_stub"
    defaults = {"wid": "RNA_POLYMERASE"}

    def ports_schema(self):
        wid = str(self.parameters["wid"])
        return {
            "complex": {
                "counts": {
                    wid: {"_default": 0, "_updater": "accumulate", "_emit": True}
                }
            }
        }

    def next_update(self, timestep, states):
        return {}


def build_karr_m1_m2_m3_decay_engine(*, time_step_s: float = 1.0, emit_step_s: float | None = None):
    m1_model = km.load_default()
    m2_model = tx.load_default()
    m3_model = tl.load_default()

    m1_proc = KarrMetabolismProcess({"model": m1_model, "time_step": time_step_s})
    m2_proc = KarrTranscriptionProcess(
        {
            "model": m2_model,
            "time_step": time_step_s,
            "condition": 1,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
        }
    )
    m3_proc = KarrTranslationProcess(
        {
            "model": m3_model,
            "time_step": time_step_s,
            "substrate_default": _M1_SUBSTRATE_DEFAULT,
        }
    )
    d4_proc = ProteinDecayStub({"wid": "RNA_POLYMERASE"})

    rxn_ids = m1_model.rxn_wcm_ids_645
    sub_ids = m1_model.raw["ids"]["substrate_wcm_585"]
    rna_init = {g: float(m2_model.counts_mature[i, 1]) for i, g in enumerate(m2_model.gene_wcm_ids)}
    prot_init = {p: float(m3_model.counts_mature[i]) for i, p in enumerate(m3_model.protein_wcm_ids)}

    return Engine(
        processes={
            "m1_karr": m1_proc,
            "m2_karr": m2_proc,
            "m3_karr": m3_proc,
            "protein_decay_stub": d4_proc,
        },
        topology={
            "m1_karr": {"metabolic_reaction": ("metabolic_reaction",), "substrates": ("substrates",)},
            "m2_karr": {"rna": ("rna",), "substrates": ("substrates",)},
            "m3_karr": {"protein": ("protein",), "substrates": ("substrates",)},
            "protein_decay_stub": {"complex": ("complex",)},
        },
        initial_state={
            "metabolic_reaction": {
                "fluxs": {rid: float(m1_model.fluxs_stored[i]) for i, rid in enumerate(rxn_ids)},
                "growth_per_s": float(m1_model.stored_runtime["growth_per_s"]),
                "growth_per_h": float(m1_model.stored_runtime["growth_per_h"]),
            },
            "substrates": {sid: _M1_SUBSTRATE_DEFAULT for sid in sub_ids},
            "rna": {"counts": rna_init},
            "protein": {"counts": prot_init},
            "complex": {"counts": {"RNA_POLYMERASE": 0}},
        },
        emit_step=emit_step_s or time_step_s,
        display_info=False,
    )

