"""ChromosomeCondensation chassis-v6 live wiring and execution contracts (Iteration 1 & 2).

Freezes the following contracts for ChromosomeCondensation live chassis integration:
1. Real chassis-v6 topology connects CC `enzymes` port to canonical live complex
   counts at ('complex', 'counts') for both SMC and SMC-ADP.
2. Real chassis-v6 topology connects CC `boundEnzymes` port to the canonical
   chromosome-bound authority at ('boundEnzymes',) initialized to the trace anchor.
3. CC is enrolled as an allocator consumer for its ATP/H2O demand WIDs.
4. Autonomous Engine/chassis execution with adequate ATP/H2O and source-derived
   free SMC complexes produces >0 new bound SMC on the chromosome, consumes
   ATP/H2O, produces ADP/PI/H, and conserves SMC complex stoichiometry across ticks.
5. Verifier and planted canaries prove that removing enzyme topology, substituting
   zero enzyme input, deferring evolution by one tick, or duplicating evolution fails
   closed, and that aggregate condensation_level relaxation is never accepted as binding activity.
6. Authoritative CC Process is request-only in orchestrated chassis mode (Iteration 2).
7. Same-tick request -> allocator grant -> SMC binding contract (Iteration 2).
"""

from __future__ import annotations

import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from vivarium.core.engine import Engine
from vivarium.core.process import Process

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


def verify_binding_delta(
    *,
    delta_bound: float,
    delta_chrom: float,
    delta_free: float,
    delta_cond: float = 0.0,
    delta_atp: float | None = None,
    delta_h2o: float | None = None,
    delta_pi: float | None = None,
    delta_h: float | None = None,
) -> None:
    """Verify SMC binding and stoichiometry deltas, rejecting no-ops and hollow relaxation."""
    del delta_cond  # Explicitly ignored; relaxation is not binding activity.
    if delta_bound <= 0.0:
        raise AssertionError(
            f"Zero-SMC no-op: expected > 0 new bound SMC in boundEnzymes, got delta={delta_bound}"
        )
    if delta_chrom <= 0.0:
        raise AssertionError(
            f"Zero-SMC no-op: expected > 0 new bound SMC in chromosome.smc_bound_count, got delta={delta_chrom}"
        )
    if delta_bound != delta_chrom:
        raise AssertionError(
            f"Bound SMC count mismatch: boundEnzymes delta={delta_bound} != chromosome delta={delta_chrom}"
        )
    if delta_free != -delta_bound:
        raise AssertionError(
            f"SMC complex count not conserved: free delta={delta_free} != -bound delta={-delta_bound}"
        )
    if delta_atp is not None and delta_atp > -delta_bound:
        raise AssertionError(
            f"ATP not consumed with expected stoichiometry: delta_atp={delta_atp}, expected <= {-delta_bound}"
        )
    if delta_h2o is not None and delta_h2o > -delta_bound:
        raise AssertionError(
            f"H2O not consumed with expected stoichiometry: delta_h2o={delta_h2o}, expected <= {-delta_bound}"
        )
    if delta_pi is not None and delta_pi < delta_bound:
        raise AssertionError(
            f"PI not produced with expected stoichiometry: delta_pi={delta_pi}, expected >= {delta_bound}"
        )
    if delta_h is not None and delta_h < delta_bound:
        raise AssertionError(
            f"H not produced with expected stoichiometry: delta_h={delta_h}, expected >= {delta_bound}"
        )


