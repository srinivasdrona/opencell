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

import json
import math
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.m_gen_constants import GENOME_LENGTH_BP, N_CHROMOSOME_COMPARTMENTS
from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet, sparse_triplet_schema
from opencell.util import MatlabRandStream

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ChromosomeCondensation_flat.mat"
_DEFAULT_CHROMOSOME_FIXTURE_PATH = "data/karr_fixtures/per_process/Chromosome_flat.mat"
_DEFAULT_METABOLITE_FIXTURE_JSON_PATH = "data/karr_fixtures/per_process/Metabolite.json"
_DEFAULT_TRACE_PATH = (
    "data/m1_sources/karr_native/per_process_traces_v2/ChromosomeCondensation_100ticks.mat"
)
_DEFAULT_POSTWARMUP_STATE_PATH = "tmp/chromcond_postwarmup_state.mat"
_LITERAL_OCCUPANCY_FIELDS: tuple[str, ...] = (
    "monomerBoundSites",
    "damagedBases",
    "gapSites",
    "abasicSites",
    "damagedSugarPhosphates",
    "intrastrandCrossLinks",
    "strandBreaks",
    "hollidayJunctions",
)
_DAMAGE_POINT_FIELDS: tuple[str, ...] = (
    "damagedBases",
    "gapSites",
    "abasicSites",
    "damagedSugarPhosphates",
    "intrastrandCrossLinks",
    "strandBreaks",
    "hollidayJunctions",
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


def _intersect_intervals(
    intervals_a: list[tuple[int, int]],
    intervals_b: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    i = 0
    j = 0
    while i < len(intervals_a) and j < len(intervals_b):
        start_a, end_a = intervals_a[i]
        start_b, end_b = intervals_b[j]
        start = max(int(start_a), int(start_b))
        end = min(int(end_a), int(end_b))
        if start <= end:
            out.append((start, end))
        if end_a < end_b:
            i += 1
        else:
            j += 1
    return out


def _intervals_overlap(
    intervals_a: list[tuple[int, int]],
    intervals_b: list[tuple[int, int]],
) -> bool:
    return bool(_intersect_intervals(intervals_a, intervals_b))


def _sort_region_pos_strnds(pos_strnds: np.ndarray) -> np.ndarray:
    if pos_strnds.size == 0:
        return np.zeros(0, dtype=np.int64)
    return np.lexsort((pos_strnds[:, 0], pos_strnds[:, 1])).astype(np.int64)


def _split_over_oric_regions(
    sequence_len: int,
    pos_strnds: np.ndarray,
    lens: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if pos_strnds.size == 0:
        return pos_strnds.copy(), lens.copy()
    pos = pos_strnds.copy()
    ln = lens.astype(np.int64, copy=True)
    idxs = np.flatnonzero(pos[:, 0] + ln - 1 > sequence_len)
    if idxs.size == 0:
        return pos, ln
    append = np.column_stack((np.ones(idxs.size, dtype=np.int64), pos[idxs, 1]))
    append_lens = pos[idxs, 0] + ln[idxs] - sequence_len - 1
    pos = np.vstack((pos, append))
    ln = np.concatenate((ln, append_lens.astype(np.int64)))
    ln[idxs] = sequence_len - pos[idxs, 0] + 1
    return pos, ln


def _join_split_over_oric_regions(
    sequence_len: int,
    pos_strnds: np.ndarray,
    lens: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if pos_strnds.size == 0:
        return pos_strnds.copy(), lens.copy()
    pos = pos_strnds[:, 0].astype(np.int64, copy=True)
    strnds = pos_strnds[:, 1].astype(np.int64, copy=True)
    ends = pos + lens.astype(np.int64, copy=False) - 1
    for strand in range(1, int(strnds.max(initial=0)) + 1):
        idx1_arr = np.flatnonzero((pos == 1) & (strnds == strand))
        idx2_arr = np.flatnonzero((ends == sequence_len) & (strnds == strand))
        if idx1_arr.size == 0 or idx2_arr.size == 0:
            continue
        idx1 = int(idx1_arr[0])
        idx2 = int(idx2_arr[0])
        if idx1 == idx2:
            continue
        ends[idx2] = ends[idx2] + (ends[idx1] - pos[idx1] + 1)
        keep = np.ones(pos.shape[0], dtype=bool)
        keep[idx1] = False
        pos = pos[keep]
        strnds = strnds[keep]
        ends = ends[keep]
    out_pos = np.column_stack((pos, strnds))
    out_lens = ends - pos + 1
    return out_pos.astype(np.int64), out_lens.astype(np.int64)


def _join_split_regions(
    sequence_len: int,
    pos_strnds: np.ndarray,
    lens: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if pos_strnds.size == 0:
        return pos_strnds.copy(), lens.copy()
    pos = pos_strnds.astype(np.int64, copy=True)
    pos[:, 0] = ((pos[:, 0] - 1) % sequence_len) + 1
    order = _sort_region_pos_strnds(pos)
    pos = pos[order]
    ln = lens.astype(np.int64, copy=False)[order]
    starts = pos[:, 0].astype(np.int64, copy=True)
    ends = starts + ln - 1
    strnds = pos[:, 1].astype(np.int64, copy=True)
    keep = np.ones(starts.shape[0], dtype=bool)
    for strand in range(1, int(strnds.max(initial=0)) + 1):
        idxs = np.flatnonzero(strnds == strand)
        if idxs.size == 0:
            continue
        for j in range(idxs.size - 1):
            left = int(idxs[j])
            right = int(idxs[j + 1])
            if ends[left] + 1 >= starts[right]:
                starts[right] = starts[left]
                ends[right] = max(int(ends[left]), int(ends[right]))
                keep[left] = False
        if idxs.size >= 2:
            kept_idxs = idxs[keep[idxs]]
            if kept_idxs.size > 0:
                idx = int(kept_idxs[0])
                last_idx = int(idxs[-1])
                if ends[last_idx] + 1 >= starts[idx] + sequence_len:
                    ends[last_idx] = sequence_len
                    starts[idx] = 1
    out_pos = np.column_stack((starts[keep], strnds[keep]))
    out_lens = ends[keep] - starts[keep] + 1
    return out_pos.astype(np.int64), out_lens.astype(np.int64)


def _exclude_regions_literal(
    sequence_len: int,
    inc_pos_strnds: np.ndarray,
    inc_lens: np.ndarray,
    exc_pos_strnds: np.ndarray,
    exc_lens: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if inc_pos_strnds.size == 0:
        return np.zeros((0, 2), dtype=np.int64), np.zeros(0, dtype=np.int64)
    if exc_pos_strnds.size == 0:
        return _join_split_over_oric_regions(sequence_len, inc_pos_strnds, inc_lens)

    inc_pos, inc_ln = _join_split_over_oric_regions(sequence_len, inc_pos_strnds, inc_lens)
    exc_ln_arr = np.asarray(exc_lens, dtype=np.int64).reshape(-1)
    if exc_ln_arr.size == 1 and exc_pos_strnds.shape[0] != 1:
        exc_ln_arr = np.repeat(exc_ln_arr, exc_pos_strnds.shape[0])
    exc_pos, exc_ln_arr = _join_split_regions(sequence_len, exc_pos_strnds, exc_ln_arr)

    exc_pos_tripled = np.concatenate(
        (exc_pos[:, 0] - sequence_len, exc_pos[:, 0], exc_pos[:, 0] + sequence_len)
    )
    exc_strands_tripled = np.concatenate((exc_pos[:, 1], exc_pos[:, 1], exc_pos[:, 1]))
    exc_lens_tripled = np.concatenate((exc_ln_arr, exc_ln_arr, exc_ln_arr))

    out_pos: list[int] = []
    out_ends: list[int] = []
    out_strands: list[int] = []
    for (start_coor, strand), length in zip(inc_pos, inc_ln, strict=False):
        end_coor = int(start_coor + length - 1)
        mask = (
            (
                ((exc_pos_tripled <= start_coor) & (exc_pos_tripled + exc_lens_tripled - 1 >= start_coor))
                | ((exc_pos_tripled <= end_coor) & (exc_pos_tripled + exc_lens_tripled - 1 >= end_coor))
                | ((exc_pos_tripled >= start_coor) & (exc_pos_tripled + exc_lens_tripled - 1 <= end_coor))
            )
            & (exc_strands_tripled == strand)
        )
        exc_idxs = np.flatnonzero(mask)
        if exc_idxs.size == 0:
            add_pos = np.asarray([start_coor], dtype=np.int64)
            add_ends = np.asarray([end_coor], dtype=np.int64)
        elif exc_pos_tripled[exc_idxs[0]] <= start_coor:
            # Source-faithful note: MATLAB uses excLens(end) here, not the
            # matched interval's own length.
            if exc_pos_tripled[exc_idxs[-1]] + exc_lens_tripled[-1] - 1 >= end_coor:
                add_pos = exc_pos_tripled[exc_idxs[:-1]] + exc_lens_tripled[exc_idxs[:-1]]
                add_ends = exc_pos_tripled[exc_idxs[1:]] - 1
            else:
                add_pos = exc_pos_tripled[exc_idxs] + exc_lens_tripled[exc_idxs]
                add_ends = np.concatenate((exc_pos_tripled[exc_idxs[1:]] - 1, np.asarray([end_coor])))
        else:
            # Mirror the same MATLAB excLens(end) behavior in the second branch.
            if exc_pos_tripled[exc_idxs[-1]] + exc_lens_tripled[-1] - 1 >= end_coor:
                add_pos = np.concatenate(
                    (np.asarray([start_coor]), exc_pos_tripled[exc_idxs[:-1]] + exc_lens_tripled[exc_idxs[:-1]])
                )
                add_ends = exc_pos_tripled[exc_idxs] - 1
            else:
                add_pos = np.concatenate(
                    (np.asarray([start_coor]), exc_pos_tripled[exc_idxs] + exc_lens_tripled[exc_idxs])
                )
                add_ends = np.concatenate((exc_pos_tripled[exc_idxs] - 1, np.asarray([end_coor])))
        out_pos.extend(int(x) for x in add_pos)
        out_ends.extend(int(x) for x in add_ends)
        out_strands.extend([int(strand)] * int(add_pos.size))

    out_pos_arr = np.asarray(out_pos, dtype=np.int64)
    out_ends_arr = np.asarray(out_ends, dtype=np.int64)
    out_strands_arr = np.asarray(out_strands, dtype=np.int64)
    high = np.flatnonzero(out_pos_arr > sequence_len)
    out_pos_arr[high] -= sequence_len
    out_ends_arr[high] -= sequence_len
    keep = out_pos_arr <= out_ends_arr
    out_pos_strnds = np.column_stack((out_pos_arr[keep], out_strands_arr[keep]))
    out_lens = out_ends_arr[keep] - out_pos_arr[keep] + 1
    out_pos_strnds, out_lens = _join_split_over_oric_regions(sequence_len, out_pos_strnds, out_lens)
    if out_pos_strnds.size == 0:
        return out_pos_strnds, out_lens
    out_pos_strnds[:, 0] = ((out_pos_strnds[:, 0] - 1) % sequence_len) + 1
    order = _sort_region_pos_strnds(out_pos_strnds)
    return out_pos_strnds[order], out_lens[order]


def _intersect_regions_literal(
    sequence_len: int,
    n_compartments: int,
    pos_a: np.ndarray,
    lens_a: np.ndarray,
    pos_b: np.ndarray,
    lens_b: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    pos_a, lens_a = _split_over_oric_regions(sequence_len, pos_a, lens_a)
    if pos_a.size:
        pos_a[:, 0] = ((pos_a[:, 0] - 1) % sequence_len) + 1
        order_a = _sort_region_pos_strnds(pos_a)
        pos_a = pos_a[order_a]
        lens_a = lens_a[order_a]

    pos_b, lens_b = _split_over_oric_regions(sequence_len, pos_b, lens_b)
    if pos_b.size:
        pos_b[:, 0] = ((pos_b[:, 0] - 1) % sequence_len) + 1
        order_b = _sort_region_pos_strnds(pos_b)
        pos_b = pos_b[order_b]
        lens_b = lens_b[order_b]

    out_pos: list[tuple[int, int]] = []
    out_lens: list[int] = []
    for strand in range(1, n_compartments + 1):
        rows_a = pos_a[:, 1] == strand if pos_a.size else np.zeros(0, dtype=bool)
        rows_b = pos_b[:, 1] == strand if pos_b.size else np.zeros(0, dtype=bool)
        pos_only_a = pos_a[rows_a, 0]
        pos_only_b = pos_b[rows_b, 0]
        ln_a = lens_a[rows_a]
        ln_b = lens_b[rows_b]
        i_a = 0
        i_b = 0
        while i_a < pos_only_a.size and i_b < pos_only_b.size:
            if pos_only_a[i_a] <= pos_only_b[i_b]:
                if pos_only_a[i_a] + ln_a[i_a] > pos_only_b[i_b]:
                    out_pos.append((int(pos_only_b[i_b]), strand))
                    if pos_only_a[i_a] + ln_a[i_a] < pos_only_b[i_b] + ln_b[i_b]:
                        out_lens.append(int(pos_only_a[i_a] + ln_a[i_a] - pos_only_b[i_b]))
                        i_a += 1
                    else:
                        out_lens.append(int(ln_b[i_b]))
                        i_b += 1
                else:
                    i_a += 1
            else:
                if pos_only_b[i_b] + ln_b[i_b] > pos_only_a[i_a]:
                    out_pos.append((int(pos_only_a[i_a]), strand))
                    if pos_only_b[i_b] + ln_b[i_b] < pos_only_a[i_a] + ln_a[i_a]:
                        out_lens.append(int(pos_only_b[i_b] + ln_b[i_b] - pos_only_a[i_a]))
                        i_b += 1
                    else:
                        out_lens.append(int(ln_a[i_a]))
                        i_a += 1
                else:
                    i_b += 1
    if not out_pos:
        return np.zeros((0, 2), dtype=np.int64), np.zeros(0, dtype=np.int64)
    return _join_split_over_oric_regions(
        sequence_len,
        np.asarray(out_pos, dtype=np.int64),
        np.asarray(out_lens, dtype=np.int64),
    )


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
        "chromosome_fixture_path": _DEFAULT_CHROMOSOME_FIXTURE_PATH,
        "metabolite_fixture_json_path": _DEFAULT_METABOLITE_FIXTURE_JSON_PATH,
        "trace_path": _DEFAULT_TRACE_PATH,
        "postwarmup_state_path": _DEFAULT_POSTWARMUP_STATE_PATH,
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
        self._load_chromosome_fixture(self.parameters["chromosome_fixture_path"])
        self._load_metabolite_fixture_json(self.parameters["metabolite_fixture_json_path"])
        self._load_trace_anchor(self.parameters["trace_path"])
        seed = int(self.parameters["rng_seed"])
        self._rng = MatlabRandStream(seed)
        self._postwarmup_state = self._load_postwarmup_state(self.parameters["postwarmup_state_path"])
        self._restore_validated_postwarmup_rng(seed=seed)
        self._np_rng = np.random.default_rng(seed)
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
        self._restore_validated_postwarmup_pools()
        self._synthetic_complex_bound: SparseTriplet | None = None
        self._prev_bound_smc_nohint: int | None = None
        self._initialized = False

    def _load_postwarmup_state(self, path: str | Path) -> dict[str, int] | None:
        try:
            resolved = _resolve_data_path(path)
        except FileNotFoundError:
            return None

        artifact = loadmat(str(resolved), squeeze_me=True, struct_as_record=False).get("artifact")
        if artifact is None or not hasattr(artifact, "metadata") or not hasattr(artifact, "post"):
            return None

        metadata = artifact.metadata
        post = artifact.post
        seed = int(np.asarray(getattr(metadata, "seed", 0)).reshape(-1)[0])
        enzymes = np.asarray(getattr(post, "enzymes", np.zeros(2, dtype=np.int64))).reshape(-1)
        bound_enzymes = np.asarray(getattr(post, "boundEnzymes", np.zeros(2, dtype=np.int64))).reshape(-1)
        rand_stream_state = int(np.asarray(getattr(post, "randStreamState", 0)).reshape(-1)[0])
        if enzymes.size <= self.enzyme_index_smc_adp or bound_enzymes.size <= self.enzyme_index_smc_adp:
            return None
        return {
            "seed": seed,
            "rand_stream_state": rand_stream_state,
            "smc": int(enzymes[self.enzyme_index_smc]),
            "smc_adp": int(enzymes[self.enzyme_index_smc_adp]),
            "bound_smc_adp": int(bound_enzymes[self.enzyme_index_smc_adp]),
        }

    def _restore_validated_postwarmup_rng(self, *, seed: int) -> None:
        if self._postwarmup_state is None or int(self._postwarmup_state["seed"]) != int(seed):
            return
        self._rng = MatlabRandStream(seed, generator="mcg16807")
        self._rng.set_state(
            {
                "generator": "mcg16807",
                "seed": int(seed),
                "mcg_state": int(self._postwarmup_state["rand_stream_state"]),
            }
        )

    def _restore_validated_postwarmup_pools(self) -> None:
        if self._postwarmup_state is None:
            return
        self._bound_smc = int(self._postwarmup_state["bound_smc_adp"])
        self._free_smc = int(self._postwarmup_state["smc"])
        self._free_smc_adp = int(self._postwarmup_state["smc_adp"])

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
        self._smc_footprint_5prime = int(math.ceil((self.smc_footprint_bp - 1.0) / 2.0))
        self._smc_footprint_3prime = int(self.smc_footprint_bp - 1.0 - self._smc_footprint_5prime)
        self._smc_exclusion_len = int(max(0, round(self.smc_sep_nt + self.smc_sep_prob_center)))
        self._smc_exclusion_offset = int(
            round((self.smc_footprint_bp - self.smc_sep_nt - self.smc_sep_prob_center) / 2.0)
        )
        self._smc_bindable_span = int(max(1, round(self.smc_footprint_bp)))

        substrates = np.asarray(fx.substrates, dtype=np.float64).reshape(-1)
        self._fixture_initial_atp = float(max(0.0, substrates[self.substrate_index_atp]))

    def _load_chromosome_fixture(self, path: str | Path) -> None:
        resolved = _resolve_data_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.dna_strandedness_ssdna = int(_coerce_scalar(fx.dnaStrandedness_ssDNA))
        self.dna_strandedness_dsdna = int(_coerce_scalar(fx.dnaStrandedness_dsDNA))
        self.monomer_dna_footprints = np.asarray(fx.monomerDNAFootprints, dtype=np.int64).reshape(-1)
        self.complex_dna_footprints = np.asarray(fx.complexDNAFootprints, dtype=np.int64).reshape(-1)
        self.monomer_dna_binding_strandedness = np.asarray(
            fx.monomerDNAFootprintBindingStrandedness,
            dtype=np.int64,
        ).reshape(-1)
        self.monomer_dna_region_strandedness = np.asarray(
            fx.monomerDNAFootprintRegionStrandedness,
            dtype=np.int64,
        ).reshape(-1)
        self.complex_dna_binding_strandedness = np.asarray(
            fx.complexDNAFootprintBindingStrandedness,
            dtype=np.int64,
        ).reshape(-1)
        self.complex_dna_region_strandedness = np.asarray(
            fx.complexDNAFootprintRegionStrandedness,
            dtype=np.int64,
        ).reshape(-1)
        self.smc_binding_strandedness = int(
            self.complex_dna_binding_strandedness[self.smc_adp_global_index - 1]
        )
        self.smc_region_strandedness = int(
            self.complex_dna_region_strandedness[self.smc_adp_global_index - 1]
        )
        self._releasable_monomer_global_indexs_for_smc = self._calc_releasable_global_indexs(
            reaction_bound=np.asarray(
                getattr(fx, "reactionBoundMonomer", np.array([], dtype=np.int64)),
                dtype=np.int64,
            ).reshape(-1),
            catalysis_matrix=np.asarray(
                getattr(fx, "reactionMonomerCatalysisMatrix", np.zeros((0, 0), dtype=np.int64)),
                dtype=np.int64,
            ),
            thresholds=np.asarray(
                getattr(fx, "reactionThresholds", np.array([], dtype=np.int64)),
                dtype=np.int64,
            ).reshape(-1),
        )
        self._releasable_complex_global_indexs_for_smc = self._calc_releasable_global_indexs(
            reaction_bound=np.asarray(
                getattr(fx, "reactionBoundComplex", np.array([], dtype=np.int64)),
                dtype=np.int64,
            ).reshape(-1),
            catalysis_matrix=np.asarray(
                getattr(fx, "reactionComplexCatalysisMatrix", np.zeros((0, 0), dtype=np.int64)),
                dtype=np.int64,
            ),
            thresholds=np.asarray(
                getattr(fx, "reactionThresholds", np.array([], dtype=np.int64)),
                dtype=np.int64,
            ).reshape(-1),
        )

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

    def _load_metabolite_fixture_json(self, path: str | Path) -> None:
        resolved = _resolve_data_path(path)
        with resolved.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        self._m6ad_global_index = int(payload["scalars"]["fixture/m6ADIndexs"])

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
            n_bound, chromosome_field_updates = self._sample_smc_binding_no_hints(
                n_binding_max=n_binding_max,
                chrom_state=states.get("chromosome", {}),
                current_bound_smc=current_bound_smc,
            )
            if n_bound > 0:
                bound_update[self.smc_adp_wid] = float(
                    bound_update.get(self.smc_adp_wid, 0.0) + n_bound
                )
            if chromosome_field_updates is not None:
                for field_name, triplet in chromosome_field_updates.items():
                    chromosome_update[field_name] = triplet.to_state()

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
    ) -> tuple[int, dict[str, SparseTriplet] | None]:
        if n_binding_max <= 0:
            return 0, None

        if not isinstance(chrom_state, dict):
            chrom_state = {}
        store = self._resolve_chromosome_store(chrom_state)
        polymerized = store.get_field("polymerizedRegions")
        if self._has_literal_chromosome_surface(chrom_state):
            complex_bound = store.get_field("complexBoundSites")
            binding_pos_strnds, binding_lens = self._build_binding_regions_literal(
                chromosome_store=store,
                polymerized=polymerized,
            )
            bound_centroids, bound_strands = self._sample_binding_regions_literal(
                pos_strnds=binding_pos_strnds,
                lens=binding_lens,
                n_to_bind=int(n_binding_max),
                sequence_len=polymerized.shape[0],
            )
            n_bound = len(bound_centroids)
            if n_bound == 0:
                return 0, None
            self._consume_inner_bind_sampling_literal(n_bound=n_bound)

            chromosome_updates = self._bind_smc_sites_literal(
                chromosome_store=store,
                complex_bound=complex_bound,
                bound_centroids=bound_centroids,
                bound_strands=bound_strands,
                sequence_len=polymerized.shape[0],
            )
            if not chromosome_updates:
                return n_bound, None
            return n_bound, chromosome_updates

        return self._sample_smc_binding_fallback(
            chrom_state=chrom_state,
            current_bound_smc=int(current_bound_smc),
            n_binding_max=int(n_binding_max),
            polymerized=polymerized,
        )

    def _sample_smc_binding_fallback(
        self,
        *,
        chrom_state: dict[str, Any],
        current_bound_smc: int,
        n_binding_max: int,
        polymerized: SparseTriplet,
    ) -> tuple[int, dict[str, SparseTriplet] | None]:
        store = self._resolve_chromosome_store(chrom_state)
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
                return n_bound, {"complexBoundSites": self._synthetic_complex_bound}
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
            bind_cap = min(
                bind_cap,
                max(0, self.default_target_bound - int(current_bound_smc)),
            )
        bound_positions, bound_strands = self._sample_binding_positions(
            intervals_by_strand=intervals_by_strand,
            n_to_bind=bind_cap,
            sequence_len=polymerized.shape[0],
        )
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
        return n_bound, {"complexBoundSites": complex_next}

    def _has_literal_chromosome_surface(self, chrom_state: dict[str, Any]) -> bool:
        return any(isinstance(chrom_state.get(field_name), dict) for field_name in _LITERAL_OCCUPANCY_FIELDS)

    def _build_binding_regions_literal(
        self,
        *,
        chromosome_store: ChromosomeStore,
        polymerized: SparseTriplet,
    ) -> tuple[np.ndarray, np.ndarray]:
        return self._build_outer_binding_regions_literal(
            chromosome_store=chromosome_store,
            polymerized=polymerized,
        )

    def _build_accessible_intervals_literal(
        self,
        *,
        chromosome_store: ChromosomeStore,
        polymerized: SparseTriplet,
    ) -> dict[int, list[tuple[int, int]]]:
        full_intervals = self._intervals_from_polymerized(polymerized)
        intervals_by_strand = self._build_polymerized_intervals_literal(
            full_intervals=full_intervals,
            n_compartments=polymerized.shape[1],
        )
        sequence_len = polymerized.shape[0]

        monomer_bound = chromosome_store.get_field("monomerBoundSites")
        for pos, strand, global_idx in monomer_bound.to_regions():
            if int(global_idx) in self._releasable_monomer_global_indexs_for_smc:
                continue
            footprint = self._footprint_by_global_index(
                global_index=int(global_idx),
                footprints=self.monomer_dna_footprints,
            )
            intervals_by_strand = self._exclude_bound_site(
                intervals_by_strand=intervals_by_strand,
                site_pos=int(pos),
                site_strand=int(strand),
                footprint=footprint,
                binding_strandedness=self._strandedness_by_global_index(
                    global_index=int(global_idx),
                    strandednesses=self.monomer_dna_binding_strandedness,
                    default=self.dna_strandedness_ssdna,
                ),
                sequence_len=sequence_len,
            )

        complex_bound = chromosome_store.get_field("complexBoundSites")
        for pos, strand, global_idx in complex_bound.to_regions():
            if int(global_idx) in self._releasable_complex_global_indexs_for_smc:
                continue
            footprint = self._footprint_by_global_index(
                global_index=int(global_idx),
                footprints=self.complex_dna_footprints,
            )
            intervals_by_strand = self._exclude_bound_site(
                intervals_by_strand=intervals_by_strand,
                site_pos=int(pos),
                site_strand=int(strand),
                footprint=footprint,
                binding_strandedness=self._strandedness_by_global_index(
                    global_index=int(global_idx),
                    strandednesses=self.complex_dna_binding_strandedness,
                    default=self.dna_strandedness_ssdna,
                ),
                sequence_len=sequence_len,
            )

        for pos, strand in self._iter_damaged_sites_literal(
            chromosome_store=chromosome_store,
            sequence_len=sequence_len,
        ):
            intervals_by_strand = self._exclude_bound_site(
                intervals_by_strand=intervals_by_strand,
                site_pos=pos,
                site_strand=strand,
                footprint=1,
                binding_strandedness=self.dna_strandedness_ssdna,
                sequence_len=sequence_len,
            )

        for pos, strand, global_idx in complex_bound.to_regions():
            if int(global_idx) != self.smc_adp_global_index:
                continue
            intervals_by_strand = self._exclude_smc_spacing_literal(
                intervals_by_strand=intervals_by_strand,
                site_pos=int(pos),
                site_strand=int(strand),
                sequence_len=sequence_len,
            )
        return intervals_by_strand

    def _build_double_stranded_regions_literal(
        self,
        polymerized: SparseTriplet,
    ) -> tuple[np.ndarray, np.ndarray]:
        full_intervals = self._intervals_from_polymerized(polymerized)
        out_pos: list[tuple[int, int]] = []
        out_lens: list[int] = []
        n_compartments = int(polymerized.shape[1])
        for strand_start in range(0, max(0, n_compartments - 1), 2):
            pair_id = strand_start // 2 + 1
            intervals = _intersect_intervals(
                full_intervals.get(strand_start, []),
                full_intervals.get(strand_start + 1, []),
            )
            for start0, end0 in intervals:
                out_pos.append((int(start0) + 1, pair_id))
                out_lens.append(int(end0 - start0 + 1))
        if not out_pos:
            return np.zeros((0, 2), dtype=np.int64), np.zeros(0, dtype=np.int64)
        return np.asarray(out_pos, dtype=np.int64), np.asarray(out_lens, dtype=np.int64)

    def _build_accessible_regions_literal(
        self,
        *,
        chromosome_store: ChromosomeStore,
        polymerized: SparseTriplet,
    ) -> tuple[np.ndarray, np.ndarray]:
        sequence_len = int(polymerized.shape[0])
        pol_pos, pol_lens = self._build_double_stranded_regions_literal(polymerized)
        if pol_pos.size == 0:
            return pol_pos, pol_lens

        exc_pos: list[tuple[int, int]] = []
        exc_lens: list[int] = []

        monomer_bound = chromosome_store.get_field("monomerBoundSites")
        for pos0, strand0, global_idx in monomer_bound.to_regions():
            global_i = int(global_idx)
            if global_i in self._releasable_monomer_global_indexs_for_smc:
                continue
            pos1 = int(pos0) + 1
            strand1 = int(strand0) + 1
            footprint = self._footprint_by_global_index(
                global_index=global_i,
                footprints=self.monomer_dna_footprints,
            )
            strandedness = self._strandedness_by_global_index(
                global_index=global_i,
                strandednesses=self.monomer_dna_binding_strandedness,
                default=self.dna_strandedness_ssdna,
            )
            if strandedness == self.dna_strandedness_dsdna:
                pair_odd = 2 * int(math.ceil(strand1 / 2.0)) - 1
                exc_pos.append((pos1, pair_odd))
                exc_pos.append((pos1, pair_odd + 1))
                exc_lens.extend((footprint, footprint))
            else:
                exc_pos.append((pos1, strand1))
                exc_lens.append(footprint)

        complex_bound = chromosome_store.get_field("complexBoundSites")
        for pos0, strand0, global_idx in complex_bound.to_regions():
            global_i = int(global_idx)
            if global_i in self._releasable_complex_global_indexs_for_smc:
                continue
            pos1 = int(pos0) + 1
            strand1 = int(strand0) + 1
            footprint = self._footprint_by_global_index(
                global_index=global_i,
                footprints=self.complex_dna_footprints,
            )
            strandedness = self._strandedness_by_global_index(
                global_index=global_i,
                strandednesses=self.complex_dna_binding_strandedness,
                default=self.dna_strandedness_ssdna,
            )
            if strandedness == self.dna_strandedness_dsdna:
                pair_odd = 2 * int(math.ceil(strand1 / 2.0)) - 1
                exc_pos.append((pos1, pair_odd))
                exc_pos.append((pos1, pair_odd + 1))
                exc_lens.extend((footprint, footprint))
            else:
                exc_pos.append((pos1, strand1))
                exc_lens.append(footprint)

        for pos0, strand0 in self._iter_damaged_sites_literal(
            chromosome_store=chromosome_store,
            sequence_len=sequence_len,
        ):
            exc_pos.append((int(pos0) + 1, int(strand0) + 1))
            exc_lens.append(1)

        exc_pos_arr = np.asarray(exc_pos, dtype=np.int64) if exc_pos else np.zeros((0, 2), dtype=np.int64)
        exc_lens_arr = np.asarray(exc_lens, dtype=np.int64) if exc_lens else np.zeros(0, dtype=np.int64)
        if exc_pos_arr.size:
            exc_pos_arr[:, 1] = np.ceil(exc_pos_arr[:, 1] / 2.0).astype(np.int64)
        pol_pos = pol_pos.copy()
        rgn_pos, rgn_lens = _exclude_regions_literal(
            sequence_len,
            pol_pos,
            pol_lens,
            exc_pos_arr,
            exc_lens_arr,
        )
        keep = np.flatnonzero(rgn_lens >= int(self.smc_footprint_bp))
        rgn_pos = rgn_pos[keep]
        rgn_lens = rgn_lens[keep]
        if rgn_pos.size:
            rgn_pos = rgn_pos.copy()
            rgn_pos[:, 1] = 2 * rgn_pos[:, 1] - 1
        return rgn_pos, rgn_lens

    def _build_outer_binding_regions_literal(
        self,
        *,
        chromosome_store: ChromosomeStore,
        polymerized: SparseTriplet,
    ) -> tuple[np.ndarray, np.ndarray]:
        sequence_len = int(polymerized.shape[0])
        n_compartments = int(polymerized.shape[1])
        caller_rows = [
            (int(pos0) + 1, int(strand0) + 1)
            for pos0, strand0, length in polymerized.to_regions()
            if int(length) > 0
        ]
        caller_lens = [int(length) for _, _, length in polymerized.to_regions() if int(length) > 0]
        caller_pos = np.asarray(caller_rows, dtype=np.int64) if caller_rows else np.zeros((0, 2), dtype=np.int64)
        caller_lens_arr = np.asarray(caller_lens, dtype=np.int64) if caller_lens else np.zeros(0, dtype=np.int64)

        smc_pos_rows: list[tuple[int, int]] = []
        complex_bound = chromosome_store.get_field("complexBoundSites")
        for pos0, strand0, global_idx in complex_bound.to_regions():
            if int(global_idx) != int(self.smc_adp_global_index):
                continue
            pos1 = int(pos0) + 1
            strand1 = int(strand0) + 1
            shifted = int(
                (
                    (
                        pos1
                        - self.smc_sep_nt / 2.0
                        - self.smc_sep_prob_center / 2.0
                        + self.smc_footprint_bp / 2.0
                        - 1.0
                    )
                    % sequence_len
                )
                + 1
            )
            pair_odd = 2 * int(math.ceil(strand1 / 2.0)) - 1
            smc_pos_rows.append((shifted, pair_odd))
            smc_pos_rows.append((shifted, pair_odd + 1))

        if smc_pos_rows:
            smc_pos = np.asarray(smc_pos_rows, dtype=np.int64)
            smc_lens = np.full(
                smc_pos.shape[0],
                int(self.smc_sep_nt + self.smc_sep_prob_center),
                dtype=np.int64,
            )
            caller_pos, caller_lens_arr = _exclude_regions_literal(
                sequence_len,
                caller_pos,
                caller_lens_arr,
                smc_pos,
                smc_lens,
            )

        accessible_pos, accessible_lens = self._build_accessible_regions_literal(
            chromosome_store=chromosome_store,
            polymerized=polymerized,
        )
        if caller_pos.size == 0 or accessible_pos.size == 0:
            return np.zeros((0, 2), dtype=np.int64), np.zeros(0, dtype=np.int64)
        return _intersect_regions_literal(
            sequence_len,
            n_compartments,
            accessible_pos,
            accessible_lens,
            caller_pos,
            caller_lens_arr,
        )

    def _sample_binding_regions_literal(
        self,
        *,
        pos_strnds: np.ndarray,
        lens: np.ndarray,
        n_to_bind: int,
        sequence_len: int,
    ) -> tuple[list[int], list[int]]:
        if n_to_bind <= 0 or sequence_len <= 0 or pos_strnds.size == 0:
            return [], []
        rgn_pos = pos_strnds.astype(np.int64, copy=True)
        rgn_lens = lens.astype(np.int64, copy=True)
        bound_positions: list[int] = []
        bound_strands: list[int] = []
        for _ in range(int(n_to_bind)):
            rgn_probs = np.maximum(0, rgn_lens - int(self.smc_footprint_bp) + 1).astype(np.float64)
            if not np.any(rgn_probs):
                break
            rgn_idx = int(self._rng.randsample(int(rgn_probs.size), 1, True, rgn_probs)[0]) - 1
            n_bind_positions = int(rgn_lens[rgn_idx] - int(self.smc_footprint_bp) + 1)
            if n_bind_positions <= 0:
                continue
            offset = int(math.ceil(float(self._rng.rand()) * float(n_bind_positions)) - 1)
            if offset < 0:
                offset = 0
            bind_pos1 = int(rgn_pos[rgn_idx, 0] + offset)
            bind_strand1 = int(rgn_pos[rgn_idx, 1])
            bound_positions.append(int((bind_pos1 - 1) % sequence_len))
            bound_strands.append(bind_strand1 - 1)
            exc_pos = np.asarray(
                [[
                    int(
                        (
                            (
                                bind_pos1
                                - self.smc_sep_nt / 2.0
                                - self.smc_sep_prob_center / 2.0
                                + self.smc_footprint_bp / 2.0
                                - 1.0
                            )
                            % sequence_len
                        )
                        + 1
                    ),
                    bind_strand1,
                ]],
                dtype=np.int64,
            )
            exc_len = np.asarray([int(self.smc_sep_nt + self.smc_sep_prob_center)], dtype=np.int64)
            rgn_pos, rgn_lens = _exclude_regions_literal(
                sequence_len,
                rgn_pos,
                rgn_lens,
                exc_pos,
                exc_len,
            )
        return bound_positions, bound_strands

    def _consume_inner_bind_sampling_literal(self, *, n_bound: int) -> None:
        n_bound_i = max(0, int(n_bound))
        if n_bound_i <= 0:
            return
        _ = self._rng.randsample(
            n_bound_i,
            n_bound_i,
            False,
            np.ones(n_bound_i, dtype=np.float64),
        )

    def _bind_smc_sites_literal(
        self,
        *,
        chromosome_store: ChromosomeStore,
        complex_bound: SparseTriplet,
        bound_centroids: list[int],
        bound_strands: list[int],
        sequence_len: int,
    ) -> dict[str, SparseTriplet]:
        if not bound_centroids:
            return {}
        monomer_bound = chromosome_store.get_field("monomerBoundSites")
        bound_positions = self._smc_centroids_to_start_positions(
            bound_centroids=bound_centroids,
            bound_strands=bound_strands,
            sequence_len=sequence_len,
        )
        monomer_next = self._release_overlapping_releasable_bound_sites_literal(
            triplet=monomer_bound,
            releasable_global_indexs=self._releasable_monomer_global_indexs_for_smc,
            footprints=self.monomer_dna_footprints,
            release_positions=bound_positions,
            release_strands=bound_strands,
            release_length=int(self.smc_footprint_bp),
            sequence_len=sequence_len,
        )
        complex_released = self._release_overlapping_releasable_bound_sites_literal(
            triplet=complex_bound,
            releasable_global_indexs=self._releasable_complex_global_indexs_for_smc,
            footprints=self.complex_dna_footprints,
            release_positions=bound_positions,
            release_strands=bound_strands,
            release_length=int(self.smc_footprint_bp),
            sequence_len=sequence_len,
        )
        complex_next = self._append_bound_sites(
            complex_bound=complex_released,
            bound_positions=bound_positions,
            bound_strands=bound_strands,
        )
        updates: dict[str, SparseTriplet] = {"complexBoundSites": complex_next}
        if (
            monomer_next.shape != monomer_bound.shape
            or not np.array_equal(monomer_next.positions, monomer_bound.positions)
            or not np.array_equal(monomer_next.strands, monomer_bound.strands)
            or not np.array_equal(monomer_next.values, monomer_bound.values)
        ):
            updates["monomerBoundSites"] = monomer_next
        return updates

    def _smc_centroids_to_start_positions(
        self,
        *,
        bound_centroids: list[int],
        bound_strands: list[int],
        sequence_len: int,
    ) -> list[int]:
        del bound_strands, sequence_len
        # WholeCell stores the sampled binding positions directly here because
        # bindProteinToChromosomeStochastically passes
        # isPositionsStrandFootprintCentroid = false into the stable bind.
        return [int(centroid) for centroid in bound_centroids]

    def _release_overlapping_releasable_bound_sites_literal(
        self,
        *,
        triplet: SparseTriplet,
        releasable_global_indexs: frozenset[int],
        footprints: np.ndarray,
        release_positions: list[int],
        release_strands: list[int],
        release_length: int,
        sequence_len: int,
    ) -> SparseTriplet:
        if triplet.calc_num_edges() == 0 or not releasable_global_indexs or not release_positions:
            return triplet

        release_intervals = [
            (
                int(release_strand) // 2,
                _split_circular_region(int(release_pos), int(release_length), int(sequence_len)),
            )
            for release_pos, release_strand in zip(release_positions, release_strands, strict=False)
        ]
        keep = np.ones(triplet.values.size, dtype=bool)
        for idx, (pos, strand, global_idx) in enumerate(triplet.to_regions()):
            global_i = int(global_idx)
            if global_i not in releasable_global_indexs:
                continue
            footprint = self._footprint_by_global_index(global_index=global_i, footprints=footprints)
            if footprint <= 0:
                continue
            bound_pair = int(strand) // 2
            bound_intervals = _split_circular_region(int(pos), int(footprint), int(sequence_len))
            for release_pair, intervals in release_intervals:
                if int(release_pair) != bound_pair:
                    continue
                if _intervals_overlap(bound_intervals, intervals):
                    keep[idx] = False
                    break
        if np.all(keep):
            return triplet
        return SparseTriplet(
            positions=triplet.positions[keep],
            strands=triplet.strands[keep],
            values=triplet.values[keep],
            shape=triplet.shape,
        )

    def _build_polymerized_intervals_literal(
        self,
        *,
        full_intervals: dict[int, list[tuple[int, int]]],
        n_compartments: int,
    ) -> dict[int, list[tuple[int, int]]]:
        if (
            self.smc_region_strandedness == self.dna_strandedness_dsdna
            and self.smc_binding_strandedness == self.dna_strandedness_dsdna
        ):
            intervals_by_strand: dict[int, list[tuple[int, int]]] = {}
            for strand_start in range(0, max(0, int(n_compartments) - 1), 2):
                strand_end = strand_start + 1
                intervals_by_strand[strand_start] = _merge_intervals(
                    _intersect_intervals(
                        full_intervals.get(strand_start, []),
                        full_intervals.get(strand_end, []),
                    )
                )
            return intervals_by_strand
        return {strand: list(intervals) for strand, intervals in full_intervals.items()}

    def _intervals_from_polymerized(
        self,
        polymerized: SparseTriplet,
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
        return intervals_by_strand

    def _footprint_by_global_index(
        self,
        *,
        global_index: int,
        footprints: np.ndarray,
    ) -> int:
        idx = int(global_index) - 1
        if idx < 0 or idx >= footprints.size:
            return 0
        return int(max(0, footprints[idx]))

    def _calc_releasable_global_indexs(
        self,
        *,
        reaction_bound: np.ndarray,
        catalysis_matrix: np.ndarray,
        thresholds: np.ndarray,
    ) -> frozenset[int]:
        if (
            reaction_bound.size == 0
            or catalysis_matrix.ndim != 2
            or catalysis_matrix.size == 0
            or thresholds.size == 0
            or catalysis_matrix.shape[0] != thresholds.size
            or self.smc_adp_global_index <= 0
            or catalysis_matrix.shape[1] < self.smc_adp_global_index
        ):
            return frozenset()
        active = catalysis_matrix[:, self.smc_adp_global_index - 1] >= thresholds
        releasable = reaction_bound * active.astype(np.int64, copy=False)
        return frozenset(int(x) for x in releasable.tolist() if int(x) != 0)

    def _strandedness_by_global_index(
        self,
        *,
        global_index: int,
        strandednesses: np.ndarray,
        default: int,
    ) -> int:
        idx = int(global_index) - 1
        if idx < 0 or idx >= strandednesses.size:
            return int(default)
        return int(strandednesses[idx])

    def _exclude_bound_site(
        self,
        *,
        intervals_by_strand: dict[int, list[tuple[int, int]]],
        site_pos: int,
        site_strand: int,
        footprint: int,
        binding_strandedness: int,
        sequence_len: int,
    ) -> dict[int, list[tuple[int, int]]]:
        if footprint <= 0:
            return intervals_by_strand
        target_strands = self._literal_target_strands(
            site_strand=int(site_strand),
            binding_strandedness=int(binding_strandedness),
        )
        for strand in target_strands:
            intervals = intervals_by_strand.get(strand, [])
            for lo, hi in _split_circular_region(int(site_pos), int(footprint), sequence_len):
                intervals = _exclude_interval(intervals, lo, hi)
            intervals_by_strand[strand] = _merge_intervals(intervals)
        return intervals_by_strand

    def _literal_target_strands(
        self,
        *,
        site_strand: int,
        binding_strandedness: int,
    ) -> tuple[int, ...]:
        strand_i = int(site_strand)
        if self.smc_binding_strandedness == self.dna_strandedness_dsdna:
            return (2 * (strand_i // 2),)
        if int(binding_strandedness) == self.dna_strandedness_dsdna:
            strand_start = 2 * (strand_i // 2)
            return (strand_start, strand_start + 1)
        return (strand_i,)

    def _exclude_smc_spacing_literal(
        self,
        *,
        intervals_by_strand: dict[int, list[tuple[int, int]]],
        site_pos: int,
        site_strand: int,
        sequence_len: int,
    ) -> dict[int, list[tuple[int, int]]]:
        exclude_start = (int(site_pos) + self._smc_exclusion_offset) % sequence_len
        for strand in self._literal_target_strands(
            site_strand=int(site_strand),
            binding_strandedness=self.dna_strandedness_dsdna,
        ):
            intervals = intervals_by_strand.get(strand, [])
            for lo, hi in _split_circular_region(
                exclude_start,
                self._smc_exclusion_len,
                sequence_len,
            ):
                intervals = _exclude_interval(intervals, lo, hi)
            intervals_by_strand[strand] = _merge_intervals(intervals)
        return intervals_by_strand

    def _iter_damaged_sites_literal(
        self,
        *,
        chromosome_store: ChromosomeStore,
        sequence_len: int,
    ) -> list[tuple[int, int]]:
        sites: list[tuple[int, int]] = []
        for field_name in ("damagedBases", "gapSites", "abasicSites", "damagedSugarPhosphates"):
            triplet = chromosome_store.get_field(field_name)
            for pos, strand, value in triplet.to_regions():
                if field_name == "damagedBases" and int(value) == int(self._m6ad_global_index):
                    continue
                sites.append((int(pos), int(strand)))

        for field_name in ("intrastrandCrossLinks",):
            triplet = chromosome_store.get_field(field_name)
            for pos, strand, _ in triplet.to_regions():
                pos_i = int(pos)
                strand_i = int(strand)
                sites.append((pos_i, strand_i))
                sites.append(
                    (
                        self._shift_damage_position(
                            pos=pos_i,
                            strand=strand_i,
                            sequence_len=sequence_len,
                            shift_kind="base5prime",
                        ),
                        strand_i,
                    )
                )

        for field_name in ("strandBreaks",):
            triplet = chromosome_store.get_field(field_name)
            for pos, strand, _ in triplet.to_regions():
                pos_i = int(pos)
                strand_i = int(strand)
                sites.append((pos_i, strand_i))
                sites.append(
                    (
                        self._shift_damage_position(
                            pos=pos_i,
                            strand=strand_i,
                            sequence_len=sequence_len,
                            shift_kind="unshift_bond5prime",
                        ),
                        strand_i,
                    )
                )
                sites.append(
                    (
                        self._shift_damage_position(
                            pos=pos_i,
                            strand=strand_i,
                            sequence_len=sequence_len,
                            shift_kind="unshift_bond3prime",
                        ),
                        strand_i,
                    )
                )
        for field_name in ("hollidayJunctions",):
            triplet = chromosome_store.get_field(field_name)
            for pos, strand, _ in triplet.to_regions():
                pos_i = int(pos)
                strand_i = int(strand)
                sites.append((pos_i, strand_i))
                sites.append(
                    (
                        self._shift_damage_position(
                            pos=pos_i,
                            strand=strand_i,
                            sequence_len=sequence_len,
                            shift_kind="bond5prime",
                        ),
                        strand_i,
                    )
                )
                sites.append(
                    (
                        self._shift_damage_position(
                            pos=pos_i,
                            strand=strand_i,
                            sequence_len=sequence_len,
                            shift_kind="bond3prime",
                        ),
                        strand_i,
                    )
                )
        return sites

    def _shift_damage_position(
        self,
        *,
        pos: int,
        strand: int,
        sequence_len: int,
        shift_kind: str,
    ) -> int:
        strand_i = int(strand)
        if shift_kind == "base3prime":
            delta = 1 if strand_i % 2 == 0 else -1
        elif shift_kind == "base5prime":
            delta = -1 if strand_i % 2 == 0 else 1
        elif shift_kind == "bond5prime":
            delta = -1 if strand_i % 2 == 0 else 0
        elif shift_kind == "bond3prime":
            delta = 0 if strand_i % 2 == 0 else -1
        elif shift_kind == "unshift_bond5prime":
            delta = 1 if strand_i % 2 == 0 else 0
        elif shift_kind == "unshift_bond3prime":
            delta = 0 if strand_i % 2 == 0 else 1
        else:
            raise ValueError(f"unsupported damage shift kind: {shift_kind}")
        return int((int(pos) + delta) % int(sequence_len))

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
            keep_idx = np.sort(np.asarray(self._np_rng.choice(current, size=desired, replace=False)))
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
        intervals_by_strand = self._intervals_from_polymerized(polymerized)

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
            regions.sort(key=lambda region: (int(region[0]), int(region[1])))
            if not regions:
                break

            weights = np.asarray(
                [max(0, int(length) - self._smc_bindable_span + 1) for _, _, length in regions],
                dtype=np.float64,
            )
            total_weight = float(weights.sum())
            if total_weight <= 0.0:
                break

            region_pick_u = float(self._rng.rand())
            cumulative = np.cumsum(weights, dtype=np.float64)
            threshold = region_pick_u * total_weight
            region_idx = int(np.searchsorted(cumulative, threshold, side="right"))
            if region_idx >= len(regions):
                region_idx = len(regions) - 1
            region_start, region_strand, region_len = regions[region_idx]
            max_offset = int(region_len) - self._smc_bindable_span
            if max_offset < 0:
                continue
            # Mirror MATLAB calcBindingPosition: ceil(rand * n_bind_positions) - 1.
            rand_real = float(self._rng.rand())
            n_bind_positions = float(max_offset + 1)
            if n_bind_positions <= 1.0:
                offset = 0
            else:
                u = max(
                    float(np.nextafter(0.0, 1.0)),
                    min(rand_real, float(np.nextafter(1.0, 0.0))),
                )
                offset = max(0, int(math.ceil(u * n_bind_positions)) - 1)
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
        sampled = int(self._np_rng.poisson(expected))
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
