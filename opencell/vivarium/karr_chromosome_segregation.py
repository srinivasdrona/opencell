"""Vivarium Process port of Karr's ChromosomeSegregation (Karr-LIGHT v1).

Primary source: docs/karr_extracts/process/08_ChromosomeSegregation.md

Karr models segregation as a gated boolean decision:
1) chromosome replicated
2) chromosome properly supercoiled
3) required segregation proteins available
4) sufficient GTP (gtpCost)

Karr-LIGHT v1 maps this to continuous state needed by downstream Phase C turns:
- chromosome.segregation_progress in [0, 1]
- chromosome.daughter_pole_positions.{left,right}
- chromosome.segregation_complete + chromosome.cell_cycle_event pulse

Deferred to v2:
- explicit decatenation/topological mechanism and locus-level spatial dynamics.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ChromosomeSegregation_flat.mat"


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Path not found: {path}")


def _coerce_scalar(value: object) -> object:
    out = value
    while isinstance(out, np.ndarray):
        if out.size == 0:
            return 0
        out = out.flat[0]
    return out


def _parse_wids(value: object) -> list[str]:
    values = np.asarray(value, dtype=object)
    out: list[str] = []
    for raw in values.ravel():
        out.append(str(_coerce_scalar(raw)))
    return out


def _one_based_to_zero(value: object) -> int:
    return int(_coerce_scalar(value)) - 1


def _clamp01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


class KarrChromosomeSegregationProcess(Process):
    """Karr Process_ChromosomeSegregation with gated progress + completion signal."""

    name = "karr_chromosome_segregation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "time_step": 1.0,
        # Boolean-rule faithful default: complete in one eligible tick.
        "segregation_rate_per_s": 1.0,
        "require_supercoiled": True,
        "min_required_enzyme_count": 1.0,
        "include_topoiv_gate": False,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])

        gtp_cost_override = self.parameters.get("gtp_cost_override")
        if gtp_cost_override is None:
            self.gtp_cost = float(self._fixture_gtp_cost)
        else:
            self.gtp_cost = float(gtp_cost_override)
        if self.gtp_cost <= 0.0:
            raise ValueError(f"gtp_cost must be > 0, got {self.gtp_cost}")

        if bool(self.parameters.get("include_topoiv_gate", False)):
            if self.topoiv_wid not in self.required_enzyme_wids:
                self.required_enzyme_wids.append(self.topoiv_wid)

    def _load_fixture(self, path: str | Path) -> None:
        mat = loadmat(str(_resolve_path(path)), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.substrate_wids = _parse_wids(fx.substrateWholeCellModelIDs)
        self.enzyme_wids = _parse_wids(fx.enzymeWholeCellModelIDs)

        self.substrate_index_gtp = _one_based_to_zero(fx.substrateIndexs_gtp)
        self.substrate_index_gdp = _one_based_to_zero(fx.substrateIndexs_gdp)
        self.substrate_index_hydrogen = _one_based_to_zero(fx.substrateIndexs_hydrogen)
        self.substrate_index_water = _one_based_to_zero(fx.substrateIndexs_water)
        self.substrate_index_phosphate = _one_based_to_zero(fx.substrateIndexs_phosphate)

        self.gtp_wid = self.substrate_wids[self.substrate_index_gtp]
        self.gdp_wid = self.substrate_wids[self.substrate_index_gdp]
        self.h_wid = self.substrate_wids[self.substrate_index_hydrogen]
        self.h2o_wid = self.substrate_wids[self.substrate_index_water]
        self.pi_wid = self.substrate_wids[self.substrate_index_phosphate]

        self.enzyme_index_cobq = _one_based_to_zero(fx.enzymeIndexs_cobQ)
        self.enzyme_index_mraz = _one_based_to_zero(fx.enzymeIndexs_mraZ)
        self.enzyme_index_obg = _one_based_to_zero(fx.enzymeIndexs_obg)
        self.enzyme_index_era = _one_based_to_zero(fx.enzymeIndexs_era)
        self.enzyme_index_topoiv = _one_based_to_zero(fx.enzymeIndexs_topoIV)

        self.cobq_wid = self.enzyme_wids[self.enzyme_index_cobq]
        self.mraz_wid = self.enzyme_wids[self.enzyme_index_mraz]
        self.obg_wid = self.enzyme_wids[self.enzyme_index_obg]
        self.era_wid = self.enzyme_wids[self.enzyme_index_era]
        self.topoiv_wid = self.enzyme_wids[self.enzyme_index_topoiv]

        self.required_enzyme_wids = [
            self.cobq_wid,
            self.mraz_wid,
            self.era_wid,
            self.obg_wid,
        ]
        self._fixture_gtp_cost = int(_coerce_scalar(fx.gtpCost))

    def ports_schema(self) -> dict[str, Any]:
        return {
            "chromosome": {
                "replication_state": {
                    "_default": "idle",
                    "_updater": "set",
                    "_emit": True,
                },
                "supercoiled": {
                    "_default": True,
                    "_updater": "set",
                    "_emit": True,
                },
                "segregation_progress": {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "daughter_pole_positions": {
                    "left": {
                        "_default": 0.0,
                        "_updater": "accumulate",
                        "_emit": True,
                    },
                    "right": {
                        "_default": 0.0,
                        "_updater": "accumulate",
                        "_emit": True,
                    },
                },
                "segregation_complete": {
                    "_default": False,
                    "_updater": "set",
                    "_emit": True,
                },
                "cell_cycle_event": {
                    "_default": "none",
                    "_updater": "set",
                    "_emit": True,
                },
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.substrate_wids
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.enzyme_wids
                }
            },
            "requests": {
                self.name: {
                    self.gtp_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                    self.h2o_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.gtp_wid: {
                        "_default": 0.0,
                        "_updater": "accumulate",
                        "_emit": False,
                    },
                    self.h2o_wid: {
                        "_default": 0.0,
                        "_updater": "accumulate",
                        "_emit": False,
                    },
                }
            },
        }

    def _allocated_or_state(
        self,
        allocated_state: dict[str, Any],
        substrate_state: dict[str, Any],
        wid: str,
    ) -> float:
        allocated = float(allocated_state.get(wid, 0.0))
        if allocated > 0.0:
            return allocated
        return float(substrate_state.get(wid, 0.0))

    def _gates_satisfied(
        self,
        *,
        replication_state: str,
        supercoiled: bool,
        protein_counts: dict[str, Any],
    ) -> bool:
        if replication_state != "complete":
            return False
        if bool(self.parameters["require_supercoiled"]) and not supercoiled:
            return False

        min_count = float(self.parameters["min_required_enzyme_count"])
        return all(float(protein_counts.get(wid, 0.0)) >= min_count for wid in self.required_enzyme_wids)

    def _progress_delta(self, dt: float, current_progress: float) -> float:
        if current_progress >= 1.0:
            return 0.0
        rate = max(0.0, float(self.parameters["segregation_rate_per_s"]))
        return min(1.0 - current_progress, rate * dt)

    def _request_level(self, can_progress: bool, current_progress: float) -> float:
        if not can_progress or current_progress >= 1.0:
            return 0.0
        return float(self.gtp_cost)

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])

        chromosome = states.get("chromosome", {})
        replication_state = str(chromosome.get("replication_state", "idle"))
        supercoiled = bool(chromosome.get("supercoiled", True))
        current_progress = _clamp01(float(chromosome.get("segregation_progress", 0.0)))
        current_complete = bool(chromosome.get("segregation_complete", False))

        pos_state = chromosome.get("daughter_pole_positions", {})
        current_left = float(pos_state.get("left", -current_progress))
        current_right = float(pos_state.get("right", current_progress))

        protein_counts = states.get("protein", {}).get("counts", {})
        gated = self._gates_satisfied(
            replication_state=replication_state,
            supercoiled=supercoiled,
            protein_counts=protein_counts,
        )

        allocated = states.get("substrates_allocated", {}).get(self.name, {})
        substrate_state = states.get("substrates", {})
        gtp_available = self._allocated_or_state(allocated, substrate_state, self.gtp_wid)
        h2o_available = self._allocated_or_state(allocated, substrate_state, self.h2o_wid)
        max_events = min(
            int(math.floor(max(0.0, gtp_available) / self.gtp_cost)),
            int(math.floor(max(0.0, h2o_available) / self.gtp_cost)),
        )

        can_progress = gated and (not current_complete) and current_progress < 1.0
        request_gtp = self._request_level(can_progress, current_progress)
        request_h2o = request_gtp

        substrate_update: dict[str, float] = {}
        progress_delta = 0.0
        if can_progress and max_events >= 1:
            progress_delta = self._progress_delta(dt, current_progress)
            if progress_delta > 0.0:
                substrate_update = {
                    self.gtp_wid: float(-self.gtp_cost),
                    self.h2o_wid: float(-self.gtp_cost),
                    self.gdp_wid: float(self.gtp_cost),
                    self.pi_wid: float(self.gtp_cost),
                    self.h_wid: float(self.gtp_cost),
                }

        new_progress = _clamp01(current_progress + progress_delta)
        desired_left = -new_progress
        desired_right = new_progress
        left_delta = desired_left - current_left
        right_delta = desired_right - current_right

        just_completed = (new_progress >= 1.0) and (not current_complete)

        chromosome_update: dict[str, Any] = {
            "cell_cycle_event": "segregation_complete" if just_completed else "none",
        }
        if progress_delta != 0.0:
            chromosome_update["segregation_progress"] = float(progress_delta)
        if left_delta != 0.0 or right_delta != 0.0:
            chromosome_update["daughter_pole_positions"] = {
                "left": float(left_delta),
                "right": float(right_delta),
            }
        if just_completed:
            chromosome_update["segregation_complete"] = True

        update: dict[str, Any] = {
            "requests": {
                self.name: {
                    self.gtp_wid: float(request_gtp),
                    self.h2o_wid: float(request_h2o),
                }
            },
            "chromosome": chromosome_update,
        }
        if substrate_update:
            update["substrates"] = substrate_update
        return update


__all__ = ["KarrChromosomeSegregationProcess"]
