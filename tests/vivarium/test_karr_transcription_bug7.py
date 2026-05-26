from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

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
from opencell.vivarium.karr_transcription_v3 import KarrTranscriptionV3Process


def _make_state(
    process: KarrTranscriptionV3Process,
    *,
    n_active_rnap: float | None = None,
    zero_rna: bool = False,
) -> dict:
    active = (
        float(process.mechanism_inputs.n_active_rnap)
        if n_active_rnap is None
        else float(n_active_rnap)
    )
    if zero_rna:
        rna_counts = {gid: 0.0 for gid in process.gene_ids}
    else:
        rna_counts = {
            gid: float(process.kinetics_model.counts_mature[i, 1])
            for i, gid in enumerate(process.gene_ids)
        }
    return {
        "rna": {"counts": rna_counts},
        "complex": {"counts": {"RNA_POLYMERASE": active}},
    }


def test_mechanism_scale_derived_from_calibrated_total() -> None:
    kinetics = tx.calibrated_chassis_model(tx.load_default())
    mechanism_inputs = tx_v2.load_default()
    proc = KarrTranscriptionV3Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )

    target_total = float(np.sum(kinetics.synthesis_rate_per_s[:, 1]))
    pred_total = float(
        np.sum(
            tx_v2.predict_gene_synthesis_per_s(
                mechanism_inputs,
                n_active=proc._fallback_n_active_rnap,
            )
        )
    )
    expected_scale = target_total / pred_total
    assert np.isfinite(proc._mechanism_scale)
    assert proc._mechanism_scale > 0.0
    assert abs(proc._mechanism_scale - expected_scale) < 1e-9


def test_synth_total_matches_calibrated_target_at_default_rnap() -> None:
    kinetics = tx.calibrated_chassis_model(tx.load_default())
    mechanism_inputs = tx_v2.load_default()
    proc = KarrTranscriptionV3Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )

    predicted = tx_v2.predict_gene_synthesis_per_s(
        mechanism_inputs,
        n_active=proc._fallback_n_active_rnap,
    )
    scaled_total = float(np.sum(predicted * proc._mechanism_scale))
    target_total = float(np.sum(kinetics.synthesis_rate_per_s[:, 1]))
    assert np.isclose(scaled_total, target_total, rtol=1e-6)


def test_ntp_drain_scaled_consistently() -> None:
    proc = KarrTranscriptionV3Process({})
    state = _make_state(proc)
    update = proc.next_update(1.0, state)

    observed_total_nt_drain = float(sum(update["substrates"].values()))
    expected_total_nt_drain = -float(
        tx_v2.total_nt_polymerization_per_s(
            proc.mechanism_inputs,
            n_active=proc._fallback_n_active_rnap,
        )
        * proc._mechanism_scale
    )
    assert np.isclose(observed_total_nt_drain, expected_total_nt_drain, rtol=1e-9)


def test_fold_change_multipliers_still_work() -> None:
    proc = KarrTranscriptionV3Process({})

    base_state = _make_state(proc, zero_rna=True)
    base = proc.next_update(1.0, base_state)

    regulated_state = _make_state(proc, zero_rna=True)
    regulated_state["tx_rate_fold_change"] = {"TU_001": 2.0}
    regulated = proc.next_update(1.0, regulated_state)

    gid0 = proc.gene_ids[0]
    base_delta = float(base["rna"]["counts"][gid0])
    regulated_delta = float(regulated["rna"]["counts"][gid0])
    assert base_delta > 0.0
    assert np.isclose(regulated_delta / base_delta, 2.0, rtol=1e-6)


def test_zero_rnap_yields_zero_synth_and_zero_drain() -> None:
    proc = KarrTranscriptionV3Process({})
    state = _make_state(proc, n_active_rnap=0.0)
    update = proc.next_update(1.0, state)

    deltas = np.array(list(update["rna"]["counts"].values()), dtype=float)
    assert np.all(deltas <= 0.0)
    assert float(sum(update.get("substrates", {}).values())) == 0.0
