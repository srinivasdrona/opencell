from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from vivarium.core.engine import Engine

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.m2 import transcription as tx
from opencell.m2 import transcription_v2 as tx_v2
from opencell.vivarium.karr_composite import build_karr_chassis_v6
from opencell.vivarium import karr_transcriptional_regulation as tx_reg_module
from opencell.vivarium.karr_transcription_v2 import KarrTranscriptionV2Process
from opencell.vivarium.karr_transcription_v3 import KarrTranscriptionV3Process
from opencell.vivarium.karr_transcriptional_regulation import (
    KarrTranscriptionalRegulationProcess,
)

_FLOAT_TOL = 1e-12


def _empty_tr_state(process: KarrTranscriptionalRegulationProcess) -> dict[str, Any]:
    return {
        "protein": {"counts": {tf: 0.0 for tf in process.tf_wids}},
        "complex": {"counts": {tf: 0.0 for tf in process.tf_wids}},
        "tf_binding": {tf: {tu: 0.0 for tu in process.tu_wids} for tf in process.tf_wids},
    }


def _tf_store(process: KarrTranscriptionalRegulationProcess, tf_wid: str) -> str:
    tf_wid_source = getattr(process, "_tf_wid_source", {})
    if isinstance(tf_wid_source, dict):
        return str(tf_wid_source.get(tf_wid, "protein"))
    return "protein"


def _set_tf_count(
    process: KarrTranscriptionalRegulationProcess,
    state: dict[str, Any],
    tf_wid: str,
    count: float,
) -> None:
    store = _tf_store(process, tf_wid)
    state[store]["counts"][tf_wid] = float(count)


def _regulated_tus_for_tf(
    process: KarrTranscriptionalRegulationProcess,
    tf_wid: str,
) -> list[str]:
    tf_i = process.tf_wids.index(tf_wid)
    mask = (
        (process.tf_promoter_affinity[tf_i] > 0.0)
        | (np.abs(process.tf_tu_fold_change[tf_i] - 1.0) > _FLOAT_TOL)
        | (np.abs(process.tf_other_activities[tf_i] - 1.0) > _FLOAT_TOL)
    )
    return [process.tu_wids[idx] for idx in np.flatnonzero(mask).tolist()]


def _apply_tf_binding_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    for tf_wid, per_tu in update.get("tf_binding", {}).items():
        for tu_wid, delta in per_tu.items():
            state["tf_binding"][tf_wid][tu_wid] = float(
                state["tf_binding"][tf_wid].get(tu_wid, 0.0) + float(delta)
            )


def _make_toy_process(
    tf_wids: list[str],
    tu_wids: list[str],
    affinity: np.ndarray,
    fold_change: np.ndarray,
    other_activities: np.ndarray | None = None,
    tf_wid_source: dict[str, str] | None = None,
    seed: int = 0,
) -> KarrTranscriptionalRegulationProcess:
    p = KarrTranscriptionalRegulationProcess({"rng_seed": seed})
    p.tf_wids = tf_wids
    p.tu_wids = tu_wids
    p.tf_promoter_affinity = np.asarray(affinity, dtype=np.float64)
    p.tf_tu_fold_change = np.asarray(fold_change, dtype=np.float64)
    if other_activities is None:
        p.tf_other_activities = np.ones_like(p.tf_tu_fold_change, dtype=np.float64)
    else:
        p.tf_other_activities = np.asarray(other_activities, dtype=np.float64)
    p.n_relationships = int(np.count_nonzero(p.tf_promoter_affinity > 0.0))
    p._n_tf = len(tf_wids)
    p._n_tu = len(tu_wids)
    p._rng = np.random.default_rng(seed)
    if tf_wid_source is None:
        tf_wid_source = {tf_wid: "protein" for tf_wid in tf_wids}
    p._tf_wid_source = {tf_wid: str(tf_wid_source.get(tf_wid, "protein")) for tf_wid in tf_wids}
    p._tf_is_complex = np.asarray(
        [p._tf_wid_source[tf_wid] == "complex" for tf_wid in tf_wids], dtype=bool
    )
    p._protein_tf_wids = [tf_wid for tf_wid in tf_wids if p._tf_wid_source[tf_wid] == "protein"]
    p._complex_tf_wids = [tf_wid for tf_wid in tf_wids if p._tf_wid_source[tf_wid] == "complex"]
    return p


