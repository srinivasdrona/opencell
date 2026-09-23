from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

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
COMPARTMENTS = ("c", "d", "e", "m", "tc", "tm")


def test_c12_step_graph_ordering_structurally_correct() -> None:
    """Claim C12: Step-graph execution layers must place a projection step in layer 0

    (before readers) and another projection step strictly after authority-writing Steps.
    """
    from vivarium.core.engine import Engine

    from opencell.vivarium.karr_composite import build_karr_chassis_v6

    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    engine = Engine(composite=composite)
    layers = engine._step_graph.get_execution_layers()


    # Find step layers by step name / class
    step_layer_map: dict[str, int] = {}
    projection_layers: list[int] = []

    for layer_idx, layer in enumerate(layers):
        for step in layer:
            step_name = getattr(step, "name", step.__class__.__name__)
            step_layer_map[step_name] = layer_idx
            if "protein_flat_projection" in step_name or "Projection" in step.__class__.__name__:
                projection_layers.append(layer_idx)

    assert projection_layers, (
        f"No protein_flat_projection step found in execution layers: {layers}"
    )
    # A projection instance must exist in the FIRST layer (layer 0)
    assert 0 in projection_layers, (
        f"Projection instance must exist in layer 0 (found projection in layers: {projection_layers})"
    )

    # Authority-writing steps (AUTH-W) must be in layers strictly < a post-projection step
    auth_writing_step_names = [
        "karr_chromosome_segregation_evolution",
        "karr_allocation_step",
    ]
    for auth_step in auth_writing_step_names:
        if auth_step in step_layer_map:
            auth_layer = step_layer_map[auth_step]
            assert any(proj_layer > auth_layer for proj_layer in projection_layers), (
                f"AUTH-W step {auth_step} in layer {auth_layer} has no subsequent projection step"
            )

    # Flat reading steps (DERIVED-R) must sit in a layer strictly > some projection instance
    # Within a layer Vivarium defers updates, so proj_layer must be strictly less than reader_layer.
    flat_reading_step_names = [
        "request_calculator_protein_pathway",
        "request_calculator_protein_translocation",
        "request_calculator_ribasm",
        "karr_observability_step",
    ]
    for reader_step in flat_reading_step_names:
        if reader_step in step_layer_map:
            reader_layer = step_layer_map[reader_step]
            assert any(proj_layer < reader_layer for proj_layer in projection_layers), (
                f"DERIVED-R step {reader_step} in layer {reader_layer} has no strictly prior projection step"
            )


def test_c13_t0_projection_correctness() -> None:
    """Claim C13: Immediately after build_karr_chassis_v6() and BEFORE any update(),

    protein.counts[wid] == sum_k mature[wid][k] for all migrated WIDs.
    Ensures projection Step executed during Engine.__init__().
    """
    from vivarium.core.engine import Engine

    from opencell.vivarium.karr_composite import build_karr_chassis_v6

    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    engine = Engine(composite=composite)
    state = engine.state.get_value()

    assert "compartment_counts" in state["protein"], "protein.compartment_counts must exist at t=0"
    mature_counts = state["protein"]["compartment_counts"]["mature"]
    flat_counts = state["protein"]["counts"]

    for wid in MIGRATED_WIDS:
        assert wid in mature_counts, f"{wid} missing from mature compartment_counts at t=0"
        expected_sum = float(sum(mature_counts[wid][k] for k in COMPARTMENTS))
        actual_flat = float(flat_counts.get(wid, 0.0))
        assert actual_flat.is_integer(), f"Non-integral flat count for {wid}: {actual_flat}"
        assert actual_flat == expected_sum, (
            f"t=0 staleness for {wid}: flat {actual_flat} != authority sum {expected_sum}"
        )