def verify_chassis_smc_binding(composite: Any, *, n_ticks: int = 2) -> dict[str, float]:
    """Execute a chassis Engine run across ticks and verify live SMC binding."""
    if n_ticks < 2:
        raise ValueError(f"n_ticks must be >= 2 to allow the one-tick request lag, got {n_ticks}")

    cc = composite["processes"]["karr_chromosome_condensation"]
    engine = Engine(composite=composite, emit_step=1.0, display_info=False)

    # Tick 1: process requests ATP/H2O based on live free SMC, allocator computes grant.
    engine.update(1.0)
    s1 = deepcopy(engine.state.get_value())

    # Tick 2: process observes grant from tick 1, executes evolveState binding.
    engine.update(1.0)
    s2 = deepcopy(engine.state.get_value())

    bound_1 = float(s1.get("boundEnzymes", {}).get(cc.smc_adp_wid, 0.0))
    bound_2 = float(s2.get("boundEnzymes", {}).get(cc.smc_adp_wid, 0.0))
    delta_bound = bound_2 - bound_1

    chrom_1 = float(s1.get("chromosome", {}).get("smc_bound_count", 0.0))
    chrom_2 = float(s2.get("chromosome", {}).get("smc_bound_count", 0.0))
    delta_chrom = chrom_2 - chrom_1

    free_1 = float(s1.get("complex", {}).get("counts", {}).get(cc.smc_wid, 0.0))
    free_2 = float(s2.get("complex", {}).get("counts", {}).get(cc.smc_wid, 0.0))
    delta_free = free_2 - free_1

    delta_cond = float(s2.get("chromosome", {}).get("condensation_level", 0.0)) - float(
        s1.get("chromosome", {}).get("condensation_level", 0.0)
    )
    delta_atp = float(s2.get("substrates", {}).get(cc.atp_wid, 0.0)) - float(
        s1.get("substrates", {}).get(cc.atp_wid, 0.0)
    )
    delta_h2o = float(s2.get("substrates", {}).get(cc.water_wid, 0.0)) - float(
        s1.get("substrates", {}).get(cc.water_wid, 0.0)
    )
    delta_pi = float(s2.get("substrates", {}).get(cc.pi_wid, 0.0)) - float(
        s1.get("substrates", {}).get(cc.pi_wid, 0.0)
    )
    delta_h = float(s2.get("substrates", {}).get(cc.hydrogen_wid, 0.0)) - float(
        s1.get("substrates", {}).get(cc.hydrogen_wid, 0.0)
    )

    verify_binding_delta(
        delta_bound=delta_bound,
        delta_chrom=delta_chrom,
        delta_free=delta_free,
        delta_cond=delta_cond,
        delta_atp=delta_atp,
        delta_h2o=delta_h2o,
        delta_pi=delta_pi,
        delta_h=delta_h,
    )

    # Exact-once guard: per-tick bound SMC delta must not exceed the ATP allocated to fund that tick.
    alloc_1 = float(s1.get("substrates_allocated", {}).get(cc.name, {}).get(cc.atp_wid, 0.0))
    alloc_2 = float(s2.get("substrates_allocated", {}).get(cc.name, {}).get(cc.atp_wid, 0.0))
    alloc_funded = max(alloc_1, alloc_2)
    if delta_bound > alloc_funded:
        raise AssertionError(
            f"Duplicate evolution: bound delta {delta_bound} exceeds allocated ATP {alloc_funded}"
        )

    return {
        "delta_bound": delta_bound,
        "delta_chrom": delta_chrom,
        "delta_free": delta_free,
        "delta_cond": delta_cond,
        "delta_atp": delta_atp,
        "delta_h2o": delta_h2o,
        "delta_pi": delta_pi,
        "delta_h": delta_h,
    }


def verify_process_is_request_only(cc: Any) -> None:
    """Assert CC process is request-only: calling next_update emits requests but no evolution keys.

    When supplied with nonzero allocatable resources, live enzymes, and bound state:
    - Must emit 'requests' for CC with positive ATP/H2O need.
    - Must NOT emit evolution keys ('boundEnzymes', 'chromosome', 'complex', 'enzymes', 'substrates').
    """
    probe_state = {
        "substrates_allocated": {
            cc.name: {
                cc.atp_wid: 50.0,
                cc.water_wid: 50.0,
            }
        },
        "substrates": {
            cc.atp_wid: 1000.0,
            cc.water_wid: 1000.0,
            cc.pi_wid: 100.0,
            cc.hydrogen_wid: 100.0,
        },
        "enzymes": {
            cc.smc_wid: 10.0,
            cc.smc_adp_wid: 5.0,
        },
        "complex": {
            "counts": {
                cc.smc_wid: 10.0,
                cc.smc_adp_wid: 5.0,
            }
        },
        "boundEnzymes": {
            cc.smc_adp_wid: float(cc.trace_anchor_bound),
        },
        "chromosome": {
            "smc_bound_count": float(cc.trace_anchor_bound),
            "condensation_level": float(cc.default_condensation_level),
        },
    }

    update = cc.next_update(1.0, probe_state)
    cc_requests = update.get("requests", {}).get(cc.name, {})
    if float(cc_requests.get(cc.atp_wid, 0.0)) <= 0.0 or float(cc_requests.get(cc.water_wid, 0.0)) <= 0.0:
        raise AssertionError(
            f"CC process must emit positive ATP/H2O requests in next_update: got {cc_requests}"
        )

    forbidden_evolution_keys = {"boundEnzymes", "chromosome", "complex", "enzymes", "substrates"}
    emitted_evolution_keys = forbidden_evolution_keys & set(update.keys())
    if emitted_evolution_keys:
        raise AssertionError(
            f"CC process must be request-only in orchestrated mode, but emitted evolution keys: {emitted_evolution_keys}"
        )


def verify_same_tick_architecture(composite: Any) -> None:
    """Verify minimal architectural surface for same-tick CC request-allocation-consume.

    Requires:
    1. Authoritative 'karr_chromosome_condensation' Process in composite['processes'].
    2. Exactly one evolution Step scheduled after karr_allocation_step (with ('karr_allocation_step',) dependency).
    3. The evolution Step references the exact same authoritative CC process instance.
    4. Authoritative CC Process is request-only: calling its next_update with nonzero
       allocations/enzymes emits requests but NO evolution keys.
    Class names are intentionally not constrained.
    """
    cc = composite.get("processes", {}).get("karr_chromosome_condensation")
    if cc is None:
        raise AssertionError("Composite must contain authoritative 'karr_chromosome_condensation' process")

    steps = composite.get("steps", {})
    flow = composite.get("flow", {})

    # Check evolution step after allocation
    evo_step = None
    for step_name, step_deps in flow.items():
        if ("karr_allocation_step",) in step_deps:
            cand = steps.get(step_name)
            if cand is None:
                continue
            if (
                ("condensation" in step_name.lower() or "chromcond" in step_name.lower())
                or getattr(cand, "_condensation_process", None) is cc
                or getattr(cand, "_proc", None) is cc
                or getattr(cand, "process", None) is cc
                or getattr(cand, "parameters", {}).get("condensation_process") is cc
                or getattr(cand, "parameters", {}).get("process") is cc
                or getattr(cand, "parameters", {}).get("chromosome_condensation_proc") is cc
            ):
                evo_step = cand
                break

    if evo_step is None:
        raise AssertionError(
            "Architectural surface violation: missing CC evolution step scheduled after karr_allocation_step."
        )

    # Evolution step must reference the authoritative CC process instance
    evo_proc = (
        getattr(evo_step, "_condensation_process", None)
        or getattr(evo_step, "_proc", None)
        or getattr(evo_step, "process", None)
        or getattr(evo_step, "parameters", {}).get("condensation_process")
        or getattr(evo_step, "parameters", {}).get("process")
        or getattr(evo_step, "parameters", {}).get("chromosome_condensation_proc")
    )
    if evo_proc is not cc:
        raise AssertionError(
            "Architectural surface violation: evolution step must reference authoritative CC process instance"
        )

    verify_process_is_request_only(cc)


