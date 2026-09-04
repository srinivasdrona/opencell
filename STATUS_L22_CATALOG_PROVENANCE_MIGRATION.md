# STATUS: L2.2 catalog-provenance migration (R6 fix)

Branch: `agent/l22-catalog-provenance-20260904` (worktree
`E:\opencell-worktrees\fix-l22-catalog-provenance`), base `5cbf4b2`.
**Not pushed/merged to main** — returned for Opus review per task
instruction.

## 2026-09-05 corrective pass (Opus re-review blocker)

The candidate above was **rejected** by Opus review with this blocker:
the resolved per-process contract (`schema.resolve_catalog_process_contract`)
silently omitted three fields actually read by code —
`primary_projection` (an ORDERED list), `joint_check`, and event
`seed_window.tick_range_from_division` — plus two secondary findings: the
generator's alternate-catalog audit path (`--catalog`) did not thread
through to the per-process contract hash, and the migration tool's
`git show` text decoding did not pin `encoding="utf-8"`.

**All five closed in this pass:**

1. `resolve_catalog_process_contract` now includes `primary_projection`
   (order preserved, default `[]`), `joint_check` (default `False`), and
   `seed_window` (only the structured `tick_range_from_division`
   sub-field; `seed_window.rationale` remains excluded free text; default
   `None` for rows with no `seed_window` at all) — see schema.py's R6
   section docstring for the full per-field justification (each verified
   by direct inspection of the actual reading code).
2. `tests/scripts/test_l22_evidence_catalog_contract.py`: 12 new tests
   proving each of the three fields stales only its own process, list
   order matters for `primary_projection`, omitted/explicit-default forms
   resolve identically, comments/key-order still don't matter, plus 5 new
   real-catalog sanity assertions — covering Replication, DNARepair,
   DNADamage, MacromolecularComplexation, Cytokinesis, and
   FtsZPolymerization by name (31 tests total in the file, up from 19).
3. `generator._current_source_hashes`/`_check_sweep_provenance_staleness`/
   `build_process_row`/`build_evidence_index`/`audit` now accept and
   thread `catalog_path`/`registry_path` straight through to
   `schema.process_contract_hashes` (mirroring `sweep.py`'s existing
   threading); the CLI gained a `--registry` flag on `generate`/`audit`.
   2 new tests in `test_l22_evidence_generator.py` prove an alternate
   `catalog_path` is actually honored (function-level and
   `build_process_row`-level).
4. `migrate_catalog_provenance.py`'s `git_show_text` now passes
   `subprocess.run(..., encoding="utf-8")` explicitly instead of relying
   on `text=True`'s locale-dependent fallback. 2 new tests in
   `test_l22_evidence_catalog_migration.py` commit a real non-ASCII byte
   sequence (em dash + Greek alpha) to a synthetic throwaway repo and
   prove both direct decoding correctness and an end-to-end migration run
   against it (14 tests total in the file, up from 12).
5. Because the resolved contract's key set changed for every process
   (three new fields, even for rows that never set any of them), the 19
   already-migrated rows' recorded `"catalog_entry"` hashes (computed
   under the incomplete first-cut contract) were themselves now stale
   under the corrected function. The tracked bundle's 19
   `sweep_provenance.json` files (+ `evidence_index.json`) were reverted
   to their pre-migration (whole-file-key) state via
   `git checkout 9141632~1 -- <paths>`, and
   `migrate_catalog_provenance.py --pre-ref f71cfbb --apply` was
   re-run against the CORRECTED code — identical outcome (19
   `MIGRATED`, `DNASupercoiling` still `SKIPPED_PRE_REF_CATALOG_MISMATCH`,
   `Cytokinesis`/`FtsZPolymerization` still `NO_EVIDENCE`), confirming none
   of the 19 rows' OWN resolved contracts (including the 3 new fields)
   changed between `f71cfbb` and the current tree. Regenerated
   `evidence_index.json` reads `integrity: OK`, `19 PASS / 1 FAIL
   (DNASupercoiling) / 2 MISSING_EVIDENCE (Cytokinesis,
   FtsZPolymerization)` — unchanged from before this pass.
   `git diff HEAD` on `evidence_bundle/`/`evidence_index.json` touches
   only each row's `"catalog_entry"`/`"event_registry_entry"` hash VALUE
   (same key names — a value update, not a key migration),
   `artifact_hashes["sweep_provenance.json"]`, and the index's
   `content_hash`/`generated_at`; verified line-by-line (not just
   `--stat`) that no `result.json`/`thresholds.json`/
   `null_calibration.json`/`SUMMARY.json`/`analytical_check.json`/
   `input_manifest.json`/`provenance.json` byte changed.

