from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest
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

from opencell.vivarium.karr_composite import (
    CHASSIS_V6_EXPECTED_PROCESS_KEYS,
    build_karr_chassis_v6,
)

_HOST_FIELDS = (
    "host_attached",
    "host_tlr1_activated",
    "host_tlr2_activated",
    "host_tlr6_activated",
    "host_nfkb_activated",
    "host_inflammatory_response_activated",
)


def _build_engine() -> Engine:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    return Engine(composite=composite, emit_step=1.0, display_info=False)


def _sum_count_timeseries(counts_ts: dict[str, list[float]]) -> np.ndarray:
    n = len(next(iter(counts_ts.values())))
    totals = np.zeros(n, dtype=np.float64)
    for series in counts_ts.values():
        totals += np.asarray(series, dtype=np.float64)
    return totals


def _sum_state_counts(state: dict[str, object], store: str) -> float:
    store_data = state.get(store, {})
    if not isinstance(store_data, dict):
        return 0.0
    counts = store_data.get("counts", {})
    if not isinstance(counts, dict):
        return 0.0
    return float(sum(float(value) for value in counts.values()))


def test_v6_builds() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    proc_keys = set(composite["processes"].keys())
    assert proc_keys >= set(CHASSIS_V6_EXPECTED_PROCESS_KEYS)


def test_v6_one_tick() -> None:
    engine = _build_engine()
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        engine.update(1.0)
    state = engine.state.get_value()
    assert "chromosome" in state
    assert "rna" in state
    assert "protein" in state


def test_v6_protein_activation_uses_one_shared_canonical_state() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    process = composite["processes"]["karr_protein_activation"]
    initial_state = composite["state"]

    assert composite["topology"]["karr_protein_activation"] == {
        "protein": ("protein",),
        "complex": ("complex",),
        "stimuli": ("stimuli",),
        "geometry": ("geometry",),
    }
    assert "activation_substrates" not in initial_state
    assert composite["topology"]["karr_translation"]["protein"] == ("protein",)
    assert composite["topology"]["karr_transcriptional_regulation"]["protein"] == (
        "protein",
    )
    assert composite["topology"]["karr_transcriptional_regulation"]["complex"] == (
        "complex",
    )

    expected = process.canonical_state()
    expected_active, expected_inactive = process.state_matrices(expected)
    initial_active, initial_inactive = process.state_matrices(initial_state)
    np.testing.assert_array_equal(initial_active, expected_active)
    np.testing.assert_array_equal(initial_inactive, expected_inactive)
    assert initial_state["geometry"]["volume"] == process.default_geometry_volume
    assert initial_state["stimuli"] == process.default_stimuli

    engine = Engine(composite=composite, emit_step=1.0, display_info=False)
    engine_active, engine_inactive = process.state_matrices(engine.state.get_value())
    np.testing.assert_array_equal(engine_active, expected_active)
    np.testing.assert_array_equal(engine_inactive, expected_inactive)


def test_v6_host_initializes_from_canonical_stores_and_stays_positive() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    process = composite["processes"]["karr_host_interaction"]
    initial_state = composite["state"]
    expected = {field: True for field in _HOST_FIELDS}

    assert composite["topology"]["karr_host_interaction"] == {
        "cell": ("cell",),
        "protein": ("protein",),
        "complex": ("complex",),
    }
    assert {
        field: initial_state["cell"][field] for field in _HOST_FIELDS
    } == expected
    for wid, count in process.fitted_monomer_counts_by_wid.items():
        assert initial_state["protein"]["counts"][wid] == count
    for wid, count in process.fitted_complex_counts_by_wid.items():
        assert initial_state["complex"]["counts"][wid] == count

    engine = Engine(composite=composite, emit_step=1.0, display_info=False)
    before_update = engine.state.get_value()
    assert {field: before_update["cell"][field] for field in _HOST_FIELDS} == expected

    engine.update(1.0)
    after_update = engine.state.get_value()
    assert {field: after_update["cell"][field] for field in _HOST_FIELDS} == expected


@pytest.mark.parametrize(
    ("pentamer_count", "expected"),
    (
        (17.0, (True, True, True, False, True, True)),
        (0.0, (True, False, False, False, False, False)),
    ),
)
def test_v6_host_complex_port_drives_engine_cascade(
    pentamer_count: float,
    expected: tuple[bool, ...],
) -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    initial_state = composite["state"]
    protein_counts = initial_state["protein"]["counts"]
    for wid in (
        "MG_075_MONOMER",
        "MG_149_MONOMER",
        "MG_309_MONOMER",
        "MG_412_MONOMER",
    ):
        protein_counts[wid] = 0.0
    initial_state["complex"]["counts"]["MG_410_411_412_PENTAMER"] = pentamer_count

    engine = Engine(composite=composite, emit_step=1.0, display_info=False)
    engine.update(1.0)
    cell = engine.state.get_value()["cell"]

    assert tuple(bool(cell[field]) for field in _HOST_FIELDS) == expected