def _make_m2_state(
    process: KarrTranscriptionV2Process,
    n_active_rnap: float | None = None,
) -> dict[str, Any]:
    active = (
        float(process.mechanism_inputs.n_active_rnap)
        if n_active_rnap is None
        else float(n_active_rnap)
    )
    return {
        "rna": {
            "counts": {
                gid: float(process.kinetics_model.counts_mature[i, 1])
                for i, gid in enumerate(process.gene_ids)
            }
        },
        "complex": {"counts": {"RNA_POLYMERASE": active}},
    }


def _mock_dense_fixture_mat(
    *,
    tf_wids: list[str],
    tu_wids: list[str],
    affinity: np.ndarray,
    fold_change: np.ndarray,
    other_activities: np.ndarray,
) -> dict[str, Any]:
    fx_dtype = np.dtype(
        [
            ("transcriptionFactorWholeCellModelIDs", object),
            ("transcriptionUnitWholeCellModelIDs", object),
            ("tfPromoterAffinityMatrix", object),
            ("tfTuFoldChangeMatrix", object),
            ("otherActivities", object),
        ]
    )
    fx = np.zeros((1, 1), dtype=fx_dtype)
    fx["transcriptionFactorWholeCellModelIDs"][0, 0] = np.asarray(tf_wids, dtype=object)
    fx["transcriptionUnitWholeCellModelIDs"][0, 0] = np.asarray(tu_wids, dtype=object)
    fx["tfPromoterAffinityMatrix"][0, 0] = np.asarray(affinity, dtype=np.float64)
    fx["tfTuFoldChangeMatrix"][0, 0] = np.asarray(fold_change, dtype=np.float64)
    fx["otherActivities"][0, 0] = np.asarray(other_activities, dtype=np.float64)

    data = np.zeros((1, 1), dtype=[("fixture", object)])
    data["fixture"][0, 0] = fx
    return {"data": data}


def test_fixture_loads() -> None:
    p = KarrTranscriptionalRegulationProcess({})
    assert p.name == "karr_transcriptional_regulation"
    assert len(p.tf_wids) == 5
    assert len(p.tu_wids) > 0
    assert p.tf_promoter_affinity.shape == (len(p.tf_wids), len(p.tu_wids))
    assert p.tf_tu_fold_change.shape == (len(p.tf_wids), len(p.tu_wids))
    assert p.tf_other_activities.shape == (len(p.tf_wids), len(p.tu_wids))
    assert p.n_relationships > 0


def test_v6_chassis_seed_path_drives_mg205_fold_change() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    tx_reg = composite["processes"]["karr_transcriptional_regulation"]
    tx_reg_topology = composite["topology"]["karr_transcriptional_regulation"]
    assert tx_reg_topology["complex"] == ("complex",)

    assert _tf_store(tx_reg, "MG_205_DIMER") == "complex"
    complex_counts = composite["state"]["complex"]["counts"]
    assert float(complex_counts["MG_205_DIMER"]) != pytest.approx(0.0)

    target_tus = _regulated_tus_for_tf(tx_reg, "MG_205_DIMER")
    assert target_tus

    engine = Engine(composite=composite, emit_step=1.0, display_info=False)
    engine.update(1.0)
    state = engine.state.get_value()
    fold_change = state["tx_rate_fold_change"]
    assert any(abs(float(fold_change[tu_wid]) - 1.0) > _FLOAT_TOL for tu_wid in target_tus)


def test_loader_rejects_binding_other_activities_overlap(monkeypatch: pytest.MonkeyPatch) -> None:
    mocked = _mock_dense_fixture_mat(
        tf_wids=["TF_A"],
        tu_wids=["TU_X"],
        affinity=np.array([[1.0]], dtype=np.float64),
        fold_change=np.array([[2.0]], dtype=np.float64),
        other_activities=np.array([[3.0]], dtype=np.float64),
    )
    monkeypatch.setattr(tx_reg_module, "_resolve_fixture_path", lambda _: Path("mocked.mat"))
    monkeypatch.setattr(tx_reg_module, "loadmat", lambda _: mocked)

    with pytest.raises(ValueError, match="overlap|overlapping"):
        tx_reg_module._load_fixture("mocked.mat")


