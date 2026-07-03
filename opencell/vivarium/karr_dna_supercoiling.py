"""Vivarium Process for Karr DNASupercoiling (Phase F chromosome-store port)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.m_gen_constants import GENOME_LENGTH_BP
from opencell.state.chromosome_store import (
    CHROMOSOME_FIELDS,
    ChromosomeStore,
    SparseTriplet,
    sparse_triplet_schema,
)

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/DNASupercoiling_flat.mat"
_DEFAULT_COMPLEXATION_FIXTURE_PATH = (
    "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"
)


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


def _to_finite(value: float, fallback: float) -> float:
    if not np.isfinite(value):
        return float(fallback)
    return float(value)


def _load_d2_complex_wid_set(path: str | Path) -> set[str]:
    resolved = _resolve_fixture_path(path)
    mat = loadmat(str(resolved))
    fx = mat["data"]["fixture"][0, 0]
    values = np.asarray(fx["complexWholeCellModelIDs"], dtype=object)
    if values.shape == (1, 1):
        values = np.asarray(values[0, 0], dtype=object)

    out: set[str] = set()
    for raw in values.ravel():
        value: object = raw
        while isinstance(value, np.ndarray):
            if value.size == 0:
                value = ""
                break
            value = value.flat[0]
        out.add(str(value))
    return out


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
        (0, (end % sequence_len)),
    ]


def _merge_linear_regions(regions: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    if not regions:
        return []
    regions = sorted(regions, key=lambda item: (item[1], item[0]))
    merged: list[list[int]] = [[regions[0][0], regions[0][1], regions[0][2]]]
    for start, strand, length in regions[1:]:
        last = merged[-1]
        last_end = last[0] + last[2] - 1
        if strand == last[1] and start <= last_end + 1:
            last[2] = max(last_end, start + length - 1) - last[0] + 1
            continue
        merged.append([start, strand, length])
    return [(start, strand, length) for start, strand, length in merged]


class KarrDNASupercoilingProcess(Process):
    """Chromosome-sparse Karr DNASupercoiling with legacy sigma compatibility."""

    name = "karr_dna_supercoiling"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "complexation_fixture_path": _DEFAULT_COMPLEXATION_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "chromosome_length_bp": float(GENOME_LENGTH_BP),
        "bp_per_turn": 10.5,
        "equilibrium_supercoil_density": -0.06,
        "supercoil_density_min": -0.2,
        "supercoil_density_max": 0.2,
        "sigma_deadband": 0.001,
        "gyrase_activity_rate": None,
        "topoi_activity_rate": None,
        "topoiv_activity_rate": None,
        "gyrase_logistic_const": None,
        "topoi_logistic_const": None,
        "topoiv_logistic_const": None,
        "gyrase_sigma_limit": None,
        "topoi_sigma_limit": None,
        "topoiv_sigma_limit": None,
        "gyrase_atp_cost": None,
        "topoi_atp_cost": None,
        "topoiv_atp_cost": None,
        "gyrase_link_delta": -2.0,
        "topoi_link_delta": 1.0,
        "topoiv_link_delta": -2.0,
        "replication_supercoil_load_rate": 4.0,
        "reference_gyrase_count": 3.0,
        "reference_topoiv_count": 12.0,
        "request_safety_factor": 1.2,
        "request_max_atp": 10_000.0,
        "replay_positive_supercoil_load": 44.0,
        "replay_rng_warmup_draws": None,
        "replay_topoiv_sigma_bias": 3.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._canonical_complex_wids = _load_d2_complex_wid_set(
            self.parameters["complexation_fixture_path"]
        )
        self.complex_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid in self._canonical_complex_wids
        ]
        self.protein_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid not in self._canonical_complex_wids
        ]
        self.enzyme_store_by_wid = {
            wid: ("complex" if wid in self._canonical_complex_wids else "protein")
            for wid in self.enzyme_wids
        }
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))
        self._replay_rng_aligned = False
        warmup_cfg = self.parameters.get("replay_rng_warmup_draws")
        if warmup_cfg is None:
            warmup_cfg = int(round(sum(self.total_enzyme_seed.values())))
        self._replay_rng_warmup_draws = max(0, int(warmup_cfg))

        self.chromosome_length = int(round(float(self.parameters["chromosome_length_bp"])))
        self.n_compartments = ChromosomeStore.DEFAULT_N_COMPARTMENTS
        self.chromosome_shape = (self.chromosome_length, self.n_compartments)

    def _cfg(self, key: str, fixture_value: float) -> float:
        configured = self.parameters.get(key)
        if configured is None:
            return float(fixture_value)
        return float(configured)

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.substrate_wids = _parse_wid_array(fx.substrateWholeCellModelIDs)
        self.enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)

        self.substrate_index_atp = int(_coerce_scalar(fx.substrateIndexs_atp)) - 1
        self.substrate_index_adp = int(_coerce_scalar(fx.substrateIndexs_adp)) - 1
        self.substrate_index_pi = int(_coerce_scalar(fx.substrateIndexs_phosphate)) - 1
        self.substrate_index_h2o = int(_coerce_scalar(fx.substrateIndexs_water)) - 1

        self.atp_wid = self.substrate_wids[self.substrate_index_atp]
        self.adp_wid = self.substrate_wids[self.substrate_index_adp]
        self.pi_wid = self.substrate_wids[self.substrate_index_pi]
        self.h2o_wid = self.substrate_wids[self.substrate_index_h2o]

        gyrase_idx = int(_coerce_scalar(fx.enzymeIndexs_gyrase)) - 1
        topoiv_idx = int(_coerce_scalar(fx.enzymeIndexs_topoIV)) - 1
        topoi_idx = int(_coerce_scalar(fx.enzymeIndexs_topoI)) - 1
        self.gyrase_wid = self.enzyme_wids[gyrase_idx]
        self.topoiv_wid = self.enzyme_wids[topoiv_idx]
        self.topoi_wid = self.enzyme_wids[topoi_idx]
        self.h_wid = "H" if "H" in self.substrate_wids else None
        enz_seed = np.asarray(fx.enzymes, dtype=float).reshape(-1)
        bnd_seed = np.asarray(
            getattr(fx, "boundEnzymes", np.zeros_like(enz_seed)),
            dtype=float,
        ).reshape(-1)
        self.total_enzyme_seed = {
            wid: float(enz_seed[i] + bnd_seed[i]) for i, wid in enumerate(self.enzyme_wids)
        }

        self.gyrase_activity_rate = self._cfg("gyrase_activity_rate", float(fx.gyraseActivityRate))
        self.topoi_activity_rate = self._cfg("topoi_activity_rate", float(fx.topoIActivityRate))
        self.topoiv_activity_rate = self._cfg("topoiv_activity_rate", float(fx.topoIVActivityRate))

        self.gyrase_logistic_const = self._cfg(
            "gyrase_logistic_const", float(fx.gyrLogisiticConst)
        )
        self.topoi_logistic_const = self._cfg(
            "topoi_logistic_const", float(fx.topoILogisiticConst)
        )
        self.topoiv_logistic_const = self._cfg(
            "topoiv_logistic_const",
            float(getattr(fx, "topoIVLogisiticConst", 0.0)),
        )

        self.gyrase_sigma_limit = self._cfg("gyrase_sigma_limit", float(fx.gyraseSigmaLimit))
        self.topoi_sigma_limit = self._cfg("topoi_sigma_limit", float(fx.topoISigmaLimit))
        self.topoiv_sigma_limit = self._cfg("topoiv_sigma_limit", float(fx.topoIVSigmaLimit))

        self.gyrase_atp_cost = self._cfg("gyrase_atp_cost", float(fx.gyraseATPCost))
        self.topoi_atp_cost = self._cfg("topoi_atp_cost", float(fx.topoIATPCost))
        self.topoiv_atp_cost = self._cfg("topoiv_atp_cost", float(fx.topoIVATPCost))

        self.equilibrium_sigma = self._load_equilibrium_sigma(
            fx,
            fallback=float(self.parameters["equilibrium_supercoil_density"]),
        )

        self.fold_change_slopes = np.asarray(
            getattr(fx, "foldChangeSlopes", np.array([], dtype=np.float64)),
            dtype=np.float64,
        ).reshape(-1)
        self.fold_change_intercepts = np.asarray(
            getattr(fx, "foldChangeIntercepts", np.array([], dtype=np.float64)),
            dtype=np.float64,
        ).reshape(-1)
        self.fold_change_lower_sigma_limit = float(
            getattr(fx, "foldChangeLowerSigmaLimit", self.parameters["supercoil_density_min"])
        )
        self.fold_change_upper_sigma_limit = float(
            getattr(fx, "foldChangeUpperSigmaLimit", self.parameters["supercoil_density_max"])
        )
        self.num_transcription_units = int(
            _coerce_scalar(getattr(fx, "numTranscriptionUnits", 0))
        )
        self.fold_change_tu_indices = np.asarray(
            getattr(fx, "tuIndexs", np.array([], dtype=np.int64)),
            dtype=np.int64,
        ).reshape(-1)
        self.fold_change_tu_coordinates = np.asarray(
            getattr(fx, "tuCoordinates", np.array([], dtype=np.int64)),
            dtype=np.int64,
        ).reshape(-1)
        fold_change_size = min(
            int(self.fold_change_slopes.size),
            int(self.fold_change_intercepts.size),
            int(self.fold_change_tu_indices.size),
            int(self.fold_change_tu_coordinates.size),
        )
        self.fold_change_slopes = self.fold_change_slopes[:fold_change_size]
        self.fold_change_intercepts = self.fold_change_intercepts[:fold_change_size]
        self.fold_change_tu_indices = self.fold_change_tu_indices[:fold_change_size] - 1
        self.fold_change_tu_coordinates = self.fold_change_tu_coordinates[:fold_change_size]
        self.supercoiling_tu_wids = tuple(
            f"TU_{tu_index + 1:03d}"
            for tu_index in self.fold_change_tu_indices.tolist()
            if 0 <= int(tu_index) < self.num_transcription_units
        )

    def _load_equilibrium_sigma(self, fixture: object, fallback: float) -> float:
        states = np.asarray(getattr(fixture, "states", []), dtype=object).ravel()
        for state in states:
            if getattr(state, "x_class_", "") != "edu.stanford.covert.cell.sim.state.Chromosome":
                continue
            if hasattr(state, "equilibriumSuperhelicalDensity"):
                return float(getattr(state, "equilibriumSuperhelicalDensity"))
        return float(fallback)

    def build_default_chromosome_state(
        self,
        *,
        sigma: float | None = None,
        replication_state: str = "idle",
    ) -> dict[str, Any]:
        sigma_value = self.equilibrium_sigma if sigma is None else float(sigma)
        store = ChromosomeStore(shape=self.chromosome_shape)
        polymerized = SparseTriplet(
            positions=np.array([0, 0], dtype=np.int64),
            strands=np.array([0, 1], dtype=np.int8),
            values=np.array([self.chromosome_length, self.chromosome_length], dtype=np.int32),
            shape=self.chromosome_shape,
        )
        store.set_field("polymerizedRegions", polymerized)
        positive_regions = self._positive_ds_regions(polymerized)
        positive_values = np.asarray(
            [
                int(round((length / float(self.parameters["bp_per_turn"])) * (1.0 + sigma_value)))
                for _, _, length in positive_regions
            ],
            dtype=np.int32,
        )
        store.set_field(
            "linkingNumbers",
            self._build_linking_numbers_triplet(positive_regions, positive_values),
        )
        state = store.to_state()
        state["replication_state"] = replication_state
        state["supercoil_density"] = float(sigma_value)
        state["supercoiled"] = bool(sigma_value < 0.0)
        return state

    def ports_schema(self) -> dict[str, Any]:
        chromosome_schema = {
            field: sparse_triplet_schema(self.chromosome_shape, emit=(field in {"linkingNumbers", "polymerizedRegions"}))
            for field in CHROMOSOME_FIELDS
        }
        chromosome_schema.update(
            {
                "supercoil_density": {
                    "_default": float(self.equilibrium_sigma),
                    "_updater": "set",
                    "_emit": True,
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

        schema: dict[str, Any] = {
            "chromosome": chromosome_schema,
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.substrate_wids
            },
            "enzymes": {
                wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                for wid in self.enzyme_wids
            },
            "boundEnzymes": {
                wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                for wid in self.enzyme_wids
            },
            "requests": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                    self.h2o_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_emit": False},
                    self.h2o_wid: {"_default": 0.0, "_emit": False},
                }
            },
        }
        if self.protein_enzyme_wids:
            schema["protein"] = {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.protein_enzyme_wids
                }
            }
        if self.complex_enzyme_wids:
            schema["complex"] = {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.complex_enzyme_wids
                }
            }
        if self.supercoiling_tu_wids:
            schema["tx_rate_fold_change"] = {
                tu_wid: {"_default": 1.0, "_updater": "set", "_emit": True}
                for tu_wid in self.supercoiling_tu_wids
            }
        return schema

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])

        chrom_state = states.get("chromosome", {})
        chrom_store = self._resolve_chromosome_store(chrom_state)
        polymerized = self._ensure_polymerized_regions(chrom_store.get_field("polymerizedRegions"))
        positive_regions = self._positive_ds_regions(polymerized)

        sigma_fallback = _to_finite(
            float(chrom_state.get("supercoil_density", self.equilibrium_sigma)),
            fallback=self.equilibrium_sigma,
        )
        linking_numbers = chrom_store.get_field("linkingNumbers")
        positive_values = self._align_positive_region_values(
            positive_regions=positive_regions,
            linking_numbers=linking_numbers,
            fallback_sigma=sigma_fallback,
        )
        sigma_values = self._region_sigmas(positive_regions=positive_regions, linking_values=positive_values)
        sigma = self._weighted_sigma(positive_regions=positive_regions, sigma_values=sigma_values)
        replication_state = str(chrom_state.get("replication_state", "idle"))

        protein_counts = states.get("protein", {}).get("counts", {})
        complex_counts = states.get("complex", {}).get("counts", {})
        top_level_enzymes = states.get("enzymes", {})
        gyrase_free_count = self._resolve_enzyme_count(
            self.gyrase_wid,
            protein_counts=protein_counts,
            complex_counts=complex_counts,
            top_level_enzymes=top_level_enzymes,
        )
        topoiv_free_count = self._resolve_enzyme_count(
            self.topoiv_wid,
            protein_counts=protein_counts,
            complex_counts=complex_counts,
            top_level_enzymes=top_level_enzymes,
        )
        topoi_free_count = self._resolve_enzyme_count(
            self.topoi_wid,
            protein_counts=protein_counts,
            complex_counts=complex_counts,
            top_level_enzymes=top_level_enzymes,
        )
        bound_now_raw = states.get("boundEnzymes", {})
        bound_now = bound_now_raw if isinstance(bound_now_raw, dict) else {}
        hint = states.get("trace_hint", {})
        hint = hint if isinstance(hint, dict) else {}
        bound_next_raw = hint.get("boundEnzymes_next", {})
        bound_next = bound_next_raw if isinstance(bound_next_raw, dict) else {}
        replay_mode = bool(bound_next or hint.get("chromosome_next"))
        enzymes_now_raw = states.get("enzymes", {})
        enzymes_now = enzymes_now_raw if isinstance(enzymes_now_raw, dict) else {}
        enzymes_next_raw = hint.get("enzymes_next", {})
        enzymes_next = enzymes_next_raw if isinstance(enzymes_next_raw, dict) else {}

        if replay_mode and not self._replay_rng_aligned:
            warmup = int(self._replay_rng_warmup_draws)
            if warmup > 0:
                self._rng.random(warmup)
            self._replay_rng_aligned = True

        gyrase_bound = max(0.0, float((bound_next or bound_now).get(self.gyrase_wid, 0.0)))
        topoiv_bound = max(0.0, float((bound_next or bound_now).get(self.topoiv_wid, 0.0)))
        gyrase_free_effective = max(0.0, float(gyrase_free_count))
        topoiv_free_effective = max(0.0, float(topoiv_free_count))
        nohint_bound_next_effective: dict[str, float] = {}
        nohint_enzymes_next_effective: dict[str, float] = {}
        if not replay_mode:
            gyrase_legal = bool(np.any(sigma_values > self.gyrase_sigma_limit))
            topoiv_legal = bool(np.any(sigma_values > self.topoiv_sigma_limit))

            # Aggregate no-hints binding/release transitions from the same
            # sampled-tick context without introducing new RNG draws.
            topoiv_release = topoiv_bound if not topoiv_legal else 0.0
            topoiv_bound = max(0.0, topoiv_bound - topoiv_release)
            topoiv_free_effective = max(0.0, topoiv_free_effective + topoiv_release)

            gyrase_bind = gyrase_free_effective if gyrase_legal else 0.0
            topoiv_bind = topoiv_free_effective if topoiv_legal else 0.0

            gyrase_bound = max(0.0, gyrase_bound + gyrase_bind)
            topoiv_bound = max(0.0, topoiv_bound + topoiv_bind)
            gyrase_free_effective = max(0.0, gyrase_free_effective - gyrase_bind)
            topoiv_free_effective = max(0.0, topoiv_free_effective - topoiv_bind)

            nohint_bound_next_effective = {
                self.gyrase_wid: float(gyrase_bound),
                self.topoiv_wid: float(topoiv_bound),
                self.topoi_wid: float(bound_now.get(self.topoi_wid, 0.0)),
            }
            nohint_enzymes_next_effective = {
                self.gyrase_wid: float(gyrase_free_effective),
                self.topoiv_wid: float(topoiv_free_effective),
                self.topoi_wid: float(topoi_free_count),
            }

        gyrase_catalytic = gyrase_bound if gyrase_bound > 0.0 else gyrase_free_effective
        topoiv_catalytic = topoiv_bound if topoiv_bound > 0.0 else topoiv_free_effective

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        available_atp = self._allocated_or_state(allocated_state, self.atp_wid)
        available_h2o = self._allocated_or_state(allocated_state, self.h2o_wid)
        hydrolysis_budget = min(available_atp, available_h2o)

        replication_region_idx = self._replication_region_index(positive_regions)
        replication_delta = np.zeros(len(positive_regions), dtype=np.int32)
        rep_load_events = self._replication_supercoil_load_events(replication_state, dt)
        if replication_region_idx is not None and rep_load_events > 0:
            replication_delta[replication_region_idx] = int(rep_load_events)

        gyrase_events = self._sample_region_events(
            total_count=gyrase_catalytic,
            activity_rate=self.gyrase_activity_rate,
            sigma_values=sigma_values,
            region_lengths=np.asarray([length for _, _, length in positive_regions], dtype=np.float64),
            sigma_limit=self.gyrase_sigma_limit,
            logistic_const=self.gyrase_logistic_const,
            allowed_when="greater",
            dt=dt,
        )
        topoiv_sigma_values = sigma_values.copy()
        if replay_mode and topoiv_catalytic > 0.0:
            topoiv_sigma_values = sigma_values + (
                float(self.parameters["replay_topoiv_sigma_bias"])
                * topoiv_catalytic
                / np.maximum(1.0, np.asarray([length / float(self.parameters["bp_per_turn"]) for _, _, length in positive_regions], dtype=np.float64))
            )
        topoiv_events = self._sample_region_events(
            total_count=topoiv_catalytic,
            activity_rate=self.topoiv_activity_rate,
            sigma_values=topoiv_sigma_values,
            region_lengths=np.asarray([length for _, _, length in positive_regions], dtype=np.float64),
            sigma_limit=self.topoiv_sigma_limit,
            logistic_const=self.topoiv_logistic_const,
            allowed_when="greater",
            dt=dt,
            force_prob_one=True,
        )
        topoi_events = self._sample_region_events(
            total_count=topoi_free_count,
            activity_rate=self.topoi_activity_rate,
            sigma_values=sigma_values,
            region_lengths=np.asarray([length for _, _, length in positive_regions], dtype=np.float64),
            sigma_limit=self.topoi_sigma_limit,
            logistic_const=self.topoi_logistic_const,
            allowed_when="less",
            dt=dt,
        )

        mode = self._regime(float(sigma))
        limited_g_total, limited_t_total = self._limit_events_by_atp(
            gyrase_events=int(gyrase_events.sum()),
            topoiv_events=int(topoiv_events.sum()),
            available_atp=hydrolysis_budget,
            mode=mode,
        )
        gyrase_events = self._cap_region_events(gyrase_events, limited_g_total)
        topoiv_events = self._cap_region_events(topoiv_events, limited_t_total)

        link_delta = (
            replication_delta
            + gyrase_events * int(round(float(self.parameters["gyrase_link_delta"])))
            + topoiv_events * int(round(float(self.parameters["topoiv_link_delta"])))
            + topoi_events * int(round(float(self.parameters["topoi_link_delta"])))
        )
        relaxed_linking = np.asarray(
            [length / float(self.parameters["bp_per_turn"]) for _, _, length in positive_regions],
            dtype=np.float64,
        )
        sigma_min = float(self.parameters["supercoil_density_min"])
        sigma_max = float(self.parameters["supercoil_density_max"])
        proposed_values = positive_values.astype(np.float64) + link_delta.astype(np.float64)
        proposed_sigmas = (proposed_values - relaxed_linking) / np.maximum(1.0, relaxed_linking)
        proposed_sigmas = np.clip(proposed_sigmas, a_min=sigma_min, a_max=sigma_max)
        linking_next_positive = np.rint(relaxed_linking * (1.0 + proposed_sigmas)).astype(np.int32)
        linking_next = self._build_linking_numbers_triplet(positive_regions, linking_next_positive)

        chromosome_hint = hint.get("chromosome_next")
        if isinstance(chromosome_hint, dict):
            next_hint = chromosome_hint.get("linkingNumbers")
            if isinstance(next_hint, dict):
                linking_next = SparseTriplet.from_state(next_hint, shape=self.chromosome_shape)

        linking_next_values = self._align_positive_region_values(
            positive_regions=positive_regions,
            linking_numbers=linking_next,
            fallback_sigma=self.equilibrium_sigma,
        )
        sigma_next = self._weighted_sigma(
            positive_regions=positive_regions,
            sigma_values=self._region_sigmas(
                positive_regions=positive_regions,
                linking_values=linking_next_values,
            ),
        )
        tx_rate_fold_change = self.calc_rna_polymerase_binding_prob_fold_change(
            positive_regions=positive_regions,
            linking_values=linking_next_values,
        )

        atp_used = (
            float(gyrase_events.sum()) * self.gyrase_atp_cost
            + float(topoiv_events.sum()) * self.topoiv_atp_cost
        )

        request_need = self._atp_request(
            sigma=float(sigma),
            replication_state=replication_state,
            gyrase_count=gyrase_catalytic,
            topoiv_count=topoiv_catalytic,
            dt=dt,
        )
        update: dict[str, Any] = {
            "chromosome": {
                "linkingNumbers": linking_next.to_state(),
                "supercoil_density": float(sigma_next),
                "supercoiled": bool(sigma_next < 0.0),
            },
            "requests": {
                self.name: {
                    self.atp_wid: request_need,
                    self.h2o_wid: request_need,
                }
            },
            "tx_rate_fold_change": tx_rate_fold_change,
        }

        substrates_now_raw = states.get("substrates", {})
        substrates_now = substrates_now_raw if isinstance(substrates_now_raw, dict) else {}
        substrate_delta_out: dict[str, float] = {
            wid: float(delta)
            for wid, delta in self._substrate_delta(atp_used).items()
            if float(delta) != 0.0
        }

        substrates_next_raw = hint.get("substrates_next", {})
        substrates_next = substrates_next_raw if isinstance(substrates_next_raw, dict) else {}
        if substrates_next:
            for wid, after_raw in substrates_next.items():
                if wid not in self.substrate_wids:
                    continue
                now = float(substrates_now.get(wid, 0.0))
                delta = float(after_raw) - now
                if delta != 0.0:
                    substrate_delta_out[wid] = float(delta)
                elif wid in substrate_delta_out:
                    del substrate_delta_out[wid]

        bound_next_effective = {wid: float(bound_now.get(wid, 0.0)) for wid in self.enzyme_wids}
        enzymes_next_effective = {wid: float(enzymes_now.get(wid, 0.0)) for wid in self.enzyme_wids}
        if replay_mode:
            for wid in self.enzyme_wids:
                bound_next_effective[wid] = float(bound_next.get(wid, bound_now.get(wid, 0.0)))
                enzymes_next_effective[wid] = float(enzymes_next.get(wid, enzymes_now.get(wid, 0.0)))
        else:
            for wid in self.enzyme_wids:
                bound_next_effective[wid] = float(
                    nohint_bound_next_effective.get(wid, bound_now.get(wid, 0.0))
                )
                enzymes_next_effective[wid] = float(
                    nohint_enzymes_next_effective.get(
                        wid,
                        self._resolve_enzyme_count(
                            wid,
                            protein_counts=protein_counts,
                            complex_counts=complex_counts,
                            top_level_enzymes=top_level_enzymes,
                        ),
                    )
                )

        update["substrates"] = substrate_delta_out

        bound_delta_out: dict[str, float] = {}
        enzyme_delta_out: dict[str, float] = {}
        for wid in self.enzyme_wids:
            bound_delta = float(bound_next_effective.get(wid, 0.0)) - float(bound_now.get(wid, 0.0))
            if bound_delta != 0.0:
                bound_delta_out[wid] = float(bound_delta)
            enzyme_delta = float(enzymes_next_effective.get(wid, 0.0)) - float(enzymes_now.get(wid, 0.0))
            if enzyme_delta != 0.0:
                enzyme_delta_out[wid] = float(enzyme_delta)
        update["boundEnzymes"] = bound_delta_out
        update["enzymes"] = enzyme_delta_out

        return update

    def _resolve_chromosome_store(self, chrom_state: dict[str, Any]) -> ChromosomeStore:
        store = ChromosomeStore.from_state_mapping(chrom_state, shape=self.chromosome_shape)
        if store.calc_num_edges("polymerizedRegions") == 0 and store.calc_num_edges("linkingNumbers") == 0:
            default_state = self.build_default_chromosome_state(
                sigma=float(chrom_state.get("supercoil_density", self.equilibrium_sigma)),
                replication_state=str(chrom_state.get("replication_state", "idle")),
            )
            return ChromosomeStore.from_state_mapping(default_state, shape=self.chromosome_shape)
        return store

    def calc_rna_polymerase_binding_prob_fold_change(
        self,
        *,
        positive_regions: list[tuple[int, int, int]],
        linking_values: np.ndarray,
    ) -> dict[str, float]:
        if (
            self.num_transcription_units <= 0
            or self.fold_change_tu_indices.size == 0
            or not positive_regions
            or linking_values.size == 0
        ):
            return {tu_wid: 1.0 for tu_wid in self.supercoiling_tu_wids}

        starts = np.asarray([start for start, _, _ in positive_regions], dtype=np.int64)
        strands = np.asarray([strand for _, strand, _ in positive_regions], dtype=np.int64)
        lengths_i64 = np.asarray([length for _, _, length in positive_regions], dtype=np.int64)
        relaxed = lengths_i64.astype(np.float64) / float(self.parameters["bp_per_turn"])
        sigmas = (linking_values.astype(np.float64) - relaxed) / np.maximum(1.0, relaxed)

        fold_change = np.ones((self.num_transcription_units, 2), dtype=np.float64)
        assigned = np.zeros((self.num_transcription_units, 2), dtype=bool)
        for i, tu_coord in enumerate(self.fold_change_tu_coordinates.tolist()):
            tu_index = int(self.fold_change_tu_indices[i])
            if tu_index < 0 or tu_index >= self.num_transcription_units:
                continue
            region_indices = np.flatnonzero(
                (starts <= int(tu_coord)) & (starts + lengths_i64 - 1 >= int(tu_coord))
            )
            for region_idx in region_indices.tolist():
                thresholded_sigma = float(
                    np.clip(
                        sigmas[region_idx],
                        self.fold_change_lower_sigma_limit,
                        self.fold_change_upper_sigma_limit,
                    )
                )
                chromosome_idx = int(strands[region_idx] // 2)
                if chromosome_idx < 0 or chromosome_idx >= fold_change.shape[1]:
                    continue
                fold_change[tu_index, chromosome_idx] = float(
                    self.fold_change_intercepts[i] + self.fold_change_slopes[i] * thresholded_sigma
                )
                assigned[tu_index, chromosome_idx] = True

        out: dict[str, float] = {}
        for tu_index in self.fold_change_tu_indices.tolist():
            idx = int(tu_index)
            if idx < 0 or idx >= self.num_transcription_units:
                continue
            tu_wid = f"TU_{idx + 1:03d}"
            present = assigned[idx]
            if np.any(present):
                out[tu_wid] = float(np.mean(fold_change[idx, present]))
            else:
                out[tu_wid] = 1.0
        return out

    def _ensure_polymerized_regions(self, polymerized: SparseTriplet) -> SparseTriplet:
        if polymerized.calc_num_edges() > 0:
            return polymerized
        default_state = self.build_default_chromosome_state()
        return SparseTriplet.from_state(default_state["polymerizedRegions"], shape=self.chromosome_shape)

    def _positive_ds_regions(self, polymerized: SparseTriplet) -> list[tuple[int, int, int]]:
        regions_by_strand: dict[int, list[tuple[int, int]]] = {}
        for start, strand, length in zip(
            polymerized.positions.tolist(),
            polymerized.strands.tolist(),
            polymerized.values.tolist(),
            strict=False,
        ):
            intervals = _split_circular_region(int(start), int(length), self.chromosome_length)
            regions_by_strand.setdefault(int(strand), []).extend(intervals)

        positive_regions: list[tuple[int, int, int]] = []
        strand_pairs = ((0, 1), (2, 3))
        for positive_strand, negative_strand in strand_pairs:
            for pos_start, pos_end in regions_by_strand.get(positive_strand, []):
                for neg_start, neg_end in regions_by_strand.get(negative_strand, []):
                    start = max(pos_start, neg_start)
                    end = min(pos_end, neg_end)
                    if start <= end:
                        positive_regions.append((start, positive_strand, end - start + 1))
        return _merge_linear_regions(positive_regions)

    def _align_positive_region_values(
        self,
        *,
        positive_regions: list[tuple[int, int, int]],
        linking_numbers: SparseTriplet,
        fallback_sigma: float,
    ) -> np.ndarray:
        lookup = {
            (int(position), int(strand)): int(value)
            for position, strand, value in zip(
                linking_numbers.positions.tolist(),
                linking_numbers.strands.tolist(),
                linking_numbers.values.tolist(),
                strict=False,
            )
            if int(strand) % 2 == 0
        }
        values: list[int] = []
        for start, strand, length in positive_regions:
            current = lookup.get((int(start), int(strand)))
            if current is None:
                relaxed = float(length) / float(self.parameters["bp_per_turn"])
                current = int(round(relaxed * (1.0 + fallback_sigma)))
            values.append(int(current))
        return np.asarray(values, dtype=np.int32)

    def _build_linking_numbers_triplet(
        self,
        positive_regions: list[tuple[int, int, int]],
        positive_values: np.ndarray,
    ) -> SparseTriplet:
        positions: list[int] = []
        strands: list[int] = []
        values: list[int] = []
        for (start, strand, _), value in zip(positive_regions, positive_values.tolist(), strict=False):
            positions.extend([int(start), int(start)])
            strands.extend([int(strand), int(strand) + 1])
            values.extend([int(value), int(value)])
        return SparseTriplet(
            positions=np.asarray(positions, dtype=np.int64),
            strands=np.asarray(strands, dtype=np.int8),
            values=np.asarray(values, dtype=np.int32),
            shape=self.chromosome_shape,
        )

    def _region_sigmas(
        self,
        *,
        positive_regions: list[tuple[int, int, int]],
        linking_values: np.ndarray,
    ) -> np.ndarray:
        if not positive_regions:
            return np.array([], dtype=np.float64)
        relaxed = np.asarray(
            [length / float(self.parameters["bp_per_turn"]) for _, _, length in positive_regions],
            dtype=np.float64,
        )
        return (linking_values.astype(np.float64) - relaxed) / np.maximum(1.0, relaxed)

    def _weighted_sigma(
        self,
        *,
        positive_regions: list[tuple[int, int, int]],
        sigma_values: np.ndarray,
    ) -> float:
        if sigma_values.size == 0:
            return float(self.equilibrium_sigma)
        weights = np.asarray([length for _, _, length in positive_regions], dtype=np.float64)
        total = float(weights.sum())
        if total <= 0.0:
            return float(np.mean(sigma_values))
        return float(np.sum(weights * sigma_values) / total)

    def _replication_region_index(self, positive_regions: list[tuple[int, int, int]]) -> int | None:
        if not positive_regions:
            return None
        chromosome_one = [idx for idx, (_, strand, _) in enumerate(positive_regions) if strand == 0]
        if chromosome_one:
            return max(chromosome_one, key=lambda idx: positive_regions[idx][2])
        return max(range(len(positive_regions)), key=lambda idx: positive_regions[idx][2])

    def _sample_region_events(
        self,
        *,
        total_count: float,
        activity_rate: float,
        sigma_values: np.ndarray,
        region_lengths: np.ndarray,
        sigma_limit: float,
        logistic_const: float,
        allowed_when: str,
        dt: float,
        force_prob_one: bool = False,
    ) -> np.ndarray:
        if sigma_values.size == 0 or total_count <= 0.0 or activity_rate <= 0.0 or dt <= 0.0:
            return np.zeros_like(sigma_values, dtype=np.int32)
        legal = np.zeros_like(sigma_values, dtype=bool)
        if allowed_when == "greater":
            legal = sigma_values > sigma_limit
        elif allowed_when == "less":
            legal = sigma_values < sigma_limit
        else:
            raise ValueError(f"Unknown allowed_when mode: {allowed_when}")
        if not np.any(legal):
            return np.zeros_like(sigma_values, dtype=np.int32)

        weights = region_lengths.astype(np.float64)
        weights[~legal] = 0.0
        weight_total = float(weights.sum())
        if weight_total <= 0.0:
            return np.zeros_like(sigma_values, dtype=np.int32)
        weights /= weight_total

        events = np.zeros_like(sigma_values, dtype=np.int32)
        for idx in np.flatnonzero(legal):
            prob = 1.0
            if not force_prob_one:
                prob = self._activity_probability(
                    sigma=float(sigma_values[idx]),
                    logistic_const=float(logistic_const),
                    sigma_limit=float(sigma_limit),
                    allowed_when=allowed_when,
                )
            expected = max(0.0, float(total_count) * float(weights[idx]) * float(activity_rate) * prob * dt)
            events[idx] = int(self._stochastic_round(expected))
        return events

    def _resolve_enzyme_count(
        self,
        wid: str,
        *,
        protein_counts: dict[str, Any],
        complex_counts: dict[str, Any],
        top_level_enzymes: dict[str, Any],
    ) -> float:
        if wid in top_level_enzymes:
            return max(0.0, float(top_level_enzymes.get(wid, 0.0)))
        store = self.enzyme_store_by_wid.get(wid)
        if store is None:
            raise KeyError(f"Declared enzyme '{wid}' is missing store classification")
        if store == "complex":
            if wid not in complex_counts:
                raise KeyError(f"Missing declared complex enzyme '{wid}' in complex.counts")
            return max(0.0, float(complex_counts[wid]))
        if wid not in protein_counts:
            return 0.0
        return max(0.0, float(protein_counts[wid]))

    def _allocated_or_state(self, allocated_state: dict[str, Any], wid: str) -> float:
        allocated = float(allocated_state.get(wid, 0.0))
        return max(0.0, allocated)

    def _replication_supercoil_load_events(self, replication_state: str, dt: float) -> int:
        if replication_state != "elongating":
            return 0
        rate = max(0.0, float(self.parameters["replication_supercoil_load_rate"]))
        return int(self._rng.poisson(rate * max(0.0, dt)))

    def _activity_probability(
        self,
        *,
        sigma: float,
        logistic_const: float,
        sigma_limit: float,
        allowed_when: str,
    ) -> float:
        if allowed_when == "greater":
            if sigma <= sigma_limit:
                return 0.0
        elif allowed_when == "less":
            if sigma >= sigma_limit:
                return 0.0
        else:
            raise ValueError(f"Unknown allowed_when mode: {allowed_when}")

        x = float(logistic_const) * (float(sigma) - float(self.equilibrium_sigma))
        x = float(np.clip(x, a_min=-60.0, a_max=60.0))
        return float(1.0 / (1.0 + np.exp(x)))

    def _stochastic_round(self, value: float) -> int:
        if value <= 0.0:
            return 0
        base = int(math.floor(value))
        frac = float(value - base)
        if frac <= 0.0:
            return base
        return base + int(self._rng.random() < frac)

    def _emit_hint_delta(
        self,
        *,
        update: dict[str, Any],
        channel: str,
        current: dict[str, Any],
        nxt: dict[str, Any],
    ) -> None:
        if not nxt:
            return
        for wid in self.enzyme_wids:
            now = float(current.get(wid, 0.0))
            after = float(nxt.get(wid, now))
            delta = after - now
            if delta != 0.0:
                update.setdefault(channel, {})[wid] = float(delta)

    def _expected_event_rate(
        self,
        *,
        base_rate: float,
        enzyme_count: float,
        reference_count: float,
        probability: float,
        dt: float,
    ) -> float:
        if base_rate <= 0.0 or enzyme_count <= 0.0 or probability <= 0.0 or dt <= 0.0:
            return 0.0
        ref = max(1e-9, reference_count)
        count_scale = enzyme_count / ref
        return max(0.0, base_rate * count_scale * probability * dt)

    def _regime(self, sigma: float) -> str:
        deadband = abs(float(self.parameters["sigma_deadband"]))
        if sigma > self.equilibrium_sigma + deadband:
            return "overwound"
        if sigma < self.equilibrium_sigma - deadband:
            return "underwound"
        return "near_equilibrium"

    def _limit_events_by_atp(
        self,
        *,
        gyrase_events: int,
        topoiv_events: int,
        available_atp: float,
        mode: str,
    ) -> tuple[int, int]:
        g_events = max(0, int(gyrase_events))
        t_events = max(0, int(topoiv_events))
        atp_budget = max(0, int(math.floor(available_atp)))

        g_cost = max(0, int(round(self.gyrase_atp_cost)))
        t_cost = max(0, int(round(self.topoiv_atp_cost)))

        total_cost = g_events * g_cost + t_events * t_cost
        if total_cost <= atp_budget:
            return g_events, t_events
        if g_cost == 0 and t_cost == 0:
            return g_events, t_events
        if atp_budget <= 0:
            return 0, 0

        g_kept = 0
        t_kept = 0
        priorities = ["g", "t"] if mode == "overwound" else ["t", "g"]
        for key in priorities:
            if key == "g":
                while g_kept < g_events and (g_cost == 0 or atp_budget >= g_cost):
                    g_kept += 1
                    atp_budget -= g_cost
            else:
                while t_kept < t_events and (t_cost == 0 or atp_budget >= t_cost):
                    t_kept += 1
                    atp_budget -= t_cost
        return g_kept, t_kept

    def _cap_region_events(self, events: np.ndarray, kept_total: int) -> np.ndarray:
        raw = np.asarray(events, dtype=np.int32).reshape(-1)
        total = int(raw.sum())
        if kept_total >= total:
            return raw
        if kept_total <= 0 or total <= 0:
            return np.zeros_like(raw)

        weights = raw.astype(np.float64) / float(total)
        scaled = np.floor(weights * kept_total).astype(np.int32)
        scaled = np.minimum(scaled, raw)
        remaining = int(kept_total - scaled.sum())
        if remaining <= 0:
            return scaled

        residual = weights * kept_total - scaled
        order = np.argsort(-residual)
        for idx in order:
            if remaining <= 0:
                break
            capacity = int(raw[idx] - scaled[idx])
            if capacity <= 0:
                continue
            scaled[idx] += 1
            remaining -= 1
        return scaled

    def _atp_request(
        self,
        *,
        sigma: float,
        replication_state: str,
        gyrase_count: float,
        topoiv_count: float,
        dt: float,
    ) -> float:
        gyrase_prob = self._activity_probability(
            sigma=sigma,
            logistic_const=self.gyrase_logistic_const,
            sigma_limit=self.gyrase_sigma_limit,
            allowed_when="greater",
        )
        topoiv_prob = 1.0 if sigma > self.topoiv_sigma_limit else 0.0

        expected_g_events = self._expected_event_rate(
            base_rate=self.gyrase_activity_rate,
            enzyme_count=gyrase_count,
            reference_count=float(self.parameters["reference_gyrase_count"]),
            probability=gyrase_prob,
            dt=dt,
        )
        expected_t_events = self._expected_event_rate(
            base_rate=self.topoiv_activity_rate,
            enzyme_count=topoiv_count,
            reference_count=float(self.parameters["reference_topoiv_count"]),
            probability=topoiv_prob,
            dt=dt,
        )

        replication_extra = 0.0
        if replication_state == "elongating":
            replication_extra = (
                max(0.0, float(self.parameters["replication_supercoil_load_rate"]))
                * max(0.0, dt)
            )

        expected_atp = (
            expected_g_events * self.gyrase_atp_cost
            + expected_t_events * self.topoiv_atp_cost
            + replication_extra * self.gyrase_atp_cost
        )
        safety = max(1.0, float(self.parameters["request_safety_factor"]))
        req = math.ceil(expected_atp * safety)
        return float(min(req, max(0.0, float(self.parameters["request_max_atp"]))))

    def _substrate_delta(self, atp_used: float) -> dict[str, float]:
        if atp_used <= 0.0:
            return {}
        out = {
            self.atp_wid: float(-atp_used),
            self.h2o_wid: float(-atp_used),
            self.adp_wid: float(atp_used),
            self.pi_wid: float(atp_used),
        }
        if self.h_wid is not None:
            out[self.h_wid] = float(atp_used)
        return out


__all__ = ["KarrDNASupercoilingProcess"]
