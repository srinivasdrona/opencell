"""Tamper/missing/skip closure tests for the discriminating_conditions
verifier extension to `scripts/l21_active_window_audit.py`
(`verify_discriminating_conditions`, `_run_pytest_nodeid`) and the
skip-vs-fail helper in `tests/vivarium/l2_replay_common.py`
(`skip_or_fail_missing_artifact`).

Opus review context: the prior verifier only re-ran ONE pytest nodeid and
trusted its return code alone (a SKIPPED test returns code 0, identical to
a genuinely PASSED one), and never independently validated the
discriminating_conditions evidence block's own sha256/predicted values.
This file proves the fixed behavior fail-closed under every scenario that
would previously have silently passed:
  - a tampered condition source sha256
  - a tampered predicted_and_actual value
  - a missing condition source file
  - a missing/empty replay_evidence.nodeids list
  - a nodeid that SKIPS instead of passing
  - the skip_or_fail_missing_artifact helper's fail-vs-skip branching

Run via:
    bin\\oc-pytest tests/scripts/test_l21_host_interaction_discriminating_conditions_verifier.py -v
"""

from __future__ import annotations

import copy
import json
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
_VIVARIUM_TESTS_DIR = REPO_ROOT / "tests" / "vivarium"
if str(_VIVARIUM_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS_DIR))

import l21_active_window_audit as active_windows  # noqa: E402
from l2_replay_common import skip_or_fail_missing_artifact  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "docs" / "phase_f" / "l2_1" / "L21_ACTIVE_WINDOWS_MANIFEST.json"


def _load_manifest_payload() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _write_single_row_manifest(tmp_path: Path, process_name: str) -> Path:
    payload = _load_manifest_payload()
    row = next(copy.deepcopy(item) for item in payload["rows"] if item["process"] == process_name)
    payload["rows"] = [row]
    manifest_path = tmp_path / "single_row_active_window_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _host_row(manifest_path: Path) -> dict:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return payload["rows"][0]


def test_discriminating_conditions_present_on_current_hostinteraction_row():
    """Sanity precondition for every test below: the real, current manifest
    row must actually carry a discriminating_conditions block with all 5
    preregistered conditions and 3 nodeids -- if this ever regresses to
    missing, every tamper test below would vacuously pass for the wrong
    reason."""
    payload = _load_manifest_payload()
    row = next(item for item in payload["rows"] if item["process"] == "HostInteraction")
    block = row["discriminating_conditions"]
    assert len(block["conditions"]) == 5
    assert len(block["replay_evidence"]["nodeids"]) == 3


def test_genuine_hostinteraction_row_verifies_clean(tmp_path: Path):
    """Baseline (no tampering): the real row must fully re-verify, proving
    the extension actually exercises real data end-to-end, not just mocks."""
    manifest_path = _write_single_row_manifest(tmp_path, "HostInteraction")
    verification = active_windows.verify_active_window_manifest_row(manifest_path, "HostInteraction")
    assert verification["verification_status"] == active_windows.MANIFEST_VERIFY_EXISTING_WINDOW_PASS
    disc = verification["discriminating_conditions_verification"]
    assert disc["passed"] is True
    assert all(c["ok"] for c in disc["conditions"])
    assert all(r["passed"] for r in disc["nodeid_results"])


