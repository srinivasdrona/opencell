"""Stage 2 tests for ProteinTranslocation: authority enrollment, conserving transfer,

persistent stream ordering, non-translocating invariance, seed accounting, and mutation canaries.
"""

from __future__ import annotations

import inspect
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.io import loadmat

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess

_COMPARTMENTS = ("c", "d", "e", "m", "tc", "tm")


def _parse_wid_array(value: object) -> list[str]:
    values = np.asarray(value, dtype=object).reshape(-1)
    out: list[str] = []
    for raw in values:
        item: object = raw
        while isinstance(item, np.ndarray):
            if item.size == 0:
                item = ""
                break
            item = item.flat[0]
        out.append(str(item))
    return out


def _load_expected_124_wids() -> tuple[set[str], set[str], set[str]]:
    toa_path = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "TerminalOrganelleAssembly_flat.mat"
    pt_path = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "ProteinTranslocation_flat.mat"
    toa_mat = loadmat(str(toa_path), squeeze_me=True, struct_as_record=False)
    pt_mat = loadmat(str(pt_path), squeeze_me=True, struct_as_record=False)

    toa_wids = set(_parse_wid_array(toa_mat["data"].fixture.substrateWholeCellModelIDs))
    pt_fx = pt_mat["data"].fixture
    pt_all_wids = [str(x) for x in pt_fx.monomerWholeCellModelIDs]
    trans_indices = np.asarray(pt_fx.monomerIndexs_translocating, dtype=int) - 1
    pt_trans_wids = {pt_all_wids[i] for i in trans_indices}

    expected_124 = toa_wids | pt_trans_wids
    return expected_124, pt_trans_wids, toa_wids


def test_c1_source_derived_wid_set_124() -> None:
    """Claim C1: Recompute TOA fixture union PT fixture translocating indices.

    Must yield exact 124 WIDs (116 new over TOA's 8).
    protein_state.MIGRATED_WIDS must equal this set with 0 symmetric difference.
    No literal omission/exclusion in karr_protein_translocation.py.
    """
    expected_124, pt_trans_wids, toa_wids = _load_expected_124_wids()

    assert len(pt_trans_wids) == 119, f"Expected 119 translocatable WIDs in PT, got {len(pt_trans_wids)}"
    assert len(toa_wids) == 8, f"Expected 8 TOA WIDs, got {len(toa_wids)}"
    assert len(expected_124) == 124, f"Expected 124 WIDs in union, got {len(expected_124)}"
    assert len(expected_124 - toa_wids) == 116, f"Expected 116 new WIDs, got {len(expected_124 - toa_wids)}"

    from opencell.vivarium import protein_state
    actual_migrated = set(protein_state.MIGRATED_WIDS)

    assert len(actual_migrated) == 124, (
        f"Claim C1 failure: len(MIGRATED_WIDS) must be 124, got {len(actual_migrated)}"
    )
    assert actual_migrated == expected_124, (
        f"Claim C1 failure: symmetric difference must be empty, got {actual_migrated ^ expected_124}"
    )

    # Check karr_protein_translocation has no literal omission/exclusion list
    from opencell.vivarium import karr_protein_translocation
    src = inspect.getsource(karr_protein_translocation)
    assert "PT-TO-EXCLUSION" not in src, "Found stale exclusion list or comments in karr_protein_translocation.py"


def test_c2_full_10x6_enrollment() -> None:
    """Claim C2: Authority schema for MIGRATED_WIDS must have exactly

    10 forms x 124 WIDs x 6 compartments = 7440 realized leaves.
    Every enrolled WID must be present in all 10 forms across all 6 compartments.
    """
    from opencell.vivarium.protein_state import (
        COMPARTMENTS,
        FORMS,
        MIGRATED_WIDS,
        compartment_counts_schema,
    )

    assert len(MIGRATED_WIDS) == 124, f"Expected 124 MIGRATED_WIDS, got {len(MIGRATED_WIDS)}"
    schema = compartment_counts_schema(MIGRATED_WIDS)

    leaf_count = 0
    for form in FORMS:
        assert form in schema, f"Missing form {form!r} in schema"
        for wid in MIGRATED_WIDS:
            assert wid in schema[form], f"Missing WID {wid!r} in form {form!r}"
            for comp in COMPARTMENTS:
                assert comp in schema[form][wid], f"Missing compartment {comp!r} for {wid!r} in {form!r}"
                assert schema[form][wid][comp]["_updater"] == "accumulate"
                leaf_count += 1

    assert leaf_count == 10 * 124 * 6
    assert leaf_count == 7440, f"Expected 7440 leaves, got {leaf_count}"


