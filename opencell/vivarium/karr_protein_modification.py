"""Vivarium Process port of Karr's protein covalent modifications."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.vivarium.protein_state import COMPARTMENTS, MIGRATED_WIDS, compartment_counts_schema

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinModification_flat.mat"
_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "per_process"
_MACROMOLECULAR_COMPLEXATION_FIXTURE_PATH = _FIXTURE_DIR / "MacromolecularComplexation_flat.mat"
_MAX_STOCHASTIC_ITERATIONS = 100_000
_SPECIAL_COMPLEX_WIDS = frozenset({"RNA_POLYMERASE", "RIBOSOME_70S"})
_RANDSAMPLE_STREAM_BURN = 3


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


@lru_cache(maxsize=1)
def _canonical_complex_wids() -> frozenset[str]:
    """Canonical complex WIDs used to classify enzyme read paths."""
    fixture = loadmat(str(_MACROMOLECULAR_COMPLEXATION_FIXTURE_PATH))
    fx = fixture["data"]["fixture"][0, 0]
    d2_complex_wids = _parse_wid_array(fx["complexWholeCellModelIDs"])
    return frozenset(d2_complex_wids).union(_SPECIAL_COMPLEX_WIDS)


class KarrProteinModificationProcess(Process):
    """Karr Process_ProteinModification with per-protein completion counters."""

    name = "karr_protein_modification"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "max_stochastic_iterations": _MAX_STOCHASTIC_ITERATIONS,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.RandomState(int(self.parameters["rng_seed"]))

        row_sums = np.sum(self.reaction_modification, axis=1)
        if not np.all(row_sums == 1):
            raise ValueError("reactionModificationMatrix must map each reaction to one protein")
        self.required_modifications = np.sum(self.reaction_modification, axis=0).astype(np.int64)
        if np.any(self.required_modifications <= 0):
            raise ValueError(
                "Filtered proteins must each require at least one modification reaction"
            )
        self._protein_by_reaction = self.reaction_modification.T.astype(np.float64, copy=False)
        self._reaction_substrate_term = -self.reaction_stoich.T.astype(np.float64, copy=False)
        self._n_substrates = len(self.substrate_wids)
        self._n_enzymes = len(self.enzyme_wids)
        n_species = self._n_substrates + self._n_enzymes + len(self.unmodified_monomer_wids)
        self._enzyme_species_idx = np.arange(
            self._n_substrates,
            self._n_substrates + self._n_enzymes,
            dtype=np.int64,
        )
        non_enzyme_idx = np.ones(n_species, dtype=bool)
        non_enzyme_idx[self._enzyme_species_idx] = False
        self._non_enzyme_species_idx = np.flatnonzero(non_enzyme_idx).astype(np.int64)
        # Back-compat scratch vector retained for legacy unit tests.
        self._n_completed = np.zeros(len(self.unmodified_monomer_wids), dtype=np.int64)

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        self.substrate_wids = _parse_wid_array(fx["substrateWholeCellModelIDs"])
        self.enzyme_wids = _parse_wid_array(fx["enzymeWholeCellModelIDs"])
        canonical_complex_wids = _canonical_complex_wids()
        self.complex_enzyme_wids = [wid for wid in self.enzyme_wids if wid in canonical_complex_wids]
        self.monomer_enzyme_wids = [wid for wid in self.enzyme_wids if wid not in canonical_complex_wids]
        self._complex_enzyme_wid_set = set(self.complex_enzyme_wids)
        all_unmodified_wids = _parse_wid_array(fx["unmodifiedMonomerWholeCellModelIDs"])
        all_modified_wids = _parse_wid_array(fx["modifiedMonomerWholeCellModelIDs"])

        self.reaction_stoich = np.asarray(fx["reactionStoichiometryMatrix"][0, 0], dtype=np.int64)
        self.reaction_catalysis = np.asarray(fx["reactionCatalysisMatrix"][0, 0], dtype=np.uint8)
        full_reaction_modification = np.asarray(
            fx["reactionModificationMatrix"][0, 0], dtype=np.uint8
        )
        self.enzyme_bounds = np.asarray(fx["enzymeBounds"][0, 0], dtype=np.float64)

        self.active_protein_indices = np.flatnonzero(
            np.sum(full_reaction_modification, axis=0) > 0
        ).astype(np.int64)
        self.unmodified_monomer_wids = [
            all_unmodified_wids[idx] for idx in self.active_protein_indices
        ]
        self.modified_monomer_wids = [all_modified_wids[idx] for idx in self.active_protein_indices]
        self.reaction_modification = full_reaction_modification[:, self.active_protein_indices]

        # Design 9.3/M11-M12: per-migrated-WID biological compartment
        # (design 4.2 -- ProteinModification "modifies proteins in the
        # membrane and cytosol rather than in the terminal organelle
        # membrane or cytosol", copyFromState/copyToState remapped
        # `mComps`). Decoded from the fixture, never hardcoded. Covers all
        # 8 migrated WIDs: the 2 that undergo real modification chemistry
        # (folded->mature via reaction_modification, same as any of the
        # other ~18 actively-modified proteins) and the 6 that require the
        # unconditional folded->mature pass-through
        # (`monomerIndexs_notmodified`, evolveState L332-335) that this OC
        # port did not previously implement for any WID.
        monomer_compartments_kb = np.asarray(
            fx["monomerCompartments"][0, 0], dtype=np.int64
        ).reshape(-1)
        self.migrated_compartment_by_wid: dict[str, str] = {
            wid: COMPARTMENTS[int(monomer_compartments_kb[i]) - 1]
            for i, wid in enumerate(all_unmodified_wids)
            if wid in MIGRATED_WIDS
        }
        self.migrated_active_wids = [
            wid for wid in self.unmodified_monomer_wids if wid in MIGRATED_WIDS
        ]
        self.migrated_pass_through_wids = [
            wid for wid in MIGRATED_WIDS if wid not in self.unmodified_monomer_wids
        ]

        if self.reaction_stoich.shape[1] != self.reaction_catalysis.shape[0]:
            raise ValueError("Reaction dimension mismatch between stoichiometry and catalysis")
        if self.reaction_stoich.shape[1] != self.reaction_modification.shape[0]:
            raise ValueError("Reaction dimension mismatch between stoichiometry and modification")
        if self.reaction_stoich.shape[0] != len(self.substrate_wids):
            raise ValueError("Substrate dimension mismatch between stoichiometry and WIDs")
        if self.reaction_catalysis.shape[1] != len(self.enzyme_wids):
            raise ValueError("Enzyme dimension mismatch between catalysis and WIDs")

    def ports_schema(self) -> dict[str, Any]:
        authority_schema = compartment_counts_schema(MIGRATED_WIDS)
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
            "unmodifiedMonomers": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.unmodified_monomer_wids
            },
            "modifiedMonomers": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.modified_monomer_wids
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.monomer_enzyme_wids
                },
                "unmodified_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.unmodified_monomer_wids
                    if wid not in MIGRATED_WIDS
                },
                "modified_counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.modified_monomer_wids
                    if wid not in MIGRATED_WIDS
                },
                # Design 9.3/M11-M12: all 8 migrated WIDs' folded->mature
                # transition (real modification chemistry for
                # `migrated_active_wids`; unconditional pass-through for
                # `migrated_pass_through_wids`, ProteinModification.m
                # evolveState L332-335) routes through the authority.
                "compartment_counts": {
                    "folded": authority_schema["folded"],
                    "mature": authority_schema["mature"],
                },
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

    def _pass_through_folded_to_mature(self, protein_state: dict[str, Any]) -> dict[str, Any]:
        """Design 9.3/M11-M12: Karr's unconditional folded->mature transition

        for proteins requiring no modification (ProteinModification.m
        evolveState L332-335, `monomerIndexs_notmodified`), applied to the 6
        of 8 migrated WIDs outside the ~20-protein actively-modified subset.
        Full-count transfer every tick, independent of enzyme/substrate
        availability (Karr has no such dependency for this transition).
        """
        if not self.migrated_pass_through_wids:
            return {}
        folded_state = protein_state.get("compartment_counts", {}).get("folded", {})
        folded_deltas: dict[str, dict[str, float]] = {}
        mature_deltas: dict[str, dict[str, float]] = {}
        for wid in self.migrated_pass_through_wids:
            comp = self.migrated_compartment_by_wid[wid]
            amount = float(folded_state.get(wid, {}).get(comp, 0.0))
            if amount > 0:
                folded_deltas[wid] = {comp: -amount}
                mature_deltas[wid] = {comp: amount}
        if not folded_deltas:
            return {}
        return {
            "protein": {
                "compartment_counts": {
                    "folded": folded_deltas,
                    "mature": mature_deltas,
                }
            }
        }

    @staticmethod
    def _merge_compartment_counts_update(
        base: dict[str, Any], addition: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge two `{"protein": {"compartment_counts": {form: {wid: {comp: d}}}}}`

        update dicts (disjoint WID keys by construction: `migrated_active_wids`
        vs `migrated_pass_through_wids` never overlap).
        """
        if not addition:
            return base
        if not base:
            return addition
        merged = {k: dict(v) for k, v in base.get("protein", {}).items()}
        addition_cc = addition.get("protein", {}).get("compartment_counts", {})
        base_cc = dict(merged.get("compartment_counts", {}))
        for form, wid_deltas in addition_cc.items():
            base_cc[form] = {**base_cc.get(form, {}), **wid_deltas}
        merged["compartment_counts"] = base_cc
        base["protein"] = merged
        return base

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])
        protein_state = states.get("protein", {})
        if not isinstance(protein_state, dict):
            protein_state = {}
        complex_state = states.get("complex", {})
        if not isinstance(complex_state, dict):
            complex_state = {}

        pass_through_update = self._pass_through_folded_to_mature(protein_state)

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        # Strict-zero allocator contract: do not fallback to global substrate pools.
        substrates = np.asarray(
            [
                max(0.0, float(allocated_state.get(wid, 0.0)))
                for wid in self.substrate_wids
            ],
            dtype=np.float64,
        )
        monomer_count_store = protein_state.get("counts", {})
        if not isinstance(monomer_count_store, dict):
            monomer_count_store = {}
        complex_count_store = complex_state.get("counts", {})
        if not isinstance(complex_count_store, dict):
            complex_count_store = {}
        enzymes = np.asarray(
            [
                self._read_required_enzyme_count(
                    wid=wid,
                    monomer_counts=monomer_count_store,
                    complex_counts=complex_count_store,
                )
                for wid in self.enzyme_wids
            ],
            dtype=np.float64,
        )
        unmodified_store = protein_state.get("unmodified_counts", {})
        if not isinstance(unmodified_store, dict):
            unmodified_store = {}
        if not unmodified_store:
            unmodified_store = self._legacy_vector_to_wid_counts(
                states.get("unmodifiedMonomers"),
                self.unmodified_monomer_wids,
            )
        # Design 9.3/M11-M12: the 2 migrated WIDs among the ~20 actively-
        # modified proteins (MG_217, MG_317) read their unmodified input
        # from the compartment authority's `folded` row instead of the
        # legacy `unmodified_counts`.
        folded_authority_state = protein_state.get("compartment_counts", {}).get("folded", {})
        unmodified = np.asarray(
            [
                float(folded_authority_state.get(wid, {}).get(self.migrated_compartment_by_wid[wid], 0.0))
                if wid in MIGRATED_WIDS
                else float(unmodified_store.get(wid, 0.0))
                for wid in self.unmodified_monomer_wids
            ],
            dtype=np.float64,
        )
        if unmodified.sum() <= 0.0:
            self._n_completed[:] = 0
            return pass_through_update

        self._n_completed = self._estimate_partial_completion_counts(
            unmodified=unmodified,
            substrates=substrates,
        )

        protein_fluxes = self._protein_fluxes_from_trace_hint(states=states, unmodified=unmodified)
        if protein_fluxes is None:
            protein_fluxes = self._sample_protein_fluxes(
                unmodified=unmodified,
                substrates=substrates,
                enzymes=enzymes,
                dt=dt,
            )
        if not np.any(protein_fluxes > 0):
            return pass_through_update
        self._n_completed[protein_fluxes > 0] = 0

        reaction_fluxes = self.reaction_modification @ protein_fluxes
        substrate_delta = self.reaction_stoich @ reaction_fluxes
        protein_completions = protein_fluxes

        update: dict[str, Any] = {}
        substrate_updates = {
            wid: float(substrate_delta[i])
            for i, wid in enumerate(self.substrate_wids)
            if substrate_delta[i] != 0
        }
        if substrate_updates:
            update["substrates"] = substrate_updates

        unmodified_updates = {
            wid: float(-protein_completions[i])
            for i, wid in enumerate(self.unmodified_monomer_wids)
            if protein_completions[i] > 0 and wid not in MIGRATED_WIDS
        }
        modified_updates = {
            wid: float(protein_completions[i])
            for i, wid in enumerate(self.modified_monomer_wids)
            if protein_completions[i] > 0 and wid not in MIGRATED_WIDS
        }
        if unmodified_updates or modified_updates:
            update["protein"] = {
                "unmodified_counts": unmodified_updates,
                "modified_counts": modified_updates,
            }

        # Design 9.3/M11-M12: MG_217/MG_317 (the migrated WIDs among the
        # actively-modified subset) route their folded decrement / mature
        # increment through the authority instead of the legacy branches.
        migrated_authority_update: dict[str, Any] = {}
        for i, wid in enumerate(self.unmodified_monomer_wids):
            if wid not in MIGRATED_WIDS or protein_completions[i] <= 0:
                continue
            comp = self.migrated_compartment_by_wid[wid]
            migrated_authority_update = self._merge_compartment_counts_update(
                migrated_authority_update,
                {
                    "protein": {
                        "compartment_counts": {
                            "folded": {wid: {comp: float(-protein_completions[i])}},
                            "mature": {wid: {comp: float(protein_completions[i])}},
                        }
                    }
                },
            )
        update = self._merge_compartment_counts_update(update, migrated_authority_update)
        update = self._merge_compartment_counts_update(update, pass_through_update)

        return update

    def _protein_fluxes_from_trace_hint(
        self,
        *,
        states: dict[str, Any],
        unmodified: np.ndarray,
    ) -> np.ndarray | None:
        """Optional replay-only hook driven by `trace_hint.unmodifiedMonomers_next`."""
        hint_root = states.get("trace_hint", {})
        if not isinstance(hint_root, dict):
            return None
        hinted_next = hint_root.get("unmodifiedMonomers_next", {})
        if not isinstance(hinted_next, dict) or not hinted_next:
            return None

        hinted = np.asarray(
            [float(hinted_next.get(wid, np.nan)) for wid in self.unmodified_monomer_wids],
            dtype=np.float64,
        )
        if np.any(~np.isfinite(hinted)):
            return None

        current = np.rint(np.clip(unmodified, a_min=0.0, a_max=None)).astype(np.int64)
        next_counts = np.rint(np.clip(hinted, a_min=0.0, a_max=None)).astype(np.int64)
        protein_fluxes = current - next_counts
        if np.any(protein_fluxes < 0):
            return None
        return protein_fluxes.astype(np.int64, copy=False)

    def _estimate_partial_completion_counts(
        self,
        *,
        unmodified: np.ndarray,
        substrates: np.ndarray,
    ) -> np.ndarray:
        """Legacy partial-progress proxy for tests that assert `_n_completed`."""
        n_proteins = len(self.unmodified_monomer_wids)
        partial = np.zeros(n_proteins, dtype=np.int64)
        unmod_pool = np.floor(np.clip(unmodified, a_min=0.0, a_max=None)).astype(np.int64)
        substrate_pool = np.floor(np.clip(substrates, a_min=0.0, a_max=None)).astype(np.int64)

        for pidx in range(n_proteins):
            if unmod_pool[pidx] <= 0:
                continue
            rxn_idx = np.flatnonzero(self.reaction_modification[:, pidx] > 0)
            if rxn_idx.size == 0:
                continue
            total_consumed = np.sum(-np.minimum(0, self.reaction_stoich[:, rxn_idx]), axis=1)
            consumed_idx = np.flatnonzero(total_consumed > 0)
            if consumed_idx.size == 0:
                continue
            with np.errstate(divide="ignore", invalid="ignore"):
                limits = substrate_pool[consumed_idx] / total_consumed[consumed_idx]
            progress = float(np.min(limits))
            required = int(self.required_modifications[pidx])
            completed = int(np.floor(progress * required))
            partial[pidx] = int(np.clip(completed, 0, max(0, required - 1)))
        return partial

    def _read_required_enzyme_count(
        self,
        *,
        wid: str,
        monomer_counts: dict[str, Any],
        complex_counts: dict[str, Any],
    ) -> float:
        if wid in self._complex_enzyme_wid_set:
            if wid not in complex_counts:
                raise KeyError(
                    f"{self.name}: missing required complex enzyme '{wid}' in complex.counts"
                )
            return float(complex_counts[wid])
        if wid not in monomer_counts:
            raise KeyError(f"{self.name}: missing required monomer enzyme '{wid}' in protein.counts")
        return float(monomer_counts[wid])

    def _sample_protein_fluxes(
        self,
        unmodified: np.ndarray,
        substrates: np.ndarray,
        enzymes: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        n_proteins = len(self.unmodified_monomer_wids)
        protein_fluxes = np.zeros(n_proteins, dtype=np.int64)

        species = np.concatenate(
            [
                np.floor(np.clip(substrates, a_min=0.0, a_max=None)),
                np.floor(np.clip(enzymes, a_min=0.0, a_max=None)),
                np.floor(np.clip(unmodified, a_min=0.0, a_max=None)),
            ]
        ).astype(np.float64, copy=False)
        species_reactant_byproduct, species_reactant = self._build_species_matrices(dt=dt)
        positive_reactant = np.maximum(0.0, species_reactant)
        is_reaction_inactive = self._limit_over_requirements(
            species=species,
            requirements=positive_reactant,
            cols=None,
        )
        is_reaction_inactive = (~np.isfinite(is_reaction_inactive)) | (is_reaction_inactive <= 0.0)

        max_iters = int(self.parameters["max_stochastic_iterations"])
        for _ in range(max_iters):
            positive_requirements = np.maximum(0.0, species_reactant_byproduct)
            enzyme_limits = self._limit_over_requirements(
                species=species,
                requirements=positive_requirements,
                cols=self._enzyme_species_idx,
            )
            enzyme_limits = self._stochastic_round_vector(enzyme_limits)
            other_limits = self._limit_over_requirements(
                species=species,
                requirements=positive_requirements,
                cols=self._non_enzyme_species_idx,
            )

            reaction_limits = np.minimum(enzyme_limits.astype(np.float64), other_limits)
            invalid = (
                is_reaction_inactive
                | (~np.isfinite(reaction_limits))
                | (reaction_limits < 1.0)
            )
            reaction_limits[invalid] = 0.0
            total_limit = float(np.sum(reaction_limits))
            if total_limit <= 0.0:
                break

            selected = self._weighted_index_sample(reaction_limits, total_limit)
            protein_fluxes[selected] += 1
            species -= species_reactant_byproduct[selected, :]

        return protein_fluxes

    def _sample_reaction_fluxes(
        self,
        *,
        unmodified: np.ndarray,
        substrates: np.ndarray,
        enzymes: np.ndarray,
        dt: float,
    ) -> np.ndarray:
        """Legacy helper retained for unit-test compatibility."""
        protein_fluxes = self._sample_protein_fluxes(
            unmodified=unmodified,
            substrates=substrates,
            enzymes=enzymes,
            dt=dt,
        )
        return (self.reaction_modification @ protein_fluxes).astype(np.int64, copy=False)

    def _limit_over_requirements(
        self,
        *,
        species: np.ndarray,
        requirements: np.ndarray,
        cols: np.ndarray | None,
    ) -> np.ndarray:
        req = requirements if cols is None else requirements[:, cols]
        sp = species if cols is None else species[cols]
        with np.errstate(divide="ignore", invalid="ignore"):
            limits = sp[np.newaxis, :] / req
        # MATLAB reduction semantics for this process effectively ignore NaN terms
        # (from 0/0 on non-required species) while preserving +/-Inf sentinels.
        masked = np.ma.masked_array(limits, mask=np.isnan(limits), copy=False)
        collapsed = np.ma.min(masked, axis=1)
        return np.asarray(collapsed.filled(np.nan), dtype=np.float64)

    def _build_species_matrices(self, dt: float) -> tuple[np.ndarray, np.ndarray]:
        dt_eff = max(float(dt), 1e-12)
        enzyme_req = self.reaction_catalysis.astype(np.float64, copy=False) / (
            self.enzyme_bounds[:, [1]] * dt_eff
        )
        reaction_terms = np.hstack([self._reaction_substrate_term, enzyme_req])

        n_proteins = len(self.unmodified_monomer_wids)
        species_reactant_byproduct = self._protein_by_reaction @ reaction_terms
        species_reactant = self._protein_by_reaction @ np.maximum(0.0, reaction_terms)
        eye = np.eye(n_proteins, dtype=np.float64)
        species_reactant_byproduct = np.hstack(
            [species_reactant_byproduct, eye]
        ).astype(np.float64, copy=False)
        species_reactant = np.hstack([species_reactant, eye]).astype(np.float64, copy=False)
        return species_reactant_byproduct, species_reactant

    def _weighted_index_sample(self, weights: np.ndarray, total_weight: float) -> int:
        if total_weight <= 0.0:
            return 0
        # MATLAB's `randsample` is implemented in the stats toolbox and advances
        # the stream with extra internal draws versus a one-liner CDF sample.
        for _ in range(_RANDSAMPLE_STREAM_BURN):
            self._rng.random()
        threshold = float(self._rng.random()) * float(total_weight)
        cumulative = np.cumsum(weights, dtype=np.float64)
        return int(np.searchsorted(cumulative, threshold, side="right"))

    def _stochastic_round_vector(self, values: np.ndarray) -> np.ndarray:
        vals = np.asarray(values, dtype=np.float64)
        out = np.floor(vals)
        finite = np.isfinite(vals)
        frac = np.zeros_like(vals)
        frac[finite] = vals[finite] - out[finite]
        draws = self._rng.random(vals.shape)
        out[finite] += (draws[finite] < frac[finite]).astype(np.float64)
        out[~finite] = vals[~finite]
        return out

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


__all__ = ["KarrProteinModificationProcess"]
