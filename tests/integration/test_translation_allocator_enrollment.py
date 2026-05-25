from __future__ import annotations

import sys
from pathlib import Path

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


def test_translation_enrolled_in_allocator_and_10_tick_nonnegative() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)

    allocation_step = composite["steps"]["karr_allocation_step"]
    consumers = dict(allocation_step.parameters["consumer_processes"])
    tl_proc = composite["processes"]["karr_translation"]

    assert "karr_translation" in consumers
    assert consumers["karr_translation"] == list(tl_proc.allocation_substrate_wids)
    assert len(consumers["karr_translation"]) == 20

    tl_topology = composite["topology"]["karr_translation"]
    assert tl_topology.get("substrates_allocated") == ("substrates_allocated",)

    engine = Engine(composite=composite, emit_step=1.0, display_info=False)
    engine.update(10.0)
    final_substrates = engine.state.get_value()["substrates"]

    negative = {wid: float(val) for wid, val in final_substrates.items() if float(val) < -1e-9}
    assert not negative, f"negative substrates after 10 ticks: {negative}"

