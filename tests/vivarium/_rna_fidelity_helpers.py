"""Independent fixture projections for bounded RNA fidelity contracts.

No F-trace outputs are read. Resource/precursor interventions below are synthetic
inputs, not claims about the default chassis. RNAProcessing's existing
``processed::`` disambiguation is shared by both processes; mature RNA lives in
``modified_counts``. No second RNA authority is introduced.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache

import numpy as np
from scipy.io import loadmat
from vivarium.core.engine import Engine

from opencell.vivarium.karr_composite import build_karr_chassis_v5, build_karr_chassis_v6
from opencell.vivarium.karr_request_calculators import RequestCalculatorRNAPathway
from opencell.vivarium.karr_rna_modification import KarrRNAModificationProcess
from opencell.vivarium.karr_rna_processing import KarrRNAProcessingProcess


@lru_cache
def fixture(name):
    return loadmat(f"data/karr_fixtures/per_process/{name}_flat.mat", simplify_cells=True)["data"][
        "fixture"
    ]


def wids(fx, key):
    return [str(wid) for wid in np.atleast_1d(fx[key])]


def processed_keys():
    fx = fixture("RNAProcessing")
    nascent = set(wids(fx, "unprocessedRNAWholeCellModelIDs"))
    return [
        f"processed::{wid}" if wid in nascent else wid
        for wid in wids(fx, "processedRNAWholeCellModelIDs")
    ]


def live_enzymes(state, fx, values):
    """Split by MATLAB's actual monomer/complex local indices, not OC metadata."""
    ids = wids(fx, "enzymeWholeCellModelIDs")
    for field, store in (
        ("enzymeMonomerLocalIndexs", "protein"),
        ("enzymeComplexLocalIndexs", "complex"),
    ):
        for index in np.atleast_1d(fx[field]).astype(int) - 1:
            state[store]["counts"][ids[index]] = float(values[index])


def blank_state(rp, rm):
    ids = set(wids(fixture("RNAProcessing"), "unprocessedRNAWholeCellModelIDs"))
    ids.update(processed_keys())
    all_mature = wids(fixture("RNAModification"), "modifiedRNAWholeCellModelIDs")
    state = {
        "substrates": {wid: 0.0 for wid in set(rp.substrate_wids + rm.substrate_wids)},
        "rna": {
            "counts": dict.fromkeys(ids, 0.0),
            "modified_counts": dict.fromkeys(all_mature, 0.0),
        },
        "protein": {"counts": {}},
        "complex": {"counts": {}},
        "requests": {},
        "substrates_allocated": {},
    }
    for proc, name in ((rp, "RNAProcessing"), (rm, "RNAModification")):
        fx = fixture(name)
        live_enzymes(state, fx, np.zeros(len(wids(fx, "enzymeWholeCellModelIDs"))))
        for channel in ("requests", "substrates_allocated"):
            state[channel][proc.name] = dict.fromkeys(proc.substrate_wids, 0.0)
    return state


def pathway(dt=1.0):
    rp = KarrRNAProcessingProcess({"time_step": dt})
    rm = KarrRNAModificationProcess({"time_step": dt})
    calc = RequestCalculatorRNAPathway({"rna_processing_proc": rp, "rna_modification_proc": rm})
    return rp, rm, calc, blank_state(rp, rm)


def vector(mapping, keys):
    return np.asarray([mapping.get(key, 0.0) for key in keys])


def exact_counts(actual, expected):
    actual = np.asarray(actual)
    assert np.array_equal(actual, np.rint(actual)), "non-integral emitted molecule delta"
    np.testing.assert_array_equal(actual, expected)


def modification_requirements(dt=1.0):
    fx = fixture("RNAModification")
    mapping = np.asarray(fx["reactionModificationMatrix"], dtype=float)
    stoich = np.asarray(fx["reactionStoichiometryMatrix"], dtype=float)
    catalysis = np.asarray(fx["reactionCatalysisMatrix"], dtype=float)
    enzyme_req = mapping.T @ (catalysis / (fx["enzymeBounds"][:, [1]] * dt))
    return mapping, stoich, enzyme_req