See `docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md` Section 13.18 for
the corrected field list and the full corrective-pass writeup.

## Problem

The accepted, source-bound Cytokinesis `M_ticks: 4000 -> 5000` catalog
edit (`8a569de`) made `generator.py audit` read **20 FAIL /
2 MISSING_EVIDENCE**. Root cause: every tracked
`evidence_bundle/<Process>/<subdir>/sweep_provenance.json`'s
`source_hashes` hashed `PROCESS_CATALOG.yaml` **whole**, under a shared
`"catalog"` key. Any single process's row edit therefore invalidated
every OTHER in-scope process's evidence too — a provenance-design defect,
not a real staleness signal. The `event_class` harness's
`event_registry.yaml` had the identical defect (verified empirically:
the same commit series appended Cytokinesis-only notes to that file,
whole-file-staling DNADamage's and RibosomeAssembly's rows).

## Design (fail-closed, not a bypass)

1. **`schema.resolve_catalog_process_contract(process, catalog_dict)`** /
   **`resolve_event_registry_process_contract(process, registry_dict)`**
   extract the RESOLVED subset of one process's row that can actually
   affect its evidence/verdict/scope:
   - Catalog: `bucket`, `harness_type` (resolved against the bucket-level
     default when the row omits it), `in_scope_L2_2`, `M_ticks`, `N_seeds`
     (resolved against `universals.N_seeds` when omitted),
     `primary_channel`, `closed_form_dominant`, `primary_distance`,
     `primary_projection` (an ORDERED list, corrected 2026-09-05),
     `joint_check` (corrected 2026-09-05),
     `event_channels`/`output_channels`/`input_channels`,
     `seed_window.tick_range_from_division` (corrected 2026-09-05;
     `seed_window.rationale` remains excluded free text), `oc_module`.
   - Registry: `in_scope_v4`, `adapter_id`, `adapter_status`,
     `event_timing_model`, `magnitude_gateable`, `required_n_seeds`.
   - Every field was verified by direct inspection of `verdict.py`,
     `generator.py`, `event_bridge.py`, the Design-A runner
     (`tests/vivarium/l2_2_design_a_runner.py`), and the L2.event runner
     (`scripts/l2_event/runner.py`) to actually be read. Free-text fields
     nothing reads (`notes`, `rationale_M`, `event_sweep_blocked_on`,
     `seed_window.rationale`, `karr_artifact`, `deferred_reason`) are
     excluded.
   - Using RESOLVED values (not raw row bytes) means an edit to
     `universals.N_seeds`/a bucket's `harness_type` default correctly
     stales every process that relies on it, without needing to
     separately track those defaults.
2. **`catalog_entry_hash`/`event_registry_entry_hash`** sha256 the
   canonical-JSON (`sort_keys=True`, no whitespace) serialization of the
   resolved contract — stable across YAML mapping key-order, formatting,
   and comment-only edits (`yaml.safe_load` already drops comments; list
   field ORDER is preserved since it is real content). Both raise
   `ValueError` for an unknown/missing/duplicated process row — fail
   closed, never a guessed/partial contract.
3. **`process_contract_hashes(process, harness_type, *, catalog_path=,
   registry_path=)`** is the single entry point that both
   `sweep.current_source_hashes()` (writer, at generation time) and
   `generator._current_source_hashes()` (checker, at audit time) call,
   merging `"catalog_entry"` (+ `"event_registry_entry"` for
   `event_class`) into the SAME `source_hashes` dict `oc_module` already
   lives in. The old whole-file `"catalog"`/`"l2_event_registry"` keys are
   REMOVED from `SWEEP_PROVENANCE_SOURCE_FILES`/`EVENT_CLASS_SOURCE_FILES`
   entirely. No new gating code path was needed: the existing R2 per-key
   staleness loop (`sweep.evidence_is_valid`/
   `generator._check_sweep_provenance_staleness`) already iterates
   `source_hashes.items()` generically, including the F5 bidirectional
   check that flags a RECORDED key no longer in the CURRENT expected set
   — this is what makes an un-migrated sentinel still carrying the old
   `"catalog"` key fail closed rather than silently pass.
4. Top-level `evidence_index.json["catalog_sha256"]` (whole-file) is
   UNCHANGED and remains purely informational — it was never gating.

## Migration tool

