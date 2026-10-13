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
   zero enzyme input, deferring evolution by one tick, duplicating evolution, or
   failing the step lifecycle (always-evolve on init or always-noop on ticks) fails
   closed, and that aggregate condensation_level relaxation is never accepted as binding activity.
6. Authoritative CC Process is request-only in orchestrated chassis mode (Iteration 2).
7. Same-tick request -> allocator grant -> SMC binding contract (Iteration 2).
8. Engine construction must not mutate CC-owned biological initial state before update.
9. KarrChromosomeCondensationEvolutionStep must enforce one-shot init lifecycle.
10. Reusing the same Composite across multiple Engine constructions must preserve biological state.
"""

from __future__ import annotations

import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from vivarium.core.engine import Engine
from vivarium.core.process import Step

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


def assert_sparse_triplets_equal(actual: Any, expected: Any, msg: str = "complexBoundSites") -> None:
    """Assert structural equality between SparseTriplet representations without array truth ambiguity."""
    if actual is None and expected is None:
        return
    assert actual is not None and expected is not None, f"{msg}: mismatch None vs non-None"
    if isinstance(actual, dict) and isinstance(expected, dict):
        assert actual.get("shape") == expected.get("shape"), f"{msg}: shape mismatch"
        for field in ("positions", "strands", "values"):
            a_arr = actual.get(field)
            e_arr = expected.get(field)
            if a_arr is None and e_arr is None:
                continue
            assert a_arr is not None and e_arr is not None, f"{msg}: field {field} missing in one"
            assert np.array_equal(a_arr, e_arr), f"{msg}: {field} arrays not equal"
    elif hasattr(actual, "shape") and hasattr(expected, "shape"):
        assert actual.shape == expected.shape, f"{msg}: shape mismatch"
        assert np.array_equal(actual.positions, expected.positions), f"{msg}: positions not equal"
        assert np.array_equal(actual.strands, expected.strands), f"{msg}: strands not equal"
        assert np.array_equal(actual.values, expected.values), f"{msg}: values not equal"
    else:
        assert actual == expected, f"{msg}: value mismatch"


def verify_binding_delta(
    *,
    delta_bound: float,
    delta_chrom: float,
    delta_free: float,
    delta_free_adp: float = 0.0,
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

    # Source identity per tick: delta(free_SMC) + delta(free_SMC_ADP) + delta(bound_SMC_ADP) == 0.
    delta_total_smc = delta_free + delta_free_adp + delta_bound
    if delta_total_smc != 0.0:
        raise AssertionError(
            f"Total SMC complex count not conserved: delta_free({delta_free}) + "
            f"delta_free_adp({delta_free_adp}) + delta_bound({delta_bound}) = {delta_total_smc} != 0"
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

    s0 = deepcopy(engine.state.get_value())

    # Tick 1: process requests ATP/H2O based on live free SMC, allocator computes grant.
    engine.update(1.0)
    s1 = deepcopy(engine.state.get_value())

    # Tick 2: execute second tick (evolution in tick 1 under same-tick or tick 2 under 1-tick lag).
    engine.update(1.0)
    s2 = deepcopy(engine.state.get_value())

    bound_0 = float(s0.get("boundEnzymes", {}).get(cc.smc_adp_wid, 0.0))
    bound_1 = float(s1.get("boundEnzymes", {}).get(cc.smc_adp_wid, 0.0))
    bound_2 = float(s2.get("boundEnzymes", {}).get(cc.smc_adp_wid, 0.0))
    delta_bound_1 = bound_1 - bound_0
    delta_bound_2 = bound_2 - bound_1
    delta_bound_total = bound_2 - bound_0

    chrom_0 = float(s0.get("chromosome", {}).get("smc_bound_count", 0.0))
    chrom_2 = float(s2.get("chromosome", {}).get("smc_bound_count", 0.0))
    delta_chrom_total = chrom_2 - chrom_0

    free_0 = float(s0.get("complex", {}).get("counts", {}).get(cc.smc_wid, 0.0))
    free_2 = float(s2.get("complex", {}).get("counts", {}).get(cc.smc_wid, 0.0))
    delta_free_total = free_2 - free_0

    free_adp_0 = float(s0.get("complex", {}).get("counts", {}).get(cc.smc_adp_wid, 0.0))
    free_adp_2 = float(s2.get("complex", {}).get("counts", {}).get(cc.smc_adp_wid, 0.0))
    delta_free_adp_total = free_adp_2 - free_adp_0

    delta_cond_total = float(s2.get("chromosome", {}).get("condensation_level", 0.0)) - float(
        s0.get("chromosome", {}).get("condensation_level", 0.0)
    )
    delta_atp_total = float(s2.get("substrates", {}).get(cc.atp_wid, 0.0)) - float(
        s0.get("substrates", {}).get(cc.atp_wid, 0.0)
    )
    delta_h2o_total = float(s2.get("substrates", {}).get(cc.water_wid, 0.0)) - float(
        s0.get("substrates", {}).get(cc.water_wid, 0.0)
    )
    delta_pi_total = float(s2.get("substrates", {}).get(cc.pi_wid, 0.0)) - float(
        s0.get("substrates", {}).get(cc.pi_wid, 0.0)
    )
    delta_h_total = float(s2.get("substrates", {}).get(cc.hydrogen_wid, 0.0)) - float(
        s0.get("substrates", {}).get(cc.hydrogen_wid, 0.0)
    )

    # Verify total binding across the 2 ticks (accepts binding in either tick 1 or tick 2).
    verify_binding_delta(
        delta_bound=delta_bound_total,
        delta_chrom=delta_chrom_total,
        delta_free=delta_free_total,
        delta_free_adp=delta_free_adp_total,
        delta_cond=delta_cond_total,
        delta_atp=delta_atp_total,
        delta_h2o=delta_h2o_total,
        delta_pi=delta_pi_total,
        delta_h=delta_h_total,
    )

    # Exact-once / allocation-bound guards: per-tick and total bound delta must not exceed allocation.
    alloc_1 = float(s1.get("substrates_allocated", {}).get(cc.name, {}).get(cc.atp_wid, 0.0))
    alloc_2 = float(s2.get("substrates_allocated", {}).get(cc.name, {}).get(cc.atp_wid, 0.0))
    alloc_total = alloc_1 + alloc_2

    if delta_bound_1 > alloc_1:
        raise AssertionError(
            f"Duplicate evolution: tick 1 bound delta {delta_bound_1} exceeds allocated ATP {alloc_1}"
        )
    if delta_bound_2 > max(alloc_1, alloc_2):
        raise AssertionError(
            f"Duplicate evolution: tick 2 bound delta {delta_bound_2} exceeds allocated ATP {max(alloc_1, alloc_2)}"
        )
    if delta_bound_total > alloc_total:
        raise AssertionError(
            f"Duplicate evolution: total bound delta {delta_bound_total} exceeds allocated ATP {alloc_total}"
        )

    return {
        "delta_bound": delta_bound_total,
        "delta_chrom": delta_chrom_total,
        "delta_free": delta_free_total,
        "delta_free_adp": delta_free_adp_total,
        "delta_cond": delta_cond_total,
        "delta_atp": delta_atp_total,
        "delta_h2o": delta_h2o_total,
        "delta_pi": delta_pi_total,
        "delta_h": delta_h_total,
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

    # Handshake requirement 1: Request-only CC process must emit phase.request_ready=True every process phase
    ready_val = update.get("phase", {}).get("request_ready")
    if ready_val is not True:
        raise AssertionError(
            f"CC process must emit phase.request_ready=True when emitting requests: got phase={update.get('phase')}"
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

    free_adp_0 = float(s0.get("complex", {}).get("counts", {}).get(cc.smc_adp_wid, 0.0))
    free_adp_1 = float(s1.get("complex", {}).get("counts", {}).get(cc.smc_adp_wid, 0.0))
    delta_free_adp = free_adp_1 - free_adp_0

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
        delta_free_adp=delta_free_adp,
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
        "delta_free_adp": delta_free_adp,
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
    assert deltas["delta_free"] + deltas["delta_free_adp"] == -deltas["delta_bound"]


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


class _OneTickLagEvolutionWrapper(Step):
    """Planted mutation wrapper: intercept an evolution step and defer evolution updates by 1 active tick."""

    def __init__(self, target: Any) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_active_tick", 0)
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
        real_update = self._target.next_update(timestep, states)
        cc_proc = getattr(self._target, "_condensation_process", None)
        cc_name = getattr(cc_proc, "name", "karr_chromosome_condensation")
        alloc = states.get("substrates_allocated", {}).get(cc_name, {})
        has_grant = any(float(v) > 0.0 for v in alloc.values())
        has_binding = (
            bool(real_update.get("boundEnzymes"))
            or float(real_update.get("chromosome", {}).get("smc_bound_count", 0.0)) > 0.0
            or float(real_update.get("substrates", {}).get("ATP", 0.0)) < 0.0
        )

        if not (has_grant or has_binding):
            # Engine initialization or no-op call without allocation/evolution: do not consume mutation phase.
            return real_update

        # Pipeline delay: defer current active tick's evolution, emit previously deferred.
        delayed_output = self._deferred
        self._deferred = {
            k: v for k, v in real_update.items()
            if k in ("boundEnzymes", "chromosome", "complex", "enzymes", "substrates")
        }
        non_evolution = {
            k: v for k, v in real_update.items()
            if k not in ("boundEnzymes", "chromosome", "complex", "enzymes", "substrates")
        }
        return {**non_evolution, **delayed_output}


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
    assert deltas["delta_free"] + deltas["delta_free_adp"] == -deltas["delta_bound"]


class _DuplicateEvolutionWrapper(Step):
    """Planted mutation wrapper: duplicate evolution updates (double binding) on active ticks."""

    def __init__(self, target: Any) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_active_tick", 0)
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
        cc_proc = getattr(self._target, "_condensation_process", None)
        cc_name = getattr(cc_proc, "name", "karr_chromosome_condensation")
        alloc = states.get("substrates_allocated", {}).get(cc_name, {})
        has_grant = any(float(v) > 0.0 for v in alloc.values())
        has_binding = (
            bool(real_update.get("boundEnzymes"))
            or float(real_update.get("chromosome", {}).get("smc_bound_count", 0.0)) > 0.0
            or float(real_update.get("substrates", {}).get("ATP", 0.0)) < 0.0
        )

        if not (has_grant or has_binding):
            # Engine initialization or no-op call without allocation/evolution: do not consume mutation phase.
            return real_update

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


class _StepIgnoresReadyFalseWrapper(Step):
    """Planted mutation wrapper: evolution step ignores request_ready=False and always evolves."""

    def __init__(self, target: Any) -> None:
        object.__setattr__(self, "_target", target)
        super().__init__(parameters=dict(getattr(target, "parameters", {})))
        self.name = getattr(target, "name", "ignores_ready_wrapper")

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
        del timestep, states
        return {
            "boundEnzymes": {"MG_213_214_298_6MER_ADP": 1.0},
            "chromosome": {"smc_bound_count": 1.0},
            "phase": {"request_ready": False},
        }


class _StepFailsToClearReadyWrapper(Step):
    """Planted mutation wrapper: evolution step executes when ready=True, but omits request_ready=False."""

    def __init__(self, target: Any) -> None:
        object.__setattr__(self, "_target", target)
        super().__init__(parameters=dict(getattr(target, "parameters", {})))
        self.name = getattr(target, "name", "no_clear_wrapper")

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
        ready = states.get("phase", {}).get("request_ready", False)
        if not ready:
            return {}
        # Evolve but omit setting request_ready=False
        return {
            "boundEnzymes": {"MG_213_214_298_6MER_ADP": 1.0},
            "chromosome": {"smc_bound_count": 1.0},
        }


def verify_process_emits_request_ready(cc: Any) -> None:
    """Assert CC process sets phase.request_ready=True in its update when emitting requests."""
    probe_state = {
        "substrates_allocated": {cc.name: {cc.atp_wid: 50.0, cc.water_wid: 50.0}},
        "substrates": {cc.atp_wid: 1000.0, cc.water_wid: 1000.0, cc.pi_wid: 100.0, cc.hydrogen_wid: 100.0},
        "enzymes": {cc.smc_wid: 10.0, cc.smc_adp_wid: 5.0},
        "complex": {"counts": {cc.smc_wid: 10.0, cc.smc_adp_wid: 5.0}},
        "boundEnzymes": {cc.smc_adp_wid: float(cc.trace_anchor_bound)},
        "chromosome": {"smc_bound_count": float(cc.trace_anchor_bound), "condensation_level": float(cc.default_condensation_level)},
    }
    update = cc.next_update(1.0, probe_state)
    ready = update.get("phase", {}).get("request_ready")
    if ready is not True:
        raise AssertionError(
            f"CC process must emit phase.request_ready=True when emitting requests: got phase={update.get('phase')}"
        )


def verify_step_handshake_lifecycle(
    step: Any,
    *,
    init_state: dict[str, Any],
    active_state: dict[str, Any],
    cc: Any,
) -> None:
    """Verify explicit request_ready store handshake lifecycle.

    1. When request_ready is False (Engine init / unready call), returns {} and leaves biology unchanged.
    2. When request_ready is True (active tick), executes evolution and sets request_ready=False in same update.
    3. When request_ready is False on a subsequent call, returns {} again (proves state-driven, not call-counter).
    """
    state_ready_false = deepcopy(init_state)
    state_ready_false.setdefault("phase", {})["request_ready"] = False

    state_ready_true = deepcopy(active_state)
    state_ready_true.setdefault("phase", {})["request_ready"] = True

    # Call 1: ready=False -> must return {}
    update1 = step.next_update(0.0, state_ready_false)
    if update1 != {}:
        raise AssertionError(
            f"Step {getattr(step, 'name', type(step).__name__)}.next_update with request_ready=False "
            f"(Engine initialization) must return empty dict {{}}, but returned: {list(update1.keys())} -> {update1}"
        )

    # Call 2: ready=True -> must evolve and emit phase: {request_ready: False}
    update2 = step.next_update(0.0, state_ready_true)
    bound_delta = float(update2.get("boundEnzymes", {}).get(cc.smc_adp_wid, 0.0))
    if bound_delta <= 0.0:
        raise AssertionError(
            f"Step {getattr(step, 'name', type(step).__name__)}.next_update with request_ready=True "
            f"must execute evolution and bind >0 SMC, got: {update2}"
        )
    step_cleared_ready = update2.get("phase", {}).get("request_ready")
    if step_cleared_ready is not False:
        raise AssertionError(
            f"Step {getattr(step, 'name', type(step).__name__)}.next_update with request_ready=True "
            f"must set phase.request_ready=False in same update, got phase={update2.get('phase')}"
        )

    # Call 3: ready=False again -> must return {} again
    update3 = step.next_update(0.0, state_ready_false)
    if update3 != {}:
        raise AssertionError(
            f"Step {getattr(step, 'name', type(step).__name__)}.next_update with request_ready=False "
            f"must return empty dict {{}} on subsequent unready calls, but returned: {list(update3.keys())} -> {update3}"
        )


def test_planted_canary_verifier_rejects_step_ignoring_ready_false() -> None:
    """Canary (f1): verifier must reject an evolution step that mutates state when request_ready=False."""
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]
    step = composite["steps"]["karr_chromosome_condensation_evolution"]
    mutated_step = _StepIgnoresReadyFalseWrapper(step)

    init_state = deepcopy(composite["state"])
    active_state = deepcopy(composite["state"])
    active_state["substrates_allocated"] = {cc.name: {cc.atp_wid: 50.0, cc.water_wid: 50.0}}

    with pytest.raises(AssertionError, match="with request_ready=False"):
        verify_step_handshake_lifecycle(mutated_step, init_state=init_state, active_state=active_state, cc=cc)


def test_planted_canary_verifier_rejects_step_failing_to_clear_ready() -> None:
    """Canary (f2): verifier must reject an evolution step that fails to set request_ready=False upon evolution."""
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]
    step = composite["steps"]["karr_chromosome_condensation_evolution"]
    mutated_step = _StepFailsToClearReadyWrapper(step)

    init_state = deepcopy(composite["state"])
    active_state = deepcopy(composite["state"])
    active_state["substrates_allocated"] = {cc.name: {cc.atp_wid: 50.0, cc.water_wid: 50.0}}

    with pytest.raises(AssertionError, match="must set phase.request_ready=False"):
        verify_step_handshake_lifecycle(mutated_step, init_state=init_state, active_state=active_state, cc=cc)


def test_planted_canary_verifier_rejects_process_failing_to_set_ready() -> None:
    """Canary (f3): verifier must reject request process that fails to emit request_ready=True."""
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]

    class _NoReadyProcessWrapper:
        def __init__(self, target: Any) -> None:
            self._target = target
            self.name = getattr(target, "name", "no_ready_proc")

        def __getattr__(self, name: str) -> Any:
            return getattr(self._target, name)

        def ports_schema(self) -> dict[str, Any]:
            return self._target.ports_schema()

        def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
            res = self._target.next_update(timestep, states)
            return {k: v for k, v in res.items() if k != "phase"}

    wrapped = _NoReadyProcessWrapper(cc)
    with pytest.raises(AssertionError, match="must emit phase.request_ready=True"):
        verify_process_emits_request_ready(wrapped)


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
    assert deltas["delta_free"] + deltas["delta_free_adp"] == -deltas["delta_bound"]


# ==============================================================================
# Contract 8: Engine initialization biological state preservation contract.
# ==============================================================================


def test_chassis_v6_chromosome_condensation_engine_init_preserves_biological_state_contract() -> None:
    """Contract 8: Engine construction must not mutate CC-owned biological initial state before update.

    Positive hard-RED regression test (fails on current code due to timestep=0.0 evolution in Engine.__init__):
    1. Builds fresh production chassis-v6 composite and snapshots all CC-owned relevant state:
       free SMC / SMC-ADP, root bound SMC-ADP, chromosome smc_bound_count / condensation_level /
       complexBoundSites, CC substrates (ATP, H2O, PI, H, ADP), and requests/allocations.
    2. Constructs Engine(composite=...) without calling engine.update.
    3. Normalizes absent request/allocation mappings and Engine-declared zero defaults as equivalent
       structural bookkeeping; asserts all request and allocation values remain zero.
    4. Asserts all biological state values remain completely unchanged.
    """
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]

    # Snapshot CC-owned state before Engine construction
    smc_before = float(composite["state"]["complex"]["counts"][cc.smc_wid])
    smc_adp_before = float(composite["state"]["complex"]["counts"][cc.smc_adp_wid])
    bound_before = float(composite["state"]["boundEnzymes"][cc.smc_adp_wid])
    chrom_count_before = float(composite["state"]["chromosome"]["smc_bound_count"])
    cond_before = float(composite["state"]["chromosome"]["condensation_level"])
    complex_bound_sites_before = deepcopy(composite["state"]["chromosome"].get("complexBoundSites"))

    tracked_substrates = [cc.atp_wid, cc.water_wid, cc.pi_wid, cc.hydrogen_wid, "ADP"]
    substrates_before = {
        wid: float(composite["state"]["substrates"].get(wid, 0.0))
        for wid in tracked_substrates
    }

    # Construct Engine without updating
    engine = Engine(composite=composite, emit_step=1.0, display_info=False)
    s0 = deepcopy(engine.state.get_value())

    # Assert biological states are strictly unchanged
    s0_smc = float(s0["complex"]["counts"][cc.smc_wid])
    assert s0_smc == smc_before, (
        f"Free SMC mutated on Engine init: {smc_before} -> {s0_smc}"
    )
    s0_smc_adp = float(s0["complex"]["counts"][cc.smc_adp_wid])
    assert s0_smc_adp == smc_adp_before, (
        f"Free SMC-ADP mutated on Engine init: {smc_adp_before} -> {s0_smc_adp}"
    )
    s0_bound = float(s0["boundEnzymes"][cc.smc_adp_wid])
    assert s0_bound == bound_before, (
        f"Bound SMC-ADP mutated on Engine init: {bound_before} -> {s0_bound}"
    )
    s0_chrom_count = float(s0["chromosome"]["smc_bound_count"])
    assert s0_chrom_count == chrom_count_before, (
        f"Chromosome smc_bound_count mutated on Engine init: {chrom_count_before} -> {s0_chrom_count}"
    )
    s0_cond = float(s0["chromosome"]["condensation_level"])
    assert s0_cond == cond_before, (
        f"Chromosome condensation_level mutated on Engine init: {cond_before} -> {s0_cond}"
    )
    for wid in tracked_substrates:
        s0_sub = float(s0["substrates"].get(wid, 0.0))
        assert s0_sub == substrates_before[wid], (
            f"Substrate '{wid}' mutated on Engine init: {substrates_before[wid]} -> {s0_sub}"
        )

    if complex_bound_sites_before is not None:
        assert_sparse_triplets_equal(
            s0["chromosome"].get("complexBoundSites"),
            complex_bound_sites_before,
            msg="Chromosome complexBoundSites",
        )

    # Normalize request and allocation mappings: allow Engine-declared zero defaults as equivalent structural bookkeeping
    s0_cc_requests = s0.get("requests", {}).get(cc.name, {})
    for wid, val in s0_cc_requests.items():
        assert float(val) == 0.0, (
            f"CC request '{wid}' must be zero on Engine init, got {val}"
        )

    s0_cc_alloc = s0.get("substrates_allocated", {}).get(cc.name, {})
    for wid, val in s0_cc_alloc.items():
        assert float(val) == 0.0, (
            f"CC allocation '{wid}' must be zero on Engine init, got {val}"
        )


# ==============================================================================
# Contract 9: Evolution Step one-shot lifecycle contract.
# ==============================================================================


def test_chassis_v6_chromosome_condensation_evolution_step_lifecycle_contract() -> None:
    """Contract 9: KarrChromosomeCondensationEvolutionStep must enforce one-shot init lifecycle.

    Direct step contract (fails on current code because first call executes evolveState):
    1. First invocation (Engine initialization at t=0): must return {} and effect no evolution.
    2. Subsequent invocation(s) with active allocated grant: must execute evolution normally,
       even when called with timestep=0.0.
    """
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]
    step = composite["steps"].get("karr_chromosome_condensation_evolution")
    assert step is not None, "Chassis v6 must contain 'karr_chromosome_condensation_evolution' step"

    init_state = deepcopy(composite["state"])
    active_state = deepcopy(composite["state"])
    active_state["substrates_allocated"] = {cc.name: {cc.atp_wid: 50.0, cc.water_wid: 50.0}}
    active_state["complex"]["counts"][cc.smc_wid] = 10.0
    active_state["complex"]["counts"][cc.smc_adp_wid] = 3.0

    verify_step_handshake_lifecycle(step, init_state=init_state, active_state=active_state, cc=cc)


# ==============================================================================
# Contract 10: Composite-reuse Engine initialization state preservation contract.
# ==============================================================================


def test_chassis_v6_chromosome_condensation_composite_reuse_engine_init_preserves_biological_state_contract() -> None:
    """Contract 10: Reusing a Composite across multiple Engine constructions must preserve biological state.

    Positive hard-RED regression test (fails on current fc16545 because the Step's initialization
    call flag is spent during Engine #1, causing Engine #2 construction to mutate biological state at t=0):
    1. Builds one production v6 Composite and snapshots all CC-owned biological state.
    2. Constructs Engine #1 from that Composite, no update; asserts biological state unchanged.
    3. Constructs Engine #2 from the SAME Composite object, no update; asserts biological state still unchanged.
    4. Normalizes absent request/allocation mappings and Engine-declared zero defaults.
    """
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]

    # Snapshot CC-owned state before any Engine construction
    smc_before = float(composite["state"]["complex"]["counts"][cc.smc_wid])
    smc_adp_before = float(composite["state"]["complex"]["counts"][cc.smc_adp_wid])
    bound_before = float(composite["state"]["boundEnzymes"][cc.smc_adp_wid])
    chrom_count_before = float(composite["state"]["chromosome"]["smc_bound_count"])
    cond_before = float(composite["state"]["chromosome"]["condensation_level"])
    complex_bound_sites_before = deepcopy(composite["state"]["chromosome"].get("complexBoundSites"))

    tracked_substrates = [cc.atp_wid, cc.water_wid, cc.pi_wid, cc.hydrogen_wid, "ADP"]
    substrates_before = {
        wid: float(composite["state"]["substrates"].get(wid, 0.0))
        for wid in tracked_substrates
    }

    # Construct Engine #1 from the Composite without updating
    engine1 = Engine(composite=composite, emit_step=1.0, display_info=False)
    s1 = deepcopy(engine1.state.get_value())

    # Assert biological states are unchanged after Engine #1
    s1_smc = float(s1["complex"]["counts"][cc.smc_wid])
    assert s1_smc == smc_before, f"Free SMC mutated on Engine #1 init: {smc_before} -> {s1_smc}"
    s1_smc_adp = float(s1["complex"]["counts"][cc.smc_adp_wid])
    assert s1_smc_adp == smc_adp_before, f"Free SMC-ADP mutated on Engine #1 init: {smc_adp_before} -> {s1_smc_adp}"
    s1_bound = float(s1["boundEnzymes"][cc.smc_adp_wid])
    assert s1_bound == bound_before, f"Bound SMC-ADP mutated on Engine #1 init: {bound_before} -> {s1_bound}"
    s1_chrom_count = float(s1["chromosome"]["smc_bound_count"])
    assert s1_chrom_count == chrom_count_before, f"Chromosome smc_bound_count mutated on Engine #1 init: {chrom_count_before} -> {s1_chrom_count}"
    s1_cond = float(s1["chromosome"]["condensation_level"])
    assert s1_cond == cond_before, f"Chromosome condensation_level mutated on Engine #1 init: {cond_before} -> {s1_cond}"
    for wid in tracked_substrates:
        s1_sub = float(s1["substrates"].get(wid, 0.0))
        assert s1_sub == substrates_before[wid], f"Substrate '{wid}' mutated on Engine #1 init: {substrates_before[wid]} -> {s1_sub}"
    if complex_bound_sites_before is not None:
        assert_sparse_triplets_equal(
            s1["chromosome"].get("complexBoundSites"),
            complex_bound_sites_before,
            msg="Chromosome complexBoundSites on Engine #1",
        )
    for wid, val in s1.get("requests", {}).get(cc.name, {}).items():
        assert float(val) == 0.0, f"CC request '{wid}' must be zero on Engine #1 init, got {val}"
    for wid, val in s1.get("substrates_allocated", {}).get(cc.name, {}).items():
        assert float(val) == 0.0, f"CC allocation '{wid}' must be zero on Engine #1 init, got {val}"

    # Construct Engine #2 from the SAME Composite object without updating
    engine2 = Engine(composite=composite, emit_step=1.0, display_info=False)
    s2 = deepcopy(engine2.state.get_value())

    # Assert biological states are still unchanged after Engine #2
    s2_smc = float(s2["complex"]["counts"][cc.smc_wid])
    assert s2_smc == smc_before, f"Free SMC mutated on Engine #2 init: {smc_before} -> {s2_smc}"
    s2_smc_adp = float(s2["complex"]["counts"][cc.smc_adp_wid])
    assert s2_smc_adp == smc_adp_before, f"Free SMC-ADP mutated on Engine #2 init: {smc_adp_before} -> {s2_smc_adp}"
    s2_bound = float(s2["boundEnzymes"][cc.smc_adp_wid])
    assert s2_bound == bound_before, f"Bound SMC-ADP mutated on Engine #2 init: {bound_before} -> {s2_bound}"
    s2_chrom_count = float(s2["chromosome"]["smc_bound_count"])
    assert s2_chrom_count == chrom_count_before, f"Chromosome smc_bound_count mutated on Engine #2 init: {chrom_count_before} -> {s2_chrom_count}"
    s2_cond = float(s2["chromosome"]["condensation_level"])
    assert s2_cond == cond_before, f"Chromosome condensation_level mutated on Engine #2 init: {cond_before} -> {s2_cond}"
    for wid in tracked_substrates:
        s2_sub = float(s2["substrates"].get(wid, 0.0))
        assert s2_sub == substrates_before[wid], f"Substrate '{wid}' mutated on Engine #2 init: {substrates_before[wid]} -> {s2_sub}"
    if complex_bound_sites_before is not None:
        assert_sparse_triplets_equal(
            s2["chromosome"].get("complexBoundSites"),
            complex_bound_sites_before,
            msg="Chromosome complexBoundSites on Engine #2",
        )
    for wid, val in s2.get("requests", {}).get(cc.name, {}).items():
        assert float(val) == 0.0, f"CC request '{wid}' must be zero on Engine #2 init, got {val}"
    for wid, val in s2.get("substrates_allocated", {}).get(cc.name, {}).items():
        assert float(val) == 0.0, f"CC allocation '{wid}' must be zero on Engine #2 init, got {val}"

    # Forbid side-effectful schema methods on evolution step
    step = composite["steps"].get("karr_chromosome_condensation_evolution")
    assert not hasattr(step, "reset_for_engine_initialization"), (
        "Evolution Step must not define reset_for_engine_initialization"
    )


# ==============================================================================
# Contract 11: Request-ready handshake topology and side-effect-free schema contract.
# ==============================================================================


def test_chassis_v6_chromosome_condensation_request_ready_handshake_topology_contract() -> None:
    """Contract 11: CC process and evolution Step must wire to shared request_ready phase store.

    Freezes:
    1. Composite topology maps both 'karr_chromosome_condensation' and
       'karr_chromosome_condensation_evolution' 'phase' port to
       ('_internal_chromosome_condensation_phase',).
    2. Initial state declares '_internal_chromosome_condensation_phase': {'request_ready': False}.
    3. Ports schema of process and step declare 'phase' with 'request_ready' (default False, updater 'set').
    4. Evolution step must NOT have side-effectful reset_for_engine_initialization method.
    """
    composite = build_karr_chassis_v6()
    cc = composite["processes"]["karr_chromosome_condensation"]
    step = composite["steps"].get("karr_chromosome_condensation_evolution")
    assert step is not None, "Chassis v6 must contain 'karr_chromosome_condensation_evolution' step"

    # 1. Topology mapping
    proc_topo = composite["topology"].get("karr_chromosome_condensation", {})
    step_topo = composite["topology"].get("karr_chromosome_condensation_evolution", {})
    assert "phase" in proc_topo, "Process topology must declare 'phase' port"
    assert "phase" in step_topo, "Evolution Step topology must declare 'phase' port"
    assert proc_topo["phase"] == ("_internal_chromosome_condensation_phase",), (
        f"Process phase port must map to ('_internal_chromosome_condensation_phase',), got {proc_topo.get('phase')}"
    )
    assert step_topo["phase"] == ("_internal_chromosome_condensation_phase",), (
        f"Step phase port must map to ('_internal_chromosome_condensation_phase',), got {step_topo.get('phase')}"
    )

    # 2. Initial state
    phase_state = composite["state"].get("_internal_chromosome_condensation_phase", {})
    assert "request_ready" in phase_state, (
        "Initial state must contain '_internal_chromosome_condensation_phase' with 'request_ready'"
    )
    assert phase_state["request_ready"] is False, (
        f"Initial request_ready must be False, got {phase_state['request_ready']}"
    )

    # 3. Ports schema
    proc_schema = cc.ports_schema().get("phase", {}).get("request_ready", {})
    assert proc_schema.get("_default") is False, "Process phase.request_ready default must be False"
    assert proc_schema.get("_updater") == "set", "Process phase.request_ready updater must be 'set'"

    step_schema = step.ports_schema().get("phase", {}).get("request_ready", {})
    assert step_schema.get("_default") is False, "Step phase.request_ready default must be False"
    assert step_schema.get("_updater") == "set", "Step phase.request_ready updater must be 'set'"

    # 4. Forbid hidden reset methods / side-effectful schema access
    assert not hasattr(step, "reset_for_engine_initialization"), (
        "Evolution Step must not define reset_for_engine_initialization; "
        "lifecycle must be governed by explicit request_ready store handshake"
    )
    assert getattr(step, "_initialization_call_spent", None) is None, (
        "Evolution Step must not use internal _initialization_call_spent flag"
    )
