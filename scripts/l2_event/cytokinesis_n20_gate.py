"""Real Cytokinesis L2.2 N=20 gate over genuine dual-division traces.

Projection-v2 dual traces remain usable as explicitly conditional pilots:
they compare the source-faithful diameter transition under Karr's observed
ring schedule and can never write authority. Projection-v3 traces add the
Cytokinesis process's private ``randStreamState`` before and after every real
``evolveState`` call. Those traces support a continuous, restored-RNG replay
of the full OpenCell ``next_update`` and exact comparison of every meaningful
non-redundant process output. No missing state is synthesized in either mode.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import wasserstein_distance

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from opencell.util.mcg16807_state_codec import parse_captured_state
from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess
from scripts.l2_event.adapters.cytokinesis import (
    DuplicateCompletionTickDetectedError,
    find_completion_tick,
    find_onset_tick,
)
from scripts.l2_event.division_gate_common import (
    DivisionGateContext,
    DivisionGateRefusalError,
    portable_oracle_path,
    repo_relative_or_absolute,
    resolve_gate_context,
    sha256_file,
    write_authority_bundle,
    write_pilot_report,
)
from scripts.l2_event.division_window_spec import CYTOKINESIS_M_TICKS
from scripts.l2_event.validate_dual_division_canary import (
    CYTOKINESIS_RNG_STATE_OBSERVABLE,
    FTSZ_N_TICKS,
    cytokinesis_full_replay_capability,
)
from scripts.l2_event.window_loader import WindowGrid, load_event_window
from scripts.l22_evidence import catalog as l22_catalog

PROCESS_NAME = "Cytokinesis"
HARNESS_TYPE = "event_class"
CONDITIONAL_ADAPTER_ID = "cytokinesis.contraction_projection.v2"
FULL_REPLAY_ADAPTER_ID = "cytokinesis.full_next_update_replay.v3"
ADAPTER_ID = FULL_REPLAY_ADAPTER_ID
DEFAULT_SUT_PROJECTOR = KarrCytokinesisProcess.calc_next_pinched_diameter
BASE_REQUIRED_OBSERVABLES = (
    "substrates",
    "enzymes",
    "boundEnzymes",
    "pinchedDiameter",
    "ftsZRing_numEdgesOneStraight",
    "ftsZRing_numEdgesTwoStraight",
    "ftsZRing_numEdgesTwoBent",
    "ftsZRing_numResidualBent",
    "chromosome_segregated",
)
FULL_REPLAY_REQUIRED_OBSERVABLES = (
    *BASE_REQUIRED_OBSERVABLES,
    CYTOKINESIS_RNG_STATE_OBSERVABLE,
)
# Backward-compatible name used by existing imports/tests: this is the
# conditional-pilot minimum, not the full-replay authority surface.
REQUIRED_OBSERVABLES = BASE_REQUIRED_OBSERVABLES
FULL_REPLAY_NONREDUNDANT_FIELDS = (
    "substrates",
    "enzymes",
    "boundEnzymes",
    "pinchedDiameter",
    "ftsZRing_numEdgesOneStraight",
    "ftsZRing_numEdgesTwoStraight",
    "ftsZRing_numEdgesTwoBent",
    "ftsZRing_numResidualBent",
    "randStreamState",
)
FULL_REPLAY_AUDIT_FIELDS = (
    *FULL_REPLAY_NONREDUNDANT_FIELDS,
    "waterRequest",
    "derivedOutputs",
    "outputContract",
)


def _default_sut_runner(
    process: KarrCytokinesisProcess,
    states: dict[str, Any],
) -> dict[str, Any]:
    return process.next_update(1.0, states)


DEFAULT_SUT_RUNNER = _default_sut_runner


class CytokinesisGateError(RuntimeError):
    """Raised for a malformed/non-source-faithful Cytokinesis gate input."""


def _scalar(value: np.ndarray, *, label: str) -> float:
    arr = np.asarray(value, dtype=np.float64)
    if arr.size != 1:
        raise CytokinesisGateError(f"{label} is not scalar: shape={arr.shape}")
    number = float(arr.reshape(-1)[0])
    if not math.isfinite(number):
        raise CytokinesisGateError(f"{label} is non-finite: {number!r}")
    return number


def _vector(grid: WindowGrid, observable: str, tick: int, *, after: bool) -> np.ndarray:
    raw = grid.after(observable, tick) if after else grid.before(observable, tick)
    arr = np.asarray(raw, dtype=np.float64).reshape(-1)
    if not np.all(np.isfinite(arr)):
        side = "after" if after else "before"
        raise CytokinesisGateError(
            f"{grid.trace_path}: {observable} {side}[{tick}] contains non-finite values"
        )
    return arr


def _integer_nonnegative(value: float, *, label: str) -> int:
    rounded = int(np.rint(value))
    if value < 0 or abs(value - rounded) > 1.0e-9:
        raise CytokinesisGateError(f"{label} must be a nonnegative integer, got {value!r}")
    return rounded


@dataclass(frozen=True)
class CytokinesisSeedEvidence:
    seed: int
    trace_path: Path
    trace_sha256: str
    onset_offset: int
    completion_offset: int
    onset_to_completion_ticks: int
    contraction_cycle_count: int
    source_projection_mismatch_ticks: tuple[int, ...]
    water_consumed: float
    phosphate_produced: float
    hydrogen_produced: float
    hydrolysis_stoichiometry_ok: bool
    polymer_payload_redundant: bool
    hydrolysis_tick_count: int

    def to_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "trace_path": str(self.trace_path),
            "trace_sha256": self.trace_sha256,
            "onset_offset": self.onset_offset,
            "completion_offset": self.completion_offset,
            "onset_to_completion_ticks": self.onset_to_completion_ticks,
            "contraction_cycle_count": self.contraction_cycle_count,
            "source_projection_mismatch_ticks": list(self.source_projection_mismatch_ticks),
            "water_consumed": self.water_consumed,
            "phosphate_produced": self.phosphate_produced,
            "hydrogen_produced": self.hydrogen_produced,
            "hydrolysis_stoichiometry_ok": self.hydrolysis_stoichiometry_ok,
            "polymer_payload_redundant": self.polymer_payload_redundant,
            "hydrolysis_tick_count": self.hydrolysis_tick_count,
        }


@dataclass(frozen=True)
class CytokinesisProjectionSurface:
    evidence: CytokinesisSeedEvidence
    karr_event_ticks: tuple[int, ...]
    oc_event_ticks: tuple[int, ...]
    karr_payloads: tuple[float, ...]
    oc_payloads: tuple[float, ...]
    replay_authority_class: str
    replay_capability_reason: str
    full_replay_checked_ticks: int
    full_replay_field_mismatch_counts: dict[str, int]
    full_replay_first_mismatches: tuple[dict[str, Any], ...]

    @property
    def full_replay_passed(self) -> bool:
        return (
            self.replay_authority_class == "FULL_NEXT_UPDATE_REPLAY_READY"
            and not any(self.full_replay_field_mismatch_counts.values())
        )


def analyze_seed(seed: int, grid: WindowGrid) -> CytokinesisSeedEvidence:
    if grid.process_name != PROCESS_NAME or grid.seed != seed:
        raise CytokinesisGateError(
            f"seed/process identity mismatch: requested seed={seed}, "
            f"metadata seed={grid.seed}, process={grid.process_name!r}"
        )
    if grid.n_ticks != CYTOKINESIS_M_TICKS:
        raise CytokinesisGateError(
            f"seed {seed}: n_ticks={grid.n_ticks}, expected {CYTOKINESIS_M_TICKS}"
        )

    before_diameter = [
        _scalar(grid.before("pinchedDiameter", tick), label=f"before diameter seed={seed} tick={tick}")
        for tick in range(grid.n_ticks)
    ]
    after_diameter = [
        _scalar(grid.after("pinchedDiameter", tick), label=f"after diameter seed={seed} tick={tick}")
        for tick in range(grid.n_ticks)
    ]
    onset = find_onset_tick(before_diameter, after_diameter)
    completion = find_completion_tick(before_diameter, after_diameter)
    if onset is None or completion is None:
        raise CytokinesisGateError(
            f"seed {seed}: complete Cytokinesis window must contain one onset and one completion"
        )
    if onset > completion:
        raise CytokinesisGateError(
            f"seed {seed}: onset tick {onset} occurs after completion {completion}"
        )

    process = KarrCytokinesisProcess({"rng_seed": seed})
    projection_mismatches: list[int] = []
    cycle_count = 0
    water_consumed = 0.0
    phosphate_produced = 0.0
    hydrogen_produced = 0.0
    polymer_redundant = True
    hydrolysis_ok = True
    hydrolysis_tick_count = 0

    for tick, (before, after) in enumerate(
        zip(before_diameter, after_diameter, strict=True)
    ):
        for field in (
            "ftsZRing_numEdgesOneStraight",
            "ftsZRing_numEdgesTwoStraight",
            "ftsZRing_numEdgesTwoBent",
            "ftsZRing_numResidualBent",
            "chromosome_segregated",
        ):
            _integer_nonnegative(
                _scalar(grid.before(field, tick), label=f"{field} before seed={seed} tick={tick}"),
                label=f"{field} before seed={seed} tick={tick}",
            )
            _integer_nonnegative(
                _scalar(grid.after(field, tick), label=f"{field} after seed={seed} tick={tick}"),
                label=f"{field} after seed={seed} tick={tick}",
            )

        substrate_delta = _vector(grid, "substrates", tick, after=True) - _vector(
            grid, "substrates", tick, after=False
        )
        enzyme_delta = _vector(grid, "enzymes", tick, after=True) - _vector(
            grid, "enzymes", tick, after=False
        )
        bound_delta = _vector(grid, "boundEnzymes", tick, after=True) - _vector(
            grid, "boundEnzymes", tick, after=False
        )
        if substrate_delta.size != len(process.fixture_substrate_wids):
            raise CytokinesisGateError(
                f"seed {seed} tick {tick}: substrate width {substrate_delta.size} "
                f"!= fixture width {len(process.fixture_substrate_wids)}"
            )
        if enzyme_delta.size != len(process.fixture_enzyme_wids) or bound_delta.size != len(
            process.fixture_enzyme_wids
        ):
            raise CytokinesisGateError(
                f"seed {seed} tick {tick}: enzyme/bound width does not match fixture"
            )

        if after < before:
            cycle_count += 1
            expected = process.calc_next_pinched_diameter(
                pinched_diameter=before,
                filament_length_nm=process.default_filament_length_nm,
            )
            if not math.isclose(after, expected, rel_tol=1.0e-12, abs_tol=1.0e-18):
                projection_mismatches.append(tick)

        water_delta = substrate_delta[process.substrate_index_water]
        pi_delta = substrate_delta[process.substrate_index_pi]
        h_delta = substrate_delta[process.substrate_index_hydrogen]
        water_consumed += max(0.0, -float(water_delta))
        phosphate_produced += max(0.0, float(pi_delta))
        hydrogen_produced += max(0.0, float(h_delta))
        if not (
            math.isclose(float(pi_delta), float(h_delta), abs_tol=1.0e-9)
            and math.isclose(float(pi_delta), -float(water_delta), abs_tol=1.0e-9)
        ):
            hydrolysis_ok = False

        hydrolysis_extent = float(pi_delta)
        if hydrolysis_extent > 0.0:
            hydrolysis_tick_count += 1
        if hydrolysis_extent > 0.0:
            # The source couples a two-polymer GTP->GDP bound-pool swap to
            # each hydrolysis event. Other phases may bind/unbind in the
            # same tick, so the net bound-pool delta is not an independent
            # payload observable even though its hydrolysis component is
            # algebraically fixed by substrate extent.
            polymer_redundant = polymer_redundant and math.isclose(
                hydrolysis_extent % process.num_ftsz_subunits_per_filament,
                0.0,
                abs_tol=1.0e-9,
            )

        for delta in np.concatenate((substrate_delta, enzyme_delta, bound_delta)):
            if abs(delta - np.rint(delta)) > 1.0e-9:
                raise CytokinesisGateError(
                    f"seed {seed} tick {tick}: captured count delta is non-integral ({delta})"
                )

    return CytokinesisSeedEvidence(
        seed=seed,
        trace_path=grid.trace_path,
        trace_sha256=sha256_file(grid.trace_path),
        onset_offset=int(onset),
        completion_offset=int(completion),
        onset_to_completion_ticks=int(completion - onset),
        contraction_cycle_count=cycle_count,
        source_projection_mismatch_ticks=tuple(projection_mismatches),
        water_consumed=water_consumed,
        phosphate_produced=phosphate_produced,
        hydrogen_produced=hydrogen_produced,
        hydrolysis_stoichiometry_ok=hydrolysis_ok,
        polymer_payload_redundant=polymer_redundant,
        hydrolysis_tick_count=hydrolysis_tick_count,
    )


def _analytical_timing_threshold(karr_offsets: np.ndarray) -> tuple[float, float]:
    if len(karr_offsets) < 2:
        raise DivisionGateRefusalError("Cytokinesis timing calibration needs at least two Karr seeds")
    pairwise = np.abs(karr_offsets[:, None] - karr_offsets[None, :])
    q95 = float(np.quantile(pairwise[np.triu_indices(len(karr_offsets), k=1)], 0.95))
    return q95, max(1.0, q95)


def _integer_vector(
    grid: WindowGrid,
    observable: str,
    tick: int,
    *,
    after: bool,
) -> np.ndarray:
    vector = _vector(grid, observable, tick, after=after)
    rounded = np.rint(vector)
    if np.any(vector < 0.0) or not np.allclose(vector, rounded, atol=1.0e-9, rtol=0.0):
        side = "after" if after else "before"
        raise CytokinesisGateError(
            f"{grid.trace_path}: {observable} {side}[{tick}] must contain "
            f"nonnegative integer counts, got {vector.tolist()}"
        )
    return rounded.astype(np.int64)


def _mapping(wids: list[str], values: np.ndarray) -> dict[str, float]:
    return {wid: float(values[idx]) for idx, wid in enumerate(wids)}


def _derived_progress(process: KarrCytokinesisProcess, diameter: float) -> float:
    if process.initial_pinched_diameter <= 0.0:
        return 1.0 if diameter <= 0.0 else 0.0
    return float(min(1.0, max(0.0, 1.0 - diameter / process.initial_pinched_diameter)))


def _full_replay_state(
    *,
    process: KarrCytokinesisProcess,
    grid: WindowGrid,
    tick: int,
) -> tuple[dict[str, Any], dict[str, np.ndarray | float | int]]:
    substrates = _integer_vector(grid, "substrates", tick, after=False)
    enzymes = _integer_vector(grid, "enzymes", tick, after=False)
    bound = _integer_vector(grid, "boundEnzymes", tick, after=False)
    if substrates.size != len(process.fixture_substrate_wids):
        raise CytokinesisGateError(
            f"seed {grid.seed} tick {tick}: substrate width {substrates.size} "
            f"!= fixture width {len(process.fixture_substrate_wids)}"
        )
    if enzymes.size != len(process.fixture_enzyme_wids) or bound.size != len(
        process.fixture_enzyme_wids
    ):
        raise CytokinesisGateError(
            f"seed {grid.seed} tick {tick}: enzyme/bound width does not match fixture"
        )

    diameter = _scalar(
        grid.before("pinchedDiameter", tick),
        label=f"seed {grid.seed} tick {tick} before diameter",
    )
    ring_values: dict[str, int] = {}
    for observable in (
        "ftsZRing_numEdgesOneStraight",
        "ftsZRing_numEdgesTwoStraight",
        "ftsZRing_numEdgesTwoBent",
        "ftsZRing_numResidualBent",
    ):
        ring_values[observable] = _integer_nonnegative(
            _scalar(
                grid.before(observable, tick),
                label=f"seed {grid.seed} tick {tick} before {observable}",
            ),
            label=f"seed {grid.seed} tick {tick} before {observable}",
        )
    segregated = bool(
        _integer_nonnegative(
            _scalar(
                grid.before("chromosome_segregated", tick),
                label=f"seed {grid.seed} tick {tick} before chromosome_segregated",
            ),
            label=f"seed {grid.seed} tick {tick} before chromosome_segregated",
        )
    )

    states = {
        "cell": {
            "division_progress": _derived_progress(process, diameter),
            "division_complete": diameter <= 0.0,
        },
        "chromosome": {"segregated": segregated},
        "geometry": {
            "pinchedDiameter": diameter,
            "pinched": diameter <= 0.0,
        },
        "ftsZRing": {
            "numEdgesOneStraight": ring_values["ftsZRing_numEdgesOneStraight"],
            "numEdgesTwoStraight": ring_values["ftsZRing_numEdgesTwoStraight"],
            "numEdgesTwoBent": ring_values["ftsZRing_numEdgesTwoBent"],
            "numResidualBent": ring_values["ftsZRing_numResidualBent"],
        },
        "substrates": _mapping(process.fixture_substrate_wids, substrates),
        "enzymes": _mapping(process.fixture_enzyme_wids, enzymes),
        "boundEnzymes": _mapping(process.fixture_enzyme_wids, bound),
        "substrates_allocated": {
            process.name: {
                process.gtp_wid: 0.0,
                process.water_wid: float(substrates[process.substrate_index_water]),
            }
        },
    }
    return states, {
        "substrates": substrates,
        "enzymes": enzymes,
        "boundEnzymes": bound,
        "pinchedDiameter": diameter,
        **ring_values,
    }


def _conditional_projection_surface(
    *,
    row: CytokinesisSeedEvidence,
    grid: WindowGrid,
    process: KarrCytokinesisProcess,
    capability_reason: str,
    sut_projector: Callable[[float, float], float],
) -> CytokinesisProjectionSurface:
    karr_event_ticks: list[int] = []
    oc_event_ticks: list[int] = []
    karr_payloads: list[float] = []
    oc_payloads: list[float] = []

    for tick in range(grid.n_ticks):
        before = _scalar(
            grid.before("pinchedDiameter", tick),
            label=f"seed {grid.seed} tick {tick} before diameter",
        )
        after = _scalar(
            grid.after("pinchedDiameter", tick),
            label=f"seed {grid.seed} tick {tick} after diameter",
        )
        if after >= before:
            continue
        projected = float(sut_projector(before, process.default_filament_length_nm))
        karr_event_ticks.append(tick)
        karr_payloads.append(after)
        if projected < before:
            oc_event_ticks.append(tick)
            oc_payloads.append(projected)

    return CytokinesisProjectionSurface(
        evidence=row,
        karr_event_ticks=tuple(karr_event_ticks),
        oc_event_ticks=tuple(oc_event_ticks),
        karr_payloads=tuple(karr_payloads),
        oc_payloads=tuple(oc_payloads),
        replay_authority_class="CONDITIONAL_PILOT_ONLY",
        replay_capability_reason=capability_reason,
        full_replay_checked_ticks=0,
        full_replay_field_mismatch_counts={field: 0 for field in FULL_REPLAY_AUDIT_FIELDS},
        full_replay_first_mismatches=(),
    )


def _full_replay_surface(
    *,
    row: CytokinesisSeedEvidence,
    grid: WindowGrid,
    process: KarrCytokinesisProcess,
    sut_runner: Callable[
        [KarrCytokinesisProcess, dict[str, Any]],
        dict[str, Any],
    ],
) -> CytokinesisProjectionSurface:
    mismatch_counts = {field: 0 for field in FULL_REPLAY_AUDIT_FIELDS}
    first_mismatches: list[dict[str, Any]] = []
    karr_event_ticks: list[int] = []
    oc_event_ticks: list[int] = []
    karr_payloads: list[float] = []
    oc_payloads: list[float] = []

    def record_mismatch(
        *,
        tick: int,
        field: str,
        oc_value: Any,
        karr_value: Any,
        detail: str = "",
    ) -> None:
        mismatch_counts[field] += 1
        if len(first_mismatches) < 32:
            def jsonify(value: Any) -> Any:
                if isinstance(value, np.ndarray):
                    return value.tolist()
                if isinstance(value, np.generic):
                    return value.item()
                return value

            first_mismatches.append(
                {
                    "tick": tick,
                    "field": field,
                    "oc": jsonify(oc_value),
                    "karr": jsonify(karr_value),
                    "detail": detail,
                }
            )

    try:
        initial_rng_state = parse_captured_state(
            grid.before(CYTOKINESIS_RNG_STATE_OBSERVABLE, 0)
        )
    except ValueError as exc:
        raise CytokinesisGateError(
            f"{grid.trace_path}: invalid initial randStreamState: {exc}"
        ) from exc
    process._rng.set_state(initial_rng_state)  # noqa: SLF001
    previous_karr_exit: int | None = None

    for tick in range(grid.n_ticks):
        states, before_values = _full_replay_state(
            process=process,
            grid=grid,
            tick=tick,
        )
        try:
            karr_rng_before = parse_captured_state(
                grid.before(CYTOKINESIS_RNG_STATE_OBSERVABLE, tick)
            )
            karr_rng_after = parse_captured_state(
                grid.after(CYTOKINESIS_RNG_STATE_OBSERVABLE, tick)
            )
        except ValueError as exc:
            raise CytokinesisGateError(
                f"{grid.trace_path}: invalid randStreamState at tick {tick}: {exc}"
            ) from exc
        if previous_karr_exit is not None and previous_karr_exit != karr_rng_before:
            raise CytokinesisGateError(
                f"{grid.trace_path}: private process RNG discontinuity before tick {tick}: "
                f"previous after={previous_karr_exit}, current before={karr_rng_before}"
            )
        oc_rng_before = process._rng.get_state()  # noqa: SLF001
        if oc_rng_before != karr_rng_before:
            record_mismatch(
                tick=tick,
                field="randStreamState",
                oc_value=oc_rng_before,
                karr_value=karr_rng_before,
                detail="entry state",
            )

        update = sut_runner(process, states)
        if not isinstance(update, dict):
            record_mismatch(
                tick=tick,
                field="outputContract",
                oc_value=type(update).__name__,
                karr_value="dict",
                detail="next_update must return a mapping",
            )
            update = {}

        def port_update(
            name: str,
            *,
            required: bool = False,
            _update: dict[str, Any] = update,
            _tick: int = tick,
        ) -> dict[str, Any]:
            value = _update.get(name)
            if isinstance(value, dict):
                return value
            if required:
                record_mismatch(
                    tick=_tick,
                    field="outputContract",
                    oc_value=value,
                    karr_value=f"dict output port {name}",
                    detail=f"missing/malformed required output port {name}",
                )
            return {}

        def apply_count_deltas(
            *,
            port: str,
            wids: list[str],
            before: np.ndarray,
            _tick: int = tick,
        ) -> np.ndarray:
            result = before.astype(np.int64, copy=True)
            updates = port_update(port)
            wid_to_index = {wid: idx for idx, wid in enumerate(wids)}
            for wid, raw_delta in updates.items():
                if wid not in wid_to_index:
                    record_mismatch(
                        tick=_tick,
                        field="outputContract",
                        oc_value=wid,
                        karr_value=tuple(wids),
                        detail=f"unexpected {port} WID",
                    )
                    continue
                try:
                    delta = float(raw_delta)
                except (TypeError, ValueError):
                    record_mismatch(
                        tick=_tick,
                        field="outputContract",
                        oc_value=raw_delta,
                        karr_value="finite integer delta",
                        detail=f"{port}.{wid}",
                    )
                    continue
                if not math.isfinite(delta) or abs(delta - np.rint(delta)) > 1.0e-9:
                    record_mismatch(
                        tick=_tick,
                        field="outputContract",
                        oc_value=raw_delta,
                        karr_value="finite integer delta",
                        detail=f"{port}.{wid}",
                    )
                    continue
                result[wid_to_index[wid]] += int(np.rint(delta))
            return result

        oc_vectors = {
            "substrates": apply_count_deltas(
                port="substrates",
                wids=process.fixture_substrate_wids,
                before=np.asarray(before_values["substrates"]),
            ),
            "enzymes": apply_count_deltas(
                port="enzymes",
                wids=process.fixture_enzyme_wids,
                before=np.asarray(before_values["enzymes"]),
            ),
            "boundEnzymes": apply_count_deltas(
                port="boundEnzymes",
                wids=process.fixture_enzyme_wids,
                before=np.asarray(before_values["boundEnzymes"]),
            ),
        }
        for observable, oc_after in oc_vectors.items():
            karr_after = _integer_vector(grid, observable, tick, after=True)
            if not np.array_equal(oc_after, karr_after):
                record_mismatch(
                    tick=tick,
                    field=observable,
                    oc_value=oc_after,
                    karr_value=karr_after,
                )

        geometry_update = port_update("geometry", required=True)
        ring_update = port_update("ftsZRing", required=True)
        before_diameter = float(before_values["pinchedDiameter"])
        karr_diameter = _scalar(
            grid.after("pinchedDiameter", tick),
            label=f"seed {grid.seed} tick {tick} after pinchedDiameter",
        )
        try:
            oc_diameter = float(geometry_update.get("pinchedDiameter", before_diameter))
        except (TypeError, ValueError):
            oc_diameter = before_diameter
        if not math.isclose(oc_diameter, karr_diameter, rel_tol=1.0e-12, abs_tol=1.0e-18):
            record_mismatch(
                tick=tick,
                field="pinchedDiameter",
                oc_value=oc_diameter,
                karr_value=karr_diameter,
            )

        ring_field_map = {
            "ftsZRing_numEdgesOneStraight": "numEdgesOneStraight",
            "ftsZRing_numEdgesTwoStraight": "numEdgesTwoStraight",
            "ftsZRing_numEdgesTwoBent": "numEdgesTwoBent",
            "ftsZRing_numResidualBent": "numResidualBent",
        }
        for observable, field_name in ring_field_map.items():
            before_ring = int(before_values[observable])
            oc_ring = _integer_nonnegative(
                float(ring_update.get(field_name, before_ring)),
                label=f"OC {field_name} seed={grid.seed} tick={tick}",
            )
            karr_ring = _integer_nonnegative(
                _scalar(
                    grid.after(observable, tick),
                    label=f"seed {grid.seed} tick {tick} after {observable}",
                ),
                label=f"seed {grid.seed} tick {tick} after {observable}",
            )
            if oc_ring != karr_ring:
                record_mismatch(
                    tick=tick,
                    field=observable,
                    oc_value=oc_ring,
                    karr_value=karr_ring,
                )

        oc_rng_after = process._rng.get_state()  # noqa: SLF001
        if oc_rng_after != karr_rng_after:
            record_mismatch(
                tick=tick,
                field="randStreamState",
                oc_value=oc_rng_after,
                karr_value=karr_rng_after,
                detail="exit state",
            )
        previous_karr_exit = karr_rng_after

        requests = port_update("requests", required=True)
        process_requests = (
            requests.get(process.name, {}) if isinstance(requests.get(process.name), dict) else {}
        )
        expected_water_request = (
            process.num_ftsz_subunits_per_filament
            * int(
                np.asarray(before_values["enzymes"])[
                    process.enzyme_index_ftsz_gtp_polymer
                ]
            )
        )
        actual_water_request = process_requests.get(process.water_wid)
        if actual_water_request != float(expected_water_request):
            record_mismatch(
                tick=tick,
                field="waterRequest",
                oc_value=actual_water_request,
                karr_value=float(expected_water_request),
                detail="Cytokinesis.calcResourceRequirements_Current literal formula",
            )

        derived_checks = {
            "geometry.pinched": (
                geometry_update.get("pinched"),
                karr_diameter <= 0.0,
            ),
            "ftsZRing.numEdges": (
                ring_update.get("numEdges"),
                process.calc_num_edges(
                    karr_diameter,
                    process.default_filament_length_nm,
                ),
            ),
            "cell.division_complete": (
                port_update("cell", required=True).get("division_complete"),
                karr_diameter <= 0.0,
            ),
        }
        for detail, (actual, expected) in derived_checks.items():
            if actual != expected:
                record_mismatch(
                    tick=tick,
                    field="derivedOutputs",
                    oc_value=actual,
                    karr_value=expected,
                    detail=detail,
                )

        before_chromosome = _integer_nonnegative(
            _scalar(
                grid.before("chromosome_segregated", tick),
                label=f"seed {grid.seed} tick {tick} before chromosome_segregated",
            ),
            label=f"seed {grid.seed} tick {tick} before chromosome_segregated",
        )
        after_chromosome = _integer_nonnegative(
            _scalar(
                grid.after("chromosome_segregated", tick),
                label=f"seed {grid.seed} tick {tick} after chromosome_segregated",
            ),
            label=f"seed {grid.seed} tick {tick} after chromosome_segregated",
        )
        if before_chromosome != after_chromosome:
            raise CytokinesisGateError(
                f"{grid.trace_path}: chromosome_segregated changed within Cytokinesis "
                f"tick {tick}, but Cytokinesis.m only reads this field"
            )

        if karr_diameter < before_diameter:
            karr_event_ticks.append(tick)
            karr_payloads.append(karr_diameter)
        if oc_diameter < before_diameter:
            oc_event_ticks.append(tick)
            oc_payloads.append(oc_diameter)

    return CytokinesisProjectionSurface(
        evidence=row,
        karr_event_ticks=tuple(karr_event_ticks),
        oc_event_ticks=tuple(oc_event_ticks),
        karr_payloads=tuple(karr_payloads),
        oc_payloads=tuple(oc_payloads),
        replay_authority_class="FULL_NEXT_UPDATE_REPLAY_READY",
        replay_capability_reason="",
        full_replay_checked_ticks=grid.n_ticks,
        full_replay_field_mismatch_counts=mismatch_counts,
        full_replay_first_mismatches=tuple(first_mismatches),
    )


def _evaluate_seed(
    *,
    seed: int,
    trace_path: Path,
    require_full_replay: bool = False,
    sut_projector: Callable[[float, float], float] = DEFAULT_SUT_PROJECTOR,
    sut_runner: Callable[
        [KarrCytokinesisProcess, dict[str, Any]],
        dict[str, Any],
    ] = DEFAULT_SUT_RUNNER,
) -> CytokinesisProjectionSurface:
    partner_path = trace_path.parent / f"FtsZPolymerization_{FTSZ_N_TICKS}ticks.mat"
    capability = cytokinesis_full_replay_capability(trace_path, partner_path)
    if require_full_replay and not capability.ready:
        raise CytokinesisGateError(
            f"seed {seed}: full Cytokinesis next_update replay authority refused: "
            f"{capability.reason}"
        )
    required_observables = (
        FULL_REPLAY_REQUIRED_OBSERVABLES
        if capability.ready
        else BASE_REQUIRED_OBSERVABLES
    )
    grid = load_event_window(
        trace_path,
        required_observables=required_observables,
        require_stride_contract=True,
    )
    row = analyze_seed(seed, grid)
    process = KarrCytokinesisProcess({"rng_seed": seed})
    if capability.ready:
        return _full_replay_surface(
            row=row,
            grid=grid,
            process=process,
            sut_runner=sut_runner,
        )
    return _conditional_projection_surface(
        row=row,
        grid=grid,
        process=process,
        capability_reason=capability.reason,
        sut_projector=sut_projector,
    )


def _evaluate_default_seed(
    args: tuple[int, Path, bool],
) -> CytokinesisProjectionSurface:
    seed, trace_path, require_full_replay = args
    return _evaluate_seed(
        seed=seed,
        trace_path=trace_path,
        require_full_replay=require_full_replay,
    )


def build_gate(
    *,
    context: DivisionGateContext,
    sut_projector: Callable[[float, float], float] = DEFAULT_SUT_PROJECTOR,
    sut_runner: Callable[
        [KarrCytokinesisProcess, dict[str, Any]],
        dict[str, Any],
    ] = DEFAULT_SUT_RUNNER,
    workers: int = 1,
) -> dict[str, Any]:
    entry = l22_catalog.in_scope_processes()[PROCESS_NAME]
    tasks = tuple(
        (
            seed,
            (
                context.source_root
                / f"per_process_traces_v2_event_s{seed:03d}"
                / f"{PROCESS_NAME}_{CYTOKINESIS_M_TICKS}ticks.mat"
            ),
            context.authoritative,
        )
        for seed in context.selected_seeds
    )
    if (
        workers > 1
        and sut_projector == DEFAULT_SUT_PROJECTOR
        and sut_runner == DEFAULT_SUT_RUNNER
    ):
        with ProcessPoolExecutor(max_workers=workers) as pool:
            surfaces = tuple(pool.map(_evaluate_default_seed, tasks))
    else:
        surfaces = tuple(
            _evaluate_seed(
                seed=seed,
                trace_path=trace_path,
                require_full_replay=require_full_replay,
                sut_projector=sut_projector,
                sut_runner=sut_runner,
            )
            for seed, trace_path, require_full_replay in tasks
        )
    replay_authority_classes = {
        surface.replay_authority_class for surface in surfaces
    }
    if len(replay_authority_classes) != 1:
        raise CytokinesisGateError(
            "mixed Cytokinesis replay projections are not a homogeneous gate cohort: "
            f"{sorted(replay_authority_classes)}"
        )
    replay_authority_class = next(iter(replay_authority_classes))
    full_replay = replay_authority_class == "FULL_NEXT_UPDATE_REPLAY_READY"
    if context.authoritative and not full_replay:
        raise CytokinesisGateError(
            "authoritative Cytokinesis gate requires full next_update replay for every seed"
        )
    evidence_rows = [surface.evidence for surface in surfaces]

    karr_offsets = np.asarray([row.onset_to_completion_ticks for row in evidence_rows])
    oc_offsets = np.asarray(
        [
            (
                surface.oc_event_ticks[-1] - surface.oc_event_ticks[0]
                if surface.oc_event_ticks
                else 0
            )
            for surface in surfaces
        ],
        dtype=np.float64,
    )
    karr_event_counts = np.asarray(
        [len(surface.karr_event_ticks) for surface in surfaces],
        dtype=np.float64,
    )
    oc_event_counts = np.asarray(
        [len(surface.oc_event_ticks) for surface in surfaces],
        dtype=np.float64,
    )
    karr_payloads = np.asarray(
        [value for surface in surfaces for value in surface.karr_payloads],
        dtype=np.float64,
    )
    oc_payloads = np.asarray(
        [value for surface in surfaces for value in surface.oc_payloads],
        dtype=np.float64,
    )
    karr_payload_nonzero = len(karr_payloads)
    oc_payload_nonzero = len(oc_payloads)
    replay_findings: list[dict[str, Any]] = []
    full_replay_field_mismatch_counts = {
        field: int(
            sum(
                surface.full_replay_field_mismatch_counts.get(field, 0)
                for surface in surfaces
            )
        )
        for field in FULL_REPLAY_AUDIT_FIELDS
    }
    full_replay_mismatch_total = int(
        sum(full_replay_field_mismatch_counts.values())
    )
    full_replay_checked_ticks = int(
        sum(surface.full_replay_checked_ticks for surface in surfaces)
    )

    for surface in surfaces:
        row = surface.evidence
        replay_findings.append(
            {
                "seed": row.seed,
                "karr_contraction_count": len(surface.karr_event_ticks),
                "oc_contraction_count": len(surface.oc_event_ticks),
                "karr_onset_offset": surface.karr_event_ticks[0],
                "oc_onset_offset": (
                    surface.oc_event_ticks[0] if surface.oc_event_ticks else None
                ),
                "karr_completion_offset": surface.karr_event_ticks[-1],
                "oc_completion_offset": (
                    surface.oc_event_ticks[-1] if surface.oc_event_ticks else None
                ),
                "karr_water_consumed_diagnostic": row.water_consumed,
                "replay_authority_class": surface.replay_authority_class,
                "replay_capability_reason": surface.replay_capability_reason,
                "full_replay_checked_ticks": surface.full_replay_checked_ticks,
                "full_replay_field_mismatch_counts": (
                    surface.full_replay_field_mismatch_counts
                ),
                "full_replay_first_mismatches": list(
                    surface.full_replay_first_mismatches
                ),
            }
        )

    timing_q95, timing_threshold = _analytical_timing_threshold(karr_offsets)
    timing_w1 = float(wasserstein_distance(karr_offsets, oc_offsets))
    count_w1 = float(wasserstein_distance(karr_event_counts, oc_event_counts))
    payload_mismatches = 0
    if len(karr_payloads) != len(oc_payloads):
        payload_mismatches += abs(len(karr_payloads) - len(oc_payloads))
    for karr_value, oc_value in zip(karr_payloads, oc_payloads, strict=False):
        if not math.isclose(karr_value, oc_value, rel_tol=1.0e-12, abs_tol=1.0e-18):
            payload_mismatches += 1
    payload_w1 = float(payload_mismatches)
    source_projection_ok = all(
        row.hydrolysis_stoichiometry_ok
        and not row.source_projection_mismatch_ticks
        and row.polymer_payload_redundant
        for row in evidence_rows
    )
    full_replay_ok = full_replay and full_replay_mismatch_total == 0
    normalized_timing = (
        timing_w1 / timing_threshold if math.isfinite(timing_w1) else float("inf")
    )
    composite_statistic = max(
        payload_w1,
        count_w1,
        normalized_timing,
        0.0 if source_projection_ok else 2.0,
        float(full_replay_mismatch_total) if full_replay else 0.0,
    )

    primary_threshold = 0.0 if full_replay else 1.0
    channels = {
        "pinchedDiameter": {
            "aggregation": "per_tick_vector_w1_mean",
            "is_primary": True,
            "is_event_channel": False,
            "w1_oc_vs_karr": composite_statistic,
            "threshold": primary_threshold,
            "q95_null": 0.0,
            "n_nonzero_oc": oc_payload_nonzero,
            "n_nonzero_karr": karr_payload_nonzero,
            "payload": {
                "pinched_diameter_mismatch_count": payload_mismatches,
                "karr_event_payload_count": len(karr_payloads),
                "oc_event_payload_count": len(oc_payloads),
                "full_replay_field_mismatch_counts": (
                    full_replay_field_mismatch_counts
                ),
            },
        },
        "contraction_event_count": {
            "aggregation": "per_tick_vector_w1_mean",
            "is_primary": False,
            "is_event_channel": False,
            "w1_oc_vs_karr": count_w1,
            "threshold": 0.0,
            "q95_null": 0.0,
            "n_nonzero_oc": int(np.sum(oc_event_counts)),
            "n_nonzero_karr": int(np.sum(karr_event_counts)),
        },
        "onset_to_completion_timing": {
            "aggregation": "per_tick_vector_w1_mean",
            "is_primary": False,
            "is_event_channel": False,
            "w1_oc_vs_karr": timing_w1,
            "threshold": timing_threshold,
            "q95_null": timing_q95,
            "n_nonzero_oc": int(np.sum(oc_event_counts)),
            "n_nonzero_karr": int(np.count_nonzero(karr_offsets)),
        },
    }
    if full_replay:
        for field in FULL_REPLAY_NONREDUNDANT_FIELDS:
            if field == "pinchedDiameter":
                continue
            mismatch_count = full_replay_field_mismatch_counts[field]
            channels[field] = {
                "aggregation": "per_tick_vector_w1_mean",
                "is_primary": False,
                "is_event_channel": False,
                "w1_oc_vs_karr": float(mismatch_count),
                "threshold": 0.0,
                "q95_null": 0.0,
                "n_nonzero_oc": full_replay_checked_ticks,
                "n_nonzero_karr": full_replay_checked_ticks,
            }
    result = {
        "process": PROCESS_NAME,
        "seeds": list(context.selected_seeds),
        "ticks": entry.m_ticks,
        "channels": channels,
        "warnings": (
            []
            if full_replay
            else [
                "conditional pilot only: trace lacks the source-bound "
                "Cytokinesis process randStreamState projection required "
                "for full next_update replay"
            ]
        ),
        "gate_surface": {
            "adapter_id": (
                FULL_REPLAY_ADAPTER_ID
                if full_replay
                else CONDITIONAL_ADAPTER_ID
            ),
            "cohort_status": context.cohort_status,
            "authority_eligible": context.authoritative and full_replay,
            "replay_authority_class": replay_authority_class,
            "full_next_update_replay": full_replay,
            "full_replay_checked_ticks": full_replay_checked_ticks,
            "full_replay_field_mismatch_counts": (
                full_replay_field_mismatch_counts
            ),
            "full_replay_passed": full_replay_ok,
            "event_semantics": "each strict pinchedDiameter decrease is one contraction-cycle event; final zero is completion",
            "payload_semantics": (
                "full OC next_update with captured before-state and restored "
                "private process RNG"
                if full_replay
                else "conditional OC calc_next_pinched_diameter under Karr's observed ring schedule"
            ),
            "meaningful_nonredundant_outputs": (
                list(FULL_REPLAY_NONREDUNDANT_FIELDS)
                if full_replay
                else ["pinchedDiameter"]
            ),
            "excluded_redundant_outputs": [
                "geometry.pinched is determined by pinchedDiameter",
                "ftsZRing.numEdges is determined by pinchedDiameter and fixture filament length",
                "cell.division_complete and division_progress are compatibility projections of pinchedDiameter",
                "fixed ring constants are fixture inputs, not stochastic outputs",
            ],
            "conditional_projection_reason": (
                "" if full_replay else surfaces[0].replay_capability_reason
            ),
            "per_seed": [row.to_json() for row in evidence_rows],
            "replay_findings": replay_findings,
        },
    }
    inputs = [
        {
            "kind": "oracle_data",
            "path": portable_oracle_path(row.trace_path),
            "_verify_path": str(row.trace_path.resolve()),
            "sha256": row.trace_sha256,
            "seed": row.seed,
            "n_ticks": entry.m_ticks,
            "trace_kind": "dual_division_window",
        }
        for row in evidence_rows
    ]
    inputs.extend(
        {
            "kind": "code",
            "path": repo_relative_or_absolute(path),
            "sha256": sha256_file(path),
        }
        for path in (
            l22_catalog.REPO_ROOT / "scripts" / "l2_event" / "cytokinesis_n20_gate.py",
            l22_catalog.REPO_ROOT / "scripts" / "l2_event" / "adapters" / "cytokinesis.py",
            l22_catalog.REPO_ROOT
            / "scripts"
            / "l2_event"
            / "validate_dual_division_canary.py",
            l22_catalog.REPO_ROOT
            / "scripts"
            / "matlab"
            / "extract_dual_division_window.m",
            l22_catalog.REPO_ROOT / "opencell" / "vivarium" / "karr_cytokinesis.py",
            l22_catalog.REPO_ROOT
            / "opencell"
            / "util"
            / "mcg16807_state_codec.py",
        )
    )
    threshold_channels: dict[str, dict[str, Any]] = {
        "pinchedDiameter": {
            "threshold": primary_threshold,
            "rule": (
                "zero mismatch across every meaningful non-redundant "
                "full-replay output, plus exact event payload/count/timing"
                if full_replay
                else "zero payload mismatches, zero event-count distance, Karr-only timing threshold, and source-projection integrity"
            ),
        },
        "contraction_event_count": {
            "threshold": 0.0,
            "rule": "exact contraction-cycle event count under the observed Karr ring schedule",
        },
        "onset_to_completion_timing": {
            "threshold": timing_threshold,
            "q95_null": timing_q95,
            "rule": "95th percentile pairwise Karr timing spread, floor 1 tick",
        },
    }
    if full_replay:
        for field in FULL_REPLAY_NONREDUNDANT_FIELDS:
            if field == "pinchedDiameter":
                continue
            threshold_channels[field] = {
                "threshold": 0.0,
                "rule": "exact per-tick full next_update replay identity",
            }
    return {
        "result": result,
        "inputs": inputs,
        "thresholds": {
            "process": PROCESS_NAME,
            "calibration_policy": (
                "exact full next_update replay from captured Karr before-state "
                "and private process RNG"
                if full_replay
                else "Karr-only analytical rules fixed before conditional OC projection"
            ),
            "channels": threshold_channels,
        },
        "null_calibration": {
            "process": PROCESS_NAME,
            "source": "Karr-only",
            "oc_outcomes_read": False,
            "timing_offsets": karr_offsets.tolist(),
            "timing_pairwise_q95": timing_q95,
        },
        "summary": {
            "process": PROCESS_NAME,
            "mode": context.mode,
            "cohort_status": context.cohort_status,
            "generated_at": datetime.now(UTC).isoformat(),
            "selected_seeds": list(context.selected_seeds),
            "oc_completed_seed_count": int(
                sum(
                    bool(surface.oc_payloads) and surface.oc_payloads[-1] == 0.0
                    for surface in surfaces
                )
            ),
            "payload_w1": payload_w1,
            "timing_w1": timing_w1,
            "count_w1": count_w1,
            "timing_span_min": int(karr_offsets.min()),
            "timing_span_max": int(karr_offsets.max()),
            "replay_authority_class": replay_authority_class,
            "full_replay_checked_ticks": full_replay_checked_ticks,
            "full_replay_mismatch_total": full_replay_mismatch_total,
        },
        "analytical_check": {
            "applicable": True,
            "name": (
                "cytokinesis_full_next_update_replay"
                if full_replay
                else "cytokinesis_conditional_source_projection"
            ),
            "passed": source_projection_ok and (full_replay_ok if full_replay else True),
            "checked_transitions": int(
                sum(row.contraction_cycle_count for row in evidence_rows)
            ),
            "checked_ticks": full_replay_checked_ticks,
            "field_mismatch_counts": full_replay_field_mismatch_counts,
        },
    }


def run(*, source_root: Path, mode: str, workers: int = 1) -> dict[str, Any]:
    context = resolve_gate_context(source_root=source_root, mode=mode)
    payload = build_gate(context=context, workers=workers)
    report = {
        "process": PROCESS_NAME,
        "mode": mode,
        "cohort": context.audit.to_json(),
        **payload,
    }
    if context.authoritative:
        output_dir = write_authority_bundle(
            process=PROCESS_NAME,
            harness_type=HARNESS_TYPE,
            result=payload["result"],
            inputs=payload["inputs"],
            thresholds=payload["thresholds"],
            null_calibration=payload["null_calibration"],
            summary=payload["summary"],
            analytical_check=payload["analytical_check"],
        )
        report["output_dir"] = str(output_dir)
    else:
        report["output_path"] = str(
            write_pilot_report(process=PROCESS_NAME, payload=report)
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("pilot", "authority"), required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        report = run(
            source_root=args.source_root,
            mode=args.mode,
            workers=max(1, args.workers),
        )
    except (
        DivisionGateRefusalError,
        CytokinesisGateError,
        DuplicateCompletionTickDetectedError,
    ) as exc:
        print(f"REFUSED: {exc}")
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
