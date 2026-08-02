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
| `tick_start` | int | The absolute (1-based simulation-tick) coordinate at which the window begins. All tick-valued metadata (`tick_start`, `tick_end`, `window_anchor`, `onset_tick`) share this **single absolute coordinate system**; local grid row `i` (0-based) maps to `tick_start + i` (see `WindowGrid.absolute_tick`). |
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

## Current state of the two real event MATs on disk

Neither of the two real event-window traces that exist today --

* `data/m1_sources/karr_native/per_process_traces_v2_event_s000/RibosomeAssembly_100ticks.mat`
* `data/m1_sources/karr_native/per_process_traces_v2_event_s000/RNAModification_100ticks.mat`

-- carries `stride`, `tick_start`, `tick_end`, or `window_anchor` in their
`metadata` group. Both were produced by an extractor generation that
predates this contract. This is why:

* `run_structural_smoke()` must call `load_and_check_window(...,
  require_stride_contract=False)` and treat the resulting
  `stride_contract_ok=False` as a non-fatal, explicitly-surfaced
  incompleteness (see the `stride_contract_ok`/`stride_contract_problems`
  fields on `run_structural_smoke()`'s result and the corresponding
  `reasons` entry in the written evidence) -- **never** a silent pass.
* The RibosomeAssembly seed-0 smoke's verdict is `NOT_APPLICABLE`, not
  `PASS`, for this reason among others (it is a structural loader/adapter
  round-trip smoke, not a calibrated gate verdict, regardless of the
  stride contract).
* Any future attempt to run a *real* (non-smoke) gate computation against
  either of these two files with the default `require_stride_contract=True`
  will raise `EventWindowRefused("INCOMPLETE_WINDOW", ...)` -- this is
  intentional and must not be worked around by loosening the loader; the
  extractor must be fixed instead.

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
`[tick_offset, tick_offset + n_ticks - 1]`; that grid's completeness is the
only thing validated for it.

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
* completion is observed more than once in a way that is ambiguous
  (duplicate/re-fire without a clean single capture);
* (`diameter_decrease` only) onset is never observed, or
  `onset_tick < tick_start`, or `onset_tick >= window_anchor` (onset must
  fall strictly inside the captured window and strictly before completion).

There is deliberately no code path that produces a file with some but not
all of these invariants satisfied; a timing-incomplete file must never be
silently written or silently accepted as valid downstream.

## Non-goals

* This document does not authorize or perform any MATLAB/Octave execution.
* This document does not change the two real event MATs on disk today, nor
  claim they will be regenerated as part of this task.
* This document does not relax `window_loader.py`'s default
  `require_stride_contract=True` behavior for any non-smoke code path.
* This document does not authorize deleting an existing on-disk trace to
  force regeneration. `scripts/l2_event/launcher.py` never deletes a
  `regenerate_invalid` file pre-emptively: a future regeneration job
  writes to a sibling `.tmp-regen` output directory, and only
  `finalize_atomic_regeneration` may replace the real file -- and only
  after independently revalidating the fresh output via the same
  `validate_existing_event_window` gauntlet. The prior file's SHA-256 is
  recorded in the plan/manifest before any such replacement so its
  identity is never lost even though it is never deleted up front.

