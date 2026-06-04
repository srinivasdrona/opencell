"""Vivarium Process port of Karr's tRNA aminoacylation flow."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/tRNAAminoacylation_flat.mat"
_D2_COMPLEX_FIXTURE_PATH = "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"
_RIBASM_COMPLEX_FIXTURE_PATH = "data/karr_fixtures/per_process/RibosomeAssembly_flat.mat"
_MAX_STOCHASTIC_ITERATIONS = 50_000


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


def _zero_based_index(value: np.ndarray) -> int:
    return int(np.asarray(value, dtype=np.int64).reshape(-1)[0]) - 1


@lru_cache(maxsize=1)
def _canonical_complex_wids() -> frozenset[str]:
    d2_mat = loadmat(str(_resolve_fixture_path(_D2_COMPLEX_FIXTURE_PATH)))
    d2_fx = d2_mat["data"]["fixture"][0, 0]
    d2_wids = set(_parse_wid_array(d2_fx["complexWholeCellModelIDs"]))

    ribasm_mat = loadmat(str(_resolve_fixture_path(_RIBASM_COMPLEX_FIXTURE_PATH)))
    ribasm_fx = ribasm_mat["data"]["fixture"][0, 0]
    ribasm_wids = set(_parse_wid_array(ribasm_fx["complexWholeCellModelIDs"]))

    return frozenset(d2_wids | ribasm_wids | {"RNA_POLYMERASE", "RIBOSOME_70S"})


class KarrTRNAAminoacylationProcess(Process):
    """Karr Process_tRNAAminoacylation replay-faithful species update."""

    name = "karr_trna_aminoacylation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "max_stochastic_iterations": _MAX_STOCHASTIC_ITERATIONS,
        "emit_noop_update": False,
        "emit_trace_heartbeat_on_noop": False,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        self.n_species_enzymes = int(self.species_enzyme_indices.size)
        self.catalytic_enzyme_wids = self.enzyme_wids[: self.n_species_enzymes]
        canonical_complex_wids = _canonical_complex_wids()
        self.complex_enzyme_wids = [
            wid for wid in self.catalytic_enzyme_wids if wid in canonical_complex_wids
        ]
        self.monomer_enzyme_wids = [
            wid for wid in self.catalytic_enzyme_wids if wid not in canonical_complex_wids
        ]
        self._enzyme_index_by_wid = {wid: idx for idx, wid in enumerate(self.enzyme_wids)}

        row_sums = np.sum(self.reaction_modification, axis=1)
        if not np.all(row_sums == 1):
            raise ValueError(
                "reactionModificationMatrix must have exactly one target RNA per reaction"
            )
        if self.species_reactant_matrix.shape[0] != len(self.free_rna_wids):
            raise ValueError("speciesReactantMatrix row count must equal free RNA count")
        if self.species_reactant_byproduct_matrix.shape != self.species_reactant_matrix.shape:
            raise ValueError("species reactant matrices must have identical shape")

        n_species_cols = int(self.species_reactant_matrix.shape[1])
        all_cols = np.arange(n_species_cols, dtype=np.int64)
        self.species_non_enzyme_indices = np.setdiff1d(
            all_cols,
            self.species_enzyme_indices,
            assume_unique=False,
        )
        self._species_reactant_byproduct_nonnegative = np.maximum(
            0.0, self.species_reactant_byproduct_matrix
        )

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        self.substrate_wids = _parse_wid_array(fx["substrateWholeCellModelIDs"])
        self.free_rna_wids = _parse_wid_array(fx["freeRNAWholeCellModelIDs"])
        self.aminoacylated_rna_wids = _parse_wid_array(fx["aminoacylatedRNAWholeCellModelIDs"])
        self.enzyme_wids = _parse_wid_array(fx["enzymeWholeCellModelIDs"])

        self.reaction_stoich = np.asarray(fx["reactionStoichiometryMatrix"][0, 0], dtype=np.int64)
        self.reaction_modification = np.asarray(
            fx["reactionModificationMatrix"][0, 0], dtype=np.int64
        )
        self.species_reactant_byproduct_matrix = np.asarray(
            fx["speciesReactantByproductMatrix"][0, 0], dtype=np.float64
        )
        self.species_reactant_matrix = np.asarray(
            fx["speciesReactantMatrix"][0, 0], dtype=np.float64
        )
        self.species_enzyme_indices = (
            np.asarray(fx["speciesIndexs_enzymes"][0, 0], dtype=np.int64).reshape(-1) - 1
        )
        self.substrate_idx_water = _zero_based_index(fx["substrateIndexs_water"][0, 0])
        self.substrate_idx_hydrogen = _zero_based_index(fx["substrateIndexs_hydrogen"][0, 0])

    def ports_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {
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
            "freeRNAs": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.free_rna_wids
            },
            "aminoacylatedRNAs": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.aminoacylated_rna_wids
            },
            "rna": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.free_rna_wids
                },
                "aminoacylated_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.aminoacylated_rna_wids
                },
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.monomer_enzyme_wids
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
        if self.complex_enzyme_wids:
            schema["complex"] = {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.complex_enzyme_wids
                }
            }
        return schema

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
        substrates = np.asarray(
            [max(0.0, float(allocated_state.get(wid, 0.0))) for wid in self.substrate_wids],
            dtype=np.float64,
        )

        free_store = rna_state.get("counts", {})
        if not isinstance(free_store, dict):
            free_store = {}
        if not free_store:
            free_store = self._legacy_vector_to_wid_counts(states.get("freeRNAs"), self.free_rna_wids)
        free_rna = np.asarray(
            [float(free_store.get(wid, 0.0)) for wid in self.free_rna_wids],
            dtype=np.float64,
        )

        amino_store = rna_state.get("aminoacylated_counts", {})
        if not isinstance(amino_store, dict):
            amino_store = {}
        if not amino_store:
            amino_store = self._legacy_vector_to_wid_counts(
                states.get("aminoacylatedRNAs"),
                self.aminoacylated_rna_wids,
            )
        aminoacylated_rna = np.asarray(
            [float(amino_store.get(wid, 0.0)) for wid in self.aminoacylated_rna_wids],
            dtype=np.float64,
        )

        protein_count_store = protein_state.get("counts", {})
        if not isinstance(protein_count_store, dict):
            protein_count_store = {}
        complex_count_store = complex_state.get("counts", {})
        if not isinstance(complex_count_store, dict):
            complex_count_store = {}
        enzymes = self._read_enzyme_vector(
            states=states,
            protein_count_store=protein_count_store,
            complex_count_store=complex_count_store,
        )

        if free_rna.sum() <= 0.0:
            return self._noop_update() if bool(self.parameters.get("emit_noop_update", False)) else {}

        reaction_fluxes = self._compute_rna_fluxes(
            substrates=substrates,
            enzymes=enzymes,
            free_rna=free_rna,
        )
        if not np.any(reaction_fluxes > 0):
            return self._noop_update() if bool(self.parameters.get("emit_noop_update", False)) else {}

        reaction_events_by_rxn = self.reaction_modification @ reaction_fluxes
        reaction_events_by_rxn = np.rint(reaction_events_by_rxn).astype(np.int64)

        substrate_delta = self.reaction_stoich @ reaction_events_by_rxn
        substrate_delta = np.rint(substrate_delta).astype(np.int64)
        free_delta = -reaction_fluxes
        aminoacylated_delta = reaction_fluxes

        update: dict[str, Any] = {}
        sub_updates = {
            wid: float(substrate_delta[i])
            for i, wid in enumerate(self.substrate_wids)
            if substrate_delta[i] != 0
        }
        if sub_updates:
            update["substrates"] = sub_updates

        free_updates = {
            wid: float(free_delta[i])
            for i, wid in enumerate(self.free_rna_wids)
            if free_delta[i] != 0
        }
        amino_updates = {
            wid: float(aminoacylated_delta[i])
            for i, wid in enumerate(self.aminoacylated_rna_wids)
            if aminoacylated_delta[i] != 0
        }
        if free_updates or amino_updates:
            update["rna"] = {
                "counts": free_updates,
                "aminoacylated_counts": amino_updates,
            }

        _ = aminoacylated_rna
        return update

    def _read_enzyme_vector(
        self,
        *,
        states: dict[str, Any],
        protein_count_store: dict[str, Any],
        complex_count_store: dict[str, Any],
    ) -> np.ndarray:
        enzyme_store = states.get("enzymes", {})
        if isinstance(enzyme_store, dict):
            if all(wid in enzyme_store for wid in self.catalytic_enzyme_wids):
                return np.asarray(
                    [float(enzyme_store.get(wid, 0.0)) for wid in self.enzyme_wids],
                    dtype=np.float64,
                )

        return self._enzyme_vector_from_split_stores(
            protein_count_store=protein_count_store,
            complex_count_store=complex_count_store,
        )

    def _enzyme_vector_from_split_stores(
        self,
        *,
        protein_count_store: dict[str, Any],
        complex_count_store: dict[str, Any],
    ) -> np.ndarray:
        missing_monomers = [wid for wid in self.monomer_enzyme_wids if wid not in protein_count_store]
        if missing_monomers:
            missing = ", ".join(missing_monomers[:5])
            raise KeyError(
                "karr_trna_aminoacylation missing required monomer enzyme WIDs in protein.counts: "
                f"{missing}"
            )

        missing_complexes = [wid for wid in self.complex_enzyme_wids if wid not in complex_count_store]
        if missing_complexes:
            missing = ", ".join(missing_complexes[:5])
            raise KeyError(
                "karr_trna_aminoacylation missing required complex enzyme WIDs in complex.counts: "
                f"{missing}"
            )

        enzyme_values = np.zeros(len(self.enzyme_wids), dtype=np.float64)
        for wid in self.monomer_enzyme_wids:
            enzyme_values[self._enzyme_index_by_wid[wid]] = float(protein_count_store[wid])
        for wid in self.complex_enzyme_wids:
            enzyme_values[self._enzyme_index_by_wid[wid]] = float(complex_count_store[wid])
        return enzyme_values

    def _compute_rna_fluxes(
        self,
        *,
        substrates: np.ndarray,
        enzymes: np.ndarray,
        free_rna: np.ndarray,
    ) -> np.ndarray:
        if enzymes.size < self.n_species_enzymes:
            raise ValueError(
                f"enzyme vector too short: {enzymes.size} < required {self.n_species_enzymes}"
            )

        n_rna = len(self.free_rna_wids)
        reaction_fluxes = np.zeros(n_rna, dtype=np.int64)
        species = np.concatenate(
            [substrates, enzymes[: self.n_species_enzymes], free_rna],
            axis=0,
        ).astype(np.float64, copy=False)

        initial_limits = self._limits_from_species(species, self.species_reactant_matrix)
        reaction_limits = np.nanmin(initial_limits, axis=1)
        reaction_limits[(~np.isfinite(reaction_limits)) | (reaction_limits < 0)] = 0.0
        is_reaction_inactive = reaction_limits <= 0.0

        max_iters = int(self.parameters["max_stochastic_iterations"])
        for _ in range(max_iters):
            limits = self._limits_from_species(
                species,
                self._species_reactant_byproduct_nonnegative,
            )

            enzyme_limits = np.nanmin(limits[:, self.species_enzyme_indices], axis=1)
            rounded_enzyme_limits = self._stochastic_round(enzyme_limits)
            non_enzyme_limits = np.nanmin(limits[:, self.species_non_enzyme_indices], axis=1)
            reaction_limits = np.minimum(rounded_enzyme_limits, non_enzyme_limits)
            reaction_limits[
                is_reaction_inactive
                | (~np.isfinite(reaction_limits))
                | (reaction_limits < 1.0)
            ] = 0.0

            active = reaction_limits > 0.0
            if not np.any(active):
                break

            edges = np.minimum(
                np.concatenate(([0.0], np.cumsum(reaction_limits / np.sum(reaction_limits)))),
                1.0,
            )
            n_rxns = float(np.min(reaction_limits[active]))

            if n_rxns <= 1.0:
                selected = self._histc_bin_index(float(self._rng.random()), edges)
                reaction_fluxes[selected] += 1
                species -= self.species_reactant_byproduct_matrix[selected, :]
                continue

            draws = int(np.floor(n_rxns))
            if draws <= 0:
                break

            multi_edges = edges.copy()
            multi_edges[-1] = 1.1
            selected_counts = self._histc_counts(
                self._rng.random(draws),
                multi_edges,
                n_bins=n_rna,
            )
            if not np.any(selected_counts):
                continue

            reaction_fluxes += selected_counts
            species -= selected_counts @ self.species_reactant_byproduct_matrix

        return reaction_fluxes

    def _limits_from_species(
        self,
        species: np.ndarray,
        reactant_matrix: np.ndarray,
    ) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            limits = species[np.newaxis, :] / reactant_matrix
        limits[:, self.substrate_idx_water] = np.nan
        limits[:, self.substrate_idx_hydrogen] = np.nan
        return limits

    def _stochastic_round(self, values: np.ndarray) -> np.ndarray:
        vals = np.asarray(values, dtype=np.float64)
        out = np.floor(vals)
        finite = np.isfinite(vals)
        frac = np.zeros_like(vals)
        frac[finite] = vals[finite] - out[finite]
        out[finite] += (self._rng.random(vals.shape)[finite] < frac[finite]).astype(np.float64)
        out[~finite] = vals[~finite]
        return out

    @staticmethod
    def _histc_bin_index(value: float, edges: np.ndarray) -> int:
        idx = int(np.searchsorted(edges, value, side="right")) - 1
        return int(np.clip(idx, 0, len(edges) - 2))

    @staticmethod
    def _histc_counts(values: np.ndarray, edges: np.ndarray, *, n_bins: int) -> np.ndarray:
        bins = np.searchsorted(edges, values, side="right") - 1
        bins = np.clip(bins, 0, n_bins)
        counts = np.bincount(bins, minlength=n_bins + 1)[:n_bins]
        return counts.astype(np.int64, copy=False)

    @staticmethod
    def _noop_update() -> dict[str, Any]:
        return {
            "substrates": {},
            "rna": {
                "counts": {},
                "aminoacylated_counts": {},
            },
        }

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


__all__ = ["KarrTRNAAminoacylationProcess"]