def test_v6_chromosome_segregation_complex_seed_gate_and_effect() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    process = composite["processes"]["karr_chromosome_segregation"]
    state = composite["state"]

    required_complex_wid = "MG_221_OCTAMER"
    complex_seed = float(state["complex"]["counts"].get(required_complex_wid, 0.0))
    assert required_complex_wid in process.required_complex_enzyme_wids
    assert complex_seed > 0.0

    length = process.sequence_len
    fully_replicated = {
        "positions": [0, 0, 0, 0],
        "strands": [0, 1, 2, 3],
        "values": [length, length, length, length],
        "shape": process.chromosome_shape,
    }
    # Real tick-99 anchor linkingNumbers values (data/m1_sources/karr_native/
    # per_process_traces_v2_event_s000/ChromosomeSegregation_100ticks.mat):
    # within tolerance of equilibrium_superhelical_density for all 4 strands.
    fully_supercoiled = {
        "positions": [0, 0, 0, 0],
        "strands": [0, 1, 2, 3],
        "values": [52013, 52013, 52026, 52026],
        "shape": process.chromosome_shape,
    }

    process_state = {
        "chromosome": {
            "segregated": False,
            "polymerizedRegions": fully_replicated,
            "linkingNumbers": fully_supercoiled,
        },
        "protein": state["protein"],
        "complex": state["complex"],
        "substrates": state["substrates"],
        "requests": {
            process.name: {
                process.gtp_wid: 0.0,
                process.h2o_wid: 0.0,
            }
        },
        "substrates_allocated": {
            process.name: {
                process.gtp_wid: float(process.gtp_cost),
                process.h2o_wid: float(process.gtp_cost),
            }
        },
    }
    update = process.next_update(1.0, process_state)
    assert update["chromosome"].get("segregated") is True

    no_complex_state = dict(process_state)
    no_complex_counts = dict(state["complex"]["counts"])
    no_complex_counts[required_complex_wid] = 0.0
    no_complex_state["complex"] = {"counts": no_complex_counts}
    update_without_complex = process.next_update(1.0, no_complex_state)
    assert "segregated" not in update_without_complex["chromosome"]


@pytest.mark.slow
def test_v6_short_run_100s() -> None:
    engine = _build_engine()
    initial_state = engine.state.get_value()
    engine.update(100.0)
    final_state = engine.state.get_value()

    dry_mass_proxy_initial = (
        _sum_state_counts(initial_state, "protein")
        + _sum_state_counts(initial_state, "rna")
        + _sum_state_counts(initial_state, "complex")
    )
    dry_mass_proxy_final = (
        _sum_state_counts(final_state, "protein")
        + _sum_state_counts(final_state, "rna")
        + _sum_state_counts(final_state, "complex")
    )

    assert dry_mass_proxy_final > dry_mass_proxy_initial * 0.99


def test_v6_cpk_002_resolved() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    chrom_damage_schema = composite["processes"]["karr_dna_damage"].ports_schema()["chromosome"]
    chrom_repair_schema = composite["processes"]["karr_dna_repair"].ports_schema()["chromosome"]

    assert "damage_events_cumulative" in chrom_damage_schema
    assert "repair_events_cumulative" in chrom_damage_schema
    assert "damage_events_cumulative" in chrom_repair_schema
    assert "repair_events_cumulative" in chrom_repair_schema


def test_v6_cpk_003_resolved() -> None:
    from opencell.vivarium.karr_dna_damage import KarrDNADamageProcess

    proc = KarrDNADamageProcess({})
    ports = proc.ports_schema()
    chrom = ports.get("chromosome", {})
    assert "fork_position_bp" in chrom
    assert "fork_positions" not in chrom


def test_v6_allocation_consumers_include_rna_decay_not_host_interaction() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    allocation = composite["steps"]["karr_allocation_step"]
    consumers = dict(allocation.parameters["consumer_processes"])

    assert consumers.get("karr_rna_decay") == ["H2O"]
    assert "karr_host_interaction" not in consumers


def test_v6_trna_aminoacylation_complex_chain_seed_port_read() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    topology = composite["topology"]["karr_trna_aminoacylation"]
    trna_proc = composite["processes"]["karr_trna_aminoacylation"]
    initial_state = composite["state"]

    assert topology["complex"] == ("complex",)
    complex_counts = initial_state["complex"]["counts"]
    seeded_complex_wids = [
        wid for wid in trna_proc.complex_enzyme_wids if float(complex_counts.get(wid, 0.0)) > 0.0
    ]
    assert seeded_complex_wids

    seeded_complex_wid = seeded_complex_wids[0]
    seeded_complex_count = float(complex_counts[seeded_complex_wid])
    assert seeded_complex_count > 0.0

    enzymes = trna_proc._enzyme_vector_from_split_stores(
        protein_count_store=initial_state["protein"]["counts"],
        complex_count_store=complex_counts,
    )
    seeded_idx = trna_proc.enzyme_wids.index(seeded_complex_wid)
    assert enzymes[seeded_idx] == pytest.approx(seeded_complex_count)
