from __future__ import annotations

import math
import sys
from copy import deepcopy
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

from opencell.state.chromosome_store import CHROMOSOME_HIDDEN_STATE_KEY, SparseTriplet
from opencell.vivarium.karr_composite import build_karr_chassis_v6
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess


def _base_state(
    process: KarrDNASupercoilingProcess,
    *,
    sigma: float,
    replication_state: str = "idle",
    atp: float = 10_000.0,
    h2o: float | None = None,
    gyrase_count: float = 3.0,
    topoiv_count: float = 12.0,
    topoi_count: float = 1.0,
    initialize_gyrase: bool = False,
) -> dict[str, Any]:
    protein_counts: dict[str, float] = {}
    complex_counts: dict[str, float] = {}
    for wid, count in (
        (process.gyrase_wid, gyrase_count),
        (process.topoiv_wid, topoiv_count),
        (process.topoi_wid, topoi_count),
    ):
        if process.enzyme_store_by_wid.get(wid) == "complex":
            complex_counts[wid] = float(count)
        else:
            protein_counts[wid] = float(count)

    substrates = {wid: 0.0 for wid in process.substrate_wids}
    substrates[process.atp_wid] = float(atp)
    substrates[process.h2o_wid] = float(atp if h2o is None else h2o)
    substrates[process.adp_wid] = 0.0
    substrates[process.pi_wid] = 0.0

    chromosome_state = process.build_default_chromosome_state(
        sigma=sigma,
        replication_state=replication_state,
    )
    bound_enzymes: dict[str, float] = {}
    if initialize_gyrase:
        initialized = process.build_default_initialized_state(
            sigma=sigma,
            replication_state=replication_state,
            available_gyrase=gyrase_count,
        )
        chromosome_state = initialized["chromosome"]
        bound_enzymes = dict(initialized["boundEnzymes"])
        gyrase_free = float(initialized["free_gyrase_count"])
        if process.enzyme_store_by_wid.get(process.gyrase_wid) == "complex":
            complex_counts[process.gyrase_wid] = gyrase_free
        else:
            protein_counts[process.gyrase_wid] = gyrase_free

    return {
        "chromosome": chromosome_state,
        "protein": {"counts": protein_counts},
        "complex": {"counts": complex_counts},
        "substrates": substrates,
        "requests": {
            process.name: {
                process.atp_wid: float(atp),
                process.h2o_wid: float(atp if h2o is None else h2o),
            }
        },
        "substrates_allocated": {
            process.name: {
                process.atp_wid: float(atp),
                process.h2o_wid: float(atp if h2o is None else h2o),
            }
        },
        "boundEnzymes": bound_enzymes,
    }


def _apply_update(
    process: KarrDNASupercoilingProcess,
    state: dict[str, Any],
    update: dict[str, Any],
) -> None:
    chrom_update = update.get("chromosome", {})
    for field_name in ("linkingNumbers", "monomerBoundSites", "complexBoundSites"):
        if field_name in chrom_update:
            state["chromosome"][field_name] = SparseTriplet.from_state(
                chrom_update[field_name],
                shape=process.chromosome_shape,
            ).to_state()
    if "supercoil_density" in chrom_update:
        state["chromosome"]["supercoil_density"] = float(chrom_update["supercoil_density"])
    if "supercoiled" in chrom_update:
        state["chromosome"]["supercoiled"] = bool(chrom_update["supercoiled"])
    if "replication_state" in chrom_update:
        state["chromosome"]["replication_state"] = str(chrom_update["replication_state"])

    for wid, delta in update.get("substrates", {}).items():
        state["substrates"][wid] = float(state["substrates"].get(wid, 0.0) + float(delta))

    for channel in ("protein", "complex"):
        counts = update.get(channel, {}).get("counts", {})
        if counts:
            bucket = state.setdefault(channel, {}).setdefault("counts", {})
            for wid, delta in counts.items():
                bucket[wid] = float(bucket.get(wid, 0.0) + float(delta))

    for channel in ("enzymes", "boundEnzymes"):
        deltas = update.get(channel, {})
        if deltas:
            bucket = state.setdefault(channel, {})
            for wid, delta in deltas.items():
                bucket[wid] = float(bucket.get(wid, 0.0) + float(delta))

    if process.name in update.get("requests", {}):
        req = update["requests"][process.name]
        state["requests"][process.name][process.atp_wid] = float(req.get(process.atp_wid, 0.0))
        state["requests"][process.name][process.h2o_wid] = float(req.get(process.h2o_wid, 0.0))


def _bound_site_triplet(
    process: KarrDNASupercoilingProcess,
    enzyme_wid: str,
    *,
    positions: list[int],
    strands: list[int],
) -> SparseTriplet:
    enzyme_idx = process.enzyme_wids.index(enzyme_wid)
    enzyme_global_idx = int(process.enzyme_global_indices[enzyme_idx])
    return SparseTriplet(
        positions=np.asarray(positions, dtype=np.int64),
        strands=np.asarray(strands, dtype=np.int64),
        values=np.full(len(positions), enzyme_global_idx, dtype=np.int64),
        shape=process.chromosome_shape,
    )


def _duplex_region_triplet(
    process: KarrDNASupercoilingProcess,
    positive_regions: list[tuple[int, int, int]],
    *,
    value_mode: str,
    sigma: float = -0.06,
) -> SparseTriplet:
    positions: list[int] = []
    strands: list[int] = []
    values: list[int] = []
    for start, strand, length in positive_regions:
        if value_mode == "polymerized":
            value = int(length)
        elif value_mode == "linking":
            relaxed = float(length) / float(process.parameters["bp_per_turn"])
            value = int(round(relaxed * (1.0 + float(sigma))))
        else:
            raise ValueError(f"unknown value mode: {value_mode}")
        positions.extend([int(start), int(start)])
        strands.extend([int(strand), int(strand) + 1])
        values.extend([value, value])
    return SparseTriplet(
        positions=np.asarray(positions, dtype=np.int64),
        strands=np.asarray(strands, dtype=np.int64),
        values=np.asarray(values, dtype=np.int64),
        shape=process.chromosome_shape,
    )


def _simulate_stochastic_binding_positions(
    *,
    seed: int | None = None,
    footprint: int,
    available_count: int,
    regions: list[tuple[int, int, int]],
    rng: np.random.Generator | None = None,
) -> list[int]:
    if rng is None:
        if seed is None:
            raise ValueError("seed is required when rng is not provided")
        rng = np.random.default_rng(seed)
    region_starts = [int(start) for start, _, _ in regions]
    region_strands = [int(strand) for _, strand, _ in regions]
    region_lengths = [int(length) for _, _, length in regions]
    region_weights = [max(0, int(length) - int(footprint) + 1) for length in region_lengths]
    positions: list[int] = []

    for _ in range(int(available_count)):
        if not any(region_weights):
            break
        weights = np.asarray(region_weights, dtype=np.float64)
        weights /= float(weights.sum())
        region_idx = int(rng.choice(len(region_weights), p=weights))
        offset = int(
            math.floor(rng.random() * float(region_lengths[region_idx] - int(footprint) + 1))
        )
        positions.append(region_starts[region_idx] + offset)

        region_starts.append(region_starts[region_idx] + offset + int(footprint))
        region_strands.append(region_strands[region_idx])
        region_lengths.append(region_lengths[region_idx] - offset - int(footprint))
        region_lengths[region_idx] = offset
        region_weights[region_idx] = max(0, region_lengths[region_idx] - int(footprint) + 1)
        region_weights.append(max(0, region_lengths[-1] - int(footprint) + 1))

    return positions


def _stochastic_round_with_rng(value: float, rng: np.random.Generator) -> int:
    if value <= 0.0:
        return 0
    base = int(math.floor(value))
    frac = float(value - base)
    if frac <= 0.0:
        return base
    return base + int(rng.random() < frac)


def _simulate_initialized_gyrase_binding(
    process: KarrDNASupercoilingProcess,
    *,
    seed: int,
    available_gyrase: float,
) -> tuple[int, list[int]]:
    rng = np.random.default_rng(seed)
    expected_binding = float(available_gyrase) * (
        1.0 - 1.0 / float(process.gyrase_mean_dwell_time) / float(process.parameters["time_step"])
    )
    n_binding = _stochastic_round_with_rng(expected_binding, rng)
    positions = _simulate_stochastic_binding_positions(
        footprint=process._enzyme_footprint(process.gyrase_idx),  # noqa: SLF001
        available_count=n_binding,
        regions=[(0, 0, process.chromosome_length)],
        rng=rng,
    )
    return n_binding, positions


def _first_nonzero_index(
    values: np.ndarray,
    *,
    exclude: int,
    min_value: int = 1,
) -> int:
    for idx, value in enumerate(np.asarray(values, dtype=np.int64).tolist(), start=1):
        if idx == int(exclude):
            continue
        if int(value) >= int(min_value):
            return idx
    raise AssertionError("expected at least one alternate positive-footprint index")


def _install_releasable_rules(
    process: KarrDNASupercoilingProcess,
    *,
    binding_enzyme_idx: int,
    releasable_monomers: tuple[int, ...] = (),
    releasable_complexes: tuple[int, ...] = (),
) -> None:
    n_rows = max(1, len(releasable_monomers), len(releasable_complexes))
    process.reaction_thresholds = np.ones(n_rows, dtype=np.int64)
    process.reaction_bound_monomer = np.zeros(n_rows, dtype=np.int64)
    process.reaction_bound_complex = np.zeros(n_rows, dtype=np.int64)
    process.reaction_monomer_catalysis_matrix = np.zeros(
        (n_rows, process.all_monomer_dna_footprints.size),
        dtype=np.int64,
    )
    process.reaction_complex_catalysis_matrix = np.zeros(
        (n_rows, process.all_complex_dna_footprints.size),
        dtype=np.int64,
    )

    binding_global_idx = int(process.enzyme_global_indices[binding_enzyme_idx])
    if process.enzyme_is_monomer[binding_enzyme_idx]:
        process.reaction_monomer_catalysis_matrix[:, binding_global_idx - 1] = 1
    else:
        process.reaction_complex_catalysis_matrix[:, binding_global_idx - 1] = 1

    for row_idx, monomer_idx in enumerate(releasable_monomers):
        process.reaction_bound_monomer[row_idx] = int(monomer_idx)
    for row_idx, complex_idx in enumerate(releasable_complexes):
        process.reaction_bound_complex[row_idx] = int(complex_idx)


