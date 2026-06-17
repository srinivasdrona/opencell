"""Vivarium Process for Karr DNADamage (Karr-light v1).

Karr primary source:
- data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/DNADamage.m
- docs/karr_extracts/process/04_DNADamage.md

This v1 implements only stochastic lesion creation and advisory replication
stall signaling. Repair chemistry and lesion-class-specific chromosome arrays
(`gapSites`, `damagedBases`, `strandBreaks`, etc.) are deferred to pc-t7/v2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet, sparse_triplet_schema
from opencell.vivarium.chromosome_views import current_damage_sites

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/DNADamage_flat.mat"
_DEFAULT_TRACE_PATH = "data/m1_sources/karr_native/per_process_traces/DNADamage_100ticks.mat"
_DEFAULT_SEQUENCE_LENGTH_NT = 580_076
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
_SPARSE_DAMAGE_FIELDS = (*_DAMAGE_FIELDS, "intrastrandCrossLinks")
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
        "trace_path": _DEFAULT_TRACE_PATH,
        "use_trace_rates_if_available": True,
        "rng_seed": 0,
        "time_step": 1.0,
        "sequence_length_nt": None,
        "enforce_unique_positions": True,
        "kind_rates_per_s": dict(_DEFAULT_KIND_RATES_PER_S),
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
        self._load_schema_observables(self.parameters.get("fixture_path", _DEFAULT_FIXTURE_PATH))

        configured_rates = self.parameters.get("kind_rates_per_s") or {}
        self.kind_rates_per_s = {
            kind: max(0.0, float(configured_rates.get(kind, _DEFAULT_KIND_RATES_PER_S[kind])))
            for kind in self.damage_kinds
        }
        self.trace_kind_rates_per_s = self._load_trace_kind_rates(
            self.parameters.get("trace_path", _DEFAULT_TRACE_PATH)
        )
        self.used_trace_rates = False
        if bool(self.parameters.get("use_trace_rates_if_available", True)) and self.trace_kind_rates_per_s:
            for kind in self.damage_kinds:
                if kind in self.trace_kind_rates_per_s:
                    self.kind_rates_per_s[kind] = max(0.0, float(self.trace_kind_rates_per_s[kind]))
            self.used_trace_rates = True

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
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])
        self._tick_index += 1
        if dt <= 0:
            return {}

        chromosome_state = states.get("chromosome", {})
        existing_sites = current_damage_sites(states)
        occupied_positions = _coerce_position_set(existing_sites)
        occupied_positions.update(self._occupied_positions_from_sparse(chromosome_state))
        fork_positions = self._active_fork_positions(chromosome_state)
        sparse_by_field = self._sparse_damage_entries(chromosome_state)
        touched_sparse_fields: set[str] = set()

        new_sites: list[dict[str, Any]] = []
        substrates_state = states.get("substrates", {})
        for kind in self.damage_kinds:
            rate_per_s = max(0.0, float(self.kind_rates_per_s.get(kind, 0.0)))

            # Radiation gating: Karr DNADamage.m L549-551 multiplies
            # selectionProbability by the radiation substrate count.
            # If the gating substrate is absent or 0, the kind doesn't fire.
            gate_wid = _RADIATION_GATE.get(kind)
            if gate_wid is not None:
                gate_count = max(0.0, float(substrates_state.get(gate_wid, 0.0)))
                rate_per_s *= gate_count

            lam = rate_per_s * dt
            if lam <= 0.0:
                continue

            n_events = int(self._rng.poisson(lam))
            if n_events <= 0:
                continue

            sampled_positions = self._sample_positions(
                n_events=n_events,
                occupied_positions=occupied_positions,
            )
            for event_idx, pos in enumerate(sampled_positions):
                site_id = f"{kind}@{int(pos)}@tick{self._tick_index}@{event_idx}"
                damage = {
                    "id": site_id,
                    "site_id": site_id,
                    "position": int(pos),
                    "kind": str(kind),
                    "age_ticks": 0,
                }
                new_sites.append(damage)
                chrom_field = _DAMAGE_KIND_TO_CHROMOSOME_FIELD[str(kind)]
                strand = int(self._rng.integers(0, self.chromosome_shape[1]))
                sparse_key = (int(pos) - 1, strand)
                sparse_by_field[chrom_field][sparse_key] = max(1, sparse_by_field[chrom_field].get(sparse_key, 0))
                touched_sparse_fields.add(chrom_field)
                if self.enforce_unique_positions:
                    occupied_positions.add(int(pos))

        if not new_sites:
            return {}

        fork_hit = self._fork_hit(new_sites, fork_positions)
        chromosome_update: dict[str, Any] = {"damage_events_cumulative": new_sites}
        chromosome_update.update(self._sparse_damage_writeback(sparse_by_field, touched_sparse_fields))
        if fork_hit:
            chromosome_update["replication_stall_flag"] = 1.0

        return {"chromosome": chromosome_update}

    def expected_events_per_tick(self, timestep: float = 1.0) -> dict[str, float]:
        dt = max(0.0, float(timestep))
        return {kind: float(self.kind_rates_per_s[kind] * dt) for kind in self.damage_kinds}

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

    def _load_trace_kind_rates(self, trace_path: str | Path) -> dict[str, float]:
        resolved = _resolve_path(trace_path)
        if not resolved.exists():
            return {}

        try:
            trace = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        except Exception:
            return {}

        out: dict[str, float] = {}
        for kind in self.damage_kinds:
            candidates = (
                kind,
                f"{kind}_events",
                f"{kind}_count",
                f"{kind}_counts",
                f"damage_{kind}",
            )
            for key in candidates:
                if key not in trace:
                    continue
                arr = np.asarray(trace[key], dtype=np.float64).reshape(-1)
                if arr.size <= 0:
                    continue
                if arr.size == 1:
                    rate = max(0.0, float(arr[0]))
                else:
                    deltas = np.diff(arr)
                    rate = max(0.0, float(np.mean(np.maximum(deltas, 0.0))))
                out[kind] = rate
                break
        return out


__all__ = ["KarrDNADamageProcess"]
