"""L2.5 composition-boundary allocator tests.

Covers the shared helper (`compute_composition_allocations` /
`refresh_allocator_views_composition` in `l2_replay_common.py`) that replaced
the idealized `refresh_allocator_views` full-pool grant at the composition
boundary (docs/phase_f/INTEGRITY_AUDIT_PRE_L25.md Finding #20). Every process
in a composition now genuinely contends for a shared pool via Karr's real
uncapped proportional arithmetic (`KarrAllocationStep`,
`@Simulation/evolveState.m:24-37`), instead of each independently receiving
the full observed pool.

Per the blocking review correction (see the superseding provenance entry in
`opencell/provenance/llm_interactions.jsonl`), the composition-boundary
allocator input is now the TRUE Karr oracle (`pool_before`/`requirements`,
`evolveState.m:24-37`), loaded via `load_composition_allocator_oracle` and
NEVER derived from `states_before`/`state['substrates']`
(docs/phase_f/L2_0A_ALLOCATOR_INPUT_GATE.md A05/D1). If that oracle is
absent everywhere the harness knows to look, every composition path fails
CLOSED with a `MISSING_ALLOCATOR_ORACLE` skip rather than fabricating a pool.

These tests exercise the shared helper directly (adversarial contention,
oversupply, zero-demand, process-key normalization, fairness/order-
invariance, no-overallocation, oracle-absent fail-closed behavior) plus a
source-level regression guard that the composition harnesses
(`l2_2_replay_common.py`, `l2_2_replay_common_v2.py`,
`test_l2_5_ppi_ppii_v2.py`) no longer call the idealized per-process grant,
and no longer read `state['substrates']` as a composition-boundary pool,
inside their tick/composition logic.
"""

from __future__ import annotations

import ast
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

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

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import (  # noqa: E402
    CompositionAllocatorOracle,
    MissingAllocatorOracleError,
    apply_composition_allocations,
    composition_allocator_oracle_status,
    compute_composition_allocations,
    load_composition_allocator_oracle,
    refresh_allocator_views_composition,
)

from opencell.vivarium.karr_allocation_step import KEY_ALIASES  # noqa: E402
from opencell.vivarium.karr_transcription import KarrTranscriptionProcess  # noqa: E402
from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process  # noqa: E402
from opencell.vivarium.karr_trna_aminoacylation import KarrTRNAAminoacylationProcess  # noqa: E402
from scripts.probe_l2_0a_allocator_input import (  # noqa: E402
    evaluate_allocator_gate,
    load_process_substrate_wids,
)


def _simple_allocator_oracle(
    pool_before: dict[str, float],
    requirements_by_process: dict[str, dict[str, float]],
) -> CompositionAllocatorOracle:
    return CompositionAllocatorOracle(
        pool_before=pool_before,
        requirements_by_process=requirements_by_process,
        projection_by_process={
            proc_name: {wid: wid for wid in reqs}
            for proc_name, reqs in requirements_by_process.items()
        },
    )


def _runtime_allocator_wids(process: object) -> list[str]:
    allocation_wids = getattr(process, "allocation_substrate_wids", None)
    if allocation_wids is not None:
        return [str(wid) for wid in allocation_wids]
    return [str(wid) for wid in process.substrate_wids]


def _allocator_state_for_processes(*processes: object) -> dict[str, dict[str, dict[str, float]]]:
    return {
        "substrates_allocated": {
            str(process.name): {
                wid: 0.0 for wid in _runtime_allocator_wids(process)
            }
            for process in processes
        }
    }


@lru_cache(maxsize=1)
def _real_allocator_gate_result():
    import l2_replay_common as helper

    oracle = helper._global_allocator_oracle()
    if oracle is None:
        return None
    return evaluate_allocator_gate(oracle, load_process_substrate_wids())