def verify_same_tick_smc_binding(composite: Any) -> dict[str, float]:
    """Execute a chassis Engine run for exactly 1 tick and verify same-tick SMC binding.

    Enforces Iteration 2 contracts:
    - Pre-condition: proves no prior substrates_allocated value was seeded.
    - Pre-condition: proves no trace hint used.
    - Runs exactly 1 tick from fresh state.
    - Asserts CC request is emitted in tick 1.
    - Asserts allocator grants ATP and H2O to CC in tick 1.
    - Asserts CC consumes that grant and binds >0 SMC in tick 1.
    - Asserts free/bound SMC and ATP/H2O/PI/H deltas are stoichiometrically consistent.
    - Asserts exact-once execution: tick 1 bound delta does not exceed allocated ATP.
    - Asserts minimal architectural surface (request-only Process, evolution step
      after allocation, single authoritative process instance).
    """
    cc = composite["processes"]["karr_chromosome_condensation"]

    # Pre-condition: prove no prior substrates_allocated was seeded
    init_allocated = composite["state"].get("substrates_allocated", {}).get(cc.name, {})
    if float(init_allocated.get(cc.atp_wid, 0.0)) != 0.0 or float(init_allocated.get(cc.water_wid, 0.0)) != 0.0:
        raise AssertionError(
            f"Pre-tick substrate allocation must be unseeded/zero: got {init_allocated}"
        )

    # Pre-condition: prove no trace hint used
    if bool(cc.parameters.get("use_trace_hint", False)):
        raise AssertionError("Trace hint is forbidden in live chassis execution (use_trace_hint=True)")
    if bool(composite["state"].get("trace_hint", {}).get("boundEnzymes_next", {})):
        raise AssertionError("Trace hint is forbidden in live chassis execution (boundEnzymes_next present)")
    if getattr(cc, "_trace_hint", None):
        raise AssertionError("Private _trace_hint is forbidden in live chassis execution")

    engine = Engine(composite=composite, emit_step=1.0, display_info=False)

    s0 = deepcopy(engine.state.get_value())
    s0_allocated = s0.get("substrates_allocated", {}).get(cc.name, {})
    if float(s0_allocated.get(cc.atp_wid, 0.0)) != 0.0 or float(s0_allocated.get(cc.water_wid, 0.0)) != 0.0:
        raise AssertionError(
            f"Engine initial substrate allocation must be unseeded/zero: got {s0_allocated}"
        )

    # Execute exactly one tick
    engine.update(1.0)
    s1 = deepcopy(engine.state.get_value())

    # Assert CC request is emitted in tick 1
    req_atp = float(s1.get("requests", {}).get(cc.name, {}).get(cc.atp_wid, 0.0))
    req_h2o = float(s1.get("requests", {}).get(cc.name, {}).get(cc.water_wid, 0.0))
    if req_atp <= 0.0 or req_h2o <= 0.0:
        raise AssertionError(
            f"CC request was not emitted in tick 1: ATP={req_atp}, H2O={req_h2o}"
        )
    if req_atp != req_h2o:
        raise AssertionError(
            f"CC ATP and H2O requests must match stoichiometry: {req_atp} != {req_h2o}"
        )

    # Assert allocator grants ATP and H2O to CC in tick 1
    alloc_atp = float(s1.get("substrates_allocated", {}).get(cc.name, {}).get(cc.atp_wid, 0.0))
    alloc_h2o = float(s1.get("substrates_allocated", {}).get(cc.name, {}).get(cc.water_wid, 0.0))
    if alloc_atp <= 0.0 or alloc_h2o <= 0.0:
        raise AssertionError(
            f"Allocator did not grant substrates to CC in tick 1: ATP={alloc_atp}, H2O={alloc_h2o}"
        )

    # Assert CC consumes that grant and binds >0 SMC in tick 1
    bound_0 = float(s0.get("boundEnzymes", {}).get(cc.smc_adp_wid, 0.0))
    bound_1 = float(s1.get("boundEnzymes", {}).get(cc.smc_adp_wid, 0.0))
    delta_bound = bound_1 - bound_0

    chrom_0 = float(s0.get("chromosome", {}).get("smc_bound_count", 0.0))
    chrom_1 = float(s1.get("chromosome", {}).get("smc_bound_count", 0.0))
    delta_chrom = chrom_1 - chrom_0

    free_0 = float(s0.get("complex", {}).get("counts", {}).get(cc.smc_wid, 0.0))
    free_1 = float(s1.get("complex", {}).get("counts", {}).get(cc.smc_wid, 0.0))
    delta_free = free_1 - free_0

    delta_cond = float(s1.get("chromosome", {}).get("condensation_level", 0.0)) - float(
        s0.get("chromosome", {}).get("condensation_level", 0.0)
    )

    delta_atp = float(s1.get("substrates", {}).get(cc.atp_wid, 0.0)) - float(
        s0.get("substrates", {}).get(cc.atp_wid, 0.0)
    )
    delta_h2o = float(s1.get("substrates", {}).get(cc.water_wid, 0.0)) - float(
        s0.get("substrates", {}).get(cc.water_wid, 0.0)
    )
    delta_pi = float(s1.get("substrates", {}).get(cc.pi_wid, 0.0)) - float(
        s0.get("substrates", {}).get(cc.pi_wid, 0.0)
    )
    delta_h = float(s1.get("substrates", {}).get(cc.hydrogen_wid, 0.0)) - float(
        s0.get("substrates", {}).get(cc.hydrogen_wid, 0.0)
    )

    verify_binding_delta(
        delta_bound=delta_bound,
        delta_chrom=delta_chrom,
        delta_free=delta_free,
        delta_cond=delta_cond,
        delta_atp=delta_atp,
        delta_h2o=delta_h2o,
        delta_pi=delta_pi,
        delta_h=delta_h,
    )

    # Exact-once guard: tick 1 bound delta must not exceed allocated ATP
    if delta_bound > alloc_atp:
        raise AssertionError(
            f"Duplicate evolution: tick 1 bound delta {delta_bound} exceeds allocated ATP {alloc_atp}"
        )

    verify_same_tick_architecture(composite)

    return {
        "delta_bound": delta_bound,
        "delta_chrom": delta_chrom,
        "delta_free": delta_free,
        "delta_cond": delta_cond,
        "delta_atp": delta_atp,
        "delta_h2o": delta_h2o,
        "delta_pi": delta_pi,
        "delta_h": delta_h,
    }


