"""Integration checks for allocator enrollment in v3/v4 direct-writer paths."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

from opencell.vivarium.karr_composite import build_karr_chassis_v3, build_karr_chassis_v4


def _resolve_step_states(engine: Any, step_key: str) -> dict[str, Any]:
    state = engine.state.get_value()
    topology = engine.topology[step_key]
    resolved: dict[str, Any] = {}
    for port, path in topology.items():
        node: Any = state
        for segment in path:
            if not isinstance(node, dict):
                node = {}
                break
            node = node.get(segment, {})
        resolved[port] = node
    return resolved


@pytest.mark.parametrize(
    ("builder", "tx_key", "tl_key"),
    [
        (build_karr_chassis_v3, "karr_transcription_v3", "karr_translation_v3"),
        (build_karr_chassis_v4, "karr_transcription_v3", "karr_translation_v3"),
    ],
    ids=["v3", "v4"],
)
def test_v3_v4_tx_tl_are_enrolled_and_emit_requests(
    builder: Any,
    tx_key: str,
    tl_key: str,
) -> None:
    engine = builder(time_step_s=1.0, emit_step_s=1.0)
    consumers = dict(engine.steps["karr_allocation_step"].parameters["consumer_processes"])

    tx_proc = engine.processes[tx_key]
    tl_proc = engine.processes[tl_key]
    assert consumers[tx_proc.name] == list(tx_proc.allocation_substrate_wids)
    assert consumers[tl_proc.name] == list(tl_proc.allocation_substrate_wids)

    tx_step_state = _resolve_step_states(engine, "request_calculator_transcription")
    tx_requests = engine.steps["request_calculator_transcription"].next_update(1.0, tx_step_state)[
        "requests"
    ][tx_proc.name]
    assert any(float(v) > 0.0 for v in tx_requests.values())

    tl_step_state = _resolve_step_states(engine, "request_calculator_translation")
    tl_requests = engine.steps["request_calculator_translation"].next_update(1.0, tl_step_state)[
        "requests"
    ][tl_proc.name]
    assert any(float(v) > 0.0 for v in tl_requests.values())


def test_v4_dynamic_bounds_enrolls_metabolism() -> None:
    engine = build_karr_chassis_v4(time_step_s=1.0, emit_step_s=1.0, dynamic_bounds=True)
    consumers = dict(engine.steps["karr_allocation_step"].parameters["consumer_processes"])
    m1_proc = engine.processes["karr_metabolism"]

    assert m1_proc.name in consumers
    assert consumers[m1_proc.name] == list(m1_proc.allocation_substrate_wids)
    assert len(consumers[m1_proc.name]) > 0
