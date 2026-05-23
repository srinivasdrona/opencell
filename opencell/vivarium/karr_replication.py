"""Vivarium Process port of Karr's Replication (Karr-LIGHT v1).

Karr-LIGHT v1 scope:
- consumes initiation state from pc-t1 via ``chromosome.replication_state``
- tracks bidirectional fork progression as bulk counters
- requests/consumes dNTPs + ATP through ``KarrAllocationStep`` contract
- emits replication completion state + event when both forks reach terC

Deferred to v2:
- SSB binding/release cycle
- Okazaki fragment strand-level machinery
- ligase fragment events and leading/lagging asymmetry
- RNAP collision dwell / pause mechanics
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/Replication_flat.mat"
_DEFAULT_CHROMOSOME_FIXTURE_PATH = "data/karr_fixtures/per_process/Chromosome_flat.mat"


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


def _read_nonnegative_int(value: object) -> int:
    return int(max(0.0, np.floor(float(value))))


class KarrReplicationProcess(Process):
    """Karr Process_Replication fork progression (light bulk form)."""

    name = "karr_replication"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "chromosome_fixture_path": _DEFAULT_CHROMOSOME_FIXTURE_PATH,
        "time_step": 1.0,
        "fork_polymerization_rate_bp_per_s": None,
        "helicase_atp_per_bp": 1.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixtures(
            fixture_path=self.parameters["fixture_path"],
            chromosome_fixture_path=self.parameters["chromosome_fixture_path"],
        )
        rate_override = self.parameters.get("fork_polymerization_rate_bp_per_s")
        self.fork_polymerization_rate_bp_per_s = (
            float(rate_override)
            if rate_override is not None
            else float(self.dna_polymerase_elongation_rate_bp_per_s)
        )
        self.helicase_atp_per_bp = max(0.0, float(self.parameters["helicase_atp_per_bp"]))
        self._completion_emitted = False

    def _load_fixtures(
        self,
        fixture_path: str | Path,
        chromosome_fixture_path: str | Path,
    ) -> None:
        replication_path = _resolve_fixture_path(fixture_path)
        chromosome_path = _resolve_fixture_path(chromosome_fixture_path)

        replication_mat = loadmat(str(replication_path), squeeze_me=True, struct_as_record=False)
        replication_fixture = replication_mat["data"].fixture

        chromosome_mat = loadmat(str(chromosome_path), squeeze_me=True, struct_as_record=False)
        chromosome_fixture = chromosome_mat["data"].fixture

        self.substrate_wids = _parse_wid_array(replication_fixture.substrateWholeCellModelIDs)
        self.substrate_index_dntp = (_parse_index_array(replication_fixture.substrateIndexs_dntp) - 1).tolist()
        self.substrate_index_atp = int(_coerce_scalar(replication_fixture.substrateIndexs_atp)) - 1

        self.dntp_wids = [self.substrate_wids[int(idx)] for idx in self.substrate_index_dntp]
        if len(self.dntp_wids) != 4:
            raise ValueError(f"Expected 4 dNTP IDs, got {len(self.dntp_wids)}")
        self.atp_wid = self.substrate_wids[self.substrate_index_atp]

        self.dna_polymerase_elongation_rate_bp_per_s = float(
            _coerce_scalar(replication_fixture.dnaPolymeraseElongationRate)
        )
        self.oric_position_bp = int(_coerce_scalar(replication_fixture.oriCPosition))
        self.terc_position_bp = int(_coerce_scalar(replication_fixture.terCPosition))

        sequence_len_bp = int(_coerce_scalar(chromosome_fixture.sequenceLen))
        sequence_gc_content = float(_coerce_scalar(chromosome_fixture.sequenceGCContent))
        self.sequence_len_bp = max(1, sequence_len_bp)
        self.sequence_gc_content = float(np.clip(sequence_gc_content, a_min=0.0, a_max=1.0))
        at_fraction = (1.0 - self.sequence_gc_content) / 2.0
        gc_fraction = self.sequence_gc_content / 2.0

        # Datp/Dctp/Dgtp/Dttp order from fixture substrateIndexs_dntp.
        self._dntp_fractions = np.asarray([at_fraction, gc_fraction, gc_fraction, at_fraction])
        self._dntp_fractions = self._dntp_fractions / np.sum(self._dntp_fractions)

    def ports_schema(self) -> dict[str, Any]:
        request_wids = [*self.dntp_wids, self.atp_wid]
        return {
            "chromosome": {
                "replication_state": {
                    "_default": "idle",
                    "_updater": "set",
                    "_emit": True,
                },
                "fork_position_bp": {
                    "left": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
                    "right": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
                },
                "events": {
                    "replication_complete": {
                        "_default": 0.0,
                        "_updater": "accumulate",
                        "_emit": True,
                    }
                },
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.substrate_wids
            },
            "requests": {
                self.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False} for wid in request_wids
                }
            },
            "substrates_allocated": {
                self.name: {
                    wid: {"_default": 0.0, "_emit": False}
                    for wid in request_wids
                }
            },
        }

    def _zero_requests(self) -> dict[str, float]:
        return {wid: 0.0 for wid in [*self.dntp_wids, self.atp_wid]}

    def _allocated_or_state(
        self,
        allocated_state: dict[str, Any],
        substrate_state: dict[str, Any],
        wid: str,
    ) -> int:
        allocated = float(allocated_state.get(wid, 0.0))
        if allocated > 0.0:
            return _read_nonnegative_int(allocated)
        return _read_nonnegative_int(substrate_state.get(wid, 0.0))

    def _partition_counts(self, total: int) -> np.ndarray:
        if total <= 0:
            return np.zeros(4, dtype=np.int64)
        raw = self._dntp_fractions * float(total)
        base = np.floor(raw).astype(np.int64)
        remainder = int(total - int(np.sum(base)))
        if remainder > 0:
            order = np.argsort(-(raw - base))
            for idx in order[:remainder]:
                base[int(idx)] += 1
        return base

    def _demand_from_advances(self, advance_left_bp: int, advance_right_bp: int) -> dict[str, int]:
        total_advanced_bp = max(0, int(advance_left_bp)) + max(0, int(advance_right_bp))
        total_polymerized_nt = 2 * total_advanced_bp
        dntp_counts = self._partition_counts(total_polymerized_nt)

        demand = {wid: int(dntp_counts[idx]) for idx, wid in enumerate(self.dntp_wids)}
        demand[self.atp_wid] = int(np.ceil(self.helicase_atp_per_bp * float(total_advanced_bp)))
        return demand

    def _completion_update(self) -> dict[str, Any]:
        chrom_update: dict[str, Any] = {"replication_state": "complete"}
        if not self._completion_emitted:
            chrom_update["events"] = {"replication_complete": 1.0}
            self._completion_emitted = True
        return {"chromosome": chrom_update}

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])
        chromosome_state = states.get("chromosome", {})
        replication_state = str(chromosome_state.get("replication_state", "idle"))
        fork_state = chromosome_state.get("fork_position_bp", {})
        left_pos_bp = _read_nonnegative_int(fork_state.get("left", 0.0))
        right_pos_bp = _read_nonnegative_int(fork_state.get("right", 0.0))

        # Reset one-shot completion emitter if an upstream coordinator restarts the cycle.
        if replication_state in {"idle", "initiating", "elongating"}:
            self._completion_emitted = False

        zero_requests = self._zero_requests()
        update: dict[str, Any] = {"requests": {self.name: zero_requests}}

        if replication_state == "idle":
            return update

        if replication_state == "initiating":
            update["chromosome"] = {"replication_state": "elongating"}
            return update

        if replication_state == "complete":
            return update

        if replication_state != "elongating":
            # Unknown state: keep requests at zero and do nothing.
            return update

        remaining_left_bp = max(0, self.terc_position_bp - left_pos_bp)
        remaining_right_bp = max(0, self.terc_position_bp - right_pos_bp)
        if remaining_left_bp <= 0 and remaining_right_bp <= 0:
            update.update(self._completion_update())
            return update

        desired_step_bp = max(0, int(np.floor(self.fork_polymerization_rate_bp_per_s * dt)))
        desired_left_bp = min(desired_step_bp, remaining_left_bp)
        desired_right_bp = min(desired_step_bp, remaining_right_bp)

        desired_demand = self._demand_from_advances(desired_left_bp, desired_right_bp)
        update["requests"] = {
            self.name: {wid: float(desired_demand.get(wid, 0)) for wid in zero_requests}
        }

        if desired_left_bp <= 0 and desired_right_bp <= 0:
            if remaining_left_bp <= 0 and remaining_right_bp <= 0:
                update.update(self._completion_update())
            return update

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        substrate_state = states.get("substrates", {})
        available = {
            wid: self._allocated_or_state(allocated_state, substrate_state, wid)
            for wid in zero_requests
        }

        limiting_ratios: list[float] = []
        for wid, req in desired_demand.items():
            if req > 0:
                limiting_ratios.append(float(available.get(wid, 0)) / float(req))
        scale = float(np.clip(min(limiting_ratios) if limiting_ratios else 1.0, a_min=0.0, a_max=1.0))

        actual_left_bp = int(np.floor(desired_left_bp * scale))
        actual_right_bp = int(np.floor(desired_right_bp * scale))

        while actual_left_bp > 0 or actual_right_bp > 0:
            demand = self._demand_from_advances(actual_left_bp, actual_right_bp)
            if all(demand[wid] <= available.get(wid, 0) for wid in demand):
                break
            if actual_left_bp >= actual_right_bp and actual_left_bp > 0:
                actual_left_bp -= 1
            elif actual_right_bp > 0:
                actual_right_bp -= 1

        if actual_left_bp <= 0 and actual_right_bp <= 0:
            return update

        actual_demand = self._demand_from_advances(actual_left_bp, actual_right_bp)
        substrate_delta = {
            wid: -float(amount) for wid, amount in actual_demand.items() if int(amount) > 0
        }
        fork_delta = {
            "left": float(actual_left_bp),
            "right": float(actual_right_bp),
        }

        update["chromosome"] = {"fork_position_bp": fork_delta}
        if substrate_delta:
            update["substrates"] = substrate_delta

        next_left_bp = left_pos_bp + actual_left_bp
        next_right_bp = right_pos_bp + actual_right_bp
        if next_left_bp >= self.terc_position_bp and next_right_bp >= self.terc_position_bp:
            completion = self._completion_update()
            update.setdefault("chromosome", {})
            update["chromosome"].update(completion["chromosome"])
        return update


__all__ = ["KarrReplicationProcess"]
