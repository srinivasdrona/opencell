from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

from opencell.vivarium.karr_ftsz_polymerization import KarrFtsZPolymerizationProcess


def _base_state(
    process: KarrFtsZPolymerizationProcess,
    *,
    enzyme_counts: np.ndarray | None = None,
    allocated_gtp: float,
    substrate_counts: dict[str, float] | None = None,
) -> dict[str, Any]:
    counts = (
        np.asarray(enzyme_counts, dtype=np.int64).copy()
        if enzyme_counts is not None
        else process._initial_enzyme_counts.copy()
    )
    substrates = {wid: 1_000_000.0 for wid in process.substrate_wids}
    if substrate_counts is not None:
        substrates.update({wid: float(value) for wid, value in substrate_counts.items()})
    return {
        "cell": {
            "ftsz_ring_count": float(process._ring_count_from_counts(counts)),
            "ftsz_ring_complete": bool(
                process._ring_count_from_counts(counts)
                >= int(process.parameters["ring_complete_threshold"])
            ),
        },
        "substrates": substrates,
        "enzymes": {wid: float(counts[idx]) for idx, wid in enumerate(process.enzyme_wids)},
        "requests": {process.name: {process.gtp_wid: 0.0}},
        "substrates_allocated": {process.name: {process.gtp_wid: float(allocated_gtp)}},
    }


def _counts_after_update(
    process: KarrFtsZPolymerizationProcess,
    current_counts: np.ndarray,
    update: dict[str, Any],
) -> np.ndarray:
    next_counts = np.asarray(current_counts, dtype=np.int64).copy()
    enzyme_delta = update.get("enzymes", {})
    for idx, wid in enumerate(process.enzyme_wids):
        next_counts[idx] += int(float(enzyme_delta.get(wid, 0.0)))
    return next_counts


def test_fixture_loads() -> None:
    process = KarrFtsZPolymerizationProcess({})
    assert process.name == "karr_ftsz_polymerization"
    assert process.gtp_wid == "GTP"
    assert len(process.enzyme_wids) == 11
    assert process.initial_ring_count > 0
    assert process._geometry_volume > 0.0


def test_integration_with_chassis_v4() -> None:
    pytest.importorskip("opencell.vivarium.karr_composite")
    from opencell.vivarium.karr_composite import build_karr_chassis_v4

    engine = build_karr_chassis_v4(time_step_s=1.0, emit_step_s=1.0)
    assert "karr_ftsz_polymerization" in engine.processes
    state = engine.state.get_value()
    assert "cell" in state
    assert "ftsz_ring_count" in state["cell"]
    assert "ftsz_ring_complete" in state["cell"]


def test_zero_enzymes_returns_noop() -> None:
    process = KarrFtsZPolymerizationProcess({})
    zero_counts = np.zeros(len(process.enzyme_wids), dtype=np.int64)
    state = _base_state(
        process,
        enzyme_counts=zero_counts,
        allocated_gtp=1_000.0,
        substrate_counts={process.gtp_wid: 1_000.0},
    )

    assert process.next_update(1.0, state) == {}


def test_mass_conservation_after_next_update() -> None:
    process = KarrFtsZPolymerizationProcess({"rng_seed": 4})
    current_counts = process._initial_enzyme_counts.copy()
    state = _base_state(process, enzyme_counts=current_counts, allocated_gtp=50_000.0)

    update = process.next_update(1.0, state)
    next_counts = _counts_after_update(process, current_counts, update)

    assert int(np.dot(process.n_monomers, next_counts)) == int(
        np.dot(process.n_monomers, current_counts)
    )


def test_rate_1_activation_equilibrium() -> None:
    process = KarrFtsZPolymerizationProcess({})
    process.activation_fwd = 1.0
    process.activation_rev = 1.0
    process.exchange_fwd = 0.0
    process.exchange_rev = 0.0
    process.nucleation_fwd = 0.0
    process.nucleation_rev = 0.0
    process.elongation_fwd = 0.0
    process.elongation_rev = 0.0

    y0 = np.zeros(len(process.enzyme_wids), dtype=np.float64)
    y0[process.enzyme_index_ftsz] = 1.0
    _, ode_solutions = process.integrate_odes(
        y0=y0,
        substrate_counts=np.zeros(len(process.substrate_wids), dtype=np.float64),
        timestep=10.0,
    )
    equilibrium = ode_solutions[:, process._last_nonnegative_solution_idx(ode_solutions)]

    assert equilibrium[process.enzyme_index_ftsz] == pytest.approx(0.5, abs=1.0e-3)
    assert equilibrium[process.enzyme_index_ftsz_gtp] == pytest.approx(0.5, abs=1.0e-3)
    assert np.all(equilibrium[process.enzyme_index_ftsz_gdp :] >= -1.0e-10)


