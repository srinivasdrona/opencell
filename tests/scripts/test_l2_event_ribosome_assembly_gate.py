"""Unit tests for the candidate gating-ready RibosomeAssembly adapter
(``scripts/l2_event/adapters/ribosome_assembly_gate.py``, adapter_id
``ribosome_assembly.gate.v1``).

Distinct from ``tests/scripts/test_l2_event_adapters.py``'s coverage of
``ribosome_assembly.smoke.v1`` -- this file is scoped to the NEW,
gating-capable adapter this task adds. It is organized in three parts:

1. Pure adapter unit tests (payload mapping, empty-update handling,
   fire_count tick-incidence semantics, multiple-particles-in-one-tick,
   unmapped-index refusal, exact-channel-width refusal) -- no real data
   required.
2. Real seed-0 structural round-trip (skipped if the local-only,
   gitignored event-window MAT is absent): proves this adapter reproduces
   the same ground-truth fires (ticks [9, 17]) and mapped payload keys the
   existing smoke adapter already established, including the specific
   per-tick WID identity (RIBOSOME_50S@9, RIBOSOME_30S@17, both Karr and
   OC) -- and that a swapped mapping breaks that identity -- AND proves
   the runner still cannot reach a computed gate verdict on this file
   today. Canary-A closeout: the real seed-0 MAT now carries a complete
   M4 stride/tick-window contract (so the strict-mode window load itself
   succeeds), but only 1 of the required 50 seeds exists on disk, so the
   ensemble-size refusal alone still blocks a computed verdict -- the
   only honest verdict for this file remains the existing
   ``structural_smoke`` / ``NOT_APPLICABLE`` path.
3. Synthetic 50-seed cohort tests driving ``scripts.l2_event.runner.
   evaluate_gate`` end-to-end through this adapter's own
   ``karr_observation``/``oc_observation`` methods (never constructing
   ``EventObservation``/``EventTimeline`` by hand) -- count/timing/payload
   PASS and FAIL, multiple particles forming in the same tick pooled into
   a real cohort, and missing/spurious OC payload components.
4. Registry-refusal tests proving this adapter remains unreachable through
   the real registry: ``evaluate_gate``/``check_adapter`` refuse this
   candidate against the LIVE ``event_registry.yaml`` RibosomeAssembly row
   (still declaring ``ribosome_assembly.smoke.v1``) with
   ``ADAPTER_NOT_REGISTERED``, and a process-name mismatch is refused with
   ``ADAPTER_PROCESS_MISMATCH`` -- this candidate adapter is never wired
   into the real dispatch path by this module.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event import metrics
from scripts.l2_event.adapters.ribosome_assembly_gate import (
    _COMPLEX_INDEX_BY_WID,
    RibosomeAssemblyGateAdapter,
    UnmappedComplexIndexError,
)
from scripts.l2_event.registry import EventRegistryEntry, resolve_process_entry
from scripts.l2_event.runner import (
    RunnerRefusal,
    check_adapter,
    check_ensemble_size,
    evaluate_gate,
    load_and_check_window,
)
from scripts.l2_event.schema import EventTimeline
from scripts.l2_event.window_loader import WindowGrid

_RA_TRACE = (
    REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2_event_s000"
    / "RibosomeAssembly_100ticks.mat"
)


def _rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


# ---------------------------------------------------------------------------
# Part 1 -- pure adapter unit tests
# ---------------------------------------------------------------------------


def _window(after_rows: list[list[float]]) -> WindowGrid:
    """Synthetic single-seed window whose `complexs` channel is `after -
    before` directly (before is always zero), matching
    test_l2_event_adapters.py's `_complex_window` helper pattern."""
    after = np.array(after_rows, dtype=float)
    before = np.zeros_like(after)
    return WindowGrid(
        process_name="RibosomeAssembly",
        seed=0,
        n_ticks=after.shape[0],
        tick_offset=0.0,
        trace_path=Path("synthetic_gate_adapter.mat"),
        observables=("complexs",),
        states_before={"complexs": before},
        states_after={"complexs": after},
    )


def test_adapter_id_is_distinct_from_the_registered_smoke_adapter():
    adapter = RibosomeAssemblyGateAdapter()
    assert adapter.adapter_id == "ribosome_assembly.gate.v1"
    assert adapter.process_name == "RibosomeAssembly"
    assert adapter.adapter_id != "ribosome_assembly.smoke.v1"


def test_default_wid_mapping_matches_the_live_process_complex_wids_order():
    """The hardcoded _COMPLEX_INDEX_BY_WID constant must match the real
    OC process's actual runtime attribute order, not merely an assumption
    -- this is what makes the fixed mapping safe to hardcode instead of
    inferring it per-run like the smoke adapter does."""
    from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess

    process = KarrRibosomeAssemblyProcess({"rng_seed": 0})
    assert process.complex_wids == ["RIBOSOME_30S", "RIBOSOME_50S"]
    assert _COMPLEX_INDEX_BY_WID == {0: "RIBOSOME_30S", 1: "RIBOSOME_50S"}


