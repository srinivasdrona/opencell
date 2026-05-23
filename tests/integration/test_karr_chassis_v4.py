"""Integration coverage for Phase-B v4 chassis wiring + ratchet closure."""

from __future__ import annotations

import sys
import time
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

from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.karr_composite import (
    build_karr_chassis_v3,
    build_karr_chassis_v4,
)

pytestmark = pytest.mark.filterwarnings("ignore:Incompatible schema assignment at .*")


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


def _charged_trna_fraction_from_state(
    state: dict[str, Any],
    trna_free_wids: list[str],
    trna_charged_wids: list[str],
) -> float:
    free = sum(float(state["rna"]["counts"].get(wid, 0.0)) for wid in trna_free_wids)
    charged = sum(
        float(state["rna"].get("aminoacylated_counts", {}).get(wid, 0.0))
        for wid in trna_charged_wids
    )
    total = free + charged
    return (charged / total) if total > 0.0 else 0.0


def _series_mean_in_window(
    ts_time: np.ndarray,
    series: np.ndarray,
    t_start: float,
    t_end: float,
) -> float:
    mask = (ts_time >= float(t_start)) & (ts_time <= float(t_end))
    if not np.any(mask):
        return 0.0
    return float(np.mean(series[mask]))


def _charged_fraction_series(
    ts: dict[str, Any],
    trna_free_wids: list[str],
    trna_charged_wids: list[str],
) -> np.ndarray:
    free_series = np.zeros(len(ts["time"]), dtype=np.float64)
    charged_series = np.zeros(len(ts["time"]), dtype=np.float64)
    for wid in trna_free_wids:
        free_series += np.asarray(
            ts["rna"]["counts"].get(wid, np.zeros(len(ts["time"]))), dtype=np.float64
        )
    for wid in trna_charged_wids:
        charged_series += np.asarray(
            ts["rna"]["aminoacylated_counts"].get(wid, np.zeros(len(ts["time"]))),
            dtype=np.float64,
        )
    denom = free_series + charged_series
    out = np.zeros_like(denom, dtype=np.float64)
    valid = denom > 0.0
    out[valid] = charged_series[valid] / denom[valid]
    return out


def _boost_common_substrates(engine: Any, wids: list[str], value: float = 50_000.0) -> None:
    for wid in wids:
        engine.state.set_path(("substrates", wid), float(value))


def _seed_protein_pathway_inputs(engine: Any) -> None:
    pp1 = engine.processes["karr_protein_processing_i"]
    pp2 = engine.processes["karr_protein_processing_ii"]
    pmod = engine.processes["karr_protein_modification"]
    pfold = engine.processes["karr_protein_folding"]
    ptrans = engine.processes["karr_protein_translocation"]

    for wid in (
        set(pp1.enzyme_wids) | set(pp2.enzyme_wids) | set(pmod.enzyme_wids) | set(pfold.enzyme_wids)
    ):
        engine.state.set_path(("protein", "counts", wid), 5_000.0)
    for wid in pp2.enzyme_wids:
        engine.state.set_path(("protein", "enzyme_counts", wid), 5_000.0)

    target_pp1 = pp1.unprocessed_monomer_wids[0]
    target_fold = pfold.unfolded_monomer_wids[0]
    target_mod = pmod.unmodified_monomer_wids[0]
    target_trans = ptrans.translocatable_wids[0]

    engine.state.set_path(("protein", "unprocessed_counts", target_pp1), 1_000.0)
    engine.state.set_path(("protein", "unfolded_counts", target_fold), 1_000.0)
    engine.state.set_path(("protein", "unmodified_counts", target_mod), 500.0)
    engine.state.set_path(("protein", "counts", target_trans), 200.0)
    engine.state.set_path(("protein", "location", target_trans), "cytoplasm")

    _boost_common_substrates(
        engine,
        list(
            set(pp1.substrate_wids)
            | set(pp2.substrate_wids)
            | set(pmod.substrate_wids)
            | set(pfold.substrate_wids)
            | set(ptrans.substrate_wids)
        ),
    )


def _seed_rna_pathway_inputs(engine: Any) -> None:
    ribasm = engine.processes["karr_ribosome_assembly"]
    rna_proc = engine.processes["karr_rna_processing"]
    rna_mod = engine.processes["karr_rna_modification"]

    for wid in rna_proc.unprocessed_rna_wids[:40]:
        engine.state.set_path(("rna", "counts", wid), 200.0)
    for wid in rna_mod.unmodified_rna_wids:
        engine.state.set_path(("rna", "counts", wid), 200.0)
    for wid in ribasm.rna_subunit_wids:
        engine.state.set_path(("rna", "counts", wid), 500.0)

    for wid in (
        set(rna_proc.enzyme_wids) | set(rna_mod.enzyme_wids) | set(ribasm.protein_state_wids)
    ):
        engine.state.set_path(("protein", "counts", wid), 2_000.0)
    for wid in ribasm.monomer_subunit_wids:
        engine.state.set_path(("protein", "counts", wid), 2_000.0)

    _boost_common_substrates(
        engine,
        list(
            set(rna_proc.substrate_wids) | set(rna_mod.substrate_wids) | set(ribasm.substrate_wids)
        ),
    )