def _advance_tick(process: KarrDNASupercoilingProcess, state: dict[str, Any]) -> dict[str, Any]:
    update = process.next_update(1.0, state)
    _apply_update(process, state, update)

    request_atp = max(0.0, float(state["requests"][process.name].get(process.atp_wid, 0.0)))
    request_h2o = max(0.0, float(state["requests"][process.name].get(process.h2o_wid, 0.0)))
    available_atp = max(0.0, float(state["substrates"].get(process.atp_wid, 0.0)))
    available_h2o = max(0.0, float(state["substrates"].get(process.h2o_wid, 0.0)))
    state["substrates_allocated"][process.name][process.atp_wid] = float(
        min(request_atp, available_atp)
    )
    state["substrates_allocated"][process.name][process.h2o_wid] = float(
        min(request_h2o, available_h2o)
    )
    return update


def test_process_instantiates_with_defaults() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
        }
    )
    assert process.name == "karr_dna_supercoiling"
    assert process.gyrase_wid == "DNA_GYRASE"
    assert process.topoiv_wid == "MG_203_204_TETRAMER"
    assert process.topoi_wid == "MG_122_MONOMER"
    assert process.atp_wid == "ATP"
    assert process.h2o_wid == "H2O"
    assert process.gyrase_activity_rate > 0.0
    assert process.topoiv_activity_rate > 0.0
    assert process.topoi_activity_rate > 0.0
    schema = process.ports_schema()["chromosome"]
    assert schema["linkingNumbers"]["positions"]["_updater"] == "set"
    assert schema["polymerizedRegions"]["positions"]["_updater"] == "set"


def test_declared_complex_enzymes_fail_fast_when_missing_from_complex_port() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
        }
    )
    state = _base_state(
        process,
        sigma=-0.02,
        atp=10_000.0,
        gyrase_count=5.0,
        topoiv_count=5.0,
    )
    state_missing_complex = deepcopy(state)
    state_missing_complex["protein"]["counts"][process.gyrase_wid] = 5.0
    state_missing_complex["protein"]["counts"][process.topoiv_wid] = 5.0
    state_missing_complex["complex"]["counts"] = {}

    with pytest.raises(KeyError, match="Missing declared complex enzyme"):
        process.next_update(1.0, state_missing_complex)


def test_chassis_seeded_complex_enzyme_changes_request_output() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    topology = composite["topology"]["karr_dna_supercoiling"]
    assert "complex" in topology

    chassis_process = composite["processes"]["karr_dna_supercoiling"]
    gyrase_free_seed = float(composite["state"]["complex"]["counts"][chassis_process.gyrase_wid])
    gyrase_bound_seed = float(composite["state"]["boundEnzymes"][chassis_process.gyrase_wid])
    gyrase_seed = gyrase_free_seed + gyrase_bound_seed
    assert gyrase_seed > 0.0

    with_seed = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 23,
        }
    )
    without_seed = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 23,
        }
    )
    state_with_seed = _base_state(
        with_seed,
        sigma=-0.02,
        atp=10_000.0,
        gyrase_count=gyrase_seed,
        topoiv_count=0.0,
        topoi_count=0.0,
        initialize_gyrase=True,
    )
    state_without_seed = _base_state(
        without_seed,
        sigma=-0.02,
        atp=10_000.0,
        gyrase_count=0.0,
        topoiv_count=0.0,
        topoi_count=0.0,
    )

    update_with_seed = with_seed.next_update(1.0, state_with_seed)
    update_without_seed = without_seed.next_update(1.0, state_without_seed)
    request_with_seed = float(update_with_seed["requests"][with_seed.name][with_seed.atp_wid])
    request_without_seed = float(
        update_without_seed["requests"][without_seed.name][without_seed.atp_wid]
    )
    assert request_with_seed > request_without_seed


def test_default_initialized_state_binds_gyrase_and_transfers_ownership() -> None:
    seed = 59
    available_gyrase = 3.0
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": seed,
        }
    )
    expected_bound, expected_positions = _simulate_initialized_gyrase_binding(
        process,
        seed=seed,
        available_gyrase=available_gyrase,
    )

    initialized = process.build_default_initialized_state(
        sigma=-0.06,
        replication_state="idle",
        available_gyrase=available_gyrase,
    )
    bound_sites = SparseTriplet.from_state(
        initialized["chromosome"]["complexBoundSites"],
        shape=process.chromosome_shape,
    )

    assert initialized["boundEnzymes"][process.gyrase_wid] == pytest.approx(float(expected_bound))
    assert initialized["boundEnzymes"][process.topoiv_wid] == pytest.approx(0.0)
    assert initialized["boundEnzymes"][process.topoi_wid] == pytest.approx(0.0)
    assert initialized["free_gyrase_count"] == pytest.approx(available_gyrase - expected_bound)
    assert bound_sites.positions.tolist() == sorted(expected_positions)
    assert bound_sites.strands.tolist() == [0] * len(expected_positions)


def test_chassis_initialization_seeds_bound_gyrase_from_default_path() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    process = composite["processes"]["karr_dna_supercoiling"]
    bound_state = composite["state"]["boundEnzymes"]
    bound_count = float(bound_state[process.gyrase_wid])
    free_count = float(composite["state"]["complex"]["counts"][process.gyrase_wid])
    total_gyrase = free_count + bound_count

    expected_process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "time_step": 1.0,
        }
    )
    expected = expected_process.build_default_initialized_state(
        replication_state="idle",
        available_gyrase=total_gyrase,
    )
    expected_sites = SparseTriplet.from_state(
        expected["chromosome"]["complexBoundSites"],
        shape=process.chromosome_shape,
    )
    actual_sites = SparseTriplet.from_state(
        composite["state"]["chromosome"]["complexBoundSites"],
        shape=process.chromosome_shape,
    )

    assert bound_count == pytest.approx(float(expected["boundEnzymes"][process.gyrase_wid]))
    assert np.array_equal(actual_sites.positions, expected_sites.positions)
    assert np.array_equal(actual_sites.strands, expected_sites.strands)
    assert np.array_equal(actual_sites.values, expected_sites.values)
    assert free_count == pytest.approx(float(expected["free_gyrase_count"]))


def test_one_tick_gyrase_sign_updates_sparse_linking_numbers() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 3,
            "gyrase_activity_rate": 4.0,
            "topoiv_activity_rate": 0.0,
            "topoi_activity_rate": 0.0,
            "reference_gyrase_count": 1.0,
            "reference_topoiv_count": 1.0,
            "chromosome_length_bp": 10_500.0,
        }
    )
    state = _base_state(
        process,
        sigma=-0.01,
        atp=1_000.0,
        gyrase_count=20.0,
        topoiv_count=0.0,
        topoi_count=0.0,
    )
    before = SparseTriplet.from_state(
        state["chromosome"]["linkingNumbers"], shape=process.chromosome_shape
    )
    update = process.next_update(1.0, state)
    after = SparseTriplet.from_state(
        update["chromosome"]["linkingNumbers"], shape=process.chromosome_shape
    )

    assert int(after.values.sum()) < int(before.values.sum())
    assert float(update["chromosome"]["supercoil_density"]) < float(
        state["chromosome"]["supercoil_density"]
    )


def test_next_update_does_not_clip_preexisting_out_of_range_sigma() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 21,
        }
    )
    state = _base_state(
        process,
        sigma=-1.0,
        atp=10_000.0,
        gyrase_count=0.0,
        topoiv_count=0.0,
        topoi_count=0.0,
    )

    before_linking = deepcopy(state["chromosome"]["linkingNumbers"])
    update = process.next_update(1.0, state)
    after_linking = SparseTriplet.from_state(
        update["chromosome"]["linkingNumbers"],
        shape=process.chromosome_shape,
    )
    before_triplet = SparseTriplet.from_state(before_linking, shape=process.chromosome_shape)

    assert np.array_equal(after_linking.positions, before_triplet.positions)
    assert np.array_equal(after_linking.strands, before_triplet.strands)
    assert np.array_equal(after_linking.values, before_triplet.values)


def test_topoiv_release_branch_preserves_protected_sites() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 7,
        }
    )
    state = _base_state(
        process,
        sigma=-0.06,
        atp=10_000.0,
        gyrase_count=0.0,
        topoiv_count=0.0,
        topoi_count=0.0,
    )
    state["chromosome"]["complexBoundSites"] = _bound_site_triplet(
        process,
        process.topoiv_wid,
        positions=[5, 205],
        strands=[0, 0],
    ).to_state()

    store = process._resolve_chromosome_store(state["chromosome"])  # noqa: SLF001
    store_next, released = process._release_bound_enzyme_from_chromosome(  # noqa: SLF001
        store=store,
        enzyme_idx=process.enzyme_wids.index(process.topoiv_wid),
        release_rate=float("inf"),
        dt=1.0,
        protected_regions=[(0, 0, 100)],
    )
    topoiv_sites = store_next.get_field("complexBoundSites")

    assert released == pytest.approx(1.0)
    assert topoiv_sites.positions.tolist() == [5]
    assert topoiv_sites.strands.tolist() == [0]