def test_karr_observation_maps_positive_deltas_to_declared_wids():
    adapter = RibosomeAssemblyGateAdapter()
    window = _window([[0.0, 0.0], [3.0, 0.0], [0.0, 5.0]])
    obs0 = adapter.karr_observation(window, 0)
    assert obs0.fired is False
    assert obs0.fire_count == 0
    obs1 = adapter.karr_observation(window, 1)
    assert obs1.fired is True
    assert obs1.fire_count == 1
    assert obs1.payload == {"RIBOSOME_30S": 3.0}
    obs2 = adapter.karr_observation(window, 2)
    assert obs2.payload == {"RIBOSOME_50S": 5.0}


def test_karr_observation_multiple_particles_same_tick_is_still_tick_incidence():
    """Both particles can form in the same tick (D2: repeated-firing,
    all-or-nothing per particle -- not mutually exclusive across the two
    particles). fire_count must remain tick incidence (1); payload must
    carry both magnitudes."""
    adapter = RibosomeAssemblyGateAdapter()
    window = _window([[2.0, 4.0]])
    obs = adapter.karr_observation(window, 0)
    assert obs.fired is True
    assert obs.fire_count == 1
    assert obs.payload == {"RIBOSOME_30S": 2.0, "RIBOSOME_50S": 4.0}


def test_karr_observation_raises_on_unmapped_complex_index():
    """Rule 1 (observable coverage complete): a channel index this
    adapter's declared mapping does not cover must refuse loudly, never
    silently drop the delta."""
    adapter = RibosomeAssemblyGateAdapter(complex_index_by_wid={0: "RIBOSOME_30S"})
    window = _window([[0.0, 7.0]])
    with pytest.raises(UnmappedComplexIndexError):
        adapter.karr_observation(window, 0)


def test_karr_observation_raises_on_channel_width_1_even_when_extra_index_absent():
    """Width check runs before per-index mapping: with the default 2-WID
    mapping, a channel that is only 1-wide must refuse even though there
    is no "extra" index at all to silently zero-fill -- the cardinality
    mismatch itself (not merely an out-of-range delta value) is the bug
    this refusal targets."""
    adapter = RibosomeAssemblyGateAdapter()
    window = _window([[3.0]])
    with pytest.raises(UnmappedComplexIndexError):
        adapter.karr_observation(window, 0)


def test_karr_observation_raises_on_channel_width_3_even_when_extra_delta_is_zero():
    """Same width check, opposite direction: a 3-wide channel must refuse
    even when the third (unmapped) index's delta is exactly 0.0 on this
    tick -- a zero value on the extra channel must not paper over the
    keyspace-cardinality drift, since some OTHER tick could carry a
    nonzero value there that would otherwise silently vanish."""
    adapter = RibosomeAssemblyGateAdapter()
    window = _window([[3.0, 4.0, 0.0]])
    with pytest.raises(UnmappedComplexIndexError):
        adapter.karr_observation(window, 0)


def test_karr_observation_raises_on_non_dense_cardinality_2_mapping_unmapped_index():
    """Distinct refusal branch from the two width tests above: here the
    mapping's *cardinality* (len == 2) matches the channel width (2)
    exactly, so the width check does NOT fire. The mapping's keys are
    non-dense over range(expected_width) (`{0: 'RIBOSOME_30S', 5:
    'RIBOSOME_50S'}`, missing index 1), so a positive delta at the
    uncovered index 1 must reach the `key is None` defensive branch
    inside the per-index loop, not the width-mismatch branch."""
    adapter = RibosomeAssemblyGateAdapter(
        complex_index_by_wid={0: "RIBOSOME_30S", 5: "RIBOSOME_50S"}
    )
    window = _window([[3.0, 4.0]])
    with pytest.raises(UnmappedComplexIndexError, match="channel index 1 has no declared WID mapping"):
        adapter.karr_observation(window, 0)


def test_oc_observation_handles_empty_update_dict_without_keyerror():
    """Spec §4 fact 5 / this task's contract: `.get('complex',
    {}).get('counts', {})`, never direct key access."""
    adapter = RibosomeAssemblyGateAdapter()
    obs = adapter.oc_observation(0, state_before={}, update={})
    assert obs.fired is False
    assert obs.fire_count == 0
    assert obs.payload == {}


def test_oc_observation_handles_update_with_no_complex_key():
    adapter = RibosomeAssemblyGateAdapter()
    obs = adapter.oc_observation(0, state_before={}, update={"substrates": {"counts": {"GTP": -1.0}}})
    assert obs.fired is False


def test_oc_observation_maps_positive_complex_counts_and_excludes_zero_values():
    adapter = RibosomeAssemblyGateAdapter()
    update = {"complex": {"counts": {"RIBOSOME_30S": 1.0, "RIBOSOME_50S": 0.0}}}
    obs = adapter.oc_observation(0, state_before={}, update=update)
    assert obs.fired is True
    assert obs.fire_count == 1
    assert obs.payload == {"RIBOSOME_30S": 1.0}


def test_oc_observation_fire_count_is_tick_incidence_not_particle_count():
    adapter = RibosomeAssemblyGateAdapter()
    update = {"complex": {"counts": {"RIBOSOME_30S": 50.0, "RIBOSOME_50S": 30.0}}}
    obs = adapter.oc_observation(0, state_before={}, update=update)
    assert obs.fire_count == 1
    assert sum(obs.payload.values()) == 80.0


