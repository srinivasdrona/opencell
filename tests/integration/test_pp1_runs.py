from __future__ import annotations

from pathlib import Path
import random
import sys

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

TIME_STEP_S = 1.0
RNG_SEED = 0
N_TICKS = 5


def _build_engine() -> Engine:
    random.seed(RNG_SEED)
    np.random.seed(RNG_SEED)
    composite = build_karr_chassis_v6(time_step_s=TIME_STEP_S, emit_step_s=TIME_STEP_S)
    return Engine(composite=composite, emit_step=TIME_STEP_S, display_info=False)


def test_pp1_writes_nonempty_delta_within_first_five_ticks() -> None:
    engine = _build_engine()
    pp1 = engine.processes["karr_protein_processing_i"]

    enzyme_counts = engine.state.get_value()["protein"]["enzyme_counts"]
    assert float(enzyme_counts.get("MG_106_DIMER", 0.0)) > 0.0
    assert float(enzyme_counts.get("MG_172_MONOMER", 0.0)) > 0.0

    # Seed one precursor so PP1 has integer substrate available within a short run.
    source_wid = pp1.unprocessed_monomer_wids[0]
    engine.state.set_path(("protein", "unprocessed_counts", source_wid), 100.0)

    fired = False
    for _ in range(N_TICKS):
        before_state = engine.state.get_value()
        before_processed_total = float(
            sum(
                float(before_state["protein"]["processed_counts"].get(wid, 0.0))
                for wid in pp1.processed_monomer_wids
            )
        )

        engine.update(TIME_STEP_S)

        after_state = engine.state.get_value()
        after_processed_total = float(
            sum(
                float(after_state["protein"]["processed_counts"].get(wid, 0.0))
                for wid in pp1.processed_monomer_wids
            )
        )
        if after_processed_total > before_processed_total:
            fired = True
            break

    assert fired, (
        "PP1 failed integration guard: no positive delta observed in "
        "`protein.processed_counts` within first five ticks."
    )
