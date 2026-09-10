"""Pre-registered sparse-event gate for DNASupercoiling `delta_nnz`.

The design goal is to keep the shared Design-A metric unchanged while adding
an explicit DNAS-only guard against zero or strongly underactive OC support on
the sparse `linkingNumbers.delta_nnz` component.
"""

from __future__ import annotations

import math
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import binomtest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_VIVARIUM_TESTS = REPO_ROOT / "tests" / "vivarium"
if str(_VIVARIUM_TESTS) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS))

from _l2_2_design_a_projections import per_component_scaled_distance  # noqa: E402

VALUE_COMPONENT = "linkingNumbers.delta_value_sum"
SPARSE_COMPONENT = "linkingNumbers.delta_nnz"


@dataclass(frozen=True)
class DNASParseGateConfig:
    alpha_family: float = 0.05
    min_karr_pooled_nonzero_ticks: int = 31
    min_karr_active_seeds: int = 31
    min_karr_clustered_seeds: int = 6


DEFAULT_CONFIG = DNASParseGateConfig()


@dataclass(frozen=True)
class SupportCounts:
    pooled_nonzero_ticks: int
    active_seeds: int
    clustered_seeds: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def component_scale_from_values(values: np.ndarray) -> float:
    """Shared scale formula used by `per_component_scaled_distance`."""
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    nonzero = np.abs(arr[np.abs(arr) > 1e-12])
    if nonzero.size == 0:
        return 1.0
    return float(max(np.percentile(nonzero, 95), 1.0))


def support_counts(values: np.ndarray) -> SupportCounts:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError(f"Expected 2D (seed, tick) matrix; got {matrix.shape}")
    mask = matrix != 0.0
    per_seed = mask.sum(axis=1)
    return SupportCounts(
        pooled_nonzero_ticks=int(mask.sum()),
        active_seeds=int(np.count_nonzero(per_seed >= 1)),
        clustered_seeds=int(np.count_nonzero(per_seed >= 2)),
    )


def exact_underactivity_pvalue(oc_count: int, karr_count: int) -> float:
    if oc_count < 0 or karr_count < 0:
        raise ValueError("Support counts must be non-negative.")
    total = int(oc_count + karr_count)
    if total == 0:
        return 1.0
    return float(binomtest(k=int(oc_count), n=total, p=0.5, alternative="less").pvalue)


def holm_adjust(pvalues: list[float]) -> list[float]:
    m = len(pvalues)
    order = sorted(range(m), key=lambda idx: pvalues[idx])
    adjusted = [0.0] * m
    running = 0.0
    for rank, original_idx in enumerate(order):
        factor = m - rank
        candidate = factor * pvalues[original_idx]
        running = max(running, candidate)
        adjusted[original_idx] = min(1.0, running)
    return adjusted


def scaled_component_result(
    oc_values: np.ndarray,
    karr_values: np.ndarray,
    *,
    component_name: str,
    scale: float,
) -> dict[str, Any]:
    oc_tensor = np.asarray(oc_values, dtype=np.float64)[:, :, np.newaxis]
    karr_tensor = np.asarray(karr_values, dtype=np.float64)[:, :, np.newaxis]
    payload = per_component_scaled_distance(
        oc_tensor,
        karr_tensor,
        {component_name: float(scale)},
    )
    return {
        "component_name": component_name,
        "scaled_w1": float(payload[component_name]),
        "raw_w1": float(payload["component_raw_w1"][component_name]),
        "scale": float(payload["component_scales"][component_name]),
        "verdict": str(payload["component_verdicts"][component_name]),
        "n_nonzero_oc": int(payload["component_n_nonzero_oc"][component_name]),
        "n_nonzero_karr": int(payload["component_n_nonzero_karr"][component_name]),
        "scaled_distance_threshold": float(payload["scaled_distance_threshold"]),
    }


