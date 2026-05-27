"""karr_rna_processing — Karr 2012 RNA Processing process (light/v5 chassis).

ARCHITECTURAL DEFER (2026-05-27): This process is registered and called every
tick but currently always returns ``{}``. This is intentional, not a bug.

Karr's MATLAB chain is:
    Transcription -> nascent TU-keyed RNA pool -> RNAProcessing -> mature mRNA/rRNA/sRNA/tRNA

OpenCell v5 chassis collapses this into TX-emits-mature: `karr_transcription`
writes mature gene-keyed RNA (`MG_###`) directly to `rna.counts`. RNAProcessing
here reads unprocessed TU-keyed RNA (`TU_###`). Intersection of the two ID
spaces is empty at runtime, so the unprocessed-pool gate at
:func:`KarrRNAProcessingProcess.next_update` correctly returns empty every tick.

The full Karr-faithful fix (TX emits nascent TU pool, RNAProcessing converts to
mature pool) is wave3 Option 1 — see ``docs/processes/rna_processing_defer.md``.

Until wave3, this module is kept registered (a) to preserve the wiring topology
for future restoration, (b) to keep the process count at 28 for canary
completeness, and (c) so any future TX change that *does* emit TU-keyed RNA
will automatically light this process up.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.vivarium.karr_trna_aminoacylation import _parse_wid_array, _resolve_fixture_path

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/RNAProcessing_flat.mat"
_MAX_STOCHASTIC_ITERATIONS = 10_000
_UNBOUNDED_LIMIT = 1_000_000_000_000


class KarrRNAProcessingProcess(Process):
    """Karr Process_RNAProcessing (deterministic + stochastic phases)."""

    name = "karr_rna_processing"
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

        self.rna_wids = list(dict.fromkeys(self.unprocessed_rna_wids + self.processed_rna_wids))
        self._processed_index_by_wid = {wid: idx for idx, wid in enumerate(self.rna_wids)}
        self._unprocessed_to_rna_idx = np.asarray(
            [self._processed_index_by_wid[wid] for wid in self.unprocessed_rna_wids], dtype=np.int64
        )

        # One reaction consumes one unprocessed RNA species.
        self.reaction_modification = np.eye(len(self.unprocessed_rna_wids), dtype=np.uint8)

        if self.reaction_stoich.shape[1] != len(self.unprocessed_rna_wids):
            raise ValueError(
                "reaction stoichiometry columns must match unprocessed RNA species count: "
                f"{self.reaction_stoich.shape[1]} != {len(self.unprocessed_rna_wids)}"
            )

        if self.reaction_catalysis.shape[0] != len(self.unprocessed_rna_wids):
            raise ValueError(
                "reaction catalysis rows must match reaction count: "
                f"{self.reaction_catalysis.shape[0]} != {len(self.unprocessed_rna_wids)}"
            )

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        self.substrate_wids = _parse_wid_array(fx["substrateWholeCellModelIDs"])
        self.unprocessed_rna_wids = _parse_wid_array(fx["unprocessedRNAWholeCellModelIDs"])
        self.processed_rna_wids = _parse_wid_array(fx["processedRNAWholeCellModelIDs"])
        self.enzyme_wids = _parse_wid_array(fx["enzymeWholeCellModelIDs"])

        self.reaction_stoich = self._read_reaction_stoich(fx)
        self.reaction_catalysis = self._read_reaction_catalysis(fx)
        self.processed_output_matrix = self._build_processed_output_matrix(fx)

        if "enzymeBounds" in fx.dtype.names:
            self.enzyme_bounds = np.asarray(fx["enzymeBounds"][0, 0], dtype=np.float64)
        else:
            self.enzyme_bounds = np.column_stack(
                [
                    np.zeros(self.reaction_stoich.shape[1], dtype=np.float64),
                    np.ones(self.reaction_stoich.shape[1], dtype=np.float64),
                ]
            )

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
        if raw.shape != (len(self.unprocessed_rna_wids), len(self.enzyme_wids)):
            raise ValueError(
                "Unexpected catalysis matrix shape: "
                f"{raw.shape}, expected ({len(self.unprocessed_rna_wids)}, {len(self.enzyme_wids)})"
            )
        return np.clip(raw, a_min=0.0, a_max=None)

    def _build_processed_output_matrix(self, fx: np.ndarray) -> np.ndarray:
        n_processed = len(self.processed_rna_wids)
        n_reactions = len(self.unprocessed_rna_wids)
        outputs: list[set[int]] = [set() for _ in range(n_reactions)]

        processed_pos = {wid: idx for idx, wid in enumerate(self.processed_rna_wids)}
        for ridx, wid in enumerate(self.unprocessed_rna_wids):
            if wid in processed_pos:
                outputs[ridx].add(processed_pos[wid])

        # Heuristic segmentation by shared TU anchors.
        tu_positions = {
            wid: pidx for pidx, wid in enumerate(self.processed_rna_wids) if wid.startswith("TU_")
        }
        anchors: list[tuple[int, int]] = [(-1, -1)]
        last_pidx = -1
        for ridx, wid in enumerate(self.unprocessed_rna_wids):
            pidx = tu_positions.get(wid)
            if pidx is not None and pidx > last_pidx:
                anchors.append((ridx, pidx))
                last_pidx = pidx
        anchors.append((n_reactions, n_processed))

        for (r0, p0), (r1, p1) in zip(anchors[:-1], anchors[1:], strict=False):
            missing = list(range(r0 + 1, r1))
            if not missing:
                continue
            segment = self.processed_rna_wids[p0 + 1 : p1]
            inserted = [wid for wid in segment if not wid.startswith("TU_")]
            if not inserted:
                continue
            for out_idx, out_wid in enumerate(inserted):
                target_rxn = missing[min(out_idx, len(missing) - 1)]
                target_pidx = processed_pos.get(out_wid)
                if target_pidx is not None:
                    outputs[target_rxn].add(target_pidx)

        # Explicit index-based hints from fixture metadata.
        self._apply_index_mapping_hints(fx, outputs)

        out_matrix = np.zeros((n_processed, n_reactions), dtype=np.int64)
        for ridx, pidx_set in enumerate(outputs):
            for pidx in pidx_set:
                if 0 <= pidx < n_processed:
                    out_matrix[pidx, ridx] = 1
        return out_matrix

    def _apply_index_mapping_hints(self, fx: np.ndarray, outputs: list[set[int]]) -> None:
        map_specs: list[tuple[str, str]] = [
            ("unprocessedRNAIndexs_mRNA", "processedRNAIndexs_mRNA"),
            ("unprocessedRNAIndexs_sRNA", "processedRNAIndexs_sRNA"),
            ("unprocessedRNAIndexs_scRNA", "processedRNAIndexs_scRNA"),
            ("unprocessedRNAIndexs_tmRNA", "processedRNAIndexs_tmRNA"),
            ("unprocessedRNAIndexs_rRNA", "processedRNAIndexs_rRNA"),
        ]
        for un_key, pr_key in map_specs:
            un_idx = self._read_1_based_indices(fx, un_key)
            pr_idx = self._read_1_based_indices(fx, pr_key)
            if not un_idx or not pr_idx:
                continue

            if len(un_idx) == len(pr_idx):
                for ridx, pidx in zip(un_idx, pr_idx, strict=False):
                    outputs[ridx].add(pidx)
                continue

            if len(un_idx) == 1:
                ridx = un_idx[0]
                for pidx in pr_idx:
                    outputs[ridx].add(pidx)
                continue

            if len(pr_idx) == 1:
                pidx = pr_idx[0]
                for ridx in un_idx:
                    outputs[ridx].add(pidx)

    def _read_1_based_indices(self, fx: np.ndarray, key: str) -> list[int]:
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
        return [
            i
            for i in out
            if 0 <= i < len(self.unprocessed_rna_wids) or 0 <= i < len(self.processed_rna_wids)
        ]

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
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
        rna_counts = states.get("rna", {}).get("counts", {})
        unprocessed = np.asarray(
            [float(rna_counts.get(wid, 0.0)) for wid in self.unprocessed_rna_wids], dtype=np.float64
        )
        # DEFER (wave3 Option 1): empty by design until TX emits TU-keyed nascent pool.
        # See module docstring + docs/processes/rna_processing_defer.md.
        if unprocessed.sum() <= 0.0:
            return {}

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        # Strict-zero allocator contract: do not fallback to global substrate pools.
        substrates = np.asarray(
            [
                max(0.0, float(allocated_state.get(wid, 0.0)))
                for wid in self.substrate_wids
            ],
            dtype=np.float64,
        )
        enzymes = np.asarray(
            [float(states["protein"]["counts"].get(wid, 0.0)) for wid in self.enzyme_wids],
            dtype=np.float64,
        )

        reaction_fluxes = self._compute_reaction_fluxes(
            unprocessed=unprocessed,
            substrates=substrates,
            enzymes=enzymes,
            dt=float(self.parameters["time_step"]),
        )
        if not np.any(reaction_fluxes > 0):
            return {}

        substrate_delta = self.reaction_stoich @ reaction_fluxes
        unprocessed_delta = -reaction_fluxes
        processed_delta = self.processed_output_matrix @ reaction_fluxes

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

    def _compute_reaction_fluxes(
        self,
        unprocessed: np.ndarray,
        substrates: np.ndarray,
        enzymes: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        n_rxn = self.reaction_stoich.shape[1]
        reaction_fluxes = np.zeros(n_rxn, dtype=np.int64)

        substrate_pool = np.floor(np.clip(substrates, a_min=0.0, a_max=None)).astype(np.int64)
        unprocessed_pool = np.floor(np.clip(unprocessed, a_min=0.0, a_max=None)).astype(np.int64)
        enzyme_remaining = np.floor(
            np.clip(self._enzyme_limit(enzymes=enzymes, dt=dt), a_min=0.0, a_max=None)
        ).astype(np.int64)

        for ridx in range(n_rxn):
            sub_limit = self._substrate_limit_for_reaction(substrate_pool, ridx)
            enz_limit = int(enzyme_remaining[ridx])
            rna_limit = int(unprocessed_pool[ridx])
            n_events = int(min(sub_limit, enz_limit, rna_limit))
            if n_events <= 0:
                continue
            reaction_fluxes[ridx] += n_events
            substrate_pool += self.reaction_stoich[:, ridx] * n_events
            unprocessed_pool[ridx] -= n_events
            enzyme_remaining[ridx] -= n_events

        max_iters = int(self.parameters["max_stochastic_iterations"])
        for _ in range(max_iters):
            progressed = self._stochastic_residual_step(
                reaction_fluxes=reaction_fluxes,
                substrate_pool=substrate_pool,
                unprocessed_pool=unprocessed_pool,
                enzyme_remaining=enzyme_remaining,
            )
            if not progressed:
                break

        return reaction_fluxes

    def _substrate_limit_for_reaction(self, substrates: np.ndarray, ridx: int) -> int:
        stoich_col = self.reaction_stoich[:, ridx]
        consumed_idx = np.flatnonzero(stoich_col < 0)
        if consumed_idx.size == 0:
            return _UNBOUNDED_LIMIT

        req = -stoich_col[consumed_idx]
        avail = substrates[consumed_idx]
        limit = int(np.min(avail // req))
        return max(0, limit)

    def _substrate_limit(self, substrates: np.ndarray) -> np.ndarray:
        n_rxn = self.reaction_stoich.shape[1]
        limits = np.zeros(n_rxn, dtype=np.int64)
        for ridx in range(n_rxn):
            limits[ridx] = self._substrate_limit_for_reaction(substrates, ridx)
        return limits

    def _enzyme_limit(self, enzymes: np.ndarray, dt: float) -> np.ndarray:
        enz = np.asarray(enzymes, dtype=np.float64).reshape(-1)
        if enz.size < len(self.enzyme_wids):
            raise ValueError(f"enzyme vector too short: {enz.size} < {len(self.enzyme_wids)}")

        catalytic_enzymes = np.clip(enz[: len(self.enzyme_wids)], a_min=0.0, a_max=None)
        limits = np.full(
            self.reaction_catalysis.shape[0], float(_UNBOUNDED_LIMIT), dtype=np.float64
        )
        for ridx in range(self.reaction_catalysis.shape[0]):
            req = self.reaction_catalysis[ridx]
            active = req > 0.0
            if not np.any(active):
                continue
            rxn_limits = (catalytic_enzymes[active] * float(dt)) / req[active]
            limits[ridx] = np.floor(np.min(rxn_limits))
        return np.clip(limits, a_min=0.0, a_max=float(_UNBOUNDED_LIMIT))

    def _stochastic_residual_step(
        self,
        reaction_fluxes: np.ndarray,
        substrate_pool: np.ndarray,
        unprocessed_pool: np.ndarray,
        enzyme_remaining: np.ndarray,
    ) -> bool:
        substrate_limit = self._substrate_limit(substrate_pool)
        residual_limit = np.minimum.reduce([substrate_limit, unprocessed_pool, enzyme_remaining])
        feasible = np.flatnonzero(residual_limit > 0)
        if feasible.size == 0:
            return False

        weights = residual_limit[feasible].astype(np.float64)
        weight_sum = float(np.sum(weights))
        if weight_sum <= 0.0:
            return False

        chosen = int(self._rng.choice(feasible, p=(weights / weight_sum)))
        if unprocessed_pool[chosen] <= 0 or enzyme_remaining[chosen] <= 0:
            return False

        reaction_fluxes[chosen] += 1
        substrate_pool += self.reaction_stoich[:, chosen]
        unprocessed_pool[chosen] -= 1
        enzyme_remaining[chosen] -= 1
        return True


__all__ = ["KarrRNAProcessingProcess"]
