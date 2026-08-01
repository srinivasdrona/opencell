"""Tests for `scripts/l2_event/adapters/cytokinesis.py` (the Cytokinesis
`single_firing` normalized event adapter).

Organized around FIX_TEMPLATE_L2_REPLAY Rules 1, 4, 6, 7, 8 as applied to
adapter authoring (see the case directive and
`docs/phase_f/l2_event/CYTOKINESIS_ADAPTER_REPORT.md` for the full
rule-by-rule mapping):

* Rule 1 (complete observable coverage, no silent skip) --
  `test_oc_observation_fails_loud_when_required_input_missing` is
  parametrized over every one of the 5 required dotted paths named by the
  case directive; each one raises `MissingCytokinesisStateInput`
  individually rather than the adapter silently defaulting a missing key.
* Rule 4/4b (per-tick state isolation, no carryover) --
  `test_*_fires_once_on_rising_edge_not_on_persistent_true` proves the
  adapter does not "carry over" a fired verdict into every later tick just
  because `division_complete` is a persistent bool.
* Rule 6 (adversarial / non-triviality probe -- no vacuous PASS on a
  quiescent trace) -- `test_quiet_standard_trace_refuses_before_any_adapter_call`
  proves the quiet-trace inversion is caught structurally (window_loader
  refusal) before any adapter/statistic code runs at all.
* Rule 7 (real code path, pass-through provenance) --
  `test_real_karr_cytokinesis_process_single_fire_detected_on_genuine_completion_tick`
  drives the actual `KarrCytokinesisProcess.next_update()` (not a
  hand-rolled shortcut) to a genuine completion tick and confirms the
  adapter's own rising-edge logic agrees with it.
* Rule 8 (no trace-cribbing in production code) -- every fixture here is
  constructed by the test itself (synthetic `WindowGrid`s, synthetic HDF5
  files, or a real process driven from a from-scratch state dict); nothing
  in `scripts/l2_event/adapters/cytokinesis.py` imports or special-cases a
  specific trace file or seed.

Also directly exercises the case directive's three named inversions plus
the two discrepancies discovered during investigation (a literal 50/50
aligned cohort spuriously hitting `DEGENERATE_NULL`; the stale
`ftsz_ring_complete`/GTP assumptions in the older design doc vs the real
`karr_cytokinesis.py` port) -- see the module-level comments beside each
scenario test below.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from opencell.vivarium.karr_cytokinesis import KarrCytokinesisProcess
from scripts.l2_event.adapters.cytokinesis import (
    REQUIRED_OC_STATE_PATHS,
    CytokinesisEventAdapter,
    MissingCytokinesisStateInput,
    division_relative_offset,
    require_cytokinesis_state_inputs,
)
from scripts.l2_event.registry import EventRegistryEntry
from scripts.l2_event.runner import evaluate_gate
from scripts.l2_event.schema import EventObservation, EventTimeline
from scripts.l2_event.window_loader import EventWindowRefused, WindowGrid, load_event_window

# ---------------------------------------------------------------------------
# Shared fixtures/helpers
# ---------------------------------------------------------------------------


def _window(tick_offset: float, before_series: list[float], after_series: list[float]) -> WindowGrid:
    n_ticks = len(before_series)
    before_arr = np.array([[v] for v in before_series], dtype=float)
    after_arr = np.array([[v] for v in after_series], dtype=float)
    return WindowGrid(
        process_name="Cytokinesis",
        seed=0,
        n_ticks=n_ticks,
        tick_offset=tick_offset,
        trace_path=Path("synthetic-in-memory"),
        observables=("division_complete",),
        states_before={"division_complete": before_arr},
        states_after={"division_complete": after_arr},
    )


def _full_oc_state(*, division_complete: bool = False) -> dict[str, Any]:
    """A minimal, but COMPLETE (all 5 required paths present), conditioned
    `state_before` dict -- shaped exactly like the real
    `karr_cytokinesis.py` port's own state (see
    `tests/vivarium/test_karr_cytokinesis.py::_base_state` for the
    full-fidelity version this is a trimmed stand-in for)."""
    return {
        "cell": {
            "ftsz_ring_complete": True,
            "division_progress": 0.5,
            "division_complete": division_complete,
        },
        "chromosome": {"segregation_progress": 1.0},
        "substrates_allocated": {"karr_cytokinesis": {"GTP": 0.0}},
    }


def _delete_dotted_path(state: dict[str, Any], path: tuple[str, ...]) -> None:
    node = state
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]


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
    scope. `adapter_status='gating_ready'` here only affects this
    in-memory fixture, exactly mirroring `test_l2_event_runner.py`'s own
    `_entry`/`_adapter_and_entry` pattern."""
    base = dict(
        process="Cytokinesis",
        in_scope_v4=True,
        adapter_id="cytokinesis.division_complete.v1",
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


ADAPTER = CytokinesisEventAdapter()

# The single, shared "division anchor" tick used by every synthetic
# cohort below -- the correct value for `WindowGrid.tick_offset` /
# `single_fire_offset`'s denominator (D2 addendum: offset = t_fire -
# t_division). Deliberately non-zero so a wrong-anchor bug (e.g. a
# harness that forgets to subtract it, or subtracts the wrong constant)
# is not accidentally invisible.
TICK_OFFSET = 10.0
N_SEEDS = 50


def _fire_tick_for_seed(seed: int) -> int:
    """Deliberately non-constant per-seed fire tick (10..16, cycling) so
    the cohort has genuine tick-position variance -- a fixed, identical
    fire tick across every seed would make `timing_gate_single_firing`'s
    own Karr-only bootstrap collapse to a zero-width null
    (`q95_null == 0.0`, i.e. `DEGENERATE_NULL`) for the SAME reason a
    literal 50/50-fired cohort collapses `count_gate`'s null (see the
    module docstring's DEGENERATE_NULL discussion below)."""
    return 10 + (seed % 7)


# ---------------------------------------------------------------------------
# Rule 4/4b -- rising-edge / single-fire detection (karr_observation)
# ---------------------------------------------------------------------------


def test_karr_observation_fires_once_on_rising_edge_not_on_persistent_true():
    # tick 2: before=0 (not complete), after=1 (complete) -> the ONE fire.
    # ticks 3, 4: before=1, after=1 -- persistently complete, must NOT
    # register as additional fires (the "double OC fire" inversion shape,
    # exercised here on the Karr side too since the same persistent-bool
    # hazard applies to both sides of the adapter).
    window = _window(
        tick_offset=TICK_OFFSET,
        before_series=[0, 0, 0, 1, 1],
        after_series=[0, 0, 1, 1, 1],
    )
    observations = [ADAPTER.karr_observation(window, t) for t in range(5)]
    fired_ticks = [o.tick for o in observations if o.fired]
    assert fired_ticks == [2]
    assert observations[2].fire_count == 1
    assert observations[2].timing_tick == 2
    assert observations[3].fired is False
    assert observations[4].fired is False


def test_karr_observation_not_applicable_when_no_transition_in_window():
    """A window where the channel never transitions (e.g. a quiescent
    seed, or -- structurally -- the quiet-standard-trace inversion this
    module guards against one layer up in window_loader) must report
    `fired=False` for every tick, not a spurious fire."""
    window = _window(tick_offset=TICK_OFFSET, before_series=[0, 0, 0], after_series=[0, 0, 0])
    observations = [ADAPTER.karr_observation(window, t) for t in range(3)]
    assert all(not o.fired for o in observations)
    assert all(o.fire_count == 0 for o in observations)


# ---------------------------------------------------------------------------
# Rule 1 -- required OC state input enforcement (oc_observation)
# ---------------------------------------------------------------------------


def test_oc_observation_fires_once_on_rising_edge():
    state_before = _full_oc_state(division_complete=False)
    update = {"cell": {"division_complete": True}}
    obs = ADAPTER.oc_observation(5, state_before, update)
    assert obs.fired is True
    assert obs.fire_count == 1
    assert obs.timing_tick == 5


def test_oc_observation_does_not_refire_once_already_complete():
    state_before = _full_oc_state(division_complete=True)
    update = {"cell": {"division_complete": True}}
    obs = ADAPTER.oc_observation(6, state_before, update)
    assert obs.fired is False
    assert obs.fire_count == 0
    assert obs.timing_tick is None


def test_oc_observation_no_fire_when_update_omits_division_complete():
    state_before = _full_oc_state(division_complete=False)
    obs = ADAPTER.oc_observation(0, state_before, update={"cell": {}})
    assert obs.fired is False


@pytest.mark.parametrize("missing_path", REQUIRED_OC_STATE_PATHS, ids=".".join)
def test_oc_observation_fails_loud_when_required_input_missing(missing_path: tuple[str, ...]):
    """Rule 1: every one of the 4 case-directive-named inputs (5 dotted
    paths, since 'division progress/complete' spans two keys) must
    individually cause a loud failure -- never a `.get(..., default)`
    that would let a harness silently omit a declared port and still
    compute a (wrong) fire/no-fire verdict."""
    state = _full_oc_state(division_complete=False)
    _delete_dotted_path(state, missing_path)
    with pytest.raises(MissingCytokinesisStateInput) as exc_info:
        ADAPTER.oc_observation(0, state, update={"cell": {"division_complete": True}})
    assert ".".join(missing_path) in str(exc_info.value)


def test_require_cytokinesis_state_inputs_passes_on_complete_state():
    require_cytokinesis_state_inputs(_full_oc_state())  # must not raise


# ---------------------------------------------------------------------------
# D2 addendum anchor formula (division_relative_offset / single_fire_offset)
# ---------------------------------------------------------------------------


def test_division_relative_offset_matches_d2_addendum_formula():
    assert division_relative_offset(tick=13, tick_offset=10.0) == pytest.approx(3.0)
    assert division_relative_offset(tick=8, tick_offset=10.0) == pytest.approx(-2.0)
    assert division_relative_offset(tick=10, tick_offset=10.0) == pytest.approx(0.0)


def test_single_fire_offset_uses_windows_own_tick_offset_not_a_hardcoded_zero():
    """Guards the 'division timing uses wrong anchor' inversion at the
    unit level: the offset must move when `tick_offset` moves, for the
    SAME fire tick -- a hardcoded-zero-anchor bug would return the same
    (wrong) value regardless of `tick_offset`."""
    window_a = _window(tick_offset=12.0, before_series=[0, 1], after_series=[1, 1])
    window_b = _window(tick_offset=3.0, before_series=[0, 1], after_series=[1, 1])
    assert ADAPTER.single_fire_offset(window_a, tick=0) == pytest.approx(-12.0)
    assert ADAPTER.single_fire_offset(window_b, tick=0) == pytest.approx(-3.0)


# ---------------------------------------------------------------------------
# Rule 7 -- real code path: drive the actual KarrCytokinesisProcess
# ---------------------------------------------------------------------------


def _enzyme_counts(process: KarrCytokinesisProcess, overrides: dict[str, float]) -> dict[str, float]:
    counts = {wid: 0.0 for wid in process.fixture_enzyme_wids}
    counts.update(overrides)
    return counts


def _real_process_state(process: KarrCytokinesisProcess) -> dict[str, Any]:
    """A from-scratch (not trace-derived -- Rule 8) real-shaped state for
    `KarrCytokinesisProcess`, adapted from
    `tests/vivarium/test_karr_cytokinesis.py`'s
    `test_division_completes_when_pinched_diameter_reaches_zero` fixture:
    enough GTP-polymer FtsZ enzyme and allocated water to run every
    pinching cycle to completion with rates=1.0."""
    return {
        "cell": {
            "ftsz_ring_complete": True,
            "division_progress": 0.0,
            "division_complete": False,
        },
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


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    if "cell" in update:
        if "division_progress" in update["cell"]:
            state["cell"]["division_progress"] = float(
                state["cell"].get("division_progress", 0.0) + float(update["cell"]["division_progress"])
            )
        if "division_complete" in update["cell"]:
            state["cell"]["division_complete"] = bool(update["cell"]["division_complete"])
    if "geometry" in update:
        state["geometry"].update(update["geometry"])
    if "ftsZRing" in update:
        state["ftsZRing"].update(update["ftsZRing"])
    for port in ("substrates", "enzymes", "boundEnzymes"):
        for wid, delta in update.get(port, {}).items():
            state[port][wid] = float(state[port].get(wid, 0.0) + float(delta))


def test_real_karr_cytokinesis_process_single_fire_detected_on_genuine_completion_tick():
    """Rule 7: this test never sets `division_complete=True` itself --
    it runs the REAL `KarrCytokinesisProcess.next_update()` for every
    tick up to and including the process's own real completion tick
    (`calc_required_pinching_cycles`), and asserts the adapter's
    `oc_observation` agrees with the process's OWN ground truth on
    exactly which tick fired."""
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
    for tick in range(cycles):
        # Rule 1, exercised inline: the real ports_schema-shaped state
        # must itself satisfy every required input before we trust the
        # adapter's verdict.
        require_cytokinesis_state_inputs(state)
        state_before_snapshot = {
            "cell": dict(state["cell"]),
            "chromosome": dict(state["chromosome"]),
            "substrates_allocated": {process.name: dict(state["substrates_allocated"][process.name])},
        }
        update = process.next_update(1.0, state)
        obs = ADAPTER.oc_observation(tick, state_before_snapshot, update)
        if obs.fired:
            fired_ticks.append(tick)
        _apply_update(state, update)

    assert fired_ticks == [cycles - 1]
    assert state["cell"]["division_complete"] is True
    assert state["geometry"]["pinchedDiameter"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Rule 6 -- quiet standard trace must refuse, never fake-PASS
# ---------------------------------------------------------------------------


def _encode_char_metadata(text: str) -> np.ndarray:
    return np.array([ord(c) for c in text], dtype=np.uint16).reshape(-1, 1)


def _write_quiet_standard_trace(path: Path, *, n_ticks: int = 5) -> Path:
    """A synthetic trace shaped like a real standard mid-cycle trace: it
    has the 3 universally-required metadata keys but NO `tick_offset` --
    exactly the structural signature `window_loader.py` uses to
    distinguish an event-window trace from a quiet standard trace (see
    that module's docstring). No `division_complete` transition is
    encoded anywhere (constant 0 the whole way through) -- this is the
    literal "quiet standard trace" the case directive names."""
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.create_dataset("n_ticks", data=np.array([n_ticks]))
        metadata.create_dataset("process_name", data=_encode_char_metadata("Cytokinesis"))
        metadata.create_dataset("rng_seed", data=np.array([0]))
        # Deliberately NOT writing metadata["tick_offset"].
        states_before = handle.create_group("states_before")
        states_after = handle.create_group("states_after")
        states_before.create_dataset("division_complete", data=np.zeros((1, n_ticks)))
        states_after.create_dataset("division_complete", data=np.zeros((1, n_ticks)))
    return path


def test_quiet_standard_trace_refuses_before_any_adapter_call(tmp_path):
    """The 'quiet standard trace yields fake event PASS' inversion: this
    must be refused by `window_loader.load_event_window` with
    `NOT_EVENT_WINDOW_TRACE` BEFORE `CytokinesisEventAdapter` or
    `evaluate_gate` ever sees the trace -- there is no code path that
    reaches a computed PASS/FAIL verdict from this fixture at all.

    Terminology note for the process report: the case directive's
    "quiet standard trace NOT_APPLICABLE" describes the desired outcome
    shape (never a gating verdict), but the runner's actual vocabulary
    for this precondition failure is the `RefusalReason`
    'NOT_EVENT_WINDOW_TRACE' surfaced as `EventWindowRefused` -- the
    schema's literal `ProcessVerdict` value `'NOT_APPLICABLE'` is
    reserved for structural-smoke runs (see `schema.py`'s
    `ProcessVerdict` docstring) and is intentionally never produced by
    this refusal path, so it is not asserted verbatim here."""
    trace_path = _write_quiet_standard_trace(tmp_path / "Cytokinesis_standard.mat")
    with pytest.raises(EventWindowRefused) as exc_info:
        load_event_window(trace_path, required_observables=("division_complete",))
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
    scenario. NOT literally 50/50 seeds firing: an empirically-verified
    finding (module docstring; see also
    `test_l2_event_metrics.py::test_count_gate_single_firing_boundary_44_refuses_45_proceeds`)
    is that a literal 50/50-fired, perfectly-aligned single_firing cohort
    makes the count channel's Karr-only bootstrap null collapse to
    `q95_null=0.0` (`DEGENERATE_NULL`, a REFUSAL) because every seed's
    count is the same constant (1.0) -- NOT a PASS. Using 47/50 (3 empty
    seeds, still well clear of the >=45/50 floor) with per-seed tick
    variance produces genuine variance in both channels, avoiding the
    degenerate-null trap while still satisfying 'aligned' (Karr and OC
    fire on exactly the same tick, for every firing seed)."""
    n_fire = 47
    karr = [_timeline(s, [_fire_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    oc = [_timeline(s, [_fire_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    offsets = np.array([division_relative_offset(_fire_tick_for_seed(s), TICK_OFFSET) for s in range(n_fire)])

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
    karr = [_timeline(s, [_fire_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    oc = [_timeline(s, [_fire_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    offsets = np.array([division_relative_offset(_fire_tick_for_seed(s), TICK_OFFSET) for s in range(n_fire)])

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


def test_evaluate_gate_wrong_anchor_on_oc_side_fails_timing_channel():
    """The 'division timing uses wrong anchor' inversion: count/support
    are otherwise identical to the passing scenario (same fire ticks,
    same seeds), but the OC-side offsets are computed against the WRONG
    anchor (0.0 instead of the correct 10.0), shifting every OC offset by
    +10 relative to Karr's. The count channel is unaffected (it only
    counts presence, not tick position) but the timing channel's W1
    distance must blow through its threshold -> FAIL, and the process
    verdict must be FAIL (not a silent PASS on the strength of the count
    channel alone)."""
    n_fire = 47
    karr = [_timeline(s, [_fire_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    oc = [_timeline(s, [_fire_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    karr_offsets = np.array([division_relative_offset(_fire_tick_for_seed(s), TICK_OFFSET) for s in range(n_fire)])
    wrong_anchor = 0.0
    oc_offsets_wrong_anchor = np.array(
        [division_relative_offset(_fire_tick_for_seed(s), wrong_anchor) for s in range(n_fire)]
    )

    result = evaluate_gate(
        process="Cytokinesis",
        registry_entry=_entry(),
        adapter=ADAPTER,
        karr_timelines=karr,
        oc_timelines=oc,
        karr_single_fire_offsets=karr_offsets,
        oc_single_fire_offsets=oc_offsets_wrong_anchor,
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
    statistical channels (spec claim C6: a firing-tick-only design must
    never silently drop an OC-only firing between/outside Karr's ticks)."""
    n_fire = 47
    karr = [_timeline(s, [_fire_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    oc = [
        _timeline(s, [_fire_tick_for_seed(s), 25] if s == 0 else ([_fire_tick_for_seed(s)] if s < n_fire else []))
        for s in range(N_SEEDS)
    ]
    offsets = np.array([division_relative_offset(_fire_tick_for_seed(s), TICK_OFFSET) for s in range(n_fire)])

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
    for every evaluate_gate call made anywhere in this file (all of which
    use `magnitude_gateable=False`, matching the authoritative catalog
    row), the payload channel must be `NOT_GATEABLE_REDUNDANT` and must
    NEVER be a member of `gating_channels` (i.e. it can never itself flip
    the process verdict). This is asserted directly against `evaluate_gate`
    rather than only implied by the other scenario tests, so a future
    accidental `magnitude_gateable=True` flip on this adapter's own
    registry-row proposal would be caught here first."""
    n_fire = 47
    karr = [_timeline(s, [_fire_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    oc = [_timeline(s, [_fire_tick_for_seed(s)] if s < n_fire else []) for s in range(N_SEEDS)]
    offsets = np.array([division_relative_offset(_fire_tick_for_seed(s), TICK_OFFSET) for s in range(n_fire)])
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
    karr = [_timeline(s, [_fire_tick_for_seed(s)]) for s in range(5)]
    oc = [_timeline(s, [_fire_tick_for_seed(s)]) for s in range(5)]
    with pytest.raises(ValueError):
        evaluate_gate(
            process="Cytokinesis",
            registry_entry=_entry(required_n_seeds=5),
            adapter=ADAPTER,
            karr_timelines=karr,
            oc_timelines=oc,
            rng=_rng(),
        )
