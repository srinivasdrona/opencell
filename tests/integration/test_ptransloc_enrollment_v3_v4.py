"""Integration checks for ProteinTranslocation allocator enrollment in v3/v4."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

from opencell.vivarium.karr_composite import build_karr_chassis_v3, build_karr_chassis_v4
from opencell.vivarium.karr_request_calculators import RequestCalculatorPTransloc


def _assert_ptrans_consumer_enrolled(engine: Any) -> None:
    consumers = dict(engine.steps["karr_allocation_step"].parameters["consumer_processes"])
    p_trans_proc = engine.processes["karr_protein_translocation"]
    assert p_trans_proc.name in consumers
    assert consumers[p_trans_proc.name] == list(p_trans_proc.allocation_substrate_wids)


def test_ptransloc_in_consumer_processes_v3() -> None:
    engine = build_karr_chassis_v3(time_step_s=1.0, emit_step_s=1.0)
    _assert_ptrans_consumer_enrolled(engine)


def test_ptransloc_in_consumer_processes_v4() -> None:
    engine = build_karr_chassis_v4(time_step_s=1.0, emit_step_s=1.0)
    _assert_ptrans_consumer_enrolled(engine)


def test_ptransloc_request_calculator_wired_v3() -> None:
    engine = build_karr_chassis_v3(time_step_s=1.0, emit_step_s=1.0)
    step = engine.steps["request_calculator_protein_translocation"]
    assert isinstance(step, RequestCalculatorPTransloc)


def test_ptransloc_request_calculator_wired_v4() -> None:
    engine = build_karr_chassis_v4(time_step_s=1.0, emit_step_s=1.0)
    step = engine.steps["request_calculator_protein_translocation"]
    assert isinstance(step, RequestCalculatorPTransloc)

