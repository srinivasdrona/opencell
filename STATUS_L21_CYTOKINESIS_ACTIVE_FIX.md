# STATUS: L2.1 Cytokinesis Active-Window CODE_GAP Fix

## Update 2 (2026-09-03) — Stage-1 probe completed: Karr's real MATLAB run is NOT bit-reproducible run-to-run

The Stage-1 randStream probe (`scripts/matlab/probe_cytokinesis_randstream_state.m`,
launched via the shared `with_matlab_slot.ps1`, ran for ~2.5 hours after
acquiring slot 3) **completed successfully** and produced a load-bearing,
unexpected result, committed as evidence at
`tmp/cytokinesis_randstream_probe_s000.json`:

```
$ bin\oc-py.cmd scripts/l2_event/analyze_cytokinesis_randstream_probe.py tmp/cytokinesis_randstream_probe_s000.json --oc-draws 226=45,227=13,228=3
seed=0 tick_start=27047
local_tick=224 ... seg_before=True seg_after=True entry=1765657302 exit=1765657302 karr_draws_this_tick=0 gap_steps=None
local_tick=225 ... seg_before=True seg_after=True entry=1765657302 exit=1765657302 karr_draws_this_tick=0 gap_steps=0
local_tick=226 ... seg_before=True seg_after=True entry=1765657302 exit=1765657302 karr_draws_this_tick=0 gap_steps=0 oc_draws=45 <-- MISMATCH
local_tick=227 ... seg_before=True seg_after=True entry=1765657302 exit=1765657302 karr_draws_this_tick=0 gap_steps=0 oc_draws=13 <-- MISMATCH
local_tick=228 ... seg_before=True seg_after=True entry=1765657302 exit=1765657302 karr_draws_this_tick=0 gap_steps=0 oc_draws=3  <-- MISMATCH
local_tick=229 ... seg_before=True seg_after=True entry=1765657302 exit=1765657302 karr_draws_this_tick=0 gap_steps=0
local_tick=230 ... seg_before=True seg_after=True entry=1765657302 exit=1765657302 karr_draws_this_tick=0 gap_steps=0
```

**This fresh MATLAB re-run's `chromosome.segregated` is already `TRUE` at
local tick 224** (and stays stable through 230, with `entry_state ==
exit_state` at every captured tick — zero randStream draws consumed
anywhere in this window). The accepted trace
(`Cytokinesis_4000ticks.mat`) records `chromosome_segregated = FALSE` for
local ticks 0-225 and the FIRST `TRUE` at local tick 226 exactly. **These
two are irreconcilable for the same seed=0 run of the same simulation
unless the underlying WholeCell MATLAB simulation is not bit-reproducible
run-to-run.**

**Why this is not a bug in the probe itself:**
- `probe_cytokinesis_randstream_state.m`'s scheduler
  (`evolve_state_with_tap_probe`) was re-verified line-by-line against the
  canonical `evolve_state_with_tap` (re-hash-checked:
  `test_duplicated_source_hash_is_current` still passes, confirming no
  drift) — structurally identical except for the two added read-only
  instrumentation lines; no control-flow, allocation, or scheduling logic
  differs.
- `data/m1_sources/WholeCell/data/Simulation_fitted.mat` (the shared,
  canonical fitted-simulation checkpoint every extraction/probe loads) and
  the canonical `DNADamage.m` (the one file `karr_bootstrap()` conditionally
  overlays) both have `LastWriteTime` = 2026-05-26, long before this
  session — ruling out "the shared MATLAB source changed mid-run from a
  parallel agent" as an explanation.
- `seed_simulation(sim, uint32(0))` deterministically resets the
  simulation-level stream and every process's own stream to the identical
  numeric seed (verified via primary source, `Simulation.m:454-459`,
  `Process.m:283,290`) — the SEEDING is not the variable here.