def seed_modification(state, proc, counts, dt=1.0, enzyme_scale=1.0):
    fx = fixture("RNAModification")
    mapping, stoich, enzyme_req = modification_requirements(dt)
    state["rna"]["counts"].update(zip(processed_keys(), map(float, counts), strict=True))
    # Sum individual reactant requirements, not net cancellation between RNAs.
    substrates = np.maximum(0, -stoich) @ mapping @ counts
    enzymes = np.ceil(enzyme_req.T @ counts * enzyme_scale) + 1
    live_enzymes(state, fx, enzymes)
    state["substrates"].update(zip(proc.substrate_wids, map(float, substrates), strict=True))
    state["substrates_allocated"][proc.name].update(
        zip(proc.substrate_wids, map(float, substrates), strict=True)
    )
    return substrates, enzymes


def assert_modification_output(update, flux):
    fx = fixture("RNAModification")
    mapping, stoich, _ = modification_requirements()
    expected_sub = stoich @ mapping @ flux
    exact_counts(
        vector(update.get("substrates", {}), wids(fx, "substrateWholeCellModelIDs")), expected_sub
    )
    exact_counts(vector(update.get("rna", {}).get("counts", {}), processed_keys()), -flux)
    exact_counts(
        vector(
            update.get("rna", {}).get("modified_counts", {}),
            wids(fx, "modifiedRNAWholeCellModelIDs"),
        ),
        flux,
    )
    assert set(update) <= {"substrates", "rna"}, "unexpected ownership/writeback"
    assert set(update.get("substrates", {})) <= set(wids(fx, "substrateWholeCellModelIDs"))
    assert set(update.get("rna", {})) <= {"counts", "modified_counts"}
    assert set(update.get("rna", {}).get("counts", {})) <= set(processed_keys())
    assert set(update.get("rna", {}).get("modified_counts", {})) <= set(
        wids(fx, "modifiedRNAWholeCellModelIDs")
    )


class UniformInputs:
    """Only random INPUTS: never computes fluxes or substitutes expected outputs."""

    def __init__(self, scalar=0.99, array=0.99, order=(0, 1, 2, 3)) -> None:
        self.scalar = scalar
        self.array = array
        self.order = np.asarray(order)
        self.calls = []

    def random(self, size=None):
        self.calls.append(("random", size))
        return self.scalar if size is None else np.full(size, self.array)

    def permutation(self, size):
        self.calls.append(("permutation", size))
        assert size == len(self.order)
        return self.order.copy()

    def integers(self, low, high):
        self.calls.append(("integers", (low, high)))
        return low + int(self.scalar * (high - low))


def builder(version):
    result = (build_karr_chassis_v5 if version == 5 else build_karr_chassis_v6)(
        time_step_s=1.0, emit_step_s=1.0
    )
    if version == 5:
        return {
            "processes": result.processes,
            "steps": result.steps,
            "flow": result.flow,
            "topology": result.topology,
            "state": result.initial_state,
        }
    return result


def production_slice(composite, process_name, state):
    """Retain genuine builder objects, registrations, topology and dependency closure.

    Remove other biology and request branches, never promote a Process to a Step,
    add ordering edges, pre-run evolution, or seed allocations from requests.
    """
    request_name = "request_calculator_rna_pathway"
    allocation_name = "karr_allocation_step"
    keep = {request_name, allocation_name, process_name}
    flow = composite["flow"]
    changed = True
    while changed:
        old = set(keep)
        for key, deps in flow.items():
            if key in keep:
                keep.update(dep[0] for dep in deps)
            # Preserve source-registered evolution steps for this process, if added.
            if process_name in key:
                keep.add(key)
        changed = keep != old
    all_components = composite["processes"] | composite["steps"]
    for key, component in all_components.items():
        if getattr(component, "_proc", None) is all_components[process_name]:
            keep.add(key)
    # The allocator's unrelated request dependencies are absent in this bounded slice.
    keep = {key for key in keep if not key.startswith("request_calculator_") or key == request_name}
    processes = {key: proc for key, proc in composite["processes"].items() if key in keep}
    steps = {key: step for key, step in composite["steps"].items() if key in keep}
    return Engine(
        processes=processes,
        steps=steps,
        flow={
            key: [dep for dep in deps if dep[0] in keep]
            for key, deps in flow.items()
            if key in keep
        },
        topology={
            key: deepcopy(composite["topology"][key])
            for key in keep
            if key in composite["topology"]
        },
        initial_state=deepcopy(state),
        display_info=False,
        emit_step=1.0,
    )
