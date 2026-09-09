#!/usr/bin/env python3
"""Mechanically promote the TranscriptionalRegulation row in
``docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json``.

Never hand-edits the manifest JSON. Mirrors the exact promotion pattern
already established by ``scripts/l21_promote_cytokinesis_manifest.py``
(mechanical trace-window discovery via ``l21_active_window_audit.py`` +
a live, fresh rerun of the process's own dedicated bit-identity L2 replay
pytest node), adapted for TranscriptionalRegulation's dec-006 shared
``Chromosome.randStream`` ledger (rather than Cytokinesis/DNADamage's
dec-005 binding, which does not apply to this process):

1. ``scripts/l21_active_window_audit.py --process TranscriptionalRegulation``
   for mechanical trace-window discovery (chosen trace, sha256,
   first-active tick).
2. A fresh, live run of
   ``tests/vivarium/test_karr_transcriptional_regulation_l2_replay.py::
   test_karr_transcriptional_regulation_l2_event_replay[event_seed_0]``
   for the actual bit-identity replay verdict (loads and replays under
   the dec-006 chromosome_rand_stream_state ledger).

Fails closed: refuses to write EXISTING_WINDOW_PASS unless the live
pytest run passes; writes CODE_GAP with the concrete failure reason
otherwise. Also pins this row's OWN companion
``chromosome_rand_stream_ledger`` sidecar sha256 (see
``scripts/l21_active_window_audit.py::_verify_manifest_ledger_binding``'s
docstring for why this is a separate, additional tamper-protection check
beyond the ledger's own internally-recorded source-file hashes).
"""

from __future__ import annotations

import hashlib
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
    "tests/vivarium/test_karr_transcriptional_regulation_l2_replay.py::"
    "test_karr_transcriptional_regulation_l2_event_replay[event_seed_0]"
)
MECHANICAL_SCAN_COMMAND = (
    "bin\\\\oc-py.cmd scripts/l21_active_window_audit.py --process TranscriptionalRegulation --write-json <temp>"
)
REPLAY_COMMAND = f"bin\\\\oc-pytest.cmd -q {PROMOTION_NODEID}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_relative_source_path(path: str, *, repo_root: Path = _REPO_ROOT) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(
            "TranscriptionalRegulation promotion requires the selected trace to exist inside "
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
    scan = run_audit(target_processes=("TranscriptionalRegulation",))
    scan_row = scan["rows"][0]
    chosen_trace = scan_row["chosen_trace"]
    if chosen_trace is None:
        raise SystemExit(f"mechanical scan found no active TranscriptionalRegulation trace: {scan_row}")
    source = _portable_source(chosen_trace)
    source_path = _REPO_ROOT / source["path"]

    replay_result = _run_promotion_pytest()
    trace_window = {
        "n_ticks": chosen_trace["n_ticks"],
        "tick_offset": chosen_trace["tick_offset"],
        "first_active_local_tick": chosen_trace["first_active_tick"],
        "first_active_absolute_tick": chosen_trace["first_active_absolute_tick"],
        "active_tick_count": chosen_trace["active_tick_count"],
        "first_active_detail": chosen_trace["first_active_detail"],
    }
    row: dict[str, object] = {
        "process": "TranscriptionalRegulation",
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
        "dnadamage_source_binding": scan_row.get("dnadamage_source_binding"),
    }

    ledger_path = source_path.with_suffix("").with_suffix(".chromosome_rand_stream_ledger.json")
    if ledger_path.exists():
        ledger_relative = _repo_relative_source_path(str(ledger_path))
        row["chromosome_rand_stream_ledger"] = {
            "path": ledger_relative,
            "sha256": _sha256(ledger_path),
            "note_2026_09_08": (
                "Pins THIS manifest row's own promotion evidence to one exact ledger sidecar "
                "file (dec-006), independent of the ledger's own self-reported provenance fields "
                "(dnadamage_source_sha256/chromosome_source_sha256/randstream_util_source_sha256/"
                "trace_sha256, all checked separately by "
                "chromosome_rand_stream_ledger.load_chromosome_rand_stream_ledger). "
                "scripts/l21_active_window_audit.py::_verify_manifest_ledger_binding hard-fails "
                "(never skips) verify_active_window_manifest_row's CLASS_EXISTING_WINDOW_PASS "
                "re-check if the live sidecar next to the resolved source trace does not hash to "
                "exactly this value."
            ),
        }

    if not replay_result["passed"]:
        row["failure_reason"] = (
            f"live pytest run of the event-window bit-identity replay gate failed "
            f"(returncode={replay_result['returncode']}): "
            f"{replay_result['stderr_tail'] or replay_result['stdout_tail']}"
        )
    return row


def main() -> int:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    new_row = build_promoted_row()

    replaced = False
    for idx, row in enumerate(payload["rows"]):
        if row.get("process") == "TranscriptionalRegulation":
            payload["rows"][idx] = new_row
            replaced = True
            break
    if not replaced:
        raise SystemExit(
            "TranscriptionalRegulation row not found in manifest; refusing to append a new row mechanically"
        )

    counts: dict[str, int] = {
        CLASS_EXISTING_WINDOW_PASS: 0,
        "CODE_GAP": 0,
        "MISSING_ACTIVE_EXTRACTION": 0,
    }
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
    print(f"Promoted TranscriptionalRegulation row: classification={new_row['classification']}")
    print(json.dumps(new_row, indent=2, sort_keys=False))
    return 0 if new_row["classification"] == CLASS_EXISTING_WINDOW_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