class _CallCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self._function_stack: list[str] = []
        self.calls: list[tuple[str | None, ast.Call]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_stack.append(node.name)
        self.generic_visit(node)
        self._function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function_stack.append(node.name)
        self.generic_visit(node)
        self._function_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        owner = self._function_stack[-1] if self._function_stack else None
        self.calls.append((owner, node))
        self.generic_visit(node)


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None

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


def test_apply_composition_allocations_writes_all_declared_wids_and_raises_on_undeclared() -> None:
    """Superseded by the hard-raise contract (point 3 of the redesign
    mandate): a computed allocation for a WID the target process's own
    schema does not declare is now a raise, never a silent drop -- see
    ``test_apply_composition_allocations_raises_on_missing_expected_wid``.
    Declared WIDs must still be written correctly when every key matches."""
    state = {
        "substrates_allocated": {
            "proc_a": {"ATP": 0.0},
            "proc_b": {"ATP": 0.0, "GTP": 0.0},
        }
    }
    apply_composition_allocations(
        state,
        {
            "proc_a": {"ATP": 5.0},
            "proc_b": {"ATP": 3.0, "GTP": 2.0},
        },
    )
    assert state["substrates_allocated"]["proc_a"] == {"ATP": 5.0}
    assert state["substrates_allocated"]["proc_b"] == {"ATP": 3.0, "GTP": 2.0}


def test_refresh_allocator_views_composition_contends_instead_of_granting_full_pool() -> None:
    """The composition-boundary refresh must NOT grant every process the
    full shared pool independently (the bug this delegation fixes)."""
    state = {
        "substrates_allocated": {
            "proc_a": {"ATP": 0.0},
            "proc_b": {"ATP": 0.0},
        },
    }
    refresh_allocator_views_composition(
        allocator_oracle=_simple_allocator_oracle(
            {"ATP": 10.0},
            {
                "proc_a": {"ATP": 6.0},
                "proc_b": {"ATP": 6.0},
            },
        ),
        state=state,
    )
    alloc_a = state["substrates_allocated"]["proc_a"]["ATP"]
    alloc_b = state["substrates_allocated"]["proc_b"]["ATP"]
    # The idealized (pre-fix) bug would set BOTH to the full pool (10.0).
    assert alloc_a != 10.0
    assert alloc_b != 10.0
    assert alloc_a == 5.0
    assert alloc_b == 5.0
    assert alloc_a + alloc_b <= 10.0


def test_refresh_allocator_views_composition_empty_requests_is_a_noop() -> None:
    state = {
        "substrates_allocated": {"proc_a": {"ATP": 7.0}},
    }
    refresh_allocator_views_composition(
        allocator_oracle=_simple_allocator_oracle({"ATP": 10.0}, {}),
        state=state,
    )
    assert state["substrates_allocated"]["proc_a"]["ATP"] == 7.0


def test_refresh_allocator_views_composition_sole_demander_not_starved_by_zero_request_partner() -> None:
    """A process requesting zero must get zero, but must NOT starve a
    co-composed process that legitimately demands the pool -- i.e. the
    zero-demand consumer is enrolled (reported explicitly, per
    `compute_composition_allocations`'s docstring) but does not reduce the
    sole real demander's uncapped proportional share."""
    state = {
        "substrates_allocated": {
            "proc_a": {"ATP": 0.0},
            "proc_b": {"ATP": 0.0},
        },
    }
    refresh_allocator_views_composition(
        allocator_oracle=_simple_allocator_oracle(
            {"ATP": 40.0},
            {
                "proc_a": {"ATP": 0.0},
                "proc_b": {"ATP": 25.0},
            },
        ),
        state=state,
    )
    assert state["substrates_allocated"]["proc_a"]["ATP"] == 0.0
    # Sole real demander gets Karr's UNCAPPED proportional share: since it is
    # the only demander, scale = pool/max(1,sum(requests)) = 40/25 = 1.6, so
    # it receives its request scaled UP to the full pool (40.0), not capped
    # at its own 25.0 request, and NOT reduced by the zero-request partner.
    assert state["substrates_allocated"]["proc_b"]["ATP"] == 40.0


def test_refresh_allocator_views_composition_process_order_cannot_overwrite_pool() -> None:
    """Order of processes in `requirements_by_process` must not change the
    resulting grants (dict iteration order independence at the harness
    boundary, mirroring `test_order_invariance_reversed_enumeration_same_grants`
    but through the full `refresh_allocator_views_composition` entry point)."""
    forward_state = {
        "substrates_allocated": {
            "proc_a": {"ATP": 0.0},
            "proc_b": {"ATP": 0.0},
            "proc_c": {"ATP": 0.0},
        },
    }
    refresh_allocator_views_composition(
        allocator_oracle=_simple_allocator_oracle(
            {"ATP": 10.0},
            {
                "proc_a": {"ATP": 6.0},
                "proc_b": {"ATP": 6.0},
                "proc_c": {"ATP": 3.0},
            },
        ),
        state=forward_state,
    )
    reversed_state = {
        "substrates_allocated": {
            "proc_c": {"ATP": 0.0},
            "proc_b": {"ATP": 0.0},
            "proc_a": {"ATP": 0.0},
        },
    }
    refresh_allocator_views_composition(
        allocator_oracle=_simple_allocator_oracle(
            {"ATP": 10.0},
            {
                "proc_c": {"ATP": 3.0},
                "proc_b": {"ATP": 6.0},
                "proc_a": {"ATP": 6.0},
            },
        ),
        state=reversed_state,
    )
    for name in ("proc_a", "proc_b", "proc_c"):
        assert (
            forward_state["substrates_allocated"][name]["ATP"]
            == reversed_state["substrates_allocated"][name]["ATP"]
        )


def test_refresh_allocator_views_composition_populates_every_composed_process_row() -> None:
    """Every composed process's own `substrates_allocated` row must
    actually receive its grant -- not just the first-declared process
    (the v1 harness bug this correction pass also fixed via
    `merge_process_state_templates`)."""
    state = {
        "substrates_allocated": {
            "proc_a": {"ATP": 0.0, "GTP": 0.0},
            "proc_b": {"ATP": 0.0},
            "proc_c": {"GTP": 0.0},
        },
    }
    refresh_allocator_views_composition(
        allocator_oracle=_simple_allocator_oracle(
            {"ATP": 8.0, "GTP": 8.0},
            {
                "proc_a": {"ATP": 4.0, "GTP": 4.0},
                "proc_b": {"ATP": 4.0},
                "proc_c": {"GTP": 4.0},
            },
        ),
        state=state,
    )
    assert state["substrates_allocated"]["proc_a"]["ATP"] == 4.0
    assert state["substrates_allocated"]["proc_a"]["GTP"] == 4.0
    assert state["substrates_allocated"]["proc_b"]["ATP"] == 4.0
    assert state["substrates_allocated"]["proc_c"]["GTP"] == 4.0


# --- Oracle availability: fail-closed skip, never fabricate -----------------


def test_composition_allocator_oracle_status_reports_missing_canonical_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`composition_allocator_oracle_status` must flag a runtime process
    name that cannot be mapped to the global oracle's canonical process
    list, by name, without raising."""
    import l2_replay_common as helper

    fake_oracle = SimpleNamespace(process_names=("Metabolism",))
    monkeypatch.setattr(helper, "_global_allocator_oracle", lambda: fake_oracle)
    status = helper.composition_allocator_oracle_status(
        {"not_a_real_runtime_process_name": ["ATP"]}
    )
    assert status is not None
    assert "MISSING_ALLOCATOR_ORACLE" in status
    assert "not_a_real_runtime_process_name" in status


def test_composition_allocator_oracle_status_none_when_oracle_absent_and_no_processes() -> None:
    """An empty `wids_by_process` never needs the oracle at all: no
    process to resolve means nothing can fail to resolve."""
    status = composition_allocator_oracle_status({})
    assert status is None


def test_composition_allocator_oracle_status_tick_coverage_exceeded() -> None:
    status = composition_allocator_oracle_status({"karr_metabolism": ["ATP"]}, tick=1)
    assert status is not None
    assert "ALLOCATOR_ORACLE_TICK_COVERAGE_EXCEEDED" in status


def test_load_composition_allocator_oracle_raises_when_oracle_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`load_composition_allocator_oracle` must raise
    `MissingAllocatorOracleError` (never fabricate a pool/requests from
    some other proxy) when the global oracle artifact is absent."""
    import l2_replay_common as helper

    monkeypatch.setattr(helper, "_global_allocator_oracle", lambda: None)
    with pytest.raises(MissingAllocatorOracleError):
        load_composition_allocator_oracle(
            wids_by_process={"karr_metabolism": ["ATP"]},
            tick=0,
        )


def test_load_composition_allocator_oracle_raises_on_tick_coverage_exceeded() -> None:
    with pytest.raises(MissingAllocatorOracleError, match="ALLOCATOR_ORACLE_TICK_COVERAGE_EXCEEDED"):
        load_composition_allocator_oracle(
            wids_by_process={"karr_metabolism": ["ATP"]},
            tick=5,
        )


def test_load_composition_allocator_oracle_raises_on_unmappable_runtime_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """point 3 / point 5: a runtime process name with no canonical mapping
    must raise, never be silently dropped."""
    import l2_replay_common as helper

    fake_oracle = SimpleNamespace(
        process_names=("Metabolism",),
        pool_before=None,
        requirements=None,
        allocations=None,
    )
    monkeypatch.setattr(helper, "_global_allocator_oracle", lambda: fake_oracle)
    monkeypatch.setattr(helper, "composition_allocator_oracle_status", lambda *a, **k: None)
    with pytest.raises(MissingAllocatorOracleError):
        load_composition_allocator_oracle(
            wids_by_process={"totally_unknown_runtime_name": ["ATP"]},
            tick=0,
        )


def test_load_composition_allocator_oracle_non_metabolite_wid_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """point 4: an unmatched selected WID must fail CLOSED with the exact
    L2.0a unmapped reason, never silently continue."""
    import l2_replay_common as helper

    fake_oracle = SimpleNamespace(
        process_names=("Metabolism",),
        metabolite_wids=("ATP",),
        compartment_wids=("c",),
        counts_shape=(1, 1),
        pool_before=np.array([5.0]),
        requirements=np.array([[3.0]]),
        allocations=np.array([[3.0]]),
    )
    monkeypatch.setattr(helper, "_global_allocator_oracle", lambda: fake_oracle)
    monkeypatch.setattr(helper, "composition_allocator_oracle_status", lambda *a, **k: None)
    with pytest.raises(
        MissingAllocatorOracleError,
        match="NOT_A_METABOLITE_WID.*wid_missing_from_oracle_metabolite_list",
    ):
        load_composition_allocator_oracle(
            wids_by_process={"karr_metabolism": ["ATP", "NOT_A_METABOLITE_WID"]},
            tick=0,
        )


def test_global_allocator_oracle_covers_all_28_processes_when_present() -> None:
    """point 6: the composition denominator must be the COMPLETE 28-process
    set, not a partial subset -- skip (not fail) if the gitignored local
    oracle artifact has not been extracted in this worktree."""
    import l2_replay_common as helper

    oracle = helper._global_allocator_oracle()
    if oracle is None:
        pytest.skip(
            "MISSING_ALLOCATOR_ORACLE: local oracle artifact not extracted "
            "in this worktree (gitignored; see composition_allocator_oracle_status)"
        )
    assert len(oracle.process_names) == 28
    assert oracle.requirements.shape[0] == 28
    assert oracle.allocations.shape[0] == 28


def test_composition_boundary_computed_matches_extracted_allocations_exactly() -> None:
    """point 2/6: run KarrAllocationStep across the COMPLETE 28-process
    requirements matrix pulled straight from the global oracle, and assert
    computed grants exactly equal Karr's own extracted allocations, at
    least for one real resolvable (process, wid) cell. Skips closed if the
    oracle has not been extracted locally."""
    import l2_replay_common as helper

    from scripts.probe_l2_0a_allocator_input import build_wid_mappings, run_allocator_full_matrix

    oracle = helper._global_allocator_oracle()
    if oracle is None:
        pytest.skip("MISSING_ALLOCATOR_ORACLE: local oracle artifact not extracted")
    process_substrate_wids = load_process_substrate_wids()
    mappings, unmapped = build_wid_mappings(oracle, process_substrate_wids)
    assert len(mappings) == 403
    assert len(unmapped) == 1022
    reason_counts: dict[str, int] = {}
    for item in unmapped:
        reason_counts[item.reason] = reason_counts.get(item.reason, 0) + 1
    assert reason_counts == {
        "multiple_active_compartment_candidates": 123,
        "multiple_local_nonzero_candidates": 11,
        "no_active_compartment_candidate": 640,
        "wid_missing_from_oracle_metabolite_list": 248,
    }
    allocations_by_process = run_allocator_full_matrix(oracle)
    checked = 0
    for (process_name, wid), mapping in mappings.items():
        proc_idx = oracle.process_names.index(process_name)
        expected = float(oracle.allocations[proc_idx, mapping.flat_index])
        observed = float(allocations_by_process.get(process_name, {}).get(mapping.mc_key, 0.0))
        assert round(expected) == round(observed), (
            f"{process_name}/{wid}->{mapping.mc_key}: expected={expected} observed={observed}"
        )
        checked += 1
    assert checked == 403


def test_tick0_canary_transcription_translation_receives_exact_runtime_grants() -> None:
    transcription = KarrTranscriptionProcess({"rng_seed": 0})
    translation = KarrTranslationV3Process({"rng_seed": 0})
    wids_by_process = {
        transcription.name: ["GTP", "H2O"],
        translation.name: ["GTP", "H2O"],
    }
    status = composition_allocator_oracle_status(wids_by_process, tick=0)
    if status is not None:
        pytest.skip(status)

    allocator_oracle = load_composition_allocator_oracle(
        wids_by_process=wids_by_process,
        tick=0,
    )
    assert len(allocator_oracle.requirements_by_process) == 28
    assert allocator_oracle.projection_by_process[transcription.name]["H2O"] == "H2O[c]"
    assert allocator_oracle.projection_by_process[translation.name]["H2O"] == "H2O[c]"
    assert "H2O" not in allocator_oracle.pool_before

    state = _allocator_state_for_processes(transcription, translation)
    refresh_allocator_views_composition(
        allocator_oracle=allocator_oracle,
        state=state,
    )

    assert state["substrates_allocated"][transcription.name]["GTP"] == 7760.0
    assert state["substrates_allocated"][translation.name]["GTP"] == 28346.0
    assert state["substrates_allocated"][transcription.name]["H2O"] == 5297030.0
    assert state["substrates_allocated"][translation.name]["H2O"] == 164661990.0


def test_tick0_canary_transcription_trna_aminoacylation_receives_exact_runtime_grants() -> None:
    transcription = KarrTranscriptionProcess({"rng_seed": 0})
    trna = KarrTRNAAminoacylationProcess({"rng_seed": 0})
    wids_by_process = {
        transcription.name: ["ATP", "H2O"],
        trna.name: ["ATP", "H2O"],
    }
    status = composition_allocator_oracle_status(wids_by_process, tick=0)
    if status is not None:
        pytest.skip(status)

    allocator_oracle = load_composition_allocator_oracle(
        wids_by_process=wids_by_process,
        tick=0,
    )
    assert len(allocator_oracle.requirements_by_process) == 28
    assert allocator_oracle.projection_by_process[transcription.name]["ATP"] == "ATP[c]"
    assert allocator_oracle.projection_by_process[trna.name]["ATP"] == "ATP[c]"
    assert allocator_oracle.projection_by_process[transcription.name]["H2O"] == "H2O[c]"
    assert allocator_oracle.projection_by_process[trna.name]["H2O"] == "H2O[c]"

    state = _allocator_state_for_processes(transcription, trna)
    refresh_allocator_views_composition(
        allocator_oracle=allocator_oracle,
        state=state,
    )

    assert state["substrates_allocated"][transcription.name]["ATP"] == 13933.0
    assert state["substrates_allocated"][trna.name]["ATP"] == 20445.0
    assert state["substrates_allocated"][transcription.name]["H2O"] == 5297030.0
    assert state["substrates_allocated"][trna.name]["H2O"] == 17101842.0


def test_apply_composition_allocations_raises_on_runtime_canonical_key_mismatch() -> None:
    """point 3: this is exactly the standalone PPI/PPII anti-pattern --
    computing allocations keyed by a MATLAB-canonical display name
    ("ProteinProcessingI") while `state['substrates_allocated']` is keyed
    by the runtime `process.name` ("karr_protein_processing_i") must raise,
    never silently no-op."""
    state = {
        "substrates_allocated": {
            "karr_protein_processing_i": {"ATP": 0.0},
        }
    }
    with pytest.raises(MissingAllocatorOracleError, match="RUNTIME process.name"):
        apply_composition_allocations(state, {"ProteinProcessingI": {"ATP": 5.0}})


def test_apply_composition_allocations_raises_on_missing_expected_wid() -> None:
    state = {"substrates_allocated": {"proc_a": {"ATP": 0.0}}}
    with pytest.raises(MissingAllocatorOracleError, match="does not declare this WID"):
        apply_composition_allocations(state, {"proc_a": {"GTP": 5.0}})


def test_apply_composition_allocations_raises_when_substrates_allocated_missing() -> None:
    with pytest.raises(MissingAllocatorOracleError):
        apply_composition_allocations({}, {"proc_a": {"ATP": 5.0}})


# --- Source-level regression guard: no idealized grant left in the harness -


def test_composition_harnesses_do_not_call_idealized_grant_in_tick_loop() -> None:
    """Static guard: `refresh_allocator_views` (the idealized per-process
    full-pool grant) must no longer appear inside the multi-process
    composition tick loops of l2_2_replay_common.py / l2_2_replay_common_v2.py
    / test_l2_5_ppi_ppii_v2.py. It remains valid ONLY at the isolated
    single-process counterfactual replay call sites
    (`_build_counterfactual_step_vector`), which this test explicitly
    allows.

    Also guards the documented API-level property rather than local
    variable spellings: composition paths must reach the contention-aware
    helper through the `allocator_oracle=` contract and must not use the
    retired raw-input kwargs (`pool_before=`, `requirements_by_process=`,
    `request_vectors=`).
    """
    for relative_path, expected_counterfactual_calls in (
        ("tests/vivarium/l2_2_replay_common.py", 1),
        ("tests/vivarium/l2_2_replay_common_v2.py", 1),
        ("tests/vivarium/test_l2_5_ppi_ppii_v2.py", 0),
    ):
        source = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative_path)
        collector = _CallCollector()
        collector.visit(tree)

        idealized_calls = [
            (owner, node)
            for owner, node in collector.calls
            if _call_name(node) == "refresh_allocator_views"
        ]
        composition_calls = [
            (owner, node)
            for owner, node in collector.calls
            if _call_name(node) == "refresh_allocator_views_composition"
        ]

        assert len(idealized_calls) == expected_counterfactual_calls, (
            f"{relative_path}: expected exactly {expected_counterfactual_calls} "
            f"idealized-grant call site(s) (isolated counterfactual replay only), "
            f"found {len(idealized_calls)}"
        )
        assert all(owner == "_build_counterfactual_step_vector" for owner, _ in idealized_calls), (
            f"{relative_path}: idealized grant is only allowed inside "
            "`_build_counterfactual_step_vector`"
        )
        assert composition_calls, (
            f"{relative_path}: composition path must call the real "
            "contention-aware allocator helper"
        )
        for _owner, node in composition_calls:
            keyword_names = {kw.arg for kw in node.keywords if kw.arg is not None}
            assert "allocator_oracle" in keyword_names, (
                f"{relative_path}: refresh_allocator_views_composition must be "
                "called through the allocator_oracle contract"
            )
            forbidden = {"pool_before", "requirements_by_process", "request_vectors"} & keyword_names
            assert not forbidden, (
                f"{relative_path}: retired raw allocator-input kwargs found at "
                f"composition boundary: {sorted(forbidden)}"
            )
