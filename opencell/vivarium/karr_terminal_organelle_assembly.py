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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/TerminalOrganelleAssembly_flat.mat"


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


class KarrTerminalOrganelleAssemblyProcess(Process):
    """Karr Process_TerminalOrganelleAssembly hierarchical component assembly."""

    name = "karr_terminal_organelle_assembly"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "time_step": 1.0,
        "target_terminal_organelle_count": 1,
        # Treat activity > threshold as available for assembly/localization.
        "activity_on_threshold": 0.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self.target_terminal_organelle_count = max(
            1, int(self.parameters["target_terminal_organelle_count"])
        )
        self.activity_on_threshold = float(self.parameters["activity_on_threshold"])

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        fixture = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)["data"].fixture

        self.component_wids = _parse_wid_array(fixture.substrateWholeCellModelIDs)
        self.enzyme_wids = _parse_wid_array(fixture.enzymeWholeCellModelIDs)
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

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.component_wids
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

        if not cell_update:
            return {}
        return {"cell": cell_update}


__all__ = ["KarrTerminalOrganelleAssemblyProcess"]
