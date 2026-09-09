from __future__ import annotations

from pathlib import Path
import sys

import h5py
import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import _l2_2_design_a_runner_helpers as helpers  # noqa: E402
import _l2_2_dnas_runner_helpers as dnas_helpers  # noqa: E402
from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet  # noqa: E402
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess  # noqa: E402

TRACE_PATH = (
    _REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2"
    / "DNASupercoiling_100ticks.mat"
)


def _triplets_equal(left: SparseTriplet, right: SparseTriplet) -> bool:
    return (
        np.array_equal(left.positions, right.positions)
        and np.array_equal(left.strands, right.strands)
        and np.array_equal(left.values, right.values)
    )


def _triplet_lookup(triplet: SparseTriplet) -> dict[tuple[int, int], int]:
    return {
        (int(position), int(strand)): int(value)
        for position, strand, value in zip(
            triplet.positions.tolist(),
            triplet.strands.tolist(),
            triplet.values.tolist(),
            strict=False,
        )
    }


def test_seed0_tick5_hidden_superhelical_density_keeps_topoiv_illegal() -> None:
    process = KarrDNASupercoilingProcess({"rng_seed": 0})
    store = ChromosomeStore.from_trace_tick(TRACE_PATH, tick=5, group_name="states_before")

    polymerized = process._ensure_polymerized_regions(store.get_field("polymerizedRegions"))  # noqa: SLF001
    positive_regions = process._positive_regions_from_store(store=store, polymerized=polymerized)  # noqa: SLF001
    linking_numbers = store.get_field("linkingNumbers")
    sigma_values = process._positive_region_sigmas_from_store(  # noqa: SLF001
        store=store,
        positive_regions=positive_regions,
        linking_numbers=linking_numbers,
        fallback_sigma=float(process.equilibrium_sigma),
    )

    assert positive_regions == [(333, 0, 579410), (579765, 0, 311), (0, 2, 311)]
    assert sigma_values.tolist() == pytest.approx(
        [-0.058828912843933205, 0.0, 0.0],
        abs=1e-12,
    )
    assert not np.any(sigma_values > float(process.topoiv_sigma_limit))


def test_seed0_tick5_replay_preserves_topoiv_zero_bind_after_state() -> None:
    process = KarrDNASupercoilingProcess({"rng_seed": 0})
    topoiv_global_idx = int(process.enzyme_global_indices[int(process.topoiv_idx)])

    with h5py.File(TRACE_PATH, "r") as trace:
        before_substrates = helpers._matlab_channel_matrix(trace, trace["states_before/substrates"])  # noqa: SLF001
        before_enzymes = helpers._matlab_channel_matrix(trace, trace["states_before/enzymes"])  # noqa: SLF001
        before_bound = helpers._matlab_channel_matrix(trace, trace["states_before/boundEnzymes"])  # noqa: SLF001
        after_store = helpers._chromosome_store_at(trace, "states_after", 5)  # noqa: SLF001

    dnas_helpers.reset_dna_supercoiling_persistent_processes(0)
    try:
        oc_result: dict[str, object] | None = None
        for tick in range(6):
            before_store = ChromosomeStore.from_trace_tick(TRACE_PATH, tick=tick, group_name="states_before")
            sample_state = {
                "substrate_wids": list(process.substrate_wids),
                "enzyme_wids": list(process.enzyme_wids),
                "oracle_before_substrates": before_substrates[tick],
                "oracle_before_enzymes": before_enzymes[tick],
                "oracle_before_bound_enzymes": before_bound[tick],
                "oracle_before_chromosome_store": before_store,
            }
            oc_result = dnas_helpers.run_dna_supercoiling_tick(0, tick, sample_state)
    finally:
        dnas_helpers.reset_dna_supercoiling_persistent_processes(0)

    assert oc_result is not None
    oc_after_store = oc_result["chromosome_after_store"]
    oc_complex = oc_after_store.get_field("complexBoundSites")
    trace_complex = after_store.get_field("complexBoundSites")
    oc_linking = oc_after_store.get_field("linkingNumbers")
    trace_linking = after_store.get_field("linkingNumbers")
    oc_linking_lookup = _triplet_lookup(oc_linking)
    trace_linking_lookup = _triplet_lookup(trace_linking)

    assert int(np.count_nonzero(oc_complex.values.astype(np.int64, copy=False) == topoiv_global_idx)) == 0
    assert int(np.count_nonzero(trace_complex.values.astype(np.int64, copy=False) == topoiv_global_idx)) == 0
    assert oc_linking_lookup[(579765, 0)] == 30
    assert oc_linking_lookup[(579765, 1)] == 30
    assert oc_linking_lookup[(0, 2)] == 30
    assert oc_linking_lookup[(0, 3)] == 30
    assert oc_linking_lookup[(579765, 0)] == trace_linking_lookup[(579765, 0)]
    assert oc_linking_lookup[(579765, 1)] == trace_linking_lookup[(579765, 1)]
    assert oc_linking_lookup[(0, 2)] == trace_linking_lookup[(0, 2)]
    assert oc_linking_lookup[(0, 3)] == trace_linking_lookup[(0, 3)]
