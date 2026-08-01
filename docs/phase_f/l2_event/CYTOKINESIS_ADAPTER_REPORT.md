# Cytokinesis L2.event Adapter -- Process Report

**Process**: Cytokinesis | **Adapter ID**: `cytokinesis.division_complete.v1`
**Branch**: `agent/l2-event-cytokinesis` @ base `d92f8ad`
**Scope**: adapter + adapter tests + this report + a proposed (non-central)
registry row fragment. No MATLAB extraction, no
`opencell/vivarium/karr_cytokinesis.py` edits, no
`docs/phase_f/l2_event/event_registry.yaml` / `evidence_index.json` edits,
no push.

## 1. What was built

| File | Purpose |
|---|---|
| `scripts/l2_event/adapters/cytokinesis.py` | `CytokinesisEventAdapter` (D7 `EventAdapter` Protocol implementation): rising-edge `karr_observation`/`oc_observation`, `division_relative_offset`/`single_fire_offset` (D2 addendum anchor), `require_cytokinesis_state_inputs`/`MissingCytokinesisStateInput` (Rule 1 fail-loud). |
| `tests/scripts/test_l2_event_adapters_cytokinesis.py` | 21 tests: unit (rising-edge, required-input enforcement, anchor formula), one real-code-path integration test against `KarrCytokinesisProcess`, and 6 `evaluate_gate` scenario tests over synthetic 50-seed cohorts. |
| `docs/phase_f/l2_event/PROPOSED_REGISTRY_ROW_cytokinesis.yaml` | Non-authoritative proposal for what a future registry flip would look like (`adapter_id`/`adapter_status` only); explicitly proposes `structural_smoke_only`, not `gating_ready`, pending a real extractor. |
| This report | Rule-by-rule verification, discrepancies discovered, exact extraction/anchor requirements. |

## 2. FIX_TEMPLATE_L2_REPLAY rule application (Rules 1, 4, 6, 7, 8)

- **Rule 1 (complete observable coverage, no silent skip).** The case
  directive names 4 required state inputs, which are 5 dotted paths
  (`cell.ftsz_ring_complete`, `cell.division_progress`,
  `cell.division_complete`, `chromosome.segregation_progress`,
  `substrates_allocated.karr_cytokinesis.GTP`). `require_cytokinesis_state_inputs`
  walks all 5 and raises `MissingCytokinesisStateInput` naming the exact
  missing path -- never a `.get(..., default)`. Verified individually via
  `test_oc_observation_fails_loud_when_required_input_missing`, parametrized
  over all 5 paths (5/5 pass).
- **Rule 4/4b (per-tick state isolation, no carryover).** Both
  `karr_observation` and `oc_observation` compute `fired` strictly from
  `(before, after)` of the SAME tick, never comparing across ticks or
  caching state between calls (the adapter is a frozen dataclass with no
  mutable fields). Verified by
  `test_karr_observation_fires_once_on_rising_edge_not_on_persistent_true`
  and `test_oc_observation_does_not_refire_once_already_complete`: a
  persistent post-completion `True` produces exactly one fire, not one per
  remaining tick.
- **Rule 6 (adversarial / non-triviality probe -- no vacuous PASS on a
  quiescent trace).** `test_quiet_standard_trace_refuses_before_any_adapter_call`
  constructs a synthetic HDF5 trace shaped like a real standard mid-cycle
  trace (has `n_ticks`/`process_name`/`rng_seed` but no `tick_offset`) and
  proves `window_loader.load_event_window` raises
  `EventWindowRefused(reason="NOT_EVENT_WINDOW_TRACE")` -- structurally,
  before `CytokinesisEventAdapter` or `evaluate_gate` ever runs. There is
  no code path from this fixture to a computed verdict of any kind.
- **Rule 7 (real code path, pass-through provenance).**
  `test_real_karr_cytokinesis_process_single_fire_detected_on_genuine_completion_tick`
  drives the actual `KarrCytokinesisProcess.next_update()` (rates=1.0,
  `calc_required_pinching_cycles` ticks) to its own genuine completion
  tick and confirms `oc_observation` agrees with the process's own ground
  truth (`fired_ticks == [cycles - 1]`) -- the test never sets
  `division_complete=True` itself; it only reads what `next_update`
  actually returned.
- **Rule 8 (no trace-cribbing in production code).**
  `scripts/l2_event/adapters/cytokinesis.py` contains no trace file paths,
  no hardcoded seed numbers, and no special-cased tick values -- every
  number it uses comes from its `window`/`state_before`/`update`
  parameters. Every test fixture in the test file is either synthetic
  in-memory data or a real process driven from a from-scratch state dict
  (never a copy of expected output pasted in as ground truth).

