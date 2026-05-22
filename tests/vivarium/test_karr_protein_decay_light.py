from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from scipy.io import loadmat

from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess


class _FixedPoissonRng:
    def __init__(self, draw: list[int] | np.ndarray) -> None:
        self._draw = np.asarray(draw, dtype=np.int64).ravel()

    def poisson(self, lam: np.ndarray) -> np.ndarray:
        lam = np.asarray(lam, dtype=np.float64)
        if self._draw.size == 1:
            return np.full(lam.shape, int(self._draw[0]), dtype=np.int64)
        if self._draw.size != lam.size:
            raise ValueError(f"draw size {self._draw.size} != lambda size {lam.size}")
        return self._draw.reshape(lam.shape).astype(np.int64)


def _build_state(
    process: ProteinDecayLightProcess, complex_counts: dict[str, float] | None = None
) -> dict[str, Any]:
    complex_counts = complex_counts or {}
    return {
        "complex": {
            "counts": {
                wid: float(complex_counts.get(wid, 0.0)) for wid in process.complex_wids
            }
        },
        "substrates": {wid: 0.0 for wid in process.substrate_wids},
        "protein": {"counts": {wid: 0.0 for wid in process.protein_wids}},
        "rna": {"counts": {wid: 0.0 for wid in process.rna_wids}},
        "requests": {"karr_protein_decay_light": {"ATP": 0.0, "H2O": 0.0}},
        "substrates_allocated": {"karr_protein_decay_light": {"ATP": 0.0, "H2O": 0.0}},
    }


@pytest.fixture(scope="module")
def default_process() -> ProteinDecayLightProcess:
    return ProteinDecayLightProcess({})


def test_fixture_loads(default_process: ProteinDecayLightProcess) -> None:
    assert 0 < len(default_process.complex_wids) <= 147
    assert default_process.complex_decay_reactions.shape[1] == len(default_process.complex_wids)
    assert default_process.complex_decay_reactions.shape[0] == len(default_process.substrate_wids)
    assert default_process.protein_complex_monomer_composition.shape == (
        len(default_process.protein_wids),
        len(default_process.complex_wids),
    )
    assert default_process.protein_complex_rna_composition.shape == (
        len(default_process.rna_wids),
        len(default_process.complex_wids),
    )


def test_no_complexes_no_decay(default_process: ProteinDecayLightProcess) -> None:
    process = ProteinDecayLightProcess(
        {
            "complex_wid_filter": default_process.complex_wids[:4],
            "rng_seed": 9,
        }
    )
    process._rng = _FixedPoissonRng([999])
    update = process.next_update(1.0, _build_state(process))

    assert update.get("complex", {}).get("counts", {}) == {}
    assert update.get("substrates", {}) == {}
    assert update.get("protein", {}).get("counts", {}) == {}
    assert update.get("rna", {}).get("counts", {}) == {}
    assert update["requests"]["karr_protein_decay_light"]["ATP"] == 0.0
    assert update["requests"]["karr_protein_decay_light"]["H2O"] == 0.0


def test_deterministic_poisson(default_process: ProteinDecayLightProcess) -> None:
    subset = default_process.complex_wids[:6]
    process_1 = ProteinDecayLightProcess({"complex_wid_filter": subset, "rng_seed": 12345})
    process_2 = ProteinDecayLightProcess({"complex_wid_filter": subset, "rng_seed": 12345})

    counts = {wid: float(10 + i) for i, wid in enumerate(subset)}
    update_1 = process_1.next_update(1.0, _build_state(process_1, counts))
    update_2 = process_2.next_update(1.0, _build_state(process_2, counts))
    assert update_1 == update_2


def test_mass_conservation_per_complex(default_process: ProteinDecayLightProcess) -> None:
    total_subunits = (
        default_process.protein_complex_monomer_composition.sum(axis=0)
        + default_process.protein_complex_rna_composition.sum(axis=0)
    )
    idx = int(np.where(total_subunits > 0)[0][0])
    wid = default_process.complex_wids[idx]
    process = ProteinDecayLightProcess({"complex_wid_filter": [wid]})

    n_complex = 7
    process._rng = _FixedPoissonRng([10_000])
    update = process.next_update(1.0, _build_state(process, {wid: float(n_complex)}))

    assert update["complex"]["counts"][wid] == float(-n_complex)

    expected_protein = process.protein_complex_monomer_composition[:, 0] * n_complex
    expected_rna = process.protein_complex_rna_composition[:, 0] * n_complex

    for i, protein_wid in enumerate(process.protein_wids):
        if expected_protein[i] != 0:
            assert update["protein"]["counts"][protein_wid] == float(expected_protein[i])
    for i, rna_wid in enumerate(process.rna_wids):
        if expected_rna[i] != 0:
            assert update["rna"]["counts"][rna_wid] == float(expected_rna[i])