def test_required_payload_components_is_always_the_fixed_two_wids():
    adapter = RibosomeAssemblyGateAdapter()
    assert adapter.required_payload_components == frozenset({"RIBOSOME_30S", "RIBOSOME_50S"})


# ---------------------------------------------------------------------------
# Part 2 -- real seed-0 structural round-trip (optional, local-only data)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _RA_TRACE.exists(), reason="Real RibosomeAssembly seed-000 event-window MAT not present locally")
def test_gate_adapter_real_seed0_round_trip_reproduces_ticks_9_and_17():
    """Structural round-trip only (never a gate verdict): this NEW
    gating-capable adapter, run over the real seed-0 trace, reproduces the
    exact same ground-truth fires the existing smoke adapter already
    established (ticks [9, 17], both Karr and OC), and its payload keys
    are drawn only from the declared {RIBOSOME_30S, RIBOSOME_50S}
    keyspace -- using the fixed mapping, not per-run wid inference."""
    from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess
    from scripts.l2_event.adapters import ribosome_assembly_smoke as ra_smoke

    window = load_and_check_window(_RA_TRACE, ra_smoke._RA_OBSERVABLES, require_stride_contract=False)
    process_obj = KarrRibosomeAssemblyProcess({"rng_seed": 0})
    adapter = RibosomeAssemblyGateAdapter()

    karr_fire_ticks: list[int] = []
    oc_fire_ticks: list[int] = []
    payload_keys_seen: set[str] = set()
    for tick in range(window.n_ticks):
        state, _ = ra_smoke.build_karr_conditioned_state(process_obj, window, tick)
        karr_obs = adapter.karr_observation(window, tick)
        update = ra_smoke.run_ribosome_assembly_oc_tick(process_obj, state)
        oc_obs = adapter.oc_observation(tick, state, update)
        if karr_obs.fired:
            karr_fire_ticks.append(tick)
            payload_keys_seen.update(karr_obs.payload.keys())
        if oc_obs.fired:
            oc_fire_ticks.append(tick)

    assert karr_fire_ticks == [9, 17]
    assert oc_fire_ticks == [9, 17]
    assert payload_keys_seen
    assert payload_keys_seen <= {"RIBOSOME_30S", "RIBOSOME_50S"}


@pytest.mark.skipif(not _RA_TRACE.exists(), reason="Real RibosomeAssembly seed-000 event-window MAT not present locally")
def test_gate_adapter_cannot_reach_a_computed_verdict_on_real_seed0():
    """Canary-A closeout: even with a fully gating-capable adapter in hand
    AND a now-complete M4 window contract, real seed-0 data still cannot
    produce a computed gate verdict today -- but for only ONE reason now,
    proven directly (never merely asserted):

    (a) the strict gate-mode window contract
        (`require_stride_contract=True`, the default `load_event_window`
        callers must use for a real gate run) now SUCCEEDS on this file --
        the regenerated MAT carries a complete stride/tick_start/tick_end
        contract (stride=1, tick_start=201, tick_end=300, absolute ticks;
        tick_offset=200 burn-in ticks precede capture) -- so this is no
        longer a blocker (M4, EVENT_WINDOW_EXTRACTOR_CONTRACT.md).
    (b) only 1 of the registry's required 50 seeds exists on disk for this
        process, so `evaluate_gate`'s own ensemble-size gauntlet
        (`check_ensemble_size`, which it always runs internally -- M2)
        refuses independently with `SINGLE_SEED_ENSEMBLE_REQUIRED` -- this
        is now the ONLY reason this file cannot reach a computed verdict.

    The only honest verdict this codebase can emit for this file remains
    `NOT_APPLICABLE` via the existing `run_structural_smoke` path (see
    `tests/scripts/test_l2_event_adapters.py::
    test_run_structural_smoke_end_to_end_against_real_seed0_never_returns_a_gate_verdict`).
    """
    from scripts.l2_event.adapters import ribosome_assembly_smoke as ra_smoke

    window = load_and_check_window(_RA_TRACE, ra_smoke._RA_OBSERVABLES, require_stride_contract=True)
    assert window.stride_contract_ok is True
    assert window.tick_offset == 200.0
    assert window.tick_start == 201
    assert window.tick_end == 300
    assert window.n_ticks == 100

    with pytest.raises(RunnerRefusal) as exc_info2:
        check_ensemble_size(n_seeds_provided=1, required_n_seeds=50)
    assert exc_info2.value.reason == "SINGLE_SEED_ENSEMBLE_REQUIRED"


