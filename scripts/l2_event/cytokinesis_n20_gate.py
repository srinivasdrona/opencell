"""Real Cytokinesis L2.2 N=20 gate over genuine dual-division traces.

The captured Cytokinesis trace contains real flattened process observables:
substrates, enzymes, boundEnzymes, pinchedDiameter, the four FtsZ-ring edge
counters, and chromosome_segregated. It does not contain the complete
state_before needed to replay ``KarrCytokinesisProcess.next_update`` without
fabricating geometry/ring constants or allocator state. This gate therefore
compares the source-faithful projected Cytokinesis transition implemented in
OpenCell -- ``calc_num_edges``/``calc_next_pinched_diameter`` -- against every
captured Karr contraction cycle, and compares meaningful process-local event
count/timing plus hydrolysis payload. No missing state is synthesized.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import math
import sys
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
from scripts.l2_event.window_loader import WindowGrid, load_event_window
from scripts.l22_evidence import catalog as l22_catalog

PROCESS_NAME = "Cytokinesis"
HARNESS_TYPE = "event_class"
ADAPTER_ID = "cytokinesis.contraction_projection.v2"
DEFAULT_SUT_PROJECTOR = KarrCytokinesisProcess.calc_next_pinched_diameter
REQUIRED_OBSERVABLES = (
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


def _evaluate_seed(
    *,
    seed: int,
    trace_path: Path,
    sut_projector=DEFAULT_SUT_PROJECTOR,
) -> CytokinesisProjectionSurface:
    grid = load_event_window(
        trace_path,
        required_observables=REQUIRED_OBSERVABLES,
        require_stride_contract=True,
    )
    row = analyze_seed(seed, grid)
    process = KarrCytokinesisProcess({"rng_seed": seed})
    karr_event_ticks: list[int] = []
    oc_event_ticks: list[int] = []
    karr_payloads: list[float] = []
    oc_payloads: list[float] = []

    for tick in range(grid.n_ticks):
        before = _scalar(
            grid.before("pinchedDiameter", tick),
            label=f"seed {seed} tick {tick} before diameter",
        )
        after = _scalar(
            grid.after("pinchedDiameter", tick),
            label=f"seed {seed} tick {tick} after diameter",
        )
        if after >= before:
            continue
        projected = float(
            sut_projector(
                before,
                process.default_filament_length_nm,
            )
        )
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
    )


def _evaluate_default_seed(args: tuple[int, Path]) -> CytokinesisProjectionSurface:
    seed, trace_path = args
    return _evaluate_seed(seed=seed, trace_path=trace_path)


def build_gate(
    *,
    context: DivisionGateContext,
    sut_projector=DEFAULT_SUT_PROJECTOR,
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
        )
        for seed in context.selected_seeds
    )
    if workers > 1 and sut_projector == DEFAULT_SUT_PROJECTOR:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            surfaces = tuple(pool.map(_evaluate_default_seed, tasks))
    else:
        surfaces = tuple(
            _evaluate_seed(
                seed=seed,
                trace_path=trace_path,
                sut_projector=sut_projector,
            )
            for seed, trace_path in tasks
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
    normalized_timing = (
        timing_w1 / timing_threshold if math.isfinite(timing_w1) else float("inf")
    )
    composite_statistic = max(
        payload_w1,
        count_w1,
        normalized_timing,
        0.0 if source_projection_ok else 2.0,
    )

    channels = {
        "pinchedDiameter": {
            "aggregation": "per_tick_vector_w1_mean",
            "is_primary": True,
            "is_event_channel": False,
            "w1_oc_vs_karr": composite_statistic,
            "threshold": 1.0,
            "q95_null": 0.0,
            "n_nonzero_oc": oc_payload_nonzero,
            "n_nonzero_karr": karr_payload_nonzero,
            "payload": {
                "pinched_diameter_mismatch_count": payload_mismatches,
                "karr_event_payload_count": len(karr_payloads),
                "oc_event_payload_count": len(oc_payloads),
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
    result = {
        "process": PROCESS_NAME,
        "seeds": list(context.selected_seeds),
        "ticks": entry.m_ticks,
        "channels": channels,
        "warnings": [],
        "gate_surface": {
            "adapter_id": ADAPTER_ID,
            "cohort_status": context.cohort_status,
            "authority_eligible": context.authoritative,
            "event_semantics": "each strict pinchedDiameter decrease is one contraction-cycle event; final zero is completion",
            "payload_semantics": "OC calc_next_pinched_diameter output vs Karr captured pinchedDiameter",
            "non_gateable_redundant_channels": [
                "substrate/enzyme/boundEnzyme OC replay requires missing per-tick randStreamState; trace-only deltas remain diagnostic",
                "bound FtsZ-GTP/GDP hydrolysis component is algebraically determined by substrate extent",
            ],
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
            l22_catalog.REPO_ROOT / "opencell" / "vivarium" / "karr_cytokinesis.py",
        )
    )
    return {
        "result": result,
        "inputs": inputs,
        "thresholds": {
            "process": PROCESS_NAME,
            "calibration_policy": "Karr-only analytical rules fixed before OC projection",
            "channels": {
                "pinchedDiameter": {
                    "threshold": 1.0,
                    "rule": "zero payload mismatches, zero event-count distance, Karr-only timing threshold, and source-projection integrity",
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
            },
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
        },
        "analytical_check": {
            "applicable": True,
            "name": "cytokinesis_source_projection",
            "passed": source_projection_ok,
            "checked_transitions": int(sum(row.contraction_cycle_count for row in evidence_rows)),
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
