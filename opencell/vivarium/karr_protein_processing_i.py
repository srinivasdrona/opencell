"""Vivarium Process port of Karr's ProteinProcessingI flow."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.vivarium.karr_trna_aminoacylation import _parse_wid_array, _resolve_fixture_path

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinProcessingI_flat.mat"
_D2_COMPLEX_FIXTURE_PATH = "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"
_RIBOSOME_ASSEMBLY_FIXTURE_PATH = "data/karr_fixtures/per_process/RibosomeAssembly_flat.mat"


@lru_cache(maxsize=1)
def _canonical_complex_wids() -> frozenset[str]:
    """Load canonical complex WIDs for process-side store classification."""
    complex_wids: set[str] = set()
    for fixture_path in (_D2_COMPLEX_FIXTURE_PATH, _RIBOSOME_ASSEMBLY_FIXTURE_PATH):
        resolved = _resolve_fixture_path(fixture_path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]
        complex_wids.update(_parse_wid_array(fx["complexWholeCellModelIDs"]))
    complex_wids.update({"RNA_POLYMERASE", "RIBOSOME_70S"})
    return frozenset(complex_wids)


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
        canonical_complex_wids = _canonical_complex_wids()
        self.complex_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid in canonical_complex_wids
        ]
        self.protein_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid not in canonical_complex_wids
        ]
        self._enzyme_source_by_wid = {
            wid: ("complex" if wid in canonical_complex_wids else "protein")
            for wid in self.enzyme_wids
        }

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
        self._fixture_enzyme_counts = np.asarray(fx["enzymes"][0, 0], dtype=np.float64).reshape(-1)
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
        protein_enzyme_schema = {
            wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
            for wid in self.protein_enzyme_wids
        }
        complex_enzyme_schema = {
            wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
            for wid in self.complex_enzyme_wids
        }

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
            "unprocessedMonomers": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.unprocessed_monomer_wids
            },
            "processedMonomers": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.processed_monomer_wids
            },
            "protein": {
                "unprocessed_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.unprocessed_monomer_wids
                },
                "processed_counts": processed_schema,
                "counts": protein_enzyme_schema,
                "enzyme_counts": protein_enzyme_schema,
            },
            "complex": {
                "counts": complex_enzyme_schema,
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

        protein_state = states.get("protein", {})
        unprocessed_state = protein_state.get("unprocessed_counts", {})
        if not isinstance(unprocessed_state, dict):
            unprocessed_state = {}
        protein_counts = protein_state.get("counts", {})
        if not isinstance(protein_counts, dict):
            protein_counts = {}

        unprocessed = np.asarray(
            [float(unprocessed_state.get(wid, 0.0)) for wid in self.unprocessed_monomer_wids],
            dtype=np.float64,
        )
        use_protein_counts_compat = False
        if unprocessed.sum() <= 0.0 and protein_counts:
            counts_unprocessed = np.asarray(
                [float(protein_counts.get(wid, 0.0)) for wid in self.unprocessed_monomer_wids],
                dtype=np.float64,
            )
            if counts_unprocessed.sum() > 0.0:
                unprocessed = counts_unprocessed
                use_protein_counts_compat = True
        if unprocessed.sum() <= 0.0:
            return {}

        substrates = self._read_allocated_or_baseline_substrates(states)
        enzymes = self._read_enzyme_counts(states, prefer_protein_counts=use_protein_counts_compat)

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
        substrate_delta[self.substrate_idx_hydrogen] += total_processed
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
            if use_protein_counts_compat:
                compat_counts_updates = {
                    **unprocessed_updates,
                    **processed_updates,
                }
                update["protein"]["counts"] = compat_counts_updates

        return update

    def _read_enzyme_counts(
        self,
        states: dict[str, Any],
        *,
        prefer_protein_counts: bool = False,
    ) -> np.ndarray:
        protein_state = states.get("protein", {})
        enzyme_state = protein_state.get("enzyme_counts")
        if not isinstance(enzyme_state, dict):
            # Backward-compatibility fallback for transitional state payloads.
            enzyme_state = protein_state.get("counts", {})
        if not isinstance(enzyme_state, dict):
            raise KeyError("karr_protein_processing_i requires protein.enzyme_counts (or protein.counts)")

        complex_state = states.get("complex", {}).get("counts", {})
        if not isinstance(complex_state, dict):
            raise KeyError("karr_protein_processing_i requires complex.counts")

        missing_protein_wids = [wid for wid in self.protein_enzyme_wids if wid not in enzyme_state]
        if missing_protein_wids:
            raise KeyError(
                "karr_protein_processing_i missing protein enzyme counts for: "
                + ", ".join(missing_protein_wids)
            )

        missing_complex_wids = [wid for wid in self.complex_enzyme_wids if wid not in complex_state]
        if missing_complex_wids:
            raise KeyError(
                "karr_protein_processing_i missing complex enzyme counts for: "
                + ", ".join(missing_complex_wids)
            )

        protein_counts_state = protein_state.get("counts", {})
        if not isinstance(protein_counts_state, dict):
            protein_counts_state = {}
        protein_enzyme_state_has_signal = any(
            float(enzyme_state.get(wid, 0.0)) > 0.0 for wid in self.protein_enzyme_wids
        )

        out = np.zeros(len(self.enzyme_wids), dtype=np.float64)
        for i, wid in enumerate(self.enzyme_wids):
            if self._enzyme_source_by_wid[wid] == "complex":
                out[i] = float(complex_state[wid])
                continue

            val = float(enzyme_state.get(wid, 0.0))
            if not protein_enzyme_state_has_signal:
                val = float(protein_counts_state.get(wid, val))
            if prefer_protein_counts:
                val = float(protein_counts_state.get(wid, val))
                if val <= 0.0 and i < self._fixture_enzyme_counts.size:
                    # L2 replay compatibility: processed/unprocessed overlays share
                    # WIDs and can overwrite monomer enzyme counts in protein.counts.
                    val = float(self._fixture_enzyme_counts[i])
            out[i] = val
        return out

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