def test_gyrase_release_branch_uses_process_rng_per_bound_site() -> None:
    seed = 11
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": seed,
        }
    )
    state = _base_state(
        process,
        sigma=-0.06,
        atp=10_000.0,
        gyrase_count=0.0,
        topoiv_count=0.0,
        topoi_count=0.0,
    )
    positions = [1, 10, 20, 30]
    state["chromosome"]["complexBoundSites"] = _bound_site_triplet(
        process,
        process.gyrase_wid,
        positions=positions,
        strands=[0, 0, 0, 0],
    ).to_state()

    expected_keep: list[int] = []
    expected_rng = np.random.default_rng(seed)
    for position, release_draw in zip(positions, expected_rng.random(len(positions)), strict=True):
        if not bool(release_draw < 0.5):
            expected_keep.append(position)

    store = process._resolve_chromosome_store(state["chromosome"])  # noqa: SLF001
    store_next, released = process._release_bound_enzyme_from_chromosome(  # noqa: SLF001
        store=store,
        enzyme_idx=process.enzyme_wids.index(process.gyrase_wid),
        release_rate=0.5,
        dt=1.0,
        protected_regions=[],
    )
    gyrase_sites = store_next.get_field("complexBoundSites")

    assert released == pytest.approx(float(len(positions) - len(expected_keep)))
    assert gyrase_sites.positions.tolist() == expected_keep
    assert gyrase_sites.strands.tolist() == [0] * len(expected_keep)


def test_topoi_transient_binding_single_full_length_uses_current_free_space() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 17,
        }
    )
    state = _base_state(
        process,
        sigma=-0.12,
        atp=10_000.0,
        gyrase_count=0.0,
        topoiv_count=0.0,
        topoi_count=4.0,
    )
    state["chromosome"]["monomerBoundSites"] = _bound_site_triplet(
        process,
        process.topoi_wid,
        positions=[10],
        strands=[0],
    ).to_state()
    state["chromosome"]["complexBoundSites"] = _bound_site_triplet(
        process,
        process.gyrase_wid,
        positions=[100],
        strands=[0],
    ).to_state()
    state["chromosome"]["damagedBases"] = SparseTriplet(
        positions=np.asarray([200], dtype=np.int64),
        strands=np.asarray([0], dtype=np.int64),
        values=np.asarray([1], dtype=np.int64),
        shape=process.chromosome_shape,
    ).to_state()

    store = process._resolve_chromosome_store(state["chromosome"])  # noqa: SLF001
    positive_regions = process._positive_ds_regions(store.get_field("polymerizedRegions"))  # noqa: SLF001
    transient = process._calculate_transient_binding(  # noqa: SLF001
        store=store,
        enzyme_idx=process.topoi_idx,
        positive_regions=positive_regions,
        legal_mask=np.asarray([True], dtype=bool),
        available_count=4.0,
    )

    expected_space = (
        process.chromosome_length
        - process._enzyme_footprint(process.topoi_idx)  # noqa: SLF001
        - process._enzyme_footprint(process.gyrase_idx)  # noqa: SLF001
        - 1
    )
    expected = min(4.0, expected_space / float(process._enzyme_footprint(process.topoi_idx)))  # noqa: SLF001
    assert transient.tolist() == pytest.approx([expected])


def test_topoi_transient_binding_two_full_length_regions_uses_half_up_half_down_split() -> None:
    seed = 23
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": seed,
        }
    )
    state = _base_state(
        process,
        sigma=-0.12,
        atp=10_000.0,
        gyrase_count=0.0,
        topoiv_count=0.0,
        topoi_count=3.0,
    )
    positive_regions = [
        (0, 0, process.chromosome_length),
        (0, 2, process.chromosome_length),
    ]
    state["chromosome"]["polymerizedRegions"] = _duplex_region_triplet(
        process,
        positive_regions,
        value_mode="polymerized",
    ).to_state()
    state["chromosome"]["linkingNumbers"] = _duplex_region_triplet(
        process,
        positive_regions,
        value_mode="linking",
        sigma=-0.12,
    ).to_state()

    store = process._resolve_chromosome_store(state["chromosome"])  # noqa: SLF001
    transient = process._calculate_transient_binding(  # noqa: SLF001
        store=store,
        enzyme_idx=process.topoi_idx,
        positive_regions=positive_regions,
        legal_mask=np.asarray([True, True], dtype=bool),
        available_count=3.0,
    )

    expected_rng = np.random.default_rng(seed)
    if bool(expected_rng.random() < 0.5):
        expected = [2.0, 1.0]
    else:
        expected = [1.0, 2.0]
    assert transient.tolist() == pytest.approx(expected)


def test_topoi_transient_binding_general_regions_respects_region_space_weights() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 29,
        }
    )
    state = _base_state(
        process,
        sigma=-0.12,
        atp=10_000.0,
        gyrase_count=0.0,
        topoiv_count=0.0,
        topoi_count=3.0,
    )
    positive_regions = [
        (0, 0, 120),
        (300, 0, 80),
    ]
    state["chromosome"]["polymerizedRegions"] = _duplex_region_triplet(
        process,
        positive_regions,
        value_mode="polymerized",
    ).to_state()
    state["chromosome"]["linkingNumbers"] = _duplex_region_triplet(
        process,
        positive_regions,
        value_mode="linking",
        sigma=-0.12,
    ).to_state()
    state["chromosome"]["monomerBoundSites"] = _bound_site_triplet(
        process,
        process.topoi_wid,
        positions=[10],
        strands=[0],
    ).to_state()
    state["chromosome"]["complexBoundSites"] = _bound_site_triplet(
        process,
        process.gyrase_wid,
        positions=[320],
        strands=[0],
    ).to_state()
    state["chromosome"]["damagedBases"] = SparseTriplet(
        positions=np.asarray([330], dtype=np.int64),
        strands=np.asarray([0], dtype=np.int64),
        values=np.asarray([1], dtype=np.int64),
        shape=process.chromosome_shape,
    ).to_state()

    store = process._resolve_chromosome_store(state["chromosome"])  # noqa: SLF001
    transient = process._calculate_transient_binding(  # noqa: SLF001
        store=store,
        enzyme_idx=process.topoi_idx,
        positive_regions=positive_regions,
        legal_mask=np.asarray([True, True], dtype=bool),
        available_count=3.0,
    )

    footprint = float(process._enzyme_footprint(process.topoi_idx))  # noqa: SLF001
    gyrase_global_idx = int(process.enzyme_global_indices[process.gyrase_idx])
    matlab_complex_space = float(process.all_monomer_dna_footprints[gyrase_global_idx - 1])
    accessible_space_b = process._accessible_space_in_region(  # noqa: SLF001
        store=store,
        start=300,
        strand=0,
        length=80,
    )
    space_a = 120.0 - footprint
    space_b = 80.0 - matlab_complex_space - 1.0
    total_space = space_a + space_b
    expected = [
        min(3.0, total_space / footprint) * space_a / total_space,
        min(3.0, total_space / footprint) * space_b / total_space,
    ]
    assert accessible_space_b == pytest.approx(space_b)
    assert transient.tolist() == pytest.approx(expected)


def test_stable_binding_sampler_splits_accessible_region_without_overlap() -> None:
    seed = 31
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": seed,
        }
    )
    footprint = process._enzyme_footprint(process.gyrase_idx)  # noqa: SLF001
    positive_regions = [(0, 0, 4 * footprint + 10)]
    store = process._resolve_chromosome_store(_base_state(process, sigma=0.12)["chromosome"])  # noqa: SLF001

    store_next, binding_result = process._bind_protein_to_chromosome_stochastically(  # noqa: SLF001
        store=store,
        enzyme_idx=process.gyrase_idx,
        available_count=2.0,
        positive_regions=positive_regions,
    )
    bound_sites = store_next.get_field("complexBoundSites")
    expected_positions = _simulate_stochastic_binding_positions(
        seed=seed,
        footprint=footprint,
        available_count=2,
        regions=positive_regions,
    )

    assert binding_result.n_bound == 2
    assert bound_sites.positions.tolist() == expected_positions
    assert bound_sites.strands.tolist() == [0, 0]
    assert abs(bound_sites.positions[0] - bound_sites.positions[1]) >= footprint


def test_releasable_proteins_classify_bound_monomer_and_complex_sites() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 37,
        }
    )
    releasable_monomer = int(process.enzyme_global_indices[process.topoi_idx])
    releasable_complex = int(process.enzyme_global_indices[process.gyrase_idx])
    _install_releasable_rules(
        process,
        binding_enzyme_idx=process.topoi_idx,
        releasable_monomers=(releasable_monomer,),
        releasable_complexes=(releasable_complex,),
    )

    monomers, complexes = process._releasable_protein_indices(  # noqa: SLF001
        binding_monomers=(releasable_monomer,),
    )

    assert monomers.tolist() == [releasable_monomer]
    assert complexes.tolist() == [releasable_complex]


def test_binding_blocked_regions_excludes_releasable_sites_and_keeps_nonreleasable_sites() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 41,
        }
    )
    releasable_monomer = int(process.enzyme_global_indices[process.topoi_idx])
    releasable_complex = int(process.enzyme_global_indices[process.gyrase_idx])
    blocking_monomer = _first_nonzero_index(
        process.all_monomer_dna_footprints,
        exclude=releasable_monomer,
    )
    blocking_complex = _first_nonzero_index(
        process.all_complex_dna_footprints,
        exclude=releasable_complex,
    )
    _install_releasable_rules(
        process,
        binding_enzyme_idx=process.topoi_idx,
        releasable_monomers=(releasable_monomer,),
        releasable_complexes=(releasable_complex,),
    )
    store = process._resolve_chromosome_store(_base_state(process, sigma=-0.12)["chromosome"])  # noqa: SLF001
    store.set_field(  # noqa: SLF001
        "monomerBoundSites",
        SparseTriplet(
            positions=np.asarray([10, 60], dtype=np.int64),
            strands=np.asarray([0, 0], dtype=np.int64),
            values=np.asarray([releasable_monomer, blocking_monomer], dtype=np.int64),
            shape=process.chromosome_shape,
        ),
    )
    store.set_field(  # noqa: SLF001
        "complexBoundSites",
        SparseTriplet(
            positions=np.asarray([120, 180], dtype=np.int64),
            strands=np.asarray([0, 0], dtype=np.int64),
            values=np.asarray([releasable_complex, blocking_complex], dtype=np.int64),
            shape=process.chromosome_shape,
        ),
    )

    blocked = process._binding_blocked_regions(store=store, enzyme_idx=process.topoi_idx)  # noqa: SLF001
    expected = [
        (
            60,
            60 + int(process.all_monomer_dna_footprints[blocking_monomer - 1]),
        ),
        (
            180,
            180 + int(process.all_complex_dna_footprints[blocking_complex - 1]),
        ),
    ]

    assert blocked == {0: sorted(expected)}