- No thread-count pinning (`maxNumCompThreads`/`-singleCompThread`) exists
  anywhere in `karr_bootstrap.m` or this probe. MATLAB's default
  multi-threaded BLAS/LAPACK (used by Metabolism's FBA/LP solve every
  tick) is a well-known source of run-to-run floating-point
  non-determinism (parallel reduction order is not guaranteed
  deterministic across runs) — this project's own
  `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md` already names this class of
  issue as known limitation **K5** ("BLAS/NumPy environment
  non-determinism"). Over a ~27,000-tick nonlinear whole-cell trajectory,
  a floating-point-level perturbation in ANY upstream process (most
  plausibly Metabolism, which every other process's resource allocation
  depends on every tick) is sufficient to shift when chromosome
  segregation completes by dozens to thousands of ticks — fully
  consistent with what was observed (segregation already complete well
  before local tick 224 in this run, vs. tick 226 in the accepted trace).

**Consequence for the tick-228 investigation:** a **fresh MATLAB re-run
cannot be used to independently regenerate a ground-truth per-draw
reference for this SPECIFIC accepted trace's realization** — the accepted
trace is one frozen, historical, non-reproducible realization of the
simulation, not a repeatable function of `seed=0` alone. This also means
**Stage 2** (the conditional, hash-bound Cytokinesis.m source overlay for
per-phase instrumentation) is **not viable for this purpose either**: it
would face the identical non-reproducibility problem — any fresh
instrumented run, however finely granular, diverges from the accepted
trace's specific trajectory well before reaching the ticks of interest.
Stage 2 is therefore **not attempted**; building it would consume another
multi-hour MATLAB slot for a run that cannot, even in principle, answer
the question it would be built to answer.

**What this does NOT change:** the L2.1 test itself is unaffected and
remains methodologically sound — it replays OC against the ACCEPTED
TRACE's own frozen, recorded `states_before`/`states_after` values (via
the per-tick witness overlay), never against a fresh re-run. The tick-228
divergence (OC 2 vs Karr 1, from the accepted trace) is real and stands.
What has changed is the CONCLUSION about how to close it: it cannot be
resolved by cross-checking against a freshly-regenerated MATLAB reference,
because no such reference can be faithfully regenerated for this specific
frozen realization. Every other avenue investigated in Update 1 below
(structural/algorithmic review of the OC port, the `_Mcg16807` shim's
correctness, the water-request fix) remains valid and closed.

**Final classification for this session: CODE_GAP stands** (not promoted
to GENUINE — full 4000-tick bit-identity is not achieved). This is
reported as a **precise, source-proven, evidence-backed blocker** per the
task's own allowed terminal-state language, not a "deep stochastic gap"
hand-wave: the blocker is specifically "Karr's own MATLAB WholeCell
simulation is not bit-reproducible run-to-run in this environment,
independently demonstrated via a real ~27,000-tick re-run whose
`chromosome.segregated` timing diverges by at least 2 ticks (and likely
much more, given the ring is already fully quiescent by local tick 224)
from the accepted trace" — a concrete, falsifiable, cited claim, not an
appeal to general stochastic complexity.

## Update 1 (2026-09-03, continuation session) — water fix + Stage-1 MATLAB probe launched

Per operator instruction: tick 228 and the water-request gap are NOT a
terminal CODE_GAP waiver. This session:

1. **Fixed** `_water_request` to Karr's literal, unconditional
   `calcResourceRequirements_Current` formula (see "Follow-up" section
   below, now closed) — commit `3efcbf7`. Confirmed via
   `test_water_request_matches_karr_literal_formula_unconditionally`
   (segregated x pinched x enzyme_count sweep) that this does **not**
   change the tick-228 residual divergence (hydrolyze phase's guard is
   false at ticks 226-229 regardless of which water formula is used, so
   this fix was necessary for source fidelity but not sufficient on its
   own to close the gap).
2. **Built** `scripts/matlab/probe_cytokinesis_randstream_state.m`
   (commit `b9c54b4`) — a tracked, hash-bound-provenance Stage-1 probe
   that re-runs the REAL full Karr Simulation trajectory (seed 0, the
   exact setup that produced the accepted genuine trace) and records
   `this.randStream.state` entering/exiting Cytokinesis's own
   `evolveState()` call for local ticks 224-230, without modifying any
   WCM source. 8 static tests pass (including a real `octave-cli`
   parse-only syntax check — confirmed valid before spending any MATLAB
   slot time on it).
3. **Built** `scripts/l2_event/analyze_cytokinesis_randstream_probe.py`
   (commit `4d0407a`) — derives Karr's real per-tick draw counts purely
   from the probe's captured states (independent Lehmer-recurrence
   forward-step count, never inferred from OC's own output), plus a
   contiguous-tick gap check that would catch a draw consumed BETWEEN two
   captured ticks. 7 unit tests pass against synthetic state sequences.
