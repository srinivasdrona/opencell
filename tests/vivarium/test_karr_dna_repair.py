from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import h5py
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

from opencell.vivarium.karr_dna_repair import KarrDNARepairProcess
from opencell.vivarium.chromosome_views import current_damage_sites


def _enzyme_counts_by_store(process: KarrDNARepairProcess) -> tuple[dict[str, float], dict[str, float]]:
    protein_counts = {
        wid: float(process.enzyme_defaults.get(wid, 0.0)) for wid in process.protein_enzyme_wids
    }
    complex_counts = {
        wid: float(process.enzyme_defaults.get(wid, 0.0)) for wid in process.complex_enzyme_wids
    }
    return protein_counts, complex_counts


def _base_state(
    process: KarrDNARepairProcess,
    *,
    damage_sites: list[dict[str, Any]] | None = None,
    substrate_pool: float = 1.0e6,
    allocated_pool: float = 0.0,
) -> dict[str, Any]:
    damage_sites = damage_sites or []
    protein_counts, complex_counts = _enzyme_counts_by_store(process)
    return {
        "chromosome": {
            "damage_events_cumulative": damage_sites,
            "repair_events_cumulative": [],
            "repair_count": 0.0,
            "repair_count_by_pathway": {pathway: 0.0 for pathway in ("ber", "ner", "hr", "nhej_like")},
        },
        "protein": {"counts": protein_counts},
        "complex": {"counts": complex_counts},
        "substrates": {wid: float(substrate_pool) for wid in process.tracked_substrates},
        "requests": {process.name: {wid: 0.0 for wid in process.tracked_substrates}},
        "substrates_allocated": {
            process.name: {wid: float(allocated_pool) for wid in process.tracked_substrates}
        },
    }


def _apply_update(
    state: dict[str, Any],
    update: dict[str, Any],
    process: KarrDNARepairProcess,
) -> None:
    chrom = update.get("chromosome", {})
    if "repair_events_cumulative" in chrom:
        state["chromosome"]["repair_events_cumulative"].extend(
            deepcopy(chrom["repair_events_cumulative"])
        )
    if "repair_count" in chrom:
        state["chromosome"]["repair_count"] = float(state["chromosome"]["repair_count"]) + float(
            chrom["repair_count"]
        )
    if "repair_count_by_pathway" in chrom:
        for pathway, delta in chrom["repair_count_by_pathway"].items():
            current = float(state["chromosome"]["repair_count_by_pathway"].get(pathway, 0.0))
            state["chromosome"]["repair_count_by_pathway"][pathway] = current + float(delta)

    if "substrates" in update:
        for wid, delta in update["substrates"].items():
            state["substrates"][wid] = float(state["substrates"].get(wid, 0.0)) + float(delta)

    if "requests" in update:
        state["requests"][process.name] = {
            wid: float(update["requests"][process.name].get(wid, 0.0)) for wid in process.tracked_substrates
        }


def _trace_path_candidates() -> list[Path]:
    return [
        _REPO_ROOT / "data" / "m1_sources" / "karr_native" / "per_process_traces" / "DNARepair_100ticks.mat",
        Path("E:/opencell/data/m1_sources/karr_native/per_process_traces/DNARepair_100ticks.mat"),
    ]


def _trace_has_nonzero_substrate_delta(path: Path) -> bool:
    with h5py.File(path, "r") as f:
        before_refs = f["states_before/substrates"]
        after_refs = f["states_after/substrates"]
        for tick in range(before_refs.shape[0]):
            before = np.asarray(f[before_refs[tick, 0]]).reshape(-1)
            after = np.asarray(f[after_refs[tick, 0]]).reshape(-1)
            if np.any(np.abs(after - before) > 1e-12):
                return True
    return False


def test_process_instantiates_with_defaults() -> None:
    process = KarrDNARepairProcess({})
    schema = process.ports_schema()

    assert process.name == "karr_dna_repair"
    assert process.atp_wid == "ATP"
    assert set(process.dntp_wids) == {"DATP", "DCTP", "DGTP", "DTTP"}
    assert process.ner_patch_length_nt >= 1.0
    assert process.hr_patch_length_nt >= 1.0
    assert set(process.pathway_reaction_indices) == {"ber", "ner", "hr", "nhej_like"}

    assert schema["chromosome"]["repair_count"]["_updater"] == "accumulate"
    assert schema["chromosome"]["repair_count_by_pathway"]["ber"]["_updater"] == "accumulate"
    assert schema["requests"][process.name]["ATP"]["_updater"] == "set"
    assert "_updater" not in schema["substrates_allocated"][process.name]["ATP"]


def test_one_tick_run_produces_positive_repair_delta() -> None:
    process = KarrDNARepairProcess({"rng_seed": 4, "pathway_rate_scale": 300.0})
    damage_sites = [
        {"site_id": f"site_{i}", "damage_type": "intrastrand_crosslink", "position": i}
        for i in range(20)
    ]
    state = _base_state(process, damage_sites=damage_sites, allocated_pool=1.0e6)
    update = process.next_update(1.0, state)

    assert update["chromosome"]["repair_count"] > 0.0
    assert len(update["chromosome"]["repair_events_cumulative"]) > 0
    assert any(float(v) < 0.0 for v in update.get("substrates", {}).values())


