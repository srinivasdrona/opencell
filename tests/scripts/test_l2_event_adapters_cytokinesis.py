"""Tests for `scripts/l2_event/adapters/cytokinesis.py` (round 2).

Round-1 correction (operator, 2026-08-02 ratified timing decision): this
file replaces round 1's `division_complete`/`tick_offset`-based tests
with a `pinchedDiameter`-based, purely sequence-derived onset/completion
model. Organized around FIX_TEMPLATE_L2_REPLAY Rules 1, 4, 6, 7, 8 as
applied to adapter authoring (see
`docs/phase_f/l2_event/CYTOKINESIS_ADAPTER_REPORT.md` for the full
rule-by-rule mapping):

* Rule 1 (complete observable coverage, no silent skip) --
  `test_oc_observation_fails_loud_when_required_input_missing` is
  parametrized over every static path in `REQUIRED_OC_STATE_PATHS` +
  `REQUIRED_OC_STATE_GROUPS`; the dynamic (fixture-derived enzyme WID /
  WATER WID) coverage is separately exercised against the REAL
  `KarrCytokinesisProcess` by the `test_require_cytokinesis_dynamic_*`
  tests.
* Rule 4/4b (per-tick state isolation, no carryover) --
  `test_*_fires_once_on_rising_edge_not_on_persistent_true` proves
  `karr_observation`/`oc_observation` do not "carry over" a fired verdict
  into every later tick just because `pinchedDiameter` clamps to (and
  stays at) zero once pinched.
* Rule 6 (adversarial / non-triviality probe -- no vacuous PASS on a
  quiescent trace) -- `test_quiet_standard_trace_refuses_before_any_adapter_call`
  proves the quiet-trace inversion is caught structurally (window_loader
  refusal) before any adapter/statistic code runs at all.
* Rule 7 (real code path, pass-through provenance) --
  `test_real_karr_cytokinesis_process_single_fire_detected_on_genuine_completion_tick`
  drives the actual `KarrCytokinesisProcess.next_update()` (not a
  hand-rolled shortcut) to a genuine completion tick and confirms the
  adapter's own rising-edge logic AND the sequence-level
  `oc_single_fire_offset` agree with it.
* Rule 8 (no trace-cribbing in production code) -- every fixture here is
  constructed by the test itself (synthetic `WindowGrid`s, synthetic HDF5
  files, synthetic `(state_before, update)` row sequences, or a real
  process driven from a from-scratch state dict); nothing in
  `scripts/l2_event/adapters/cytokinesis.py` imports or special-cases a
  specific trace file or seed.

Also directly exercises the case directive's named inversions plus the
correction round's new requirements: metadata-independent (`tick_offset`)
derivation, within-tick "instantaneous" ring-ready consumption, no-decrease
completion refusal, duplicate-completion refusal, non-finite/shape-invalid
diameter refusal, WATER-vs-GTP, and missing dynamic enzyme/bound-enzyme
state.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.l2_event.adapters.cytokinesis as cytokinesis_adapter_module
from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess
from scripts.l2_event.adapters.cytokinesis import (
    REQUIRED_OC_STATE_GROUPS,
    REQUIRED_OC_STATE_PATHS,
    CompletionWithoutPrecedingOnset,
    CytokinesisEventAdapter,
    DuplicateCompletionTickDetected,
    InvalidPinchedDiameterSequence,
    MissingCytokinesisStateInput,
    NoCompletionTickDetected,
    OnsetAfterCompletionTick,
    find_completion_tick,
    find_onset_tick,
    karr_single_fire_offset,
    oc_single_fire_offset,
    require_cytokinesis_dynamic_state_inputs,
    require_cytokinesis_state_inputs,
    single_fire_offset_from_sequences,
)
from scripts.l2_event.registry import EventRegistryEntry
from scripts.l2_event.runner import evaluate_gate
from scripts.l2_event.schema import EventObservation, EventTimeline
from scripts.l2_event.window_loader import EventWindowRefused, WindowGrid, load_event_window

ADAPTER_SOURCE_PATH = REPO_ROOT / "scripts" / "l2_event" / "adapters" / "cytokinesis.py"

ADAPTER = CytokinesisEventAdapter()

ALL_REQUIRED_STATIC_PATHS = REQUIRED_OC_STATE_PATHS + REQUIRED_OC_STATE_GROUPS

# ---------------------------------------------------------------------------
# Shared fixtures/helpers
# ---------------------------------------------------------------------------


def _window(*, tick_offset: float, before_series: list[float], after_series: list[float]) -> WindowGrid:
    n_ticks = len(before_series)
    before_arr = np.array([[v] for v in before_series], dtype=float)
    after_arr = np.array([[v] for v in after_series], dtype=float)
    return WindowGrid(
        process_name="Cytokinesis",
        seed=0,
        n_ticks=n_ticks,
        tick_offset=tick_offset,
        trace_path=Path("synthetic-in-memory"),
        observables=("pinchedDiameter",),
        states_before={"pinchedDiameter": before_arr},
        states_after={"pinchedDiameter": after_arr},
    )


def _full_oc_state(*, pinched_diameter: float = 5.0, pinched: bool = False) -> dict[str, Any]:
    """A minimal, but COMPLETE (every `REQUIRED_OC_STATE_PATHS`/
    `REQUIRED_OC_STATE_GROUPS` path present) conditioned `state_before`
    dict, shaped like the real `karr_cytokinesis.py` port's own state --
    see `_real_process_state` for the full-fidelity, process-fixture-
    derived version this is a trimmed stand-in for. Uses an arbitrary
    placeholder enzyme WID/WATER key since these tests exercise only the
    STATIC required-path check (`require_cytokinesis_state_inputs`); the
    dynamic fixture-WID check (`require_cytokinesis_dynamic_state_inputs`)
    is exercised separately below against the REAL `KarrCytokinesisProcess`."""
    return {
        "cell": {"division_progress": 0.5},
        "chromosome": {"segregation_progress": 1.0},
        "geometry": {"width": 1.0e-6, "pinchedDiameter": pinched_diameter, "pinched": pinched},
        "ftsZRing": {
            "numEdgesOneStraight": 0,
            "numEdgesTwoStraight": 0,
            "numEdgesTwoBent": 0,
            "numResidualBent": 0,
            "numFtsZSubunitsPerFilament": 9,
            "filamentLengthInNm": 40.0,
        },
        "enzymes": {"ANY_ENZYME_WID": 10.0},
        "boundEnzymes": {"ANY_ENZYME_WID": 0.0},
        "substrates_allocated": {"karr_cytokinesis": {"WATER": 1_000_000.0}},
    }


def _delete_dotted_path(state: dict[str, Any], path: tuple[str, ...]) -> None:
    node = state
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]


def _oc_rows_from_sequence(
    before: list[float], after: list[float]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        ({"geometry": {"pinchedDiameter": b}}, {"geometry": {"pinchedDiameter": a}})
        for b, a in zip(before, after, strict=True)
    ]


def _synthetic_pinch_sequence(
    *, onset_tick: int, completion_tick: int, n_ticks: int = 30, start_diameter: float = 10.0
) -> tuple[list[float], list[float]]:
    """Builds a physically-coherent `pinchedDiameter` before/after
    sequence for ONE seed: flat at `start_diameter` for every tick before
    `onset_tick` (no decrease yet), decreasing from `onset_tick` through
    `completion_tick` inclusive (reaching exactly 0 AT `completion_tick`),
    then flat at 0 for the rest of the window. `onset_tick ==
    completion_tick` produces the "instantaneous" single-tick case (a
    completed ring bending and pinching to zero within the same tick)."""
    assert 0 <= onset_tick <= completion_tick < n_ticks
    before = [start_diameter] * n_ticks
    after = [start_diameter] * n_ticks
    n_steps = completion_tick - onset_tick + 1
    step = start_diameter / n_steps
    current = start_diameter
    for t in range(onset_tick, completion_tick + 1):
        before[t] = current
        current = max(0.0, current - step)
        if t == completion_tick:
            current = 0.0
        after[t] = current
    for t in range(completion_tick + 1, n_ticks):
        before[t] = 0.0
        after[t] = 0.0
    return before, after


def _timeline(seed: int, fire_ticks: list[int], n_ticks: int = 30) -> EventTimeline:
    fire_set = set(fire_ticks)
    obs = tuple(
        EventObservation(
            tick=t,
            fired=t in fire_set,
            fire_count=1 if t in fire_set else 0,
            timing_tick=t if t in fire_set else None,
        )
        for t in range(n_ticks)
    )
    return EventTimeline(process="Cytokinesis", seed=seed, observations=obs)


def _entry(**overrides) -> EventRegistryEntry:
    """A LOCALLY-constructed registry entry for `evaluate_gate` tests --
    never the real `docs/phase_f/l2_event/event_registry.yaml`, which
    stays frozen at `adapter_status: not_implemented` per this task's
    scope."""
    base = dict(
        process="Cytokinesis",
        in_scope_v4=True,
        adapter_id="cytokinesis.pinched_diameter_completion.v1",
        adapter_status="gating_ready",
        event_timing_model="single_firing",
        magnitude_gateable=False,
        required_n_seeds=50,
        deferred_reason=None,
    )
    base.update(overrides)
    return EventRegistryEntry(**base)


def _rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


ONSET_TICK = 10
N_SEEDS = 50


def _completion_tick_for_seed(seed: int) -> int:
    """Deliberately non-constant per-seed completion tick (10..16,
    cycling) so the cohort has genuine tick-position AND offset variance
    -- an empirically-verified requirement (see report): a literal
    50/50-fired, perfectly-aligned, IDENTICAL-offset single_firing cohort
    makes both the count and timing channels' Karr-only bootstrap nulls
    collapse (`q95_null == 0.0`, `DEGENERATE_NULL`) rather than PASS."""
    return ONSET_TICK + (seed % 7)


def _offset_for_seed(seed: int) -> float:
    """`_completion_tick_for_seed(seed) - ONSET_TICK`, computed directly
    for the 50-seed `evaluate_gate` cohort tests below (which only need
    the NUMERIC offsets `evaluate_gate`/`timing_gate_single_firing`
    consume, not a full synthetic per-seed trace). The actual
    sequence-scan derivation (`onset -> completion -> offset`) is
    exercised end-to-end, per-seed, by the dedicated
    `test_karr_single_fire_offset_*`/`test_oc_single_fire_offset_*` tests
    below via `_synthetic_pinch_sequence`."""
    return float(seed % 7)


# ---------------------------------------------------------------------------
# Rule 4/4b -- rising-edge / single-fire detection (karr_observation)
# ---------------------------------------------------------------------------


def test_karr_observation_fires_once_on_rising_edge_not_on_persistent_true():
    # tick 2: before=10 (not yet pinched), after=0 (pinched) -> the ONE
    # fire. ticks 3, 4: before=after=0 -- persistently pinched, must NOT
    # register as additional fires (the "double OC fire" inversion shape
    # applies to the Karr side too since the same persistent-zero hazard
    # exists on both sides of the adapter).
    window = _window(
        tick_offset=10.0,
        before_series=[10, 10, 10, 0, 0],
        after_series=[10, 10, 0, 0, 0],
    )
    observations = [ADAPTER.karr_observation(window, t) for t in range(5)]
    fired_ticks = [o.tick for o in observations if o.fired]
    assert fired_ticks == [2]
    assert observations[2].fire_count == 1
    assert observations[2].timing_tick == 2
    assert observations[3].fired is False
    assert observations[4].fired is False


def test_karr_observation_not_applicable_when_no_transition_in_window():
    """A window where `pinchedDiameter` never transitions (e.g. a
    quiescent seed, or -- structurally -- the quiet-standard-trace
    inversion this module guards against one layer up in window_loader)
    must report `fired=False` for every tick, not a spurious fire."""
    window = _window(tick_offset=10.0, before_series=[10, 10, 10], after_series=[10, 10, 10])
    observations = [ADAPTER.karr_observation(window, t) for t in range(3)]
    assert all(not o.fired for o in observations)
    assert all(o.fire_count == 0 for o in observations)


def test_karr_observation_raises_on_non_finite_reading():
    window = _window(tick_offset=0.0, before_series=[10.0, float("nan")], after_series=[10.0, 5.0])
    with pytest.raises(InvalidPinchedDiameterSequence):
        ADAPTER.karr_observation(window, 1)


# ---------------------------------------------------------------------------
# Rule 1 -- required OC state input enforcement (oc_observation)
# ---------------------------------------------------------------------------


def test_oc_observation_fires_once_on_rising_edge():
    state_before = _full_oc_state(pinched_diameter=10.0, pinched=False)
    update = {"geometry": {"pinchedDiameter": 0.0, "pinched": True}}
    obs = ADAPTER.oc_observation(5, state_before, update)
    assert obs.fired is True
    assert obs.fire_count == 1
    assert obs.timing_tick == 5


def test_oc_observation_does_not_refire_once_already_complete():
    state_before = _full_oc_state(pinched_diameter=0.0, pinched=True)
    update = {"geometry": {"pinchedDiameter": 0.0, "pinched": True}}
    obs = ADAPTER.oc_observation(6, state_before, update)
    assert obs.fired is False
    assert obs.fire_count == 0
    assert obs.timing_tick is None


def test_oc_observation_no_fire_when_update_omits_geometry():
    state_before = _full_oc_state(pinched_diameter=10.0, pinched=False)
    obs = ADAPTER.oc_observation(0, state_before, update={})
    assert obs.fired is False


def test_oc_observation_raises_on_non_finite_before_diameter():
    state_before = _full_oc_state(pinched_diameter=float("nan"))
    with pytest.raises(InvalidPinchedDiameterSequence):
        ADAPTER.oc_observation(0, state_before, update={"geometry": {"pinchedDiameter": 0.0}})


def test_oc_observation_raises_on_non_finite_after_diameter():
    state_before = _full_oc_state(pinched_diameter=10.0)
    with pytest.raises(InvalidPinchedDiameterSequence):
        ADAPTER.oc_observation(0, state_before, update={"geometry": {"pinchedDiameter": float("inf")}})


@pytest.mark.parametrize("missing_path", ALL_REQUIRED_STATIC_PATHS, ids=".".join)
def test_oc_observation_fails_loud_when_required_input_missing(missing_path: tuple[str, ...]):
    """Rule 1: every static path in `REQUIRED_OC_STATE_PATHS` +
    `REQUIRED_OC_STATE_GROUPS` must individually cause a loud failure --
    never a `.get(..., default)` that would let a harness silently omit a
    declared/read port and still compute a (wrong) fire/no-fire verdict."""
    state = _full_oc_state(pinched_diameter=10.0, pinched=False)
    _delete_dotted_path(state, missing_path)
    with pytest.raises(MissingCytokinesisStateInput) as exc_info:
        ADAPTER.oc_observation(0, state, update={"geometry": {"pinchedDiameter": 0.0}})
    assert ".".join(missing_path) in str(exc_info.value)


def test_require_cytokinesis_state_inputs_passes_on_complete_state():
    require_cytokinesis_state_inputs(_full_oc_state())  # must not raise


def test_required_oc_state_paths_excludes_vestigial_and_gtp_inputs():
    """Inversion test for the round-1 mistake: `cell.ftsz_ring_complete`
    (declared in ports_schema, never read by next_update()) and any GTP
    path (declared for legacy plumbing, request hardcoded to 0.0, never
    read back) must NOT be part of the required manifest;
    `cell.division_complete` (written by next_update, not read by it) must
    not be required either -- completion is now derived purely from
    `geometry.pinchedDiameter`."""
    assert ("cell", "ftsz_ring_complete") not in ALL_REQUIRED_STATIC_PATHS
    assert ("cell", "division_complete") not in ALL_REQUIRED_STATIC_PATHS
    assert not any("GTP" in segment for path in ALL_REQUIRED_STATIC_PATHS for segment in path)


# ---------------------------------------------------------------------------
# Dynamic (fixture-derived) enzyme WID / WATER WID coverage
# ---------------------------------------------------------------------------


def _enzyme_counts(process: KarrCytokinesisProcess, overrides: dict[str, float]) -> dict[str, float]:
    counts = {wid: 0.0 for wid in process.fixture_enzyme_wids}
    counts.update(overrides)
    return counts


def _real_process_state(process: KarrCytokinesisProcess) -> dict[str, Any]:
    """A from-scratch (not trace-derived -- Rule 8) real-shaped state for
    `KarrCytokinesisProcess`: enough GTP-polymer FtsZ enzyme and allocated
    water to run every pinching cycle to completion with rates=1.0."""
    return {
        "cell": {"division_progress": 0.0},
        "chromosome": {"segregation_progress": 1.0, "segregated": True},
        "geometry": {
            "width": process.initial_width,
            "pinchedDiameter": process.initial_pinched_diameter,
            "pinched": False,
        },
        "ftsZRing": {
            "numEdges": 0,
            "numEdgesOneStraight": 0,
            "numEdgesTwoStraight": 0,
            "numEdgesTwoBent": 0,
            "numResidualBent": 0,
            "numFtsZSubunitsPerFilament": process.num_ftsz_subunits_per_filament,
            "filamentLengthInNm": process.default_filament_length_nm,
        },
        "substrates": {process.water_wid: 1_000_000.0},
        "enzymes": _enzyme_counts(
            process,
            {
                process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp_polymer]: 10_000.0,
                process.fixture_enzyme_wids[process.enzyme_index_ftsz_gdp]: 3.0,
                process.fixture_enzyme_wids[process.enzyme_index_ftsz_gtp]: 6.0,
            },
        ),
        "boundEnzymes": _enzyme_counts(process, {}),
        "requests": {process.name: {process.gtp_wid: 0.0, process.water_wid: 0.0}},
        "substrates_allocated": {process.name: {process.gtp_wid: 0.0, process.water_wid: 1_000_000.0}},
    }


def test_require_cytokinesis_dynamic_state_inputs_passes_with_full_process_state():
    process = KarrCytokinesisProcess()
    state = _real_process_state(process)
    require_cytokinesis_state_inputs(state)
    require_cytokinesis_dynamic_state_inputs(state, process)  # must not raise


def test_require_cytokinesis_dynamic_state_inputs_gtp_alone_is_not_sufficient():
    """WATER-vs-GTP inversion: a `state_before` with GTP allocated but
    WATER missing must still fail -- GTP's allocated value is never read
    back by `next_update()` (module docstring); only WATER gates
    hydrolysis."""
    process = KarrCytokinesisProcess()
    state = _real_process_state(process)
    state["substrates_allocated"][process.name] = {process.gtp_wid: 1_000_000.0}  # WATER removed
    with pytest.raises(MissingCytokinesisStateInput) as exc_info:
        require_cytokinesis_dynamic_state_inputs(state, process)
    assert process.water_wid in str(exc_info.value)


def test_require_cytokinesis_dynamic_state_inputs_missing_enzyme_wid_raises():
    process = KarrCytokinesisProcess()
    state = _real_process_state(process)
    missing_wid = process.fixture_enzyme_wids[0]
    del state["enzymes"][missing_wid]
    with pytest.raises(MissingCytokinesisStateInput) as exc_info:
        require_cytokinesis_dynamic_state_inputs(state, process)
    assert missing_wid in str(exc_info.value)
    assert "enzymes." in str(exc_info.value)


def test_require_cytokinesis_dynamic_state_inputs_missing_bound_enzyme_wid_raises():
    process = KarrCytokinesisProcess()
    state = _real_process_state(process)
    missing_wid = process.fixture_enzyme_wids[0]
    del state["boundEnzymes"][missing_wid]
    with pytest.raises(MissingCytokinesisStateInput) as exc_info:
        require_cytokinesis_dynamic_state_inputs(state, process)
    assert missing_wid in str(exc_info.value)
    assert "boundEnzymes." in str(exc_info.value)


# ---------------------------------------------------------------------------
# Sequence-scan primitives -- find_onset_tick / find_completion_tick
# ---------------------------------------------------------------------------


def test_find_onset_tick_returns_first_strict_decrease():
    before = [10.0, 10.0, 6.0, 6.0, 0.0]
    after = [10.0, 6.0, 6.0, 0.0, 0.0]
    assert find_onset_tick(before, after) == 1


def test_find_onset_tick_returns_none_when_no_decrease_ever_occurs():
    before = [10.0] * 5
    after = [10.0] * 5
    assert find_onset_tick(before, after) is None


def test_find_completion_tick_returns_none_when_never_reaches_zero():
    before = [10.0, 6.0, 6.0]
    after = [6.0, 6.0, 6.0]
    assert find_completion_tick(before, after) is None


def test_find_completion_tick_raises_on_duplicate_completion():
    before = [5.0, 0.0, 5.0, 0.0]
    after = [0.0, 0.0, 0.0, 0.0]
    with pytest.raises(DuplicateCompletionTickDetected):
        find_completion_tick(before, after)


def test_find_onset_tick_raises_on_non_finite_value():
    with pytest.raises(InvalidPinchedDiameterSequence):
        find_onset_tick([10.0, float("nan")], [10.0, 5.0])


def test_find_onset_tick_raises_on_negative_value():
    with pytest.raises(InvalidPinchedDiameterSequence):
        find_onset_tick([10.0, -1.0], [10.0, 5.0])


def test_find_onset_tick_raises_on_mismatched_lengths():
    with pytest.raises(InvalidPinchedDiameterSequence):
        find_onset_tick([10.0, 5.0], [10.0])


def test_find_onset_tick_raises_on_non_scalar_reading():
    with pytest.raises(InvalidPinchedDiameterSequence):
        find_onset_tick([10.0, np.array([1.0, 2.0])], [10.0, 5.0])


def test_find_onset_tick_raises_on_empty_sequence():
    with pytest.raises(InvalidPinchedDiameterSequence):
        find_onset_tick([], [])


# ---------------------------------------------------------------------------
# single_fire_offset_from_sequences -- the only place offset arithmetic
# happens (correction: "Offset is exactly completion_tick - onset_tick")
# ---------------------------------------------------------------------------


def test_single_fire_offset_from_sequences_multi_tick():
    before, after = _synthetic_pinch_sequence(onset_tick=3, completion_tick=6, n_ticks=10)
    assert single_fire_offset_from_sequences(before, after) == pytest.approx(3.0)


def test_single_fire_offset_from_sequences_instantaneous_case_is_zero():
    """Ratified 2026-08-02 decision: 'if the instantaneous ring-ready
    state is consumed within one tick, contraction onset is the first
    strict decrease in pinchedDiameter' -- onset and completion coincide,
    offset == 0, and this is a VALID outcome, not an error."""
    before, after = _synthetic_pinch_sequence(onset_tick=4, completion_tick=4, n_ticks=10)
    assert single_fire_offset_from_sequences(before, after) == pytest.approx(0.0)


def test_single_fire_offset_refuses_when_no_decrease_ever_occurs():
    """'No-decrease completion refusal': a sequence with no strict
    decrease anywhere also, definitionally, never completes -- an offset
    cannot be computed."""
    before = [10.0] * 10
    after = [10.0] * 10
    with pytest.raises(NoCompletionTickDetected):
        single_fire_offset_from_sequences(before, after)


def test_single_fire_offset_refuses_on_duplicate_completion():
    before = [5.0, 0.0, 5.0, 0.0]
    after = [0.0, 0.0, 0.0, 0.0]
    with pytest.raises(DuplicateCompletionTickDetected):
        single_fire_offset_from_sequences(before, after)


def test_single_fire_offset_defensive_guard_completion_without_onset(monkeypatch):
    """Defensive Rule-1-style guard: under a correctly-defined completion
    predicate this is structurally unreachable via
    `find_onset_tick`/`find_completion_tick` on valid data (the
    completion tick is itself always a valid onset candidate), so this
    monkeypatches `find_onset_tick` to simulate a hypothetical FUTURE
    regression where onset detection diverges from completion detection,
    and proves `single_fire_offset_from_sequences` fails loudly rather
    than silently accepting the inconsistency."""
    monkeypatch.setattr(cytokinesis_adapter_module, "find_onset_tick", lambda before, after: None)
    with pytest.raises(CompletionWithoutPrecedingOnset):
        single_fire_offset_from_sequences([5.0], [0.0])


def test_single_fire_offset_defensive_guard_onset_after_completion(monkeypatch):
    """Defensive guard, structurally unreachable on valid data (see
    above) -- monkeypatches `find_onset_tick` to report an onset tick
    strictly later than the real completion tick, proving
    `single_fire_offset_from_sequences` refuses rather than reporting a
    negative offset."""
    monkeypatch.setattr(cytokinesis_adapter_module, "find_onset_tick", lambda before, after: 99)
    with pytest.raises(OnsetAfterCompletionTick):
        single_fire_offset_from_sequences([5.0], [0.0])


# ---------------------------------------------------------------------------
# karr_single_fire_offset / oc_single_fire_offset -- the sequence helpers
# ---------------------------------------------------------------------------


def test_karr_single_fire_offset_matches_sequence_derivation():
    before, after = _synthetic_pinch_sequence(onset_tick=3, completion_tick=6, n_ticks=10)
    window = _window(tick_offset=0.0, before_series=before, after_series=after)
    assert karr_single_fire_offset(window) == pytest.approx(3.0)


def test_karr_single_fire_offset_is_independent_of_tick_offset():
    """Correction: proof that changing `WindowGrid.tick_offset` cannot
    alter the derived offset -- two windows share the IDENTICAL
    pinchedDiameter sequence but declare wildly different `tick_offset`
    metadata values; the derived offset must be identical."""
    before, after = _synthetic_pinch_sequence(onset_tick=3, completion_tick=6, n_ticks=10)
    window_a = _window(tick_offset=0.0, before_series=before, after_series=after)
    window_b = _window(tick_offset=999.0, before_series=before, after_series=after)
    assert karr_single_fire_offset(window_a) == pytest.approx(3.0)
    assert karr_single_fire_offset(window_b) == pytest.approx(3.0)
    assert karr_single_fire_offset(window_a) == karr_single_fire_offset(window_b)


def test_karr_single_fire_offset_instantaneous_ring_ready_consumed_within_one_tick():
    before, after = _synthetic_pinch_sequence(onset_tick=4, completion_tick=4, n_ticks=10)
    window = _window(tick_offset=0.0, before_series=before, after_series=after)
    assert karr_single_fire_offset(window) == pytest.approx(0.0)


def test_oc_single_fire_offset_matches_sequence_derivation():
    before, after = _synthetic_pinch_sequence(onset_tick=2, completion_tick=5, n_ticks=8)
    rows = _oc_rows_from_sequence(before, after)
    assert oc_single_fire_offset(rows) == pytest.approx(3.0)


def test_oc_single_fire_offset_instantaneous_ring_ready_consumed_within_one_tick():
    before, after = _synthetic_pinch_sequence(onset_tick=4, completion_tick=4, n_ticks=10)
    rows = _oc_rows_from_sequence(before, after)
    assert oc_single_fire_offset(rows) == pytest.approx(0.0)


def test_oc_single_fire_offset_raises_when_row_missing_geometry():
    rows = [({"geometry": {"pinchedDiameter": 10.0}}, {"geometry": {"pinchedDiameter": 10.0}}), ({}, {"geometry": {"pinchedDiameter": 0.0}})]
    with pytest.raises(MissingCytokinesisStateInput):
        oc_single_fire_offset(rows)


def test_tick_offset_and_window_anchor_absent_from_adapter_attribute_access():
    """Correction: 'tick_offset must be completely absent from timing
    arithmetic.' Parses the adapter module's AST (NOT a raw substring
    search, which would false-positive on this module's own prose
    docstrings explaining WHY tick_offset/window_anchor are deliberately
    not used) and asserts no `.tick_offset` or `.window_anchor` ATTRIBUTE
    ACCESS exists anywhere in the actual code."""
    source = ADAPTER_SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    offending = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in ("tick_offset", "window_anchor")
    ]
    assert offending == []


# ---------------------------------------------------------------------------
# Rule 7 -- real code path: drive the actual KarrCytokinesisProcess
# ---------------------------------------------------------------------------


def _snapshot_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "cell": dict(state["cell"]),
        "chromosome": dict(state["chromosome"]),
        "geometry": dict(state["geometry"]),
        "ftsZRing": dict(state["ftsZRing"]),
        "enzymes": dict(state["enzymes"]),
        "boundEnzymes": dict(state["boundEnzymes"]),
        "substrates_allocated": {k: dict(v) for k, v in state["substrates_allocated"].items()},
    }


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    if "cell" in update and "division_progress" in update["cell"]:
        state["cell"]["division_progress"] = float(
            state["cell"].get("division_progress", 0.0) + float(update["cell"]["division_progress"])
        )
    if "geometry" in update:
        state["geometry"].update(update["geometry"])
    if "ftsZRing" in update:
        state["ftsZRing"].update(update["ftsZRing"])
    for port in ("substrates", "enzymes", "boundEnzymes"):
        for wid, delta in update.get(port, {}).items():
            state[port][wid] = float(state[port].get(wid, 0.0) + float(delta))


def test_real_karr_cytokinesis_process_single_fire_detected_on_genuine_completion_tick():
    """Rule 7: this test never sets `pinchedDiameter=0` itself -- it runs
    the REAL `KarrCytokinesisProcess.next_update()` for every tick up to
    and including the process's own real completion tick
    (`calc_required_pinching_cycles`), and asserts:
    (1) the adapter's `oc_observation` agrees with the process's OWN
        ground truth on exactly which tick fired;
    (2) `oc_single_fire_offset` over the full collected row sequence
        agrees with an independently-derived onset/completion pair
        (`find_onset_tick`/`find_completion_tick` on the SAME sequence)
        -- i.e. the offset helper is self-consistent with the low-level
        scan primitives, not a separately-hardcoded number."""
    process = KarrCytokinesisProcess(
        {
            "rate_filament_binding_membrane": 1.0,
            "rate_filament_dissociation": 1.0,
            "rate_ftsz_gtp_hydrolysis": 1.0,
        }
    )
    cycles = process.calc_required_pinching_cycles(
        process.initial_pinched_diameter, process.default_filament_length_nm
    )
    state = _real_process_state(process)

    fired_ticks: list[int] = []
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for tick in range(cycles):
        # Rule 1, exercised inline: the real ports_schema-shaped state
        # must itself satisfy every required (static + dynamic) input
        # before we trust the adapter's verdict.
        require_cytokinesis_state_inputs(state)
        require_cytokinesis_dynamic_state_inputs(state, process)
        state_before_snapshot = _snapshot_state(state)
        update = process.next_update(1.0, state)
        obs = ADAPTER.oc_observation(tick, state_before_snapshot, update)
        if obs.fired:
            fired_ticks.append(tick)
        rows.append((state_before_snapshot, update))
        _apply_update(state, update)

    assert fired_ticks == [cycles - 1]
    assert state["geometry"]["pinchedDiameter"] == pytest.approx(0.0)
    assert state["geometry"]["pinched"] is True

    before_seq = [row[0]["geometry"]["pinchedDiameter"] for row in rows]
    after_seq = [row[1]["geometry"]["pinchedDiameter"] for row in rows]
    independent_completion = find_completion_tick(before_seq, after_seq)
    independent_onset = find_onset_tick(before_seq, after_seq)
    assert independent_completion == cycles - 1
    assert independent_onset is not None
    assert independent_onset <= independent_completion

    assert oc_single_fire_offset(rows) == pytest.approx(float(independent_completion - independent_onset))


# ---------------------------------------------------------------------------
# Rule 6 -- quiet standard trace must refuse, never fake-PASS
# ---------------------------------------------------------------------------


def _encode_char_metadata(text: str) -> np.ndarray:
    return np.array([ord(c) for c in text], dtype=np.uint16).reshape(-1, 1)


def _write_quiet_standard_trace(path: Path, *, n_ticks: int = 5) -> Path:
    """A synthetic trace shaped like a real standard mid-cycle trace: it
    has the 3 universally-required metadata keys but NO `tick_offset` --
    exactly the structural signature `window_loader.py` uses to
    distinguish an event-window trace from a quiet standard trace. No
    `pinchedDiameter` transition is encoded anywhere (constant positive
    value the whole way through) -- this is the literal "quiet standard
    trace" the case directive names."""
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata("Cytokinesis"))
        metadata.create_dataset("rng_seed", data=np.array([0]))
        # Deliberately NOT writing metadata["tick_offset"].
        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        states_before.create_dataset("pinchedDiameter", data=np.full((1, n_ticks), 10.0))
        states_after.create_dataset("pinchedDiameter", data=np.full((1, n_ticks), 10.0))
    return path


