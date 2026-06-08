from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TESTS_DIR = _REPO_ROOT / "tests" / "vivarium"
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from _l2_2_design_a_projections import (  # noqa: E402
    hurdle_event_rate_plus_conditional_distance,
    per_component_scaled_distance,
)


def _default_scale(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    nonzero = np.abs(arr[np.abs(arr) > 1e-12])
    if nonzero.size == 0:
        return 1.0
    return float(max(np.percentile(nonzero, 95), 1.0))


def main() -> int:
    rng = np.random.default_rng(20260608)

    per_component_entry = {
        "name": "SyntheticProjectionProcess",
        "primary_distance": "per_component_scaled",
        "primary_projection": [
            "delta_fork_position_bp.left",
            "repair_count_by_pathway.ber_delta",
            "repair_count_by_pathway.ner_delta",
        ],
    }
    karr_per_component = rng.normal(
        loc=np.asarray([12.0, 3.0, 1.0]),
        scale=np.asarray([1.5, 0.5, 0.25]),
        size=(20, 10, 3),
    )
    oc_per_component = karr_per_component.copy()
    oc_per_component[:, :, 0] += 4.0
    oc_per_component[:, :, 1] *= 1.2
    oc_per_component[:, :, 2] += 0.1
    component_scales = {
        component: _default_scale(karr_per_component[:, :, idx])
        for idx, component in enumerate(per_component_entry["primary_projection"])
    }
    per_component_payload = per_component_scaled_distance(
        oc_per_component,
        karr_per_component,
        component_scales,
    )
    assert set(per_component_payload["component_verdicts"]) == set(per_component_entry["primary_projection"])

    hurdle_entry = {
        "name": "SyntheticRepairHurdle",
        "primary_distance": "hurdle_event_rate_plus_conditional_scaled_distance",
        "primary_projection": [
            "repair_event_present",
            "repair_count_by_pathway.ber_delta",
            "repair_count_by_pathway.ner_delta",
            "repair_count_by_pathway.hr_delta",
            "repair_count_by_pathway.nhej_like_delta",
        ],
    }
    oc_hurdle = np.zeros((20, 10, 5), dtype=np.float64)
    karr_hurdle = np.zeros((20, 10, 5), dtype=np.float64)
    oc_event_mask = rng.random((20, 10)) < 0.35
    karr_event_mask = rng.random((20, 10)) < 0.30
    oc_hurdle[:, :, 0] = oc_event_mask.astype(np.float64)
    karr_hurdle[:, :, 0] = karr_event_mask.astype(np.float64)
    for idx, scale in enumerate((4.0, 2.5, 1.5, 1.0), start=1):
        oc_hurdle[:, :, idx] = oc_event_mask * rng.gamma(shape=2.0 + idx, scale=scale, size=(20, 10))
        karr_hurdle[:, :, idx] = karr_event_mask * rng.gamma(shape=1.5 + idx, scale=scale * 0.9, size=(20, 10))
    hurdle_payload = hurdle_event_rate_plus_conditional_distance(oc_hurdle, karr_hurdle)
    assert set(hurdle_payload["conditional_w1_per_component"]) == {
        "component_1",
        "component_2",
        "component_3",
        "component_4",
    }

    print(
        "per_component",
        f"joint_verdict={per_component_payload['joint_verdict']}",
        f"components={len(per_component_payload['component_verdicts'])}",
    )
    print(
        "hurdle",
        f"joint_verdict={hurdle_payload['joint_verdict']}",
        f"event_rate_diff={hurdle_payload['event_rate_diff']:.6f}",
        f"conditionals={len(hurdle_payload['conditional_w1_per_component'])}",
    )
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