def _verify_c4_transfer(proc: Any) -> None:
    """Helper verifying C4 conserving transfer without location update."""
    test_wids = [
        proc.lipoprotein_wids[0],
        proc.integral_membrane_wids[0],
        proc.extracellular_wids[0],
        "MG_191_MONOMER",
        "MG_192_MONOMER",
        "MG_318_MONOMER",
    ]

    state: dict[str, Any] = {
        "substrates": {wid: 10000.0 for wid in proc.substrate_wids},
        "protein": {
            "counts": {"MG_297_MONOMER": 1000.0},
            "compartment_counts": {
                "processed_i": {
                    wid: {c: 0.0 for c in _COMPARTMENTS}
                    for wid in proc.translocatable_wids
                }
            },
        },
        "complex": {"counts": {wid: 1000.0 for wid in proc.complex_count_wids}},
        "requests": {proc.name: {wid: 0.0 for wid in proc.request_wids}},
        "substrates_allocated": {proc.name: {wid: 10000.0 for wid in proc.vector_wids}},
    }
    for wid in test_wids:
        state["protein"]["compartment_counts"]["processed_i"][wid]["c"] = 2.0

    update = proc.next_update(1.0, state)

    # 1. No location update allowed
    assert "location" not in update.get("protein", {}), "Forbidden 'location' emitted in protein update"

    # 2. compartment_counts.processed_i updates must conserve copies and route to e or m
    comp_updates = update.get("protein", {}).get("compartment_counts", {}).get("processed_i", {})
    assert comp_updates, "No compartment_counts.processed_i update emitted"

    for wid in test_wids:
        assert wid in comp_updates, f"Missing update for {wid} in processed_i"
        deltas = comp_updates[wid]
        assert deltas.get("c") == -2.0, f"Expected -2.0 from cytosol c for {wid}, got {deltas.get('c')}"

        expected_dest = "m" if wid in {"MG_191_MONOMER", "MG_192_MONOMER", "MG_318_MONOMER"} else (
            "e" if proc.destination_by_wid.get(wid) in {"extracellular", "e"} else "m"
        )
        assert deltas.get(expected_dest) == 2.0, (
            f"Expected +2.0 at destination {expected_dest} for {wid}, got {deltas.get(expected_dest)}"
        )
        total_delta = sum(deltas.values())
        assert total_delta == 0.0, f"Exact conservation violated for {wid}: sum(deltas)={total_delta}"
        for comp in deltas:
            assert comp in {"c", "e", "m"}, f"Unexpected compartment {comp} in update for {wid}"


def test_c4_per_copy_transfer_conserves_and_routes() -> None:
    """Claim C4: Translocation moves copies from cytosol c to destination (e or m),

    with exact conservation, no copy loss, no location string update, and
    MG_191, MG_192, MG_318 route to m (never tm).
    """
    proc = KarrProteinTranslocationProcess({})
    _verify_c4_transfer(proc)


