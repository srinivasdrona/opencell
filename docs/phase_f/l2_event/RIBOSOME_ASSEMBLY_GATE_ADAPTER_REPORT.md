# RibosomeAssembly gating-ready adapter — process report

Branch: `agent/l2-event-ribosome` (worktree `E:\opencell-worktrees\l2-event-ribosome`)
Base: `d92f8ad` ("provenance: map integrated L2.event foundation")
Scope: SLOT 3 case directive — build a second, gating-capable RibosomeAssembly
adapter alongside the existing registered `ribosome_assembly.smoke.v1`
structural-smoke adapter. No MATLAB extraction, no process/production code
changes, no catalog/`event_registry.yaml`/`evidence_index.json` edits, no push.

## DAP beats (DELIBERATE_ACTION_PREFIX_v2)

1. **Read domain contract** — `L2_EVENT_GATE_SPEC_v4.md` §4/§5 (D2 repeated-
   firing timing statistic, D3 count-gate guard, D6 payload gate, D7 adapter
   contract), `EVENT_REGISTRY_SCHEMA.md`, `FIX_TEMPLATE_L2_REPLAY.md` Rules
   1/4/6/7/8.
2. **Confirm registry ground truth** — the live `event_registry.yaml`
   RibosomeAssembly row already matches the prompt's "authoritative" entry
   verbatim (`adapter_id: ribosome_assembly.smoke.v1`,
   `adapter_status: structural_smoke_only`, `event_timing_model:
   repeated_firing`, `magnitude_gateable: true`, `required_n_seeds: 50`). No
   registry edit made or needed.
3. **Reverse-engineer the existing foundation** — `schema.py`, `registry.py`,
   `metrics.py`, `runner.py`, `evidence.py`, `window_loader.py`,
   `adapters/base.py`, `adapters/fakes.py`, `adapters/ribosome_assembly_smoke.py`
   are all pre-existing and committed at `d92f8ad`; this task adds a new,
   standalone, unregistered adapter module, not a foundation rebuild.
4. **Empirically ground the expected fires** — ran `run_structural_smoke`
   directly against the real seed-0 event-window trace and confirmed
   `karr_total_fires=2`, `oc_total_fires=2`, fire ticks **[9, 17]** on both
   sides, matching the case directive's stated expectation exactly (not
   assumed from the prompt).
5. **Build + test** — new adapter module
   (`scripts/l2_event/adapters/ribosome_assembly_gate.py`) and test suite
   (`tests/scripts/test_l2_event_ribosome_assembly_gate.py`), run end to end,
   confirm no regression in the pre-existing L2.event suite.

## Environment landmine found and fixed (local only, not a deliverable)

The real seed-0 event-window trace
(`data/m1_sources/karr_native/per_process_traces_v2_event_s000/RibosomeAssembly_100ticks.mat`)
is gitignored (`.gitignore:39`,
`data/m1_sources/karr_native/per_process_traces_v2_event_s*/`). A fresh `git
worktree` does not inherit untracked files from the main checkout, so this
worktree initially had zero seeds on disk even though the registry/evidence
bundle reference it. The file was copied from the main checkout
(`E:\opencell\data\m1_sources\...`) into the identical relative path in this
worktree; its SHA-256
(`6f1ad7f8d1c96e3807e8e454bb5914820d509b72f9eb6f62ea1b934d0ef41ca8`) was
verified to match the hash already recorded in the tracked
`evidence_bundle/RibosomeAssembly/input_manifest.json`. This is **not** new
extraction — it is replicating already-derived local fixture data that the
worktree mechanism failed to inherit. No tracked file changed as a result
(the copy is itself gitignored).

An exploratory CLI run (`python -m scripts.l2_event.runner --process
RibosomeAssembly --mode smoke --seeds 0`) mutated tracked evidence files
(`evidence_bundle/RibosomeAssembly/{SUMMARY,provenance}.json`,
`evidence_index.json`) and created an untracked `artifacts/l2_event/...` run
directory. Both were reverted/deleted before any commit, per the "no
catalog/event_registry/evidence_index edits" constraint.

## What was built

