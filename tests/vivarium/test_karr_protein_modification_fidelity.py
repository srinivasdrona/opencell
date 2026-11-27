"""Source-observable PM readiness freeze; intentionally not an L2.5 gate.

Authorities: ProteinModification.m:198-222 (network/compartments), 227-287
(folded/mature views), 324-327 (request), 331-393 (evolution);
ProteinModification_flat.mat supplies every matrix, index, WID and rate.
No replay output, production delta helper, or repaired scheduling graph is
used as an expected-output source. Synthetic counts below are interventions,
not fitted biological parameters.
"""

from __future__ import annotations

import builtins
import sys
from copy import deepcopy
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest
from scipy.io import loadmat
from vivarium.core.engine import Engine

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if "opencell" in sys.modules:
    _loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _ROOT not in _loaded.parents:
        for _name in list(sys.modules):
            if _name == "opencell" or _name.startswith("opencell."):
                del sys.modules[_name]

from opencell.vivarium.karr_allocation_step import KarrAllocationStep
from opencell.vivarium.karr_composite import build_karr_chassis_v5, build_karr_chassis_v6
from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess
from opencell.vivarium.karr_protein_modification import KarrProteinModificationProcess
from opencell.vivarium.karr_protein_processing_i import KarrProteinProcessingIProcess
from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess
from opencell.vivarium.karr_protein_translocation import KarrProteinTranslocationProcess
from opencell.vivarium.karr_request_calculators import RequestCalculatorProteinPathway
from opencell.vivarium.protein_state import (
    COMPARTMENTS,
    FORMS,
    MIGRATED_WIDS,
    ProteinFlatProjectionWriteError,
)

_PM = "karr_protein_modification"
_REQUEST = "request_calculator_protein_pathway"


def _strings(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in np.asarray(value).reshape(-1))


@dataclass(frozen=True)
class _Model:
    substrates: tuple[str, ...]
    enzymes: tuple[str, ...]
    unmodified: tuple[str, ...]
    modified: tuple[str, ...]
    active: np.ndarray
    stoich: np.ndarray
    catalysis: np.ndarray
    modification: np.ndarray
    net_species: np.ndarray
    gross_species: np.ndarray
    enzyme_cols: np.ndarray
    monomer_enzymes: frozenset[int]
    complex_enzymes: frozenset[int]
    compartments: tuple[str, ...]
    dt: float


