"""Vivarium Process for Karr HostInteraction (literal boolean-cascade port).

Primary source:
- data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/HostInteraction.m
- data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/Host.m
- docs/karr_extracts/process/27_HostInteraction.md

Karr's HostInteraction.evolveState() is a pure, memoryless boolean cascade
recomputed FRESH every tick from the CURRENT (raw, not fractional) copy
numbers of 14 enzyme monomers/complexes -- there is no RNG, no rate
constant, and no timestep dependence anywhere in the source:

    isBacteriumAdherent = all(enzymes(terminalOrganelle) > 0) && all(enzymes(adhesin) > 0)
    isTLRActivated(1)   = isBacteriumAdherent && any(enzymes(tlr12Ligand) > 0)
    isTLRActivated(2)   = isBacteriumAdherent && (any(enzymes(tlr12Ligand) > 0) || any(enzymes(tlr26Ligand) > 0))
    isTLRActivated(6)   = isBacteriumAdherent && any(enzymes(tlr26Ligand) > 0)
    isNFkBActivated     = (isTLRActivated(2) && isTLRActivated(1)) || (isTLRActivated(2) && isTLRActivated(6))
    isInflammatoryResponseActivated = isNFkBActivated || (isBacteriumAdherent && any(enzymes(antigen) > 0))

A prior "Karr-light v1" revision of this module replaced this cascade with a
fabricated continuous adhesion-fraction + stochastic Poisson bind/unbind
model (CODE_DEVIATES per docs/phase_f/audits/HostInteraction_semantic_audit.md
HI-S4-01/HI-S4-02/HI-S5-02) and never modeled the TLR/NF-kB/inflammatory
outputs at all. This revision replaces that approximation with the literal
port above (L2.1 closure, see
docs/phase_f/l2_1/HOSTINTERACTION_ACTIVE_WINDOW_DECISION.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/HostInteraction_flat.mat"


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


# Host cell-state keys this process owns (mirrors Karr's Host state object's
# 4 boolean properties -- see Host.m). Kept as a module-level tuple so
# ports_schema() and next_update() can never silently drift apart.
_HOST_BOOLEAN_FIELDS = (
    "host_attached",  # Host.isBacteriumAdherent
    "host_tlr1_activated",  # Host.isTLRActivated(Host.tlrIndexs_1 == 1)
    "host_tlr2_activated",  # Host.isTLRActivated(Host.tlrIndexs_2 == 2)
    "host_tlr6_activated",  # Host.isTLRActivated(Host.tlrIndexs_6 == 3)
    "host_nfkb_activated",  # Host.isNFkBActivated
    "host_inflammatory_response_activated",  # Host.isInflammatoryResponseActivated
)


class KarrHostInteractionProcess(Process):
    """Literal port of Karr's HostInteraction boolean adherence/signaling cascade."""

    name = "karr_host_interaction"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "time_step": 1.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)
        self.substrate_wids = _parse_wid_array(fx.substrateWholeCellModelIDs)
        self.enzyme_ref_counts = np.asarray(fx.enzymes, dtype=np.float64).reshape(-1)
        if self.enzyme_ref_counts.size != len(self.enzyme_wids):
            raise ValueError(
                "HostInteraction fixture mismatch: enzyme count vector size differs from WIDs"
            )

        def _wids_for(role_group_attr: str) -> list[str]:
            idx = _parse_index_array(getattr(fx, role_group_attr)) - 1
            return [self.enzyme_wids[int(i)] for i in idx.tolist()]

        # Index sets exactly as declared by HostInteraction.m's own
        # enzymeIndexs_* properties (see role_groups in
        # data/karr_input_spec/HostInteraction.yaml, which mirrors them
        # 1:1 with wids already resolved).
        self.terminal_organelle_wids = _wids_for("enzymeIndexs_terminalOrganelle")
        self.adhesin_wids = _wids_for("enzymeIndexs_adhesin")
        self.tlr12_ligand_wids = _wids_for("enzymeIndexs_tlr12Ligand")
        self.tlr26_ligand_wids = _wids_for("enzymeIndexs_tlr26Ligand")
        self.antigen_wids = _wids_for("enzymeIndexs_antigen")

    def ports_schema(self) -> dict[str, Any]:
        required_wids = sorted(
            set(self.terminal_organelle_wids)
            | set(self.adhesin_wids)
            | set(self.tlr12_ligand_wids)
            | set(self.tlr26_ligand_wids)
            | set(self.antigen_wids)
        )
        return {
            # substrates/enzymes/boundEnzymes: HostInteraction.m declares
            # substrateWholeCellModelIDs = {} and never reads/writes
            # this.substrates/this.boundEnzymes (evolveState only reads
            # this.enzymes and only mutates this.host's booleans -- see
            # HostInteraction.m:266-303). These ports are wired-conformance
            # pass-throughs only (never mutated by next_update, matching
            # the L2a replay contract in
            # tests/vivarium/test_karr_host_interaction_l2_replay.py), not
            # read by the real biology below.
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
            "cell": {
                field: {"_default": False, "_updater": "set", "_emit": True}
                for field in _HOST_BOOLEAN_FIELDS
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in required_wids
                }
            },
        }

    @staticmethod
    def _all_nonzero(wids: list[str], counts_state: dict[str, Any]) -> bool:
        # MATLAB all([]) == true (vacuous truth); mirrored here rather than
        # short-circuiting on an empty index set, matching HostInteraction.m's
        # own `all(this.enzymes(idx))` semantics exactly.
        if not wids:
            return True
        return all(float(counts_state.get(wid, 0.0)) > 0.0 for wid in wids)

    @staticmethod
    def _any_nonzero(wids: list[str], counts_state: dict[str, Any]) -> bool:
        # MATLAB any([]) == false.
        return any(float(counts_state.get(wid, 0.0)) > 0.0 for wid in wids)

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        # HostInteraction.evolveState() has no timestep/rate dependence at
        # all -- the cascade below is recomputed identically regardless of
        # dt (see HostInteraction.m:266-303).
        del timestep

        cell_state = states.get("cell", {})
        protein_counts = states.get("protein", {}).get("counts", {})

        is_adherent = self._all_nonzero(
            self.terminal_organelle_wids, protein_counts
        ) and self._all_nonzero(self.adhesin_wids, protein_counts)

        tlr12_ligand_present = self._any_nonzero(self.tlr12_ligand_wids, protein_counts)
        tlr26_ligand_present = self._any_nonzero(self.tlr26_ligand_wids, protein_counts)

        tlr1 = is_adherent and tlr12_ligand_present
        tlr2 = is_adherent and (tlr12_ligand_present or tlr26_ligand_present)
        tlr6 = is_adherent and tlr26_ligand_present

        nfkb = (tlr2 and tlr1) or (tlr2 and tlr6)
        inflammatory = nfkb or (
            is_adherent and self._any_nonzero(self.antigen_wids, protein_counts)
        )

        computed = {
            "host_attached": is_adherent,
            "host_tlr1_activated": tlr1,
            "host_tlr2_activated": tlr2,
            "host_tlr6_activated": tlr6,
            "host_nfkb_activated": nfkb,
            "host_inflammatory_response_activated": inflammatory,
        }

        cell_update = {
            field: value
            for field, value in computed.items()
            if bool(cell_state.get(field, False)) != value
        }

        update: dict[str, Any] = {}
        if cell_update:
            update["cell"] = cell_update
        return update


__all__ = ["KarrHostInteractionProcess"]
