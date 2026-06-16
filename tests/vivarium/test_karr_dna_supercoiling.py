from __future__ import annotations

from copy import deepcopy
import math
import sys
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

from opencell.state.chromosome_store import SparseTriplet
from opencell.vivarium.karr_composite import build_karr_chassis_v6
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess


def _base_state(
    process: KarrDNASupercoilingProcess,
    *,
    sigma: float,
    replication_state: str = "idle",
    atp: float = 10_000.0,
    h2o: float | None = None,
    gyrase_count: float = 3.0,
    topoiv_count: float = 12.0,
    topoi_count: float = 1.0,
) -> dict[str, Any]:
    protein_counts: dict[str, float] = {}
    complex_counts: dict[str, float] = {}
    for wid, count in (
        (process.gyrase_wid, gyrase_count),
        (process.topoiv_wid, topoiv_count),
        (process.topoi_wid, topoi_count),
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
        "chromosome": process.build_default_chromosome_state(
            sigma=sigma,
            replication_state=replication_state,
        ),
        "protein": {"counts": protein_counts},
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
        "boundEnzymes": {},
    }


def _apply_update(
    process: KarrDNASupercoilingProcess,
    state: dict[str, Any],
    update: dict[str, Any],
) -> None:
    chrom_update = update.get("chromosome", {})
    if "linkingNumbers" in chrom_update:
        state["chromosome"]["linkingNumbers"] = SparseTriplet.from_state(
            chrom_update["linkingNumbers"],
            shape=process.chromosome_shape,
        ).to_state()
    if "supercoil_density" in chrom_update:
        state["chromosome"]["supercoil_density"] = float(chrom_update["supercoil_density"])
    if "supercoiled" in chrom_update:
        state["chromosome"]["supercoiled"] = bool(chrom_update["supercoiled"])
    if "replication_state" in chrom_update:
        state["chromosome"]["replication_state"] = str(chrom_update["replication_state"])

    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0) + float(delta))

    for channel in ("protein", "complex"):
        counts = update.get(channel, {}).get("counts", {})
        if counts:
            bucket = state.setdefault(channel, {}).setdefault("counts", {})
            for wid, delta in counts.items():
                bucket[wid] = float(bucket.get(wid, 0.0) + float(delta))

    for channel in ("enzymes", "boundEnzymes"):
        deltas = update.get(channel, {})
        if deltas:
            bucket = state.setdefault(channel, {})
            for wid, delta in deltas.items():
                bucket[wid] = float(bucket.get(wid, 0.0) + float(delta))

    if process.name in update.get("requests", {}):
        req = update["requests"][process.name]
        state["requests"][process.name][process.atp_wid] = float(req.get(process.atp_wid, 0.0))
        state["requests"][process.name][process.h2o_wid] = float(req.get(process.h2o_wid, 0.0))


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
    process = KarrDNASupercoilingProcess({})
    assert process.name == "karr_dna_supercoiling"
    assert process.gyrase_wid == "DNA_GYRASE"
    assert process.topoiv_wid == "MG_203_204_TETRAMER"
    assert process.topoi_wid == "MG_122_MONOMER"
    assert process.atp_wid == "ATP"
    assert process.h2o_wid == "H2O"
    assert process.gyrase_activity_rate > 0.0
    assert process.topoiv_activity_rate > 0.0
    assert process.topoi_activity_rate > 0.0
    schema = process.ports_schema()["chromosome"]
    assert schema["linkingNumbers"]["positions"]["_updater"] == "set"
    assert schema["polymerizedRegions"]["positions"]["_updater"] == "set"


def test_declared_complex_enzymes_fail_fast_when_missing_from_complex_port() -> None:
    process = KarrDNASupercoilingProcess({})
    state = _base_state(
        process,
        sigma=-0.02,
        atp=10_000.0,
        gyrase_count=5.0,
        topoiv_count=5.0,
    )
    state_missing_complex = deepcopy(state)
    state_missing_complex["protein"]["counts"][process.gyrase_wid] = 5.0
    state_missing_complex["protein"]["counts"][process.topoiv_wid] = 5.0
    state_missing_complex["complex"]["counts"] = {}

    with pytest.raises(KeyError, match="Missing declared complex enzyme"):
        process.next_update(1.0, state_missing_complex)


def test_chassis_seeded_complex_enzyme_changes_request_output() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    topology = composite["topology"]["karr_dna_supercoiling"]
    assert "complex" in topology

    chassis_process = composite["processes"]["karr_dna_supercoiling"]
    gyrase_seed = float(composite["state"]["complex"]["counts"][chassis_process.gyrase_wid])
    assert gyrase_seed > 0.0

    with_seed = KarrDNASupercoilingProcess({"rng_seed": 23})
    without_seed = KarrDNASupercoilingProcess({"rng_seed": 23})
    state_with_seed = _base_state(
        with_seed,
        sigma=-0.02,
        atp=10_000.0,
        gyrase_count=gyrase_seed,
        topoiv_count=0.0,
        topoi_count=0.0,
    )
    state_without_seed = _base_state(
        without_seed,
        sigma=-0.02,
        atp=10_000.0,
        gyrase_count=0.0,
        topoiv_count=0.0,
        topoi_count=0.0,
    )

    update_with_seed = with_seed.next_update(1.0, state_with_seed)
    update_without_seed = without_seed.next_update(1.0, state_without_seed)
    request_with_seed = float(update_with_seed["requests"][with_seed.name][with_seed.atp_wid])
    request_without_seed = float(update_without_seed["requests"][without_seed.name][without_seed.atp_wid])
    assert request_with_seed > request_without_seed