def test_chassis_seeded_complex_wid_changes_repair_output() -> None:
    from opencell.vivarium.karr_composite import build_karr_chassis_v6

    process_with = KarrDNARepairProcess({"rng_seed": 23, "pathway_rate_scale": 1.0})
    process_without = KarrDNARepairProcess({"rng_seed": 23, "pathway_rate_scale": 1.0})

    chassis = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    chassis_state = chassis["state"] if isinstance(chassis, dict) else chassis.state
    seeded_wid = "MG_073_206_421_TETRAMER"
    assert seeded_wid in process_with.complex_enzyme_wids
    assert chassis_state["complex"]["counts"][seeded_wid] > 0.0

    damage_sites = [
        {"site_id": f"ner_{idx}", "damage_type": "intrastrand_crosslink", "position": idx}
        for idx in range(20)
    ]
    state_with = _base_state(process_with, damage_sites=damage_sites, allocated_pool=1.0e6)
    state_without = _base_state(process_without, damage_sites=damage_sites, allocated_pool=1.0e6)
    for wid in process_with.complex_enzyme_wids:
        seeded_count = float(chassis_state["complex"]["counts"][wid])
        state_with["complex"]["counts"][wid] = seeded_count
        state_without["complex"]["counts"][wid] = seeded_count
    state_without["complex"]["counts"][seeded_wid] = 0.0

    update_with = process_with.next_update(1.0, state_with)
    update_without = process_without.next_update(1.0, state_without)

    with_ner = float(update_with["chromosome"]["repair_count_by_pathway"]["ner"])
    without_ner = float(update_without["chromosome"]["repair_count_by_pathway"]["ner"])
    assert with_ner != without_ner


def test_allocation_contract_honored() -> None:
    params = {"rng_seed": 11, "pathway_rate_scale": 500.0}
    lesions = [{"site_id": f"x{i}", "damage_type": "double_strand_break"} for i in range(10)]

    p_high = KarrDNARepairProcess(params)
    p_low = KarrDNARepairProcess(params)

    s_high = _base_state(p_high, damage_sites=deepcopy(lesions), allocated_pool=1.0e6)
    s_low = _base_state(p_low, damage_sites=deepcopy(lesions), substrate_pool=0.0, allocated_pool=0.0)

    u_high = p_high.next_update(1.0, s_high)
    u_low = p_low.next_update(1.0, s_low)

    assert u_high["chromosome"]["repair_count"] > 0.0
    assert u_low.get("chromosome", {}).get("repair_count", 0.0) == 0.0
    assert u_high["requests"][p_high.name]["ATP"] > 0.0
    assert u_low["requests"][p_low.name]["ATP"] > 0.0


def test_pathway_routing_and_counts() -> None:
    process = KarrDNARepairProcess({"rng_seed": 13, "pathway_rate_scale": 1000.0})
    damage_sites = [
        {"site_id": "ab1", "damage_type": "abasic_site"},
        {"site_id": "db1", "damage_type": "damaged_base"},
        {"site_id": "ix1", "damage_type": "intrastrand_crosslink"},
        {"site_id": "ds1", "damage_type": "double_strand_break"},
        {"site_id": "ss1", "damage_type": "single_strand_break"},
    ]
    state = _base_state(process, damage_sites=damage_sites, allocated_pool=1.0e6)
    update = process.next_update(1.0, state)

    by_pathway = update["chromosome"]["repair_count_by_pathway"]
    assert by_pathway["ber"] == pytest.approx(2.0)
    assert by_pathway["ner"] == pytest.approx(1.0)
    assert by_pathway["hr"] == pytest.approx(1.0)
    assert by_pathway["nhej_like"] == pytest.approx(1.0)
    assert len(update["chromosome"]["repair_events_cumulative"]) == 5


def test_steady_state_100_ticks_matches_trace_quiescent() -> None:
    process = KarrDNARepairProcess({"rng_seed": 17})
    state = _base_state(process, damage_sites=[], substrate_pool=1.0e6, allocated_pool=0.0)

    for _ in range(100):
        update = process.next_update(1.0, state)
        _apply_update(state, update, process)

    assert state["chromosome"]["repair_count"] == pytest.approx(0.0)
    assert all(v == pytest.approx(0.0) for v in state["chromosome"]["repair_count_by_pathway"].values())
    assert all(state["substrates"][wid] == pytest.approx(1.0e6) for wid in process.tracked_substrates)

    for candidate in _trace_path_candidates():
        if candidate.exists():
            assert _trace_has_nonzero_substrate_delta(candidate) is False
            break


def test_no_nan_or_negative_regression() -> None:
    process = KarrDNARepairProcess({"rng_seed": 19, "pathway_rate_scale": 600.0})
    damage_sites = [
        {"site_id": f"ab{i}", "damage_type": "abasic_site"} for i in range(30)
    ] + [
        {"site_id": f"ix{i}", "damage_type": "intrastrand_crosslink"} for i in range(10)
    ]
    state = _base_state(process, damage_sites=damage_sites, substrate_pool=5.0e3, allocated_pool=0.0)

    for _ in range(100):
        update = process.next_update(1.0, state)
        _apply_update(state, update, process)

        assert np.isfinite(state["chromosome"]["repair_count"])
        assert state["chromosome"]["repair_count"] >= 0.0
        assert all(
            np.isfinite(value) and value >= 0.0 for value in state["chromosome"]["repair_count_by_pathway"].values()
        )
        assert all(np.isfinite(value) and value >= -1e-9 for value in state["substrates"].values())
        assert len(current_damage_sites(state)) >= 0
