# STATUS: Division-window cohort-censoring contract (final Opus review round)

Branch `fix/division-censor-contract`, worktree
`E:\opencell-worktrees\fix-division-censor-contract`, base `701b991`.
Not merged/pushed to main. Sections 1-6 below (unchanged since the second
Opus re-review) record the code fixes for all six original review items.
See "Final round: accounting refresh + seed 6 backfill" at the bottom of
this document for this session's work: a fresh dedicated-root audit
(23 COMPLETED + 2 RIGHT_CENSORED, up from 21+1) and seed 6's mechanical
RIGHT_CENSORED backfill.

## 1. Horizon predicate: recorded >= window_anchor, not recorded >= n_ticks (FIXED)

* **The real bug**: the first fix round's monotone-minimum check compared
  a COMPLETED trace's recorded `max_search_ticks` against the process's
  own `n_ticks` (e.g. 5000 for Cytokinesis) — far too loose. It would have
  silently accepted impossible metadata such as `max_search_ticks=6000`
  paired with `window_anchor=31993` (a search ceiling that could never
  have observed that completion).
* **Fix**: `launcher.validate_existing_event_window` now requires
  `metadata.max_search_ticks >= metadata.window_anchor` (both non-null)
  for a COMPLETED anchor trace — the tightest floor directly available
  from the trace's own already-loaded metadata, and the correct
  structural invariant (the real capture loop can never observe a
  completion strictly beyond the search ceiling it was actually bounded
  by). This still preserves monotone validity of every currently-banked
  50000-recorded completion (`50000 >= window_anchor` trivially, since
  `window_anchor` never exceeds a few tens of thousands of ticks) while
  correctly rejecting the impossible `max=6000/anchor=31993` case.
* `docs/phase_f/l2_event/division_window_spec.json`'s
  `max_search_ticks_validation_policy` prose updated to describe this
  corrected policy explicitly, including why the first round's `n_ticks`
  floor was too loose.
* New tests added to `test_l2_event_launcher.py`: the exact
  `max=6000/anchor=31993` impossible-metadata fixture Opus named
  (`test_anchor_trace_realistic_impossible_horizon_max6000_anchor31993_is_rejected`),
  the general "clears n_ticks but still impossible" gap
  (`test_anchor_trace_max_search_ticks_above_n_ticks_but_below_window_anchor_is_rejected`),
  the boundary case (`recorded == window_anchor` validates), and the
  original smaller-than-both-floors rejection, updated to check the new
  message wording.
* **All 21 currently-banked COMPLETED pairs (seeds 0-5, 17, 34-47) were
  re-validated end-to-end this session under the corrected check via
  `validate_dual_division_canary` — 21/21 PASS** (run natively against
  the real `dual_division_cohort_current` root; see verification section
  below for the exact output). RIGHT_CENSORED's exact/full `>=100000`
  requirement (a separate, unrelated check in
  `division_cohort_selector`) is unchanged.

## 2. Default root execution (FIXED)