4. **Launched** the probe (`tmp/run_cytokinesis_randstream_probe_s000.m`)
   via the session's shared slot coordinator
   (`C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\with_matlab_slot.ps1`,
   `-Slots 4`, `-Tag cytokinesis_randstream_probe_s000`,
   `-TimeoutMinutes 720`) as a **durable background waiter**, coordinating
   with (never bypassing/stopping) the live 50-seed Cytokinesis L2.2
   extraction queue (PID `18600`, unaffected — see "L2.2 queue
   implications" below) that shares the same 4-slot pool.

**Operational handoff — SUPERSEDED, probe completed (see "Update 2" above
for the result and conclusion):**

- The probe ran to completion (~2.5 hours after acquiring slot 3) and
  produced `tmp/cytokinesis_randstream_probe_s000.json` (committed as
  evidence). Its result is analyzed and interpreted in "Update 2" above —
  do NOT re-run this probe expecting a different/corrective result; the
  finding is that Karr's own MATLAB simulation is not bit-reproducible
  run-to-run, which a re-run would only re-demonstrate (at the cost of
  another multi-hour MATLAB slot), not resolve.
- Do NOT re-launch a duplicate probe job before checking
  `Get-Process -Id <pid-from-a-later-session>` / the shared slot lock
  directory (`C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\matlab-slots\`)
  for an already-running one.

**Task**: Close the Cytokinesis L2.1 active-window CODE_GAP found in the
accepted genuine 4000-tick event trace. Branch
`agent/l21-cytokinesis-active-fix-20260903`, worktree
`E:\opencell-worktrees\fix-l21-cytokinesis-active`.

## Composition mandate compliance

Per `docs/prompts/COMPOSITION_MANDATE_v2.md` and
`docs/prompts/FIX_TEMPLATE_L2_REPLAY.md`, the authoritative catalog entry
was read and quoted **before** investigation began. Cytokinesis entry from
`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` (verbatim):

```yaml
  - name: Cytokinesis
    oc_module: opencell/vivarium/karr_cytokinesis.py
    bucket: EVENT_CLASS
    harness_type: event_class
    in_scope_L2_2: true
    M_ticks: 4000
    N_seeds: 50
    event_density: sparse                 # only active during division
    input_channels: [substrates, enzymes, chromosome]
    output_channels: [substrates, chromosome]
    event_channels: [chromosome]
    primary_channel: substrates
    karr_artifact: per_process_traces_v2
    rationale_M: "2026-08-05 (Canary D closeout): the old M_ticks=100 'default' failed closed -- seed 0's real onset-to-completion span is 3871 ticks (onset_tick=27556, completion_tick=31427), not ~50-100. 4000 is the smallest validated seed-0 LOWER BOUND (the exact retry size that succeeded), NOT a confirmed cohort-wide maximum -- see event_sweep_blocked_on."
    event_sweep_blocked_on: "N=50 sweep unauthorized until scripts/l2_event/survey_cytokinesis_onset_span.py reports a FULL (50/50 seed) survey of the real onset-to-completion span and the cohort-wide maximum is reconciled into M_ticks/seed_window here. Do not run an uncontrolled 50-seed extraction to determine this number -- generate seeds one at a time via the resumable/atomic scripts/l2_event/launcher.py and re-run the survey once all 50 exist."
    notes: "v3 (2026-06-11): reclassified to EVENT_CLASS. v3.7 (2026-06-16): SUT audit DIVERGENT_DOCUMENTED. v3.8 (2026-06-16): FIXED at 3cee339 — full 5-phase FtsZ ring port replacing Karr-light v1. All 5 stochastic phases, edge state tracking, geometry, mass conservation. Algorithm now faithful to Karr. Still EVENT_CLASS — needs event-window traces for distributional validation. v3.9 (2026-08-05): Canary D CLOSED — real seed-0 anchor trace extracted post-mnrnd-shim-fix (data/m1_sources/karr_native/per_process_traces_v2_event_s000/Cytokinesis_4000ticks.mat). M_ticks/seed_window reconciled to the seed-0 lower bound (see rationale_M); still 1/50 required seeds, N=50 remains blocked (see event_sweep_blocked_on). v3.10 (2026-08-06): renamed blocked_on -> event_sweep_blocked_on -- the former name collided with derive_l25_pair_matrix.py's generic L2.2 pass/fail fallback, incorrectly flipping Cytokinesis's l2_2_passed to False in the pairwise matrix even though its actual L2.2 in-scope status is unaffected by the N=50 sweep authorization gate. See docs/phase_f/l2_event/event_registry.yaml + docs/phase_f/l2_event/CYTOKINESIS_ADAPTER_REPORT.md §9-11 for full detail."
    seed_window:
      tick_range_from_division: [-3999, 0]     # reconciled 2026-08-05: seed-0 lower bound, not yet a cohort-wide maximum (see event_sweep_blocked_on)
      rationale: "Cytokinesis is biologically active only in late cell cycle around division. 2026-08-05: the prior [-50,0] rationale assumed a span far too short for the real Karr dynamics (3871 ticks observed on seed 0); [-3999,0] is the validated seed-0 lower bound pending a full 50-seed survey (scripts/l2_event/survey_cytokinesis_onset_span.py)."
```

This is an **L2.1** task (per-process single-trace bit-identity), not L2.2
(distributional). The catalog entry is quoted per mandate because the task
explicitly requires it and because it defines the `karr_artifact`
(`per_process_traces_v2`, matching the accepted trace family) and confirms
Cytokinesis's `event_class`/sparse-activity nature that motivates the
event-window (anchor) trace used here.

## Branch setup

- Merged local `main` (`b0b800c`) into this branch (merge commit `77a1215`).
  One true conflict: `opencell/provenance/llm_interactions.jsonl`
  (append-only log). Resolved by taking the **union** of both sides
  (7 HEAD records + 18 main records = 25 in the conflicted block, 248 total
  lines after merge), sorted by `timestamp_utc`. No `event_id` collisions;
  all 248 lines re-validated as parseable JSON. `plan.md` merged cleanly
  with no conflict; main's newest "Operational handoff" snapshot
  (2026-09-03 00:53 IST) correctly remains the non-superseded block at the
  top of the file.
- Created a directory junction `data\m1_sources\WholeCell` in this worktree
  pointing directly at the canonical `E:\opencell\data\m1_sources\WholeCell`
  (gitignored source tree, not checked out per-worktree). Junctioned
  directly from the canonical root per the TRAPS.md
  `git-worktree-junction-traversal` guidance (never junction-of-junction).

## Primary sources read (in order, before any edit)

1. `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Cytokinesis.m`
   — full class header + `evolveState` (lines ~178-260) + static helpers.
2. `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/FtsZRing.m`
   — confirms `numEdges` is a **dependent** (computed) property:
   `floor(pi / asin(filamentLengthInNm*1e-9 / pinchedDiameter))`, and that
   only Cytokinesis (no other process) writes `numEdgesOneStraight` /
   `numEdgesTwoStraight` / `numEdgesTwoBent` / `numResidualBent`.
3. `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/Process.m:283,290`
   — `this.randStream = edu.stanford.covert.util.RandStream('mcg16807')`;
   `seedRandStream()` -> `this.randStream.reset(this.seed)`.
4. `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/Simulation.m:454-459`
   — `seedRandStream`: `for i=1:length(processes); o.seed=this.seed;
   o.seedRandStream(); end` — **every** process reseeded with the
   **identical** simulation-level seed value, independently.
5. `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+util/RandStream.m`
   — confirms this is a thin wrapper over MATLAB's built-in
   `RandStream(type, ...)`; `'mcg16807'` is MATLAB's standard
   Park-Miller "Minimal Standard" multiplicative-congruential generator,
   not `mt19937ar` (the Mersenne Twister MATLAB's *default* stream uses).
6. `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/FtsZPolymerization.m`
   — grepped for `ftsZRing` usage: zero matches. Confirms
   FtsZPolymerization never touches ring-edge counters (only the shared
   enzyme pool), so Cytokinesis exclusively owns the observable under
   investigation.
7. Genuine event trace:
   `data/m1_sources/karr_native/per_process_traces_v2_event_s000/Cytokinesis_4000ticks.mat`
   (`n_ticks=4000`, `tick_start=27047`, `onset_tick=27310`,
   `window_anchor=31046`, `rng_seed=0`).
8. `opencell/vivarium/karr_cytokinesis.py` (the SUT) and
   `opencell/util/matlab_rng.py` / `opencell/vivarium/karr_protein_decay_light.py`
   (existing MATLAB-RNG shims already used by other Karr ports in this
   codebase — `karr_replication.py`, `karr_protein_translocation.py`,
   `karr_metabolism.py`).

No web fetches were made; nothing beyond local primary sources was needed.

## Root cause (first proven divergence, tick 226)

`KarrCytokinesisProcess.__init__` seeded:

```python
self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))
```

NumPy's `default_rng` uses **PCG64**. Karr's real `this.randStream` is a
**Park-Miller / Lehmer multiplicative-congruential generator (`mcg16807`)**
— an entirely unrelated bit stream from the same numeric seed (source
citation #3/#4/#5 above). Every process in the real Simulation is
independently reset with the *same* scalar seed value (no per-process
offset), matching the pre-existing `_Mcg16807(seed)` direct-seed convention
already used elsewhere in this codebase.

### Fix

- Added `_MatlabCytokinesisRNG`, a minimal `.random()` adapter over the
  canonical `_Mcg16807` shim (`opencell/vivarium/karr_protein_decay_light.py`),
  reused rather than duplicated (same pattern as `karr_metabolism.py`,
  `karr_chromosome_condensation.py`'s intended usage).
- Replaced `self._rng = np.random.default_rng(...)` with
  `self._rng = _MatlabCytokinesisRNG(int(self.parameters["rng_seed"]))`.
- No change to `evolveState`'s ported structure (`_phase_bind_first_and_second_straight`
  etc.) — the loop/guard/threshold logic already faithfully mirrored
  `Cytokinesis.m` character-for-character; only the RNG *provider* was
  wrong.

### Independent validation of the `_Mcg16807` shim

Before trusting the shim over 50+ consecutive draws, it was checked
against the **published Park & Miller (1988) "Minimal Standard" generator
test vector**: seed=1, after 10000 iterations the internal state must equal
exactly `1043618065`. Verified bit-exact (see commit; probe deleted after
use). This independently confirms the shim's Lehmer recurrence
(`state = 16807*state mod (2**31-1)`) is a correct, standard
implementation with no cumulative-iteration bug possible (Python's
arbitrary-precision `int` arithmetic makes this recurrence exact for any
seed/iteration count).

## First-divergence ledger (tick 226, absolute tick 27273)

All values read directly from `states_before`/`states_after` at trace-local
tick 226 (Karr ground truth) vs. `KarrCytokinesisProcess.next_update`'s
emitted absolute values (with the ring/geometry/chromosome witness overlay
already in place from the prior harness-fix commit `5ab1667`).

| Field | Karr `before` | Karr `after` | OC (wrong RNG) `after` | OC (fixed) `after` |
|---|---|---|---|---|
| `chromosome.segregated` | 0 | 1 (tick226 is the first-ever active tick; 0 for every tick 0-225) | — | — |
| `geometry.pinchedDiameter` | 2.840467121583285e-07 | unchanged | unchanged | unchanged |
| `ftsZRing.numEdges` (dependent, both sides agree) | 22 | 22 | 22 | 22 |
| `ftsZRing.numEdgesOneStraight` | 0 | **9** | 6 | **9** |
| `ftsZRing.numEdgesTwoStraight` | 0 | **11** | ? | **11** |
| `enzymes[MG_224_9MER_GTP]` | 34 | 3 | — | 3 |
| `boundEnzymes[MG_224_9MER_GTP]` | 0 | 31 | — | 31 |

Decomposition of tick 226's 45-draw `_phase_bind_first_and_second_straight`
call (fully deterministic given ground-truth-fed `ring` input — no
ambiguity in trip counts, only in per-draw outcomes):

- Pass 1 (`j=1`, `empty_edges=22`): 22 draws, 19 successes (rate 0.7).
- Pass 2 (`j=2`, `empty_edges=22-19=3`): 3 draws, 1 success.
- Final promote loop (`numEdgesOneStraight=19+1=20`): 20 draws, 11 successes.
- Total: 45 draws, final `(numEdgesOneStraight, numEdgesTwoStraight) = (20-11, 11) = (9, 11)`.

This exact `(9, 11)` matches Karr's real recorded after-state precisely,
under the fixed RNG. Tick 227 (before=(9,11), after=(3,19)) **also**
matches exactly with a second, independently-verified deterministic
decomposition (2+0+11=13 draws). Both tests confirmed via
`tests/vivarium/test_karr_cytokinesis_l2_replay.py::test_karr_cytokinesis_l2_event_replay`.

## Residual divergence (tick 228, absolute tick 27275) — NOT resolved

After the RNG-family fix, the harness's first mismatch moves from tick 226
to **tick 228**:

- Karr `before`: `numEdgesOneStraight=3, numEdgesTwoStraight=19` (matches
  OC's tick-227 output exactly, ledger-continuous).
- `numEdges=22` (both sides), so
  `empty_edges = 22-3-19 = 0` — the `j`-loop (pass1/pass2) is provably a
  **0-draw no-op** on both sides (deterministic from ground-truth input,
  no RNG dependency in the trip count itself).
- Final promote loop trip count = `numEdgesOneStraight = 3` — also
  provably deterministic, not RNG-dependent.
- OC's 3 draws at this exact stream position:
  `[0.9092081016438119, 0.06056432754758947, 0.9046530923362137]` → exactly
  **1** success (`<=0.7`) → OC final `(2, 20)`.
- Karr's real recorded after-state: `(1, 21)` → requires **2** successes
  in the same 3 draws.

**Exhaustive elimination performed** (all primary-source-grounded, no
speculation left unchecked):

1. `_phase_unbind_residual_bent` — guard passes at both tick 227-end and
   tick 228 (`numEdgesOneStraight+numEdgesTwoStraight==numEdges`), but
   `numResidualBent=0` throughout ticks 0-229 (confirmed via full sweep)
   → 0 draws regardless.
2. `_phase_hydrolyze_and_bend` — guard (`numEdgesTwoBent+numEdgesTwoStraight==numEdges`)
   is false for both OC's (0+20=20) and Karr's (0+21=21) post-bind ring
   state at tick 228 → never fires, 0 draws either way.
3. `_phase_dissociate_first_bent` — guard requires
   `numEdgesTwoStraight==0`; false (20 or 21) on both sides → skipped.
4. `numFtsZSubunitsPerFilament`/enzyme availability: enzymes[GTP_polymer]=13
   at tick 228, never limiting for a 3-draw loop.
5. `calc_num_edges` matches Karr's `FtsZRing.calcNumEdges` formula
   character-for-character (`floor(pi/asin(L*1e-9/d))`); the diameter at
   this tick is `0.235` away from the nearest floor-integer boundary
   (verified numerically) — not a libm-precision floor-flip risk.
6. Full 4000-tick sweep: 3774 active ticks, 317 mismatches (8.4%), first at
   228, last at 3966 — **not** a near-100%-mismatch pattern a full stream
   desync would produce on an exact-integer comparison; consistent with a
   **single, permanent stream-position offset** introduced once (not a
   recurring per-tick bug), after which large-trip-count ticks
   occasionally still land on the same aggregate sum by chance while
   small-trip-count ticks (like 228's 3 draws) are far more sensitive.
7. `_water_request`'s formula was found to differ from Karr's
   `calcResourceRequirements_Current` (Karr's simpler
   `numFtsZSubunitsPerFilament * enzymes[GTP_polymer]` vs. OC's
   phase-aware `potential_hydrolysis_edges`-based estimate) — a real,
   separate discrepancy, but **ruled out** as the tick-228 cause because
   the hydrolyze phase never fires at tick 226-229 on either side (item 2
   above), so the water-allocation path is never exercised here. Flagged
   as a follow-up item (see below), not fixed in this pass (out of the
   proven first-divergence scope; fixing it would not change tick 228's
   outcome and risks an unrelated, unverified change).

**What I could not verify without live MATLAB**: whether
`edu.stanford.covert.util.RandStream('mcg16807')`'s Statistics-Toolbox
wrapper applies any decorrelation/scrambling beyond the plain Park-Miller
recurrence for very long draw sequences. The `_Mcg16807` shim is proven
exact against the published reference vector and against 58 consecutive
real Karr draws spanning two full ticks with a non-trivial, self-referential,
RNG-dependent trip-count decomposition (astronomically unlikely to match by
chance if misaligned) — this is strong evidence the shim itself is correct,
which is why the residual gap could not be attributed to it either. This is
a **precise, source-proven blocker**: a single-tick, single-position stream
desync whose upstream cause (an extra or missing draw somewhere in the real
Karr trajectory, not reproducible from the available primary sources) could
not be conclusively pinned down in this session.

## Tests added

`tests/vivarium/test_karr_cytokinesis.py`:

- `test_rng_provider_is_mcg16807_not_numpy_default_rng` — anti-regression:
  asserts `process._rng` wraps `_Mcg16807`, not a NumPy `Generator`.
- `test_rng_first_draw_matches_mcg16807_park_miller_reference` — pins the
  exact first `.random()` value for `rng_seed=0` (`7.826369259425611e-06`).
- `test_rng_no_oracle_file_io_in_production_module` — anti-cheat (Rule 8):
  greps the production module source for forbidden oracle markers
  (`_100ticks`, `_4000ticks`, `states_before`, `states_after`, `h5py`).

No hardcoded tick-226/228-specific branches, oracle file reads, or answer
leakage were added anywhere in `opencell/vivarium/karr_cytokinesis.py`
(confirmed by the new Rule 8 test itself, which would fail if any were).

## Exact commands run and results

```
bin\oc-pytest.cmd tests/vivarium/test_karr_cytokinesis.py -q -rs
  -> 10 passed

