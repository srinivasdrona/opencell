from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

# Canonical constants from design spec
FORMS = (
    "nascent",
    "processed_i",
    "processed_ii",
    "signal_sequence",
    "folded",
    "mature",
    "inactivated",
    "bound",
    "misfolded",
    "damaged",
)
COMPARTMENTS = ("c", "d", "e", "m", "tc", "tm")
import numpy as np
from scipy.io import loadmat


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


def load_source_derived_migrated_wids() -> tuple[str, ...]:
    toa_path = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "TerminalOrganelleAssembly_flat.mat"
    pt_path = _REPO_ROOT / "data" / "karr_fixtures" / "per_process" / "ProteinTranslocation_flat.mat"
    toa_mat = loadmat(str(toa_path), squeeze_me=True, struct_as_record=False)
    pt_mat = loadmat(str(pt_path), squeeze_me=True, struct_as_record=False)
    toa_wids = set(_parse_wid_array(toa_mat["data"].fixture.substrateWholeCellModelIDs))
    pt_fx = pt_mat["data"].fixture
    pt_wids = [str(x) for x in pt_fx.monomerWholeCellModelIDs]
    trans_indices = np.asarray(pt_fx.monomerIndexs_translocating, dtype=int) - 1
    pt_trans_wids = {pt_wids[i] for i in trans_indices}
    return tuple(sorted(toa_wids | pt_trans_wids))


MIGRATED_WIDS = load_source_derived_migrated_wids()


def test_c1_single_authority_write_rejection() -> None:
    """Claim C1: Applying an update directly to flat protein.counts must raise

    ProteinFlatProjectionWriteError naming the path, and preserve leaf value.
    """
    from vivarium.core.engine import Engine

    from opencell.vivarium.karr_composite import build_karr_chassis_v6

    try:
        from opencell.vivarium.protein_state import ProteinFlatProjectionWriteError
        assert issubclass(ProteinFlatProjectionWriteError, Exception)
    except ImportError as exc:
        pytest.fail(f"Stage-1 protein_state module not yet implemented: {exc}")

    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    engine = Engine(composite=composite)
    state_view = engine.state.get_value()


    # Pre-condition: authority has mature row for MG_312_MONOMER
    assert "compartment_counts" in state_view["protein"], "protein.compartment_counts must exist in chassis store"
    mature_row = state_view["protein"]["compartment_counts"]["mature"]["MG_312_MONOMER"]
    expected_sum = float(sum(mature_row[k] for k in COMPARTMENTS))
    current_flat = float(state_view["protein"]["counts"]["MG_312_MONOMER"])
    assert current_flat.is_integer(), f"Expected integer count, got {current_flat}"
    assert current_flat == expected_sum

    # Attempt direct write to flat leaf: MUST raise exception naming the path and failed update
    rogue_update = {"protein": {"counts": {"MG_312_MONOMER": 1.0}}}
    with pytest.raises(Exception) as exc_info:
        engine.state.apply_update(rogue_update)

    err_str = str(exc_info.value)
    assert "failed update" in err_str.lower(), f"Expected 'failed update' in exception message, got: {err_str}"
    assert "MG_312_MONOMER" in err_str, f"Expected 'MG_312_MONOMER' in exception message, got: {err_str}"
    assert (
        "('protein', 'counts', 'MG_312_MONOMER')" in err_str
        or ("protein" in err_str and "counts" in err_str and "MG_312_MONOMER" in err_str)
    ), f"Expected path ('protein', 'counts', 'MG_312_MONOMER') in exception message, got: {err_str}"

    # Leaf value after rejected write MUST remain unchanged
    after_view = engine.state.get_value()
    after_flat = float(after_view["protein"]["counts"]["MG_312_MONOMER"])
    assert after_flat.is_integer(), f"Expected integer count, got {after_flat}"
    assert after_flat == expected_sum


