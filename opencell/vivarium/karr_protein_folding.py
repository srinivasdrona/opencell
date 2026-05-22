"""Vivarium Process port of Karr's ProteinFolding flow.

Two-phase implementation for monomer folding:
1. Ion/prosthetic-group binding.
2. Trigger/chaperone-mediated folding with stochastic allocation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinFolding_flat.mat"
_MAX_STOCHASTIC_ITERATIONS = 200_000
_DEFAULT_ATP_PER_CHAPERONE_CYCLE = 4


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


def _parse_zero_based_index(value: np.ndarray) -> int:
    scalar: object = np.asarray(value, dtype=object).ravel()[0]
    while isinstance(scalar, np.ndarray):
        if scalar.size == 0:
            raise ValueError("Cannot parse zero-based index from empty MATLAB array")
        scalar = scalar.flat[0]
    return int(scalar) - 1


class KarrProteinFoldingProcess(Process):
    """Karr Process_ProteinFolding (ion binding + chaperone folding)."""

    name = "karr_protein_folding"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "max_stochastic_iterations": _MAX_STOCHASTIC_ITERATIONS,
        "atp_per_chaperone_cycle": _DEFAULT_ATP_PER_CHAPERONE_CYCLE,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        atp_per_cycle = int(self.parameters["atp_per_chaperone_cycle"])
        if atp_per_cycle <= 0:
            raise ValueError("atp_per_chaperone_cycle must be > 0")
        self._atp_per_chaperone_cycle = atp_per_cycle

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        self.substrate_wids = _parse_wid_array(fx["substrateWholeCellModelIDs"])
        self.enzyme_wids = _parse_wid_array(fx["enzymeWholeCellModelIDs"])
        self.unfolded_monomer_wids = _parse_wid_array(fx["unfoldedMonomerWholeCellModelIDs"])
        self.folded_monomer_wids = _parse_wid_array(fx["foldedMonomerWholeCellModelIDs"])

        n_monomers = len(self.unfolded_monomer_wids)
        self.protein_prosthetic_matrix = np.asarray(
            fx["proteinProstheticGroupMatrix"][0, 0], dtype=np.int64
        )[:n_monomers, : len(self.substrate_wids)]
        self.protein_chaperone_matrix = np.asarray(
            fx["proteinChaperoneMatrix"][0, 0], dtype=np.int64
        )[:n_monomers, : len(self.enzyme_wids)]

        self.substrate_idx_atp = _parse_zero_based_index(fx["substrateIndexs_atp"])
        self.substrate_idx_fe2 = _parse_zero_based_index(fx["substrateIndexs_fe2"])
        self.substrate_idx_mg = _parse_zero_based_index(fx["substrateIndexs_mg"])
        self.substrate_idx_zinc = _parse_zero_based_index(fx["substrateIndexs_zinc"])

        self.enzyme_idx_trigger_factor = _parse_zero_based_index(
            fx["enzymeIndexs_triggerFactor"]
        )
        self.enzyme_idx_dnaK = _parse_zero_based_index(fx["enzymeIndexs_dnaK"])
        self.enzyme_idx_dnaJ = _parse_zero_based_index(fx["enzymeIndexs_dnaJ"])
        self.enzyme_idx_grpE = _parse_zero_based_index(fx["enzymeIndexs_grpE"])
        self.enzyme_idx_groELES = _parse_zero_based_index(fx["enzymeIndexs_groELES"])

        # Trigger factor is globally required in this Karr process.
        self.protein_chaperone_matrix[:, self.enzyme_idx_trigger_factor] = 1

        self.ion_required_mask = np.sum(self.protein_prosthetic_matrix, axis=1) > 0
        self.chaperone_dependent_mask = (
            np.sum(self.protein_chaperone_matrix, axis=1)
            - self.protein_chaperone_matrix[:, self.enzyme_idx_trigger_factor]
        ) > 0

        self._all_chaperone_indices = np.arange(len(self.enzyme_wids), dtype=np.int64)
        self._required_enzyme_indices: list[np.ndarray] = []
        for chaperone_dependent in self.chaperone_dependent_mask:
            if chaperone_dependent:
                self._required_enzyme_indices.append(self._all_chaperone_indices)
            else:
                self._required_enzyme_indices.append(
                    np.asarray([self.enzyme_idx_trigger_factor], dtype=np.int64)
                )

    def ports_schema(self) -> dict[str, Any]:
        count_wids = list(dict.fromkeys([*self.folded_monomer_wids, *self.enzyme_wids]))
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in count_wids
                },
                "unfolded_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.unfolded_monomer_wids
                },
            },
            "substrates_allocated": {
                self.name: {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.substrate_wids
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        substrate_state = states.get("substrates", {})
        substrate_counts = np.asarray(
            [
                self._allocated_or_free(wid, allocated_state=allocated_state, fallback_state=substrate_state)
                for wid in self.substrate_wids
            ],
            dtype=np.float64,
        )
        substrate_pool = np.floor(np.clip(substrate_counts, a_min=0.0, a_max=None)).astype(np.int64)

        unfolded_pool = np.asarray(
            [float(states["protein"]["unfolded_counts"].get(wid, 0.0)) for wid in self.unfolded_monomer_wids],
            dtype=np.float64,
        )
        unfolded_pool = np.floor(np.clip(unfolded_pool, a_min=0.0, a_max=None)).astype(np.int64)

        if unfolded_pool.sum() <= 0:
            return {}

        enzyme_pool = np.asarray(
            [float(states["protein"]["counts"].get(wid, 0.0)) for wid in self.enzyme_wids],
            dtype=np.float64,
        )
        enzyme_pool = np.floor(np.clip(enzyme_pool, a_min=0.0, a_max=None)).astype(np.int64)

        ion_ready, ion_consumed = self._phase1_ion_binding(
            unfolded_pool=unfolded_pool,
            substrate_pool=substrate_pool,
        )

        fold_events, atp_consumed = self._phase2_chaperone_folding(
            ion_ready=ion_ready,
            enzyme_pool=enzyme_pool,
            atp_available=int(substrate_pool[self.substrate_idx_atp]),
        )

        substrate_delta = -ion_consumed
        substrate_delta[self.substrate_idx_atp] -= int(atp_consumed)
        unfolded_delta = -fold_events
        folded_delta = fold_events

        update: dict[str, Any] = {}
        substrate_update = {
            wid: float(substrate_delta[idx])
            for idx, wid in enumerate(self.substrate_wids)
            if substrate_delta[idx] != 0
        }
        if substrate_update:
            update["substrates"] = substrate_update

        unfolded_update = {
            wid: float(unfolded_delta[idx])
            for idx, wid in enumerate(self.unfolded_monomer_wids)
            if unfolded_delta[idx] != 0
        }
        folded_update = {
            wid: float(folded_delta[idx])
            for idx, wid in enumerate(self.folded_monomer_wids)
            if folded_delta[idx] != 0
        }
        if unfolded_update or folded_update:
            update["protein"] = {
                "unfolded_counts": unfolded_update,
                "counts": folded_update,
            }

        return update

    @staticmethod
    def _allocated_or_free(
        wid: str,
        allocated_state: dict[str, Any],
        fallback_state: dict[str, Any],
    ) -> float:
        allocated_value = float(allocated_state.get(wid, 0.0))
        if allocated_value > 0.0:
            return allocated_value
        return float(fallback_state.get(wid, 0.0))

    def _phase1_ion_binding(
        self,
        unfolded_pool: np.ndarray,
        substrate_pool: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        ion_ready = np.zeros_like(unfolded_pool, dtype=np.int64)
        ion_consumed = np.zeros_like(substrate_pool, dtype=np.int64)

        for pidx in np.flatnonzero(unfolded_pool > 0):
            available = int(unfolded_pool[pidx])
            required = self.protein_prosthetic_matrix[pidx]
            req_idx = np.flatnonzero(required > 0)

            if req_idx.size == 0:
                ion_ready[pidx] = available
                continue

            max_bind = available
            for sidx in req_idx:
                req = int(required[sidx])
                max_bind = min(max_bind, int(substrate_pool[sidx] // req))
                if max_bind <= 0:
                    break

            if max_bind <= 0:
                continue

            ion_ready[pidx] = int(max_bind)
            for sidx in req_idx:
                need = int(required[sidx]) * int(max_bind)
                substrate_pool[sidx] -= need
                ion_consumed[sidx] += need

        return ion_ready, ion_consumed

    def _phase2_chaperone_folding(
        self,
        ion_ready: np.ndarray,
        enzyme_pool: np.ndarray,
        atp_available: int,
    ) -> tuple[np.ndarray, int]:
        fold_events = np.zeros_like(ion_ready, dtype=np.int64)
        pending = np.asarray(ion_ready, dtype=np.int64).copy()
        capacities = np.asarray(enzyme_pool, dtype=np.int64).copy()
        atp_remaining = max(0, int(atp_available))

        max_iters = int(self.parameters["max_stochastic_iterations"])
        if max_iters <= 0:
            return fold_events, 0

        for _ in range(max_iters):
            candidates = np.flatnonzero(pending > 0)
            if candidates.size == 0:
                break

            feasible: list[int] = []
            weights: list[float] = []
            for pidx in candidates:
                required_chaperones = self._required_enzyme_indices[int(pidx)]
                if np.any(capacities[required_chaperones] <= 0):
                    continue
                if (
                    self.chaperone_dependent_mask[int(pidx)]
                    and atp_remaining < self._atp_per_chaperone_cycle
                ):
                    continue

                feasible.append(int(pidx))
                weights.append(float(pending[int(pidx)]))

            if not feasible:
                break

            probs = np.asarray(weights, dtype=np.float64)
            probs /= float(np.sum(probs))
            chosen = int(self._rng.choice(np.asarray(feasible, dtype=np.int64), p=probs))

            fold_events[chosen] += 1
            pending[chosen] -= 1

            required_chaperones = self._required_enzyme_indices[chosen]
            capacities[required_chaperones] -= 1
            if self.chaperone_dependent_mask[chosen]:
                atp_remaining -= self._atp_per_chaperone_cycle

        return fold_events, int(max(0, atp_available - atp_remaining))


__all__ = ["KarrProteinFoldingProcess"]
