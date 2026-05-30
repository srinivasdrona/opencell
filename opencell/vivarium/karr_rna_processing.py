"""karr_rna_processing — Karr 2012 RNA processing replay implementation."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.vivarium.karr_trna_aminoacylation import _parse_wid_array, _resolve_fixture_path

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/RNAProcessing_flat.mat"
_RNA_STATE_FIXTURE_PATH = "data/karr_fixtures/per_process/Rna_flat.mat"
_D2_COMPLEXATION_FIXTURE_PATH = "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"
_RIBOSOME_ASSEMBLY_FIXTURE_PATH = "data/karr_fixtures/per_process/RibosomeAssembly_flat.mat"
_FIXED_COMPLEX_WIDS = frozenset({"RNA_POLYMERASE", "RIBOSOME_70S"})
_RNA_TYPE_KEYS = (
    "unprocessedRNAIndexs_mRNA",
    "unprocessedRNAIndexs_rRNA",
    "unprocessedRNAIndexs_sRNA",
    "unprocessedRNAIndexs_tRNA",
)


@lru_cache(maxsize=1)
def _canonical_complex_wids() -> frozenset[str]:
    complex_wids: set[str] = set()
    for fixture_path in (_D2_COMPLEXATION_FIXTURE_PATH, _RIBOSOME_ASSEMBLY_FIXTURE_PATH):
        resolved = _resolve_fixture_path(fixture_path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]
        complex_wids.update(_parse_wid_array(fx["complexWholeCellModelIDs"]))
    complex_wids.update(_FIXED_COMPLEX_WIDS)
    return frozenset(complex_wids)


class KarrRNAProcessingProcess(Process):
    """Karr Process_RNAProcessing (evolveState/evolveState_Helper parity)."""

    name = "karr_rna_processing"
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
        self.monomer_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid not in canonical_complex_wids
        ]
        self._complex_enzyme_wid_set = set(self.complex_enzyme_wids)

        self.rna_wids = list(dict.fromkeys(self.unprocessed_rna_wids + self.processed_rna_wids))

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        self.substrate_wids = _parse_wid_array(fx["substrateWholeCellModelIDs"])
        self.unprocessed_rna_wids = _parse_wid_array(fx["unprocessedRNAWholeCellModelIDs"])
        raw_processed_rna_wids = _parse_wid_array(fx["processedRNAWholeCellModelIDs"])
        unprocessed_wid_set = set(self.unprocessed_rna_wids)
        # Replay harness projects processed/unprocessed vectors through a shared
        # `rna.counts` store. Disambiguate overlapping processed IDs so mature
        # and nascent pools do not cancel each other in-place.
        self.processed_rna_wids = [
            f"processed::{wid}" if wid in unprocessed_wid_set else wid
            for wid in raw_processed_rna_wids
        ]
        self.enzyme_wids = _parse_wid_array(fx["enzymeWholeCellModelIDs"])

        self.reaction_stoich = self._read_reaction_stoich(fx)
        self.reaction_catalysis = self._read_reaction_catalysis(fx)
        self.processed_output_matrix = self._load_processed_output_matrix()

        if self.reaction_stoich.shape != (len(self.substrate_wids), len(self.unprocessed_rna_wids)):
            raise ValueError(
                "Unexpected reaction stoichiometry shape: "
                f"{self.reaction_stoich.shape}, expected "
                f"({len(self.substrate_wids)}, {len(self.unprocessed_rna_wids)})"
            )
        if self.reaction_catalysis.shape != (len(self.unprocessed_rna_wids), len(self.enzyme_wids)):
            raise ValueError(
                "Unexpected reaction catalysis shape: "
                f"{self.reaction_catalysis.shape}, expected "
                f"({len(self.unprocessed_rna_wids)}, {len(self.enzyme_wids)})"
            )

        self._rna_type_reaction_indices = [
            np.asarray(
                self._read_1_based_indices(
                    fx,
                    key,
                    expected_size=len(self.unprocessed_rna_wids),
                ),
                dtype=np.int64,
            )
            for key in _RNA_TYPE_KEYS
        ]
        if not any(indices.size > 0 for indices in self._rna_type_reaction_indices):
            raise ValueError("RNAProcessing fixture is missing all unprocessedRNA class indices")

    def _read_reaction_stoich(self, fx: np.ndarray) -> np.ndarray:
        if "reactionStoichiometryMatrix" in fx.dtype.names:
            raw = np.asarray(fx["reactionStoichiometryMatrix"][0, 0], dtype=np.float64)
        elif "reactantByproductMatrix" in fx.dtype.names:
            raw = np.asarray(fx["reactantByproductMatrix"][0, 0], dtype=np.float64)
        else:
            raise KeyError("Fixture missing reaction stoichiometry field")
        return np.asarray(np.rint(raw), dtype=np.int64)

    def _read_reaction_catalysis(self, fx: np.ndarray) -> np.ndarray:
        if "reactionCatalysisMatrix" in fx.dtype.names:
            raw = np.asarray(fx["reactionCatalysisMatrix"][0, 0], dtype=np.float64)
        elif "catalysisMatrix" in fx.dtype.names:
            raw = np.asarray(fx["catalysisMatrix"][0, 0], dtype=np.float64)
        else:
            raise KeyError("Fixture missing reaction catalysis field")

        if raw.shape == (len(self.enzyme_wids), len(self.unprocessed_rna_wids)):
            raw = raw.T
        return np.clip(raw, a_min=0.0, a_max=None)

    def _load_processed_output_matrix(self) -> np.ndarray:
        resolved = _resolve_fixture_path(_RNA_STATE_FIXTURE_PATH)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]
        if "nascentRNAMatureRNAComposition" not in fx.dtype.names:
            raise KeyError("Rna fixture missing nascentRNAMatureRNAComposition")

        matrix = np.asarray(fx["nascentRNAMatureRNAComposition"][0, 0], dtype=np.int64)
        expected_shape = (len(self.processed_rna_wids), len(self.unprocessed_rna_wids))
        if matrix.shape != expected_shape:
            raise ValueError(
                "Unexpected nascentRNAMatureRNAComposition shape: "
                f"{matrix.shape}, expected {expected_shape}"
            )
        return matrix

    def _read_1_based_indices(
        self,
        fx: np.ndarray,
        key: str,
        *,
        expected_size: int,
    ) -> list[int]:
        if key not in fx.dtype.names:
            return []
        raw = fx[key]
        value = raw[0, 0] if isinstance(raw, np.ndarray) and raw.shape == (1, 1) else raw
        arr = np.asarray(value).reshape(-1)
        out: list[int] = []
        for v in arr:
            try:
                out.append(int(v) - 1)
            except (TypeError, ValueError):
                continue
        return [i for i in out if 0 <= i < expected_size]

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
            "unprocessedRNAs": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.unprocessed_rna_wids
            },
            "processedRNAs": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.processed_rna_wids
            },
            "rna": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.rna_wids
                }
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

        rna_counts = states.get("rna", {}).get("counts", {})
        if not isinstance(rna_counts, dict):
            rna_counts = {}
        unprocessed = np.asarray(
            [float(rna_counts.get(wid, 0.0)) for wid in self.unprocessed_rna_wids], dtype=np.float64
        )
        if unprocessed.sum() <= 0.0:
            return {}

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        substrates = np.asarray(
            [max(0.0, float(allocated_state.get(wid, 0.0))) for wid in self.substrate_wids],
            dtype=np.float64,
        )

        enzyme_state = states.get("enzymes", {})
        if isinstance(enzyme_state, dict) and enzyme_state:
            enzymes = np.asarray(
                [float(enzyme_state.get(wid, 0.0)) for wid in self.enzyme_wids], dtype=np.float64
            )
        else:
            protein_state = states.get("protein", {})
            if not isinstance(protein_state, dict):
                protein_state = {}
            complex_state = states.get("complex", {})
            if not isinstance(complex_state, dict):
                complex_state = {}
            enzymes = self._enzyme_counts_from_stores(
                protein_count_store=protein_state.get("counts", {}),
                complex_count_store=complex_state.get("counts", {}),
            )

        processing_events = self._compute_processing_events(
            unprocessed=unprocessed,
            substrates=substrates,
            enzymes=enzymes,
            dt=float(self.parameters["time_step"]),
        )
        if not np.any(processing_events > 0):
            return {}

        substrate_delta = self.reaction_stoich @ processing_events
        unprocessed_delta = -processing_events
        processed_delta = self.processed_output_matrix @ processing_events

        rna_updates: dict[str, float] = {}
        for ridx, wid in enumerate(self.unprocessed_rna_wids):
            delta = int(unprocessed_delta[ridx])
            if delta != 0:
                rna_updates[wid] = float(rna_updates.get(wid, 0.0) + delta)
        for pidx, wid in enumerate(self.processed_rna_wids):
            delta = int(processed_delta[pidx])
            if delta != 0:
                rna_updates[wid] = float(rna_updates.get(wid, 0.0) + delta)

        update: dict[str, Any] = {}
        sub_updates = {
            wid: float(substrate_delta[sidx])
            for sidx, wid in enumerate(self.substrate_wids)
            if substrate_delta[sidx] != 0
        }
        if sub_updates:
            update["substrates"] = sub_updates
        if rna_updates:
            update["rna"] = {"counts": rna_updates}
        return update

    def _enzyme_counts_from_stores(
        self,
        protein_count_store: Any,
        complex_count_store: Any,
    ) -> np.ndarray:
        if not isinstance(protein_count_store, dict):
            protein_count_store = {}
        if not isinstance(complex_count_store, dict):
            complex_count_store = {}

        missing: list[str] = []
        enzymes = np.zeros(len(self.enzyme_wids), dtype=np.float64)
        for eidx, wid in enumerate(self.enzyme_wids):
            if wid in self._complex_enzyme_wid_set:
                if wid not in complex_count_store:
                    missing.append(f"complex.counts[{wid}]")
                enzymes[eidx] = float(complex_count_store.get(wid, 0.0))
            else:
                if wid not in protein_count_store:
                    missing.append(f"protein.counts[{wid}]")
                enzymes[eidx] = float(protein_count_store.get(wid, 0.0))

        if missing:
            joined = ", ".join(sorted(missing))
            raise KeyError(
                "KarrRNAProcessingProcess missing declared enzyme inputs in state stores: "
                f"{joined}"
            )
        return enzymes

    def _compute_processing_events(
        self,
        *,
        unprocessed: np.ndarray,
        substrates: np.ndarray,
        enzymes: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        # Mirrors RNAProcessing.m evolveState/evolveState_Helper:
        # iterate RNA classes in random order, upper-bound events, then
        # sample counts without replacement weighted by unprocessed counts.
        substrate_pool = np.floor(np.clip(substrates, a_min=0.0, a_max=None)).astype(np.int64)
        unprocessed_pool = np.floor(np.clip(unprocessed, a_min=0.0, a_max=None)).astype(np.int64)
        enzyme_pool = np.clip(np.asarray(enzymes, dtype=np.float64), a_min=0.0, a_max=None)
        processing_events = np.zeros(len(self.unprocessed_rna_wids), dtype=np.int64)

        order = self._rng.permutation(len(self._rna_type_reaction_indices))
        for order_idx in order:
            reaction_indices = self._rna_type_reaction_indices[int(order_idx)]
            if reaction_indices.size == 0:
                continue

            total_rnas = int(np.sum(unprocessed_pool[reaction_indices]))
            if total_rnas <= 0:
                continue

            max_substrate_demand = np.maximum(
                0,
                -np.min(self.reaction_stoich[:, reaction_indices], axis=1),
            ).astype(np.float64)
            substrate_limits = np.divide(
                substrate_pool.astype(np.float64),
                max_substrate_demand,
                out=np.full(max_substrate_demand.shape, np.inf, dtype=np.float64),
                where=max_substrate_demand > 0,
            )

            representative_idx = int(reaction_indices[0])
            enzyme_requirements = self.reaction_catalysis[representative_idx, :]
            enzyme_limits = self._stochastic_round(
                np.divide(
                    enzyme_pool * float(dt),
                    enzyme_requirements,
                    out=np.full(enzyme_requirements.shape, np.inf, dtype=np.float64),
                    where=enzyme_requirements > 0,
                )
            )

            num_reactions = int(
                np.floor(
                    min(
                        float(total_rnas),
                        float(np.min(enzyme_limits)),
                        float(np.min(substrate_limits)),
                    )
                )
            )
            if num_reactions <= 0:
                continue

            selected = self._rand_counts(unprocessed_pool[reaction_indices], num_reactions)
            if not np.any(selected > 0):
                continue

            processing_events[reaction_indices] += selected
            unprocessed_pool[reaction_indices] -= selected
            substrate_pool += self.reaction_stoich[:, reaction_indices] @ selected

        return processing_events

    def _stochastic_round(self, value: np.ndarray) -> np.ndarray:
        value = np.asarray(value, dtype=np.float64)
        with np.errstate(invalid="ignore"):
            round_up = self._rng.random(value.shape) < np.mod(value, 1.0)
        rounded = value.copy()
        rounded[round_up] = np.ceil(value[round_up])
        rounded[~round_up] = np.floor(value[~round_up])
        return rounded

    def _rand_counts(self, counts: np.ndarray, n_select: int) -> np.ndarray:
        counts = np.asarray(counts, dtype=np.int64)
        total = int(np.sum(counts))
        if n_select <= 0 or total <= 0:
            return np.zeros_like(counts, dtype=np.int64)

        n_select = int(min(n_select, total))
        if n_select == total:
            return counts.copy()

        positive_select = True
        if n_select > total / 2:
            positive_select = False
            n_select = total - n_select

        cumulative = np.cumsum(counts, dtype=np.int64)
        selected = np.zeros_like(counts, dtype=np.int64)
        for _ in range(int(n_select)):
            draw = int(self._rng.integers(1, int(cumulative[-1]) + 1))
            chosen_idx = int(np.searchsorted(cumulative, draw, side="left"))
            selected[chosen_idx] += 1
            cumulative[chosen_idx:] -= 1

        if not positive_select:
            return counts - selected
        return selected


__all__ = ["KarrRNAProcessingProcess"]
