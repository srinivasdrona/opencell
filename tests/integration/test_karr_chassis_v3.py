"""Integration coverage for the A3.3 v3 chassis + ratchet closure."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.karr_composite import (
    build_karr_chassis_v2,
    build_karr_chassis_v3,
)


@pytest.fixture(scope="module")
def m1_model() -> km.KarrMetabolismModel:
    return km.load_default()


@pytest.fixture(scope="module")
def m2_model() -> tx.KarrTranscriptionModel:
    return tx.load_default()


@pytest.fixture(scope="module")
def m3_model() -> tl.KarrTranslationModel:
    return tl.load_default()


def _assert_branch_accumulate(schema_branch: dict[str, Any]) -> None:
    for key, value in schema_branch.items():
        if key == "_updater":
            assert value == "accumulate"
            continue
        if isinstance(value, dict):
            _assert_branch_accumulate(value)


def _top_complex_wids(state: dict[str, Any], n: int = 10) -> list[str]:
    counts = state.get("complex", {}).get("counts", {})
    if not counts:
        return []
    ranked = sorted(
        counts.items(),
        key=lambda item: float(item[1]),
        reverse=True,
    )
    return [wid for wid, _ in ranked[:n]]


def test_chassis_v3_builds(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_chassis_v3(
        m1_model,
        m2_model,
        m3_model,
        time_step_s=1.0,
        emit_step_s=1.0,
    )
    assert engine is not None
    assert "karr_metabolism" in engine.processes
    assert "karr_transcription_v3" in engine.processes
    assert "karr_translation_v3" in engine.processes
    assert "karr_macromolecular_complexation" in engine.processes
    assert "karr_protein_decay_light" in engine.processes
    assert "request_calculator_d2" in engine.steps
    assert "request_calculator_pd" in engine.steps
    assert "karr_allocation_step" in engine.steps


def test_chassis_v3_10_ticks(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_chassis_v3(
        m1_model,
        m2_model,
        m3_model,
        time_step_s=1.0,
        emit_step_s=1.0,
    )
    engine.update(10.0)
    state = engine.state.get_value()

    complex_counts = state.get("complex", {}).get("counts", {})
    assert complex_counts
    assert any(float(cnt) > 0.0 for cnt in complex_counts.values())
    for wid, cnt in complex_counts.items():
        assert float(cnt) >= 0.0, f"negative complex count for {wid}: {cnt}"
    assert np.isfinite(sum(float(v) for v in complex_counts.values()))


def test_chassis_v3_ratchet_closure_steady_state(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    """1000-tick closed loop: D.2-real assembles, PD-light degrades.

    Steady state criterion:
      - for top-10 initial complexes, mean in ticks 700-1000 stays within
        25% of mean in ticks 400-700.
    """
    engine = build_karr_chassis_v3(
        m1_model,
        m2_model,
        m3_model,
        time_step_s=1.0,
        emit_step_s=10.0,
    )
    state0 = engine.state.get_value()
    top10 = _top_complex_wids(state0, n=10)
    if len(top10) < 10:
        candidates = list(engine.processes["karr_macromolecular_complexation"].complex_wids)
        top10 = (top10 + [wid for wid in candidates if wid not in top10])[:10]
    assert len(top10) == 10

    trajectories = {wid: [] for wid in top10}
    for _ in range(100):
        engine.update(10.0)
        state = engine.state.get_value()
        complex_counts = state.get("complex", {}).get("counts", {})
        for wid in trajectories:
            trajectories[wid].append(float(complex_counts.get(wid, 0.0)))

    assert any(max(traj) > 0.0 for traj in trajectories.values())
    for wid, traj in trajectories.items():
        mid_mean = float(np.mean(traj[40:70]))
        late_mean = float(np.mean(traj[70:100]))
        drift = abs(late_mean - mid_mean) / max(1.0, mid_mean)
        assert drift < 0.25, (
            f"Complex {wid} not at steady state: "
            f"mid={mid_mean:.3f}, late={late_mean:.3f}, drift={drift:.2%}"
        )


def test_v2_chassis_still_works() -> None:
    engine = build_karr_chassis_v2(time_step_s=1.0, emit_step_s=1.0)
    engine.update(10.0)
    state = engine.state.get_value()

    assert len(state["rna"]["counts"]) == 525
    assert len(state["protein"]["counts"]) == 482
    assert np.isfinite(sum(float(v) for v in state["rna"]["counts"].values()))
    assert np.isfinite(sum(float(v) for v in state["protein"]["counts"].values()))
    assert np.isfinite(sum(float(v) for v in state["complex"]["counts"].values()))


def test_chassis_v3_all_writers_accumulate(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_chassis_v3(
        m1_model,
        m2_model,
        m3_model,
        time_step_s=1.0,
        emit_step_s=1.0,
    )

    p_m1 = engine.processes["karr_metabolism"].ports_schema()
    p_m2 = engine.processes["karr_transcription_v3"].ports_schema()
    p_m3 = engine.processes["karr_translation_v3"].ports_schema()
    p_d2 = engine.processes["karr_macromolecular_complexation"].ports_schema()
    p_pd = engine.processes["karr_protein_decay_light"].ports_schema()

    _assert_branch_accumulate(p_m1["substrates"])
    _assert_branch_accumulate(p_m2["rna"]["counts"])
    _assert_branch_accumulate(p_m2["substrates"])
    _assert_branch_accumulate(p_m3["protein"]["unprocessed_counts"])
    _assert_branch_accumulate(p_m3["substrates"])
    _assert_branch_accumulate(p_d2["complex"]["counts"])
    _assert_branch_accumulate(p_d2["substrates"])
    _assert_branch_accumulate(p_pd["complex"]["counts"])
    _assert_branch_accumulate(p_pd["protein"]["counts"])
    _assert_branch_accumulate(p_pd["rna"]["counts"])
    _assert_branch_accumulate(p_pd["substrates"])

    step_req_d2 = engine.steps["request_calculator_d2"].ports_schema()
    step_req_pd = engine.steps["request_calculator_pd"].ports_schema()
    step_alloc = engine.steps["karr_allocation_step"].ports_schema()

    any_d2_leaf = next(iter(step_req_d2["requests"]["karr_macromolecular_complexation"].values()))
    assert any_d2_leaf["_updater"] == "set"
    assert step_req_pd["requests"]["karr_protein_decay_light"]["ATP"]["_updater"] == "set"
    assert step_req_pd["requests"]["karr_protein_decay_light"]["H2O"]["_updater"] == "set"
    any_alloc_req_leaf = next(iter(step_alloc["requests"]["karr_macromolecular_complexation"].values()))
    assert any_alloc_req_leaf["_updater"] == "set"
    any_alloc_out_leaf = next(
        iter(step_alloc["substrates_allocated"]["karr_protein_decay_light"].values())
    )
    assert any_alloc_out_leaf["_updater"] == "set"


def test_allocation_step_constrains_under_scarcity(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_chassis_v3(
        m1_model,
        m2_model,
        m3_model,
        time_step_s=1.0,
        emit_step_s=1.0,
    )
    allocation = engine.steps["karr_allocation_step"]
    update = allocation.next_update(
        1.0,
        {
            "substrates": {"ATP": 5.0, "H2O": 4.0},
            "requests": {
                "karr_macromolecular_complexation": {"ATP": 40.0, "H2O": 20.0},
                "karr_protein_decay_light": {"ATP": 60.0, "H2O": 30.0},
            },
            "substrates_allocated": {
                "karr_macromolecular_complexation": {"ATP": 0.0, "H2O": 0.0},
                "karr_protein_decay_light": {"ATP": 0.0, "H2O": 0.0},
            },
        },
    )
    allocated = update["substrates_allocated"]
    assert allocated["karr_macromolecular_complexation"]["ATP"] == 2.0
    assert allocated["karr_protein_decay_light"]["ATP"] == 3.0
    assert allocated["karr_macromolecular_complexation"]["H2O"] == 1.0
    assert allocated["karr_protein_decay_light"]["H2O"] == 2.0


def test_d2_and_decay_both_active(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_chassis_v3(
        m1_model,
        m2_model,
        m3_model,
        time_step_s=1.0,
        emit_step_s=1.0,
    )
    d2_proc = engine.processes["karr_macromolecular_complexation"]
    pd_proc = engine.processes["karr_protein_decay_light"]

    for wid in d2_proc.substrate_wids:
        engine.state.set_path(("substrates", wid), 5_000.0)
    for wid in pd_proc.complex_wids[:12]:
        engine.state.set_path(("complex", "counts", wid), 100_000.0)

    flags = {"d2_positive": False, "pd_negative": False}
    orig_d2_next = d2_proc.next_update
    orig_pd_next = pd_proc.next_update

    def wrapped_d2_next(timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        update = orig_d2_next(timestep, states)
        if any(v > 0.0 for v in update.get("complex", {}).get("counts", {}).values()):
            flags["d2_positive"] = True
        return update

    def wrapped_pd_next(timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        update = orig_pd_next(timestep, states)
        if any(v < 0.0 for v in update.get("complex", {}).get("counts", {}).values()):
            flags["pd_negative"] = True
        return update

    d2_proc.next_update = wrapped_d2_next
    pd_proc.next_update = wrapped_pd_next
    try:
        engine.update(100.0)
    finally:
        d2_proc.next_update = orig_d2_next
        pd_proc.next_update = orig_pd_next

    assert flags["d2_positive"], "D.2-real never emitted positive complex deltas"
    assert flags["pd_negative"], "ProteinDecay-light never emitted negative complex deltas"


def test_emit_step_records_complex_trajectories(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_chassis_v3(
        m1_model,
        m2_model,
        m3_model,
        time_step_s=1.0,
        emit_step_s=2.0,
    )
    engine.update(10.0)
    ts = engine.emitter.get_timeseries()

    assert "complex" in ts
    assert "counts" in ts["complex"]
    assert len(ts["complex"]["counts"]) > 0
    wid = engine.processes["karr_macromolecular_complexation"].complex_wids[0]
    assert wid in ts["complex"]["counts"]
    series = np.asarray(ts["complex"]["counts"][wid], dtype=float)
    assert len(series) == len(ts["time"])
    assert len(series) == 6
    assert np.all(np.isfinite(series))

