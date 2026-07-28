"""Regression tests for bin\\oc-py.cmd and bin\\oc-pytest.cmd exit-code propagation.

Root cause under test: both wrappers previously ended with a bare `endlocal`
as their last statement. When a batch file's *last executed command* is
`endlocal` (or any command that itself always succeeds), cmd.exe reports
*that* command's own exit code to the parent process — not the value of
`%ERRORLEVEL%` at that point in the script. Since `endlocal` always
"succeeds", the wrapper always reported exit code 0 to PowerShell/cmd.exe,
even when the wrapped WSL command (python/pytest) exited nonzero. This meant
any gate or CI check that shells out through these wrappers could never
observe a real failure — a silent false-green.

The fix captures `%ERRORLEVEL%` into a variable immediately after the `wsl`
call, then does `endlocal & exit /b %_RC%` so the captured value (not
`endlocal`'s own status) becomes the batch file's real exit code.

These tests must actually invoke the compiled `.cmd` wrappers as real Windows
processes (via the WSL-to-Windows interop path, since this project's tests
run under the WSL venv per repo convention) and assert on the observed
process exit code — inspecting the wrapper's *text* is not sufficient to
catch this class of bug, since the bug is about batch-file control flow, not
about what commands appear in the file.
"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "wrapper_scripts"

# The WSL-to-Windows interop binary used to actually launch the .cmd wrapper
# as a real Windows process from within this WSL pytest run. This is the
# path oc-py.cmd/oc-pytest.cmd's own `wsl` call would use in reverse, and is
# always present on any WSL install with interop enabled (the default).
_CMD_EXE = "/mnt/c/Windows/System32/cmd.exe"


def _wsl_interop_available() -> bool:
    """Best-effort check that we're on WSL with Windows interop enabled.

    Returns False (triggering an explicit skip) only when genuinely
    unavailable, e.g. a plain-Linux CI runner with no Windows host to call
    back into. On the target dev machine for this fix, this is always True.
    """
    if platform.system() != "Linux":
        return False
    try:
        release = Path("/proc/version").read_text().lower()
    except OSError:
        return False
    if "microsoft" not in release:
        return False
    return Path(_CMD_EXE).exists()


pytestmark = pytest.mark.skipif(
    not _wsl_interop_available(),
    reason="requires running under WSL with Windows interop (cmd.exe) reachable",
)


def _run_wrapper(wrapper: str, args: list[str]) -> subprocess.CompletedProcess:
    """Invoke bin\\<wrapper> as a real Windows process and return its result.

    `wrapper` is forwarded to cmd.exe as a Windows-relative path
    (`bin\\oc-py.cmd`) so that the wrapper's own `%CD%`-based WSL path
    translation runs exactly as it would for a real caller.
    """
    win_relative = f"bin\\{wrapper}"
    return subprocess.run(
        [_CMD_EXE, "/c", win_relative, *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )


class TestOcPyExitCodes:
    def test_success_exit_zero(self) -> None:
        result = _run_wrapper(
            "oc-py.cmd", ["tests/fixtures/wrapper_scripts/echo_exit.py", "0"]
        )
        assert result.returncode == 0, result.stderr

    def test_explicit_nonzero_exit_propagates(self) -> None:
        result = _run_wrapper(
            "oc-py.cmd", ["tests/fixtures/wrapper_scripts/echo_exit.py", "7"]
        )
        assert result.returncode == 7, result.stderr

    def test_argument_forwarding_drives_observed_exit_code(self) -> None:
        # Same script, different forwarded argument -> different exit code.
        # This is the same code path as the exit-code tests above, but
        # asserted explicitly against a second, distinct value to confirm
        # that the exit code we observe really is a function of the
        # forwarded argument (and not e.g. a stuck/hardcoded value).
        result = _run_wrapper(
            "oc-py.cmd", ["tests/fixtures/wrapper_scripts/echo_exit.py", "3"]
        )
        assert result.returncode == 3, result.stderr

    def test_missing_script_is_nonzero(self) -> None:
        result = _run_wrapper("oc-py.cmd", ["tests/fixtures/wrapper_scripts/does_not_exist.py"])
        assert result.returncode != 0
        assert "No such file" in result.stdout or "No such file" in result.stderr


class TestOcPytestExitCodes:
    def test_success_exit_zero(self) -> None:
        result = _run_wrapper(
            "oc-pytest.cmd", ["tests/fixtures/wrapper_scripts/pass_case.py", "-q"]
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_test_failure_is_nonzero(self) -> None:
        result = _run_wrapper(
            "oc-pytest.cmd", ["tests/fixtures/wrapper_scripts/fail_case.py", "-q"]
        )
        # pytest exit code 1 == "tests were collected and ran but some failed".
        assert result.returncode == 1, result.stdout + result.stderr

    def test_collection_usage_error_is_nonzero(self) -> None:
        result = _run_wrapper(
            "oc-pytest.cmd", ["tests/fixtures/wrapper_scripts/does_not_exist.py", "-q"]
        )
        # pytest exit code 4 == "pytest command line usage error"
        # (e.g. requested file/path not found).
        assert result.returncode == 4, result.stdout + result.stderr


def test_wrappers_exist_and_are_the_fixed_version() -> None:
    """Guard against silent regression of the fix itself.

    Both wrappers must capture the WSL child's errorlevel into a variable
    before `endlocal`, and must exit the batch file with that captured value
    rather than falling off the end of the script (which reports
    `endlocal`'s own exit code, always 0).
    """
    for wrapper in ("oc-py.cmd", "oc-pytest.cmd"):
        text = (REPO_ROOT / "bin" / wrapper).read_text()
        assert "endlocal & exit /b" in text, (
            f"{wrapper} no longer preserves the WSL child's exit code through "
            "endlocal; see this file's module docstring for the bug this guards against."
        )