@pytest.mark.skipif(not _RA_TRACE.exists(), reason="Real RibosomeAssembly seed-000 event-window MAT not present locally")
def test_gate_adapter_real_seed0_tick9_and_tick17_wid_identity():
    """Structural-only, real-seed0 identity check, stronger than the
    ticks-only round-trip above: not just THAT ticks 9 and 17 fire, but
    WHICH named complex forms at each, on BOTH sides. Ground truth
    (established directly from this adapter against the real trace):
    tick 9 forms RIBOSOME_50S (only), tick 17 forms RIBOSOME_30S (only) --
    for both the Karr channel and the OC `update` dict. This is the
    concrete guard against a payload-key-to-WID mismap (SLOT 1's named
    inversion: "payload keys map Karr positional complexes to wrong OC
    WIDs")."""
    from opencell.vivarium.karr_ribosome_assembly import KarrRibosomeAssemblyProcess
    from scripts.l2_event.adapters import ribosome_assembly_smoke as ra_smoke

    window = load_and_check_window(_RA_TRACE, ra_smoke._RA_OBSERVABLES, require_stride_contract=False)
    process_obj = KarrRibosomeAssemblyProcess({"rng_seed": 0})
    adapter = RibosomeAssemblyGateAdapter()

    karr_obs_9 = adapter.karr_observation(window, 9)
    karr_obs_17 = adapter.karr_observation(window, 17)
    assert karr_obs_9.payload == {"RIBOSOME_50S": 1.0}
    assert karr_obs_17.payload == {"RIBOSOME_30S": 1.0}

    oc_payloads: dict[int, dict[str, float]] = {}
    for tick in (9, 17):
        state, _ = ra_smoke.build_karr_conditioned_state(process_obj, window, tick)
        update = ra_smoke.run_ribosome_assembly_oc_tick(process_obj, state)
        oc_payloads[tick] = adapter.oc_observation(tick, state, update).payload
    assert oc_payloads[9] == {"RIBOSOME_50S": 1.0}
    assert oc_payloads[17] == {"RIBOSOME_30S": 1.0}


@pytest.mark.skipif(not _RA_TRACE.exists(), reason="Real RibosomeAssembly seed-000 event-window MAT not present locally")
def test_gate_adapter_real_seed0_swapped_wid_map_breaks_the_identity():
    """Negative control for the identity test above: an adapter configured
    with the two WIDs deliberately SWAPPED must reproduce the WRONG
    identity on the Karr side at both ticks (tick 9 now reads as
    RIBOSOME_30S, tick 17 as RIBOSOME_50S) -- proving the identity test
    above is actually sensitive to the mapping, not a tautology that would
    pass regardless of which WID a given positional index is assigned to.
    (The OC side has no equivalent failure mode to swap: `oc_observation`
    never consults `complex_index_by_wid` at all -- OC's own
    `update['complex']['counts']` dict is already WID-keyed by the OC
    process itself, so there is no positional index for a mapping to get
    wrong on that side; this is exactly why a payload-key mismap can only
    originate on the Karr positional-array side, which is what this test
    targets.)"""
    from scripts.l2_event.adapters import ribosome_assembly_smoke as ra_smoke

    window = load_and_check_window(_RA_TRACE, ra_smoke._RA_OBSERVABLES, require_stride_contract=False)
    swapped = RibosomeAssemblyGateAdapter(complex_index_by_wid={0: "RIBOSOME_50S", 1: "RIBOSOME_30S"})

    karr_obs_9 = swapped.karr_observation(window, 9)
    karr_obs_17 = swapped.karr_observation(window, 17)
    assert karr_obs_9.payload == {"RIBOSOME_30S": 1.0}
    assert karr_obs_9.payload != {"RIBOSOME_50S": 1.0}
    assert karr_obs_17.payload == {"RIBOSOME_50S": 1.0}
    assert karr_obs_17.payload != {"RIBOSOME_30S": 1.0}


# ---------------------------------------------------------------------------
# Part 3 -- synthetic 50-seed cohorts through evaluate_gate
# ---------------------------------------------------------------------------

_N_SEEDS = 50
_N_TICKS = 30


def _entry(**overrides) -> EventRegistryEntry:
    """Matches this task's authoritative registry row exactly, except
    `adapter_status` is overridden to `gating_ready` -- a purely in-memory
    dataclass instance a test constructs directly, never written to the
    real `event_registry.yaml` (no registry edits per this task's scope).
    """
    base = dict(
        process="RibosomeAssembly",
        in_scope_v4=True,
        adapter_id="ribosome_assembly.gate.v1",
        adapter_status="gating_ready",
        event_timing_model="repeated_firing",
        magnitude_gateable=True,
        required_n_seeds=50,
        deferred_reason=None,
    )
    base.update(overrides)
    return EventRegistryEntry(**base)


def _repeated_firing_cohort(n_seeds: int = _N_SEEDS, n_ticks: int = _N_TICKS) -> list[list[int]]:
    """Fire-tick lists with real inter-seed variance (2/3/4 fires per
    seed, cycling tick position), matching
    `test_l2_event_runner._repeated_firing_cohort`'s pattern so pooled
    Karr support clears the >=50 M1 floor and the null bootstrap is never
    degenerate."""
    fires = []
    for s in range(n_seeds):
        k = 2 + (s % 3)
        base = 3 + (s % 5)
        fires.append([t for t in (base + i * 2 for i in range(k)) if t < n_ticks])
    return fires


