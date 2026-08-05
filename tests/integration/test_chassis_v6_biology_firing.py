from __future__ import annotations

import random
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

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

from opencell.vivarium.karr_composite import build_karr_chassis_v6

SIM_DURATION_S = 5_000.0
TIME_STEP_S = 1.0
RNG_SEED = 0

CORE_SUBSTRATES: tuple[str, ...] = ("AD", "URA", "ATP", "GTP", "H2O")
ORIC_SITE_KEYS: tuple[str, ...] = ("R1", "R2", "R3", "R4", "R5")
ATP_BURN_IN_TICKS = 10
C1_PERTURB_WARMUP_TICKS = 50
C1_PERTURB_PULSE_TICKS = 40
C1_PERTURB_RECOVERY_TICKS = 40
C1_PERTURB_ATP_DRAIN_PER_TICK = 100.0
C1_PERTURB_MIN_ATP_DROP = 100.0
# Stationarity tolerance for the pre- and post-pulse windows. Metabolism is now
# allocator-mediated (Track-A A2 enrollment), so ATP no longer settles to a
# bit-identical steady state in the absence of perturbation; tiny redistribution
# through the allocator request matrix produces ~1-molecule drift per tick on a
# count of ~10^8. 2.0 molecules/tick is 50x smaller than C1_PERTURB_MIN_ATP_DROP
# (100/tick), preserving the SNR of the pulse-response signal we actually care
# about, while accepting that pre/recovery windows are no longer bit-stationary.
C1_PERTURB_STATIONARY_TOLERANCE = 2.0

# Canonical DnaA keys were inspected from chassis_v6 t=0 state.
DNAA_RNA_KEY = "MG_469"
DNAA_PROTEIN_KEY = "MG_469_MONOMER"


class BiologyTimeseries(TypedDict):
    atp: np.ndarray
    dnaa_rna: np.ndarray
    dnaa_protein: np.ndarray
    oric_bound_total: np.ndarray


@dataclass(frozen=True)
class BiologyRun:
    engine: Engine
    initial_state: dict[str, Any]
    final_state: dict[str, Any]


_TIMESERIES_BY_ENGINE_ID: dict[int, BiologyTimeseries] = {}


def _build_engine(*, karr_parity_mode: bool = True) -> Engine:
    random.seed(RNG_SEED)
    np.random.seed(RNG_SEED)
    composite = build_karr_chassis_v6(
        time_step_s=TIME_STEP_S,
        emit_step_s=TIME_STEP_S,
        karr_parity_mode=karr_parity_mode,
    )
    return Engine(composite=composite, emit_step=TIME_STEP_S, display_info=False)


def _final_state(engine: Engine) -> dict[str, Any]:
    return engine.state.get_value()


def _timeseries(engine: Engine) -> BiologyTimeseries:
    series = _TIMESERIES_BY_ENGINE_ID.get(id(engine))
    if series is None:
        raise RuntimeError("No cached biology timeseries found for this engine instance")
    return series


def _run_c1_atp_demand_pulse(*, karr_parity_mode: bool) -> np.ndarray:
    """Inject deterministic ATP demand and capture ATP response over warm-up/pulse/recovery."""
    engine = _build_engine(karr_parity_mode=karr_parity_mode)
    atp_series: list[float] = [float(_final_state(engine)["substrates"]["ATP"])]

    total_ticks = C1_PERTURB_WARMUP_TICKS + C1_PERTURB_PULSE_TICKS + C1_PERTURB_RECOVERY_TICKS
    pulse_end = C1_PERTURB_WARMUP_TICKS + C1_PERTURB_PULSE_TICKS

    for tick in range(total_ticks):
        if C1_PERTURB_WARMUP_TICKS <= tick < pulse_end:
            cur_atp = float(_final_state(engine)["substrates"]["ATP"])
            drained = min(C1_PERTURB_ATP_DRAIN_PER_TICK, cur_atp)
            if drained > 0.0:
                engine.state.set_value({"substrates": {"ATP": cur_atp - drained}})
        engine.update(TIME_STEP_S)
        atp_series.append(float(_final_state(engine)["substrates"]["ATP"]))

    return np.asarray(atp_series, dtype=np.float64)


def _oric_r1_r5_total(state: dict[str, Any]) -> float:
    dnaa_complex_count = state["chromosome"]["dnaa_complex_count"]
    return float(sum(float(dnaa_complex_count.get(site_id, 0.0)) for site_id in ORIC_SITE_KEYS))


