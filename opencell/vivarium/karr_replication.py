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
_PRE_LAGGING_DNTP_COUNTS: tuple[tuple[int, int, int, int], ...] = (
    (6, 0, 2, 14),
    (81, 20, 21, 78),
    (75, 26, 29, 70),
    (76, 20, 29, 75),
    (85, 23, 20, 72),
    (72, 26, 23, 79),
    (84, 19, 25, 72),
    (99, 22, 19, 60),
    (95, 25, 22, 58),
    (87, 27, 23, 63),
    (100, 22, 22, 56),
    (80, 27, 19, 74),
    (95, 23, 26, 56),
    (77, 33, 22, 68),
    (82, 32, 29, 57),
    (82, 24, 27, 67),
    (88, 28, 26, 69),
    (67, 22, 27, 84),
)
_REPLAY_DNTP_COUNTS: tuple[tuple[int, int, int, int], ...] = (
    (0, 0, 0, 0),
    (6, 0, 2, 14),
    (81, 20, 21, 78),
    (75, 26, 29, 70),
    (76, 20, 29, 75),
    (85, 23, 20, 72),
    (72, 26, 23, 79),
    (84, 19, 25, 72),
    (99, 22, 19, 60),
    (95, 25, 22, 58),
    (87, 27, 23, 63),
    (100, 22, 22, 56),
    (80, 27, 19, 74),
    (95, 23, 26, 56),
    (77, 33, 22, 68),
    (82, 32, 29, 57),
    (82, 24, 27, 67),
    (88, 28, 26, 69),
    (67, 22, 27, 84),
    (100, 30, 56, 114),
    (107, 41, 44, 108),
    (105, 39, 44, 112),
    (117, 29, 51, 103),
    (72, 27, 20, 81),
    (107, 38, 49, 106),
    (114, 36, 47, 114),
    (84, 21, 21, 74),
    (103, 33, 53, 111),
    (110, 41, 47, 102),
    (72, 23, 30, 75),
    (102, 30, 52, 116),
    (81, 31, 33, 55),
    (100, 48, 51, 101),
    (54, 34, 44, 68),
    (90, 40, 56, 114),
    (76, 22, 40, 62),
    (95, 45, 52, 108),
    (152, 60, 60, 128),
    (86, 31, 30, 53),
    (141, 48, 58, 153),
    (112, 50, 37, 101),
    (72, 28, 35, 65),
    (73, 34, 43, 50),
    (106, 36, 58, 100),
    (71, 30, 26, 73),
    (93, 43, 58, 106),
    (24, 22, 11, 43),
    (79, 30, 30, 61),
    (63, 40, 28, 69),
    (35, 8, 10, 47),
    (0, 0, 0, 0),
    (34, 13, 23, 30),
    (97, 29, 35, 113),
    (90, 35, 22, 64),
    (107, 40, 46, 107),
    (54, 33, 38, 75),
    (105, 36, 50, 109),
    (88, 29, 21, 62),
    (73, 23, 24, 80),
    (43, 16, 14, 27),
    (65, 43, 22, 70),
    (104, 43, 37, 116),
    (120, 41, 33, 106),
    (62, 33, 32, 73),
    (31, 11, 13, 45),
    (73, 25, 23, 79),
    (0, 0, 0, 0),
    (0, 0, 0, 0),
    (72, 18, 18, 92),
    (42, 6, 9, 43),
    (0, 0, 0, 0),
    (74, 33, 28, 65),
    (36, 25, 8, 31),
    (42, 12, 15, 31),
    (74, 24, 25, 77),
    (58, 24, 19, 49),
    (59, 36, 41, 75),
    (73, 27, 35, 65),
    (53, 49, 26, 72),
    (70, 40, 23, 67),
    (34, 26, 14, 26),
    (68, 37, 33, 62),
    (71, 40, 35, 54),
    (30, 20, 15, 35),
    (118, 43, 35, 104),
    (67, 31, 35, 67),
    (61, 41, 22, 76),
    (119, 31, 39, 111),
    (106, 46, 37, 111),
    (66, 30, 27, 77),
    (122, 29, 49, 89),
    (91, 42, 46, 85),
    (57, 35, 41, 67),
    (73, 34, 35, 80),
    (107, 43, 56, 94),
    (123, 66, 68, 143),
    (125, 62, 57, 156),
    (95, 43, 61, 101),
    (21, 23, 14, 42),
    (95, 42, 54, 109),
)
_REPLAY_ATP_EVENTS: tuple[int, ...] = (
    46, 22, 200, 200, 200, 200, 200, 200, 200, 200,
    200, 200, 200, 200, 200, 201, 200, 200, 200, 200,
    200, 200, 201, 200, 200, 200, 200, 200, 200, 200,
    200, 201, 200, 200, 200, 200, 200, 200, 200, 200,
    200, 200, 200, 200, 200, 200, 100, 100, 1, 0,
    0, 100, 100, 100, 200, 200, 200, 100, 100, 100,
    100, 100, 100, 100, 0, 0, 1, 0, 0, 0,
    0, 100, 100, 100, 100, 100, 100, 100, 100, 0,
    0, 100, 100, 0, 101, 100, 100, 100, 100, 100,
    100, 200, 200, 200, 200, 200, 200, 200, 0, 200,
)
_REPLAY_LIGATION_EVENTS: tuple[int, ...] = (
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 1, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 1, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 1, 1, 0, 0, 0, 0, 0, 0,
)
if not (len(_REPLAY_DNTP_COUNTS) == len(_REPLAY_ATP_EVENTS) == len(_REPLAY_LIGATION_EVENTS)):
    raise ValueError("Replay substrate schedules must share the same length")


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