@pytest.fixture(scope="module")
def v4_long_run(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> dict[str, Any]:
    engine = build_karr_chassis_v4(
        m1_model,
        m2_model,
        m3_model,
        time_step_s=1.0,
        emit_step_s=10.0,
    )
    engine.update(2_000.0)
    return {
        "engine": engine,
        "state": engine.state.get_value(),
        "timeseries": engine.emitter.get_timeseries(),
    }


def test_chassis_v4_builds(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_chassis_v4(m1_model, m2_model, m3_model, time_step_s=1.0, emit_step_s=1.0)
    assert engine is not None
    expected_processes = {
        "karr_metabolism",
        "karr_transcription_v3",
        "karr_translation_v3",
        "karr_macromolecular_complexation",
        "karr_protein_decay_light",
        "karr_trna_aminoacylation",
        "karr_ribosome_assembly",
        "karr_transcriptional_regulation",
        "karr_rna_processing",
        "karr_rna_modification",
        "karr_protein_processing_i",
        "karr_protein_processing_ii",
        "karr_protein_modification",
        "karr_protein_folding",
        "karr_protein_translocation",
        "karr_protein_activation",
    }
    expected_steps = {
        "request_calculator_d2",
        "request_calculator_pd",
        "request_calculator_ribasm",
        "request_calculator_trna",
        "request_calculator_rna_pathway",
        "request_calculator_protein_pathway",
        "karr_allocation_step",
    }
    assert expected_processes.issubset(set(engine.processes))
    assert expected_steps.issubset(set(engine.steps))


def test_chassis_v4_10_ticks_smoke(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_chassis_v4(m1_model, m2_model, m3_model, time_step_s=1.0, emit_step_s=1.0)
    engine.update(10.0)
    state = engine.state.get_value()

    assert state.get("complex", {}).get("counts")
    assert state.get("protein", {}).get("counts")
    assert state.get("rna", {}).get("counts")
    assert np.isfinite(sum(float(v) for v in state["complex"]["counts"].values()))
    assert np.isfinite(sum(float(v) for v in state["protein"]["counts"].values()))
    assert np.isfinite(sum(float(v) for v in state["rna"]["counts"].values()))
    assert all(float(v) >= 0.0 for v in state["complex"]["counts"].values())


def test_chassis_v4_full_protein_pipeline_10_ticks(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_chassis_v4(m1_model, m2_model, m3_model, time_step_s=1.0, emit_step_s=1.0)
    _seed_protein_pathway_inputs(engine)

    pp1 = engine.processes["karr_protein_processing_i"]
    pfold = engine.processes["karr_protein_folding"]
    pmod = engine.processes["karr_protein_modification"]

    target_pp1 = pp1.unprocessed_monomer_wids[0]
    target_fold = pfold.unfolded_monomer_wids[0]
    target_mod_un = pmod.unmodified_monomer_wids[0]
    target_mod = pmod.modified_monomer_wids[0]

    before = engine.state.get_value()
    before_unprocessed = float(before["protein"]["unprocessed_counts"].get(target_pp1, 0.0))
    before_unfolded = float(before["protein"]["unfolded_counts"].get(target_fold, 0.0))
    before_unmodified = float(before["protein"]["unmodified_counts"].get(target_mod_un, 0.0))
    before_modified = float(before["protein"]["modified_counts"].get(target_mod, 0.0))

    engine.update(10.0)
    after = engine.state.get_value()
    after_unprocessed = float(after["protein"]["unprocessed_counts"].get(target_pp1, 0.0))
    after_unfolded = float(after["protein"]["unfolded_counts"].get(target_fold, 0.0))
    after_unmodified = float(after["protein"]["unmodified_counts"].get(target_mod_un, 0.0))
    after_modified = float(after["protein"]["modified_counts"].get(target_mod, 0.0))

    assert after_unprocessed < before_unprocessed
    assert after_unfolded < before_unfolded
    assert after_unmodified <= before_unmodified
    assert after_modified >= before_modified
    assert "activity" in after["protein"]
    assert len(after["protein"]["activity"]) == len(
        engine.processes["karr_protein_activation"].regulated_protein_wids
    )


def test_chassis_v4_full_rna_pipeline_10_ticks(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_chassis_v4(m1_model, m2_model, m3_model, time_step_s=1.0, emit_step_s=1.0)
    _seed_rna_pathway_inputs(engine)

    before = engine.state.get_value()
    before_modified = sum(float(v) for v in before["rna"].get("modified_counts", {}).values())
    before_rib = float(before["complex"]["counts"].get("RIBOSOME_30S", 0.0)) + float(
        before["complex"]["counts"].get("RIBOSOME_50S", 0.0)
    )

    engine.update(10.0)
    after = engine.state.get_value()
    after_modified = sum(float(v) for v in after["rna"].get("modified_counts", {}).values())
    after_rib = float(after["complex"]["counts"].get("RIBOSOME_30S", 0.0)) + float(
        after["complex"]["counts"].get("RIBOSOME_50S", 0.0)
    )

    assert after_modified >= before_modified
    assert after_rib >= before_rib
    assert after_rib > 0.0


def test_chassis_v4_ribosome_assembly_consumes_gtpases(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine_low = build_karr_chassis_v4(
        m1_model, m2_model, m3_model, time_step_s=1.0, emit_step_s=1.0
    )
    engine_high = build_karr_chassis_v4(
        m1_model, m2_model, m3_model, time_step_s=1.0, emit_step_s=1.0
    )

    for eng in (engine_low, engine_high):
        _seed_rna_pathway_inputs(eng)

    engine_low.state.set_path(("substrates", "GTP"), 20.0)
    engine_low.state.set_path(("substrates", "H2O"), 20.0)
    engine_high.state.set_path(("substrates", "GTP"), 20_000.0)
    engine_high.state.set_path(("substrates", "H2O"), 20_000.0)

    engine_low.update(100.0)
    engine_high.update(100.0)

    state_low = engine_low.state.get_value()
    state_high = engine_high.state.get_value()
    rib_low = float(state_low["complex"]["counts"].get("RIBOSOME_30S", 0.0)) + float(
        state_low["complex"]["counts"].get("RIBOSOME_50S", 0.0)
    )
    rib_high = float(state_high["complex"]["counts"].get("RIBOSOME_30S", 0.0)) + float(
        state_high["complex"]["counts"].get("RIBOSOME_50S", 0.0)
    )

    assert rib_high > rib_low
    assert float(state_low["substrates"].get("GTP", 0.0)) < 20.0
    assert all(float(v) >= 0.0 for v in state_low["protein"]["counts"].values())


def test_chassis_v4_extended_ratchet_closure(v4_long_run: dict[str, Any]) -> None:
    engine = v4_long_run["engine"]
    ts = v4_long_run["timeseries"]
    state = v4_long_run["state"]
    ts_time = np.asarray(ts["time"], dtype=np.float64)

    complex_counts = state.get("complex", {}).get("counts", {})
    top_complex = [
        wid
        for wid, _ in sorted(complex_counts.items(), key=lambda kv: float(kv[1]), reverse=True)[:20]
    ]
    protein_counts = state.get("protein", {}).get("counts", {})
    top_protein = [
        wid
        for wid, _ in sorted(protein_counts.items(), key=lambda kv: float(kv[1]), reverse=True)[:20]
    ]
    assert len(top_complex) == 20
    assert len(top_protein) == 20

    drifts_complex: dict[str, float] = {}
    for wid in top_complex:
        series = np.asarray(
            ts["complex"]["counts"].get(wid, np.zeros_like(ts_time)), dtype=np.float64
        )
        mid = _series_mean_in_window(ts_time, series, 800.0, 1200.0)
        late = _series_mean_in_window(ts_time, series, 1500.0, 2000.0)
        drifts_complex[wid] = abs(late - mid) / max(1.0, abs(mid))

    drifts_protein: dict[str, float] = {}
    for wid in top_protein:
        series = np.asarray(
            ts["protein"]["counts"].get(wid, np.zeros_like(ts_time)), dtype=np.float64
        )
        mid = _series_mean_in_window(ts_time, series, 800.0, 1200.0)
        late = _series_mean_in_window(ts_time, series, 1500.0, 2000.0)
        drifts_protein[wid] = abs(late - mid) / max(1.0, abs(mid))

    trna_proc = engine.processes["karr_trna_aminoacylation"]
    frac_series = _charged_fraction_series(
        ts, trna_proc.free_rna_wids, trna_proc.aminoacylated_rna_wids
    )
    frac_mid = _series_mean_in_window(ts_time, frac_series, 800.0, 1200.0)
    frac_late = _series_mean_in_window(ts_time, frac_series, 1500.0, 2000.0)
    frac_drift = abs(frac_late - frac_mid) / max(1e-9, abs(frac_mid))

    worst_complex = max(drifts_complex.values())
    worst_protein = max(drifts_protein.values())
    assert worst_complex < 0.25, f"worst complex drift={worst_complex:.2%}"
    assert worst_protein < 0.25, f"worst protein drift={worst_protein:.2%}"
    assert frac_drift < 0.25, f"charged tRNA fraction drift={frac_drift:.2%}"


def test_chassis_v4_steady_state_charged_trna_67pct(v4_long_run: dict[str, Any]) -> None:
    engine = v4_long_run["engine"]
    state = v4_long_run["state"]
    trna_proc = engine.processes["karr_trna_aminoacylation"]

    frac = _charged_trna_fraction_from_state(
        state,
        trna_proc.free_rna_wids,
        trna_proc.aminoacylated_rna_wids,
    )
    assert frac == pytest.approx(0.67, abs=0.10)


def test_chassis_v3_still_works() -> None:
    engine = build_karr_chassis_v3(time_step_s=1.0, emit_step_s=1.0)
    engine.update(10.0)
    state = engine.state.get_value()

    assert len(state["rna"]["counts"]) == 525
    assert len(state["protein"]["counts"]) == 482
    assert np.isfinite(sum(float(v) for v in state["complex"]["counts"].values()))
    assert np.isfinite(sum(float(v) for v in state["protein"]["counts"].values()))
    assert np.isfinite(sum(float(v) for v in state["rna"]["counts"].values()))


def test_chassis_v4_all_writers_accumulate(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_chassis_v4(m1_model, m2_model, m3_model, time_step_s=1.0, emit_step_s=1.0)

    p_m1 = engine.processes["karr_metabolism"].ports_schema()
    p_m2 = engine.processes["karr_transcription_v3"].ports_schema()
    p_m3 = engine.processes["karr_translation_v3"].ports_schema()
    p_d2 = engine.processes["karr_macromolecular_complexation"].ports_schema()
    p_pd = engine.processes["karr_protein_decay_light"].ports_schema()
    p_trna = engine.processes["karr_trna_aminoacylation"].ports_schema()
    p_ribasm = engine.processes["karr_ribosome_assembly"].ports_schema()
    p_rna_proc = engine.processes["karr_rna_processing"].ports_schema()
    p_rna_mod = engine.processes["karr_rna_modification"].ports_schema()
    p_pp1 = engine.processes["karr_protein_processing_i"].ports_schema()
    p_pp2 = engine.processes["karr_protein_processing_ii"].ports_schema()
    p_pmod = engine.processes["karr_protein_modification"].ports_schema()
    p_pfold = engine.processes["karr_protein_folding"].ports_schema()
    p_ptrans = engine.processes["karr_protein_translocation"].ports_schema()

    _assert_branch_accumulate(p_m1["substrates"])
    _assert_branch_accumulate(p_m2["rna"]["counts"])
    _assert_branch_accumulate(p_m2["substrates"])
    _assert_branch_accumulate(p_m3["protein"]["counts"])
    _assert_branch_accumulate(p_m3["substrates"])
    _assert_branch_accumulate(p_d2["complex"]["counts"])
    _assert_branch_accumulate(p_d2["substrates"])
    _assert_branch_accumulate(p_pd["complex"]["counts"])
    _assert_branch_accumulate(p_pd["substrates"])
    _assert_branch_accumulate(p_trna["rna"]["counts"])
    _assert_branch_accumulate(p_trna["rna"]["aminoacylated_counts"])
    _assert_branch_accumulate(p_trna["substrates"])
    _assert_branch_accumulate(p_ribasm["complex"]["counts"])
    _assert_branch_accumulate(p_rna_proc["rna"]["counts"])
    _assert_branch_accumulate(p_rna_mod["rna"]["counts"])
    _assert_branch_accumulate(p_pp1["protein"]["unprocessed_counts"])
    _assert_branch_accumulate(p_pp2["protein"]["unprocessed_counts"])
    _assert_branch_accumulate(p_pmod["protein"]["unmodified_counts"])
    _assert_branch_accumulate(p_pfold["protein"]["unfolded_counts"])
    _assert_branch_accumulate(p_ptrans["protein"]["counts"])

    step_alloc = engine.steps["karr_allocation_step"].ports_schema()
    any_alloc_out_leaf = next(
        iter(step_alloc["substrates_allocated"]["karr_protein_processing_i"].values())
    )
    assert any_alloc_out_leaf["_updater"] == "set"


def test_chassis_v4_tick_rate(
    m1_model: km.KarrMetabolismModel,
    m2_model: tx.KarrTranscriptionModel,
    m3_model: tl.KarrTranslationModel,
) -> None:
    engine = build_karr_chassis_v4(m1_model, m2_model, m3_model, time_step_s=1.0, emit_step_s=10.0)
    start = time.perf_counter()
    engine.update(100.0)
    elapsed = time.perf_counter() - start
    ticks_per_s = 100.0 / max(elapsed, 1e-9)
    assert ticks_per_s > 5.0, f"tick_rate={ticks_per_s:.2f} ticks/s"


