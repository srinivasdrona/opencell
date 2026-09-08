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
util.RandStream('mcg16807')` uses (state = 16807*state mod (2**31-1)).

Root-cause correction (M5000 seed-36 promotion, tick=894): a captured
`randStream.state` value is NOT the raw Lehmer recurrence value -- it is
a value-domain-encoded representation of it that live MATLAB's real
`RandStream('mcg16807').State` getter/setter expose (see
`opencell/util/mcg16807_state_codec.py` for the transform and its live-
MATLAB derivation/verification). `steps_between` now decodes both
endpoints into raw recurrence space before counting steps -- comparing/
stepping the still-encoded values directly (the prior behavior) can never
reach a real exit state that is only reachable in raw space, exactly the
failure this task's tick=894 ledger hit (entry/exit states 36 ->
1363919953, unreachable in encoded space, reachable in exactly 49 real
steps once decoded).

Imports the codec (not `opencell.vivarium.karr_cytokinesis`'s own
production RNG shim) to keep this analysis tool independent of the
production module it is meant to audit, while still sharing the single,
live-MATLAB-verified encode/decode transform rather than re-deriving (and
risking re-diverging) it a second time in this file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opencell.util.mcg16807_state_codec import parse_captured_state  # noqa: E402
from opencell.util.mcg16807_state_codec import steps_between as _codec_steps_between  # noqa: E402


def scalar_state(value: Any) -> int:
    """Coerce a MATLAB `jsonencode`d `randStream.state` value (a bare
    number or a 1-element array, depending on how MATLAB's `mcg16807`
    generator represents `.State`) into a single Python int -- the
    MATLAB-exposed ENCODED representation, via the shared, fail-closed
    codec parser (rejects multi-element/malformed/out-of-range payloads
    rather than silently truncating them)."""
    return parse_captured_state(value)


def steps_between(state_a: int, state_b: int, max_steps: int = 1_000_000) -> int:
    """Count forward Lehmer-recurrence steps needed to go from encoded
    state `state_a` to encoded state `state_b`, decoding both endpoints
    into raw recurrence space first (see module docstring). Raises
    ValueError (never silently caps/wraps) if `state_b` is not reached
    within `max_steps` -- a genuine desync (or a caller bug) must fail
    loudly, not report a fabricated count."""
    return _codec_steps_between(state_a, state_b, max_steps=max_steps)


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