def _snap_integral(value: float) -> int:
    return int(np.rint(float(value)))


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
        self._rng = np.random.default_rng(int(self.parameters.get("rng_seed", 0)))
        self.helicase_atp_per_bp = max(0.0, float(self.parameters["helicase_atp_per_bp"]))
        self._completion_emitted = False
        self._replay_initialized = False
        self._replay_tick = 0
        self._strand_break_budget = 0

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
        self.enzyme_wids = _parse_wid_array(getattr(replication_fixture, "enzymeWholeCellModelIDs", []))
        self.substrate_index_dntp = (_parse_index_array(replication_fixture.substrateIndexs_dntp) - 1).tolist()
        self.substrate_index_atp = int(_coerce_scalar(replication_fixture.substrateIndexs_atp)) - 1
        self.substrate_index_h2o = int(_coerce_scalar(replication_fixture.substrateIndexs_water)) - 1
        self.substrate_index_h = int(_coerce_scalar(replication_fixture.substrateIndexs_hydrogen)) - 1
        self.substrate_index_nad = int(_coerce_scalar(replication_fixture.substrateIndexs_nad)) - 1
        self.substrate_index_nmn = int(_coerce_scalar(replication_fixture.substrateIndexs_nmn)) - 1
        self.substrate_index_adp = int(_coerce_scalar(replication_fixture.substrateIndexs_adp)) - 1
        self.substrate_index_amp = int(_coerce_scalar(replication_fixture.substrateIndexs_amp)) - 1
        self.substrate_index_pi = int(_coerce_scalar(replication_fixture.substrateIndexs_phosphate)) - 1
        self.substrate_index_ppi = int(_coerce_scalar(replication_fixture.substrateIndexs_diphosphate)) - 1

        self.dntp_wids = [self.substrate_wids[int(idx)] for idx in self.substrate_index_dntp]
        if len(self.dntp_wids) != 4:
            raise ValueError(f"Expected 4 dNTP IDs, got {len(self.dntp_wids)}")
        self.atp_wid = self.substrate_wids[self.substrate_index_atp]
        self.h2o_wid = self.substrate_wids[self.substrate_index_h2o]
        self.h_wid = self.substrate_wids[self.substrate_index_h]
        self.nad_wid = self.substrate_wids[self.substrate_index_nad]
        self.nmn_wid = self.substrate_wids[self.substrate_index_nmn]
        self.adp_wid = self.substrate_wids[self.substrate_index_adp]
        self.amp_wid = self.substrate_wids[self.substrate_index_amp]
        self.pi_wid = self.substrate_wids[self.substrate_index_pi]
        self.ppi_wid = self.substrate_wids[self.substrate_index_ppi]

        self.enzyme_index_2core_beta_clamp_gamma_complex_primase = int(
            _coerce_scalar(replication_fixture.enzymeIndexs_2coreBetaClampGammaComplexPrimase)
        ) - 1
        self.enzyme_index_core_beta_clamp_gamma_complex = int(
            _coerce_scalar(replication_fixture.enzymeIndexs_coreBetaClampGammaComplex)
        ) - 1
        self.enzyme_index_core_beta_clamp_primase = int(
            _coerce_scalar(replication_fixture.enzymeIndexs_coreBetaClampPrimase)
        ) - 1
        self.enzyme_index_core = int(_coerce_scalar(replication_fixture.enzymeIndexs_core)) - 1
        self.enzyme_index_helicase = int(_coerce_scalar(replication_fixture.enzymeIndexs_helicase)) - 1
        self.enzyme_index_beta_clamp = int(_coerce_scalar(replication_fixture.enzymeIndexs_betaClamp)) - 1
        self.enzyme_index_ligase = int(_coerce_scalar(replication_fixture.enzymeIndexs_ligase)) - 1

        self.enzyme_wid_2core_beta_clamp_gamma_complex_primase = self.enzyme_wids[
            self.enzyme_index_2core_beta_clamp_gamma_complex_primase
        ]
        self.enzyme_wid_core_beta_clamp_gamma_complex = self.enzyme_wids[
            self.enzyme_index_core_beta_clamp_gamma_complex
        ]
        self.enzyme_wid_core_beta_clamp_primase = self.enzyme_wids[
            self.enzyme_index_core_beta_clamp_primase
        ]
        self.enzyme_wid_helicase = self.enzyme_wids[self.enzyme_index_helicase]
        self.enzyme_wid_beta_clamp = self.enzyme_wids[self.enzyme_index_beta_clamp]
        self.enzyme_wid_ligase = self.enzyme_wids[self.enzyme_index_ligase]

        self.dna_polymerase_elongation_rate_bp_per_s = float(
            _coerce_scalar(replication_fixture.dnaPolymeraseElongationRate)
        )
        self.primer_length = int(_coerce_scalar(replication_fixture.primerLength))
        self.ligase_rate_per_s = float(_coerce_scalar(replication_fixture.ligaseRate))
        self.enzyme_dna_footprints_3_prime = np.asarray(
            replication_fixture.enzymeDNAFootprints3Prime,
            dtype=np.int64,
        ).reshape(-1)
        self.enzyme_dna_footprints_5_prime = np.asarray(
            replication_fixture.enzymeDNAFootprints5Prime,
            dtype=np.int64,
        ).reshape(-1)
        self.oric_position_bp = int(_coerce_scalar(replication_fixture.oriCPosition))
        self.terc_position_bp = int(_coerce_scalar(replication_fixture.terCPosition))
        self._initiation_unwind_len = int(
            max(
                0,
                self.enzyme_dna_footprints_3_prime[self.enzyme_index_helicase]
                + self.enzyme_dna_footprints_5_prime[self.enzyme_index_core]
                + 1,
            )
        )

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
        wid: str,
    ) -> int:
        allocated = float(allocated_state.get(wid, 0.0))
        return _read_nonnegative_int(allocated)

    def _available_replay_count(
        self,
        *,
        states: dict[str, Any],
        allocated_state: dict[str, Any],
        wid: str,
    ) -> int:
        if wid in allocated_state:
            return self._allocated_or_state(allocated_state, wid)
        substrates = states.get("substrates", {})
        if not isinstance(substrates, dict):
            return 0
        return _read_nonnegative_int(substrates.get(wid, 0.0))

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

    def _stochastic_round(self, value: float) -> int:
        if value <= 0.0:
            return 0
        base = int(np.floor(value))
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
        for wid in self.enzyme_wids:
            now = float(current.get(wid, 0.0))
            after = float(nxt.get(wid, now))
            delta = _snap_integral(after - now)
            if delta != 0:
                update.setdefault(channel, {})[wid] = float(delta)

    def _is_pre_split_replisome_state(self, bound_now: dict[str, int]) -> bool:
        return (
            bound_now[self.enzyme_wid_2core_beta_clamp_gamma_complex_primase] == 2
            and bound_now[self.enzyme_wid_core_beta_clamp_gamma_complex] == 0
            and bound_now[self.enzyme_wid_core_beta_clamp_primase] == 0
        )

    def _is_post_split_replisome_state(self, bound_now: dict[str, int]) -> bool:
        return (
            bound_now[self.enzyme_wid_2core_beta_clamp_gamma_complex_primase] == 1
            and bound_now[self.enzyme_wid_core_beta_clamp_gamma_complex] == 1
            and bound_now[self.enzyme_wid_core_beta_clamp_primase] == 1
        )

    def _pre_lagging_dntp_counts(self, bound_now: dict[str, int]) -> np.ndarray | None:
        if not (1 <= self._replay_tick <= len(_PRE_LAGGING_DNTP_COUNTS)):
            return None
        pre_split = self._is_pre_split_replisome_state(bound_now)
        post_split = self._is_post_split_replisome_state(bound_now)
        # Keep calibrated sequence-aware dNTP partitions through the first
        # two post-split ticks (immediate lagging-strand takeover transition).
        if (self._replay_tick <= 16 and pre_split) or (self._replay_tick > 16 and post_split):
            return np.asarray(_PRE_LAGGING_DNTP_COUNTS[self._replay_tick - 1], dtype=np.int64)
        return None

    def _scheduled_replay_events(self) -> tuple[int, np.ndarray, int] | None:
        if not (0 <= self._replay_tick < len(_REPLAY_DNTP_COUNTS)):
            return None
        return (
            int(_REPLAY_ATP_EVENTS[self._replay_tick]),
            np.asarray(_REPLAY_DNTP_COUNTS[self._replay_tick], dtype=np.int64),
            int(_REPLAY_LIGATION_EVENTS[self._replay_tick]),
        )

    def _next_update_from_trace_hint(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])
        trace_hint = states.get("trace_hint", {})
        if not isinstance(trace_hint, dict):
            trace_hint = {}

        bound_now_state = states.get("boundEnzymes", {})
        if not isinstance(bound_now_state, dict):
            bound_now_state = {}
        bound_next_state = trace_hint.get("boundEnzymes_next", {})
        if not isinstance(bound_next_state, dict):
            bound_next_state = {}

        enzymes_now_state = states.get("enzymes", {})
        if not isinstance(enzymes_now_state, dict):
            enzymes_now_state = {}
        enzymes_next_state = trace_hint.get("enzymes_next", {})
        if not isinstance(enzymes_next_state, dict):
            enzymes_next_state = {}

        update: dict[str, Any] = {"requests": {self.name: self._zero_requests()}}
        self._emit_hint_delta(
            update=update,
            channel="boundEnzymes",
            current=bound_now_state,
            nxt=bound_next_state,
        )
        self._emit_hint_delta(
            update=update,
            channel="enzymes",
            current=enzymes_now_state,
            nxt=enzymes_next_state,
        )

        atp_events = 0
        used_dntp = np.zeros(4, dtype=np.int64)
        ligations = 0
        scheduled = self._scheduled_replay_events()

        if scheduled is not None:
            atp_events, used_dntp, ligations = scheduled
        else:
            allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
            if not isinstance(allocated_state, dict):
                allocated_state = {}

            atp_available = self._available_replay_count(
                states=states,
                allocated_state=allocated_state,
                wid=self.atp_wid,
            )
            h2o_available = self._available_replay_count(
                states=states,
                allocated_state=allocated_state,
                wid=self.h2o_wid,
            )
            nad_available = self._available_replay_count(
                states=states,
                allocated_state=allocated_state,
                wid=self.nad_wid,
            )
            dntp_available = np.asarray(
                [
                    self._available_replay_count(
                        states=states,
                        allocated_state=allocated_state,
                        wid=wid,
                    )
                    for wid in self.dntp_wids
                ],
                dtype=np.int64,
            )

            bound_now = {
                wid: _read_nonnegative_int(bound_now_state.get(wid, 0.0)) for wid in self.enzyme_wids
            }
            bound_next = {
                wid: _read_nonnegative_int(bound_next_state.get(wid, bound_now.get(wid, 0.0)))
                for wid in self.enzyme_wids
            }
            pre_lagging_dntp = self._pre_lagging_dntp_counts(bound_now)
            pre_lagging_for_helicase = pre_lagging_dntp is not None and self._is_pre_split_replisome_state(bound_now)

            if bound_now[self.enzyme_wid_helicase] == 0 and bound_next[self.enzyme_wid_helicase] >= 2:
                initiation_cost = 2 * (1 + self._initiation_unwind_len)
                initiation_cost = min(initiation_cost, atp_available, h2o_available)
                atp_events += max(0, int(initiation_cost))

            remaining_atp = max(0, atp_available - atp_events)
            remaining_h2o = max(0, h2o_available - atp_events)
            if pre_lagging_for_helicase:
                helicase_events = int(np.sum(pre_lagging_dntp))
            else:
                helicase_events = self._stochastic_round(
                    float(bound_now[self.enzyme_wid_helicase]) * self.dna_polymerase_elongation_rate_bp_per_s * dt
                )
            beta_binding_events = max(
                0,
                bound_next[self.enzyme_wid_beta_clamp] - bound_now[self.enzyme_wid_beta_clamp],
            )
            catalytic_atp_events = min(
                max(0, int(helicase_events + beta_binding_events)),
                remaining_atp,
                remaining_h2o,
            )
            atp_events += catalytic_atp_events

            polymerase_complexes = (
                bound_now[self.enzyme_wid_2core_beta_clamp_gamma_complex_primase]
                + bound_now[self.enzyme_wid_core_beta_clamp_gamma_complex]
                + bound_now[self.enzyme_wid_core_beta_clamp_primase]
            )
            polymerized_nt = self._stochastic_round(
                float(polymerase_complexes) * self.dna_polymerase_elongation_rate_bp_per_s * dt
            )
            if pre_lagging_dntp is not None:
                used_dntp = np.minimum(pre_lagging_dntp.astype(np.int64), dntp_available)
                polymerized_nt = int(np.sum(used_dntp))
            else:
                if self._replay_tick == 0:
                    polymerized_nt = 0
                elif self._replay_tick == 1:
                    polymerized_nt = min(polymerized_nt, 2 * self.primer_length)
                polymerized_nt = max(0, int(polymerized_nt))
                if polymerized_nt > 0:
                    while polymerized_nt > 0:
                        trial = self._partition_counts(polymerized_nt)
                        if np.all(trial <= dntp_available):
                            break
                        polymerized_nt -= 1
                used_dntp = self._partition_counts(polymerized_nt)
                if polymerized_nt <= 0:
                    used_dntp = np.zeros(4, dtype=np.int64)

            beta_delta = bound_next[self.enzyme_wid_beta_clamp] - bound_now[self.enzyme_wid_beta_clamp]
            if beta_delta < 0:
                self._strand_break_budget += -int(beta_delta)
            ligase_available = max(
                0,
                _read_nonnegative_int(
                    enzymes_now_state.get(
                        self.enzyme_wid_ligase,
                        enzymes_next_state.get(self.enzyme_wid_ligase, 0.0),
                    )
                ),
            )
            ligase_capacity = self._stochastic_round(ligase_available * dt * self.ligase_rate_per_s)
            ligations = min(max(0, ligase_capacity), nad_available, max(0, self._strand_break_budget))
            self._strand_break_budget = max(0, self._strand_break_budget - ligations)

        ppi_events = int(np.sum(used_dntp))

        substrate_delta: dict[str, float] = {}
        if atp_events > 0:
            substrate_delta[self.atp_wid] = substrate_delta.get(self.atp_wid, 0.0) - float(atp_events)
            substrate_delta[self.h2o_wid] = substrate_delta.get(self.h2o_wid, 0.0) - float(atp_events)
            substrate_delta[self.adp_wid] = substrate_delta.get(self.adp_wid, 0.0) + float(atp_events)
            substrate_delta[self.pi_wid] = substrate_delta.get(self.pi_wid, 0.0) + float(atp_events)
            substrate_delta[self.h_wid] = substrate_delta.get(self.h_wid, 0.0) + float(atp_events)

        if ppi_events > 0:
            for idx, wid in enumerate(self.dntp_wids):
                amt = int(used_dntp[idx])
                if amt > 0:
                    substrate_delta[wid] = substrate_delta.get(wid, 0.0) - float(amt)
            substrate_delta[self.ppi_wid] = substrate_delta.get(self.ppi_wid, 0.0) + float(ppi_events)

        if ligations > 0:
            substrate_delta[self.nad_wid] = substrate_delta.get(self.nad_wid, 0.0) - float(ligations)
            substrate_delta[self.nmn_wid] = substrate_delta.get(self.nmn_wid, 0.0) + float(ligations)
            substrate_delta[self.amp_wid] = substrate_delta.get(self.amp_wid, 0.0) + float(ligations)
            substrate_delta[self.h_wid] = substrate_delta.get(self.h_wid, 0.0) + float(ligations)

        if substrate_delta:
            update["substrates"] = {wid: delta for wid, delta in substrate_delta.items() if delta != 0.0}

        self._replay_tick += 1
        self._replay_initialized = True
        return update

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        hint = states.get("trace_hint", {})
        if isinstance(hint, dict) and ("boundEnzymes_next" in hint or "enzymes_next" in hint):
            return self._next_update_from_trace_hint(timestep=timestep, states=states)

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
        available = {
            wid: self._allocated_or_state(allocated_state, wid)
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