def test_c1b_no_leaf_path_drift() -> None:
    """Claim C1b: Store paths under protein.compartment_counts must exactly match

    10 forms x 8 WIDs x 6 compartments = 480 leaves at Stage 1b.
    """
    from vivarium.core.engine import Engine

    from opencell.vivarium.karr_composite import build_karr_chassis_v6

    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    engine = Engine(composite=composite)
    state_view = engine.state.get_value()


    assert "compartment_counts" in state_view["protein"], "protein.compartment_counts missing"
    comp_counts = state_view["protein"]["compartment_counts"]

    observed_paths: set[tuple[str, str, str]] = set()
    for form_key, wids_dict in comp_counts.items():
        assert form_key in FORMS, f"Unexpected form {form_key!r} not in {FORMS}"
        for wid_key, comps_dict in wids_dict.items():
            assert wid_key in MIGRATED_WIDS, f"Unexpected WID {wid_key!r} in Stage 1b authority"
            for comp_key, val in comps_dict.items():
                assert comp_key in COMPARTMENTS, f"Unexpected compartment {comp_key!r}"
                assert isinstance(val, (int, float)), f"Value at ({form_key}, {wid_key}, {comp_key}) not numeric"
                observed_paths.add((form_key, wid_key, comp_key))

    expected_paths = {
        (form, wid, comp)
        for form in FORMS
        for wid in MIGRATED_WIDS
        for comp in COMPARTMENTS
    }
    assert len(observed_paths) == 7440, f"Expected exactly 7440 leaves (10 forms x 124 WIDs x 6 compartments), found {len(observed_paths)}"
    assert observed_paths == expected_paths


def test_c1c_flat_identity_through_reader_port() -> None:
    """Claim C1c: Mutating authority reflects in flat view through reader's port."""
    from vivarium.core.engine import Engine

    from opencell.vivarium.karr_composite import build_karr_chassis_v6

    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    engine = Engine(composite=composite)
    initial_state = engine.state.get_value()
    assert "compartment_counts" in initial_state["protein"], "compartment_counts missing"

    wid = "MG_318_MONOMER"
    old_flat = float(initial_state["protein"]["counts"][wid])

    # Mutate authority directly by +7 copies in membrane compartment 'm'
    authority_update = {
        "protein": {
            "compartment_counts": {
                "mature": {
                    wid: {"m": 7.0}
                }
            }
        }
    }
    engine.state.apply_update(authority_update)

    # Run steps to trigger projection
    engine.run_steps()

    after_state = engine.state.get_value()
    new_flat = float(after_state["protein"]["counts"][wid])
    assert new_flat.is_integer(), f"Expected integer count, got {new_flat}"
    assert new_flat == old_flat + 7.0, f"Expected flat count {old_flat + 7.0}, got {new_flat}"


