"""L2.5 composition-boundary allocator tests.

Covers the shared helper (`compute_composition_allocations` /
`refresh_allocator_views_composition` in `l2_replay_common.py`) that replaced
the idealized `refresh_allocator_views` full-pool grant at the composition
boundary (docs/phase_f/INTEGRITY_AUDIT_PRE_L25.md Finding #20). Every process
in a composition now genuinely contends for a shared pool via Karr's real
uncapped proportional arithmetic (`KarrAllocationStep`,
`@Simulation/evolveState.m:24-37`), instead of each independently receiving
the full observed pool.

These tests exercise the shared helper directly (adversarial contention,
oversupply, zero-demand, process-key normalization, fairness/order-
invariance, no-overallocation) plus a source-level regression guard that the
composition harnesses (`l2_2_replay_common.py`, `l2_2_replay_common_v2.py`)
no longer call the idealized per-process grant inside their tick loops.
"""

from __future__ import annotations

import sys
from pathlib import Path

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

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import (  # noqa: E402
    apply_composition_allocations,
    compute_composition_allocations,
    refresh_allocator_views_composition,
)

from opencell.vivarium.karr_allocation_step import KEY_ALIASES  # noqa: E402

# --- Beat-3 predicted-outcome arithmetic -----------------------------------


def test_beat3_undersupply_pool10_requests_6_6_yields_5_5() -> None:
    # pool ATP=10, two requests 6/6: scale = 10/max(1,12) = 0.8333;
    # floor(6*0.8333) = 5 for both.
    allocated = compute_composition_allocations(
        requests_by_process={
            "proc_a": {"ATP": 6.0},
            "proc_b": {"ATP": 6.0},
        },
        pool={"ATP": 10.0},
    )
    assert allocated["proc_a"]["ATP"] == 5.0
    assert allocated["proc_b"]["ATP"] == 5.0


def test_beat3_oversupply_pool20_requests_6_4_yields_12_8() -> None:
    # pool ATP=20, requests 6/4 (undersupplied sum=10 < pool=20): Karr's
    # UNCAPPED share hands out the whole pool proportionally.
    # scale = 20/max(1,10) = 2.0; floor(6*2)=12, floor(4*2)=8.
    allocated = compute_composition_allocations(
        requests_by_process={
            "proc_a": {"ATP": 6.0},
            "proc_b": {"ATP": 4.0},
        },
        pool={"ATP": 20.0},
    )
    assert allocated["proc_a"]["ATP"] == 12.0
    assert allocated["proc_b"]["ATP"] == 8.0


def test_order_invariance_reversed_enumeration_same_grants() -> None:
    """Reversing process enumeration order must not change per-process grants."""
    forward = compute_composition_allocations(
        requests_by_process={
            "proc_a": {"ATP": 6.0},
            "proc_b": {"ATP": 6.0},
            "proc_c": {"ATP": 3.0},
        },
        pool={"ATP": 10.0},
    )
    reversed_requests = {
        "proc_c": {"ATP": 3.0},
        "proc_b": {"ATP": 6.0},
        "proc_a": {"ATP": 6.0},
    }
    reversed_result = compute_composition_allocations(
        requests_by_process=reversed_requests,
        pool={"ATP": 10.0},
    )
    for name in ("proc_a", "proc_b", "proc_c"):
        assert forward[name]["ATP"] == reversed_result[name]["ATP"]


# --- Adversarial contention / edge cases ------------------------------------


def test_zero_demand_process_gets_zero_and_does_not_starve_others() -> None:
    allocated = compute_composition_allocations(
        requests_by_process={
            "proc_a": {"ATP": 0.0},
            "proc_b": {"ATP": 50.0},
        },
        pool={"ATP": 100.0},
    )
    assert allocated["proc_a"]["ATP"] == 0.0
    # Oversupply: proc_b is the only demander, gets full uncapped share.
    assert allocated["proc_b"]["ATP"] == 100.0