## 3. The three named inversions -- how each is guarded

1. **Quiet standard trace -> fake event PASS.** Guarded structurally by
   `window_loader`'s `NOT_EVENT_WINDOW_TRACE` refusal (see Rule 6 above) --
   verified directly, not merely assumed. **Terminology note**: the case
   directive's phrase "quiet standard trace NOT_APPLICABLE" describes the
   *intended outcome shape* ("never a gating verdict"); the runner's own
   vocabulary for this precondition failure is the `RefusalReason`
   `NOT_EVENT_WINDOW_TRACE` (surfaced as `EventWindowRefused`), not the
   schema's literal `ProcessVerdict` value `"NOT_APPLICABLE"` (reserved for
   structural-smoke runs per `schema.py`'s own docstring). The test asserts
   the real refusal reason and documents this distinction rather than
   asserting a `ProcessVerdict` value the codebase would never actually
   produce for this case.
2. **Division timing uses wrong anchor.**
   `test_evaluate_gate_wrong_anchor_on_oc_side_fails_timing_channel`
   constructs an otherwise-identical 47/50-aligned cohort but computes the
   OC-side offsets against the wrong anchor (`0.0` instead of the correct
   `10.0`), shifting every OC offset by +10. Empirically verified
   (`rng=default_rng(0)`): `count` stays `SEED_NOISE` (unaffected -- it
   only counts presence) but `timing` -> `FAIL` (`w1=10.0` vs
   `threshold=2.43`), and the process verdict is `FAIL`, not a silent PASS
   riding on the count channel alone.
3. **Redundant payload accidentally made gating.**
   `test_evaluate_gate_payload_channel_is_always_not_gateable_redundant_never_gating`
   asserts, for a `magnitude_gateable=False` registry entry (matching the
   authoritative catalog row), that `evaluate_gate`'s payload channel is
   always `NOT_GATEABLE_REDUNDANT` with `statistic_value=None` --
   confirmed this can never itself flip a verdict, since
   `evaluate_gate`'s own `gating_channels` list explicitly excludes any
   channel with that verdict (`runner.py`: `gating_channels = [c for c in
   channels if c.verdict not in ("NOT_GATEABLE_REDUNDANT",)]`).

## 4. Empirically-verified design decisions

- **"50-seed cohorts pass at 50 aligned events" -> tested as 47/50, not
  literally 50/50.** Empirically verified against the real
  `scripts.l2_event.metrics`/`runner` code (a throwaway probe script, run
  and deleted before committing) that a literal 50/50-fired,
  perfectly-aligned single-firing cohort makes the count channel's
  Karr-only cluster bootstrap collapse (`q95_null=0.0` ->
  `DEGENERATE_NULL`, a REFUSAL) because every seed's count is the
  identical constant `1.0`. This is the same reason the framework's own
  precedent test
  (`test_l2_event_metrics.py::test_count_gate_single_firing_boundary_44_refuses_45_proceeds`)
  uses 45/50, not 50/50. 47/50 (3 empty seeds, still well above the
  >=45/50 floor) with per-seed tick variance (`10 + seed % 7`) produces
  genuine variance and both channels land on `SEED_NOISE` -> process
  `PASS`. "Aligned" is satisfied in the sense the directive intends: for
  every firing seed, Karr and OC fire on the exact same tick.
- **44/50 Karr-fired -> REFUSED, exactly as directed.** Both `count`
  (`count_support_floor("single_firing", 50) == ceil(0.9*50) == 45`) and
  `timing` (`44/50 == 0.88 < 0.9`) independently return
  `INSUFFICIENT_KARR_SUPPORT`; the process verdict is `REFUSED`.

## 5. Verified discrepancies against stale baseline docs (primary-source discipline)

Checked directly against the current `opencell/vivarium/karr_cytokinesis.py`
HEAD, not the older narrative in `L2_EVENT_GATE_SPEC_v4.md` §4 fact 1 or
`docs/design/pc-t9-cytokinesis.md`:

| Case-directive-required input | Declared in `ports_schema()`? | Actually read in `next_update()`? |
|---|---|---|
| `cell.ftsz_ring_complete` | Yes (`_updater: "set"`) | **No** -- never read or assigned; vestigial from an earlier port revision superseded by the current explicit FtsZ-ring/geometry state machine. |
| `cell.division_progress` / `cell.division_complete` | Yes | Yes -- read via `_current_division_progress`, written every tick. |
| `chromosome.segregation_progress` | Yes | Yes -- read via `_segregated()`. |
| `substrates_allocated.karr_cytokinesis.GTP` | Yes (declared in `requests`/`substrates_allocated`) | **No** -- `next_update()` hardcodes the GTP *request* to `0.0` and never reads the allocated `GTP` value back; the port's actual hydrolysis-limiting allocation channel today is `WATER` (`substrates_allocated.karr_cytokinesis.<water_wid>`), confirmed also by `docs/phase_f/STATUS_cytokinesis_precondition.md`. |

