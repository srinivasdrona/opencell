"""Tests for the real Karr D.2 macromolecular complexation process."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from opencell.vivarium.karr_d2_real import (
    KarrD2RealProcess,
    _closed_form_bounds,
    _per_cluster_mc,
)


def _load_snapshot_state(process: KarrD2RealProcess) -> dict[str, Any]:
    """Load or synthesize a realistic D.2 state snapshot for one tick tests.

    A dedicated D.2 snapshot fixture is not guaranteed in all worktrees, so this
    helper synthesizes stable, realistic integer counts from a seeded RNG.
    """
    rng = np.random.default_rng(20260522)
    substrate_counts = rng.integers(100, 1000, size=len(process.substrate_wids))

    return {
        "substrates": {
            wid: float(substrate_counts[idx]) for idx, wid in enumerate(process.substrate_wids)
        },
        "complex": {"counts": {wid: 0.0 for wid in process.complex_wids}},
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }


def test_fixture_loads() -> None:
    p = KarrD2RealProcess({})
    assert len(p.complex_wids) == 147
    assert len(p.substrate_wids) == 210
    assert p.complex_composition.shape == (210, 147)
    assert len(p.networks) == 2
    assert p.networks[0].shape == (206, 145)
    assert p.networks[1].shape == (4, 2)


def test_no_subunits_no_complexes() -> None:
    p = KarrD2RealProcess({})
    states = {
        "substrates": {wid: 0.0 for wid in p.substrate_wids},
        "complex": {"counts": {wid: 0.0 for wid in p.complex_wids}},
        "requests": {p.name: {wid: 0.0 for wid in p.substrate_wids}},
        "substrates_allocated": {p.name: {wid: 0.0 for wid in p.substrate_wids}},
    }

    update = p.next_update(1.0, states)
    assert update["complex"]["counts"] == {}
    assert update["substrates"] == {}


def test_mass_conservation() -> None:
    p = KarrD2RealProcess({"rng_seed": 42})
    states = _load_snapshot_state(p)
    update = p.next_update(1.0, states)

    formed = np.array(
        [int(update["complex"]["counts"].get(wid, 0.0)) for wid in p.complex_wids],
        dtype=np.int64,
    )
    delta_sub = np.array(
        [int(update["substrates"].get(wid, 0.0)) for wid in p.substrate_wids],
        dtype=np.int64,
    )
    expected = -(p.complex_composition @ formed)
    assert np.array_equal(delta_sub, expected)


def test_cluster1_closed_form() -> None:
    p = KarrD2RealProcess({"rng_seed": 0})
    states = _load_snapshot_state(p)
    update = p.next_update(1.0, states)

    formed = np.array(
        [int(update["complex"]["counts"].get(wid, 0.0)) for wid in p.complex_wids],
        dtype=np.int64,
    )
    c1_sub_mask = p.substrates2net == 1
    c1_cpx_mask = p.complexes2net == 1
    stoich1 = p.complex_composition[np.ix_(c1_sub_mask, c1_cpx_mask)]

    sub_avail = np.array(
        [int(states["substrates"][wid]) for wid in p.substrate_wids], dtype=np.int64
    )
    bounds = _closed_form_bounds(sub_avail[c1_sub_mask], stoich1)
    assert np.all(formed[c1_cpx_mask] <= bounds)


def test_cluster2_mc_deterministic() -> None:
    p1 = KarrD2RealProcess({"rng_seed": 42})
    s1 = _load_snapshot_state(p1)
    u1 = p1.next_update(1.0, s1)

    p2 = KarrD2RealProcess({"rng_seed": 42})
    s2 = _load_snapshot_state(p2)
    u2 = p2.next_update(1.0, s2)

    assert u1 == u2


def test_ub_zero_safety_filter() -> None:
    stoich = np.array([[1, 2], [1, 0]], dtype=np.int64)
    sub_avail = np.array([5, 0], dtype=np.int64)

    rng = np.random.default_rng(0)
    formed = _per_cluster_mc(sub_avail, stoich, rng, rate_constant=1.0)
    assert formed[0] == 0
    assert formed[1] > 0


def test_one_tick_from_snapshot() -> None:
    p = KarrD2RealProcess({"rng_seed": 0})
    states = _load_snapshot_state(p)
    update = p.next_update(1.0, states)

    total_formed = sum(update["complex"]["counts"].values())
    assert total_formed > 0.0


def test_integration_with_allocation_step() -> None:
    pytest.importorskip("opencell.vivarium.karr_allocation_step")
    from opencell.vivarium.karr_allocation_step import KarrAllocationStep

    p = KarrD2RealProcess({"rng_seed": 0})
    snapshot = _load_snapshot_state(p)

    alloc_step = KarrAllocationStep(
        {
            "consumer_processes": [(p.name, list(p.substrate_wids))],
            "substrate_wids": list(p.substrate_wids),
        }
    )
    alloc_input = {
        "substrates": dict(snapshot["substrates"]),
        "requests": {p.name: {wid: 0.0 for wid in p.substrate_wids}},
        "substrates_allocated": {p.name: {wid: 0.0 for wid in p.substrate_wids}},
    }
    alloc_update = alloc_step.next_update(1.0, alloc_input)

    allocated = alloc_update.get("substrates_allocated", {}).get(p.name, {})
    assert all(float(allocated.get(wid, 0.0)) == 0.0 for wid in p.substrate_wids)

    snapshot["substrates_allocated"] = {
        p.name: {wid: float(allocated.get(wid, 0.0)) for wid in p.substrate_wids}
    }
    d2_update = p.next_update(1.0, snapshot)
    assert sum(d2_update["complex"]["counts"].values()) > 0.0