def derive_minimal_cc_atp_request_and_free_smc(
    composite: Any,
) -> tuple[int, float]:
    """Mechanically derive the minimal CC ATP request and free SMC input that receives >=1 grant.

    Evaluates the actual competing tick-1 requests and post-tick substrate pools from the exact
    same snapshot using the real KarrAllocationStep on candidate requests, adhering to proportional
    fair-share algebra:
      floor(R * pool_ATP / (other_demand + R)) >= 1
    Then maps the required request to required free SMC via CC's request formula:
      request_need = free_SMC + free_SMC_ADP
      free_SMC = max(0, request_need - free_SMC_ADP)
    """
    cc = composite["processes"]["karr_chromosome_condensation"]
    alloc_step = composite["steps"]["karr_allocation_step"]

    # Run 1 tick of a probe engine to capture actual competing tick-1 requests
    # and the post-tick substrate pools from the exact same state snapshot.
    probe_engine = Engine(composite=deepcopy(composite), emit_step=1.0, display_info=False)
    probe_engine.update(1.0)
    tick1_state = probe_engine.state.get_value()
    tick1_requests = tick1_state["requests"]
    pool_atp = float(tick1_state["substrates"][cc.atp_wid])
    pool_h2o = float(tick1_state["substrates"][cc.water_wid])

    other_demand = sum(
        float(req.get(cc.atp_wid, 0.0))
        for proc_name, req in tick1_requests.items()
        if proc_name != cc.name
    )

    base_candidate = max(1, math.ceil(other_demand / max(1.0, pool_atp - 1.0)))
    min_request = None
    for candidate_r in range(max(1, base_candidate - 2), base_candidate + 10):
        test_requests = {p: dict(r) for p, r in tick1_requests.items()}
        test_requests[cc.name] = {
            cc.atp_wid: float(candidate_r),
            cc.water_wid: float(candidate_r),
        }
        alloc_res = alloc_step.next_update(
            1.0,
            {
                "substrates": {cc.atp_wid: pool_atp, cc.water_wid: pool_h2o},
                "requests": test_requests,
            },
        )
        granted_atp = alloc_res["substrates_allocated"][cc.name][cc.atp_wid]
        granted_h2o = alloc_res["substrates_allocated"][cc.name][cc.water_wid]
        if granted_atp >= 1.0 and granted_h2o >= 1.0:
            min_request = candidate_r
            break

    if min_request is None:
        raise RuntimeError("Failed to derive minimal CC ATP request receiving >=1 grant")

    # Assert returned candidate actually receives >=1 ATP and H2O under the captured post-tick snapshot.
    test_requests_candidate = {p: dict(r) for p, r in tick1_requests.items()}
    test_requests_candidate[cc.name] = {
        cc.atp_wid: float(min_request),
        cc.water_wid: float(min_request),
    }
    candidate_alloc = alloc_step.next_update(
        1.0,
        {
            "substrates": {cc.atp_wid: pool_atp, cc.water_wid: pool_h2o},
            "requests": test_requests_candidate,
        },
    )
    assert candidate_alloc["substrates_allocated"][cc.name][cc.atp_wid] >= 1.0
    assert candidate_alloc["substrates_allocated"][cc.name][cc.water_wid] >= 1.0

    # Minimality proof: candidate - 1 must receive zero for at least ATP.
    below_candidate = min_request - 1
    test_requests_below = {p: dict(r) for p, r in tick1_requests.items()}
    test_requests_below[cc.name] = {
        cc.atp_wid: float(below_candidate),
        cc.water_wid: float(below_candidate),
    }
    below_alloc = alloc_step.next_update(
        1.0,
        {
            "substrates": {cc.atp_wid: pool_atp, cc.water_wid: pool_h2o},
            "requests": test_requests_below,
        },
    )
    assert below_alloc["substrates_allocated"][cc.name][cc.atp_wid] == 0.0

    fixture_smc_adp = float(cc._fixture_enzyme_smc_adp)
    required_free_smc = float(max(0, min_request - fixture_smc_adp))
    return min_request, required_free_smc


