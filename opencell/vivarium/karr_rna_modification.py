"""Vivarium Process port of Karr's RNA modification flow."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/RNAModification_flat.mat"
_D2_COMPLEX_FIXTURE_PATH = "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"
_MAX_STOCHASTIC_ITERATIONS = 10_000


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


@lru_cache(maxsize=1)
def _load_d2_complex_wids(path: str = _D2_COMPLEX_FIXTURE_PATH) -> frozenset[str]:
    resolved = _resolve_fixture_path(path)
    mat = loadmat(str(resolved))
    fx = mat["data"]["fixture"][0, 0]
    return frozenset(_parse_wid_array(fx["complexWholeCellModelIDs"]))


class KarrRNAModificationProcess(Process):
    """Karr Process_RNAModification with internal per-RNA completion counters."""

    name = "karr_rna_modification"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "max_stochastic_iterations": _MAX_STOCHASTIC_ITERATIONS,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._d2_complex_wids = _load_d2_complex_wids()
        self.complex_enzyme_wids = [wid for wid in self.enzyme_wids if wid in self._d2_complex_wids]
        self.monomer_enzyme_wids = [wid for wid in self.enzyme_wids if wid not in self._d2_complex_wids]
        self._complex_enzyme_wid_set = set(self.complex_enzyme_wids)
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        row_sums = np.sum(self.reaction_modification, axis=1)
        if not np.all(row_sums == 1):
            raise ValueError(
                "reactionModificationMatrix must have exactly one target RNA per reaction"
            )
        self._reaction_target_idx = np.argmax(self.reaction_modification, axis=1).astype(np.int64)

        self.required_reactions_per_rna = np.sum(self.reaction_modification, axis=0).astype(
            np.int64
        )
        self._n_completed = np.zeros(len(self.unmodified_rna_wids), dtype=np.int64)

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        all_unmodified = _parse_wid_array(fx["unmodifiedRNAWholeCellModelIDs"])
        all_modified = _parse_wid_array(fx["modifiedRNAWholeCellModelIDs"])

        raw_reaction_modification = np.asarray(
            fx["reactionModificationMatrix"][0, 0], dtype=np.uint8
        )
        self._active_rna_indices = np.flatnonzero(
            np.sum(raw_reaction_modification, axis=0) > 0
        ).astype(np.int64)
        if self._active_rna_indices.size == 0:
            raise ValueError("No active RNA modification targets found in fixture")

        self.substrate_wids = _parse_wid_array(fx["substrateWholeCellModelIDs"])
        self.unmodified_rna_wids = [all_unmodified[i] for i in self._active_rna_indices]
        self.modified_rna_wids = [all_modified[i] for i in self._active_rna_indices]
        self.enzyme_wids = _parse_wid_array(fx["enzymeWholeCellModelIDs"])

        self.reaction_stoich = np.asarray(fx["reactionStoichiometryMatrix"][0, 0], dtype=np.int64)
        self.reaction_catalysis = np.asarray(fx["reactionCatalysisMatrix"][0, 0], dtype=np.uint8)
        self.reaction_modification = raw_reaction_modification[:, self._active_rna_indices]
        self.enzyme_bounds = np.asarray(fx["enzymeBounds"][0, 0], dtype=np.float64)

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
            },
            "rna": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.unmodified_rna_wids
                },
                "modified_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.modified_rna_wids
                },
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.monomer_enzyme_wids
                }
            },
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.complex_enzyme_wids
                }
            },
            "requests": {
                self.name: {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.substrate_wids
                }
            },
            "substrates_allocated": {
                self.name: {
                    wid: {"_default": 0.0, "_emit": False}
                    for wid in self.substrate_wids
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        rna_state = states.get("rna", {})
        if not isinstance(rna_state, dict):
            rna_state = {}
        protein_state = states.get("protein", {})
        if not isinstance(protein_state, dict):
            protein_state = {}
        complex_state = states.get("complex", {})
        if not isinstance(complex_state, dict):
            complex_state = {}

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        # Strict-zero allocator contract: do not fallback to global substrate pools.
        substrates = np.asarray(
            [
                max(0.0, float(allocated_state.get(wid, 0.0)))
                for wid in self.substrate_wids
            ],
            dtype=np.float64,
        )
        unmodified_store = rna_state.get("counts", {})
        if not isinstance(unmodified_store, dict):
            unmodified_store = {}
        if not unmodified_store:
            unmodified_store = self._legacy_vector_to_wid_counts(
                states.get("unmodifiedRNAs"),
                self.unmodified_rna_wids,
            )
        unmodified_rna = np.asarray(
            [float(unmodified_store.get(wid, 0.0)) for wid in self.unmodified_rna_wids],
            dtype=np.float64,
        )
        modified_store = rna_state.get("modified_counts", {})
        if not isinstance(modified_store, dict):
            modified_store = {}
        if not modified_store:
            modified_store = self._legacy_vector_to_wid_counts(
                states.get("modifiedRNAs"),
                self.modified_rna_wids,
            )
        modified_rna = np.asarray(
            [
                float(modified_store.get(wid, 0.0))
                for wid in self.modified_rna_wids
            ],
            dtype=np.float64,
        )
        protein_count_store = protein_state.get("counts", {})
        if not isinstance(protein_count_store, dict):
            protein_count_store = {}
        complex_count_store = complex_state.get("counts", {})
        if not isinstance(complex_count_store, dict):
            complex_count_store = {}
        self._require_declared_enzyme_inputs(
            protein_count_store=protein_count_store,
            complex_count_store=complex_count_store,
        )
        enzymes = np.asarray(
            [
                float(complex_count_store[wid])
                if wid in self._complex_enzyme_wid_set
                else float(protein_count_store[wid])
                for wid in self.enzyme_wids
            ],
            dtype=np.float64,
        )

        if unmodified_rna.sum() <= 0.0:
            return {}

        reaction_fluxes = self._compute_reaction_fluxes(
            unmodified_rna=unmodified_rna,
            substrates=substrates,
            enzymes=enzymes,
            dt=float(self.parameters["time_step"]),
        )
        if not np.any(reaction_fluxes > 0):
            return {}

        substrate_delta = self.reaction_stoich @ reaction_fluxes
        completed_this_step = (self.reaction_modification.T @ reaction_fluxes).astype(np.int64)
        self._n_completed += completed_this_step

        transition_events = np.zeros_like(self._n_completed)
        for ridx, required in enumerate(self.required_reactions_per_rna):
            if required <= 0:
                continue
            if self._n_completed[ridx] >= required and unmodified_rna[ridx] > 0.0:
                transition_events[ridx] = 1
                self._n_completed[ridx] = 0

        update: dict[str, Any] = {}
        sub_updates = {
            wid: float(substrate_delta[i])
            for i, wid in enumerate(self.substrate_wids)
            if substrate_delta[i] != 0
        }
        if sub_updates:
            update["substrates"] = sub_updates

        unmodified_delta = -transition_events
        modified_delta = transition_events
        unmodified_updates = {
            wid: float(unmodified_delta[i])
            for i, wid in enumerate(self.unmodified_rna_wids)
            if unmodified_delta[i] != 0
        }
        modified_updates = {
            wid: float(modified_delta[i])
            for i, wid in enumerate(self.modified_rna_wids)
            if modified_delta[i] != 0
        }
        if unmodified_updates or modified_updates:
            update["rna"] = {
                "counts": unmodified_updates,
                "modified_counts": modified_updates,
            }

        # Keep explicit read-path for modified store in tests and engines.
        _ = modified_rna
        return update

    def _require_declared_enzyme_inputs(
        self,
        protein_count_store: dict[str, Any],
        complex_count_store: dict[str, Any],
    ) -> None:
        missing_monomers = [wid for wid in self.monomer_enzyme_wids if wid not in protein_count_store]
        missing_complexes = [wid for wid in self.complex_enzyme_wids if wid not in complex_count_store]
        if not missing_monomers and not missing_complexes:
            return

        parts: list[str] = []
        if missing_monomers:
            parts.append(f"protein.counts missing {missing_monomers}")
        if missing_complexes:
            parts.append(f"complex.counts missing {missing_complexes}")
        raise ValueError(
            "KarrRNAModificationProcess missing declared enzyme inputs: " + "; ".join(parts)
        )

    def _compute_reaction_fluxes(
        self,
        unmodified_rna: np.ndarray,
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
        unmodified_available = (np.asarray(unmodified_rna) > 0).astype(np.int64)
        reaction_remaining = unmodified_available[self._reaction_target_idx].copy()

        # Phase 1: deterministic allocation.
        for ridx in range(n_rxn):
            sub_limit = self._substrate_limit_for_reaction(substrate_pool, ridx)
            enz_limit = int(enzyme_remaining[ridx])
            reaction_limit = int(reaction_remaining[ridx])
            n_events = int(min(sub_limit, enz_limit, reaction_limit))
            if n_events <= 0:
                continue

            reaction_fluxes[ridx] += n_events
            substrate_pool += self.reaction_stoich[:, ridx] * n_events
            enzyme_remaining[ridx] -= n_events
            reaction_remaining[ridx] -= n_events

        # Phase 2: stochastic residual sampling.
        max_iters = int(self.parameters["max_stochastic_iterations"])
        for _ in range(max_iters):
            progressed = self._stochastic_residual_step(
                reaction_fluxes=reaction_fluxes,
                substrate_pool=substrate_pool,
                enzyme_remaining=enzyme_remaining,
                reaction_remaining=reaction_remaining,
            )
            if not progressed:
                break

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

    def _stochastic_residual_step(
        self,
        reaction_fluxes: np.ndarray,
        substrate_pool: np.ndarray,
        enzyme_remaining: np.ndarray,
        reaction_remaining: np.ndarray,
    ) -> bool:
        substrate_limit = self._substrate_limit(substrate_pool)
        residual_limit = np.minimum.reduce([substrate_limit, enzyme_remaining, reaction_remaining])

        feasible = np.flatnonzero(residual_limit > 0)
        if feasible.size == 0:
            return False

        weights = residual_limit[feasible].astype(np.float64)
        weight_sum = float(np.sum(weights))
        if weight_sum <= 0.0:
            return False

        chosen = int(self._rng.choice(feasible, p=(weights / weight_sum)))
        if enzyme_remaining[chosen] <= 0 or reaction_remaining[chosen] <= 0:
            return False

        reaction_fluxes[chosen] += 1
        substrate_pool += self.reaction_stoich[:, chosen]
        enzyme_remaining[chosen] -= 1
        reaction_remaining[chosen] -= 1
        return True

    @staticmethod
    def _legacy_vector_to_wid_counts(
        values: Any,
        wids: list[str],
    ) -> dict[str, float]:
        if values is None:
            return {}
        try:
            flat = np.asarray(values, dtype=np.float64).reshape(-1)
        except (TypeError, ValueError):
            return {}
        if flat.size != len(wids):
            return {}
        return {wid: float(flat[idx]) for idx, wid in enumerate(wids)}


__all__ = ["KarrRNAModificationProcess"]