@pytest.fixture(scope="module")
def biology_run() -> BiologyRun:
    """Run a deterministic 5,000-second chassis_v6 simulation once for all biology checks."""
    engine = _build_engine()
    initial_state = deepcopy(_final_state(engine))

    atp_series: list[float] = [float(initial_state["substrates"]["ATP"])]
    dnaa_rna_series: list[float] = [float(initial_state["rna"]["counts"].get(DNAA_RNA_KEY, 0.0))]
    dnaa_protein_series: list[float] = [
        float(initial_state["protein"]["counts"].get(DNAA_PROTEIN_KEY, 0.0))
    ]
    oric_bound_series: list[float] = [_oric_r1_r5_total(initial_state)]

    n_ticks = int(SIM_DURATION_S / TIME_STEP_S)
    for _ in range(n_ticks):
        engine.update(TIME_STEP_S)
        state = _final_state(engine)
        atp_series.append(float(state["substrates"]["ATP"]))
        dnaa_rna_series.append(float(state["rna"]["counts"].get(DNAA_RNA_KEY, 0.0)))
        dnaa_protein_series.append(float(state["protein"]["counts"].get(DNAA_PROTEIN_KEY, 0.0)))
        oric_bound_series.append(_oric_r1_r5_total(state))

    _TIMESERIES_BY_ENGINE_ID[id(engine)] = {
        "atp": np.asarray(atp_series, dtype=np.float64),
        "dnaa_rna": np.asarray(dnaa_rna_series, dtype=np.float64),
        "dnaa_protein": np.asarray(dnaa_protein_series, dtype=np.float64),
        "oric_bound_total": np.asarray(oric_bound_series, dtype=np.float64),
    }
    return BiologyRun(
        engine=engine,
        initial_state=initial_state,
        final_state=deepcopy(_final_state(engine)),
    )


def test_a1_central_dogma_transcription_generates_new_mrna(biology_run: BiologyRun) -> None:
    """A1: catches non-firing transcription that only decays/reshuffles pre-seeded RNA pools."""
    initial_counts = biology_run.initial_state["rna"]["counts"]
    final_counts = biology_run.final_state["rna"]["counts"]

    newly_expressed = [
        rna_id
        for rna_id, initial_value in initial_counts.items()
        if float(initial_value) <= 0.0 and float(final_counts.get(rna_id, 0.0)) > 0.0
    ]
    final_positive_total = sum(1 for value in final_counts.values() if float(value) > 0.0)

    assert newly_expressed, (
        "A1 central dogma check failed: no previously absent mRNA species became >0 "
        f"by t={SIM_DURATION_S:.0f}s; newly_expressed={len(newly_expressed)}, "
        f"final_positive_total={final_positive_total}."
    )


def test_a2_central_dogma_translation_increases_output_pool(biology_run: BiologyRun) -> None:
    """A2: catches non-firing translation by requiring growth in `protein.unprocessed_counts`."""
    initial_protein = biology_run.initial_state["protein"]
    final_protein = biology_run.final_state["protein"]

    output_pool_increased = [
        protein_id
        for protein_id, initial_value in initial_protein["unprocessed_counts"].items()
        if float(final_protein["unprocessed_counts"].get(protein_id, 0.0)) > float(initial_value)
    ]
    mature_pool_increased = [
        protein_id
        for protein_id, initial_value in initial_protein["counts"].items()
        if float(final_protein["counts"].get(protein_id, 0.0)) > float(initial_value)
    ]

    assert output_pool_increased, (
        "A2 central dogma check failed: translation output pool `protein.unprocessed_counts` "
        "never increased (no direct evidence of new protein synthesis). "
        f"output_pool_increased={len(output_pool_increased)}, "
        f"mature_pool_increased={len(mature_pool_increased)}."
    )


def test_a3_central_dogma_dnaa_expression_occurs(biology_run: BiologyRun) -> None:
    """A3: catches silent replication-gate expression (`MG_469` / `MG_469_MONOMER` stays zero)."""
    series = _timeseries(biology_run.engine)
    max_dnaa_rna = float(np.max(series["dnaa_rna"]))
    max_dnaa_protein = float(np.max(series["dnaa_protein"]))

    assert max_dnaa_rna > 0.0 or max_dnaa_protein > 0.0, (
        "A3 central dogma check failed: DnaA expression never appeared over 5,000s; "
        f"max_{DNAA_RNA_KEY}={max_dnaa_rna:.6g}, "
        f"max_{DNAA_PROTEIN_KEY}={max_dnaa_protein:.6g}."
    )


