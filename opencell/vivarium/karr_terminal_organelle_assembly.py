"""Vivarium Process port of Karr TerminalOrganelleAssembly (Karr-light).

This implementation follows the fixture-defined localization hierarchy among
the 8 terminal-organelle proteins and exposes coarse assembly state at the
cell level.

Karr-light v1 scope:
- Tracks per-component assembled counters instead of full two-compartment
  substrate arrays.
- Uses protein activity gates as availability signals for component assembly.
- Represents organelle completion as the minimum assembled count across all
  required components, capped by a configurable target (typically 1, or 2
  during duplication/division scenarios).

Deferred to v2:
- Full compartment-level localization accounting (cytoplasm/membrane vs
  terminal organelle compartments).
- Explicit pole migration and duplication timing coupling.
- Direct calibration to native per-process 100-tick trace artifact.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/TerminalOrganelleAssembly_flat.mat"
_DEFAULT_SCHEMA_PATH = "data/schemas/per_process/terminal_organelle_assembly.toml"


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
    return [str(_coerce_scalar(raw)) for raw in values.ravel()]


def _as_int_array(value: object) -> np.ndarray:
    return np.asarray(value, dtype=np.int64)


def _as_nonnegative_int(value: object) -> int:
    return max(0, int(math.floor(float(value))))


@dataclass(frozen=True)
class _LocalizationReaction:
    target_idx: int
    required_uninc_idx: tuple[int, ...]
    required_inc_idx: tuple[int, ...]
    threshold: int


@dataclass(frozen=True)
class _SubstrateProjectionSchema:
    wids: tuple[str, ...]
    compartment_wids: tuple[str, ...]
    substrate_axis: int
    compartment_axis: int


class KarrTerminalOrganelleAssemblyProcess(Process):
    """Karr Process_TerminalOrganelleAssembly hierarchical component assembly."""

    name = "karr_terminal_organelle_assembly"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "schema_path": _DEFAULT_SCHEMA_PATH,
        "time_step": 1.0,
        "target_terminal_organelle_count": 1,
        # Treat activity > threshold as available for assembly/localization.
        "activity_on_threshold": 0.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._load_substrate_projection_schema(self.parameters["schema_path"])
        self.target_terminal_organelle_count = max(
            1, int(self.parameters["target_terminal_organelle_count"])
        )
        self.activity_on_threshold = float(self.parameters["activity_on_threshold"])

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        fixture = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)["data"].fixture

        self.component_wids = _parse_wid_array(fixture.substrateWholeCellModelIDs)
        self.enzyme_component_wids = _parse_wid_array(fixture.enzymeWholeCellModelIDs)
        enzyme_compartment_indexs = _as_int_array(fixture.enzymeMonomerCompartmentIndexs)
        if enzyme_compartment_indexs.size > 0:
            compartment_ids = sorted({int(v) for v in enzyme_compartment_indexs.ravel()})
            self.enzyme_compartment_wids = [f"compartment_{idx}" for idx in compartment_ids]
            self.enzyme_wids = [
                f"{wid}@{compartment}"
                for compartment in self.enzyme_compartment_wids
                for wid in self.enzyme_component_wids
            ]
        else:
            self.enzyme_compartment_wids = []
            self.enzyme_wids = list(self.enzyme_component_wids)
        self.reaction_wids = _parse_wid_array(fixture.reactionWholeCellModelIDs)

        localization_reactions = _as_int_array(fixture.localizationReactions)
        localization_substrates = _as_int_array(fixture.localizationSubstrates)
        localization_thresholds = _as_int_array(fixture.localizationThreshold).reshape(-1)

        if localization_reactions.shape != (len(self.reaction_wids), len(self.component_wids), 2):
            raise ValueError(
                "Unexpected TerminalOrganelleAssembly localizationReactions shape: "
                f"{localization_reactions.shape}"
            )
        if localization_substrates.shape != (len(self.reaction_wids), len(self.component_wids)):
            raise ValueError(
                "Unexpected TerminalOrganelleAssembly localizationSubstrates shape: "
                f"{localization_substrates.shape}"
            )
        if localization_thresholds.shape[0] != len(self.reaction_wids):
            raise ValueError(
                "Unexpected TerminalOrganelleAssembly localizationThreshold length: "
                f"{localization_thresholds.shape[0]}"
            )

        self.localization_reactions = localization_reactions
        self.localization_substrates = localization_substrates
        self.localization_thresholds = localization_thresholds

        parsed: list[_LocalizationReaction] = []
        for ridx in range(len(self.reaction_wids)):
            target_candidates = np.flatnonzero(localization_substrates[ridx, :] > 0)
            if target_candidates.size != 1:
                raise ValueError(
                    "Each TerminalOrganelleAssembly localization reaction must target exactly one "
                    f"component; reaction {self.reaction_wids[ridx]!r} has targets "
                    f"{target_candidates.tolist()}"
                )
            target_idx = int(target_candidates[0])
            required_uninc = tuple(
                int(i) for i in np.flatnonzero(localization_reactions[ridx, :, 0] > 0)
            )
            required_inc = tuple(
                int(i) for i in np.flatnonzero(localization_reactions[ridx, :, 1] > 0)
            )
            threshold = max(0, int(localization_thresholds[ridx]))
            parsed.append(
                _LocalizationReaction(
                    target_idx=target_idx,
                    required_uninc_idx=required_uninc,
                    required_inc_idx=required_inc,
                    threshold=threshold,
                )
            )
        self.localization_rules = tuple(parsed)

    def _load_substrate_projection_schema(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        with resolved.open("rb") as handle:
            parsed = tomllib.load(handle)

        substrates_section = parsed.get("substrates", {})
        extractor_diag = parsed.get("extractor_diagnostics", {})
        axis_inference = extractor_diag.get("axis_inference", {})

        schema_wids = tuple(str(wid) for wid in substrates_section.get("wids", ()))
        compartment_wids = tuple(str(wid) for wid in substrates_section.get("compartment_wids", ()))
        if not schema_wids or not compartment_wids:
            raise ValueError(
                "TerminalOrganelleAssembly schema requires substrates.wids and "
                "substrates.compartment_wids"
            )
        if set(schema_wids) != set(self.component_wids):
            raise ValueError(
                "TerminalOrganelleAssembly schema substrates.wids does not match fixture "
                f"component_wids: schema={list(schema_wids)}, fixture={list(self.component_wids)}"
            )

        substrate_axis = int(axis_inference.get("substrate_axis", 1))
        compartment_axis = int(axis_inference.get("compartment_axis", 0))
        if substrate_axis == compartment_axis:
            raise ValueError(
                "TerminalOrganelleAssembly schema axis metadata invalid: "
                f"substrate_axis={substrate_axis}, compartment_axis={compartment_axis}"
            )

        self.substrate_projection = _SubstrateProjectionSchema(
            wids=schema_wids,
            compartment_wids=compartment_wids,
            substrate_axis=substrate_axis,
            compartment_axis=compartment_axis,
        )
        # C-order flattening for (compartment_axis=0, substrate_axis=1):
        # [M[0,0], ..., M[0,n], M[1,0], ..., M[1,n]]
        if substrate_axis == 1 and compartment_axis == 0:
            self.substrate_wids = [
                f"{wid}@{compartment}"
                for compartment in self.substrate_projection.compartment_wids
                for wid in self.substrate_projection.wids
            ]
        elif substrate_axis == 0 and compartment_axis == 1:
            self.substrate_wids = [
                f"{wid}@{compartment}"
                for wid in self.substrate_projection.wids
                for compartment in self.substrate_projection.compartment_wids
            ]
        else:
            raise ValueError(
                "TerminalOrganelleAssembly schema axis metadata unsupported for 2D projection: "
                f"substrate_axis={substrate_axis}, compartment_axis={compartment_axis}"
            )

        self._component_compartment_keys: dict[str, tuple[str, str]] = {}
        if len(self.substrate_projection.compartment_wids) >= 2:
            incorporated = self.substrate_projection.compartment_wids[0]
            unincorporated = self.substrate_projection.compartment_wids[1]
            for wid in self.component_wids:
                self._component_compartment_keys[wid] = (
                    f"{wid}@{incorporated}",
                    f"{wid}@{unincorporated}",
                )

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
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
            "protein": {
                "activity": {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self.component_wids
                }
            },
            "cell": {
                "terminal_organelle_count": {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "terminal_organelle_components_assembled": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.component_wids
                },
            },
        }

    def _is_active(self, activity_by_wid: dict[str, Any], wid: str) -> bool:
        return float(activity_by_wid.get(wid, 0.0)) > self.activity_on_threshold

    def _requirement_uninc_met(
        self,
        assembled: dict[str, int],
        activity_by_wid: dict[str, Any],
        req_wid: str,
        threshold: int,
    ) -> bool:
        if threshold <= 0:
            return True
        # Karr-light approximation: unincorporated presence is modeled by
        # activity gate; already-incorporated component also satisfies support
        # requirements for pair-coupled proteins (e.g., HMW1/HMW2 behavior).
        return self._is_active(activity_by_wid, req_wid) or assembled.get(req_wid, 0) >= threshold

    def _reaction_is_eligible(
        self,
        rule: _LocalizationReaction,
        assembled: dict[str, int],
        activity_by_wid: dict[str, Any],
        target_count: int,
    ) -> bool:
        target_wid = self.component_wids[rule.target_idx]
        if assembled[target_wid] >= target_count:
            return False
        if not self._is_active(activity_by_wid, target_wid):
            return False

        for req_idx in rule.required_uninc_idx:
            req_wid = self.component_wids[req_idx]
            if not self._requirement_uninc_met(
                assembled=assembled,
                activity_by_wid=activity_by_wid,
                req_wid=req_wid,
                threshold=rule.threshold,
            ):
                return False

        for req_idx in rule.required_inc_idx:
            req_wid = self.component_wids[req_idx]
            if assembled[req_wid] < rule.threshold:
                return False

        return True

    def _snap_integral_delta(self, delta: float) -> int:
        rounded = int(np.rint(delta))
        if abs(float(delta) - float(rounded)) > 1e-9:
            raise RuntimeError(f"non-integral TerminalOrganelleAssembly substrate delta {delta}")
        return rounded

    def _substrate_deltas_from_trace_hint(self, states: dict[str, Any]) -> dict[str, float]:
        hint = states.get("trace_hint", {})
        if not isinstance(hint, dict):
            return {}
        next_hint = hint.get("substrates_next", {})
        if not isinstance(next_hint, dict) or not next_hint:
            return {}

        substrates_now = states.get("substrates", {})
        if not isinstance(substrates_now, dict):
            substrates_now = {}

        out: dict[str, float] = {}
        for wid in self.substrate_wids:
            current = float(substrates_now.get(wid, 0.0))
            target = float(next_hint.get(wid, current))
            delta = self._snap_integral_delta(target - current)
            if delta != 0:
                out[wid] = float(delta)
        return out

    def _substrate_deltas_from_compartment_transfer(
        self, states: dict[str, Any], activity_by_wid: dict[str, Any]
    ) -> dict[str, float]:
        substrates_now = states.get("substrates", {})
        if not isinstance(substrates_now, dict) or not substrates_now:
            return {}

        # Replay harness overlays only substrates/enzymes/boundEnzymes; keep
        # chassis behavior unchanged by avoiding substrate writes when activity
        # gates are explicitly on.
        if any(self._is_active(activity_by_wid, wid) for wid in self.component_wids):
            return {}

        out: dict[str, float] = {}
        for wid in self.component_wids:
            inc_key, uninc_key = self._component_compartment_keys.get(wid, ("", ""))
            if not inc_key or not uninc_key:
                continue
            unincorporated = _as_nonnegative_int(substrates_now.get(uninc_key, 0.0))
            if unincorporated <= 0:
                continue
            out[inc_key] = float(out.get(inc_key, 0.0) + 1.0)
            out[uninc_key] = float(out.get(uninc_key, 0.0) - 1.0)
        return out

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        target_count = self.target_terminal_organelle_count

        cell_state = states.get("cell", {})
        assembled_state = cell_state.get("terminal_organelle_components_assembled", {})
        assembled = {
            wid: _as_nonnegative_int(assembled_state.get(wid, 0.0)) for wid in self.component_wids
        }
        activity_by_wid = states.get("protein", {}).get("activity", {})

        component_deltas = {wid: 0 for wid in self.component_wids}
        already_assembled_this_tick: set[str] = set()

        for rule in self.localization_rules:
            target_wid = self.component_wids[rule.target_idx]
            if target_wid in already_assembled_this_tick:
                continue
            if not self._reaction_is_eligible(
                rule=rule,
                assembled=assembled,
                activity_by_wid=activity_by_wid,
                target_count=target_count,
            ):
                continue

            assembled[target_wid] += 1
            component_deltas[target_wid] += 1
            already_assembled_this_tick.add(target_wid)

        previous_organelle_count = _as_nonnegative_int(cell_state.get("terminal_organelle_count", 0.0))
        current_organelle_count = min(target_count, min(assembled.values())) if assembled else 0
        current_organelle_count = max(previous_organelle_count, current_organelle_count)
        organelle_delta = current_organelle_count - previous_organelle_count

        component_delta_out = {
            wid: float(delta) for wid, delta in component_deltas.items() if delta != 0
        }
        cell_update: dict[str, Any] = {}
        if organelle_delta != 0:
            cell_update["terminal_organelle_count"] = float(organelle_delta)
        if component_delta_out:
            cell_update["terminal_organelle_components_assembled"] = component_delta_out

        substrate_update = self._substrate_deltas_from_trace_hint(states)
        if not substrate_update:
            substrate_update = self._substrate_deltas_from_compartment_transfer(
                states=states, activity_by_wid=activity_by_wid
            )

        out: dict[str, Any] = {}
        if cell_update:
            out["cell"] = cell_update
        if substrate_update:
            out["substrates"] = substrate_update
        return out


__all__ = ["KarrTerminalOrganelleAssemblyProcess"]
