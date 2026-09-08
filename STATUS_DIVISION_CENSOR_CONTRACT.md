# STATUS: Division-window cohort-censoring contract (second Opus re-review fixes)

Branch `fix/division-censor-contract`, worktree
`E:\opencell-worktrees\fix-division-censor-contract`, base `701b991`.
Not merged/pushed to main. This revises the previous candidate after
Opus's SECOND implementation re-review rejected three remaining
blockers; all six review items are addressed below.

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

## Open items carried forward

1. Seed 6 remains genuinely unresolved (still running) — no code or
   documentation change can close this; it requires the live process to
   finish.
2. A bulk sidecar-backfill pass for the 21 already-completed seeds
   (writing real `division_window_attempt.json` files next to their
   existing trace pairs, now that the identity-cross-check machinery to
   do so safely exists) remains designed but not executed in this
   branch, since it would write into shared worker worktrees / the
   shared consolidated root outside a narrowly-scoped code-fix branch.
3. `premature_seeds` does not itself distinguish COMPLETED from
   RIGHT_CENSORED within the premature bucket (seed 18 appears there
   alongside 17/34-47) — `completed_seeds`/`censored_seeds` (both scoped
   to the contiguous prefix only) provide the status breakdown instead.
   Not changed this round since no review item asked for it; flagged
   here in case a future round wants a `premature_completed_seeds`/
   `premature_censored_seeds` split for clarity.
