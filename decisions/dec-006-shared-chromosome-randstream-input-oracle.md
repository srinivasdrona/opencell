# DEC-006: Shared `Chromosome.randStream` state is a captured input oracle, not RNG output leakage

**Status:** Active
**Date:** 2026-09-05
**Decision:** Karr's shared `Chromosome.randStream` `.State` scalar (and the
per-tick raw-draw ledger derived from it) is INPUT STATE for L2.1 replay
purposes, on the same footing as the substrate/enzyme/chromosome-occupancy
counts every L2.1 replay harness already overlays from `states_before`/
`states_after`. Capturing it via the extractor and reconciling it offline
into an ordered per-tick raw-draw list is a legitimate, hash-bound
source-fidelity technique for processes whose real stochastic draws come from
this shared stream (TranscriptionalRegulation, DNADamage, and any other
process reachable through `ChromosomeProcessAspect.bindProteinToChromosome`/
`Chromosome.m::sampleAccessibleRegions`/`setSiteDamaged`/`setSiteProteinBound`
family methods) -- it is not an oracle-answer leak and does not violate
`FIX_TEMPLATE_L2_REPLAY.md` Rule 8.

## Renumbering note

Authored and originally numbered `dec-005` on worktree `wave-l21-repinit`
(branch `agent/l21-repinit-20260817`). Renamed to `dec-006` for this
current-main integration candidate because current main independently
already has its own `dec-005` (`decisions/dec-005-full-simulation-
source-hash-binding.md`, a different, unrelated-at-authoring-time but
now-related decision -- see "Related Decisions" below) by the time this
integration was prepared. No content changed beyond the id/filename and
internal self-references; this is the same decision, same date, same
worktree of origin.

## Context

Both the TranscriptionalRegulation L2.1 lane
(`agent/l21-txreg-active-fix-20260903`) and the DNADamage L2.1 lane
(`agent/l21-dnadamage-active-fix-20260903`), working independently on
sibling worktrees, discovered the SAME architectural fact via live-MATLAB
probing: Karr's real per-site/per-position weighted sampling for both
processes is NOT drawn from `this.randStream` (`edu.stanford.covert.cell.
sim.Process.m:283`, private per-process stream), but from `this.chromosome.
randStream` where `this.chromosome` is the shared `Chromosome` STATE object
(`edu.stanford.covert.cell.sim.state.Chromosome.m` extends `CellState.m`,
which constructs/seeds its OWN `RandStream('mcg16807')` the identical way
every process does -- `CellState.m:21,36,42-50`). This stream is a SINGLE
instance, shared and advanced by every one of Karr's ~28 processes that ever
binds/damages/samples chromosome sites in a tick, in whatever per-tick
RANDOMIZED process-evaluation order the scheduler happens to pick
(`extract_per_process_traces_v2.m::evolve_state_with_tap`'s
`randperm(nProcesses)`/`rand_stream.randperm(nProcesses)` loop).

This makes bit-exact, single-process L2.1 replay of the shared stream's
POSITION structurally impossible from first principles alone: an isolated
harness has no way to know how many draws every OTHER process consumed on
this stream, on this tick or any prior one, without modeling the full
28-process ecosystem. Prior sessions on both lanes treated this as an
architectural ceiling and stopped at CODE_GAP with that explanation
(see `STATUS_L21_TXREG_ACTIVE_FIX.md`'s "2026-09-04/05 continuation" section
and `STATUS_L21_DNADAMAGE_ACTIVE_FIX.md`'s "Remaining blockers" #1, both
pre-dating this decision).

That ceiling is real for *inferring* the stream's position from first
principles. It is NOT real for *capturing* the stream's position directly:
`this.chromosome.randStream.state` is a plain, live-readable/writable MATLAB
property (`edu.stanford.covert.util.RandStream.m:273-278`, delegating to the
builtin `RandStream('mcg16807').State`). A live probe
(`scripts/matlab/probe_l21_chromosome_randstream_state.m`, run independently
by both lanes with overlapping seed sets including seed 0) proves:

- `.State` is exactly readable and writable, and a fresh `RandStream` object
  with an injected `.State` value continues drawing bit-identically from
  that exact point (`reconstruction_ok=true` for every seed tested).
- `.State`'s own internal encoding does NOT follow any simple closed-form
  formula either lane derived (`seed*65536 mod M` / `16807*x mod M`) --
  `all_formula_matches=false` in both probes. This means `.State` cannot be
  decoded into either lane's own Python-side LCG state representation
  directly.

