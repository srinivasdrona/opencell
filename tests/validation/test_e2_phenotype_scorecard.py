from __future__ import annotations

import sys
from pathlib import Path
from typing import get_args

import numpy as np
import pytest

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.validation.phenotype_registry import Bucket, PHENOTYPES
from opencell.validation.phenotype_scorecard import (
    E2_SCORECARD_PATH,
    load_v6_trajectory_fixture,
    run_from_fixture,
    score,
)


@pytest.fixture(scope="session")
def chassis_v6_trajectory() -> dict:
    return load_v6_trajectory_fixture()


def test_e2_all_kps_registered() -> None:
    """All 28 IDs KP01..KP28 present in PHENOTYPES."""
    assert sorted(PHENOTYPES.keys()) == [f"KP{i:02d}" for i in range(1, 29)]
    for kp in PHENOTYPES.values():
        assert kp.bucket in get_args(Bucket)
        assert kp.extractor is not None


@pytest.mark.slow
def test_e2_extractors_run(chassis_v6_trajectory: dict) -> None:
    """Each extractor returns a float/bool/None and does not raise."""
    for kp in PHENOTYPES.values():
        result = kp.extractor(chassis_v6_trajectory)
        assert result is None or isinstance(result, (int, float, bool, np.floating, np.integer))


@pytest.mark.slow
def test_e2_scorecard_pass_count(chassis_v6_trajectory: dict) -> None:
    """Pre-fix baseline acceptance: at least 6 of 28 PASS."""
    scorecard = score(chassis_v6_trajectory)
    pass_count = sum(1 for row in scorecard if row.status == "PASS")
    assert pass_count >= 6, f"Only {pass_count}/28 PASS"


@pytest.mark.slow
def test_e2_no_unhandled_blocked(chassis_v6_trajectory: dict) -> None:
    """Every BLOCKED has a documented v1.1 TODO id."""
    scorecard = score(chassis_v6_trajectory)
    blocked = [row for row in scorecard if row.status == "BLOCKED"]
    for row in blocked:
        assert row.disposition_todo_id is not None, f"{row.kp_id} blocked without TODO id"


@pytest.mark.slow
def test_e2_report_emitted() -> None:
    """docs/phase_e/E2_scorecard.md exists with all 28 rows."""
    path = Path(E2_SCORECARD_PATH)
    if not path.exists():
        run_from_fixture(out_path=path)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    for i in range(1, 29):
        assert f"KP{i:02d}" in content
