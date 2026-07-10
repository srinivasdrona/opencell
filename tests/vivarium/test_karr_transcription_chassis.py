"""Smoke tests for the Karr-native M2 vivarium chassis."""

from __future__ import annotations

import numpy as np
import pytest

from opencell.m2 import transcription as tx
from opencell.vivarium.karr_transcription import (
    KarrTranscriptionProcess,
    build_karr_m2_engine,
)


@pytest.fixture(scope="module")
def model() -> tx.KarrTranscriptionModel:
    return tx.load_default()


def test_process_builds(model: tx.KarrTranscriptionModel) -> None:
    proc = KarrTranscriptionProcess({"model": model})
    schema = proc.ports_schema()
    assert len(schema["rna"]["counts"]) == 525
    # Faithful 12-species transcription substrate vocabulary from fixture.
    assert tuple(schema["substrates"]) == (
        "ATP",
        "CTP",
        "GTP",
        "UTP",
        "AMP",
        "CMP",
        "GMP",
        "UMP",
        "ADP",
        "PPI",
        "H2O",
        "H",
    )


def test_simulation_path_emits_karr_byproducts(model: tx.KarrTranscriptionModel) -> None:
    proc = KarrTranscriptionProcess({"model": model, "rng_seed": 0})
    proc._tu_sequences = ("A",)
    proc._tu_binding_prob = np.asarray([1.0], dtype=float)
    proc._polymerase_slots = [
        {
            "active": True,
            "tu_idx": 0,
            "position": 1,
            "chromosome_pos": 0,
        }
    ]

    substrate_state = {wid: 0.0 for wid in proc.substrate_wids}
    substrate_state["ATP"] = 1.0

    deltas = proc._simulate_polymerization_substrate_deltas(
        timestep=1.0,
        states={"substrates": substrate_state},
        effective_bound_counts={
            "RNA_POLYMERASE": 1,
            "RNA_POLYMERASE_HOLOENZYME": 0,
        },
    )

    assert deltas == {
        "ATP": -1.0,
        "PPI": 1.0,
        "H2O": -1.0,
        "H": 1.0,
    }


def test_engine_runs_100_steps_without_drift(
    model: tx.KarrTranscriptionModel,
) -> None:
    engine = build_karr_m2_engine(model=model, time_step_s=1.0)
    engine.update(100.0)
    ts = engine.emitter.get_timeseries()

    # All 525 RNA series are finite and stable (started at steady state).
    for gid, series in ts["rna"]["counts"].items():
        a = np.asarray(series, dtype=float)
        assert np.all(np.isfinite(a)), f"RNA {gid} non-finite"
        spread = float(np.max(a[1:]) - np.min(a[1:]))
        assert spread < 1e-6, f"RNA {gid} drifted: spread={spread}"

    # Substrate accumulators must be strictly negative (consumption).
    for ntp in ("ATP", "CTP", "GTP", "UTP"):
        a = np.asarray(ts["substrates"][ntp], dtype=float)
        # last sample = sum of -ntp_per_s over 100s
        assert a[-1] < 0, f"{ntp} not consumed: {a[-1]}"
        # roughly: last ~= - 100s * ntp_per_s (chassis uses calibrated model
        # whose synthesis rate yields s/k = counts_mature, so the operative
        # NTP demand is the calibrated value, not the KB-fitted one).
        expected = -100.0 * tx.ntp_consumption_per_s(tx.calibrated_chassis_model(model))[ntp]
        rel = abs(a[-1] - expected) / abs(expected)
        assert rel < 0.05, f"{ntp} consumption off: {a[-1]} vs {expected}"


def test_engine_starting_from_zero_approaches_steady_state(
    model: tx.KarrTranscriptionModel,
) -> None:
    """1800s integration from zero counts: chassis converges to Karr's
    State_Rna mature SS counts (counts_mature) for fast-decaying genes
    that have a non-zero SS count."""
    init = np.zeros(model.n_genes)
    engine = build_karr_m2_engine(model=model, time_step_s=1.0, initial_rna_counts=init)
    engine.update(1800.0)
    ts = engine.emitter.get_timeseries()

    target = model.counts_mature[:, 1]  # default condition=1 (mean)
    fast = (model.half_life_min > 0) & (model.half_life_min <= 5.0) & (target > 0)
    final = np.array([float(ts["rna"]["counts"][gid][-1]) for gid in model.gene_wcm_ids])
    rel = np.abs(final[fast] - target[fast]) / np.maximum(target[fast], 1e-12)
    assert float(np.max(rel)) < 0.05, (
        f"fast genes not at steady state: max rel = {rel.max():.4f} (n_fast={int(fast.sum())})"
    )
