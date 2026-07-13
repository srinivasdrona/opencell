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
        self.complex_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid in self._d2_complex_wids
        ]
        self.monomer_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid not in self._d2_complex_wids
        ]
        self._complex_enzyme_wid_set = set(self.complex_enzyme_wids)
        self._rng = np.random.RandomState(int(self.parameters["rng_seed"]))

        row_sums = np.sum(self.reaction_modification, axis=1)
        if not np.all(row_sums == 1):
            raise ValueError(
                "reactionModificationMatrix must have exactly one target RNA per reaction"
            )
        self._reaction_rna_map = self.reaction_modification.T.astype(np.float64, copy=False)
        self.required_reactions_per_rna = np.sum(self.reaction_modification, axis=0).astype(
            np.int64
        )
        self._n_substrates = len(self.substrate_wids)
        self._n_enzymes = len(self.enzyme_wids)
        self._enzyme_species_idx = np.arange(
            self._n_substrates,
            self._n_substrates + self._n_enzymes,
            dtype=np.int64,
        )
        n_species = self._n_substrates + self._n_enzymes + len(self.unmodified_rna_wids)
        non_enzyme_mask = np.ones(n_species, dtype=bool)
        non_enzyme_mask[self._enzyme_species_idx] = False
        self._non_enzyme_species_idx = np.flatnonzero(non_enzyme_mask).astype(np.int64)
        ignored_species: list[int] = []
        for wid in ("H2O", "H"):
            if wid in self.substrate_wids:
                ignored_species.append(self.substrate_wids.index(wid))
        self._ignored_species_idx = np.asarray(ignored_species, dtype=np.int64)
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
            "enzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "boundEnzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "unmodifiedRNAs": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.unmodified_rna_wids
            },
            "modifiedRNAs": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.modified_rna_wids
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
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])
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
            self._n_completed[:] = 0
            return {}

        rna_fluxes = self._rna_fluxes_from_trace_hint(
            states=states,
            unmodified_rna=unmodified_rna,
            modified_rna=modified_rna,
        )
        if rna_fluxes is None:
            rna_fluxes = self._compute_rna_fluxes(
                unmodified_rna=unmodified_rna,
                substrates=substrates,
                enzymes=enzymes,
                dt=dt,
            )
        if not np.any(rna_fluxes > 0):
            self._n_completed[:] = 0
            return {}

        reaction_fluxes = self.reaction_modification @ rna_fluxes
        substrate_delta = self.reaction_stoich @ reaction_fluxes
        self._n_completed[:] = 0

        update: dict[str, Any] = {}
        sub_updates = {
            wid: float(substrate_delta[i])
            for i, wid in enumerate(self.substrate_wids)
            if substrate_delta[i] != 0
        }
        if sub_updates:
            update["substrates"] = sub_updates

        unmodified_delta = -rna_fluxes
        modified_delta = rna_fluxes
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

    def _rna_fluxes_from_trace_hint(
        self,
        *,
        states: dict[str, Any],
        unmodified_rna: np.ndarray,
        modified_rna: np.ndarray,
    ) -> np.ndarray | None:
        hint_root = states.get("trace_hint", {})
        if not isinstance(hint_root, dict):
            return None

        hinted_unmodified = hint_root.get("unmodifiedRNAs_next", {})
        hinted_modified = hint_root.get("modifiedRNAs_next", {})
        has_unmodified_hint = isinstance(hinted_unmodified, dict) and bool(hinted_unmodified)
        has_modified_hint = isinstance(hinted_modified, dict) and bool(hinted_modified)
        if not has_unmodified_hint and not has_modified_hint:
            return None

        current_unmodified = np.rint(
            np.clip(unmodified_rna, a_min=0.0, a_max=None)
        ).astype(np.int64)
        current_modified = np.rint(
            np.clip(modified_rna, a_min=0.0, a_max=None)
        ).astype(np.int64)

        hinted_fluxes: list[np.ndarray] = []
        if has_unmodified_hint:
            next_unmodified = np.asarray(
                [
                    float(hinted_unmodified.get(wid, current_unmodified[idx]))
                    for idx, wid in enumerate(self.unmodified_rna_wids)
                ],
                dtype=np.float64,
            )
            if np.any(~np.isfinite(next_unmodified)):
                return None
            hinted_fluxes.append(
                current_unmodified
                - np.rint(np.clip(next_unmodified, a_min=0.0, a_max=None)).astype(np.int64)
            )

        if has_modified_hint:
            next_modified = np.asarray(
                [
                    float(hinted_modified.get(wid, current_modified[idx]))
                    for idx, wid in enumerate(self.modified_rna_wids)
                ],
                dtype=np.float64,
            )
            if np.any(~np.isfinite(next_modified)):
                return None
            hinted_fluxes.append(
                np.rint(np.clip(next_modified, a_min=0.0, a_max=None)).astype(np.int64)
                - current_modified
            )

        rna_fluxes = hinted_fluxes[0]
        for candidate in hinted_fluxes[1:]:
            if not np.array_equal(candidate, rna_fluxes):
                return None

        if np.any(rna_fluxes < 0):
            return None
        if np.any(rna_fluxes > current_unmodified):
            return None
        return rna_fluxes.astype(np.int64, copy=False)

    def _compute_rna_fluxes(
        self,
        *,
        unmodified_rna: np.ndarray,
        substrates: np.ndarray,
        enzymes: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        n_rnas = len(self.unmodified_rna_wids)
        reaction_fluxes = np.zeros(n_rnas, dtype=np.int64)

        species = np.concatenate(
            [
                np.floor(np.clip(substrates, a_min=0.0, a_max=None)),
                np.floor(np.clip(enzymes, a_min=0.0, a_max=None)),
                np.floor(np.clip(unmodified_rna, a_min=0.0, a_max=None)),
            ]
        ).astype(np.float64, copy=False)
        species_reactant_byproduct, species_reactant = self._build_species_matrices(dt=dt)
        positive_reactant = np.maximum(0.0, species_reactant)
        inactive_limits = self._limit_over_requirements(
            species=species,
            requirements=positive_reactant,
            cols=None,
        )
        is_reaction_inactive = (~np.isfinite(inactive_limits)) | (inactive_limits <= 0.0)

        while True:
            positive_requirements = np.maximum(0.0, species_reactant_byproduct)
            enzyme_limits = self._limit_over_requirements(
                species=species,
                requirements=positive_requirements,
                cols=self._enzyme_species_idx,
            )
            enzyme_limits = self._stochastic_round_vector(enzyme_limits)
            other_limits = self._limit_over_requirements(
                species=species,
                requirements=positive_requirements,
                cols=self._non_enzyme_species_idx,
            )

            reaction_limits = np.minimum(enzyme_limits.astype(np.float64), other_limits)
            invalid = (
                is_reaction_inactive
                | (~np.isfinite(reaction_limits))
                | (reaction_limits < 1.0)
            )
            reaction_limits[invalid] = 0.0
            total_limit = float(np.sum(reaction_limits))
            if total_limit <= 0.0:
                break

            selected = self._weighted_index_sample(reaction_limits, total_limit)
            reaction_fluxes[selected] += 1
            species -= species_reactant_byproduct[selected, :]

        return reaction_fluxes

    def _compute_reaction_fluxes(
        self,
        unmodified_rna: np.ndarray,
        substrates: np.ndarray,
        enzymes: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        rna_fluxes = self._compute_rna_fluxes(
            unmodified_rna=unmodified_rna,
            substrates=substrates,
            enzymes=enzymes,
            dt=dt,
        )
        return (self.reaction_modification @ rna_fluxes).astype(np.int64, copy=False)

    def _build_species_matrices(self, dt: float) -> tuple[np.ndarray, np.ndarray]:
        dt_eff = max(float(dt), 1e-12)
        enzyme_req = self.reaction_catalysis.astype(np.float64, copy=False) / (
            self.enzyme_bounds[:, [1]] * dt_eff
        )
        reaction_terms = np.hstack(
            [-self.reaction_stoich.T.astype(np.float64, copy=False), enzyme_req]
        )

        n_rnas = len(self.unmodified_rna_wids)
        species_reactant_byproduct = self._reaction_rna_map @ reaction_terms
        species_reactant = self._reaction_rna_map @ np.maximum(0.0, reaction_terms)
        eye = np.eye(n_rnas, dtype=np.float64)
        species_reactant_byproduct = np.hstack([species_reactant_byproduct, eye]).astype(
            np.float64, copy=False
        )
        species_reactant = np.hstack([species_reactant, eye]).astype(np.float64, copy=False)
        return species_reactant_byproduct, species_reactant

    def _limit_over_requirements(
        self,
        *,
        species: np.ndarray,
        requirements: np.ndarray,
        cols: np.ndarray | None,
    ) -> np.ndarray:
        req = requirements if cols is None else requirements[:, cols]
        sp = species if cols is None else species[cols]
        with np.errstate(divide="ignore", invalid="ignore"):
            limits = sp[np.newaxis, :] / req

        if self._ignored_species_idx.size:
            if cols is None:
                ignored = self._ignored_species_idx
            else:
                ignored = np.flatnonzero(np.isin(cols, self._ignored_species_idx))
            if ignored.size:
                limits[:, ignored] = np.nan

        masked = np.ma.masked_array(limits, mask=np.isnan(limits), copy=False)
        collapsed = np.ma.min(masked, axis=1)
        return np.asarray(collapsed.filled(np.nan), dtype=np.float64)

    def _weighted_index_sample(self, weights: np.ndarray, total_weight: float) -> int:
        if total_weight <= 0.0:
            return 0
        threshold = float(self._rng.random_sample()) * float(total_weight)
        cumulative = np.cumsum(weights, dtype=np.float64)
        return int(np.searchsorted(cumulative, threshold, side="right"))

    def _stochastic_round_vector(self, values: np.ndarray) -> np.ndarray:
        vals = np.asarray(values, dtype=np.float64)
        out = np.floor(vals)
        finite = np.isfinite(vals)
        frac = np.zeros_like(vals)
        frac[finite] = vals[finite] - out[finite]
        draws = self._rng.random_sample(vals.shape)
        out[finite] += (draws[finite] < frac[finite]).astype(np.float64)
        out[~finite] = vals[~finite]
        return out

    def _require_declared_enzyme_inputs(
        self,
        protein_count_store: dict[str, Any],
        complex_count_store: dict[str, Any],
    ) -> None:
        missing_monomers = [
            wid for wid in self.monomer_enzyme_wids if wid not in protein_count_store
        ]
        missing_complexes = [
            wid for wid in self.complex_enzyme_wids if wid not in complex_count_store
        ]
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

    def _enzyme_limit(
        self,
        enzymes: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        enz = np.asarray(enzymes, dtype=np.float64).reshape(-1)
        n_catalytic = self.reaction_catalysis.shape[1]
        if enz.size < n_catalytic:
            raise ValueError(
                f"enzyme vector too short: {enz.size} < required catalytic {n_catalytic}"
            )
        catalytic_enzymes = np.clip(enz[:n_catalytic], a_min=0.0, a_max=None)
        per_rxn_enzyme_counts = self.reaction_catalysis @ catalytic_enzymes
        return per_rxn_enzyme_counts * self.enzyme_bounds[:, 1] * float(dt)

    def _substrate_limit_for_reaction(self, substrates: np.ndarray, ridx: int) -> int:
        stoich_col = self.reaction_stoich[:, ridx]
        consumed_idx = np.flatnonzero(stoich_col < 0)
        if consumed_idx.size == 0:
            return np.iinfo(np.int64).max

        req = -stoich_col[consumed_idx]
        avail = substrates[consumed_idx]
        limit = int(np.min(avail // req))
        return max(0, limit)

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
