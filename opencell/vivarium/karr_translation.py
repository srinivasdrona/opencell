"""Vivarium Process wrapper for Karr-native M3 translation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.m3 import translation as tl

_DEFAULT_TRANSLATION_FIXTURE_PATH = "data/karr_fixtures/per_process/Translation_flat.mat"


def _resolve_fixture_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


def _parse_wid_array(value: object) -> list[str]:
    values = np.asarray(value, dtype=object)
    out: list[str] = []
    for raw in values.ravel():
        item: object = raw
        while isinstance(item, np.ndarray):
            if item.size == 0:
                item = ""
                break
            item = item.flat[0]
        out.append(str(item))
    return out


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
        "fixture_path": _DEFAULT_TRANSLATION_FIXTURE_PATH,
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
        self.enzyme_wids = self._load_enzyme_wids(self.parameters["fixture_path"])

    def _load_enzyme_wids(self, fixture_path: str | Path) -> list[str]:
        try:
            resolved = _resolve_fixture_path(fixture_path)
            fixture = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)["data"].fixture
        except Exception:
            return []
        enzyme_ids = getattr(fixture, "enzymeWholeCellModelIDs", None)
        if enzyme_ids is None:
            return []
        return _parse_wid_array(enzyme_ids)

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
