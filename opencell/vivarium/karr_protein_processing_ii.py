"""Vivarium Process port of Karr's ProteinProcessingII flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process, Step

from opencell.vivarium.protein_state import COMPARTMENTS, MIGRATED_WIDS, compartment_counts_schema

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

        # Design 9.3/M05-M08: per-migrated-WID biological compartment (design
        # 4.2 -- ProteinProcessingII.m modifies proteins "in the membrane and
        # cytosol rather than in the terminal organelle membrane or cytosol"
        # L196-198; `monomerCompartments` is the tc->c / tm->m remapped KB
        # compartment used throughout PP2/Folding/Modification). Decoded from
        # the fixture, never hardcoded.
        monomer_compartments_kb = np.asarray(
            fx["monomerCompartments"][0, 0], dtype=np.int64
        ).reshape(-1)
        self.migrated_compartment_by_wid: dict[str, str] = {
            wid: COMPARTMENTS[int(monomer_compartments_kb[i]) - 1]
            for i, wid in enumerate(self.unprocessed_monomer_wids)
            if wid in MIGRATED_WIDS
        }
        enzyme_compartments = np.asarray(
            fx["enzymeMonomerCompartmentIndexs"][0, 0], dtype=np.int64
        ).reshape(-1)
        self.enzyme_compartment_by_wid = {
            wid: COMPARTMENTS[int(enzyme_compartments[i]) - 1]
            for i, wid in enumerate(self.enzyme_wids)
        }

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

    def input_protein_schema(self) -> dict[str, Any]:
        """Source-owned processed-I and mature enzyme inputs (copyFromState)."""
        authority_schema = compartment_counts_schema(MIGRATED_WIDS)
        return {
            "compartment_counts": {
                "processed_i": authority_schema["processed_i"],
                "mature": {
                    wid: authority_schema["mature"][wid] for wid in self.enzyme_wids
                },
            },
        }

    def read_processing_inputs(
        self, states: dict[str, Any]
    ) -> tuple[np.ndarray, np.ndarray]:
        """ProteinProcessingII.m:205-217 and Process.m:611-670 live inputs."""
        protein = states.get("protein", {})
        authority = protein.get("compartment_counts", {})
        processed_i = authority.get("processed_i", {})
        legacy_counts = protein.get("counts", {})
        precursors = np.asarray([
            float(processed_i.get(wid, {}).get(self.migrated_compartment_by_wid[wid], 0.0))
            if wid in MIGRATED_WIDS else float(legacy_counts.get(wid, 0.0))
            for wid in self.unprocessed_monomer_wids
        ], dtype=np.float64)
        mature = authority.get("mature", {})
        enzymes = np.asarray([
            float(mature.get(wid, {}).get(self.enzyme_compartment_by_wid[wid], 0.0))
            for wid in self.enzyme_wids
        ], dtype=np.float64)
        return precursors, enzymes

    def calculate_request(self, states: dict[str, Any]) -> dict[str, float]:
        """ProteinProcessingII.m:325-345; no substrate availability or RNG."""
        precursors, enzymes = self.read_processing_inputs(states)
        dt = float(self.parameters["time_step"])
        request = np.zeros(len(self.substrate_wids), dtype=np.float64)
        request[self.substrate_index_water] = min(
            np.ceil(enzymes[self.enzyme_index_signal_peptidase]
                    * self.lipoprotein_signal_peptidase_specific_rate * dt),
            np.sum(precursors[self.peptidase_indices]),
        )
        request[self.substrate_index_pg160] = min(
            np.ceil(enzymes[self.enzyme_index_dag_transferase]
                    * self.lipoprotein_diacylglyceryl_transferase_specific_rate * dt),
            np.sum(precursors[self.lipoprotein_indices]),
        )
        return {wid: float(request[i]) for i, wid in enumerate(self.substrate_wids)}

    def ports_schema(self) -> dict[str, Any]:
        authority_schema = compartment_counts_schema(MIGRATED_WIDS)
        input_schema = self.input_protein_schema()
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
                    if wid not in MIGRATED_WIDS
                },
                "unfolded_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.processed_monomer_wids
                    if wid not in MIGRATED_WIDS
                },
                "signal_sequence_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.signal_sequence_monomer_wids
                    if wid not in MIGRATED_WIDS
                },
                "enzyme_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.enzyme_wids
                },
                # Keep the nonmigrated standalone legacy route undeclared:
                # chassis counts are mature, not processed-I. Exposing them
                # here would newly drain that mature pool via pass-through.
                # The bounded migrated inputs below are the live authority.
                "compartment_counts": {
                    **input_schema["compartment_counts"],
                    "processed_ii": authority_schema["processed_ii"],
                    "signal_sequence": authority_schema["signal_sequence"],
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
        unprocessed_all, enzymes = self.read_processing_inputs(states)
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
            if processed_delta[i] != 0 and wid not in MIGRATED_WIDS
        }
        unprocessed_update = {
            wid: float(unprocessed_delta_vec[i])
            for i, wid in enumerate(self.unprocessed_monomer_wids)
            if unprocessed_delta_vec[i] != 0 and wid not in MIGRATED_WIDS
        }
        signal_update = {
            wid: float(signal_delta[i])
            for i, wid in enumerate(self.signal_sequence_monomer_wids)
            if signal_delta[i] != 0 and wid not in MIGRATED_WIDS
        }

        # Design 9.3/M05-M07: migrated WIDs route processedI decrement /
        # processedII increment through the authority, each at its own
        # biological compartment (m for the 3 membrane-destined WIDs, c for
        # the 5 cytosol-destined WIDs -- design 4.2/4.4).
        processed_i_authority_update: dict[str, dict[str, float]] = {}
        processed_ii_authority_update: dict[str, dict[str, float]] = {}
        signal_authority_update = {
            wid: {"c": float(signal_delta[i])}
            for i, wid in enumerate(self.signal_sequence_monomer_wids)
            if wid in MIGRATED_WIDS and signal_delta[i] != 0
        }
        for i, wid in enumerate(self.unprocessed_monomer_wids):
            if wid not in MIGRATED_WIDS:
                continue
            comp = self.migrated_compartment_by_wid[wid]
            if unprocessed_delta_vec[i] != 0:
                processed_i_authority_update[wid] = {comp: float(unprocessed_delta_vec[i])}
            if processed_delta[i] != 0:
                processed_ii_authority_update[wid] = {comp: float(processed_delta[i])}

        protein_update: dict[str, Any] = {}
        if processed_update:
            protein_update["processed_counts"] = processed_update
        if unprocessed_update:
            protein_update["counts"] = unprocessed_update
        if signal_update:
            protein_update["signal_sequence_counts"] = signal_update
        if processed_i_authority_update or processed_ii_authority_update or signal_authority_update:
            protein_update["compartment_counts"] = {
                "processed_i": processed_i_authority_update,
                "processed_ii": processed_ii_authority_update,
                "signal_sequence": signal_authority_update,
            }
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


PP2_PHASE_STORE_KEY = "_internal_protein_processing_ii_phase"


def _phase_ports_schema() -> dict[str, Any]:
    return {"request_ready": {"_default": False, "_updater": "set", "_emit": False}}


class KarrProteinProcessingIIRequestProcess(Process):
    """Arm this tick's calculator/allocation/evolution without evolving at t0."""

    name = "karr_protein_processing_ii"
    defaults: dict[str, Any] = {"time_step": 1.0}

    def ports_schema(self) -> dict[str, Any]:
        return {"phase": _phase_ports_schema()}

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep, states
        return {"phase": {"request_ready": True}}


class KarrProteinProcessingIIEvolutionStep(Step):
    """Consume the new grant once per armed request via public next_update."""

    name = "karr_protein_processing_ii_evolution"
    defaults: dict[str, Any] = {"processing_process": None}

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        process = self.parameters["processing_process"]
        if not isinstance(process, KarrProteinProcessingIIProcess):
            raise ValueError("PP2 evolution requires an explicit KarrProteinProcessingIIProcess")
        self.processing_process = process

    def ports_schema(self) -> dict[str, Any]:
        schema = self.processing_process.ports_schema()
        schema["phase"] = _phase_ports_schema()
        return schema

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        if states.get("phase", {}).get("request_ready") is not True:
            return {}
        update = self.processing_process.next_update(timestep, states)
        update["phase"] = {"request_ready": False}
        return update


__all__ = [
    "KarrProteinProcessingIIProcess",
    "KarrProteinProcessingIIRequestProcess",
    "KarrProteinProcessingIIEvolutionStep",
    "PP2_PHASE_STORE_KEY",
]