def _build_cohort(
    karr_fires: list[list[int]],
    oc_fires: list[list[int]],
    *,
    n_ticks: int,
    karr_payload_fn,
    oc_payload_fn,
    adapter: RibosomeAssemblyGateAdapter,
) -> tuple[list[EventTimeline], list[EventTimeline], list[list[dict]], list[list[dict]]]:
    """Build one seed's worth of Karr/OC `EventTimeline`s (plus their
    per-seed payload lists, per `payload_gate`'s cardinality contract) for
    every seed in the cohort, by feeding synthetic per-tick `complexs`
    deltas / OC `update` dicts through THIS adapter's own
    `karr_observation`/`oc_observation` -- never constructing
    `EventObservation`/`EventTimeline` by hand (Rule 7: real code path).
    """
    karr_timelines: list[EventTimeline] = []
    oc_timelines: list[EventTimeline] = []
    karr_payloads_by_seed: list[list[dict]] = []
    oc_payloads_by_seed: list[list[dict]] = []

    for seed, (karr_ticks, oc_ticks) in enumerate(zip(karr_fires, oc_fires, strict=True)):
        karr_set = set(karr_ticks)
        after = np.zeros((n_ticks, 2), dtype=float)
        for t in karr_set:
            for wid, val in karr_payload_fn(seed, t).items():
                idx = 0 if wid == "RIBOSOME_30S" else 1
                after[t, idx] = val
        window = WindowGrid(
            process_name="RibosomeAssembly",
            seed=seed,
            n_ticks=n_ticks,
            tick_offset=0.0,
            trace_path=Path(f"synthetic_seed{seed:03d}.mat"),
            observables=("complexs",),
            states_before={"complexs": np.zeros((n_ticks, 2), dtype=float)},
            states_after={"complexs": after},
        )
        karr_obs = tuple(adapter.karr_observation(window, t) for t in range(n_ticks))
        karr_timelines.append(EventTimeline(process="RibosomeAssembly", seed=seed, observations=karr_obs))
        karr_payloads_by_seed.append([o.payload for o in karr_obs if o.fired])

        oc_set = set(oc_ticks)
        oc_obs_list = []
        for t in range(n_ticks):
            if t in oc_set:
                payload = oc_payload_fn(seed, t)
                update = {"complex": {"counts": payload}} if payload else {}
            else:
                update = {}
            oc_obs_list.append(adapter.oc_observation(t, state_before={}, update=update))
        oc_timelines.append(EventTimeline(process="RibosomeAssembly", seed=seed, observations=tuple(oc_obs_list)))
        oc_payloads_by_seed.append([o.payload for o in oc_obs_list if o.fired])

    return karr_timelines, oc_timelines, karr_payloads_by_seed, oc_payloads_by_seed


def _matched_payload(seed: int, tick: int) -> dict[str, float]:
    """Both particles form together (exercises the dual-particle-in-one-
    tick path pooled into a real 50-seed cohort, not just the Part-1 unit
    test), magnitude varies mildly across seeds so neither side's null
    bootstrap is degenerate."""
    return {
        "RIBOSOME_30S": 5.0 + (seed % 5) * 0.5,
        "RIBOSOME_50S": 3.0 + (seed % 4) * 0.5,
    }


def test_evaluate_gate_passes_for_matching_ra_cohort_with_dual_particle_firings():
    fire_ticks = _repeated_firing_cohort()
    karr, oc, karr_pl, oc_pl = _build_cohort(
        fire_ticks,
        fire_ticks,
        n_ticks=_N_TICKS,
        karr_payload_fn=_matched_payload,
        oc_payload_fn=_matched_payload,
        adapter=RibosomeAssemblyGateAdapter(),
    )
    result = evaluate_gate(
        process="RibosomeAssembly",
        registry_entry=_entry(),
        adapter=RibosomeAssemblyGateAdapter(),
        karr_timelines=karr,
        oc_timelines=oc,
        karr_payloads_by_seed=karr_pl,
        oc_payloads_by_seed=oc_pl,
        rng=_rng(),
    )
    assert result.verdict == "PASS"
    count_channel = next(c for c in result.channels if c.channel == "count")
    timing_channel = next(c for c in result.channels if c.channel == "timing")
    payload_channel = next(c for c in result.channels if c.channel == "payload")
    assert count_channel.verdict in ("PASS", "SEED_NOISE")
    assert timing_channel.verdict in ("PASS", "SEED_NOISE")
    assert payload_channel.verdict in ("PASS", "SEED_NOISE")


def test_evaluate_gate_fails_on_count_divergence_oc_fires_far_fewer_events():
    """D3 support-guard violation (deterministic, not bootstrap-dependent):
    OC fires only once per seed while Karr fires 2-4 times per seed, so
    T_oc falls below floor(0.5 * T_karr)."""
    karr_fires = _repeated_firing_cohort()
    oc_fires = [ticks[:1] for ticks in karr_fires]
    karr, oc, karr_pl, oc_pl = _build_cohort(
        karr_fires,
        oc_fires,
        n_ticks=_N_TICKS,
        karr_payload_fn=_matched_payload,
        oc_payload_fn=_matched_payload,
        adapter=RibosomeAssemblyGateAdapter(),
    )
    result = evaluate_gate(
        process="RibosomeAssembly",
        registry_entry=_entry(),
        adapter=RibosomeAssemblyGateAdapter(),
        karr_timelines=karr,
        oc_timelines=oc,
        karr_payloads_by_seed=karr_pl,
        oc_payloads_by_seed=oc_pl,
        rng=_rng(),
    )
    count_channel = next(c for c in result.channels if c.channel == "count")
    assert count_channel.verdict == "FAIL"
    assert result.verdict == "FAIL"