def test_atp_h2o_accounting(default_process: ProteinDecayLightProcess) -> None:
    fixture = loadmat(
        "data/karr_fixtures/per_process/ProteinDecay_flat.mat",
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture
    states = np.asarray(fixture.states, dtype=object).ravel()
    protein_complex_state = [
        state
        for state in states
        if getattr(state, "x_class_", "") == "edu.stanford.covert.cell.sim.state.ProteinComplex"
    ][0]
    all_complex_wids = np.asarray(
        protein_complex_state.wholeCellModelIDs, dtype=object
    ).ravel().astype(str)
    all_complex_decay_reactions = np.asarray(fixture.complexDecayReactions, dtype=np.int64)
    atp_idx = int(fixture.substrateIndexs_atp) - 1
    idx = int(np.where(all_complex_decay_reactions[atp_idx] != 0)[0][0])
    wid = str(all_complex_wids[idx])

    process = ProteinDecayLightProcess({"complex_wid_filter": [wid]})

    n_decay = 3
    process._rng = _FixedPoissonRng([10_000])
    update = process.next_update(1.0, _build_state(process, {wid: float(n_decay)}))

    expected_sub = process.complex_decay_reactions[:, 0] * n_decay
    atp_wid = process.substrate_wids[process.substrate_index_atp]
    h2o_wid = process.substrate_wids[process.substrate_index_water]

    assert update["substrates"][atp_wid] == float(expected_sub[process.substrate_index_atp])
    if expected_sub[process.substrate_index_water] != 0:
        assert update["substrates"][h2o_wid] == float(expected_sub[process.substrate_index_water])
    else:
        assert h2o_wid not in update["substrates"]
    req = update["requests"]["karr_protein_decay_light"]
    assert req["ATP"] == float(abs(expected_sub[process.substrate_index_atp]))
    assert req["H2O"] == float(abs(expected_sub[process.substrate_index_water]))


def test_requests_state_derived(default_process: ProteinDecayLightProcess) -> None:
    subset = default_process.complex_wids[:3]
    process = ProteinDecayLightProcess({"complex_wid_filter": subset})

    process._rng = _FixedPoissonRng([100, 1, 100])
    counts = {subset[0]: 2.0, subset[1]: 5.0, subset[2]: 0.0}
    update = process.next_update(1.0, _build_state(process, counts))

    n_decay = np.asarray([2, 1, 0], dtype=np.int64)
    expected_sub = process.complex_decay_reactions @ n_decay
    expected_atp = float(abs(expected_sub[process.substrate_index_atp]))
    expected_h2o = float(abs(expected_sub[process.substrate_index_water]))

    req = update["requests"]["karr_protein_decay_light"]
    assert req["ATP"] == expected_atp
    assert req["H2O"] == expected_h2o


def test_bounded_by_counts(default_process: ProteinDecayLightProcess) -> None:
    subset = default_process.complex_wids[:4]
    process = ProteinDecayLightProcess({"complex_wid_filter": subset})
    process._rng = _FixedPoissonRng([10_000])

    counts = {subset[0]: 1.0, subset[1]: 0.0, subset[2]: 3.0, subset[3]: 2.0}
    update = process.next_update(1.0, _build_state(process, counts))

    deltas = update.get("complex", {}).get("counts", {})
    for wid in subset:
        have = int(round(float(counts[wid])))
        observed_decay = int(round(float(-deltas.get(wid, 0.0))))
        assert 0 <= observed_decay <= have
        if have > 0:
            assert observed_decay == have


def test_integration_with_d2_real() -> None:
    pytest.importorskip("opencell.vivarium.karr_d2_real")
    process = ProteinDecayLightProcess({})
    assert 0 < len(process.complex_wids) <= 147