def test_apply_substrate_limits_clips_to_gtp_budget() -> None:
    process = KarrFtsZPolymerizationProcess({})
    current_counts = np.zeros(len(process.enzyme_wids), dtype=np.int64)
    current_counts[process.enzyme_index_ftsz] = 3

    proposed = current_counts.copy()
    proposed[process.enzyme_index_ftsz] = 0
    proposed[process.enzyme_index_ftsz_gtp] = 3

    substrates = np.zeros(len(process.substrate_wids), dtype=np.float64)
    substrates[process.substrate_index_gtp] = 1.0

    enzymes, limited_substrates = process.apply_substrate_limits(
        enzymes=proposed,
        substrates=substrates,
        current_counts=current_counts,
    )

    assert np.array_equal(enzymes, np.asarray([2, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], dtype=np.int64))
    assert limited_substrates[process.substrate_index_gtp] == pytest.approx(0.0)
    assert int(np.dot(process.n_monomers, enzymes)) == int(np.dot(process.n_monomers, current_counts))


def test_apply_substrate_limits_hydrolyzes_gtp_when_gdp_is_short() -> None:
    process = KarrFtsZPolymerizationProcess({})
    current_counts = np.zeros(len(process.enzyme_wids), dtype=np.int64)
    current_counts[process.enzyme_index_ftsz] = 1

    proposed = current_counts.copy()
    proposed[process.enzyme_index_ftsz] = 0
    proposed[process.enzyme_index_ftsz_gdp] = 1

    substrates = np.zeros(len(process.substrate_wids), dtype=np.float64)
    substrates[process.substrate_index_gtp] = 1.0
    substrates[process.substrate_index_water] = 1.0

    _, limited_substrates = process.apply_substrate_limits(
        enzymes=proposed,
        substrates=substrates,
        current_counts=current_counts,
    )

    assert limited_substrates[process.substrate_index_gdp] == pytest.approx(0.0)
    assert limited_substrates[process.substrate_index_gtp] == pytest.approx(0.0)
    assert limited_substrates[process.substrate_index_pi] == pytest.approx(1.0)
    assert limited_substrates[process.substrate_index_water] == pytest.approx(0.0)
    assert limited_substrates[process.substrate_index_h] == pytest.approx(1.0)


def test_gtp_consumption_matches_karr_stoichiometry() -> None:
    process = KarrFtsZPolymerizationProcess({"rng_seed": 0})
    current_counts = np.zeros(len(process.enzyme_wids), dtype=np.int64)
    current_counts[process.enzyme_index_ftsz] = 20
    state = _base_state(
        process,
        enzyme_counts=current_counts,
        allocated_gtp=1_000.0,
        substrate_counts={
            process.gdp_wid: 0.0,
            process.gtp_wid: 1_000.0,
            process.h2o_wid: 1_000.0,
        },
    )

    update = process.next_update(1.0, state)
    next_counts = _counts_after_update(process, current_counts, update)
    substrate_delta = {wid: int(float(value)) for wid, value in update.get("substrates", {}).items()}

    bound_gtp_delta = int(np.dot(process.n_gtp, next_counts - current_counts))
    hydrolysis = substrate_delta.get(process.pi_wid, 0)
    assert -substrate_delta.get(process.gtp_wid, 0) == bound_gtp_delta + hydrolysis
    assert substrate_delta.get(process.gdp_wid, 0) == 0
    assert substrate_delta.get(process.pi_wid, 0) == hydrolysis
    assert substrate_delta.get(process.h2o_wid, 0) == -hydrolysis
    assert substrate_delta.get(process.h_wid, 0) == hydrolysis