def test_c1d_aggregate_invariance_across_toa_transfer() -> None:
    """Claim C1d: Minimal real Vivarium Engine containing production TOA plus production

    projection Step proves that TOA transfer changes compartment distribution while
    leaving aggregate sum exactly invariant (integer-exact) before and after the step.
    Minimal composition isolates TOA transfer with zero interference from other processes.
    """
    from vivarium.core.composer import Composite
    from vivarium.core.engine import Engine

    try:
        from opencell.vivarium.protein_flat_projection_step import (
            ProteinFlatProjectionStep,
        )
        from opencell.vivarium.protein_state import (
            COMPARTMENTS as PS_COMPARTMENTS,
        )
        from opencell.vivarium.protein_state import (
            FORMS as PS_FORMS,
        )
        from opencell.vivarium.protein_state import (
            MIGRATED_WIDS as PS_MIGRATED_WIDS,
        )
    except ImportError as exc:
        pytest.fail(f"Stage-1 protein_state / projection step not yet implemented: {exc}")

    from opencell.vivarium.karr_terminal_organelle_assembly import (
        KarrTerminalOrganelleAssemblyProcess,
    )

    toa_proc = KarrTerminalOrganelleAssemblyProcess({"time_step": 1.0})
    proj_step = ProteinFlatProjectionStep({})

    processes = {"karr_terminal_organelle_assembly": toa_proc}
    steps = {"protein_flat_projection": proj_step}
    flow = {"protein_flat_projection": []}
    topology = {
        "karr_terminal_organelle_assembly": {"protein": ("protein",)},
        "protein_flat_projection": {"protein": ("protein",)},
    }

    initial_state: dict[str, Any] = {
        "protein": {
            "counts": {wid: 0.0 for wid in PS_MIGRATED_WIDS},
            "compartment_counts": {
                form: {
                    wid: {comp: 0.0 for comp in PS_COMPARTMENTS}
                    for wid in PS_MIGRATED_WIDS
                }
                for form in PS_FORMS
            },
        }
    }
    wid = "MG_312_MONOMER"
    initial_state["protein"]["compartment_counts"]["mature"][wid]["c"] = 1.0
    initial_state["protein"]["compartment_counts"]["mature"][wid]["tc"] = 26.0
    initial_state["protein"]["compartment_counts"]["mature"]["MG_218_MONOMER"]["tc"] = 33.0

    composite = Composite(
        processes=processes,
        steps=steps,
        flow=flow,
        topology=topology,
        state=initial_state,
    )
    engine = Engine(composite=composite)

    state_before = engine.state.get_value()
    flat_before = float(state_before["protein"]["counts"][wid])
    assert flat_before.is_integer(), f"Expected integer count before, got {flat_before}"
    assert flat_before == 27.0, f"Expected 27.0 before step, got {flat_before}"

    # Execute one tick (runs TOA process update, then projection step)
    engine.update(1.0)

    state_after = engine.state.get_value()
    mature_after = state_after["protein"]["compartment_counts"]["mature"][wid]
    flat_after = float(state_after["protein"]["counts"][wid])

    # Compartments must have shifted: c: 1 -> 0, tc: 26 -> 27 (integer-exact)
    assert mature_after["c"] == 0.0, f"Expected c == 0.0, got {mature_after['c']}"
    assert mature_after["tc"] == 27.0, f"Expected tc == 27.0, got {mature_after['tc']}"
    assert float(mature_after["c"]).is_integer()
    assert float(mature_after["tc"]).is_integer()

    # Aggregate flat count MUST remain exactly invariant at 27.0
    assert flat_after.is_integer()
    assert flat_after == 27.0


def test_c6_no_path_resurrection_after_100_ticks() -> None:
    """Claim C6: 100-tick realized store has no resurrected legacy path for any of the 124 WIDs.

    Running the full chassis for 100 ticks must preserve single-authority invariance:
    no undeclared protein.counts leaf, no resurrected legacy branches for any enrolled WID,
    and direct flat writes continue to be rejected.
    """
    from vivarium.core.engine import Engine

    from opencell.vivarium.karr_composite import build_karr_chassis_v6

    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    engine = Engine(composite=composite)

    # Run for 100 ticks
    engine.update(100.0)

    final_state = engine.state.get_value()
    protein_state = final_state.get("protein", {})
    assert "compartment_counts" in protein_state, "compartment_counts missing after 100 ticks"
    mature_store = protein_state["compartment_counts"].get("mature", {})
    flat_counts = protein_state.get("counts", {})

    legacy_branches = (
        "unprocessed_counts",
        "processed_counts",
        "unfolded_counts",
        "unmodified_counts",
        "modified_counts",
        "signal_sequence_counts",
        "location",
    )

    resurrected: list[str] = []
    for wid in MIGRATED_WIDS:
        # 1. No legacy branch in store may contain enrolled WID
        for branch in legacy_branches:
            if branch in protein_state and wid in protein_state[branch]:
                resurrected.append(f"WID {wid} resurrected under protein.{branch}")

        # 2. Flat count must match sum across compartments
        if wid in mature_store:
            expected_flat = sum(float(mature_store[wid].get(c, 0.0)) for c in COMPARTMENTS)
            actual_flat = float(flat_counts.get(wid, 0.0))
            assert actual_flat.is_integer(), f"Non-integer flat count for {wid}: {actual_flat}"
            assert actual_flat == expected_flat, f"Flat mismatch for {wid}: flat={actual_flat}, comp_sum={expected_flat}"

    assert not resurrected, "Resurrected legacy paths found after 100 ticks:\n" + "\n".join(resurrected)

    # 3. Direct write to flat counts for an enrolled WID must still be rejected
    test_wid = MIGRATED_WIDS[0]
    with pytest.raises(Exception):
        engine.state.apply_update({"protein": {"counts": {test_wid: 999.0}}})