def test_b1_substrate_sanity_no_negative_core_substrates(biology_run: BiologyRun) -> None:
    """B1: catches accumulate+default drain bugs that drive key metabolites below zero."""
    final_substrates = biology_run.final_state["substrates"]
    core_values = {sid: float(final_substrates.get(sid, np.nan)) for sid in CORE_SUBSTRATES}
    negative = {sid: value for sid, value in core_values.items() if value < 0.0}

    assert not negative, (
        "B1 substrate sanity check failed: core substrates dropped below zero; "
        f"values={core_values}."
    )


def test_b2_substrate_sanity_core_initialization_not_all_unit_values(
    biology_run: BiologyRun,
) -> None:
    """B2: catches `_default: 1.0` initialization of biologically central substrates."""
    initial_substrates = biology_run.initial_state["substrates"]
    core_initial = {sid: float(initial_substrates.get(sid, np.nan)) for sid in CORE_SUBSTRATES}
    max_core_initial = max(core_initial.values())

    assert max_core_initial > 100.0, (
        "B2 substrate sanity check failed: no core substrate started above 100 at t=0; "
        f"core_initial={core_initial}."
    )


@pytest.mark.parametrize("karr_parity_mode", [True, False], ids=["parity_true", "parity_false"])
def test_c1_metabolism_responds_to_atp_demand_under_karr_parity(karr_parity_mode: bool) -> None:
    """C1-Karr-valid: ATP should move during injected demand pulse, not in isolated steady state."""
    atp = _run_c1_atp_demand_pulse(karr_parity_mode=karr_parity_mode)
    warmup_end = C1_PERTURB_WARMUP_TICKS
    pulse_end = C1_PERTURB_WARMUP_TICKS + C1_PERTURB_PULSE_TICKS

    assert atp.size > pulse_end + 1, (
        "C1 demand-pulse setup failed: ATP timeseries shorter than pulse boundary; "
        f"len={atp.size}, pulse_end={pulse_end}."
    )

    pre_delta = np.diff(atp[ATP_BURN_IN_TICKS : warmup_end + 1])
    pulse_delta = np.diff(atp[warmup_end : pulse_end + 1])
    recovery_delta = np.diff(atp[pulse_end:])
    atp_before_pulse = float(atp[warmup_end])
    atp_after_pulse = float(atp[pulse_end])
    atp_drop = atp_before_pulse - atp_after_pulse

    assert float(np.max(np.abs(pre_delta))) <= C1_PERTURB_STATIONARY_TOLERANCE, (
        "C1 demand-pulse baseline failed: ATP moved before perturbation window; "
        f"max_abs_pre_delta={float(np.max(np.abs(pre_delta))):.12g}, "
        f"tolerance={C1_PERTURB_STATIONARY_TOLERANCE:.12g}."
    )
    assert np.any(pulse_delta < 0.0), (
        "C1 demand-pulse response failed: ATP never decreased during perturbation window; "
        f"first_pulse_delta={float(pulse_delta[0]):.12g}, "
        f"last_pulse_delta={float(pulse_delta[-1]):.12g}."
    )
    assert atp_drop >= C1_PERTURB_MIN_ATP_DROP, (
        "C1 demand-pulse response failed: ATP drop during perturbation was too small; "
        f"drop={atp_drop:.12g}, expected_min={C1_PERTURB_MIN_ATP_DROP:.12g}, "
        f"atp_before={atp_before_pulse:.12g}, atp_after={atp_after_pulse:.12g}."
    )
    assert float(np.max(np.abs(recovery_delta))) <= C1_PERTURB_STATIONARY_TOLERANCE, (
        "C1 demand-pulse recovery failed: ATP did not settle after perturbation window; "
        f"max_abs_recovery_delta={float(np.max(np.abs(recovery_delta))):.12g}, "
        f"tolerance={C1_PERTURB_STATIONARY_TOLERANCE:.12g}."
    )


@pytest.mark.xfail(
    strict=False,
    reason="Requires DnaA expression + activation; tracked separately",
)
def test_d1_replication_gate_dnaa_binds_oric_sites_r1_to_r5(biology_run: BiologyRun) -> None:
    """D1 (loose gate): keep oriC occupancy assertion present so future fixes can un-xfail it."""
    oric_bound_total = _timeseries(biology_run.engine)["oric_bound_total"]
    max_oric_bound_total = float(np.max(oric_bound_total))

    assert max_oric_bound_total > 0.0, (
        "D1 replication-gate check failed: no DnaA occupancy observed at oriC R1-R5; "
        f"max_R1_to_R5_total={max_oric_bound_total:.6g}."
    )
