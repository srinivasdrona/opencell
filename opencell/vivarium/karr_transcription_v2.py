"""Vivarium Process wrapper for M2 v2 mechanism-based transcription.

Dynamic-pool discipline (A3 step 2, non-negotiable):
- Read consumer inputs from ``complex.counts.<wid>`` inside every
  ``next_update`` call.
- Never cache those values in ``__init__`` or assume they are constant
  tick-to-tick.

Current complex-count dependency and provenance:
- ``complex.counts["RNA_POLYMERASE"]`` -> active RNAP count proxy used
  as ``n_active`` for :func:`opencell.m2.transcription_v2.predict_gene_synthesis_per_s`.
  The WID is in D.2 ownership seeds derived from
  ``MacromolecularComplexation_flat.mat`` / ``RibosomeAssembly_flat.mat``
  and default counts come from ``ProteinComplex_flat.mat`` via
  :class:`opencell.vivarium.karr_d2_stub.KarrD2StubProcess`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from vivarium.core.process import Process

from opencell.m2 import transcription as tx
from opencell.m2 import transcription_v2 as tx_v2

_M2_CONSUMED_SUBSTRATES: tuple[str, ...] = ("ATP", "CTP", "GTP", "UTP")
_RNAP_COUNT_WID = "RNA_POLYMERASE"


class KarrTranscriptionV2Process(Process):
    """Mechanism-driven transcription wrapper for the central-dogma chassis."""

    name = "karr_transcription_v2"
    defaults: dict[str, Any] = {
        "kinetics_model": None,
        "mechanism_inputs": None,
        "time_step": 1.0,
        "write_substrate_deltas": True,
        "substrate_default": 0.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        kinetics_model = self.parameters.get("kinetics_model")
        if kinetics_model is None:
            kinetics_model = tx.calibrated_chassis_model(tx.load_default())
        mechanism_inputs = self.parameters.get("mechanism_inputs")
        if mechanism_inputs is None:
            mechanism_inputs = tx_v2.load_default()

        self.kinetics_model: tx.KarrTranscriptionModel = kinetics_model
        self.mechanism_inputs: tx_v2.MechanismInputs = mechanism_inputs
        self.gene_ids = self.kinetics_model.gene_wcm_ids
        if len(self.gene_ids) != self.mechanism_inputs.n_genes:
            raise ValueError(
                "M2 v2 wrapper expects matching gene dimensions: "
                f"kinetics={len(self.gene_ids)} mechanism={self.mechanism_inputs.n_genes}"
            )

        self.consumed_substrates: tuple[str, ...] = _M2_CONSUMED_SUBSTRATES
        self._fallback_n_active_rnap = int(self.mechanism_inputs.n_active_rnap)

    def ports_schema(self) -> dict[str, Any]:
        rna_ss = self.kinetics_model.counts_mature[:, 1]
        return {
            "rna": {
                "counts": {
                    gid: {
                        "_default": float(rna_ss[i]),
                        "_updater": "set",
                        "_emit": True,
                    }
                    for i, gid in enumerate(self.gene_ids)
                }
            },
            "substrates": {
                ntp: {
                    "_default": float(self.parameters["substrate_default"]),
                    "_updater": "accumulate",
                    "_emit": True,
                }
                for ntp in self.consumed_substrates
            },
            "complex": {
                "counts": {
                    _RNAP_COUNT_WID: {
                        "_default": float(self._fallback_n_active_rnap),
                        "_updater": "accumulate",
                        "_emit": False,
                    }
                }
            },
        }

    def _step_rna(self, rna: np.ndarray, synth_per_s: np.ndarray, dt_s: float) -> np.ndarray:
        decay = self.kinetics_model.decay_rate_per_s
        out = np.empty_like(rna)
        no_decay = decay <= 0.0
        if np.any(~no_decay):
            idx = ~no_decay
            ss = synth_per_s[idx] / decay[idx]
            out[idx] = ss + (rna[idx] - ss) * np.exp(-decay[idx] * dt_s)
        if np.any(no_decay):
            out[no_decay] = rna[no_decay] + synth_per_s[no_decay] * dt_s
        return out

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        rna = np.array([float(states["rna"]["counts"][gid]) for gid in self.gene_ids], dtype=float)

        complex_counts = states.get("complex", {}).get("counts", {})
        # DYNAMIC: read per-tick; do not cache. d2-stub writes nothing today but D.2-real will.
        n_active_rnap = float(complex_counts.get(_RNAP_COUNT_WID, self._fallback_n_active_rnap))
        if n_active_rnap < 0.0:
            n_active_rnap = 0.0

        synth_gene_per_s = tx_v2.predict_gene_synthesis_per_s(
            self.mechanism_inputs, n_active=n_active_rnap
        )
        rna_next = self._step_rna(rna, synth_gene_per_s, timestep)

        update: dict[str, Any] = {
            "rna": {"counts": {gid: float(rna_next[i]) for i, gid in enumerate(self.gene_ids)}}
        }
        if self.parameters["write_substrate_deltas"]:
            total_nt = tx_v2.total_nt_polymerization_per_s(
                self.mechanism_inputs, n_active=n_active_rnap
            )
            per_ntp = total_nt / 4.0
            update["substrates"] = {ntp: -per_ntp * timestep for ntp in self.consumed_substrates}
        return update
