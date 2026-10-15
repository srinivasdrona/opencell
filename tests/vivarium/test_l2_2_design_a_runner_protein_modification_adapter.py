"""Source-only PM Design-A adapter contracts, not a registered N50 gate.

The fixture and captured BEFORE vectors are authorities. Expected synthetic
chemistry is S @ R @ protein_flux, never replay states_after or SUT helpers.
Design-A 2.2/4.1 uses an independent validation seed per (seed, tick), unlike
the separately retained persistent exact-replay diagnostic.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest
from scipy.io import loadmat

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import _l2_2_design_a_runner_helpers as helpers
import l2_2_design_a_runner as runner

from opencell.vivarium.protein_state import COMPARTMENTS, MIGRATED_WIDS

_PM = "ProteinModification"


@cache
def _fixture():
    return loadmat(
        str(_ROOT / "data" / "karr_fixtures" / "per_process" / "ProteinModification_flat.mat"),
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture


def _indices(name: str) -> np.ndarray:
    return np.asarray(getattr(_fixture(), name), dtype=int).reshape(-1) - 1


def _payload() -> dict[str, Any]:
    f = _fixture()
    return {
        "substrate_wids": list(map(str, f.substrateWholeCellModelIDs)),
        "enzyme_wids": list(map(str, f.enzymeWholeCellModelIDs)),
        "monomer_wids": list(map(str, f.unmodifiedMonomerWholeCellModelIDs))
        + list(map(str, f.modifiedMonomerWholeCellModelIDs)),
        "oracle_before_substrates": np.zeros(len(f.substrateWholeCellModelIDs)),
        "oracle_before_enzymes": np.zeros(len(f.enzymeWholeCellModelIDs)),
        "oracle_before_bound_enzymes": np.zeros(len(f.enzymeWholeCellModelIDs)),
        "oracle_before_monomers": np.zeros(
            len(f.unmodifiedMonomerWholeCellModelIDs) + len(f.modifiedMonomerWholeCellModelIDs)
        ),
    }


def _home(i: int) -> str:
    comp = COMPARTMENTS[int(_fixture().monomerCompartments[i]) - 1]
    return {"tc": "c", "tm": "m"}.get(comp, comp)


def _full_forms(state: dict[str, Any]) -> np.ndarray:
    result = []
    for field, form, wids in (
        ("unmodified_counts", "folded", _fixture().unmodifiedMonomerWholeCellModelIDs),
        ("modified_counts", "mature", _fixture().modifiedMonomerWholeCellModelIDs),
    ):
        result.extend(
            state["protein"]["compartment_counts"][form][str(wid)][_home(i)]
            if str(wid) in MIGRATED_WIDS
            else state["protein"][field][str(wid)]
            for i, wid in enumerate(wids)
        )
    return np.asarray(result)


def _assert_runtime_input(process, runtime, payload) -> None:
    f = _fixture()
    full_n = len(f.unmodifiedMonomerWholeCellModelIDs)
    unmodified, enzymes = process.live_inputs(runtime)
    np.testing.assert_array_equal(
        unmodified, payload["oracle_before_monomers"][:full_n][_indices("monomerIndexs_modified")]
    )
    np.testing.assert_array_equal(enzymes, payload["oracle_before_enzymes"])
    np.testing.assert_array_equal(_full_forms(runtime), payload["oracle_before_monomers"])
    np.testing.assert_array_equal(
        [runtime["substrates"][wid] for wid in payload["substrate_wids"]],
        payload["oracle_before_substrates"],
    )
    np.testing.assert_array_equal(
        [runtime["substrates_allocated"][process.name][wid] for wid in payload["substrate_wids"]],
        payload["oracle_before_substrates"],
    )
    for i, wid in enumerate(payload["enzyme_wids"]):
        port = "protein" if i in _indices("enzymeMonomerLocalIndexs") else "complex"
        assert runtime[port]["counts"][wid] == payload["oracle_before_enzymes"][i]
    for field in ("unmodified_counts", "modified_counts"):
        assert not set(runtime["protein"][field]) & set(MIGRATED_WIDS)
    assert not any("oracle" in str(key) or "hint" in str(key) for key in runtime)


def _assert_same_payload(actual, before) -> None:
    for key in before:
        np.testing.assert_array_equal(actual[key], before[key], err_msg=key)


def test_all_seed0_before_inputs_reach_real_adapter_source_reader(monkeypatch) -> None:
    payload = _payload()
    original = helpers.KarrProteinModificationProcess.next_update
    seen = []

    def observe(self, timestep, runtime):
        _assert_runtime_input(self, runtime, payload)
        seen.append(self)
        return original(self, timestep, runtime)

    monkeypatch.setattr(helpers.KarrProteinModificationProcess, "next_update", observe)
    path = (
        _ROOT
        / "data"
        / "m1_sources"
        / "karr_native"
        / "per_process_traces_v2"
        / "ProteinModification_100ticks.mat"
    )
    with h5py.File(path, "r") as trace:
        assert int(np.asarray(trace["metadata/n_ticks"][()]).item()) == 100
        for tick in range(100):
            vectors = {
                obs: np.asarray(trace[trace["states_before"][obs][0, tick]][()]).reshape(-1)
                for obs in (
                    "substrates",
                    "enzymes",
                    "boundEnzymes",
                    "unmodifiedMonomers",
                    "modifiedMonomers",
                )
            }
            payload["oracle_before_substrates"] = vectors["substrates"]
            payload["oracle_before_enzymes"] = vectors["enzymes"]
            payload["oracle_before_bound_enzymes"] = vectors["boundEnzymes"]
            payload["oracle_before_monomers"] = np.concatenate(
                [vectors["unmodifiedMonomers"], vectors["modifiedMonomers"]]
            )
            before = deepcopy(payload)
            result = helpers.run_oc_tick(_PM, 0, tick, payload)
            assert set(result) == {"substrates", "monomers", "sample_seed"}
            assert result["substrates"].shape == payload["oracle_before_substrates"].shape
            assert result["monomers"].shape == payload["oracle_before_monomers"].shape
            _assert_same_payload(payload, before)
    assert len(seen) == 100
    assert len({id(process) for process in seen}) == 100


def _saturated_payload(i: int) -> tuple[dict[str, Any], np.ndarray]:
    f = _fixture()
    payload = _payload()
    flux = np.zeros(len(f.unmodifiedMonomerWholeCellModelIDs))
    flux[i] = 1
    full_n = len(flux)
    payload["oracle_before_monomers"][i] = 1
    payload["oracle_before_monomers"][full_n + i] = 7
    stoich = np.asarray(f.reactionStoichiometryMatrix)
    modification = np.asarray(f.reactionModificationMatrix)
    delta = stoich @ modification @ flux
    payload["oracle_before_substrates"] = np.maximum(0, -stoich) @ modification @ flux + 1
    enzyme_cols = _indices("speciesIndexs_enzymes")
    payload["oracle_before_enzymes"] = (
        np.ceil(np.max(np.asarray(f.speciesReactantMatrix)[:, enzyme_cols], axis=0)) + 1
    )
    return payload, delta


def _assert_complete_output(result, payload, i, delta, *, completed: bool = True) -> None:
    expected = payload["oracle_before_monomers"].copy()
    full_n = len(_fixture().unmodifiedMonomerWholeCellModelIDs)
    if completed:
        expected[i] -= 1
        expected[full_n + i] += 1
    np.testing.assert_array_equal(result["monomers"], expected)
    np.testing.assert_array_equal(result["substrates"], payload["oracle_before_substrates"] + delta)
    for channel in ("substrates", "monomers"):
        np.testing.assert_array_equal(result[channel], np.rint(result[channel]))


@pytest.mark.parametrize(
    "i",
    _indices("monomerIndexs_modified"),
    ids=[
        str(_fixture().unmodifiedMonomerWholeCellModelIDs[i])
        for i in _indices("monomerIndexs_modified")
    ],
)
def test_every_active_protein_projects_complete_actual_output(i) -> None:
    payload, delta = _saturated_payload(int(i))
    before = deepcopy(payload)
    result = helpers.run_oc_tick(_PM, 7, 3, payload)
    _assert_complete_output(result, payload, i, delta)
    _assert_same_payload(payload, before)


@pytest.mark.parametrize("migrated", [True, False], ids=["migrated", "nonmigrated"])
def test_actual_nonreacting_pass_through_is_not_input_identity(migrated: bool) -> None:
    f = _fixture()
    i = next(
        int(i)
        for i in _indices("monomerIndexs_notmodified")
        if (str(f.unmodifiedMonomerWholeCellModelIDs[i]) in MIGRATED_WIDS) == migrated
    )
    payload, _ = _saturated_payload(i)
    payload["oracle_before_substrates"][:] = 0
    payload["oracle_before_enzymes"][:] = 0
    result = helpers.run_oc_tick(_PM, 8, 4, payload)
    _assert_complete_output(result, payload, i, np.zeros_like(payload["oracle_before_substrates"]))


class _ForbiddenTargets(dict):
    def __getitem__(self, key) -> Any:
        if str(key).startswith("oracle_after") or key in {"trace_hint", "cached_target"}:
            raise AssertionError(f"PM adapter read a forbidden target: {key}")
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return default


@pytest.mark.parametrize("resources", [False, True], ids=["no-resource", "real-chemistry"])
def test_target_poison_cannot_supply_or_veto_adapter_outputs(resources: bool) -> None:
    i = int(_indices("monomerIndexs_modified")[0])
    payload, delta = _saturated_payload(i)
    if not resources:
        payload["oracle_before_substrates"][:] = 0
        payload["oracle_before_enzymes"][:] = 0
        delta[:] = 0
    poison = _ForbiddenTargets(payload)
    poison.update(
        {
            "oracle_after_substrates": np.full(len(payload["substrate_wids"]), 999_999),
            "oracle_after_monomers": np.full(len(payload["monomer_wids"]), 999_999),
            "oracle_after_all": object(),
            "oracle_after_by_channel": object(),
            "trace_hint": {"unmodifiedMonomers_next": object()},
            "cached_target": object(),
        }
    )
    with pytest.raises(AssertionError, match="forbidden target"):
        poison["oracle_after_monomers"]
    result = helpers.run_oc_tick(_PM, 9, 5, poison)
    _assert_complete_output(result, payload, i, delta, completed=resources)


def test_design_a_repeated_sample_ignores_mutated_process_cache(monkeypatch) -> None:
    i = int(_indices("monomerIndexs_modified")[0])
    payload, _ = _saturated_payload(i)
    payload["oracle_before_enzymes"][:] = 1
    seen = []
    original = helpers.KarrProteinModificationProcess.next_update
    expected_seed = None

    def observe(self, timestep, runtime):
        assert self.parameters["rng_seed"] == expected_seed
        for actual, expected in zip(
            self._rng.get_state(), np.random.RandomState(expected_seed).get_state(), strict=True
        ):
            np.testing.assert_array_equal(actual, expected)
        seen.append(self)
        return original(self, timestep, runtime)

    monkeypatch.setattr(helpers.KarrProteinModificationProcess, "next_update", observe)
    outputs, seeds = [], []
    for seed, tick in ((7, 53), (7, 53), (7, 54), (8, 53)):
        expected_seed = int(
            np.random.SeedSequence([helpers.L2_2_VALIDATION_SEED, seed, tick]).generate_state(
                1, dtype=np.uint32
            )[0]
        )
        cached = helpers._protein_modification_process(expected_seed)
        cached._rng.random(100)
        result = helpers.run_oc_tick(_PM, seed, tick, payload)
        assert seen[-1] is not cached
        assert result["sample_seed"] == expected_seed
        outputs.append(result)
        seeds.append(result["sample_seed"])
    assert seeds[0] == seeds[1]
    assert len(set(seeds)) == 3
    assert len({id(process) for process in seen}) == 4
    for channel in ("substrates", "monomers"):
        np.testing.assert_array_equal(outputs[0][channel], outputs[1][channel])


def test_registered_pm_channel_shape_and_gate_contract_are_unchanged() -> None:
    entry = runner._process_catalog_entry(_PM)
    assert entry["bucket"] == "ALGORITHMIC_SHALLOW"
    assert (entry["N_seeds"], entry["M_ticks"]) == (50, 100)
    assert runner._process_primary_channel(_PM) == "monomers"
    assert runner._process_output_channels(_PM) == ("substrates", "monomers")
    sample = helpers._protein_modification_process(0)
    wids = runner._observable_wids(_PM, sample)
    assert wids["monomers"] == _payload()["monomer_wids"]
    assert len(wids["monomers"]) == 2 * len(_fixture().unmodifiedMonomerWholeCellModelIDs)
    assert len(wids["substrates"]) == len(_fixture().substrateWholeCellModelIDs)
