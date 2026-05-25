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
  :class:`opencell.vivarium.karr_macromolecular_complexation_stub.MacromolecularComplexationStubProcess`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from vivarium.core.process import Process

from opencell.m2 import transcription as tx
from opencell.m2 import transcription_v2 as tx_v2

_M2_CONSUMED_SUBSTRATES: tuple[str, ...] = ("ATP", "CTP", "GTP", "UTP")
_RNAP_COUNT_WID = "RNA_POLYMERASE"


class KarrTranscriptionV3Process(Process):
    """Mechanism-driven transcription wrapper for the central-dogma chassis.

    Optional regulation input:
    - Reads ``tx_rate_fold_change`` as a per-transcription-unit multiplier.
    - When this port is not wired, synthesis remains bit-identical to the
      pre-regulation implementation.
    """

    name = "karr_transcription_v3"
    defaults: dict[str, Any] = {
        "kinetics_model": None,
        "mechanism_inputs": None,
        "time_step": 1.0,
        "write_substrate_deltas": True,
        "use_allocator_budget": False,
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
        self.tu_wids = tuple(f"TU_{idx + 1:03d}" for idx in range(len(self.gene_ids)))
        self._gene_idx_by_wid = {wid: idx for idx, wid in enumerate(self.gene_ids)}
        self._tu_idx_by_wid = {wid: idx for idx, wid in enumerate(self.tu_wids)}
        if len(self.gene_ids) != self.mechanism_inputs.n_genes:
            raise ValueError(
                "M2 v2 wrapper expects matching gene dimensions: "
                f"kinetics={len(self.gene_ids)} mechanism={self.mechanism_inputs.n_genes}"
            )

        self.consumed_substrates: tuple[str, ...] = _M2_CONSUMED_SUBSTRATES
        self.allocation_substrate_wids: tuple[str, ...] = self.consumed_substrates
        self._fallback_n_active_rnap = int(self.mechanism_inputs.n_active_rnap)
        target_total_per_s = float(np.sum(self.kinetics_model.synthesis_rate_per_s[:, 1]))
        pred_total_per_s = float(
            np.sum(
                tx_v2.predict_gene_synthesis_per_s(
                    self.mechanism_inputs,
                    n_active=self._fallback_n_active_rnap,
                )
            )
        )
        if pred_total_per_s <= 0.0 or not np.isfinite(pred_total_per_s):
            raise ValueError(
                "Bug 7: mechanism predicted total synthesis non-positive "
                f"({pred_total_per_s}); cannot derive calibration scale."
            )
        self._mechanism_scale: float = target_total_per_s / pred_total_per_s

    def ports_schema(self) -> dict[str, Any]:
        rna_ss = self.kinetics_model.counts_mature[:, 1]
        schema: dict[str, Any] = {
            "rna": {
                "counts": {
                    gid: {
                        "_default": float(rna_ss[i]),
                        "_updater": "accumulate",
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
            "tx_rate_fold_change": {
                tu_wid: {"_default": 1.0, "_updater": "set", "_emit": False}
                for tu_wid in self.tu_wids
            },
        }
        if bool(self.parameters["use_allocator_budget"]):
            schema["substrates_allocated"] = {
                self.name: {
                    wid: {"_default": 0.0, "_emit": False} for wid in self.allocation_substrate_wids
                }
            }
        return schema

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

    def _predict_total_nt_polymerization_per_s(self, n_active_rnap: float) -> float:
        total_nt = tx_v2.total_nt_polymerization_per_s(
            self.mechanism_inputs,
            n_active=n_active_rnap,
        )
        return float(total_nt * self._mechanism_scale)

    def _allocated_ntp_deltas(
        self,
        timestep: float,
        states: dict[str, Any],
        n_active_rnap: float,
    ) -> dict[str, float]:
        total_nt = self._predict_total_nt_polymerization_per_s(n_active_rnap)
        per_ntp_need = max(0.0, total_nt / 4.0 * float(timestep))
        allocated = states.get("substrates_allocated", {}).get(self.name, {})
        out: dict[str, float] = {}
        for ntp in self.consumed_substrates:
            budget = max(0.0, float(allocated.get(ntp, 0.0)))
            consumed = min(per_ntp_need, budget)
            if consumed > 0.0:
                out[ntp] = -consumed
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
        fold_changes = states.get("tx_rate_fold_change", {})
        if fold_changes:
            multipliers = np.ones_like(synth_gene_per_s, dtype=float)
            for tu_wid, raw_multiplier in fold_changes.items():
                idx: int | None = None
                if tu_wid in self._gene_idx_by_wid:
                    idx = self._gene_idx_by_wid[tu_wid]
                elif tu_wid in self._tu_idx_by_wid:
                    idx = self._tu_idx_by_wid[tu_wid]
                elif isinstance(tu_wid, str) and tu_wid.startswith("TU_"):
                    try:
                        parsed = int(tu_wid[3:]) - 1
                    except ValueError:
                        parsed = -1
                    if 0 <= parsed < multipliers.size:
                        idx = parsed
                if idx is not None:
                    multipliers[idx] = float(raw_multiplier)
            synth_gene_per_s = synth_gene_per_s * multipliers
        # Bug 7: calibrate mechanism rate to Karr chassis target.
        # Scaling preserves relative TU distribution but anchors the
        # global total to kinetics_model.synthesis_rate_per_s.
        synth_gene_per_s = synth_gene_per_s * self._mechanism_scale
        rna_next = self._step_rna(rna, synth_gene_per_s, timestep)

        update: dict[str, Any] = {
            "rna": {
                "counts": {gid: float(rna_next[i] - rna[i]) for i, gid in enumerate(self.gene_ids)}
            }
        }
        if self.parameters["write_substrate_deltas"]:
            if bool(self.parameters["use_allocator_budget"]):
                substrate_update = self._allocated_ntp_deltas(timestep, states, n_active_rnap)
            else:
                total_nt = self._predict_total_nt_polymerization_per_s(n_active_rnap)
                per_ntp = max(0.0, total_nt / 4.0) * float(timestep)
                substrate_update = {
                    ntp: -per_ntp for ntp in self.consumed_substrates if per_ntp > 0.0
                }
            if substrate_update:
                update["substrates"] = substrate_update
        return update
