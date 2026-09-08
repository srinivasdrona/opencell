#!/usr/bin/env python3
"""Mechanically promote the Cytokinesis row in
``docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json``.

Never hand-edits the manifest JSON. Combines two independently-generated,
reproducible pieces of evidence -- exactly the same "audit tool for
trace-window discovery + a dedicated pytest node for the bit-identity
verdict" pattern already used by every other EXISTING_WINDOW_PASS row in
this manifest (Cytokinesis's own RNG-state-restoring replay semantics are
implemented in the L2 replay test's harness, not in the generic
``l21_active_window_audit.py`` engine -- see that module's
``_classify_live_trace_candidate`` docstring history):

1. ``scripts/l21_active_window_audit.py --process Cytokinesis`` for
   mechanical trace-window discovery (chosen trace, sha256, first-active
   tick, dec-005 DNADamage source-hash-binding status).
2. A fresh, live run of
   ``tests/vivarium/test_karr_cytokinesis_l2_replay.py::
   test_karr_cytokinesis_l2_event_replay_m5000_randstream_bound`` (the
   task-mandated M5000 seed-36 promotion gate) for the actual bit-identity
   replay verdict.

Fails closed: refuses to write EXISTING_WINDOW_PASS unless BOTH the
dec-005 DNADamage source-hash binding verifies AND the live pytest run
passes; writes CODE_GAP with the concrete failure reason otherwise.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.l21_active_window_audit import (  # noqa: E402
    CLASS_EXISTING_WINDOW_PASS,
    run_audit,
)

MANIFEST_PATH = _REPO_ROOT / "docs" / "phase_f" / "l2_1" / "L21_ACTIVE_WINDOWS_MANIFEST.json"
PROMOTION_NODEID = (
    "tests/vivarium/test_karr_cytokinesis_l2_replay.py::"
    "test_karr_cytokinesis_l2_event_replay_m5000_randstream_bound[event_seed_36_m5000]"
)
MECHANICAL_SCAN_COMMAND = "bin\\\\oc-py.cmd scripts/l21_active_window_audit.py --process Cytokinesis --write-json <temp>"
REPLAY_COMMAND = f"bin\\\\oc-pytest.cmd -q {PROMOTION_NODEID}"


def _repo_relative_source_path(path: str, *, repo_root: Path = _REPO_ROOT) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(
            "Cytokinesis promotion requires the selected trace to exist inside "
            f"the current repository root: trace={resolved} repo_root={repo_root.resolve()}"
        ) from exc


def _portable_source(chosen_trace: dict[str, object]) -> dict[str, object]:
    relative_path = _repo_relative_source_path(str(chosen_trace["path"]))
    return {
        "path": relative_path,
        "repo_relative_hint": relative_path,
        "sha256": chosen_trace["sha256"],
        "trace_family": chosen_trace["trace_family"],
        "source_manifest": chosen_trace["source_manifest"],
    }


def _run_promotion_pytest() -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", PROMOTION_NODEID],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    stdout_tail = "\n".join(line for line in completed.stdout.strip().splitlines()[-20:] if line)
    stderr_tail = "\n".join(line for line in completed.stderr.strip().splitlines()[-20:] if line)
    return {
        "passed": completed.returncode == 0,
        "nodeid": PROMOTION_NODEID,
        "returncode": completed.returncode,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }


def build_promoted_row() -> dict[str, object]:
    scan = run_audit(target_processes=("Cytokinesis",))
    scan_row = scan["rows"][0]
    chosen_trace = scan_row["chosen_trace"]
    if chosen_trace is None:
        raise SystemExit(f"mechanical scan found no active Cytokinesis trace: {scan_row}")
    source = _portable_source(chosen_trace)

    dnadamage_binding = scan_row.get("dnadamage_source_binding")
    if dnadamage_binding is None or not dnadamage_binding.get("verified"):
        return {
            "process": "Cytokinesis",
            "classification": "CODE_GAP",
            "existing_trace_suffices": True,
            "activity_predicate": scan_row["activity_predicate"],
            "source": source,
            "dnadamage_source_binding": dnadamage_binding,
            "failure_reason": "dec-005 DNADamage source-hash binding did not verify; refusing to promote",
        }

    replay_result = _run_promotion_pytest()
    trace_window = {
        "n_ticks": chosen_trace["n_ticks"],
        "tick_offset": chosen_trace["tick_offset"],
        "first_active_local_tick": chosen_trace["first_active_tick"],
        "first_active_absolute_tick": chosen_trace["first_active_absolute_tick"],
        "active_tick_count": chosen_trace["active_tick_count"],
        "first_active_detail": chosen_trace["first_active_detail"],
    }
    row = {
        "process": "Cytokinesis",
        "classification": CLASS_EXISTING_WINDOW_PASS if replay_result["passed"] else "CODE_GAP",
        "existing_trace_suffices": True,
        "activity_predicate": scan_row["activity_predicate"],
        "source": source,
        "trace_window": trace_window,
        "mechanical_scan": {
            "scanned_candidate_count": scan_row["scanned_candidate_count"],
            "command": MECHANICAL_SCAN_COMMAND,
        },
        "replay_evidence": {
            "type": "pytest",
            "nodeid": PROMOTION_NODEID,
            "outcome": "passed" if replay_result["passed"] else "failed",
            "command": REPLAY_COMMAND,
        },
        "dnadamage_source_binding": dnadamage_binding,
    }
    if not replay_result["passed"]:
        row["failure_reason"] = (
            f"live pytest run of the M5000 promotion gate failed (returncode={replay_result['returncode']}): "
            f"{replay_result['stderr_tail'] or replay_result['stdout_tail']}"
        )
    return row


def main() -> int:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    new_row = build_promoted_row()

    replaced = False
    for idx, row in enumerate(payload["rows"]):
        if row.get("process") == "Cytokinesis":
            payload["rows"][idx] = new_row
            replaced = True
            break
    if not replaced:
        raise SystemExit("Cytokinesis row not found in manifest; refusing to append a new row mechanically")

    counts: dict[str, int] = {}
    for row in payload["rows"]:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    payload["counts"] = counts

    if new_row["classification"] == CLASS_EXISTING_WINDOW_PASS:
        nodeids = [
            row["replay_evidence"]["nodeid"]
            for row in payload["rows"]
            if row.get("classification") == CLASS_EXISTING_WINDOW_PASS and isinstance(row.get("replay_evidence"), dict)
        ]
        payload["pytest_replay_command"] = "bin\\\\oc-pytest.cmd -q " + " ".join(nodeids)

    MANIFEST_PATH.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Promoted Cytokinesis row: classification={new_row['classification']}")
    print(json.dumps(new_row, indent=2, sort_keys=False))
    return 0 if new_row["classification"] == CLASS_EXISTING_WINDOW_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
