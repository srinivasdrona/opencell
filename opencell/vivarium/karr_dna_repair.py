"""Vivarium Process port of Karr DNARepair with Karr-light pathway aggregation.

Karr-light v1 scope:
- Repair queued damage sites by pathway (BER, NER, HR, NHEJ-like fallback).
- Bound repair throughput by fixture-derived enzyme kinetics.
- Consume ATP + dNTP pools via KarrAllocationStep request/allocation contract.

Deferred to v2:
- Full per-base chromosome state transitions across all DNA damage arrays.
- DisA binding dynamics and restriction/modification mechanics.
- Complete small-molecule stoichiometry beyond ATP + dNTP aggregate budgets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet, sparse_triplet_schema
from opencell.vivarium.chromosome_views import current_damage_sites

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/DNARepair_flat.mat"
_D2_COMPLEX_FIXTURE_PATH = "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"

_PATHWAYS = ("ber", "ner", "hr", "nhej_like")
_DAMAGE_FIELDS = (
    "damagedBases",
    "strandBreaks",
    "gapSites",
    "abasicSites",
    "damagedSugarPhosphates",
)
_RM_DERIVED_FIELDS = (
    "m6ADMethylatedSites",
    "hemiunmethylatedMunIRMSites",
    "restrictableMunIRMSites",
)

_DAMAGE_TYPE_ALIASES: dict[str, str] = {
    "abasic": "abasic_site",
    "abasicsite": "abasic_site",
    "abasic_site": "abasic_site",
    "ap_site": "abasic_site",
    "damagedbase": "damaged_base",
    "damaged_base": "damaged_base",
    "base_damage": "damaged_base",
    "intrastrandcrosslink": "intrastrand_crosslink",
    "intrastrand_crosslink": "intrastrand_crosslink",
    "crosslink": "intrastrand_crosslink",
    "single_strand_break": "single_strand_break",
    "single_strandbreak": "single_strand_break",
    "strand_break": "single_strand_break",
    "ssb": "single_strand_break",
    "double_strand_break": "double_strand_break",
    "double_strandbreak": "double_strand_break",
    "dsb": "double_strand_break",
}


@dataclass(frozen=True)
class _DamageSite:
    site_id: str
    damage_type: str
    payload: dict[str, Any]


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


def _coerce_scalar(value: object) -> object:
    out = value
    while isinstance(out, np.ndarray):
        if out.size == 0:
            return 0
        out = out.flat[0]
    return out


def _parse_wid_array(value: object) -> list[str]:
    arr = np.asarray(value, dtype=object)
    out: list[str] = []
    for raw in arr.ravel():
        out.append(str(_coerce_scalar(raw)))
    return out


@lru_cache(maxsize=1)
def _canonical_complex_wids() -> frozenset[str]:
    resolved = _resolve_path(_D2_COMPLEX_FIXTURE_PATH)
    mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
    fx = mat["data"].fixture
    return frozenset(_parse_wid_array(fx.complexWholeCellModelIDs))


def _parse_index_array(value: object) -> np.ndarray:
    raw = np.asarray(value)
    while raw.dtype == object and raw.size == 1 and isinstance(raw.flat[0], np.ndarray):
        raw = np.asarray(raw.flat[0])
    return np.asarray(raw, dtype=np.int64).reshape(-1)


def _normalize_damage_type(raw: object) -> str:
    key = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    key = key.replace("__", "_")
    return _DAMAGE_TYPE_ALIASES.get(key, key)


def _normalize_dntp_split(raw: object | None) -> np.ndarray:
    if raw is None:
        return np.full(4, 0.25, dtype=np.float64)
    arr = np.asarray(raw, dtype=np.float64).reshape(-1)
    if arr.size != 4:
        raise ValueError(f"dntp_split must have exactly 4 entries, got {arr.size}")
    arr = np.clip(arr, a_min=0.0, a_max=None)
    total = float(np.sum(arr))
    if total <= 0.0:
        return np.full(4, 0.25, dtype=np.float64)
    return arr / total


def _split_circular_region(start: int, length: int, sequence_len: int) -> list[tuple[int, int]]:
    if length <= 0:
        return []
    start = int(start) % sequence_len
    length = int(length)
    if length >= sequence_len:
        return [(0, sequence_len - 1)]
    end = start + length - 1
    if end < sequence_len:
        return [(start, end)]
    return [
        (start, sequence_len - 1),
        (0, end % sequence_len),
    ]


class KarrDNARepairProcess(Process):
    """Karr DNARepair (light) with pathway-level aggregate repair events."""

    name = "karr_dna_repair"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "chromosome_length_bp": float(ChromosomeStore.DEFAULT_SEQUENCE_LEN),
        "pathway_rate_scale": 1.0,
        "ber_patch_length_nt": 1.0,
        "nhej_patch_length_nt": 1.0,
        "dntp_split": (0.25, 0.25, 0.25, 0.25),
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self.chromosome_length = int(round(float(self.parameters["chromosome_length_bp"])))
        self.chromosome_shape = (self.chromosome_length, ChromosomeStore.DEFAULT_N_COMPARTMENTS)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))
        self._rm_rng = np.random.default_rng(int(self.parameters["rng_seed"]) + 18017)

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.substrate_wids = _parse_wid_array(fx.substrateWholeCellModelIDs)
        self.enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)
        self.reaction_wids = _parse_wid_array(fx.reactionWholeCellModelIDs)

        self.reaction_small_molecule_stoich = np.asarray(
            fx.reactionSmallMoleculeStoichiometryMatrix,
            dtype=np.float64,
        )
        self.reaction_catalysis = np.asarray(fx.reactionCatalysisMatrix, dtype=np.float64)
        self.reaction_ub = np.asarray(fx.enzymeBounds, dtype=np.float64)[:, 1]

        if self.reaction_catalysis.shape[0] != len(self.reaction_wids):
            raise ValueError(
                "DNARepair reactionCatalysis row mismatch: "
                f"{self.reaction_catalysis.shape[0]} vs {len(self.reaction_wids)}"
            )
        if self.reaction_catalysis.shape[1] != len(self.enzyme_wids):
            raise ValueError(
                "DNARepair reactionCatalysis column mismatch: "
                f"{self.reaction_catalysis.shape[1]} vs {len(self.enzyme_wids)}"
            )
        if self.reaction_small_molecule_stoich.shape[0] != len(self.substrate_wids):
            raise ValueError(
                "DNARepair stoichiometry substrate mismatch: "
                f"{self.reaction_small_molecule_stoich.shape[0]} vs {len(self.substrate_wids)}"
            )
        if self.reaction_small_molecule_stoich.shape[1] != len(self.reaction_wids):
            raise ValueError(
                "DNARepair stoichiometry reaction mismatch: "
                f"{self.reaction_small_molecule_stoich.shape[1]} vs {len(self.reaction_wids)}"
            )

        self.enzyme_defaults = {
            wid: float(max(0.0, cnt))
            for wid, cnt in zip(
                self.enzyme_wids,
                np.asarray(fx.enzymes, dtype=np.float64).reshape(-1),
                strict=False,
            )
        }
        canonical_complex_wids = _canonical_complex_wids()
        self.complex_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid in canonical_complex_wids
        ]
        self.protein_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid not in canonical_complex_wids
        ]

        self.pathway_reaction_indices: dict[str, np.ndarray] = {
            "ber": _parse_index_array(fx.reactionIndexs_BER) - 1,
            "ner": _parse_index_array(fx.reactionIndexs_NER) - 1,
            "hr": _parse_index_array(fx.reactionIndexs_HR_dsbr) - 1,
            # NHEJ-like fallback uses ligation machinery as an aggregate proxy.
            "nhej_like": _parse_index_array(fx.reactionIndexs_ligation) - 1,
        }
        for pathway, rxn_idx in self.pathway_reaction_indices.items():
            if rxn_idx.size == 0:
                raise ValueError(f"DNARepair pathway {pathway} has no mapped reactions")
        self._rm_muni_methylation_idx = self.reaction_wids.index("DNA_RM_MunI_Methylation")
        self._rm_muni_restriction_idx = self.reaction_wids.index("DNA_RM_MunI_Restriction")
        self._rm_typeii_enzyme_idx = int(_coerce_scalar(fx.enzymeIndexs_RM_typeII)) - 1
        self._rm_typeii_enzyme_wid = self.enzyme_wids[self._rm_typeii_enzyme_idx]
        self._disa_enzyme_idx = int(_coerce_scalar(fx.enzymeIndexs_DisA)) - 1
        self._disa_enzyme_wid = self.enzyme_wids[self._disa_enzyme_idx]
        self._disa_dna_footprint = int(
            max(
                1,
                int(
                    np.asarray(fx.enzymeDNAFootprints, dtype=np.int64).reshape(-1)[
                        self._disa_enzyme_idx
                    ]
                ),
            )
        )
        self._substrate_global_indices = _parse_index_array(fx.substrateGlobalIndexs)
        self._m6ad_local_idx = int(_coerce_scalar(fx.substrateIndexs_m6AD)) - 1
        self._m6ad_global_index = int(self._substrate_global_indices[self._m6ad_local_idx])
        self._rm_muni_sites = (np.asarray(fx.RM_MunI_RecognitionSites, dtype=np.int64) - 1) % max(
            1,
            self.chromosome_length,
        )
        self._rm_muni_methylated_positions = (
            _parse_index_array(fx.RM_MunI_MethylatedPositions) - 1
        ).astype(np.int64)
        self._rm_muni_restriction_positions = (
            _parse_index_array(fx.RM_MunI_RestrictionPositions) - 1
        ).astype(np.int64)
        if self._rm_muni_methylated_positions.size != 2:
            raise ValueError(
                "DNARepair expected 2 MunI methylated positions, got "
                f"{self._rm_muni_methylated_positions.size}"
            )
        if self._rm_muni_restriction_positions.size != 2:
            raise ValueError(
                "DNARepair expected 2 MunI restriction positions, got "
                f"{self._rm_muni_restriction_positions.size}"
            )

        if "ATP" not in self.substrate_wids:
            raise ValueError("DNARepair fixture missing ATP substrate")
        self.atp_wid = "ATP"
        self.atp_index = self.substrate_wids.index(self.atp_wid)

        self.dntp_indices = (_parse_index_array(fx.substrateIndexs_dNTPs) - 1).astype(np.int64)
        if self.dntp_indices.size != 4:
            raise ValueError(f"DNARepair expected 4 dNTP indices, got {self.dntp_indices.size}")
        self.dntp_wids = [self.substrate_wids[int(idx)] for idx in self.dntp_indices]

        expected_dntp_wids = {"DATP", "DCTP", "DGTP", "DTTP"}
        if set(self.dntp_wids) != expected_dntp_wids:
            raise ValueError(
                "DNARepair dNTP WIDs mismatch: expected "
                f"{expected_dntp_wids}, got {set(self.dntp_wids)}"
            )

        self.ner_patch_length_nt = float(
            max(
                1.0,
                float(_coerce_scalar(fx.NER_UvrABC_IncisionMargin3))
                + float(_coerce_scalar(fx.NER_UvrABC_IncisionMargin5))
                + 1.0,
            )
        )
        self.hr_patch_length_nt = float(max(1.0, float(_coerce_scalar(fx.HR_PolA_ResectionLength))))
        self.ber_patch_length_nt = float(max(1.0, float(self.parameters["ber_patch_length_nt"])))
        self.nhej_patch_length_nt = float(max(1.0, float(self.parameters["nhej_patch_length_nt"])))

        self.pathway_patch_length_nt = {
            "ber": self.ber_patch_length_nt,
            "ner": self.ner_patch_length_nt,
            "hr": self.hr_patch_length_nt,
            "nhej_like": self.nhej_patch_length_nt,
        }
        self.dntp_split = _normalize_dntp_split(self.parameters.get("dntp_split"))

        self.pathway_atp_cost = {pathway: self._pathway_atp_cost(pathway) for pathway in _PATHWAYS}
        self.tracked_substrates = [self.atp_wid, *self.dntp_wids]
        self.pathway_per_event_substrate_cost = {
            pathway: self._per_event_substrate_cost(pathway) for pathway in _PATHWAYS
        }

    def ports_schema(self) -> dict[str, Any]:
        chromosome_schema = {
            field: sparse_triplet_schema(self.chromosome_shape, emit=(field in set(_DAMAGE_FIELDS)))
            for field in _DAMAGE_FIELDS
        }
        chromosome_schema.update(
            {
                field: sparse_triplet_schema(self.chromosome_shape, emit=True)
                for field in _RM_DERIVED_FIELDS
            }
        )
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
                "repair_count": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
                "repair_count_by_pathway": {
                    pathway: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for pathway in _PATHWAYS
                },
            }
        )
        return {
            "chromosome": chromosome_schema,
            "protein": {
                "counts": {
                    wid: {"_default": self.enzyme_defaults.get(wid, 0.0), "_updater": "accumulate"}
                    for wid in self.protein_enzyme_wids
                }
            },
            "complex": {
                "counts": {
                    wid: {"_default": self.enzyme_defaults.get(wid, 0.0), "_updater": "accumulate"}
                    for wid in self.complex_enzyme_wids
                }
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.tracked_substrates
            },
            "enzymes": {
                wid: {
                    "_default": self.enzyme_defaults.get(wid, 0.0),
                    "_updater": "accumulate",
                    "_emit": False,
                }
                for wid in self.enzyme_wids
            },
            "boundEnzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "requests": {
                self.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self.tracked_substrates
                }
            },
            "substrates_allocated": {
                self.name: {
                    wid: {"_default": 0.0, "_emit": False} for wid in self.tracked_substrates
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])
        chrom_state = states.get("chromosome", {})

        hint = states.get("trace_hint", {})
        hint = hint if isinstance(hint, dict) else {}
        replay_chromosome_next = hint.get("chromosome_next")
        replay_chromosome_next = (
            replay_chromosome_next if isinstance(replay_chromosome_next, dict) else None
        )
        replay_enzymes_next = hint.get("enzymes_next")
        replay_enzymes_next = replay_enzymes_next if isinstance(replay_enzymes_next, dict) else None
        replay_bound_enzymes_next = hint.get("boundEnzymes_next")
        replay_bound_enzymes_next = (
            replay_bound_enzymes_next if isinstance(replay_bound_enzymes_next, dict) else None
        )

        damage_sites = self._damage_sites(chrom_state, states)

        enzyme_counts = self._enzyme_counts(states)
        desired_repairs, indices_by_pathway = self._desired_repairs(
            damage_sites=damage_sites,
            enzyme_counts=enzyme_counts,
            dt=dt,
        )
        requests = self._substrate_needs_for_repairs(desired_repairs)

        allocated = states.get("substrates_allocated", {}).get(self.name, {})
        available = {
            wid: self._allocated_or_state(allocated, wid) for wid in self.tracked_substrates
        }
        actual_repairs = self._bounded_repairs(desired_repairs=desired_repairs, available=available)

        substrate_consumption = self._substrate_needs_for_repairs(actual_repairs)
        consumed_total = int(sum(actual_repairs.values()))
        substrate_delta: dict[str, float] = {}

        update: dict[str, Any] = {
            "requests": {self.name: {wid: float(requests[wid]) for wid in self.tracked_substrates}}
        }

        if any(val > 0.0 for val in substrate_consumption.values()):
            for wid in self.tracked_substrates:
                value = float(substrate_consumption[wid])
                if value > 0.0:
                    substrate_delta[wid] = substrate_delta.get(wid, 0.0) - value

        chromosome_update: dict[str, Any] = {}

        if consumed_total > 0:
            repaired_indices = self._sample_repaired_indices(indices_by_pathway, actual_repairs)
            repair_events = [
                self._repair_event_from_site(damage_sites[idx].payload)
                for idx in sorted(repaired_indices)
            ]
            chromosome_update = {
                "repair_events_cumulative": repair_events,
                "repair_count": float(consumed_total),
                "repair_count_by_pathway": {
                    pathway: float(actual_repairs[pathway])
                    for pathway in _PATHWAYS
                    if actual_repairs[pathway] > 0
                },
            }
            chromosome_sparse_delta = self._chromosome_damage_writeback(
                chrom_state=chrom_state,
                damage_sites=damage_sites,
                repaired_indices=repaired_indices,
            )
            if chromosome_sparse_delta:
                chromosome_update.update(chromosome_sparse_delta)

        rm_chrom_state = dict(chrom_state)
        for field_name in _DAMAGE_FIELDS:
            if field_name in chromosome_update:
                rm_chrom_state[field_name] = chromosome_update[field_name]

        rm_chromosome_update, rm_substrate_delta = self._evolve_state_restriction_modification(
            chrom_state=rm_chrom_state,
            enzyme_counts=enzyme_counts,
            dt=dt,
            substrate_state=states.get("substrates", {}),
            substrate_delta=substrate_delta,
            replay_chromosome_next=replay_chromosome_next,
        )
        if rm_chromosome_update:
            chromosome_update.update(rm_chromosome_update)
        for wid, delta in rm_substrate_delta.items():
            substrate_delta[wid] = substrate_delta.get(wid, 0.0) + float(delta)

        disa_enzyme_delta, disa_bound_enzyme_delta = self.evolveState_DisA(
            chrom_state={**dict(chrom_state), **chromosome_update},
            states=states,
            enzyme_counts=enzyme_counts,
            replay_enzymes_next=replay_enzymes_next,
            replay_bound_enzymes_next=replay_bound_enzymes_next,
        )

        if chromosome_update:
            update["chromosome"] = chromosome_update
        if disa_enzyme_delta:
            update["enzymes"] = disa_enzyme_delta
        if disa_bound_enzyme_delta:
            update["boundEnzymes"] = disa_bound_enzyme_delta
        if any(abs(delta) > 0.0 for delta in substrate_delta.values()):
            update["substrates"] = {
                wid: float(delta)
                for wid, delta in substrate_delta.items()
                if abs(float(delta)) > 0.0
            }

        return update

    def _resolve_chromosome_store(self, chrom_state: dict[str, Any]) -> ChromosomeStore:
        return ChromosomeStore.from_state_mapping(chrom_state, shape=self.chromosome_shape)

    def _sparse_field_map(
        self, chrom_state: dict[str, Any], field_name: str
    ) -> dict[tuple[int, int], int]:
        raw = chrom_state.get(field_name)
        if not isinstance(raw, dict):
            return {}
        triplet = SparseTriplet.from_state(raw, shape=self.chromosome_shape)
        return {
            (int(position), int(strand)): int(value)
            for position, strand, value in zip(
                triplet.positions.tolist(),
                triplet.strands.tolist(),
                triplet.values.tolist(),
                strict=False,
            )
            if int(value) != 0
        }

    def _triplet_state_from_map(self, coord_values: dict[tuple[int, int], int]) -> dict[str, Any]:
        entries = sorted(coord_values.items(), key=lambda item: (item[0][0], item[0][1]))
        if entries:
            positions = np.asarray([coord[0] for coord, _ in entries], dtype=np.int64)
            strands = np.asarray([coord[1] for coord, _ in entries], dtype=np.int64)
            values = np.asarray([value for _, value in entries], dtype=np.int64)
        else:
            positions = np.array([], dtype=np.int64)
            strands = np.array([], dtype=np.int64)
            values = np.array([], dtype=np.int64)
        return SparseTriplet(
            positions=positions,
            strands=strands,
            values=values,
            shape=self.chromosome_shape,
        ).to_state()

    def _polymerized_intervals_by_strand(
        self,
        chrom_state: dict[str, Any],
    ) -> dict[int, list[tuple[int, int]]]:
        raw = chrom_state.get("polymerizedRegions")
        if not isinstance(raw, dict):
            return {}
        triplet = SparseTriplet.from_state(raw, shape=self.chromosome_shape)
        out: dict[int, list[tuple[int, int]]] = {}
        for start, strand, length in zip(
            triplet.positions.tolist(),
            triplet.strands.tolist(),
            triplet.values.tolist(),
            strict=False,
        ):
            intervals = _split_circular_region(int(start), int(length), self.chromosome_length)
            if not intervals:
                continue
            out.setdefault(int(strand), []).extend(intervals)
        return out

    @staticmethod
    def _is_polymerized_coord(
        coord: tuple[int, int],
        intervals_by_strand: dict[int, list[tuple[int, int]]],
    ) -> bool:
        position, strand = coord
        for start, end in intervals_by_strand.get(int(strand), []):
            if int(start) <= int(position) <= int(end):
                return True
        return False

    def _muni_site_sets(
        self,
        *,
        field_maps: dict[str, dict[tuple[int, int], int]],
        polymerized_intervals: dict[int, list[tuple[int, int]]],
    ) -> dict[str, list[tuple[int, int]]]:
        damaged_bases = field_maps["damagedBases"]
        strand_breaks = field_maps["strandBreaks"]
        non_break_damage_coords: set[tuple[int, int]] = set()
        for field_name in (
            "damagedBases",
            "gapSites",
            "abasicSites",
            "damagedSugarPhosphates",
            "intrastrandCrossLinks",
            "hollidayJunctions",
        ):
            non_break_damage_coords.update(field_maps[field_name].keys())
        all_damage_coords = set(non_break_damage_coords) | set(strand_breaks.keys())

        hemi_targets: set[tuple[int, int]] = set()
        restrictable_targets: set[tuple[int, int]] = set()
        methylated_coords: set[tuple[int, int]] = set()
        n_sites = int(self._rm_muni_sites.shape[0])
        methyl_pos_a = int(self._rm_muni_methylated_positions[0])
        methyl_pos_b = int(self._rm_muni_methylated_positions[1])
        restrict_pos_a = int(self._rm_muni_restriction_positions[0])
        restrict_pos_b = int(self._rm_muni_restriction_positions[1])

        for strand_a, strand_b in ((0, 1), (2, 3)):
            for site_idx in range(n_sites):
                site_positions = self._rm_muni_sites[site_idx, :]

                methyl_coord_a = (int(site_positions[methyl_pos_a]), int(strand_a))
                methyl_coord_b = (int(site_positions[methyl_pos_b]), int(strand_b))
                restriction_coord_a = (int(site_positions[restrict_pos_a]), int(strand_a))
                restriction_coord_b = (int(site_positions[restrict_pos_b]), int(strand_b))

                is_methylated_a = damaged_bases.get(methyl_coord_a, 0) == self._m6ad_global_index
                is_methylated_b = damaged_bases.get(methyl_coord_b, 0) == self._m6ad_global_index

                if is_methylated_a:
                    methylated_coords.add(methyl_coord_a)
                if is_methylated_b:
                    methylated_coords.add(methyl_coord_b)

                is_site_methylated = bool(is_methylated_a and is_methylated_b)
                is_site_unmethylated = bool((not is_methylated_a) and (not is_methylated_b))
                is_site_hemimethylated = bool(
                    (not is_site_methylated) and (not is_site_unmethylated)
                )
                if is_site_hemimethylated:
                    if not is_methylated_a:
                        hemi_targets.add(methyl_coord_a)
                    if not is_methylated_b:
                        hemi_targets.add(methyl_coord_b)

                motif_coords = [
                    (int(position), int(strand_a)) for position in site_positions.tolist()
                ] + [(int(position), int(strand_b)) for position in site_positions.tolist()]
                restriction_coords = {restriction_coord_a, restriction_coord_b}
                is_site_damaged = False
                for coord in motif_coords:
                    if coord not in all_damage_coords:
                        continue
                    if (
                        coord in restriction_coords
                        and coord in strand_breaks
                        and coord not in non_break_damage_coords
                    ):
                        # Karr calcRestrictableMunIRMSites ignores strand breaks
                        # at cleavage positions.
                        continue
                    is_site_damaged = True
                    break

                if not is_site_unmethylated or is_site_damaged:
                    continue
                if self._is_polymerized_coord(restriction_coord_a, polymerized_intervals):
                    restrictable_targets.add(restriction_coord_a)
                if self._is_polymerized_coord(restriction_coord_b, polymerized_intervals):
                    restrictable_targets.add(restriction_coord_b)

        return {
            "hemiunmethylatedMunIRMSites": sorted(hemi_targets),
            "restrictableMunIRMSites": sorted(restrictable_targets),
            "m6ADMethylatedSites": sorted(methylated_coords),
        }

    def _stochastic_round(self, expected: float) -> int:
        if expected <= 0.0:
            return 0
        base = int(np.floor(expected))
        frac = float(expected - base)
        if frac <= 0.0:
            return base
        return base + int(self._rm_rng.random() < frac)

    def _effective_substrate_amount(
        self,
        *,
        wid: str,
        substrate_state: dict[str, Any],
        substrate_delta: dict[str, float],
    ) -> float:
        return max(
            0.0,
            float(substrate_state.get(wid, 0.0)) + float(substrate_delta.get(wid, 0.0)),
        )

    def _reaction_substrate_capacity(
        self,
        *,
        reaction_idx: int,
        substrate_state: dict[str, Any],
        substrate_delta: dict[str, float],
    ) -> int:
        stoich_col = self.reaction_small_molecule_stoich[:, int(reaction_idx)]
        consumed_idx = np.flatnonzero(stoich_col < 0.0)
        if consumed_idx.size == 0:
            return int(np.iinfo(np.int32).max)
        capacities: list[int] = []
        for sub_idx in consumed_idx.tolist():
            wid = self.substrate_wids[int(sub_idx)]
            needed = float(-stoich_col[int(sub_idx)])
            if needed <= 0.0:
                continue
            available = self._effective_substrate_amount(
                wid=wid,
                substrate_state=substrate_state,
                substrate_delta=substrate_delta,
            )
            capacities.append(int(np.floor(available / needed)))
        if not capacities:
            return int(np.iinfo(np.int32).max)
        return max(0, int(min(capacities)))

    def _apply_reaction_substrate_stoich(
        self,
        *,
        reaction_idx: int,
        n_reactions: int,
        substrate_delta: dict[str, float],
    ) -> None:
        if n_reactions <= 0:
            return
        stoich_col = self.reaction_small_molecule_stoich[:, int(reaction_idx)]
        for sub_idx in np.flatnonzero(stoich_col != 0.0).tolist():
            wid = self.substrate_wids[int(sub_idx)]
            delta = float(stoich_col[int(sub_idx)]) * float(n_reactions)
            substrate_delta[wid] = substrate_delta.get(wid, 0.0) + delta

    def evolveState_Modification(  # noqa: N802
        self,
        *,
        field_maps: dict[str, dict[tuple[int, int], int]],
        polymerized_intervals: dict[int, list[tuple[int, int]]],
        substrate_state: dict[str, Any],
        substrate_delta: dict[str, float],
        enzyme_counts: dict[str, float],
        dt: float,
        replay_next_damaged_bases: dict[tuple[int, int], int] | None = None,
    ) -> int:
        muni_sets = self._muni_site_sets(
            field_maps=field_maps, polymerized_intervals=polymerized_intervals
        )
        candidate_coords = muni_sets["hemiunmethylatedMunIRMSites"]
        if not candidate_coords:
            return 0

        reaction_idx = int(self._rm_muni_methylation_idx)
        if replay_next_damaged_bases is not None:
            # Hint-gated replay: methylate exactly the hemiunmethylated sites that the
            # recorded next chromosome shows as m6AD. Deterministic (no stochastic rate
            # or site selection); transparent when no hint is supplied (the mechanistic
            # path below runs). Consistent with the DNASupercoiling replay channel.
            m6 = int(self._m6ad_global_index)
            chosen_coords = [
                coord
                for coord in candidate_coords
                if int(replay_next_damaged_bases.get(coord, 0)) == m6
            ]
            if not chosen_coords:
                return 0
            for coord in chosen_coords:
                field_maps["damagedBases"][coord] = m6
            self._apply_reaction_substrate_stoich(
                reaction_idx=reaction_idx,
                n_reactions=len(chosen_coords),
                substrate_delta=substrate_delta,
            )
            return len(chosen_coords)
        substrate_cap = self._reaction_substrate_capacity(
            reaction_idx=reaction_idx,
            substrate_state=substrate_state,
            substrate_delta=substrate_delta,
        )
        enzyme_cap = self._stochastic_round(
            float(enzyme_counts.get(self._rm_typeii_enzyme_wid, 0.0))
            * float(dt)
            * float(self.reaction_ub[reaction_idx])
        )
        n_reactions = max(0, min(len(candidate_coords), substrate_cap, enzyme_cap))
        if n_reactions <= 0:
            return 0

        candidate_idx = np.arange(len(candidate_coords), dtype=np.int64)
        if n_reactions < len(candidate_coords):
            chosen = self._rm_rng.choice(candidate_idx, size=int(n_reactions), replace=False)
            chosen_idx = np.asarray(chosen, dtype=np.int64).reshape(-1)
        else:
            chosen_idx = candidate_idx
        for idx in chosen_idx.tolist():
            coord = candidate_coords[int(idx)]
            field_maps["damagedBases"][coord] = int(self._m6ad_global_index)

        self._apply_reaction_substrate_stoich(
            reaction_idx=reaction_idx,
            n_reactions=int(n_reactions),
            substrate_delta=substrate_delta,
        )
        return int(n_reactions)

    def evolveState_Restriction(  # noqa: N802
        self,
        *,
        field_maps: dict[str, dict[tuple[int, int], int]],
        polymerized_intervals: dict[int, list[tuple[int, int]]],
        substrate_state: dict[str, Any],
        substrate_delta: dict[str, float],
        enzyme_counts: dict[str, float],
        dt: float,
        replay_next_strand_breaks: dict[tuple[int, int], int] | None = None,
    ) -> int:
        muni_sets = self._muni_site_sets(
            field_maps=field_maps, polymerized_intervals=polymerized_intervals
        )
        candidate_coords = muni_sets["restrictableMunIRMSites"]
        if not candidate_coords:
            return 0

        reaction_idx = int(self._rm_muni_restriction_idx)
        if replay_next_strand_breaks is not None:
            # Hint-gated replay: cleave exactly the restrictable sites the recorded next
            # chromosome shows as strand-broken. Deterministic; transparent when no hint.
            chosen_coords = [
                coord
                for coord in candidate_coords
                if int(replay_next_strand_breaks.get(coord, 0)) != 0
            ]
            if not chosen_coords:
                return 0
            for coord in chosen_coords:
                field_maps["strandBreaks"][coord] = 1
            self._apply_reaction_substrate_stoich(
                reaction_idx=reaction_idx,
                n_reactions=len(chosen_coords),
                substrate_delta=substrate_delta,
            )
            return len(chosen_coords)
        substrate_cap = self._reaction_substrate_capacity(
            reaction_idx=reaction_idx,
            substrate_state=substrate_state,
            substrate_delta=substrate_delta,
        )
        enzyme_cap = self._stochastic_round(
            float(enzyme_counts.get(self._rm_typeii_enzyme_wid, 0.0))
            * float(dt)
            * float(self.reaction_ub[reaction_idx])
        )
        n_reactions = max(0, min(len(candidate_coords), substrate_cap, enzyme_cap))
        if n_reactions <= 0:
            return 0

        candidate_idx = np.arange(len(candidate_coords), dtype=np.int64)
        if n_reactions < len(candidate_coords):
            chosen = self._rm_rng.choice(candidate_idx, size=int(n_reactions), replace=False)
            chosen_idx = np.asarray(chosen, dtype=np.int64).reshape(-1)
        else:
            chosen_idx = candidate_idx
        for idx in chosen_idx.tolist():
            coord = candidate_coords[int(idx)]
            field_maps["strandBreaks"][coord] = 1

        self._apply_reaction_substrate_stoich(
            reaction_idx=reaction_idx,
            n_reactions=int(n_reactions),
            substrate_delta=substrate_delta,
        )
        return int(n_reactions)

    def _evolve_state_restriction_modification(
        self,
        *,
        chrom_state: dict[str, Any],
        enzyme_counts: dict[str, float],
        dt: float,
        substrate_state: dict[str, Any],
        substrate_delta: dict[str, float],
        replay_chromosome_next: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, float]]:
        field_maps: dict[str, dict[tuple[int, int], int]] = {
            "damagedBases": self._sparse_field_map(chrom_state, "damagedBases"),
            "strandBreaks": self._sparse_field_map(chrom_state, "strandBreaks"),
            "gapSites": self._sparse_field_map(chrom_state, "gapSites"),
            "abasicSites": self._sparse_field_map(chrom_state, "abasicSites"),
            "damagedSugarPhosphates": self._sparse_field_map(chrom_state, "damagedSugarPhosphates"),
            "intrastrandCrossLinks": self._sparse_field_map(chrom_state, "intrastrandCrossLinks"),
            "hollidayJunctions": self._sparse_field_map(chrom_state, "hollidayJunctions"),
        }
        polymerized_intervals = self._polymerized_intervals_by_strand(chrom_state)
        rm_substrate_delta: dict[str, float] = {}
        merged_substrate_delta = dict(substrate_delta)

        replay_next_damaged_bases: dict[tuple[int, int], int] | None = None
        replay_next_strand_breaks: dict[tuple[int, int], int] | None = None
        if replay_chromosome_next is not None:
            replay_next_damaged_bases = self._sparse_field_map(
                replay_chromosome_next, "damagedBases"
            )
            replay_next_strand_breaks = self._sparse_field_map(
                replay_chromosome_next, "strandBreaks"
            )

        def _modification() -> None:
            self.evolveState_Modification(
                field_maps=field_maps,
                polymerized_intervals=polymerized_intervals,
                substrate_state=substrate_state,
                substrate_delta=merged_substrate_delta,
                enzyme_counts=enzyme_counts,
                dt=dt,
                replay_next_damaged_bases=replay_next_damaged_bases,
            )

        def _restriction() -> None:
            self.evolveState_Restriction(
                field_maps=field_maps,
                polymerized_intervals=polymerized_intervals,
                substrate_state=substrate_state,
                substrate_delta=merged_substrate_delta,
                enzyme_counts=enzyme_counts,
                dt=dt,
                replay_next_strand_breaks=replay_next_strand_breaks,
            )

        # Replay derives per-reaction counts from the recorded chromosome, which is
        # order-independent, so use a fixed order; otherwise preserve Karr's random order.
        modification_first = (
            True if replay_chromosome_next is not None else (self._rm_rng.random() > 0.5)
        )
        if modification_first:
            _modification()
            _restriction()
        else:
            _restriction()
            _modification()

        for wid, value in merged_substrate_delta.items():
            delta = float(value) - float(substrate_delta.get(wid, 0.0))
            if delta != 0.0:
                rm_substrate_delta[wid] = delta

        muni_sets = self._muni_site_sets(
            field_maps=field_maps,
            polymerized_intervals=polymerized_intervals,
        )

        chromosome_update: dict[str, Any] = {
            "damagedBases": self._triplet_state_from_map(field_maps["damagedBases"]),
            "strandBreaks": self._triplet_state_from_map(field_maps["strandBreaks"]),
        }
        for field_name in _RM_DERIVED_FIELDS:
            coord_map = {coord: 1 for coord in muni_sets[field_name]}
            chromosome_update[field_name] = self._triplet_state_from_map(coord_map)
        return chromosome_update, rm_substrate_delta

    def _damaged_sites_excm6ad(self, chrom_state: dict[str, Any]) -> list[tuple[int, int]]:
        m6ad_sites = set(self._sparse_field_map(chrom_state, "m6ADMethylatedSites").keys())
        candidate_fields = (
            "damagedBases",
            "gapSites",
            "abasicSites",
            "damagedSugarPhosphates",
            "intrastrandCrossLinks",
            "strandBreaks",
            "hollidayJunctions",
        )
        out: set[tuple[int, int]] = set()
        for field_name in candidate_fields:
            coords = set(self._sparse_field_map(chrom_state, field_name).keys())
            if field_name == "damagedBases":
                coords -= m6ad_sites
            out.update(coords)
        return sorted(out, key=lambda coord: (coord[0], coord[1]))

    def _disa_bindable_capacity(self, coords: list[tuple[int, int]]) -> int:
        if not coords:
            return 0
        min_spacing = int(max(1, self._disa_dna_footprint))
        by_strand: dict[int, list[int]] = {}
        for position, strand in coords:
            by_strand.setdefault(int(strand), []).append(int(position))

        n_bindable = 0
        for positions in by_strand.values():
            unique_sorted = sorted(set(positions))
            last_pos: int | None = None
            for position in unique_sorted:
                if last_pos is None or int(position) - int(last_pos) >= min_spacing:
                    n_bindable += 1
                    last_pos = int(position)
        return int(n_bindable)

    def evolveState_DisA(  # noqa: N802
        self,
        *,
        chrom_state: dict[str, Any],
        states: dict[str, Any],
        enzyme_counts: dict[str, float],
        replay_enzymes_next: dict[str, float] | None = None,
        replay_bound_enzymes_next: dict[str, float] | None = None,
    ) -> tuple[dict[str, float], dict[str, float]]:
        damaged_sites_excm6ad = self._damaged_sites_excm6ad(chrom_state)
        if not damaged_sites_excm6ad:
            return {}, {}

        polymerized_intervals = self._polymerized_intervals_by_strand(chrom_state)
        if polymerized_intervals:
            damaged_sites_excm6ad = [
                coord
                for coord in damaged_sites_excm6ad
                if self._is_polymerized_coord(coord, polymerized_intervals)
            ]
            if not damaged_sites_excm6ad:
                return {}, {}

        enzymes_state = states.get("enzymes", {})
        if isinstance(enzymes_state, dict):
            free_dis_a = float(
                max(
                    0.0,
                    enzymes_state.get(
                        self._disa_enzyme_wid,
                        enzyme_counts.get(self._disa_enzyme_wid, 0.0),
                    ),
                )
            )
        else:
            free_dis_a = float(max(0.0, enzyme_counts.get(self._disa_enzyme_wid, 0.0)))

        bound_state = states.get("boundEnzymes", {})
        if isinstance(bound_state, dict):
            bound_dis_a = float(max(0.0, bound_state.get(self._disa_enzyme_wid, 0.0)))
        else:
            bound_dis_a = 0.0

        if replay_enzymes_next is not None or replay_bound_enzymes_next is not None:
            next_free_dis_a = float(
                (replay_enzymes_next or {}).get(
                    self._disa_enzyme_wid,
                    free_dis_a,
                )
            )
            next_bound_dis_a = float(
                (replay_bound_enzymes_next or {}).get(
                    self._disa_enzyme_wid,
                    bound_dis_a,
                )
            )
            enzyme_delta = next_free_dis_a - free_dis_a
            bound_delta = next_bound_dis_a - bound_dis_a
            return (
                {self._disa_enzyme_wid: enzyme_delta} if enzyme_delta != 0.0 else {},
                {self._disa_enzyme_wid: bound_delta} if bound_delta != 0.0 else {},
            )

        free_dis_a_i = int(np.floor(free_dis_a))
        bound_dis_a_i = int(np.floor(bound_dis_a))
        if free_dis_a_i <= 0:
            return {}, {}

        bindable_capacity = self._disa_bindable_capacity(damaged_sites_excm6ad)
        available_sites = int(max(0, bindable_capacity - bound_dis_a_i))
        n_bind = int(min(free_dis_a_i, available_sites))
        if n_bind <= 0:
            return {}, {}

        return (
            {self._disa_enzyme_wid: -float(n_bind)},
            {self._disa_enzyme_wid: float(n_bind)},
        )

    def _damage_sites(
        self, chrom_state: dict[str, Any], states: dict[str, Any]
    ) -> list[_DamageSite]:
        sparse_sites = self._damage_sites_from_sparse(chrom_state)
        if sparse_sites:
            return sparse_sites
        return self._canonical_damage_sites(current_damage_sites(states))

    def _damage_sites_from_sparse(self, chrom_state: dict[str, Any]) -> list[_DamageSite]:
        store = self._resolve_chromosome_store(chrom_state)
        out: list[_DamageSite] = []

        for field_name in ("damagedBases", "abasicSites", "damagedSugarPhosphates", "gapSites"):
            triplet = store.get_field(field_name)
            damage_type = {
                "damagedBases": "damaged_base",
                "abasicSites": "abasic_site",
                "damagedSugarPhosphates": "abasic_site",
                "gapSites": "single_strand_break",
            }[field_name]
            for position, strand, value in zip(
                triplet.positions.tolist(),
                triplet.strands.tolist(),
                triplet.values.tolist(),
                strict=False,
            ):
                if field_name == "damagedBases" and int(value) == int(self._m6ad_global_index):
                    # MunI methyl marks are not DNA lesions for BER/NER/HR routing.
                    continue
                site_id = f"{field_name}:{int(position)}:{int(strand)}"
                payload = {
                    "id": site_id,
                    "site_id": site_id,
                    "damage_type": damage_type,
                    "position": int(position),
                    "strand": int(strand),
                    "field_name": field_name,
                    "coordinates": [(int(position), int(strand))],
                    "value": int(value),
                }
                out.append(_DamageSite(site_id=site_id, damage_type=damage_type, payload=payload))

        strand_breaks = store.get_field("strandBreaks")
        break_values = {
            (int(position), int(strand)): int(value)
            for position, strand, value in zip(
                strand_breaks.positions.tolist(),
                strand_breaks.strands.tolist(),
                strand_breaks.values.tolist(),
                strict=False,
            )
        }
        seen_breaks: set[tuple[int, int]] = set()
        for (position, strand), value in sorted(break_values.items()):
            if (position, strand) in seen_breaks:
                continue
            paired_strand = strand + 1 if strand % 2 == 0 else strand - 1
            pair_key = (position, paired_strand)
            if pair_key in break_values:
                seen_breaks.add((position, strand))
                seen_breaks.add(pair_key)
                site_id = (
                    "strandBreaks:"
                    f"{position}:{min(strand, paired_strand)}-"
                    f"{max(strand, paired_strand)}"
                )
                payload = {
                    "id": site_id,
                    "site_id": site_id,
                    "damage_type": "double_strand_break",
                    "position": int(position),
                    "field_name": "strandBreaks",
                    "coordinates": [
                        (int(position), int(strand)),
                        (int(position), int(paired_strand)),
                    ],
                    "value": int(value) + int(break_values[pair_key]),
                }
                out.append(
                    _DamageSite(site_id=site_id, damage_type="double_strand_break", payload=payload)
                )
                continue

            seen_breaks.add((position, strand))
            site_id = f"strandBreaks:{position}:{strand}"
            payload = {
                "id": site_id,
                "site_id": site_id,
                "damage_type": "single_strand_break",
                "position": int(position),
                "strand": int(strand),
                "field_name": "strandBreaks",
                "coordinates": [(int(position), int(strand))],
                "value": int(value),
            }
            out.append(
                _DamageSite(site_id=site_id, damage_type="single_strand_break", payload=payload)
            )

        return out

    def _chromosome_damage_writeback(
        self,
        *,
        chrom_state: dict[str, Any],
        damage_sites: list[_DamageSite],
        repaired_indices: set[int],
    ) -> dict[str, Any]:
        if not repaired_indices:
            return {}

        store = self._resolve_chromosome_store(chrom_state)
        by_field: dict[str, dict[tuple[int, int], int]] = {}
        for field_name in _DAMAGE_FIELDS:
            triplet = store.get_field(field_name)
            by_field[field_name] = {
                (int(position), int(strand)): int(value)
                for position, strand, value in zip(
                    triplet.positions.tolist(),
                    triplet.strands.tolist(),
                    triplet.values.tolist(),
                    strict=False,
                )
            }

        touched_fields: set[str] = set()
        for idx in repaired_indices:
            if idx < 0 or idx >= len(damage_sites):
                continue
            payload = damage_sites[idx].payload
            field_name = str(payload.get("field_name", ""))
            if field_name not in by_field:
                continue
            coords = payload.get("coordinates")
            if not isinstance(coords, list):
                position = payload.get("position")
                strand = payload.get("strand")
                if position is None or strand is None:
                    continue
                coords = [(int(position), int(strand))]
            for coord in coords:
                if not isinstance(coord, (tuple, list)) or len(coord) != 2:
                    continue
                key = (int(coord[0]), int(coord[1]))
                if key in by_field[field_name]:
                    by_field[field_name].pop(key, None)
                    touched_fields.add(field_name)

        chromosome_update: dict[str, Any] = {}
        for field_name in sorted(touched_fields):
            entries = sorted(
                by_field[field_name].items(), key=lambda item: (item[0][0], item[0][1])
            )
            if entries:
                positions = np.asarray([coord[0] for coord, _ in entries], dtype=np.int64)
                strands = np.asarray([coord[1] for coord, _ in entries], dtype=np.int64)
                values = np.asarray([value for _, value in entries], dtype=np.int64)
            else:
                positions = np.array([], dtype=np.int64)
                strands = np.array([], dtype=np.int64)
                values = np.array([], dtype=np.int64)
            chromosome_update[field_name] = SparseTriplet(
                positions=positions,
                strands=strands,
                values=values,
                shape=self.chromosome_shape,
            ).to_state()
        return chromosome_update

    def _canonical_damage_sites(self, raw: object) -> list[_DamageSite]:
        normalized: list[_DamageSite] = []
        if raw is None:
            return normalized

        records: list[object] = []
        if isinstance(raw, dict):
            if "sites" in raw and isinstance(raw["sites"], (list, tuple)):
                records.extend(list(raw["sites"]))
            else:
                for site_id, payload in raw.items():
                    if isinstance(payload, dict):
                        rec = dict(payload)
                        rec.setdefault("site_id", site_id)
                    else:
                        rec = {"site_id": site_id, "damage_type": payload}
                    records.append(rec)
        elif isinstance(raw, (list, tuple)):
            records.extend(list(raw))
        else:
            records.append(raw)

        for idx, rec in enumerate(records):
            payload: dict[str, Any]
            if isinstance(rec, dict):
                payload = dict(rec)
                damage_raw = payload.get(
                    "damage_type", payload.get("type", payload.get("kind", "unknown"))
                )
                site_raw = payload.get("site_id", payload.get("id"))
            elif isinstance(rec, (tuple, list)):
                if len(rec) >= 2:
                    payload = {"position": rec[0], "damage_type": rec[1]}
                elif len(rec) == 1:
                    payload = {"damage_type": rec[0]}
                else:
                    payload = {"damage_type": "unknown"}
                damage_raw = payload["damage_type"]
                site_raw = payload.get("site_id")
            else:
                payload = {"damage_type": rec}
                damage_raw = rec
                site_raw = None

            damage_type = _normalize_damage_type(damage_raw)
            if site_raw is None:
                if "position" in payload:
                    site_id = f"{damage_type}@{payload['position']}"
                else:
                    site_id = f"{damage_type}#{idx:05d}"
            else:
                site_id = str(site_raw)
            payload["damage_type"] = damage_type
            payload["site_id"] = site_id
            payload.setdefault("id", site_id)
            normalized.append(
                _DamageSite(site_id=site_id, damage_type=damage_type, payload=payload)
            )
        return normalized

    def _repair_event_from_site(self, site: dict[str, Any]) -> dict[str, Any]:
        site_id = str(site.get("id", site.get("site_id", "")))
        if not site_id:
            damage_type = str(site.get("damage_type", site.get("kind", "unknown")))
            site_id = f"{damage_type}@{site['position']}" if "position" in site else damage_type
        event = {
            "id": site_id,
            "site_id": site_id,
            "damage_type": str(site.get("damage_type", site.get("kind", "unknown"))),
        }
        if "position" in site:
            event["position"] = site["position"]
        return event

    def _enzyme_counts(self, states: dict[str, Any]) -> dict[str, float]:
        protein_counts = states.get("protein", {}).get("counts", {})
        complex_counts = states.get("complex", {}).get("counts", {})
        if not isinstance(protein_counts, dict):
            protein_counts = {}
        if not isinstance(complex_counts, dict):
            complex_counts = {}

        missing_protein = [wid for wid in self.protein_enzyme_wids if wid not in protein_counts]
        missing_complex = [wid for wid in self.complex_enzyme_wids if wid not in complex_counts]
        if missing_protein or missing_complex:
            raise KeyError(
                "karr_dna_repair missing declared enzyme counts: "
                f"protein={missing_protein}, complex={missing_complex}"
            )

        out: dict[str, float] = {}
        for wid in self.protein_enzyme_wids:
            out[wid] = float(max(0.0, protein_counts[wid]))
        for wid in self.complex_enzyme_wids:
            out[wid] = float(max(0.0, complex_counts[wid]))
        return out

    def _pathway_for_damage_type(self, damage_type: str) -> str:
        if damage_type in {"abasic_site", "damaged_base"}:
            return "ber"
        if damage_type in {"intrastrand_crosslink"}:
            return "ner"
        if damage_type in {"double_strand_break"}:
            return "hr"
        if damage_type in {"single_strand_break"}:
            return "nhej_like"
        return "nhej_like"

    def _pathway_capacity_per_s(self, pathway: str, enzyme_counts: dict[str, float]) -> float:
        rxn_indices = self.pathway_reaction_indices[pathway]
        capacities: list[float] = []
        for rxn_idx in rxn_indices:
            ub = float(self.reaction_ub[int(rxn_idx)])
            if not math.isfinite(ub) or ub <= 0.0:
                continue

            catalyst_col = self.reaction_catalysis[int(rxn_idx), :]
            catalyst_indices = np.flatnonzero(np.abs(catalyst_col) > 0.0)
            if catalyst_indices.size <= 0:
                continue

            enzyme_total = 0.0
            for enz_idx in catalyst_indices:
                enz_wid = self.enzyme_wids[int(enz_idx)]
                stoich = abs(float(catalyst_col[int(enz_idx)]))
                enzyme_total += float(max(0.0, enzyme_counts.get(enz_wid, 0.0))) / max(stoich, 1.0)
            if enzyme_total <= 0.0:
                continue
            capacities.append(ub * enzyme_total)

        if not capacities:
            return 0.0
        return float(min(capacities) * float(self.parameters["pathway_rate_scale"]))

    def _desired_repairs(
        self,
        damage_sites: list[_DamageSite],
        enzyme_counts: dict[str, float],
        dt: float,
    ) -> tuple[dict[str, int], dict[str, list[int]]]:
        indices_by_pathway = {pathway: [] for pathway in _PATHWAYS}
        for idx, site in enumerate(damage_sites):
            indices_by_pathway[self._pathway_for_damage_type(site.damage_type)].append(idx)

        desired: dict[str, int] = {pathway: 0 for pathway in _PATHWAYS}
        for pathway in _PATHWAYS:
            lesion_count = len(indices_by_pathway[pathway])
            if lesion_count <= 0:
                continue
            capacity_per_s = self._pathway_capacity_per_s(pathway, enzyme_counts)
            expected = max(0.0, capacity_per_s * float(dt) * float(lesion_count))
            n = int(self._rng.poisson(expected))
            desired[pathway] = int(min(max(0, n), lesion_count))
        return desired, indices_by_pathway

    def _pathway_atp_cost(self, pathway: str) -> float:
        rxn_indices = self.pathway_reaction_indices[pathway]
        atp_row = self.reaction_small_molecule_stoich[self.atp_index, rxn_indices]
        return float(np.sum(np.clip(-atp_row, a_min=0.0, a_max=None)))

    def _per_event_substrate_cost(self, pathway: str) -> dict[str, float]:
        out = {wid: 0.0 for wid in self.tracked_substrates}
        out[self.atp_wid] = float(self.pathway_atp_cost[pathway])

        dntp_total = float(self.pathway_patch_length_nt[pathway])
        for idx, wid in enumerate(self.dntp_wids):
            out[wid] = float(dntp_total * self.dntp_split[idx])
        return out

    def _substrate_needs_for_repairs(self, repairs_by_pathway: dict[str, int]) -> dict[str, float]:
        needs = {wid: 0.0 for wid in self.tracked_substrates}
        for pathway, n in repairs_by_pathway.items():
            if n <= 0:
                continue
            per_event = self.pathway_per_event_substrate_cost[pathway]
            for wid in self.tracked_substrates:
                needs[wid] += float(n) * float(per_event[wid])
        return needs

    def _bounded_repairs(
        self,
        desired_repairs: dict[str, int],
        available: dict[str, float],
    ) -> dict[str, int]:
        if all(n <= 0 for n in desired_repairs.values()):
            return {pathway: 0 for pathway in _PATHWAYS}

        desired_need = self._substrate_needs_for_repairs(desired_repairs)
        scale = 1.0
        for wid, need in desired_need.items():
            if need <= 0.0:
                continue
            have = max(0.0, float(available.get(wid, 0.0)))
            scale = min(scale, have / need)

        actual = {
            pathway: int(max(0, math.floor(float(n) * scale)))
            for pathway, n in desired_repairs.items()
        }

        consumed = self._substrate_needs_for_repairs(actual)
        remaining = {
            wid: max(0.0, float(available.get(wid, 0.0)) - float(consumed.get(wid, 0.0)))
            for wid in self.tracked_substrates
        }

        progressed = True
        while progressed:
            progressed = False
            for pathway in sorted(_PATHWAYS, key=lambda name: desired_repairs[name], reverse=True):
                if actual[pathway] >= desired_repairs[pathway]:
                    continue
                per_event = self.pathway_per_event_substrate_cost[pathway]
                feasible = all(
                    remaining[wid] + 1e-12 >= per_event[wid] for wid in self.tracked_substrates
                )
                if not feasible:
                    continue
                actual[pathway] += 1
                for wid in self.tracked_substrates:
                    remaining[wid] = max(0.0, remaining[wid] - per_event[wid])
                progressed = True
        return actual

    def _sample_repaired_indices(
        self,
        indices_by_pathway: dict[str, list[int]],
        repairs_by_pathway: dict[str, int],
    ) -> set[int]:
        repaired: set[int] = set()
        for pathway in _PATHWAYS:
            n = repairs_by_pathway[pathway]
            if n <= 0:
                continue
            candidates = np.asarray(indices_by_pathway[pathway], dtype=np.int64)
            if candidates.size <= 0:
                continue
            n = min(int(n), int(candidates.size))
            chosen = self._rng.choice(candidates, size=n, replace=False)
            repaired.update(int(idx) for idx in np.asarray(chosen, dtype=np.int64).reshape(-1))
        return repaired

    def _allocated_or_state(
        self,
        allocated_state: dict[str, Any],
        wid: str,
    ) -> float:
        allocated = float(allocated_state.get(wid, 0.0))
        return max(0.0, allocated)


__all__ = ["KarrDNARepairProcess"]
