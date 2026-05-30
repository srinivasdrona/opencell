from __future__ import annotations

from copy import deepcopy
import math
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

from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess
from opencell.vivarium.karr_composite import build_karr_chassis_v6


def _base_state(
    process: KarrDNASupercoilingProcess,
    *,
    sigma: float,
    replication_state: str = "idle",
    atp: float = 10_000.0,
    h2o: float | None = None,
    gyrase_count: float = 3.0,
    topoiv_count: float = 12.0,
) -> dict[str, Any]:
    protein_counts: dict[str, float] = {}
    complex_counts: dict[str, float] = {}
    for wid, count in (
        (process.gyrase_wid, gyrase_count),
        (process.topoiv_wid, topoiv_count),
    ):
        if process.enzyme_store_by_wid.get(wid) == "complex":
            complex_counts[wid] = float(count)
        else:
            protein_counts[wid] = float(count)

    substrates = {wid: 0.0 for wid in process.substrate_wids}
    substrates[process.atp_wid] = float(atp)
    substrates[process.h2o_wid] = float(atp if h2o is None else h2o)
    substrates[process.adp_wid] = 0.0
    substrates[process.pi_wid] = 0.0

    return {
        "chromosome": {
            "supercoil_density": float(sigma),
            "replication_state": replication_state,
            "supercoiled": sigma < 0.0,
        },
        "protein": {
            "counts": protein_counts
        },
        "complex": {"counts": complex_counts},
        "substrates": substrates,
        "requests": {
            process.name: {
                process.atp_wid: float(atp),
                process.h2o_wid: float(atp if h2o is None else h2o),
            }
        },
        "substrates_allocated": {
            process.name: {
                process.atp_wid: float(atp),
                process.h2o_wid: float(atp if h2o is None else h2o),
            }
        },
    }


def _apply_update(process: KarrDNASupercoilingProcess, state: dict[str, Any], update: dict[str, Any]) -> None:
    chrom_update = update.get("chromosome", {})
    if "supercoil_density" in chrom_update:
        state["chromosome"]["supercoil_density"] = float(
            state["chromosome"].get("supercoil_density", process.equilibrium_sigma)
            + float(chrom_update["supercoil_density"])
        )
    if "supercoiled" in chrom_update:
        state["chromosome"]["supercoiled"] = bool(chrom_update["supercoiled"])
    if "replication_state" in chrom_update:
        state["chromosome"]["replication_state"] = str(chrom_update["replication_state"])

    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0) + float(delta))

    for wid, delta in update.get("protein", {}).get("counts", {}).items():
        state["protein"]["counts"][wid] = float(
            state["protein"]["counts"].get(wid, 0.0) + float(delta)
        )

    if process.name in update.get("requests", {}):
        req_atp = float(update["requests"][process.name].get(process.atp_wid, 0.0))
        req_h2o = float(update["requests"][process.name].get(process.h2o_wid, 0.0))
        state["requests"][process.name][process.atp_wid] = req_atp
        state["requests"][process.name][process.h2o_wid] = req_h2o


def _advance_tick(process: KarrDNASupercoilingProcess, state: dict[str, Any]) -> dict[str, Any]:
    update = process.next_update(1.0, state)
    _apply_update(process, state, update)

    request_atp = max(0.0, float(state["requests"][process.name].get(process.atp_wid, 0.0)))
    request_h2o = max(0.0, float(state["requests"][process.name].get(process.h2o_wid, 0.0)))
    available_atp = max(0.0, float(state["substrates"].get(process.atp_wid, 0.0)))
    available_h2o = max(0.0, float(state["substrates"].get(process.h2o_wid, 0.0)))
    state["substrates_allocated"][process.name][process.atp_wid] = float(min(request_atp, available_atp))
    state["substrates_allocated"][process.name][process.h2o_wid] = float(
        min(request_h2o, available_h2o)
    )
    return update


def test_process_instantiates_with_defaults() -> None:
    p = KarrDNASupercoilingProcess({})
    assert p.name == "karr_dna_supercoiling"
    assert p.gyrase_wid == "DNA_GYRASE"
    assert p.topoiv_wid == "MG_203_204_TETRAMER"
    assert p.atp_wid == "ATP"
    assert p.h2o_wid == "H2O"
    assert p.gyrase_activity_rate > 0.0
    assert p.topoiv_activity_rate > 0.0
    assert p.equilibrium_sigma == pytest.approx(-0.06, rel=1e-6)


def test_declared_complex_enzymes_fail_fast_when_missing_from_complex_port() -> None:
    p = KarrDNASupercoilingProcess({})
    state = _base_state(
        p,
        sigma=-0.02,
        atp=10_000.0,
        gyrase_count=5.0,
        topoiv_count=5.0,
    )
    state_missing_complex = deepcopy(state)
    state_missing_complex["protein"]["counts"][p.gyrase_wid] = 5.0
    state_missing_complex["protein"]["counts"][p.topoiv_wid] = 5.0
    state_missing_complex["complex"]["counts"] = {}

    with pytest.raises(KeyError, match="Missing declared complex enzyme"):
        p.next_update(1.0, state_missing_complex)


