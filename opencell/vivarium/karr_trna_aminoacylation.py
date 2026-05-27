"""Vivarium Process port of Karr's tRNA aminoacylation flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/tRNAAminoacylation_flat.mat"
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


class KarrTRNAAminoacylationProcess(Process):
    """Karr Process_tRNAAminoacylation (deterministic + stochastic phases)."""

    name = "karr_trna_aminoacylation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "max_stochastic_iterations": _MAX_STOCHASTIC_ITERATIONS,
        # Optional traceability hook for chassis-level diagnostics: emit a
        # structured no-op update instead of `{}` when guards suppress flux.
        "emit_noop_update": False,
        # When enabled, the chassis tracer may emit a heartbeat row for no-op ticks.
        "emit_trace_heartbeat_on_noop": False,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        row_sums = np.sum(self.reaction_modification, axis=1)
        if not np.all(row_sums == 1):
            raise ValueError(
                "reactionModificationMatrix must have exactly one target RNA per reaction"
            )
        self._reaction_target_idx = np.argmax(self.reaction_modification, axis=1).astype(np.int64)

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        self.substrate_wids = _parse_wid_array(fx["substrateWholeCellModelIDs"])
        self.free_rna_wids = _parse_wid_array(fx["freeRNAWholeCellModelIDs"])
        self.aminoacylated_rna_wids = _parse_wid_array(fx["aminoacylatedRNAWholeCellModelIDs"])
        self.enzyme_wids = _parse_wid_array(fx["enzymeWholeCellModelIDs"])

        self.reaction_stoich = np.asarray(fx["reactionStoichiometryMatrix"][0, 0], dtype=np.int64)
        self.reaction_catalysis = np.asarray(fx["reactionCatalysisMatrix"][0, 0], dtype=np.uint8)
        self.reaction_modification = np.asarray(
            fx["reactionModificationMatrix"][0, 0], dtype=np.uint8
        )
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
                    for wid in self.enzyme_wids
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

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        # Strict-zero allocator contract: do not fallback to global substrate pools.
        substrates = np.asarray(
            [
                max(0.0, float(allocated_state.get(wid, 0.0)))
                for wid in self.substrate_wids
            ],
            dtype=np.float64,
        )
        free_store = rna_state.get("counts", {})
        if not isinstance(free_store, dict):
            free_store = {}
        if not free_store:
            free_store = self._legacy_vector_to_wid_counts(
                states.get("freeRNAs"),
                self.free_rna_wids,
            )
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
            [
                float(amino_store.get(wid, 0.0))
                for wid in self.aminoacylated_rna_wids
            ],
            dtype=np.float64,
        )
        protein_count_store = protein_state.get("counts", {})
        if not isinstance(protein_count_store, dict):
            protein_count_store = {}
        enzymes = np.asarray(
            [float(protein_count_store.get(wid, 0.0)) for wid in self.enzyme_wids],
            dtype=np.float64,
        )

        if free_rna.sum() <= 0.0:
            return self._noop_update() if bool(self.parameters.get("emit_noop_update", False)) else {}

        reaction_fluxes = self._compute_reaction_fluxes(
            free_rna=free_rna,
            substrates=substrates,
            enzymes=enzymes,
            dt=float(self.parameters["time_step"]),
        )
        if not np.any(reaction_fluxes > 0):
            return self._noop_update() if bool(self.parameters.get("emit_noop_update", False)) else {}

        substrate_delta = self.reaction_stoich @ reaction_fluxes
        rna_consumed = self.reaction_modification.T @ reaction_fluxes
        free_delta = -rna_consumed
        aminoacylated_delta = rna_consumed

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

        # Keep explicit read-path for charged store in tests and engines.
        _ = aminoacylated_rna
        return update

    @staticmethod
    def _noop_update() -> dict[str, Any]:
        return {
            "substrates": {},
            "rna": {
                "counts": {},
                "aminoacylated_counts": {},
            },
        }

    def _compute_reaction_fluxes(
        self,
        free_rna: np.ndarray,
        substrates: np.ndarray,
        enzymes: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        n_rxn = self.reaction_stoich.shape[1]
        reaction_fluxes = np.zeros(n_rxn, dtype=np.int64)

        substrate_pool = np.floor(np.clip(substrates, a_min=0.0, a_max=None)).astype(np.int64)
        free_pool = np.floor(np.clip(free_rna, a_min=0.0, a_max=None)).astype(np.int64)
        enzyme_remaining = np.floor(
            np.clip(self._enzyme_limit(enzymes=enzymes, dt=dt), a_min=0.0, a_max=None)
        ).astype(np.int64)

        # Phase 1: deterministic allocation.
        for ridx in range(n_rxn):
            sub_limit = self._substrate_limit_for_reaction(substrate_pool, ridx)
            enz_limit = int(enzyme_remaining[ridx])
            free_limit = int(free_pool[self._reaction_target_idx[ridx]])
            n_events = int(min(sub_limit, enz_limit, free_limit))
            if n_events <= 0:
                continue

            reaction_fluxes[ridx] += n_events
            substrate_pool += self.reaction_stoich[:, ridx] * n_events
            free_pool[self._reaction_target_idx[ridx]] -= n_events
            enzyme_remaining[ridx] -= n_events

        # Phase 2: stochastic residual sampling.
        max_iters = int(self.parameters["max_stochastic_iterations"])
        for _ in range(max_iters):
            progressed = self._stochastic_residual_step(
                reaction_fluxes=reaction_fluxes,
                substrate_pool=substrate_pool,
                free_pool=free_pool,
                enzyme_remaining=enzyme_remaining,
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
        free_pool: np.ndarray,
        enzyme_remaining: np.ndarray,
    ) -> bool:
        substrate_limit = self._substrate_limit(substrate_pool)
        free_limit = self.reaction_modification @ free_pool
        residual_limit = np.minimum.reduce([substrate_limit, free_limit, enzyme_remaining])

        feasible = np.flatnonzero(residual_limit > 0)
        if feasible.size == 0:
            return False

        weights = residual_limit[feasible].astype(np.float64)
        weight_sum = float(np.sum(weights))
        if weight_sum <= 0.0:
            return False

        chosen = int(self._rng.choice(feasible, p=(weights / weight_sum)))
        target_idx = int(self._reaction_target_idx[chosen])

        if free_pool[target_idx] <= 0 or enzyme_remaining[chosen] <= 0:
            return False

        reaction_fluxes[chosen] += 1
        substrate_pool += self.reaction_stoich[:, chosen]
        free_pool[target_idx] -= 1
        enzyme_remaining[chosen] -= 1
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


__all__ = ["KarrTRNAAminoacylationProcess"]
