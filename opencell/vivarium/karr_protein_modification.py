"""Vivarium Process port of Karr's protein covalent modifications."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinModification_flat.mat"
_MAX_STOCHASTIC_ITERATIONS = 100_000


def _resolve_fixture_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


def _parse_wid_array(cell_array: np.ndarray) -> list[str]:
    """Convert MATLAB cell-string arrays into a flat Python string list."""
    values = np.asarray(cell_array, dtype=object)
    if values.shape == (1, 1):
        values = np.asarray(values[0, 0], dtype=object)

    out: list[str] = []
    for raw in values.ravel():
        value: object = raw
        while isinstance(value, np.ndarray):
            if value.size == 0:
                value = ""
                break
            value = value.flat[0]
        out.append(str(value))
    return out


class KarrProteinModificationProcess(Process):
    """Karr Process_ProteinModification with per-protein completion counters."""

    name = "karr_protein_modification"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "max_stochastic_iterations": _MAX_STOCHASTIC_ITERATIONS,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))
        self._n_completed = np.zeros(len(self.unmodified_monomer_wids), dtype=np.int64)

        row_sums = np.sum(self.reaction_modification, axis=1)
        if not np.all(row_sums == 1):
            raise ValueError("reactionModificationMatrix must map each reaction to one protein")
        self._reaction_target_idx = np.argmax(self.reaction_modification, axis=1).astype(np.int64)

        self.required_modifications = np.sum(self.reaction_modification, axis=0).astype(np.int64)
        if np.any(self.required_modifications <= 0):
            raise ValueError("Filtered proteins must each require at least one modification reaction")

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        self.substrate_wids = _parse_wid_array(fx["substrateWholeCellModelIDs"])
        self.enzyme_wids = _parse_wid_array(fx["enzymeWholeCellModelIDs"])
        all_unmodified_wids = _parse_wid_array(fx["unmodifiedMonomerWholeCellModelIDs"])
        all_modified_wids = _parse_wid_array(fx["modifiedMonomerWholeCellModelIDs"])

        self.reaction_stoich = np.asarray(fx["reactionStoichiometryMatrix"][0, 0], dtype=np.int64)
        self.reaction_catalysis = np.asarray(fx["reactionCatalysisMatrix"][0, 0], dtype=np.uint8)
        full_reaction_modification = np.asarray(
            fx["reactionModificationMatrix"][0, 0], dtype=np.uint8
        )
        self.enzyme_bounds = np.asarray(fx["enzymeBounds"][0, 0], dtype=np.float64)

        self.active_protein_indices = np.flatnonzero(
            np.sum(full_reaction_modification, axis=0) > 0
        ).astype(np.int64)
        self.unmodified_monomer_wids = [
            all_unmodified_wids[idx] for idx in self.active_protein_indices
        ]
        self.modified_monomer_wids = [
            all_modified_wids[idx] for idx in self.active_protein_indices
        ]
        self.reaction_modification = full_reaction_modification[:, self.active_protein_indices]

        if self.reaction_stoich.shape[1] != self.reaction_catalysis.shape[0]:
            raise ValueError("Reaction dimension mismatch between stoichiometry and catalysis")
        if self.reaction_stoich.shape[1] != self.reaction_modification.shape[0]:
            raise ValueError("Reaction dimension mismatch between stoichiometry and modification")
        if self.reaction_stoich.shape[0] != len(self.substrate_wids):
            raise ValueError("Substrate dimension mismatch between stoichiometry and WIDs")
        if self.reaction_catalysis.shape[1] != len(self.enzyme_wids):
            raise ValueError("Enzyme dimension mismatch between catalysis and WIDs")

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.enzyme_wids
                },
                "unmodified_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.unmodified_monomer_wids
                },
                "modified_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.modified_monomer_wids
                },
            },
            "requests": {
                self.name: {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.substrate_wids
                }
            },
            "substrates_allocated": {
                self.name: {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.substrate_wids
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        substrate_state = states.get("substrates", {})
        substrates = np.asarray(
            [
                float(allocated_state.get(wid, 0.0))
                if float(allocated_state.get(wid, 0.0)) > 0.0
                else float(substrate_state.get(wid, 0.0))
                for wid in self.substrate_wids
            ],
            dtype=np.float64,
        )
        enzymes = np.asarray(
            [float(states["protein"]["counts"].get(wid, 0.0)) for wid in self.enzyme_wids],
            dtype=np.float64,
        )
        unmodified = np.asarray(
            [
                float(states["protein"]["unmodified_counts"].get(wid, 0.0))
                for wid in self.unmodified_monomer_wids
            ],
            dtype=np.float64,
        )
        if unmodified.sum() <= 0.0:
            return {}

        reaction_fluxes = self._sample_reaction_fluxes(
            unmodified=unmodified,
            substrates=substrates,
            enzymes=enzymes,
            dt=dt,
        )
        if not np.any(reaction_fluxes > 0):
            return {}

        substrate_delta = self.reaction_stoich @ reaction_fluxes
        completed_by_protein = self.reaction_modification.T @ reaction_fluxes
        self._n_completed += completed_by_protein

        unmodified_pool = np.floor(np.clip(unmodified, a_min=0.0, a_max=None)).astype(np.int64)
        protein_completions = np.minimum(
            unmodified_pool,
            self._n_completed // self.required_modifications,
        ).astype(np.int64)
        self._n_completed -= protein_completions * self.required_modifications

        update: dict[str, Any] = {}
        substrate_updates = {
            wid: float(substrate_delta[i])
            for i, wid in enumerate(self.substrate_wids)
            if substrate_delta[i] != 0
        }
        if substrate_updates:
            update["substrates"] = substrate_updates

        unmodified_updates = {
            wid: float(-protein_completions[i])
            for i, wid in enumerate(self.unmodified_monomer_wids)
            if protein_completions[i] > 0
        }
        modified_updates = {
            wid: float(protein_completions[i])
            for i, wid in enumerate(self.modified_monomer_wids)
            if protein_completions[i] > 0
        }
        if unmodified_updates or modified_updates:
            update["protein"] = {
                "unmodified_counts": unmodified_updates,
                "modified_counts": modified_updates,
            }

        return update

    def _sample_reaction_fluxes(
        self,
        unmodified: np.ndarray,
        substrates: np.ndarray,
        enzymes: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        n_rxn = self.reaction_stoich.shape[1]
        reaction_fluxes = np.zeros(n_rxn, dtype=np.int64)

        substrate_pool = np.floor(np.clip(substrates, a_min=0.0, a_max=None)).astype(np.int64)
        enzyme_remaining = np.floor(
            np.clip(self._enzyme_limit(enzymes=enzymes, dt=dt), a_min=0.0, a_max=None)
        ).astype(np.int64)
        unmodified_pool = np.floor(np.clip(unmodified, a_min=0.0, a_max=None)).astype(np.int64)
        protein_capacity = np.maximum(
            0, unmodified_pool * self.required_modifications - self._n_completed
        ).astype(np.int64)

        max_iters = int(self.parameters["max_stochastic_iterations"])
        for _ in range(max_iters):
            substrate_limit = self._substrate_limit(substrate_pool)
            target_limit = protein_capacity[self._reaction_target_idx]
            residual_limit = np.minimum.reduce([substrate_limit, target_limit, enzyme_remaining])
            feasible = np.flatnonzero(residual_limit > 0)
            if feasible.size == 0:
                break

            weights = residual_limit[feasible].astype(np.float64)
            weight_sum = float(np.sum(weights))
            if weight_sum <= 0.0:
                break

            chosen = int(self._rng.choice(feasible, p=(weights / weight_sum)))
            target_idx = int(self._reaction_target_idx[chosen])
            if protein_capacity[target_idx] <= 0:
                continue

            reaction_fluxes[chosen] += 1
            substrate_pool += self.reaction_stoich[:, chosen]
            enzyme_remaining[chosen] -= 1
            protein_capacity[target_idx] -= 1

        return reaction_fluxes

    def _substrate_limit_for_reaction(self, substrates: np.ndarray, ridx: int) -> int:
        stoich_col = self.reaction_stoich[:, ridx]
        consumed_idx = np.flatnonzero(stoich_col < 0)
        if consumed_idx.size == 0:
            return np.iinfo(np.int64).max

        req = -stoich_col[consumed_idx]
        avail = substrates[consumed_idx]
        limit = int(np.min(avail // req))
        return max(0, limit)

    def _substrate_limit(self, substrates: np.ndarray) -> np.ndarray:
        substrate_pool = np.floor(np.clip(substrates, a_min=0.0, a_max=None)).astype(np.int64)
        n_rxn = self.reaction_stoich.shape[1]
        limits = np.zeros(n_rxn, dtype=np.int64)
        for ridx in range(n_rxn):
            limits[ridx] = self._substrate_limit_for_reaction(substrate_pool, ridx)
        return limits

    def _enzyme_limit(self, enzymes: np.ndarray, dt: float) -> np.ndarray:
        enz = np.asarray(enzymes, dtype=np.float64).reshape(-1)
        n_catalytic = self.reaction_catalysis.shape[1]
        if enz.size < n_catalytic:
            raise ValueError(
                f"enzyme vector too short: {enz.size} < required catalytic {n_catalytic}"
            )
        catalytic_enzymes = np.clip(enz[:n_catalytic], a_min=0.0, a_max=None)
        per_rxn_enzyme_counts = self.reaction_catalysis @ catalytic_enzymes
        return per_rxn_enzyme_counts * self.enzyme_bounds[:, 1] * float(dt)


__all__ = ["KarrProteinModificationProcess"]