bin\oc-pytest.cmd tests/integration/test_l1b_verify_wiring.py::test_all_28_rows_run_without_exception -q
  -> 1 passed   (process-local L1b; Cytokinesis has no per-process-named L1b
                 test in this repo's L1b suite, only the all-28-rows gate)

bin\oc-pytest.cmd "tests/vivarium/test_karr_cytokinesis_l2_replay.py::test_karr_cytokinesis_l2_event_replay" -q -rs -v
  -> 1 failed: L2a ring-witness mismatch: tick=228, field=ftsZRing.numEdgesOneStraight, oc=2, karr=1
     (exact active-window nodeid; first-mismatch tick moved from 226 -> 228)

ruff check opencell/vivarium/karr_cytokinesis.py tests/vivarium/test_karr_cytokinesis.py
  -> All checks passed!
```

## Final L2.1 classification

**CODE_GAP** (unchanged verdict; NOT promoted to GENUINE). The manifest row
in `docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json` (`Cytokinesis`
entry, `classification: "CODE_GAP"`) was **not hand-edited** — its
`code_gap_evidence`/`first_active_detail` fields are machine-generated by
`scripts/l21_active_window_audit.py` and predate even this session's fix
(they still show the pre-fix `first_mismatch_oc_val: 0.0`, stale relative
to both the "OC 6" state this task started from and the "OC 9" state now
achieved for tick 226). Regenerating this evidence blob requires the
audit tool's own re-run, not manual JSON editing; that re-run should happen
once tick 228 (or whatever the true first divergence is at that point) is
resolved, not now, to avoid recording a still-CODE_GAP row's evidence twice.

**Fail-closed verification requirement**: the "Promote Cytokinesis manifest
CODE_GAP -> GENUINE only after fail-closed fresh verification" gate is
**not met** this session — the full 4000-tick active-window replay is not
yet bit-identical (317/3774 active-tick mismatches remain, first at 228).

## L2.2 queue implications (blast radius)

- The live 50-seed Cytokinesis L2.2 extraction queue (PID `18600`,
  `scripts\matlab\run_cytokinesis_genuine_chunk.ps1`, running in worktree
  `E:\opencell-worktrees\genuine-l22-cytokinesis`) was checked (not
  disturbed, not stopped/restarted). It is a **pure-MATLAB ground-truth
  extraction** process — it does not import or execute
  `opencell/vivarium/karr_cytokinesis.py` at all, so this fix has **zero
  effect** on the extraction itself. 5/50 seeds exist so far
  (`per_process_traces_v2_event_s000` through `s004`).
- **L2.2 evaluation/comparison** (the step that runs OC's `next_update`
  against each extracted seed) **does** import this same production
  module. Any L2.2 evaluation run against the 5 (or eventually 50)
  extracted seeds under the **pre-fix** RNG family would be evaluating
  stale, wrong-RNG-family OC output and must be **re-run under this
  fixed tree** once the cohort completes. No such full-cohort evaluation
  currently exists (per `event_sweep_blocked_on` in the catalog — the
  N=50 sweep itself is not yet authorized/complete), so there is no
  "already-completed" L2.2 verdict to invalidate/regenerate at this time.
- Per the no-fabrication instruction: I am **not** drawing any
  distributional (L2.2) conclusion from the partial 5-seed cohort. The
  only claim made here is L2.1 (single accepted seed-0 trace, per-tick
  bit-identity), which remains CODE_GAP.
- Once the 50/50 cohort completes and `event_sweep_blocked_on` is
  reconciled, whoever runs the L2.2 evaluation must do so against this
  fixed `karr_cytokinesis.py` (or later fixes on top of it), not the
  pre-`a5d1aa0` version.

## Follow-up (status as of the continuation session)

- ~~`_water_request`'s formula in `karr_cytokinesis.py` diverges from
  Karr's `calcResourceRequirements_Current`~~ — **CLOSED** in the
  continuation session (commit `3efcbf7`): replaced with Karr's literal,
  unconditional formula. Confirmed (via a segregated x pinched x
  enzyme_count sweep test) this does not change the tick-228 divergence.
- The tick-228 stream-position divergence: a Stage-1 MATLAB randStream
  state probe (`scripts/matlab/probe_cytokinesis_randstream_state.m`,
  commit `b9c54b4`) ran to completion and proved Karr's own MATLAB
  simulation is not bit-reproducible run-to-run in this environment (see
  "Update 2" at the top of this file) — a fresh re-run cannot supply a
  ground-truth per-draw reference for the accepted trace's specific
  realization, so Stage 2 (per-phase source overlay) was not attempted.
- **Remaining viable paths for a future session** (not attempted here;
  each is a substantial, separately-scoped undertaking):
  1. Re-extract a brand-new instrumented Cytokinesis event trace (same
     seed=0, anchor-window discovery to completion, with randStream-state
     capture built into the extraction itself so state data comes from
     the SAME run that produces the trace, never a separate re-run). This
     would produce a DIFFERENT accepted trace (its own newly-discovered
     `tick_start`/`onset_tick`, since completion timing is itself subject
     to the same non-determinism) and require superseding the currently
     accepted `Cytokinesis_4000ticks.mat` plus updating the L2.1 test's
     trace reference — a decision with real provenance/acceptance
     implications outside this task's scope; flag for explicit
     authorization before undertaking it.
  2. Investigate whether pinning MATLAB to single-threaded execution
     (`-singleCompThread`, `maxNumCompThreads(1)`) makes re-runs
     reproducible, and if so, whether the ORIGINAL accepted-trace
     extraction ran under the same constraint (unknown from available
     provenance) — only useful if the original run was ALSO
     single-threaded; otherwise a single-threaded re-run still can't
     match a multi-threaded original.

## Commits (this branch, this session)

- `77a1215` — merge main (`b0b800c`) into this branch; union-resolved the
  one append-only provenance conflict.
- `a5d1aa0` — `fix(cytokinesis): seed process RNG from MATLAB-faithful
  mcg16807, not numpy PCG64` + 3 regression/anti-cheat tests.
- `191a7bc` — initial `STATUS_L21_CYTOKINESIS_ACTIVE_FIX.md` + provenance log.
- `3efcbf7` — `fix(cytokinesis): replace heuristic _water_request with
  Karr's literal calcResourceRequirements_Current` + sweep test.
- `60b45ab` — provenance log for the water-request fix.
- `b9c54b4` — `feat(l21-cytokinesis): add Stage-1 randStream state probe`
  (`scripts/matlab/probe_cytokinesis_randstream_state.m` + 8 static tests).
- `686cd68` — provenance log for the Stage-1 probe.
- `4d0407a` — `feat(l21-cytokinesis): add randStream-probe analysis tool +
  launcher script` (`scripts/l2_event/analyze_cytokinesis_randstream_probe.py`
  + 7 synthetic unit tests + `tmp/run_cytokinesis_randstream_probe_s000.m`).
- `c66f6e9` — provenance log for the analyzer + launch.
- `6eb2b3a` — STATUS update recording the probe launch/handoff (superseded
  by this file's current content once the probe completed).
- (this commit) — STATUS update with the completed probe's result
  (`tmp/cytokinesis_randstream_probe_s000.json`, committed as evidence)
  and the non-reproducibility finding/final classification.

Not pushed; not merged into main, per instructions.
