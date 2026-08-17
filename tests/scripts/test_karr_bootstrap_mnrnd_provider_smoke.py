"""Real local MATLAB smoke for the genuine-mnrnd provider migration.

This is intentionally a real MATLAB test, not a synthetic fixture or
source-inspection test. It proves the exact operator-reported scenario:

1. `restoredefaultpath; addpath('scripts/matlab')` initially resolves
   `mnrnd` to the repo shim.
2. `karr_bootstrap()` re-promotes and verifies the genuine Statistics
   Toolbox provider.
3. After bootstrap, `which mnrnd` stays on the MathWorks toolbox path and
   the returned provider metadata matches the current local install.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import launcher  # noqa: E402

if os.name == "nt":
    MATLAB_ROOT = Path(r"E:\MATLAB")
    MATLAB_EXE = MATLAB_ROOT / "bin" / "matlab.exe"
    MATLAB_REPO_ROOT = REPO_ROOT.as_posix()
    EXPECTED_PROVIDER_PATH = MATLAB_ROOT / launcher.GENUINE_MNRND_RELATIVE_PATH
else:
    MATLAB_ROOT = Path("/mnt/e/MATLAB")
    MATLAB_EXE = MATLAB_ROOT / "bin" / "matlab.exe"
    relative_repo = REPO_ROOT.relative_to("/mnt/e")
    MATLAB_REPO_ROOT = f"E:/{relative_repo.as_posix()}"
    EXPECTED_PROVIDER_PATH = Path(r"E:\MATLAB") / launcher.GENUINE_MNRND_RELATIVE_PATH

pytestmark = pytest.mark.skipif(not MATLAB_EXE.exists(), reason="Real MATLAB not present locally")


def _extract_json(stdout: str) -> dict[str, str]:
    match = re.search(r"JSON_RESULT=(\{.*\})", stdout)
    assert match is not None, f"expected JSON_RESULT marker in MATLAB stdout, got:\n{stdout}"
    return json.loads(match.group(1))


def test_karr_bootstrap_rebinds_real_mnrnd_after_repo_paths():
    expected_provider = launcher.current_genuine_mnrnd_provider(matlab_root=MATLAB_ROOT)
    batch = (
        f"restoredefaultpath; cd('{MATLAB_REPO_ROOT}'); addpath('scripts/matlab'); "
        "result = struct(); "
        "result.before = which('mnrnd'); "
        "[~, provider] = karr_bootstrap(); "
        "result.after = which('mnrnd'); "
        "result.after_binornd = which('binornd'); "
        "result.after_poissrnd = which('poissrnd'); "
        "result.after_random = which('random'); "
        "result.after_randsample = which('randsample'); "
        "result.kind = provider.kind; "
        "result.matlab_release = provider.matlab_release; "
        "result.toolbox_version = provider.toolbox_version; "
        "result.provider_path_relative_to_matlabroot = provider.provider_path_relative_to_matlabroot; "
        "result.sha256_lf_normalized = provider.sha256_lf_normalized; "
        "disp(['JSON_RESULT=' jsonencode(result)]);"
    )
    result = subprocess.run(
        [str(MATLAB_EXE), "-batch", batch],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    payload = _extract_json(result.stdout)
    before_path = payload["before"].replace("/", "\\")
    after_path = payload["after"].replace("/", "\\")
    expected_after = str(EXPECTED_PROVIDER_PATH).replace("/", "\\")

    assert before_path.endswith(r"scripts\matlab\mnrnd.m"), before_path
    assert after_path == expected_after
    assert after_path != before_path
    assert payload["kind"] == expected_provider["kind"]
    assert payload["matlab_release"] == expected_provider["matlab_release"]
    assert payload["toolbox_version"] == expected_provider["toolbox_version"]
    assert (
        payload["provider_path_relative_to_matlabroot"]
        == expected_provider["provider_path_relative_to_matlabroot"]
    )
    assert payload["sha256_lf_normalized"] == expected_provider["sha256_lf_normalized"]
    for name in ("binornd", "poissrnd", "random", "randsample"):
        expected_path = str(Path(r"E:\MATLAB") / launcher.STATISTICS_TOOLBOX_FUNCTIONS_RELATIVE_DIR / f"{name}.m")
        assert payload[f"after_{name}"].replace("/", "\\") == expected_path.replace("/", "\\")


def test_karr_bootstrap_fails_if_caller_cwd_contains_repo_shim():
    scripts_dir = f"{MATLAB_REPO_ROOT}/scripts/matlab"
    batch = (
        f"restoredefaultpath; cd('{scripts_dir}'); addpath('{scripts_dir}'); "
        "karr_bootstrap();"
    )
    result = subprocess.run(
        [str(MATLAB_EXE), "-batch", batch],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0, combined
    assert "Current-folder and repo shims are prohibited as Karr evidence" in combined