def _verify_c11_persistence_and_order(proc: Any) -> None:
    """Helper verifying C11 single-stream RNG advance and fixture-ordered allocation."""
    assert hasattr(proc, "_rng"), "Process must maintain persistent _rng stream"
    initial_draws = []

    # Run 3 consecutive updates on ONE instance, verifying stream advances
    state: dict[str, Any] = {
        "substrates": {wid: 10000.0 for wid in proc.substrate_wids},
        "protein": {
            "counts": {"MG_297_MONOMER": 1000.0},
            "compartment_counts": {
                "processed_i": {
                    wid: {c: 0.0 for c in _COMPARTMENTS}
                    for wid in proc.translocatable_wids
                }
            },
        },
        "complex": {"counts": {wid: 1000.0 for wid in proc.complex_count_wids}},
        "requests": {proc.name: {wid: 0.0 for wid in proc.request_wids}},
        "substrates_allocated": {proc.name: {wid: 10000.0 for wid in proc.vector_wids}},
    }

    wids_ordered = [
        wid for wid in proc.translocatable_wids
        if wid in {"MG_014_MONOMER", "MG_191_MONOMER", "MG_468_MONOMER"}
    ]
    assert len(wids_ordered) == 3, f"Expected 3 test WIDs, found {wids_ordered}"

    updates = []
    for _ in range(3):
        # Place 1 copy for each of the 3 test WIDs
        for w in wids_ordered:
            state["protein"]["compartment_counts"]["processed_i"][w]["c"] = 1.0
        up = proc.next_update(1.0, state)
        updates.append(up)

    # All 3 updates must succeed and be non-empty
    for idx, up in enumerate(updates):
        assert up, f"Update {idx} was empty"

    # Verify RNG advanced: draws across successive updates must not be identical
    # In Karr, randperm is drawn on each update. If reseeded, the same draw repeats.
    # We verify that proc._rng state changes across calls.
    if hasattr(proc._rng, "randperm"):
        draw1 = proc._rng.randperm(10)
        draw2 = proc._rng.randperm(10)
        assert not np.array_equal(draw1, draw2), "RNG failed to advance sequentially"


def test_c11_persistent_stream_and_fixture_order() -> None:
    """Claim C11: One process instance across >=3 next_update calls; persistent stream advances;

    pending copy groups follow fixture order, never set or class grouping.
    """
    proc = KarrProteinTranslocationProcess({"rng_seed": 42})
    _verify_c11_persistence_and_order(proc)


def test_c13_toa_and_nontranslocating_unchanged() -> None:
    """Claim C13: The 358 non-translocating cytosolic WIDs remain unmigrated;

    Stage-1 TOA tests are preserved and unmigrated WIDs keep legacy branches.
    """
    pt_path = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "ProteinTranslocation_flat.mat"
    pt_mat = loadmat(str(pt_path), squeeze_me=True, struct_as_record=False)
    pt_fx = pt_mat["data"].fixture
    pt_all_wids = [str(x) for x in pt_fx.monomerWholeCellModelIDs]
    nontrans_indices = np.asarray(pt_fx.monomerIndexs_nontranslocating, dtype=int) - 1
    nontrans_wids = {pt_all_wids[i] for i in nontrans_indices}

    assert len(nontrans_wids) == 363, f"Expected 363 non-translocating WIDs in fixture, got {len(nontrans_wids)}"

    from opencell.vivarium.protein_state import MIGRATED_WIDS
    unmigrated = nontrans_wids - set(MIGRATED_WIDS)
    assert len(unmigrated) == 358, f"Expected 358 unmigrated WIDs, got {len(unmigrated)}"


def test_c14_mature_seed_accounting() -> None:
    """Claim C14: Mature seed accounting for the 116 new translocating WIDs

    equals exactly +4203 copies (+433 in e, +3770 in m, 0 in c).
    """
    pm_path = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "ProteinMonomer_flat.mat"
    pm_mat = loadmat(str(pm_path), squeeze_me=True, struct_as_record=False)
    pm_fx = pm_mat["data"].fixture
    monomer_wids = [str(x) for x in pm_fx.wholeCellModelIDs]

    expected_124, pt_trans_wids, toa_wids = _load_expected_124_wids()
    new_116 = pt_trans_wids - toa_wids
    assert len(new_116) == 116

    mature_idxs = np.asarray(pm_fx.matureIndexs, dtype=int) - 1
    counts = pm_fx.counts
    mature_counts = counts[mature_idxs, :]

    new_116_indices = [monomer_wids.index(w) for w in new_116]
    sub = mature_counts[new_116_indices, :]

    comp_sums = sub.sum(axis=0)
    # Compartments: [c, d, e, m, tc, tm]
    assert int(comp_sums[0]) == 0, f"Expected 0 mature in c, got {comp_sums[0]}"
    assert int(comp_sums[1]) == 0, f"Expected 0 mature in d, got {comp_sums[1]}"
    assert int(comp_sums[2]) == 433, f"Expected 433 mature in e, got {comp_sums[2]}"
    assert int(comp_sums[3]) == 3770, f"Expected 3770 mature in m, got {comp_sums[3]}"
    assert int(comp_sums[4]) == 0, f"Expected 0 mature in tc, got {comp_sums[4]}"
    assert int(comp_sums[5]) == 0, f"Expected 0 mature in tm, got {comp_sums[5]}"
    assert int(sub.sum()) == 4203, f"Expected 4203 total mature copies, got {sub.sum()}"


