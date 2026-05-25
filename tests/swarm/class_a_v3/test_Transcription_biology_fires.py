"""Biology-firing canary for Transcription v3 (swarm pilot Class A)."""

from __future__ import annotations

import numpy as np
from vivarium.core.composition import simulate_process

from opencell.validation.predicates import (
    all_nonnegative,
    monotonically_decreasing,
    monotonically_increasing,
)
from opencell.vivarium.karr_transcription_v3 import KarrTranscriptionV3Process


def _simulate_transcription_v3(
    *,
    total_time: int,
    tx_rate_fold_change: dict[str, float] | None = None,
) -> tuple[KarrTranscriptionV3Process, dict]:
    proc = KarrTranscriptionV3Process({"time_step": 1.0})
    initial = {
        "rna": {"counts": {gid: 0.0 for gid in proc.gene_ids}},
        "substrates": {"ATP": 0.0, "CTP": 0.0, "GTP": 0.0, "UTP": 0.0},
        "complex": {"counts": {"RNA_POLYMERASE": float(proc.mechanism_inputs.n_active_rnap)}},
        "tx_rate_fold_change": tx_rate_fold_change or {},
    }
    data = simulate_process(proc, {"total_time": total_time, "initial_state": initial})
    return proc, data


def test_Transcription_v3_fires() -> None:
    proc, data = _simulate_transcription_v3(total_time=5)

    total_rna = np.array(
        [
            sum(data["rna"]["counts"][gid][i] for gid in proc.gene_ids)
            for i in range(len(data["time"]))
        ],
        dtype=float,
    )
    rna_matrix = np.array([data["rna"]["counts"][gid] for gid in proc.gene_ids], dtype=float)
    atp = np.array(data["substrates"]["ATP"], dtype=float)
    ctp = np.array(data["substrates"]["CTP"], dtype=float)
    gtp = np.array(data["substrates"]["GTP"], dtype=float)
    utp = np.array(data["substrates"]["UTP"], dtype=float)

    # Starting from zero RNA, transcription synthesis should increase total RNA over time.
    assert total_rna[-1] > total_rna[0]
    assert monotonically_increasing(total_rna)

    # Mature RNA counts should remain non-negative under production/decay dynamics.
    assert all_nonnegative(rna_matrix)

    # Polymerization should consume each NTP channel monotonically.
    assert monotonically_decreasing(atp)
    assert monotonically_decreasing(ctp)
    assert monotonically_decreasing(gtp)
    assert monotonically_decreasing(utp)

    # This v3 implementation uses symmetric NTP splitting, so channels should match exactly.
    assert np.allclose(atp, ctp, rtol=0.0, atol=1e-12)
    assert np.allclose(atp, gtp, rtol=0.0, atol=1e-12)
    assert np.allclose(atp, utp, rtol=0.0, atol=1e-12)

    # Transcriptional regulation input should modulate at least one TU-linked gene trajectory.
    first_gene = proc.gene_ids[0]
    _, baseline = _simulate_transcription_v3(total_time=1, tx_rate_fold_change={})
    _, suppressed = _simulate_transcription_v3(
        total_time=1,
        tx_rate_fold_change={"TU_001": 0.0},
    )
    baseline_delta = float(
        baseline["rna"]["counts"][first_gene][-1] - baseline["rna"]["counts"][first_gene][0]
    )
    suppressed_delta = float(
        suppressed["rna"]["counts"][first_gene][-1] - suppressed["rna"]["counts"][first_gene][0]
    )
    assert suppressed_delta < baseline_delta
