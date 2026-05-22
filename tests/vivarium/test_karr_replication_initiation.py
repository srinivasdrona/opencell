from __future__ import annotations

import sys
from copy import deepcopy
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

from opencell.vivarium.karr_replication_initiation import KarrReplicationInitiationProcess


def _base_state(
    process: KarrReplicationInitiationProcess,
    *,
    free_dnaa: float,
    atp: float,
    supercoiled: bool = True,
) -> dict[str, Any]:
    return {
        "chromosome": {
            "dnaa_complex_count": {site_id: 0 for site_id in process.all_dnaa_sites},
            "replication_state": "idle",
            "supercoiled": supercoiled,
        },
        "protein": {"counts": {process.dnaa_wid: float(free_dnaa)}},
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "requests": {process.name: {process.atp_wid: 0.0, process.water_wid: 0.0}},
        "substrates_allocated": {
            process.name: {process.atp_wid: float(atp), process.water_wid: float(atp)}
        },
    }


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    for site_id, delta in update.get("chromosome", {}).get("dnaa_complex_count", {}).items():
        state["chromosome"]["dnaa_complex_count"][site_id] = int(
            state["chromosome"]["dnaa_complex_count"].get(site_id, 0) + int(delta)
        )
    if "replication_state" in update.get("chromosome", {}):
        state["chromosome"]["replication_state"] = str(update["chromosome"]["replication_state"])

    for wid, delta in update.get("protein", {}).get("counts", {}).items():
        current = float(state["protein"]["counts"].get(wid, 0.0))
        state["protein"]["counts"][wid] = float(current + float(delta))

    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0) + float(delta))
        state["substrates_allocated"][next(iter(state["substrates_allocated"]))][wid] = float(
            state["substrates"][wid]
        )


def _sum_oric(state: dict[str, Any], process: KarrReplicationInitiationProcess) -> int:
    return int(
        sum(
            int(state["chromosome"]["dnaa_complex_count"].get(site_id, 0))
            for site_id in process.oric_site_ids
        )
    )


def _ticks_to_initiation(
    process: KarrReplicationInitiationProcess,
    state: dict[str, Any],
    *,
    max_ticks: int = 200,
) -> int | None:
    for tick in range(1, max_ticks + 1):
        update = process.next_update(1.0, state)
        _apply_update(state, update)
        if state["chromosome"]["replication_state"] == "initiating":
            return tick
    return None


def test_fixture_loads() -> None:
    p = KarrReplicationInitiationProcess({})
    assert p.name == "karr_replication_initiation"
    assert p.dnaa_wid == "MG_469_MONOMER"
    assert len(p.all_dnaa_sites) >= 2_000
    assert p.oric_site_ids == ["R1", "R2", "R3", "R4", "R5"]
    assert p.kb_atp > p.kb_adp > 0
    assert p.kd_atp > 0
    assert p.k_regen > 0


def test_zero_free_dnaa_no_activity() -> None:
    p = KarrReplicationInitiationProcess({"rng_seed": 7})
    state = _base_state(p, free_dnaa=0.0, atp=10_000.0, supercoiled=True)
    update = p.next_update(1.0, state)
    assert update.get("chromosome", {}).get("dnaa_complex_count", {}) == {}
    assert p.atp_wid not in update.get("substrates", {})


def test_activation_consumes_atp() -> None:
    p = KarrReplicationInitiationProcess(
        {
            "rng_seed": 1,
            "binding_rate_scale": 1.0e12,
            "polymerization_rate_scale": 1.0e12,
            "release_rate_scale": 1.0e12,
            "inactivation_rate_scale": 1.0e24,
            "regen_rate_scale": 1.0e12,
        }
    )
    state = _base_state(p, free_dnaa=8.0, atp=100.0, supercoiled=False)
    update = p.next_update(1.0, state)
    assert update["substrates"][p.atp_wid] == pytest.approx(-8.0)


def test_polymer_growth_at_oric() -> None:
    p = KarrReplicationInitiationProcess(
        {
            "rng_seed": 3,
            "binding_rate_scale": 1.0e10,
            "polymerization_rate_scale": 150.0,
            "release_rate_scale": 1.0e12,
            "inactivation_rate_scale": 1.0e24,
            "regen_rate_scale": 1.0e12,
        }
    )
    state = _base_state(p, free_dnaa=180.0, atp=5_000.0, supercoiled=True)
    start_oric = _sum_oric(state, p)
    for _ in range(8):
        _apply_update(state, p.next_update(1.0, state))
    end_oric = _sum_oric(state, p)
    assert end_oric > start_oric
    assert any(state["chromosome"]["dnaa_complex_count"][sid] > 0 for sid in p.r1234_site_ids)


