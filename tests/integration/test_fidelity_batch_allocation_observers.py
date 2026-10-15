"""Observer canaries on the four real evolution owners, not mocked transitions."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "vivarium"))

import _rna_fidelity_helpers as rna
import test_karr_protein_modification_fidelity as pm
import test_karr_protein_processing_ii_fidelity as pp2
from opencell.vivarium.karr_protein_modification import (
    KarrProteinModificationEvolutionStep,
    KarrProteinModificationRequestProcess,
)
from opencell.vivarium.karr_protein_processing_ii import (
    KarrProteinProcessingIIEvolutionStep,
    KarrProteinProcessingIIProcess,
)
from opencell.vivarium.karr_rna_modification import KarrRNAModificationEvolutionStep
from opencell.vivarium.karr_rna_processing import KarrRNAProcessingEvolutionStep
from scripts.l2_4_verify_conservation import ConservationCollector, evaluate_tick_part_b
from scripts.run_chassis_v6_32400t import DiagnosticCollector


def _prepared(family):
    processes = {}
    if family == "PP2":
        owner = KarrProteinProcessingIIProcess({})
        step = KarrProteinProcessingIIEvolutionStep({"processing_process": owner})
        state = pp2._state()
        pp2._precursor(state, int(pp2._indices("lipoproteinMonomerIndexs")[0]), 1)
        pp2._grant(state, owner, 1000)
        name = owner.name + "_evolution"
    elif family == "PM":
        owner = KarrProteinModificationRequestProcess({})
        step = KarrProteinModificationEvolutionStep({"modification_process": owner})
        state = pm._state()
        counts = np.zeros(len(pm._model().unmodified))
        counts[pm._model().active[0]] = 1
        pm._put_precursors(state, counts)
        pm._supply(state, counts)
        # The Step delegates to this registered Process; count only the outer call.
        processes[owner.name] = owner
        name = owner.name + "_evolution"
    else:
        rp, rm, _, state = rna.pathway()
        if family == "RM":
            step = KarrRNAModificationEvolutionStep({})
            counts = np.zeros(len(step.processed_rna_wids))
            mapping, _, _ = rna.modification_requirements()
            counts[np.flatnonzero(np.any(mapping != 0, axis=0))[0]] = 1
            rna.seed_modification(state, rm, counts)
        else:
            step = KarrRNAProcessingEvolutionStep({})
            counts = np.zeros(len(step.unprocessed_rna_wids))
            counts[rna.processing_indices("rRNA")[0]] = 1
            rna.seed_processing(state, rp, counts)
        owner = step
        name = owner.name
    state["phase"] = {"request_ready": True}
    topology = {port: (port,) for port in step.ports_schema()}
    composite = SimpleNamespace(
        processes=processes,
        steps={name: step},
        topology={key: topology for key in (*processes, name)},
    )
    return composite, step, owner.name, name, state


@pytest.mark.parametrize("family", ["PP2", "PM", "RM", "RP"])
@pytest.mark.parametrize("observer", ["conservation", "diagnostic"])
@pytest.mark.parametrize("mode", ["positive", "overspend", "missing-leaf", "unknown-owner"])
def test_real_owner_at_use_grants_and_fail_closed_canaries(family, observer, mode, tmp_path):
    composite, step, owner, registration, state = _prepared(family)
    original = step.next_update
    if mode == "unknown-owner":
        step.allocation_owner = "unknown_consuming_phase"
    if mode in {"overspend", "missing-leaf"}:
        missing = next(w for w, value in state["substrates_allocated"][owner].items() if value > 0)
        if mode == "missing-leaf":
            del state["substrates_allocated"][owner][missing]

        def faulty_update(dt, states):
            update = original(dt, states)
            if mode == "missing-leaf":
                # Deliberately corrupt the real public return, not the accounting.
                update.setdefault("substrates", {})[missing] = -1.0
            else:
                wid = next(w for w, delta in update["substrates"].items() if delta < 0)
                update["substrates"][wid] = -(states["substrates_allocated"][owner][wid] + 1)
            return update

        step.next_update = faulty_update
    if observer == "conservation":
        collector = ConservationCollector(composite=composite, seed=0)
    else:
        collector = DiagnosticCollector(
            composite=composite, process_traces_dir=tmp_path, process_trace_stride=1, seed=0
        )
    collector.set_tick(1)
    update = step.next_update(1.0, state)
    actual = {wid: float(value) for wid, value in update["substrates"].items() if value != 0}
    assert any(value < 0 for value in actual.values()), "real owner path was not exercised"
    assert dict(collector.per_tick_process_sums) == actual, "nested evolution double accounting"
    accounting_owner = "unknown_consuming_phase" if mode == "unknown-owner" else owner
    if observer == "conservation":
        deltas = {name: dict(values) for name, values in collector.per_tick_process_wid_deltas.items()}
        assert deltas == {accounting_owner: actual}
    else:
        collector.close()
        trace_name = accounting_owner if accounting_owner in composite.processes else registration
        with (tmp_path / f"{trace_name}.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        deltas = {accounting_owner: {
            row["substrate"]: float(row["delta"])
            for row in rows if row["substrate"] in actual
        }}
        assert deltas == {accounting_owner: actual}
        assert all(row["process_name"] == accounting_owner for row in rows)
    # Stale, pre-update grants are all zero; only the actual Step input can pass.
    grants = {owner: dict.fromkeys(state["substrates"], 0.0)}
    grants.update(collector.per_tick_allocations_at_use)
    result = evaluate_tick_part_b(
        seed=0, tick=1, after=dict.fromkeys(state["substrates"], 1000.0),
        proc_deltas=deltas, substrates_allocated=grants,
    )
    if mode == "positive":
        assert not result.failures
        assert any(value > 0 for value in grants[owner].values())
    else:
        assert any(
            failure.failure_kind == "over_allocation"
            and failure.process_name == accounting_owner
            for failure in result.failures
        )
    collector.set_tick(2)
    assert not collector.per_tick_allocations_at_use
