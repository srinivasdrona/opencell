# STATUS: L2.1 Cytokinesis Clean Integration (2026-09-08)

## Summary

Scoped, surgical integration of the accepted Cytokinesis L2.1 active-window
fix from `fix-l21-cytokinesis-active` (HEAD `75e4977`, base `3b424e7`, see
that worktree's `STATUS_L21_CYTOKINESIS_ACTIVE_FIX.md` Update 6) onto
current main (`4ff3b5d`), in this dedicated clean integration worktree.
Followed the operator-relayed final Opus integration prescription exactly:
scoped file selection (never a wholesale branch merge), required edits
verified/applied, three-way merges on every file main had independently
evolved since the branch's base, M5000 trace data copy + hash
verification, mechanical manifest promotion via the branch's own promotion
script, and the full post-review gate checklist.

**Result: Cytokinesis L2.1 promoted `CODE_GAP` -> `EXISTING_WINDOW_PASS`.**
`docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json` counts:
`7/3/1` -> **`8 EXISTING_WINDOW_PASS / 2 CODE_GAP / 1 MISSING_ACTIVE_EXTRACTION`**.
All 10 other rows byte-for-byte preserved. Not merged/pushed to main --
committed on `integrate/l21-cytokinesis-clean` (`46373f6`, `2bf2366`),
awaiting final lightweight review.

## What was taken from the source branch (scoped, not wholesale)

- `opencell/util/mcg16807_state_codec.py` + `tests/util/test_mcg16807_state_codec.py`
  (new, 26 tests) -- live-MATLAB-verified mcg16807 `State` encode/decode.
- `opencell/vivarium/karr_cytokinesis.py` + `tests/vivarium/test_karr_cytokinesis.py`
  + `tests/vivarium/test_karr_cytokinesis_l2_replay.py` -- codec wiring,
  `filamentLengthInNm` fixture fix (no `40.0` fallback), M5000 randStream
  ledger.
- `scripts/l2_event/analyze_cytokinesis_randstream_probe.py` + test --
  `steps_between`/`scalar_state` analyzer.
- `scripts/l21_promote_cytokinesis_manifest.py` -- mechanical, fail-closed
  manifest promotion script.
- `scripts/matlab/probe_cytokinesis_randstream_state.m` + static test --
  Stage-1 probe (extractor-hash pin **recomputed** against the final
  merged extractor: `c801738037e48d789fa52268c9576463dbce958a4f1d5bca62310902c57a5c37`).
- `data/schemas/per_process_wiring/Cytokinesis.yaml` +
  `docs/phase_f/l2_event/evidence_bundle/Cytokinesis/input_manifest.json`
  (M5000 seed-36 trace hash `b0c919e8089da0ae2813b9301c167d24a6c766bce7dde83bbf621d3ade3eeeb0`
  added alongside the existing seed-0 entry).

**Never carried:** `opencell/vivarium/karr_protein_decay_light.py` (branch's
own Update 6 reverted all changes to it -- confirmed identical to main),
and no stale other-process replay fixture files.

## Required edits verified/applied

1. **No `40.0` fallback** -- `karr_cytokinesis.py` hard-fails
   (`_require_positive_float`) if the FtsZRing fixture lacks
   `filamentLengthInNm`/`numFtsZSubunitsPerNm`; confirmed no `40.0` literal
   remains in the load path.
2. **Full RNG payload parser** -- `_karr_randstream_state` passes the
   entire captured cell-vector to `parse_captured_state`, never a
   pre-truncated `[0]` slice; confirmed via 5 dedicated hard-fail tests
   (multi-element/NaN/non-integer/out-of-range) plus a genuine-single-element
   acceptance test.
3. **Removed banned extractor token** -- `karr_cytokinesis.py`'s docstring
   reference to `extract_per_process_traces_v2.m` was reworded (no
   `per_process_traces` substring) so it no longer trips
   `test_l2_no_oracle_dependency.py`'s AST string-literal scanner via a
   documentation mention rather than a real oracle read. Also removed the
   stale, non-main-safe absolute-worktree-path Cytokinesis fallback in
   `l21_active_window_audit.py::_special_candidates` (Update 6 blocker #4).
4. **Correct STATUS attribution** -- this integration's own STATUS
   (this file) accurately attributes science fixes to the source branch
   and integration-specific fixes (see "Bugs found during merge" below) to
   this integration pass.
5. **Removed Cyt from oracle allowlist** -- `karr_cytokinesis.py` dropped
   from `tests/vivarium/test_l2_no_oracle_dependency.py::_ALLOWLIST`
   (genuinely clean post-fix). A pre-existing, unrelated staleness
   (`karr_dna_damage.py` also no longer violates but remains allowlisted)
   was left untouched -- confirmed present on main *before* this
   integration (out of scope; not introduced by this change).
6. **Refreshed method-map/wiring anchors** -- `scripts/l1b_verify_wiring.py
   --process Cytokinesis` -> PASS (1/1); full 28-process sweep -> 27/28
   PASS (pre-existing, unrelated `DNADamage` `check_oc_anchors_resolve`
   failure untouched).

## Three-way merges (main had independently evolved every one of these since the branch's base)

- **`scripts/matlab/extract_per_process_traces_v2.m`**: clean auto-merge.
  Per-tick `randStreamState` capture (both tap points, inside the generic
  `if proc_idx == target_idx` block -- applies to whichever process is
  being extracted, never Cytokinesis-gated) and unconditional (not
  `canonical_name`-gated) dec-005 DNADamage source-hash metadata compose
  cleanly with main's existing Host/TranscriptionalRegulation/current
  hunks.
- **`scripts/l21_active_window_audit.py`**: 3 manual conflicts. Kept
  main's current chromosome/Host/DNA fixes; added the M5000-preferred-trace
  selection and dec-005 binding check. **Bug found and fixed during
  merge**: `_choose_preferred_or_earliest_active` silently fell through to
  the generic earliest-active heuristic when the mandated M5000 trace was
  present but showed no activity (`first_active_tick is None`) --
  contradicting its own docstring's "never silently substitutes another
  trace when the mandated one IS present" claim. Now raises `RuntimeError`
  instead (present-but-inactive preferred trace hard fail, as required).
- **`scripts/l2_event/launcher.py`**: 3 manual conflicts, all involving a
  genuine **API collision**: main and the branch each independently added
  a `current_genuine_dnadamage_source()` with different signatures/return
  keys (main: `repo_root` kwarg, `*_lf_normalized` keys; branch: `wcm_root`
  kwarg, bare keys). Kept main's version verbatim (main API). The
  branch's net-new `_read_dnadamage_source_metadata()` (a trace-file
  metadata reader main lacked) merged in cleanly (non-conflicting) and was
  kept. Fixed its two downstream consumers
  (`l21_active_window_audit.py::_dnadamage_source_binding_status`, the
  M5000 promotion test) to derive "resolved" from main's
  `overlay_required`/`*_lf_normalized` fields instead of a nonexistent
  `resolved_sha256` key. Adapted `test_l2_event_launcher.py`'s two
  `current_genuine_dnadamage_source` tests (kwarg name, key names, and one
  error-message substring `"!= required"` -> `"!= expected"`) to test
  main's kept API instead of the rejected one.
- **`tests/scripts/test_extract_per_process_traces_v2_static.py`**:
  clean auto-merge, combined assertions (extended dnadamage-overlay test +
  new randStreamState-capture test). Both sides had independently added an
  identical `test_pick_snapshot_properties_includes_transcriptional_regulation_binding_surfaces`;
  de-duplicated to one copy.
- **`data/karr_method_inventory/oc_method_map.yaml`**,
  **`tests/scripts/test_l2_event_launcher.py`**: main's tip was
  byte-identical to the branch's base for both, so the merge trivially
  resolved to main's/branch's content respectively with no manual
  intervention (`test_l2_event_launcher.py` still needed the two
  `current_genuine_dnadamage_source` test fixes above, applied after the
  auto-merge).

## Data

Copied the M5000 seed-36 trace (gitignored, 39MB) from
`fix-l21-cytokinesis-active`'s worktree into:
- this integration worktree, and
- `main-integrate`'s local root (for eventual main integration).

Both copies verified `sha256 = b0c919e8089da0ae2813b9301c167d24a6c766bce7dde83bbf621d3ade3eeeb0`,
matching the source worktree and the recorded manifest hash exactly.

## Manifest promotion

`scripts/l21_promote_cytokinesis_manifest.py` run live: fresh mechanical
scan (`l21_active_window_audit.py --process Cytokinesis`, 2 candidates
scanned) + fresh live run of
`test_karr_cytokinesis_l2_event_replay_m5000_randstream_bound[event_seed_36_m5000]`
(passed). dec-005 DNADamage source-hash binding verified
(`trace_resolved_sha256 == current_resolved_sha256`,
`86d8b3c2d2ed42df03e1b9ea14f06efc4b645a4e6aeaa3ef938b9ea41ad27e7e`).
Surgical single-row replacement (diff touches only the `Cytokinesis` row,
top-level `counts`, and `pytest_replay_command`); all 10 other rows
byte-for-byte unchanged. Final counts:
`8 EXISTING_WINDOW_PASS / 2 CODE_GAP / 1 MISSING_ACTIVE_EXTRACTION`.

Note: running `scripts/l21_active_window_audit.py --process Cytokinesis`
**standalone** (outside the promotion script) still reports `CODE_GAP` for
Cytokinesis -- this is expected and by the promotion script's own design:
Cytokinesis's RNG-state-restoring replay semantics live in the specialized
L2 replay test harness (`_run_replay`/`_assert_randstream_ledger`/RNG-state
restoration at tick 0), not in the generic audit engine's
`_classify_live_trace_candidate`, which lacks that restoration and so
mismatches from tick 0. The manifest (the authoritative source) is
produced by the promotion script's combination of the mechanical scan
(trace discovery/hash/dec-005 binding) with the specialized pytest verdict
-- never by the generic engine alone.

## Post-review gate results

All run via `bin\oc-pytest.cmd` / `bin\oc-py.cmd` (WSL venv), per the
project's execution-environment rule.

```
Promotion test (M5000 randstream-bound, live)              -> PASSED, not skipped
tests/util/test_mcg16807_state_codec.py                     \
tests/vivarium/test_karr_cytokinesis.py                      | 68 passed, 1 skipped
tests/vivarium/test_karr_cytokinesis_l2_replay.py             (skip = optional M4000
tests/scripts/test_analyze_cytokinesis_randstream_probe.py   seed-0 trace absent in
                                                              this fresh worktree;
                                                              M5000 promotion node PASSED)
tests/vivarium/test_l2_no_oracle_dependency.py               -> 37 passed, 1 failed
tests/prompts/test_rule8_no_oracle_reads.py                    (failure = pre-existing,
                                                                 unrelated karr_dna_damage.py
                                                                 allowlist staleness,
                                                                 confirmed present on main
                                                                 BEFORE this integration;
                                                                 Cytokinesis itself clean)
tests/scripts/test_division_window_spec.py                  \
tests/scripts/test_l2_event_launcher.py                      |
tests/scripts/test_extract_per_process_traces_v2_static.py   |
tests/scripts/test_l22_evidence_generator.py                 | 197 total, all passed
tests/vivarium/test_l2_1_strict_rubric.py                    | after 2 fixes (see below)
tests/scripts/test_probe_l2_1_strict_rubric_active_windows.py|
tests/integration/test_l1b_verify_wiring.py                  |
tests/scripts/test_probe_cytokinesis_randstream_state_static.py/

  Fixed during this pass (both downstream test-expectation staleness, not
  functional bugs):
  - test_l2_event_launcher.py::test_plan_regenerate_invalid_for_dnadamage_source_mismatch
    expected the rejected branch API's error wording ("!= required");
    updated to main's kept wording ("!= expected").
  - test_probe_l2_1_strict_rubric_active_windows.py::
    EXPECTED_ACTIVE_WINDOW_VERDICTS['Cytokinesis'] was CODE_GAP; updated to
    GENUINE to match the promoted manifest.

l1b_verify_wiring.py --process Cytokinesis                   -> PASS (1/1)
l1b_verify_wiring.py (full 28-process sweep)                 -> 27/28 PASS
                                                                 (DNADamage pre-existing,
                                                                  unrelated, untouched)
ruff check <all touched .py files>                            -> All checks passed!
```

`docs/phase_f/l2_1/L21_ACTIVE_WINDOWS_MANIFEST.json` counts after
promotion: `8/2/1` (see above) -- matches the expected `8 EWP/2 CODE_GAP/1
MISSING` at this moment (no concurrent DNADamage integration landed during
this pass).

## Not done in this pass

- Not merged/pushed into main. This worktree/branch
  (`integrate/l21-cytokinesis-clean`) is ready for final lightweight
  review; the operator's own merge/push discipline applies.
- Did not re-run the full multi-process `l21_active_window_audit.py`
  sweep (no `--process` filter) live to completion -- historical runtimes
  for some of the other 10 target processes (e.g. Metabolism FVA) run to
  tens of minutes each; the authoritative manifest state was instead
  verified via the promotion script's own mechanical scan plus the full
  `test_probe_l2_1_strict_rubric_active_windows.py` per-process rubric
  sweep (197-test batch above), which independently re-derives every
  row's verdict from the current tree and passed for all 11 rows
  including Cytokinesis.
