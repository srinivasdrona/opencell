"""Vivarium Process port of Karr ChromosomeCondensation (Karr-light v1).

Karr-light v1 scope:
- Tracks aggregate SMC occupancy (`chromosome.smc_bound_count`) instead of
  per-position loop topology on each chromosome.
- Tracks aggregate compaction (`chromosome.condensation_level` in [0, 1]).
- Couples to replication loosely by pausing/reducing binding when forks pass.

Deferred to v2:
- Region-level binding probabilities p(L), p(x) over explicit chromosome spans.
- Base-position footprint exclusion and explicit replication-bubble geometry.
- Per-loop topology and chromosome-specific occupancy maps.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ChromosomeCondensation_flat.mat"
_DEFAULT_TRACE_PATH = (
    "data/m1_sources/karr_native/per_process_traces/ChromosomeCondensation_100ticks.mat"
)


def _resolve_data_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    # Trace files may exist in /mnt/e/opencell (main checkout) during worktree runs.
    mounted_root = Path("/mnt/e/opencell")
    mounted = mounted_root / candidate
    if mounted.exists():
        return mounted

    raise FileNotFoundError(f"Data file not found: {path}")


def _coerce_scalar(value: object) -> object:
    out = value
    while isinstance(out, np.ndarray):
        if out.size == 0:
            return 0
        out = out.flat[0]
    return out


def _parse_wid_array(value: object) -> list[str]:
    values = np.asarray(value, dtype=object)
    out: list[str] = []
    for raw in values.ravel():
        out.append(str(_coerce_scalar(raw)))
    return out


def _safe_floor_nonneg(value: float) -> int:
    return max(0, int(math.floor(float(value))))


def _safe_clip01(value: float) -> float:
    return float(np.clip(float(value), a_min=0.0, a_max=1.0))


class KarrChromosomeCondensationProcess(Process):
    """Karr Process_ChromosomeCondensation aggregate SMC condensation model."""

    name = "karr_chromosome_condensation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "trace_path": _DEFAULT_TRACE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "genome_length_bp": 580_076.0,
        "binding_relaxation_time_s": 120.0,
        "displacement_rate_per_s": 2.0e-3,
        "condensation_tau_s": 40.0,
        "atp_half_saturation": 500.0,
        "elongation_binding_scale": 0.35,
        "elongation_condensation_scale": 0.92,
        "fork_pause_probability": 0.5,
        "trace_gap_tolerance_for_binding": 5.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._load_trace_anchor(self.parameters["trace_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        self._total_smc_pool = int(
            self._fixture_enzyme_smc + self._fixture_enzyme_smc_adp + self.trace_anchor_bound
        )
        self._bound_smc = int(self.trace_anchor_bound)
        self._free_smc = int(min(self._fixture_enzyme_smc, self._total_smc_pool - self._bound_smc))
        self._free_smc_adp = int(max(0, self._total_smc_pool - self._bound_smc - self._free_smc))
        self._initialized = False

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_data_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.substrate_wids = _parse_wid_array(fx.substrateWholeCellModelIDs)
        self.enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)

        self.substrate_index_atp = int(_coerce_scalar(fx.substrateIndexs_atp)) - 1
        self.substrate_index_adp = int(_coerce_scalar(fx.substrateIndexs_adp)) - 1
        self.substrate_index_pi = int(_coerce_scalar(fx.substrateIndexs_phosphate)) - 1
        self.substrate_index_water = int(_coerce_scalar(fx.substrateIndexs_water)) - 1
        self.substrate_index_h = int(_coerce_scalar(fx.substrateIndexs_hydrogen)) - 1

        self.atp_wid = self.substrate_wids[self.substrate_index_atp]
        self.adp_wid = self.substrate_wids[self.substrate_index_adp]
        self.pi_wid = self.substrate_wids[self.substrate_index_pi]
        self.water_wid = self.substrate_wids[self.substrate_index_water]
        self.hydrogen_wid = self.substrate_wids[self.substrate_index_h]

        self.enzyme_index_smc = int(_coerce_scalar(fx.enzymeIndexs_SMC)) - 1
        self.enzyme_index_smc_adp = int(_coerce_scalar(fx.enzymeIndexs_SMC_ADP)) - 1

        self.smc_wid = self.enzyme_wids[self.enzyme_index_smc]
        self.smc_adp_wid = self.enzyme_wids[self.enzyme_index_smc_adp]

        enzymes = np.asarray(fx.enzymes, dtype=np.int64).reshape(-1)
        bound_enzymes = np.asarray(fx.boundEnzymes, dtype=np.int64).reshape(-1)

        self._fixture_enzyme_smc = int(max(0, enzymes[self.enzyme_index_smc]))
        self._fixture_enzyme_smc_adp = int(max(0, enzymes[self.enzyme_index_smc_adp]))
        self._fixture_bound_smc_adp = int(max(0, bound_enzymes[self.enzyme_index_smc_adp]))

        self.smc_sep_nt = float(_coerce_scalar(fx.smcSepNt))
        self.smc_sep_prob_center = float(_coerce_scalar(fx.smcSepProbCenter))
        self.smc_footprint_bp = float(np.asarray(fx.enzymeDNAFootprints, dtype=np.float64).flat[0])

        substrates = np.asarray(fx.substrates, dtype=np.float64).reshape(-1)
        self._fixture_initial_atp = float(max(0.0, substrates[self.substrate_index_atp]))

    def _load_trace_anchor(self, path: str | Path) -> None:
        # Default anchor: fixture-derived baseline.
        self.trace_anchor_bound = int(self._fixture_bound_smc_adp)
        self.trace_states_after_empty = True

        try:
            resolved = _resolve_data_path(path)
        except FileNotFoundError:
            return

        with h5py.File(resolved, "r") as trace:
            before_ds = trace.get("states_before/boundEnzymes")
            if before_ds is not None and before_ds.dtype == object and before_ds.size > 0:
                ref = before_ds[()][0, 0]
                before_values = np.asarray(trace[ref][()], dtype=np.float64).reshape(-1)
                if before_values.size > self.enzyme_index_smc_adp:
                    self.trace_anchor_bound = int(
                        max(0.0, before_values[self.enzyme_index_smc_adp])
                    )

            after_ds = trace.get("states_after/boundEnzymes")
            if after_ds is not None:
                self.trace_states_after_empty = bool(
                    int(after_ds.attrs.get("MATLAB_empty", 0)) == 1
                )

    @property
    def total_smc_complexes(self) -> int:
        return int(self._total_smc_pool)

    @property
    def default_target_bound(self) -> int:
        spacing_target = int(
            round(float(self.parameters["genome_length_bp"]) / max(1.0, self.smc_sep_nt))
        )
        return max(1, min(self.total_smc_complexes, spacing_target))

    @property
    def default_condensation_level(self) -> float:
        atp_activity = self._atp_activity(self._fixture_initial_atp)
        smc_fraction = self._smc_fraction(self.trace_anchor_bound)
        return _safe_clip01(smc_fraction * atp_activity)

    def ports_schema(self) -> dict[str, Any]:
        return {
            "chromosome": {
                "smc_bound_count": {
                    "_default": float(self.trace_anchor_bound),
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "condensation_level": {
                    "_default": float(self.default_condensation_level),
                    "_updater": "accumulate",
                    "_emit": True,
                },
                # Read-only inputs from other Phase-C processes.
                "replication_state": {"_default": "idle", "_updater": "set", "_emit": False},
                "forks_passing": {"_default": False, "_updater": "set", "_emit": False},
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.substrate_wids
            },
            "enzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "boundEnzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "requests": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                    self.water_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_emit": False},
                    self.water_wid: {"_default": 0.0, "_emit": False},
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])
        chromosome_state = states.get("chromosome", {})
        current_bound = _safe_floor_nonneg(
            float(chromosome_state.get("smc_bound_count", self._bound_smc))
        )
        current_cond = _safe_clip01(
            float(chromosome_state.get("condensation_level", self.default_condensation_level))
        )
        replication_state = str(chromosome_state.get("replication_state", "idle"))
        forks_passing = bool(chromosome_state.get("forks_passing", False))

        self._sync_internal_state(current_bound)

        allocated = states.get("substrates_allocated", {}).get(self.name, {})
        available_atp = self._allocated_or_state(allocated, self.atp_wid)
        available_h2o = self._allocated_or_state(allocated, self.water_wid)

        update: dict[str, Any] = {}
        substrate_delta: dict[str, float] = {}
        start_bound = int(self._bound_smc)

        target_bound = self.default_target_bound
        gap = max(0, target_bound - self._bound_smc)

        is_elongating = replication_state == "elongating"
        fork_active = bool(forks_passing or is_elongating)
        pause_tick = bool(
            fork_active and self._rng.random() < float(self.parameters["fork_pause_probability"])
        )
        elongation_scale = (
            float(self.parameters["elongation_binding_scale"]) if fork_active and not pause_tick else 1.0
        )
        if pause_tick:
            elongation_scale = 0.0

        bind_events = self._sample_binding_events(
            dt=dt,
            gap=gap,
            available_atp=available_atp,
            available_h2o=available_h2o,
            elongation_scale=elongation_scale,
        )
        if bind_events > 0:
            self._free_smc -= bind_events
            self._bound_smc += bind_events
            substrate_delta[self.atp_wid] = substrate_delta.get(self.atp_wid, 0.0) - float(bind_events)
            substrate_delta[self.water_wid] = substrate_delta.get(self.water_wid, 0.0) - float(bind_events)
            substrate_delta[self.adp_wid] = substrate_delta.get(self.adp_wid, 0.0) + float(bind_events)
            substrate_delta[self.pi_wid] = substrate_delta.get(self.pi_wid, 0.0) + float(bind_events)
            substrate_delta[self.hydrogen_wid] = (
                substrate_delta.get(self.hydrogen_wid, 0.0) + float(bind_events)
            )

        if fork_active:
            displaced = self._sample_displacement_events(dt=dt)
            if displaced > 0:
                self._bound_smc -= displaced
                self._free_smc += displaced

        end_bound = int(self._bound_smc)
        smc_delta = end_bound - start_bound

        atp_activity = self._atp_activity(available_atp)
        smc_fraction = self._smc_fraction(end_bound)
        target_cond = _safe_clip01(smc_fraction * atp_activity)
        if fork_active:
            target_cond = _safe_clip01(
                target_cond * float(self.parameters["elongation_condensation_scale"])
            )
        cond_delta = self._condensation_delta(
            current_cond=current_cond,
            target_cond=target_cond,
            dt=dt,
        )

        chromosome_update: dict[str, float] = {}
        if smc_delta != 0:
            chromosome_update["smc_bound_count"] = float(smc_delta)
        if cond_delta != 0.0:
            chromosome_update["condensation_level"] = float(cond_delta)
        if chromosome_update:
            update["chromosome"] = chromosome_update

        substrate_update = {wid: delta for wid, delta in substrate_delta.items() if delta != 0.0}
        if substrate_update:
            update["substrates"] = substrate_update

        request_need = 0.0 if pause_tick else float(max(0, target_bound - end_bound))
        update["requests"] = {
            self.name: {
                self.atp_wid: request_need,
                self.water_wid: request_need,
            }
        }
        return update

    def _allocated_or_state(
        self,
        allocated_state: dict[str, Any],
        wid: str,
    ) -> float:
        allocated = float(allocated_state.get(wid, 0.0))
        return max(0.0, allocated)

    def _sync_internal_state(self, current_bound: int) -> None:
        target_bound = max(0, current_bound)
        if not self._initialized:
            self._bound_smc = target_bound
            free_total = max(0, self.total_smc_complexes - self._bound_smc)
            self._free_smc = min(self._free_smc, free_total)
            self._free_smc_adp = max(0, free_total - self._free_smc)
            self._initialized = True
            return

        if target_bound > self._bound_smc:
            need = target_bound - self._bound_smc
            pull_smc = min(self._free_smc, need)
            self._free_smc -= pull_smc
            self._bound_smc += pull_smc
            need -= pull_smc
            if need > 0:
                pull_adp = min(self._free_smc_adp, need)
                self._free_smc_adp -= pull_adp
                self._bound_smc += pull_adp
        elif target_bound < self._bound_smc:
            release = self._bound_smc - target_bound
            self._bound_smc -= release
            self._free_smc += release

        # Maintain non-negative pools and a fixed total SMC pool.
        self._free_smc = max(0, int(self._free_smc))
        self._free_smc_adp = max(0, int(self._free_smc_adp))
        self._bound_smc = max(0, int(self._bound_smc))

        total = self._free_smc + self._free_smc_adp + self._bound_smc
        if total != self.total_smc_complexes:
            diff = self.total_smc_complexes - total
            if diff > 0:
                self._free_smc += diff
            else:
                remove = min(self._free_smc, -diff)
                self._free_smc -= remove
                rem = -diff - remove
                if rem > 0:
                    self._free_smc_adp = max(0, self._free_smc_adp - rem)

    def _sample_binding_events(
        self,
        *,
        dt: float,
        gap: int,
        available_atp: float,
        available_h2o: float,
        elongation_scale: float,
    ) -> int:
        if gap <= 0 or dt <= 0.0:
            return 0
        max_possible = min(
            gap,
            self._free_smc,
            _safe_floor_nonneg(available_atp),
            _safe_floor_nonneg(available_h2o),
        )
        if max_possible <= 0:
            return 0

        # Trace anchor has empty states_after for this process; treat small gaps as steady-state.
        gap_tolerance = float(self.parameters["trace_gap_tolerance_for_binding"])
        if self.trace_states_after_empty and gap <= gap_tolerance:
            return 0

        relax_time = max(1.0e-9, float(self.parameters["binding_relaxation_time_s"]))
        expected = (float(gap) / relax_time) * dt * max(0.0, float(elongation_scale))
        if expected <= 0.0:
            return 0
        sampled = int(self._rng.poisson(expected))
        return int(max(0, min(sampled, max_possible)))

    def _sample_displacement_events(self, *, dt: float) -> int:
        if self._bound_smc <= 0 or dt <= 0.0:
            return 0
        rate = max(0.0, float(self.parameters["displacement_rate_per_s"]))
        expected = float(self._bound_smc) * rate * dt
        if expected <= 0.0:
            return 0
        sampled = int(self._rng.poisson(expected))
        return int(max(0, min(sampled, self._bound_smc)))

    def _atp_activity(self, atp_available: float) -> float:
        atp = max(0.0, float(atp_available))
        k_half = max(1.0e-9, float(self.parameters["atp_half_saturation"]))
        return atp / (atp + k_half)

    def _smc_fraction(self, smc_bound_count: int) -> float:
        denom = float(max(1, self.default_target_bound))
        return _safe_clip01(float(max(0, smc_bound_count)) / denom)

    def _condensation_delta(self, *, current_cond: float, target_cond: float, dt: float) -> float:
        tau = max(1.0e-9, float(self.parameters["condensation_tau_s"]))
        alpha = 1.0 - math.exp(-max(0.0, dt) / tau)
        new_cond = _safe_clip01(current_cond + alpha * (target_cond - current_cond))
        delta = new_cond - current_cond
        if not math.isfinite(delta):
            return 0.0
        return float(delta)


__all__ = ["KarrChromosomeCondensationProcess"]
