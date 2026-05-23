from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest

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
from opencell.vivarium.karr_transcription_v2 import KarrTranscriptionV2Process
from opencell.vivarium.karr_transcription_v3 import KarrTranscriptionV3Process
from opencell.vivarium.karr_transcriptional_regulation import (
    KarrTranscriptionalRegulationProcess,
)


def _empty_tr_state(process: KarrTranscriptionalRegulationProcess) -> dict[str, Any]:
    return {
        "protein": {"counts": {tf: 0.0 for tf in process.tf_wids}},
        "tf_binding": {tf: {tu: 0.0 for tu in process.tu_wids} for tf in process.tf_wids},
    }


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
    seed: int = 0,
) -> KarrTranscriptionalRegulationProcess:
    p = KarrTranscriptionalRegulationProcess({"rng_seed": seed})
    p.tf_wids = tf_wids
    p.tu_wids = tu_wids
    p.tf_promoter_affinity = np.asarray(affinity, dtype=np.float64)
    p.tf_tu_fold_change = np.asarray(fold_change, dtype=np.float64)
    p.n_relationships = int(np.count_nonzero(p.tf_promoter_affinity > 0.0))
    p._n_tf = len(tf_wids)
    p._n_tu = len(tu_wids)
    p._rng = np.random.default_rng(seed)
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


def test_fixture_loads() -> None:
    p = KarrTranscriptionalRegulationProcess({})
    assert p.name == "karr_transcriptional_regulation"
    assert len(p.tf_wids) == 5
    assert len(p.tu_wids) > 0
    assert p.tf_promoter_affinity.shape == (len(p.tf_wids), len(p.tu_wids))
    assert p.tf_tu_fold_change.shape == (len(p.tf_wids), len(p.tu_wids))
    assert p.n_relationships > 0


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
        state["protein"]["counts"]["TF_A"] = 1.0
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
    state["protein"]["counts"]["TF_A"] = 10.0

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
    state["protein"]["counts"]["TF_A"] = 1.0
    state["protein"]["counts"]["TF_B"] = 1.0

    update = p.next_update(1.0, state)
    assert update["tx_rate_fold_change"]["TU_X"] == pytest.approx(4.0)


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
    state["protein"]["counts"]["TF_A"] = 1.0
    first = p.next_update(1.0, state)
    _apply_tf_binding_update(state, first)
    assert first["tx_rate_fold_change"]["TU_A"] == pytest.approx(3.0)

    state["protein"]["counts"]["TF_A"] = 0.0
    second = p.next_update(1.0, state)
    assert second["tf_binding"]["TF_A"]["TU_A"] == pytest.approx(-1.0)
    assert second["tx_rate_fold_change"]["TU_A"] == pytest.approx(1.0)


def test_steady_state_binding_fraction() -> None:
    p = KarrTranscriptionalRegulationProcess({"rng_seed": 0})
    state = _empty_tr_state(p)
    for tf in p.tf_wids:
        state["protein"]["counts"][tf] = 10.0

    for _ in range(100):
        update = p.next_update(1.0, state)
        _apply_tf_binding_update(state, update)

    total_bound = 0.0
    for tf in p.tf_wids:
        total_bound += sum(float(state["tf_binding"][tf][tu]) for tu in p.tu_wids)
    total_tf = sum(float(state["protein"]["counts"][tf]) for tf in p.tf_wids)
    bound_fraction = (total_bound / total_tf) if total_tf > 0.0 else 0.0
    assert bound_fraction > 0.40


def test_no_regression_m2v3_without_regulation() -> None:
    kinetics = tx.calibrated_chassis_model(tx.load_default())
    mechanism_inputs = tx_v2.load_default()

    v2 = KarrTranscriptionV2Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )
    v3 = KarrTranscriptionV3Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )
    state = _make_m2_state(v2)
    prior = np.array([float(state["rna"]["counts"][gid]) for gid in v2.gene_ids], dtype=float)

    update_v2 = v2.next_update(1.0, state)
    update_v3 = v3.next_update(1.0, state)
    v2_abs = np.array([float(update_v2["rna"]["counts"][gid]) for gid in v2.gene_ids], dtype=float)
    v3_delta = np.array(
        [float(update_v3["rna"]["counts"][gid]) for gid in v3.gene_ids], dtype=float
    )

    np.testing.assert_allclose(prior + v3_delta, v2_abs, rtol=0.0, atol=1e-9)