def test_zero_supply_all_processes_get_zero() -> None:
    allocated = compute_composition_allocations(
        requests_by_process={
            "proc_a": {"ATP": 30.0},
            "proc_b": {"ATP": 20.0},
        },
        pool={"ATP": 0.0},
    )
    assert allocated["proc_a"]["ATP"] == 0.0
    assert allocated["proc_b"]["ATP"] == 0.0


def test_three_way_contention_no_overallocation() -> None:
    """Sum of allocated must never exceed the pool, across a k>2 composition."""
    allocated = compute_composition_allocations(
        requests_by_process={
            "proc_a": {"ATP": 17.0},
            "proc_b": {"ATP": 5.0},
            "proc_c": {"ATP": 41.0},
        },
        pool={"ATP": 30.0},
    )
    total_allocated = sum(allocated[name]["ATP"] for name in ("proc_a", "proc_b", "proc_c"))
    assert total_allocated <= 30.0


def test_no_overallocation_across_multiple_wids_and_scales() -> None:
    """Sweep several pool/request magnitudes; allocated sum must never exceed pool."""
    scenarios = [
        ({"proc_a": {"ATP": 1.0}, "proc_b": {"ATP": 1.0}}, {"ATP": 1.0}),
        ({"proc_a": {"ATP": 3.0}, "proc_b": {"ATP": 5.0}}, {"ATP": 4.0}),
        ({"proc_a": {"ATP": 1000.0}, "proc_b": {"ATP": 1.0}}, {"ATP": 999.0}),
        ({"proc_a": {"GTP": 9.0}, "proc_b": {"GTP": 9.0}}, {"GTP": 5.0}),
    ]
    for requests_by_process, pool in scenarios:
        allocated = compute_composition_allocations(requests_by_process=requests_by_process, pool=pool)
        for wid, available in pool.items():
            total = sum(allocated[name].get(wid, 0.0) for name in requests_by_process)
            assert total <= available, f"over-allocation for {wid}: {total} > {available}"


def test_multi_wid_independent_contention() -> None:
    """WIDs are allocated independently; contention on one WID must not bleed into another."""
    allocated = compute_composition_allocations(
        requests_by_process={
            "proc_a": {"ATP": 30.0, "GTP": 3.0},
            "proc_b": {"ATP": 20.0, "GTP": 9.0},
        },
        pool={"ATP": 10.0, "GTP": 9.0},
    )
    assert allocated["proc_a"]["ATP"] == 6.0
    assert allocated["proc_b"]["ATP"] == 4.0
    assert allocated["proc_a"]["GTP"] == 2.0
    assert allocated["proc_b"]["GTP"] == 6.0


def test_process_key_normalization_resolves_alias_to_canonical_key() -> None:
    """A legacy alias key must resolve to its canonical process name in the
    returned allocation (KarrAllocationStep's KEY_ALIASES normalization must
    survive the composition boundary helper)."""
    alias, canonical = next(iter(KEY_ALIASES.items()))
    allocated = compute_composition_allocations(
        requests_by_process={
            alias: {"ATP": 4.0},
            "consumer_b": {"ATP": 4.0},
        },
        pool={"ATP": 8.0},
    )
    # exact supply (4+4==8): both requesters get exactly what they asked.
    assert allocated[canonical]["ATP"] == 4.0
    assert allocated["consumer_b"]["ATP"] == 4.0
    assert alias not in allocated


