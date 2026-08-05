"""No-hint, per-tick Karr-before-reset seed0/100-tick topology diagnostic.

Distinct from `test_karr_replication_l2_replay.py` /
`test_karr_replication_initiation_l2_replay.py` (which use
`trace_hint`-driven replay and validate ONLY the accepted activity gate
(L2.1) and `strand_1..4` projection plumbing -- an accounting/plumbing
check, not a topology check): every test in THIS file drives
`KarrReplicationProcess.next_update` through its genuine, non-hint branch
(`_l2_2_design_a_runner_helpers.py::_run_replication_tick`'s target
branch, per the approved TURN-2 adjudication), exercising the literal
Okazaki-fragment initiate/advance/terminate state machine ported from
`Replication.m`.

PROVENANCE CAVEAT (do not overclaim): each tick below is built by
constructing a FRESH `KarrReplicationProcess` and overlaying the real
oracle's OWN `states_before[tick]` snapshot (substrates/enzymes/
boundEnzymes/chromosome) directly from the hash-pinned 100-tick trace,
then calling `next_update` exactly once. This is a PER-TICK RESET
diagnostic, not a continuously-evolving trajectory -- no state carries
over between ticks, and no `trace_hint` (oracle "after" values) is ever
read (`forbid_sut_oracle_file_io` enforces this). A genuinely continuous,
path-consistent Replication run over many ticks still depends on
`ReplicationInitiation`/direct multi-process coupling, which is out of
this topology repair's scope.

OPUS G1 UPDATE -- SSB-cycle divergence resolved, a SEPARATE residual
confound identified (do not overclaim either direction):

Prior to the G1 pass, `free_and_bind_ssbs`'s candidate-binding-site
scoping was wrong on ALL 4 strands (see that method's own docstring), so
the REAL (non-bypassed) `_apply_ssb_cycle` path diverged from the
SSB-state-bypassed path -- the module previously attributed ALL
real-vs-bypass divergence to the SSB-cycle's per-tick-fresh-RNG-draw
being an inherently uncorrelated stochastic confound. That framing is now
KNOWN WRONG: after the G1 scoping fix, `_run_events_scan(bypass_ssb_cycle
=False)` (real path) and `_run_events_scan(bypass_ssb_cycle=True)`
(bypass) produce IDENTICAL initiation/termination tick sets -- the
SSB-cycle stochastic step is no longer a meaningful source of divergence
at seed0 once genuinely scoped.

However, NEITHER path currently achieves Opus's required EXACT tick-set/
multiplicity equality (init == {15,22,31,48,66,84} exactly, term ==
{52:1,76:1,91:1,92:1} exactly). Both paths instead fire SPURIOUS
initiation ticks immediately adjacent to/before each real expected tick
(e.g. 46,47 before the real 48; 65 before the real 66) and spurious/
duplicate termination ticks in multi-tick runs immediately before/at each
real expected tick (e.g. 49,50,51 before/at the real 52; both columns at
91 instead of one).

FINDING 2 UPDATE (2026-08-05): this residual is a genuine IMPLEMENTATION
GAP in the ported budget/`limits` machinery, not merely a harness
per-tick-reset artifact -- correcting a prior mischaracterization in this
docstring. Root-cause diagnosis (per-tick inspection of the oracle's own
`states_before` pre-tick position/fragment-progress values, confirmed
directly against `_okazaki_fragment_progress`/`_okazaki_fragment_length`
computed from the oracle's own historical `polymerizedRegions`): at ticks
46/47/49/50/51 etc. the oracle's own recorded pre-tick state has NOT yet
reached the real completion/initiation boundary, yet THIS diagnostic's
own per-tick advance reaches it early. Replication.m:768-782's primase-
kinetics `limits` (primer-length-vs-progress cap, replacing a flat
`floor(rate*dt)` budget) has since been ported literally
(`_primer_length_capped_step`/`_leading_strand_distance_since_origin`);
it is CONFIRMED CORRECT (matches the literal MATLAB formula, verified by
dedicated unit tests) but CONFIRMED INSUFFICIENT ALONE to close this
specific tick-set mismatch -- re-running this exact scan after that port
still reproduces the identical spurious tick set unchanged (46,47,65
extra-init; 49,50,51,75 extra-term; both columns at 91). The remaining
gap is real production-code missing behavior, most likely
Replication.m:786-808's per-strand `isRegionAccessible` sequence/
occupancy-aware extents and/or the RNA-polymerase-collision and terC/
linking-number stall semantics at Replication.m:820-863 (Finding 4
territory, not yet ported at the time of this update) -- NOT an
inherent, unfixable property of a per-tick-reset construction. It is
explicitly out of scope for the current pass only in the narrow sense
that it has not yet been implemented, not because it is unimplementable
or immaterial. `test_seed0_events_are_a_superset_of_expected_ticks`
below asserts what CAN currently be honestly claimed (every real event
tick is present in both paths, i.e. no event is silently missing); it
deliberately does NOT assert exact equality, and must not be mistaken
for the acceptance criterion Opus specified, nor read as evidence that
exact equality is structurally unreachable.

SSB-CYCLE STOCHASTIC DIVERGENCE (historical context, now empirically
superseded by the finding above -- retained only for provenance):
`_apply_ssb_cycle` (Karr's `dissociateFreeSSBComplexes`/`freeAndBindSSBs`,
Replication.m:568-571) is a genuinely stochastic step (adjudication #3
explicitly permits reusing the RNG there). `test_seed0_events_fire_when_
fed_oracle_ssb_state` below still bypasses `_apply_ssb_cycle` (feeding the
oracle's own, path-consistent SSB occupancy straight through, unmodified)
as a CAUSALITY-ONLY probe (isolating the deterministic position/fragment
machinery from the SSB-cycle's own stochastic draw) -- it is NOT an
acceptance test and its passing must not be read as a claim of real-path
fidelity; see the update above for what it actually demonstrates now
(identical results to the real path, not independent confirmation of
exact-tick correctness).

FINDING 3 UPDATE (2026-08-05): `_advance_replication_forks` now draws one
fair coin per tick (Replication.m:604-607's `randStream.randperm`,
literally reduced to its pairwise marginal: P=1/2 for any 2 elements of a
uniform random permutation) deciding whether `terminateOkazakiFragment`
is drawn to run before or after `unwindAndPolymerizeDNA` in a tick where
that tick's own advance is what completes a fragment -- see
`_advance_replication_forks`'s docstring and
`test_karr_replication_advance_and_terminate.py::
test_finding3_terminate_ordering_coin_same_tick_vs_deferred_no_hint_trajectory`
for the literal port and its dedicated continuous-trajectory regression.
This is drawn from the SAME per-process `self._rng` stream the SSB cycle
(`dissociate_free_ssb_complexes`/`free_and_bind_ssbs`) already draws
from, matching Karr's real model (a single ordered `randStream` per
process, not a separate stream per subfunction) -- so the coin's exact
stream POSITION, and therefore its outcome, now legitimately depends on
how many SSB-cycle draws happened earlier that same tick. At seed0,
every checked tick in the active-replisome window has 26-33 SSB8mer
sites bound, so the SSB cycle's own dissociation draw
(`free_and_bind_ssbs`'s `self._rng.random(ssb_indices.size)`) is
essentially ALWAYS nonzero-length there -- meaning the coin's outcome at
a given tick now routinely differs between the SSB-cycle-bypassed probe
(zero draws before the coin) and the genuine real path (a real,
tick-varying number of draws before the coin). `test_real_path_matches_
bypass_path_exactly_ssb_cycle_no_longer_the_confound` below is corrected
accordingly: its ORIGINAL claim (bypass and real paths produce identical
tick sets) is superseded by this newly-introduced, understood,
MECHANISM-DRIVEN divergence source -- not a return of the ORIGINAL
SSB-cycle confound that test was built to rule out. A companion check
(`test_finding3_coin_is_the_sole_new_real_vs_bypass_divergence_source`)
proves this directly: forcing the SAME external coin value into BOTH
paths (while leaving the SSB cycle's OTHER real draws untouched) restores
exact real==bypass equality, isolating the new divergence to exactly the
coin's stream-position sensitivity and nothing else.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_replay_common import (
    build_state_template,
    cell_vector,
    forbid_sut_oracle_file_io,
    overlay_observable_into_state,
    refresh_allocator_views,
    resolve_trace_path,
)

from opencell.state.chromosome_store import ChromosomeStore
from opencell.vivarium.karr_replication import KarrReplicationProcess

_EXPECTED_INITIATION_TICKS = frozenset({15, 22, 31, 48, 66, 84})
_EXPECTED_TERMINATION_TICKS = frozenset({52, 76, 91, 92})


class _FixedCoinRealSSB:
    """RNG proxy for isolating Finding 3's coin from the SSB cycle's own
    (unaffected, still-genuinely-stochastic) draws: intercepts ONLY the
    no-arg `.random()` call (`_advance_replication_forks`'s coin is the
    sole no-arg `.random()` call anywhere in the no-hint path --
    `_stochastic_round`'s own no-arg `.random()` calls live exclusively in
    `_next_update_from_trace_hint`, never reached here) and returns a
    fixed value for it, while `.random(n)`/`.choice(...)` (the SSB cycle's
    dissociation-mask and site-selection draws) delegate to a real,
    independently-seeded generator so that machinery is untouched."""

    def __init__(self, seed: int, coin_value: float) -> None:
        self._real = np.random.default_rng(seed)
        self._coin_value = coin_value

    def random(self, *args: object, **kwargs: object) -> Any:
        if not args and not kwargs:
            return self._coin_value
        return self._real.random(*args, **kwargs)

    def choice(self, *args: object, **kwargs: object) -> Any:
        return self._real.choice(*args, **kwargs)


def _build_tick_state(trace_path: Path, tick: int) -> tuple[KarrReplicationProcess, dict[str, Any]]:
    process = KarrReplicationProcess({"rng_seed": 0})
    state = build_state_template(process)
    with h5py.File(trace_path, "r") as trace:
        for observable in ("substrates", "enzymes", "boundEnzymes"):
            vec = cell_vector(trace, "states_before", observable, tick)
            wids = process.substrate_wids if observable == "substrates" else process.enzyme_wids
            overlay_observable_into_state(
                process=process, state=state, observable=observable, vector=vec, wids=wids
            )
        store = ChromosomeStore.from_trace_tick(trace_path, tick=tick, group_name="states_before")
    state["chromosome"] = store.to_state()
    state["chromosome"]["replication_state"] = "elongating"
    refresh_allocator_views(process, state)
    return process, state


def _run_events_scan(
    *, bypass_ssb_cycle: bool, fixed_coin: float | None = None
) -> tuple[list[int], dict[int, list[int]]]:
    trace_path = resolve_trace_path("Replication")
    init_ticks: list[int] = []
    term_ticks: dict[int, list[int]] = {}

    for tick in range(100):
        process, state = _build_tick_state(trace_path, tick)
        if fixed_coin is not None:
            # Finding 3 isolation probe: pin the sole no-arg `.random()`
            # call (the same-tick-vs-deferred termination coin) while
            # leaving the SSB cycle's own `.random(n)`/`.choice(...)`
            # draws genuinely stochastic (see `_FixedCoinRealSSB`).
            process._rng = _FixedCoinRealSSB(seed=0, coin_value=fixed_coin)
        if bypass_ssb_cycle:
            # See module docstring: isolates the deterministic topology
            # machine from the separately-scoped SSB-cycle stochastic
            # divergence by leaving `complexBoundSites` exactly as
            # oracle-supplied instead of re-randomizing it from a single,
            # uncorrelated fresh RNG draw.
            process._apply_ssb_cycle = lambda **kwargs: None

        orig_initiate = process._initiate_okazaki_fragments
        orig_terminate = process._terminate_okazaki_fragment_column
        fired = {"init": False, "term": []}

        def _wrapped_initiate(*args, orig=orig_initiate, fired=fired, **kwargs):
            before = kwargs["complex_bound_sites"].positions.size
            result = orig(*args, **kwargs)
            if result.positions.size != before:
                fired["init"] = True
            return result

        def _wrapped_terminate(column, *args, orig=orig_terminate, fired=fired, **kwargs):
            result = orig(column, *args, **kwargs)
            if result[2]:
                fired["term"].append(column)
            return result

        process._initiate_okazaki_fragments = _wrapped_initiate
        process._terminate_okazaki_fragment_column = _wrapped_terminate

        with forbid_sut_oracle_file_io():
            process.next_update(1.0, state)

        if fired["init"]:
            init_ticks.append(tick)
        if fired["term"]:
            term_ticks[tick] = fired["term"]

    return init_ticks, term_ticks


def test_seed0_events_are_a_superset_of_expected_ticks_bypass_probe() -> None:
    """CAUSALITY-ONLY, NON-ACCEPTANCE probe (see module docstring): with
    the SSB-cycle stochastic re-draw bypassed (oracle-consistent SSB
    occupancy fed straight through), every one of Karr's real seed0
    initiation/termination events is still reached (no event is silently
    missing) -- but this does NOT demonstrate exact real-path fidelity:
    both this bypass path and the genuine real path also fire additional,
    spurious near-boundary ticks (see module docstring's Finding 2 update
    for the diagnosed root cause: a genuine implementation gap in the
    ported `limits`/occlusion-extent machinery -- primer-length primase
    kinetics alone confirmed insufficient, per-strand accessibility and
    RNAP-collision/terC stall semantics not yet ported -- not an inherent
    per-tick-reset-harness artifact). Passing this test must NOT be read
    as a claim that the ported topology machine reproduces Karr's real
    event timing exactly, nor that the gap is unfixable.

    FINDING 3 NOTE: this probe uses `bypass_ssb_cycle=True`, so Finding
    3's coin (see module docstring) is always drawn as the tick's first
    `self._rng` call here -- this test's superset claim is therefore
    unaffected by Finding 3 (a deferred completion still shows up on a
    LATER probed tick's own oracle-fed pre-state reaching the same
    boundary independently; it is not depending on any specific tick's
    coin outcome to satisfy the "every expected tick is present"
    property).
    """
    init_ticks, term_ticks = _run_events_scan(bypass_ssb_cycle=True)

    missing_init = _EXPECTED_INITIATION_TICKS - set(init_ticks)
    assert not missing_init, f"missing expected initiation ticks: {sorted(missing_init)}"

    missing_term = _EXPECTED_TERMINATION_TICKS - set(term_ticks)
    assert not missing_term, f"missing expected termination ticks: {sorted(missing_term)}"


def test_real_path_init_ticks_match_bypass_term_divergence_is_finding3_coin_explained() -> None:
    """UPDATED under Finding 3 (2026-08-05): this test's ORIGINAL claim
    (real and SSB-cycle-bypassed paths produce IDENTICAL initiation AND
    termination tick sets) is now superseded and must not be re-asserted
    as-is -- see module docstring's "FINDING 3 UPDATE". Init-tick equality
    still holds unconditionally (initiation never depends on the new
    coin). Term-tick equality NO LONGER holds, and -- unlike an earlier
    draft of this correction -- term EVENT COUNT can also legitimately
    differ (verified empirically: 5 vs 9 at seed0), because this
    harness's own `_build_tick_state` construction resets to a BRAND NEW
    process from the oracle's real pre-tick state every tick (see module
    docstring's PROVENANCE CAVEAT): if the coin defers a completion to
    "next tick's unconditional retry" (see `_advance_replication_forks`),
    that retry never actually happens in THIS harness, because tick+1's
    probe is seeded from the ORACLE's own already-advanced state, not
    from tick t's OC-internal post-advance state -- so a deferred
    completion silently vanishes from this specific scan entirely rather
    than moving to the next tick, for both real and bypass. Real and
    bypass paths defer at different, stream-position-dependent ticks, so
    they can lose different completions to this harness gap, which is
    why total counts also diverge. This is a harness-construction
    artifact of Finding 3 interacting with the per-tick-reset design (NOT
    lost data in the actual, continuously-evolving production code path
    -- see `test_finding3_terminate_ordering_coin_same_tick_vs_deferred_
    no_hint_trajectory` in test_karr_replication_advance_and_terminate.py
    for the continuous 2-tick trajectory proving no real data loss).
    Consequently this test can ONLY honestly assert init-tick equality;
    term-tick/count comparison in this per-tick-reset harness is not a
    meaningful signal under Finding 3 and must not be asserted here. See
    `test_finding3_coin_is_the_sole_new_real_vs_bypass_divergence_source`
    below for the isolation proof that FIXING the coin (removing its
    stream-position sensitivity, not the harness gap) restores exact
    term-tick equality too."""
    real_init, real_term = _run_events_scan(bypass_ssb_cycle=False)
    bypass_init, bypass_term = _run_events_scan(bypass_ssb_cycle=True)

    assert real_init == bypass_init
    # Term-tick/count equality is deliberately NOT asserted here under
    # Finding 3 -- see docstring above. `real_term`/`bypass_term` are
    # still returned by `_run_events_scan` and retained as local
    # variables for readability/debuggability, not asserted against.
    del real_term, bypass_term


def test_finding3_coin_is_the_sole_new_real_vs_bypass_divergence_source() -> None:
    """Isolation proof for the divergence documented above: when BOTH the
    real and bypass scans are run with the SAME externally-fixed coin
    value (via `_FixedCoinRealSSB`, which leaves the SSB cycle's own
    `.random(n)`/`.choice(...)` draws genuinely stochastic and untouched),
    exact real==bypass equality is restored for BOTH initiation and
    termination tick sets, for both coin polarities. This proves the new
    divergence is caused SOLELY by the coin's stream-position sensitivity
    (a legitimate, literal consequence of porting Karr's shared-
    `randStream` semantics) and not by any reintroduction of the original,
    pre-G1 SSB-cycle confound this file's earlier tests were built to
    rule out."""
    for coin_value in (0.1, 0.9):
        real_init, real_term = _run_events_scan(bypass_ssb_cycle=False, fixed_coin=coin_value)
        bypass_init, bypass_term = _run_events_scan(bypass_ssb_cycle=True, fixed_coin=coin_value)

        assert real_init == bypass_init, f"coin={coin_value}: init tick sets diverged"
        assert real_term == bypass_term, f"coin={coin_value}: term tick sets diverged"


def test_seed0_full_pipeline_no_hint_diagnostic_runs_without_exception() -> None:
    """The FULL pipeline (real, non-bypassed `_apply_ssb_cycle`, i.e. the
    genuine no-hint `next_update` branch with no special-casing) must run
    cleanly across all 100 seed0 ticks without raising any fail-closed
    unsupported-condition error, using ONLY `states_before` (never
    `trace_hint`/oracle-after values). This is the honest, reportable
    "full pipeline" seed0/100-tick diagnostic: it does NOT assert the SSB-
    gated event ticks match exactly (see module docstring), only that the
    pipeline itself is exception-free and genuinely non-hint end to end.
    """
    trace_path = resolve_trace_path("Replication")
    for tick in range(100):
        process, state = _build_tick_state(trace_path, tick)
        with forbid_sut_oracle_file_io():
            process.next_update(1.0, state)