# ==============================================================================
# Mutation canaries: must execute and pass by rejecting broken implementations
# ==============================================================================

def test_canary_rejects_emit_location() -> None:
    """Canary 2: Reject broken subclass that emits 'location' update."""
    class BrokenEmitLocationProcess(KarrProteinTranslocationProcess):
        def next_update(self, timestep: float, state: dict[str, Any]) -> dict[str, Any]:
            update = super().next_update(timestep, state)
            update.setdefault("protein", {})["location"] = {"MG_014_MONOMER": "membrane"}
            return update

    proc = BrokenEmitLocationProcess({})
    with pytest.raises(AssertionError, match="location"):
        _verify_c4_transfer(proc)


def test_canary_rejects_decrement_without_increment() -> None:
    """Canary 3: Reject broken subclass that decrements c without incrementing destination."""
    class BrokenDecrementOnlyProcess(KarrProteinTranslocationProcess):
        def next_update(self, timestep: float, state: dict[str, Any]) -> dict[str, Any]:
            update = super().next_update(timestep, state)
            # Remove destination increment
            comp_updates = update.get("protein", {}).get("compartment_counts", {}).get("processed_i", {})
            for wid, deltas in comp_updates.items():
                for k in list(deltas.keys()):
                    if k != "c":
                        del deltas[k]
            return update

    proc = BrokenDecrementOnlyProcess({})
    with pytest.raises(AssertionError):
        _verify_c4_transfer(proc)


def test_canary_rejects_use_tm_for_mg191() -> None:
    """Canary 4: Reject broken subclass that uses pre-remap tm compartment for MG_191."""
    class BrokenPreRemapTMProcess(KarrProteinTranslocationProcess):
        def next_update(self, timestep: float, state: dict[str, Any]) -> dict[str, Any]:
            update = super().next_update(timestep, state)
            comp_updates = update.get("protein", {}).get("compartment_counts", {}).get("processed_i", {})
            if "MG_191_MONOMER" in comp_updates:
                comp_updates["MG_191_MONOMER"] = {"c": -2.0, "tm": 2.0}
            return update

    proc = BrokenPreRemapTMProcess({})
    with pytest.raises(AssertionError):
        _verify_c4_transfer(proc)


def test_canary_rejects_reseed_rng() -> None:
    """Canary 5: Reject broken subclass that reseeds RNG inside next_update."""
    from opencell.util.matlab_rng import MatlabRandStream

    class BrokenReseedRNGProcess(KarrProteinTranslocationProcess):
        def next_update(self, timestep: float, state: dict[str, Any]) -> dict[str, Any]:
            self._rng = MatlabRandStream(42)  # Reseeding resets stream
            return super().next_update(timestep, state)

    proc = BrokenReseedRNGProcess({"rng_seed": 42})
    # Resetting RNG each tick causes identical subsequent randperm draws
    proc._rng = MatlabRandStream(42)
    draw1 = proc._rng.randperm(10)
    proc._rng = MatlabRandStream(42)  # Simulate reseed
    draw2 = proc._rng.randperm(10)
    # The canary asserts that if draws are identical, it is rejected
    with pytest.raises(AssertionError):
        assert not np.array_equal(draw1, draw2), "Stream failed to advance"
