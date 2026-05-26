"""Vivarium Process port of Karr's ProteinProcessingI flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.vivarium.karr_trna_aminoacylation import _parse_wid_array, _resolve_fixture_path

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinProcessingI_flat.mat"


class KarrProteinProcessingIProcess(Process):
    """Karr Process_ProteinProcessingI (deformylation + N-Met cleavage)."""

    name = "karr_protein_processing_i"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        if len(self.unprocessed_monomer_wids) != len(self.processed_monomer_wids):
            raise ValueError("unprocessed and processed monomer WID lengths must match")
        if len(self.met_cleavage_mask) != len(self.unprocessed_monomer_wids):
            raise ValueError("methionine cleavage mask must match monomer length")
        if self.enzyme_idx_deformylase >= len(self.enzyme_wids):
            raise ValueError("deformylase index out of bounds for enzyme list")
        if self.enzyme_idx_methionine_aminopeptidase >= len(self.enzyme_wids):
            raise ValueError("methionine aminopeptidase index out of bounds for enzyme list")

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        self.substrate_wids = _parse_wid_array(fx["substrateWholeCellModelIDs"])
        self.enzyme_wids = _parse_wid_array(fx["enzymeWholeCellModelIDs"])
        self.unprocessed_monomer_wids = _parse_wid_array(fx["unprocessedMonomerWholeCellModelIDs"])
        self.processed_monomer_wids = _parse_wid_array(fx["processedMonomerWholeCellModelIDs"])

        self.met_cleavage_mask = (
            np.asarray(
                fx["nascentMonomerNTerminalMethionineCleavages"][0, 0], dtype=np.uint8
            ).reshape(-1)
            > 0
        )

        self.deformylase_specific_rate = float(
            np.asarray(fx["deformylaseSpecificRate"][0, 0], dtype=np.float64).reshape(-1)[0]
        )
        self.methionine_aminopeptidase_specific_rate = float(
            np.asarray(fx["methionineAminoPeptidaseSpecificRate"][0, 0], dtype=np.float64).reshape(
                -1
            )[0]
        )

        self.substrate_idx_water = (
            int(np.asarray(fx["substrateIndexs_water"][0, 0], dtype=np.int64).reshape(-1)[0]) - 1
        )
        self.substrate_idx_hydrogen = (
            int(np.asarray(fx["substrateIndexs_hydrogen"][0, 0], dtype=np.int64).reshape(-1)[0]) - 1
        )
        self.substrate_idx_methionine = (
            int(np.asarray(fx["substrateIndexs_methionine"][0, 0], dtype=np.int64).reshape(-1)[0])
            - 1
        )
        self.substrate_idx_formate = (
            int(np.asarray(fx["substrateIndexs_formate"][0, 0], dtype=np.int64).reshape(-1)[0]) - 1
        )

        self.enzyme_idx_deformylase = (
            int(np.asarray(fx["enzymeIndexs_deformylase"][0, 0], dtype=np.int64).reshape(-1)[0]) - 1
        )
        self.enzyme_idx_methionine_aminopeptidase = (
            int(
                np.asarray(
                    fx["enzymeIndexs_methionineAminoPeptidase"][0, 0], dtype=np.int64
                ).reshape(-1)[0]
            )
            - 1
        )

    def ports_schema(self) -> dict[str, Any]:
        processed_schema = {
            wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
            for wid in self.processed_monomer_wids
        }

        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
            },
            "protein": {
                "unprocessed_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.unprocessed_monomer_wids
                },
                "processed_counts": processed_schema,
                "counts": {
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
        dt = float(self.parameters["time_step"])

        unprocessed = np.asarray(
            [
                float(states["protein"].get("unprocessed_counts", {}).get(wid, 0.0))
                for wid in self.unprocessed_monomer_wids
            ],
            dtype=np.float64,
        )
        if unprocessed.sum() <= 0.0:
            return {}

        substrates = self._read_allocated_or_baseline_substrates(states)
        enzymes = np.asarray(
            [float(states["protein"]["counts"].get(wid, 0.0)) for wid in self.enzyme_wids],
            dtype=np.float64,
        )

        unprocessed_pool = np.floor(np.clip(unprocessed, a_min=0.0, a_max=None)).astype(np.int64)
        substrate_pool = np.floor(np.clip(substrates, a_min=0.0, a_max=None)).astype(np.int64)
        if not np.any(unprocessed_pool > 0) or substrate_pool[self.substrate_idx_water] <= 0:
            return {}

        deformylase_limit = int(
            np.floor(
                max(0.0, enzymes[self.enzyme_idx_deformylase]) * self.deformylase_specific_rate * dt
            )
        )
        methionine_aminopeptidase_limit = int(
            np.floor(
                max(0.0, enzymes[self.enzyme_idx_methionine_aminopeptidase])
                * self.methionine_aminopeptidase_specific_rate
                * dt
            )
        )
        water_remaining = int(substrate_pool[self.substrate_idx_water])

        cleavage_limit = int(
            min(
                int(np.sum(unprocessed_pool[self.met_cleavage_mask])),
                deformylase_limit,
                methionine_aminopeptidase_limit,
                water_remaining // 2,
            )
        )
        cleavage_events = self._sample_weighted_events(
            pool_counts=unprocessed_pool,
            eligible_mask=self.met_cleavage_mask,
            n_events=cleavage_limit,
        )
        cleavage_count = int(np.sum(cleavage_events))

        if cleavage_count > 0:
            unprocessed_pool -= cleavage_events
            deformylase_limit -= cleavage_count
            water_remaining -= 2 * cleavage_count

        non_cleavage_mask = ~self.met_cleavage_mask
        deformyl_only_limit = int(
            min(
                int(np.sum(unprocessed_pool[non_cleavage_mask])),
                deformylase_limit,
                water_remaining,
            )
        )
        deformyl_only_events = self._sample_weighted_events(
            pool_counts=unprocessed_pool,
            eligible_mask=non_cleavage_mask,
            n_events=deformyl_only_limit,
        )
        deformyl_only_count = int(np.sum(deformyl_only_events))

        total_processed = cleavage_count + deformyl_only_count
        if total_processed <= 0:
            return {}

        processed_events = cleavage_events + deformyl_only_events

        substrate_delta = np.zeros(len(self.substrate_wids), dtype=np.int64)
        substrate_delta[self.substrate_idx_water] -= total_processed + cleavage_count
        substrate_delta[self.substrate_idx_formate] += total_processed
        substrate_delta[self.substrate_idx_methionine] += cleavage_count

        update: dict[str, Any] = {}
        substrate_updates = {
            wid: float(substrate_delta[i])
            for i, wid in enumerate(self.substrate_wids)
            if substrate_delta[i] != 0
        }
        if substrate_updates:
            update["substrates"] = substrate_updates

        unprocessed_updates = {
            wid: -float(processed_events[i])
            for i, wid in enumerate(self.unprocessed_monomer_wids)
            if processed_events[i] > 0
        }
        processed_updates = {
            wid: float(processed_events[i])
            for i, wid in enumerate(self.processed_monomer_wids)
            if processed_events[i] > 0
        }
        if unprocessed_updates or processed_updates:
            update["protein"] = {
                "unprocessed_counts": unprocessed_updates,
                "processed_counts": processed_updates,
            }

        return update

    def _read_allocated_or_baseline_substrates(self, states: dict[str, Any]) -> np.ndarray:
        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        # Strict-zero allocator contract: do not fallback to global substrate pools.
        return np.asarray(
            [
                max(0.0, float(allocated_state.get(wid, 0.0)))
                for wid in self.substrate_wids
            ],
            dtype=np.float64,
        )

    def _sample_weighted_events(
        self,
        pool_counts: np.ndarray,
        eligible_mask: np.ndarray,
        n_events: int,
    ) -> np.ndarray:
        events = np.zeros_like(pool_counts, dtype=np.int64)
        if n_events <= 0:
            return events

        eligible_idx = np.flatnonzero((pool_counts > 0) & eligible_mask)
        if eligible_idx.size == 0:
            return events

        eligible_counts = pool_counts[eligible_idx].astype(np.int64)
        draws = int(min(n_events, int(np.sum(eligible_counts))))
        if draws <= 0:
            return events

        if hasattr(self._rng, "multivariate_hypergeometric"):
            sampled = self._rng.multivariate_hypergeometric(eligible_counts, draws).astype(np.int64)
            events[eligible_idx] = sampled
            return events

        sampled = np.zeros_like(eligible_counts, dtype=np.int64)
        remaining = eligible_counts.copy()
        for _ in range(draws):
            total = int(np.sum(remaining))
            if total <= 0:
                break
            probs = remaining.astype(np.float64) / float(total)
            choice = int(self._rng.choice(remaining.size, p=probs))
            sampled[choice] += 1
            remaining[choice] -= 1

        events[eligible_idx] = sampled
        return events


__all__ = ["KarrProteinProcessingIProcess"]
