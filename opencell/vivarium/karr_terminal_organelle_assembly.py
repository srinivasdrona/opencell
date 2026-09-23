"""Vivarium Process port of Karr's TerminalOrganelleAssembly (Design D4 rewrite).

Primary source: `TerminalOrganelleAssembly.m` (fixed-point localization
hierarchy, `evolveState` L316-337; plane/threshold definitions L124-125,
165-230, 279). Design section 4.2 proves Karr's TOA owns no private state:
`this.substrates` is a linear-index *view* of `ProteinMonomer.counts`,
refreshed each tick by `Process.m:569-571` and written back by
`Process.m:818-820`. This port reproduces that: it declares ONE `protein`
port mapped onto the compartmental authority's `mature` row, builds its
local 8x2 (incorporated, unincorporated) working view directly from that
row every tick, executes Karr's exact fixed-point transfer, and emits the
result back as a compartment-count delta. There is no `cell` port, no
`substrates`/`enzymes`/`boundEnzymes` port, no activity gate, no
`target_terminal_organelle_count` cap, and no replay-only input read
(design D4; all of those were the Karr-light reduced-state substitute this
rewrite deletes).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.vivarium.protein_state import COMPARTMENTS

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/TerminalOrganelleAssembly_flat.mat"

# MATLAB `compartmentIndexs_incorporated = 1` / `compartmentIndexs_unincorporated = 2`
# (TerminalOrganelleAssembly.m:124-125) as 0-based plane indices into the
# fixture's 3rd axis (`localizationReactions`) / 2nd axis (`substrates`,
# `substrateMonomerCompartmentIndexs`).
_PLANE_INCORPORATED = 0
_PLANE_UNINCORPORATED = 1


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


@dataclass(frozen=True)
class _LocalizationReaction:
    target_idx: int
    required_uninc_idx: tuple[int, ...]
    required_inc_idx: tuple[int, ...]
    threshold: int


class KarrTerminalOrganelleAssemblyProcess(Process):
    """Karr Process_TerminalOrganelleAssembly: fixed-point hierarchical
    localization executed directly against the compartmental ProteinMonomer
    authority's `mature` row (design D4). No private substrate matrix.
    """

    name = "karr_terminal_organelle_assembly"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "time_step": 1.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        fixture = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)["data"].fixture

        self.component_wids = _parse_wid_array(fixture.substrateWholeCellModelIDs)
        self.reaction_wids = _parse_wid_array(fixture.reactionWholeCellModelIDs)

        # Metadata retained ONLY for L2.1 replay pass-through length checks
        # (`enzymes`/`boundEnzymes` are Karr pass-through observables this
        # process's `evolveState` never reads -- `ReactionProcess`'s generic
        # machinery populates them; TOA's `evolveState` reads only
        # `this.substrates`, TerminalOrganelleAssembly.m:316-337). Not used
        # in `ports_schema`/`next_update`.
        self.enzyme_component_wids = _parse_wid_array(fixture.enzymeWholeCellModelIDs)
        enzyme_compartment_indexs = _as_int_array(fixture.enzymeMonomerCompartmentIndexs)
        if enzyme_compartment_indexs.size > 0:
            n_enzyme_compartments = len({int(v) for v in enzyme_compartment_indexs.ravel()})
        else:
            n_enzyme_compartments = 1
        self.enzyme_wids = [
            f"{wid}@{compartment_idx}"
            for compartment_idx in range(n_enzyme_compartments)
            for wid in self.enzyme_component_wids
        ]
        self.substrate_wids = [
            f"{wid}@plane{plane}" for plane in range(2) for wid in self.component_wids
        ]

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

        # Per-component biological compartment ids (design 4.2), decoded from
        # the fixture's own `substrateMonomerCompartmentIndexs` (8x2, 1-based
        # KB compartment index) -- never hardcoded. Column
        # `compartmentIndexs_incorporated`=1 (plane 0 here) is the terminal-
        # organelle destination (tc/tm); column
        # `compartmentIndexs_unincorporated`=2 (plane 1) is the
        # pre-incorporation source (c/m).
        monomer_compartment_idx = _as_int_array(fixture.substrateMonomerCompartmentIndexs)
        if monomer_compartment_idx.shape != (len(self.component_wids), 2):
            raise ValueError(
                "Unexpected TerminalOrganelleAssembly substrateMonomerCompartmentIndexs shape: "
                f"{monomer_compartment_idx.shape}"
            )
        self.incorporated_compartment_by_wid: dict[str, str] = {}
        self.unincorporated_compartment_by_wid: dict[str, str] = {}
        for i, wid in enumerate(self.component_wids):
            inc_kb_idx = int(monomer_compartment_idx[i, _PLANE_INCORPORATED])
            uninc_kb_idx = int(monomer_compartment_idx[i, _PLANE_UNINCORPORATED])
            self.incorporated_compartment_by_wid[wid] = COMPARTMENTS[inc_kb_idx - 1]
            self.unincorporated_compartment_by_wid[wid] = COMPARTMENTS[uninc_kb_idx - 1]

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
            # localizationReactions(i,j,k): protein j in compartment k
            # required for reaction i (TerminalOrganelleAssembly.m:213-214).
            # Plane 0 (compartmentIndexs_incorporated) = incorporated
            # requirement; plane 1 (compartmentIndexs_unincorporated) =
            # unincorporated requirement (evolveState L318-320).
            required_inc = tuple(
                int(i)
                for i in np.flatnonzero(localization_reactions[ridx, :, _PLANE_INCORPORATED] > 0)
            )
            required_uninc = tuple(
                int(i)
                for i in np.flatnonzero(localization_reactions[ridx, :, _PLANE_UNINCORPORATED] > 0)
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
            "protein": {
                "compartment_counts": {
                    "mature": {
                        wid: {comp: {"_default": 0.0} for comp in COMPARTMENTS}
                        for wid in self.component_wids
                    }
                }
            }
        }

    def _active_reactions(self, inc: np.ndarray, uninc: np.ndarray) -> np.ndarray:
        """TerminalOrganelleAssembly.m:318-320 verbatim (as an elementwise sum

        of individually-satisfied requirement indicators, matching the
        matrix-vector product `localizationReactions(:,:,1)*(substrates(:,1)>0)
        + localizationReactions(:,:,2)*(substrates(:,2)>0) >= threshold`).
        """
        active = np.zeros(len(self.localization_rules), dtype=bool)
        for ridx, rule in enumerate(self.localization_rules):
            n_met = sum(1 for j in rule.required_inc_idx if inc[j] > 0) + sum(
                1 for j in rule.required_uninc_idx if uninc[j] > 0
            )
            active[ridx] = n_met >= rule.threshold
        return active

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep

        mature_state = states.get("protein", {}).get("compartment_counts", {}).get("mature", {})

        # Local 8x2 (incorporated, unincorporated) working view, read fresh
        # from the authority every tick -- the Python-side equivalent of
        # Karr's `Process.m:569-571` refresh of `this.substrates` from
        # `ProteinMonomer.counts` (design 4.2). No persistent private state.
        inc = np.zeros(len(self.component_wids), dtype=np.int64)
        uninc = np.zeros(len(self.component_wids), dtype=np.int64)
        for i, wid in enumerate(self.component_wids):
            row = mature_state.get(wid, {})
            inc[i] = int(round(float(row.get(self.incorporated_compartment_by_wid[wid], 0.0))))
            uninc[i] = int(round(float(row.get(self.unincorporated_compartment_by_wid[wid], 0.0))))

        inc_initial = inc.copy()
        uninc_initial = uninc.copy()

        # TerminalOrganelleAssembly.m:316-337 verbatim: fixed-point loop,
        # full-count transfer (`inc += uninc; uninc = 0`), break on no
        # progress.
        while np.any(uninc > 0):
            active_reactions = self._active_reactions(inc, uninc)

            localizing = np.zeros(len(self.component_wids), dtype=bool)
            for ridx, rule in enumerate(self.localization_rules):
                if active_reactions[ridx] and uninc[rule.target_idx] > 0:
                    localizing[rule.target_idx] = True

            if not np.any(localizing):
                break

            inc[localizing] += uninc[localizing]
            uninc[localizing] = 0

        if np.array_equal(inc, inc_initial) and np.array_equal(uninc, uninc_initial):
            return {}

        mature_update: dict[str, dict[str, float]] = {}
        for i, wid in enumerate(self.component_wids):
            delta_inc = float(inc[i] - inc_initial[i])
            delta_uninc = float(uninc[i] - uninc_initial[i])
            if delta_inc == 0.0 and delta_uninc == 0.0:
                continue
            comp_deltas: dict[str, float] = {}
            if delta_inc != 0.0:
                comp_deltas[self.incorporated_compartment_by_wid[wid]] = delta_inc
            if delta_uninc != 0.0:
                comp_deltas[self.unincorporated_compartment_by_wid[wid]] = delta_uninc
            mature_update[wid] = comp_deltas

        if not mature_update:
            return {}

        return {"protein": {"compartment_counts": {"mature": mature_update}}}


__all__ = ["KarrTerminalOrganelleAssemblyProcess"]
