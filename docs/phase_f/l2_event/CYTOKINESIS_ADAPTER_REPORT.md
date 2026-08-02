# Cytokinesis L2.event Adapter -- Process Report (Round 2)

**Process**: Cytokinesis | **Adapter ID**: `cytokinesis.pinched_diameter_completion.v1`
**Branch**: `agent/l2-event-cytokinesis` @ base `d92f8ad` (round 2 built on
round-1 HEAD `1f5b382`, itself rejected/corrected by the operator)
**Scope**: adapter + adapter tests + this report + a proposed (non-central)
registry row fragment. No MATLAB extraction, no
`opencell/vivarium/karr_cytokinesis.py` edits, no
`scripts/l2_event/window_loader.py` / `runner.py` / `metrics.py` /
`base.py` / `docs/phase_f/l2_event/event_registry.yaml` /
`evidence_index.json` edits, no push.

## 0. Why round 2 exists -- what was rejected and why

Round 1 (`1f5b382`) was rejected by the operator on two independent
grounds, both confirmed against the primary Karr source
(`Cytokinesis.m`, `FtsZRing.m`, `CellGeometry.m`) and the current
`opencell/vivarium/karr_cytokinesis.py` HEAD during Turn-1 read-only
investigation:

1. **Wrong timing anchor.** Round 1's `division_relative_offset(tick,
   tick_offset)` used `WindowGrid.tick_offset` as if it were a
   contraction-onset anchor. It is not: `tick_offset` is
   burn-in/window-placement metadata (see `window_loader.py`'s own
   docstring). The ratified operator timing decision (2026-08-02) is
   that the process-local interval must be gated from **contraction
   onset** (first strict `pinchedDiameter` decrease) to
   **geometry-pinch completion** (`pinchedDiameter` positive -> zero),
   derived purely from the diameter sequence itself.
2. **Wrong/stale required-input manifest.** Round 1 required
   `cell.ftsz_ring_complete` (declared in `ports_schema()` but never
   read by `next_update()` -- vestigial) and
   `substrates_allocated.karr_cytokinesis.GTP` (the GTP *request* is
   hardcoded to `0.0`; the allocated value is never read back). Round 1
   also detected completion from `cell.division_complete`, an
   extractor-invented Karr channel name that does not exist anywhere in
   `Cytokinesis.m`/`FtsZRing.m`/`CellGeometry.m`.

Round 2 replaces both: timing is derived purely and statelessly from a
complete `pinchedDiameter` sequence (never from `tick_offset` or any
`window_anchor` metadata scalar), and the required-input manifest is
re-audited line-by-line against `next_update()`'s actual read surface,
including the dynamic `enzymes`/`boundEnzymes` state and the WATER (not
GTP) allocation channel.

## 1. What was built

| File | Purpose |
|---|---|
| `scripts/l2_event/adapters/cytokinesis.py` | `CytokinesisEventAdapter` (D7 `EventAdapter` Protocol implementation): stateless per-tick `karr_observation`/`oc_observation` projecting the real `pinchedDiameter` before/after channel; adapter-local, metadata-free sequence-scanning helpers (`find_onset_tick`, `find_completion_tick`, `single_fire_offset_from_sequences`, `karr_single_fire_offset`, `oc_single_fire_offset`) that derive `t_completion - t_onset` purely from a complete per-seed sequence; `require_cytokinesis_state_inputs`/`require_cytokinesis_dynamic_state_inputs` (Rule 1 fail-loud, re-audited manifest incl. dynamic enzyme/WATER validation). |
| `tests/scripts/test_l2_event_adapters_cytokinesis.py` | 45 test functions / 58 collected test cases (parametrized cases included): per-tick observation unit tests, sequence-primitive tests (onset/completion scan, non-finite/negative/mismatched/non-scalar/empty-sequence refusals, duplicate-completion refusal), offset-derivation tests (multi-tick, instantaneous, metadata-independence, two monkeypatch-based defensive-guard tests), dynamic-input validation tests against the real `KarrCytokinesisProcess`, an AST-based regression test proving no `.tick_offset`/`.window_anchor` attribute access exists anywhere in the adapter module, one real-code-path integration test against `KarrCytokinesisProcess`, and 6 `evaluate_gate` scenario tests over synthetic 50-seed cohorts. |
| `docs/phase_f/l2_event/PROPOSED_REGISTRY_ROW_cytokinesis.yaml` | Non-authoritative proposal for what a future registry flip would look like (`adapter_id`/`adapter_status` only); explicitly proposes `structural_smoke_only`, not `gating_ready`, pending a real extractor AND `window_anchor` exposure/validation (see §6). |
| This report | Rule-by-rule verification, round-1-vs-round-2 discrepancies, exact extraction/anchor requirements. |

## 2. Karr and OC source anchors -- onset, completion, actual read/write state

Quoted with file:line anchors (`data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/...`,
present only in the main checkout, gitignored, not in this worktree):

- **`Cytokinesis.m:174`** -- segregation gate: `if ~this.chromosome.segregated ... return`.
  Cytokinesis does nothing at all until chromosome segregation is complete.
- **`Cytokinesis.m:220-221`** -- the pinch-decrease is only reachable when
  the ring is FULLY bent: `numEdgesTwoBent + numEdgesTwoStraight ==
  numEdges && numEdgesTwoStraight > 0 && numResidualBent == 0`.
- **`Cytokinesis.m:238-239`** -- the actual `pinchedDiameter` write, additionally
  gated on `numEdgesTwoStraight == 0 && ~pinched` (i.e. the ring has just
  finished bending AND the cell is not already pinched).
- **`Cytokinesis.m:264-282`** (`calcNextPinchedDiameter`) -- computes the next
  diameter and clamps the RESULT to exactly `0` once
  `result <= filamentLengthInNm*1e-9` -- this is Karr's own completion rule,
  mechanically reproduced by this adapter's `before>0, after==0` predicate.
- **`CellGeometry.m:193-194`** -- `pinched` is a DERIVED getter
  (`pinchedDiameter == 0`), never an independently-set flag.
- **`FtsZRing.m:113-120,125-126`** -- `numEdges` getter returns `0` once
  `pinchedDiameter==0`; `calcNumEdges` formula matches OC's own
  `_ring_state()` port.
- **`CellGeometry.m:100`** -- `pinchedDiameter`'s doc comment: "m; diameter
  where cell is pinched the most" -- the one field this adapter now
  projects on the Karr side (`KARR_EVENT_CHANNEL = "pinchedDiameter"`),
  replacing round-1's invented `division_complete` label.

OC (`opencell/vivarium/karr_cytokinesis.py`) actual read/write surface,
re-verified against HEAD for this round:

- `ports_schema()` (~line 215) declares `cell.ftsz_ring_complete`
  (`_updater: "set"`), but `next_update()` (~line 330) never reads or
  assigns it -- confirmed vestigial, dropped from the required-input
  manifest.
- `cell.division_complete` is written unconditionally every tick as
  `bool(geometry["pinched"])`, but `next_update()` never reads it back --
  an output, not a conditioning input, and not this adapter's completion
  signal (see §3).
- The GTP request is hardcoded to `0.0` in the returned update; the
  allocated GTP value is never read back. Only
  `substrates_allocated["karr_cytokinesis"][water_wid]` (via
  `_allocated_count`) gates hydrolysis -- WATER, not GTP, is required.
- `_ring_state()` recomputes `numEdges` itself (never reads an input
  `numEdges`) -- correctly excluded from the required-input manifest.
- `enzymes`/`boundEnzymes` (dynamic dicts keyed by fixture-derived FtsZ
  enzyme WIDs) and `water_wid` (itself fixture-derived) are read by
  `next_update()` via `_counts_from_state`/`_allocated_count` -- present in
  round 1's manifest as neither static paths nor validated at all; round 2
  adds `REQUIRED_OC_STATE_GROUPS` + `require_cytokinesis_dynamic_state_inputs`
  to cover them without hardcoding fixture-specific WIDs.
- `chromosome.segregated` is an explicit, process-sanctioned
  fallback-override of `chromosome.segregation_progress` -- kept
  `segregation_progress` as the single required static path (not a
  silently-defaulted dead port like `ftsz_ring_complete`).

## 3. Exact predicates

**Onset anchor** (`find_onset_tick`): scan a COMPLETE per-seed
`pinchedDiameter` before/after sequence; return the local tick index of
the FIRST tick where `after[t] < before[t]` (strict decrease). Returns
`None` (not an error) if no such tick exists anywhere -- "no onset in
this window" is a valid non-firing outcome on its own. If a ring becomes
fully bent and pinches to zero within the same tick ("instantaneous"/
within-tick ring-ready consumption), that tick's own `before>0 -> after
== 0` transition is itself the first strict decrease, so onset ==
completion and the offset is exactly `0`.

**Completion fire** (`find_completion_tick` / `karr_observation` /
`oc_observation`): the tick where `before > 0` AND `after == 0`,
mechanically derived from the diameter itself (Karr's own
`calcNextPinchedDiameter` clamp-to-zero rule, §2) -- never from
`cell.division_complete` or any other extractor-invented label. At most
one such tick may exist per seed (`magnitude_gateable: false`); more than
one raises `DuplicateCompletionTickDetected`.

**Refusal when onset/completion ordering or support is absent**
(`single_fire_offset_from_sequences`, the sole
`completion_tick - onset_tick` arithmetic site in this module):

| Condition | Exception raised |
|---|---|
| No completion tick in the sequence (includes "never decreases") | `NoCompletionTickDetected` |
| More than one completion tick | `DuplicateCompletionTickDetected` |
| Completion found but no strict decrease anywhere (defensive; structurally unreachable on valid data -- completion is itself always a decrease) | `CompletionWithoutPrecedingOnset` |
| Onset found strictly after completion (defensive; structurally unreachable on valid data) | `OnsetAfterCompletionTick` |
| Any reading non-finite, negative, non-scalar, or before/after length-mismatched | `InvalidPinchedDiameterSequence` |

None of these is ever encoded as a fake `EventObservation` or a silent
no-fire -- every one is a raised exception, matching FIX_TEMPLATE_L2_REPLAY
Rule 1 fail-loud philosophy. `karr_observation`/`oc_observation`
themselves remain pure per-tick projections (no sequence scan, no
carryover) and simply return `fired=False` for a given tick's own
before/after pair if that tick's predicate doesn't hold -- they never
raise a timing error, only the sequence-level offset helpers do.

## 4. Timing: `window_anchor` vs `tick_offset` -- what this adapter consumes

This adapter's timing arithmetic reads **only** the `pinchedDiameter`
values themselves (`window.before(...)`/`window.after(...)` for Karr;
`state_before`/`update` row pairs for OC). It never reads
`WindowGrid.tick_offset` anywhere (verified structurally, not just by
convention -- see `test_tick_offset_and_window_anchor_absent_from_adapter_attribute_access`,
an AST-based check that parses the module and asserts no
`.tick_offset`/`.window_anchor` attribute access exists at all). Current
`WindowGrid`/runner APIs are sufficient for this: `WindowGrid.before`/
`.after`/`.n_ticks` already expose everything `karr_pinched_diameter_sequence`
needs, and no shared-file change is required for this adapter's own
onset/completion derivation.

**What remains genuinely blocked** (per operator correction #4, not
resolved by this branch): future GATE-mode wiring -- i.e. actually
promoting `adapter_status` beyond `structural_smoke_only` -- requires the
extractor to expose a `window_anchor` value on real Cytokinesis traces
AND for that value to be validated (by whatever component owns real gate
promotion, not this adapter) to equal this adapter's own
data-derived onset tick, in the SAME tick-index coordinate system. Today
`window_anchor` is checked only for *existence* inside
`window_loader.py`'s `_check_stride_contract` (M4 stride-contract
metadata) and is discarded -- never surfaced on the returned `WindowGrid`
object at all. This is a dependency on the shared extractor/window
surfaces, explicitly out of scope for this branch (see §7), and is
**not** implemented, worked around, or bypassed here.

## 5. Required-input manifest (re-audited)

`REQUIRED_OC_STATE_PATHS` (11 static dotted paths, `require_cytokinesis_state_inputs`):
`cell.division_progress`, `chromosome.segregation_progress`,
`geometry.width`, `geometry.pinchedDiameter`, `geometry.pinched`,
`ftsZRing.numEdgesOneStraight`, `ftsZRing.numEdgesTwoStraight`,
`ftsZRing.numEdgesTwoBent`, `ftsZRing.numResidualBent`,
`ftsZRing.numFtsZSubunitsPerFilament`, `ftsZRing.filamentLengthInNm`.

`REQUIRED_OC_STATE_GROUPS` (group-presence only, exact WID membership
validated separately): `enzymes`, `boundEnzymes`,
`substrates_allocated.karr_cytokinesis`.

`require_cytokinesis_dynamic_state_inputs(state_before, process)`
(new in round 2): validates, against a real `KarrCytokinesisProcess`
instance's `.water_wid` and `.fixture_enzyme_wids` (both fixture/runtime-
derived, never hardcoded literals), that
`substrates_allocated.karr_cytokinesis.<water_wid>` is present (the
process's actual hydrolysis-limiting allocation channel -- a GTP
allocation alone does NOT satisfy this, since the allocated GTP value is
never read back), and that every fixture enzyme WID is present in BOTH
`enzymes` and `boundEnzymes` (both dicts `next_update()` reads via
`_counts_from_state`).

**Explicitly dropped from round 1**: `cell.ftsz_ring_complete` (declared,
never read -- vestigial) and any GTP path (declared for legacy plumbing,
request hardcoded to `0.0`, allocated value never read back).
`cell.division_complete` is also not required as an input -- it is
written by `next_update`, never read by it, and is no longer this
adapter's completion signal (see §3).

## 6. Files modified in this branch (round 2)

- `scripts/l2_event/adapters/cytokinesis.py` (full rewrite)
- `tests/scripts/test_l2_event_adapters_cytokinesis.py` (full rewrite)
- `docs/phase_f/l2_event/CYTOKINESIS_ADAPTER_REPORT.md` (this file)
- `docs/phase_f/l2_event/PROPOSED_REGISTRY_ROW_cytokinesis.yaml`

**Explicitly NOT touched** (per operator instruction; shared/concurrent
INTENT review surfaces): `scripts/l2_event/window_loader.py`,
`scripts/l2_event/runner.py`, `scripts/l2_event/metrics.py`,
`scripts/l2_event/adapters/base.py`,
`docs/phase_f/l2_event/event_registry.yaml`, any shared schema/registry/
index file, `opencell/vivarium/karr_cytokinesis.py`. No MATLAB extraction
was performed; no real Cytokinesis event-window trace exists on disk
(0/50 seeds, unchanged from before this task).

## 7. Test results

```
tests/scripts/test_l2_event_adapters_cytokinesis.py: 58 passed (45 test functions, incl. parametrized cases)