* **The real bug**: `authoritative_karr_native_root()`'s three candidates
  (this checkout, and the MAIN CHECKOUT's Windows/WSL paths) never
  actually matched where the real consolidated data lives — the
  dedicated root is under a SIBLING WORKTREE named `main-integrate`, not
  the main checkout (`E:\opencell`) itself. Every default invocation
  therefore silently fell through to `autodiscover_karr_native_roots`'s
  full ~93-sibling-worktree scan, which (before this round's other fixes)
  could traceback on a documented-superseded/legacy trace pair in an
  unrelated worktree.
* **Fix**: added a portable, drive-letter-independent candidate —
  `repo_root.parent / "main-integrate" / data/m1_sources/karr_native/
  dual_division_cohort_current` — which correctly resolves regardless of
  which worktree this code runs from or which drive letter the checkout
  lives on. Verified: `authoritative_karr_native_root()` now resolves to
  the real `.../main-integrate/data/m1_sources/karr_native/
  dual_division_cohort_current` path in this environment.
* `default_search_roots()` now returns the authoritative root ONLY (or an
  empty list if it cannot be found anywhere) — it NEVER appends the
  broader sibling-worktree scan by default. A new `broad_search_roots()`
  function offers that broader scan as an explicit opt-in for callers who
  want it (e.g. a one-off manual consolidation audit).
* `main()`'s CLI now fails closed with an actionable stderr message
  (naming `--search-root` as the required override) when the
  authoritative root cannot be found anywhere, instead of silently
  broadening the scan.
* `discover_ledger` gained an `authoritative_root` parameter: a
  NON-authoritative root's resolution failure (invalid/superseded trace,
  any other exception) is now caught and reported in a new
  `rejected_root_traces` list, never fatal; the SAME failure in the
  authoritative root itself remains fatal. `resolve_seed_attempt` itself
  was also hardened to convert raw `OSError`/`ValueError`/`KeyError` from
  `validate_dual_division_canary` (e.g. a non-HDF5 garbage file) into
  `CohortContractError` rather than letting it escape as a bare
  traceback, at both call sites (sidecar cross-check and trace-only
  backfill).
* Added `--search-root` passthrough to
  `ftsz_pre_division_evidence.py --use-cohort-selector`.
* **Real no-arg CLI proof, this exact machine layout**: ran
  `python scripts/l2_event/division_cohort_selector.py` with zero
  arguments. Result: a clean JSON report (6 completed, 16 premature, 26
  gaps, 0 rejected_root_traces) and exit code 2 — **no traceback**. Full
  captured output is in `DIVISION_WINDOW_MIGRATION.md`'s "Real no-arg CLI
  proof" section. (Run natively for I/O speed against the real E: drive
  data — behaviorally identical to the canonical WSL path; the WSL
  invocation was independently confirmed not to traceback either, only
  slower due to cross-filesystem HDF5 reads.)
* New portable/fast automated tests (not depending on the real machine's
  data): multi-root agreement/dedup, a genuine two-valid-records
  contradiction (still fatal), non-authoritative-root invalid trace
  (rejected, not fatal), authoritative-root invalid trace (still fatal),
  sibling-`main-integrate` resolution, `default_search_roots` never
  broadening by default, and mocked no-arg CLI report/exit2 + fail-closed
  proofs.

## 3. Record identity cross-check (FIXED)

