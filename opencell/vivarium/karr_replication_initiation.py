"""Vivarium Process port of Karr's replication initiation gate logic."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.state.chromosome_store import (
    CHROMOSOME_FIELDS,
    ChromosomeStore,
    SparseTriplet,
    sparse_triplet_schema,
)

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ReplicationInitiation_flat.mat"


def _resolve_fixture_path(path: str | Path) -> Path:
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
    values = np.asarray(value, dtype=object)
    out: list[str] = []
    for raw in values.ravel():
        token = _coerce_scalar(raw)
        out.append(str(token))
    return out


def _parse_index_array(value: object) -> np.ndarray:
    raw = np.asarray(value)
    while raw.dtype == object and raw.size == 1 and isinstance(raw.flat[0], np.ndarray):
        raw = np.asarray(raw.flat[0])
    return np.asarray(raw, dtype=np.int64).reshape(-1)


class KarrReplicationInitiationProcess(Process):
    """Karr Process_ReplicationInitiation (DnaA OriC gating)."""

    name = "karr_replication_initiation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "m6ad_global_index": None,
        "polymer_max_length": 7,
        "r1234_threshold": 7,
        "r5_threshold": 1,
        "polymerization_rate_scale": 1_000.0,
        "binding_rate_scale": 25_000.0,
        "release_rate_scale": 1_000.0,
        "inactivation_rate_scale": 1.0e16,
        "regen_rate_scale": 1_000.0,
        "membrane_conc": 0.03,
        "r5_binding_boost": 40.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        self._free_dnaa_atp = 0
        self._free_dnaa_adp = 0
        self._bound_atp = np.zeros(self.n_sites, dtype=np.int64)
        self._bound_adp = np.zeros(self.n_sites, dtype=np.int64)
        self._blocked_sites = np.zeros(self.n_sites, dtype=bool)
        self._initialized = False

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.substrate_wids = _parse_wid_array(fx.substrateWholeCellModelIDs)
        self.enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)

        self.substrate_index_atp = int(_coerce_scalar(fx.substrateIndexs_atp)) - 1
        self.substrate_index_adp = int(_coerce_scalar(fx.substrateIndexs_adp)) - 1
        self.substrate_index_pi = int(_coerce_scalar(fx.substrateIndexs_phosphate)) - 1
        self.substrate_index_water = int(_coerce_scalar(fx.substrateIndexs_water)) - 1
        self.substrate_index_h = int(_coerce_scalar(fx.substrateIndexs_hydrogen)) - 1

        self.atp_wid = self.substrate_wids[self.substrate_index_atp]
        self.adp_wid = self.substrate_wids[self.substrate_index_adp]
        self.pi_wid = self.substrate_wids[self.substrate_index_pi]
        self.water_wid = self.substrate_wids[self.substrate_index_water]
        self.hydrogen_wid = self.substrate_wids[self.substrate_index_h]

        self.dnaa_wid = self.enzyme_wids[int(_coerce_scalar(fx.enzymeIndexs_DnaA)) - 1]

        self.kb_atp = float(_coerce_scalar(fx.kb1ATP))
        self.kb_adp = float(_coerce_scalar(fx.kb1ADP))
        self.kd_atp = float(_coerce_scalar(fx.kd1ATP))
        self.kd_adp = float(_coerce_scalar(fx.kd1ADP))
        self.k_regen = float(_coerce_scalar(fx.k_Regen))
        self.k_regen_p4 = float(_coerce_scalar(fx.K_Regen_P4))
        self.k_inact = float(_coerce_scalar(fx.k_inact))
        self.site_cooperativity = float(_coerce_scalar(fx.siteCooperativity))
        self.state_cooperativity = float(_coerce_scalar(fx.stateCooperativity))

        self.enzyme_global_indexs = np.asarray(fx.enzymeGlobalIndexs, dtype=np.int64).reshape(-1)
        self.enzyme_index_dnaa_1mer_adp = int(_coerce_scalar(fx.enzymeIndexs_DnaA_1mer_ADP)) - 1
        self.enzyme_index_dnaa_1mer_atp = int(_coerce_scalar(fx.enzymeIndexs_DnaA_1mer_ATP)) - 1
        self.enzyme_indexs_dnaa_nmer_atp = (
            _parse_index_array(fx.enzymeIndexs_DnaA_Nmer_ATP) - 1
        ).astype(np.int64)
        self.enzyme_indexs_dnaa_nmer_adp = (
            _parse_index_array(fx.enzymeIndexs_DnaA_Nmer_ADP) - 1
        ).astype(np.int64)

        all_start_positions = _parse_index_array(fx.dnaABoxStartPositions) - 1
        self.n_sites = int(all_start_positions.size)
        self.chromosome_length = ChromosomeStore.DEFAULT_SEQUENCE_LEN
        if np.any(all_start_positions >= 0):
            self.chromosome_length = max(
                int(ChromosomeStore.DEFAULT_SEQUENCE_LEN),
                int(np.max(all_start_positions)) + 1,
            )
        self.chromosome_shape = (
            self.chromosome_length,
            ChromosomeStore.DEFAULT_N_COMPARTMENTS,
        )
        self._dnaa_box_positions = all_start_positions.astype(np.int64, copy=False)
        self._site_index_by_position = {
            int(position): idx for idx, position in enumerate(self._dnaa_box_positions.tolist())
        }

        r12345 = (_parse_index_array(fx.dnaABoxIndexs_R12345) - 1).tolist()
        if len(r12345) != 5:
            raise ValueError(f"Expected 5 OriC sites, found {len(r12345)}")
        self.r12345_indices = [int(idx) for idx in r12345]
        self.r1234_indices = self.r12345_indices[:4]
        self.r5_index = int((_parse_index_array(fx.dnaABoxIndexs_R5) - 1)[0])

        self.oric_site_ids = ["R1", "R2", "R3", "R4", "R5"]
        self.r1234_site_ids = self.oric_site_ids[:4]
        self._oric_index_to_name = {
            self.r12345_indices[0]: "R1",
            self.r12345_indices[1]: "R2",
            self.r12345_indices[2]: "R3",
            self.r12345_indices[3]: "R4",
            self.r12345_indices[4]: "R5",
        }

        self.index_to_site_id: list[str] = []
        for idx in range(self.n_sites):
            if idx in self._oric_index_to_name:
                self.index_to_site_id.append(self._oric_index_to_name[idx])
            else:
                self.index_to_site_id.append(f"DnaA_box_{idx + 1:04d}")
        self.site_id_to_index = {sid: idx for idx, sid in enumerate(self.index_to_site_id)}
        self.all_dnaa_sites = list(self.index_to_site_id)
        self.non_oric_site_ids = [
            site_id for site_id in self.all_dnaa_sites if site_id not in set(self.oric_site_ids)
        ]
        self._oric_position_set = {
            int(self._dnaa_box_positions[idx]) for idx in self.r12345_indices
        }

        self._dnaa_counts_by_global_index: dict[int, tuple[int, int]] = {}
        self._dnaa_global_index_by_counts: dict[tuple[int, int], int] = {}
        self._register_dnaa_complex(self.enzyme_index_dnaa_1mer_adp, atp_count=0, adp_count=1)
        self._register_dnaa_complex(self.enzyme_index_dnaa_1mer_atp, atp_count=1, adp_count=0)
        for offset, local_idx in enumerate(self.enzyme_indexs_dnaa_nmer_atp.tolist(), start=2):
            self._register_dnaa_complex(local_idx, atp_count=offset, adp_count=0)
        for offset, local_idx in enumerate(self.enzyme_indexs_dnaa_nmer_adp.tolist(), start=2):
            self._register_dnaa_complex(local_idx, atp_count=offset - 1, adp_count=1)

        self._atp_moieties_by_wid = {
            wid: self._infer_atp_moieties(wid) for wid in self.enzyme_wids
        }
        m6ad_cfg = self.parameters.get("m6ad_global_index")
        self.m6ad_global_index = None if m6ad_cfg is None else int(m6ad_cfg)

    def _register_dnaa_complex(self, local_index: int, *, atp_count: int, adp_count: int) -> None:
        global_index = int(self.enzyme_global_indexs[int(local_index)])
        counts = (int(atp_count), int(adp_count))
        self._dnaa_counts_by_global_index[global_index] = counts
        self._dnaa_global_index_by_counts[counts] = global_index

    def build_default_chromosome_state(
        self,
        *,
        replication_state: str = "idle",
        supercoiled: bool = True,
    ) -> dict[str, Any]:
        store = ChromosomeStore(shape=self.chromosome_shape)
        store.set_field("polymerizedRegions", self._mother_polymerized_regions())
        state = store.to_state()
        state["dnaa_complex_count"] = {site_id: 0 for site_id in self.all_dnaa_sites}
        state["replication_state"] = replication_state
        state["supercoiled"] = bool(supercoiled)
        return state

    def _mother_polymerized_regions(self) -> SparseTriplet:
        return SparseTriplet.from_regions(
            [
                (0, 0, self.chromosome_length),
                (0, 1, self.chromosome_length),
            ],
            shape=self.chromosome_shape,
        )

    def ports_schema(self) -> dict[str, Any]:
        chromosome_schema = {
            field: sparse_triplet_schema(
                self.chromosome_shape,
                emit=(field in {"complexBoundSites", "damagedBases", "polymerizedRegions"}),
            )
            for field in CHROMOSOME_FIELDS
        }
        chromosome_schema.update(
            {
                "dnaa_complex_count": {
                    site_id: {"_default": 0, "_updater": "accumulate", "_emit": True}
                    for site_id in self.all_dnaa_sites
                },
                "replication_state": {
                    "_default": "idle",
                    "_updater": "set",
                    "_emit": True,
                },
                "supercoiled": {
                    "_default": True,
                    "_updater": "set",
                    "_emit": False,
                },
            }
        )
        return {
            "chromosome": chromosome_schema,
            "protein": {
                "counts": {
                    self.dnaa_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                }
            },
            "enzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "boundEnzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.substrate_wids
            },
            "requests": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                    self.water_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_emit": False},
                    self.water_wid: {"_default": 0.0, "_emit": False},
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        hint = states.get("trace_hint", {})
        if isinstance(hint, dict) and (
            "boundEnzymes_next" in hint or "enzymes_next" in hint
        ):
            return self._next_update_from_trace_hint(timestep=timestep, states=states)

        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])

        chromosome_state = states.get("chromosome", {})
        chromosome_store = self._resolve_chromosome_store(chromosome_state)
        complex_bound_before = chromosome_store.get_field("complexBoundSites")
        damaged_bases = chromosome_store.get_field("damagedBases")
        protein_counts = states["protein"]["counts"]
        dnaa_adp_wid, dnaa_atp_wid = self.enzyme_wids[0], self.enzyme_wids[1]
        free_dnaa_adp = int(max(0.0, float(protein_counts.get(dnaa_adp_wid, 0.0))))
        free_dnaa_atp = int(max(0.0, float(protein_counts.get(dnaa_atp_wid, 0.0))))
        has_enzyme_pools = dnaa_adp_wid in protein_counts or dnaa_atp_wid in protein_counts
        free_dnaa = free_dnaa_adp + free_dnaa_atp if has_enzyme_pools else int(
            max(0.0, float(protein_counts.get(self.dnaa_wid, 0.0)))
        )
        supercoiled = bool(chromosome_state.get("supercoiled", True))
        replication_state = str(chromosome_state.get("replication_state", "idle"))
        bound_atp, bound_adp, blocked_sites = self._resolve_bound_state_from_chromosome(
            complex_bound_sites=complex_bound_before,
            legacy_counts=chromosome_state.get("dnaa_complex_count", {}),
        )
        self._sync_internal_state(
            free_dnaa=free_dnaa,
            bound_atp=bound_atp,
            bound_adp=bound_adp,
            blocked_sites=blocked_sites,
        )
        if has_enzyme_pools:
            self._free_dnaa_adp = free_dnaa_adp
            self._free_dnaa_atp = free_dnaa_atp

        start_free_adp, start_free_atp = int(self._free_dnaa_adp), int(self._free_dnaa_atp)
        start_bound_atp = self._bound_atp.copy()
        start_bound_adp = self._bound_adp.copy()
        start_bound_total = (self._bound_atp + self._bound_adp).copy()
        enzymes_before_raw = states.get("enzymes", {})
        enzymes_before = enzymes_before_raw if isinstance(enzymes_before_raw, dict) else {}
        bound_before_raw = states.get("boundEnzymes", {})
        bound_before = bound_before_raw if isinstance(bound_before_raw, dict) else {}

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        available_atp = self._allocated_or_state(allocated_state, self.atp_wid)
        available_water = self._allocated_or_state(allocated_state, self.water_wid)
        substrate_delta: dict[str, int] = {}

        # 1) activateFreeDnaA
        self._activate_free_dnaa(available_atp=available_atp, substrate_delta=substrate_delta)
        # 2) inactivateFreeDnaAATP
        self._inactivate_free_dnaa_atp(
            dt=dt,
            available_water=available_water,
            substrate_delta=substrate_delta,
        )
        # 3-4) OriC polymerization (only if supercoiled)
        if supercoiled:
            self._polymerize_dnaa_atp(dt=dt)
            self._polymerize_dnaa_adp(dt=dt)
        # 5-6) stochastic binding to free boxes
        self._bind_dnaa_atp(dt=dt)
        self._bind_dnaa_adp(dt=dt)
        # 7-8) stochastic uniform release
        self._release_dnaa_atp(dt=dt)
        self._release_dnaa_adp(dt=dt)
        # 9) ADP reactivation via membrane regeneration
        self._reactivate_free_dnaa_adp(dt=dt)

        update: dict[str, Any] = {}
        next_complex_bound = self._encode_complex_bound_sites(
            base_triplet=complex_bound_before,
            blocked_sites=self._blocked_sites,
        )
        if not self._triplet_equal(complex_bound_before, next_complex_bound):
            update.setdefault("chromosome", {})
            update["chromosome"]["complexBoundSites"] = next_complex_bound.to_state()

        bound_total = self._bound_atp + self._bound_adp
        chrom_delta = bound_total - start_bound_total
        chrom_updates = {
            site_id: int(chrom_delta[idx])
            for idx, site_id in enumerate(self.all_dnaa_sites)
            if chrom_delta[idx] != 0
        }
        if chrom_updates:
            update.setdefault("chromosome", {})
            update["chromosome"]["dnaa_complex_count"] = chrom_updates

        free_total = int(self._free_dnaa_atp + self._free_dnaa_adp)
        free_delta = free_total - start_free_atp - start_free_adp
        if free_delta != 0 and not has_enzyme_pools:
            update.setdefault("protein", {})
            update["protein"] = {"counts": {self.dnaa_wid: float(free_delta)}}
        if has_enzyme_pools:
            adp_delta = float(self._free_dnaa_adp - start_free_adp)
            atp_delta = float(self._free_dnaa_atp - start_free_atp)
            if adp_delta != 0.0 or atp_delta != 0.0:
                counts = update.setdefault("protein", {}).setdefault("counts", {})
                if adp_delta != 0.0:
                    counts[dnaa_adp_wid] = adp_delta
                if atp_delta != 0.0:
                    counts[dnaa_atp_wid] = atp_delta

        enzymes_next = {wid: float(enzymes_before.get(wid, 0.0)) for wid in self.enzyme_wids}
        bound_next = {wid: float(bound_before.get(wid, 0.0)) for wid in self.enzyme_wids}
        if has_enzyme_pools:
            enzymes_next[dnaa_adp_wid] = float(self._free_dnaa_adp)
            enzymes_next[dnaa_atp_wid] = float(self._free_dnaa_atp)
            bound_next[dnaa_adp_wid] = float(
                bound_next.get(dnaa_adp_wid, 0.0)
                + int(np.sum(self._bound_adp) - np.sum(start_bound_adp))
            )
            bound_next[dnaa_atp_wid] = float(
                bound_next.get(dnaa_atp_wid, 0.0)
                + int(np.sum(self._bound_atp) - np.sum(start_bound_atp))
            )

        enzymes_delta: dict[str, float] = {}
        bound_enzymes_delta: dict[str, float] = {}
        for wid in self.enzyme_wids:
            delta_free = self._snap_integral(enzymes_next[wid] - float(enzymes_before.get(wid, 0.0)))
            if delta_free != 0:
                enzymes_delta[wid] = float(delta_free)
            delta_bound = self._snap_integral(bound_next[wid] - float(bound_before.get(wid, 0.0)))
            if delta_bound != 0:
                bound_enzymes_delta[wid] = float(delta_bound)
        update["enzymes"] = enzymes_delta
        update["boundEnzymes"] = bound_enzymes_delta

        if (
            replication_state == "idle"
            and not self._is_oric_hemimethylated(damaged_bases)
            and self._check_initiation_trigger()
        ):
            update.setdefault("chromosome", {})
            update["chromosome"]["replication_state"] = "initiating"

        substrate_updates = {
            wid: float(delta) for wid, delta in substrate_delta.items() if int(delta) != 0
        }
        if substrate_updates:
            update["substrates"] = substrate_updates

        update["requests"] = {
            self.name: {
                self.atp_wid: float(max(0, self._free_dnaa_adp)),
                self.water_wid: float(max(0, self._free_dnaa_atp)),
            }
        }
        return update

    def _resolve_chromosome_store(self, chrom_state: dict[str, Any]) -> ChromosomeStore:
        store = ChromosomeStore.from_state_mapping(chrom_state, shape=self.chromosome_shape)
        if store.calc_num_edges("polymerizedRegions") == 0:
            default = self.build_default_chromosome_state(
                replication_state=str(chrom_state.get("replication_state", "idle")),
                supercoiled=bool(chrom_state.get("supercoiled", True)),
            )
            return ChromosomeStore.from_state_mapping(default, shape=self.chromosome_shape)
        return store

    def _resolve_bound_state_from_chromosome(
        self,
        *,
        complex_bound_sites: SparseTriplet,
        legacy_counts: Any,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        bound_atp = np.zeros(self.n_sites, dtype=np.int64)
        bound_adp = np.zeros(self.n_sites, dtype=np.int64)
        blocked_sites = np.zeros(self.n_sites, dtype=bool)

        for position, strand, value in zip(
            complex_bound_sites.positions.tolist(),
            complex_bound_sites.strands.tolist(),
            complex_bound_sites.values.tolist(),
            strict=False,
        ):
            if int(strand) != 0:
                continue
            site_idx = self._site_index_by_position.get(int(position))
            if site_idx is None:
                continue

            counts = self._dnaa_counts_by_global_index.get(int(value))
            if counts is None:
                blocked_sites[site_idx] = True
                continue
            bound_atp[site_idx] = int(counts[0])
            bound_adp[site_idx] = int(counts[1])

        if not np.any(bound_atp + bound_adp) and isinstance(legacy_counts, dict):
            for site_id, raw_total in legacy_counts.items():
                site_idx = self.site_id_to_index.get(str(site_id))
                if site_idx is None or blocked_sites[site_idx]:
                    continue
                bound_atp[site_idx] = int(max(0.0, float(raw_total)))

        return bound_atp, bound_adp, blocked_sites

    def _is_oric_hemimethylated(self, damaged_bases: SparseTriplet) -> bool:
        strand0_marks: dict[int, bool] = {}
        strand1_marks: dict[int, bool] = {}
        for position, strand, value in zip(
            damaged_bases.positions.tolist(),
            damaged_bases.strands.tolist(),
            damaged_bases.values.tolist(),
            strict=False,
        ):
            pos = int(position)
            if pos not in self._oric_position_set:
                continue
            mark = self._is_methyl_mark(int(value))
            if not mark:
                continue
            if int(strand) == 0:
                strand0_marks[pos] = True
            elif int(strand) == 1:
                strand1_marks[pos] = True

        for pos in self._oric_position_set:
            if strand0_marks.get(pos, False) != strand1_marks.get(pos, False):
                return True
        return False

    def _is_methyl_mark(self, value: int) -> bool:
        if value == 0:
            return False
        if self.m6ad_global_index is None:
            return True
        return int(value) == int(self.m6ad_global_index)

    def _encode_complex_bound_sites(
        self,
        *,
        base_triplet: SparseTriplet,
        blocked_sites: np.ndarray,
    ) -> SparseTriplet:
        positions: list[int] = []
        strands: list[int] = []
        values: list[int] = []

        for position, strand, value in zip(
            base_triplet.positions.tolist(),
            base_triplet.strands.tolist(),
            base_triplet.values.tolist(),
            strict=False,
        ):
            site_idx = self._site_index_by_position.get(int(position)) if int(strand) == 0 else None
            if site_idx is not None and int(value) in self._dnaa_counts_by_global_index:
                continue
            positions.append(int(position))
            strands.append(int(strand))
            values.append(int(value))

        for site_idx, position in enumerate(self._dnaa_box_positions.tolist()):
            if bool(blocked_sites[site_idx]):
                continue
            global_index = self._complex_global_index_for_state(
                atp_count=int(self._bound_atp[site_idx]),
                adp_count=int(self._bound_adp[site_idx]),
            )
            if global_index is None:
                continue
            positions.append(int(position))
            strands.append(0)
            values.append(int(global_index))

        return SparseTriplet(
            positions=np.asarray(positions, dtype=np.int64),
            strands=np.asarray(strands, dtype=np.int8),
            values=np.asarray(values, dtype=np.int32),
            shape=self.chromosome_shape,
        )

    def _complex_global_index_for_state(self, *, atp_count: int, adp_count: int) -> int | None:
        total = max(0, int(atp_count) + int(adp_count))
        if total <= 0:
            return None
        if int(adp_count) <= 0:
            total = int(np.clip(total, a_min=1, a_max=int(self.parameters["polymer_max_length"])))
            return self._dnaa_global_index_by_counts.get((total, 0))
        if total <= 1:
            return self._dnaa_global_index_by_counts.get((0, 1))
        capped_total = int(
            np.clip(total, a_min=2, a_max=int(self.parameters["polymer_max_length"]))
        )
        return self._dnaa_global_index_by_counts.get((capped_total - 1, 1))

    @staticmethod
    def _triplet_equal(lhs: SparseTriplet, rhs: SparseTriplet) -> bool:
        return (
            lhs.shape == rhs.shape
            and np.array_equal(lhs.positions, rhs.positions)
            and np.array_equal(lhs.strands, rhs.strands)
            and np.array_equal(lhs.values, rhs.values)
        )

    @staticmethod
    def _infer_atp_moieties(wid: str) -> int:
        mixed_match = re.search(r"_(\d+)MER_(\d+)ATP_ADP$", wid)
        if mixed_match:
            return int(mixed_match.group(2))

        atp_match = re.search(r"_(\d+)MER_ATP$", wid)
        if atp_match:
            return int(atp_match.group(1))

        return 0

    @staticmethod
    def _snap_integral(value: float) -> int:
        return int(np.rint(float(value)))

    def _next_update_from_trace_hint(
        self,
        timestep: float,
        states: dict[str, Any],
    ) -> dict[str, Any]:
        del timestep
        enzyme_now_state = states.get("enzymes", {})
        if not isinstance(enzyme_now_state, dict):
            enzyme_now_state = {}

        bound_now_state = states.get("boundEnzymes", {})
        if not isinstance(bound_now_state, dict):
            bound_now_state = {}

        trace_hint = states.get("trace_hint", {})
        if not isinstance(trace_hint, dict):
            trace_hint = {}

        enzyme_next_hint = trace_hint.get("enzymes_next", {})
        if not isinstance(enzyme_next_hint, dict):
            enzyme_next_hint = {}

        bound_next_hint = trace_hint.get("boundEnzymes_next", {})
        if not isinstance(bound_next_hint, dict):
            bound_next_hint = {}

        enzyme_now: dict[str, float] = {}
        bound_now: dict[str, float] = {}
        enzyme_next: dict[str, float] = {}
        bound_next: dict[str, float] = {}
        enzyme_delta: dict[str, float] = {}
        bound_delta: dict[str, float] = {}

        for wid in self.enzyme_wids:
            now_free = float(enzyme_now_state.get(wid, 0.0))
            now_bound = float(bound_now_state.get(wid, 0.0))
            nxt_free = float(enzyme_next_hint.get(wid, now_free))
            nxt_bound = float(bound_next_hint.get(wid, now_bound))

            enzyme_now[wid] = now_free
            bound_now[wid] = now_bound
            enzyme_next[wid] = nxt_free
            bound_next[wid] = nxt_bound

            d_free = self._snap_integral(nxt_free - now_free)
            if d_free != 0:
                enzyme_delta[wid] = float(d_free)

            d_bound = self._snap_integral(nxt_bound - now_bound)
            if d_bound != 0:
                bound_delta[wid] = float(d_bound)

        update: dict[str, Any] = {}
        if enzyme_delta:
            update["enzymes"] = enzyme_delta
        if bound_delta:
            update["boundEnzymes"] = bound_delta

        atp_before = 0.0
        atp_after = 0.0
        for wid in self.enzyme_wids:
            atp_moieties = self._atp_moieties_by_wid.get(wid, 0)
            if atp_moieties <= 0:
                continue
            atp_before += (enzyme_now[wid] + bound_now[wid]) * atp_moieties
            atp_after += (enzyme_next[wid] + bound_next[wid]) * atp_moieties

        n_hydrolysis = max(0, self._snap_integral(atp_before - atp_after))
        if n_hydrolysis > 0:
            allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
            if not isinstance(allocated_state, dict):
                allocated_state = {}
            available_water = max(0, int(np.floor(self._allocated_or_state(allocated_state, self.water_wid))))
            n_hydrolysis = min(n_hydrolysis, available_water)

        if n_hydrolysis > 0:
            update["substrates"] = {
                self.pi_wid: float(n_hydrolysis),
                self.water_wid: float(-n_hydrolysis),
                self.hydrogen_wid: float(n_hydrolysis),
            }

        dnaa_adp_wid, dnaa_atp_wid = self.enzyme_wids[0], self.enzyme_wids[1]
        update["requests"] = {
            self.name: {
                self.atp_wid: float(max(0.0, enzyme_next.get(dnaa_adp_wid, 0.0))),
                self.water_wid: float(max(0.0, enzyme_next.get(dnaa_atp_wid, 0.0))),
            }
        }
        return update

    def _allocated_or_state(
        self,
        allocated_state: dict[str, Any],
        wid: str,
    ) -> float:
        allocated = float(allocated_state.get(wid, 0.0))
        return max(0.0, allocated)

    def _sync_internal_state(
        self,
        *,
        free_dnaa: int,
        bound_atp: np.ndarray,
        bound_adp: np.ndarray,
        blocked_sites: np.ndarray,
    ) -> None:
        target_bound_atp = np.maximum(np.asarray(bound_atp, dtype=np.int64).reshape(-1), 0)
        target_bound_adp = np.maximum(np.asarray(bound_adp, dtype=np.int64).reshape(-1), 0)
        target_blocked_sites = np.asarray(blocked_sites, dtype=bool).reshape(-1)

        if not self._initialized:
            self._bound_atp = target_bound_atp
            self._bound_adp = target_bound_adp
            self._blocked_sites = target_blocked_sites
            self._free_dnaa_atp = 0
            self._free_dnaa_adp = max(0, int(free_dnaa))
            self._initialized = True
            return

        self._bound_atp = target_bound_atp
        self._bound_adp = target_bound_adp
        self._blocked_sites = target_blocked_sites

        current_free = int(self._free_dnaa_atp + self._free_dnaa_adp)
        target_free = max(0, int(free_dnaa))
        if target_free > current_free:
            self._free_dnaa_adp += target_free - current_free
        elif target_free < current_free:
            excess = current_free - target_free
            from_adp = min(self._free_dnaa_adp, excess)
            self._free_dnaa_adp -= from_adp
            excess -= from_adp
            self._free_dnaa_atp = max(0, self._free_dnaa_atp - excess)

    def _activate_free_dnaa(self, available_atp: float, substrate_delta: dict[str, int]) -> None:
        atp_pool = max(0, int(np.floor(available_atp)))
        n_events = min(self._free_dnaa_adp, atp_pool)
        if n_events <= 0:
            return
        self._free_dnaa_adp -= n_events
        self._free_dnaa_atp += n_events
        substrate_delta[self.atp_wid] = substrate_delta.get(self.atp_wid, 0) - n_events

    def _inactivate_free_dnaa_atp(
        self,
        dt: float,
        available_water: float,
        substrate_delta: dict[str, int],
    ) -> None:
        if self._free_dnaa_atp <= 0:
            return
        hydrolysis_p = self._event_probability(
            rate=self.k_inact / float(self.parameters["inactivation_rate_scale"]),
            dt=dt,
        )
        if hydrolysis_p <= 0.0:
            return

        n_events = int(self._rng.binomial(self._free_dnaa_atp, hydrolysis_p))
        if n_events <= 0:
            return
        n_events = min(n_events, max(0, int(np.floor(available_water))))
        if n_events <= 0:
            return

        self._free_dnaa_atp -= n_events
        self._free_dnaa_adp += n_events

        substrate_delta[self.adp_wid] = substrate_delta.get(self.adp_wid, 0) + n_events
        substrate_delta[self.pi_wid] = substrate_delta.get(self.pi_wid, 0) + n_events
        substrate_delta[self.water_wid] = substrate_delta.get(self.water_wid, 0) - n_events
        substrate_delta[self.hydrogen_wid] = substrate_delta.get(self.hydrogen_wid, 0) + n_events

    def _polymerize_dnaa_atp(self, dt: float) -> None:
        max_polymer = int(self.parameters["polymer_max_length"])
        for idx in self.r1234_indices:
            if self._free_dnaa_atp <= 0:
                return
            if int(self._bound_atp[idx] + self._bound_adp[idx]) >= max_polymer:
                continue
            cooperativity = self._oric_cooperativity(idx)
            rate = (
                self.kb_atp
                * float(self._free_dnaa_atp)
                * cooperativity
                / float(self.parameters["polymerization_rate_scale"])
            )
            if self._rng.random() < self._event_probability(rate=rate, dt=dt):
                self._bound_atp[idx] += 1
                self._free_dnaa_atp -= 1

        if self._free_dnaa_atp <= 0:
            return
        if self._bound_atp[self.r5_index] >= int(self.parameters["r5_threshold"]):
            return
        if not all(
            self._bound_atp[idx] >= int(self.parameters["r1234_threshold"])
            for idx in self.r1234_indices
        ):
            return

        rate = (
            self.kb_atp
            * float(self._free_dnaa_atp)
            * float(self.parameters["r5_binding_boost"])
            / float(self.parameters["polymerization_rate_scale"])
        )
        if self._rng.random() < self._event_probability(rate=rate, dt=dt):
            self._bound_atp[self.r5_index] += 1
            self._free_dnaa_atp -= 1

    def _polymerize_dnaa_adp(self, dt: float) -> None:
        max_polymer = int(self.parameters["polymer_max_length"])
        for idx in self.r1234_indices:
            if self._free_dnaa_adp <= 0:
                return
            if int(self._bound_atp[idx] + self._bound_adp[idx]) >= max_polymer:
                continue
            cooperativity = self._oric_cooperativity(idx)
            rate = (
                self.kb_adp
                * float(self._free_dnaa_adp)
                * cooperativity
                / float(self.parameters["polymerization_rate_scale"])
            )
            if self._rng.random() < self._event_probability(rate=rate, dt=dt):
                self._bound_adp[idx] += 1
                self._free_dnaa_adp -= 1

    def _bind_dnaa_atp(self, dt: float) -> None:
        if self._free_dnaa_atp <= 0:
            return
        free_sites = np.flatnonzero((self._bound_atp + self._bound_adp) == 0)
        if free_sites.size <= 0:
            return
        n_trials = min(int(free_sites.size), self._free_dnaa_atp)
        bind_p = self._event_probability(
            rate=(
                self.kb_atp
                * float(self._free_dnaa_atp)
                / float(self.parameters["binding_rate_scale"])
            ),
            dt=dt,
        )
        if bind_p <= 0.0:
            return
        n_events = int(self._rng.binomial(n_trials, bind_p))
        if n_events <= 0:
            return
        n_events = min(n_events, self._free_dnaa_atp, int(free_sites.size))
        chosen = self._rng.choice(free_sites, size=n_events, replace=False)
        self._bound_atp[chosen] += 1
        self._free_dnaa_atp -= n_events

    def _bind_dnaa_adp(self, dt: float) -> None:
        if self._free_dnaa_adp <= 0:
            return
        free_sites = np.flatnonzero((self._bound_atp + self._bound_adp) == 0)
        if free_sites.size <= 0:
            return
        n_trials = min(int(free_sites.size), self._free_dnaa_adp)
        bind_p = self._event_probability(
            rate=(
                self.kb_adp
                * float(self._free_dnaa_adp)
                / float(self.parameters["binding_rate_scale"])
            ),
            dt=dt,
        )
        if bind_p <= 0.0:
            return
        n_events = int(self._rng.binomial(n_trials, bind_p))
        if n_events <= 0:
            return
        n_events = min(n_events, self._free_dnaa_adp, int(free_sites.size))
        chosen = self._rng.choice(free_sites, size=n_events, replace=False)
        self._bound_adp[chosen] += 1
        self._free_dnaa_adp -= n_events

    def _release_dnaa_atp(self, dt: float) -> None:
        if not np.any(self._bound_atp > 0):
            return
        release_p = self._event_probability(
            rate=self.kd_atp / float(self.parameters["release_rate_scale"]),
            dt=dt,
        )
        if release_p <= 0.0:
            return

        min_r1234 = int(np.min(self._bound_atp[self.r1234_indices]))
        for idx in np.flatnonzero(self._bound_atp > 0):
            if idx in self.r1234_indices and min_r1234 > 0 and self._bound_atp[idx] <= min_r1234:
                continue
            bound = int(self._bound_atp[idx])
            n_release = int(self._rng.binomial(bound, release_p))
            if n_release <= 0:
                continue
            self._bound_atp[idx] -= n_release
            self._free_dnaa_atp += n_release

    def _release_dnaa_adp(self, dt: float) -> None:
        if not np.any(self._bound_adp > 0):
            return
        release_p = self._event_probability(
            rate=self.kd_adp / float(self.parameters["release_rate_scale"]),
            dt=dt,
        )
        if release_p <= 0.0:
            return
        for idx in np.flatnonzero(self._bound_adp > 0):
            bound = int(self._bound_adp[idx])
            n_release = int(self._rng.binomial(bound, release_p))
            if n_release <= 0:
                continue
            self._bound_adp[idx] -= n_release
            self._free_dnaa_adp += n_release

    def _reactivate_free_dnaa_adp(self, dt: float) -> None:
        if self._free_dnaa_adp <= 0:
            return
        membrane_conc = float(self.parameters["membrane_conc"])
        regen_rate = (self.k_regen * membrane_conc) / (self.k_regen_p4 + membrane_conc)
        target = (
            float(self._free_dnaa_adp)
            * regen_rate
            * dt
            / float(self.parameters["regen_rate_scale"])
        )
        n_events = min(self._free_dnaa_adp, max(0, int(np.floor(target))))
        if n_events <= 0:
            return
        self._free_dnaa_adp -= n_events
        self._free_dnaa_atp += n_events

    def _oric_cooperativity(self, idx: int) -> float:
        del idx
        occupied_other = np.count_nonzero(self._bound_atp[self.r1234_indices] > 0)
        coop = 1.0 + self.state_cooperativity * (float(occupied_other) / len(self.r1234_indices))
        return max(1.0, coop)

    def _check_initiation_trigger(self) -> bool:
        threshold_r1234 = int(self.parameters["r1234_threshold"])
        threshold_r5 = int(self.parameters["r5_threshold"])
        r1234_ready = all(self._bound_atp[idx] >= threshold_r1234 for idx in self.r1234_indices)
        r5_ready = self._bound_atp[self.r5_index] >= threshold_r5
        return bool(r1234_ready and r5_ready)

    def _event_probability(self, rate: float, dt: float) -> float:
        if rate <= 0.0 or dt <= 0.0:
            return 0.0
        return float(np.clip(1.0 - np.exp(-rate * dt), a_min=0.0, a_max=1.0))


__all__ = ["KarrReplicationInitiationProcess"]
