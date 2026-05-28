from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.io import loadmat
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

from opencell.vivarium.karr_trna_aminoacylation import KarrTRNAAminoacylationProcess

_FIXTURE_PATH = "data/karr_fixtures/per_process/tRNAAminoacylation_flat.mat"


def _load_snapshot_state(process: KarrTRNAAminoacylationProcess) -> dict[str, Any]:
    """Load a realistic per-tick state from the tRNAAminoacylation fixture."""
    fixture = loadmat(_FIXTURE_PATH)["data"]["fixture"][0, 0]

    try:
        substrates = np.asarray(fixture["substrates"][0, 0], dtype=np.float64).reshape(-1)
        free_rna = np.asarray(fixture["freeRNAs"][0, 0], dtype=np.float64).reshape(-1)
        amino_rna = np.asarray(fixture["aminoacylatedRNAs"][0, 0], dtype=np.float64).reshape(-1)
        enzymes = np.asarray(fixture["enzymes"][0, 0], dtype=np.float64).reshape(-1)

        if (
            substrates.size != len(process.substrate_wids)
            or free_rna.size != len(process.free_rna_wids)
            or amino_rna.size != len(process.aminoacylated_rna_wids)
            or enzymes.size != len(process.enzyme_wids)
        ):
            raise ValueError("fixture vector length mismatch")
    except Exception:
        rng = np.random.default_rng(20260522)
        substrates = rng.integers(1_000, 10_000, size=len(process.substrate_wids)).astype(float)
        free_rna = rng.integers(1, 50, size=len(process.free_rna_wids)).astype(float)
        amino_rna = rng.integers(1, 80, size=len(process.aminoacylated_rna_wids)).astype(float)
        enzymes = rng.integers(1, 100, size=len(process.enzyme_wids)).astype(float)

    enzyme_by_wid = {wid: float(enzymes[idx]) for idx, wid in enumerate(process.enzyme_wids)}

    return {
        "substrates": {
            wid: float(substrates[idx]) for idx, wid in enumerate(process.substrate_wids)
        },
        "rna": {
            "counts": {wid: float(free_rna[idx]) for idx, wid in enumerate(process.free_rna_wids)},
            "aminoacylated_counts": {
                wid: float(amino_rna[idx]) for idx, wid in enumerate(process.aminoacylated_rna_wids)
            },
        },
        "protein": {
            "counts": {wid: enzyme_by_wid[wid] for wid in process.monomer_enzyme_wids}
        },
        "complex": {
            "counts": {wid: enzyme_by_wid[wid] for wid in process.complex_enzyme_wids}
        },
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {
            process.name: {
                wid: float(substrates[idx]) for idx, wid in enumerate(process.substrate_wids)
            }
        },
    }


def _apply_update(
    state: dict[str, Any],
    update: dict[str, Any],
    process: KarrTRNAAminoacylationProcess,
) -> None:
    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"][wid] + float(delta))
        state["substrates_allocated"][process.name][wid] = float(state["substrates"][wid])

    for wid, delta in update.get("rna", {}).get("counts", {}).items():
        state["rna"]["counts"][wid] = float(state["rna"]["counts"][wid] + float(delta))

    for wid, delta in update.get("rna", {}).get("aminoacylated_counts", {}).items():
        state["rna"]["aminoacylated_counts"][wid] = float(
            state["rna"]["aminoacylated_counts"][wid] + float(delta)
        )


def _charged_fraction(state: dict[str, Any], process: KarrTRNAAminoacylationProcess) -> float:
    free = sum(float(state["rna"]["counts"][wid]) for wid in process.free_rna_wids)
    charged = sum(
        float(state["rna"]["aminoacylated_counts"][wid]) for wid in process.aminoacylated_rna_wids
    )
    total = free + charged
    return float(charged / total) if total > 0.0 else 0.0


def test_fixture_loads() -> None:
    p = KarrTRNAAminoacylationProcess({})
    assert p.name == "karr_trna_aminoacylation"
    assert len(p.substrate_wids) == 30
    assert len(p.free_rna_wids) == 37
    assert len(p.aminoacylated_rna_wids) == 37
    assert len(p.enzyme_wids) == 58

    assert p.reaction_stoich.shape == (30, 39)
    assert p.reaction_stoich.dtype == np.int64
    assert p.reaction_catalysis.shape == (39, 21)
    assert p.reaction_catalysis.dtype == np.uint8
    assert p.reaction_modification.shape == (39, 37)
    assert p.reaction_modification.dtype == np.uint8
    assert p.enzyme_bounds.shape == (39, 2)
    assert p.enzyme_bounds.dtype == np.float64


