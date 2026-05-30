"""Vivarium Process for Karr DNASupercoiling (Phase C, Karr-light v1).

This implementation is intentionally light-scope for Phase C turn 3:
- tracks bulk chromosome supercoiling as a scalar (`chromosome.supercoil_density`)
- models stochastic gyrase/topoIV actions with ATP coupling
- couples replication elongation to additional positive supercoiling load

Deferred v2 scope (documented in docs/design/pc-t3-supercoiling.md):
- full region-resolved linking-number mechanics
- explicit enzyme binding/processivity and fork-collision knockoff dynamics
- topoI branch and supercoiling-driven transcription fold-change outputs
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/DNASupercoiling_flat.mat"
_DEFAULT_COMPLEXATION_FIXTURE_PATH = (
    "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"
)


def _resolve_fixture_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


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
        token = _coerce_scalar(raw)
        out.append(str(token))
    return out


def _to_finite(value: float, fallback: float) -> float:
    if not np.isfinite(value):
        return float(fallback)
    return float(value)


def _load_d2_complex_wid_set(path: str | Path) -> set[str]:
    resolved = _resolve_fixture_path(path)
    mat = loadmat(str(resolved))
    fx = mat["data"]["fixture"][0, 0]
    values = np.asarray(fx["complexWholeCellModelIDs"], dtype=object)
    if values.shape == (1, 1):
        values = np.asarray(values[0, 0], dtype=object)

    out: set[str] = set()
    for raw in values.ravel():
        value: object = raw
        while isinstance(value, np.ndarray):
            if value.size == 0:
                value = ""
                break
            value = value.flat[0]
        out.add(str(value))
    return out


class KarrDNASupercoilingProcess(Process):
    """Karr Process_DNASupercoiling (light bulk-sigma variant)."""

    name = "karr_dna_supercoiling"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "complexation_fixture_path": _DEFAULT_COMPLEXATION_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "chromosome_length_bp": 580_076.0,
        "bp_per_turn": 10.5,
        "equilibrium_supercoil_density": -0.06,
        "supercoil_density_min": -0.2,
        "supercoil_density_max": 0.2,
        "sigma_deadband": 0.001,
        # Fixture-driven defaults if set to None.
        "gyrase_activity_rate": None,
        "topoiv_activity_rate": None,
        "gyrase_logistic_const": None,
        "topoiv_logistic_const": None,
        "gyrase_sigma_limit": None,
        "topoiv_sigma_limit": None,
        "gyrase_atp_cost": None,
        "topoiv_atp_cost": None,
        # Light-scope link changes per event.
        "gyrase_link_delta": -1.0,
        "topoiv_link_delta": 1.0,
        # Coupling: elongating replication consumes negative supercoils.
        "replication_supercoil_load_rate": 4.0,
        "reference_gyrase_count": 3.0,
        "reference_topoiv_count": 12.0,
        "request_safety_factor": 1.2,
        "request_max_atp": 10_000.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._canonical_complex_wids = _load_d2_complex_wid_set(
            self.parameters["complexation_fixture_path"]
        )
        self.complex_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid in self._canonical_complex_wids
        ]
        self.protein_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid not in self._canonical_complex_wids
        ]
        self.enzyme_store_by_wid = {
            wid: ("complex" if wid in self._canonical_complex_wids else "protein")
            for wid in self.enzyme_wids
        }
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        chromosome_length = float(self.parameters["chromosome_length_bp"])
        bp_per_turn = float(self.parameters["bp_per_turn"])
        self.linking_number_relaxed = max(1.0, chromosome_length / bp_per_turn)

    def _cfg(self, key: str, fixture_value: float) -> float:
        configured = self.parameters.get(key)
        if configured is None:
            return float(fixture_value)
        return float(configured)

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.substrate_wids = _parse_wid_array(fx.substrateWholeCellModelIDs)
        self.enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)

        self.substrate_index_atp = int(_coerce_scalar(fx.substrateIndexs_atp)) - 1
        self.substrate_index_adp = int(_coerce_scalar(fx.substrateIndexs_adp)) - 1
        self.substrate_index_pi = int(_coerce_scalar(fx.substrateIndexs_phosphate)) - 1
        self.substrate_index_h2o = int(_coerce_scalar(fx.substrateIndexs_water)) - 1

        self.atp_wid = self.substrate_wids[self.substrate_index_atp]
        self.adp_wid = self.substrate_wids[self.substrate_index_adp]
        self.pi_wid = self.substrate_wids[self.substrate_index_pi]
        self.h2o_wid = self.substrate_wids[self.substrate_index_h2o]

        gyrase_idx = int(_coerce_scalar(fx.enzymeIndexs_gyrase)) - 1
        topoiv_idx = int(_coerce_scalar(fx.enzymeIndexs_topoIV)) - 1
        self.gyrase_wid = self.enzyme_wids[gyrase_idx]
        self.topoiv_wid = self.enzyme_wids[topoiv_idx]

        self.gyrase_activity_rate = self._cfg("gyrase_activity_rate", float(fx.gyraseActivityRate))
        self.topoiv_activity_rate = self._cfg("topoiv_activity_rate", float(fx.topoIVActivityRate))

        self.gyrase_logistic_const = self._cfg("gyrase_logistic_const", float(fx.gyrLogisiticConst))
        self.topoiv_logistic_const = self._cfg("topoiv_logistic_const", float(fx.topoILogisiticConst))

        self.gyrase_sigma_limit = self._cfg("gyrase_sigma_limit", float(fx.gyraseSigmaLimit))
        # Light-scope topoIV relaxation branch is gated on sigma < 0 by default.
        self.topoiv_sigma_limit = self._cfg("topoiv_sigma_limit", float(fx.topoIVSigmaLimit))

        self.gyrase_atp_cost = self._cfg("gyrase_atp_cost", float(fx.gyraseATPCost))
        self.topoiv_atp_cost = self._cfg("topoiv_atp_cost", float(fx.topoIVATPCost))

        self.equilibrium_sigma = self._load_equilibrium_sigma(
            fx,
            fallback=float(self.parameters["equilibrium_supercoil_density"]),
        )

    def _load_equilibrium_sigma(self, fixture: object, fallback: float) -> float:
        states = np.asarray(getattr(fixture, "states", []), dtype=object).ravel()
        for state in states:
            if getattr(state, "x_class_", "") != "edu.stanford.covert.cell.sim.state.Chromosome":
                continue
            if hasattr(state, "equilibriumSuperhelicalDensity"):
                return float(getattr(state, "equilibriumSuperhelicalDensity"))
        return float(fallback)

    def ports_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {
            "chromosome": {
                "supercoil_density": {
                    "_default": float(self.equilibrium_sigma),
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "replication_state": {
                    "_default": "idle",
                    "_updater": "set",
                    "_emit": True,
                },
                "supercoiled": {
                    "_default": True,
                    "_updater": "set",
                    "_emit": False,
                },
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
                    self.h2o_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_emit": False},
                    self.h2o_wid: {"_default": 0.0, "_emit": False},
                }
            },
        }
        if self.protein_enzyme_wids:
            schema["protein"] = {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.protein_enzyme_wids
                }
            }
        if self.complex_enzyme_wids:
            schema["complex"] = {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.complex_enzyme_wids
                }
            }
        return schema

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])

        chrom_state = states.get("chromosome", {})
        sigma = _to_finite(
            float(chrom_state.get("supercoil_density", self.equilibrium_sigma)),
            fallback=self.equilibrium_sigma,
        )
        replication_state = str(chrom_state.get("replication_state", "idle"))

        protein_counts = states.get("protein", {}).get("counts", {})
        complex_counts = states.get("complex", {}).get("counts", {})
        gyrase_count = self._resolve_enzyme_count(
            self.gyrase_wid, protein_counts=protein_counts, complex_counts=complex_counts
        )
        topoiv_count = self._resolve_enzyme_count(
            self.topoiv_wid, protein_counts=protein_counts, complex_counts=complex_counts
        )

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        available_atp = self._allocated_or_state(allocated_state, self.atp_wid)
        available_h2o = self._allocated_or_state(allocated_state, self.h2o_wid)
        hydrolysis_budget = min(available_atp, available_h2o)

        rep_load_events = self._replication_supercoil_load_events(replication_state, dt)
        rep_sigma_delta = rep_load_events / self.linking_number_relaxed
        sigma_after_rep = sigma + rep_sigma_delta

        mode = self._regime(sigma_after_rep)
        gyrase_prob = self._activity_probability(
            sigma=sigma_after_rep,
            logistic_const=self.gyrase_logistic_const,
            sigma_limit=self.gyrase_sigma_limit,
            allowed_when="greater",
        )
        topoiv_prob = self._activity_probability(
            sigma=sigma_after_rep,
            logistic_const=self.topoiv_logistic_const,
            sigma_limit=self.topoiv_sigma_limit,
            allowed_when="less",
        )

        gyrase_events = int(
            self._rng.poisson(
                self._expected_event_rate(
                    base_rate=self.gyrase_activity_rate,
                    enzyme_count=gyrase_count,
                    reference_count=float(self.parameters["reference_gyrase_count"]),
                    probability=gyrase_prob,
                    dt=dt,
                )
            )
        )
        topoiv_events = int(
            self._rng.poisson(
                self._expected_event_rate(
                    base_rate=self.topoiv_activity_rate,
                    enzyme_count=topoiv_count,
                    reference_count=float(self.parameters["reference_topoiv_count"]),
                    probability=topoiv_prob,
                    dt=dt,
                )
            )
        )

        gyrase_events, topoiv_events = self._limit_events_by_atp(
            gyrase_events=gyrase_events,
            topoiv_events=topoiv_events,
            available_atp=hydrolysis_budget,
            mode=mode,
        )

        link_delta = (
            float(gyrase_events) * float(self.parameters["gyrase_link_delta"])
            + float(topoiv_events) * float(self.parameters["topoiv_link_delta"])
        )
        sigma_delta = rep_sigma_delta + (link_delta / self.linking_number_relaxed)

        sigma_min = float(self.parameters["supercoil_density_min"])
        sigma_max = float(self.parameters["supercoil_density_max"])
        sigma_next = float(np.clip(sigma + sigma_delta, a_min=sigma_min, a_max=sigma_max))
        sigma_delta = sigma_next - sigma

        atp_used = (
            float(gyrase_events) * self.gyrase_atp_cost
            + float(topoiv_events) * self.topoiv_atp_cost
        )

        request_need = self._atp_request(
            sigma=sigma_after_rep,
            replication_state=replication_state,
            gyrase_count=gyrase_count,
            topoiv_count=topoiv_count,
            dt=dt,
        )
        update: dict[str, Any] = {
            "chromosome": {
                "supercoiled": bool(sigma_next < 0.0),
            },
            "requests": {
                self.name: {
                    self.atp_wid: request_need,
                    self.h2o_wid: request_need,
                }
            },
        }

        if sigma_delta != 0.0:
            update["chromosome"]["supercoil_density"] = float(sigma_delta)

        substrate_delta = self._substrate_delta(atp_used)
        if substrate_delta:
            update["substrates"] = substrate_delta

        return update

    def _resolve_enzyme_count(
        self,
        wid: str,
        *,
        protein_counts: dict[str, Any],
        complex_counts: dict[str, Any],
    ) -> float:
        store = self.enzyme_store_by_wid.get(wid)
        if store is None:
            raise KeyError(f"Declared enzyme '{wid}' is missing store classification")
        if store == "complex":
            if wid not in complex_counts:
                raise KeyError(
                    f"Missing declared complex enzyme '{wid}' in complex.counts"
                )
            return max(0.0, float(complex_counts[wid]))
        if wid not in protein_counts:
            raise KeyError(f"Missing declared protein enzyme '{wid}' in protein.counts")
        return max(0.0, float(protein_counts[wid]))

    def _allocated_or_state(
        self,
        allocated_state: dict[str, Any],
        wid: str,
    ) -> float:
        allocated = float(allocated_state.get(wid, 0.0))
        return max(0.0, allocated)

    def _replication_supercoil_load_events(self, replication_state: str, dt: float) -> int:
        if replication_state != "elongating":
            return 0
        rate = max(0.0, float(self.parameters["replication_supercoil_load_rate"]))
        return int(self._rng.poisson(rate * max(0.0, dt)))

    def _activity_probability(
        self,
        *,
        sigma: float,
        logistic_const: float,
        sigma_limit: float,
        allowed_when: str,
    ) -> float:
        if allowed_when == "greater":
            if sigma <= sigma_limit:
                return 0.0
        elif allowed_when == "less":
            if sigma >= sigma_limit:
                return 0.0
        else:
            raise ValueError(f"Unknown allowed_when mode: {allowed_when}")

        x = float(logistic_const) * (float(sigma) - float(self.equilibrium_sigma))
        x = float(np.clip(x, a_min=-60.0, a_max=60.0))
        return float(1.0 / (1.0 + np.exp(x)))

    def _expected_event_rate(
        self,
        *,
        base_rate: float,
        enzyme_count: float,
        reference_count: float,
        probability: float,
        dt: float,
    ) -> float:
        if base_rate <= 0.0 or enzyme_count <= 0.0 or probability <= 0.0 or dt <= 0.0:
            return 0.0
        ref = max(1e-9, reference_count)
        count_scale = enzyme_count / ref
        return max(0.0, base_rate * count_scale * probability * dt)

    def _regime(self, sigma: float) -> str:
        deadband = abs(float(self.parameters["sigma_deadband"]))
        if sigma > self.equilibrium_sigma + deadband:
            return "overwound"
        if sigma < self.equilibrium_sigma - deadband:
            return "underwound"
        return "near_equilibrium"

    def _limit_events_by_atp(
        self,
        *,
        gyrase_events: int,
        topoiv_events: int,
        available_atp: float,
        mode: str,
    ) -> tuple[int, int]:
        g_events = max(0, int(gyrase_events))
        t_events = max(0, int(topoiv_events))
        atp_budget = max(0, int(math.floor(available_atp)))

        g_cost = max(0, int(round(self.gyrase_atp_cost)))
        t_cost = max(0, int(round(self.topoiv_atp_cost)))

        total_cost = g_events * g_cost + t_events * t_cost
        if total_cost <= atp_budget:
            return g_events, t_events

        if g_cost == 0 and t_cost == 0:
            return g_events, t_events
        if atp_budget <= 0:
            return 0, 0

        g_kept = 0
        t_kept = 0

        priorities = ["g", "t"] if mode == "overwound" else ["t", "g"]

        for key in priorities:
            if key == "g":
                while g_kept < g_events and (g_cost == 0 or atp_budget >= g_cost):
                    g_kept += 1
                    atp_budget -= g_cost
            else:
                while t_kept < t_events and (t_cost == 0 or atp_budget >= t_cost):
                    t_kept += 1
                    atp_budget -= t_cost

        return g_kept, t_kept

    def _atp_request(
        self,
        *,
        sigma: float,
        replication_state: str,
        gyrase_count: float,
        topoiv_count: float,
        dt: float,
    ) -> float:
        gyrase_prob = self._activity_probability(
            sigma=sigma,
            logistic_const=self.gyrase_logistic_const,
            sigma_limit=self.gyrase_sigma_limit,
            allowed_when="greater",
        )
        topoiv_prob = self._activity_probability(
            sigma=sigma,
            logistic_const=self.topoiv_logistic_const,
            sigma_limit=self.topoiv_sigma_limit,
            allowed_when="less",
        )

        expected_g_events = self._expected_event_rate(
            base_rate=self.gyrase_activity_rate,
            enzyme_count=gyrase_count,
            reference_count=float(self.parameters["reference_gyrase_count"]),
            probability=gyrase_prob,
            dt=dt,
        )
        expected_t_events = self._expected_event_rate(
            base_rate=self.topoiv_activity_rate,
            enzyme_count=topoiv_count,
            reference_count=float(self.parameters["reference_topoiv_count"]),
            probability=topoiv_prob,
            dt=dt,
        )

        replication_extra = 0.0
        if replication_state == "elongating":
            replication_extra = (
                max(0.0, float(self.parameters["replication_supercoil_load_rate"]))
                * max(0.0, dt)
            )

        expected_atp = (
            expected_g_events * self.gyrase_atp_cost
            + expected_t_events * self.topoiv_atp_cost
            + replication_extra * self.gyrase_atp_cost
        )
        safety = max(1.0, float(self.parameters["request_safety_factor"]))
        req = math.ceil(expected_atp * safety)
        return float(min(req, max(0.0, float(self.parameters["request_max_atp"]))))

    def _substrate_delta(self, atp_used: float) -> dict[str, float]:
        if atp_used <= 0.0:
            return {}
        return {
            self.atp_wid: float(-atp_used),
            self.h2o_wid: float(-atp_used),
            self.adp_wid: float(atp_used),
            self.pi_wid: float(atp_used),
        }


__all__ = ["KarrDNASupercoilingProcess"]