def test_stable_binding_sampler_respects_existing_blocked_footprints() -> None:
    seed = 37
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": seed,
        }
    )
    footprint = process._enzyme_footprint(process.topoiv_idx)  # noqa: SLF001
    blocked_footprint = process._enzyme_footprint(process.gyrase_idx)  # noqa: SLF001
    positive_regions = [(0, 0, 5 * footprint + 20)]
    store = process._resolve_chromosome_store(_base_state(process, sigma=0.12)["chromosome"])  # noqa: SLF001
    blocked_start = footprint + 5
    store.set_field(  # noqa: SLF001
        "complexBoundSites",
        _bound_site_triplet(
            process,
            process.gyrase_wid,
            positions=[blocked_start],
            strands=[0],
        ),
    )

    accessible_regions = [
        (0, 0, blocked_start),
        (
            blocked_start + blocked_footprint,
            0,
            positive_regions[0][2] - blocked_start - blocked_footprint,
        ),
    ]
    store_next, binding_result = process._bind_protein_to_chromosome_stochastically(  # noqa: SLF001
        store=store,
        enzyme_idx=process.topoiv_idx,
        available_count=1.0,
        positive_regions=positive_regions,
    )
    bound_sites = store_next.get_field("complexBoundSites")
    expected_positions = _simulate_stochastic_binding_positions(
        seed=seed,
        footprint=footprint,
        available_count=1,
        regions=accessible_regions,
    )

    assert binding_result.n_bound == 1
    assert bound_sites.positions.tolist() == sorted([blocked_start, expected_positions[0]])
    assert bound_sites.strands.tolist() == [0, 0]
    assert not (
        expected_positions[0] < blocked_start + blocked_footprint
        and expected_positions[0] + footprint > blocked_start
    )


def test_accessible_binding_regions_merge_overlapping_nonreleasable_footprints() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 43,
        }
    )
    blocker_idx = int(process.enzyme_global_indices[process.gyrase_idx])
    blocker_footprint = int(process.all_complex_dna_footprints[blocker_idx - 1])
    _install_releasable_rules(
        process,
        binding_enzyme_idx=process.topoiv_idx,
        releasable_complexes=(),
    )
    positive_regions = [(0, 0, 3 * blocker_footprint)]
    second_start = blocker_footprint // 2
    store = process._resolve_chromosome_store(_base_state(process, sigma=0.12)["chromosome"])  # noqa: SLF001
    store.set_field(  # noqa: SLF001
        "complexBoundSites",
        SparseTriplet(
            positions=np.asarray([0, second_start], dtype=np.int64),
            strands=np.asarray([0, 0], dtype=np.int64),
            values=np.asarray([blocker_idx, blocker_idx], dtype=np.int64),
            shape=process.chromosome_shape,
        ),
    )

    accessible = process._accessible_binding_regions(  # noqa: SLF001
        store=store,
        enzyme_idx=process.topoiv_idx,
        positive_regions=positive_regions,
    )

    assert accessible == [
        ((second_start + blocker_footprint), 0, 2 * blocker_footprint - second_start)
    ]


def test_releasable_blocker_is_released_across_strands_and_new_topoiv_binding_blocks_second_step() -> (
    None
):
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 47,
        }
    )
    candidate_global_idx = int(process.enzyme_global_indices[process.topoiv_idx])
    blocker_idx = _first_nonzero_index(
        process.all_complex_dna_footprints,
        exclude=candidate_global_idx,
        min_value=process._enzyme_footprint(process.topoiv_idx),  # noqa: SLF001
    )
    _install_releasable_rules(
        process,
        binding_enzyme_idx=process.topoiv_idx,
        releasable_complexes=(blocker_idx,),
    )
    footprint = process._enzyme_footprint(process.topoiv_idx)  # noqa: SLF001
    positive_regions = [(0, 0, footprint)]
    store = process._resolve_chromosome_store(_base_state(process, sigma=0.12)["chromosome"])  # noqa: SLF001
    store.set_field(  # noqa: SLF001
        "complexBoundSites",
        SparseTriplet(
            positions=np.asarray([0], dtype=np.int64),
            strands=np.asarray([1], dtype=np.int64),
            values=np.asarray([blocker_idx], dtype=np.int64),
            shape=process.chromosome_shape,
        ),
    )

    store_after_first, binding_first = process._bind_protein_to_chromosome_stochastically(  # noqa: SLF001
        store=store,
        enzyme_idx=process.topoiv_idx,
        available_count=1.0,
        positive_regions=positive_regions,
    )
    first_bound_sites = store_after_first.get_field("complexBoundSites")

    assert binding_first.n_bound == 1
    assert first_bound_sites.positions.tolist() == [0]
    assert first_bound_sites.strands.tolist() == [0]
    assert first_bound_sites.values.tolist() == [candidate_global_idx]

    store_after_second, binding_second = process._bind_protein_to_chromosome_stochastically(  # noqa: SLF001
        store=store_after_first,
        enzyme_idx=process.topoiv_idx,
        available_count=1.0,
        positive_regions=positive_regions,
    )
    second_bound_sites = store_after_second.get_field("complexBoundSites")

    assert binding_second.n_bound == 0
    assert second_bound_sites.positions.tolist() == [0]
    assert second_bound_sites.strands.tolist() == [0]
    assert second_bound_sites.values.tolist() == [candidate_global_idx]


def test_stable_binding_overwrites_releasable_same_anchor_in_sparse_store() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 53,
        }
    )
    candidate_global_idx = int(process.enzyme_global_indices[process.topoiv_idx])
    blocker_idx = int(process._stable_binding_external_complex_indices[0])  # noqa: SLF001
    _install_releasable_rules(
        process,
        binding_enzyme_idx=process.topoiv_idx,
        releasable_complexes=(blocker_idx,),
    )
    footprint = process._enzyme_footprint(process.topoiv_idx)  # noqa: SLF001
    positive_regions = [(25, 0, footprint)]
    store = process._resolve_chromosome_store(_base_state(process, sigma=0.12)["chromosome"])  # noqa: SLF001
    store.set_field(  # noqa: SLF001
        "complexBoundSites",
        SparseTriplet(
            positions=np.asarray([25], dtype=np.int64),
            strands=np.asarray([0], dtype=np.int64),
            values=np.asarray([blocker_idx], dtype=np.int64),
            shape=process.chromosome_shape,
        ),
    )

    store_next, binding_result = process._bind_protein_to_chromosome_stochastically(  # noqa: SLF001
        store=store,
        enzyme_idx=process.topoiv_idx,
        available_count=1.0,
        positive_regions=positive_regions,
    )
    bound_sites = store_next.get_field("complexBoundSites")

    assert binding_result.n_bound == 1
    assert binding_result.released_complexes.tolist() == [0, -1]
    assert [
        (effect.molecule_kind, effect.global_index, effect.mature_delta, effect.bound_delta)
        for effect in binding_result.side_effects
    ] == [("complex", blocker_idx, 1, -1)]
    assert bound_sites.positions.tolist() == [25]
    assert bound_sites.strands.tolist() == [0]
    assert bound_sites.values.tolist() == [candidate_global_idx]


def test_validate_sampled_stable_binding_sites_rejects_start_outside_candidate_window() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 67,
        }
    )
    footprint = process._enzyme_footprint(process.topoiv_idx)  # noqa: SLF001

    with pytest.raises(ValueError, match="outside the source candidate space"):
        process._validate_sampled_stable_binding_sites(  # noqa: SLF001
            accessible_regions=[(25, 0, footprint)],
            positions=[26],
            strands=[0],
            footprint=footprint,
        )


def test_validate_sampled_stable_binding_sites_rejects_overlap() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 71,
        }
    )
    footprint = process._enzyme_footprint(process.topoiv_idx)  # noqa: SLF001

    with pytest.raises(ValueError, match="overlapping source-invalid sites"):
        process._validate_sampled_stable_binding_sites(  # noqa: SLF001
            accessible_regions=[(0, 0, 3 * footprint)],
            positions=[0, footprint - 1],
            strands=[0, 0],
            footprint=footprint,
        )


def test_hidden_double_stranded_regions_and_damaged_sites_block_stable_binding() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 73,
        }
    )
    footprint = process._enzyme_footprint(process.topoiv_idx)  # noqa: SLF001
    region_start = 100
    store = process._resolve_chromosome_store(_base_state(process, sigma=0.12)["chromosome"])  # noqa: SLF001

    state = store.to_state()
    state[CHROMOSOME_HIDDEN_STATE_KEY] = {
        "doubleStrandedRegions": {
            "positions": np.asarray([region_start, region_start], dtype=np.int64),
            "strands": np.asarray([0, 1], dtype=np.int8),
            "values": np.asarray([footprint, footprint], dtype=np.int32),
            "shape": process.chromosome_shape,
        },
        "damagedSites": {
            "positions": np.asarray([region_start], dtype=np.int64),
            "strands": np.asarray([0], dtype=np.int8),
            "values": np.asarray([1], dtype=np.int32),
            "shape": process.chromosome_shape,
        },
    }
    hidden_store = process._resolve_chromosome_store(state)  # noqa: SLF001
    positive_regions = process._positive_regions_from_store(  # noqa: SLF001
        store=hidden_store,
        polymerized=hidden_store.get_field("polymerizedRegions"),
    )

    assert positive_regions == [(region_start, 0, footprint)]
    assert process._accessible_binding_regions(  # noqa: SLF001
        store=hidden_store,
        enzyme_idx=process.topoiv_idx,
        positive_regions=positive_regions,
    ) == [(region_start + 1, 0, footprint - 1)]

    store_next, binding_result = process._bind_protein_to_chromosome_stochastically(  # noqa: SLF001
        store=hidden_store,
        enzyme_idx=process.topoiv_idx,
        available_count=1.0,
        positive_regions=positive_regions,
    )

    assert binding_result.n_bound == 0
    assert store_next.get_field("complexBoundSites").positions.size == 0


