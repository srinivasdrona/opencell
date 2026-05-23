from __future__ import annotations

import pickle
import sys
from pathlib import Path

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

from opencell.validation.karr_trajectory import load_karr_trajectory
from opencell.validation.trajectory_compare import (
    SCAFFOLD_OBSERVABLES,
    compare_full_trajectory,
)

V6_FIXTURE_PATH = Path("data/phase_e/v6_trajectory_32400s.pkl")
EXPECTED_OBSERVABLES = tuple(SCAFFOLD_OBSERVABLES)


def _load_v6_fixture() -> dict:
    with V6_FIXTURE_PATH.open("rb") as f:
        return pickle.load(f)


@pytest.mark.slow
def test_e1_real_match_fixture_exists() -> None:
    """The v6 trajectory pickle was produced and loadable."""
    assert V6_FIXTURE_PATH.exists()
    d = _load_v6_fixture()
    assert d["chassis"] == "v6"
    assert d["schema_version"] == 1
    assert d["ticks_completed"] >= 30000


def test_e1_comparator_runs() -> None:
    """Comparator processes the fixture without crashing on any observable."""
    v6 = _load_v6_fixture()
    karr = load_karr_trajectory()
    result = compare_full_trajectory(v6, karr)
    for obs in EXPECTED_OBSERVABLES:
        assert obs in result
        assert result[obs]["status"] in {"PASS", "FAIL", "MISSING_KARR", "MISSING_OPENCELL"}


def test_e1_at_least_one_observable_passes() -> None:
    """Sanity floor: framework is wired correctly (NOT a fidelity claim)."""
    v6 = _load_v6_fixture()
    karr = load_karr_trajectory()
    result = compare_full_trajectory(v6, karr)
    passing = [obs for obs, metrics in result.items() if metrics["status"] == "PASS"]
    assert len(passing) >= 1, f"No observable passed; framework likely broken. Detail: {result}"