def _build_reference_wired_composite() -> Any:
    """Helper constructing an explicitly wired chassis composite for canary verification."""
    c = build_karr_chassis_v6()
    cc = c["processes"]["karr_chromosome_condensation"]
    c["topology"]["karr_chromosome_condensation"]["enzymes"] = ("complex", "counts")
    c["topology"]["karr_chromosome_condensation"]["boundEnzymes"] = ("boundEnzymes",)
    _, required_free_smc = derive_minimal_cc_atp_request_and_free_smc(c)
    c["state"]["complex"]["counts"][cc.smc_wid] = float(required_free_smc)
    c["state"]["complex"]["counts"][cc.smc_adp_wid] = float(cc._fixture_enzyme_smc_adp)
    c["state"]["boundEnzymes"][cc.smc_adp_wid] = float(cc.trace_anchor_bound)
    return c


# ==============================================================================
# Contract 1: Topology connects CC `enzymes` to live complex counts.
# ==============================================================================


def test_chassis_v6_chromosome_condensation_topology_enzymes_contract() -> None:
    """Contract 1: chassis-v6 topology must connect CC enzymes port to ('complex', 'counts')."""
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]
    topology = composite["topology"]["karr_chromosome_condensation"]

    assert "enzymes" in topology, (
        "karr_chromosome_condensation topology must connect declared 'enzymes' port "
        "to live complex counts"
    )
    assert topology["enzymes"] == ("complex", "counts"), (
        f"CC enzymes port must connect to ('complex', 'counts'), got {topology.get('enzymes')}"
    )

    complex_counts = composite["state"]["complex"]["counts"]
    assert cc.smc_wid in complex_counts, (
        f"Live complex counts must include free SMC complex '{cc.smc_wid}'"
    )
    assert complex_counts[cc.smc_wid] == float(cc._fixture_enzyme_smc), (
        f"Initial free SMC count in complex.counts must equal fixture value "
        f"{cc._fixture_enzyme_smc}, got {complex_counts.get(cc.smc_wid)}"
    )
    assert cc.smc_adp_wid in complex_counts, (
        f"Live complex counts must include free SMC-ADP complex '{cc.smc_adp_wid}'"
    )
    assert complex_counts[cc.smc_adp_wid] == float(cc._fixture_enzyme_smc_adp), (
        f"Initial free SMC-ADP count in complex.counts must equal fixture value "
        f"{cc._fixture_enzyme_smc_adp}, got {complex_counts.get(cc.smc_adp_wid)}"
    )


# ==============================================================================
# Contract 2: Topology connects CC `boundEnzymes` to canonical bound store.
# ==============================================================================


def test_chassis_v6_chromosome_condensation_topology_bound_enzymes_contract() -> None:
    """Contract 2: chassis-v6 topology must connect CC boundEnzymes port to ('boundEnzymes',)."""
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]
    topology = composite["topology"]["karr_chromosome_condensation"]

    assert "boundEnzymes" in topology, (
        "karr_chromosome_condensation topology must connect declared 'boundEnzymes' port"
    )
    assert topology["boundEnzymes"] == ("boundEnzymes",), (
        f"CC boundEnzymes port must connect to ('boundEnzymes',), got {topology.get('boundEnzymes')}"
    )

    bound_enzymes = composite["state"]["boundEnzymes"]
    assert cc.smc_adp_wid in bound_enzymes, (
        f"boundEnzymes store must include SMC-ADP '{cc.smc_adp_wid}'"
    )
    assert bound_enzymes[cc.smc_adp_wid] == float(cc.trace_anchor_bound), (
        f"Initial bound SMC-ADP in boundEnzymes must match trace anchor {cc.trace_anchor_bound}, "
        f"got {bound_enzymes.get(cc.smc_adp_wid)}"
    )
    assert composite["state"]["chromosome"]["smc_bound_count"] == float(cc.trace_anchor_bound), (
        f"Initial chromosome.smc_bound_count must match trace anchor {cc.trace_anchor_bound}"
    )


# ==============================================================================
# Contract 3: Allocator enrollment for ATP and H2O.
# ==============================================================================