def test_next_update_stably_binds_legal_gyrase_and_updates_counts() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 41,
        }
    )
    state = _base_state(
        process,
        sigma=0.12,
        atp=10_000.0,
        gyrase_count=1.0,
        topoiv_count=0.0,
        topoi_count=0.0,
    )
    state["enzymes"] = {
        process.gyrase_wid: 1.0,
        process.topoiv_wid: 0.0,
        process.topoi_wid: 0.0,
    }

    update = process.next_update(1.0, state)
    bound_delta = float(update.get("boundEnzymes", {}).get(process.gyrase_wid, 0.0))
    free_delta = float(update.get("enzymes", {}).get(process.gyrase_wid, 0.0))
    bound_sites = SparseTriplet.from_state(
        update["chromosome"]["complexBoundSites"],
        shape=process.chromosome_shape,
    )

    assert bound_delta == pytest.approx(1.0)
    assert free_delta == pytest.approx(-1.0)
    assert bound_sites.positions.size == 1
    assert bound_sites.strands.tolist() == [0]


def test_next_update_stable_binding_applies_external_complex_side_effects() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 59,
            "gyrase_activity_rate": 0.0,
            "topoiv_activity_rate": 0.0,
            "topoi_activity_rate": 0.0,
        }
    )
    blocker_idx = int(process._stable_binding_external_complex_indices[0])  # noqa: SLF001
    blocker_wid = process._stable_binding_external_complex_wids[0]  # noqa: SLF001
    footprint = process._enzyme_footprint(process.topoiv_idx)  # noqa: SLF001
    _install_releasable_rules(
        process,
        binding_enzyme_idx=process.topoiv_idx,
        releasable_complexes=(blocker_idx,),
    )
    state = _base_state(
        process,
        sigma=0.12,
        atp=10_000.0,
        gyrase_count=0.0,
        topoiv_count=1.0,
        topoi_count=0.0,
    )
    state["enzymes"] = {
        process.gyrase_wid: 0.0,
        process.topoiv_wid: 1.0,
        process.topoi_wid: 0.0,
    }
    state["complex"]["counts"][blocker_wid] = 0.0
    state["chromosome"]["polymerizedRegions"] = _duplex_region_triplet(
        process,
        [(25, 0, footprint)],
        value_mode="polymerized",
    ).to_state()
    state["chromosome"]["linkingNumbers"] = _duplex_region_triplet(
        process,
        [(25, 0, footprint)],
        value_mode="linking",
        sigma=0.12,
    ).to_state()
    state["chromosome"]["complexBoundSites"] = SparseTriplet(
        positions=np.asarray([25], dtype=np.int64),
        strands=np.asarray([1], dtype=np.int64),
        values=np.asarray([blocker_idx], dtype=np.int64),
        shape=process.chromosome_shape,
    ).to_state()

    update = process.next_update(1.0, state)
    bound_sites = SparseTriplet.from_state(
        update["chromosome"]["complexBoundSites"],
        shape=process.chromosome_shape,
    )

    assert float(update["boundEnzymes"][process.topoiv_wid]) == pytest.approx(1.0)
    assert float(update["enzymes"][process.topoiv_wid]) == pytest.approx(-1.0)
    assert float(update["complex"]["counts"][blocker_wid]) == pytest.approx(1.0)
    assert bound_sites.to_regions() == [
        (25, 0, int(process.enzyme_global_indices[process.topoiv_idx]))
    ]


def test_next_update_stable_binding_side_effect_fires_once_across_ticks() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 61,
            "gyrase_activity_rate": 0.0,
            "topoiv_activity_rate": 0.0,
            "topoi_activity_rate": 0.0,
        }
    )
    blocker_idx = int(process._stable_binding_external_complex_indices[0])  # noqa: SLF001
    blocker_wid = process._stable_binding_external_complex_wids[0]  # noqa: SLF001
    footprint = process._enzyme_footprint(process.topoiv_idx)  # noqa: SLF001
    _install_releasable_rules(
        process,
        binding_enzyme_idx=process.topoiv_idx,
        releasable_complexes=(blocker_idx,),
    )
    state = _base_state(
        process,
        sigma=0.12,
        atp=10_000.0,
        gyrase_count=0.0,
        topoiv_count=1.0,
        topoi_count=0.0,
    )
    state["enzymes"] = {
        process.gyrase_wid: 0.0,
        process.topoiv_wid: 1.0,
        process.topoi_wid: 0.0,
    }
    state["complex"]["counts"][blocker_wid] = 0.0
    state["chromosome"]["polymerizedRegions"] = _duplex_region_triplet(
        process,
        [(25, 0, footprint)],
        value_mode="polymerized",
    ).to_state()
    state["chromosome"]["linkingNumbers"] = _duplex_region_triplet(
        process,
        [(25, 0, footprint)],
        value_mode="linking",
        sigma=0.12,
    ).to_state()
    state["chromosome"]["complexBoundSites"] = SparseTriplet(
        positions=np.asarray([25], dtype=np.int64),
        strands=np.asarray([1], dtype=np.int64),
        values=np.asarray([blocker_idx], dtype=np.int64),
        shape=process.chromosome_shape,
    ).to_state()

    update1 = _advance_tick(process, state)
    update2 = _advance_tick(process, state)
    bound_sites = SparseTriplet.from_state(
        state["chromosome"]["complexBoundSites"],
        shape=process.chromosome_shape,
    )

    assert float(update1["complex"]["counts"][blocker_wid]) == pytest.approx(1.0)
    assert float(
        update2.get("complex", {}).get("counts", {}).get(blocker_wid, 0.0)
    ) == pytest.approx(0.0)
    assert float(state["complex"]["counts"][blocker_wid]) == pytest.approx(1.0)
    assert float(state["boundEnzymes"][process.topoiv_wid]) == pytest.approx(1.0)
    assert float(state["enzymes"][process.topoiv_wid]) == pytest.approx(0.0)
    assert bound_sites.to_regions() == [
        (25, 0, int(process.enzyme_global_indices[process.topoiv_idx]))
    ]


def test_activity_loop_uses_bound_topoiv_sites_per_region_instead_of_length_weights() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 43,
            "gyrase_activity_rate": 0.0,
            "topoiv_activity_rate": 1.0,
            "topoi_activity_rate": 0.0,
        }
    )
    state = _base_state(
        process,
        sigma=0.12,
        atp=10_000.0,
        gyrase_count=0.0,
        topoiv_count=0.0,
        topoi_count=0.0,
    )
    positive_regions = [
        (0, 0, 1000),
        (2000, 0, 100),
    ]
    state["chromosome"]["polymerizedRegions"] = _duplex_region_triplet(
        process,
        positive_regions,
        value_mode="polymerized",
    ).to_state()
    state["chromosome"]["linkingNumbers"] = _duplex_region_triplet(
        process,
        positive_regions,
        value_mode="linking",
        sigma=0.12,
    ).to_state()
    state["chromosome"]["complexBoundSites"] = _bound_site_triplet(
        process,
        process.topoiv_wid,
        positions=[2000],
        strands=[0],
    ).to_state()
    state["boundEnzymes"] = {process.topoiv_wid: 1.0}

    before_linking = SparseTriplet.from_state(
        state["chromosome"]["linkingNumbers"],
        shape=process.chromosome_shape,
    )
    update = process.next_update(1.0, state)
    after_linking = SparseTriplet.from_state(
        update["chromosome"]["linkingNumbers"],
        shape=process.chromosome_shape,
    )
    before_values = process._align_positive_region_values(  # noqa: SLF001
        positive_regions=positive_regions,
        linking_numbers=before_linking,
        fallback_sigma=process.equilibrium_sigma,
    )
    after_values = process._align_positive_region_values(  # noqa: SLF001
        positive_regions=positive_regions,
        linking_numbers=after_linking,
        fallback_sigma=process.equilibrium_sigma,
    )

    assert int(after_values[0]) == int(before_values[0])
    assert int(after_values[1]) == int(
        before_values[1] + int(process.parameters["topoiv_link_delta"])
    )


