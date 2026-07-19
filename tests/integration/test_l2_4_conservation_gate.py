from __future__ import annotations

import json
from pathlib import Path

from scripts.l2_4_verify_conservation import CONSERVATION_FAIL
from scripts.l2_4_verify_conservation import PASS
from scripts.l2_4_verify_conservation import SeedRunResult
from scripts.l2_4_verify_conservation import evaluate_tick_part_a
from scripts.l2_4_verify_conservation import run_part_a_gate
from scripts.l2_4_verify_conservation import summarize_gate_runs


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
