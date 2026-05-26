"""Karr translation v3 -- Karr-light port of MATLAB +process/Translation.m

SCOPE DECLARATION (non-parity)
==============================

This module is a **deliberate scope reduction** of Karr's MATLAB
`Translation.m::evolveState`. It is NOT a faithful per-line port.
This declaration also applies to `karr_translation_v2.py` and
`karr_translation.py`.

Karr-light reductions vs `Translation.m::evolveState`:

  1. Coarse, deterministic rate wrapper. No event ordering. MATLAB shuffles
     subfunctions per tick with `randperm`.
  2. No stochastic draws. MATLAB uses `stochasticRound` and `randsample` for
     ribosome-event scheduling.
  3. Full substrate write-back semantics absent. MATLAB updates GTP/ATP/H2O/PI/H
     pools alongside polymerization; this module updates only the limited subset
     in the allocation contract.
  4. No per-codon sequence chemistry. MATLAB iterates codons; this module uses
     aggregate rate * dt.

Preserved:
  - Overall translation-rate intent (residues/sec * ribosomes).
  - Output contract for downstream modules.

OpenCell additions:
  - n_active_ribosomes clamp (axis-C ✗ at line 159; remove or gate during P3 cleanup).
  - allocation-port indirection.

Audit: Track-P2 (2026-05-26). Karr-light status: declared.

---

Vivarium Process wrapper for M3 v2 mechanism-based translation.

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
        "use_allocator_budget": False,
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
        self.allocation_substrate_wids: tuple[str, ...] = tuple(self.aa_ids)
        self._fallback_n_active_ribosomes = int(self.mechanism_inputs.n_active_ribosomes)

    def ports_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {
            "protein": {
                "unprocessed_counts": {
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
        if bool(self.parameters["use_allocator_budget"]):
            schema["substrates_allocated"] = {
                self.name: {
                    wid: {"_default": 0.0, "_emit": False} for wid in self.allocation_substrate_wids
                }
            }
        return schema

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

    def _predict_substrate_need(
        self,
        synth_per_s: np.ndarray,
        timestep: float,
    ) -> dict[str, float]:
        per_metabolite = (synth_per_s[:, None] * self.kinetics_model.base_counts).sum(axis=0)
        return {
            aa: max(0.0, float(per_metabolite[col]) * float(timestep))
            for aa, col in zip(self.aa_ids, self.kinetics_model.aa_col_indices, strict=False)
        }

    def _allocated_aa_deltas(
        self,
        need_by_aa: dict[str, float],
        states: dict[str, Any],
    ) -> dict[str, float]:
        allocated = states.get("substrates_allocated", {}).get(self.name, {})
        out: dict[str, float] = {}
        for aa, need in need_by_aa.items():
            if need <= 0.0:
                continue
            budget = max(0.0, float(allocated.get(aa, 0.0)))
            consumed = min(need, budget)
            if consumed > 0.0:
                out[aa] = -consumed
        return out

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        protein_state = states.get("protein", {})
        counts_state = protein_state.get("counts", protein_state.get("unprocessed_counts", {}))
        counts = np.array(
            [
                float(counts_state.get(pid, self.kinetics_model.counts_mature[i]))
                for i, pid in enumerate(self.protein_ids)
            ],
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
                "unprocessed_counts": {
                    pid: float(protein_next[i] - counts[i])
                    for i, pid in enumerate(self.protein_ids)
                }
            }
        }

        if self.parameters["write_substrate_deltas"]:
            need_by_aa = self._predict_substrate_need(synth_per_s, timestep)
            if bool(self.parameters["use_allocator_budget"]):
                substrate_update = self._allocated_aa_deltas(need_by_aa, states)
            else:
                substrate_update = {aa: -need for aa, need in need_by_aa.items() if need > 0.0}
            if substrate_update:
                update["substrates"] = substrate_update
        return update
