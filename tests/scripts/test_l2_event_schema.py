"""Unit tests for `scripts/l2_event/schema.py` (requirement 6: normalized
event-record invariants + JSON round-tripping for the versioned schema)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.schema import (
    EventObservation,
    EventTimeline,
    GateChannelResult,
    ResultDoc,
    read_json,
    write_json_atomic,
)


def test_event_observation_fired_requires_fire_count_and_timing_tick():
    with pytest.raises(ValueError):
        EventObservation(tick=0, fired=True, fire_count=0, timing_tick=None)
    with pytest.raises(ValueError):
        EventObservation(tick=0, fired=True, fire_count=1, timing_tick=None)


def test_event_observation_not_fired_requires_zero_count_and_no_timing_tick():
    with pytest.raises(ValueError):
        EventObservation(tick=0, fired=False, fire_count=1, timing_tick=None)
    with pytest.raises(ValueError):
        EventObservation(tick=0, fired=False, fire_count=0, timing_tick=3)


def test_event_observation_negative_fire_count_rejected():
    with pytest.raises(ValueError):
        EventObservation(tick=0, fired=False, fire_count=-1, timing_tick=None)


def test_event_observation_valid_construction_roundtrips_to_json():
    obs = EventObservation(tick=5, fired=True, fire_count=2, timing_tick=5, payload={"x": 1.0})
    payload = obs.to_json()
    assert payload["tick"] == 5
    assert payload["fire_count"] == 2
    assert payload["payload"] == {"x": 1.0}


def test_event_timeline_total_fire_count_and_fire_ticks_bag_semantics():
    obs = (
        EventObservation(tick=0, fired=False, fire_count=0, timing_tick=None),
        EventObservation(tick=1, fired=True, fire_count=2, timing_tick=1),
        EventObservation(tick=2, fired=False, fire_count=0, timing_tick=None),
        EventObservation(tick=3, fired=True, fire_count=1, timing_tick=3),
    )
    timeline = EventTimeline(process="Test", seed=0, observations=obs)
    assert timeline.n_ticks == 4
    assert timeline.total_fire_count == 3
    # fire_ticks is a *bag*: tick 1 fired twice, so it appears twice.
    assert timeline.fire_ticks == (1, 1, 3)


def test_write_json_atomic_and_read_json_roundtrip(tmp_path):
    path = tmp_path / "nested" / "doc.json"
    payload = {"a": 1, "b": [1, 2, 3], "c": {"d": "e"}}
    write_json_atomic(path, payload)
    assert path.exists()
    # No leftover .tmp file after a successful atomic write.
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    assert read_json(path) == payload


def test_result_doc_to_json_serializes_nested_gate_channel_results():
    channel = GateChannelResult(
        channel="count",
        verdict="PASS",
        statistic_name="w1_per_seed_count",
        statistic_value=0.1,
        q95_null=0.2,
        k_eng=3.0,
        threshold=0.6,
        n_nonzero_oc=5,
        n_nonzero_karr=5,
    )
    result = ResultDoc(
        schema_version=1,
        process="Test",
        adapter_id="test.adapter.v1",
        event_timing_model="repeated_firing",
        mode="gate",
        verdict="PASS",
        channels=[channel],
        oc_only_fire_ticks={},
        n_seeds_karr=5,
        n_seeds_oc=5,
    )
    payload = result.to_json()
    assert payload["channels"][0]["verdict"] == "PASS"
    assert isinstance(payload["channels"][0], dict)