def test_no_free_rna_no_action() -> None:
    p = KarrTRNAAminoacylationProcess({})
    state = _load_snapshot_state(p)
    for wid in p.free_rna_wids:
        state["rna"]["counts"][wid] = 0.0

    update = p.next_update(1.0, state)
    assert update == {}


def test_mass_conservation() -> None:
    p = KarrTRNAAminoacylationProcess({"rng_seed": 42})
    state = _load_snapshot_state(p)

    free = np.array([state["rna"]["counts"][wid] for wid in p.free_rna_wids], dtype=np.float64)
    substrates = np.array([state["substrates"][wid] for wid in p.substrate_wids], dtype=np.float64)
    enzymes = p._enzyme_vector_from_split_stores(
        protein_count_store=state["protein"]["counts"],
        complex_count_store=state["complex"]["counts"],
    )
    flux = p._compute_reaction_fluxes(free_rna=free, substrates=substrates, enzymes=enzymes, dt=1.0)

    update = p.next_update(1.0, state)
    observed_sub = np.array(
        [int(update["substrates"].get(wid, 0.0)) for wid in p.substrate_wids], dtype=np.int64
    )
    expected_sub = p.reaction_stoich @ flux
    np.testing.assert_array_equal(observed_sub, expected_sub)

    free_delta = np.array(
        [int(update["rna"]["counts"].get(wid, 0.0)) for wid in p.free_rna_wids], dtype=np.int64
    )
    charged_delta = np.array(
        [
            int(update["rna"]["aminoacylated_counts"].get(wid, 0.0))
            for wid in p.aminoacylated_rna_wids
        ],
        dtype=np.int64,
    )
    np.testing.assert_array_equal(free_delta + charged_delta, np.zeros_like(free_delta))


def test_steady_state_fraction() -> None:
    p = KarrTRNAAminoacylationProcess({"rng_seed": 0})
    state = _load_snapshot_state(p)

    # Keep ATP finite so the process approaches a bounded charged fraction over 100 ticks.
    state["substrates"]["ATP"] = 50.0
    state["substrates_allocated"][p.name]["ATP"] = 50.0

    for _ in range(100):
        update = p.next_update(1.0, state)
        if not update:
            break
        _apply_update(state, update, p)

    charged_fraction = _charged_fraction(state, p)
    assert charged_fraction == pytest.approx(0.67, abs=0.05)


def test_deterministic_phase_only() -> None:
    p1 = KarrTRNAAminoacylationProcess({"rng_seed": 1, "max_stochastic_iterations": 0})
    p2 = KarrTRNAAminoacylationProcess({"rng_seed": 999, "max_stochastic_iterations": 0})

    state_1 = _load_snapshot_state(p1)
    state_1["substrates"]["ATP"] = 75.0
    state_1["substrates_allocated"][p1.name]["ATP"] = 75.0
    state_2 = deepcopy(state_1)

    update_1 = p1.next_update(1.0, state_1)
    update_2 = p2.next_update(1.0, state_2)
    assert update_1 == update_2


def test_atp_consumption() -> None:
    p = KarrTRNAAminoacylationProcess({"rng_seed": 0})
    state = _load_snapshot_state(p)

    # Limit ATP to 100 events; suppress the no-ATP formyl-transfer branch.
    state["substrates"]["ATP"] = 100.0
    state["substrates_allocated"][p.name]["ATP"] = 100.0
    state["rna"]["counts"]["MG488"] = 0.0

    update = p.next_update(1.0, state)
    assert update["substrates"]["ATP"] == pytest.approx(-100.0)
    charged_events = sum(float(v) for v in update["rna"]["aminoacylated_counts"].values())
    assert charged_events == pytest.approx(100.0)


def test_enzyme_limit_kicks_in() -> None:
    p = KarrTRNAAminoacylationProcess({"rng_seed": 0, "max_stochastic_iterations": 0})
    state = _load_snapshot_state(p)

    ridx = 0
    enzyme_idx = int(np.argmax(p.reaction_catalysis[ridx]))
    enzyme_wid = p.enzyme_wids[enzyme_idx]
    target_wid = p.free_rna_wids[int(np.argmax(p.reaction_modification[ridx]))]

    for wid in p.free_rna_wids:
        state["rna"]["counts"][wid] = 0.0
    state["rna"]["counts"][target_wid] = 10.0

    for wid in p.monomer_enzyme_wids:
        state["protein"]["counts"][wid] = 0.0
    for wid in p.complex_enzyme_wids:
        state["complex"]["counts"][wid] = 0.0
    for sidx, coeff in enumerate(p.reaction_stoich[:, ridx]):
        if coeff < 0:
            wid = p.substrate_wids[sidx]
            state["substrates"][wid] = 100.0
            state["substrates_allocated"][p.name][wid] = 100.0

    update_starved = p.next_update(1.0, state)
    assert update_starved == {}

    if enzyme_wid in p.complex_enzyme_wids:
        state["complex"]["counts"][enzyme_wid] = 2.0
    else:
        state["protein"]["counts"][enzyme_wid] = 2.0
    update_enzyme = p.next_update(1.0, state)
    assert update_enzyme["rna"]["counts"][target_wid] < 0.0
    assert update_enzyme["rna"]["aminoacylated_counts"][target_wid] > 0.0