def zero_side_raw_w1(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return 0.0
    return float(np.abs(arr).sum()) / float(arr.size)


def evaluate_sparse_component(
    oc_values: np.ndarray,
    karr_values: np.ndarray,
    *,
    scale: float,
    config: DNASParseGateConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    oc_support = support_counts(oc_values)
    karr_support = support_counts(karr_values)
    metric = scaled_component_result(
        oc_values,
        karr_values,
        component_name=SPARSE_COMPONENT,
        scale=scale,
    )

    axes = [
        ("pooled_nonzero_ticks", oc_support.pooled_nonzero_ticks, karr_support.pooled_nonzero_ticks, config.min_karr_pooled_nonzero_ticks),
        ("active_seeds", oc_support.active_seeds, karr_support.active_seeds, config.min_karr_active_seeds),
        ("clustered_seeds", oc_support.clustered_seeds, karr_support.clustered_seeds, config.min_karr_clustered_seeds),
    ]

    support_ok = all(karr_count >= floor for _, _, karr_count, floor in axes)
    raw_pvalues = [exact_underactivity_pvalue(oc_count, karr_count) for _, oc_count, karr_count, _ in axes]
    holm_pvalues = holm_adjust(raw_pvalues)
    axis_results: list[dict[str, Any]] = []
    any_reject = False
    alpha = float(config.alpha_family)
    for (name, oc_count, karr_count, floor), raw_pvalue, holm_pvalue in zip(axes, raw_pvalues, holm_pvalues, strict=True):
        rejected = support_ok and holm_pvalue < alpha
        any_reject = any_reject or rejected
        axis_results.append(
            {
                "axis": name,
                "oc_count": int(oc_count),
                "karr_count": int(karr_count),
                "karr_support_floor": int(floor),
                "karr_support_ok": bool(karr_count >= floor),
                "raw_pvalue": float(raw_pvalue),
                "holm_adjusted_pvalue": float(holm_pvalue),
                "rejected_underactivity": bool(rejected),
            }
        )

    if not support_ok:
        verdict = "PRIMARY_INSUFFICIENT_SAMPLES"
    elif any_reject:
        verdict = "PRIMARY_UNDERACTIVE"
    elif metric["verdict"] != "PASS":
        verdict = "FAIL"
    else:
        verdict = "PASS"

    return {
        "component_name": SPARSE_COMPONENT,
        "config": asdict(config),
        "oc_support": oc_support.to_dict(),
        "karr_support": karr_support.to_dict(),
        "support_ok": bool(support_ok),
        "underactivity_axes": axis_results,
        "metric": metric,
        "zero_oc_hypothetical_raw_w1": zero_side_raw_w1(karr_values),
        "verdict": verdict,
    }


def evaluate_process(
    oc_tensor: np.ndarray,
    karr_tensor: np.ndarray,
    component_scales: dict[str, float] | None = None,
    *,
    config: DNASParseGateConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    oc = np.asarray(oc_tensor, dtype=np.float64)
    karr = np.asarray(karr_tensor, dtype=np.float64)
    if oc.shape != karr.shape:
        raise ValueError(f"Tensor shape mismatch: {oc.shape} vs {karr.shape}")
    if oc.ndim != 3 or oc.shape[2] != 2:
        raise ValueError(f"Expected (seed, tick, 2) tensor; got {oc.shape}")

    scales = dict(component_scales or {})
    value_scale = float(scales.get(VALUE_COMPONENT, component_scale_from_values(karr[:, :, 0])))
    sparse_scale = float(scales.get(SPARSE_COMPONENT, component_scale_from_values(karr[:, :, 1])))

    value_metric = scaled_component_result(
        oc[:, :, 0],
        karr[:, :, 0],
        component_name=VALUE_COMPONENT,
        scale=value_scale,
    )
    sparse_component = evaluate_sparse_component(
        oc[:, :, 1],
        karr[:, :, 1],
        scale=sparse_scale,
        config=config,
    )

    if value_metric["verdict"] != "PASS":
        process_verdict = "FAIL"
    else:
        process_verdict = str(sparse_component["verdict"])

    return {
        "process": "DNASupercoiling",
        "primary_channel": "chromosome",
        "primary_projection": [VALUE_COMPONENT, SPARSE_COMPONENT],
        "config": asdict(config),
        "delta_value_sum_metric": value_metric,
        "delta_nnz_sparse_gate": sparse_component,
        "process_verdict": process_verdict,
    }


def sensitivity_evaluations(
    oc_tensor: np.ndarray,
    karr_tensor: np.ndarray,
    component_scales: dict[str, float] | None = None,
) -> dict[str, Any]:
    floor_11 = replace(DEFAULT_CONFIG, min_karr_clustered_seeds=11)
    floor_14 = replace(DEFAULT_CONFIG, min_karr_clustered_seeds=14)
    return {
        "clustered_floor_11": evaluate_process(oc_tensor, karr_tensor, component_scales, config=floor_11),
        "clustered_floor_14": evaluate_process(oc_tensor, karr_tensor, component_scales, config=floor_14),
    }


def guarantee_examples() -> dict[str, float]:
    return {
        "pooled_or_active_half_vs_31_raw_pvalue": exact_underactivity_pvalue(15, 31),
        "clustered_zero_vs_6_raw_pvalue": exact_underactivity_pvalue(0, 6),
        "clustered_two_vs_11_raw_pvalue": exact_underactivity_pvalue(2, 11),
        "clustered_four_vs_14_raw_pvalue": exact_underactivity_pvalue(4, 14),
        "holm_alpha_per_test_upper_bound": DEFAULT_CONFIG.alpha_family / 3.0,
    }


__all__ = [
    "DEFAULT_CONFIG",
    "DNASParseGateConfig",
    "SPARSE_COMPONENT",
    "VALUE_COMPONENT",
    "component_scale_from_values",
    "evaluate_process",
    "evaluate_sparse_component",
    "exact_underactivity_pvalue",
    "guarantee_examples",
    "holm_adjust",
    "sensitivity_evaluations",
    "support_counts",
    "zero_side_raw_w1",
]
