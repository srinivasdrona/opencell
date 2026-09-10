"""Pre-registered TWO-SIDED sparse-event gate for DNASupercoiling `delta_nnz`.

`sparse_gate.py` (shared Design-A catalog helper, not touched by this module)
implements a ONE-SIDED underactivity-only guard: its
`exact_underactivity_pvalue` calls
`scipy.stats.binomtest(..., alternative="less")`, which can only ever reject
OC being *less* active than Karr. It structurally cannot reject OC being
*more* active than Karr no matter how extreme the overactivity is. That one-
sided rule was exercised in STATUS_L22_DNAS_FOLLOWUP8.md and returned
`PASS` on a frozen `N=200` rerun where OC was pooled/active/clustered
`1486/200/200` against Karr's `65/58/7` -- i.e. an ~23x pooled overactivity
that a support-count PASS papered over. That PASS is REJECTED as not
statistically credible and is not reused here (see PROMPT_SEPT2.md).

This module defines a new, independent, DNAS-only two-sided rule that
rejects BOTH directions of sparse-support mismatch:

  H0 (per axis): OC and Karr are equally likely to contribute to the pooled
    support total for that axis (each observed "hit" is OC's with
    probability p=0.5).
  H1 (two-sided): OC's share of the pooled total differs from 0.5 in either
    direction -- i.e. OC is either underactive (its share << 0.5, support
    count far below Karr's) or overactive (its share >> 0.5, support count
    far above Karr's).

Test statistic: exact two-sided binomial test,
`binomtest(k=oc_count, n=oc_count + karr_count, p=0.5, alternative="two-sided")`,
one test per axis (`pooled_nonzero_ticks`, `active_seeds`, `clustered_seeds`),
Holm-Bonferroni corrected across the 3 axes at family alpha=0.05 (same alpha
and correction procedure as the one-sided rule, for comparability -- only the
test's `alternative` and the resulting PASS/FAIL semantics differ).

A rejected axis is additionally labeled by direction
(`oc_count > karr_count` => `OVERACTIVE`, `oc_count < karr_count` =>
`UNDERACTIVE`) so a reviewer can see which failure mode fired.

Unlike the one-sided rule's Karr-support floor (which exists only to keep an
underactivity-only claim meaningful), this two-sided rule does not require a
minimum Karr count: a Karr count of zero against a large OC count is itself
the single clearest possible overactivity signal, and the exact two-sided
binomial test already accounts for its own power at any n > 0. The rule only
declines to test (returns `PRIMARY_INSUFFICIENT_SAMPLES`) when the pooled
total (oc_count + karr_count) is exactly zero, i.e. there is no information
to test.

The dense `delta_value_sum` component keeps using the shared
`per_component_scaled_distance` magnitude metric unchanged (imported, not
edited) via `scaled_component_result` -- that metric is already a symmetric
distance and was never the source of the one-sided flaw.

This file is new and DNAS-scoped. It imports read-only utilities from the
shared `sparse_gate` module (`support_counts`, `holm_adjust`,
`scaled_component_result`, `component_scale_from_values`) but does not modify
that module, the shared `_l2_2_design_a_projections` catalog helper, or any
process/index files.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import binomtest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_dnas_rare_event.sparse_gate import (  # noqa: E402
    SPARSE_COMPONENT,
    VALUE_COMPONENT,
    component_scale_from_values,
    holm_adjust,
    scaled_component_result,
    support_counts,
)

__all__ = [
    "DEFAULT_CONFIG",
    "SPARSE_COMPONENT",
    "VALUE_COMPONENT",
    "TwoSidedSparseGateConfig",
    "evaluate_process",
    "evaluate_sparse_component",
    "exact_two_sided_pvalue",
    "preregistration_examples",
]


@dataclass(frozen=True)
class TwoSidedSparseGateConfig:
    """Frozen configuration for the two-sided rule.

    `alpha_family` and the three axes mirror the one-sided rule's config for
    direct comparability; there is deliberately no `min_karr_*` floor because
    the two-sided test needs no minimum Karr support to detect overactivity.
    """

    alpha_family: float = 0.05


DEFAULT_CONFIG = TwoSidedSparseGateConfig()

AXIS_NAMES: tuple[str, ...] = ("pooled_nonzero_ticks", "active_seeds", "clustered_seeds")


def exact_two_sided_pvalue(oc_count: int, karr_count: int) -> float:
    """Exact two-sided binomial test of OC's share of pooled support.

    H0: P(a pooled hit is OC's) = 0.5. Rejects when OC's count is either far
    below Karr's (underactivity) or far above Karr's (overactivity).
    """
    if oc_count < 0 or karr_count < 0:
        raise ValueError("Support counts must be non-negative.")
    total = int(oc_count + karr_count)
    if total == 0:
        return 1.0
    return float(binomtest(k=int(oc_count), n=total, p=0.5, alternative="two-sided").pvalue)


def _direction(oc_count: int, karr_count: int) -> str:
    if oc_count > karr_count:
        return "OVERACTIVE"
    if oc_count < karr_count:
        return "UNDERACTIVE"
    return "BALANCED"


def evaluate_sparse_component(
    oc_values: np.ndarray,
    karr_values: np.ndarray,
    *,
    scale: float,
    config: TwoSidedSparseGateConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    oc_support = support_counts(oc_values)
    karr_support = support_counts(karr_values)
    metric = scaled_component_result(
        oc_values,
        karr_values,
        component_name=SPARSE_COMPONENT,
        scale=scale,
    )

    axis_counts = [
        (name, getattr(oc_support, name), getattr(karr_support, name))
        for name in AXIS_NAMES
    ]

    totals_present = [oc_count + karr_count for _, oc_count, karr_count in axis_counts]
    support_ok = all(total > 0 for total in totals_present)

    raw_pvalues = [exact_two_sided_pvalue(oc_count, karr_count) for _, oc_count, karr_count in axis_counts]
    holm_pvalues = holm_adjust(raw_pvalues)
    alpha = float(config.alpha_family)

    axis_results: list[dict[str, Any]] = []
    any_reject_overactive = False
    any_reject_underactive = False
    for (name, oc_count, karr_count), total, raw_pvalue, holm_pvalue in zip(
        axis_counts, totals_present, raw_pvalues, holm_pvalues, strict=True
    ):
        testable = total > 0
        rejected = testable and holm_pvalue < alpha
        direction = _direction(oc_count, karr_count) if rejected else "BALANCED"
        if rejected and direction == "OVERACTIVE":
            any_reject_overactive = True
        if rejected and direction == "UNDERACTIVE":
            any_reject_underactive = True
        axis_results.append(
            {
                "axis": name,
                "oc_count": int(oc_count),
                "karr_count": int(karr_count),
                "pooled_total": int(total),
                "testable": bool(testable),
                "raw_pvalue": float(raw_pvalue),
                "holm_adjusted_pvalue": float(holm_pvalue),
                "rejected": bool(rejected),
                "direction": direction,
            }
        )

    if not support_ok:
        verdict = "PRIMARY_INSUFFICIENT_SAMPLES"
    elif any_reject_overactive and any_reject_underactive:
        verdict = "PRIMARY_MIXED_UNDER_AND_OVERACTIVE"
    elif any_reject_overactive:
        verdict = "PRIMARY_OVERACTIVE"
    elif any_reject_underactive:
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
        "axes": axis_results,
        "metric": metric,
        "verdict": verdict,
    }


def evaluate_process(
    oc_tensor: np.ndarray,
    karr_tensor: np.ndarray,
    component_scales: dict[str, float] | None = None,
    *,
    config: TwoSidedSparseGateConfig = DEFAULT_CONFIG,
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
        "rule": "two_sided_sparse_gate",
        "config": asdict(config),
        "delta_value_sum_metric": value_metric,
        "delta_nnz_sparse_gate": sparse_component,
        "process_verdict": process_verdict,
    }


def preregistration_examples() -> dict[str, float]:
    """Frozen worked examples committed as part of the preregistration.

    These are the exact FOLLOWUP8 frozen support counts
    (pooled/active/clustered OC=1486/200/200 vs Karr=65/58/7) fed through
    `exact_two_sided_pvalue`, to demonstrate -- BEFORE the N=200 rerun in this
    task -- that this rule would have rejected that prior one-sided PASS.
    """
    return {
        "followup8_pooled_1486_vs_65_two_sided_pvalue": exact_two_sided_pvalue(1486, 65),
        "followup8_active_200_vs_58_two_sided_pvalue": exact_two_sided_pvalue(200, 58),
        "followup8_clustered_200_vs_7_two_sided_pvalue": exact_two_sided_pvalue(200, 7),
        "holm_alpha_per_test_upper_bound": DEFAULT_CONFIG.alpha_family / 3.0,
    }
