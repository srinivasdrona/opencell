"""Vivarium Process port of Karr's ProteinProcessingII flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinProcessingII_flat.mat"


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


def _parse_index_1based(value: np.ndarray) -> int:
    return int(np.asarray(value[0, 0], dtype=np.int64).reshape(-1)[0]) - 1


class KarrProteinProcessingIIProcess(Process):
    """Karr Process_ProteinProcessingII (lipoprotein DAG transfer + cleavage)."""

    name = "karr_protein_processing_ii"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        self.substrate_wids = _parse_wid_array(fx["substrateWholeCellModelIDs"])
        self.enzyme_wids = _parse_wid_array(fx["enzymeWholeCellModelIDs"])
        self.unprocessed_monomer_wids = _parse_wid_array(fx["unprocessedMonomerWholeCellModelIDs"])
        self.processed_monomer_wids = _parse_wid_array(fx["processedMonomerWholeCellModelIDs"])
        self.signal_sequence_monomer_wids = _parse_wid_array(
            fx["signalSequenceMonomerWholeCellModelIDs"]
        )

        self.substrate_index_water = _parse_index_1based(fx["substrateIndexs_water"])
        self.substrate_index_pg160 = _parse_index_1based(fx["substrateIndexs_PG160"])
        self.substrate_index_snglyp = _parse_index_1based(fx["substrateIndexs_SNGLYP"])
        self.substrate_index_hydrogen = _parse_index_1based(fx["substrateIndexs_hydrogen"])
        self.enzyme_index_signal_peptidase = _parse_index_1based(fx["enzymeIndexs_signalPeptidase"])
        self.enzyme_index_dag_transferase = _parse_index_1based(
            fx["enzymeIndexs_diacylglycerylTransferase"]
        )

        lipoprotein_indices = np.asarray(
            fx["lipoproteinMonomerIndexs"][0, 0], dtype=np.int64
        ).reshape(-1)
        self.lipoprotein_indices = lipoprotein_indices - 1
        self.lipoprotein_wids = [
            self.processed_monomer_wids[int(i)] for i in self.lipoprotein_indices
        ]
        self.secreted_indices = (
            np.asarray(fx["secretedMonomerIndexs"][0, 0], dtype=np.int64).reshape(-1) - 1
        )
        self.non_lipo_non_cleaved_indices = (
            np.asarray(fx["unprocessedMonomerIndexs"][0, 0], dtype=np.int64).reshape(-1) - 1
        )
        self.peptidase_indices = np.concatenate(
            (self.lipoprotein_indices, self.secreted_indices)
        ).astype(np.int64)

        n_sub = len(self.substrate_wids)
        n_lipo = len(self.lipoprotein_indices)
        n_rxn = 2 * n_lipo
        transferase_reaction_index = np.arange(0, n_rxn, 2, dtype=np.int64)
        cleavage_reaction_index = transferase_reaction_index + 1

        # Compatibility surface used by chassis builders (v4/v5): substrate x reaction.
        self.reaction_stoich = np.zeros((n_sub, n_rxn), dtype=np.int64)
        self.reaction_stoich[self.substrate_index_pg160, transferase_reaction_index] = -1
        self.reaction_stoich[self.substrate_index_snglyp, transferase_reaction_index] = 1
        self.reaction_stoich[self.substrate_index_hydrogen, transferase_reaction_index] = 1
        self.reaction_stoich[self.substrate_index_water, cleavage_reaction_index] = -1
        self.substrate_index_dag = self.substrate_index_pg160

        self.lipoprotein_signal_peptidase_specific_rate = float(
            np.asarray(fx["lipoproteinSignalPeptidaseSpecificRate"][0, 0]).reshape(-1)[0]
        )
        self.lipoprotein_diacylglyceryl_transferase_specific_rate = float(
            np.asarray(fx["lipoproteinDiacylglycerylTransferaseSpecificRate"][0, 0]).reshape(-1)[0]
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
            "processedMonomers": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.processed_monomer_wids
            },
            "unprocessedMonomers": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.unprocessed_monomer_wids
            },
            "protein": {
                "processed_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.processed_monomer_wids
                },
                "unfolded_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.processed_monomer_wids
                },
                "signal_sequence_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.signal_sequence_monomer_wids
                },
                "enzyme_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.enzyme_wids
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
                    wid: {"_default": 0.0, "_emit": False}
                    for wid in self.substrate_wids
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        # Strict-zero allocator contract: do not fallback to global substrate pools.
        substrates = np.asarray(
            [
                max(0.0, float(allocated_state.get(wid, 0.0)))
                for wid in self.substrate_wids
            ],
            dtype=np.float64,
        )
        dt = float(self.parameters["time_step"])
        output_wids = self.processed_monomer_wids
        protein_state = states.get("protein", {})
        unprocessed_all = np.asarray(
            [
                float(protein_state.get("counts", {}).get(wid, 0.0))
                for wid in self.unprocessed_monomer_wids
            ],
            dtype=np.float64,
        )
        enzymes = np.asarray(
            [float(protein_state.get("enzyme_counts", {}).get(wid, 0.0)) for wid in self.enzyme_wids],
            dtype=np.float64,
        )
        unprocessed_pool = np.floor(np.clip(unprocessed_all, a_min=0.0, a_max=None)).astype(np.int64)
        substrate_pool = np.floor(np.clip(substrates, a_min=0.0, a_max=None)).astype(np.int64)

        substrate_delta = np.zeros(len(self.substrate_wids), dtype=np.int64)
        processed_delta = np.zeros(len(output_wids), dtype=np.int64)
        unprocessed_delta_vec = np.zeros(len(self.unprocessed_monomer_wids), dtype=np.int64)
        signal_delta = np.zeros(len(self.signal_sequence_monomer_wids), dtype=np.int64)

        # MATLAB evolveState first transitions non-lipoprotein/non-secreted monomers directly.
        pass_through_counts = unprocessed_pool[self.non_lipo_non_cleaved_indices]
        if np.any(pass_through_counts > 0):
            unprocessed_pool[self.non_lipo_non_cleaved_indices] -= pass_through_counts
            processed_delta[self.non_lipo_non_cleaved_indices] += pass_through_counts
            unprocessed_delta_vec[self.non_lipo_non_cleaved_indices] -= pass_through_counts

        if not np.any(unprocessed_pool[self.peptidase_indices] > 0):
            return self._build_update(
                substrate_delta=substrate_delta,
                processed_delta=processed_delta,
                unprocessed_delta_vec=unprocessed_delta_vec,
                signal_delta=signal_delta,
            )

        peptidase_limit = (
            max(0.0, float(enzymes[self.enzyme_index_signal_peptidase]))
            * self.lipoprotein_signal_peptidase_specific_rate
            * dt
        )

        # Phase 1: coupled cleavage + transferase processing when lipoproteins are available.
        if np.any(unprocessed_pool[self.lipoprotein_indices] > 0):
            transferase_limit = (
                max(0.0, float(enzymes[self.enzyme_index_dag_transferase]))
                * self.lipoprotein_diacylglyceryl_transferase_specific_rate
                * dt
            )
            transformations = unprocessed_pool.astype(np.float64)
            self._scale_transformations(
                transformations=transformations,
                indices=self.peptidase_indices,
                limit=peptidase_limit,
            )
            self._scale_transformations(
                transformations=transformations,
                indices=self.lipoprotein_indices,
                limit=transferase_limit,
            )
            transformations_int = self._stochastic_round(transformations)
            self._clip_by_resource(
                transformations=transformations_int,
                indices=self.peptidase_indices,
                available=substrate_pool[self.substrate_index_water],
            )
            self._clip_by_resource(
                transformations=transformations_int,
                indices=self.lipoprotein_indices,
                available=substrate_pool[self.substrate_index_pg160],
            )
            self._apply_transformations(
                transformations=transformations_int,
                substrate_pool=substrate_pool,
                substrate_delta=substrate_delta,
                processed_delta=processed_delta,
                unprocessed_pool=unprocessed_pool,
                unprocessed_delta_vec=unprocessed_delta_vec,
                signal_delta=signal_delta,
            )
            peptidase_limit -= float(np.sum(transformations_int[self.peptidase_indices]))

        # Phase 2: additional peptidase cleavage with remaining activity.
        transformations = unprocessed_pool.astype(np.float64)
        self._scale_transformations(
            transformations=transformations,
            indices=self.peptidase_indices,
            limit=peptidase_limit,
        )
        transformations[self.lipoprotein_indices] = 0.0
        if np.any(transformations > 0):
            transformations_int = self._stochastic_round(transformations)
            self._clip_by_resource(
                transformations=transformations_int,
                indices=self.peptidase_indices,
                available=substrate_pool[self.substrate_index_water],
            )
            self._apply_transformations(
                transformations=transformations_int,
                substrate_pool=substrate_pool,
                substrate_delta=substrate_delta,
                processed_delta=processed_delta,
                unprocessed_pool=unprocessed_pool,
                unprocessed_delta_vec=unprocessed_delta_vec,
                signal_delta=signal_delta,
            )

        return self._build_update(
            substrate_delta=substrate_delta,
            processed_delta=processed_delta,
            unprocessed_delta_vec=unprocessed_delta_vec,
            signal_delta=signal_delta,
        )

    def _build_update(
        self,
        *,
        substrate_delta: np.ndarray,
        processed_delta: np.ndarray,
        unprocessed_delta_vec: np.ndarray,
        signal_delta: np.ndarray,
    ) -> dict[str, Any]:
        update: dict[str, Any] = {}
        substrate_update = {
            wid: float(substrate_delta[i])
            for i, wid in enumerate(self.substrate_wids)
            if substrate_delta[i] != 0
        }
        if substrate_update:
            update["substrates"] = substrate_update

        processed_update = {
            wid: float(processed_delta[i])
            for i, wid in enumerate(self.processed_monomer_wids)
            if processed_delta[i] != 0
        }
        unprocessed_update = {
            wid: float(unprocessed_delta_vec[i])
            for i, wid in enumerate(self.unprocessed_monomer_wids)
            if unprocessed_delta_vec[i] != 0
        }
        signal_update = {
            wid: float(signal_delta[i])
            for i, wid in enumerate(self.signal_sequence_monomer_wids)
            if signal_delta[i] != 0
        }

        protein_update: dict[str, dict[str, float]] = {}
        if processed_update:
            protein_update["processed_counts"] = processed_update
        if unprocessed_update:
            protein_update["counts"] = unprocessed_update
        if signal_update:
            protein_update["signal_sequence_counts"] = signal_update
        if protein_update:
            update["protein"] = protein_update

        return update

    def _scale_transformations(
        self,
        *,
        transformations: np.ndarray,
        indices: np.ndarray,
        limit: float,
    ) -> bool:
        if indices.size == 0:
            return False
        total = float(np.sum(transformations[indices]))
        if total <= 0.0:
            transformations[indices] = 0.0
            return False
        bounded_limit = max(0.0, float(limit))
        scale = min(1.0, bounded_limit / total)
        transformations[indices] *= scale
        return True

    def _stochastic_round(self, values: np.ndarray) -> np.ndarray:
        clipped = np.clip(values, a_min=0.0, a_max=None)
        floors = np.floor(clipped)
        frac = clipped - floors
        draws = self._rng.random(clipped.shape) < frac
        return floors.astype(np.int64) + draws.astype(np.int64)

    def _clip_by_resource(
        self,
        *,
        transformations: np.ndarray,
        indices: np.ndarray,
        available: int,
    ) -> None:
        if indices.size == 0:
            return
        available_int = max(0, int(available))
        current = transformations[indices]
        current_total = int(np.sum(current))
        if current_total <= available_int:
            return
        allocated = self._multinomial_allocation(
            n=available_int,
            weights=current.astype(np.float64),
        )
        transformations[indices] = np.minimum(current, allocated)

    def _multinomial_allocation(self, *, n: int, weights: np.ndarray) -> np.ndarray:
        out = np.zeros(weights.shape[0], dtype=np.int64)
        n_int = max(0, int(n))
        if n_int <= 0:
            return out
        clipped_weights = np.clip(weights, a_min=0.0, a_max=None)
        weight_total = float(np.sum(clipped_weights))
        if weight_total <= 0.0:
            return out
        probs = clipped_weights / weight_total
        return self._rng.multinomial(n_int, probs).astype(np.int64)

    def _apply_transformations(
        self,
        *,
        transformations: np.ndarray,
        substrate_pool: np.ndarray,
        substrate_delta: np.ndarray,
        processed_delta: np.ndarray,
        unprocessed_pool: np.ndarray,
        unprocessed_delta_vec: np.ndarray,
        signal_delta: np.ndarray,
    ) -> None:
        if not np.any(transformations > 0):
            return
        peptidase_events = int(np.sum(transformations[self.peptidase_indices]))
        transferase_events = int(np.sum(transformations[self.lipoprotein_indices]))

        processed_delta += transformations
        unprocessed_pool -= transformations
        unprocessed_delta_vec -= transformations
        signal_delta[self.peptidase_indices] += transformations[self.peptidase_indices]

        if peptidase_events > 0:
            substrate_delta[self.substrate_index_water] -= peptidase_events
            substrate_pool[self.substrate_index_water] -= peptidase_events
        if transferase_events > 0:
            substrate_delta[self.substrate_index_pg160] -= transferase_events
            substrate_delta[self.substrate_index_snglyp] += transferase_events
            substrate_delta[self.substrate_index_hydrogen] += transferase_events
            substrate_pool[self.substrate_index_pg160] -= transferase_events


__all__ = ["KarrProteinProcessingIIProcess"]
