from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
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

from opencell.m1 import calc_flux_bounds as cfb
from opencell.m1 import karr_metabolism as km
from opencell.vivarium.karr_metabolism import KarrMetabolismProcess


PARAMS_FIXTURE = Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "parameters.json"


def _build_dynamic_proc(*, karr_parity_mode: bool) -> KarrMetabolismProcess:
    return KarrMetabolismProcess(
        {
            "model": km.load_default(),
            "dynamic_bounds": True,
            "use_allocator_budget": False,
            "karr_parity_mode": karr_parity_mode,
        }
    )


def test_dynamic_process_loads_ngam_from_parameters_fixture() -> None:
    proc = _build_dynamic_proc(karr_parity_mode=False)
    params = json.loads(PARAMS_FIXTURE.read_text())
    expected = float(params["processes"]["Metabolism"]["nonGrowthAssociatedMaintenance"])
    assert proc._ngam_mmol_per_gdw_h == pytest.approx(expected, rel=0.0, abs=0.0)


@pytest.mark.parametrize("karr_parity_mode", [False, True])
def test_dynamic_update_gates_atpm_floor_on_karr_parity_mode(
    monkeypatch: pytest.MonkeyPatch,
    karr_parity_mode: bool,
) -> None:
    proc = _build_dynamic_proc(karr_parity_mode=karr_parity_mode)
    assert proc._atpm_fba_col is not None

    captured: dict[str, np.ndarray] = {}
    forced_bounds = np.column_stack(
        [
            np.zeros(proc.model.n_reactions, dtype=float),
            np.full(proc.model.n_reactions, np.inf, dtype=float),
        ]
    )
    forced_bounds[int(proc._atpm_fba_col), 1] = 1e12

    def _fake_compute_bounds(
        substrates: np.ndarray,
        enzymes: np.ndarray,
        cell_dry_mass: float,
        step_size_sec: float,
        catalysis: np.ndarray,
        enz_bounds: np.ndarray,
        fba_reaction_bounds: np.ndarray,
        dyn: cfb.M1DynamicsInputs,
        apply_protein_bounds: bool = False,
    ) -> np.ndarray:
        del (
            substrates,
            enzymes,
            cell_dry_mass,
            step_size_sec,
            catalysis,
            enz_bounds,
            fba_reaction_bounds,
            dyn,
            apply_protein_bounds,
        )
        return forced_bounds.copy()

    def _fake_solve_fba(
        model: km.KarrMetabolismModel,
        objective_col: int | None = None,
        sense: str = "max",
        big: float = km.DEFAULT_BIG,
        use_full_objective: bool = True,
        lb_override: np.ndarray | None = None,
        ub_override: np.ndarray | None = None,
    ) -> tuple[np.ndarray, dict]:
        del objective_col, sense, use_full_objective
        assert lb_override is not None
        assert ub_override is not None
        captured["lb"] = np.asarray(lb_override, dtype=float).copy()
        captured["ub"] = np.asarray(ub_override, dtype=float).copy()
        zero_v = np.zeros(model.n_reactions, dtype=float)
        return zero_v, {
            "status": "ok",
            "message": "test fake solve",
            "objective_value": 0.0,
            "biomass_flux_per_s": 0.0,
            "biomass_flux_per_h": 0.0,
            "big": float(big),
            "use_full_objective": True,
            "n_nonzero": 0,
        }

    monkeypatch.setattr(cfb, "compute_bounds", _fake_compute_bounds)
    monkeypatch.setattr(km, "solve_fba", _fake_solve_fba)

    shared_substrates = {sid: 1.0 for sid in proc._sub_ids}
    proc.next_update(1.0, {"substrates": shared_substrates})

    assert "lb" in captured and "ub" in captured
    col = int(proc._atpm_fba_col)
    lb_val = float(captured["lb"][col])
    ub_val = float(captured["ub"][col])
    floor = float(proc._atpm_lb_floor_for_tick(1.0))

    assert lb_val <= ub_val + 1e-9
    if karr_parity_mode:
        assert lb_val == pytest.approx(0.0, rel=0.0, abs=1e-12)
        assert lb_val < floor
    else:
        assert lb_val >= min(floor, ub_val) - 1e-9