def test_evaluate_gate_fails_on_timing_divergence_oc_shifted_to_a_different_cycle_region():
    """Counts match exactly (isolating the divergence to timing only): OC
    fires the same NUMBER of times per seed as Karr, but shifted +15 ticks
    into a different region of the enumerated window."""
    karr_fires = _repeated_firing_cohort(n_ticks=_N_TICKS)
    # Max Karr tick is 7 + 3*2 = 13, so +15 (<= 28) never exceeds _N_TICKS=30:
    # every seed's fire count is preserved exactly, isolating the divergence
    # to timing only (no incidental count-gate divergence).
    oc_fires = [[t + 15 for t in ticks] for ticks in karr_fires]
    assert all(len(oc) == len(karr) for oc, karr in zip(oc_fires, karr_fires, strict=True))
    karr, oc, karr_pl, oc_pl = _build_cohort(
        karr_fires,
        oc_fires,
        n_ticks=_N_TICKS,
        karr_payload_fn=_matched_payload,
        oc_payload_fn=_matched_payload,
        adapter=RibosomeAssemblyGateAdapter(),
    )
    result = evaluate_gate(
        process="RibosomeAssembly",
        registry_entry=_entry(),
        adapter=RibosomeAssemblyGateAdapter(),
        karr_timelines=karr,
        oc_timelines=oc,
        karr_payloads_by_seed=karr_pl,
        oc_payloads_by_seed=oc_pl,
        rng=_rng(),
    )
    timing_channel = next(c for c in result.channels if c.channel == "timing")
    assert timing_channel.verdict == "FAIL"
    assert result.verdict == "FAIL"


def test_evaluate_gate_fails_on_payload_magnitude_divergence():
    """Counts and timing match exactly; only the magnitude on both named
    complexes is off by two orders of magnitude."""
    fire_ticks = _repeated_firing_cohort()

    def _oc_payload(seed: int, tick: int) -> dict[str, float]:
        base = _matched_payload(seed, tick)
        return {k: v * 100.0 for k, v in base.items()}

    karr, oc, karr_pl, oc_pl = _build_cohort(
        fire_ticks,
        fire_ticks,
        n_ticks=_N_TICKS,
        karr_payload_fn=_matched_payload,
        oc_payload_fn=_oc_payload,
        adapter=RibosomeAssemblyGateAdapter(),
    )
    result = evaluate_gate(
        process="RibosomeAssembly",
        registry_entry=_entry(),
        adapter=RibosomeAssemblyGateAdapter(),
        karr_timelines=karr,
        oc_timelines=oc,
        karr_payloads_by_seed=karr_pl,
        oc_payloads_by_seed=oc_pl,
        rng=_rng(),
    )
    payload_channel = next(c for c in result.channels if c.channel == "payload")
    assert payload_channel.verdict == "FAIL"
    assert result.verdict == "FAIL"


def test_evaluate_gate_fails_when_oc_never_reports_the_50s_component():
    """Missing OC component: Karr's payload includes both RIBOSOME_30S and
    RIBOSOME_50S across the cohort, but OC's payload silently never
    reports RIBOSOME_50S at all (as if that half of a port's complex.counts
    write were dropped). The adapter's declared `required_payload_components`
    still matches the UNION of both sides (Karr contributes RIBOSOME_50S to
    the union), so this reaches the per-component NO_OC_COMPONENT verdict
    rather than the coarser keyspace-mismatch refusal."""
    fire_ticks = _repeated_firing_cohort()

    def _oc_payload_missing_50s(seed: int, tick: int) -> dict[str, float]:
        base = _matched_payload(seed, tick)
        return {k: v for k, v in base.items() if k != "RIBOSOME_50S"}

    karr, oc, karr_pl, oc_pl = _build_cohort(
        fire_ticks,
        fire_ticks,
        n_ticks=_N_TICKS,
        karr_payload_fn=_matched_payload,
        oc_payload_fn=_oc_payload_missing_50s,
        adapter=RibosomeAssemblyGateAdapter(),
    )
    result = evaluate_gate(
        process="RibosomeAssembly",
        registry_entry=_entry(),
        adapter=RibosomeAssemblyGateAdapter(),
        karr_timelines=karr,
        oc_timelines=oc,
        karr_payloads_by_seed=karr_pl,
        oc_payloads_by_seed=oc_pl,
        rng=_rng(),
    )
    payload_channel = next(c for c in result.channels if c.channel == "payload")
    assert payload_channel.verdict == "NO_OC_COMPONENT"
    component_verdicts = {c.component: c.verdict for c in payload_channel.per_component}
    assert component_verdicts["RIBOSOME_50S"] == "NO_OC_COMPONENT"
    assert result.verdict == "FAIL"


