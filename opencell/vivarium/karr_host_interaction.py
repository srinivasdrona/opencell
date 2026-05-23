"""Vivarium Process for Karr HostInteraction adhesion dynamics (Karr-light v1).

Primary source:
- docs/karr_extracts/process/27_HostInteraction.md

Karr-light v1 scope:
- Aggregate stochastic adhesion/unbinding events (not per-receptor docking)
- Terminal organelle + adhesin readiness gating
- ATP usage through KarrAllocationStep request/allocation contract

Deferred to v2:
- Full host signaling cascade (TLR / NF-kB / inflammatory response)
- Explicit hydrolysis coproduct bookkeeping for ATP usage
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/HostInteraction_flat.mat"
_DEFAULT_TRACE_PATH = "data/m1_sources/karr_native/per_process_traces/HostInteraction_100ticks.mat"
_ATP_WID = "ATP"


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


def _parse_wid_array(value: object) -> list[str]:
    values = np.asarray(value, dtype=object)
    out: list[str] = []
    for raw in values.ravel():
        token = _coerce_scalar(raw)
        out.append(str(token))
    return out


def _parse_index_array(value: object) -> np.ndarray:
    raw = np.asarray(value)
    while raw.dtype == object and raw.size == 1 and isinstance(raw.flat[0], np.ndarray):
        raw = np.asarray(raw.flat[0])
    return np.asarray(raw, dtype=np.int64).reshape(-1)


def _is_binary_like(series: np.ndarray) -> bool:
    arr = np.asarray(series, dtype=np.float64).reshape(-1)
    if arr.size < 5:
        return False
    if np.any(~np.isfinite(arr)):
        return False
    if np.any((arr < -1e-9) | (arr > 1.0 + 1e-9)):
        return False
    uniq = np.unique(np.round(arr, decimals=8))
    return uniq.size <= 3


def _trace_rate_from_attachment_series(series: np.ndarray, dt: float) -> tuple[float, float] | None:
    if dt <= 0.0:
        return None
    arr = np.asarray(series, dtype=np.float64).reshape(-1)
    if arr.size < 2:
        return None
    attached = arr > 0.5
    prev = attached[:-1]
    nxt = attached[1:]
    n_attach = int(np.count_nonzero(~prev & nxt))
    n_detach = int(np.count_nonzero(prev & ~nxt))
    unbound_time = float(np.count_nonzero(~prev)) * dt
    bound_time = float(np.count_nonzero(prev)) * dt
    if unbound_time <= 0.0 or bound_time <= 0.0:
        return None
    bind_rate = n_attach / unbound_time
    unbind_rate = n_detach / bound_time
    if bind_rate <= 0.0 and unbind_rate <= 0.0:
        return None
    return max(bind_rate, 0.0), max(unbind_rate, 0.0)


def _extract_trace_rates(trace_path: str | Path) -> tuple[float, float] | None:
    try:
        resolved = _resolve_path(trace_path)
    except FileNotFoundError:
        return None

    try:
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
    except Exception:
        return None

    lower_keys = {str(k).lower(): k for k in mat.keys()}
    bind_key = next(
        (k for k in lower_keys if "bind_rate" in k or "attach_rate" in k),
        None,
    )
    unbind_key = next(
        (k for k in lower_keys if "unbind_rate" in k or "detach_rate" in k),
        None,
    )
    if bind_key is not None and unbind_key is not None:
        bind_val = float(_coerce_scalar(mat[lower_keys[bind_key]]))
        unbind_val = float(_coerce_scalar(mat[lower_keys[unbind_key]]))
        if bind_val >= 0.0 and unbind_val >= 0.0:
            return bind_val, unbind_val

    dt = 1.0
    dt_key = next((k for k in lower_keys if "step" in k and "sec" in k), None)
    if dt_key is not None:
        try:
            dt = float(_coerce_scalar(mat[lower_keys[dt_key]]))
        except Exception:
            dt = 1.0

    for raw_key, value in mat.items():
        key = str(raw_key).lower()
        if not any(token in key for token in ("attach", "adher", "host")):
            continue
        arr = np.asarray(value)
        if arr.dtype == object and arr.size == 1 and isinstance(arr.flat[0], np.ndarray):
            arr = np.asarray(arr.flat[0])
        if not np.issubdtype(arr.dtype, np.number):
            continue
        if arr.ndim > 2:
            continue
        flat = np.asarray(arr, dtype=np.float64).reshape(-1)
        if not _is_binary_like(flat):
            continue
        rates = _trace_rate_from_attachment_series(flat, dt=dt)
        if rates is not None:
            return rates
    return None


class KarrHostInteractionProcess(Process):
    """HostInteraction adhesion process with stochastic aggregate bond dynamics."""

    name = "karr_host_interaction"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "trace_path": _DEFAULT_TRACE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "max_adhesion_bonds": 100,
        "terminal_organelle_saturation_count": 1.0,
        "attach_threshold": 0.60,
        "bind_rate_per_s": 0.08,
        "unbind_rate_per_s": 0.02,
        "atp_per_binding_event": 1.0,
        "use_trace_rates": True,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        explicit_params = parameters or {}
        super().__init__(parameters)
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))
        self.atp_wid = _ATP_WID
        self._load_fixture(self.parameters["fixture_path"])

        bind_rate = float(self.parameters["bind_rate_per_s"])
        unbind_rate = float(self.parameters["unbind_rate_per_s"])
        if bool(self.parameters.get("use_trace_rates", True)):
            inferred = _extract_trace_rates(self.parameters["trace_path"])
            if inferred is not None:
                inferred_bind, inferred_unbind = inferred
                if "bind_rate_per_s" not in explicit_params:
                    bind_rate = inferred_bind
                if "unbind_rate_per_s" not in explicit_params:
                    unbind_rate = inferred_unbind

        self.bind_rate_per_s = max(0.0, bind_rate)
        self.unbind_rate_per_s = max(0.0, unbind_rate)
        self.max_adhesion_bonds = max(1, int(self.parameters["max_adhesion_bonds"]))
        self.terminal_organelle_saturation_count = max(
            1e-9, float(self.parameters["terminal_organelle_saturation_count"])
        )
        self.attach_threshold = float(np.clip(float(self.parameters["attach_threshold"]), 0.0, 1.0))
        self.atp_per_binding_event = max(0.0, float(self.parameters["atp_per_binding_event"]))

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)
        self.enzyme_ref_counts = np.asarray(fx.enzymes, dtype=np.float64).reshape(-1)
        if self.enzyme_ref_counts.size != len(self.enzyme_wids):
            raise ValueError(
                "HostInteraction fixture mismatch: enzyme count vector size differs from WIDs"
            )

        adhesin_idx = _parse_index_array(fx.enzymeIndexs_adhesin) - 1
        terminal_idx = _parse_index_array(fx.enzymeIndexs_terminalOrganelle) - 1
        self.adhesin_wids = [self.enzyme_wids[int(i)] for i in adhesin_idx.tolist()]
        self.terminal_organelle_wids = [self.enzyme_wids[int(i)] for i in terminal_idx.tolist()]

        self.reference_count_by_wid: dict[str, float] = {}
        for wid, ref in zip(self.enzyme_wids, self.enzyme_ref_counts, strict=False):
            self.reference_count_by_wid[wid] = float(max(1.0, float(ref)))

    def ports_schema(self) -> dict[str, Any]:
        required_wids = sorted(set(self.adhesin_wids) | set(self.terminal_organelle_wids))
        return {
            "cell": {
                "terminal_organelle_count": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
                "host_adhesion_strength": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
                "host_attached": {"_default": False, "_updater": "set", "_emit": True},
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in required_wids
                }
            },
            "substrates": {
                self.atp_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True},
            },
            "requests": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False},
                }
            },
        }

    def _expression_fraction(self, wids: list[str], counts_state: dict[str, Any]) -> float:
        if not wids:
            return 1.0
        fractions: list[float] = []
        for wid in wids:
            ref = self.reference_count_by_wid.get(wid, 1.0)
            current = max(0.0, float(counts_state.get(wid, 0.0)))
            fractions.append(float(np.clip(current / ref, 0.0, 1.0)))
        return float(min(fractions))

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

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0.0 else float(self.parameters["time_step"])
        dt = max(dt, 1e-9)

        cell_state = states.get("cell", {})
        protein_counts = states.get("protein", {}).get("counts", {})

        prev_strength = float(np.clip(float(cell_state.get("host_adhesion_strength", 0.0)), 0.0, 1.0))
        prev_attached = bool(cell_state.get("host_attached", prev_strength >= self.attach_threshold))
        terminal_organelle_count = max(0.0, float(cell_state.get("terminal_organelle_count", 0.0)))

        adhesin_fraction = self._expression_fraction(self.adhesin_wids, protein_counts)
        terminal_fraction = self._expression_fraction(self.terminal_organelle_wids, protein_counts)
        terminal_structure_fraction = float(
            np.clip(terminal_organelle_count / self.terminal_organelle_saturation_count, 0.0, 1.0)
        )
        adhesion_capability = float(
            np.clip(adhesin_fraction * terminal_fraction * terminal_structure_fraction, 0.0, 1.0)
        )

        prev_bound = int(np.clip(np.rint(prev_strength * self.max_adhesion_bonds), 0, self.max_adhesion_bonds))
        free_sites = self.max_adhesion_bonds - prev_bound

        expected_bind = max(0.0, self.bind_rate_per_s * adhesion_capability * float(free_sites) * dt)
        expected_unbind = max(0.0, self.unbind_rate_per_s * float(prev_bound) * dt)

        proposed_bind = int(min(self._rng.poisson(expected_bind), free_sites)) if free_sites > 0 else 0
        proposed_unbind = int(min(self._rng.poisson(expected_unbind), prev_bound)) if prev_bound > 0 else 0

        requested_atp = float(proposed_bind) * self.atp_per_binding_event
        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        substrate_state = states.get("substrates", {})
        available_atp = max(0.0, self._allocated_or_state(allocated_state, substrate_state, self.atp_wid))

        if self.atp_per_binding_event > 0.0:
            max_bind_from_atp = int(np.floor(available_atp / self.atp_per_binding_event))
        else:
            max_bind_from_atp = proposed_bind
        applied_bind = min(proposed_bind, max_bind_from_atp)

        next_bound = int(np.clip(prev_bound + applied_bind - proposed_unbind, 0, self.max_adhesion_bonds))
        next_strength = float(next_bound) / float(self.max_adhesion_bonds)
        strength_delta = float(next_strength - prev_strength)
        next_attached = bool(next_strength >= self.attach_threshold)

        update: dict[str, Any] = {
            "requests": {self.name: {self.atp_wid: requested_atp}},
        }
        cell_update: dict[str, Any] = {}
        if abs(strength_delta) > 0.0:
            cell_update["host_adhesion_strength"] = strength_delta
        if next_attached != prev_attached:
            cell_update["host_attached"] = next_attached
        if cell_update:
            update["cell"] = cell_update

        atp_consumed = float(applied_bind) * self.atp_per_binding_event
        if atp_consumed > 0.0:
            update["substrates"] = {self.atp_wid: -atp_consumed}

        return update


__all__ = ["KarrHostInteractionProcess"]
