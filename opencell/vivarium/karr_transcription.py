"""Vivarium Process wrapper for Karr-native M2 transcription."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.m2 import transcription as tx

_M2_CONSUMED_SUBSTRATES: tuple[str, ...] = ("ATP", "CTP", "GTP", "UTP")
_DEFAULT_TX_FIXTURE_PATH = "data/karr_fixtures/per_process/Transcription_flat.mat"


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


class KarrTranscriptionProcess(Process):
    """1-second-tick analytical integrator of Karr-prescribed RNA dynamics.

    For every 525 genes:  dRNA_i/dt = s_i - k_i * RNA_i, integrated in
    closed form per tick.  Writes:
      - rna.counts (525-dict by WCM ID, 'set' updater)
      - substrates.{ATP,CTP,GTP,UTP} (deltas, 'accumulate', negative)

    `condition` parameter (0/1/2) selects synthesis-rate column.  Default
    1 (Karr's mean condition).

    Phase C.3 throttle (opt-in via ``enable_throttle``):
      When True the process ALSO declares a read view on the shared
      ``m1_pools`` store (4 NTP keys) and computes a uniform
      synthesis-scaling factor ``f`` per tick:

          f = min over ntp in {ATP,CTP,GTP,UTP} of
              clip(pool[ntp] / (rate_unscaled[ntp] * dt), 0, 1)

      That ``f`` is passed to ``step_analytical`` AND to
      ``ntp_consumption_per_s`` so RNA evolution and substrate-delta
      emission scale together (no over-draining).  Required when on:
      M1 must be in dynamic-bounds mode so ``m1_pools`` exists.
    """

    name = "karr_transcription"
    defaults: dict[str, Any] = {
        "model": None,
        "fixture_path": _DEFAULT_TX_FIXTURE_PATH,
        "time_step": 1.0,
        "condition": 1,
        "write_substrate_deltas": True,
        "substrate_default": 0.0,
        "enable_throttle": False,
        "m1_pool_default": 0.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        model = self.parameters.get("model")
        if model is None:
            model = tx.load_default()
        self.model: tx.KarrTranscriptionModel = model
        self.condition = int(self.parameters["condition"])
        self.gene_ids = self.model.gene_wcm_ids
        self.enable_throttle: bool = bool(self.parameters["enable_throttle"])
        self.consumed_substrates: tuple[str, ...] = _M2_CONSUMED_SUBSTRATES
        self.enzyme_wids = self._load_enzyme_wids(self.parameters["fixture_path"])

        # E.1b calibration: build a chassis-operative model whose
        # synthesis rate is recalibrated so dRNA/dt = 0 at counts_mature.
        # The KB-fitted synthesis rate (model.synthesis_rate_per_s)
        # interpreted as molecules-per-second yields s/k = expression
        # column 1 (~41327 total mRNA SS), but Karr's actual State_Rna
        # mature cytosol total is 784.  Karr's "expression" is a relative
        # microarray field, NOT an absolute count.  We rescale per-gene
        # synthesis rate so s/k = counts_mature, preserving SS at the
        # true Karr count and keeping all downstream NTP-consumption /
        # throttle arithmetic consistent.  ``counts_mature`` is per
        # condition (low/mean/high), so the calibrated synthesis rate
        # is also per condition; this process picks the column matching
        # ``self.condition`` at runtime.  The pure-M2 oracle tests
        # continue to use the untouched ``model`` (KB convention).
        self._chassis_model = tx.calibrated_chassis_model(model)

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
        # Initial RNA counts: Karr State_Rna mature cytosol counts
        # (counts_mature, ingested in M2 fixture v4 as a per-condition
        # 2-D array).  We pick the column matching ``self.condition``
        # so the chassis SS matches the per-condition synthesis rate
        # used by ``step_analytical`` and ``ntp_consumption_per_s``.
        # This replaces the v1/v2 wiring that used expression[:, condition]
        # -- a transcription-rate (per-minute) field, not a count -- which
        # over-stated SS RNA molecule counts ~53x and broke the cell-mass
        # aggregator (Phase E.1b finding).
        ss = self.model.counts_mature[:, self.condition]
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
                "_default": float(self.parameters["substrate_default"]),
                "_updater": "accumulate",
                "_emit": True,
            }
            for ntp in self.consumed_substrates
        }
        schema: dict[str, Any] = {
            "rna": {"counts": rna_schema},
            "substrates": substrates_schema,
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
            # Read view on m1_pools.  M1 owns the authoritative leaf
            # settings; we declare matching subset so port-merge is a
            # no-op.  We never emit a real m1_pools update.
            schema["m1_pools"] = {
                ntp: {
                    "_default": float(self.parameters["m1_pool_default"]),
                    "_updater": "set",
                    "_emit": False,
                }
                for ntp in self.consumed_substrates
            }
        return schema

    def _compute_throttle(
        self,
        m1_pools: dict[str, float],
        timestep: float,
    ) -> float:
        """Return clip-to-[0,1] synthesis scale based on m1_pools head-room.

        ``f = min over consumed s of (pool[s] / (rate[s] * dt))`` capped
        at 1.0.  Substrates with rate==0 don't constrain.  Non-finite
        pools/rates raise; negative pools are treated as 0.
        """
        if timestep <= 0.0:
            raise ValueError(f"throttle requires positive timestep, got {timestep}")
        # Unscaled rate at synth_scale=1.0 — what we'd consume if free.
        rate = tx.ntp_consumption_per_s(self._chassis_model, condition=self.condition)
        f = 1.0
        for s in self.consumed_substrates:
            req = float(rate[s]) * timestep
            if req <= 0.0:
                continue
            pool = float(m1_pools.get(s, 0.0))
            if not np.isfinite(pool) or not np.isfinite(req):
                raise RuntimeError(f"throttle non-finite: pool[{s}]={pool} req={req}")
            pool = max(0.0, pool)
            f_s = pool / req
            if f_s < f:
                f = f_s
        return float(np.clip(f, 0.0, 1.0))

    def next_update(self, timestep: float, states: dict) -> dict:
        rna = np.array(
            [float(states["rna"]["counts"][g]) for g in self.gene_ids],
            dtype=float,
        )
        if self.enable_throttle:
            m1_pools = states.get("m1_pools", {})
            synth_scale = self._compute_throttle(m1_pools, timestep)
        else:
            synth_scale = 1.0

        rna_next = tx.step_analytical(
            self._chassis_model,
            rna,
            timestep,
            condition=self.condition,
            synth_scale=synth_scale,
        )
        rna_set = {g: float(rna_next[i]) for i, g in enumerate(self.gene_ids)}

        update: dict[str, Any] = {"rna": {"counts": rna_set}}
        if self.parameters["write_substrate_deltas"]:
            ntp = tx.ntp_consumption_per_s(
                self._chassis_model,
                condition=self.condition,
                synth_scale=synth_scale,
            )
            update["substrates"] = {s: -ntp[s] * timestep for s in self.consumed_substrates}
        return update


def build_karr_m2_engine(
    *,
    model: tx.KarrTranscriptionModel | None = None,
    time_step_s: float = 1.0,
    emit_step_s: float | None = None,
    initial_rna_counts: np.ndarray | None = None,
) -> object:
    """Build a Vivarium Engine running just M2 (transcription)."""
    from vivarium.core.engine import Engine

    if model is None:
        model = tx.load_default()
    proc = KarrTranscriptionProcess({"model": model, "time_step": time_step_s})
    schema = proc.ports_schema()

    if initial_rna_counts is None:
        rna_init = {g: schema["rna"]["counts"][g]["_default"] for g in model.gene_wcm_ids}
    else:
        rna_init = {g: float(initial_rna_counts[i]) for i, g in enumerate(model.gene_wcm_ids)}

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
