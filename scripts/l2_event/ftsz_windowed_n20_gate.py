"""Windowed-continuous FtsZPolymerization L2.2 gate for the N=20 cohort.

FtsZPolymerization is an ODE/discretization process, not a binary event.
This gate compares the real per-tick enzyme and substrate update surfaces
over the selector-owned 200-tick pre-division windows. Thresholds are
calibrated exclusively from deterministic, symmetry-collapsed rotating
Karr-only seed splits; the calibration API cannot receive OC outcomes.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
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

from opencell.vivarium.karr_ftsz_polymerization import (
    KarrFtsZPolymerizationProcess,
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
from scripts.l2_event.ftsz_pre_division_evidence import (
    GATE_CHANNELS,
    GEOMETRY_VOLUME_CHANNEL,
    REQUIRED_M_TICKS,
    FtsZWindowContractError,
    geometry_volume_for_tick,
    validate_seed_window,
)
from scripts.l2_event.window_loader import EventWindowRefused
from scripts.l22_evidence import catalog as l22_catalog

PROCESS_NAME = "FtsZPolymerization"
HARNESS_TYPE = "windowed_continuous"
ADAPTER_ID = "ftsz.windowed_distribution.v1"
ENGINEERING_MULTIPLIER = 3.0
MIN_NONZERO_SAMPLES = 30


class FtsZGateError(RuntimeError):
    """Raised when a window/replay violates the continuous-gate contract."""


@dataclass(frozen=True)
class KarrOnlyCalibration:
    channel: str
    q95_null: float
    threshold: float
    seed_count: int
    unique_split_count: int
    symmetry_collapsed: bool
    component_scales: tuple[float, ...]
    split_statistics: tuple[float, ...]
    policy: str

    def to_json(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "q95_null": self.q95_null,
            "threshold": self.threshold,
            "seed_count": self.seed_count,
            "unique_split_count": self.unique_split_count,
            "symmetry_collapsed": self.symmetry_collapsed,
            "component_scales": list(self.component_scales),
            "split_statistics": list(self.split_statistics),
            "policy": self.policy,
        }


@dataclass(frozen=True)
class SeedSurface:
    seed: int
    trace_path: Path
    trace_sha256: str
    karr_enzymes: np.ndarray
    oc_enzymes: np.ndarray
    karr_substrates: np.ndarray
    oc_substrates: np.ndarray
    karr_activity_ticks: int
    oc_activity_ticks: int
    monomer_projection_max_abs_discrepancy: float
    geometry_volume_min_l: float
    geometry_volume_max_l: float

    def summary_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "trace_path": portable_oracle_path(self.trace_path),
            "trace_sha256": self.trace_sha256,
            "karr_activity_ticks": self.karr_activity_ticks,
            "oc_activity_ticks": self.oc_activity_ticks,
            "monomer_projection_max_abs_discrepancy": self.monomer_projection_max_abs_discrepancy,
            "geometry_volume_min_l": self.geometry_volume_min_l,
            "geometry_volume_max_l": self.geometry_volume_max_l,
        }


def _import_l2_replay_common():
    tests_dir = l22_catalog.REPO_ROOT / "tests" / "vivarium"
    import sys

    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    import l2_replay_common  # noqa: PLC0415

    return l2_replay_common


def _finite_matrix(value: np.ndarray, *, label: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.ndim != 2 or not np.all(np.isfinite(matrix)):
        raise FtsZGateError(f"{label} must be a finite 2-D matrix, got shape={matrix.shape}")
    return matrix


def _geometry_volume_for_tick(grid: Any, tick: int) -> float:
    try:
        return geometry_volume_for_tick(grid, tick)
    except FtsZWindowContractError as exc:
        raise FtsZGateError(str(exc)) from exc


def _component_scales(karr_seed_arrays: tuple[np.ndarray, ...]) -> np.ndarray:
    pooled = np.concatenate(karr_seed_arrays, axis=0)
    q25 = np.quantile(pooled, 0.25, axis=0)
    q75 = np.quantile(pooled, 0.75, axis=0)
    return np.maximum(1.0, q75 - q25)


def _scaled_component_w1(
    left: tuple[np.ndarray, ...],
    right: tuple[np.ndarray, ...],
    scales: np.ndarray,
) -> float:
    left_pool = np.concatenate(left, axis=0)
    right_pool = np.concatenate(right, axis=0)
    if left_pool.shape[1] != right_pool.shape[1] or left_pool.shape[1] != len(scales):
        raise FtsZGateError("component width mismatch in FtsZ distributional distance")
    distances = [
        float(wasserstein_distance(left_pool[:, idx], right_pool[:, idx])) / float(scales[idx])
        for idx in range(left_pool.shape[1])
    ]
    return float(np.mean(distances))


def _component_support_findings(
    karr_seed_arrays: tuple[np.ndarray, ...],
    oc_seed_arrays: tuple[np.ndarray, ...],
    *,
    wids: tuple[str, ...],
) -> list[dict[str, Any]]:
    karr_pool = np.concatenate(karr_seed_arrays, axis=0)
    oc_pool = np.concatenate(oc_seed_arrays, axis=0)
    if (
        karr_pool.shape[1] != oc_pool.shape[1]
        or karr_pool.shape[1] != len(wids)
    ):
        raise FtsZGateError("component width mismatch in FtsZ support guard")

    findings: list[dict[str, Any]] = []
    for idx, wid in enumerate(wids):
        karr_nonzero = int(np.count_nonzero(karr_pool[:, idx]))
        oc_nonzero = int(np.count_nonzero(oc_pool[:, idx]))
        if karr_nonzero == 0 and oc_nonzero == 0:
            continue
        if (
            karr_nonzero < MIN_NONZERO_SAMPLES
            or oc_nonzero < MIN_NONZERO_SAMPLES
        ):
            findings.append(
                {
                    "wid": wid,
                    "karr_nonzero": karr_nonzero,
                    "oc_nonzero": oc_nonzero,
                    "minimum_required_per_side": MIN_NONZERO_SAMPLES,
                    "reason": "insufficient per-component nonzero support",
                }
            )
    return findings


def calibrate_karr_only(
    channel: str,
    karr_seed_arrays: tuple[np.ndarray, ...],
) -> KarrOnlyCalibration:
    """Calibrate a channel without accepting, reading, or naming OC data.

    The seed order is selector-owned and fixed before outcomes. For each
    circular rotation, the first floor(N/2) Karr seeds form one sample and
    the remainder form the holdout. For even N, rotation N/2 only swaps the
    two halves of rotation 0, and W1 is symmetric, so only the first N/2
    unordered split pairs are distinct. Odd N has no exact complementary
    duplicate and retains all N rotations. The 95th percentile of those
    Karr-only distances is multiplied by the preregistered engineering
    factor 3.
    """
    if len(karr_seed_arrays) < 4:
        raise DivisionGateRefusalError(
            f"{channel}: Karr-only rotating split calibration needs at least 4 seeds"
        )
    matrices = tuple(
        _finite_matrix(array, label=f"{channel} Karr seed matrix")
        for array in karr_seed_arrays
    )
    widths = {matrix.shape[1] for matrix in matrices}
    if len(widths) != 1:
        raise FtsZGateError(f"{channel}: Karr seed matrices have inconsistent widths")
    scales = _component_scales(matrices)
    split_size = len(matrices) // 2
    symmetry_collapsed = len(matrices) % 2 == 0
    rotation_count = split_size if symmetry_collapsed else len(matrices)
    split_statistics: list[float] = []
    for rotation in range(rotation_count):
        rotated = matrices[rotation:] + matrices[:rotation]
        left = rotated[:split_size]
        right = rotated[split_size:]
        split_statistics.append(_scaled_component_w1(left, right, scales))
    q95 = float(np.quantile(np.asarray(split_statistics), 0.95))
    threshold = ENGINEERING_MULTIPLIER * q95
    return KarrOnlyCalibration(
        channel=channel,
        q95_null=q95,
        threshold=threshold,
        seed_count=len(matrices),
        unique_split_count=len(split_statistics),
        symmetry_collapsed=symmetry_collapsed,
        component_scales=tuple(float(value) for value in scales),
        split_statistics=tuple(split_statistics),
        policy=(
            "selector-order rotating Karr-only split/holdout; collapse "
            "complementary half-split duplicates when N is even; q95 over "
            f"distinct split statistics; threshold={ENGINEERING_MULTIPLIER}*q95"
        ),
    )


def _collect_surface(
    *,
    seed: int,
    trace_path: Path,
    process_factory=KarrFtsZPolymerizationProcess,
) -> SeedSurface:
    l2 = _import_l2_replay_common()
    try:
        grid = validate_seed_window(
            seed,
            trace_path,
            required_observables=(*GATE_CHANNELS, GEOMETRY_VOLUME_CHANNEL),
        )
    except (EventWindowRefused, FtsZWindowContractError) as exc:
        raise FtsZGateError(
            f"seed {seed}: source-faithful replay requires captured "
            f"{GEOMETRY_VOLUME_CHANNEL!r}: {exc}"
        ) from exc
    process = process_factory({"rng_seed": seed})
    state_template = l2.build_state_template(process)
    wids_by_observable: dict[str, list[str]] = {}
    for observable in GATE_CHANNELS:
        explicit_attr = {"substrates": "substrate_wids", "enzymes": "enzyme_wids"}[
            observable
        ]
        wids_by_observable[observable] = l2.infer_wids_for_observable(
            process,
            state_template,
            observable,
            karr_len=int(grid.before(observable, 0).shape[0]),
            explicit_attr=explicit_attr,
        )

    karr_enzyme_rows: list[np.ndarray] = []
    oc_enzyme_rows: list[np.ndarray] = []
    karr_substrate_rows: list[np.ndarray] = []
    oc_substrate_rows: list[np.ndarray] = []
    monomer_discrepancy: list[float] = []
    geometry_volumes: list[float] = []

    for tick in range(grid.n_ticks):
        state = l2.build_state_template(process)
        if state.get("trace_hint"):
            raise FtsZGateError("FtsZ gate forbids trace_hint before overlay")
        before = {observable: grid.before(observable, tick) for observable in GATE_CHANNELS}
        after = {observable: grid.after(observable, tick) for observable in GATE_CHANNELS}
        for observable in GATE_CHANNELS:
            l2.overlay_observable_into_state(
                process=process,
                state=state,
                observable=observable,
                vector=before[observable],
                wids=wids_by_observable[observable],
            )
        try:
            volume_l = _geometry_volume_for_tick(grid, tick)
        except FtsZGateError as exc:
            raise FtsZGateError(f"seed {seed} {exc}") from exc
        state["geometry"]["volume"] = volume_l
        geometry_volumes.append(volume_l)
        l2.refresh_allocator_views(process, state)
        if state.get("trace_hint"):
            raise FtsZGateError("FtsZ gate forbids trace_hint after overlay")

        with l2.forbid_sut_oracle_file_io():
            update = process.next_update(1.0, state)
        deltas = dict(l2.collect_count_delta_dicts(update))
        oc_enzyme = np.asarray(
            [
                float(deltas.get("enzymes", {}).get(wid, 0.0))
                for wid in process.enzyme_wids
            ],
            dtype=np.float64,
        )
        oc_substrate = np.asarray(
            [
                float(deltas.get("substrates", {}).get(wid, 0.0))
                for wid in process.substrate_wids
            ],
            dtype=np.float64,
        )
        karr_enzyme = np.asarray(after["enzymes"] - before["enzymes"], dtype=np.float64)
        karr_substrate = np.asarray(
            after["substrates"] - before["substrates"], dtype=np.float64
        )
        for label, vector in (
            ("karr_enzyme", karr_enzyme),
            ("oc_enzyme", oc_enzyme),
            ("karr_substrate", karr_substrate),
            ("oc_substrate", oc_substrate),
        ):
            if not np.all(np.isfinite(vector)):
                raise FtsZGateError(f"seed {seed} tick {tick}: {label} is non-finite")
            if np.any(np.abs(vector - np.rint(vector)) > 1.0e-9):
                raise FtsZGateError(
                    f"seed {seed} tick {tick}: {label} contains non-integral count deltas"
                )

        karr_enzyme_rows.append(karr_enzyme)
        oc_enzyme_rows.append(oc_enzyme)
        karr_substrate_rows.append(karr_substrate)
        oc_substrate_rows.append(oc_substrate)
        monomer_discrepancy.append(
            abs(
                float(np.dot(process.n_monomers, karr_enzyme))
                - float(np.dot(process.n_monomers, oc_enzyme))
            )
        )

    karr_enzymes = np.vstack(karr_enzyme_rows)
    oc_enzymes = np.vstack(oc_enzyme_rows)
    karr_substrates = np.vstack(karr_substrate_rows)
    oc_substrates = np.vstack(oc_substrate_rows)
    return SeedSurface(
        seed=seed,
        trace_path=grid.trace_path,
        trace_sha256=sha256_file(grid.trace_path),
        karr_enzymes=karr_enzymes,
        oc_enzymes=oc_enzymes,
        karr_substrates=karr_substrates,
        oc_substrates=oc_substrates,
        karr_activity_ticks=int(np.count_nonzero(np.sum(np.abs(karr_enzymes), axis=1))),
        oc_activity_ticks=int(np.count_nonzero(np.sum(np.abs(oc_enzymes), axis=1))),
        monomer_projection_max_abs_discrepancy=float(np.max(monomer_discrepancy)),
        geometry_volume_min_l=float(np.min(geometry_volumes)),
        geometry_volume_max_l=float(np.max(geometry_volumes)),
    )


def _collect_default_surface(args: tuple[int, Path]) -> SeedSurface:
    seed, trace_path = args
    return _collect_surface(seed=seed, trace_path=trace_path)


def _zero_support_findings(
    karr_seed_arrays: tuple[np.ndarray, ...],
    oc_seed_arrays: tuple[np.ndarray, ...],
    *,
    wids: tuple[str, ...],
) -> list[dict[str, Any]]:
    karr_pool = np.concatenate(karr_seed_arrays, axis=0)
    oc_pool = np.concatenate(oc_seed_arrays, axis=0)
    findings: list[dict[str, Any]] = []
    for idx, wid in enumerate(wids):
        karr_nonzero = int(np.count_nonzero(karr_pool[:, idx]))
        oc_nonzero = int(np.count_nonzero(oc_pool[:, idx]))
        if (karr_nonzero == 0) != (oc_nonzero == 0):
            findings.append(
                {
                    "wid": wid,
                    "karr_nonzero": karr_nonzero,
                    "oc_nonzero": oc_nonzero,
                    "reason": "zero-vs-nonzero support mismatch",
                }
            )
    return findings


def build_gate(
    *,
    context: DivisionGateContext,
    process_factory=KarrFtsZPolymerizationProcess,
    workers: int = 1,
) -> dict[str, Any]:
    entry = l22_catalog.in_scope_processes()[PROCESS_NAME]
    tasks = tuple(
        (
            seed,
            (
                context.source_root
                / f"per_process_traces_v2_event_s{seed:03d}"
                / f"{PROCESS_NAME}_{REQUIRED_M_TICKS}ticks.mat"
            ),
        )
        for seed in context.selected_seeds
    )
    if workers > 1 and process_factory is KarrFtsZPolymerizationProcess:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            surfaces = tuple(pool.map(_collect_default_surface, tasks))
    else:
        surfaces = tuple(
            _collect_surface(
                seed=seed,
                trace_path=trace_path,
                process_factory=process_factory,
            )
            for seed, trace_path in tasks
        )
    split_index = len(surfaces) // 2
    calibration_surfaces = surfaces[:split_index]
    evaluation_surfaces = surfaces[split_index:]
    if len(calibration_surfaces) < 4 or len(evaluation_surfaces) < 2:
        raise DivisionGateRefusalError(
            "FtsZ windowed gate needs at least 4 Karr-only calibration seeds "
            "and 2 independent evaluation seeds"
        )
    probe_process = KarrFtsZPolymerizationProcess()
    calibration_karr_enzymes = tuple(
        surface.karr_enzymes for surface in calibration_surfaces
    )
    calibration_karr_substrates = tuple(
        surface.karr_substrates for surface in calibration_surfaces
    )
    karr_enzymes = tuple(surface.karr_enzymes for surface in evaluation_surfaces)
    oc_enzymes = tuple(surface.oc_enzymes for surface in evaluation_surfaces)
    karr_substrates = tuple(
        surface.karr_substrates for surface in evaluation_surfaces
    )
    oc_substrates = tuple(surface.oc_substrates for surface in evaluation_surfaces)

    enzyme_calibration = calibrate_karr_only(
        "enzymes", calibration_karr_enzymes
    )
    substrate_calibration = calibrate_karr_only(
        "substrates", calibration_karr_substrates
    )
    enzyme_distance = _scaled_component_w1(
        karr_enzymes,
        oc_enzymes,
        np.asarray(enzyme_calibration.component_scales),
    )
    substrate_distance = _scaled_component_w1(
        karr_substrates,
        oc_substrates,
        np.asarray(substrate_calibration.component_scales),
    )
    enzyme_zero_mismatches = _zero_support_findings(
        karr_enzymes,
        oc_enzymes,
        wids=tuple(probe_process.enzyme_wids),
    )
    substrate_zero_mismatches = _zero_support_findings(
        karr_substrates,
        oc_substrates,
        wids=tuple(probe_process.substrate_wids),
    )
    enzyme_support_failures = _component_support_findings(
        karr_enzymes,
        oc_enzymes,
        wids=tuple(probe_process.enzyme_wids),
    )
    substrate_support_failures = _component_support_findings(
        karr_substrates,
        oc_substrates,
        wids=tuple(probe_process.substrate_wids),
    )
    activity_failures = [
        {
            "seed": surface.seed,
            "karr_activity_ticks": surface.karr_activity_ticks,
            "oc_activity_ticks": surface.oc_activity_ticks,
        }
        for surface in evaluation_surfaces
        if surface.karr_activity_ticks == 0 or surface.oc_activity_ticks == 0
    ]
    monomer_failures = [
        {
            "seed": surface.seed,
            "max_abs_discrepancy": surface.monomer_projection_max_abs_discrepancy,
        }
        for surface in evaluation_surfaces
        if surface.monomer_projection_max_abs_discrepancy != 0.0
    ]
    karr_enzyme_nonzero = int(
        np.count_nonzero(np.concatenate(karr_enzymes, axis=0))
    )
    oc_enzyme_nonzero = int(np.count_nonzero(np.concatenate(oc_enzymes, axis=0)))
    karr_substrate_nonzero = int(
        np.count_nonzero(np.concatenate(karr_substrates, axis=0))
    )
    oc_substrate_nonzero = int(
        np.count_nonzero(np.concatenate(oc_substrates, axis=0))
    )
    insufficient = bool(enzyme_support_failures)

    enzyme_effective_distance = enzyme_distance
    if (
        activity_failures
        or enzyme_zero_mismatches
        or enzyme_support_failures
        or monomer_failures
    ):
        enzyme_effective_distance = max(
            enzyme_effective_distance,
            enzyme_calibration.threshold + max(1.0, enzyme_calibration.q95_null),
        )
    substrate_effective_distance = substrate_distance
    if substrate_zero_mismatches or substrate_support_failures:
        substrate_effective_distance = max(
            substrate_effective_distance,
            substrate_calibration.threshold
            + max(1.0, substrate_calibration.q95_null),
        )

    channels = {
        "enzymes": {
            "aggregation": "per_tick_vector_w1_mean",
            "is_primary": True,
            "is_event_channel": False,
            "w1_oc_vs_karr": enzyme_effective_distance,
            "threshold": enzyme_calibration.threshold,
            "q95_null": enzyme_calibration.q95_null,
            "n_nonzero_oc": oc_enzyme_nonzero,
            "n_nonzero_karr": karr_enzyme_nonzero,
            "raw_distribution_distance": enzyme_distance,
            "minimum_nonzero_samples_per_active_component": MIN_NONZERO_SAMPLES,
        },
        "substrates": {
            "aggregation": "per_tick_vector_w1_mean",
            "is_primary": False,
            "is_event_channel": False,
            "w1_oc_vs_karr": substrate_effective_distance,
            "threshold": substrate_calibration.threshold,
            "q95_null": substrate_calibration.q95_null,
            "n_nonzero_oc": oc_substrate_nonzero,
            "n_nonzero_karr": karr_substrate_nonzero,
            "raw_distribution_distance": substrate_distance,
            "minimum_nonzero_samples_per_active_component": MIN_NONZERO_SAMPLES,
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
            "semantics": "windowed continuous enzyme/substrate update distributions",
            "activity_failures": activity_failures,
            "enzyme_zero_support_mismatches": enzyme_zero_mismatches,
            "substrate_zero_support_mismatches": substrate_zero_mismatches,
            "enzyme_component_support_failures": enzyme_support_failures,
            "substrate_component_support_failures": substrate_support_failures,
            "insufficient_primary_samples": insufficient,
            "monomer_projection_failures": monomer_failures,
            "calibration_seeds": [
                surface.seed for surface in calibration_surfaces
            ],
            "evaluation_seeds": [
                surface.seed for surface in evaluation_surfaces
            ],
            "per_seed": [surface.summary_json() for surface in surfaces],
        },
    }
    inputs = [
        {
            "kind": "oracle_data",
            "path": portable_oracle_path(surface.trace_path),
            "_verify_path": str(surface.trace_path.resolve()),
            "sha256": surface.trace_sha256,
            "seed": surface.seed,
            "n_ticks": entry.m_ticks,
            "trace_kind": "dual_division_window",
        }
        for surface in surfaces
    ]
    inputs.extend(
        {
            "kind": "code",
            "path": repo_relative_or_absolute(path),
            "sha256": sha256_file(path),
        }
        for path in (
            l22_catalog.REPO_ROOT / "scripts" / "l2_event" / "ftsz_windowed_n20_gate.py",
            l22_catalog.REPO_ROOT / "scripts" / "l2_event" / "ftsz_pre_division_evidence.py",
            l22_catalog.REPO_ROOT / "scripts" / "matlab" / "extract_dual_division_window.m",
            l22_catalog.REPO_ROOT / "opencell" / "vivarium" / "karr_ftsz_polymerization.py",
            l22_catalog.REPO_ROOT / "tests" / "vivarium" / "l2_replay_common.py",
        )
    )
    return {
        "result": result,
        "inputs": inputs,
        "thresholds": {
            "process": PROCESS_NAME,
            "calibration_policy": (
                "Karr-only rotating split/holdout with complementary "
                "half-split duplicates collapsed; OC outcomes inaccessible "
                "to calibrator"
            ),
            "calibration_seeds": [
                surface.seed for surface in calibration_surfaces
            ],
            "evaluation_seeds": [
                surface.seed for surface in evaluation_surfaces
            ],
            "channels": {
                "enzymes": enzyme_calibration.to_json(),
                "substrates": substrate_calibration.to_json(),
            },
        },
        "null_calibration": {
            "process": PROCESS_NAME,
            "source": "Karr-only",
            "oc_outcomes_read": False,
            "calibration_seeds": [
                surface.seed for surface in calibration_surfaces
            ],
            "evaluation_seeds": [
                surface.seed for surface in evaluation_surfaces
            ],
            "channels": {
                "enzymes": enzyme_calibration.to_json(),
                "substrates": substrate_calibration.to_json(),
            },
        },
        "summary": {
            "process": PROCESS_NAME,
            "mode": context.mode,
            "cohort_status": context.cohort_status,
            "generated_at": datetime.now(UTC).isoformat(),
            "selected_seeds": list(context.selected_seeds),
            "calibration_seeds": [
                surface.seed for surface in calibration_surfaces
            ],
            "evaluation_seeds": [
                surface.seed for surface in evaluation_surfaces
            ],
            "enzyme_distance": enzyme_distance,
            "enzyme_threshold": enzyme_calibration.threshold,
            "substrate_distance": substrate_distance,
            "substrate_threshold": substrate_calibration.threshold,
            "karr_activity_seed_count": sum(
                surface.karr_activity_ticks > 0
                for surface in evaluation_surfaces
            ),
            "oc_activity_seed_count": sum(
                surface.oc_activity_ticks > 0 for surface in evaluation_surfaces
            ),
            "monomer_projection_max_abs_discrepancy": max(
                surface.monomer_projection_max_abs_discrepancy
                for surface in evaluation_surfaces
            ),
        },
        "analytical_check": {
            "applicable": True,
            "name": "ftsz_monomer_conservation_and_activity",
            "passed": not activity_failures
            and not monomer_failures
            and not enzyme_zero_mismatches
            and not substrate_zero_mismatches
            and not enzyme_support_failures
            and not substrate_support_failures
            and not insufficient,
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
            expected_selected_seeds=context.selected_seeds,
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
    except (DivisionGateRefusalError, FtsZGateError) as exc:
        print(f"REFUSED: {exc}")
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
