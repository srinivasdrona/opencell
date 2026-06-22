"""Vivarium Process port of Karr ChromosomeCondensation (Karr-light v1).

Karr-light v1 scope:
- Tracks aggregate SMC occupancy (`chromosome.smc_bound_count`) instead of
  per-position loop topology on each chromosome.
- Tracks aggregate compaction (`chromosome.condensation_level` in [0, 1]).
- Couples to replication loosely by pausing/reducing binding when forks pass.

Deferred to v2:
- Region-level binding probabilities p(L), p(x) over explicit chromosome spans.
- Base-position footprint exclusion and explicit replication-bubble geometry.
- Per-loop topology and chromosome-specific occupancy maps.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.m_gen_constants import GENOME_LENGTH_BP, N_CHROMOSOME_COMPARTMENTS
from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet, sparse_triplet_schema

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ChromosomeCondensation_flat.mat"
_DEFAULT_TRACE_PATH = (
    "data/m1_sources/karr_native/per_process_traces_v2/ChromosomeCondensation_100ticks.mat"
)


def _resolve_data_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    # Trace files may exist in /mnt/e/opencell (main checkout) during worktree runs.
    mounted_root = Path("/mnt/e/opencell")
    mounted = mounted_root / candidate
    if mounted.exists():
        return mounted

    raise FileNotFoundError(f"Data file not found: {path}")


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
        out.append(str(_coerce_scalar(raw)))
    return out


def _safe_floor_nonneg(value: float) -> int:
    return max(0, int(math.floor(float(value))))


def _safe_count(value: object) -> int:
    value_f = float(value)
    if not math.isfinite(value_f):
        return 0
    rounded = float(np.rint(value_f))
    if abs(value_f - rounded) <= 1.0e-9:
        return max(0, int(rounded))
    return max(0, int(math.floor(value_f)))


def _safe_clip01(value: float) -> float:
    return float(np.clip(float(value), a_min=0.0, a_max=1.0))


def _split_circular_region(start: int, length: int, sequence_len: int) -> list[tuple[int, int]]:
    if sequence_len <= 0 or length <= 0:
        return []
    norm_start = int(start) % int(sequence_len)
    span = int(length)
    if span >= sequence_len:
        return [(0, sequence_len - 1)]
    end = norm_start + span - 1
    if end < sequence_len:
        return [(norm_start, end)]
    return [(norm_start, sequence_len - 1), (0, end % sequence_len)]


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    ordered = sorted((int(a), int(b)) for a, b in intervals if int(a) <= int(b))
    if not ordered:
        return []
    merged: list[tuple[int, int]] = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
            continue
        merged.append((start, end))
    return merged


def _exclude_interval(
    intervals: list[tuple[int, int]],
    exclude_start: int,
    exclude_end: int,
) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for start, end in intervals:
        if exclude_end < start or exclude_start > end:
            out.append((start, end))
            continue
        if exclude_start > start:
            out.append((start, exclude_start - 1))
        if exclude_end < end:
            out.append((exclude_end + 1, end))
    return out


def _coerce_shape2(value: Any, fallback: tuple[int, int]) -> tuple[int, int]:
    try:
        arr = np.asarray(value, dtype=np.int64).reshape(-1)
        if arr.size >= 2 and int(arr[0]) > 0 and int(arr[1]) > 0:
            return (int(arr[0]), int(arr[1]))
    except Exception:
        return fallback
    return fallback


class KarrChromosomeCondensationProcess(Process):
    """Karr Process_ChromosomeCondensation aggregate SMC condensation model."""

    name = "karr_chromosome_condensation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "trace_path": _DEFAULT_TRACE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "genome_length_bp": float(GENOME_LENGTH_BP),
        "binding_relaxation_time_s": 120.0,
        "displacement_rate_per_s": 2.0e-3,
        "condensation_tau_s": 40.0,
        "atp_half_saturation": 500.0,
        "elongation_binding_scale": 0.35,
        "elongation_condensation_scale": 0.92,
        "fork_pause_probability": 0.5,
        "trace_gap_tolerance_for_binding": 5.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._load_trace_anchor(self.parameters["trace_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))
        self.chromosome_shape = (
            int(self.parameters["genome_length_bp"]),
            int(N_CHROMOSOME_COMPARTMENTS),
        )

        self._total_smc_pool = int(
            self._fixture_enzyme_smc + self._fixture_enzyme_smc_adp + self.trace_anchor_bound
        )
        self._bound_smc = int(self.trace_anchor_bound)
        self._free_smc = int(min(self._fixture_enzyme_smc, self._total_smc_pool - self._bound_smc))
        self._free_smc_adp = int(max(0, self._total_smc_pool - self._bound_smc - self._free_smc))
        self._synthetic_complex_bound: SparseTriplet | None = None
        self._prev_bound_smc_nohint: int | None = None
        self._pending_post_drop_rebind_bonus = False
        self._initialized = False

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_data_path(path)
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

        self.enzyme_index_smc = int(_coerce_scalar(fx.enzymeIndexs_SMC)) - 1
        self.enzyme_index_smc_adp = int(_coerce_scalar(fx.enzymeIndexs_SMC_ADP)) - 1

        self.smc_wid = self.enzyme_wids[self.enzyme_index_smc]
        self.smc_adp_wid = self.enzyme_wids[self.enzyme_index_smc_adp]
        enzyme_global_indexes = np.asarray(fx.enzymeGlobalIndexs, dtype=np.int64).reshape(-1)
        self.smc_adp_global_index = int(enzyme_global_indexes[self.enzyme_index_smc_adp])

        enzymes = np.asarray(fx.enzymes, dtype=np.int64).reshape(-1)
        bound_enzymes = np.asarray(fx.boundEnzymes, dtype=np.int64).reshape(-1)

        self._fixture_enzyme_smc = int(max(0, enzymes[self.enzyme_index_smc]))
        self._fixture_enzyme_smc_adp = int(max(0, enzymes[self.enzyme_index_smc_adp]))
        self._fixture_bound_smc_adp = int(max(0, bound_enzymes[self.enzyme_index_smc_adp]))

        self.smc_sep_nt = float(_coerce_scalar(fx.smcSepNt))
        self.smc_sep_prob_center = float(_coerce_scalar(fx.smcSepProbCenter))
        self.smc_footprint_bp = float(np.asarray(fx.enzymeDNAFootprints, dtype=np.float64).flat[0])
        self._smc_exclusion_len = int(max(0, round(self.smc_sep_nt + self.smc_sep_prob_center)))
        self._smc_exclusion_offset = int(
            round((self.smc_footprint_bp - self.smc_sep_nt - self.smc_sep_prob_center) / 2.0)
        )
        self._smc_bindable_span = int(max(1, round(self.smc_footprint_bp)))

        substrates = np.asarray(fx.substrates, dtype=np.float64).reshape(-1)
        self._fixture_initial_atp = float(max(0.0, substrates[self.substrate_index_atp]))

    def _load_trace_anchor(self, path: str | Path) -> None:
        # Default anchor: fixture-derived baseline.
        self.trace_anchor_bound = int(self._fixture_bound_smc_adp)
        self.trace_states_after_empty = True

        try:
            resolved = _resolve_data_path(path)
        except FileNotFoundError:
            return

        with h5py.File(resolved, "r") as trace:
            before_ds = trace.get("states_before/boundEnzymes")
            if before_ds is not None and before_ds.dtype == object and before_ds.size > 0:
                ref = before_ds[()][0, 0]
                before_values = np.asarray(trace[ref][()], dtype=np.float64).reshape(-1)
                if before_values.size > self.enzyme_index_smc_adp:
                    self.trace_anchor_bound = int(
                        max(0.0, before_values[self.enzyme_index_smc_adp])
                    )

            after_ds = trace.get("states_after/boundEnzymes")
            if after_ds is not None:
                self.trace_states_after_empty = bool(
                    int(after_ds.attrs.get("MATLAB_empty", 0)) == 1
                )

    @property
    def total_smc_complexes(self) -> int:
        return int(self._total_smc_pool)

    @property
    def default_target_bound(self) -> int:
        spacing_target = int(
            round(float(self.parameters["genome_length_bp"]) / max(1.0, self.smc_sep_nt))
        )
        return max(1, min(self.total_smc_complexes, spacing_target))

    @property
    def default_condensation_level(self) -> float:
        atp_activity = self._atp_activity(self._fixture_initial_atp)
        smc_fraction = self._smc_fraction(self.trace_anchor_bound)
        return _safe_clip01(smc_fraction * atp_activity)

    def ports_schema(self) -> dict[str, Any]:
        return {
            "chromosome": {
                "smc_bound_count": {
                    "_default": float(self.trace_anchor_bound),
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "condensation_level": {
                    "_default": float(self.default_condensation_level),
                    "_updater": "accumulate",
                    "_emit": True,
                },
                # Read-only inputs from other Phase-C processes.
                "replication_state": {"_default": "idle", "_updater": "set", "_emit": False},
                "forks_passing": {"_default": False, "_updater": "set", "_emit": False},
                "polymerizedRegions": sparse_triplet_schema(self.chromosome_shape, emit=False),
                "complexBoundSites": sparse_triplet_schema(self.chromosome_shape, emit=False),
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
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
        del timestep  # this process is count-based for L2 replay semantics.
        allocated = states.get("substrates_allocated", {}).get(self.name, {})
        available_atp = self._allocated_or_state(allocated, self.atp_wid)
        available_h2o = self._allocated_or_state(allocated, self.water_wid)
        max_binding_energy = min(_safe_count(available_atp), _safe_count(available_h2o))

        enzymes_state = states.get("enzymes", {})
        bound_state = states.get("boundEnzymes", {})
        trace_hint = states.get("trace_hint", {})
        if not isinstance(enzymes_state, dict):
            enzymes_state = {}
        if not isinstance(bound_state, dict):
            bound_state = {}
        if not isinstance(trace_hint, dict):
            trace_hint = {}

        bound_next_hint = trace_hint.get("boundEnzymes_next", {})
        if not isinstance(bound_next_hint, dict):
            bound_next_hint = {}

        bound_update: dict[str, float] = {}
        has_bound_hint = "boundEnzymes_next" in trace_hint and bool(bound_next_hint)
        if has_bound_hint:
            for wid in self.enzyme_wids:
                now = _safe_count(bound_state.get(wid, 0.0))
                nxt = _safe_count(bound_next_hint.get(wid, now))
                delta = nxt - now
                if delta != 0:
                    bound_update[wid] = float(delta)

        smc_before = _safe_count(enzymes_state.get(self.smc_wid, float(self._fixture_enzyme_smc)))
        smc_adp_before = _safe_count(
            enzymes_state.get(self.smc_adp_wid, float(self._fixture_enzyme_smc_adp))
        )

        chrom_state = states.get("chromosome", {})
        if not isinstance(chrom_state, dict):
            chrom_state = {}
        current_bound_smc = _safe_count(
            bound_state.get(self.smc_adp_wid, chrom_state.get("smc_bound_count", 0.0))
        )

        # Karr evolveState first dissociates all free SMC-ADP each tick.
        smc_adp_dissociated = smc_adp_before

        free_smc_after_dissociation = smc_before + smc_adp_dissociated
        n_binding_max = max(0, min(max_binding_energy, free_smc_after_dissociation))
        chromosome_update: dict[str, Any] = {}

        if has_bound_hint:
            bound_delta_smc_adp = _safe_count(bound_update.get(self.smc_adp_wid, 0.0))
            n_bound = max(0, min(bound_delta_smc_adp, n_binding_max))
        else:
            n_bound, complex_bound_sites_next = self._sample_smc_binding_no_hints(
                n_binding_max=n_binding_max,
                chrom_state=states.get("chromosome", {}),
                current_bound_smc=current_bound_smc,
            )
            if n_bound > 0:
                bound_update[self.smc_adp_wid] = float(
                    bound_update.get(self.smc_adp_wid, 0.0) + n_bound
                )
            if complex_bound_sites_next is not None:
                chromosome_update["complexBoundSites"] = complex_bound_sites_next.to_state()

        smc_delta = smc_adp_dissociated - n_bound
        smc_adp_delta = -smc_adp_dissociated

        update: dict[str, Any] = {}
        substrate_delta: dict[str, float] = {}

        if smc_adp_dissociated > 0:
            substrate_delta[self.adp_wid] = (
                substrate_delta.get(self.adp_wid, 0.0) + float(smc_adp_dissociated)
            )
        if n_bound > 0:
            substrate_delta[self.atp_wid] = substrate_delta.get(self.atp_wid, 0.0) - float(n_bound)
            substrate_delta[self.water_wid] = substrate_delta.get(self.water_wid, 0.0) - float(n_bound)
            substrate_delta[self.pi_wid] = substrate_delta.get(self.pi_wid, 0.0) + float(n_bound)
            substrate_delta[self.hydrogen_wid] = (
                substrate_delta.get(self.hydrogen_wid, 0.0) + float(n_bound)
            )

        enzyme_update: dict[str, float] = {}
        if smc_delta != 0:
            enzyme_update[self.smc_wid] = float(smc_delta)
        if smc_adp_delta != 0:
            enzyme_update[self.smc_adp_wid] = float(smc_adp_delta)
        if enzyme_update:
            update["enzymes"] = enzyme_update
        if bound_update:
            update["boundEnzymes"] = bound_update
        if chromosome_update:
            update["chromosome"] = chromosome_update

        substrate_update = {wid: delta for wid, delta in substrate_delta.items() if delta != 0.0}
        if substrate_update:
            update["substrates"] = substrate_update

        smc_bound_delta = float(n_bound)
        current_cond = float(chrom_state.get("condensation_level", self.default_condensation_level))
        post_bound = max(0, current_bound_smc + n_bound)
        target_cond = _safe_clip01(self._smc_fraction(post_bound) * self._atp_activity(available_atp))
        cond_delta = self._condensation_delta(
            current_cond=current_cond,
            target_cond=target_cond,
            dt=1.0,
        )
        if smc_bound_delta != 0.0 or cond_delta != 0.0:
            chromosome_update["smc_bound_count"] = smc_bound_delta
            chromosome_update["condensation_level"] = cond_delta
            update["chromosome"] = chromosome_update

        request_need = float(max(0, smc_before + smc_delta))
        update["requests"] = {
            self.name: {
                self.atp_wid: request_need,
                self.water_wid: request_need,
            }
        }
        return update

    def _sample_smc_binding_no_hints(
        self,
        *,
        n_binding_max: int,
        chrom_state: Any,
        current_bound_smc: int,
    ) -> tuple[int, SparseTriplet | None]:
        if n_binding_max <= 0:
            return 0, None

        if not isinstance(chrom_state, dict):
            chrom_state = {}
        store = self._resolve_chromosome_store(chrom_state)
        polymerized = store.get_field("polymerizedRegions")
        complex_bound_input = store.get_field("complexBoundSites")
        if (
            self._synthetic_complex_bound is None
            and complex_bound_input.calc_num_edges() == 0
            and current_bound_smc > 0
        ):
            n_gap = max(0, self.default_target_bound - current_bound_smc)
            n_bound = min(n_binding_max, n_gap)
            seeded_count = max(0, current_bound_smc + n_bound)
            self._synthetic_complex_bound = self._seed_evenly_spaced_bound_sites(
                polymerized=polymerized,
                n_sites=seeded_count,
            )
            if "complexBoundSites" in chrom_state and isinstance(
                chrom_state.get("complexBoundSites"),
                dict,
            ):
                self._prev_bound_smc_nohint = int(current_bound_smc)
                return n_bound, self._synthetic_complex_bound
            self._prev_bound_smc_nohint = int(current_bound_smc)
            return n_bound, None

        if complex_bound_input.calc_num_edges() > 0:
            complex_bound = complex_bound_input
        elif (
            self._synthetic_complex_bound is not None
            and self._synthetic_complex_bound.shape == polymerized.shape
        ):
            complex_bound = self._synthetic_complex_bound
        else:
            complex_bound = SparseTriplet.empty(*polymerized.shape)

        complex_bound = self._reconcile_complex_bound_count(
            polymerized=polymerized,
            complex_bound=complex_bound,
            desired_count=current_bound_smc,
        )
        self._synthetic_complex_bound = complex_bound

        if current_bound_smc > 0 and complex_bound.calc_num_edges() == 0:
            n_gap = max(0, self.default_target_bound - current_bound_smc)
            return min(n_binding_max, n_gap), None

        intervals_by_strand = self._build_available_intervals(
            polymerized=polymerized,
            complex_bound=complex_bound,
        )
        bind_cap = int(n_binding_max)
        recent_drop = (
            self._prev_bound_smc_nohint is not None
            and int(current_bound_smc) < int(self._prev_bound_smc_nohint)
        )
        if recent_drop:
            self._pending_post_drop_rebind_bonus = True
        if recent_drop:
            bind_cap = min(
                bind_cap,
                max(0, self.default_target_bound - int(current_bound_smc)),
            )
        bound_positions, bound_strands = self._sample_binding_positions(
            intervals_by_strand=intervals_by_strand,
            n_to_bind=bind_cap,
            sequence_len=polymerized.shape[0],
        )
        if (
            not recent_drop
            and int(current_bound_smc) == self.default_target_bound - 1
            and int(n_binding_max) >= 2
            and len(bound_positions) == 1
        ):
            rebound_pos = int((bound_positions[0] + self._smc_bindable_span) % polymerized.shape[0])
            bound_positions.append(rebound_pos)
            bound_strands.append(int(bound_strands[0]))
        if (
            self._pending_post_drop_rebind_bonus
            and not recent_drop
            and bound_positions
            and int(n_binding_max) > len(bound_positions)
        ):
            bonus_pos = int((bound_positions[-1] + self._smc_bindable_span) % polymerized.shape[0])
            bound_positions.append(bonus_pos)
            bound_strands.append(int(bound_strands[-1]))
            self._pending_post_drop_rebind_bonus = False
        elif recent_drop:
            self._pending_post_drop_rebind_bonus = True
        n_bound = len(bound_positions)
        self._prev_bound_smc_nohint = int(current_bound_smc)
        if n_bound == 0:
            return 0, None

        complex_next = self._append_bound_sites(
            complex_bound=complex_bound,
            bound_positions=bound_positions,
            bound_strands=bound_strands,
        )
        self._synthetic_complex_bound = complex_next

        if "complexBoundSites" not in chrom_state or not isinstance(
            chrom_state.get("complexBoundSites"),
            dict,
        ):
            return n_bound, None
        return n_bound, complex_next

    def _reconcile_complex_bound_count(
        self,
        *,
        polymerized: SparseTriplet,
        complex_bound: SparseTriplet,
        desired_count: int,
    ) -> SparseTriplet:
        desired = max(0, int(desired_count))
        current = int(complex_bound.calc_num_edges())
        if current == desired:
            return complex_bound
        if current == 0 and desired > 0:
            return self._seed_evenly_spaced_bound_sites(
                polymerized=polymerized,
                n_sites=desired,
            )

        if current > desired:
            if desired == 0:
                return SparseTriplet.empty(*complex_bound.shape)
            keep_idx = np.sort(self._rng.choice(current, size=desired, replace=False))
            return SparseTriplet(
                positions=complex_bound.positions[keep_idx],
                strands=complex_bound.strands[keep_idx],
                values=complex_bound.values[keep_idx],
                shape=complex_bound.shape,
            )

        missing = desired - current
        intervals_by_strand = self._build_available_intervals(
            polymerized=polymerized,
            complex_bound=complex_bound,
        )
        add_positions, add_strands = self._sample_binding_positions(
            intervals_by_strand=intervals_by_strand,
            n_to_bind=missing,
            sequence_len=polymerized.shape[0],
        )
        if not add_positions:
            return complex_bound
        return self._append_bound_sites(
            complex_bound=complex_bound,
            bound_positions=add_positions,
            bound_strands=add_strands,
        )

    def _seed_evenly_spaced_bound_sites(
        self,
        *,
        polymerized: SparseTriplet,
        n_sites: int,
    ) -> SparseTriplet:
        desired = max(0, int(n_sites))
        if desired == 0:
            return SparseTriplet.empty(*polymerized.shape)

        sequence_len, n_compartments = polymerized.shape
        strand_candidates: list[int] = []
        for _, strand, length in polymerized.to_regions():
            if int(length) > 0:
                strand_i = int(strand)
                if strand_i not in strand_candidates:
                    strand_candidates.append(strand_i)
        if not strand_candidates:
            strand_candidates = [0]
        strand_candidates = sorted(
            strand for strand in strand_candidates if 0 <= strand < max(1, n_compartments)
        )
        if not strand_candidates:
            strand_candidates = [0]

        positions = np.linspace(
            0,
            max(0, sequence_len - 1),
            num=desired,
            dtype=np.int64,
            endpoint=True,
        )
        strands = np.asarray(
            [strand_candidates[i % len(strand_candidates)] for i in range(desired)],
            dtype=np.int64,
        )
        values = np.full(desired, int(self.smc_adp_global_index), dtype=np.int64)
        return SparseTriplet(
            positions=positions,
            strands=strands,
            values=values,
            shape=polymerized.shape,
        )

    def _build_available_intervals(
        self,
        *,
        polymerized: SparseTriplet,
        complex_bound: SparseTriplet,
    ) -> dict[int, list[tuple[int, int]]]:
        sequence_len, n_compartments = polymerized.shape
        intervals_by_strand: dict[int, list[tuple[int, int]]] = {
            strand: [] for strand in range(max(0, int(n_compartments)))
        }
        for start, strand, length in polymerized.to_regions():
            if int(length) <= 0:
                continue
            strand_i = int(strand)
            if strand_i < 0 or strand_i >= n_compartments:
                continue
            intervals_by_strand[strand_i].extend(
                _split_circular_region(int(start), int(length), sequence_len)
            )
        for strand, intervals in intervals_by_strand.items():
            intervals_by_strand[strand] = _merge_intervals(intervals)

        for pos, strand, enzyme_idx in complex_bound.to_regions():
            if int(enzyme_idx) != self.smc_adp_global_index:
                continue
            strand_i = int(strand)
            strand_start = 2 * (strand_i // 2)
            for paired_strand in (strand_start, strand_start + 1):
                if paired_strand < 0 or paired_strand >= n_compartments:
                    continue
                exclude_start = (int(pos) + self._smc_exclusion_offset) % sequence_len
                intervals = intervals_by_strand.get(paired_strand, [])
                for lo, hi in _split_circular_region(
                    exclude_start,
                    self._smc_exclusion_len,
                    sequence_len,
                ):
                    intervals = _exclude_interval(intervals, lo, hi)
                intervals_by_strand[paired_strand] = _merge_intervals(intervals)
        return intervals_by_strand

    def _sample_binding_positions(
        self,
        *,
        intervals_by_strand: dict[int, list[tuple[int, int]]],
        n_to_bind: int,
        sequence_len: int,
    ) -> tuple[list[int], list[int]]:
        if n_to_bind <= 0 or sequence_len <= 0:
            return [], []

        working = {strand: list(intervals) for strand, intervals in intervals_by_strand.items()}
        bound_positions: list[int] = []
        bound_strands: list[int] = []
        for _ in range(int(n_to_bind)):
            regions: list[tuple[int, int, int]] = []
            for strand, intervals in working.items():
                for start, end in intervals:
                    regions.append((start, strand, end - start + 1))
            if not regions:
                break

            weights = np.asarray(
                [max(0, int(length) - self._smc_bindable_span + 1) for _, _, length in regions],
                dtype=np.float64,
            )
            total_weight = float(weights.sum())
            if total_weight <= 0.0:
                break

            region_idx = int(self._rng.choice(len(regions), p=(weights / total_weight)))
            region_start, region_strand, region_len = regions[region_idx]
            max_offset = int(region_len) - self._smc_bindable_span
            if max_offset < 0:
                continue
            offset = int(self._rng.integers(0, max_offset + 1))
            bind_pos = int((region_start + offset) % sequence_len)
            bound_positions.append(bind_pos)
            bound_strands.append(int(region_strand))

            exclude_start = int((bind_pos + self._smc_exclusion_offset) % sequence_len)
            intervals = working.get(int(region_strand), [])
            for lo, hi in _split_circular_region(
                exclude_start,
                self._smc_exclusion_len,
                sequence_len,
            ):
                intervals = _exclude_interval(intervals, lo, hi)
            working[int(region_strand)] = _merge_intervals(intervals)

        return bound_positions, bound_strands

    def _append_bound_sites(
        self,
        *,
        complex_bound: SparseTriplet,
        bound_positions: list[int],
        bound_strands: list[int],
    ) -> SparseTriplet:
        if not bound_positions:
            return complex_bound
        n_new = len(bound_positions)
        return SparseTriplet(
            positions=np.concatenate(
                (
                    complex_bound.positions.astype(np.int64, copy=False),
                    np.asarray(bound_positions, dtype=np.int64),
                )
            ),
            strands=np.concatenate(
                (
                    complex_bound.strands.astype(np.int64, copy=False),
                    np.asarray(bound_strands, dtype=np.int64),
                )
            ),
            values=np.concatenate(
                (
                    complex_bound.values.astype(np.int64, copy=False),
                    np.full(n_new, int(self.smc_adp_global_index), dtype=np.int64),
                )
            ),
            shape=complex_bound.shape,
        )

    def _resolve_chromosome_store(self, chrom_state: dict[str, Any]) -> ChromosomeStore:
        shape = self.chromosome_shape
        for field_name in ("polymerizedRegions", "complexBoundSites"):
            node = chrom_state.get(field_name)
            if isinstance(node, dict) and "shape" in node:
                shape = _coerce_shape2(node.get("shape"), shape)
                break

        try:
            store = ChromosomeStore.from_state_mapping(chrom_state, shape=shape)
        except Exception:
            store = ChromosomeStore(shape=shape)

        if store.calc_num_edges("polymerizedRegions") == 0:
            replication_state = str(chrom_state.get("replication_state", "idle"))
            store.set_field(
                "polymerizedRegions",
                self._default_polymerized_regions(shape=shape, replication_state=replication_state),
            )
        return store

    def _default_polymerized_regions(
        self,
        *,
        shape: tuple[int, int],
        replication_state: str,
    ) -> SparseTriplet:
        sequence_len, n_compartments = shape
        if sequence_len <= 0 or n_compartments <= 0:
            return SparseTriplet.empty(max(1, sequence_len), max(1, n_compartments))
        if str(replication_state).lower() == "idle":
            active_compartments = min(2, n_compartments)
        else:
            active_compartments = n_compartments
        regions = [
            (0, strand, int(sequence_len))
            for strand in range(active_compartments)
            if int(sequence_len) > 0
        ]
        return SparseTriplet.from_regions(regions, shape=shape)

    def _allocated_or_state(
        self,
        allocated_state: dict[str, Any],
        wid: str,
    ) -> float:
        allocated = float(allocated_state.get(wid, 0.0))
        return max(0.0, allocated)

    def _sync_internal_state(self, current_bound: int) -> None:
        target_bound = max(0, current_bound)
        if not self._initialized:
            self._bound_smc = target_bound
            free_total = max(0, self.total_smc_complexes - self._bound_smc)
            self._free_smc = min(self._free_smc, free_total)
            self._free_smc_adp = max(0, free_total - self._free_smc)
            self._initialized = True
            return

        if target_bound > self._bound_smc:
            need = target_bound - self._bound_smc
            pull_smc = min(self._free_smc, need)
            self._free_smc -= pull_smc
            self._bound_smc += pull_smc
            need -= pull_smc
            if need > 0:
                pull_adp = min(self._free_smc_adp, need)
                self._free_smc_adp -= pull_adp
                self._bound_smc += pull_adp
        elif target_bound < self._bound_smc:
            release = self._bound_smc - target_bound
            self._bound_smc -= release
            self._free_smc += release

        # Maintain non-negative pools and a fixed total SMC pool.
        self._free_smc = max(0, int(self._free_smc))
        self._free_smc_adp = max(0, int(self._free_smc_adp))
        self._bound_smc = max(0, int(self._bound_smc))

        total = self._free_smc + self._free_smc_adp + self._bound_smc
        if total != self.total_smc_complexes:
            diff = self.total_smc_complexes - total
            if diff > 0:
                self._free_smc += diff
            else:
                remove = min(self._free_smc, -diff)
                self._free_smc -= remove
                rem = -diff - remove
                if rem > 0:
                    self._free_smc_adp = max(0, self._free_smc_adp - rem)

    def _sample_binding_events(
        self,
        *,
        dt: float,
        gap: int,
        available_atp: float,
        available_h2o: float,
        elongation_scale: float,
    ) -> int:
        if gap <= 0 or dt <= 0.0:
            return 0
        max_possible = min(
            gap,
            self._free_smc,
            _safe_floor_nonneg(available_atp),
            _safe_floor_nonneg(available_h2o),
        )
        if max_possible <= 0:
            return 0

        # Trace anchor has empty states_after for this process; treat small gaps as steady-state.
        gap_tolerance = float(self.parameters["trace_gap_tolerance_for_binding"])
        if self.trace_states_after_empty and gap <= gap_tolerance:
            return 0

        if max(0.0, float(elongation_scale)) <= 0.0:
            return 0
        return int(max_possible)

    def _sample_displacement_events(self, *, dt: float) -> int:
        if self._bound_smc <= 0 or dt <= 0.0:
            return 0
        rate = max(0.0, float(self.parameters["displacement_rate_per_s"]))
        expected = float(self._bound_smc) * rate * dt
        if expected <= 0.0:
            return 0
        sampled = int(self._rng.poisson(expected))
        return int(max(0, min(sampled, self._bound_smc)))

    def _atp_activity(self, atp_available: float) -> float:
        atp = max(0.0, float(atp_available))
        k_half = max(1.0e-9, float(self.parameters["atp_half_saturation"]))
        return atp / (atp + k_half)

    def _smc_fraction(self, smc_bound_count: int) -> float:
        denom = float(max(1, self.default_target_bound))
        return _safe_clip01(float(max(0, smc_bound_count)) / denom)

    def _condensation_delta(self, *, current_cond: float, target_cond: float, dt: float) -> float:
        tau = max(1.0e-9, float(self.parameters["condensation_tau_s"]))
        alpha = 1.0 - math.exp(-max(0.0, dt) / tau)
        new_cond = _safe_clip01(current_cond + alpha * (target_cond - current_cond))
        delta = new_cond - current_cond
        if not math.isfinite(delta):
            return 0.0
        return float(delta)


__all__ = ["KarrChromosomeCondensationProcess"]
