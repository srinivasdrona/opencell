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
        "use_allocator_budget": False,
        "substrate_default": 0.0,
        "rng_seed": 0,
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
        self.enzyme_wids = ("MG_173_MONOMER", "MG_142_MONOMER", "MG_196_MONOMER", "MG_089_DIMER", "MG_026_MONOMER", "MG_451_DIMER", "MG_433_DIMER", "MG_258_MONOMER", "MG_435_MONOMER", "RIBOSOME_30S", "RIBOSOME_30S_IF3", "RIBOSOME_50S", "RIBOSOME_70S", "MG_0004", "MG_059_MONOMER", "MG_083_MONOMER")
        if len(self.protein_ids) != self.mechanism_inputs.n_proteins:
            raise ValueError(
                "M3 v2 wrapper expects matching protein dimensions: "
                f"kinetics={len(self.protein_ids)} mechanism={self.mechanism_inputs.n_proteins}"
            )

        self.aa_ids = self.kinetics_model.aa_wcm_ids
        self.allocation_substrate_wids: tuple[str, ...] = tuple(self.aa_ids)
        self._fallback_n_active_ribosomes = int(self.mechanism_inputs.n_active_ribosomes)
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

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
                out[aa] = float(-self._stochastic_round_nonnegative(consumed))
        return out

    def _stochastic_round_nonnegative(self, expected_count: float) -> int:
        if not np.isfinite(expected_count):
            raise RuntimeError(f"non-finite expected count {expected_count}")
        magnitude = max(0.0, float(expected_count))
        base = int(np.floor(magnitude))
        frac = float(np.clip(magnitude - float(base), 0.0, 1.0))
        return base + int(self._rng.binomial(1, frac))

    def _stochastic_round_delta(self, expected_delta: float) -> int:
        if not np.isfinite(expected_delta):
            raise RuntimeError(f"non-finite expected delta {expected_delta}")
        sign = -1 if expected_delta < 0.0 else 1
        rounded_mag = self._stochastic_round_nonnegative(abs(float(expected_delta)))
        return sign * rounded_mag

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        protein_state = states.get("protein", {})
        counts_state = protein_state.get("unprocessed_counts", protein_state.get("counts", {}))
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
                    pid: float(self._stochastic_round_delta(float(protein_next[i] - counts[i])))
                    for i, pid in enumerate(self.protein_ids)
                }
            }
        }
        p_counts = protein_state.get("counts", {})
        if isinstance(p_counts, dict):
            c_counts = states.get("complex", {}).get("counts", {})
            f_if3 = float(p_counts.get("MG_196_MONOMER", c_counts.get("MG_196_MONOMER", 0.0)))
            r30s = float(p_counts.get("RIBOSOME_30S", c_counts.get("RIBOSOME_30S", 0.0)))
            r30s_if3 = float(p_counts.get("RIBOSOME_30S_IF3", c_counts.get("RIBOSOME_30S_IF3", 0.0)))
            r50s = float(p_counts.get("RIBOSOME_50S", c_counts.get("RIBOSOME_50S", 0.0)))
            bind = int(min(max(0.0, r30s), max(0.0, f_if3)))
            init = int(min(max(0.0, r50s), max(0.0, r30s_if3 + bind)))
            if bind or init:
                p_upd = update["protein"].setdefault("counts", {})
                c_upd = update.setdefault("complex", {}).setdefault("counts", {})
                for wid, dv in (("MG_196_MONOMER", -bind + init), ("RIBOSOME_30S", -bind), ("RIBOSOME_30S_IF3", bind - init), ("RIBOSOME_50S", -init)):
                    if not dv:
                        continue
                    tgt = c_upd if wid in c_counts and wid not in p_counts else p_upd
                    tgt[wid] = float(tgt.get(wid, 0.0) + dv)

        if self.parameters["write_substrate_deltas"]:
            need_by_aa = self._predict_substrate_need(synth_per_s, timestep)
            if bool(self.parameters["use_allocator_budget"]):
                substrate_update = self._allocated_aa_deltas(need_by_aa, states)
            else:
                current_substrates = states.get("substrates", {})
                substrate_update: dict[str, float] = {}
                for aa, need in need_by_aa.items():
                    if need <= 0.0:
                        continue
                    actual = min(float(need), max(0.0, float(current_substrates.get(aa, 0.0))))
                    rounded = self._stochastic_round_nonnegative(actual)
                    if rounded > 0:
                        substrate_update[aa] = float(-rounded)
            if substrate_update:
                update["substrates"] = substrate_update
        return update
