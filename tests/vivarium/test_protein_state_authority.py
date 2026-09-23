from __future__ import annotations

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
MIGRATED_WIDS = (
    "MG_191_MONOMER",
    "MG_192_MONOMER",
    "MG_217_MONOMER",
    "MG_218_MONOMER",
    "MG_312_MONOMER",
    "MG_317_MONOMER",
    "MG_318_MONOMER",
    "MG_386_MONOMER",
)


def test_c1_single_authority_write_rejection() -> None:
    """Claim C1: Applying an update directly to flat protein.counts must raise

    ProteinFlatProjectionWriteError naming the path, and preserve leaf value.
    """
    from vivarium.core.engine import Engine

    from opencell.vivarium.karr_composite import build_karr_chassis_v6

    try:
        from opencell.vivarium.protein_state import ProteinFlatProjectionWriteError
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
    assert current_flat == pytest.approx(expected_sum)

    # Attempt direct write to flat leaf: MUST raise ProteinFlatProjectionWriteError
    rogue_update = {"protein": {"counts": {"MG_312_MONOMER": 1.0}}}
    with pytest.raises(Exception) as exc_info:
        engine.state.apply_update(rogue_update)

    err_str = str(exc_info.value)
    assert "ProteinFlatProjectionWriteError" in err_str or isinstance(
        exc_info.value, ProteinFlatProjectionWriteError
    ), f"Expected ProteinFlatProjectionWriteError, got: {err_str}"
    assert "MG_312_MONOMER" in err_str

    # Leaf value after rejected write MUST remain unchanged
    after_view = engine.state.get_value()
    assert float(after_view["protein"]["counts"]["MG_312_MONOMER"]) == pytest.approx(expected_sum)


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
    assert observed_paths == expected_paths
    assert len(observed_paths) == 480, f"Expected exactly 480 leaves, found {len(observed_paths)}"


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
    assert new_flat == pytest.approx(old_flat + 7.0), f"Expected flat count {old_flat + 7.0}, got {new_flat}"


def test_c1d_aggregate_invariance_across_toa_transfer() -> None:
    """Claim C1d: TOA transfer changes compartment distribution but leaves

    aggregate sum exactly invariant both before and after the step.
    """
    from vivarium.core.engine import Engine

    from opencell.vivarium.karr_composite import build_karr_chassis_v6

    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    engine = Engine(composite=composite)
    initial_state = engine.state.get_value()

    assert "compartment_counts" in initial_state["protein"], "compartment_counts missing"

    wid = "MG_312_MONOMER"
    # Seed mature MG_312 = {tc: 26, c: 1}, others 0
    seed_update = {
        "protein": {
            "compartment_counts": {
                "mature": {
                    wid: {
                        "c": 1.0 - float(initial_state["protein"]["compartment_counts"]["mature"][wid]["c"]),
                        "tc": 26.0 - float(initial_state["protein"]["compartment_counts"]["mature"][wid]["tc"]),
                    }
                }
            }
        }
    }
    engine.state.apply_update(seed_update)
    engine.run_steps()

    state_before = engine.state.get_value()
    flat_before = float(state_before["protein"]["counts"][wid])
    assert flat_before == pytest.approx(27.0)

    # Execute one simulation tick (running TOA)
    engine.update(1.0)

    state_after = engine.state.get_value()
    mature_after = state_after["protein"]["compartment_counts"]["mature"][wid]
    flat_after = float(state_after["protein"]["counts"][wid])

    # Compartments must have shifted: c: 1 -> 0, tc: 26 -> 27
    assert mature_after["c"] == pytest.approx(0.0)
    assert mature_after["tc"] == pytest.approx(27.0)
    # Aggregate flat count MUST remain exactly invariant at 27.0
    assert flat_after == pytest.approx(27.0)