`scripts/l22_evidence/migrate_catalog_provenance.py` — one-shot,
atomic/resumable. Per row, refuses migration unless an EXPLICIT
`--pre-ref` proves ALL of:

1. the row's recorded whole-file `"catalog"` (+, for `event_class`,
   `"l2_event_registry"`) hash equals the ACTUAL sha256 of that file at
   `--pre-ref` (`git show <ref>:<path>`, never a local checkout);
2. every OTHER recorded `source_hashes` entry still matches the CURRENT
   tree (reuses the real, already-fixed `sweep.current_source_hashes`);
3. every `sidecar_hashes` entry still matches the CURRENT bytes on disk;
4. the process's OWN resolved catalog (+ registry) contract is
   byte-identical between `--pre-ref` and the current tree.

Only then does it drop the old key(s) and add the new one(s) — every
OTHER field (`process`/`n_seeds`/`m_ticks`/`completion_status`/
`git_sha`/`git_dirty`/`sidecar_hashes`/`inputs_verified`/
`evaluator_schema_version`/`result_schema_version`/every other
`source_hashes` entry) is copied through byte-for-byte unchanged.
`result.json`/`thresholds.json`/`null_calibration.json`/`SUMMARY.json`/
`analytical_check.json`/`input_manifest.json`/`provenance.json` are
NEVER touched. Writes are atomic (temp file + `os.replace`; verified via
a test that makes `os.replace` raise mid-run and confirms the original
file is untouched with a recoverable `.json.tmp` sibling) and
idempotent/resumable (an already-migrated row is reported
`ALREADY_MIGRATED` and left alone).

## Pre-ref determination (verified, not assumed)

`git log --oneline --all -- docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`
showed `8a569de "feat(l2-event): preregister Cytokinesis M_ticks=5000
single source of truth"` as the commit that changed Cytokinesis's
`M_ticks: 4000 -> 5000`. Its parent, **`f71cfbb`**, is the pre-ref.
Verified (not assumed):

```
sha256(git show f71cfbb:docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml)
  == f200c8d64190e918b4eaa5215204ee6c03853d67c628aeb5a5de58558e16152f
```

matches the recorded `source_hashes["catalog"]` in **19 of the 20**
tracked `sweep_provenance.json` files (every one except
DNASupercoiling, whose recorded hash — `d7e205d0...` — predates
`f71cfbb`, consistent with it also being independently stale on
`runner`/`helpers`/`projections`/`oc_module`/`chromosome_store_module`/
`l2_replay_common` — real, unrelated drift, plus a genuine
`PRIMARY_INSUFFICIENT_SAMPLES` scientific failure).

```
sha256(git show f71cfbb:docs/phase_f/l2_event/event_registry.yaml)
  == 7f57d616221569ad9ce51d84a1723ecf6ccb2dc46bf1346e60fb47f916b43f9d
```

matches both `event_class` rows' recorded `source_hashes["l2_event_registry"]`
(DNADamage, RibosomeAssembly).

## Migrated rows (19)

DNADamage, DNARepair, MacromolecularComplexation, Metabolism,
ProteinDecay, ProteinFolding, ProteinModification, ProteinProcessingI,
ProteinProcessingII, ProteinTranslocation, RNADecay, RNAModification,
RNAProcessing, Replication, ReplicationInitiation, RibosomeAssembly,
Transcription, Translation, tRNAAminoacylation.

**Not migrated:** DNASupercoiling (recorded catalog hash predates
`f71cfbb`; independently stale on unrelated source hashes; already FAIL
for real scientific reasons). **No tracked evidence:** Cytokinesis,
FtsZPolymerization (unaffected either way).

## Before / after audit

| | Before | After |
|---|---|---|
| `integrity` | FAIL | **OK** |
| `aggregate_verdict` | NON_GREEN | NON_GREEN (expected/honest) |
| `PASS` | 0 (all rows carried a stale-provenance reason) | **19** |
| `FAIL` | 20 | **1** (DNASupercoiling, real reasons) |
| `MISSING_EVIDENCE` | 2 | 2 (Cytokinesis, FtsZPolymerization — unchanged) |

Verified byte-identical: every migrated row's `result.json`,
`thresholds.json`, `null_calibration.json`, `SUMMARY.json`,
`analytical_check.json`, `input_manifest.json`, `provenance.json`, and
`sweep_provenance.json["sidecar_hashes"]`/`["git_sha"]`/
`["completion_status"]`/etc are unchanged (`git diff --stat` on
`evidence_bundle/` touches only 19 files, each a 1-line-removed/
1-line-added `source_hashes` edit, 2 lines for the 2 `event_class`
rows). MacromolecularComplexation's row specifically: `green: true`,
`mechanical_verdict: PASS`, `reasons: []` — unchanged from its prior
accepted closure.

