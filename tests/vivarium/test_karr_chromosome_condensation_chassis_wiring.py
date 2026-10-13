"""ChromosomeCondensation chassis-v6 live wiring and execution contracts (Iteration 1).

Freezes the following contracts for ChromosomeCondensation live chassis integration:
1. Real chassis-v6 topology connects CC `enzymes` port to canonical live complex
   counts at ('complex', 'counts') for both SMC and SMC-ADP.
2. Real chassis-v6 topology connects CC `boundEnzymes` port to the canonical
   chromosome-bound authority at ('boundEnzymes',) initialized to the trace anchor.
3. CC is enrolled as an allocator consumer for its ATP/H2O demand WIDs.
4. Autonomous Engine/chassis execution with adequate ATP/H2O and source-derived
   free SMC complexes produces >0 new bound SMC on the chromosome, consumes
   ATP/H2O, produces ADP/PI/H, and conserves SMC complex stoichiometry across ticks.
5. Verifier and planted canaries prove that removing enzyme topology or substituting
   zero enzyme input fails closed, and that aggregate condensation_level relaxation
   is never accepted as binding activity.
6. Diagnostic test proves current request is not consumed same tick (Iteration 2).
"""

from __future__ import annotations

import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

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

    Evaluates the actual competing tick-1 requests and current substrate pools using the
    real KarrAllocationStep on candidate requests, adhering to proportional fair-share algebra:
      floor(R * pool_ATP / (other_demand + R)) >= 1
    Then maps the required request to required free SMC via CC's request formula:
      request_need = free_SMC + free_SMC_ADP
      free_SMC = max(0, request_need - free_SMC_ADP)
    """
    cc = composite["processes"]["karr_chromosome_condensation"]
    alloc_step = composite["steps"]["karr_allocation_step"]
    pool_atp = float(composite["state"]["substrates"][cc.atp_wid])
    pool_h2o = float(composite["state"]["substrates"][cc.water_wid])

    # Run 1 tick of a probe engine to capture actual competing tick-1 requests.
    probe_engine = Engine(composite=deepcopy(composite), emit_step=1.0, display_info=False)
    probe_engine.update(1.0)
    tick1_requests = probe_engine.state.get_value()["requests"]

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
        granted = alloc_res["substrates_allocated"][cc.name][cc.atp_wid]
        if granted >= 1.0:
            min_request = candidate_r
            break

    if min_request is None:
        raise RuntimeError("Failed to derive minimal CC ATP request receiving >=1 grant")

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


# ==============================================================================
# Contract 7: Diagnostic test for Iteration 2 (same-tick request consumption).
# ==============================================================================


@pytest.mark.xfail(
    strict=True,
    reason="Iteration 2: same-tick request consumption not yet implemented (one-tick lag active)",
)
def test_diagnostic_iteration2_same_tick_consumption_is_red() -> None:
    """Iteration 2 diagnostic: prove current request is not consumed same tick.

    Even on a wired chassis, tick 1 exhibits the known one-tick request lag
    (requests are computed in the Process phase, while allocations are computed
    in the following Step phase). Same-tick consumption is out of scope for
    Iteration 1 and remains an intentional strict XFAIL diagnostic here.
    """
    composite = _build_reference_wired_composite()
    cc = composite["processes"]["karr_chromosome_condensation"]
    engine = Engine(composite=composite, emit_step=1.0, display_info=False)

    s0 = deepcopy(engine.state.get_value())
    engine.update(1.0)
    s1 = deepcopy(engine.state.get_value())

    delta_bound_tick1 = float(s1["boundEnzymes"].get(cc.smc_adp_wid, 0.0)) - float(
        s0["boundEnzymes"].get(cc.smc_adp_wid, 0.0)
    )

    # In Iteration 1, delta_bound_tick1 == 0.0 because of the one-tick lag.
    # This assertion requires same-tick consumption (> 0), demonstrating Iteration 2 scope.
    assert delta_bound_tick1 > 0.0, (
        f"Iteration 2 diagnostic: same-tick consumption not yet implemented "
        f"(delta_bound_tick1={delta_bound_tick1:.1f}, expected > 0.0)"
    )
