from __future__ import annotations

import json
import sys
from pathlib import Path

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

from vivarium.core import process as vivarium_process_module

if not hasattr(vivarium_process_module, "Step"):
    class Step(vivarium_process_module.Process):
        pass

    vivarium_process_module.Step = Step

from opencell.m1 import karr_metabolism as km
from opencell.m1.compartmented import AVOGADRO, SECONDS_PER_HOUR
from opencell.vivarium.karr_metabolism import KarrMetabolismProcess
from opencell.vivarium.karr_request_calculators import RequestCalculatorMetabolism

PARAMS_FIXTURE = Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "parameters.json"


def _build_calc(*, karr_parity_mode: bool, atp_demand: float = 0.0) -> RequestCalculatorMetabolism:
    proc = KarrMetabolismProcess(
        {
            "model": km.load_default(),
            "dynamic_bounds": True,
            "use_allocator_budget": True,
            "karr_parity_mode": karr_parity_mode,
        }
    )
    proc._last_allocation_demand = {wid: 0.0 for wid in proc.allocation_substrate_wids}
    if "ATP" in proc._last_allocation_demand:
        proc._last_allocation_demand["ATP"] = float(atp_demand)
    return RequestCalculatorMetabolism(
        {
            "metabolism_proc": proc,
            "karr_parity_mode": karr_parity_mode,
        }
    )


def _expected_floor_for_tick(calc: RequestCalculatorMetabolism, tick_s: float) -> float:
    params = json.loads(PARAMS_FIXTURE.read_text())
    ngam = float(params["processes"]["Metabolism"]["nonGrowthAssociatedMaintenance"])
    gam = float(params["processes"]["Metabolism"]["growthAssociatedMaintenance"])
    cell_dry_mass_g = float(calc._m1_proc.model.stored_runtime["cell_dry_total_mass_g"])
    growth_per_s = float(calc._m1_proc.model.stored_runtime["meanInitialGrowthRate_per_s"])

    mmol_per_tick = ngam * cell_dry_mass_g * tick_s / SECONDS_PER_HOUR
    mmol_per_tick += gam * growth_per_s * cell_dry_mass_g * tick_s
    return mmol_per_tick * 1e-3 * AVOGADRO


@pytest.mark.parametrize("karr_parity_mode", [False, True])
def test_request_calculator_metabolism_karr_parity_mode_gates_ngam_floor(
    karr_parity_mode: bool,
) -> None:
    stoich_demand = 5.0
    calc = _build_calc(karr_parity_mode=karr_parity_mode, atp_demand=stoich_demand)

    update = calc.next_update(1.0, {})
    atp_request = float(update["requests"][calc._m1_proc.name]["ATP"])
    expected_floor = _expected_floor_for_tick(calc, 1.0)

    if karr_parity_mode:
        assert atp_request == pytest.approx(stoich_demand, rel=1e-12, abs=1e-9)
        assert atp_request < expected_floor
    else:
        assert atp_request > 0.0
        assert atp_request >= expected_floor - 1e-9
        assert atp_request >= stoich_demand


@pytest.mark.parametrize("karr_parity_mode", [False, True])
def test_request_calculator_metabolism_scales_with_tick(karr_parity_mode: bool) -> None:
    calc = _build_calc(karr_parity_mode=karr_parity_mode)

    req_1s = float(calc.next_update(1.0, {})["requests"][calc._m1_proc.name]["ATP"])
    req_5s = float(calc.next_update(5.0, {})["requests"][calc._m1_proc.name]["ATP"])

    if karr_parity_mode:
        assert req_1s == pytest.approx(0.0, rel=1e-12, abs=1e-9)
        assert req_5s == pytest.approx(0.0, rel=1e-12, abs=1e-9)
    else:
        assert req_1s > 0.0
        assert req_5s == pytest.approx(req_1s * 5.0, rel=1e-12, abs=1e-9)


@pytest.mark.parametrize("karr_parity_mode", [False, True])
def test_request_calculator_metabolism_uses_process_time_step_when_step_dt_zero(
    karr_parity_mode: bool,
) -> None:
    calc = _build_calc(karr_parity_mode=karr_parity_mode)

    req_0s = float(calc.next_update(0.0, {})["requests"][calc._m1_proc.name]["ATP"])
    req_1s = float(calc.next_update(1.0, {})["requests"][calc._m1_proc.name]["ATP"])

    assert req_0s == pytest.approx(req_1s, rel=1e-12, abs=1e-9)
    if karr_parity_mode:
        assert req_1s == pytest.approx(0.0, rel=1e-12, abs=1e-9)