def test_chassis_v6_chromosome_condensation_allocator_enrollment_contract() -> None:
    """Contract 3: CC must be enrolled in allocator consumer_processes for ATP and H2O."""
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]
    allocator = composite["steps"]["karr_allocation_step"]

    consumers = dict(allocator.parameters["consumer_processes"])
    assert cc.name in consumers, (
        f"Process '{cc.name}' must be enrolled in allocator consumer_processes"
    )
    enrolled_wids = consumers[cc.name]
    assert cc.atp_wid in enrolled_wids, (
        f"ATP WID '{cc.atp_wid}' must be enrolled for '{cc.name}'"
    )
    assert cc.water_wid in enrolled_wids, (
        f"H2O WID '{cc.water_wid}' must be enrolled for '{cc.name}'"
    )

    alloc_substrates = set(allocator.parameters["substrate_wids"])
    assert cc.atp_wid in alloc_substrates
    assert cc.water_wid in alloc_substrates

    # Direct allocator execution check.
    alloc_update = allocator.next_update(
        1.0,
        {
            "substrates": {cc.atp_wid: 50.0, cc.water_wid: 50.0},
            "requests": {cc.name: {cc.atp_wid: 5.0, cc.water_wid: 5.0}},
        },
    )
    allocated_cc = alloc_update["substrates_allocated"][cc.name]
    assert allocated_cc[cc.atp_wid] > 0.0
    assert allocated_cc[cc.water_wid] > 0.0


# ==============================================================================
# Contract 4: Allocation-threshold stress canary executes through real Engine.
# ==============================================================================


def test_chassis_v6_chromosome_condensation_allocation_threshold_stress_execution() -> None:
    """Contract 4: allocation-threshold stress canary executes through real Engine and binds SMC.

    Derives the minimal CC ATP request that receives >=1 grant from the actual competing
    chassis requests and substrate pool, maps that to required free SMC via CC's request formula,
    and runs a fresh real composite for two ticks using production topology.
    Fails on current code because production topology does not wire CC enzymes/boundEnzymes.
    """
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]

    min_request, required_free_smc = derive_minimal_cc_atp_request_and_free_smc(composite)
    assert min_request >= 1
    assert required_free_smc >= 0.0

    # Supply the mechanically derived free SMC input; existing source-derived substrate
    # pools and production topology are NOT overridden.
    composite["state"]["complex"]["counts"][cc.smc_wid] = float(required_free_smc)
    composite["state"]["complex"]["counts"][cc.smc_adp_wid] = float(cc._fixture_enzyme_smc_adp)
    composite["state"]["boundEnzymes"][cc.smc_adp_wid] = float(cc.trace_anchor_bound)

    deltas = verify_chassis_smc_binding(composite, n_ticks=2)
    assert deltas["delta_bound"] > 0.0
    assert deltas["delta_free"] == -deltas["delta_bound"]


# ==============================================================================
# Contract 5: Default-chassis source seeds starvation (strict XFAIL).
# ==============================================================================


@pytest.mark.xfail(
    strict=True,
    reason="External allocator/request starvation grants zero ATP to CC under default source seeds",
)
def test_default_chassis_source_seeds_activity_starvation() -> None:
    """Default-chassis source seeds test: proves starvation under unmodified source seeds.

    With exact unmodified source seeds (free SMC=5, SMC-ADP=3), competing chassis
    demand (~1.01M ATP) vs substrate pool (~36k ATP) scales CC's 8 ATP request to < 1.0,
    resulting in floor(req * scale) == 0.0 granted ATP.
    This test runs with exact unmodified source seeds/pools; it XFAILs currently,
    and will strict-XPASS if upstream allocator fairness or demand reduction
    later unblocks CC activity under default seeds.
    """
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]

    # Even if topology were wired and fixture seeds initialized, default seeds yield 0 binding.
    composite["topology"]["karr_chromosome_condensation"]["enzymes"] = ("complex", "counts")
    composite["topology"]["karr_chromosome_condensation"]["boundEnzymes"] = ("boundEnzymes",)
    composite["state"]["complex"]["counts"][cc.smc_wid] = float(cc._fixture_enzyme_smc)
    composite["state"]["complex"]["counts"][cc.smc_adp_wid] = float(cc._fixture_enzyme_smc_adp)
    composite["state"]["boundEnzymes"][cc.smc_adp_wid] = float(cc.trace_anchor_bound)

    deltas = verify_chassis_smc_binding(composite, n_ticks=2)
    assert deltas["delta_bound"] > 0.0


# ==============================================================================
# Contract 6: Planted canaries.
# ==============================================================================


def test_planted_canary_verifier_rejects_missing_enzyme_topology() -> None:
    """Canary (a): verifier must reject composite when enzyme topology is missing."""
    composite = _build_reference_wired_composite()
    composite["topology"]["karr_chromosome_condensation"].pop("enzymes", None)

    with pytest.raises(AssertionError, match="Zero-SMC no-op"):
        verify_chassis_smc_binding(composite, n_ticks=2)