Neither of these facts prevents restoring the exact input state, because the
extractor can capture `.State` immediately before/after the target process's
own `evolveState()` tap point (`merge_chromosome_rand_stream_state`, ported
verbatim between lanes into `extract_per_process_traces_v2.m`), and an
OFFLINE, non-destructive MATLAB reconstruction
(`scripts/matlab/reconstruct_chromosome_draw_ledger.m`, also ported verbatim)
can walk a SCRATCH clone stream from `state_before[t]` to `state_after[t]`,
recording every raw `rand()` value along the way -- entirely independent of
`.State`'s internal encoding, since MATLAB itself performs the walk. The
result is an exact, hash-bound, per-tick ordered list of the raw scalar
draws Karr's real shared stream produced for that tick's target-process
window -- not a guess, not an average, not a warmup-count approximation.

## Decision

1. `chromosome_rand_stream_state` (a single opaque `.State` scalar, before
   and after the target process's `evolveState()` tap point) is a permitted,
   ADDITIVE field in `states_before`/`states_after` for any process's
   `extract_per_process_traces_v2.m` extraction. It is INPUT STATE (like
   substrate/enzyme/chromosome-occupancy counts already overlaid every
   tick), never an oracle ANSWER (a binding/damage outcome) -- callers'
   ported algorithms still compute their own result from it.
2. The field name, its tap-point semantics (immediately before/after the
   target process's own `evolveState()` call, inside the real
   allocator-correct per-tick scheduler loop), and the companion
   `reconstruct_chromosome_draw_ledger.m` JSON schema (`trace_sha256`,
   `chromosome_source_sha256`, `randstream_util_source_sha256`, `per_tick[]`
   with `tick`/`state_before`/`state_after`/`n_draws`/`draws`) are FROZEN
   and SHARED across every lane that adopts this technique. Do not rename
   fields, change the tap point, or invent a parallel format -- extend this
   one so traces/ledgers stay interoperable across processes and lanes.
3. Any L2.1 replay harness consuming a ledger MUST fail closed on:
   - a ledger bound (by `trace_sha256`) to a DIFFERENT trace file than the
     one being replayed;
   - a ledger reconstructed against different `Chromosome.m`/`RandStream.m`
     source bytes than currently on disk;
   - the ported algorithm consuming MORE raw draws than the ledger recorded
     for a tick (immediate `RuntimeError` on ledger exhaustion, not a
     silent fresh/repeated value);
   - the ported algorithm consuming FEWER raw draws than the ledger recorded
     for a tick (`assert_fully_consumed()` after the tick completes).
   No silent truncation, padding, or fallback-to-fresh-seed is permitted at
   any point once a ledger is loaded for a given tick.
4. A ledger's ABSENCE (sidecar file simply not present, e.g. because the
   process's trace has not yet been re-extracted with the ledger-capture
   extension) is not an error -- callers fall back to the pre-existing
   freshly-seeded stand-in stream for that replay, with the pre-existing
   CODE_GAP-permitting behavior unchanged.
5. This technique does not, by itself, guarantee full bit-identity: it
   eliminates exactly one variable (the shared stream's per-tick input
   position). Any remaining divergence after adopting it is a genuinely
   narrower, further-debuggable gap in the target process's OWN ported
   draw-count/branch logic -- report it honestly as such, do not retroactively
   re-invoke the "architectural ceiling" framing once this technique is in
   use for that process.

## Arguments For

1. **Matches the actual source semantics.** Every other L2.1 replay harness
   in this project already overlays REAL, oracle-sourced per-tick input
   state (substrate counts, enzyme counts, chromosome occupancy) every
   tick; this is one more per-tick input datum of exactly the same kind
   (a number the target process's own tick depends on), not a new category
   of information.
2. **Independently discovered and independently verified by two lanes.**
   Neither lane copied the other's numeric formula (both probes were run
   fresh, on different seed sets, with overlapping seed 0); both concluded
   the same mechanism and the same "no closed-form decode, but exact
   readable/writable/round-trippable" empirical result. This is a
   convergent, cross-checked finding, not a single session's assumption.