## Tests

- **`tests/scripts/test_l22_evidence_catalog_contract.py`** (31 tests,
  19 original + 12 added 2026-09-05): cross-process isolation for both
  `catalog_entry_hash` and `event_registry_entry_hash` (a Cytokinesis-analog
  M_ticks edit never changes Translation's/Macromol's hash), a process's
  own M/N/primary_channel/harness_type change stales only that process,
  `universals.N_seeds`/a bucket's `harness_type` default change stales
  processes relying on it (never one that overrides explicitly),
  comment-only and YAML-reformatting/key-order edits change nothing,
  unknown/duplicate process raises, `process_contract_hashes` includes
  `event_registry_entry` only for `event_class`, an explicit un-migrated-
  sentinel test (real `Metabolism` evidence with `catalog_entry` swapped
  back to the old whole-file `catalog` key is flagged non-green via the
  F5 bidirectional extra-recorded-key check), real-catalog sanity checks
  (every in-scope process resolves without raising, deterministic across
  repeated calls); **2026-09-05 additions**: `primary_projection` isolation
  (DNARepair-only edit never staling Replication/DNADamage/Translation),
  order-sensitivity (reordering Replication's components changes the hash
  even with identical membership/length), omitted-vs-explicit-`[]`
  consistency; `joint_check` isolation (MacromolecularComplexation-only)
  and omitted-vs-explicit-`false` consistency; `seed_window.
  tick_range_from_division` isolation (Cytokinesis-only edit never staling
  FtsZPolymerization), `rationale` free-text exclusion,
  omitted-resolves-to-`None`; plus 5 real-catalog sanity assertions on the
  actual Replication/DNARepair/DNADamage/MacromolecularComplexation/
  Cytokinesis/FtsZPolymerization/Translation rows.
