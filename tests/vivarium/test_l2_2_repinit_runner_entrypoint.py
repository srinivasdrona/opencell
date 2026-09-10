"""Tests for the ReplicationInitiation-specific runner entrypoint (R12).

Verifies the OFFICIAL evidence-generation path mechanically enforces
requested M == catalog M_ticks BEFORE any oracle loading/evaluation --
the exact gap an independent integration review required closed: the
generic `l2_2_design_a_runner.py` CLI accepts ANY `--ticks` value and
`_normalize_seed_axis` silently slices the oracle down to it, with
nothing failing closed on a mismatch. `sweep.runner_command` launches
THIS entrypoint (never the generic runner directly) for
ReplicationInitiation jobs -- see `scripts/l22_evidence/sweep.py`'s R12
docstring note.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENTRYPOINT_SCRIPT = _REPO_ROOT / "tests" / "vivarium" / "_l2_2_repinit_runner_entrypoint.py"

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import _l2_2_repinit_runner_entrypoint as entrypoint  # noqa: E402


def _skip_if_raw_data_absent() -> None:
    karr_native = _REPO_ROOT / "data" / "m1_sources" / "karr_native"
    if not (karr_native / "per_process_traces_v2_s000" / "ReplicationInitiation_200ticks.mat").is_file():
        pytest.skip(
            "Genuine gitignored RepInit raw seed traces are not present on this "
            "machine/checkout; this is a local-evidence verification test, not a "
            "CI-portable one."
        )


# --- Unit-level: entrypoint's own validation, no subprocess, no oracle I/O -


def test_validate_requested_m_rejects_wrong_process() -> None:
    with pytest.raises(entrypoint.RepInitEntrypointError, match="registered ONLY"):
        entrypoint.validate_requested_m(["--process", "Translation", "--ticks", "100"])


def test_validate_requested_m_rejects_100_ticks() -> None:
    """Reproduces the exact defect: requesting M=100 (every OTHER
    design_a_per_tick process's catalog M_ticks) for ReplicationInitiation
    (catalog M_ticks=200) must be rejected, never silently truncated."""
    with pytest.raises(entrypoint.RepInitEntrypointError, match="does not equal"):
        entrypoint.validate_requested_m(
            ["--process", "ReplicationInitiation", "--ticks", "100"]
        )


def test_validate_requested_m_accepts_200_ticks() -> None:
    """Must NOT raise for the correct, live catalog M_ticks value."""
    entrypoint.validate_requested_m(
        ["--process", "ReplicationInitiation", "--ticks", "200"]
    )


def test_validate_requested_m_requires_ticks_argument() -> None:
    with pytest.raises(entrypoint.RepInitEntrypointError, match="required"):
        entrypoint.validate_requested_m(["--process", "ReplicationInitiation"])


def test_main_rejects_before_delegating_to_shared_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """`main()` must never reach `l2_2_design_a_runner.main()` when the
    requested M is wrong -- proven here by making the shared runner's own
    `main` raise if ever called, then confirming a --ticks 100 invocation
    returns the CLI-error exit code (2) without tripping that guard."""

    def _boom(argv: object) -> int:
        raise AssertionError("l2_2_design_a_runner.main() must never be reached on a rejected request")

    import l2_2_design_a_runner

    monkeypatch.setattr(l2_2_design_a_runner, "main", _boom)
    exit_code = entrypoint.main(
        ["--process", "ReplicationInitiation", "--ticks", "100", "--seeds", "1", "--output-dir", "/tmp/unused"]
    )
    assert exit_code == 2


def test_main_delegates_to_shared_runner_when_m_is_correct(monkeypatch: pytest.MonkeyPatch) -> None:
    """`main()` must delegate to `l2_2_design_a_runner.main()` -- with the
    EXACT SAME argv -- once M validation passes. The shared runner itself
    is mocked here (a fast, pure-unit-level positive check) so this test
    does not incur the real ~3-minute end-to-end evaluation cost; see
    `test_official_entrypoint_subprocess_accepts_200_ticks_and_evaluates`
    below for the real, unmocked subprocess proof."""
    captured: dict[str, object] = {}

    def _fake_main(argv: list[str]) -> int:
        captured["argv"] = argv
        return 0

    import l2_2_design_a_runner

    monkeypatch.setattr(l2_2_design_a_runner, "main", _fake_main)
    given_argv = [
        "--process", "ReplicationInitiation", "--ticks", "200",
        "--seeds", "1", "--output-dir", "/tmp/unused",
    ]
    exit_code = entrypoint.main(given_argv)
    assert exit_code == 0
    assert captured["argv"] == given_argv


# --- Real subprocess: the exact official invocation shape sweep.py uses ---


def test_official_entrypoint_subprocess_rejects_100_ticks_before_evaluation(tmp_path: Path) -> None:
    """Invokes the ACTUAL entrypoint script as a subprocess -- the exact
    shape `sweep.runner_command` launches for ReplicationInitiation jobs
    -- with `--ticks 100` (every other process's catalog M_ticks). Must
    fail fast (well under the time any real oracle load/evaluation would
    take) with exit code 2 and never print a verdict line."""
    result = subprocess.run(
        [
            sys.executable,
            str(_ENTRYPOINT_SCRIPT),
            "--process", "ReplicationInitiation",
            "--seeds", "1",
            "--ticks", "100",
            "--output-dir", str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "does not equal" in result.stderr
    assert "PASS" not in result.stdout and "FAIL" not in result.stdout


@pytest.mark.slow
def test_official_entrypoint_subprocess_accepts_200_ticks_and_evaluates(tmp_path: Path) -> None:
    """Invokes the ACTUAL entrypoint script as a subprocess with the
    correct catalog M_ticks=200 and a single seed (keeps the real,
    unmocked end-to-end cost to a few minutes rather than the full N=50
    sweep). Must NOT be rejected by the M-validation guard, and must
    reach a real mechanical verdict."""
    _skip_if_raw_data_absent()
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            str(_ENTRYPOINT_SCRIPT),
            "--process", "ReplicationInitiation",
            "--seeds", "1",
            "--ticks", "200",
            "--output-dir", str(out_dir),
            "--bootstrap-B", "20",
        ],
        capture_output=True,
        text=True,
        timeout=580,
    )
    assert "does not equal" not in result.stderr, (
        f"M-validation guard incorrectly rejected a genuine --ticks 200 request: {result.stderr}"
    )
    assert result.returncode in (0, 1), f"unexpected exit code {result.returncode}: {result.stderr}"
    assert "ReplicationInitiation" in result.stdout
    assert (out_dir / "result.json").is_file()
