"""Vivarium Process port of Karr's ProteinProcessingII flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinProcessingII_flat.mat"
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


def _parse_index_1based(value: np.ndarray) -> int:
    return int(np.asarray(value[0, 0], dtype=np.int64).reshape(-1)[0]) - 1


class KarrProteinProcessingIIProcess(Process):
    """Karr Process_ProteinProcessingII (lipoprotein DAG transfer + cleavage)."""

    name = "karr_protein_processing_ii"
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

        self.required_reactions = np.sum(self.reaction_modification, axis=0).astype(np.int64)
        self._n_completed = np.zeros(len(self.lipoprotein_wids), dtype=np.int64)
        self._n_dagged_pending = np.zeros(len(self.lipoprotein_wids), dtype=np.int64)

        if not np.all(self.required_reactions == 2):
            raise ValueError("ProteinProcessingII expects exactly two reactions per lipoprotein")

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
        self.substrate_index_dag = _parse_index_1based(fx["substrateIndexs_diacylglycerolCys"])
        self.enzyme_index_signal_peptidase = _parse_index_1based(fx["enzymeIndexs_signalPeptidase"])
        self.enzyme_index_dag_transferase = _parse_index_1based(
            fx["enzymeIndexs_diacylglycerylTransferase"]
        )

        lipoprotein_indices = np.asarray(
            fx["lipoproteinMonomerIndexs"][0, 0], dtype=np.int64
        ).reshape(-1)
        self.lipoprotein_indices = lipoprotein_indices - 1
        self.secreted_indices = (
            np.asarray(fx["secretedMonomerIndexs"][0, 0], dtype=np.int64).reshape(-1) - 1
        )
        self.non_lipo_non_cleaved_indices = (
            np.asarray(fx["unprocessedMonomerIndexs"][0, 0], dtype=np.int64).reshape(-1) - 1
        )
        self.lipoprotein_wids = [
            self.processed_monomer_wids[int(i)] for i in self.lipoprotein_indices
        ]

        dag_rate = float(
            np.asarray(fx["lipoproteinDiacylglycerylTransferaseSpecificRate"][0, 0]).reshape(-1)[0]
        )
        cleave_rate = float(
            np.asarray(fx["lipoproteinSignalPeptidaseSpecificRate"][0, 0]).reshape(-1)[0]
        )

        n_sub = len(self.substrate_wids)
        n_lipo = len(self.lipoprotein_indices)
        n_enz = len(self.enzyme_wids)
        n_rxn = 2 * n_lipo

        self._dag_reaction_index = np.arange(0, n_rxn, 2, dtype=np.int64)
        self._cleavage_reaction_index = self._dag_reaction_index + 1

        self.reaction_stoich = np.zeros((n_sub, n_rxn), dtype=np.int64)
        self.reaction_stoich[self.substrate_index_dag, self._dag_reaction_index] = -1
        self.reaction_stoich[self.substrate_index_water, self._cleavage_reaction_index] = -1

        self.reaction_catalysis = np.zeros((n_rxn, n_enz), dtype=np.uint8)
        self.reaction_catalysis[self._dag_reaction_index, self.enzyme_index_dag_transferase] = 1
        self.reaction_catalysis[
            self._cleavage_reaction_index, self.enzyme_index_signal_peptidase
        ] = 1

        self.reaction_modification = np.zeros((n_rxn, n_lipo), dtype=np.uint8)
        self.reaction_modification[self._dag_reaction_index, np.arange(n_lipo)] = 1
        self.reaction_modification[self._cleavage_reaction_index, np.arange(n_lipo)] = 1

        self.enzyme_bounds = np.zeros((n_rxn, 2), dtype=np.float64)
        self.enzyme_bounds[self._dag_reaction_index, 1] = dag_rate
        self.enzyme_bounds[self._cleavage_reaction_index, 1] = cleave_rate

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
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
        output_wids = self.processed_monomer_wids
        processed_all = np.asarray(
            [
                float(states["protein"].get("processed_counts", {}).get(wid, 0.0))
                for wid in output_wids
            ],
            dtype=np.float64,
        )
        unprocessed_all = np.asarray(
            [float(states["protein"].get("counts", {}).get(wid, 0.0)) for wid in self.unprocessed_monomer_wids],
            dtype=np.float64,
        )
        lipoprotein_processed = processed_all[self.lipoprotein_indices]
        enzymes = np.asarray(
            [
                float(states["protein"].get("enzyme_counts", {}).get(wid, 0.0))
                for wid in self.enzyme_wids
            ],
            dtype=np.float64,
        )
        pass_through_idx = np.concatenate((self.non_lipo_non_cleaved_indices, self.secreted_indices))
        pass_through_counts = np.floor(np.clip(unprocessed_all[pass_through_idx], a_min=0.0, a_max=None)).astype(np.int64)

        if processed_all.sum() <= 0.0 and not np.any(pass_through_counts > 0):
            return {}

        substrate_delta = np.zeros(len(self.substrate_wids), dtype=np.int64)
        processed_delta = np.zeros(len(output_wids), dtype=np.int64)
        unfolded_delta = np.zeros(len(output_wids), dtype=np.int64)
        unprocessed_delta: dict[str, float] = {}
        signal_update: dict[str, float] = {}

        if np.any(pass_through_counts > 0):
            processed_delta[pass_through_idx] += pass_through_counts
            unprocessed_delta = {self.unprocessed_monomer_wids[int(i)]: -float(n) for i, n in zip(pass_through_idx, pass_through_counts) if n > 0}

        if lipoprotein_processed.sum() > 0.0:
            reaction_fluxes = self._compute_reaction_fluxes(
                processed_lipoproteins=lipoprotein_processed,
                substrates=substrates,
                enzymes=enzymes,
                dt=float(self.parameters["time_step"]),
            )
        else:
            reaction_fluxes = np.zeros(self.reaction_stoich.shape[1], dtype=np.int64)

        if np.any(reaction_fluxes > 0):
            substrate_delta += self.reaction_stoich @ reaction_fluxes
            dag_flux = reaction_fluxes[self._dag_reaction_index]
            cleavage_flux = reaction_fluxes[self._cleavage_reaction_index]

            self._n_completed += self.reaction_modification.T @ reaction_fluxes
            self._n_dagged_pending += dag_flux - cleavage_flux
            self._n_dagged_pending = np.clip(self._n_dagged_pending, a_min=0, a_max=None)

            completion_capacity = np.floor_divide(self._n_completed, self.required_reactions)
            lipoprotein_processed_int = np.floor(
                np.clip(lipoprotein_processed, a_min=0.0, a_max=None)
            ).astype(np.int64)
            completed_now = np.minimum.reduce(
                [completion_capacity, cleavage_flux, lipoprotein_processed_int]
            )
            self._n_completed -= completed_now * self.required_reactions

            for lidx, completed in enumerate(completed_now):
                if completed <= 0:
                    continue
                pidx = int(self.lipoprotein_indices[lidx])
                processed_wid = output_wids[pidx]
                signal_wid = self.signal_sequence_monomer_wids[pidx]

                processed_delta[pidx] -= int(completed)
                unfolded_delta[pidx] += int(completed)
                signal_update[signal_wid] = signal_update.get(signal_wid, 0.0) + float(completed)

        update: dict[str, Any] = {}
        substrate_update = {
            wid: float(substrate_delta[i])
            for i, wid in enumerate(self.substrate_wids)
            if substrate_delta[i] != 0
        }
        if substrate_update:
            update["substrates"] = substrate_update

        processed_update = {
            wid: float(processed_delta[i]) for i, wid in enumerate(output_wids) if processed_delta[i] != 0
        }
        unfolded_update = {
            wid: float(unfolded_delta[i]) for i, wid in enumerate(output_wids) if unfolded_delta[i] != 0
        }
        protein_update: dict[str, dict[str, float]] = {}
        if processed_update:
            protein_update["processed_counts"] = processed_update
        if unfolded_update:
            protein_update["unfolded_counts"] = unfolded_update
        if unprocessed_delta:
            protein_update["counts"] = unprocessed_delta
        if signal_update:
            protein_update["signal_sequence_counts"] = signal_update
        if protein_update:
            update["protein"] = protein_update

        return update

    def _compute_reaction_fluxes(
        self,
        processed_lipoproteins: np.ndarray,
        substrates: np.ndarray,
        enzymes: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        n_rxn = self.reaction_stoich.shape[1]
        reaction_fluxes = np.zeros(n_rxn, dtype=np.int64)
        substrate_pool = np.floor(np.clip(substrates, a_min=0.0, a_max=None)).astype(np.int64)
        processed_pool = np.floor(
            np.clip(processed_lipoproteins, a_min=0.0, a_max=None)
        ).astype(np.int64)
        enzyme_remaining = np.floor(
            np.clip(self._enzyme_limit(enzymes=enzymes, dt=dt), a_min=0.0, a_max=None)
        ).astype(np.int64)
        dag_available = np.maximum(processed_pool - self._n_dagged_pending, 0).astype(np.int64)
        cleavage_available = np.clip(self._n_dagged_pending, a_min=0, a_max=None).astype(np.int64)

        for ridx in range(n_rxn):
            progressed = self._apply_reaction_allocation(
                ridx=ridx,
                n_events=min(
                    self._substrate_limit_for_reaction(substrate_pool, ridx),
                    int(enzyme_remaining[ridx]),
                    int(
                        dag_available[ridx // 2] if ridx % 2 == 0 else cleavage_available[ridx // 2]
                    ),
                ),
                reaction_fluxes=reaction_fluxes,
                substrate_pool=substrate_pool,
                enzyme_remaining=enzyme_remaining,
                dag_available=dag_available,
                cleavage_available=cleavage_available,
            )
            if not progressed:
                continue

        max_iters = int(self.parameters["max_stochastic_iterations"])
        for _ in range(max_iters):
            progressed = self._stochastic_residual_step(
                reaction_fluxes=reaction_fluxes,
                substrate_pool=substrate_pool,
                enzyme_remaining=enzyme_remaining,
                dag_available=dag_available,
                cleavage_available=cleavage_available,
            )
            if not progressed:
                break

        return reaction_fluxes

    def _apply_reaction_allocation(
        self,
        ridx: int,
        n_events: int,
        reaction_fluxes: np.ndarray,
        substrate_pool: np.ndarray,
        enzyme_remaining: np.ndarray,
        dag_available: np.ndarray,
        cleavage_available: np.ndarray,
    ) -> bool:
        if n_events <= 0:
            return False
        protein_idx = ridx // 2
        reaction_fluxes[ridx] += int(n_events)
        substrate_pool += self.reaction_stoich[:, ridx] * int(n_events)
        enzyme_remaining[ridx] -= int(n_events)
        if ridx % 2 == 0:
            dag_available[protein_idx] -= int(n_events)
            cleavage_available[protein_idx] += int(n_events)
        else:
            cleavage_available[protein_idx] -= int(n_events)
        return True

    def _substrate_limit_for_reaction(self, substrates: np.ndarray, ridx: int) -> int:
        stoich_col = self.reaction_stoich[:, ridx]
        consumed_idx = np.flatnonzero(stoich_col < 0)
        if consumed_idx.size == 0:
            return np.iinfo(np.int64).max
        req = -stoich_col[consumed_idx]
        avail = substrates[consumed_idx]
        return max(0, int(np.min(avail // req)))

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
        dag_available: np.ndarray,
        cleavage_available: np.ndarray,
    ) -> bool:
        n_rxn = self.reaction_stoich.shape[1]
        residual_limit = np.zeros(n_rxn, dtype=np.int64)
        for ridx in range(n_rxn):
            target_limit = int(
                dag_available[ridx // 2] if ridx % 2 == 0 else cleavage_available[ridx // 2]
            )
            residual_limit[ridx] = min(
                self._substrate_limit_for_reaction(substrate_pool, ridx),
                int(enzyme_remaining[ridx]),
                target_limit,
            )

        feasible = np.flatnonzero(residual_limit > 0)
        if feasible.size == 0:
            return False
        weights = residual_limit[feasible].astype(np.float64)
        weight_sum = float(np.sum(weights))
        if weight_sum <= 0.0:
            return False

        chosen = int(self._rng.choice(feasible, p=(weights / weight_sum)))
        return self._apply_reaction_allocation(
            ridx=chosen,
            n_events=1,
            reaction_fluxes=reaction_fluxes,
            substrate_pool=substrate_pool,
            enzyme_remaining=enzyme_remaining,
            dag_available=dag_available,
            cleavage_available=cleavage_available,
        )


__all__ = ["KarrProteinProcessingIIProcess"]