def test_initiation_trigger_fires() -> None:
    p = KarrReplicationInitiationProcess(
        {
            "rng_seed": 11,
            "binding_rate_scale": 1.0e10,
            "polymerization_rate_scale": 90.0,
            "release_rate_scale": 1.0e12,
            "inactivation_rate_scale": 1.0e24,
            "regen_rate_scale": 1.0e12,
            "r5_binding_boost": 100.0,
        }
    )
    state = _base_state(p, free_dnaa=260.0, atp=10_000.0, supercoiled=True)
    ticks = _ticks_to_initiation(p, state, max_ticks=50)
    assert ticks is not None
    assert state["chromosome"]["replication_state"] == "initiating"
    assert all(
        state["chromosome"]["dnaa_complex_count"][sid] >= int(p.parameters["r1234_threshold"])
        for sid in p.r1234_site_ids
    )
    assert state["chromosome"]["dnaa_complex_count"]["R5"] >= int(p.parameters["r5_threshold"])


def test_titration_effect() -> None:
    params = {
        "rng_seed": 13,
        "binding_rate_scale": 22_000.0,
        "polymerization_rate_scale": 220.0,
        "release_rate_scale": 1.0e12,
        "inactivation_rate_scale": 1.0e24,
        "regen_rate_scale": 1.0e12,
        "r5_binding_boost": 70.0,
    }
    p_lo = KarrReplicationInitiationProcess(params)
    p_hi = KarrReplicationInitiationProcess(params)

    low_titration = _base_state(p_lo, free_dnaa=260.0, atp=10_000.0, supercoiled=True)
    high_titration = _base_state(p_hi, free_dnaa=20.0, atp=10_000.0, supercoiled=True)
    for site_id in p_hi.non_oric_site_ids[:300]:
        high_titration["chromosome"]["dnaa_complex_count"][site_id] = 1

    ticks_low = _ticks_to_initiation(p_lo, low_titration, max_ticks=120)
    ticks_high = _ticks_to_initiation(p_hi, high_titration, max_ticks=120)
    assert ticks_low is not None
    assert ticks_high is None or ticks_high > ticks_low


def test_no_supercoil_no_polymerization() -> None:
    p = KarrReplicationInitiationProcess(
        {
            "rng_seed": 21,
            "binding_rate_scale": 1.0e12,
            "polymerization_rate_scale": 5.0,
            "release_rate_scale": 1.0e12,
            "inactivation_rate_scale": 1.0e24,
            "regen_rate_scale": 1.0e12,
        }
    )
    state = _base_state(p, free_dnaa=240.0, atp=5_000.0, supercoiled=False)
    for _ in range(10):
        _apply_update(state, p.next_update(1.0, state))
    assert all(state["chromosome"]["dnaa_complex_count"][sid] == 0 for sid in p.r1234_site_ids)


def test_deterministic_with_seed() -> None:
    params = {
        "rng_seed": 99,
        "binding_rate_scale": 40_000.0,
        "polymerization_rate_scale": 180.0,
        "release_rate_scale": 3_000.0,
        "inactivation_rate_scale": 5.0e15,
        "regen_rate_scale": 2_000.0,
    }
    p1 = KarrReplicationInitiationProcess(params)
    p2 = KarrReplicationInitiationProcess(params)
    s1 = _base_state(p1, free_dnaa=190.0, atp=8_000.0, supercoiled=True)
    s2 = deepcopy(s1)

    updates_1: list[dict[str, Any]] = []
    updates_2: list[dict[str, Any]] = []
    for _ in range(20):
        u1 = p1.next_update(1.0, s1)
        u2 = p2.next_update(1.0, s2)
        updates_1.append(u1)
        updates_2.append(u2)
        _apply_update(s1, u1)
        _apply_update(s2, u2)

    assert updates_1 == updates_2
    assert s1 == s2


def test_release_kinetics() -> None:
    p = KarrReplicationInitiationProcess(
        {
            "rng_seed": 5,
            "binding_rate_scale": 1.0e12,
            "polymerization_rate_scale": 1.0e12,
            "release_rate_scale": 8.0,
            "inactivation_rate_scale": 1.0e24,
            "regen_rate_scale": 1.0e12,
        }
    )
    state = _base_state(p, free_dnaa=0.0, atp=0.0, supercoiled=True)
    seeded_sites = ["R1", "R2", "R3", "R4", "R5"] + p.non_oric_site_ids[:15]
    for site_id in seeded_sites:
        state["chromosome"]["dnaa_complex_count"][site_id] = 4

    start_bound = sum(state["chromosome"]["dnaa_complex_count"][sid] for sid in seeded_sites)
    update = p.next_update(1.0, state)
    _apply_update(state, update)
    end_bound = sum(state["chromosome"]["dnaa_complex_count"][sid] for sid in seeded_sites)
    free_after = state["protein"]["counts"][p.dnaa_wid]

    assert end_bound < start_bound
    assert free_after > 0