def test_evaluate_gate_fails_when_oc_reports_a_spurious_extra_component():
    """Spurious OC component: OC's payload includes a bogus extra key
    outside the adapter's declared 2-WID keyspace. Because this adapter
    always declares `required_payload_components` (never None, unlike the
    smoke adapter's optional mapping), the observed union no longer
    exactly matches the required set, so `payload_gate` refuses with a
    hard keyspace-mismatch FAIL BEFORE computing any per-component metric
    -- a stricter (and earlier) rejection than the generic
    SPURIOUS_OC_COMPONENT per-component path a less strict adapter would
    hit (see test_payload_gate_direct_call_reports_spurious_oc_component_
    verdict_without_required_components below for that generic path)."""
    fire_ticks = _repeated_firing_cohort()

    def _oc_payload_with_bogus_key(seed: int, tick: int) -> dict[str, float]:
        base = dict(_matched_payload(seed, tick))
        base["RIBOSOME_EXTRA_BOGUS"] = 1.0
        return base

    karr, oc, karr_pl, oc_pl = _build_cohort(
        fire_ticks,
        fire_ticks,
        n_ticks=_N_TICKS,
        karr_payload_fn=_matched_payload,
        oc_payload_fn=_oc_payload_with_bogus_key,
        adapter=RibosomeAssemblyGateAdapter(),
    )
    result = evaluate_gate(
        process="RibosomeAssembly",
        registry_entry=_entry(),
        adapter=RibosomeAssemblyGateAdapter(),
        karr_timelines=karr,
        oc_timelines=oc,
        karr_payloads_by_seed=karr_pl,
        oc_payloads_by_seed=oc_pl,
        rng=_rng(),
    )
    payload_channel = next(c for c in result.channels if c.channel == "payload")
    assert payload_channel.verdict == "FAIL"
    assert any("does not exactly match the adapter's required keyspace" in r for r in payload_channel.reasons)
    assert result.verdict == "FAIL"