Combined regression run (pre-existing adjacent L2.event + OC process suites,
zero adapter-branch changes to any of these files):
tests/scripts/test_l2_event_adapters.py
tests/scripts/test_l2_event_runner.py
tests/scripts/test_l2_event_metrics.py
tests/scripts/test_l2_event_window_loader.py
tests/vivarium/test_karr_cytokinesis.py
  -> 115 passed, 6 skipped in 29.24s
```

The 6 skips are all pre-existing, real-data-dependent tests unrelated to
this change ("Real RibosomeAssembly seed-000 event-window MAT not present
locally" -- `test_l2_event_adapters.py`, `test_l2_event_runner.py`,
`test_l2_event_window_loader.py`); none are new skips introduced by this
task, and none are Cytokinesis-related (Cytokinesis has 0 real traces
either way -- see §8).

Predicted-vs-actual test outcomes (per operator correction #6):

| Predicted outcome | Test(s) | Result |
|---|---|---|
| One completion fire | `test_karr_observation_fires_once_on_rising_edge_not_on_persistent_true`, `test_oc_observation_fires_once_on_rising_edge` | pass |
| Persistent completion, no refire | `test_karr_observation_fires_once_on_rising_edge_not_on_persistent_true`, `test_oc_observation_does_not_refire_once_already_complete` | pass |
| Wrong/missing anchor refuses or fails | `test_find_onset_tick_returns_none_when_no_decrease_ever_occurs`, `test_single_fire_offset_refuses_when_no_decrease_ever_occurs`, `test_evaluate_gate_wrong_onset_on_oc_side_fails_timing_channel` | pass |
| Wrong ordering refuses | `test_single_fire_offset_defensive_guard_onset_after_completion` (monkeypatch) | pass |
| Spurious OC completion fails | `test_evaluate_gate_double_oc_fire_outside_window_fails_via_spurious_c6`, `test_find_completion_tick_raises_on_duplicate_completion`, `test_single_fire_offset_refuses_on_duplicate_completion` | pass |
| Missing real state fails loudly | `test_oc_observation_fails_loud_when_required_input_missing` (parametrized over every required path), dynamic-input tests (§ below) | pass |
| Payload remains non-gating | `test_evaluate_gate_payload_channel_is_always_not_gateable_redundant_never_gating` | pass |
| No real-data PASS | not claimed anywhere in this report or the registry proposal (§8) | n/a (by design) |
| Zero extraction/trace changes | no `.mat`/extraction code touched; `git diff` scope limited to the 4 files in §6 | pass |

Inversion tests (per operator correction #6/#7, "prove `tick_offset`
changes cannot alter the offset" and vestigial-input guards):

- `test_karr_single_fire_offset_is_independent_of_tick_offset` -- constructs
  two otherwise-identical windows differing only in `tick_offset` and
  asserts `karr_single_fire_offset` returns the identical value for both.
- `test_required_oc_state_paths_excludes_vestigial_and_gtp_inputs` --
  asserts `cell.ftsz_ring_complete` and any GTP dotted path are absent
  from `REQUIRED_OC_STATE_PATHS`.
- `test_require_cytokinesis_dynamic_state_inputs_gtp_alone_is_not_sufficient` --
  a state with an allocated GTP value but no allocated WATER value still
  raises `MissingCytokinesisStateInput` (WATER-vs-GTP).
- `test_karr_single_fire_offset_instantaneous_ring_ready_consumed_within_one_tick`,
  `test_oc_single_fire_offset_instantaneous_ring_ready_consumed_within_one_tick` --
  within-tick ring-ready consumption (onset == completion tick) still
  yields offset `0`, not a missing-onset refusal.
- `test_single_fire_offset_defensive_guard_completion_without_onset`,
  `test_single_fire_offset_defensive_guard_onset_after_completion` --
  monkeypatch-based (these orderings are structurally unreachable via
  `find_onset_tick`/`find_completion_tick` on valid data; see §3) proofs
  that the defensive guards fire correctly if a future regression ever
  decouples the two searches.
- `test_require_cytokinesis_dynamic_state_inputs_missing_enzyme_wid_raises`,
  `test_require_cytokinesis_dynamic_state_inputs_missing_bound_enzyme_wid_raises` --
  missing dynamic enzyme/bound-enzyme state fails loudly.
- `test_tick_offset_and_window_anchor_absent_from_adapter_attribute_access` --
  AST-based (not substring-based, to avoid false-positiving on the
  module's own explanatory docstrings) proof that no `.tick_offset`/
  `.window_anchor` attribute access exists anywhere in the adapter module.

## 8. What this task does NOT claim

- No MATLAB extraction was performed; no real Cytokinesis event-window
  trace exists on disk (0/50 seeds, unchanged from before this task).
- The central `docs/phase_f/l2_event/event_registry.yaml` was NOT edited;
  Cytokinesis remains `adapter_status: not_implemented` / `adapter_id:
  null` there. `PROPOSED_REGISTRY_ROW_cytokinesis.yaml` is a proposal
  only, itself proposing `structural_smoke_only` (not `gating_ready`).
- `opencell/vivarium/karr_cytokinesis.py` was not modified.
- `scripts/l2_event/window_loader.py`, `runner.py`, `metrics.py`,
  `base.py` were not modified -- these are shared surfaces concurrently
  in INTENT review on another branch; any dependency this adapter has on
  them (§4: `window_anchor` exposure/validation) is identified as
  BLOCKED, not worked around.
- No claim of "gating-ready" or "PASS" against real data is made
  anywhere in this report or the proposed registry row -- `evaluate_gate`
  tests in this report use synthetic 50-seed cohorts only, exactly as in
  round 1, and exist to prove the adapter's mechanics (fire/no-fire,
  timing-channel sensitivity, payload non-gating) are correct against
  the runner/metrics code as it exists today, not to certify real-data
  gating readiness.
