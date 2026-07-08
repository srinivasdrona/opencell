"""Unit tests for the L2.0 observable-schema gate (scripts/probe_l2_0_schema_audit.py).

These tests exercise the *pure* gate logic (`verdict`, `_gate_result`) and the
oracle-absent SKIP path, so they run in CI without the gitignored per-process
``.mat`` oracle inputs. The full 28-process comparison is enforced locally /
in the nightly full-source run (mirroring the L1b wiring gate's MATLAB-anchor
skip).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "probe_l2_0_schema_audit.py"

_spec = importlib.util.spec_from_file_location("_l2_0_probe", _SCRIPT)
assert _spec is not None and _spec.loader is not None
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


# ── verdict() ─────────────────────────────────────────────────────────────

def test_verdict_error_when_err_present() -> None:
    assert probe.verdict({"a"}, {"a"}, "ImportError: boom") == "ERROR"


def test_verdict_red_when_no_overlap() -> None:
    assert probe.verdict({"a", "b"}, {"c", "d"}, None) == "RED"


def test_verdict_green_when_karr_subset_of_oc() -> None:
    assert probe.verdict({"a", "b"}, {"a", "b", "c"}, None) == "GREEN"


def test_verdict_amber_when_partial_overlap() -> None:
    assert probe.verdict({"a", "b", "c"}, {"a", "z"}, None) == "AMBER"


# ── _gate_result() ────────────────────────────────────────────────────────

def _row(process: str, v: str) -> dict[str, Any]:
    return {"process": process, "verdict": v}


def test_gate_pass_all_green() -> None:
    rows = [_row(f"P{i}", "GREEN") for i in range(28)]
    counts = {"GREEN": 28, "AMBER": 0, "RED": 0, "ERROR": 0}
    code, msg = probe._gate_result(rows, counts, expected_n=28)
    assert code == 0
    assert "PASS" in msg and "28/28" in msg


def test_gate_fail_on_red() -> None:
    rows = [_row("P0", "RED")] + [_row(f"P{i}", "GREEN") for i in range(1, 28)]
    counts = {"GREEN": 27, "AMBER": 0, "RED": 1, "ERROR": 0}
    code, msg = probe._gate_result(rows, counts, expected_n=28)
    assert code == 1
    assert "FAIL" in msg and "P0=RED" in msg


def test_gate_fail_on_amber_regression() -> None:
    rows = [_row("P0", "AMBER")] + [_row(f"P{i}", "GREEN") for i in range(1, 28)]
    counts = {"GREEN": 27, "AMBER": 1, "RED": 0, "ERROR": 0}
    code, msg = probe._gate_result(rows, counts, expected_n=28)
    assert code == 1
    assert "FAIL" in msg and "P0=AMBER" in msg


def test_gate_fail_on_incomplete_oracle_set() -> None:
    rows = [_row(f"P{i}", "GREEN") for i in range(10)]
    counts = {"GREEN": 10, "AMBER": 0, "RED": 0, "ERROR": 0}
    code, msg = probe._gate_result(rows, counts, expected_n=28)
    assert code == 1
    assert "incomplete oracle set" in msg and "10/28" in msg


# ── SKIP path (oracle inputs absent) ──────────────────────────────────────

def test_main_skips_cleanly_when_inputs_absent(monkeypatch, capsys) -> None:
    absent = probe.REPO / "data" / "m1_sources" / "karr_native" / "_absent_test_dir"
    monkeypatch.setattr(probe, "MATS_DIR", absent)
    rc = probe.main()
    assert rc == 0
    assert "SKIPPED" in capsys.readouterr().out