- `scripts/l2_event/adapters/ribosome_assembly_gate.py` — new
  `RibosomeAssemblyGateAdapter` (`adapter_id = "ribosome_assembly.gate.v1"`,
  distinct from the registered `ribosome_assembly.smoke.v1`). Not imported or
  wired into `event_registry.yaml`, `runner.py`'s adapter dispatch, or
  `evidence.py` — it is a standalone module exercised only by its own test
  suite and by direct construction of an in-memory `EventRegistryEntry` in
  tests (the existing architecture already supports this: `EventRegistryEntry`
  is a plain frozen dataclass, so `evaluate_gate` can be exercised end-to-end
  for a not-yet-promoted adapter without touching the real YAML).
  - `karr_observation`: reads the `complexs` channel; maps positive deltas at
    fixed indices `{0: RIBOSOME_30S, 1: RIBOSOME_50S}` to WIDs (this ordering
    was confirmed live against
    `KarrRibosomeAssemblyProcess({"rng_seed": 0}).complex_wids ==
    ["RIBOSOME_30S", "RIBOSOME_50S"]`, seed-independent, so a hardcoded map is
    justified — unlike the smoke adapter's runtime-inferred mapping). The
    check is an exact **width-2 check**, not a per-index membership check:
    before any per-index mapping runs, the delta vector's positional width
    must equal exactly `len(complex_index_by_wid)` (`2` for the default
    mapping), and `UnmappedComplexIndexError` is raised on any width
    mismatch — including a **width-1** channel (one index short of the
    declared mapping) — even when the missing/extra index's delta would
    have been exactly zero on that tick. A channel with the right width but
    non-dense keys still raises `UnmappedComplexIndexError` defensively on
    the first index with no entry in `complex_index_by_wid` (coverage-gap
    detection per FIX_TEMPLATE Rule 1; a cardinality drift is a
    coverage-completeness bug regardless of whether a given tick's data
    happened to paper over it).
  - `oc_observation`: `update.get('complex', {}).get('counts', {})` per the
    contract; handles a missing `'complex'` key and an entirely empty
    `update` dict without raising.
  - `required_payload_components`: always the fixed frozenset
    `{RIBOSOME_30S, RIBOSOME_50S}` — both Karr and OC per-tick fully
    enumerated so spurious OC-only fires are detectable (FIX_TEMPLATE Rule 8:
    no trace-cribbing / adversarial non-triviality), and `fire_count` is tick
    incidence (not particle count) on both sides.
- `tests/scripts/test_l2_event_ribosome_assembly_gate.py` — **30 tests**
  (20 at first submission; the Opus5 pre-merge review round added 7 more,
  reaching 27; the first closeout sub-round — report drift and the two
  `evaluate_gate`-level refusal tests, see below — added 2, reaching 29;
  this second closeout sub-round adds the final 1), five groups:
  1. Pure adapter unit tests: WID-mapping-matches-live-process, positive-delta
     mapping, multi-particle-same-tick still counts as one tick fire, the
     width-2 channel check (including a dedicated width-1 and a width-3
     refusal case, each via `UnmappedComplexIndexError`), a genuine
     non-dense-keys unmapped-index case (`{0: RIBOSOME_30S, 5:
     RIBOSOME_50S}` against a width-2 channel — cardinality matches so the
     width check does not fire, isolating the `key is None` defensive
     branch inside the per-index loop, distinct from the width-1/width-3
     cases above which never reach that branch), empty/no-`'complex'`-key
     update handling, fixed required-components.
  2. Real seed-0 round-trip (skipped if the trace file is absent): reproduces
     fire ticks **[9, 17]** through the new adapter, and proves the runner
     still cannot reach a computed verdict on it
     (`evaluate_gate`/`load_and_check_window` refuses with
     `INCOMPLETE_WINDOW` because the file lacks the M4 stride/tick_start/
     tick_end/window_anchor metadata contract, and separately
     `check_ensemble_size` refuses with `SINGLE_SEED_ENSEMBLE_REQUIRED`); plus
     a real-seed0 tick9/tick17 WID-identity round-trip through both
     `karr_observation` and `oc_observation`, and a negative control proving
     a deliberately swapped WID map breaks that identity on the Karr side
     only.
  3. Synthetic 50-seed cohorts driven through the adapter's own
     `karr_observation`/`oc_observation` via `evaluate_gate`: PASS with
     dual-particle firings; count-divergence FAIL (deterministic, via the D3
     hard support-ratio guard, not RNG-dependent); timing-divergence FAIL
     (count-preserving +15-tick shift, isolating the divergence to timing
     only); payload-magnitude FAIL; missing-OC-component FAIL
     (`NO_OC_COMPONENT`); spurious-extra-OC-component FAIL (keyspace-mismatch,
     since `required_payload_components` is never `None` for this adapter);
     spurious-OC-only-firing FAIL (between-Karr-event OC fires, per case
     directive requirement); plus one supplementary direct
     `metrics.payload_gate` call with `required_components=None` to exercise
     the finer-grained `NO_OC_COMPONENT`/`SPURIOUS_OC_COMPONENT` per-component
     verdicts explicitly (the fixed-adapter path never reaches those because
     its keyspace check fires first).
  4. Registry-refusal tests: `check_adapter`/`evaluate_gate` both refuse this
     candidate adapter against the LIVE, on-disk `event_registry.yaml`
     RibosomeAssembly row (still `ribosome_assembly.smoke.v1`) with
     `ADAPTER_NOT_REGISTERED`, and `check_adapter` refuses an adapter/process
     name mismatch with `ADAPTER_PROCESS_MISMATCH`.
  5. **New in this round** — two `evaluate_gate`-level refusal tests, built
     through the same `_build_cohort` real-adapter helper as group 3 (not a
     bare direct call to `check_ensemble_size`/`check_empty_support`): an
     under-supported 5-seed cohort refuses with
     `SINGLE_SEED_ENSEMBLE_REQUIRED` (never PASS, never any other computed
     verdict), and a fully quiet 50-seed cohort — zero fires on both the
     Karr and OC side — refuses with `EMPTY_EVENT_SUPPORT` (never a vacuous
     zero==zero PASS).

## Test results

```
tests/scripts/test_l2_event_ribosome_assembly_gate.py .............................. 30 passed in 27.51s
tests/scripts/test_l2_event_adapters.py
tests/scripts/test_l2_event_runner.py
tests/scripts/test_l2_event_registry.py
tests/scripts/test_l2_event_metrics.py                            ...................... 113 passed in 33.26s

# combined (all five files together):
143 passed in 32.69s

# tests/scripts -k l2_event (broader l2_event-scoped selector, includes the
# five files above plus other l2_event-named test modules under tests/scripts):
199 passed, 717 deselected in 36.34s
```

No regressions in the pre-existing L2.event suite; the new module is purely
additive (not imported by any existing module). `ruff check` on both touched
files (`scripts/l2_event/adapters/ribosome_assembly_gate.py`,
`tests/scripts/test_l2_event_ribosome_assembly_gate.py`) reports zero
findings.

## Closeout round: three non-blocking Opus5 review notes (two closed, one retained)

Opus5's pre-merge review of `5839798` accepted the adapter logic outright and
left three non-blocking notes across the two closeout sub-rounds (no adapter
production-logic changes were required or made in either sub-round; no defect
was found). Two are now closed; the third is an intentionally retained
registration-time consideration, not a defect, and is not claimed as fixed:

1. **Closed** — this report itself was stale relative to `5839798`: it still
   described the pre-review 20-test/index-membership-only state instead of
   `5839798`'s actual width-2 channel check (with its width-1/width-3
   refusal cases) and 27-test suite. Fixed in the first closeout sub-round
   (test-count/grouping and the `karr_observation` description now match
   HEAD as of that round).
