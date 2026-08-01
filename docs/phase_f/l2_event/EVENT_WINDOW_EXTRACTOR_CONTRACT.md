# L2.event Window Extractor Contract (M4, documentation-only)

Status: **contract implemented in code, not yet run.**
`scripts/matlab/extract_per_process_traces_v2.m` now accepts an optional
`window_contract` ('fixed' | 'anchor') + `anchor_opts` argument pair that
writes exactly the metadata keys this document specifies, and
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
| `tick_start` | int | The absolute tick (or tick-offset-relative tick, see below) at which the window begins. |
| `tick_end` **or** `window_anchor` | int / float | The window's other boundary. A **fixed-length** window (e.g. "100 ticks starting at tick_start") records `tick_end`. A **division-anchored** window (e.g. "100 ticks ending at the division event, wherever that falls per-seed") may instead record `window_anchor` -- the tick offset of the anchor event -- since `tick_end` is seed-dependent in that case. At least one of the two is required ("as applicable" per the governing requirement); a trace with neither is refused. |

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
metadata/tick_start    -- int, absolute or tick_offset-relative window start
metadata/tick_end      -- int, present for fixed-length windows
   -- or --
metadata/window_anchor -- int/float, present for division-anchored windows
                           (at least one of tick_end/window_anchor required)
```

No other change to the extractor's output format, per-tick payload
encoding, or directory layout (`per_process_traces_v2_event_s{seed:03d}/`)
is implied by this contract. `stride`/`tick_start`/`tick_end` are derived
mechanically from the caller-supplied `tick_offset` burn-in for
`window_contract='fixed'`; `tick_start`/`window_anchor` for
`window_contract='anchor'` are discovered from a real, observed simulation
completion signal (`capture_anchor_window()` in
`extract_per_process_traces_v2.m`; default signal is
`CellGeometry.pinched`/`pinchedDiameter == 0`, Cytokinesis's own real
division-complete state) -- never fabricated, never derived from an
expected/desired outcome. See `scripts/l2_event/launcher.py` for the
corresponding MATLAB-free planning/command-builder surface (specs, CLI,
validate-before-skip). Neither piece of code has been run against a real
simulation as part of writing this contract update.

## Non-goals

* This document does not authorize or perform any MATLAB/Octave execution.
* This document does not change the two real event MATs on disk today, nor
  claim they will be regenerated as part of this task.
* This document does not relax `window_loader.py`'s default
  `require_stride_contract=True` behavior for any non-smoke code path.