def test_one_tick_gyrase_sign_updates_sparse_linking_numbers() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "rng_seed": 3,
            "gyrase_activity_rate": 4.0,
            "topoiv_activity_rate": 0.0,
            "topoi_activity_rate": 0.0,
            "reference_gyrase_count": 1.0,
            "reference_topoiv_count": 1.0,
            "chromosome_length_bp": 10_500.0,
        }
    )
    state = _base_state(
        process,
        sigma=-0.01,
        atp=1_000.0,
        gyrase_count=20.0,
        topoiv_count=0.0,
        topoi_count=0.0,
    )
    before = SparseTriplet.from_state(state["chromosome"]["linkingNumbers"], shape=process.chromosome_shape)
    update = process.next_update(1.0, state)
    after = SparseTriplet.from_state(update["chromosome"]["linkingNumbers"], shape=process.chromosome_shape)

    assert int(after.values.sum()) < int(before.values.sum())
    assert float(update["chromosome"]["supercoil_density"]) < float(state["chromosome"]["supercoil_density"])


def test_allocation_contract_bounds_atp_use() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "rng_seed": 1,
            "gyrase_activity_rate": 8.0,
            "topoiv_activity_rate": 8.0,
            "topoi_activity_rate": 0.0,
            "reference_gyrase_count": 1.0,
            "reference_topoiv_count": 1.0,
        }
    )
    state = _base_state(
        process,
        sigma=-0.02,
        atp=2.0,
        gyrase_count=30.0,
        topoiv_count=30.0,
        topoi_count=0.0,
    )
    state["substrates_allocated"][process.name][process.atp_wid] = 2.0
    state["substrates_allocated"][process.name][process.h2o_wid] = 2.0

    update = process.next_update(1.0, state)
    atp_delta = float(update.get("substrates", {}).get(process.atp_wid, 0.0))

    assert atp_delta >= -2.0
    assert atp_delta <= 0.0
    assert float(update["requests"][process.name][process.atp_wid]) >= 0.0


def test_replication_elongating_increases_gyrase_request() -> None:
    idle = KarrDNASupercoilingProcess({"rng_seed": 9})
    elong = KarrDNASupercoilingProcess({"rng_seed": 9})

    idle_state = _base_state(idle, sigma=-0.06, replication_state="idle")
    elong_state = _base_state(elong, sigma=-0.06, replication_state="elongating")

    idle_update = idle.next_update(1.0, idle_state)
    elong_update = elong.next_update(1.0, elong_state)

    idle_req = float(idle_update["requests"][idle.name][idle.atp_wid])
    elong_req = float(elong_update["requests"][elong.name][elong.atp_wid])
    assert elong_req >= idle_req


def test_100tick_steady_state_near_karr_sigma() -> None:
    process = KarrDNASupercoilingProcess({"rng_seed": 11})
    state = _base_state(
        process,
        sigma=-0.06,
        atp=250_000.0,
        gyrase_count=3.0,
        topoiv_count=12.0,
        topoi_count=1.0,
    )

    sigma_values = [float(state["chromosome"]["supercoil_density"])]
    for _ in range(100):
        _advance_tick(process, state)
        sigma_values.append(float(state["chromosome"]["supercoil_density"]))

    target = abs(float(process.equilibrium_sigma))
    mean_abs_sigma = sum(abs(value) for value in sigma_values[-50:]) / 50.0
    assert mean_abs_sigma == pytest.approx(target, rel=0.20)


def test_no_nan_or_negative_regressions() -> None:
    process = KarrDNASupercoilingProcess({"rng_seed": 13})
    state = _base_state(
        process,
        sigma=-0.06,
        atp=100_000.0,
        replication_state="elongating",
        gyrase_count=8.0,
        topoiv_count=8.0,
        topoi_count=2.0,
    )

    for _ in range(120):
        _advance_tick(process, state)

    sigma = float(state["chromosome"]["supercoil_density"])
    assert math.isfinite(sigma)
    linking = SparseTriplet.from_state(state["chromosome"]["linkingNumbers"], shape=process.chromosome_shape)
    assert np.isfinite(linking.values.astype(float)).all()
    for wid, value in state["substrates"].items():
        assert math.isfinite(float(value))
        assert float(value) >= 0.0, f"negative substrate {wid}: {value}"
