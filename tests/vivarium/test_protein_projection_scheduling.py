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
    """Claim C12: Step-graph execution layers must place a pre-projection step strictly

    before flat-reading Steps, and a post-projection step strictly after authority-writing
    Steps and strictly before post-write readers (observability).
    """
    from vivarium.core.engine import Engine

    from opencell.vivarium.karr_composite import build_karr_chassis_v6

    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    engine = Engine(composite=composite)
    layers = engine._step_graph.get_execution_layers()

    # Resolve each HierarchyPath tuple to its registered step name / object via engine._step_paths
    step_layer_map: dict[str, int] = {}
    projection_layers: list[int] = []
    pre_projection_layer: int | None = None
    post_projection_layer: int | None = None

    for layer_idx, layer in enumerate(layers):
        for path in layer:
            step_obj = engine._step_paths.get(path)
            step_key = path[-1] if path else ""
            step_name = getattr(step_obj, "name", step_key) if step_obj else step_key
            step_layer_map[step_key] = layer_idx
            step_layer_map[step_name] = layer_idx
            if step_obj is not None:
                step_layer_map[step_obj.__class__.__name__] = layer_idx

            is_projection = (
                "protein_flat_projection" in step_key
                or "protein_flat_projection" in step_name
                or (step_obj is not None and "ProteinFlatProjection" in step_obj.__class__.__name__)
            )
            if is_projection:
                projection_layers.append(layer_idx)
                if "pre" in step_key or "pre" in step_name:
                    pre_projection_layer = layer_idx
                elif "post" in step_key or "post" in step_name:
                    post_projection_layer = layer_idx

    assert projection_layers, (
        f"No protein_flat_projection step found in execution layers: {layers}"
    )

    if pre_projection_layer is None:
        pre_projection_layer = min(projection_layers)
    if post_projection_layer is None:
        post_projection_layer = max(projection_layers)

    # 1. Pre-projection layer must be strictly less than every specified flat-count reader layer
    flat_reading_steps = [
        "request_calculator_protein_pathway",
        "request_calculator_protein_translocation",
        "request_calculator_ribasm",
    ]
    for reader in flat_reading_steps:
        assert reader in step_layer_map, f"Flat-count reader {reader} missing from step graph"
        reader_layer = step_layer_map[reader]
        assert pre_projection_layer < reader_layer, (
            f"Pre-projection layer {pre_projection_layer} must be strictly less than "
            f"reader {reader} layer {reader_layer}"
        )

    # 2. Every authority-writing Step must be strictly less than post-projection layer
    auth_writing_steps = [
        "karr_allocation_step",
        "karr_chromosome_segregation_evolution",
    ]
    for auth_step in auth_writing_steps:
        assert auth_step in step_layer_map, f"AUTH-W step {auth_step} missing from step graph"
        auth_layer = step_layer_map[auth_step]
        assert auth_layer < post_projection_layer, (
            f"AUTH-W step {auth_step} layer {auth_layer} must be strictly less than "
            f"post-projection layer {post_projection_layer}"
        )

    # 3. Post-projection layer must be strictly less than observability/derived readers requiring post-write state
    post_write_readers = [
        "karr_observability_step",
    ]
    for obs_step in post_write_readers:
        assert obs_step in step_layer_map, f"Post-write reader {obs_step} missing from step graph"
        obs_layer = step_layer_map[obs_step]
        assert post_projection_layer < obs_layer, (
            f"Post-projection layer {post_projection_layer} must be strictly less than "
            f"observability step {obs_step} layer {obs_layer}"
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
