from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pytest
from vivarium.core.engine import Engine

from opencell.m3 import translation as tl
from opencell.m3 import translation_v2 as tl_v2
from opencell.vivarium.karr_translation_v2 import KarrTranslationV2Process
from opencell.vivarium.karr_translation_v3 import KarrTranslationV3Process


def _collect_updaters(node):
    if isinstance(node, dict):
        updater = node.get("_updater")
        if updater is not None:
            yield updater
        for value in node.values():
            yield from _collect_updaters(value)


def _make_m3_state(
    process: KarrTranslationV2Process | KarrTranslationV3Process,
    n_active_ribosomes: float | None = None,
    substrate_wids: tuple[str, ...] | None = None,
    substrate_level: float = 0.0,
):
    active = (
        float(process.mechanism_inputs.n_active_ribosomes)
        if n_active_ribosomes is None
        else float(n_active_ribosomes)
    )
    state = {
        "protein": {
            "counts": {
                pid: float(process.kinetics_model.counts_mature[i])
                for i, pid in enumerate(process.protein_ids)
            }
        },
        "complex": {"counts": {"RIBOSOME_70S": active}},
    }
    if substrate_wids is not None:
        state["substrates"] = {wid: float(substrate_level) for wid in substrate_wids}
    return state


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
    deltas = []
    unproc = ts.get("protein", {}).get("unprocessed_counts", {})
    nascent = ts.get("protein", {}).get("compartment_counts", {}).get("nascent", {})
    for pid in kinetics.protein_wcm_ids:
        if pid in unproc and len(unproc[pid]) > 0:
            deltas.append(float(unproc[pid][-1]))
        elif pid in nascent and "c" in nascent[pid] and len(nascent[pid]["c"]) > 0:
            deltas.append(float(nascent[pid]["c"][-1]))
        else:
            deltas.append(0.0)
    return np.array(deltas)


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

    def _extract_v3_delta(update: dict[str, Any], pid: str) -> float:
        prot = update.get("protein", {})
        unproc = prot.get("unprocessed_counts", {})
        if pid in unproc:
            return float(unproc[pid])
        nascent = prot.get("compartment_counts", {}).get("nascent", {})
        if pid in nascent:
            return float(nascent[pid].get("c", 0.0))
        return 0.0

    v3_delta = np.array(
        [_extract_v3_delta(update_v3, pid) for pid in v3.protein_ids]
    )
    expected_v3 = KarrTranslationV3Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )
    expected_delta = np.array(
        [
            float(expected_v3._stochastic_round_delta(float(v2_abs[i] - prior[i])))
            for i in range(len(v3.protein_ids))
        ]
    )

    np.testing.assert_array_equal(v3_delta, expected_delta)


def test_schema_only_accumulate() -> None:
    process = KarrTranslationV3Process({})
    schema = process.ports_schema()

    for leaf in schema["protein"]["unprocessed_counts"].values():
        assert leaf["_updater"] == "accumulate"

    updaters = set(_collect_updaters(schema))
    assert "set" not in updaters
    assert len(process.aa_ids) == 20
    assert process.substrate_wids == (
        "ALA",
        "ARG",
        "ASN",
        "ASP",
        "CYS",
        "GLN",
        "GLU",
        "GLY",
        "HIS",
        "ILE",
        "LEU",
        "LYS",
        "MET",
        "PHE",
        "PRO",
        "SER",
        "THR",
        "TRP",
        "TYR",
        "VAL",
        "FMET",
        "GTP",
        "GDP",
        "PI",
        "H2O",
        "H",
    )
    assert process.allocation_substrate_wids == (
        "ALA",
        "ARG",
        "ASN",
        "ASP",
        "CYS",
        "GLN",
        "GLU",
        "GLY",
        "HIS",
        "ILE",
        "LEU",
        "LYS",
        "MET",
        "PHE",
        "PRO",
        "SER",
        "THR",
        "TRP",
        "TYR",
        "VAL",
        "GTP",
        "H2O",
    )
    assert len(schema["substrates"]) == 26
    assert tuple(schema["substrates"]) == process.substrate_wids


def test_order_insensitivity() -> None:
    ab = _run_ordered_m3(("proc_a", "proc_b"))
    ba = _run_ordered_m3(("proc_b", "proc_a"))
    np.testing.assert_allclose(ab, ba, rtol=0.0, atol=1e-9)


def test_substrate_deltas_emit_faithful_energy_cycle() -> None:
    kinetics = tl.load_default()
    mechanism_inputs = tl_v2.load_default()
    v3 = KarrTranslationV3Process(
        {"kinetics_model": kinetics, "mechanism_inputs": mechanism_inputs}
    )

    state = _make_m3_state(v3, substrate_wids=v3.substrate_wids, substrate_level=1.0e9)
    update_v3 = v3.next_update(1.0, state)

    substrate_update = update_v3["substrates"]
    prot_update = update_v3.get("protein", {})
    unprocessed = prot_update.get("unprocessed_counts", {})
    nascent = prot_update.get("compartment_counts", {}).get("nascent", {})
    aa_consumed = sum(
        int(-substrate_update[aa])
        for aa in v3.aa_ids
        if aa in substrate_update and substrate_update[aa] < 0.0
    )
    n_proteins = sum(
        int(delta)
        for delta in unprocessed.values()
        if float(delta) > 0.0
    ) + sum(
        int(deltas.get("c", 0.0))
        for deltas in nascent.values()
        if float(deltas.get("c", 0.0)) > 0.0
    )
    expected_energy = 2 * aa_consumed + 3 * n_proteins

    assert aa_consumed > 0
    assert n_proteins > 0
    assert "FMET" not in substrate_update
    assert substrate_update["GTP"] == pytest.approx(-expected_energy)
    assert substrate_update["H2O"] == pytest.approx(-expected_energy)
    assert substrate_update["GDP"] == pytest.approx(expected_energy)
    assert substrate_update["PI"] == pytest.approx(expected_energy)
    assert substrate_update["H"] == pytest.approx(expected_energy)
