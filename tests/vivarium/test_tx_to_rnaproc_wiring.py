from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

from opencell.vivarium.karr_rna_processing import KarrRNAProcessingProcess
from opencell.vivarium.karr_transcription_v3 import KarrTranscriptionV3Process


def _rxn_ids_without_tu_self_cancellation(
    process: KarrRNAProcessingProcess,
    n: int,
) -> list[str]:
    processed_idx = {wid: idx for idx, wid in enumerate(process.processed_rna_wids)}
    out: list[str] = []
    for ridx, wid in enumerate(process.unprocessed_rna_wids):
        pidx = processed_idx.get(wid)
        if pidx is not None and int(process.processed_output_matrix[pidx, ridx]) != 0:
            continue
        out.append(wid)
        if len(out) >= n:
            break
    if len(out) < n:
        raise AssertionError(f"Need at least {n} non-self-canceling TU IDs, found {len(out)}")
    return out


def _rna_processing_state(
    process: KarrRNAProcessingProcess,
    unprocessed_counts: dict[str, float],
) -> dict[str, Any]:
    state = {
        "substrates": {wid: 1_000_000.0 for wid in process.substrate_wids},
        "rna": {"counts": {wid: 0.0 for wid in process.rna_wids}},
        "protein": {"counts": {wid: 1_000_000.0 for wid in process.monomer_enzyme_wids}},
        "complex": {"counts": {wid: 1_000_000.0 for wid in process.complex_enzyme_wids}},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 1_000_000.0 for wid in process.substrate_wids}},
    }
    for wid, count in unprocessed_counts.items():
        state["rna"]["counts"][wid] = float(count)
    return state


def _transcription_state(tx: KarrTranscriptionV3Process) -> dict[str, Any]:
    return {
        "rna": {"counts": {gid: 0.0 for gid in tx.gene_ids}},
        "complex": {"counts": {"RNA_POLYMERASE": float(tx._fallback_n_active_rnap)}},
        "tx_rate_fold_change": {},
        "substrates_allocated": {
            tx.name: {wid: 1_000_000.0 for wid in tx.allocation_substrate_wids}
        },
    }


def test_tx_to_rnaproc_tu_contract_for_known_ids() -> None:
    tx = KarrTranscriptionV3Process({"emit_unprocessed_tu": True})
    rp = KarrRNAProcessingProcess({"rng_seed": 0, "max_stochastic_iterations": 0})

    expected_tu_ids = _rxn_ids_without_tu_self_cancellation(rp, n=3)

    tx_update = tx.next_update(1.0, _transcription_state(tx))
    tx_rna_keys = set(tx_update.get("rna", {}).get("counts", {}).keys())
    missing = [wid for wid in expected_tu_ids if wid not in tx_rna_keys]
    assert not missing, (
        "Transcription->RNAProcessing wiring contract broken: producer update is missing "
        f"TU IDs required by RNAProcessing: {missing}"
    )

    synthetic_tx_update = {"rna": {"counts": {wid: 5.0 for wid in expected_tu_ids}}}
    rp_state = _rna_processing_state(rp, synthetic_tx_update["rna"]["counts"])
    rp_update = rp.next_update(1.0, rp_state)
    assert "rna" in rp_update and "counts" in rp_update["rna"]

    neg_tu_ids = {
        wid
        for wid, delta in rp_update["rna"]["counts"].items()
        if wid in set(expected_tu_ids) and float(delta) < 0.0
    }
    assert neg_tu_ids == set(expected_tu_ids)
