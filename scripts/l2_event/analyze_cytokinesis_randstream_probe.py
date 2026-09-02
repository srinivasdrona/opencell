"""Analyze `scripts/matlab/probe_cytokinesis_randstream_state.m`'s output
JSON: derive the number of real Lehmer/mcg16807 recurrence steps ("draws")
Karr's genuine Cytokinesis process consumed between consecutive captured
`randStream.state` snapshots, and report them alongside
`chromosome.segregated` so they can be directly compared against
OpenCell's own per-tick draw counts (45, 13, 3 for the accepted seed-0
trace's local ticks 226, 227, 228 respectively -- see
STATUS_L21_CYTOKINESIS_ACTIVE_FIX.md) to localize the first
extra/missing draw responsible for the tick-228 residual divergence.

Never infers Karr's real draw counts from OpenCell's own aggregate
output -- every number this script reports is derived purely from the
probe's own captured MATLAB `randStream.state` values, by counting
forward steps of the SAME Lehmer recurrence Karr's `edu.stanford.covert.
util.RandStream('mcg16807')` uses (state = 16807*state mod (2**31-1)),
independently re-implemented here (not imported from
`opencell.vivarium.karr_protein_decay_light._Mcg16807`, to keep this
analysis tool fully independent of the production module it is meant to
audit).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

_MOD = 2_147_483_647
_MUL = 16_807


def scalar_state(value: Any) -> int:
    """Coerce a MATLAB `jsonencode`d `randStream.state` value (a bare
    number or a 1-element array, depending on how MATLAB's `mcg16807`
    generator represents `.State`) into a single Python int."""
    if isinstance(value, list):
        if len(value) != 1:
            raise ValueError(f"expected a scalar or 1-element randStream.state, got {value!r}")
        return int(value[0])
    return int(value)


def steps_between(state_a: int, state_b: int, max_steps: int = 1_000_000) -> int:
    """Count forward Lehmer-recurrence steps needed to go from `state_a`
    to `state_b`. Raises ValueError (never silently caps/wraps) if
    `state_b` is not reached within `max_steps` -- a genuine desync (or a
    caller bug) must fail loudly, not report a fabricated count."""
    state = int(state_a)
    target = int(state_b)
    if state == target:
        return 0
    for step in range(1, max_steps + 1):
        state = (_MUL * state) % _MOD
        if state == target:
            return step
    raise ValueError(f"state {target} not reached from {state_a} within {max_steps} Lehmer steps")


def analyze(captures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one report row per capture: local_tick, segregated flags,
    entry/exit state, draws consumed WITHIN this tick's own evolveState
    call (entry->exit), and draws consumed BETWEEN this tick's entry and
    the PREVIOUS capture's exit (should be 0 whenever both ticks are
    contiguous local ticks with no gap -- a nonzero value here would mean
    some other draw source ran between the two captured ticks, which is
    impossible for this process's own dedicated randStream unless the
    capture window itself has a gap)."""
    rows: list[dict[str, Any]] = []
    prev_exit: int | None = None
    prev_local_tick: int | None = None
    for cap in captures:
        entry = scalar_state(cap["entry_state"])
        exit_ = scalar_state(cap["exit_state"])
        local_tick = int(cap["local_tick"])
        seg_before = bool(cap["chromosome_segregated_before"])
        seg_after = bool(cap["chromosome_segregated_after"])

        try:
            draws_this_tick: int | str = steps_between(entry, exit_)
        except ValueError as exc:
            draws_this_tick = f"ERROR: {exc}"

        gap_steps: int | str | None = None
        if prev_exit is not None:
            contiguous = prev_local_tick is not None and local_tick == prev_local_tick + 1
            try:
                gap_steps = steps_between(prev_exit, entry)
            except ValueError as exc:
                gap_steps = f"ERROR: {exc}"
            if contiguous and gap_steps != 0:
                gap_steps = f"UNEXPECTED_NONZERO_GAP({gap_steps})"

        rows.append(
            {
                "local_tick": local_tick,
                "absolute_tick": int(cap["absolute_tick"]),
                "chromosome_segregated_before": seg_before,
                "chromosome_segregated_after": seg_after,
                "entry_state": entry,
                "exit_state": exit_,
                "draws_this_tick": draws_this_tick,
                "gap_steps_from_prev_exit": gap_steps,
            }
        )
        prev_exit = exit_
        prev_local_tick = local_tick
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe_json", type=Path, help="Path to the probe's output JSON")
    parser.add_argument(
        "--oc-draws",
        type=str,
        default="",
        help=(
            "Optional comma-separated local_tick=count pairs of OpenCell's "
            "own draw counts to cross-print alongside Karr's real counts "
            "(e.g. '226=45,227=13,228=3'). Never used to compute Karr's "
            "counts -- display only."
        ),
    )
    args = parser.parse_args()

    data = json.loads(args.probe_json.read_text(encoding="utf-8"))
    captures = data["captures"]
    if isinstance(captures, dict):
        captures = [captures]

    oc_draws: dict[int, int] = {}
    for pair in args.oc_draws.split(","):
        pair = pair.strip()
        if not pair:
            continue
        tick_str, count_str = pair.split("=")
        oc_draws[int(tick_str)] = int(count_str)

    print(f"seed={data.get('seed')} tick_start={data.get('tick_start')}")
    for row in analyze(captures):
        oc_count = oc_draws.get(row["local_tick"])
        oc_note = f" oc_draws={oc_count}" if oc_count is not None else ""
        mismatch_note = ""
        if oc_count is not None and isinstance(row["draws_this_tick"], int):
            mismatch_note = " <-- MISMATCH" if row["draws_this_tick"] != oc_count else " <-- match"
        print(
            f"local_tick={row['local_tick']} absolute_tick={row['absolute_tick']} "
            f"seg_before={row['chromosome_segregated_before']} "
            f"seg_after={row['chromosome_segregated_after']} "
            f"entry={row['entry_state']} exit={row['exit_state']} "
            f"karr_draws_this_tick={row['draws_this_tick']} "
            f"gap_steps={row['gap_steps_from_prev_exit']}"
            f"{oc_note}{mismatch_note}"
        )


if __name__ == "__main__":
    main()
