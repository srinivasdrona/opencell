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
            if mod_name == "opencell" or mod_name.startswith("opencell.") or mod_name.startswith("scripts."):
                del sys.modules[mod_name]

from opencell.m1 import karr_metabolism as km
from opencell.m2 import transcription as tx
from opencell.m3 import translation as tl
from opencell.vivarium.karr_composite import build_karr_chassis_v6
from scripts.run_chassis_v6_32400t import DiagnosticCollector


def test_trna_aminoacylation_trace_nonempty_after_100_ticks(tmp_path: Path) -> None:
    m1_model = km.load_default()
    m2_model = tx.load_default()
    m3_model = tl.load_default()

    probe = build_karr_chassis_v6(m1_model=m1_model, m2_model=m2_model, m3_model=m3_model)
    timestep_s = float(
        getattr(probe.processes.get("karr_metabolism"), "parameters", {}).get("time_step", 1.0)
    )

    ticks = 100
    composite = build_karr_chassis_v6(
        m1_model=m1_model,
        m2_model=m2_model,
        m3_model=m3_model,
        time_step_s=timestep_s,
        emit_step_s=float(ticks),
    )
    diagnostics = DiagnosticCollector(
        composite=composite,
        process_traces_dir=tmp_path / "process_traces",
        process_trace_stride=10,
        seed=42,
    )
    engine = Engine(composite=composite, emit_step=float(ticks), display_info=False)

    for tick in range(1, ticks + 1):
        diagnostics.set_tick(tick)
        engine.update(timestep_s)
    diagnostics.close()

    trace_path = tmp_path / "process_traces" / "karr_trna_aminoacylation.csv"
    assert trace_path.exists()
    assert trace_path.stat().st_size > 35