def test_chassis_seeded_complex_enzyme_changes_request_output() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    topology = composite["topology"]["karr_dna_supercoiling"]
    assert "complex" in topology

    chassis_process = composite["processes"]["karr_dna_supercoiling"]
    gyrase_seed = float(composite["state"]["complex"]["counts"][chassis_process.gyrase_wid])
    assert gyrase_seed > 0.0

    p_with_seed = KarrDNASupercoilingProcess({"rng_seed": 23})
    p_without_seed = KarrDNASupercoilingProcess({"rng_seed": 23})
    state_with_seed = _base_state(
        p_with_seed,
        sigma=-0.02,
        atp=10_000.0,
        gyrase_count=gyrase_seed,
        topoiv_count=0.0,
    )
    state_without_seed = _base_state(
        p_without_seed,
        sigma=-0.02,
        atp=10_000.0,
        gyrase_count=0.0,
        topoiv_count=0.0,
    )

    update_with_seed = p_with_seed.next_update(1.0, state_with_seed)
    update_without_seed = p_without_seed.next_update(1.0, state_without_seed)
    request_with_seed = float(update_with_seed["requests"][p_with_seed.name][p_with_seed.atp_wid])
    request_without_seed = float(
        update_without_seed["requests"][p_without_seed.name][p_without_seed.atp_wid]
    )
    assert request_with_seed > request_without_seed


def test_one_tick_gyrase_sign() -> None:
    p = KarrDNASupercoilingProcess(
        {
            "rng_seed": 3,
            "gyrase_activity_rate": 4.0,
            "topoiv_activity_rate": 0.05,
            "reference_gyrase_count": 1.0,
            "reference_topoiv_count": 1.0,
            "chromosome_length_bp": 10_500.0,
        }
    )
    state = _base_state(
        p,
        sigma=-0.01,
        atp=1_000.0,
        gyrase_count=20.0,
        topoiv_count=1.0,
    )
    update = p.next_update(1.0, state)

    sigma_delta = float(update.get("chromosome", {}).get("supercoil_density", 0.0))
    assert sigma_delta < 0.0


def test_allocation_contract_bounds_atp_use() -> None:
    p = KarrDNASupercoilingProcess(
        {
            "rng_seed": 1,
            "gyrase_activity_rate": 8.0,
            "topoiv_activity_rate": 8.0,
            "reference_gyrase_count": 1.0,
            "reference_topoiv_count": 1.0,
        }
    )
    state = _base_state(
        p,
        sigma=-0.02,
        atp=2.0,
        gyrase_count=30.0,
        topoiv_count=30.0,
    )
    state["substrates_allocated"][p.name][p.atp_wid] = 2.0

    update = p.next_update(1.0, state)
    atp_delta = float(update.get("substrates", {}).get(p.atp_wid, 0.0))

    assert atp_delta >= -2.0
    assert atp_delta <= 0.0
    process_request = float(update["requests"][p.name][p.atp_wid])
    assert process_request >= 0.0


def test_replication_elongating_increases_gyrase_request() -> None:
    p_idle = KarrDNASupercoilingProcess({"rng_seed": 9})
    p_elong = KarrDNASupercoilingProcess({"rng_seed": 9})

    idle_state = _base_state(p_idle, sigma=-0.06, replication_state="idle")
    elong_state = _base_state(p_elong, sigma=-0.06, replication_state="elongating")

    idle_update = p_idle.next_update(1.0, idle_state)
    elong_update = p_elong.next_update(1.0, elong_state)

    idle_req = float(idle_update["requests"][p_idle.name][p_idle.atp_wid])
    elong_req = float(elong_update["requests"][p_elong.name][p_elong.atp_wid])
    assert elong_req >= idle_req


def test_100tick_steady_state_near_karr_sigma() -> None:
    p = KarrDNASupercoilingProcess({"rng_seed": 11})
    state = _base_state(
        p,
        sigma=-0.06,
        atp=250_000.0,
        gyrase_count=3.0,
        topoiv_count=12.0,
    )

    sigma_values = [float(state["chromosome"]["supercoil_density"])]
    for _ in range(100):
        _advance_tick(p, state)
        sigma_values.append(float(state["chromosome"]["supercoil_density"]))

    target = abs(float(p.equilibrium_sigma))
    mean_abs_sigma = sum(abs(v) for v in sigma_values[-50:]) / 50.0
    assert mean_abs_sigma == pytest.approx(target, rel=0.10)


def test_no_nan_or_negative_regressions() -> None:
    p = KarrDNASupercoilingProcess({"rng_seed": 13})
    state = _base_state(
        p,
        sigma=-0.06,
        atp=100_000.0,
        replication_state="elongating",
        gyrase_count=8.0,
        topoiv_count=8.0,
    )

    for _ in range(120):
        _advance_tick(p, state)

    sigma = float(state["chromosome"]["supercoil_density"])
    assert math.isfinite(sigma)
    for wid, value in state["substrates"].items():
        assert math.isfinite(float(value))
        assert float(value) >= 0.0, f"negative substrate {wid}: {value}"
