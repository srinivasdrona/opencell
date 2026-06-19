"""Probe H10: allocator-budget squeeze at DNASupercoiling.next_update entry.

Investigation-only probe. Does not modify harness behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Ensure imports resolve to this worktree.
_REPO_ROOT = Path(__file__).resolve().parents[1]
import sys

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

import tests.vivarium.l2_2_replay_common_v2 as h


TARGET_PROCESS = "DNASupercoiling"
PAIR = ["ChromosomeCondensation", "DNASupercoiling"]
ISOLATED = ["DNASupercoiling"]


@dataclass
class Capture:
    case: str
    call_index: int
    substrates_allocated_key_present: bool
    substrates_allocated_top_keys: list[str]
    allocated_dnas_atp: float | str
    allocated_dnas_h2o: float | str
    raw_substrates_atp: float | str
    raw_substrates_h2o: float | str
    allocated_or_state_atp: float
    allocated_or_state_h2o: float
    run_outcome: str


def _as_float_or_absent(value: Any) -> float | str:
    try:
        return float(value)
    except (TypeError, ValueError):
        return "ABSENT"


def _fmt(value: float | str) -> str:
    if isinstance(value, str):
        return value
    return str(int(round(float(value))))


def _collect_snapshot(*, case: str, call_index: int, proc: Any, states: dict[str, Any]) -> Capture:
    has_alloc_key = isinstance(states, dict) and "substrates_allocated" in states
    alloc_root_raw = states.get("substrates_allocated") if isinstance(states, dict) else None
    alloc_root = alloc_root_raw if isinstance(alloc_root_raw, dict) else {}
    alloc_top_keys = sorted(str(k) for k in alloc_root.keys())

    dnas_alloc_raw = alloc_root.get(proc.name, {})
    dnas_alloc = dnas_alloc_raw if isinstance(dnas_alloc_raw, dict) else {}
    alloc_atp = _as_float_or_absent(dnas_alloc.get(proc.atp_wid, "ABSENT"))
    alloc_h2o = _as_float_or_absent(dnas_alloc.get(proc.h2o_wid, "ABSENT"))

    substrates_raw = states.get("substrates") if isinstance(states, dict) else None
    substrates = substrates_raw if isinstance(substrates_raw, dict) else {}
    raw_atp = _as_float_or_absent(substrates.get(proc.atp_wid, "ABSENT"))
    raw_h2o = _as_float_or_absent(substrates.get(proc.h2o_wid, "ABSENT"))

    available_atp = float(proc._allocated_or_state(dnas_alloc, proc.atp_wid))
    available_h2o = float(proc._allocated_or_state(dnas_alloc, proc.h2o_wid))

    return Capture(
        case=case,
        call_index=call_index,
        substrates_allocated_key_present=has_alloc_key,
        substrates_allocated_top_keys=alloc_top_keys,
        allocated_dnas_atp=alloc_atp,
        allocated_dnas_h2o=alloc_h2o,
        raw_substrates_atp=raw_atp,
        raw_substrates_h2o=raw_h2o,
        allocated_or_state_atp=available_atp,
        allocated_or_state_h2o=available_h2o,
        run_outcome="",
    )


def _run_case(case: str, under_test_processes: list[str]) -> Capture:
    process_cls = h._PROCESS_SPECS[TARGET_PROCESS].process_cls
    original_next_update = process_cls.next_update
    captured: list[Capture] = []
    call_count = 0
    run_outcome = "PASS"

    def wrapped_next_update(self: Any, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if not captured:
            captured.append(
                _collect_snapshot(
                    case=case,
                    call_index=call_count,
                    proc=self,
                    states=states,
                )
            )
        return original_next_update(self, timestep, states)

    process_cls.next_update = wrapped_next_update
    try:
        try:
            h.run_integrated_replay_v2(
                under_test_processes=under_test_processes,
                rng_seed=0,
                disable_trace_hints=True,
            )
        except BaseException as exc:
            run_outcome = f"{type(exc).__name__}: {exc}"
    finally:
        process_cls.next_update = original_next_update

    if not captured:
        raise RuntimeError(f"{case}: probe did not capture DNASupercoiling.next_update call.")
    snap = captured[0]
    snap.run_outcome = run_outcome
    return snap


def _is_float(value: float | str) -> bool:
    return isinstance(value, (float, int))


def _verdict(composition: Capture, isolation: Capture) -> str:
    comp_squeezed = (
        _is_float(composition.raw_substrates_atp)
        and _is_float(composition.raw_substrates_h2o)
        and composition.allocated_or_state_atp < float(composition.raw_substrates_atp)
        and composition.allocated_or_state_h2o < float(composition.raw_substrates_h2o)
    )
    iso_full_pool = (
        _is_float(isolation.raw_substrates_atp)
        and _is_float(isolation.raw_substrates_h2o)
        and isolation.allocated_or_state_atp == float(isolation.raw_substrates_atp)
        and isolation.allocated_or_state_h2o == float(isolation.raw_substrates_h2o)
    )
    comp_reads_alloc = (
        _is_float(composition.allocated_dnas_atp)
        and _is_float(composition.allocated_dnas_h2o)
        and composition.allocated_or_state_atp == float(composition.allocated_dnas_atp)
        and composition.allocated_or_state_h2o == float(composition.allocated_dnas_h2o)
    )
    if comp_squeezed and comp_reads_alloc and iso_full_pool:
        return "CONFIRMED"
    if not comp_squeezed:
        return "REJECTED"
    return "REDIRECTED"


def _print_case_row(c: Capture) -> None:
    print(
        " | ".join(
            [
                c.case,
                str(c.substrates_allocated_key_present),
                ",".join(c.substrates_allocated_top_keys) if c.substrates_allocated_top_keys else "NONE",
                _fmt(c.allocated_dnas_atp),
                _fmt(c.allocated_dnas_h2o),
                _fmt(c.raw_substrates_atp),
                _fmt(c.raw_substrates_h2o),
                _fmt(c.allocated_or_state_atp),
                _fmt(c.allocated_or_state_h2o),
                str(c.call_index),
            ]
        )
    )


def main() -> None:
    composition = _run_case("composition", PAIR)
    isolation = _run_case("isolation", ISOLATED)
    verdict = _verdict(composition, isolation)

    print("=== H10 allocator-budget probe ===")
    print("under_test composition=['ChromosomeCondensation', 'DNASupercoiling'], isolation=['DNASupercoiling']")
    print("disable_trace_hints=True")
    print("")
    print(
        "case | has_substrates_allocated_key | substrates_allocated_top_keys | "
        "alloc[DNAS][ATP] | alloc[DNAS][H2O] | states['substrates'][ATP] | states['substrates'][H2O] | "
        "_allocated_or_state(ATP) | _allocated_or_state(H2O) | next_update_call_index"
    )
    print("-" * 260)
    _print_case_row(composition)
    _print_case_row(isolation)
    print("")
    print(f"composition_run_outcome={composition.run_outcome}")
    print(f"isolation_run_outcome={isolation.run_outcome}")
    print(f"VERDICT={verdict}")


if __name__ == "__main__":
    main()
