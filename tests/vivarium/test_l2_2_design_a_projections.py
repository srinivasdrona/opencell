from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from _l2_2_design_a_projections import (  # noqa: E402
    extract_projection,
    hurdle_event_rate_plus_conditional_distance,
    per_component_scaled_distance,
)


def _tick_payload() -> dict[str, object]:
    return {
        "before": {
            "chromosome": {
                "fork_position_bp": {"left": 25.0, "right": 30.0},
                "replication_state": "initiating",
                "events": {"replication_complete": 0.0},
                "repair_events_cumulative": [{"id": "repair-0"}],
                "repair_count_by_pathway": {"ber": 1.0, "ner": 0.0},
            }
        },
        "after": {
            "chromosome": {
                "fork_position_bp": {"left": 40.0, "right": 45.0},
                "replication_state": "elongating",
                "events": {"replication_complete": 1.0},
                "repair_events_cumulative": [{"id": "repair-0"}, {"id": "repair-1"}],
                "repair_count_by_pathway": {"ber": 3.0, "ner": 0.0},
            }
        },
    }


def test_extract_projection_resolves_dotted_paths_and_derived_components() -> None:
    projection = extract_projection(
        _tick_payload(),
        [
            "delta_fork_position_bp.left",
            "replication_state",
            "replication_complete_fired_this_tick",
            "repair_event_present",
            "repair_count_by_pathway.ber_delta",
        ],
    )

    assert projection.shape == (5,)
    assert np.array_equal(projection, np.asarray([15.0, 2.0, 1.0, 1.0, 2.0], dtype=np.float64))


def test_extract_projection_raises_clear_error_for_missing_path() -> None:
    with pytest.raises(KeyError, match="missing.branch"):
        extract_projection(_tick_payload(), ["missing.branch"])


def test_per_component_scaled_distance_reports_component_scores_and_joint_verdict() -> None:
    oc = np.zeros((2, 2, 2), dtype=np.float64)
    karr = np.zeros((2, 2, 2), dtype=np.float64)
    karr[:, :, 0] = 10.0
    karr[:, :, 1] = 2.0

    payload = per_component_scaled_distance(
        oc,
        karr,
        {
            "fork_progress": 5.0,
            "repair_count": 4.0,
        },
    )

    assert payload["fork_progress"] == pytest.approx(2.0)
    assert payload["repair_count"] == pytest.approx(0.5)
    assert payload["component_raw_w1"]["fork_progress"] == pytest.approx(10.0)
    assert payload["component_verdicts"]["fork_progress"] == "FAIL"
    assert payload["component_verdicts"]["repair_count"] == "PASS"
    assert payload["joint_verdict"] == "FAIL"


def test_hurdle_distance_handles_all_zero_event_surface() -> None:
    oc = np.zeros((2, 3, 5), dtype=np.float64)
    karr = np.zeros((2, 3, 5), dtype=np.float64)

    payload = hurdle_event_rate_plus_conditional_distance(oc, karr)

    assert payload["event_rate_diff"] == pytest.approx(0.0)
    assert payload["conditional_w1_per_component"] == {
        "component_1": 0.0,
        "component_2": 0.0,
        "component_3": 0.0,
        "component_4": 0.0,
    }
    assert payload["joint_verdict"] == "PASS"


def test_hurdle_distance_uses_nonzero_subsets_for_conditionals() -> None:
    oc = np.zeros((1, 4, 3), dtype=np.float64)
    karr = np.zeros((1, 4, 3), dtype=np.float64)

    oc[0, :, 0] = np.asarray([1.0, 0.0, 1.0, 0.0])
    karr[0, :, 0] = np.asarray([1.0, 1.0, 0.0, 0.0])
    oc[0, :, 1] = np.asarray([10.0, 0.0, 6.0, 0.0])
    karr[0, :, 1] = np.asarray([4.0, 8.0, 0.0, 0.0])
    oc[0, :, 2] = np.asarray([3.0, 0.0, 5.0, 0.0])
    karr[0, :, 2] = np.asarray([3.0, 3.0, 0.0, 0.0])

    payload = hurdle_event_rate_plus_conditional_distance(oc, karr)

    assert payload["event_rate_diff"] == pytest.approx(0.0)
    assert payload["conditional_w1_per_component"]["component_1"] == pytest.approx(2.0)
    assert payload["conditional_w1_per_component"]["component_2"] == pytest.approx(1.0)
    assert payload["conditional_scaled_w1_per_component"]["component_1"] > 0.0
    assert set(payload["component_verdicts"]) == {"component_1", "component_2"}