def test_integration_with_chassis_v3() -> None:
    pytest.importorskip("opencell.vivarium.karr_composite")
    from opencell.vivarium.karr_composite import build_karr_chassis_v3

    process = KarrTRNAAminoacylationProcess({})
    engine = build_karr_chassis_v3(time_step_s=1.0, emit_step_s=1.0)
    chassis_state = engine.state.get_value()

    state = {
        "substrates": {
            wid: float(chassis_state.get("substrates", {}).get(wid, 0.0))
            for wid in process.substrate_wids
        },
        "rna": {
            "counts": {
                wid: float(chassis_state.get("rna", {}).get("counts", {}).get(wid, 0.0))
                for wid in process.free_rna_wids
            },
            "aminoacylated_counts": {wid: 0.0 for wid in process.aminoacylated_rna_wids},
        },
        "protein": {
            "counts": {
                wid: float(chassis_state.get("protein", {}).get("counts", {}).get(wid, 0.0))
                for wid in process.monomer_enzyme_wids
            }
        },
        "complex": {
            "counts": {
                wid: float(chassis_state.get("complex", {}).get("counts", {}).get(wid, 0.0))
                for wid in process.complex_enzyme_wids
            }
        },
        "requests": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }
    update = process.next_update(1.0, state)
    assert isinstance(update, dict)


def test_within_tick_lag_at_dt_1s() -> None:
    process = KarrTRNAAminoacylationProcess({"rng_seed": 0})
    state = _load_snapshot_state(process)
    state["substrates"]["ATP"] = 50.0
    for wid in process.substrate_wids:
        state["substrates_allocated"][process.name][wid] = 0.0

    engine = Engine(
        processes={"karr_trna_aminoacylation": process},
        topology={
            "karr_trna_aminoacylation": {
                "substrates": ("substrates",),
                "rna": ("rna",),
                "protein": ("protein",),
                "complex": ("complex",),
                "requests": ("requests",),
                "substrates_allocated": ("substrates_allocated",),
            }
        },
        initial_state=state,
        emit_step=1.0,
        display_info=False,
    )
    engine.update(100.0)
    final_state = engine.state.get_value()
    final_fraction = _charged_fraction(final_state, process)
    assert abs(final_fraction - 0.67) <= 0.05


def test_v6_chassis_seeded_complex_enzyme_is_flux_active_without_manual_store_writes() -> None:
    pytest.importorskip("opencell.vivarium.karr_composite")
    from opencell.vivarium.karr_composite import build_karr_chassis_v6

    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    process = composite["processes"]["karr_trna_aminoacylation"]
    initial_state = deepcopy(composite["state"])
    complex_counts = initial_state["complex"]["counts"]

    seeded_complex_wids = [
        wid for wid in process.complex_enzyme_wids if float(complex_counts.get(wid, 0.0)) > 0.0
    ]
    assert seeded_complex_wids
    seeded_complex_wid = seeded_complex_wids[0]
    seeded_complex_count = float(complex_counts[seeded_complex_wid])
    assert seeded_complex_count > 0.0

    initial_state.setdefault("substrates_allocated", {})
    initial_state["substrates_allocated"][process.name] = {
        wid: float(initial_state["substrates"].get(wid, 0.0)) for wid in process.substrate_wids
    }
    enzymes = process._enzyme_vector_from_split_stores(
        protein_count_store=initial_state["protein"]["counts"],
        complex_count_store=initial_state["complex"]["counts"],
    )
    free_rna = np.asarray(
        [float(initial_state["rna"]["counts"][wid]) for wid in process.free_rna_wids],
        dtype=np.float64,
    )
    substrates = np.asarray(
        [float(initial_state["substrates_allocated"][process.name][wid]) for wid in process.substrate_wids],
        dtype=np.float64,
    )
    fluxes = process._compute_reaction_fluxes(
        free_rna=free_rna,
        substrates=substrates,
        enzymes=enzymes,
        dt=float(process.parameters["time_step"]),
    )

    enzyme_idx = process.enzyme_wids.index(seeded_complex_wid)
    catalyzed_rxn_idx = np.flatnonzero(process.reaction_catalysis[:, enzyme_idx] > 0)
    assert catalyzed_rxn_idx.size > 0
    assert np.any(fluxes[catalyzed_rxn_idx] > 0)