def test_align_positive_region_values_uses_ledger_sigma_not_global_fallback() -> None:
    """Regression + inversion pin for the seed46/tick24 root-cause fix.

    _positive_region_sigmas_from_store (legality gating) already checks the
    superhelicalDensity input oracle FIRST for a per-region real sigma. Prior
    to this fix, _align_positive_region_values (the WRITEBACK baseline that
    activity deltas get added to) ignored that oracle entirely for regions
    with no explicit linkingNumbers entry, always falling back to a single
    global `equilibrium_sigma`-derived scalar -- letting OC treat the SAME
    region as simultaneously "far from relaxed" (real oracle sigma, gating
    legality) and "at the relaxed baseline" (global fallback, writeback),
    producing spurious activity real MATLAB never has. This pins that the
    writeback baseline now uses the SAME per-region sigma the legality gate
    uses, with an explicit inversion check proving the fix changes the
    computed baseline (not merely internal bookkeeping).
    """
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 53,
        }
    )
    positive_regions = [(0, 0, 411)]
    empty_linking = SparseTriplet(
        positions=np.zeros(0, dtype=np.int64),
        strands=np.zeros(0, dtype=np.int8),
        values=np.zeros(0, dtype=np.int32),
        shape=process.chromosome_shape,
    )
    chrom_state = process.build_default_chromosome_state(sigma=0.0, replication_state="idle")
    store = process._resolve_chromosome_store(chrom_state)  # noqa: SLF001
    # Real (nascent-region-like) sigma far from equilibrium -- deliberately
    # NOT equal to process.equilibrium_sigma, mirroring the seed46/tick24
    # finding (real MATLAB sigma ~= -0.9963 for a just-polymerized region).
    real_region_sigma = -0.9963429463604637
    assert real_region_sigma != pytest.approx(process.equilibrium_sigma)
    store.set_hidden_sparse_field(
        "superhelicalDensity",
        {
            "positions": np.asarray([0], dtype=np.int64),
            "strands": np.asarray([0], dtype=np.int64),
            "values": np.asarray([real_region_sigma], dtype=np.float64),
            "shape": process.chromosome_shape,
        },
    )

    sigma_values = process._positive_region_sigmas_from_store(  # noqa: SLF001
        store=store,
        positive_regions=positive_regions,
        linking_numbers=empty_linking,
        fallback_sigma=process.equilibrium_sigma,
    )
    assert float(sigma_values[0]) == pytest.approx(real_region_sigma, abs=1e-9)

    fixed_values = process._align_positive_region_values(  # noqa: SLF001
        positive_regions=positive_regions,
        linking_numbers=empty_linking,
        fallback_sigma=sigma_values,
    )
    relaxed = 411.0 / float(process.parameters["bp_per_turn"])
    expected = int(round(relaxed * (1.0 + real_region_sigma)))
    assert int(fixed_values[0]) == expected

    # Inversion: the OLD call pattern (global equilibrium_sigma fallback,
    # blind to the per-region oracle) gives a MEANINGFULLY DIFFERENT
    # baseline -- proving this is a real behavior change, not a no-op.
    old_style_values = process._align_positive_region_values(  # noqa: SLF001
        positive_regions=positive_regions,
        linking_numbers=empty_linking,
        fallback_sigma=process.equilibrium_sigma,
    )
    assert int(old_style_values[0]) != int(fixed_values[0])


def test_activity_loop_consumes_atp_inside_randomized_enzyme_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = 47
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": seed,
            "gyrase_activity_rate": 1.0,
            "topoiv_activity_rate": 1.0,
            "topoi_activity_rate": 0.0,
        }
    )
    state = _base_state(
        process,
        sigma=0.12,
        atp=float(process.gyrase_atp_cost),
        h2o=float(process.gyrase_atp_cost),
        gyrase_count=0.0,
        topoiv_count=0.0,
        topoi_count=0.0,
    )
    gyrase_global_idx = int(process.enzyme_global_indices[process.gyrase_idx])
    topoiv_global_idx = int(process.enzyme_global_indices[process.topoiv_idx])
    state["chromosome"]["complexBoundSites"] = SparseTriplet(
        positions=np.asarray([10, 120], dtype=np.int64),
        strands=np.asarray([0, 0], dtype=np.int64),
        values=np.asarray([gyrase_global_idx, topoiv_global_idx], dtype=np.int64),
        shape=process.chromosome_shape,
    ).to_state()

    monkeypatch.setattr(
        process,
        "_enzyme_activity_probability_for_sigma",
        lambda **_: 1.0,
    )

    store = process._resolve_chromosome_store(state["chromosome"])  # noqa: SLF001
    positive_regions = process._positive_ds_regions(store.get_field("polymerizedRegions"))  # noqa: SLF001
    events, atp_used = process._sample_activity_events_by_region(  # noqa: SLF001
        store=store,
        positive_regions=positive_regions,
        sigma_values=np.asarray([0.12], dtype=np.float64),
        legal=np.asarray([[True, True, False]], dtype=bool),
        topoi_transient=np.zeros(1, dtype=np.float64),
        available_atp=float(process.gyrase_atp_cost),
        available_h2o=float(process.gyrase_atp_cost),
        dt=1.0,
    )

    expected_order = np.random.default_rng(seed).permutation(len(process.enzyme_wids)).tolist()
    gyrase_first = expected_order.index(process.gyrase_idx) < expected_order.index(
        process.topoiv_idx
    )

    assert int(events[0, process.gyrase_idx]) == int(gyrase_first)
    assert int(events[0, process.topoiv_idx]) == int(not gyrase_first)
    assert int(events.sum()) == 1
    assert atp_used == pytest.approx(float(process.gyrase_atp_cost))


def test_low_atp_multi_tick_only_allows_first_bound_topoiv_event() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 53,
            "gyrase_activity_rate": 0.0,
            "topoiv_activity_rate": 1.0,
            "topoi_activity_rate": 0.0,
        }
    )
    atp_cost = float(process.topoiv_atp_cost)
    state = _base_state(
        process,
        sigma=0.12,
        atp=atp_cost,
        h2o=atp_cost,
        gyrase_count=0.0,
        topoiv_count=0.0,
        topoi_count=0.0,
    )
    state["chromosome"]["complexBoundSites"] = _bound_site_triplet(
        process,
        process.topoiv_wid,
        positions=[100],
        strands=[0],
    ).to_state()
    state["boundEnzymes"] = {
        process.gyrase_wid: 0.0,
        process.topoiv_wid: 1.0,
        process.topoi_wid: 0.0,
    }
    state["enzymes"] = {
        process.gyrase_wid: 0.0,
        process.topoiv_wid: 0.0,
        process.topoi_wid: 0.0,
    }

    before_linking = SparseTriplet.from_state(
        state["chromosome"]["linkingNumbers"],
        shape=process.chromosome_shape,
    )
    positive_regions = process._positive_ds_regions(  # noqa: SLF001
        SparseTriplet.from_state(
            state["chromosome"]["polymerizedRegions"], shape=process.chromosome_shape
        )
    )
    before_values = process._align_positive_region_values(  # noqa: SLF001
        positive_regions=positive_regions,
        linking_numbers=before_linking,
        fallback_sigma=process.equilibrium_sigma,
    )

    update1 = _advance_tick(process, state)
    update2 = _advance_tick(process, state)

    after_linking = SparseTriplet.from_state(
        state["chromosome"]["linkingNumbers"],
        shape=process.chromosome_shape,
    )
    after_values = process._align_positive_region_values(  # noqa: SLF001
        positive_regions=positive_regions,
        linking_numbers=after_linking,
        fallback_sigma=process.equilibrium_sigma,
    )

    assert float(update1.get("substrates", {}).get(process.atp_wid, 0.0)) == pytest.approx(
        -atp_cost
    )
    assert float(update2.get("substrates", {}).get(process.atp_wid, 0.0)) == pytest.approx(0.0)
    assert float(state["substrates"][process.atp_wid]) == pytest.approx(0.0)
    assert int(after_values[0]) == int(
        before_values[0] + int(process.parameters["topoiv_link_delta"])
    )


def test_allocation_contract_bounds_atp_use() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 1,
            "gyrase_activity_rate": 8.0,
            "topoiv_activity_rate": 8.0,
            "topoi_activity_rate": 0.0,
            "reference_gyrase_count": 1.0,
            "reference_topoiv_count": 1.0,
        }
    )
    state = _base_state(
        process,
        sigma=-0.02,
        atp=2.0,
        gyrase_count=30.0,
        topoiv_count=30.0,
        topoi_count=0.0,
    )
    state["substrates_allocated"][process.name][process.atp_wid] = 2.0
    state["substrates_allocated"][process.name][process.h2o_wid] = 2.0

    update = process.next_update(1.0, state)
    atp_delta = float(update.get("substrates", {}).get(process.atp_wid, 0.0))

    assert atp_delta >= -2.0
    assert atp_delta <= 0.0
    assert float(update["requests"][process.name][process.atp_wid]) >= 0.0


def test_replication_elongating_increases_gyrase_request() -> None:
    idle = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 9,
        }
    )
    elong = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 9,
        }
    )

    idle_state = _base_state(idle, sigma=-0.06, replication_state="idle")
    elong_state = _base_state(elong, sigma=-0.06, replication_state="elongating")

    idle_update = idle.next_update(1.0, idle_state)
    elong_update = elong.next_update(1.0, elong_state)

    idle_req = float(idle_update["requests"][idle.name][idle.atp_wid])
    elong_req = float(elong_update["requests"][elong.name][elong.atp_wid])
    assert elong_req >= idle_req


def test_100tick_steady_state_near_karr_sigma() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 11,
        }
    )
    state = _base_state(
        process,
        sigma=-0.06,
        atp=250_000.0,
        gyrase_count=3.0,
        topoiv_count=12.0,
        topoi_count=1.0,
        initialize_gyrase=True,
    )

    sigma_values = [float(state["chromosome"]["supercoil_density"])]
    for _ in range(100):
        _advance_tick(process, state)
        sigma_values.append(float(state["chromosome"]["supercoil_density"]))

    target = abs(float(process.equilibrium_sigma))
    mean_abs_sigma = sum(abs(value) for value in sigma_values[-50:]) / 50.0
    assert mean_abs_sigma == pytest.approx(target, rel=0.20)


def test_no_nan_or_negative_regressions() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 13,
        }
    )
    state = _base_state(
        process,
        sigma=-0.06,
        atp=100_000.0,
        replication_state="elongating",
        gyrase_count=8.0,
        topoiv_count=8.0,
        topoi_count=2.0,
    )

    for _ in range(120):
        _advance_tick(process, state)

    sigma = float(state["chromosome"]["supercoil_density"])
    assert math.isfinite(sigma)
    linking = SparseTriplet.from_state(
        state["chromosome"]["linkingNumbers"], shape=process.chromosome_shape
    )
    assert np.isfinite(linking.values.astype(float)).all()
    for wid, value in state["substrates"].items():
        assert math.isfinite(float(value))
        assert float(value) >= 0.0, f"negative substrate {wid}: {value}"