def test_planted_canary_verifier_rejects_zero_or_default_enzyme_input() -> None:
    """Canary (b): verifier must reject composite when free SMC and SMC-ADP inputs are zero."""
    composite = _build_reference_wired_composite()
    cc = composite["processes"]["karr_chromosome_condensation"]
    composite["state"]["complex"]["counts"][cc.smc_wid] = 0.0
    composite["state"]["complex"]["counts"][cc.smc_adp_wid] = 0.0

    with pytest.raises(AssertionError, match="Zero-SMC no-op"):
        verify_chassis_smc_binding(composite, n_ticks=2)


def test_planted_canary_verifier_rejects_condensation_level_relaxation_without_binding() -> None:
    """Contract 8: verifier must refuse to count condensation_level relaxation as binding."""
    with pytest.raises(AssertionError, match="Zero-SMC no-op"):
        verify_binding_delta(
            delta_bound=0.0,
            delta_chrom=0.0,
            delta_free=0.0,
            delta_cond=0.05,
        )


class _OneTickLagEvolutionWrapper(Process):
    """Planted mutation wrapper: intercept an object's next_update and defer evolution updates by 1 tick."""

    def __init__(self, target: Any) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_tick", 0)
        object.__setattr__(self, "_deferred", {})
        super().__init__(parameters=dict(getattr(target, "parameters", {})))
        self.name = getattr(target, "name", "lag_wrapper")

    def __getattr__(self, name: str) -> Any:
        if name == "_target":
            raise AttributeError(name)
        target = self.__dict__.get("_target")
        if target is None:
            raise AttributeError(name)
        return getattr(target, name)

    def ports_schema(self) -> dict[str, Any]:
        return self._target.ports_schema()

    def calculate_timestep(self, states: dict[str, Any]) -> float:
        calc_fn = getattr(self._target, "calculate_timestep", None)
        if callable(calc_fn):
            return float(calc_fn(states))
        return 1.0

    def update_condition(self, timestep: float, states: dict[str, Any]) -> bool:
        cond_fn = getattr(self._target, "update_condition", None)
        if callable(cond_fn):
            return bool(cond_fn(timestep, states))
        return True

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        self._tick += 1
        real_update = self._target.next_update(timestep, states)
        if self._tick == 1:
            # Tick 1: hold back evolution updates; pass requests if present.
            self._deferred = {
                k: v for k, v in real_update.items()
                if k in ("boundEnzymes", "chromosome", "complex", "substrates")
            }
            return {
                k: v for k, v in real_update.items()
                if k not in ("boundEnzymes", "chromosome", "complex", "substrates")
            }
        elif self._tick == 2:
            # Tick 2: release deferred evolution updates merged with tick 2.
            combined = dict(real_update)
            for k, v in self._deferred.items():
                if k not in combined:
                    combined[k] = v
                elif isinstance(v, dict) and isinstance(combined[k], dict):
                    merged_dict = dict(combined[k])
                    for sub_k, sub_v in v.items():
                        merged_dict[sub_k] = merged_dict.get(sub_k, 0.0) + sub_v
                    combined[k] = merged_dict
            return combined
        return real_update


def _plant_one_tick_lag_mutation_on_composite(composite: Any) -> Any:
    """Plant a one-tick lag mutation on whichever composite component executes CC evolution."""
    cc = composite["processes"]["karr_chromosome_condensation"]
    evo_step_key = None
    for key, step in composite.get("steps", {}).items():
        if ("condensation" in key.lower() or "chromcond" in key.lower()) and "request" not in key.lower():
            evo_step_key = key
            break
        if (
            getattr(step, "_condensation_process", None) is cc
            or getattr(step, "_proc", None) is cc
            or getattr(step, "process", None) is cc
            or getattr(step, "parameters", {}).get("condensation_process") is cc
        ) and "request" not in key.lower():
            evo_step_key = key
            break

    if evo_step_key is not None:
        composite["steps"][evo_step_key] = _OneTickLagEvolutionWrapper(composite["steps"][evo_step_key])
    else:
        composite["processes"]["karr_chromosome_condensation"] = _OneTickLagEvolutionWrapper(cc)
    return composite


def test_planted_canary_verifier_rejects_one_tick_lag_mutation() -> None:
    """Canary (d): verifier must reject composite when CC evolution exhibits a one-tick lag.

    Proves that `verify_same_tick_smc_binding` is sensitive to timing, isolating timing
    from starvation:
    1. Running the lagged composite for 1 tick is rejected by the same-tick verifier
       (AssertionError: Zero-SMC no-op).
    2. Running an identical lagged composite for 2 ticks passes, proving that evolution
       was legitimately deferred rather than destroyed.
    """
    composite = _build_reference_wired_composite()
    mutated_1tick = _plant_one_tick_lag_mutation_on_composite(deepcopy(composite))
    with pytest.raises(AssertionError, match="Zero-SMC no-op"):
        verify_same_tick_smc_binding(mutated_1tick)

    mutated_2tick = _plant_one_tick_lag_mutation_on_composite(deepcopy(composite))
    deltas = verify_chassis_smc_binding(mutated_2tick, n_ticks=2)
    assert deltas["delta_bound"] > 0.0
    assert deltas["delta_free"] == -deltas["delta_bound"]


