from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from vivarium.core.engine import Engine

from opencell.m3 import translation as tl
from opencell.m3 import translation_v2 as tl_v2
from opencell.vivarium.karr_m3_v2 import KarrTranslationV2Process
from opencell.vivarium.karr_m3_v3 import KarrTranslationV3Process


def _collect_updaters(node):
    if isinstance(node, dict):
        updater = node.get("_updater")
        if updater is not None:
            yield updater
        for value in node.values():
            yield from _collect_updaters(value)


def _make_m3_state(process: KarrTranslationV2Process, n_active_ribosomes: float | None = None):
    active = (
        float(process.mechanism_inputs.n_active_ribosomes)
        if n_active_ribosomes is None
        else float(n_active_ribosomes)
    )
    return {
        "protein": {
            "counts": {
                pid: float(process.kinetics_model.counts_mature[i])
                for i, pid in enumerate(process.protein_ids)
            }
        },
        "complex": {"counts": {"RIBOSOME_70S": active}},
    }


def _run_ordered_m3(order: tuple[str, str]) -> np.ndarray:
    kinetics = tl.load_default()
    base_inputs = tl_v2.load_default()
    shifted_mrna = base_inputs.mrna_counts.copy()
    shifted_mrna[0] *= 1.5
    shifted_inputs = replace(base_inputs, mrna_counts=shifted_mrna)

    all_processes = {
        "proc_a": KarrTranslationV3Process(
            {"kinetics_model": kinetics, "mechanism_inputs": base_inputs}
        ),
        "proc_b": KarrTranslationV3Process(
            {"kinetics_model": kinetics, "mechanism_inputs": shifted_inputs}
        ),
    }

    processes = {name: all_processes[name] for name in order}
    topology = {
        name: {
            "protein": ("protein",),
            "substrates": ("substrates",),
            "complex": ("complex",),
        }
        for name in order
    }

    engine = Engine(
        processes=processes,
        topology=topology,
        emit_step=1.0,
        display_info=False,
    )
    engine.update(1.0)
    ts = engine.emitter.get_timeseries()
    return np.array([float(ts["protein"]["counts"][pid][-1]) for pid in kinetics.protein_wcm_ids])


def test_delta_equals_v2_absolute() -> None:
    kinetics = tl.load_default()
    mechanism_inputs = tl_v2.load_default()

    v2 = KarrTranslationV2Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )
    v3 = KarrTranslationV3Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )

    state = _make_m3_state(v2)
    prior = np.array([float(state["protein"]["counts"][pid]) for pid in v2.protein_ids])

    update_v2 = v2.next_update(1.0, state)
    update_v3 = v3.next_update(1.0, state)

    v2_abs = np.array([float(update_v2["protein"]["counts"][pid]) for pid in v2.protein_ids])
    v3_delta = np.array([float(update_v3["protein"]["counts"][pid]) for pid in v3.protein_ids])

    np.testing.assert_allclose(prior + v3_delta, v2_abs, rtol=0.0, atol=1e-9)


def test_schema_only_accumulate() -> None:
    schema = KarrTranslationV3Process({}).ports_schema()

    for leaf in schema["protein"]["counts"].values():
        assert leaf["_updater"] == "accumulate"

    updaters = set(_collect_updaters(schema))
    assert "set" not in updaters


def test_order_insensitivity() -> None:
    ab = _run_ordered_m3(("proc_a", "proc_b"))
    ba = _run_ordered_m3(("proc_b", "proc_a"))
    np.testing.assert_allclose(ab, ba, rtol=0.0, atol=1e-9)


def test_substrate_delta_unchanged() -> None:
    kinetics = tl.load_default()
    mechanism_inputs = tl_v2.load_default()
    v2 = KarrTranslationV2Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )
    v3 = KarrTranslationV3Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )

    state = _make_m3_state(v2)
    update_v2 = v2.next_update(1.0, state)
    update_v3 = v3.next_update(1.0, state)

    assert update_v2["substrates"]["ALA"] == pytest.approx(-56.53433442828094)
    assert update_v2["substrates"]["GLY"] == pytest.approx(-46.88127639605819)
    assert update_v3["substrates"]["ALA"] == pytest.approx(update_v2["substrates"]["ALA"])
    assert update_v3["substrates"]["GLY"] == pytest.approx(update_v2["substrates"]["GLY"])
