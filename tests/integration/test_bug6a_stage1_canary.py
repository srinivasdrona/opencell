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
from opencell.vivarium.karr_metabolism import _KARR_DEMAND_KEYS


def _run_chassis_v6_120_ticks() -> dict[str, object]:
    random.seed(0)
    np.random.seed(0)
    engine = Engine(
        composite=build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0),
        emit_step=1.0,
        display_info=False,
    )

    initial_substrates = dict(engine.state.get_value()["substrates"])
    writeback_total_positive: list[float] = []
    writeback_keys_seen: set[str] = set()

    try:
        for _tick in range(120):
            engine.update(1.0)
            state = engine.state.get_value()
            diag = state["m1_dynamic_diagnostics"]
            writeback_total_positive.append(float(diag["bug6a_writeback_total_positive"]))
            writeback_keys_seen.update(diag["bug6a_writeback_keys"])
    except Exception as exc:  # pragma: no cover - failure path asserts runtime health
        pytest.fail(f"120-tick chassis_v6 canary raised unexpectedly: {exc!r}")

    final_state = engine.state.get_value()
    final_substrates = dict(final_state["substrates"])
    demand_cumulative_delta = {
        sid: float(final_substrates[sid] - initial_substrates[sid]) for sid in _KARR_DEMAND_KEYS
    }
    totals = np.asarray(writeback_total_positive, dtype=np.float64)
    return {
        "totals": totals,
        "cumulative": np.cumsum(totals),
        "demand_delta": demand_cumulative_delta,
        "final_substrates": final_substrates,
        "keys_seen": writeback_keys_seen,
    }


def test_bug6a_stage1_chassis_v6_canary_120_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCELL_ENABLE_LP_WRITEBACK", "1")
    enabled = _run_chassis_v6_120_ticks()

    totals_on = enabled["totals"]
    cumulative_on = enabled["cumulative"]
    demand_delta_on = enabled["demand_delta"]
    final_sub_on = enabled["final_substrates"]
    keys_seen_on = enabled["keys_seen"]

    assert np.all(np.isfinite(totals_on))
    assert np.all(totals_on >= -1e-12)
    assert np.any(totals_on > 0.0)
    assert np.all(np.diff(cumulative_on) >= -1e-12)
    assert keys_seen_on
    assert all(key in _KARR_DEMAND_KEYS for key in keys_seen_on)

    monkeypatch.setenv("OPENCELL_ENABLE_LP_WRITEBACK", "0")
    disabled = _run_chassis_v6_120_ticks()

    totals_off = disabled["totals"]
    demand_delta_off = disabled["demand_delta"]
    final_sub_off = disabled["final_substrates"]
    keys_seen_off = disabled["keys_seen"]

    assert np.all(np.isfinite(totals_off))
    assert np.allclose(totals_off, 0.0, atol=1e-12)
    assert not keys_seen_off
    assert float(np.sum(totals_on)) > float(np.sum(totals_off))
    # Shared substrate drift may be equal to float precision at the
    # native chassis scales; verify expected direction non-strictly.
    assert final_sub_on["ATP"] >= final_sub_off["ATP"] - 1e-9
    assert sum(demand_delta_on.values()) >= sum(demand_delta_off.values()) - 1e-9