def test_evaluate_gate_fails_on_spurious_oc_only_firings_between_karr_events():
    """C6: OC firing on ticks Karr never fired at all (an OC-only fire
    between real Karr events) must fail the whole process verdict --
    directly guards SLOT 1's named inversion ('OC-only between-event
    firings are missed')."""
    karr_fires = _repeated_firing_cohort()
    # Same real fires as Karr, plus one additional spurious OC-only fire
    # per seed at a tick Karr never used in this cohort's construction.
    oc_fires = [ticks + [_N_TICKS - 1] for ticks in karr_fires]

    def _oc_payload(seed: int, tick: int) -> dict[str, float]:
        return _matched_payload(seed, tick)

    karr, oc, karr_pl, oc_pl = _build_cohort(
        karr_fires,
        oc_fires,
        n_ticks=_N_TICKS,
        karr_payload_fn=_matched_payload,
        oc_payload_fn=_oc_payload,
        adapter=RibosomeAssemblyGateAdapter(),
    )
    result = evaluate_gate(
        process="RibosomeAssembly",
        registry_entry=_entry(),
        adapter=RibosomeAssemblyGateAdapter(),
        karr_timelines=karr,
        oc_timelines=oc,
        karr_payloads_by_seed=karr_pl,
        oc_payloads_by_seed=oc_pl,
        rng=_rng(),
    )
    assert result.verdict == "FAIL"
    assert result.oc_only_fire_ticks
    assert any("spurious OC-only" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Supplementary: generic per-component verdicts at the metrics layer
# (required_components=None), showing the underlying NO_OC_COMPONENT /
# SPURIOUS_OC_COMPONENT verdicts this adapter's stricter required-keyspace
# check is specifically designed to pre-empt.
# ---------------------------------------------------------------------------


def test_payload_gate_direct_call_reports_missing_and_spurious_component_verdicts():
    rng = _rng()
    karr_payloads_by_seed = [[{"RIBOSOME_30S": 5.0 + (s % 5) * 0.5, "RIBOSOME_50S": 3.0 + (s % 4) * 0.5}] for s in range(50)]
    oc_payloads_by_seed = [
        [{"RIBOSOME_30S": 5.0 + (s % 5) * 0.5, "RIBOSOME_EXTRA_BOGUS": 1.0}] for s in range(50)
    ]
    result = metrics.payload_gate(
        karr_payloads_by_seed,
        oc_payloads_by_seed,
        rng=rng,
        required_components=None,
        expected_n_seeds=50,
    )
    component_verdicts = {c.component: c.verdict for c in result.per_component}
    assert component_verdicts["RIBOSOME_50S"] == "NO_OC_COMPONENT"
    assert component_verdicts["RIBOSOME_EXTRA_BOGUS"] == "SPURIOUS_OC_COMPONENT"


# ---------------------------------------------------------------------------
# Part 4 -- registry-refusal tests: this candidate adapter stays
# unreachable/unregistered through the real dispatch path
# ---------------------------------------------------------------------------


def test_check_adapter_refuses_gate_adapter_against_the_live_registered_smoke_adapter():
    """The LIVE, on-disk `event_registry.yaml` RibosomeAssembly row still
    declares `ribosome_assembly.smoke.v1` (unchanged by this task -- no
    registry edits made). `check_adapter` must refuse this candidate
    `ribosome_assembly.gate.v1` adapter against that live row with
    `ADAPTER_NOT_REGISTERED`, proving the new adapter is not reachable
    through the real registry no matter how gate-capable its
    implementation is."""
    live_entry = resolve_process_entry("RibosomeAssembly")
    assert live_entry.adapter_id == "ribosome_assembly.smoke.v1"
    assert live_entry.adapter_status == "structural_smoke_only"

    with pytest.raises(RunnerRefusal) as exc_info:
        check_adapter(RibosomeAssemblyGateAdapter(), "RibosomeAssembly", live_entry)
    assert exc_info.value.reason == "ADAPTER_NOT_REGISTERED"


def test_evaluate_gate_refuses_gate_adapter_against_the_live_registered_smoke_adapter():
    """Same refusal, exercised through the full `evaluate_gate` entry point
    (M2: it always runs the same refusal gauntlet internally, so no direct
    caller -- this test included -- can reach a computed verdict by
    bypassing `check_adapter`)."""
    live_entry = resolve_process_entry("RibosomeAssembly")
    with pytest.raises(RunnerRefusal) as exc_info:
        evaluate_gate(
            process="RibosomeAssembly",
            registry_entry=live_entry,
            adapter=RibosomeAssemblyGateAdapter(),
            karr_timelines=[],
            oc_timelines=[],
            rng=_rng(),
        )
    assert exc_info.value.reason == "ADAPTER_NOT_REGISTERED"


def test_check_adapter_refuses_on_adapter_process_name_mismatch():
    """`check_adapter`'s process-identity check is independent of, and
    runs before, its registered-adapter-id check: an adapter whose own
    declared `process_name` does not match the process being evaluated
    must refuse with `ADAPTER_PROCESS_MISMATCH`, even if its `adapter_id`
    would otherwise match the registry entry passed in."""
    adapter = RibosomeAssemblyGateAdapter()
    adapter.process_name = "SomeOtherProcess"  # instance override, class default is "RibosomeAssembly"
    entry = _entry()  # adapter_id == adapter.adapter_id, so only the process-name check can fire
    assert entry.adapter_id == adapter.adapter_id

    with pytest.raises(RunnerRefusal) as exc_info:
        check_adapter(adapter, "RibosomeAssembly", entry)
    assert exc_info.value.reason == "ADAPTER_PROCESS_MISMATCH"


# ---------------------------------------------------------------------------
# Part 5 -- evaluate_gate-level refusal tests (Opus5 non-blocking review
# note #2): the refusal gauntlet (`check_ensemble_size`,
# `check_empty_support`) is exercised end-to-end through this adapter's own
# `karr_observation`/`oc_observation` and `_build_cohort`, not just via a
# bare direct call to the standalone `check_ensemble_size` function (Part 3
# above already covers that unit-level case for reference).
# ---------------------------------------------------------------------------


def test_evaluate_gate_refuses_an_under_supported_low_fired_seed_cohort():
    """A cohort with far fewer seeds than the registry's declared
    `required_n_seeds=50` (here: 5 fired seeds, well below the 50-seed
    ensemble floor) must refuse with `SINGLE_SEED_ENSEMBLE_REQUIRED` --
    never PASS, never any other computed verdict -- because
    `evaluate_gate` runs `check_ensemble_size` before any gate math, per
    its own docstring (M2 review): a real adapter that only manages to
    fire on a handful of seeds is exactly the under-powered-cohort case
    this refusal exists to catch."""
    fire_ticks = _repeated_firing_cohort(n_seeds=5)
    karr, oc, karr_pl, oc_pl = _build_cohort(
        fire_ticks,
        fire_ticks,
        n_ticks=_N_TICKS,
        karr_payload_fn=_matched_payload,
        oc_payload_fn=_matched_payload,
        adapter=RibosomeAssemblyGateAdapter(),
    )
    assert len(karr) == 5

    with pytest.raises(RunnerRefusal) as exc_info:
        evaluate_gate(
            process="RibosomeAssembly",
            registry_entry=_entry(),
            adapter=RibosomeAssemblyGateAdapter(),
            karr_timelines=karr,
            oc_timelines=oc,
            karr_payloads_by_seed=karr_pl,
            oc_payloads_by_seed=oc_pl,
            rng=_rng(),
        )
    assert exc_info.value.reason == "SINGLE_SEED_ENSEMBLE_REQUIRED"


def test_evaluate_gate_refuses_a_fully_quiet_karr_and_oc_cohort():
    """A full 50-seed cohort where BOTH Karr and OC never fire a single
    tick (built through this adapter's own `oc_observation`/
    `karr_observation` over all-empty fire-tick lists, not hand-built
    `EventObservation`s) must refuse with `EMPTY_EVENT_SUPPORT` -- the
    vacuous zero==zero case `check_empty_support` exists to catch --
    rather than reporting a computed PASS verdict for a cohort that never
    observed a single event on either side."""
    quiet_fires = [[] for _ in range(_N_SEEDS)]
    karr, oc, karr_pl, oc_pl = _build_cohort(
        quiet_fires,
        quiet_fires,
        n_ticks=_N_TICKS,
        karr_payload_fn=_matched_payload,
        oc_payload_fn=_matched_payload,
        adapter=RibosomeAssemblyGateAdapter(),
    )
    assert len(karr) == _N_SEEDS
    assert sum(t.total_fire_count for t in karr) == 0
    assert sum(t.total_fire_count for t in oc) == 0

    with pytest.raises(RunnerRefusal) as exc_info:
        evaluate_gate(
            process="RibosomeAssembly",
            registry_entry=_entry(),
            adapter=RibosomeAssemblyGateAdapter(),
            karr_timelines=karr,
            oc_timelines=oc,
            karr_payloads_by_seed=karr_pl,
            oc_payloads_by_seed=oc_pl,
            rng=_rng(),
        )
    assert exc_info.value.reason == "EMPTY_EVENT_SUPPORT"
