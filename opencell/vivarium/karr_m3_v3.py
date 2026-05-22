"""Vivarium Process wrapper for M3 v2 mechanism-based translation.

Dynamic-pool discipline (A3 step 2, non-negotiable):
- Read consumer inputs from ``complex.counts.<wid>`` inside every
  ``next_update`` call.
- Never cache those values in ``__init__`` or assume they are constant
  tick-to-tick.

Current complex-count dependency and provenance:
- ``complex.counts["RIBOSOME_70S"]`` -> active ribosome count proxy used
  as ``n_active`` for :func:`opencell.m3.translation_v2.predict_synthesis_per_s`.
  In D.2 strategy notes, ``RIBOSOME_70S`` remains Process_Translation-owned,
  while D.2 owns assembly-side pools. This wrapper still reads from the
  shared ``complex.counts`` port each tick to stay compatible with the
  dynamic-pool contract once D.2-real lands.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from vivarium.core.process import Process

from opencell.m3 import translation as tl
from opencell.m3 import translation_v2 as tl_v2

_RIBOSOME_ACTIVE_WID = "RIBOSOME_70S"


class KarrTranslationV3Process(Process):
    """Mechanism-driven translation wrapper for the central-dogma chassis."""

    name = "karr_translation_v3"
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
            kinetics_model = tl.load_default()
        mechanism_inputs = self.parameters.get("mechanism_inputs")
        if mechanism_inputs is None:
            mechanism_inputs = tl_v2.load_default()

        self.kinetics_model: tl.KarrTranslationModel = kinetics_model
        self.mechanism_inputs: tl_v2.RibosomeMechanismInputs = mechanism_inputs
        self.protein_ids = self.kinetics_model.protein_wcm_ids
        if len(self.protein_ids) != self.mechanism_inputs.n_proteins:
            raise ValueError(
                "M3 v2 wrapper expects matching protein dimensions: "
                f"kinetics={len(self.protein_ids)} mechanism={self.mechanism_inputs.n_proteins}"
            )

        self.aa_ids = self.kinetics_model.aa_wcm_ids
        self._fallback_n_active_ribosomes = int(self.mechanism_inputs.n_active_ribosomes)

    def ports_schema(self) -> dict[str, Any]:
        return {
            "protein": {
                "counts": {
                    pid: {
                        "_default": float(self.kinetics_model.counts_mature[i]),
                        "_updater": "accumulate",
                        "_emit": True,
                    }
                    for i, pid in enumerate(self.protein_ids)
                }
            },
            "substrates": {
                aa: {
                    "_default": float(self.parameters["substrate_default"]),
                    "_updater": "accumulate",
                    "_emit": True,
                }
                for aa in self.aa_ids
            },
            "complex": {
                "counts": {
                    _RIBOSOME_ACTIVE_WID: {
                        "_default": float(self._fallback_n_active_ribosomes),
                        "_updater": "accumulate",
                        "_emit": False,
                    }
                }
            },
        }

    def _step_protein(self, counts: np.ndarray, synth_per_s: np.ndarray, dt_s: float) -> np.ndarray:
        decay = self.kinetics_model.decay_rate_per_s
        out = np.empty_like(counts)
        no_decay = decay <= 0.0
        if np.any(~no_decay):
            idx = ~no_decay
            ss = synth_per_s[idx] / decay[idx]
            out[idx] = ss + (counts[idx] - ss) * np.exp(-decay[idx] * dt_s)
        if np.any(no_decay):
            out[no_decay] = counts[no_decay] + synth_per_s[no_decay] * dt_s
        return out

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        counts = np.array(
            [float(states["protein"]["counts"][pid]) for pid in self.protein_ids],
            dtype=float,
        )

        complex_counts = states.get("complex", {}).get("counts", {})
        # DYNAMIC: read per-tick; do not cache. d2-stub writes nothing today but D.2-real will.
        n_active_ribosomes = float(
            complex_counts.get(_RIBOSOME_ACTIVE_WID, self._fallback_n_active_ribosomes)
        )
        if n_active_ribosomes < 0.0:
            n_active_ribosomes = 0.0

        synth_per_s = tl_v2.predict_synthesis_per_s(
            self.mechanism_inputs, n_active=n_active_ribosomes
        )
        protein_next = self._step_protein(counts, synth_per_s, timestep)

        update: dict[str, Any] = {
            "protein": {
                "counts": {
                    pid: float(protein_next[i] - counts[i]) for i, pid in enumerate(self.protein_ids)
                }
            }
        }

        if self.parameters["write_substrate_deltas"]:
            per_metabolite = (synth_per_s[:, None] * self.kinetics_model.base_counts).sum(axis=0)
            update["substrates"] = {
                aa: -float(per_metabolite[col]) * timestep
                for aa, col in zip(
                    self.aa_ids, self.kinetics_model.aa_col_indices, strict=False
                )
            }
        return update
