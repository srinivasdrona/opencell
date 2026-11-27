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


def test_ptransloc_request_calculator_declares_complex_port() -> None:
    """D4 requirement: RequestCalculatorPTransloc must declare a 'complex' port

    so that complex enzymes (MG_0001_048, MG_072_DIMER, MG_055_170_277_464_476_20MER)
    can be read to calculate capacity.
    """
    from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess

    pt_proc = KarrProteinTranslocationProcess({})
    calc = RequestCalculatorPTransloc({"protein_translocation_proc": pt_proc})
    schema = calc.ports_schema()
    assert "complex" in schema, "RequestCalculatorPTransloc must declare 'complex' port"
    assert "counts" in schema["complex"], "RequestCalculatorPTransloc must declare 'counts' under 'complex' port"


def test_ptransloc_request_calculator_complex_wired_in_chassis_v3_and_v4() -> None:
    """D4 requirement: Composite topology must wire request_calculator_protein_translocation's

    'complex' port to ('complex',).
    """
    for builder, label in [
        (build_karr_chassis_v3, "v3"),
        (build_karr_chassis_v4, "v4"),
    ]:
        engine = builder(time_step_s=1.0, emit_step_s=1.0)
        # Check topology in composite
        composite = getattr(engine, "composite", engine)
        topology = composite.topology if hasattr(composite, "topology") else engine.topology
        step_topo = topology.get("request_calculator_protein_translocation", {})
        assert "complex" in step_topo, (
            f"request_calculator_protein_translocation in {label} must wire 'complex' port"
        )
        assert tuple(step_topo["complex"]) == ("complex",), (
            f"request_calculator_protein_translocation in {label} must wire 'complex' to ('complex',)"
        )
