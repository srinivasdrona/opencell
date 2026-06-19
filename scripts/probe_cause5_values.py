"""Per-process L2.5 no-hints value probe (tick-0).

For each of 6 CAUSE_5 processes, run the harness in isolated single-process mode
with disable_trace_hints=True and capture the structured failure record.

The record contains:
- process_wid: which WID first diverged
- observable: which channel (substrates / enzymes / boundEnzymes / ...)
- karr_val: what Karr's trace says
- oc_val: what OC emitted
- diff: oc_val - karr_val

This tells us the SHAPE of the divergence per process:
- 'channel emits zeros / matches before-state' -> still missing-emit bug
- 'channel emits wrong nonzero value' -> value-level biology gap
- 'CAUSE_5 disappears -> process now green isolated' -> the Group A fix worked, pair failure is harness/CAUSE_4
"""
from __future__ import annotations

import json
import traceback
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

import pytest

from tests.vivarium.l2_2_replay_common_v2 import run_integrated_replay_v2

PROCESSES = [
    "DNASupercoiling",
    "FtsZPolymerization",
    "ProteinModification",
    "RNADecay",
    "Transcription",
    "Replication",
    "ReplicationInitiation",
]


def probe_one(process_name: str) -> dict:
    """Run the harness in isolated mode and capture structured failure record."""
    buf_out = StringIO()
    buf_err = StringIO()
    try:
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            run_integrated_replay_v2(
                under_test_processes=[process_name],
                rng_seed=0,
                disable_trace_hints=True,
            )
        return {"process": process_name, "verdict": "ISOLATED PASS (no-hints)", "record": None}
    except pytest.fail.Exception as e:
        msg = str(e)
        # Format: "L2.2.v2 structured failure: <json>"
        if "structured failure:" in msg:
            json_part = msg.split("structured failure:", 1)[1].strip()
            try:
                record = json.loads(json_part)
                return {"process": process_name, "verdict": "ISOLATED FAIL", "record": record}
            except json.JSONDecodeError:
                return {"process": process_name, "verdict": "ISOLATED FAIL", "record_raw": json_part}
        return {"process": process_name, "verdict": "ISOLATED FAIL", "msg": msg}
    except Exception as e:
        return {
            "process": process_name,
            "verdict": f"PROBE ERROR: {type(e).__name__}",
            "msg": str(e),
            "tb": traceback.format_exc(limit=5),
        }


def main() -> None:
    print("=" * 80)
    print("Per-process L2.5 no-hints isolated tick-0 value probe")
    print("=" * 80)
    print()
    results = []
    for p in PROCESSES:
        print(f"--- {p} ---")
        r = probe_one(p)
        results.append(r)
        if r["verdict"] == "ISOLATED PASS (no-hints)":
            print(f"  GREEN: isolated replay passes; pair failure (if any) is harness/CAUSE_4 or interaction effect.")
        elif r["verdict"] == "ISOLATED FAIL" and r.get("record"):
            rec = r["record"]
            print(f"  RED: tick={rec.get('tick')} obs={rec.get('observable')} wid={rec.get('process_wid')}")
            print(f"       karr={rec.get('karr_val')}  oc={rec.get('oc_val')}  diff={rec.get('diff')}  mode={rec.get('compare_mode')}")
            print(f"       cause={rec.get('cause_code')}")
            # Classify the value
            karr_v = rec.get('karr_val', 0)
            oc_v = rec.get('oc_val', 0)
            if oc_v == 0 and karr_v != 0:
                print(f"       SHAPE: 'oc emits zero (no movement)' -> still missing-emit")
            elif oc_v != 0 and karr_v == 0:
                print(f"       SHAPE: 'oc emits movement when Karr is still' -> over-emit")
            elif oc_v != 0 and karr_v != 0:
                print(f"       SHAPE: 'oc and karr both move but disagree' -> value-level biology gap")
            else:
                print(f"       SHAPE: 'both zero??' -> probe bug or harness edge case")
        else:
            print(f"  ERROR: {r.get('verdict')}  {r.get('msg', '')[:200]}")
        print()

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for r in results:
        rec = r.get("record") or {}
        line = f"  {r['process']:25s}  {r['verdict']}"
        if rec:
            line += f"  obs={rec.get('observable', '?'):15s} wid={rec.get('process_wid', '?'):20s}  karr={rec.get('karr_val', '?')}  oc={rec.get('oc_val', '?')}"
        print(line)


if __name__ == "__main__":
    main()