3. **Removes speculation from the STATUS record.** Prior status files on
   both lanes described the shared-stream gap in prose ("architecturally
   unreachable") without a concrete mechanism to test that claim further.
   This decision converts that prose into a falsifiable, hash-bound
   artifact any future session can regenerate and re-check.
4. **No oracle-output leakage.** The ledger never encodes WHICH site won,
   WHAT the damage outcome was, or any other answer -- only the RNG
   generator's position, exactly mirroring how a captured chromosome
   occupancy snapshot encodes "what exists" without encoding "what this
   tick's algorithm should conclude from it."

## Arguments Against (and rejected reasons)

1. **"This just moves the goalposts -- now L2.1 needs a ledger fixture,
   which is more infrastructure than a simple replay."** Rejected: the
   infrastructure is a single additive extractor field plus one offline
   MATLAB reconciliation script, both already fully general (process-
   agnostic) and reused verbatim across two lanes. It is materially less
   infrastructure than modeling the 28-process ecosystem, the only
   alternative path to the same fidelity level.
2. **"A per-tick ledger sidecar is a new provenance surface to keep in
   sync with the trace it's bound to."** Rejected, and structurally
   addressed: the ledger records `trace_sha256` and the exact
   `Chromosome.m`/`RandStream.m` source hashes it was reconstructed
   against; any loader must fail closed on a mismatch (see Decision #3),
   so staleness cannot silently propagate into a replay result.
3. **"This could be seen as tuning the replay to pass."** Rejected: the
   ledger is captured BEFORE any Python-side algorithm runs against it (it
   is extracted directly from the live MATLAB simulation, from the SAME
   run that produced the trace's other input-state fields), and the
   fail-closed over/under-consumption checks mean a wrong Python algorithm
   still fails loudly -- it cannot pass by "fitting" the ledger, only by
   genuinely consuming the same draws in the same order Karr's real
   algorithm did.

## Consequences

- `scripts/matlab/extract_per_process_traces_v2.m`'s
  `merge_chromosome_rand_stream_state`/tap-point wiring becomes a shared,
  cross-lane-maintained extension; future edits to it must consider both
  (all) lanes using it.
- `scripts/matlab/probe_l21_chromosome_randstream_state.m` and
  `reconstruct_chromosome_draw_ledger.m` become shared, reusable tools
  (not process-specific), living under `scripts/matlab/` without a
  process name in the filename.
- Each consuming process gets its own small `<Process>ChromosomeLedgerRandStream`
  subclass of its own process-local mcg16807 shim (e.g.
  `TxRegChromosomeLedgerRandStream`, `KarrLedgerReplayStream`), each
  overriding only the single scalar-draw primitive its own class already
  funnels every higher-level method through -- no shared base class is
  introduced across processes, preserving each process's existing
  provenance-hash isolation (per-process shim files, not a shared RNG
  module).
- Production code paths are unaffected: the ledger stream is ONLY ever
  constructed and injected by an L2.1 replay TEST harness, never by
  `next_update` itself (no oracle-read path in production, per Rule 8).

## Related Decisions

- **DEC-005** (`decisions/dec-005-full-simulation-source-hash-binding.md`):
  a sibling source-hash-binding decision for Cytokinesis/FtsZPolymerization
  event-window traces, drafted independently (worktree
  `fix-dual-cyt-window`) around the same time as this decision's own
  worktree (`wave-l21-repinit`). DEC-005's own "Revisit Triggers" section
  explicitly anticipated this integration's need: *"`extract_per_process_
  traces_v2.m`'s single-process extractor is ever asked to write this
  metadata unconditionally too (closing its own narrower blind spot)."*
  This integration candidate DOES exactly that (see "Consequences" below)
  so that `tests/vivarium/chromosome_rand_stream_ledger.py`'s
  `dnadamage_source_sha256` cross-check (required by main's stricter
  loader, itself introduced to satisfy DEC-005) can also be satisfied by
  ReplicationInitiation's plain (`window_contract=''`), non-DNADamage,
  non-event-window 200-tick trace extraction -- a case DEC-005 explicitly
  scoped OUT of its own fix. Both decisions are compatible and additive:
  DEC-005 fixed the dual-tap event-window extractor's blind spot for
  Cytokinesis/FtsZPolymerization; this integration fixes the SAME
  underlying blind spot in the single-process extractor's own metadata
  write, for every process/window-contract, RepInit's included.

## Consequences (integration addendum)

- `scripts/matlab/extract_per_process_traces_v2.m`'s metadata block now
  writes `dnadamage_source_resolved_sha256` (and its
  `dnadamage_source_original_sha256`/`dnadamage_source_patched_sha256`/
  `dnadamage_source_resolved_path` siblings) for EVERY extracted trace,
  regardless of `canonical_name`/`window_contract` -- not just
  `canonical_name == 'DNADamage'` under `window_contract in {'fixed',
  'anchor'}` as before this integration. `karr_bootstrap()` already
  computes this `dnadamage_overlay` return value unconditionally for
  every call; this is a pure additive relocation of an existing,
  already-computed value into every trace's metadata, not a new
  computation, and does not change any existing DNADamage trace's
  recorded values.
- `scripts/matlab/reconstruct_chromosome_draw_ledger.m` needed no change
  for this: it already reads `dnadamage_source_resolved_sha256` from the
  TRACE's own metadata (not recomputed), so it transparently picks up the
  newly-available field for the RepInit trace once the extractor change
  above lands.
