# L2.event Window Extractor Contract (M4, documentation-only)

Status: **contract implemented in code, not yet run.**
`scripts/matlab/extract_per_process_traces_v2.m` now accepts an optional
`window_contract` ('fixed' | 'anchor') + `anchor_opts` argument pair that
writes exactly the metadata keys this document specifies (including the
`onset_tick` timing anchor and the flattened numeric event-observable
projection, both added to close the Opus 5 rejection findings below), and
`scripts/l2_event/launcher.py` provides the MATLAB-free planning/command-
builder surface (validate-before-skip via the unmodified
`window_loader.load_event_window`, `require_stride_contract=True`). No
MATLAB/Octave extraction has been run or is proposed by this document or by
that code; the two real event MATs on disk today (below) are unchanged.
This document remains the unambiguous target both pieces of code were
written against (and the doc `window_loader.py` points to from its refusal
messages).

## Why this exists

`scripts/l2_event/window_loader.py` (D1: "per-tick fully enumerated window
loader") must refuse any trace that is not a complete, dense, stride-1
event-window grid over a well-defined tick range (requirement 4: "Runner
must refuse missing/incomplete stride-1 window"). To do that mechanically
-- not by eyeballing the data -- the loader needs three pieces of metadata
that are *not currently produced* by the existing (pre-event) extractor
generation:

| Key | Type | Meaning |
|---|---|---|
| `stride` | int | Tick spacing between consecutive samples in the grid. **Must equal 1** for a fully enumerated window; any other value means the grid is sparse/subsampled and is refused (`EventWindowRefused("INCOMPLETE_WINDOW", ...)`). |
| `tick_start` | int | The absolute (1-based simulation-tick) coordinate at which the window begins. All tick-valued metadata (`tick_start`, `tick_end`, `window_anchor`, `onset_tick`) share this **single absolute coordinate system**; local grid row `i` (0-based) maps to `tick_start + i` (see `WindowGrid.absolute_tick`). For `window_contract='fixed'`, burn-in consumes absolute ticks `1..tick_offset` *before* capture begins, so `tick_start == tick_offset + 1` (never `tick_offset` itself); `metadata/tick_offset` always records the burn-in tick **count**, never a discovered/derived tick. |
| `tick_end` **or** `window_anchor` | int / float | The window's other boundary. A **fixed-length** window (e.g. "100 ticks starting at tick_start") records `tick_end`. A **division/event-anchored** window (e.g. "N ticks ending at the observed completion event, wherever that falls per-seed") instead records `window_anchor` -- the **capture-boundary** tick, i.e. the completion tick the fixed-size window ends at -- since `tick_end` is seed-dependent in that case. At least one of the two is required ("as applicable" per the governing requirement); a trace with neither is refused. |
| `onset_tick` | int, optional | **Timing anchor**, distinct from `window_anchor`. Present only for `signal_kind='diameter_decrease'` anchor windows (ratified Cytokinesis timing decision, 2026-08-02): the observed *first strict decrease* of `CellGeometry.pinchedDiameter` (contraction onset), never a caller-supplied or fabricated value. Must satisfy `tick_start <= onset_tick < window_anchor`. `completion_tick` is **not** a separate persisted key -- it is a derived alias for `window_anchor` (`WindowGrid.completion_tick`); persisting a second redundant completion field was deliberately rejected to avoid two sources of truth for the same tick. |

**`window_anchor` (capture boundary) vs. `onset_tick` (timing anchor) --
do not conflate the two.** `window_anchor`/`completion_tick` is *where the
fixed-size window ends* (so every trace in a cohort has the same
`n_ticks`, satisfying the D1 "complete, dense, stride-1 ... grid" contract
even though the absolute tick of division varies per seed). `onset_tick`
is *when the timing-relevant biological event actually started*, discovered
independently from the same real signal. `tick_offset` is **never** timing
arithmetic -- it is burn-in/window-placement bookkeeping only (the tick at
which capture began), and must never be read as if it were `onset_tick` or
`window_anchor`. A future Cytokinesis adapter (e.g.
`scripts/l2_event/adapters/cytokinesis.py` in a downstream branch) that
computes a division-relative offset **must** read `window.onset_tick`/
`window.completion_tick`, and must cross-check the metadata `onset_tick`
against the trace's own flattened `pinchedDiameter` before/after values
(see below) rather than trusting the metadata field alone -- a metadata
field with no matching observed transition is a contract violation, not a
valid input.

`window_loader._check_stride_contract()` checks exactly these three
conditions and returns a list of human-readable problem strings (empty =
compliant). Callers choose whether the contract is fatal
(`require_stride_contract=True`, the default, used by any real gate
computation) or advisory-only (`require_stride_contract=False`, used only
by `run_structural_smoke()`'s read-only loader smoke, which explicitly
cannot produce a gate verdict either way).

## Current state of the real event MATs on disk

**Canary-A closeout update:** the RibosomeAssembly seed-000 file below was
regenerated with a complete `stride`/`tick_start`/`tick_end` contract
(`stride=1`, `tick_start=201`, `tick_end=300`, `tick_offset=200`
burn-in ticks, `n_ticks=100`) -- see
`RIBOSOME_ASSEMBLY_GATE_ADAPTER_REPORT.md`'s "Canary-A closeout" section
for the verified regeneration. It no longer predates this contract. The
sibling `RNAModification` seed-000 file (an incidental finding, not one of
the four EVENT_CLASS target processes) is untouched by this closeout and
still predates the contract:

* `data/m1_sources/karr_native/per_process_traces_v2_event_s000/RibosomeAssembly_100ticks.mat`
  -- **now carries** the full `stride`/`tick_start`/`tick_end` contract.
* `data/m1_sources/karr_native/per_process_traces_v2_event_s000/RNAModification_100ticks.mat`
  -- still does **not** carry `stride`, `tick_start`, `tick_end`, or
  `window_anchor` (untouched, out of this closeout's scope).

Consequences of the RibosomeAssembly file's contract now being complete:

* `load_and_check_window(..., require_stride_contract=True)` (the strict
  default used by any real gate computation) now **succeeds** on this
  file -- it no longer raises `EventWindowRefused("INCOMPLETE_WINDOW",
  ...)`. This does **not** make the file gate-eligible: only 1 of the
  registry's required 50 ensemble seeds exists on disk, so
  `evaluate_gate`'s ensemble-size gauntlet independently refuses with
  `SINGLE_SEED_ENSEMBLE_REQUIRED` regardless of window-contract
  completeness.
* `run_structural_smoke()`'s relaxed load
  (`require_stride_contract=False`) now reports `stride_contract_ok=True`
  with zero problems for this file (see the `stride_contract_ok`/
  `stride_contract_problems` fields on `run_structural_smoke()`'s result
  and the corresponding `reasons` entry in the written evidence) -- this
  was previously `False` under the pre-Canary-A file and is correctly
  updated now that the underlying data genuinely satisfies the contract.
* The RibosomeAssembly seed-0 smoke's verdict remains `NOT_APPLICABLE`,
  not `PASS` -- it is a structural loader/adapter round-trip smoke, not a
  calibrated gate verdict, regardless of the stride contract's
  completeness.
* A real (non-smoke) gate computation against the untouched
  `RNAModification` file with the default `require_stride_contract=True`
  still raises `EventWindowRefused("INCOMPLETE_WINDOW", ...)` -- this
  remains intentional and must not be worked around by loosening the
  loader; that file's extractor output must be fixed instead, if and when
  `RNAModification` is ever brought into v4 scope.

## What the extractor emits (`window_contract='fixed'`/`'anchor'`)

For each `metadata` group in a trace file intended for `L2.event` gate
computation (not structural smoke), in addition to the existing required
keys (`n_ticks`, `process_name`, `rng_seed`, and the event-window
discriminator `tick_offset`):

```text
metadata/stride       -- int, must be 1 for a real gate computation
metadata/tick_start    -- int, absolute window start (single tick coordinate system)
metadata/tick_end      -- int, present for fixed-length windows
   -- or --
metadata/window_anchor -- int/float, present for division/event-anchored windows
                           (at least one of tick_end/window_anchor required)
metadata/onset_tick     -- int, present ONLY for signal_kind='diameter_decrease'
                           anchor windows: the observed onset (timing anchor),
                           distinct from window_anchor (capture boundary).
```

No other change to the extractor's per-tick payload encoding or directory
layout (`per_process_traces_v2_event_s{seed:03d}/`) is implied by this
contract beyond the numeric event-observable projection described below.
`stride`/`tick_start`/`tick_end` are derived mechanically from the
caller-supplied `tick_offset` burn-in for `window_contract='fixed'`;
`tick_start`/`window_anchor`/`onset_tick` for `window_contract='anchor'`
are discovered from a real, observed simulation signal
(`capture_anchor_window()` in `extract_per_process_traces_v2.m`) -- never
fabricated, never derived from an expected/desired outcome. See
`scripts/l2_event/launcher.py` for the corresponding MATLAB-free
planning/command-builder surface (specs, CLI, validate-before-skip).
Neither piece of code has been run against a real simulation as part of
writing this contract update.

### Anchor-window observed predicates

Two `signal_kind` values are supported, both evaluated from the same
before/after tap-point snapshots `evolve_state_with_tap` already takes at
every tick (never a persistent end-of-tick boolean, which cannot
distinguish "already true at window entry" from "just became true"):

* `'diameter_decrease'` (default; the ratified Cytokinesis timing
  decision) -- **onset**: the first tick where
  `before.pinchedDiameter > after.pinchedDiameter >= 0` (a genuine strict
  decrease, with a captured prior value proving it was not already at its
  final value). **Completion** (`window_anchor`): the later tick where
  `before.pinchedDiameter > 0 && after.pinchedDiameter == 0`. The vestigial
  OpenCell `cell.ftsz_ring_complete` flag and any normalized whole-cell-cycle
  position are **never** used for this signal.
* `'boolean_transition'` (generic fallback for a non-Cytokinesis process) --
  the first tick where `before.(signal_field)` is `false` and
  `after.(signal_field)` is `true`: a genuine observed false->true
  transition with a captured prior value, never an immediate/first-tick
  "already true" state accepted as if it were a real transition.

A **fixed** window (`window_contract='fixed'`) has no onset/completion
predicate at all -- it is simply the dense stride-1 grid
`[tick_offset + 1, tick_offset + n_ticks]` (burn-in consumes absolute
ticks `1..tick_offset` before capture begins); that grid's completeness is
the only thing validated for it.

### Numeric event-observable projection

`window_loader._cell_series()` can only materialize per-tick **numeric or
logical scalars** from an HDF5 cell array -- never a raw MATLAB
object/struct. The generic snapshot machinery
(`pick_snapshot_properties()`/`sanitize_snapshot_value()`) does not include
`geometry`/`ftsZRing` and would sanitize them to an opaque
`<object:ClassName>` placeholder string if it did. `merge_event_observables()`
therefore adds a **separate, additive** flattened numeric projection at the
exact tap points used for onset/completion detection, so an anchor trace's
`states_before`/`states_after` groups always contain loader-usable
top-level fields:

* `pinchedDiameter` (before/after) -- for `signal_kind='diameter_decrease'`.
* `ftsZRing_numEdgesOneStraight`, `ftsZRing_numEdgesTwoStraight`,
  `ftsZRing_numEdgesTwoBent`, `ftsZRing_numResidualBent` (before/after) --
  the four FtsZRing ring-state witnesses `Cytokinesis.evolveState()` itself
  gates the diameter update on, included so onset/completion can be
  cross-checked against the real ring state that produced them.
* `chromosome_segregated` (before/after, logical) -- for
  `signal_kind='diameter_decrease'` only. `Chromosome.segregated`
  (`data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/
  Chromosome.m`) is the exact, and only, chromosome-state scalar
  `Cytokinesis.evolveState()` itself reads (`if ~this.chromosome.segregated;
  return; end`). Flattening this one scalar makes the full sparse
  `chromosome` object unnecessary for this signal_kind: `pick_snapshot_
  properties()`'s generic `chromosome` snapshot (used by other processes'
  fixed/generic-anchor windows, and by `signal_kind='boolean_transition'`)
  is deliberately EXCLUDED for `window_contract='anchor'` +
  `signal_kind='diameter_decrease'` traces only, since the anchor search
  loop taps before/after state for up to `max_search_ticks` (default
  50000) ticks and serializing the full sparse Chromosome object twice per
  searched tick is unbounded, unnecessary snapshot cost once this scalar
  is available. Fixed windows and generic `boolean_transition` anchors are
  unaffected -- their `chromosome` snapshots (if `chromosome` is in that
  process's `pick_snapshot_properties()` set) are unchanged.
* `(signal_field)` (before/after, logical) -- for `signal_kind='boolean_transition'`.

Every projected field is validated present, scalar, numeric/logical as
appropriate, and finite before the extractor will accept a captured
window; `window_loader.load_event_window`'s
`require_scalar_finite_observables` parameter re-checks the same guarantee
at load time (never trusting the extractor alone). This projection never
saves an opaque object/struct cell that the loader cannot load, and never
replaces the existing `substrates`/`enzymes`-style observable machinery
used by fixed windows (which never populates it -- `merge_event_observables`
is only invoked when `anchor_opts` is supplied).

### Fixed circular capture window, and fail-fast on an incomplete result

An anchor window captures a **fixed `n_ticks`-length circular buffer
ending at the completion tick**, so every trace in a cohort has an equal
window length regardless of when division happens to occur for that seed.
`capture_anchor_window()` fails the extraction outright (raises a MATLAB
error; never writes a partial/incomplete file) if any of:

* the full `n_ticks`-length window was not collected before completion
  fired (i.e. completion fired before the circular buffer had filled);
* completion is never observed within `max_search_ticks`;
* (`diameter_decrease` only) onset is never observed, or
  `onset_tick < tick_start`, or `onset_tick >= window_anchor` (onset must
  fall strictly inside the captured window and strictly before completion).

The search stops at the **first** observed completion tick (break); there
is no duplicate-completion detection, and none is claimed -- a first
observed completion plus an immediate stop is the accepted, sufficient
behavior.

There is deliberately no code path that produces a file with some but not
all of these invariants satisfied; a timing-incomplete file must never be
silently written or silently accepted as valid downstream.

### Anchor-config identity-binding metadata

In addition to `tick_start`/`window_anchor`/`onset_tick`, every
`window_contract='anchor'` trace also persists the exact anchor
configuration it was produced for:

```text
metadata/signal_kind                       -- char, e.g. 'diameter_decrease'
metadata/signal_property                   -- char, e.g. 'geometry'
metadata/signal_field                      -- char, e.g. 'pinchedDiameter'
metadata/max_search_ticks                  -- int32
metadata/event_observable_projection_version -- int32 (currently 2; bumped
                                                 from 1 by the performance/
                                                 sufficiency patch that added
                                                 chromosome_segregated and
                                                 removed the full chromosome
                                                 object from
                                                 signal_kind='diameter_decrease'
                                                 anchor traces -- a stale v1
                                                 on-disk trace, either
                                                 signal_kind, must refuse/
                                                 regenerate, never silently
                                                 skip-valid against a v2 spec)
```

`scripts/l2_event/launcher.validate_existing_event_window` cross-checks
all five of these against the requested `AnchorWindowSpec` before ever
returning `skip_valid` -- a trace produced for a *different*
`signal_kind`/`signal_property`/`signal_field`/`max_search_ticks`, or
under a stale observable-projection schema version, can never silently
satisfy a different anchor request. For `window_contract='fixed'`,
`validate_existing_event_window` likewise cross-checks
`metadata/tick_offset == spec.tick_offset`,
`metadata/tick_start == spec.tick_offset + 1`, and
`metadata/tick_end == spec.tick_offset + spec.n_ticks` exactly.

A future Cytokinesis adapter must additionally cross-check the metadata
`onset_tick` against the trace's own flattened `pinchedDiameter`
before/after values (see above) -- metadata identity agreement alone is
necessary but not sufficient; the adapter must also confirm the numeric
transition the metadata claims is actually present in the data.

### Atomic regeneration: unique per-job token

A `regenerate_invalid` job never writes to a bare, reusable `.tmp-regen`
directory. `scripts/l2_event/launcher.allocate_unique_temp_output_path`
mints a fresh random token per job and confirms its
`.tmp-regen-<token>` directory does not already exist before the job is
emitted, so two plans (or a stale leftover directory from an
interrupted/abandoned prior run) can never collide. `finalize_atomic_regeneration`
requires that same `expected_token` (the temp directory name must embed
it) plus the pre-run manifest hash (`WindowDecision.prior_file_sha256`,
the real file's SHA-256 captured at plan time) before it will even
attempt `os.replace`; if the real file's current hash no longer matches
that manifest, or the temp directory's token doesn't match, finalize
refuses and leaves the real file byte-identical. `scripts/l2_event/
launcher.list_stale_regeneration_temp_dirs` is a read-only lister for
leftover `.tmp-regen-*` directories -- it never deletes anything; the
real trace files never live inside a `.tmp-regen-*` directory, so no
future cleanup tool built on its output could ever touch final evidence.

### Safe spec identifiers (shell-boundary hardening)

`_matlab_quote` (`scripts/l2_event/launcher.py`) secures only the MATLAB
single-quoted string-literal context (doubling an embedded `'`, MATLAB's
own escaping convention) -- it does not, by itself, secure a future shell
boundary a job runner might invoke this command string through (e.g.
`wsl bash -c "matlab -batch '...'"`; no such invocation exists in this
module). The actual defense is applied at `FixedWindowSpec`/
`AnchorWindowSpec` construction time: `process`, `signal_property`, and
`signal_field` are rejected outright (`_require_safe_identifier`,
independent of and before `_matlab_quote` is ever applied) if they
contain a double quote, backtick, `$`, `;`, or a newline/carriage-return
-- the characters that could break out of that future shell boundary
regardless of MATLAB-level quoting. A plain embedded single quote is
deliberately NOT rejected here: it is a legitimate character that
`_matlab_quote` already escapes correctly (see
`test_build_matlab_command_quotes_embedded_single_quote_in_process_name`).

### MATLAB failure propagation

`extract_per_process_traces_v2.m`'s per-process loop accumulates failures
(process-not-found, or any tick/anchor-search error) across all requested
processes, still `fprintf`ing a diagnostic line for each so multi-process
runs keep their per-process visibility. After the loop, if any process
failed, the function throws (`error(...)`), which `build_matlab_command`'s
`try/catch` converts into a nonzero process exit code. A batch can never
exit 0 while a requested process silently failed to extract.

### Static parse checking (no MATLAB/Octave simulation run)

Chained dynamic-field access (e.g. `a.(b).(c)`) is **valid MATLAB/Octave
syntax** -- it is not, and was never, a parse defect; any earlier claim to
the contrary in this document or in test code was incorrect and has been
removed. `merge_event_observables()`'s two-step
temporary-variable dereference (`container = mod.(container_name);` then
`container.pinchedDiameter`) is kept as a readability/validation choice
(each dereference gets its own `isprop`/`isfield` check), not as a
required workaround.

A genuinely parse-only (never-executing) static check IS possible and was
verified empirically in a disposable scratch directory (never against
this repository's real extractor file, and with no simulation/bootstrap
ever invoked): prefixing a `.m` file with a leading `1;` statement turns
every subsequent `function ... end` definition into a **local function**
inside a script, and Octave's `source()` parses the whole file (raising a
syntax error for a malformed function body, including a malformed nested
helper function) without ever calling any of those local functions. This
was confirmed both for a single-function file and for a multi-function
file where one local function calls another. `tests/scripts/
test_extract_per_process_traces_v2_static.py` uses this technique for an
optional, environment-gated (skips cleanly when MATLAB/Octave is
unavailable) real parse-only probe against the actual extractor file, in
addition to (not instead of) the lightweight block-keyword-balance
heuristic. No extraction/simulation/bootstrap is authorized or performed
by that test.

## Non-goals

* This document does not authorize or perform any MATLAB/Octave execution.
* This document does not change the two real event MATs on disk today, nor
  claim they will be regenerated as part of this task.
* This document does not relax `window_loader.py`'s default
  `require_stride_contract=True` behavior for any non-smoke code path.
* This document does not authorize deleting an existing on-disk trace to
  force regeneration. `scripts/l2_event/launcher.py` never deletes a
  `regenerate_invalid` file pre-emptively: a future regeneration job
  writes to a unique, existence-checked `.tmp-regen-<token>` output
  directory, and only `finalize_atomic_regeneration` may replace the real
  file -- and only after rebinding to the exact spec + token + pre-run
  manifest hash and independently revalidating the fresh output via the
  same `validate_existing_event_window` gauntlet. The prior file's
  SHA-256 is recorded in the plan/manifest before any such replacement so
  its identity is never lost even though it is never deleted up front.


