"""Vivarium Process for Karr DNADamage (Karr-light v1).

Karr primary source:
- data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/DNADamage.m
- docs/karr_extracts/process/04_DNADamage.md

This v1 implements only stochastic lesion creation and advisory replication
stall signaling. Repair chemistry and lesion-class-specific chromosome arrays
(`gapSites`, `damagedBases`, `strandBreaks`, etc.) are deferred to pc-t7/v2.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.m_gen_constants import GENOME_LENGTH_BP as _DEFAULT_SEQUENCE_LENGTH_NT
from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet, sparse_triplet_schema
from opencell.vivarium.chromosome_views import current_damage_sites

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/DNADamage_flat.mat"
_DAMAGE_KINDS = ("uv_like", "oxidative", "alkylation", "depurination")
_DAMAGE_FIELDS = (
    "damagedBases",
    "strandBreaks",
    "gapSites",
    "abasicSites",
    "damagedSugarPhosphates",
)

# Radiation gating: maps damage kind → substrate WID that must be >0 for
# that kind to fire.  Karr DNADamage.m line 549: if radiationLclIdx ~= 0,
# selectionProbability *= substrates(radiationLclIdx).  uv_like covers the
# 10 UVB_radiation-gated reactions; oxidative covers the 13 gamma_radiation-
# gated reactions.  Spontaneous kinds (alkylation, depurination) have no
# radiation gate and fire unconditionally at their (very low) base rates.
_RADIATION_GATE: dict[str, str] = {
    "uv_like": "UVB_radiation",
    "oxidative": "gamma_radiation",
}
_SPARSE_DAMAGE_FIELDS = (*_DAMAGE_FIELDS, "intrastrandCrossLinks", "hollidayJunctions")
_DAMAGE_KIND_TO_CHROMOSOME_FIELD = {
    "uv_like": "intrastrandCrossLinks",
    "oxidative": "damagedBases",
    "alkylation": "damagedBases",
    "depurination": "abasicSites",
}
_DEFAULT_KIND_RATES_PER_S = {
    # Karr extract table order-of-magnitude defaults for a light baseline.
    "uv_like": 6.0e-1,
    "oxidative": 1.7e-11,
    "alkylation": 0.0,
    "depurination": 8.4e-5,
}


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    return candidate


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _coerce_scalar(value: object) -> object:
    out = value
    while isinstance(out, np.ndarray):
        if out.size == 0:
            return ""
        out = out.flat[0]
    return out


def _is_finite_number(value: object) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _coerce_position_set(entries: Iterable[object]) -> set[int]:
    positions: set[int] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pos = entry.get("position")
        if _is_finite_number(pos):
            ipos = int(float(pos))
            if ipos > 0:
                positions.add(ipos)
    return positions


class KarrDNADamageProcess(Process):
    """Karr Process_DNADamage light port: stochastic lesion creation only."""

    name = "karr_dna_damage"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "sequence_length_nt": None,
        "enforce_unique_positions": True,
        "kind_rates_per_s": dict(_DEFAULT_KIND_RATES_PER_S),
        "fork_match_tolerance_nt": 0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        raw_parameters = {} if parameters is None else dict(parameters)
        super().__init__(parameters)
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))
        self.damage_kinds = list(_DAMAGE_KINDS)
        self._tick_index = 0
        self.chromosome_length = int(_DEFAULT_SEQUENCE_LENGTH_NT)
        self.chromosome_shape = (self.chromosome_length, ChromosomeStore.DEFAULT_N_COMPARTMENTS)
        self.substrate_wids: list[str] = []
        self.enzyme_wids: list[str] = []
        self.allocation_substrate_wids: list[str] = []
        self._allocation_substrate_indices: list[int] = []
        self.sequence_gc_content = 0.5
        self.reaction_bounds = np.zeros((0, 2), dtype=np.float64)
        self.reaction_small_molecule_stoich = np.zeros((0, 0), dtype=np.float64)
        self.reaction_radiation = np.zeros((0,), dtype=np.int64)
        self.reaction_ids: list[str] = []
        self.reaction_damage_types: list[str] = []
        self.reaction_dna_products = np.zeros((0,), dtype=np.int64)
        self.reaction_vulnerable_motifs: list[object] = []
        self.reaction_vulnerable_motif_types: list[str] = []
        self._load_schema_observables(self.parameters.get("fixture_path", _DEFAULT_FIXTURE_PATH))

        # Rule 8: production never reads a per-tick oracle trace to derive
        # rates. kind_rates_per_s is always exactly the canonical
        # _DEFAULT_KIND_RATES_PER_S baseline or an explicit caller-supplied
        # override via the `kind_rates_per_s` parameter -- never anything
        # loaded from a per-tick Karr trace file.
        configured_rates = self.parameters.get("kind_rates_per_s") or {}
        self.kind_rates_per_s = {
            kind: max(0.0, float(configured_rates.get(kind, _DEFAULT_KIND_RATES_PER_S[kind])))
            for kind in self.damage_kinds
        }
        # Compatibility-only debug/test surface: callers may still pass an
        # explicit kind-rate override, but production firing now comes from
        # the source-faithful per-reaction calcExpectedReactionRates() path.
        self._kind_rate_override_active = "kind_rates_per_s" in raw_parameters and raw_parameters.get(
            "kind_rates_per_s"
        ) is not None

        sequence_length_param = self.parameters.get("sequence_length_nt")
        if sequence_length_param is not None and _is_finite_number(sequence_length_param):
            self.sequence_length_nt = max(1, int(float(sequence_length_param)))
        else:
            self.sequence_length_nt = self._load_sequence_length_from_fixture(
                self.parameters.get("fixture_path", _DEFAULT_FIXTURE_PATH)
            )
        self.sequence_length_nt = min(self.sequence_length_nt, self.chromosome_length)
        self.fork_match_tolerance_nt = max(0, _safe_int(self.parameters.get("fork_match_tolerance_nt"), 0))
        self.enforce_unique_positions = bool(self.parameters.get("enforce_unique_positions", True))

    def _load_schema_observables(self, fixture_path: str | Path) -> None:
        resolved = _resolve_path(fixture_path)
        if not resolved.exists():
            return
        try:
            fixture = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)["data"].fixture
        except Exception:
            return
        substrate_ids = getattr(fixture, "substrateWholeCellModelIDs", None)
        enzyme_ids = getattr(fixture, "enzymeWholeCellModelIDs", None)
        if substrate_ids is not None:
            self.substrate_wids = [str(_coerce_scalar(raw)) for raw in np.asarray(substrate_ids, dtype=object).ravel()]
        if enzyme_ids is not None:
            self.enzyme_wids = [str(_coerce_scalar(raw)) for raw in np.asarray(enzyme_ids, dtype=object).ravel()]
        reaction_bounds = getattr(fixture, "reactionBounds", None)
        reaction_ids = getattr(fixture, "reactionWholeCellModelIDs", None)
        reaction_small_stoich = getattr(fixture, "reactionSmallMoleculeStoichiometryMatrix", None)
        reaction_damage_types = getattr(fixture, "reactionDamageTypes", None)
        reaction_dna_products = getattr(fixture, "reactionDNAProduct", None)
        reaction_radiation = getattr(fixture, "reactionRadiation", None)
        reaction_vulnerable_motifs = getattr(fixture, "reactionVulnerableMotifs", None)
        reaction_vulnerable_motif_types = getattr(fixture, "reactionVulnerableMotifTypes", None)
        if reaction_bounds is not None:
            self.reaction_bounds = np.asarray(reaction_bounds, dtype=np.float64)
        if reaction_ids is not None:
            self.reaction_ids = [str(_coerce_scalar(raw)) for raw in np.asarray(reaction_ids, dtype=object).ravel()]
        if reaction_small_stoich is not None:
            self.reaction_small_molecule_stoich = np.asarray(reaction_small_stoich, dtype=np.float64)
            consumed_idx = np.flatnonzero(
                np.any(self.reaction_small_molecule_stoich < 0.0, axis=1)
            ).tolist()
            self._allocation_substrate_indices = [int(idx) for idx in consumed_idx]
            self.allocation_substrate_wids = [
                self.substrate_wids[int(idx)]
                for idx in consumed_idx
                if 0 <= int(idx) < len(self.substrate_wids)
            ]
        if reaction_damage_types is not None:
            self.reaction_damage_types = [
                str(_coerce_scalar(raw))
                for raw in np.asarray(reaction_damage_types, dtype=object).ravel()
            ]
        if reaction_dna_products is not None:
            self.reaction_dna_products = np.asarray(reaction_dna_products, dtype=np.int64).reshape(-1)
        if reaction_radiation is not None:
            self.reaction_radiation = np.asarray(reaction_radiation, dtype=np.int64).reshape(-1)
        if reaction_vulnerable_motifs is not None:
            self.reaction_vulnerable_motifs = [
                _coerce_scalar(raw) for raw in np.asarray(reaction_vulnerable_motifs, dtype=object).ravel()
            ]
        if reaction_vulnerable_motif_types is not None:
            self.reaction_vulnerable_motif_types = [
                str(_coerce_scalar(raw))
                for raw in np.asarray(reaction_vulnerable_motif_types, dtype=object).ravel()
            ]

        states = np.asarray(getattr(fixture, "states", []), dtype=object).ravel()
        for state in states:
            cls = str(getattr(state, "x_class_", ""))
            if not cls.endswith("Chromosome"):
                continue
            gc = getattr(state, "sequenceGCContent", None)
            if _is_finite_number(gc):
                self.sequence_gc_content = float(gc)
            break

    def ports_schema(self) -> dict[str, Any]:
        chromosome_schema = {
            field: sparse_triplet_schema(self.chromosome_shape, emit=True)
            for field in _SPARSE_DAMAGE_FIELDS
        }
        chromosome_schema.update(
            {
                "damage_events_cumulative": {
                    "_default": [],
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "repair_events_cumulative": {
                    "_default": [],
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "fork_position_bp": {
                    "left": {"_default": None, "_updater": "accumulate", "_emit": False},
                    "right": {"_default": None, "_updater": "accumulate", "_emit": False},
                },
                "replication_stall_flag": {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "replication_state": {
                    "_default": "idle",
                    "_updater": "set",
                    "_emit": False,
                },
            }
        )
        return {
            "chromosome": chromosome_schema,
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
            "requests": {
                self.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self.allocation_substrate_wids
                }
            },
            "substrates_allocated": {
                self.name: {
                    wid: {"_default": 0.0, "_emit": False}
                    for wid in self.allocation_substrate_wids
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])
        self._tick_index += 1
        current_requests = self.calcResourceRequirements_Current(states)
        requests_update = {
            self.name: {
                self.substrate_wids[idx]: float(current_requests[idx])
                for idx in self._allocation_substrate_indices
                if 0 <= int(idx) < len(self.substrate_wids) and int(idx) < current_requests.size
            }
        }
        update: dict[str, Any] = {"requests": requests_update}
        if dt <= 0:
            return update

        chromosome_state = states.get("chromosome", {})
        existing_sites = current_damage_sites(states)
        occupied_positions = _coerce_position_set(existing_sites)
        occupied_positions.update(self._occupied_positions_from_sparse(chromosome_state))
        fork_positions = self._active_fork_positions(chromosome_state)
        sparse_by_field = self._sparse_damage_entries(chromosome_state)
        touched_sparse_fields: set[str] = set()

        new_sites: list[dict[str, Any]] = []
        rates = self.calcExpectedReactionRates(states)
        if self._kind_rate_override_active:
            rates = self._scaled_reaction_rates_from_kind_override(rates)
        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})

        for rxn_idx in self._reaction_order(rates.size):
            lam = max(0.0, float(rates[int(rxn_idx)]) * dt)
            if lam <= 0.0:
                continue

            max_reactions = self._max_reactions_for_reaction(
                int(rxn_idx),
                allocated_state=allocated_state,
                substrates_state=states.get("substrates", {}),
            )
            if max_reactions is not None and max_reactions <= 0:
                continue

            n_events = int(self._rng.poisson(lam))
            if max_reactions is not None:
                n_events = min(n_events, int(max_reactions))
            if n_events <= 0:
                continue

            sampled_coords = self._sample_reaction_coords(
                reaction_index=int(rxn_idx),
                n_events=n_events,
                chromosome_state=chromosome_state,
                sparse_by_field=sparse_by_field,
                occupied_positions=occupied_positions,
            )
            if not sampled_coords:
                continue

            damage_field = self._reaction_damage_field(int(rxn_idx))
            damage_product = self._reaction_damage_product(int(rxn_idx))
            reaction_id = self._reaction_id(int(rxn_idx))
            kind = self._legacy_damage_kind(int(rxn_idx))
            for event_idx, (zero_based_pos, strand) in enumerate(sampled_coords):
                pos = int(zero_based_pos) + 1
                site_id = f"{reaction_id}@{int(pos)}@tick{self._tick_index}@{event_idx}"
                damage = {
                    "id": site_id,
                    "site_id": site_id,
                    "position": int(pos),
                    "kind": str(kind),
                    "reaction_id": reaction_id,
                    "reaction_index": int(rxn_idx),
                    "damage_field": damage_field,
                    "damage_product": damage_product,
                    "age_ticks": 0,
                }
                new_sites.append(damage)
                sparse_key = (int(zero_based_pos), int(strand))
                sparse_by_field[damage_field][sparse_key] = damage_product
                touched_sparse_fields.add(damage_field)
                if self.enforce_unique_positions and self._reaction_uses_sequence_sampling(int(rxn_idx)):
                    occupied_positions.add(int(pos))

        if not new_sites:
            return update

        fork_hit = self._fork_hit(new_sites, fork_positions)
        chromosome_update: dict[str, Any] = {"damage_events_cumulative": new_sites}
        chromosome_update.update(self._sparse_damage_writeback(sparse_by_field, touched_sparse_fields))
        if fork_hit:
            chromosome_update["replication_stall_flag"] = 1.0

        update["chromosome"] = chromosome_update
        return update

    def calcResourceRequirements_Current(self, states: dict[str, Any] | None = None) -> np.ndarray:
        if states is None:
            states = {}
        rates = self.calcExpectedReactionRates(states)
        if self.reaction_small_molecule_stoich.size == 0 or rates.size == 0:
            return np.zeros((len(self.substrate_wids),), dtype=np.float64)
        requirements = np.maximum(
            0.0,
            -self.reaction_small_molecule_stoich @ rates,
        )
        return np.asarray(requirements, dtype=np.float64).reshape(-1)

    def calcExpectedReactionRates(self, states: dict[str, Any] | None = None) -> np.ndarray:
        if states is None:
            states = {}
        if self.reaction_bounds.size == 0:
            return np.zeros((0,), dtype=np.float64)
        n_vulnerable_sites = self.calcNumberVulnerableSites(states)
        rates = np.asarray(n_vulnerable_sites, dtype=np.float64) * self.reaction_bounds[:, 1]
        substrates_state = states.get("substrates", {})
        for rxn_idx, radiation_sub_idx in enumerate(self.reaction_radiation.tolist()):
            if int(radiation_sub_idx) == 0:
                continue
            local_idx = int(radiation_sub_idx) - 1
            if local_idx < 0 or local_idx >= len(self.substrate_wids):
                continue
            wid = self.substrate_wids[local_idx]
            rates[rxn_idx] *= max(0.0, float(substrates_state.get(wid, 0.0)))
        return rates

    def calcNumberVulnerableSites(self, states: dict[str, Any] | None = None) -> np.ndarray:
        if states is None:
            states = {}
        n_reactions = int(self.reaction_bounds.shape[0]) if self.reaction_bounds.ndim >= 2 else 0
        out = np.zeros((n_reactions,), dtype=np.float64)
        if n_reactions <= 0:
            return out

        chromosome_state = states.get("chromosome", {})
        chromosome_store = self._resolve_chromosome_store(chromosome_state)
        polymerized_nt = self._polymerized_nt_count(chromosome_store)
        dntp_composition = np.asarray(
            [
                (1.0 - float(self.sequence_gc_content)) / 2.0,
                float(self.sequence_gc_content) / 2.0,
                float(self.sequence_gc_content) / 2.0,
                (1.0 - float(self.sequence_gc_content)) / 2.0,
            ],
            dtype=np.float64,
        )
        base_to_idx = {"A": 0, "C": 1, "G": 2, "T": 3}

        damaged_sites = self._damaged_sites_value_map(chromosome_store, chromosome_state)
        damaged_coords_by_value: dict[int, set[tuple[int, int]]] = {}
        for coord, value in damaged_sites.items():
            damaged_coords_by_value.setdefault(int(value), set()).add(coord)

        for rxn_idx in range(min(n_reactions, len(self.reaction_vulnerable_motifs))):
            motif = self.reaction_vulnerable_motifs[rxn_idx]
            motif_type = (
                self.reaction_vulnerable_motif_types[rxn_idx]
                if rxn_idx < len(self.reaction_vulnerable_motif_types)
                else ""
            )
            if isinstance(motif, str):
                letters = [base_to_idx[base] for base in motif if base in base_to_idx]
                if not letters:
                    out[rxn_idx] = 0.0
                    continue
                out[rxn_idx] = float(polymerized_nt) * float(np.prod(dntp_composition[letters]))
                continue

            try:
                motif_value = int(motif)
            except (TypeError, ValueError):
                continue
            if not motif_type or not hasattr(chromosome_store, "get_field"):
                continue
            try:
                specific_triplet = chromosome_store.get_field(str(motif_type))
            except KeyError:
                continue
            specific_coords = {
                (int(position), int(strand))
                for position, strand, value in zip(
                    specific_triplet.positions.tolist(),
                    specific_triplet.strands.tolist(),
                    specific_triplet.values.tolist(),
                    strict=False,
                )
                if int(value) == motif_value
            }
            if not specific_coords:
                continue
            damaged_coords = damaged_coords_by_value.get(motif_value, set())
            if not damaged_coords:
                continue
            out[rxn_idx] = float(len(specific_coords & damaged_coords))
        return out

    def expected_events_per_tick(self, timestep: float = 1.0) -> dict[str, float]:
        dt = max(0.0, float(timestep))
        return {kind: float(self.kind_rates_per_s[kind] * dt) for kind in self.damage_kinds}

    def _allocated_or_state(self, allocated_state: dict[str, Any], substrates_state: dict[str, Any], wid: str) -> float:
        if wid in allocated_state:
            return max(0.0, float(allocated_state.get(wid, 0.0)))
        return max(0.0, float(substrates_state.get(wid, 0.0)))

    def _reaction_order(self, n_reactions: int) -> np.ndarray:
        if n_reactions <= 0:
            return np.asarray([], dtype=np.int64)
        permutation = getattr(self._rng, "permutation", None)
        if callable(permutation):
            return np.asarray(permutation(int(n_reactions)), dtype=np.int64).reshape(-1)
        return np.arange(n_reactions, dtype=np.int64)

    def _reaction_id(self, reaction_index: int) -> str:
        if 0 <= int(reaction_index) < len(self.reaction_ids):
            return self.reaction_ids[int(reaction_index)]
        return f"reaction_{int(reaction_index)}"

    def _reaction_damage_field(self, reaction_index: int) -> str:
        if 0 <= int(reaction_index) < len(self.reaction_damage_types):
            field = str(self.reaction_damage_types[int(reaction_index)])
            if field in _SPARSE_DAMAGE_FIELDS:
                return field
        return "damagedBases"

    def _reaction_damage_product(self, reaction_index: int) -> int:
        if 0 <= int(reaction_index) < int(self.reaction_dna_products.size):
            return int(self.reaction_dna_products[int(reaction_index)])
        return 1

    def _legacy_damage_kind(self, reaction_index: int) -> str:
        field = self._reaction_damage_field(reaction_index)
        reaction_id = self._reaction_id(reaction_index)
        radiation_idx = int(self.reaction_radiation[int(reaction_index)]) if int(reaction_index) < self.reaction_radiation.size else 0
        if field == "intrastrandCrossLinks":
            return "uv_like"
        if "BaseLoss" in reaction_id or field == "abasicSites":
            return "depurination"
        if radiation_idx != 0 or field in {"strandBreaks", "damagedSugarPhosphates"}:
            return "oxidative"
        if "BaseDeamination" in reaction_id or field == "damagedBases":
            return "alkylation"
        return "oxidative"

    def _scaled_reaction_rates_from_kind_override(self, rates: np.ndarray) -> np.ndarray:
        scaled = np.asarray(rates, dtype=np.float64).copy()
        if scaled.size == 0:
            return scaled
        for kind in self.damage_kinds:
            idxs = [idx for idx in range(scaled.size) if self._legacy_damage_kind(idx) == kind]
            if not idxs:
                continue
            baseline = float(np.sum(scaled[idxs]))
            target = max(0.0, float(self.kind_rates_per_s.get(kind, 0.0)))
            if baseline <= 0.0:
                scaled[idxs] = 0.0
                continue
            scaled[idxs] *= target / baseline
        return scaled

    def _max_reactions_for_reaction(
        self,
        reaction_index: int,
        *,
        allocated_state: dict[str, Any],
        substrates_state: dict[str, Any],
    ) -> int | None:
        if self.reaction_small_molecule_stoich.size == 0:
            return None
        if reaction_index < 0 or reaction_index >= self.reaction_small_molecule_stoich.shape[1]:
            return None
        stoich = np.asarray(self.reaction_small_molecule_stoich[:, int(reaction_index)], dtype=np.float64).reshape(-1)
        denom = np.abs(np.maximum(0.0, -stoich))
        active = denom > 0.0
        if not np.any(active):
            return None
        ratios: list[float] = []
        for sub_idx in np.flatnonzero(active).tolist():
            if sub_idx < 0 or sub_idx >= len(self.substrate_wids):
                return 0
            wid = self.substrate_wids[int(sub_idx)]
            available = self._allocated_or_state(allocated_state, substrates_state, wid)
            ratios.append(available / float(denom[int(sub_idx)]))
        if not ratios:
            return None
        return max(0, int(np.floor(min(ratios))))

    def _reaction_uses_sequence_sampling(self, reaction_index: int) -> bool:
        if reaction_index < 0 or reaction_index >= len(self.reaction_vulnerable_motifs):
            return True
        return isinstance(self.reaction_vulnerable_motifs[int(reaction_index)], str)

    def _sample_reaction_coords(
        self,
        *,
        reaction_index: int,
        n_events: int,
        chromosome_state: dict[str, Any],
        sparse_by_field: dict[str, dict[tuple[int, int], int]],
        occupied_positions: set[int],
    ) -> list[tuple[int, int]]:
        if n_events <= 0:
            return []

        motif = self.reaction_vulnerable_motifs[int(reaction_index)] if reaction_index < len(self.reaction_vulnerable_motifs) else ""
        if not isinstance(motif, str):
            candidates = self._reaction_candidate_coords(chromosome_state, reaction_index)
            if not candidates:
                return []
            order = self._reaction_order(len(candidates)).tolist()
            limit = min(int(n_events), len(candidates))
            return [candidates[int(order[idx])] for idx in range(limit)]

        sampled_positions = self._sample_positions(
            n_events=n_events,
            occupied_positions=occupied_positions,
        )
        if sampled_positions.size <= 0:
            return []
        strands = np.asarray(
            self._rng.integers(0, self.chromosome_shape[1], size=sampled_positions.size, dtype=np.int64),
            dtype=np.int64,
        ).reshape(-1)
        out: list[tuple[int, int]] = []
        for pos, strand in zip(sampled_positions.tolist(), strands.tolist(), strict=False):
            out.append((int(pos) - 1, int(strand)))
        return out

    def _reaction_candidate_coords(
        self,
        chromosome_state: dict[str, Any],
        reaction_index: int,
    ) -> list[tuple[int, int]]:
        if reaction_index < 0 or reaction_index >= len(self.reaction_vulnerable_motifs):
            return []
        motif = self.reaction_vulnerable_motifs[int(reaction_index)]
        motif_type = (
            self.reaction_vulnerable_motif_types[int(reaction_index)]
            if reaction_index < len(self.reaction_vulnerable_motif_types)
            else ""
        )
        try:
            motif_value = int(motif)
        except (TypeError, ValueError):
            return []
        if not motif_type:
            return []

        store = self._resolve_chromosome_store(chromosome_state)
        try:
            specific_triplet = store.get_field(str(motif_type))
        except KeyError:
            return []
        damaged_sites = self._damaged_sites_value_map(store, chromosome_state)
        damaged_coords = {
            coord for coord, value in damaged_sites.items() if int(value) == motif_value
        }
        if not damaged_coords:
            return []

        candidates: list[tuple[int, int]] = []
        for position, strand, value in zip(
            specific_triplet.positions.tolist(),
            specific_triplet.strands.tolist(),
            specific_triplet.values.tolist(),
            strict=False,
        ):
            coord = (int(position), int(strand))
            if int(value) == motif_value and coord in damaged_coords:
                candidates.append(coord)
        return candidates

    def _polymerized_nt_count(self, chromosome_store: ChromosomeStore) -> float:
        try:
            polymerized = chromosome_store.get_field("polymerizedRegions")
        except KeyError:
            polymerized = SparseTriplet.empty(*self.chromosome_shape)
        total = float(np.sum(np.asarray(polymerized.values, dtype=np.float64)))
        if total > 0.0:
            return total
        return float(2 * self.sequence_length_nt)

    def _damaged_sites_value_map(
        self,
        chromosome_store: ChromosomeStore,
        chromosome_state: dict[str, Any],
    ) -> dict[tuple[int, int], int]:
        m6ad_coords = self._rm_m6ad_coords(chromosome_state)
        combined: dict[tuple[int, int], int] = {}
        for field_name in (
            "damagedBases",
            "gapSites",
            "abasicSites",
            "damagedSugarPhosphates",
            "intrastrandCrossLinks",
            "strandBreaks",
            "hollidayJunctions",
        ):
            triplet = chromosome_store.get_field(field_name)
            for position, strand, value in zip(
                triplet.positions.tolist(),
                triplet.strands.tolist(),
                triplet.values.tolist(),
                strict=False,
            ):
                coord = (int(position), int(strand))
                if field_name == "damagedBases" and coord in m6ad_coords:
                    continue
                combined[coord] = int(combined.get(coord, 0) + int(value))
        return combined

    def _rm_m6ad_coords(self, chromosome_state: dict[str, Any]) -> set[tuple[int, int]]:
        raw = chromosome_state.get("m6ADMethylatedSites")
        if not isinstance(raw, dict):
            return set()
        triplet = SparseTriplet.from_state(raw, shape=self.chromosome_shape)
        return {
            (int(position), int(strand))
            for position, strand in zip(
                triplet.positions.tolist(),
                triplet.strands.tolist(),
                strict=False,
            )
        }

    def _sample_positions(self, n_events: int, occupied_positions: set[int]) -> np.ndarray:
        if n_events <= 0:
            return np.asarray([], dtype=np.int64)

        target = int(n_events)
        if self.enforce_unique_positions:
            free_capacity = max(0, self.sequence_length_nt - len(occupied_positions))
            target = min(target, free_capacity)
            if target <= 0:
                return np.asarray([], dtype=np.int64)
        else:
            return self._rng.integers(1, self.sequence_length_nt + 1, size=target, dtype=np.int64)

        # Typical event counts are small; rejection sampling is sufficient here.
        out: list[int] = []
        used = set(int(v) for v in occupied_positions)
        max_attempts = max(64, target * 10)
        attempts = 0
        while len(out) < target and attempts < max_attempts:
            remaining = target - len(out)
            draws = self._rng.integers(1, self.sequence_length_nt + 1, size=remaining, dtype=np.int64)
            for draw in draws:
                pos = int(draw)
                if pos in used:
                    continue
                used.add(pos)
                out.append(pos)
                if len(out) >= target:
                    break
            attempts += remaining

        if len(out) < target:
            # Deterministic fill to guarantee monotone append semantics.
            for pos in range(1, self.sequence_length_nt + 1):
                if pos in used:
                    continue
                out.append(pos)
                used.add(pos)
                if len(out) >= target:
                    break

        return np.asarray(out, dtype=np.int64)

    def _active_fork_positions(self, chromosome_state: dict[str, Any]) -> set[int]:
        replication_state = str(chromosome_state.get("replication_state", "idle"))
        if replication_state in {"idle", "initiating", "complete"}:
            return set()

        raw = chromosome_state.get("fork_position_bp", {})
        if isinstance(raw, dict):
            candidates: list[object] = [raw.get("left"), raw.get("right")]
        else:
            candidates = [None, None]

        out: set[int] = set()
        for value in candidates:
            if not _is_finite_number(value):
                continue
            pos = int(round(float(value)))
            if 1 <= pos <= self.sequence_length_nt:
                out.add(pos)
        return out

    def _fork_hit(self, new_sites: list[dict[str, Any]], fork_positions: set[int]) -> bool:
        if not fork_positions:
            return False
        tolerance = int(self.fork_match_tolerance_nt)
        if tolerance <= 0:
            return any(int(site["position"]) in fork_positions for site in new_sites)

        for site in new_sites:
            pos = int(site["position"])
            for fork_pos in fork_positions:
                if abs(pos - fork_pos) <= tolerance:
                    return True
        return False

    def _resolve_chromosome_store(self, chrom_state: dict[str, Any]) -> ChromosomeStore:
        return ChromosomeStore.from_state_mapping(chrom_state, shape=self.chromosome_shape)

    def _occupied_positions_from_sparse(self, chrom_state: dict[str, Any]) -> set[int]:
        store = self._resolve_chromosome_store(chrom_state)
        occupied: set[int] = set()
        for field_name in _SPARSE_DAMAGE_FIELDS:
            triplet = store.get_field(field_name)
            for position in triplet.positions.tolist():
                pos = int(position) + 1
                if 1 <= pos <= self.sequence_length_nt:
                    occupied.add(pos)
        return occupied

    def _sparse_damage_entries(self, chrom_state: dict[str, Any]) -> dict[str, dict[tuple[int, int], int]]:
        store = self._resolve_chromosome_store(chrom_state)
        by_field: dict[str, dict[tuple[int, int], int]] = {}
        for field_name in _SPARSE_DAMAGE_FIELDS:
            triplet = store.get_field(field_name)
            by_field[field_name] = {
                (int(position), int(strand)): int(value)
                for position, strand, value in zip(
                    triplet.positions.tolist(),
                    triplet.strands.tolist(),
                    triplet.values.tolist(),
                    strict=False,
                )
                if int(value) != 0
            }
        return by_field

    def _sparse_damage_writeback(
        self,
        by_field: dict[str, dict[tuple[int, int], int]],
        touched_fields: set[str],
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for field_name in sorted(touched_fields):
            entries = sorted(by_field[field_name].items(), key=lambda item: (item[0][0], item[0][1]))
            if entries:
                positions = np.asarray([coord[0] for coord, _ in entries], dtype=np.int64)
                strands = np.asarray([coord[1] for coord, _ in entries], dtype=np.int64)
                values = np.asarray([value for _, value in entries], dtype=np.int64)
            else:
                positions = np.array([], dtype=np.int64)
                strands = np.array([], dtype=np.int64)
                values = np.array([], dtype=np.int64)
            out[field_name] = SparseTriplet(
                positions=positions,
                strands=strands,
                values=values,
                shape=self.chromosome_shape,
            ).to_state()
        return out

    def _load_sequence_length_from_fixture(self, fixture_path: str | Path) -> int:
        resolved = _resolve_path(fixture_path)
        if not resolved.exists():
            return _DEFAULT_SEQUENCE_LENGTH_NT

        try:
            fixture = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)["data"].fixture
            states = np.asarray(getattr(fixture, "states", []), dtype=object).ravel()
            for state in states:
                cls = str(getattr(state, "x_class_", ""))
                if cls.endswith("Chromosome"):
                    seq_len = _safe_int(getattr(state, "sequenceLen", 0), 0)
                    if seq_len > 0:
                        return seq_len
        except Exception:
            return _DEFAULT_SEQUENCE_LENGTH_NT

        return _DEFAULT_SEQUENCE_LENGTH_NT


__all__ = ["KarrDNADamageProcess"]
