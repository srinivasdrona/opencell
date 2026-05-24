from __future__ import annotations

from pathlib import Path
import random
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

from opencell.vivarium.karr_composite import build_karr_chassis_v6


def test_bug6b_chassis_v6_canary_120_ticks_non_negative_pools() -> None:
    random.seed(0)
    np.random.seed(0)
    engine = Engine(
        composite=build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0),
        emit_step=1.0,
        display_info=False,
    )

    min_ctp_60 = np.inf
    min_utp_60 = np.inf
    min_atp_120 = np.inf
    min_gtp_120 = np.inf

    try:
        for tick in range(1, 121):
            engine.update(1.0)
            pools = engine.state.get_value()["m1_pools"]
            ctp = float(pools["CTP"])
            utp = float(pools["UTP"])
            atp = float(pools["ATP"])
            gtp = float(pools["GTP"])
            min_atp_120 = min(min_atp_120, atp)
            min_gtp_120 = min(min_gtp_120, gtp)
            if tick <= 60:
                min_ctp_60 = min(min_ctp_60, ctp)
                min_utp_60 = min(min_utp_60, utp)
    except Exception as exc:  # pragma: no cover - failure path asserts runtime health
        pytest.fail(f"120-tick chassis_v6 canary raised unexpectedly: {exc!r}")

    assert min_ctp_60 >= 0.0
    assert min_utp_60 >= 0.0
    assert min_atp_120 >= 0.0
    assert min_gtp_120 >= 0.0

    ts = engine.emitter.get_timeseries()
    assert "m1_dynamic_diagnostics" in ts
    diag = ts["m1_dynamic_diagnostics"]
    assert "bug6b_clamped_reactions" in diag
    clamp_series = np.asarray(diag["bug6b_clamped_reactions"], dtype=np.float64)
    assert clamp_series.size > 0
    assert np.all(np.isfinite(clamp_series))