def test_tampered_condition_sha256_fails_closed(tmp_path: Path):
    manifest_path = _write_single_row_manifest(tmp_path, "HostInteraction")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["rows"][0]["discriminating_conditions"]["conditions"][0]["source"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    row = _host_row(manifest_path)
    disc = active_windows.verify_discriminating_conditions(row, manifest_path, "HostInteraction")
    assert disc["passed"] is False
    assert "sha256 mismatch" in disc["conditions"][0]["failure_reason"]
    # Short-circuit property: a cheap per-condition failure must skip the
    # expensive pytest-subprocess nodeid reruns entirely.
    assert disc["nodeid_results"] == []


def test_tampered_condition_predicted_value_fails_closed(tmp_path: Path):
    """Flip one recorded predicted_and_actual boolean so it no longer
    matches the genuine trace -- proves the verifier actually re-reads and
    compares real trace values, not just trusts the recorded dict."""
    manifest_path = _write_single_row_manifest(tmp_path, "HostInteraction")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    condition = payload["rows"][0]["discriminating_conditions"]["conditions"][0]
    field = next(iter(condition["predicted_and_actual"]))
    condition["predicted_and_actual"][field] = not condition["predicted_and_actual"][field]
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    row = _host_row(manifest_path)
    disc = active_windows.verify_discriminating_conditions(row, manifest_path, "HostInteraction")
    assert disc["passed"] is False
    assert "mismatch vs genuine trace" in disc["conditions"][0]["failure_reason"]
    assert disc["nodeid_results"] == []


def test_missing_condition_source_fails_closed(tmp_path: Path):
    manifest_path = _write_single_row_manifest(tmp_path, "HostInteraction")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["rows"][0]["discriminating_conditions"]["conditions"][0]["source"]["path"] = (
        "data/m1_sources/karr_native/per_process_traces_v2_host_condition_does_not_exist_s000/HostInteraction_5ticks.mat"
    )
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    row = _host_row(manifest_path)
    disc = active_windows.verify_discriminating_conditions(row, manifest_path, "HostInteraction")
    assert disc["passed"] is False
    assert "missing" in disc["conditions"][0]["failure_reason"]
    assert disc["nodeid_results"] == []


def test_empty_nodeids_list_fails_closed(tmp_path: Path):
    manifest_path = _write_single_row_manifest(tmp_path, "HostInteraction")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["rows"][0]["discriminating_conditions"]["replay_evidence"]["nodeids"] = []
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    row = _host_row(manifest_path)
    disc = active_windows.verify_discriminating_conditions(row, manifest_path, "HostInteraction")
    assert disc["passed"] is False
    assert "nodeids" in disc["failure_reason"]


def test_missing_discriminating_conditions_block_fails_closed(tmp_path: Path):
    manifest_path = _write_single_row_manifest(tmp_path, "HostInteraction")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del payload["rows"][0]["discriminating_conditions"]
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    verification = active_windows.verify_active_window_manifest_row(manifest_path, "HostInteraction")
    # No discriminating_conditions block at all means the extension never
    # engages (backward compatible for other processes' rows that don't
    # carry this evidence shape) -- this is intentionally NOT a failure by
    # itself, but it must not silently claim the extension ran.
    assert verification["discriminating_conditions_verification"] is None


def test_skipped_nodeid_is_reported_as_failed_not_passed(tmp_path: Path):
    """The core "treat skipped as failure" property: pytest's own exit
    code is 0 for both an all-passed run and an all-skipped run, so a
    naive `returncode == 0` check cannot tell them apart. Build a real,
    throwaway pytest file whose sole test unconditionally skips, and prove
    `_run_pytest_nodeid` reports `passed=False` for it."""
    skip_test_file = tmp_path / "test_always_skips.py"
    skip_test_file.write_text(
        textwrap.dedent(
            """
            import pytest

            def test_this_always_skips():
                pytest.skip("intentional skip for containment test")
            """
        ),
        encoding="utf-8",
    )
    nodeid = f"{skip_test_file}::test_this_always_skips"
    result = active_windows._run_pytest_nodeid(nodeid)
    assert result["returncode"] == 0, "a skipped-only pytest run still exits 0"
    assert result["skipped_count"] == 1
    assert result["passed"] is False, "a skip must never be reported as passed"
    assert "SKIPPED" in result["error"]


def test_passing_nodeid_is_reported_as_passed(tmp_path: Path):
    """Companion positive control for the skip test above: a genuinely
    passing test must still be reported as passed=True, proving the skip
    detection doesn't over-fire on ordinary green output."""
    pass_test_file = tmp_path / "test_always_passes.py"
    pass_test_file.write_text(
        textwrap.dedent(
            """
            def test_this_always_passes():
                assert True
            """
        ),
        encoding="utf-8",
    )
    nodeid = f"{pass_test_file}::test_this_always_passes"
    result = active_windows._run_pytest_nodeid(nodeid)
    assert result["returncode"] == 0
    assert result["skipped_count"] == 0
    assert result["passed"] is True


def test_skip_or_fail_missing_artifact_fails_for_existing_window_pass_process():
    """HostInteraction's real manifest row is EXISTING_WINDOW_PASS, so a
    missing artifact for that process must FAIL, never skip."""
    with pytest.raises(pytest.fail.Exception):
        skip_or_fail_missing_artifact(
            Path("does/not/exist.mat"), "HostInteraction", "synthetic missing-artifact test"
        )


def test_skip_or_fail_missing_artifact_skips_for_non_pass_process():
    """A process whose manifest row is NOT EXISTING_WINDOW_PASS (e.g. a
    CODE_GAP row) carries no genuine-evidence claim, so a missing artifact
    for it legitimately skips rather than fails."""
    payload = _load_manifest_payload()
    non_pass_processes = [
        row["process"] for row in payload["rows"] if row["classification"] != active_windows.CLASS_EXISTING_WINDOW_PASS
    ]
    assert non_pass_processes, "expected at least one non-PASS row in the real manifest to exercise this branch"
    with pytest.raises(pytest.skip.Exception):
        skip_or_fail_missing_artifact(
            Path("does/not/exist.mat"), non_pass_processes[0], "synthetic missing-artifact test"
        )


def test_skip_or_fail_missing_artifact_skips_for_unknown_process():
    """A process name absent from the manifest entirely also legitimately
    skips (no classification means no genuine-evidence claim to violate)."""
    with pytest.raises(pytest.skip.Exception):
        skip_or_fail_missing_artifact(
            Path("does/not/exist.mat"), "NotARealProcessName", "synthetic missing-artifact test"
        )