@cache
def _model() -> _Model:
    fx = loadmat(
        str(_ROOT / "data" / "karr_fixtures" / "per_process" / "ProteinModification_flat.mat"),
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture
    comps = [COMPARTMENTS[int(i) - 1] for i in fx.monomerCompartments]
    return _Model(
        substrates=_strings(fx.substrateWholeCellModelIDs),
        enzymes=_strings(fx.enzymeWholeCellModelIDs),
        unmodified=_strings(fx.unmodifiedMonomerWholeCellModelIDs),
        modified=_strings(fx.modifiedMonomerWholeCellModelIDs),
        active=np.asarray(fx.monomerIndexs_modified, dtype=int).reshape(-1) - 1,
        stoich=np.asarray(fx.reactionStoichiometryMatrix, dtype=float),
        catalysis=np.asarray(fx.reactionCatalysisMatrix, dtype=float),
        modification=np.asarray(fx.reactionModificationMatrix, dtype=float),
        net_species=np.asarray(fx.speciesReactantByproductMatrix, dtype=float),
        gross_species=np.asarray(fx.speciesReactantMatrix, dtype=float),
        enzyme_cols=np.asarray(fx.speciesIndexs_enzymes, dtype=int).reshape(-1) - 1,
        monomer_enzymes=frozenset(
            np.asarray(fx.enzymeMonomerLocalIndexs, dtype=int).reshape(-1) - 1
        ),
        complex_enzymes=frozenset(
            np.asarray(fx.enzymeComplexLocalIndexs, dtype=int).reshape(-1) - 1
        ),
        compartments=tuple({"tc": "c", "tm": "m"}.get(c, c) for c in comps),
        dt=float(fx.stepSizeSec),
    )


def _calculator(process: KarrProteinModificationProcess) -> RequestCalculatorProteinPathway:
    return RequestCalculatorProteinPathway(
        {
            "protein_processing_i_proc": KarrProteinProcessingIProcess({}),
            "protein_processing_ii_proc": KarrProteinProcessingIIProcess({}),
            "protein_modification_proc": process,
            "protein_folding_proc": KarrProteinFoldingProcess({}),
            "protein_translocation_proc": KarrProteinTranslocationProcess({}),
        }
    )


def _state() -> dict[str, Any]:
    m = _model()
    return {
        "substrates": dict.fromkeys(m.substrates, 0.0),
        "enzymes": dict.fromkeys(m.enzymes, 0.0),
        "boundEnzymes": dict.fromkeys(m.enzymes, 0.0),
        "unmodifiedMonomers": dict.fromkeys(m.unmodified, 0.0),
        "modifiedMonomers": dict.fromkeys(m.modified, 0.0),
        "protein": {
            "counts": {m.enzymes[i]: 0.0 for i in m.monomer_enzymes},
            "unmodified_counts": {wid: 0.0 for wid in m.unmodified if wid not in MIGRATED_WIDS},
            "modified_counts": {wid: 0.0 for wid in m.modified if wid not in MIGRATED_WIDS},
            "compartment_counts": {
                form: {wid: dict.fromkeys(COMPARTMENTS, 0.0) for wid in MIGRATED_WIDS}
                for form in FORMS
            },
        },
        "complex": {"counts": {m.enzymes[i]: 0.0 for i in m.complex_enzymes}},
        "requests": {_PM: dict.fromkeys(m.substrates, 0.0)},
        "substrates_allocated": {_PM: dict.fromkeys(m.substrates, 0.0)},
    }


def _put_precursors(state: dict[str, Any], counts: np.ndarray) -> None:
    m = _model()
    for i, wid in enumerate(m.unmodified):
        if wid in MIGRATED_WIDS:
            state["protein"]["compartment_counts"]["folded"][wid][m.compartments[i]] = float(
                counts[i]
            )
        else:
            state["protein"]["unmodified_counts"][wid] = float(counts[i])


def _put_enzymes(state: dict[str, Any], counts: np.ndarray) -> None:
    m = _model()
    for i, wid in enumerate(m.enzymes):
        store = state["complex"] if i in m.complex_enzymes else state["protein"]
        store["counts"][wid] = float(counts[i])


def _supply(state: dict[str, Any], flux: np.ndarray, *, dt: float = 1.0) -> None:
    m = _model()
    substrate_counts = np.maximum(0, -m.stoich) @ m.modification @ flux + 1
    enzyme_counts = np.ceil(m.gross_species[:, m.enzyme_cols].T @ flux[m.active] * m.dt / dt) + 1
    _put_enzymes(state, enzyme_counts)
    state["substrates"] = dict(zip(m.substrates, substrate_counts, strict=True))
    state["substrates_allocated"][_PM] = dict(state["substrates"])


def _leaves(tree: dict[str, Any], path: tuple[str, ...] = ()) -> dict[tuple[str, ...], float]:
    result: dict[tuple[str, ...], float] = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            result.update(_leaves(value, (*path, key)))
        else:
            number = float(value)
            assert np.isfinite(number), (*path, key, number)
            assert number == np.rint(number), (*path, key, number)
            result[(*path, key)] = number
    return result


def _expected_delta(flux: np.ndarray) -> dict[tuple[str, ...], float]:
    m = _model()
    expected = {
        ("substrates", wid): float(value)
        for wid, value in zip(m.substrates, m.stoich @ m.modification @ flux, strict=True)
    }
    for i, wid in enumerate(m.unmodified):
        if wid in MIGRATED_WIDS:
            for form, sign in (("folded", -1), ("mature", 1)):
                expected[("protein", "compartment_counts", form, wid, m.compartments[i])] = (
                    sign * float(flux[i])
                )
        else:
            expected[("protein", "unmodified_counts", wid)] = -float(flux[i])
            expected[("protein", "modified_counts", m.modified[i])] = float(flux[i])
    return expected


def _assert_delta(update: dict[str, Any], flux: np.ndarray) -> None:
    actual = _leaves(update)
    expected = _expected_delta(flux)
    assert set(actual) <= set(expected), f"Unexpected output leaves: {set(actual) - set(expected)}"
    assert {p: v for p, v in actual.items() if v} == {p: v for p, v in expected.items() if v}


def _run(
    process: KarrProteinModificationProcess, state: dict[str, Any], *, dt: float = 1.0
) -> dict[str, Any]:
    before = deepcopy(state)
    update = process.next_update(dt, state)
    assert state == before, "next_update mutated its input instead of returning deltas"
    return update


def _request_expected(counts: np.ndarray, enzymes: np.ndarray, dt: float) -> dict[str, float]:
    m = _model()
    # MATLAB 324-327: no kcat and no metabolite-availability term.
    reaction_demand = np.minimum(np.ceil(m.catalysis @ enzymes * dt), m.modification @ counts)
    return dict(zip(m.substrates, np.maximum(0, -m.stoich) @ reaction_demand, strict=True))


@pytest.mark.parametrize(
    ("copies", "enzyme", "configured_dt", "pool"),
    [
        (0, 7, 1, 19),
        (7, 0, 1, 19),
        (11, 1, 1, 19),
        (1, 11, 1, 19),
        (11, 0.25, 1, 19),
        (11, 0.25, 3, 19),
        (11, 0.25, 5, 19),
        (11, 1, 1, 0),
        (11, 1, 1, 1),
    ],
    ids=[
        "zero-demand",
        "zero-enzyme",
        "enzyme-limited",
        "demand-limited",
        "fractional-ceil",
        "nonunit-dt-below-one",
        "nonunit-dt-above-one",
        "no-availability-cap",
        "low-availability",
    ],
)
def test_request_exact_full_fixture_algebra(copies, enzyme, configured_dt, pool) -> None:
    m = _model()
    process = KarrProteinModificationProcess({"time_step": configured_dt})
    calc = _calculator(process)
    state = _state()
    counts = np.zeros(len(m.unmodified))
    counts[m.active] = copies
    enzymes = np.full(len(m.enzymes), enzyme)
    _put_precursors(state, counts)
    _put_enzymes(state, enzymes)
    state["substrates"] = dict.fromkeys(m.substrates, pool)
    before = deepcopy(state)
    rng_before = deepcopy(process._rng.get_state())
    update = calc.next_update(0.0, state)
    assert state == before
    for old, new in zip(rng_before, process._rng.get_state(), strict=True):
        np.testing.assert_array_equal(old, new)
    assert set(update) == {"requests"}
    assert update["requests"][_PM] == _request_expected(counts, enzymes, configured_dt)
    assert all(
        value == 0
        for name, request in update["requests"].items()
        if name != _PM
        for value in request.values()
    )


def test_request_is_not_substrate_availability_identity() -> None:
    m = _model()
    calc = _calculator(KarrProteinModificationProcess({}))
    state = _state()
    counts = np.zeros(len(m.unmodified))
    counts[m.active] = 1
    _put_precursors(state, counts)
    enzymes = np.ones(len(m.enzymes))
    _put_enzymes(state, enzymes)
    state["substrates"] = dict.fromkeys(m.substrates, 1)
    first = calc.next_update(1, state)["requests"][_PM]
    state["substrates"] = dict.fromkeys(m.substrates, len(m.active))
    second = calc.next_update(1, state)["requests"][_PM]
    assert first == second == _request_expected(counts, enzymes, m.dt)


@pytest.mark.parametrize(
    "active_idx", range(len(_model().active)), ids=[_model().unmodified[i] for i in _model().active]
)
def test_request_each_fixture_reaction_column_reaches_its_complete_substrate_vector(
    active_idx,
) -> None:
    m = _model()
    state = _state()
    counts = np.zeros(len(m.unmodified))
    counts[m.active[active_idx]] = 1
    _put_precursors(state, counts)
    _put_enzymes(state, np.ones(len(m.enzymes)))
    state["substrates"] = dict.fromkeys(m.substrates, 7)
    expected = _request_expected(counts, np.ones(len(m.enzymes)), m.dt)
    assert any(expected.values())
    assert (
        _calculator(KarrProteinModificationProcess({})).next_update(0, state)["requests"][_PM]
        == expected
    )


_MIGRATED_ACTIVE = tuple(
    _model().unmodified[i] for i in _model().active if _model().unmodified[i] in MIGRATED_WIDS
)


@pytest.mark.parametrize("wid", _MIGRATED_ACTIVE)
@pytest.mark.parametrize("shadow", [0, 19])
def test_request_reads_live_folded_authority_not_shadows(wid: str, shadow: int) -> None:
    m = _model()
    calc = _calculator(KarrProteinModificationProcess({}))
    state = _state()
    idx = m.unmodified.index(wid)
    counts = np.zeros(len(m.unmodified))
    counts[idx] = 1
    _put_precursors(state, counts)
    _put_enzymes(state, np.ones(len(m.enzymes)))
    state["protein"]["unmodified_counts"][wid] = shadow
    state["unmodifiedMonomers"][wid] = shadow
    for comp in COMPARTMENTS:
        if comp != m.compartments[idx]:
            state["protein"]["compartment_counts"]["folded"][wid][comp] = shadow
    expected = _request_expected(counts, np.ones(len(m.enzymes)), m.dt)
    assert calc.next_update(1, state)["requests"][_PM] == expected


@pytest.mark.parametrize("enzyme_idx", range(len(_model().enzymes)), ids=_model().enzymes)
@pytest.mark.parametrize("surface", ["request", "evolution"])
def test_request_and_evolution_share_live_enzyme_routes(enzyme_idx: int, surface: str) -> None:
    m = _model()
    state = _state()
    eligible = np.flatnonzero((m.modification.T @ m.catalysis)[:, enzyme_idx] > 0)
    assert eligible.size
    idx = int(eligible[0])
    counts = np.zeros(len(m.unmodified))
    counts[idx] = 1
    _put_precursors(state, counts)
    _supply(state, counts)
    enzyme_wid = m.enzymes[enzyme_idx]
    # A conflicting wrong store and local enzyme vector must not supply activity.
    right_store = state["complex"] if enzyme_idx in m.complex_enzymes else state["protein"]
    wrong_store = state["protein"] if enzyme_idx in m.complex_enzymes else state["complex"]
    amount = right_store["counts"][enzyme_wid]
    right_store["counts"][enzyme_wid] = 0
    wrong_store["counts"][enzyme_wid] = amount
    state["enzymes"][enzyme_wid] = amount
    state["boundEnzymes"][enzyme_wid] = amount
    process = KarrProteinModificationProcess({})
    if surface == "evolution":
        _assert_delta(_run(process, state), np.zeros_like(counts))
    else:
        assert _calculator(process).next_update(1, state)["requests"][_PM] == dict.fromkeys(
            m.substrates, 0
        )
    right_store["counts"][enzyme_wid] = amount
    wrong_store["counts"][enzyme_wid] = 0
    state["enzymes"][enzyme_wid] = 0
    state["boundEnzymes"][enzyme_wid] = 0
    enzyme_counts = np.zeros(len(m.enzymes))
    enzyme_counts[enzyme_idx] = amount
    if surface == "evolution":
        _assert_delta(_run(KarrProteinModificationProcess({}), state), counts)
    else:
        assert _calculator(process).next_update(1, state)["requests"][_PM] == _request_expected(
            counts, enzyme_counts, m.dt
        )


def test_request_engine_exposes_declared_live_inputs() -> None:
    m = _model()
    calc = _calculator(KarrProteinModificationProcess({}))
    state = _state()
    counts = np.zeros(len(m.unmodified))
    counts[m.unmodified.index(_MIGRATED_ACTIVE[0])] = 1
    _put_precursors(state, counts)
    _put_enzymes(state, np.ones(len(m.enzymes)))
    seen: list[dict[str, Any]] = []
    original = calc.next_update

    def record(timestep, states):
        seen.append(deepcopy(states))
        return original(timestep, states)

    calc.next_update = record
    engine = Engine(
        steps={_REQUEST: calc},
        topology={_REQUEST: {p: (p,) for p in calc.ports_schema()}},
        initial_state=state,
        display_info=False,
    )
    try:
        assert seen
        observed_folded = seen[-1]["protein"].get("compartment_counts", {}).get("folded", {})
        for wid in _MIGRATED_ACTIVE:
            comp = m.compartments[m.unmodified.index(wid)]
            assert (
                observed_folded.get(wid, {}).get(comp)
                == state["protein"]["compartment_counts"]["folded"][wid][comp]
            )
        for i, wid in enumerate(m.enzymes):
            port = "complex" if i in m.complex_enzymes else "protein"
            assert seen[-1].get(port, {}).get("counts", {}).get(wid) == 1
        assert engine.state.get_value()["requests"][_PM] == _request_expected(
            counts, np.ones(len(m.enzymes)), m.dt
        )
    finally:
        engine.end()


@pytest.mark.parametrize(
    "active_idx", range(len(_model().active)), ids=[_model().unmodified[i] for i in _model().active]
)
def test_every_active_protein_full_output_and_reaction_projection(active_idx: int) -> None:
    m = _model()
    counts = np.zeros(len(m.unmodified))
    counts[m.active[active_idx]] = 3
    state = _state()
    _put_precursors(state, counts)
    _supply(state, counts)
    _assert_delta(_run(KarrProteinModificationProcess({}), state), counts)


@pytest.mark.parametrize("wid", _MIGRATED_ACTIVE)
def test_evolution_migrated_shadows_and_wrong_compartments_cannot_supply_precursor(wid) -> None:
    m = _model()
    counts = np.zeros(len(m.unmodified))
    idx = m.unmodified.index(wid)
    counts[idx] = 3
    state = _state()
    _supply(state, counts)
    state["protein"]["unmodified_counts"][wid] = 3
    state["unmodifiedMonomers"][wid] = 3
    for comp in COMPARTMENTS:
        if comp != m.compartments[idx]:
            state["protein"]["compartment_counts"]["folded"][wid][comp] = 3
    _assert_delta(_run(KarrProteinModificationProcess({}), state), np.zeros_like(counts))
    _put_precursors(state, counts)
    _assert_delta(_run(KarrProteinModificationProcess({}), state), counts)


def test_pass_through_all_nonreacting_proteins_without_enzyme_or_grant() -> None:
    m = _model()
    counts = np.ones(len(m.unmodified))
    counts[m.active] = 0
    state = _state()
    _put_precursors(state, counts)
    _assert_delta(_run(KarrProteinModificationProcess({}), state), counts)


def test_pass_through_migrated_proteins_conserve_full_compartment_state() -> None:
    m = _model()
    counts = np.zeros(len(m.unmodified))
    for i, wid in enumerate(m.unmodified):
        if wid in MIGRATED_WIDS and i not in m.active:
            counts[i] = 1
    assert counts.sum() > 0
    state = _state()
    _put_precursors(state, counts)
    for wid in MIGRATED_WIDS:
        state["protein"]["compartment_counts"]["mature"][wid]["e"] = 7
    _assert_delta(_run(KarrProteinModificationProcess({}), state), counts)


@pytest.mark.parametrize("missing", ["grant", "enzyme", "precursor"])
def test_no_reaction_when_each_feasibility_input_is_absent(missing: str) -> None:
    m = _model()
    counts = np.zeros(len(m.unmodified))
    counts[m.active[0]] = 1
    state = _state()
    _put_precursors(state, counts)
    _supply(state, counts)
    if missing == "grant":
        state["substrates_allocated"][_PM] = dict.fromkeys(m.substrates, 0)
    elif missing == "enzyme":
        _put_enzymes(state, np.zeros(len(m.enzymes)))
    else:
        _put_precursors(state, np.zeros_like(counts))
    _assert_delta(_run(KarrProteinModificationProcess({}), state), np.zeros_like(counts))


def test_incomplete_multisite_modification_consumes_nothing() -> None:
    m = _model()
    costs = -(m.stoich @ m.modification)[m.substrates.index("ATP")]
    target = int(np.argmax(costs))
    assert costs[target] > 1
    counts = np.zeros(len(m.unmodified))
    counts[target] = 1
    state = _state()
    _put_precursors(state, counts)
    _supply(state, counts)
    state["substrates_allocated"][_PM]["ATP"] = float(costs[target] - 1)
    _assert_delta(_run(KarrProteinModificationProcess({}), state), np.zeros_like(counts))


@pytest.mark.parametrize(
    "resources", [False, True], ids=["impossible-completion", "veto-completion"]
)
def test_trace_hint_cannot_inject_or_veto_full_output(resources: bool) -> None:
    m = _model()
    counts = np.zeros(len(m.unmodified))
    counts[m.active[0]] = 1
    state = _state()
    _put_precursors(state, counts)
    if resources:
        _supply(state, counts)
    before_process = KarrProteinModificationProcess({"rng_seed": 13})
    hinted_process = KarrProteinModificationProcess({"rng_seed": 13})
    plain_update = _run(before_process, state)
    hinted = deepcopy(state)
    hinted["trace_hint"] = {
        "unmodifiedMonomers_next": {
            m.unmodified[i]: float(counts[i] if resources else 0) for i in m.active
        }
    }
    hinted_update = _run(hinted_process, hinted)
    _assert_delta(plain_update, counts if resources else np.zeros_like(counts))
    assert hinted_update == plain_update, "An output hint changed real production evolution"
    for plain, injected in zip(
        before_process._rng.get_state(), hinted_process._rng.get_state(), strict=True
    ):
        np.testing.assert_array_equal(plain, injected)


class _FixedDraws:
    """Test stream only: constant draws reveal weights/rounding without an output oracle."""

    def __init__(self, value: float) -> None:
        self.value = value
        self.calls = 0

    def random(self, size=None):
        self.calls += 1
        return self.value if size is None else np.full(size, self.value)


def _reference_flux(
    substrates: np.ndarray, enzymes: np.ndarray, unmodified: np.ndarray, draw: float, dt: float
) -> np.ndarray:
    """Bounded transcription of MATLAB 351-379 using fixture network matrices."""
    m = _model()
    net = m.net_species.copy()
    gross = m.gross_species.copy()
    net[:, m.enzyme_cols] *= m.dt / dt
    gross[:, m.enzyme_cols] *= m.dt / dt
    species = np.concatenate([substrates, enzymes, unmodified[m.active]]).astype(float)
    other_cols = np.setdiff1d(np.arange(species.size), m.enzyme_cols)

    def limits(requirements, cols):
        with np.errstate(divide="ignore", invalid="ignore"):
            quotients = species[cols][None, :] / requirements[:, cols]
        return np.min(np.where(np.isnan(quotients), np.inf, quotients), axis=1)

    initial = limits(gross, np.arange(species.size))
    inactive = (~np.isfinite(initial)) | (initial <= 0)
    flux = np.zeros(len(m.unmodified))
    # Each selected protein consumes one precursor; this bound is not a production cap.
    for _ in range(int(unmodified.sum()) + 1):
        required = np.maximum(0, net)
        enzyme_limit = limits(required, m.enzyme_cols)
        with np.errstate(invalid="ignore"):
            rounded = np.floor(enzyme_limit) + (draw < np.mod(enzyme_limit, 1))
        weights = np.minimum(rounded, limits(required, other_cols))
        weights[inactive | ~np.isfinite(weights) | (weights < 1)] = 0
        if not np.any(weights):
            return flux
        selected = int(np.searchsorted(np.cumsum(weights), draw * weights.sum(), side="right"))
        flux[m.active[selected]] += 1
        species -= net[selected]
    raise AssertionError("Source reference exceeded its precursor-derived termination bound")


@pytest.mark.parametrize("draw", [0.125, 0.875], ids=["low-draw", "high-draw"])
@pytest.mark.parametrize("dt", [0.5, 2.0])
def test_stochastic_feasibility_weighted_loop_matches_fixture_reference(draw, dt) -> None:
    m = _model()
    counts = np.zeros(len(m.unmodified))
    # Different multi-site ATP costs make selection observable under a shared finite grant.
    atp_row = m.substrates.index("ATP")
    costs = -(m.stoich @ m.modification)[atp_row, m.active]
    candidates = np.flatnonzero(costs > 0)
    cheap, expensive = (
        candidates[np.argmin(costs[candidates])],
        candidates[np.argmax(costs[candidates])],
    )
    counts[m.active[[cheap, expensive]]] = [3, 2]
    state = _state()
    _put_precursors(state, counts)
    _supply(state, counts, dt=dt)
    state["substrates_allocated"][_PM]["ATP"] = float(costs[expensive] + costs[cheap])
    substrates = np.array([state["substrates_allocated"][_PM][wid] for wid in m.substrates])
    # Small integer enzyme counts force stochastic rounding of kinetic capacity.
    enzymes = np.ones(len(m.enzymes))
    enzymes[m.catalysis[:, :].sum(axis=0) > 0] = np.ceil(
        np.max(m.gross_species[:, m.enzyme_cols], axis=0) * m.dt / dt
    )
    _put_enzymes(state, enzymes)
    expected = _reference_flux(substrates, enzymes, counts, draw, dt)
    assert 0 < expected.sum() < counts.sum(), "Synthetic witness did not exercise competition"
    stream = _FixedDraws(draw)
    process = KarrProteinModificationProcess({})
    process._rng = stream
    _assert_delta(_run(process, state, dt=dt), expected)
    assert stream.calls > 0, "The real stochastic path was not exercised"


@pytest.mark.parametrize("draw", [0.0, 0.999], ids=["round-up", "round-down"])
def test_fractional_kinetic_capacity_is_stochastically_rounded_not_deterministic(draw) -> None:
    m = _model()
    counts = np.zeros(len(m.unmodified))
    counts[m.active[0]] = 1
    state = _state()
    _put_precursors(state, counts)
    _supply(state, counts)
    enzymes = np.ones(len(m.enzymes))
    _put_enzymes(state, enzymes)
    substrate_counts = np.array([state["substrates_allocated"][_PM][wid] for wid in m.substrates])
    expected = _reference_flux(substrate_counts, enzymes, counts, draw, m.dt)
    assert expected.sum() == (1 if draw == 0 else 0)
    process = KarrProteinModificationProcess({})
    process._rng = _FixedDraws(draw)
    _assert_delta(_run(process, state), expected)


@pytest.mark.parametrize("mutation", ["stale-grant", "duplicate-evolution"])
def test_full_output_verifier_rejects_real_stale_grant_and_duplicate_execution(mutation) -> None:
    m = _model()
    counts = np.zeros(len(m.unmodified))
    counts[m.active[0]] = 1
    state = _state()
    _put_precursors(state, counts)
    _supply(state, counts)
    _assert_delta(_run(KarrProteinModificationProcess({}), state), counts)
    if mutation == "stale-grant":
        stale = deepcopy(state)
        stale["substrates_allocated"][_PM] = dict.fromkeys(m.substrates, 0)
        observed = _run(KarrProteinModificationProcess({}), stale)
    else:
        first = _run(KarrProteinModificationProcess({}), state)
        second = _run(KarrProteinModificationProcess({}), state)
        combined = _leaves(first)
        for path, value in _leaves(second).items():
            combined[path] = combined.get(path, 0) + value
        observed = {}
        for path, value in combined.items():
            branch = observed
            for part in path[:-1]:
                branch = branch.setdefault(part, {})
            branch[path[-1]] = value
    with pytest.raises(AssertionError):
        _assert_delta(observed, counts)


def test_iteration_budget_cannot_silently_truncate_a_feasible_tick() -> None:
    m = _model()
    counts = np.zeros(len(m.unmodified))
    counts[m.active[0]] = 3
    state = _state()
    _put_precursors(state, counts)
    _supply(state, counts)
    _assert_delta(
        _run(KarrProteinModificationProcess({"max_stochastic_iterations": 1}), state), counts
    )


def test_evolution_needs_no_files_and_is_not_tick_targeted(monkeypatch) -> None:
    m = _model()
    counts = np.zeros(len(m.unmodified))
    counts[m.active[0]] = 1
    state = _state()
    _put_precursors(state, counts)
    _supply(state, counts)
    processes = [KarrProteinModificationProcess({"rng_seed": 17}) for _ in range(3)]

    def forbidden(*args, **kwargs):
        raise AssertionError("Evolution tried to read a file after fixture initialization")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(h5py, "File", forbidden)
    monkeypatch.setitem(
        KarrProteinModificationProcess.next_update.__globals__, "loadmat", forbidden
    )
    for tick, process in zip((0, 49, 99), processes, strict=True):
        observed_state = deepcopy(state)
        observed_state.update({"tick": tick, "time": tick, "seed": tick})
        _assert_delta(_run(process, observed_state), counts)


def _production_slice(builder, monkeypatch):
    """Prune unrelated registrations/edges, never add or reorder a production edge."""
    source = builder(time_step_s=1, emit_step_s=1)
    if isinstance(source, Engine):
        processes, steps = dict(source.processes), dict(source.steps)
        topology, flow = deepcopy(source.topology), deepcopy(source.flow)
        source.end()
    else:
        processes, steps = dict(source.processes), dict(source.steps)
        topology, flow = deepcopy(source.topology), deepcopy(source.flow)
    selected = {
        key
        for key in set(processes) | set(steps)
        if "protein_modification" in key
        or key
        in {
            _REQUEST,
            "karr_allocation_step",
            "protein_flat_projection_pre",
            "protein_flat_projection_post",
        }
    }
    kept_processes = {key: obj for key, obj in processes.items() if key in selected}
    kept_steps = {key: obj for key, obj in steps.items() if key in selected}
    kept_flow = {
        key: [edge for edge in edges if edge and edge[0] in selected]
        for key, edges in flow.items()
        if key in selected
    }
    assert isinstance(kept_steps["karr_allocation_step"], KarrAllocationStep)
    assert isinstance(kept_steps[_REQUEST], RequestCalculatorProteinPathway)
    assert kept_steps[_REQUEST]._pm_proc is kept_processes[_PM]
    calls: list[dict[str, Any]] = []
    depth = 0

    def recorder(key, original):
        def record(timestep, states):
            nonlocal depth
            outermost = depth == 0
            depth += 1
            try:
                update = original(timestep, states)
            finally:
                depth -= 1
            if outermost:
                calls.append(
                    {
                        "key": key,
                        "dt": timestep,
                        "state": deepcopy(states),
                        "update": deepcopy(update),
                    }
                )
            return update

        return record

    for key, component in {**kept_processes, **kept_steps}.items():
        if "protein_modification" in key:
            monkeypatch.setattr(component, "next_update", recorder(key, component.next_update))
    return {
        "processes": kept_processes,
        "steps": kept_steps,
        "flow": kept_flow,
        "topology": {key: value for key, value in topology.items() if key in selected},
    }, calls


def _assert_biology(actual: dict[str, Any], before: dict[str, Any], flux: np.ndarray) -> None:
    """Full biological projection, including unchanged forms, compartments and shadows."""
    expected = deepcopy(before)
    for path, delta in _expected_delta(flux).items():
        if delta == 0:
            continue
        branch = expected
        for part in path[:-1]:
            branch = branch.setdefault(part, {})
        branch[path[-1]] = branch.get(path[-1], 0) + delta
    # Projection is the sole writer of these flat migrated leaves.
    for wid in MIGRATED_WIDS:
        expected["protein"]["counts"][wid] = sum(
            expected["protein"]["compartment_counts"]["mature"][wid].values()
        )

    def nonzero(tree):
        return {p: v for p, v in _leaves(tree).items() if v}

    assert nonzero(actual["substrates"]) == nonzero(expected["substrates"])
    for key in ("unmodified_counts", "modified_counts", "compartment_counts", "counts"):
        assert nonzero(actual["protein"][key]) == nonzero(expected["protein"][key]), key
        if key in {"unmodified_counts", "modified_counts"}:
            assert not set(actual["protein"][key]).intersection(MIGRATED_WIDS), key
    assert nonzero(actual["complex"]) == nonzero(expected["complex"])


@pytest.mark.parametrize(
    "builder", [build_karr_chassis_v5, build_karr_chassis_v6], ids=["v5", "v6"]
)
@pytest.mark.parametrize("enzyme_idx", [0, 2], ids=["monomer-enzyme", "complex-enzyme"])
def test_real_builder_same_tick_request_allocation_evolution(
    builder, monkeypatch, enzyme_idx
) -> None:
    m = _model()
    registration, calls = _production_slice(builder, monkeypatch)
    counts = np.zeros(len(m.unmodified))
    target = np.flatnonzero((m.modification.T @ m.catalysis)[:, enzyme_idx] > 0)[0]
    counts[target] = 1
    initial = _state()
    _supply(initial, counts)
    initial["substrates_allocated"][_PM] = dict.fromkeys(m.substrates, 0)
    engine = Engine(**registration, initial_state=initial, display_info=False)
    try:
        t0 = deepcopy(engine.state.get_value())
        _assert_biology(t0, t0, np.zeros_like(counts))
        assert all(value == 0 for value in t0["substrates_allocated"][_PM].values())
        assert not any(
            _leaves(call["update"]).get(path, 0)
            for call in calls
            for path in _expected_delta(counts)
        ), "Engine construction executed biological evolution"
        # Valid post-construction precursor intervention; no request/grant/output injection.
        for i in np.flatnonzero(counts):
            wid = m.unmodified[i]
            path = (
                ("protein", "compartment_counts", "folded", wid, m.compartments[i])
                if wid in MIGRATED_WIDS
                else ("protein", "unmodified_counts", wid)
            )
            engine.state.get_path(path).set_value(float(counts[i]))
        before = deepcopy(engine.state.get_value())
        calls.clear()
        engine.update(1)
        after = engine.state.get_value()
        _assert_biology(after, before, counts)
        enzymes = np.array(
            [
                before["complex" if i in m.complex_enzymes else "protein"]["counts"][wid]
                for i, wid in enumerate(m.enzymes)
            ]
        )
        assert after["requests"][_PM] == _request_expected(counts, enzymes, m.dt)
        # Sole nonzero consumer: Karr's uncapped proportional allocator grants the pool.
        request = _request_expected(counts, enzymes, m.dt)
        expected_grant = {
            wid: float(np.floor(request[wid] * before["substrates"][wid] / max(1, request[wid])))
            for wid in m.substrates
        }
        assert after["substrates_allocated"][_PM] == expected_grant
        biological_calls = [
            call
            for call in calls
            if any(_leaves(call["update"]).get(path, 0) for path in _expected_delta(counts))
        ]
        assert len(biological_calls) == 1, "Stale-grant or duplicate biological evolution"
        assert biological_calls[0]["state"]["substrates_allocated"][_PM] == expected_grant
        _assert_biology(engine.state.get_value(), before, counts)
        next_before = deepcopy(after)
        engine.update(1)
        next_after = engine.state.get_value()
        _assert_biology(next_after, next_before, np.zeros_like(counts))
        assert next_after["requests"][_PM] == dict.fromkeys(m.substrates, 0)
        assert next_after["substrates_allocated"][_PM] == dict.fromkeys(m.substrates, 0)
    finally:
        engine.end()


@pytest.mark.parametrize(
    "builder", [build_karr_chassis_v5, build_karr_chassis_v6], ids=["v5", "v6"]
)
def test_real_builder_init_preserves_live_precursor_without_evolving(builder, monkeypatch) -> None:
    m = _model()
    registration, _ = _production_slice(builder, monkeypatch)
    counts = np.zeros(len(m.unmodified))
    counts[m.active[0]] = 1
    initial = _state()
    _put_precursors(initial, counts)
    _supply(initial, counts)
    initial["substrates_allocated"][_PM] = dict.fromkeys(m.substrates, 0)
    engine = Engine(**registration, initial_state=initial, display_info=False)
    try:
        actual = engine.state.get_value()
        # Compare biology only: request/allocation bookkeeping at t0 is not evolution.
        for wid in MIGRATED_WIDS:
            initial["protein"]["counts"][wid] = 0
        expected = deepcopy(actual)
        for key in ("unmodified_counts", "modified_counts", "compartment_counts"):
            expected["protein"][key].update(initial["protein"][key])
        expected["substrates"].update(initial["substrates"])
        _assert_biology(actual, expected, np.zeros_like(counts))
    finally:
        engine.end()


def test_protected_flat_projection_rejects_an_actual_store_write() -> None:
    from opencell.vivarium.protein_flat_projection_step import ProteinFlatProjectionStep

    projection = ProteinFlatProjectionStep({})
    engine = Engine(
        steps={"projection": projection},
        topology={"projection": {"protein": ("protein",)}},
        initial_state=_state(),
        display_info=False,
    )
    try:
        wid = _MIGRATED_ACTIVE[0]
        # Vivarium wraps updater exceptions; inspect its cause, not its generic type.
        with pytest.raises(Exception, match="failed update") as error:
            engine.state.apply_update({"protein": {"counts": {wid: 1}}}, engine.state)
        assert isinstance(error.value.__context__, ProteinFlatProjectionWriteError)
    finally:
        engine.end()
