"""PP2-only Design-A source-input and anti-laundering adapter regressions.

ProteinProcessingII.m:199-268 owns processed-I/II and cytosolic signals;
Process.m:611-670 owns live mature enzymes. Catalog outputs remain the local
substrate vector and unprocessed-monomer vector, not a six-compartment cube.
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

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import _l2_2_design_a_runner_helpers as runner_helpers
from l2_replay_common import cell_vector, resolve_trace_path

from opencell.vivarium.protein_state import MIGRATED_WIDS


@cache
def _fixture() -> Any:
    return loadmat(
        _REPO_ROOT / "data/karr_fixtures/per_process/ProteinProcessingII_flat.mat",
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture


def _indices(name: str) -> np.ndarray:
    return np.atleast_1d(getattr(_fixture(), name)).astype(int) - 1


def _payload(mode: str = "active") -> dict[str, Any]:
    """Synthetic demand-limited lipo1/secreted1/non-target2; fixture enzymes/rates."""
    fx = _fixture()
    monomer_wids = list(map(str, fx.unprocessedMonomerWholeCellModelIDs))
    monomers = np.zeros(len(monomer_wids))
    monomers[int(_indices("lipoproteinMonomerIndexs")[0])] = 1
    monomers[int(_indices("secretedMonomerIndexs")[0])] = 1
    non_target = next(int(i) for i in _indices("unprocessedMonomerIndexs") if monomer_wids[int(i)] not in MIGRATED_WIDS)
    monomers[non_target] = 2
    substrates = np.zeros(len(fx.substrateWholeCellModelIDs))
    substrates[int(fx.substrateIndexs_water) - 1] = monomers[
        np.concatenate((_indices("lipoproteinMonomerIndexs"), _indices("secretedMonomerIndexs")))
    ].sum()
    substrates[int(fx.substrateIndexs_PG160) - 1] = monomers[_indices("lipoproteinMonomerIndexs")].sum()
    enzymes = np.asarray(fx.enzymes, dtype=float).reshape(-1)
    if mode == "zero_enzymes":
        enzymes = np.zeros_like(enzymes)
    if mode == "zero_grant":
        substrates[:] = 0
    return {
        "substrate_wids": list(map(str, fx.substrateWholeCellModelIDs)),
        "enzyme_wids": list(map(str, fx.enzymeWholeCellModelIDs)),
        "monomer_wids": monomer_wids,
        "oracle_before_substrates": substrates,
        "oracle_before_enzymes": enzymes,
        "oracle_before_monomers": monomers,
    }


@pytest.fixture
def captured_updates(monkeypatch: Any) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []
    process_type = runner_helpers.KarrProteinProcessingIIProcess
    original = process_type.next_update

    def observed(process: Any, timestep: float, state: dict[str, Any]) -> dict[str, Any]:
        assert "trace_hint" not in state
        assert not any(key.startswith("oracle_after") for key in state)
        precursors, enzymes = process.read_processing_inputs(state)
        captured.append({
            "runtime": deepcopy(state), "precursors": precursors.copy(), "enzymes": enzymes.copy(),
        })
        return original(process, timestep, state)

    monkeypatch.setattr(process_type, "next_update", observed)
    return captured


@pytest.mark.parametrize("axis", ["precursors", "enzymes"])
def test_ppii_design_a_projects_inputs_into_the_actual_source_reader(
    captured_updates: list[dict[str, Any]], axis: str,
) -> None:
    payload = _payload()
    runner_helpers._run_protein_processing_ii_tick(seed=13, tick=4, state=payload)
    assert len(captured_updates) == 1
    expected = payload["oracle_before_monomers" if axis == "precursors" else "oracle_before_enzymes"]
    np.testing.assert_array_equal(captured_updates[0][axis], expected)
    protein = captured_updates[0]["runtime"]["protein"]
    assert not set(protein.get("counts", {})) & set(payload["monomer_wids"])
    assert all(value == 0 for value in protein["enzyme_counts"].values())


@pytest.mark.parametrize("mode", ["active", "zero_enzymes", "zero_grant"])
def test_ppii_design_a_preserves_local_vector_dimensions_and_source_response(mode: str) -> None:
    payload = _payload(mode)
    before = deepcopy(payload)
    result = runner_helpers._run_protein_processing_ii_tick(seed=13, tick=4, state=payload)
    assert result["substrates"].shape == payload["oracle_before_substrates"].shape
    assert result["monomers"].shape == payload["oracle_before_monomers"].shape
    expected_monomers = payload["oracle_before_monomers"].copy()
    expected_monomers[_indices("unprocessedMonomerIndexs")] = 0
    expected_substrates = payload["oracle_before_substrates"].copy()
    if mode == "active":
        fx = _fixture()
        enzymes = payload["oracle_before_enzymes"]
        peptidase = np.concatenate((_indices("lipoproteinMonomerIndexs"), _indices("secretedMonomerIndexs")))
        cleavages = float(expected_monomers[peptidase].sum())
        transfers = float(expected_monomers[_indices("lipoproteinMonomerIndexs")].sum())
        assert enzymes[int(fx.enzymeIndexs_signalPeptidase) - 1] * fx.lipoproteinSignalPeptidaseSpecificRate * fx.stepSizeSec >= cleavages
        assert enzymes[int(fx.enzymeIndexs_diacylglycerylTransferase) - 1] * fx.lipoproteinDiacylglycerylTransferaseSpecificRate * fx.stepSizeSec >= transfers
        expected_monomers[peptidase] = 0
        expected_substrates[int(fx.substrateIndexs_water) - 1] -= cleavages
        expected_substrates[int(fx.substrateIndexs_PG160) - 1] -= transfers
        expected_substrates[int(fx.substrateIndexs_SNGLYP) - 1] += transfers
        expected_substrates[int(fx.substrateIndexs_hydrogen) - 1] += transfers
    np.testing.assert_array_equal(result["substrates"], expected_substrates)
    np.testing.assert_array_equal(result["monomers"], expected_monomers)
    np.testing.assert_array_equal(result["substrates"], np.rint(result["substrates"]))
    np.testing.assert_array_equal(result["monomers"], np.rint(result["monomers"]))
    assert result["sample_seed"] == runner_helpers._sample_seed(13, 4)
    for key in ("oracle_before_substrates", "oracle_before_enzymes", "oracle_before_monomers"):
        np.testing.assert_array_equal(payload[key], before[key])


class _NoAfterReads(dict[str, Any]):
    def __getitem__(self, key: str) -> Any:
        assert not key.startswith("oracle_after") and key != "trace_hint", key
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        assert not key.startswith("oracle_after") and key != "trace_hint", key
        return super().get(key, default)


def test_ppii_design_a_rejects_answer_reads_and_ignores_poisoned_hints(
    captured_updates: list[dict[str, Any]],
) -> None:
    payload = _payload()
    results = []
    for poison in (111, 222):  # Deliberately synthetic, different from the real source response.
        state = _NoAfterReads(payload)
        state["oracle_after_substrates"] = np.full_like(payload["oracle_before_substrates"], poison)
        state["oracle_after_monomers"] = np.full_like(payload["oracle_before_monomers"], poison)
        state["trace_hint"] = {"monomers_next": poison}
        results.append(runner_helpers._run_protein_processing_ii_tick(seed=13, tick=4, state=state))
    assert len(captured_updates) == 2
    for channel in ("substrates", "monomers"):
        np.testing.assert_array_equal(results[0][channel], results[1][channel])
        assert not np.all(results[0][channel] == 111)
        assert not np.all(results[0][channel] == 222)


def test_ppii_design_a_captured_before_inputs_reach_public_update(
    captured_updates: list[dict[str, Any]],
) -> None:
    payload = _payload()
    peptidase = np.concatenate((_indices("lipoproteinMonomerIndexs"), _indices("secretedMonomerIndexs")))
    with h5py.File(resolve_trace_path("ProteinProcessingII"), "r") as trace:
        n_ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        tick = next(
            tick for tick in range(n_ticks)
            if np.any(cell_vector(trace, "states_before", "unprocessedMonomers", tick)[peptidase] > 0)
        )
        for target, observable in (
            ("oracle_before_substrates", "substrates"),
            ("oracle_before_enzymes", "enzymes"),
            ("oracle_before_monomers", "unprocessedMonomers"),
        ):
            payload[target] = cell_vector(trace, "states_before", observable, tick)
    result = runner_helpers._run_protein_processing_ii_tick(seed=0, tick=tick, state=payload)
    assert len(captured_updates) == 1
    np.testing.assert_array_equal(captured_updates[0]["precursors"], payload["oracle_before_monomers"])
    np.testing.assert_array_equal(captured_updates[0]["enzymes"], payload["oracle_before_enzymes"])
    assert result["monomers"].shape == payload["oracle_before_monomers"].shape