**Design decision (documented, not silently "fixed"):** the adapter still
enforces presence of all 5 paths, including the 2 the process doesn't
currently read back, because both are live, declared `ports_schema()` keys
and a harness that silently omits a declared port is exactly the
"default quiet" failure mode Rule 1 exists to refuse. If a future task
removes these vestigial ports from `karr_cytokinesis.py`, this adapter's
required-input list must be updated in the same change (not left silently
stale) -- see `scripts/l2_event/adapters/cytokinesis.py`'s module
docstring for the same citation.

## 6. Exact extraction/anchor requirements for a future MATLAB extractor

No MATLAB extraction was performed in this task. For a future extractor to
make this adapter's `adapter_status` promotable beyond
`structural_smoke_only`:

1. **Karr-side channel name**: `division_complete` (this adapter's
   `KARR_EVENT_CHANNEL` constant), sampled as a 0/1 (or bool-castable)
   scalar in both `states_before` and `states_after` groups, every tick,
   stride-1, over the process's declared event window -- matching the
   existing `WindowGrid`/`load_event_window` contract used by
   RibosomeAssembly's real trace today (`per_process_traces_v2_event_s{seed:03d}/Cytokinesis_100ticks.mat`).
2. **`metadata/tick_offset`** must be present and equal to the window's
   division/reference anchor tick, in the SAME tick-index coordinate
   system as the `states_before`/`states_after` arrays (0-based, local to
   the window) -- this is the single value `division_relative_offset`
   subtracts from the local fire tick to compute `t_fire - t_division`
   (D2 addendum). **This convention is defined by this adapter, not
   ratified by any extractor** -- spec QO1 remains open. Any extractor
   landing later must either match this exactly or this adapter's
   `division_relative_offset`/`single_fire_offset` must be updated in the
   same change.
3. **M4 stride/window-boundary metadata** (`stride=1`, `tick_start`, and
   at least one of `tick_end`/`window_anchor`) -- the same contract
   `window_loader.py` already enforces for every event-window trace
   (`EVENT_WINDOW_EXTRACTOR_CONTRACT.md`); Cytokinesis gets no special
   exemption from this.
4. **At least 45 of the required 50 seeds must Karr-fire** (catalog
   support floor, C2) for a real `evaluate_gate("gate", ...)` run to reach
   anything other than `REFUSED`.
5. **Rising-edge semantics on the Karr side**: since `division_complete`
   (or whatever native Karr field feeds this channel) is very likely a
   persistent post-completion `True` in the source simulation too (the OC
   port's own field is modeled directly on it), the extractor's
   `states_before`/`states_after` pair for a given tick must reflect the
   ACTUAL before/after transition at that tick -- not two independent
   samples of a state that may have already flipped earlier, which would
   make the rising-edge detector under- or over-fire.

## 7. Test results

```
tests/scripts/test_l2_event_adapters_cytokinesis.py: 21 passed
tests/scripts/test_l2_event_adapters.py:               10 passed, 3 skipped
tests/scripts/test_l2_event_runner.py:                 (included in combined run below)
tests/scripts/test_l2_event_metrics.py:                (included in combined run below)
tests/scripts/test_l2_event_window_loader.py:          (included in combined run below)
tests/vivarium/test_karr_cytokinesis.py:               (included in combined run below)

Combined regression run (all of the above):
115 passed, 6 skipped in 33.37s
```

6 skips are all pre-existing, real-data-dependent tests unrelated to this
change (real RA/standard MAT files not required to be present locally);
none are new skips introduced by this task.

## 8. What this task does NOT claim

- No MATLAB extraction was performed; no real Cytokinesis event-window
  trace exists on disk (0/50 seeds, unchanged from before this task).
- The central `docs/phase_f/l2_event/event_registry.yaml` was NOT edited;
  Cytokinesis remains `adapter_status: not_implemented` / `adapter_id:
  null` there. `PROPOSED_REGISTRY_ROW_cytokinesis.yaml` is a proposal
  only, itself proposing `structural_smoke_only` (not `gating_ready`).
- `opencell/vivarium/karr_cytokinesis.py` was not modified; the verified
  `ftsz_ring_complete`/GTP discrepancies are documented, not "fixed"
  (fixing them is out of this task's scope and would be a production-code
  change).