2. **Closed** — the refusal gauntlet (`SINGLE_SEED_ENSEMBLE_REQUIRED`,
   `EMPTY_EVENT_SUPPORT`) had unit-level coverage (a bare direct call to
   `check_ensemble_size`) but no test exercising it through
   `evaluate_gate`/`_build_cohort` with this adapter's own
   `karr_observation`/`oc_observation` for an under-supported cohort or a
   fully quiet Karr+OC cohort. Added in the first closeout sub-round (group 5
   above); both refuse as expected, neither reaches a computed verdict. This
   second sub-round also closed a narrower, adjacent gap the first sub-round
   left unaddressed: the existing `test_karr_observation_raises_on_
   unmapped_complex_index` test (cardinality-1 mapping against a width-2
   channel) only ever reached the width-mismatch branch, never the
   `key is None` defensive branch for a non-dense mapping whose cardinality
   *does* match the channel width. Added
   `test_karr_observation_raises_on_non_dense_cardinality_2_mapping_unmapped_index`
   (`{0: RIBOSOME_30S, 5: RIBOSOME_50S}` against a width-2 channel) to
   isolate that branch specifically, asserted via the exact
   "channel index 1 has no declared WID mapping" message.
3. **Intentionally retained, not fixed** — a registration-time consideration
   about `required_payload_components`'s union-equality check (see the
   property's docstring above): because this adapter always requires the
   full fixed `{RIBOSOME_30S, RIBOSOME_50S}` keyspace, a real 50-seed cohort
   in which one of the two particles genuinely never forms across the whole
   ensemble (a legitimate low-probability biological outcome, not a data or
   adapter bug) would fail closed with a payload-channel `FAIL` rather than
   PASS. This is the same union-equality semantics already covered by
   `test_evaluate_gate_fails_when_oc_reports_a_spurious_extra_component` /
   `..._fails_when_oc_never_reports_the_50s_component`, so it is not an
   untested code path — it is a design tradeoff to flag for whoever
   eventually attempts registration/promotion of this adapter, not something
   this narrow, adapter/test-only closeout round is scoped to change. No
   adapter production-logic change is made here; this note is recorded so it
   is not lost, not resolved.