def test_canonical_complex_wids_loader_raises_on_malformed_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    malformed_fx = np.zeros((1, 1), dtype=[("wrongField", object)])
    malformed_data = np.zeros((1, 1), dtype=[("fixture", object)])
    malformed_data["fixture"][0, 0] = malformed_fx
    monkeypatch.setattr(tx_reg_module, "_resolve_fixture_path", lambda _: Path("mocked_complex.mat"))
    monkeypatch.setattr(tx_reg_module, "loadmat", lambda _: {"data": malformed_data})

    with pytest.raises(KeyError, match="complexWholeCellModelIDs"):
        tx_reg_module._load_canonical_complex_wids("mocked_complex.mat")


def test_ports_schema_registers_tf_wids_in_mapped_store_only() -> None:
    p = KarrTranscriptionalRegulationProcess({})
    schema = p.ports_schema()

    protein_wids = set(schema["protein"]["counts"])
    complex_wids = set(schema["complex"]["counts"])
    expected_protein = {tf_wid for tf_wid in p.tf_wids if _tf_store(p, tf_wid) == "protein"}
    expected_complex = {tf_wid for tf_wid in p.tf_wids if _tf_store(p, tf_wid) == "complex"}

    assert protein_wids == expected_protein
    assert complex_wids == expected_complex
    assert protein_wids.isdisjoint(complex_wids)


def test_missing_tf_wid_in_expected_store_raises() -> None:
    p = _make_toy_process(
        tf_wids=["TF_DIMER"],
        tu_wids=["TU_X"],
        affinity=np.array([[1.0]], dtype=np.float64),
        fold_change=np.array([[2.0]], dtype=np.float64),
        tf_wid_source={"TF_DIMER": "complex"},
        seed=0,
    )
    state = _empty_tr_state(p)
    del state["complex"]["counts"]["TF_DIMER"]

    with pytest.raises(KeyError, match="TF_DIMER.*complex"):
        p.next_update(1.0, state)


def test_no_free_tfs_no_binding_change() -> None:
    p = KarrTranscriptionalRegulationProcess({"rng_seed": 1})
    state = _empty_tr_state(p)
    update = p.next_update(1.0, state)

    assert update["tf_binding"] == {}
    assert set(update["tx_rate_fold_change"]) == set(p.tu_wids)
    assert all(val == pytest.approx(1.0) for val in update["tx_rate_fold_change"].values())


def test_high_affinity_tf_binds_first() -> None:
    trials = 300
    hi_hits = 0
    lo_hits = 0
    for seed in range(trials):
        p = _make_toy_process(
            tf_wids=["TF_A"],
            tu_wids=["TU_HI", "TU_LO"],
            affinity=np.array([[10.0, 1.0]], dtype=np.float64),
            fold_change=np.array([[1.5, 1.5]], dtype=np.float64),
            seed=seed,
        )
        state = _empty_tr_state(p)
        _set_tf_count(p, state, "TF_A", 1.0)
        update = p.next_update(1.0, state)
        chosen = next(iter(update["tf_binding"]["TF_A"]))
        if chosen == "TU_HI":
            hi_hits += 1
        else:
            lo_hits += 1

    assert hi_hits > lo_hits


def test_one_copy_per_tf_per_promoter() -> None:
    p = _make_toy_process(
        tf_wids=["TF_A"],
        tu_wids=["TU_A"],
        affinity=np.array([[1.0]], dtype=np.float64),
        fold_change=np.array([[2.0]], dtype=np.float64),
        seed=0,
    )
    state = _empty_tr_state(p)
    _set_tf_count(p, state, "TF_A", 10.0)

    update = p.next_update(1.0, state)
    assert update["tf_binding"]["TF_A"]["TU_A"] == pytest.approx(1.0)
    _apply_tf_binding_update(state, update)

    update_next = p.next_update(1.0, state)
    assert update_next["tf_binding"] == {}


def test_fold_change_multiplicative() -> None:
    p = _make_toy_process(
        tf_wids=["TF_A", "TF_B"],
        tu_wids=["TU_X"],
        affinity=np.array([[1.0], [1.0]], dtype=np.float64),
        fold_change=np.array([[2.0], [2.0]], dtype=np.float64),
        seed=0,
    )
    state = _empty_tr_state(p)
    _set_tf_count(p, state, "TF_A", 1.0)
    _set_tf_count(p, state, "TF_B", 1.0)

    update = p.next_update(1.0, state)
    assert update["tx_rate_fold_change"]["TU_X"] == pytest.approx(4.0)