def test_matlab_exclude_regions_reproduces_real_matlab_excLens_end_indexing_bug() -> None:  # noqa: N802
    """Direct port test for `_matlab_exclude_regions` against the exact
    scenario that produced the Opus-flagged audit-boundary breach at
    seed=0, tick_zero_based=81 (STATUS_L22_DNAS_SEPT2.md): a fragment
    with one small, clearly-non-blocking nearby exclusion (49bp, well
    short of the fragment's own length), but where a SEPARATE, much
    larger exclusion (630bp) sorts last (globally, across all strands)
    in the call.

    Verified against live MATLAB
    (`scripts/matlab/l22_dnas_full_bind_activity_probe.m`'s
    `traced_testC`/hardcoded-literal cross-check): real MATLAB's
    `Chromosome.excludeRegions` returns EMPTY for this fragment --- not
    because the 630bp exclusion is anywhere near it, but because
    `Chromosome.m:2632`'s "does the matched exclusion reach the
    fragment's end?" check literally reads `excLens(end)` (the length of
    whichever exclusion sorts LAST in the whole call), not
    `excLens(excIdxs(end))` (the actual matched exclusion's own length).
    """
    from opencell.vivarium.karr_dna_supercoiling import _matlab_exclude_regions  # noqa: PLC0415

    # A fragment [39, 450) on strand 0 (matching the real seed 0, tick 81
    # topoIV case's relative geometry: the sole nearby exclusion starts
    # BEFORE the fragment and extends a little way into it), with:
    #   - one exclusion at [0, 49) that starts before the fragment and
    #     extends into it (real divergence-causing case: only 49bp, ends
    #     at 48, far short of reaching the fragment's own end at 449),
    #   - one unrelated, much larger exclusion on a DIFFERENT strand (2)
    #     that sorts last (highest position) across the whole call and
    #     is long enough that `excLens(end)` "reaching" the fragment's
    #     end (449) from the matched exclusion's start (0) would flip the
    #     branch: 0 + 630 - 1 = 629 >= 449.
    included = [(39, 0, 411)]
    excluded = [(0, 0, 49), (100_000, 2, 630)]

    result = _matlab_exclude_regions(included, excluded, chromosome_length=580_076)

    assert result == [], (
        "bug-compatible port must reproduce real MATLAB's empty result -- "
        f"got {result!r}"
    )

    # Inversion: a "textbook", per-fragment-local interval subtraction
    # (ignoring the unrelated strand-2 exclusion entirely, as any
    # correctness-first implementation would) gives a materially
    # DIFFERENT, non-empty answer -- proof this is a real, deliberate
    # bug-for-bug behavior change, not inert refactoring.
    naive_result = []
    seg_start, seg_end = 39, 450
    exc_start, exc_end = 0, 49
    if exc_start > seg_start:
        naive_result.append((seg_start, 0, exc_start - seg_start))
    if exc_end < seg_end:
        naive_result.append((exc_end, 0, seg_end - exc_end))
    assert naive_result == [(49, 0, 401)]
    assert naive_result != result


def test_matlab_join_split_regions_reproduces_real_matlab_origin_wrap_normalization() -> None:
    """Direct port test for `_matlab_join_split_regions` against Opus's
    exact hand example (0-based exclusions
    ``[(500, 0, 10), (580051, 0, 630)]`` on a 580076bp chromosome), the
    central fidelity blocker in the first audit-boundary-closure attempt:
    `Chromosome.joinSplitRegions`'s origin-wrap normalization
    (`Chromosome.m:2811-2817`) REWRITES the last exclusion's recorded
    length in place whenever a boundary-crossing exclusion coexists on
    the same pair-strand with one near the origin -- this was previously
    omitted (the prior port used the shared, plain adjacent-merge-only
    `_merge_linear_regions`, whose docstring incorrectly claimed the
    origin-wrap "does not occur for the exclusion lists this function is
    used with").

    Verified against live MATLAB, decisively, via a standalone,
    hardcoded-input probe
    (`scripts/matlab/l22_dnas_join_split_regions_originwrap_probe.m`,
    calling the real, unmodified `Chromosome.joinSplitRegions` and
    `Chromosome.excludeRegions` directly -- not inferred from the pooled
    projection tensor): real MATLAB's post-join lengths for this exact
    input are ``[510, 25]``, not the raw ``[10, 630]`` a plain merge
    would report, and the real `excludeRegions` output for a fragment at
    0-based ``[510, 604]`` (the exact range this normalization step
    determines the accessibility of) is FULLY ACCESSIBLE -- both
    confirmed byte-for-byte against this test's expected values.
    """
    from opencell.vivarium.karr_dna_supercoiling import _matlab_join_split_regions  # noqa: PLC0415

    chromosome_length = 580_076
    excluded = [(500, 0, 10), (580_051, 0, 630)]

    joined = _matlab_join_split_regions(excluded, chromosome_length=chromosome_length)

    assert joined == [(0, 0, 510), (580_051, 0, 25)], (
        "must reproduce real MATLAB's origin-wrap-normalized lengths "
        f"[510, 25] -- got {joined!r}"
    )

    # Boundary-condition pins (also live-MATLAB-verified via the same
    # probe): the wrap only fires when a second exclusion on the same
    # strand exists AND is close enough to the origin to satisfy
    # `ends(last)+1 >= starts(first)+L`. A single boundary-crossing
    # exclusion alone never triggers it (needs >=2 entries); at 0-based
    # position 605 the wrap fires (equality case); at 606 it does not.
    assert _matlab_join_split_regions(
        [(580_051, 0, 630)], chromosome_length=chromosome_length
    ) == [(580_051, 0, 630)]
    assert _matlab_join_split_regions(
        [(605, 0, 10), (580_051, 0, 630)], chromosome_length=chromosome_length
    ) == [(0, 0, 615), (580_051, 0, 25)]
    assert _matlab_join_split_regions(
        [(606, 0, 10), (580_051, 0, 630)], chromosome_length=chromosome_length
    ) == [(606, 0, 10), (580_051, 0, 630)]


def test_accessible_binding_regions_origin_wrap_boundary_crossing_footprint() -> None:
    """Genuine end-to-end inversion for the origin-wrap fidelity blocker:
    drives the REAL, unmodified `_binding_blocked_regions` and
    `_accessible_binding_regions` (not a hand-rolled substitute) with two
    real bound complexes -- one whose footprint genuinely extends past
    `chromosome_length` (gyrase, footprint 140, positioned 50bp from the
    chromosome's end so its footprint overshoots by 90bp), and one near
    the chromosome origin (topoiv, footprint 34) close enough to satisfy
    `Chromosome.joinSplitRegions`'s origin-wrap condition
    (`ends(last)+1 >= starts(first)+L`) -- and asserts on the real
    accessible-region OUTPUT for a fragment covering the specific 16bp
    gap this wrap determines (0-based ``[74, 89]``, live-MATLAB-verified
    via `probe_find_decisive_params.py`/
    `scripts/matlab/l22_dnas_join_split_regions_originwrap_probe.m`'s
    worked structure): the correct, origin-wrap-aware computation reports
    this gap FULLY ACCESSIBLE; a `_split_circular_region`-based
    pre-split (the prior, incorrect `_binding_blocked_regions` behavior,
    reverting root cause C) would instead report it BLOCKED, because
    splitting the boundary-crossing footprint before the join step
    changes what the join step's naive adjacency-merge combines it with,
    silently dropping the origin-wrap's length-shrinking rewrite.

    Because this test calls `_binding_blocked_regions`/
    `_accessible_binding_regions` directly (the real production code
    path, not a copy), reverting root cause C (restoring the
    `_split_circular_region` pre-split inside `_binding_blocked_regions`)
    would make THIS test's own primary assertion fail -- the inversion is
    not a separate, disconnected computation.
    """
    from opencell.vivarium.karr_dna_supercoiling import (  # noqa: PLC0415
        _matlab_exclude_regions,
        _split_circular_region,
    )

    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 79,
        }
    )
    chrom_len = process.chromosome_length
    far_footprint = process._enzyme_footprint(process.gyrase_idx)  # noqa: SLF001
    near_footprint = process._enzyme_footprint(process.topoiv_idx)  # noqa: SLF001
    far_global_idx = int(process.enzyme_global_indices[process.gyrase_idx])
    near_global_idx = int(process.enzyme_global_indices[process.topoiv_idx])

    far_start = chrom_len - 50  # footprint (140) extends 90bp past chrom_len
    near_start = 40  # close enough to the origin to satisfy the wrap condition

    _install_releasable_rules(
        process,
        binding_enzyme_idx=process.topoi_idx,
        releasable_complexes=(),
    )
    store = process._resolve_chromosome_store(_base_state(process, sigma=0.12)["chromosome"])  # noqa: SLF001
    store.set_field(  # noqa: SLF001
        "complexBoundSites",
        SparseTriplet(
            positions=np.asarray([far_start, near_start], dtype=np.int64),
            strands=np.asarray([0, 0], dtype=np.int64),
            values=np.asarray([far_global_idx, near_global_idx], dtype=np.int64),
            shape=process.chromosome_shape,
        ),
    )

    decisive_gap_start = near_start + near_footprint  # 74: where NEW leaves accessible
    decisive_gap_len = 16  # up to 90 (where OLD's merged block would have ended)

    accessible = process._accessible_binding_regions(  # noqa: SLF001
        store=store,
        enzyme_idx=process.topoi_idx,
        positive_regions=[(decisive_gap_start, 0, decisive_gap_len)],
    )

    assert accessible == [(decisive_gap_start, 0, decisive_gap_len)], (
        "the real _binding_blocked_regions/_accessible_binding_regions path must report "
        f"this gap fully accessible (matching live MATLAB); got {accessible!r}"
    )

    # Inversion: reconstruct what `_binding_blocked_regions` computed
    # BEFORE root cause C's fix (pre-splitting a boundary-crossing
    # footprint via `_split_circular_region`) and feed it through the
    # SAME `_matlab_exclude_regions` used above, to show explicitly why
    # reverting root cause C changes the answer for this exact input.
    far_split_pieces = _split_circular_region(far_start, far_footprint, chrom_len)
    old_style_excluded = [(near_start, 0, near_footprint)] + [
        (seg_start, 0, seg_end - seg_start + 1) for seg_start, seg_end in far_split_pieces
    ]
    old_style_result = _matlab_exclude_regions(
        [(decisive_gap_start, 0, decisive_gap_len)],
        old_style_excluded,
        chromosome_length=chrom_len,
    )
    assert old_style_result == [], (
        "pre-split (reverted root cause C) exclusion construction must incorrectly report "
        f"this same gap as fully blocked; got {old_style_result!r}"
    )
    assert old_style_result != accessible


