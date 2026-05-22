"""Smoke tests for A3 step 2 v2 chassis composition."""

from __future__ import annotations

import numpy as np
import pytest

from opencell.m2 import transcription_v2 as tx_v2
from opencell.m3 import translation_v2 as tl_v2
from opencell.vivarium.karr_composite import build_karr_chassis_v2


def test_build_karr_chassis_v2_smoke() -> None:
    engine = build_karr_chassis_v2(time_step_s=1.0, emit_step_s=1.0)
    state = engine.state.get_value()
    assert "metabolic_reaction" in state
    assert "substrates" in state
    assert "rna" in state and "counts" in state["rna"]
    assert "protein" in state and "counts" in state["protein"]
    assert "complex" in state and "counts" in state["complex"]
    assert len(state["rna"]["counts"]) == 525
    assert len(state["protein"]["counts"]) == 482


def test_karr_chassis_v2_single_tick_smoke() -> None:
    engine = build_karr_chassis_v2(time_step_s=1.0, emit_step_s=1.0)
    state_t0 = engine.state.get_value()
    engine.update(1.0)
    state_t1 = engine.state.get_value()

    assert set(state_t0["rna"]["counts"]) == set(state_t1["rna"]["counts"])
    assert set(state_t0["protein"]["counts"]) == set(state_t1["protein"]["counts"])
    assert set(state_t0["complex"]["counts"]) <= set(state_t1["complex"]["counts"])
    assert np.isfinite(sum(state_t1["rna"]["counts"].values()))
    assert np.isfinite(sum(state_t1["protein"]["counts"].values()))


def test_v2_wrappers_read_dynamic_complex_counts_each_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    m2_reads: list[float] = []
    m3_reads: list[float] = []

    orig_m2_predict = tx_v2.predict_gene_synthesis_per_s
    orig_m3_predict = tl_v2.predict_synthesis_per_s

    def _spy_m2_predict(
        inputs: tx_v2.MechanismInputs,
        n_active: int | float | None = None,
        p_bind: np.ndarray | None = None,
    ) -> np.ndarray:
        m2_reads.append(float(inputs.n_active_rnap if n_active is None else n_active))
        return orig_m2_predict(inputs, n_active=n_active, p_bind=p_bind)

    def _spy_m3_predict(
        inputs: tl_v2.RibosomeMechanismInputs,
        n_active: int | float | None = None,
        mrna_counts: np.ndarray | None = None,
    ) -> np.ndarray:
        m3_reads.append(float(inputs.n_active_ribosomes if n_active is None else n_active))
        return orig_m3_predict(inputs, n_active=n_active, mrna_counts=mrna_counts)

    monkeypatch.setattr(tx_v2, "predict_gene_synthesis_per_s", _spy_m2_predict)
    monkeypatch.setattr(tl_v2, "predict_synthesis_per_s", _spy_m3_predict)

    engine = build_karr_chassis_v2(time_step_s=1.0, emit_step_s=1.0)
    engine.state.set_path(("complex", "counts", "RNA_POLYMERASE"), 13.0)
    engine.state.set_path(("complex", "counts", "RIBOSOME_70S"), 29.0)
    engine.update(1.0)

    engine.state.set_path(("complex", "counts", "RNA_POLYMERASE"), 37.0)
    engine.state.set_path(("complex", "counts", "RIBOSOME_70S"), 61.0)
    engine.update(1.0)

    assert m2_reads == pytest.approx([13.0, 37.0])
    assert m3_reads == pytest.approx([29.0, 61.0])


def test_v2_promotes_p7_from_trivial_round_trip() -> None:
    """Under v2 mechanics, p7-style RNA stability is no longer trivially flat."""
    engine = build_karr_chassis_v2(time_step_s=1.0, emit_step_s=1.0)
    engine.state.set_path(("complex", "counts", "RNA_POLYMERASE"), 35.0)
    engine.state.set_path(("complex", "counts", "RIBOSOME_70S"), 56.0)
    engine.update(20.0)
    ts = engine.emitter.get_timeseries()

    rna_counts = ts["rna"]["counts"]
    n_steps = len(next(iter(rna_counts.values())))
    total = np.array(
        [sum(vals[t] for vals in rna_counts.values()) for t in range(n_steps)],
        dtype=float,
    )
    drift = abs(float(total[-1]) - float(total[0])) / float(total[0])
    assert drift > 0.02