def test_other_activities_fold_change_tracks_tf_presence() -> None:
    p = _make_toy_process(
        tf_wids=["TF_A"],
        tu_wids=["TU_X"],
        affinity=np.array([[0.0]], dtype=np.float64),
        fold_change=np.array([[1.0]], dtype=np.float64),
        other_activities=np.array([[3.0]], dtype=np.float64),
        seed=0,
    )
    state = _empty_tr_state(p)

    update_none = p.next_update(1.0, state)
    assert update_none["tf_binding"] == {}
    assert update_none["tx_rate_fold_change"]["TU_X"] == pytest.approx(1.0)

    _set_tf_count(p, state, "TF_A", 1.0)
    update_present = p.next_update(1.0, state)
    assert update_present["tf_binding"] == {}
    assert update_present["tx_rate_fold_change"]["TU_X"] == pytest.approx(3.0)


def test_m2v3_reads_fold_change() -> None:
    kinetics = tx.calibrated_chassis_model(tx.load_default())
    mechanism_inputs = tx_v2.load_default()
    m2 = KarrTranscriptionV3Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )
    v2 = KarrTranscriptionV2Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )
    state_base = _make_m2_state(v2)
    state_fc = deepcopy(state_base)
    state_fc["tx_rate_fold_change"] = {"TU_001": 2.0}

    base = m2.next_update(1.0, state_base)
    regulated = m2.next_update(1.0, state_fc)

    gid0 = m2.gene_ids[0]
    gid1 = m2.gene_ids[1]
    assert abs(float(regulated["rna"]["counts"][gid0])) > abs(float(base["rna"]["counts"][gid0]))
    assert regulated["rna"]["counts"][gid1] == pytest.approx(base["rna"]["counts"][gid1])


def test_unbinding_recovers_baseline() -> None:
    p = _make_toy_process(
        tf_wids=["TF_A"],
        tu_wids=["TU_A"],
        affinity=np.array([[1.0]], dtype=np.float64),
        fold_change=np.array([[3.0]], dtype=np.float64),
        seed=0,
    )
    state = _empty_tr_state(p)
    _set_tf_count(p, state, "TF_A", 1.0)
    first = p.next_update(1.0, state)
    _apply_tf_binding_update(state, first)
    assert first["tx_rate_fold_change"]["TU_A"] == pytest.approx(3.0)

    _set_tf_count(p, state, "TF_A", 0.0)
    second = p.next_update(1.0, state)
    assert second["tf_binding"]["TF_A"]["TU_A"] == pytest.approx(-1.0)
    assert second["tx_rate_fold_change"]["TU_A"] == pytest.approx(1.0)


def test_steady_state_binding_fraction() -> None:
    p = KarrTranscriptionalRegulationProcess({"rng_seed": 0})
    state = _empty_tr_state(p)
    for tf in p.tf_wids:
        _set_tf_count(p, state, tf, 10.0)

    for _ in range(100):
        update = p.next_update(1.0, state)
        _apply_tf_binding_update(state, update)

    total_bound = 0.0
    for tf in p.tf_wids:
        total_bound += sum(float(state["tf_binding"][tf][tu]) for tu in p.tu_wids)
    total_tf = 0.0
    for tf in p.tf_wids:
        total_tf += float(state[_tf_store(p, tf)]["counts"][tf])
    binding_capacity = float(np.count_nonzero(p.tf_promoter_affinity > 0.0))
    expected_bound = min(total_tf, binding_capacity)
    if expected_bound > 0.0:
        assert total_bound >= 0.90 * expected_bound


def test_no_regression_m2v3_without_regulation() -> None:
    kinetics = tx.calibrated_chassis_model(tx.load_default())
    mechanism_inputs = tx_v2.load_default()

    v3 = KarrTranscriptionV3Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )
    state = _make_m2_state(v3)
    prior = np.array([float(state["rna"]["counts"][gid]) for gid in v3.gene_ids], dtype=float)
    n_active = float(state["complex"]["counts"]["RNA_POLYMERASE"])
    synth_gene_per_s = (
        tx_v2.predict_gene_synthesis_per_s(mechanism_inputs, n_active=n_active) * v3._mechanism_scale
    )
    expected_abs = v3._step_rna(prior, synth_gene_per_s, 1.0)

    update_v3 = v3.next_update(1.0, state)
    v3_delta = np.array(
        [float(update_v3["rna"]["counts"][gid]) for gid in v3.gene_ids], dtype=float
    )

    np.testing.assert_allclose(prior + v3_delta, expected_abs, rtol=0.0, atol=1e-9)
