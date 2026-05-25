from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
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

CORE_SUBSTRATES: tuple[str, ...] = ("AD", "URA", "ATP", "GTP", "H2O")
SIM_DURATION_S = 5_000.0
TIME_STEP_S = 1.0


def test_b1_substrate_sanity() -> None:
    composite = build_karr_chassis_v6(time_step_s=TIME_STEP_S, emit_step_s=TIME_STEP_S)
    engine = Engine(composite=composite, emit_step=TIME_STEP_S, display_info=False)
    engine.update(SIM_DURATION_S)

    final_substrates = engine.state.get_value()["substrates"]
    core_values = {sid: float(final_substrates.get(sid, np.nan)) for sid in CORE_SUBSTRATES}
    negative_core = {sid: value for sid, value in core_values.items() if value < 0.0}
    negative_any = {
        sid: float(value)
        for sid, value in final_substrates.items()
        if float(value) < 0.0
    }

    assert not negative_core, f"core substrate(s) dropped below zero: {negative_core}"
    assert not negative_any, f"substrate(s) dropped below zero: {negative_any}"

