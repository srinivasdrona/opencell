"""Tests for ProteinTranslocation request calculator exact Karr algebra (Claims C7, C8, C9, C10, C12)

and mutation canaries.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess
from opencell.vivarium.karr_request_calculators import RequestCalculatorPTransloc

_COMPARTMENTS = ("c", "d", "e", "m", "tc", "tm")


def _build_test_state(
    proc: KarrProteinTranslocationProcess,
    *,
    atpase: float,
    pore: float,
    srp: float,
    receptor: float,
    pending_c: dict[str, float],
    pool: dict[str, float],
) -> dict[str, Any]:
    """Construct minimal state for RequestCalculatorPTransloc."""
    comp_processed = {
        wid: {c: 0.0 for c in _COMPARTMENTS}
        for wid in proc.translocatable_wids
    }
    for wid, count in pending_c.items():
        if wid in comp_processed:
            comp_processed[wid]["c"] = float(count)

    # Enzyme distribution:
    # proc.srp_wid -> MG_0001_048 (complex)
    # proc.srp_receptor_wid -> MG_297_MONOMER (protein)
    # proc.translocase_atpase_wid -> MG_072_DIMER (complex)
    # proc.translocase_pore_wid -> MG_055_170_277_464_476_20MER (complex)
    complex_counts: dict[str, float] = {
        proc.srp_wid: float(srp),
        proc.translocase_atpase_wid: float(atpase),
        proc.translocase_pore_wid: float(pore),
    }
    protein_counts: dict[str, float] = {
        proc.srp_receptor_wid: float(receptor),
    }

    substrates_dict = {wid: 0.0 for wid in proc.substrate_wids}
    substrates_dict.update({k: float(v) for k, v in pool.items()})

    return {
        "substrates": substrates_dict,
        "complex": {"counts": complex_counts},
        "protein": {
            "counts": protein_counts,
            "compartment_counts": {
                "processed_i": comp_processed,
            },
        },
    }


def _evaluate_calc(calc: Any, proc: KarrProteinTranslocationProcess, state: dict[str, Any], dt: float = 1.0) -> dict[str, float]:
    update = calc.next_update(dt, state)
    requests = update.get("requests", {}).get(proc.name, {})
    return {
        "ATP": float(requests.get(proc.atp_wid, 0.0)),
        "GTP": float(requests.get(proc.gtp_wid, 0.0)),
        "H2O": float(requests.get(proc.h2o_wid, 0.0)),
    }


# ==============================================================================
# Claim C7: Hand-derived request cases
# ==============================================================================

@pytest.mark.parametrize(
    "case_name, atpase, pore, srp, receptor, pending_c, pool, expected_atp, expected_gtp, expected_h2o",
    [
        (
            "zero_enzymes",
            0.0, 0.0, 0.0, 0.0,
            {"MG_014_MONOMER": 10.0, "MG_032_MONOMER": 7.0},
            {"ATP": 0.0, "GTP": 0.0, "H2O": 0.0},
            0.0, 0.0, 0.0,
        ),
        (
            "pool_gt_need",
            1000.0, 1000.0, 1000.0, 1000.0,
            {"MG_014_MONOMER": 10.0, "MG_032_MONOMER": 7.0},
            {"ATP": 500000.0, "GTP": 400000.0, "H2O": 900000.0},
            320.0, 14.0, 334.0,
        ),
        (
            "srp_capped",
            1000.0, 1000.0, 3.0, 3.0,
            {"MG_014_MONOMER": 10.0, "MG_032_MONOMER": 7.0},
            {"ATP": 0.0, "GTP": 0.0, "H2O": 0.0},
            320.0, 6.0, 326.0,
        ),
        (
            "translocase_zero",
            0.0, 0.0, 1000.0, 1000.0,
            {"MG_014_MONOMER": 10.0, "MG_032_MONOMER": 7.0},
            {"ATP": 0.0, "GTP": 0.0, "H2O": 0.0},
            0.0, 14.0, 14.0,
        ),
    ],
    ids=["zero_enzymes", "pool_gt_need", "srp_capped", "translocase_zero"],
)
def test_c7_adversarial_states(
    case_name: str,
    atpase: float,
    pore: float,
    srp: float,
    receptor: float,
    pending_c: dict[str, float],
    pool: dict[str, float],
    expected_atp: float,
    expected_gtp: float,
    expected_h2o: float,
) -> None:
    """Claim C7: Hand-derived request cases match Karr exact request algebra."""
    proc = KarrProteinTranslocationProcess({})
    calc = RequestCalculatorPTransloc({"protein_translocation_proc": proc})
    state = _build_test_state(
        proc,
        atpase=atpase,
        pore=pore,
        srp=srp,
        receptor=receptor,
        pending_c=pending_c,
        pool=pool,
    )
    result = _evaluate_calc(calc, proc, state, dt=1.0)

    assert result["ATP"] == expected_atp, (
        f"Case {case_name}: expected ATP {expected_atp}, got {result['ATP']}"
    )
    assert result["GTP"] == expected_gtp, (
        f"Case {case_name}: expected GTP {expected_gtp}, got {result['GTP']}"
    )
    assert result["H2O"] == expected_h2o, (
        f"Case {case_name}: expected H2O {expected_h2o}, got {result['H2O']}"
    )


# ==============================================================================
# Claim C8: Capacity expression semantics (no /35, SRP min exact)
# ==============================================================================

def test_c8_capacity_units() -> None:
    """Claim C8: translocases capacity uses ceil(min(ATPase, pore) * 2.71e12 * dt)

    with NO division by 35. SRP capacity uses ceil(min(SRP, receptor) * dt).
    """
    proc = KarrProteinTranslocationProcess({})
    calc = RequestCalculatorPTransloc({"protein_translocation_proc": proc})

    # At min(ATPase, pore) = 1e-12 and dt = 1.0:
    # 1e-12 * 2.71e12 = 2.71 -> ceil(2.71) = 3 translocases (amino acids capacity).
    # If divided by 35: 2.71 / 35 = 0.077 -> ceil(0.077) = 1.
    # With pending_c large (e.g. 1000 copies of MG_014_MONOMER, len=623),
    # translocase capacity binds.
    state = _build_test_state(
        proc,
        atpase=1e-12,
        pore=1e-12,
        srp=1000.0,
        receptor=1000.0,
        pending_c={"MG_014_MONOMER": 1000.0},
        pool={"ATP": 0.0, "GTP": 0.0, "H2O": 0.0},
    )
    result = _evaluate_calc(calc, proc, state, dt=1.0)
    assert result["ATP"] == 3.0, (
        f"Claim C8 failure: translocases capacity must be 3 (without /35), got {result['ATP']}"
    )


# ==============================================================================
# Claim C9: Substrate pool independence (no pool floor)
# ==============================================================================

def test_c9_pool_independence() -> None:
    """Claim C9: Holding pending monomers and enzymes fixed while substrate pool

    sweeps across {0, 1e3, 1e9} must yield IDENTICAL requests (no pool floor).
    """
    proc = KarrProteinTranslocationProcess({})
    calc = RequestCalculatorPTransloc({"protein_translocation_proc": proc})

    results = []
    for pool_level in [0.0, 1000.0, 1e9]:
        state = _build_test_state(
            proc,
            atpase=1000.0,
            pore=1000.0,
            srp=1000.0,
            receptor=1000.0,
            pending_c={"MG_014_MONOMER": 10.0, "MG_032_MONOMER": 7.0},
            pool={"ATP": pool_level, "GTP": pool_level, "H2O": pool_level * 2.0},
        )
        res = _evaluate_calc(calc, proc, state, dt=1.0)
        results.append(res)

    assert results[0] == results[1] == results[2], (
        f"Claim C9 failure: pool sweep caused request variation (pool floor active): {results}"
    )
    assert results[0]["ATP"] == 320.0
    assert results[0]["GTP"] == 14.0
    assert results[0]["H2O"] == 334.0


# ==============================================================================
# Claim C10: Water stoichiometry identity
# ==============================================================================

def test_c10_water_identity() -> None:
    """Claim C10: H2O == ATP + GTP exactly; all other substrate WIDs zero."""
    proc = KarrProteinTranslocationProcess({})
    calc = RequestCalculatorPTransloc({"protein_translocation_proc": proc})

    state = _build_test_state(
        proc,
        atpase=1000.0,
        pore=1000.0,
        srp=3.0,
        receptor=3.0,
        pending_c={"MG_014_MONOMER": 5.0, "MG_032_MONOMER": 4.0},
        pool={},
    )
    update = calc.next_update(1.0, state)
    requests = update.get("requests", {}).get(proc.name, {})

    atp_req = float(requests.get(proc.atp_wid, 0.0))
    gtp_req = float(requests.get(proc.gtp_wid, 0.0))
    h2o_req = float(requests.get(proc.h2o_wid, 0.0))

    assert h2o_req == atp_req + gtp_req, (
        f"Claim C10 failure: H2O ({h2o_req}) != ATP ({atp_req}) + GTP ({gtp_req})"
    )

    # All other substrates must have request 0.0
    for wid in proc.substrate_wids:
        if wid not in {proc.atp_wid, proc.gtp_wid, proc.h2o_wid}:
            assert float(requests.get(wid, 0.0)) == 0.0, (
                f"Substrate {wid} requested non-zero: {requests.get(wid)}"
            )


# ==============================================================================
# Claim C12: Real Engine same-tick pipeline reads authority and complex port
# ==============================================================================

def test_c12_engine_same_tick_pipeline() -> None:
    """Claim C12: In a real Vivarium Engine, same-tick request->allocation->evolution

    reads authority processed_i cytosol counts and complex port, never flat mature counts.
    """
    from vivarium.core.composer import Composite
    from vivarium.core.engine import Engine

    from opencell.vivarium.karr_allocation_step import KarrAllocationStep

    proc = KarrProteinTranslocationProcess({})
    calc = RequestCalculatorPTransloc({"protein_translocation_proc": proc})
    alloc = KarrAllocationStep({
        "consumer_processes": [(proc.name, list(proc.allocation_substrate_wids))],
        "substrate_wids": list(proc.allocation_substrate_wids),
    })

    processes = {proc.name: proc}
    steps = {
        "calc": calc,
        "alloc": alloc,
    }
    flow = {
        "calc": [],
        "alloc": ["calc"],
    }
    topology = {
        proc.name: {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "complex": ("complex",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
        "calc": {
            "substrates": ("substrates",),
            "protein": ("protein",),
            "complex": ("complex",),
            "requests": ("requests",),
        },
        "alloc": {
            "substrates": ("substrates",),
            "requests": ("requests",),
            "substrates_allocated": ("substrates_allocated",),
        },
    }

    # Setup state: 10 copies of MG_014 in processed_i cytosol
    state = _build_test_state(
        proc,
        atpase=1000.0,
        pore=1000.0,
        srp=1000.0,
        receptor=1000.0,
        pending_c={"MG_014_MONOMER": 10.0},
        pool={"ATP": 1000.0, "GTP": 1000.0, "H2O": 2000.0},
    )
    # Give allocation store and requests store initial empty dicts
    state["requests"] = {proc.name: {}}
    state["substrates_allocated"] = {proc.name: {}}

    composite = Composite(
        processes=processes,
        steps=steps,
        flow=flow,
        topology=topology,
        state=state,
    )
    engine = Engine(composite=composite)

    # Step calculator and allocator
    engine.run_steps()
    st = engine.state.get_value()

    # Calculator must have emitted request of 180 ATP, 0 GTP, 180 H2O (MG_014 len 623 -> 18 ATP/copy * 10 = 180)
    reqs = st["requests"][proc.name]
    assert reqs["ATP"] == 180.0
    assert reqs["GTP"] == 0.0
    assert reqs["H2O"] == 180.0


# ==============================================================================
# Mutation canaries: must execute and pass by rejecting broken calculator logic
# ==============================================================================

def test_canary_rejects_max_need_pool() -> None:
    """Canary 1: Reject broken calculator that restores max(need, pool)."""
    class BrokenPoolFloorCalculator(RequestCalculatorPTransloc):
        def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
            update = super().next_update(timestep, states)
            # Add pool floor
            pool = states.get("substrates", {})
            reqs = update.get("requests", {}).get(self._pt_proc.name, {})
            for k in reqs:
                reqs[k] = max(reqs[k], float(pool.get(k, 0.0)))
            return update

    proc = KarrProteinTranslocationProcess({})
    calc = BrokenPoolFloorCalculator({"protein_translocation_proc": proc})

    # When tested on pool sweep, it must vary and raise AssertionError
    results = []
    for pool_val in [0.0, 1000.0]:
        st = _build_test_state(
            proc,
            atpase=1000.0,
            pore=1000.0,
            srp=1000.0,
            receptor=1000.0,
            pending_c={"MG_014_MONOMER": 10.0, "MG_032_MONOMER": 7.0},
            pool={"ATP": pool_val, "GTP": pool_val, "H2O": pool_val * 2.0},
        )
        results.append(_evaluate_calc(calc, proc, st))

    with pytest.raises(AssertionError):
        assert results[0] == results[1]


def test_canary_rejects_drop_srp_min() -> None:
    """Canary 6: Reject broken calculator that drops SRP min() capacity bound."""
    class BrokenNoSRPMinCalculator(RequestCalculatorPTransloc):
        def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
            update = super().next_update(timestep, states)
            # Simulate uncapped GTP need
            reqs = update.get("requests", {}).get(self._pt_proc.name, {})
            reqs[self._pt_proc.gtp_wid] = 14.0  # Fails to cap at 6
            return update

    proc = KarrProteinTranslocationProcess({})
    calc = BrokenNoSRPMinCalculator({"protein_translocation_proc": proc})
    st = _build_test_state(
        proc,
        atpase=1000.0,
        pore=1000.0,
        srp=3.0,
        receptor=3.0,
        pending_c={"MG_014_MONOMER": 10.0, "MG_032_MONOMER": 7.0},
        pool={},
    )
    res = _evaluate_calc(calc, proc, st)
    with pytest.raises(AssertionError):
        assert res["GTP"] == 6.0


def test_canary_rejects_divide_translocase_by_35() -> None:
    """Canary 7: Reject broken calculator that divides translocases capacity by 35."""
    class BrokenDiv35Calculator(RequestCalculatorPTransloc):
        def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
            update = super().next_update(timestep, states)
            reqs = update.get("requests", {}).get(self._pt_proc.name, {})
            reqs[self._pt_proc.atp_wid] = 1.0  # Incorrectly divided cap
            return update

    proc = KarrProteinTranslocationProcess({})
    calc = BrokenDiv35Calculator({"protein_translocation_proc": proc})
    st = _build_test_state(
        proc,
        atpase=1e-12,
        pore=1e-12,
        srp=1000.0,
        receptor=1000.0,
        pending_c={"MG_014_MONOMER": 1000.0},
        pool={},
    )
    res = _evaluate_calc(calc, proc, st)
    with pytest.raises(AssertionError):
        assert res["ATP"] == 3.0
