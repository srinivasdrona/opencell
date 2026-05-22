from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from vivarium.core.engine import Engine

from opencell.m2 import transcription as tx
from opencell.m2 import transcription_v2 as tx_v2
from opencell.vivarium.karr_m2_v2 import KarrTranscriptionV2Process
from opencell.vivarium.karr_m2_v3 import KarrTranscriptionV3Process


def _collect_updaters(node):
    if isinstance(node, dict):
        updater = node.get("_updater")
        if updater is not None:
            yield updater
        for value in node.values():
            yield from _collect_updaters(value)


def _make_m2_state(process: KarrTranscriptionV2Process, n_active_rnap: float | None = None):
    active = (
        float(process.mechanism_inputs.n_active_rnap)
        if n_active_rnap is None
        else float(n_active_rnap)
    )
    return {
        "rna": {
            "counts": {
                gid: float(process.kinetics_model.counts_mature[i, 1])
                for i, gid in enumerate(process.gene_ids)
            }
        },
        "complex": {"counts": {"RNA_POLYMERASE": active}},
    }


def _run_ordered_m2(order: tuple[str, str]) -> np.ndarray:
    kinetics = tx.calibrated_chassis_model(tx.load_default())
    base_inputs = tx_v2.load_default()
    shifted_p_bind = base_inputs.p_bind_bare.copy()
    shifted_p_bind[0] *= 1.5
    shifted_inputs = replace(base_inputs, p_bind_bare=shifted_p_bind)

    all_processes = {
        "proc_a": KarrTranscriptionV3Process(
            {"kinetics_model": kinetics, "mechanism_inputs": base_inputs}
        ),
        "proc_b": KarrTranscriptionV3Process(
            {"kinetics_model": kinetics, "mechanism_inputs": shifted_inputs}
        ),
    }

    processes = {name: all_processes[name] for name in order}
    topology = {
        name: {
            "rna": ("rna",),
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
    return np.array([float(ts["rna"]["counts"][gid][-1]) for gid in kinetics.gene_wcm_ids])


def test_delta_equals_v2_absolute() -> None:
    kinetics = tx.calibrated_chassis_model(tx.load_default())
    mechanism_inputs = tx_v2.load_default()

    v2 = KarrTranscriptionV2Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )
    v3 = KarrTranscriptionV3Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )

    state = _make_m2_state(v2)
    prior = np.array([float(state["rna"]["counts"][gid]) for gid in v2.gene_ids])

    update_v2 = v2.next_update(1.0, state)
    update_v3 = v3.next_update(1.0, state)

    v2_abs = np.array([float(update_v2["rna"]["counts"][gid]) for gid in v2.gene_ids])
    v3_delta = np.array([float(update_v3["rna"]["counts"][gid]) for gid in v3.gene_ids])

    np.testing.assert_allclose(prior + v3_delta, v2_abs, rtol=0.0, atol=1e-9)


def test_schema_only_accumulate() -> None:
    schema = KarrTranscriptionV3Process({}).ports_schema()

    for leaf in schema["rna"]["counts"].values():
        assert leaf["_updater"] == "accumulate"

    updaters = set(_collect_updaters(schema))
    assert "set" not in updaters


def test_order_insensitivity() -> None:
    ab = _run_ordered_m2(("proc_a", "proc_b"))
    ba = _run_ordered_m2(("proc_b", "proc_a"))
    np.testing.assert_allclose(ab, ba, rtol=0.0, atol=1e-9)


def test_substrate_delta_unchanged() -> None:
    kinetics = tx.calibrated_chassis_model(tx.load_default())
    mechanism_inputs = tx_v2.load_default()
    v2 = KarrTranscriptionV2Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )
    v3 = KarrTranscriptionV3Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )

    state = _make_m2_state(v2)
    update_v2 = v2.next_update(1.0, state)
    update_v3 = v3.next_update(1.0, state)

    assert update_v2["substrates"]["ATP"] == pytest.approx(-437.49999999999994)
    assert update_v2["substrates"]["GTP"] == pytest.approx(-437.49999999999994)
    assert update_v3["substrates"]["ATP"] == pytest.approx(update_v2["substrates"]["ATP"])
    assert update_v3["substrates"]["GTP"] == pytest.approx(update_v2["substrates"]["GTP"])
