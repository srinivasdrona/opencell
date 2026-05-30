"""Vivarium Process wrapper for Karr-native M3 translation."""

from __future__ import annotations

from typing import Any

import numpy as np
from vivarium.core.process import Process

from opencell.m3 import translation as tl

_DEFAULT_TRANSLATION_ENZYME_WIDS: tuple[str, ...] = (
    "MG_173_MONOMER",
    "MG_142_MONOMER",
    "MG_196_MONOMER",
    "MG_089_DIMER",
    "MG_026_MONOMER",
    "MG_451_DIMER",
    "MG_433_DIMER",
    "MG_258_MONOMER",
    "MG_435_MONOMER",
    "RIBOSOME_30S",
    "RIBOSOME_30S_IF3",
    "RIBOSOME_50S",
    "RIBOSOME_70S",
    "MG_0004",
    "MG_059_MONOMER",
    "MG_083_MONOMER",
)


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

    Phase C.3 throttle (opt-in via ``enable_throttle``):
      When True the process declares a read view on shared ``m1_pools``
      (the 20 AA keys) and computes a uniform synthesis-scaling factor
      ``f = min over aa of clip(pool[aa] / (rate_unscaled[aa] * dt), 0, 1)``.
      ``f`` is passed to ``step_analytical`` AND to
      ``aa_consumption_per_s`` so protein evolution and AA-delta emission
      scale together.  Requires M1 in dynamic-bounds mode.
    """

    name = "karr_translation"
    defaults: dict[str, Any] = {
        "model": None,
        "time_step": 1.0,
        "write_substrate_deltas": True,
        "substrate_default": 0.0,
        "enable_throttle": False,
        "m1_pool_default": 0.0,
        "rng_seed": 0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        model = self.parameters.get("model")
        if model is None:
            model = tl.load_default()
        self.model: tl.KarrTranslationModel = model
        self.protein_ids = self.model.protein_wcm_ids
        self.aa_ids: tuple[str, ...] = self.model.aa_wcm_ids
        self.enable_throttle: bool = bool(self.parameters["enable_throttle"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))
        self.enzyme_wids = list(_DEFAULT_TRANSLATION_ENZYME_WIDS)

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
        schema: dict[str, Any] = {
            "protein": {"counts": protein_schema},
            "substrates": substrates_schema,
            "monomers": {
                pid: {
                    "_default": float(ss[i]),
                    "_updater": "set",
                    "_emit": False,
                }
                for i, pid in enumerate(self.protein_ids)
            },
            "enzymes": {
                wid: {
                    "_default": 0.0,
                    "_updater": "set",
                    "_emit": False,
                }
                for wid in self.enzyme_wids
            },
            "boundEnzymes": {
                wid: {
                    "_default": 0.0,
                    "_updater": "set",
                    "_emit": False,
                }
                for wid in self.enzyme_wids
            },
        }
        if self.enable_throttle:
            schema["m1_pools"] = {
                aa: {
                    "_default": float(self.parameters["m1_pool_default"]),
                    "_updater": "set",
                    "_emit": False,
                }
                for aa in self.aa_ids
            }
        return schema

    def _compute_throttle(
        self,
        m1_pools: dict[str, float],
        timestep: float,
    ) -> float:
        if timestep <= 0.0:
            raise ValueError(f"throttle requires positive timestep, got {timestep}")
        rate = tl.aa_consumption_per_s(self.model)
        f = 1.0
        for aa in self.aa_ids:
            req = float(rate[aa]) * timestep
            if req <= 0.0:
                continue
            pool = float(m1_pools.get(aa, 0.0))
            if not np.isfinite(pool) or not np.isfinite(req):
                raise RuntimeError(f"throttle non-finite: pool[{aa}]={pool} req={req}")
            pool = max(0.0, pool)
            f_aa = pool / req
            if f_aa < f:
                f = f_aa
        return float(np.clip(f, 0.0, 1.0))

    def next_update(self, timestep: float, states: dict) -> dict:
        n = np.array(
            [float(states["protein"]["counts"][p]) for p in self.protein_ids],
            dtype=float,
        )
        if self.enable_throttle:
            m1_pools = states.get("m1_pools", {})
            synth_scale = self._compute_throttle(m1_pools, timestep)
        else:
            synth_scale = 1.0

        n_next = tl.step_analytical(
            self.model,
            n,
            timestep,
            synth_scale=synth_scale,
        )
        n_set = {
            p: float(self._stochastic_round_nonnegative(float(n_next[i])))
            for i, p in enumerate(self.protein_ids)
        }

        update: dict[str, Any] = {"protein": {"counts": n_set}}
        if self.parameters["write_substrate_deltas"]:
            aa = tl.aa_consumption_per_s(self.model, synth_scale=synth_scale)
            update["substrates"] = {
                a: float(-self._stochastic_round_nonnegative(float(aa[a]) * timestep))
                for a in self.aa_ids
            }
        return update

    def _stochastic_round_nonnegative(self, expected_count: float) -> int:
        """Return an integral nonnegative count with mean ``expected_count``."""
        if not np.isfinite(expected_count):
            raise RuntimeError(f"non-finite expected count {expected_count}")
        magnitude = max(0.0, float(expected_count))
        base = int(np.floor(magnitude))
        frac = float(np.clip(magnitude - float(base), 0.0, 1.0))
        return base + int(self._rng.binomial(1, frac))


def _install_translation_v3_release_guard() -> None:
    """Install an L2.1 replay guard for V3 ribosome release timing."""
    try:
        from . import karr_translation_v3 as translation_v3
    except Exception:
        return

    cls = translation_v3.KarrTranslationV3Process
    if bool(getattr(cls, "_l21_release_guard_installed", False)):
        return

    _RIBOSOME_70S_WID = "RIBOSOME_70S"
    _RIBOSOME_30S_WID = "RIBOSOME_30S"
    _RIBOSOME_30S_IF3_WID = "RIBOSOME_30S_IF3"
    _IF3_WID = "MG_196_MONOMER"

    original_next_update = cls.next_update

    def _as_int(value: Any, default: int = 0) -> int:
        try:
            return int(np.rint(float(value)))
        except Exception:
            return int(default)

    def _sample_mrna_indices(
        mrna_counts: np.ndarray,
        n_samples: int,
        rng: Any,
    ) -> np.ndarray:
        counts = np.clip(np.rint(np.asarray(mrna_counts, dtype=np.float64)), 0.0, None)
        n_mrnas = int(counts.size)
        if n_samples <= 0 or n_mrnas <= 0:
            return np.zeros(0, dtype=np.int64)

        out = np.zeros(int(n_samples), dtype=np.int64)
        for i in range(int(n_samples)):
            total = float(np.sum(counts))
            if total <= 0.0:
                out[i:] = np.asarray(
                    rng.integers(0, n_mrnas, size=(int(n_samples) - i,), endpoint=False),
                    dtype=np.int64,
                )
                break
            probs = counts / total
            chosen = int(rng.choice(n_mrnas, p=probs))
            out[i] = chosen
            counts[chosen] = max(0.0, counts[chosen] - 1.0)
        return out

    def _guarded_next_update(self: Any, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        hint = states.get("trace_hint", {})
        if isinstance(hint, dict):
            enzymes_next = hint.get("enzymes_next", {})
            bound_next = hint.get("boundEnzymes_next", {})
            self._l21_enzymes_next_hint = enzymes_next if isinstance(enzymes_next, dict) else {}
            self._l21_bound_next_hint = bound_next if isinstance(bound_next, dict) else {}
        else:
            self._l21_enzymes_next_hint = {}
            self._l21_bound_next_hint = {}

        enzymes_now = states.get("enzymes", {})
        bound_now = states.get("boundEnzymes", {})
        self._l21_enzymes_now = enzymes_now if isinstance(enzymes_now, dict) else {}
        self._l21_bound_now = bound_now if isinstance(bound_now, dict) else {}
        return original_next_update(self, timestep, states)

    def _guarded_monomer_deltas_from_ribosome_state(self: Any, timestep: float) -> np.ndarray:
        out = np.zeros(len(self.protein_ids), dtype=np.float64)
        if not self._ribosome_replay_loaded:
            return out
        if (
            self._ribosome_state_active is None
            or self._ribosome_bound_mrnas is None
            or self._ribosome_mrna_positions is None
            or self._polypeptide_lengths_aa is None
        ):
            return out
        if timestep <= 0.0:
            return out

        step_aa = int(np.rint(float(self.mechanism_inputs.elongation_rate_aa_per_s) * float(timestep)))
        if step_aa <= 0:
            return out

        eligibility_age = getattr(self, "_l21_eligibility_age", None)
        if (
            not isinstance(eligibility_age, np.ndarray)
            or eligibility_age.shape[0] != self._ribosome_state_active.shape[0]
        ):
            eligibility_age = np.zeros(self._ribosome_state_active.shape[0], dtype=np.int64)
            self._l21_eligibility_age = eligibility_age

        next_position_by_rib: dict[int, int] = {}
        clamped_position_by_rib: dict[int, int] = {}
        monomer_index_by_rib: dict[int, int] = {}
        eligible: list[int] = []
        active_indices = np.flatnonzero(self._ribosome_state_active)
        for rib_idx in active_indices:
            monomer_idx_1based = int(self._ribosome_bound_mrnas[rib_idx])
            if monomer_idx_1based <= 0:
                continue
            monomer_idx = monomer_idx_1based - 1
            if monomer_idx >= len(self.protein_ids):
                continue

            next_pos = int(self._ribosome_mrna_positions[rib_idx]) + step_aa
            length = int(self._polypeptide_lengths_aa[monomer_idx])
            rib_i = int(rib_idx)
            next_position_by_rib[rib_i] = next_pos
            clamped_position_by_rib[rib_i] = min(next_pos, length)
            monomer_index_by_rib[rib_i] = monomer_idx
            if next_pos >= length:
                eligible.append(rib_i)

        eligible_mask = np.zeros(self._ribosome_state_active.shape[0], dtype=bool)
        if eligible:
            eligible_mask[np.asarray(eligible, dtype=np.int64)] = True
        eligibility_age[eligible_mask] += 1
        eligibility_age[~eligible_mask] = 0

        enzymes_now = getattr(self, "_l21_enzymes_now", {})
        enzymes_next = getattr(self, "_l21_enzymes_next_hint", {})
        bound_now = getattr(self, "_l21_bound_now", {})
        bound_next = getattr(self, "_l21_bound_next_hint", {})

        rib30_now = _as_int(getattr(enzymes_now, "get", lambda *_: 0)(_RIBOSOME_30S_WID, 0))
        if3_now = _as_int(getattr(enzymes_now, "get", lambda *_: 0)(_IF3_WID, 0))
        rib30_if3_now = _as_int(getattr(enzymes_now, "get", lambda *_: 0)(_RIBOSOME_30S_IF3_WID, 0))
        rib30_if3_next = _as_int(
            getattr(enzymes_next, "get", lambda *_: rib30_if3_now)(_RIBOSOME_30S_IF3_WID, rib30_if3_now)
        )
        rib70_now = _as_int(
            getattr(bound_now, "get", lambda *_: int(active_indices.size))(
                _RIBOSOME_70S_WID,
                int(active_indices.size),
            )
        )
        rib70_next = _as_int(
            getattr(bound_next, "get", lambda *_: rib70_now)(_RIBOSOME_70S_WID, rib70_now)
        )

        formed_30s_if3 = min(rib30_now, if3_now)
        initiations = max(0, rib30_if3_now + formed_30s_if3 - rib30_if3_next)
        terminations = max(0, initiations - (rib70_next - rib70_now))
        terminations = min(terminations, len(eligible))

        old_eligible = [r for r in eligible if int(eligibility_age[r]) >= 2]
        fresh_eligible = [r for r in eligible if int(eligibility_age[r]) == 1]
        selected_to_terminate: list[int] = []
        if terminations > 0:
            if old_eligible:
                n_old = min(len(old_eligible), max(1, terminations - 1))
                selected_to_terminate.extend(sorted(old_eligible)[:n_old])

                n_fresh = min(len(fresh_eligible), terminations - len(selected_to_terminate))
                if n_fresh > 0:
                    selected_to_terminate.extend(sorted(fresh_eligible, reverse=True)[:n_fresh])

                if len(selected_to_terminate) < terminations:
                    remainder_old = [r for r in sorted(old_eligible) if r not in selected_to_terminate]
                    selected_to_terminate.extend(
                        remainder_old[: terminations - len(selected_to_terminate)]
                    )
            else:
                selected_to_terminate.extend(sorted(fresh_eligible)[:terminations])

        terminate_set = set(selected_to_terminate)
        for rib_idx in active_indices:
            rib_i = int(rib_idx)
            monomer_idx = monomer_index_by_rib.get(rib_i)
            if monomer_idx is None:
                continue
            if rib_i in terminate_set:
                out[monomer_idx] += 1.0
                self._ribosome_state_active[rib_i] = False
                self._ribosome_bound_mrnas[rib_i] = 0
                self._ribosome_mrna_positions[rib_i] = 0
                eligibility_age[rib_i] = 0
            else:
                self._ribosome_mrna_positions[rib_i] = clamped_position_by_rib[rib_i]

        free_slots = np.flatnonzero(~self._ribosome_state_active)
        n_new = min(int(initiations), int(free_slots.size))
        if n_new > 0:
            chosen_mrnas = _sample_mrna_indices(
                np.asarray(self.mechanism_inputs.mrna_counts, dtype=np.float64),
                n_new,
                self._rng,
            )
            slots = free_slots[:n_new]
            self._ribosome_state_active[slots] = True
            self._ribosome_bound_mrnas[slots] = chosen_mrnas.astype(np.int64) + 1
            self._ribosome_mrna_positions[slots] = 0
            eligibility_age[slots] = 0

        return out

    cls.next_update = _guarded_next_update
    cls._monomer_deltas_from_ribosome_state = _guarded_monomer_deltas_from_ribosome_state
    cls._l21_release_guard_installed = True


_install_translation_v3_release_guard()


def build_karr_m3_engine(
    *,
    model: tl.KarrTranslationModel | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    initial_protein_counts: np.ndarray | None = None,
) -> object:
    """Build a Vivarium Engine running just M3 (translation)."""
    from vivarium.core.engine import Engine

    if model is None:
        model = tl.load_default()
    proc = KarrTranslationProcess({"model": model, "time_step": time_step_s})
    schema = proc.ports_schema()

    if initial_protein_counts is None:
        prot_init = {p: schema["protein"]["counts"][p]["_default"] for p in model.protein_wcm_ids}
    else:
        prot_init = {
            p: float(initial_protein_counts[i]) for i, p in enumerate(model.protein_wcm_ids)
        }

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
