"""One existing physical complex-stock counterexample, not future C2 biology.

ProteinComplex.m:101-120 and MoleculeCountState.m:86-92 define mature rows
and count * row MW / Avogadro. The current D2 seed reads these exact counts;
PT reads the same complex.counts stock. A one-particle UNIT increment must
reach all three live mass readers without counting aliases/activity views.
"""

from copy import deepcopy

import numpy as np
import pytest
import test_cohort1_shared_mass_projection_contract as frozen
from scipy.constants import Avogadro
from vivarium.core.engine import Engine

from opencell.analysis.cell_mass import compute_cell_mass
from opencell.vivarium.karr_composite import build_karr_chassis_v6
from opencell.vivarium.karr_observability_step import KarrObservabilityStep
from scripts.run_chassis_v6_32400t import MassEstimator


@pytest.fixture(scope="module")
def physical_stock():
    c = frozen.contract.__wrapped__()
    fx = frozen.rna_inputs.fixture("ProteinComplex")
    ids = frozen.rna_inputs.wids(fx, "wholeCellModelIDs")
    rows = np.atleast_1d(fx["matureIndexs"]).astype(int) - 1
    wid = "MG_072_DIMER"
    row = next(int(row) for row in rows if ids[row] == wid)
    home = int(np.asarray(fx["compartments"]).reshape(-1)[row]) - 1
    seed = float(np.asarray(fx["counts"])[row, home])
    mw = float(np.asarray(fx["molecularWeights"]).reshape(-1)[row])
    pt = frozen.rna_inputs.fixture("ProteinTranslocation")
    enzymes = frozen.rna_inputs.wids(pt, "enzymeWholeCellModelIDs")
    complex_enzymes = {
        enzymes[i] for i in np.atleast_1d(pt["enzymeComplexLocalIndexs"]).astype(int) - 1
    }
    assert wid in complex_enzymes and seed > 0 and mw > 0
    assert c["base"]["complex"]["counts"][wid] == seed
    assert wid not in c["protein_forms"]["mature"] and wid not in c["substrate"]
    production = build_karr_chassis_v6(
        m1_model=c["models"][0], m2_model=c["models"][1], m3_model=c["models"][2],
        time_step_s=1.0, emit_step_s=1.0, enable_pool_replenishment=False,
    )
    return c, wid, mw / Avogadro, production


@pytest.mark.parametrize("reader", ("helper", "observer", "csv"))
def test_existing_source_complex_particle_changes_full_state_mass(reader, physical_stock, record_property):
    c, wid, source_delta, production = physical_stock
    before = deepcopy(c["base"])
    before["rna"] = deepcopy(c["cases"]["mixed_forms"])
    monomer_alias = next(key for key in c["protein_forms"]["mature"]
                         if key not in frozen.rna_inputs.wids(
                             frozen.rna_inputs.fixture("ProteinComplex"), "wholeCellModelIDs"))
    before["complex"]["counts"].update({
        "not_a_source_complex": float("nan"), monomer_alias: float("nan"),
    })
    before["complex"]["activity"] = {wid: float("nan")}
    before["complex"]["enzyme_counts"] = {wid: float("nan")}
    after = deepcopy(before)
    after["complex"]["counts"][wid] += 1.0  # UNIT input, not a natural trajectory claim.
    totals = []
    for state in (before, after):
        original = deepcopy(state)
        if reader == "helper":
            total = compute_cell_mass(state, *c["models"]).total_g
        elif reader == "csv":
            total = MassEstimator.build(*c["models"]).dry_mass_g(state)
        else:
            registered = production.steps["karr_observability_step"]
            assert type(registered) is KarrObservabilityStep
            observer = type(registered)(dict(registered.parameters))
            engine = Engine(
                steps={"karr_observability_step": observer},
                topology={"karr_observability_step": deepcopy(
                    production.topology["karr_observability_step"])},
                initial_state=deepcopy(state), display_info=False,
            )
            engine.update(1.0)
            total = engine.state.get_value()["phenotype_observables"]["cell_dry_mass_g"]
        np.testing.assert_equal(state, original)
        assert np.isfinite(total), "unknown/monomer aliases and activity views are not new particles"
        totals.append(total)
    actual_delta = totals[1] - totals[0]
    record_property("source_particle", wid)
    record_property("source_particle_delta_g", source_delta)
    record_property("actual_reader_delta_g", actual_delta)
    record_property("existing_unmerged_nascent_store", "nascent_counts" in before["complex"])
    # Subtracting two full-cell floats costs ~1e-11 relative precision for
    # one particle; abs=0 still rejects the current entirely missing mass.
    assert actual_delta == pytest.approx(source_delta, rel=1e-9, abs=0)