- **`tests/scripts/test_l22_evidence_catalog_migration.py`** (14 tests,
  12 original + 2 added 2026-09-05): builds a REAL, synthetic, throwaway
  git repository per test (never mocked) to exercise the actual
  `git show <ref>:<path>` code path. Covers: happy-path migration of
  unrelated rows + refusal of a genuinely-changed one (Cytokinesis-analog);
  never touches `result.json`/other authority files; idempotency;
  atomic-write crash recovery (simulated `os.replace` failure); wrong
  `--pre-ref` refuses every row; non-catalog source-hash drift refuses;
  sidecar mutation after generation refuses; event_class registry pre-ref
  mismatch refuses independently of the catalog check; a sentinel
  `process` field mismatch (copied from a different process's directory)
  refuses; missing evidence reports `NO_EVIDENCE`; unknown process filter
  raises; **2026-09-05 additions**: `git_show_text` correctly decodes a
  real committed non-ASCII byte sequence (em dash + Greek alpha) as UTF-8
  (direct round-trip proof against a raw, encoding-agnostic
  `subprocess.run(..., text=False)` sha256, plus an end-to-end migration
  run that succeeds despite the non-ASCII bytes).
- **`tests/scripts/test_l22_evidence_generator.py`** (2 tests added
  2026-09-05): `_current_source_hashes` and `build_process_row` honor an
  explicit alternate `catalog_path` for the `"catalog_entry"` staleness
  hash (proven both at the hash-value level and via a real PASS row
  flipping to stale when audited against an altered catalog copy) rather
  than silently defaulting to the real tracked `PROCESS_CATALOG.yaml`.
- **Pre-existing suites**: fixed ~30 tests in
  `tests/scripts/test_l22_evidence_sweep.py` (generic sweep-mechanics
  tests that constructed `SweepJob`s with synthetic process names never
  present in the real catalog — harmless before this fix, a hard
  `ValueError` after, since `sweep.current_source_hashes` now resolves
  `catalog_entry_hash` for whatever `process` it's given) by using real,
  distinct in-scope catalog process names instead; fixed 1 test in
  `test_l22_evidence_anticheat.py`
  (`test_sut_oc_module_change_stales_only_that_process`, same root
  cause: synthetic `ProcessEntry.name` values "FakeProcA"/"FakeProcB");
  tightened 1 test in `test_l22_evidence_portability.py`
  (`test_generate_falls_back_to_bundle_when_evidence_root_absent`,
  whose comparison baseline — the live, gitignored `EVIDENCE_ROOT` tree —
  is legitimately absent on this machine; now compares against an
  explicit bundle-rooted build and asserts a real PASS row exists, per
  the test's own prior docstring's stated future-tightening intent).

**Full-suite run** (`test_l22_evidence_{sweep,anticheat,generator,
portability,catalog_contract,catalog_migration}.py` +
`test_l2_2_strict_rubric.py`, 174 tests, re-run 2026-09-05 after the
corrective pass): **173 passed, 1 failed**. The
1 failure
(`test_l22_evidence_anticheat.py::test_process_dependency_registry_matches_real_current_import_graph`)
is a stale assertion about `schema.PROCESS_DEPENDENCY_FILES["DNADamage"]`
unrelated to this task — confirmed via `git stash` to fail identically
on the unmodified baseline. Also confirmed pre-existing/unrelated via the
same method:
`test_l22_evidence_ast_completeness.py::test_zero_uncovered_first_party_imports_across_real_in_scope_processes`
(Replication registry gap).

## Commits (this branch, 9, on top of `5cbf4b2`)

1. `e2a6c49` — `fix(l22-evidence): replace whole-catalog provenance with
   per-process contract hashes` — schema.py/generator.py/sweep.py +
   fixture repairs + new contract tests.
2. `fd2b848` — `feat(l22-evidence): one-shot migration tool for legacy
   whole-catalog sweep_provenance.json` — migration tool + anti-tamper
   tests.
3. `9141632` — `data(l22-evidence): migrate tracked bundle to per-process
   catalog contracts, regenerate index` — applied migration, regenerated
   `evidence_index.json`, portability test tightening, provenance log.
4. `e8fe3b2` — `docs(l22-evidence): document R6 per-process
   catalog-contract fix (Section 13.18)` — EVIDENCE_INDEX_SPEC.md.
5. `4decbee` — `docs(l22-evidence): STATUS write-up + plan.md
   operational handoff refresh` — this file + plan.md.
6. `8369662` — `test(l22-evidence): explicit test that a leftover old
   whole-catalog key is rejected` — direct anti-tamper proof of the
   post-migration fail-closed property.
7. `f4f376f` — `fix(l22-evidence): R6 corrective pass -- field
   completeness, catalog_path threading, encoding` (2026-09-05, Opus
   re-review) — `primary_projection`/`joint_check`/`seed_window.
   tick_range_from_division` added to the resolved contract;
   `catalog_path`/`registry_path` threaded through
   `generator.py`'s staleness-checking functions and CLI; `git_show_text`
   pins `encoding="utf-8"`; 16 new tests across 3 test files.
8. `85fd64b` — `data(l22-evidence): re-migrate bundle under corrected R6
   catalog contract` (2026-09-05) — reverted the 19 migrated rows to
   pre-migration state and re-ran the migration tool against the
   corrected code; identical outcome (19 PASS / 1 FAIL /
   2 MISSING_EVIDENCE).
9. (this commit) — `docs(l22-evidence): correct Section 13.18 field list
   + STATUS completeness claims` (2026-09-05) — EVIDENCE_INDEX_SPEC.md +
   this file, reflecting the corrective pass.

## Not done / explicitly out of scope

- No sweep reruns (per task instruction — this is a provenance-metadata
  fix, not a biology rerun).
- Did not push or merge to main — returned for Opus review.
- Did not touch `PROCESS_CATALOG.yaml`/`event_registry.yaml` row content
  themselves (only how they are hashed for staleness).
- Did not fix the 2 confirmed-pre-existing, unrelated test failures
  (DNADamage `PROCESS_DEPENDENCY_FILES` registry gap; Replication AST
  import-completeness registry gap) — out of scope for this task;
  reconfirmed unrelated after the 2026-09-05 corrective pass too (both
  still fail identically under `git stash` on this branch's own
  unmodified baseline).
- **CORRECTED 2026-09-05** (previously listed here as "not done", now
  done): `generator._current_source_hashes`/`_check_sweep_provenance_
  staleness`/`build_process_row`/`build_evidence_index`/`audit` now all
  accept and thread `catalog_path`/`registry_path` straight through to
  `schema.process_contract_hashes`, and the CLI gained a `--registry`
  flag on `generate`/`audit` — see the corrective-pass section at the top
  of this file and `EVIDENCE_INDEX_SPEC.md` Section 13.18.
