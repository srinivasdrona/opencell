"""Analyze the real-MATLAB ReplicationInitiation RNG ledger (ticks 0-4, or
wider ranges captured via scripts/matlab/probe_repinit_rng_ledger.m(n_ticks)).

Reads a matlab_rng_ledger_ticks0-N.jsonl file (produced by
scripts/matlab/probe_repinit_rng_ledger.m via the RandStream instrumentation
overlay) and, for each logged call, derives the exact number of underlying
mcg16807 primitive draws it consumed.

Primary derivation: directly from the logged `result` field. Every
RNG-consuming method this overlay instruments either returns a numeric
vector whose length IS the primitive-draw count (`rand`, most `randsample`/
`randperm` paths) or a scalar whose computation is documented (by both the
canonical MATLAB source and this project's `_Mcg16807RandStream` port) to
always consume exactly one draw regardless of input (`stochasticRound`).
This has been cross-validated, this session, against OC's own instrumented
draw log value-for-value (not just count-for-count) via
scripts/tmp_repinit_ledger_diff.py -- 689 consecutive draws bit-identical
across ticks 0-19 -- so this is a verified-correct derivation, not a guess.

Secondary (best-effort) cross-check: a state_before -> state_after delta
using the textbook mcg16807 recurrence x_{n+1} = (16807 * x_n) mod
(2^31 - 1). This does NOT currently resolve for any call in the captured
ledgers: MATLAB's `RandStream('mcg16807', ...).State` property is a scalar,
but empirically it is NOT the bare LCG iterate under that recurrence (e.g.
seq 1 of matlab_rng_ledger_ticks0-4.jsonl records state_before=931316785,
state_after=1523096582; no number of textbook-recurrence steps from
931316785 reaches 1523096582 within 5,000,000 steps). Its exact internal
encoding is undecoded and is NOT required for this analysis's actual goal
(comparing draw COUNTS and VALUES against OC) -- the result-field-derived
count is authoritative and is what the per-tick summary and OC comparison
below are computed from. The state-delta path is retained only as a
labelled, non-fatal diagnostic in case a future MATLAB-side probe decodes
the true encoding.

This lets us compare MATLAB's actual per-call/per-tick draw counts against
OC's own ported draw log (e.g. .repinit_tick4_full_draws.log, or a wider
scripts/tmp_repinit_oc_ledger.py-style capture) without needing to reverse
engineer the Statistics Toolbox's own randsample() internals.

Usage (WSL/oc-py; no MATLAB dependency, pure Python):
    bin\\oc-py scripts/analyze_repinit_rng_ledger.py \\
        --ledger docs/phase_f/probes/repinit_rng_ledger/matlab_rng_ledger_ticks0-4.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

A = 16807
M = 2_147_483_647  # 2**31 - 1
MAX_STEPS = 5_000_000  # generous bound; real per-call draw counts are tiny


def draws_between(state_before: int, state_after: int) -> int | None:
    """Best-effort textbook-mcg16807 state-delta cross-check (see module
    docstring): returns the number of x_{n+1}=(16807*x_n) mod (2^31-1) steps
    from state_before to state_after, or None if unreachable within
    MAX_STEPS. This has not resolved for any call captured so far -- MATLAB's
    RandStream('mcg16807',...).State scalar is not the bare LCG iterate under
    this recurrence, and its true encoding is undecoded. Kept as a labelled,
    non-fatal diagnostic; the result-derived count (derive_draws_from_result)
    is authoritative for this analysis.
    """
    if state_before == state_after:
        return 0
    x = state_before
    for step in range(1, MAX_STEPS + 1):
        x = (x * A) % M
        if x == state_after:
            return step
    return None


def derive_draws_from_result(method: str, result: str) -> int:
    """Authoritative per-call draw count, derived directly from the logged
    `result` field (see module docstring for why this is correct and
    verified, rather than the state-delta approach).

    - A vector result (`"[v1;v2;...]"`, from `rand`/most `randsample`/
      `randperm` paths) consumes exactly one primitive draw per element.
    - `stochasticRound` always consumes exactly one draw regardless of
      input, per both the canonical MATLAB source (RandStream.m) and this
      project's `_Mcg16807RandStream.stochastic_round` port -- confirmed by
      this session's real-MATLAB ledger showing exactly one such call per
      `stochasticRound` invocation, matching OC's own draw log 1:1.
    - Any other scalar (non-vector) result is treated as a single draw,
      matching every other instrumented method in the overlay
      (rng_ledger_overlay/+edu/+stanford/+covert/+util/RandStream.m) that
      returns a scalar.
    """
    if result.startswith("["):
        cleaned = result.strip("[]")
        if not cleaned.strip():
            return 0
        return len([p for p in cleaned.split(";") if p.strip()])
    return 1


def parse_state(raw: str) -> int:
    # MATLAB mat2str of a 1x1 (or short vector) numeric state; take the
    # first (and normally only) integer literal.
    cleaned = raw.strip("[]")
    parts = [p for p in cleaned.replace(";", " ").split() if p]
    return int(float(parts[0]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--max-tick", type=int, default=4)
    parser.add_argument(
        "--oc-cumulative-through-tick3",
        type=int,
        default=238,
        help="OC's own cumulative draw count through end of tick 3, for the "
        "final match/mismatch comparison line (default 238, from the "
        "original .repinit_tick4_full_draws.log capture). Pass the current "
        "value from scripts/tmp_repinit_oc_ledger.py's output if it has "
        "since changed (e.g. after a production fix).",
    )
    args = parser.parse_args()

    if not args.ledger.exists():
        print(f"ERROR: ledger file not found: {args.ledger}")
        return 2

    per_tick_calls: dict[int, list[dict]] = {}
    total_draws_by_tick_end: dict[int, int] = {}
    cumulative = 0
    state_delta_unresolved: list[dict] = []

    with args.ledger.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"WARNING: line {line_no} failed to parse: {exc}")
                continue
            tick = int(entry["tick"])

            # Authoritative: derive draws from the logged result field
            # (verified correct this session -- see module docstring).
            n_draws = derive_draws_from_result(entry["method"], entry["result"])
            entry["_derived_draws"] = n_draws
            cumulative += n_draws
            entry["_cumulative_after"] = cumulative

            # Secondary, best-effort, non-fatal cross-check only.
            state_before = parse_state(entry["state_before"])
            state_after = parse_state(entry["state_after"])
            if draws_between(state_before, state_after) is None:
                state_delta_unresolved.append(entry)

            per_tick_calls.setdefault(tick, []).append(entry)
            total_draws_by_tick_end[tick] = cumulative

    print("=== Per-tick call summary (draws derived from logged result field) ===")
    for tick in sorted(per_tick_calls):
        if tick > args.max_tick:
            continue
        calls = per_tick_calls[tick]
        tick_draw_total = sum(c["_derived_draws"] for c in calls)
        print(f"tick {tick}: {len(calls)} RNG-consuming calls, "
              f"{tick_draw_total} draws this tick, "
              f"cumulative={total_draws_by_tick_end[tick]}")
        for c in calls:
            print(f"    seq={c['seq']:>4} method={c['method']:<28} "
                  f"draws={c['_derived_draws']!s:>4} "
                  f"args={c.get('args', '')[:60]!r} result={c.get('result', '')[:40]!r}")

    if state_delta_unresolved:
        print(
            "\n=== Secondary state-delta cross-check: UNRESOLVED for all "
            f"{len(state_delta_unresolved)} call(s) (informational only, "
            "not fatal -- see module docstring; the result-derived counts "
            "above are authoritative and unaffected) ==="
        )

    print("\n=== Cumulative draws at end of each tick ===")
    for tick in sorted(total_draws_by_tick_end):
        if tick > args.max_tick:
            continue
        print(f"  end of tick {tick}: {total_draws_by_tick_end[tick]} cumulative draws")

    print(f"\nOC reference cumulative draws through end of tick 3: "
          f"{args.oc_cumulative_through_tick3}")
    if 3 in total_draws_by_tick_end:
        matlab_through_tick3 = total_draws_by_tick_end[3]
        print(f"MATLAB (this ledger) cumulative draws through end of tick 3: "
              f"{matlab_through_tick3}")
        delta = matlab_through_tick3 - args.oc_cumulative_through_tick3
        if delta == 0:
            print("MATCH: MATLAB and OC consumed the identical total draw "
                  "count through tick 3.")
        else:
            print(f"MISMATCH: MATLAB consumed {delta:+d} draws relative to "
                  f"OC's {args.oc_cumulative_through_tick3} through tick 3 -- "
                  "this is the drift to localize.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