## Runner status (unchanged, as expected)

`ribosome_assembly.gate.v1` is **not** registered in `event_registry.yaml`
and is not gating-ready. Running the CLI/`evaluate_gate` for the real process
still resolves to the registered `ribosome_assembly.smoke.v1` adapter and
`mode="structural_smoke"` (verdict `NOT_APPLICABLE`), exactly as before this
change. This report does not claim the process is gate-eligible today.

## Exact missing raw-data requirements

To promote `ribosome_assembly.gate.v1` (or any adapter) to
`adapter_status: gating_ready` for RibosomeAssembly, the following raw data
does not currently exist on disk and must be produced by the (separate,
out-of-scope-here) MATLAB/Octave extraction pipeline:

1. **49 additional seeds** of event-window traces,
   `data/m1_sources/karr_native/per_process_traces_v2_event_s{001..049}/RibosomeAssembly_100ticks.mat`,
   matching the existing seed-000 file's shape/channel convention. Only
   `per_process_traces_v2_event_s000/RibosomeAssembly_100ticks.mat` exists
   locally (1 of the `required_n_seeds: 50` the registry already declares).
   `check_ensemble_size`'s `SINGLE_SEED_ENSEMBLE_REQUIRED` refusal is a direct,
   verified consequence of this gap.
2. **A complete M4 stride/window-anchor metadata contract** on every one of
   those files: `stride`, `tick_start`, `tick_end` (or `window_anchor`) must
   all be present and consistent. The existing seed-000 file predates this
   contract, which is why `load_and_check_window`/`evaluate_gate` refuses with
   `INCOMPLETE_WINDOW` on it today (verified empirically in this session's
   test 2 group above) — this is a metadata/provenance gap, not a numerical
   one; re-extracting seed 000 with the contract populated (in addition to
   the 49 new seeds) is required, not merely appending new seeds.
3. No new payload/complex-count channels are needed — the existing `complexs`
   (Karr) / `complex.counts` (OC) channels already carry everything the D6/D7
   contract requires; the gap is purely ensemble size (item 1) and metadata
   completeness (item 2).

Until both are supplied, the runner will continue to correctly refuse a
computed gate verdict for RibosomeAssembly, and `ribosome_assembly.gate.v1`
must remain unregistered / `adapter_status: not gating_ready` in the real
registry (see the proposed patch fragment for the row this would become once
the data exists).