def test_process_key_normalization_merges_alias_and_canonical_as_one_consumer() -> None:
    """If a caller accidentally registers demand under BOTH the alias and
    its canonical name, they must be summed as ONE consumer's request --
    not treated as two independent consumers that would double-dip the
    shared pool."""
    alias, canonical = next(iter(KEY_ALIASES.items()))
    merged_only = compute_composition_allocations(
        requests_by_process={
            canonical: {"ATP": 8.0},
            "consumer_b": {"ATP": 4.0},
        },
        pool={"ATP": 12.0},
    )
    split_alias_and_canonical = compute_composition_allocations(
        requests_by_process={
            alias: {"ATP": 5.0},
            canonical: {"ATP": 3.0},
            "consumer_b": {"ATP": 4.0},
        },
        pool={"ATP": 12.0},
    )
    assert len(split_alias_and_canonical) == 2  # merged into one consumer + consumer_b
    assert split_alias_and_canonical[canonical]["ATP"] == merged_only[canonical]["ATP"]
    assert split_alias_and_canonical["consumer_b"]["ATP"] == merged_only["consumer_b"]["ATP"]


# --- apply_composition_allocations / refresh_allocator_views_composition ---


def test_apply_composition_allocations_only_writes_declared_wids() -> None:
    state = {
        "substrates_allocated": {
            "proc_a": {"ATP": 0.0},
            "proc_b": {"ATP": 0.0, "GTP": 0.0},
        }
    }
    apply_composition_allocations(
        state,
        {
            "proc_a": {"ATP": 5.0, "UNDECLARED_WID": 999.0},
            "proc_b": {"ATP": 3.0, "GTP": 2.0},
        },
    )
    assert state["substrates_allocated"]["proc_a"] == {"ATP": 5.0}
    assert state["substrates_allocated"]["proc_b"] == {"ATP": 3.0, "GTP": 2.0}


def test_refresh_allocator_views_composition_contends_instead_of_granting_full_pool() -> None:
    """The composition-boundary refresh must NOT grant every process the
    full shared pool independently (the bug this delegation fixes)."""
    state = {
        "substrates": {"ATP": 10.0},
        "substrates_allocated": {
            "proc_a": {"ATP": 0.0},
            "proc_b": {"ATP": 0.0},
        },
    }
    refresh_allocator_views_composition(
        request_vectors={
            "proc_a": {"ATP": 6.0},
            "proc_b": {"ATP": 6.0},
        },
        state=state,
    )
    alloc_a = state["substrates_allocated"]["proc_a"]["ATP"]
    alloc_b = state["substrates_allocated"]["proc_b"]["ATP"]
    # The idealized (pre-fix) bug would set BOTH to the full pool (10.0).
    assert alloc_a != 10.0
    assert alloc_b != 10.0
    assert alloc_a == 5.0
    assert alloc_b == 5.0
    assert alloc_a + alloc_b <= state["substrates"]["ATP"]


def test_refresh_allocator_views_composition_empty_requests_is_a_noop() -> None:
    state = {
        "substrates": {"ATP": 10.0},
        "substrates_allocated": {"proc_a": {"ATP": 7.0}},
    }
    refresh_allocator_views_composition(request_vectors={}, state=state)
    assert state["substrates_allocated"]["proc_a"]["ATP"] == 7.0


# --- Source-level regression guard: no idealized grant left in the harness -


def test_composition_harnesses_do_not_call_idealized_grant_in_tick_loop() -> None:
    """Static guard: `refresh_allocator_views` (the idealized per-process
    full-pool grant) must no longer appear inside the multi-process
    composition tick loops of l2_2_replay_common.py / l2_2_replay_common_v2.py.
    It remains valid ONLY at the isolated single-process counterfactual
    replay call sites (`_build_counterfactual_step_vector`), which this test
    explicitly allows."""
    for relative_path, allowed_call_count in (
        ("tests/vivarium/l2_2_replay_common.py", 1),
        ("tests/vivarium/l2_2_replay_common_v2.py", 1),
    ):
        source = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
        call_count = source.count("refresh_allocator_views(ctx.process")
        assert call_count == allowed_call_count, (
            f"{relative_path}: expected exactly {allowed_call_count} "
            f"idealized-grant call site(s) (isolated counterfactual replay "
            f"only), found {call_count}"
        )
        assert "refresh_allocator_views_composition(" in source, (
            f"{relative_path}: composition tick loop must call the real "
            "contention-aware allocator helper"
        )
