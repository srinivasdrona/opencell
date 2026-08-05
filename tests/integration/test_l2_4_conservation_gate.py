from __future__ import annotations

import json
from pathlib import Path

from scripts.l2_4_verify_conservation import (
    CONSERVATION_FAIL,
    PARTB_FAIL,
    PASS,
    SeedRunResult,
    evaluate_tick_part_a,
    evaluate_tick_part_b,
    run_part_a_gate,
    summarize_gate_runs,
)


def test_planted_leak_returns_conservation_fail() -> None:
    outcome = evaluate_tick_part_a(
        seed=7,
        tick=1,
        before={"SYNTH_INTERNAL": 10.0},
        after={"SYNTH_INTERNAL": 11.0},
        proc_delta={},
        exchange_wids=frozenset(),
    )
    summary = summarize_gate_runs(
        requested_ticks=1,
        seeds=(7,),
        exchange_wids=frozenset(),
        exchange_wid_source="synthetic",
        per_seed=(
            SeedRunResult(
                seed=7,
                ticks_requested=1,
                ticks_completed=1,
                horizon_completed=True,
                exchange_wids_skipped=outcome.exchange_wids_skipped,
                max_abs_unattributed=outcome.max_abs_unattributed,
                failures=outcome.failures,
            ),
        ),
    )

    assert summary.verdict == CONSERVATION_FAIL
    assert summary.total_failures == 1
    assert summary.top_failures[0].wid == "SYNTH_INTERNAL"
    assert summary.top_failures[0].failure_kind == "unattributed"
    assert summary.top_failures[0].unattributed == 1


def test_one_tick_uncapped_smoke_verdict(tmp_path: Path) -> None:
    out_dir = tmp_path / "part_a_smoke"
    summary = run_part_a_gate(ticks=1, seeds=(0,), out_dir=out_dir, fresh=True)

    assert summary.verdict == PASS
    assert summary.total_failures == 0
    assert summary.stability_failure is None
    assert len(summary.per_seed) == 1
    assert summary.per_seed[0].ticks_completed == 1
    assert summary.per_seed[0].horizon_completed is True

    payload = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert payload["verdict"] == PASS
    assert payload["exchange_wid_count"] == 124


def test_multi_tick_uncapped_no_false_over_allocation(tmp_path: Path) -> None:
    """Regression guard for the Part-B allocation-snapshot off-by-one.

    The over_allocation false positive only appears once an allocator-mediated
    pool depletes over several ticks (the allocation of record for tick T is the
    value present BEFORE the update, not the allocator's freshly recomputed value
    after it). A 1-tick smoke run cannot catch it; this multi-tick run can.
    """
    out_dir = tmp_path / "part_b_multitick"
    summary = run_part_a_gate(ticks=14, seeds=(0,), out_dir=out_dir, fresh=True)

    assert summary.verdict == PASS, (
        "multi-tick uncapped gate must be clean; a Part-B over_allocation here "
        "means the allocation snapshot regressed to the post-update (next-tick) value"
    )
    assert summary.total_failures == 0
    assert summary.per_seed[0].ticks_completed == 14


def test_planted_over_allocation_returns_part_b_fail() -> None:
    outcome = evaluate_tick_part_b(
        seed=11,
        tick=3,
        after={"ATP": 7.0},
        proc_deltas={"consumer_a": {"ATP": -5.0}},
        substrates_allocated={"consumer_a": {"ATP": 4.0}},
    )
    summary = summarize_gate_runs(
        requested_ticks=3,
        seeds=(11,),
        exchange_wids=frozenset(),
        exchange_wid_source="synthetic",
        per_seed=(
            SeedRunResult(
                seed=11,
                ticks_requested=3,
                ticks_completed=3,
                horizon_completed=True,
                exchange_wids_skipped=0,
                max_abs_unattributed=0,
                failures=outcome.failures,
            ),
        ),
    )

    assert summary.verdict == PARTB_FAIL
    assert summary.part_b_failures == 1
    assert summary.top_failures[0].failure_kind == "over_allocation"
    assert summary.top_failures[0].process_name == "consumer_a"
    assert summary.top_failures[0].wid == "ATP"
    assert summary.top_failures[0].consumed == 5
    assert summary.top_failures[0].allocated == 4


def test_planted_negative_pool_returns_part_b_fail() -> None:
    outcome = evaluate_tick_part_b(
        seed=13,
        tick=2,
        after={"H2O": -1.0},
        proc_deltas={},
        substrates_allocated={},
    )
    summary = summarize_gate_runs(
        requested_ticks=2,
        seeds=(13,),
        exchange_wids=frozenset(),
        exchange_wid_source="synthetic",
        per_seed=(
            SeedRunResult(
                seed=13,
                ticks_requested=2,
                ticks_completed=2,
                horizon_completed=True,
                exchange_wids_skipped=0,
                max_abs_unattributed=0,
                failures=outcome.failures,
            ),
        ),
    )

    assert summary.verdict == PARTB_FAIL
    assert summary.part_b_failures == 1
    assert summary.top_failures[0].failure_kind == "negative_pool"
    assert summary.top_failures[0].wid == "H2O"
    assert summary.top_failures[0].rounded_value == -1


def test_planted_fractional_part_a_delta_returns_fractional_failure() -> None:
    outcome = evaluate_tick_part_a(
        seed=17,
        tick=4,
        before={"SYNTH_INTERNAL": 10.0},
        after={"SYNTH_INTERNAL": 10.5},
        proc_delta={"SYNTH_INTERNAL": 0.5},
        exchange_wids=frozenset(),
    )

    fractional_failures = [failure for failure in outcome.failures if failure.failure_kind == "fractional"]

    assert len(fractional_failures) == 2
    assert {failure.field for failure in fractional_failures} == {"after", "proc_delta"}