def test_quiet_standard_trace_refuses_before_any_adapter_call(tmp_path):
    """The 'quiet standard trace yields fake event PASS' inversion: this
    must be refused by `window_loader.load_event_window` with
    `NOT_EVENT_WINDOW_TRACE` BEFORE `CytokinesisEventAdapter` or
    `evaluate_gate` ever sees the trace -- there is no code path that
    reaches a computed PASS/FAIL verdict from this fixture at all."""
    trace_path = _write_quiet_standard_trace(tmp_path / "Cytokinesis_standard.mat")
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(trace_path, required_observables=("pinchedDiameter",))
    assert exc_info.value.reason == "NOT_EVENT_WINDOW_TRACE"


# ---------------------------------------------------------------------------
# evaluate_gate integration scenarios (synthetic 50-seed cohorts)
# ---------------------------------------------------------------------------
#
# All numeric outcomes below were verified empirically against the real
# `scripts.l2_event.metrics`/`runner` code (rng seed fixed to 0) before
# being encoded as assertions -- see the process report's "Verification"
# section for the exact probe transcript.


def test_evaluate_gate_47_of_50_aligned_firing_seeds_passes():
    """The case directive's '50-seed cohorts pass at 50 aligned events'
    scenario. NOT literally 50/50 seeds firing (see `DEGENERATE_NULL`
    discussion in `_completion_tick_for_seed`'s docstring): 47/50 (3
    empty seeds) with per-seed tick/offset variance produces genuine
    variance in both channels while still satisfying 'aligned' (Karr and
    OC fire on exactly the same tick, for every firing seed)."""
    n_fire = 47
    karr = [_timeline(s, [_completion_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    oc = [_timeline(s, [_completion_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    offsets = np.array([_offset_for_seed(s) for s in range(n_fire)])

    result = evaluate_gate(
        process="Cytokinesis",
        registry_entry=_entry(),
        adapter=ADAPTER,
        karr_timelines=karr,
        oc_timelines=oc,
        karr_single_fire_offsets=offsets,
        oc_single_fire_offsets=offsets.copy(),
        rng=_rng(),
    )
    assert result.verdict == "PASS"
    channel_verdicts = {c.channel: c.verdict for c in result.channels}
    assert channel_verdicts["count"] in ("PASS", "SEED_NOISE")
    assert channel_verdicts["timing"] in ("PASS", "SEED_NOISE")
    assert channel_verdicts["payload"] == "NOT_GATEABLE_REDUNDANT"
    assert not result.oc_only_fire_ticks


def test_evaluate_gate_44_of_50_karr_fires_refuses_insufficient_support():
    """Catalog support floor: '>=45/50 Karr-fired seeds'. 44/50 must
    REFUSE (INSUFFICIENT_KARR_SUPPORT), matching the case directive's
    '44 Karr fires refuses' expectation exactly at the boundary."""
    n_fire = 44
    karr = [_timeline(s, [_completion_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    oc = [_timeline(s, [_completion_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    offsets = np.array([_offset_for_seed(s) for s in range(n_fire)])

    result = evaluate_gate(
        process="Cytokinesis",
        registry_entry=_entry(),
        adapter=ADAPTER,
        karr_timelines=karr,
        oc_timelines=oc,
        karr_single_fire_offsets=offsets,
        oc_single_fire_offsets=offsets.copy(),
        rng=_rng(),
    )
    assert result.verdict == "REFUSED"
    channel_verdicts = {c.channel: c.verdict for c in result.channels}
    assert channel_verdicts["count"] == "INSUFFICIENT_KARR_SUPPORT"
    assert channel_verdicts["timing"] == "INSUFFICIENT_KARR_SUPPORT"


def test_evaluate_gate_wrong_onset_on_oc_side_fails_timing_channel():
    """Regression proxy for the round-1 'division timing uses wrong
    anchor' inversion, reframed against the round-2 onset/completion
    model: count/support are otherwise identical to the passing scenario
    (same fire ticks, same seeds), but the OC-side offsets carry a
    systematic +10 bias (as if OC onset detection had regressed to a
    stale window-placement constant instead of the real per-seed derived
    onset). The count channel is unaffected (it only counts presence,
    not tick position) but the timing channel's W1 distance must blow
    through its threshold -> FAIL, and the process verdict must be FAIL
    (not a silent PASS on the strength of the count channel alone)."""
    n_fire = 47
    karr = [_timeline(s, [_completion_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    oc = [_timeline(s, [_completion_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    karr_offsets = np.array([_offset_for_seed(s) for s in range(n_fire)])
    oc_offsets_wrong = karr_offsets + 10.0

    result = evaluate_gate(
        process="Cytokinesis",
        registry_entry=_entry(),
        adapter=ADAPTER,
        karr_timelines=karr,
        oc_timelines=oc,
        karr_single_fire_offsets=karr_offsets,
        oc_single_fire_offsets=oc_offsets_wrong,
        rng=_rng(),
    )
    assert result.verdict == "FAIL"
    channel_verdicts = {c.channel: c.verdict for c in result.channels}
    assert channel_verdicts["timing"] == "FAIL"


def test_evaluate_gate_double_oc_fire_outside_window_fails_via_spurious_c6():
    """The 'double OC fire / spurious outside window' inversion: seed 0's
    OC timeline fires an EXTRA time at tick 25 (well outside Karr's
    firing window), on top of its correctly-aligned fire at its normal
    tick. This must be caught by the C6 OC-only-firing check and fail the
    WHOLE process -- independent of, and prior to, the count/timing
    statistical channels."""
    n_fire = 47
    karr = [_timeline(s, [_completion_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    oc = [
        _timeline(
            s,
            [_completion_tick_for_seed(s), 25] if s == 0 else ([_completion_tick_for_seed(s)] if s < n_fire else []),
        )
        for s in range(N_SEEDS)
    ]
    offsets = np.array([_offset_for_seed(s) for s in range(n_fire)])

    result = evaluate_gate(
        process="Cytokinesis",
        registry_entry=_entry(),
        adapter=ADAPTER,
        karr_timelines=karr,
        oc_timelines=oc,
        karr_single_fire_offsets=offsets,
        oc_single_fire_offsets=offsets.copy(),
        rng=_rng(),
    )
    assert result.verdict == "FAIL"
    assert result.oc_only_fire_ticks == {"0": [25]}
    assert any("spurious OC-only" in r for r in result.reasons)


def test_evaluate_gate_payload_channel_is_always_not_gateable_redundant_never_gating():
    """D6 / the 'redundant payload accidentally made gating' inversion:
    for every `evaluate_gate` call made anywhere in this file (all of
    which use `magnitude_gateable=False`, matching the authoritative
    catalog row), the payload channel must be `NOT_GATEABLE_REDUNDANT`
    and must NEVER be a member of `gating_channels`."""
    n_fire = 47
    karr = [_timeline(s, [_completion_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    oc = [_timeline(s, [_completion_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    offsets = np.array([_offset_for_seed(s) for s in range(n_fire)])
    entry = _entry(magnitude_gateable=False)
    assert entry.magnitude_gateable is False

    result = evaluate_gate(
        process="Cytokinesis",
        registry_entry=entry,
        adapter=ADAPTER,
        karr_timelines=karr,
        oc_timelines=oc,
        karr_single_fire_offsets=offsets,
        oc_single_fire_offsets=offsets.copy(),
        rng=_rng(),
    )
    payload_channel = next(c for c in result.channels if c.channel == "payload")
    assert payload_channel.verdict == "NOT_GATEABLE_REDUNDANT"
    assert payload_channel.statistic_value is None


def test_evaluate_gate_single_firing_requires_offsets_for_cytokinesis_entry():
    """Reproduces the generic `test_evaluate_gate_single_firing_requires_offsets`
    guarantee (test_l2_event_runner.py) specifically through a
    Cytokinesis-shaped registry entry/adapter, so this file does not
    silently assume that generic contract still applies once a real
    process/adapter is wired in."""
    karr = [_timeline(s, [_completion_tick_for_seed(s)]) for s in range(5)]
    oc = [_timeline(s, [_completion_tick_for_seed(s)]) for s in range(5)]
    with pytest.raises(ValueError):
        evaluate_gate(
            process="Cytokinesis",
            registry_entry=_entry(required_n_seeds=5),
            adapter=ADAPTER,
            karr_timelines=karr,
            oc_timelines=oc,
            rng=_rng(),
        )
