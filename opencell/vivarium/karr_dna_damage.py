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
# Chromosome state's own per-process-style fixture. Carries the WholeCellKB
# monomer/complex DNA-footprint arrays (`monomerDNAFootprints`,
# `complexDNAFootprints`) that Karr's Chromosome.m::sampleAccessibleSites
# subtracts from `nAccessibleSites`. Not part of DNADamage's own fixture --
# DNADamage.m never touches these arrays directly, it delegates to
# `this.chromosome.setSiteDamaged`, which lives on the Chromosome state.
_DEFAULT_CHROMOSOME_FIXTURE_PATH = "data/karr_fixtures/per_process/Chromosome_flat.mat"
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
        "chromosome_fixture_path": _DEFAULT_CHROMOSOME_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "sequence_length_nt": None,
        "enforce_unique_positions": True,
        "fork_match_tolerance_nt": 0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
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
        self.monomer_dna_footprints = np.zeros((0,), dtype=np.float64)
        self.complex_dna_footprints = np.zeros((0,), dtype=np.float64)
        self._load_schema_observables(self.parameters.get("fixture_path", _DEFAULT_FIXTURE_PATH))
        self._load_footprint_fixture(
            self.parameters.get("chromosome_fixture_path", _DEFAULT_CHROMOSOME_FIXTURE_PATH)
        )

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

    def _load_footprint_fixture(self, fixture_path: str | Path) -> None:
        """Load WholeCellKB monomer/complex DNA-footprint arrays.

        Karr source: Chromosome.m::sampleAccessibleSites subtracts
        ``sum(this.monomerDNAFootprints(boundMonomers, 1))`` and
        ``sum(this.complexDNAFootprints(boundComplexs, 1))`` from
        ``nAccessibleSites``. These arrays are indexed by the 1-based global
        monomer/complex index stored as the *value* of each
        ``monomerBoundSites``/``complexBoundSites`` sparse entry; index i
        (0-based, ``value - 1``) here holds the footprint (nt) for global
        species index ``value``. Fail closed (empty arrays -> zero
        contribution, not fabricated data) if the fixture is unavailable.
        """
        resolved = _resolve_path(fixture_path)
        if not resolved.exists():
            return
        try:
            fixture = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)["data"].fixture
        except Exception:
            return
        monomer_footprints = getattr(fixture, "monomerDNAFootprints", None)
        complex_footprints = getattr(fixture, "complexDNAFootprints", None)
        if monomer_footprints is not None:
            self.monomer_dna_footprints = np.asarray(monomer_footprints, dtype=np.float64).reshape(-1)
        if complex_footprints is not None:
            self.complex_dna_footprints = np.asarray(complex_footprints, dtype=np.float64).reshape(-1)

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
        chromosome_store = self._resolve_chromosome_store(chromosome_state)
        existing_sites = current_damage_sites(states)
        occupied_positions = _coerce_position_set(existing_sites)
        occupied_positions.update(self._occupied_positions_from_sparse(chromosome_state))
        occupied_positions.update(self._footprint_occupied_positions(chromosome_store))
        fork_positions = self._active_fork_positions(chromosome_state)
        sparse_by_field = self._sparse_damage_entries(chromosome_state)
        touched_sparse_fields: set[str] = set()

        # Literal Karr DNADamage.m::evolveState per-reaction loop. Firing is
        # never derived from calcExpectedReactionRates()/
        # calcNumberVulnerableSites() (those exist solely for
        # calcResourceRequirements_Current above, matching Karr's own
        # split); each reaction gets its own stepSizeSec*reactionBounds(:,2)
        # selectionProbability, gated by a random-order maxReactions cap
        # read from a same-tick-mutable substrate pool (substrate
        # writeback, Karr line: `substrates = substrates + numDamaged *
        # reactionSmallMoleculeStoichiometryMatrix(:,j)`).
        n_accessible_sites = self._n_accessible_sites(chromosome_store, chromosome_state)
        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        substrates_state = states.get("substrates", {})
        working_substrates: dict[str, float] = {
            wid: self._allocated_or_state(allocated_state, substrates_state, wid) for wid in self.substrate_wids
        }
        substrate_deltas: dict[str, float] = {}

        new_sites: list[dict[str, Any]] = []
        n_reactions = int(self.reaction_bounds.shape[0]) if self.reaction_bounds.ndim >= 2 else 0

        for rxn_idx in self._reaction_order(n_reactions):
            rxn_idx = int(rxn_idx)

            max_reactions = self._max_reactions_for_reaction(rxn_idx, working_substrates=working_substrates)
            if max_reactions is not None and max_reactions <= 0:
                continue

            selection_probability = self._selection_probability(rxn_idx, dt, working_substrates)
            if selection_probability <= 0.0:
                continue

            sampled_coords = self._sample_reaction_coords(
                reaction_index=rxn_idx,
                max_reactions=max_reactions,
                selection_probability=selection_probability,
                n_accessible_sites=n_accessible_sites,
                chromosome_state=chromosome_state,
                sparse_by_field=sparse_by_field,
                occupied_positions=occupied_positions,
            )
            if not sampled_coords:
                continue

            damage_field = self._reaction_damage_field(rxn_idx)
            damage_product = self._reaction_damage_product(rxn_idx)
            reaction_id = self._reaction_id(rxn_idx)
            kind = self._legacy_damage_kind(rxn_idx)
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
                if self.enforce_unique_positions and self._reaction_uses_sequence_sampling(rxn_idx):
                    occupied_positions.add(int(pos))

            # Substrate writeback (Karr line 543): the small-molecule pool
            # this same reaction consumed/produced feeds every subsequent
            # reaction this tick (working_substrates) AND must be
            # reflected in the real `substrates` port (accumulate updater)
            # so DNADamage's consumption is not silently dropped.
            count = len(sampled_coords)
            if count and self.reaction_small_molecule_stoich.size and rxn_idx < self.reaction_small_molecule_stoich.shape[1]:
                stoich_col = self.reaction_small_molecule_stoich[:, rxn_idx]
                for sub_idx, delta in enumerate(stoich_col.tolist()):
                    if delta == 0.0 or sub_idx >= len(self.substrate_wids):
                        continue
                    wid = self.substrate_wids[sub_idx]
                    contribution = count * float(delta)
                    working_substrates[wid] = working_substrates.get(wid, 0.0) + contribution
                    substrate_deltas[wid] = substrate_deltas.get(wid, 0.0) + contribution

        if substrate_deltas:
            update["substrates"] = {wid: delta for wid, delta in substrate_deltas.items() if delta != 0.0}

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
        # Fail-closed (item 6): an unknown/out-of-range reaction damage
        # type is a corrupt-fixture or programming error, never silently
        # routed to a plausible-looking default field.
        if reaction_index < 0 or reaction_index >= len(self.reaction_damage_types):
            raise ValueError(
                f"DNADamage reaction index {reaction_index} has no reactionDamageTypes "
                "entry (fail-closed: refusing to guess a damage field)"
            )
        field = str(self.reaction_damage_types[int(reaction_index)])
        if field not in _SPARSE_DAMAGE_FIELDS:
            raise ValueError(
                f"DNADamage reaction index {reaction_index} damage field {field!r} is not "
                "a known sparse chromosome field (fail-closed: refusing to guess a damage field)"
            )
        return field

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

    def _stochastic_round(self, value: float) -> int:
        """Karr `randStream.stochasticRound`: floor(value) + Bernoulli(frac)."""
        if value <= 0.0:
            return 0
        base = int(np.floor(value))
        frac = float(value - base)
        if frac <= 0.0:
            return base
        return base + int(self._rng.random() < frac)

    def _selection_probability(
        self,
        reaction_index: int,
        dt: float,
        working_substrates: dict[str, float],
    ) -> float:
        """Literal Karr DNADamage.m::evolveState selectionProbability.

        `selectionProbability = stepSizeSec * reactionBounds(j,2)`, scaled
        by the radiation-dose substrate level when `reactionRadiation(j) ~=
        0`. This never reads calcExpectedReactionRates()/
        calcNumberVulnerableSites() -- those are a distinct Karr code path
        used only for FBA resource-request bookkeeping.
        """
        if self.reaction_bounds.ndim < 2 or reaction_index < 0 or reaction_index >= self.reaction_bounds.shape[0]:
            return 0.0
        prob = float(dt) * float(self.reaction_bounds[int(reaction_index), 1])
        if prob == 0.0:
            return 0.0
        radiation_idx = (
            int(self.reaction_radiation[int(reaction_index)]) if reaction_index < self.reaction_radiation.size else 0
        )
        if radiation_idx != 0:
            local_idx = radiation_idx - 1
            if local_idx < 0 or local_idx >= len(self.substrate_wids):
                return 0.0
            wid = self.substrate_wids[local_idx]
            prob *= max(0.0, float(working_substrates.get(wid, 0.0)))
        return max(0.0, prob)

    def _n_accessible_sites(
        self,
        chromosome_store: ChromosomeStore,
        chromosome_state: dict[str, Any],
    ) -> float:
        """Literal Karr Chromosome.m::sampleAccessibleSites nAccessibleSites.

        `nAccessibleSites = collapse(polymerizedRegions)
        - sum(monomerDNAFootprints(boundMonomers))
        - sum(complexDNAFootprints(boundComplexs)) - nnz(damagedSites)`.
        """
        polymerized_nt = self._polymerized_nt_count(chromosome_store)
        monomer_footprint_sum = self._bound_footprint_sum(
            chromosome_store, "monomerBoundSites", self.monomer_dna_footprints
        )
        complex_footprint_sum = self._bound_footprint_sum(
            chromosome_store, "complexBoundSites", self.complex_dna_footprints
        )
        damaged_nnz = float(len(self._damaged_sites_value_map(chromosome_store, chromosome_state)))
        return max(0.0, polymerized_nt - monomer_footprint_sum - complex_footprint_sum - damaged_nnz)

    def _bound_footprint_sum(
        self,
        chromosome_store: ChromosomeStore,
        field_name: str,
        footprint_table: np.ndarray,
    ) -> float:
        if footprint_table.size == 0:
            return 0.0
        try:
            triplet = chromosome_store.get_field(field_name)
        except KeyError:
            return 0.0
        n = int(footprint_table.size)
        total = 0.0
        for value in triplet.values.tolist():
            idx = int(value) - 1
            if 0 <= idx < n:
                total += float(footprint_table[idx])
        return total

    def _footprint_occupied_positions(self, chromosome_store: ChromosomeStore) -> set[int]:
        """Positions occluded by bound-protein DNA footprints.

        Documented scope narrowing: Karr's `isRegionAccessible` occludes an
        asymmetric 5'/3' window keyed by strand direction and footprint
        binding-strandedness; here we mark a footprint-width window
        downstream of the bound anchor position on both strands (a
        strand-agnostic, coarser-than-Karr exclusion -- rejects at least as
        many candidate sites as the literal formula, never fewer), matching
        the same strand-agnostic convention `_occupied_positions_from_sparse`
        already uses for existing-damage exclusion.
        """
        occupied: set[int] = set()
        if self.sequence_length_nt <= 0:
            return occupied
        for field_name, footprint_table in (
            ("monomerBoundSites", self.monomer_dna_footprints),
            ("complexBoundSites", self.complex_dna_footprints),
        ):
            if footprint_table.size == 0:
                continue
            try:
                triplet = chromosome_store.get_field(field_name)
            except KeyError:
                continue
            n = int(footprint_table.size)
            for position, value in zip(triplet.positions.tolist(), triplet.values.tolist(), strict=False):
                idx = int(value) - 1
                if not (0 <= idx < n):
                    continue
                footprint = int(footprint_table[idx])
                if footprint <= 0:
                    continue
                start = int(position) + 1
                for offset in range(footprint):
                    pos = ((start + offset - 1) % self.sequence_length_nt) + 1
                    occupied.add(pos)
        return occupied

    def _max_reactions_for_reaction(
        self,
        reaction_index: int,
        *,
        working_substrates: dict[str, float],
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
            available = max(0.0, float(working_substrates.get(wid, 0.0)))
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
        max_reactions: int | None,
        selection_probability: float,
        n_accessible_sites: float,
        chromosome_state: dict[str, Any],
        sparse_by_field: dict[str, dict[tuple[int, int], int]],
        occupied_positions: set[int],
    ) -> list[tuple[int, int]]:
        if selection_probability <= 0.0:
            return []
        if max_reactions is not None and max_reactions <= 0:
            return []

        motif = self.reaction_vulnerable_motifs[int(reaction_index)] if reaction_index < len(self.reaction_vulnerable_motifs) else ""
        if not isinstance(motif, str):
            # Karr Chromosome.m::setSiteDamaged non-string branch:
            # `maxDamages = min(maxDamages, stochasticRound(nCandidates * probDamage))`
            candidates = self._reaction_candidate_coords(chromosome_state, reaction_index)
            if not candidates:
                return []
            n_sites = self._stochastic_round(len(candidates) * selection_probability)
            if max_reactions is not None:
                n_sites = min(n_sites, int(max_reactions))
            if n_sites <= 0:
                return []
            order = self._reaction_order(len(candidates)).tolist()
            limit = min(n_sites, len(candidates))
            return [candidates[int(order[idx])] for idx in range(limit)]

        # Karr Chromosome.m::sampleAccessibleSites string-motif branch:
        # `nGC = sum(seq=='G'|seq=='C')`;
        # `nSites = min(nSites, stochasticRound(nAccessibleSites * prob *
        #  (gc/2)^nGC * ((1-gc)/2)^(seqLen-nGC)))`.
        gc = float(self.sequence_gc_content)
        # Karr: `nGC = sum(seq=='G'|seq=='C')`; the complement exponent is
        # `seqLen - nGC`, not an explicit A/T count, so any non-G/C
        # character in the motif (there are none in practice, but this
        # matches the literal formula for any input) falls in that bucket.
        n_gc = sum(1 for base in motif if base in ("G", "C"))
        n_complement = len(motif) - n_gc
        gc_term = (gc / 2.0) ** n_gc * ((1.0 - gc) / 2.0) ** n_complement
        n_sites = self._stochastic_round(n_accessible_sites * selection_probability * gc_term)
        if max_reactions is not None:
            n_sites = min(n_sites, int(max_reactions))
        if n_sites <= 0:
            return []

        sampled_positions = self._sample_positions(
            n_events=n_sites,
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