def test_matlab_join_split_over_oric_regions_reproduces_real_matlab_wrap_join() -> None:
    """Direct port test for `_matlab_join_split_over_oric_regions`
    (`Chromosome.joinSplitOverOriCRegions`, `Chromosome.m:2767-2788`) --
    the second review's central fidelity blocker: real
    `Chromosome.excludeRegions` calls this at BOTH ends of its
    computation (`Chromosome.m:2606` on the included fragment list;
    again near `Chromosome.m:2674-2677` on the raw output fragment list,
    before the final position normalization), and a prior version of
    `_matlab_exclude_regions` omitted it entirely at both call sites,
    with a docstring claiming (falsely) that it was unreachable for this
    module's callers.

    Mandatory decisive cross-check (not inferred): real MATLAB's
    ``excludeRegions([1 1], 580076, [100 1; 580000 1], [50; 50])``
    returns exactly TWO accessible regions -- 1-based ``(150,
    len=579850)`` and ``(580050, len=126)`` -- not three, confirmed via
    a standalone, hardcoded-input probe
    (`scripts/matlab/l22_dnas_join_split_regions_originwrap_probe.m`'s
    ``opus_review2_full_chromosome_included`` case, calling the real,
    unmodified `Chromosome.excludeRegions` directly).
    """
    from opencell.vivarium.karr_dna_supercoiling import (  # noqa: PLC0415
        _matlab_exclude_regions,
        _matlab_join_split_over_oric_regions,
    )

    chromosome_length = 580_076

    # Direct port test for the join-over-oric helper itself: three
    # fragments where one starts at position 0 and another ends at
    # chromosome_length-1 on the SAME strand must be combined into one.
    joined = _matlab_join_split_over_oric_regions(
        [(0, 0, 99), (149, 0, 579_850), (580_049, 0, 27)],
        chromosome_length=chromosome_length,
    )
    assert joined == [(149, 0, 579_850), (580_049, 0, 126)], (
        f"must join the position-0 fragment into the chromosome_length-1-ending "
        f"fragment; got {joined!r}"
    )

    # Full excludeRegions cross-check (0-based translation of Opus's
    # exact hand example: 1-based included [1,580076], excluded [100,50]
    # and [580000,50] -> 0-based included [0,580076), excluded
    # [(99,0,50),(579999,0,50)]).
    included = [(0, 0, chromosome_length)]
    excluded = [(99, 0, 50), (579_999, 0, 50)]
    result = _matlab_exclude_regions(included, excluded, chromosome_length=chromosome_length)
    assert result == [(149, 0, 579_850), (580_049, 0, 126)], (
        "must reproduce real MATLAB's exact TWO-region output (not three) -- "
        f"got {result!r}"
    )


def test_accessible_binding_regions_join_split_over_oric_wrapped_fragment() -> None:
    """Genuine end-to-end inversion for the `joinSplitOverOriCRegions`
    fidelity blocker: drives the REAL, unmodified
    `_binding_blocked_regions`/`_accessible_binding_regions` with a
    SINGLE full-chromosome positive region (the shape a freshly
    initialized, unreplicated chromosome's sole `doubleStrandedRegions`
    entry actually has) and two real bound complexes positioned so
    neither individually overshoots `chromosome_length` (isolating this
    test from the separate `joinSplitRegions` origin-wrap already
    covered by `test_accessible_binding_regions_origin_wrap_boundary_
    crossing_footprint`): topoiv (footprint 34) near the origin, gyrase
    (footprint 140) positioned 150bp before the chromosome's end.

    Live-MATLAB-verified ground truth
    (`scripts/matlab/l22_dnas_join_split_regions_originwrap_probe.m`'s
    ``oric_join_real_footprints`` case, real footprints, real
    `excludeRegions` call): exactly TWO accessible regions, 0-based
    ``(134, len=579792)`` and ``(580066, len=110)`` -- the second being
    the SINGLE joined wrapped fragment (10bp before the origin + 100bp
    after it), not two separate unjoined fragments.
    """
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 83,
        }
    )
    chrom_len = process.chromosome_length
    near_footprint = process._enzyme_footprint(process.topoiv_idx)  # noqa: SLF001
    far_footprint = process._enzyme_footprint(process.gyrase_idx)  # noqa: SLF001
    near_global_idx = int(process.enzyme_global_indices[process.topoiv_idx])
    far_global_idx = int(process.enzyme_global_indices[process.gyrase_idx])

    near_start = 100
    far_start = chrom_len - 150

    _install_releasable_rules(
        process,
        binding_enzyme_idx=process.topoi_idx,
        releasable_complexes=(),
    )
    store = process._resolve_chromosome_store(_base_state(process, sigma=0.12)["chromosome"])  # noqa: SLF001
    store.set_field(  # noqa: SLF001
        "complexBoundSites",
        SparseTriplet(
            positions=np.asarray([near_start, far_start], dtype=np.int64),
            strands=np.asarray([0, 0], dtype=np.int64),
            values=np.asarray([near_global_idx, far_global_idx], dtype=np.int64),
            shape=process.chromosome_shape,
        ),
    )

    accessible = process._accessible_binding_regions(  # noqa: SLF001
        store=store,
        enzyme_idx=process.topoi_idx,
        positive_regions=[(0, 0, chrom_len)],
    )

    expected_near_end = near_start + near_footprint  # 134
    expected_middle_len = far_start - expected_near_end
    expected_wrapped_start = far_start + far_footprint
    expected_wrapped_len = (chrom_len - expected_wrapped_start) + near_start

    assert accessible == [
        (expected_near_end, 0, expected_middle_len),
        (expected_wrapped_start, 0, expected_wrapped_len),
    ], (
        "the real _binding_blocked_regions/_accessible_binding_regions path must report "
        "exactly two accessible regions (the middle chunk and ONE joined wrapped "
        f"fragment), matching live MATLAB; got {accessible!r}"
    )
    # Pinned against the live-MATLAB probe's literal values, independent
    # of this test's own arithmetic.
    assert accessible == [(134, 0, 579_792), (580_066, 0, 110)]

    # Inversion (manually verified, not baked into automated CI since it
    # requires editing production source in place): temporarily removing
    # both `_matlab_join_split_over_oric_regions` calls from
    # `_matlab_exclude_regions` (the included-fragment pre-processing
    # call and the raw-output post-processing call) makes this test's
    # PRIMARY assertion above fail -- the single full-chromosome fragment
    # then produces THREE unjoined accessible regions instead of two
    # (the wrapped remainder splits into a `[0, near_start)` piece and a
    # `[far_end+1, chrom_len)` piece, exactly mirroring the raw,
    # unjoined `oric_join_real_footprints` MATLAB probe intermediate).
    # Confirmed by hand during this fix (see STATUS_L22_DNAS_SEPT2.md's
    # Session 6 account) and re-confirmed after the fix was restored.


def test_damage_pairs_excludes_m6ad_methylation_marks_from_binding_exclusion() -> None:
    """`Chromosome.calcDamagedSites` (`Chromosome.m:3626-3627`) calls
    `getDamagedSites` with `includeM6AD=false`: an m6AD-methylated
    `damagedBases` entry is a routine epigenetic mark, not damage, and
    real MATLAB's binding-exclusion logic (`getAccessibleRegions`'s
    `dmgPosStrnds = find(this.damagedSites)`) never blocks protein
    binding because of one. Confirmed against the frozen trace
    (seed=0, tick_zero_based=81): every `damagedBases` entry in this
    corpus shares the SAME value (761/761 == DNARepair's
    `_m6ad_global_index`), and real MATLAB's live `c.damagedSites` query
    at that exact tick/region shows none of them as damage.
    """
    process = KarrDNASupercoilingProcess(
        {
            "chromosome_release_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "superhelical_density_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "process_rng_ledger_path": False,  # synthetic state, not a real MATLAB trace: opt out of ledger lookup
            "rng_seed": 61,
        }
    )
    store = process._resolve_chromosome_store(_base_state(process, sigma=0.12)["chromosome"])  # noqa: SLF001
    m6ad_value = process._m6ad_global_index  # noqa: SLF001
    genuine_damage_value = m6ad_value + 1  # any value that is NOT the m6AD marker
    store.set_field(  # noqa: SLF001
        "damagedBases",
        SparseTriplet(
            positions=np.asarray([10, 20], dtype=np.int64),
            strands=np.asarray([0, 0], dtype=np.int64),
            values=np.asarray([m6ad_value, genuine_damage_value], dtype=np.int64),
            shape=process.chromosome_shape,
        ),
    )

    pairs = process._damage_pairs(store)  # noqa: SLF001
    pair_positions = {int(position) for position, _ in pairs.tolist()}

    assert 20 in pair_positions, "a genuine (non-m6AD) damagedBases entry must still block binding"
    assert 10 not in pair_positions, "an m6AD-methylation-marked damagedBases entry must NOT block binding"

    # Inversion: the prior (unfiltered) behavior would have included BOTH
    # positions -- proof this is a real behavior change, not inert
    # bookkeeping.
    naive_pairs = {10, 20}
    assert pair_positions != naive_pairs
    assert pair_positions == {20}
