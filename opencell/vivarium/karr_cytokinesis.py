"""Vivarium Process for Karr Cytokinesis (Karr-light v1).

Karr-light v1 scope:
- Bulk cytokinesis progress ratchet (`cell.division_progress` in [0, 1]).
- Dual-gate activation on completed Z-ring assembly and chromosome segregation.
- Allocation-bounded GTP consumption coupled to progress.

Deferred to v2:
- Edge-wise FtsZ polygon mechanics (bind/bend/dissociate cycle).
- Per-monomer FtsZ GTP/GDP polymer state transitions.
- Explicit pinched-diameter geometry evolution from CellGeometry/FtsZRing states.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/Cytokinesis_flat.mat"
_DEFAULT_TRACE_PATH = "data/m1_sources/karr_native/per_process_traces/Cytokinesis_100ticks.mat"
_DEFAULT_FALLBACK_TRACE_TICKS = 100


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    # Worktree convenience: E:/opencell-worktrees/<branch> -> sibling E:/opencell
    main_repo = repo_root.parents[1] / "opencell"
    sibling = main_repo / candidate
    if sibling.exists():
        return sibling

    raise FileNotFoundError(f"Path not found: {path}")


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


def _optional_trace_ticks(path: str | Path) -> int | None:
    try:
        resolved = _resolve_path(path)
    except FileNotFoundError:
        return None

    try:
        import h5py
    except ImportError:
        return None

    try:
        with h5py.File(resolved, "r") as handle:
            if "metadata/n_ticks" not in handle:
                return None
            n_ticks = int(np.array(handle["metadata/n_ticks"]).reshape(-1)[0])
            return n_ticks if n_ticks > 0 else None
    except OSError:
        return None


class KarrCytokinesisProcess(Process):
    """Karr Process_Cytokinesis (bulk ring constriction light port)."""

    name = "karr_cytokinesis"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "trace_path": _DEFAULT_TRACE_PATH,
        "time_step": 1.0,
        "gtp_wid": "GTP",
        "min_segregation_progress": 1.0,
        "gating_tolerance": 1.0e-9,
        # 1 progress unit per ~100 active ticks (trace-window light calibration).
        "active_division_rate_per_s": None,
        # Simple bulk energetic coupling in v1: each GTP supports fixed progress.
        "progress_per_gtp": 0.01,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])

        self.gtp_wid = str(self.parameters["gtp_wid"])
        self.min_segregation_progress = float(self.parameters["min_segregation_progress"])
        self.gating_tolerance = float(self.parameters["gating_tolerance"])
        self.progress_per_gtp = float(self.parameters["progress_per_gtp"])

        if not math.isfinite(self.progress_per_gtp) or self.progress_per_gtp <= 0.0:
            raise ValueError("progress_per_gtp must be finite and > 0")

        trace_ticks = _optional_trace_ticks(self.parameters["trace_path"])
        self.trace_n_ticks = int(trace_ticks or _DEFAULT_FALLBACK_TRACE_TICKS)

        configured_rate = self.parameters.get("active_division_rate_per_s")
        if configured_rate is None:
            self.active_division_rate_per_s = 1.0 / float(self.trace_n_ticks)
        else:
            self.active_division_rate_per_s = float(configured_rate)

        if (not math.isfinite(self.active_division_rate_per_s)) or self.active_division_rate_per_s < 0.0:
            raise ValueError("active_division_rate_per_s must be finite and >= 0")

        self._substrate_wids = sorted(set(self.fixture_substrate_wids + [self.gtp_wid]))

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.fixture_substrate_wids = _parse_wid_array(fx.substrateWholeCellModelIDs)
        self.fixture_enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)

        self.rate_filament_binding_membrane = float(_coerce_scalar(fx.rateFilamentBindingMembrane))
        self.rate_filament_dissociation = float(_coerce_scalar(fx.rateFilamentDissociation))
        self.rate_ftsz_gtp_hydrolysis = float(_coerce_scalar(fx.rateFtsZGtpHydrolysis))

        self.substrate_index_pi = int(_coerce_scalar(fx.substrateIndexs_phosphate)) - 1
        self.substrate_index_water = int(_coerce_scalar(fx.substrateIndexs_water)) - 1
        self.substrate_index_hydrogen = int(_coerce_scalar(fx.substrateIndexs_hydrogen)) - 1

    def ports_schema(self) -> dict[str, Any]:
        return {
            "cell": {
                "ftsz_ring_complete": {
                    "_default": False,
                    "_updater": "set",
                    "_emit": True,
                },
                "division_progress": {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "division_complete": {
                    "_default": False,
                    "_updater": "set",
                    "_emit": True,
                },
            },
            "chromosome": {
                "segregation_progress": {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": True,
                }
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self._substrate_wids
            },
            "requests": {
                self.name: {
                    self.gtp_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.gtp_wid: {
                        "_default": 0.0,

                        "_emit": False,
                    },
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])

        cell_state = states.get("cell", {})
        chromosome_state = states.get("chromosome", {})
        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})

        raw_progress = float(cell_state.get("division_progress", 0.0))
        progress = self._clamp01(raw_progress)
        progress_correction = progress - raw_progress if math.isfinite(raw_progress) else 0.0
        is_complete = bool(cell_state.get("division_complete", False)) or progress >= 1.0

        gates_ready = self._gates_ready(cell_state=cell_state, chromosome_state=chromosome_state)
        available_gtp = self._allocated_or_state(allocated_state, self.gtp_wid)

        requested_gtp = 0.0
        progress_delta = 0.0
        gtp_used = 0.0

        if (not is_complete) and gates_ready and dt > 0.0 and self.active_division_rate_per_s > 0.0:
            remaining = max(0.0, 1.0 - progress)
            desired_progress = min(remaining, self.active_division_rate_per_s * dt)
            requested_gtp = desired_progress / self.progress_per_gtp

            max_progress_by_gtp = max(0.0, available_gtp) * self.progress_per_gtp
            progress_delta = min(desired_progress, max_progress_by_gtp)
            progress_delta = self._clamp_nonnegative(progress_delta)
            gtp_used = progress_delta / self.progress_per_gtp if progress_delta > 0.0 else 0.0

        update: dict[str, Any] = {
            "requests": {
                self.name: {
                    self.gtp_wid: float(max(0.0, requested_gtp)),
                }
            }
        }

        if abs(progress_correction) > 0.0:
            update.setdefault("cell", {})
            update["cell"]["division_progress"] = float(progress_correction)

        if progress_delta > 0.0:
            update.setdefault("cell", {})
            existing = float(update["cell"].get("division_progress", 0.0))
            update["cell"]["division_progress"] = float(existing + progress_delta)
            update["substrates"] = {self.gtp_wid: float(-gtp_used)}

        final_progress = self._clamp01(progress + progress_delta)
        if final_progress >= 1.0 - self.gating_tolerance and (not bool(cell_state.get("division_complete", False))):
            update.setdefault("cell", {})
            update["cell"]["division_complete"] = True

        return update

    def _gates_ready(self, cell_state: dict[str, Any], chromosome_state: dict[str, Any]) -> bool:
        ring_complete = bool(cell_state.get("ftsz_ring_complete", False))
        segregation_progress = float(chromosome_state.get("segregation_progress", 0.0))
        segregation_ready = segregation_progress + self.gating_tolerance >= self.min_segregation_progress
        return bool(ring_complete and segregation_ready)

    @staticmethod
    def _clamp01(value: float) -> float:
        if not math.isfinite(value):
            return 0.0
        return float(min(1.0, max(0.0, value)))

    @staticmethod
    def _clamp_nonnegative(value: float) -> float:
        if not math.isfinite(value):
            return 0.0
        return float(max(0.0, value))

    @staticmethod
    def _allocated_or_state(
        allocated_state: dict[str, Any],
        wid: str,
    ) -> float:
        allocated = float(allocated_state.get(wid, 0.0))
        return max(0.0, allocated)


__all__ = ["KarrCytokinesisProcess"]
