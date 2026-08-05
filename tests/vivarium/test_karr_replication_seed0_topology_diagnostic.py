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
91 instead of one). Root-cause diagnosis (see
`_probe_g1_boundary`-style per-tick inspection performed during this
pass, not committed as a scratch file): at ticks 46/47/49/50/51 etc. the
oracle's OWN recorded `states_before` pre-tick position/fragment-progress
values have NOT yet reached the real completion/initiation boundary
(confirmed directly against `_okazaki_fragment_progress`/
`_okazaki_fragment_length` computed from the oracle's own historical
`polymerizedRegions`) -- but THIS diagnostic's own per-tick
nucleotide-advance budget (`desired_step_bp`
=floor(`fork_polymerization_rate_bp_per_s` * dt), scaled by
`substrates_allocated`; Karr's own `evolveState`/allocator machinery, NOT
part of this topology port's scope, and explicitly preserved unchanged
per the c3 adjudication: "Preserve the existing accepted total
nucleotide-advance/dNTP budget calculation unchanged") does not
reconstruct the REAL oracle's own historical per-tick consumed advance
amount for an ISOLATED, per-tick-reset construction. Our own simulated
advance for that single tick can therefore legitimately reach (and, in
this per-tick-reset harness, immediately act on) a fragment-completion/
initiation boundary a few bp/ticks earlier than the oracle's real,
continuously-accumulated trajectory did. This is a genuine, understood
residual gap in the isolated-tick diagnostic's budget reconstruction --
NOT a defect in the ported position/fragment/merge state machine itself,
and it is explicitly out of scope for this pass per the untouched-budget-
calculation adjudication. `test_seed0_events_are_a_superset_of_expected_
ticks` below asserts what CAN currently be honestly claimed (every real
event tick is present in both paths, i.e. no event is silently missing);
it deliberately does NOT assert exact equality, and must not be
mistaken for the acceptance criterion Opus specified.

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
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import h5py

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


def _run_events_scan(*, bypass_ssb_cycle: bool) -> tuple[list[int], dict[int, list[int]]]:
    trace_path = resolve_trace_path("Replication")
    init_ticks: list[int] = []
    term_ticks: dict[int, list[int]] = {}

    for tick in range(100):
        process, state = _build_tick_state(trace_path, tick)
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
    spurious near-boundary ticks (see module docstring's G1 update for the
    diagnosed root cause: an isolated-per-tick advance-budget
    reconstruction mismatch, not a topology-state-machine defect). Passing
    this test must NOT be read as a claim that the ported topology machine
    reproduces Karr's real event timing exactly.
    """
    init_ticks, term_ticks = _run_events_scan(bypass_ssb_cycle=True)

    missing_init = _EXPECTED_INITIATION_TICKS - set(init_ticks)
    assert not missing_init, f"missing expected initiation ticks: {sorted(missing_init)}"

    missing_term = _EXPECTED_TERMINATION_TICKS - set(term_ticks)
    assert not missing_term, f"missing expected termination ticks: {sorted(missing_term)}"


def test_real_path_matches_bypass_path_exactly_ssb_cycle_no_longer_the_confound() -> None:
    """Opus G1 finding: after the `free_and_bind_ssbs` fork-window scoping
    fix, the GENUINE real path (`bypass_ssb_cycle=False`, i.e. the actual
    no-hint `next_update` branch with no special-casing) produces the
    EXACT SAME initiation/termination tick sets as the SSB-state-bypass
    probe above -- proving the SSB-cycle stochastic re-draw is no longer a
    meaningful source of real-vs-bypass divergence at seed0 (prior to this
    fix, the two paths diverged and the module wrongly attributed ALL of
    that divergence to the SSB-cycle's per-tick-fresh-RNG-draw). This is a
    real, currently-true, and currently-verified claim; it does NOT assert
    exact equality against Karr's real event ticks (see module docstring
    for the separately-diagnosed residual gap that prevents that)."""
    real_init, real_term = _run_events_scan(bypass_ssb_cycle=False)
    bypass_init, bypass_term = _run_events_scan(bypass_ssb_cycle=True)

    assert real_init == bypass_init
    assert real_term == bypass_term


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