* **The real bug**: when an attempt JSON existed alongside COMPLETED
  trace files, `resolve_seed_attempt` only confirmed the trace pair
  independently validated PASS — it then returned an `AttemptRecord`
  built from the SIDECAR's own self-claimed fields (onset/completion
  ticks, both trace hashes, source/provider identity), never
  cross-checked against what `validate_dual_division_canary` actually
  measured from the real files. A copied/tampered sidecar (or one written
  for a different seed's trace pair) could smuggle a false claim past the
  PASS gate.
* **Fix**: every sidecar identity field with a directly measurable
  counterpart (`max_search_ticks` — now also read from the trace's own
  metadata via `_read_metadata_int`, `mnrnd_provider_sha256`,
  `dnadamage_source_resolved_sha256`, `onset_tick`, `completion_tick`,
  `cytokinesis_trace_sha256`, `ftsz_trace_sha256`) is cross-checked
  against the MEASURED value; any disagreement raises
  `CohortContractError` naming both the claimed and measured values. The
  returned `AttemptRecord` always carries the MEASURED values, never the
  sidecar's raw claims. Cross-root agreement checks
  (`discover_ledger`/`_records_agree`) therefore now only ever compare
  measured values.
* `_IDENTITY_FIELDS` (the cross-root agreement field list) also gained
  `max_search_ticks`, which the first round's list had omitted — a gap
  that let a mismatched `max_search_ticks` between two roots' RIGHT_
  CENSORED records slip past the contradiction check entirely.
* New tests: a tampered-sidecar-over-garbage-trace scenario (proves the
  malformed-trace defense fires first), a tampered `onset_tick` over a
  REAL, PASS-validating HDF5 fixture pair (the genuine inversion — proves
  the identity cross-check itself fires), and a positive control (a
  correct sidecar is accepted and the record carries measured values).

## 4. Docs/STATUS accounting corrected by discovery (FIXED)

* Re-surveyed the real `dual_division_cohort_current` root this session:
  **22 seed directories** — **21 COMPLETED pairs** (0-5, 17, 34-47) plus
  **1 RIGHT_CENSORED** (seed 18, backfilled the prior round). Of the 21
  COMPLETED pairs, 6 (seeds 0-5) are the contiguous-selectable prefix and
  **15** (17, 34-47) are premature — the prior round's STATUS/migration
  doc incorrectly said "21" premature; corrected throughout.
  `docs/phase_f/l2_event/DIVISION_WINDOW_MIGRATION.md` rewritten again
  with the corrected breakdown, explicitly labeled as a dated snapshot,
  and now includes the real captured `division_cohort_selector.py`
  no-arg CLI JSON output as the generated-by-the-auditor evidence for
  these counts (rather than a hand-computed table only).

## 5. Non-forced batch skips (not hard-errors on) an existing valid RIGHT_CENSORED record (FIXED)

* **The gap**: a RIGHT_CENSORED seed has neither trace file, so the
  driver's existing `both_exist` skip check never fired for it; the
  now-non-forced re-run would fall through to calling
  `extract_dual_division_window` again, which (per the first round's
  fix) raises `extract_dual_division_window:censored_attempt_exists` —
  and the driver's catch-block only specially handled the NEW
  `:right_censored` identifier, so this OTHER identifier fell into
  `failed_seeds`, incorrectly turning "already honestly censored" into
  an aggregate-throw-worthy defect.
* **Fix**: `extract_dual_division_window_seeds.m` now checks for an
  existing valid RIGHT_CENSORED record BEFORE ever calling the extractor
  (skip + report into a new `already_censored_seeds` bucket, never
  counted toward `censored_seeds` this-run or `failed_seeds`), with a
  belt-and-braces catch-block handler for
  `:censored_attempt_exists` doing the same if the pre-check is ever
  bypassed. New static tests confirm the pre-check precedes the
  extractor call and never touches `failed_seeds`, the catch-block
  fallback behaves identically, and the new bucket is declared.

## 6. Verification re-run

* Targeted suite: **275 passed** (up from 267 last round — 8 net new
  tests this round after accounting for the removed/renamed
  `n_ticks`-floor test): `test_division_cohort_selector.py` 40,
  `test_division_window_spec.py` 27,
  `test_division_window_selection_contract_static.py` 6,
  `test_extract_dual_division_window_static.py` 40,
  `test_prepare_cytokinesis_cohort.py` 5,
  `test_ftsz_pre_division_evidence.py` 26,
  `test_validate_dual_division_canary.py` 17,
  `test_l2_event_launcher.py` 98, `test_backfill_right_censored_from_log.py` 16.
* **Live dedicated-root audit, all 21 validators**: ran
  `validate_dual_division_canary` against every one of the 21 real
  banked COMPLETED pairs (seeds 0-5, 17, 34-47) in
  `dual_division_cohort_current`, natively, under the corrected
  `window_anchor`-based horizon check — **21/21 PASS**, zero reasons.
* **No-arg CLI, real machine layout**: clean JSON report + exit code 2,
  no traceback (see item 2 and `DIVISION_WINDOW_MIGRATION.md`).
* L2.2 evidence portability (`test_l22_evidence_portability.py`): **7
  passed**, the required **19 PASS / 1 FAIL / 2 MISSING_EVIDENCE**
  Design-A tally remains intact (`PROCESS_CATALOG.yaml` still untouched).
* Full `l2_event`/`division`/`cytokinesis`/`ftsz`/`backfill`-scoped sweep:
  **385 passed, 17 skipped**, the same 1 pre-existing unrelated failure
  reconfirmed present at base `701b991`
  (`test_shared_evidence_index_is_known_stale_for_ribosome_assembly_after_this_promotion`).
* `ruff check` on every new/modified Python file: clean.
* Provenance logged (`opencell/provenance/llm_interactions.jsonl`) at the
  same commit as this STATUS update.
* Seed 6's live 100000-tick attempt (`bulk-division-a/artifacts/
  seed6_100k_probe.status`) reconfirmed still `RUNNING` at the end of
  this session — untouched throughout.

## Open items carried forward (as of the second re-review; see "Final round" below for resolution)

1. ~~Seed 6 remains genuinely unresolved (still running)~~ — **RESOLVED
   this session**: the live attempt finished RIGHT_CENSORED and was
   mechanically backfilled; see "Final round" below.
2. A bulk sidecar-backfill pass for the (now 23) already-completed seeds
   (writing real `division_window_attempt.json` files next to their
   existing trace pairs, now that the identity-cross-check machinery to
   do so safely exists) remains designed but not executed in this
   branch, since it would write into shared worker worktrees / the
   shared consolidated root outside a narrowly-scoped code-fix branch.
3. `premature_seeds` does not itself distinguish COMPLETED from
   RIGHT_CENSORED within the premature bucket (seed 18 appears there
   alongside 17/34-49) — `completed_seeds`/`censored_seeds` (both scoped
   to the contiguous prefix only) provide the status breakdown instead.
   Not changed this round since no review item asked for it; flagged
   here in case a future round wants a `premature_completed_seeds`/
   `premature_censored_seeds` split for clarity.

## Final round: accounting refresh + seed 6 backfill (2026-09-09, this session)

* **Fresh dedicated-root audit** (Opus item 4 — "currently 24? Inspect
  fresh, not hardcoded"): re-surveyed
  `main-integrate/data/m1_sources/karr_native/dual_division_cohort_current`
  directly this session. Real count: **25 seed directories** — **23
  COMPLETED pairs** (seeds 0-5, 17, 34-49 — worker C finished 48/49 since
  the last round's 34-47 snapshot) plus **2 RIGHT_CENSORED** (seed 18,
  backfilled two rounds ago; seed 6, backfilled this session, see below).
  Neither "24" nor last round's "21+1" is current; both prior counts are
  superseded by this fresh survey. `docs/phase_f/l2_event/
  DIVISION_WINDOW_MIGRATION.md` rewritten again with the corrected
  breakdown and a fresh real no-arg CLI capture.
* **Seed 6 mechanically backfilled** (Opus item 5): `bulk-division-a/
  artifacts/seed6_100k_probe.status` (job
  `dual_a_s006_100k_probe_20260908_221616_27040`) finished this session —
  `FAILED seed=6 max_search_ticks=100000`, no `.mat` output files ever
  emitted. The preserved job log's exact extractor error text ("seed 6:
  division-completion signal did not fire within max_search_ticks=100000
  ticks") was parsed and independently re-verified via the SAME reviewed
  `scripts/l2_event/backfill_right_censored_from_log.py` tool used for
  seed 18 (never fabricated): the log's referenced DNADamage overlay
  (`bulk-division-a/tmp/wcm_source_overlay/src/.../DNADamage.m`)
  independently hashes to
  `86d8b3c2d2ed42df03e1b9ea14f06efc4b645a4e6aeaa3ef938b9ea41ad27e7e` —
  byte-identical to this worktree's current dec-005-resolved patched
  DNADamage source (the SAME hash seed 18's evidence chain verified,
  confirming both worker worktrees ran against the identical current-main
  source) — and the log's mnrnd provider line matches the current genuine
  provider exactly. Wrote
  `dual_division_cohort_current/per_process_traces_v2_event_s006/
  division_window_attempt.json` (`RIGHT_CENSORED`, `max_search_ticks=
  100000`, both hashes verified, no trace files present — mutual
  exclusivity intact). No code changes were needed for this step; the
  backfill tool already existed from the seed-18 round and required zero
  modification to handle seed 6.
* **Re-run verification (Opus item 7), this session**:
  * Targeted suite (the 9 files from section 6 above): **275 passed**
    (unchanged from last round — the horizon/root/identity code paths
    were not touched this session, only data + docs).
  * Broader `l2_event`/`division`/`cytokinesis`/`ftsz`/`backfill`-scoped
    sweep: **385 passed, 17 skipped, 1 failed** — the same pre-existing,
    unrelated `test_shared_evidence_index_is_known_stale_for_
    ribosome_assembly_after_this_promotion` failure reconfirmed present
    (RibosomeAssembly provenance hash staleness, nothing to do with
    division/censoring).
  * `test_l22_evidence_portability.py`: **7 passed** (Design-A tally
    unaffected by this session's work).
  * **Live dedicated-root audit, all 23 COMPLETED + both RIGHT_CENSORED
    records**: the real no-arg `division_cohort_selector.py` invocation
    (native WSL via `bin/oc-py`, ~9 minutes — validates every COMPLETED
    pair's full canary, not just the contiguous prefix) returned a clean
    report: `attempted_count=7` (seeds 0-5 COMPLETED + seed 6
    RIGHT_CENSORED), `completed_count=6`, `censored_seeds=[6]`,
    `contiguous_prefix_end=6`, `next_seed_to_attempt=7`,
    `premature_seeds=[17, 18, 34..49]` (18 entries), `gap_seeds=[7..16,
    19..33]` (25 entries), `invalid_censor_seeds=[]`,
    `rejected_root_traces=[]`, `source_hash_mismatches=[]`,
    `duplicate_trace_hashes=[]`, exit code 2 (`selection_satisfied=
    false`, 6 of 50 required). Exactly matches the expected shape:
    completed 0-5 then censored 6 form the contiguous prefix, next
    attempt is 7, and 17/34-49 (plus censored 18) remain premature —
    zero `CohortContractError`s across all 25 real seed directories.
  * No-arg CLI proof: confirmed above IS the no-arg invocation (no
    `--search-root` passed) — clean JSON report + exit code 2, no
    traceback, resolving `authoritative_karr_native_root()` to the real
    `main-integrate` sibling-worktree path with zero manual
    configuration.
  * `ruff check` on files touched this session (docs only — no Python
    changed): N/A; the last Python-touching round's `ruff check` (clean)
    still applies unchanged.
  * L2.2 board: unrelated to this branch's scope; `plan.md`'s narrative
    (updated by a separate, concurrent ChromCond-integration line of
    work) correctly reads "L2.2 remains integrity-OK at 18/2/2" (the
    RepInit-demotion-adjusted `evidence.audit_index()` FAIL/MISSING tally
    for the shared tracked index) — not the older "19/1/2"; this is a
    DIFFERENT metric from this document's own "19 PASS/1 FAIL/2
    MISSING_EVIDENCE" Design-A/`PROCESS_CATALOG.yaml`-scope tally in
    section 6 above (`n_in_scope=22`, unaffected by RepInit's demotion).
    Neither this branch's tests nor its docs claim a stale "19/1/2" as
    the current L2.2 audit-index board.
  * Current-main merge analysis: `main-integrate` is at `bcbdd3f` ("docs:
    record seed 6 right censoring") — a concurrent, independent line of
    work on main already narrates seed 6's genuine right-censoring and
    instructs backfilling it "from its preserved `dual_a_s006_100k_probe`
    log only through the reviewed source/provider-binding tool", which is
    exactly what this branch did. No conflict: this branch only wrote a
    new (previously-absent) data file into the shared, untracked
    `dual_division_cohort_current` directory (confirmed via `git status`
    in `main-integrate` — the whole directory is untracked, not
    gitignored, and was already untracked before this session); no git
    state in `main-integrate` was touched, and this branch's own commits
    remain unmerged/unpushed as required.
* Provenance to be logged (`opencell/provenance/llm_interactions.jsonl`)
  at the same commit as this STATUS update.