class _DuplicateEvolutionWrapper(Process):
    """Planted mutation wrapper: duplicate evolution updates (double binding)."""

    def __init__(self, target: Any) -> None:
        object.__setattr__(self, "_target", target)
        super().__init__(parameters=dict(getattr(target, "parameters", {})))
        self.name = getattr(target, "name", "duplicate_wrapper")

    def __getattr__(self, name: str) -> Any:
        if name == "_target":
            raise AttributeError(name)
        target = self.__dict__.get("_target")
        if target is None:
            raise AttributeError(name)
        return getattr(target, name)

    def ports_schema(self) -> dict[str, Any]:
        return self._target.ports_schema()

    def calculate_timestep(self, states: dict[str, Any]) -> float:
        calc_fn = getattr(self._target, "calculate_timestep", None)
        if callable(calc_fn):
            return float(calc_fn(states))
        return 1.0

    def update_condition(self, timestep: float, states: dict[str, Any]) -> bool:
        cond_fn = getattr(self._target, "update_condition", None)
        if callable(cond_fn):
            return bool(cond_fn(timestep, states))
        return True

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        real_update = self._target.next_update(timestep, states)
        doubled = dict(real_update)
        for k in ("boundEnzymes", "chromosome", "complex", "enzymes", "substrates"):
            if k in doubled and isinstance(doubled[k], dict):
                doubled[k] = {
                    sub_k: (sub_v * 2.0 if isinstance(sub_v, (int, float)) else sub_v)
                    for sub_k, sub_v in doubled[k].items()
                }
        return doubled


def _plant_duplicate_evolution_mutation_on_composite(composite: Any) -> Any:
    """Plant a duplicate-evolution mutation on whichever composite component executes CC evolution."""
    cc = composite["processes"]["karr_chromosome_condensation"]
    evo_step_key = None
    for key, step in composite.get("steps", {}).items():
        if ("condensation" in key.lower() or "chromcond" in key.lower()) and "request" not in key.lower():
            evo_step_key = key
            break
        if (
            getattr(step, "_condensation_process", None) is cc
            or getattr(step, "_proc", None) is cc
            or getattr(step, "process", None) is cc
            or getattr(step, "parameters", {}).get("condensation_process") is cc
        ) and "request" not in key.lower():
            evo_step_key = key
            break

    if evo_step_key is not None:
        composite["steps"][evo_step_key] = _DuplicateEvolutionWrapper(composite["steps"][evo_step_key])
    else:
        composite["processes"]["karr_chromosome_condensation"] = _DuplicateEvolutionWrapper(cc)
    return composite


def test_planted_canary_verifier_rejects_duplicate_evolution_mutation() -> None:
    """Canary (e): verifier must reject composite when CC evolution executes more than once per allocation."""
    composite = _build_reference_wired_composite()
    mutated = _plant_duplicate_evolution_mutation_on_composite(deepcopy(composite))
    with pytest.raises(AssertionError, match="Duplicate evolution|exceeds allocated"):
        verify_chassis_smc_binding(mutated, n_ticks=2)


# ==============================================================================
# Contract 7: Request-only Process and same-tick consume contracts (Iteration 2).
# ==============================================================================


def test_chassis_v6_chromosome_condensation_process_is_request_only_contract() -> None:
    """Contract 7a: CC process must be request-only in orchestrated chassis mode.

    Iteration 2 architectural contract (currently hard RED on unmodified production):
    In the orchestrated chassis architecture, the Process phase is the request phase.
    Calling CC process next_update with nonzero allocatable resources, live enzymes,
    and bound state must emit requests for ATP and H2O, but must NOT emit any evolution
    updates ('boundEnzymes', 'chromosome', 'complex', 'enzymes', 'substrates').
    Evolution is the sole responsibility of the post-allocation evolution Step.
    """
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]
    verify_process_is_request_only(cc)


def test_chassis_v6_chromosome_condensation_same_tick_request_allocation_consume_contract() -> None:
    """Contract 7b: CC request -> allocator grant -> SMC binding in the exact same tick.

    Iteration 2 positive contract (currently hard RED on unmodified production):
    1. Build real v6 composite with production topology.
    2. Derive minimal fair-share free SMC stress input from one consistent request/pool snapshot.
    3. Prove no prior substrates_allocated was seeded and no trace hint used.
    4. Execute exactly one Engine tick from fresh state.
    5. Assert same-tick request emission, allocator grant, SMC binding (>0), and delta consistency.
    6. Verify architectural surface: authoritative process is request-only, evolution step after
       allocation, with one authoritative process instance.
    """
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]

    min_request, required_free_smc = derive_minimal_cc_atp_request_and_free_smc(composite)
    assert min_request >= 1
    assert required_free_smc >= 0.0

    # Supply the mechanically derived free SMC input; existing source-derived substrate
    # pools and production topology are NOT overridden.
    composite["state"]["complex"]["counts"][cc.smc_wid] = float(required_free_smc)
    composite["state"]["complex"]["counts"][cc.smc_adp_wid] = float(cc._fixture_enzyme_smc_adp)
    composite["state"]["boundEnzymes"][cc.smc_adp_wid] = float(cc.trace_anchor_bound)

    deltas = verify_same_tick_smc_binding(composite)
    assert deltas["delta_bound"] > 0.0
    assert deltas["delta_free"] == -deltas["delta_bound"]
