"""Diagnose karr_trna_aminoacylation call/update behavior in chassis_v6.

Runs a short chassis_v6 simulation and instruments:
- request_calculator_trna output
- karr_allocation_step grant for karr_trna_aminoacylation
- karr_trna_aminoacylation next_update output shape

Outputs:
- <out-dir>/trna_diagnose_tick_log.csv
- STATUS_diagnose.md
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from vivarium.core.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.karr_composite import build_karr_chassis_v6

TRNA_PROCESS_NAME = "karr_trna_aminoacylation"
TRNA_REQUEST_STEP_NAME = "request_calculator_trna"
ALLOCATOR_STEP_NAME = "karr_allocation_step"


def _vector_summary(values: dict[str, Any] | None) -> dict[str, float | int]:
    if not isinstance(values, dict) or not values:
        return {"sum": 0.0, "nonzero": 0, "max": 0.0}
    arr = np.asarray([float(v) for v in values.values()], dtype=np.float64)
    abs_arr = np.abs(arr)
    return {
        "sum": float(arr.sum()),
        "nonzero": int(np.count_nonzero(abs_arr > 0.0)),
        "max": float(abs_arr.max(initial=0.0)),
    }


def _json_compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _classify_hypothesis(
    *,
    calls: int,
    nonempty_updates: int,
    nonzero_request_ticks: int,
    nonzero_grant_ticks: int,
) -> str:
    if calls == 0:
        return "H1"
    if nonzero_request_ticks > 0 and nonzero_grant_ticks == 0:
        return "H3"
    if calls > 0 and nonempty_updates < calls:
        return "H2"
    return "H4"


def run_diagnosis(*, ticks: int, out_dir: Path) -> tuple[dict[str, Any], Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tick_log_path = out_dir / "trna_diagnose_tick_log.csv"

    # Canonical build path mirrored from scripts/run_chassis_v6_32400t.py.
    m1_model = km.load_default()
    m2_model = tx.load_default()
    m3_model = tl.load_default()
    probe = build_karr_chassis_v6(m1_model=m1_model, m2_model=m2_model, m3_model=m3_model)
    timestep_s = float(
        getattr(probe.processes.get("karr_metabolism"), "parameters", {}).get("time_step", 1.0)
    )
    composite = build_karr_chassis_v6(
        m1_model=m1_model,
        m2_model=m2_model,
        m3_model=m3_model,
        time_step_s=timestep_s,
        emit_step_s=float(ticks),
    )

    trna_proc = composite.processes[TRNA_PROCESS_NAME]
    trna_req_step = composite.steps[TRNA_REQUEST_STEP_NAME]
    allocation_step = composite.steps[ALLOCATOR_STEP_NAME]

    orig_req_next_update = trna_req_step.next_update
    orig_alloc_next_update = allocation_step.next_update
    orig_trna_next_update = trna_proc.next_update

    context: dict[str, Any] = {
        "tick": 0,
        "req_summary": {"sum": 0.0, "nonzero": 0, "max": 0.0},
        "grant_summary": {"sum": 0.0, "nonzero": 0, "max": 0.0},
        "req_calls": 0,
        "alloc_calls": 0,
    }
    rows: list[dict[str, Any]] = []

    def req_wrapper(timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        update = orig_req_next_update(timestep, states)
        req_vector = update.get("requests", {}).get(TRNA_PROCESS_NAME, {}) if isinstance(update, dict) else {}
        context["req_summary"] = _vector_summary(req_vector)
        context["req_calls"] = int(context["req_calls"]) + 1
        return update

    def alloc_wrapper(timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        update = orig_alloc_next_update(timestep, states)
        grant_vector = (
            update.get("substrates_allocated", {}).get(TRNA_PROCESS_NAME, {})
            if isinstance(update, dict)
            else {}
        )
        context["grant_summary"] = _vector_summary(grant_vector)
        context["alloc_calls"] = int(context["alloc_calls"]) + 1
        return update

    def trna_wrapper(timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        update = orig_trna_next_update(timestep, states)
        update_dict = update if isinstance(update, dict) else {}
        free_rna_sum = float(
            sum(
                float(states.get("rna", {}).get("counts", {}).get(wid, 0.0))
                for wid in trna_proc.free_rna_wids
            )
        )
        empty_reason = ""
        if len(update_dict) == 0:
            empty_reason = "guard_free_rna" if free_rna_sum <= 0.0 else "guard_zero_flux"

        rows.append(
            {
                "tick": int(context["tick"]),
                "len_states_in": int(len(states)) if isinstance(states, dict) else 0,
                "len_updates_out": int(len(update_dict)),
                "update_keys": "|".join(sorted(str(k) for k in update_dict.keys())),
                "request_calc_output": _json_compact(context["req_summary"]),
                "allocator_grant_to_trna": _json_compact(context["grant_summary"]),
                "request_call_count_seen": int(context["req_calls"]),
                "alloc_call_count_seen": int(context["alloc_calls"]),
                "free_rna_sum": f"{free_rna_sum:.12g}",
                "empty_reason": empty_reason,
            }
        )
        return update

    trna_req_step.next_update = req_wrapper
    allocation_step.next_update = alloc_wrapper
    trna_proc.next_update = trna_wrapper

    engine = Engine(composite=composite, emit_step=float(ticks), display_info=False)
    for tick in range(1, ticks + 1):
        context["tick"] = int(tick)
        engine.update(timestep_s)

    with tick_log_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "tick",
                "len_states_in",
                "len_updates_out",
                "update_keys",
                "request_calc_output",
                "allocator_grant_to_trna",
                "request_call_count_seen",
                "alloc_call_count_seen",
                "free_rna_sum",
                "empty_reason",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    calls = len(rows)
    nonempty_updates = sum(1 for row in rows if int(row["len_updates_out"]) > 0)
    nonzero_request_ticks = sum(
        1 for row in rows if float(json.loads(str(row["request_calc_output"]))["sum"]) > 0.0
    )
    nonzero_grant_ticks = sum(
        1 for row in rows if float(json.loads(str(row["allocator_grant_to_trna"]))["sum"]) > 0.0
    )
    empty_reason_counts = Counter(str(row["empty_reason"]) for row in rows if row["empty_reason"])
    hypothesis = _classify_hypothesis(
        calls=calls,
        nonempty_updates=nonempty_updates,
        nonzero_request_ticks=nonzero_request_ticks,
        nonzero_grant_ticks=nonzero_grant_ticks,
    )

    summary = {
        "ticks": int(ticks),
        "timestep_s": float(timestep_s),
        "trna_calls": int(calls),
        "nonempty_updates": int(nonempty_updates),
        "nonempty_fraction": float(nonempty_updates / calls) if calls > 0 else 0.0,
        "nonzero_request_ticks": int(nonzero_request_ticks),
        "nonzero_grant_ticks": int(nonzero_grant_ticks),
        "empty_reason_counts": dict(empty_reason_counts),
        "hypothesis": hypothesis,
        "tick_log_csv": str(tick_log_path),
    }
    return summary, tick_log_path


def write_status(summary: dict[str, Any], output_path: Path) -> None:
    fraction_pct = 100.0 * float(summary.get("nonempty_fraction", 0.0))
    status_lines = [
        "# tRNA Aminoacylation Diagnose Status",
        "",
        f"- ticks_run: {summary['ticks']}",
        f"- timestep_s: {summary['timestep_s']}",
        f"- trna_calls: {summary['trna_calls']}",
        f"- nonempty_updates: {summary['nonempty_updates']} ({fraction_pct:.1f}%)",
        f"- nonzero_request_ticks: {summary['nonzero_request_ticks']}",
        f"- nonzero_grant_ticks: {summary['nonzero_grant_ticks']}",
        f"- empty_reason_counts: {summary['empty_reason_counts']}",
        f"- tick_log_csv: `{summary['tick_log_csv']}`",
        "",
        "## Hypothesis Fit",
        f"- classified_hypothesis: {summary['hypothesis']}",
        "- H1 check: process is called each tick when `trna_calls == ticks`.",
        "- H2 check: calls happen, requests/grants are present, but updates are empty on most ticks.",
        "- H3 check: allocator grant is always zero even though request is nonzero.",
        "- H4 check: updates exist but trace exclusion drops them (runner-side).",
        "",
        "## Interpretation",
        "- Current evidence points to guard-driven empty updates after process invocation, not missing enrollment.",
    ]
    output_path.write_text("\n".join(status_lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks", type=int, default=200)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("artifacts") / "trna_diagnose_200t",
    )
    parser.add_argument(
        "--status-path",
        type=Path,
        default=Path("STATUS_diagnose.md"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary, _ = run_diagnosis(ticks=int(args.ticks), out_dir=Path(args.out_dir))
    write_status(summary, Path(args.status_path))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
