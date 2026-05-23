from __future__ import annotations

import warnings
from pathlib import Path
import sys

import numpy as np
import pytest
from vivarium.core.engine import Engine

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

from opencell.vivarium.karr_composite import (
    CHASSIS_V6_EXPECTED_PROCESS_KEYS,
    build_karr_chassis_v6,
)


def _build_engine() -> Engine:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    return Engine(composite=composite, emit_step=1.0, display_info=False)


def _sum_count_timeseries(counts_ts: dict[str, list[float]]) -> np.ndarray:
    n = len(next(iter(counts_ts.values())))
    totals = np.zeros(n, dtype=np.float64)
    for series in counts_ts.values():
        totals += np.asarray(series, dtype=np.float64)
    return totals


def test_v6_builds() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    proc_keys = set(composite["processes"].keys())
    assert proc_keys >= set(CHASSIS_V6_EXPECTED_PROCESS_KEYS)


def test_v6_one_tick() -> None:
    engine = _build_engine()
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        engine.update(1.0)
    state = engine.state.get_value()
    assert "chromosome" in state
    assert "rna" in state
    assert "protein" in state


@pytest.mark.slow
def test_v6_short_run_100s() -> None:
    engine = _build_engine()
    engine.update(100.0)
    ts = engine.emitter.get_timeseries()

    protein_total = _sum_count_timeseries(ts["protein"]["counts"])
    rna_total = _sum_count_timeseries(ts["rna"]["counts"])
    complex_total = _sum_count_timeseries(ts["complex"]["counts"])
    dry_mass_proxy = protein_total + rna_total + complex_total

    assert dry_mass_proxy[-1] > dry_mass_proxy[0] * 0.99
