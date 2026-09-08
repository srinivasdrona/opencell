# STATUS: Division-window cohort-censoring contract

Branch `fix/division-censor-contract`, worktree
`E:\opencell-worktrees\fix-division-censor-contract`, base `701b991`
(`docs: preregister division censoring direction`, main-integrate). Not
merged/pushed to main.

## What this delivers

A preregistered, machine-loadable seed-selection/censoring-horizon
contract for the Cytokinesis + FtsZPolymerization dual-tap division-window
cohort, closing the gap exposed by seeds 6 and 18 (no completion within
the pre-existing `max_search_ticks=50000`, no partial trace files, and no
mechanically-bindable evidence for their reported 100000-tick diagnostics).

1. **Spec (schema v3)** —
   `docs/phase_f/l2_event/division_window_spec.json` gains a top-level
   `selection_contract`: `candidate_seed_start=0`,
   `required_completed_windows=50`, `max_search_ticks=100000`,
   `selection_order="ascending_seed"`,
   `attempt_record_filename="division_window_attempt.json"`,
   `attempt_status_values=["COMPLETED","RIGHT_CENSORED"]`, plus a
   `known_censored_seeds_pending_backfill` note for seeds 6/18. Does
   **not** change any process's `m_ticks`/`tick_range_from_division`, and
   does **not** change `N_seeds`/`M_ticks` in `PROCESS_CATALOG.yaml`.
2. **Fail-closed accessors** — `scripts/l2_event/division_window_spec.py`
   (`selection_contract()`, `candidate_seed_start()`,
   `required_completed_windows()`, `selection_horizon_max_search_ticks()`,
   `selection_order()`, `attempt_record_filename()`,
   `attempt_status_values()`) and the new
   `scripts/matlab/division_window_selection_contract.m`, mirroring the
   existing per-process loaders' "no defaults, raise loudly" discipline
   exactly.
3. **Extractor** — `scripts/matlab/extract_dual_division_window.m` now:
   * distinguishes right-censoring (`ok=false` because the search
     exhausted the entire `max_search_ticks` horizon with no completion
     tick — the ONE genuine censoring outcome) from every other capture
     failure via a new `censored` output on `capture_dual_anchor_windows`;
   * raises a dedicated `extract_dual_division_window:right_censored`
     error identifier on right-censoring, distinct from
     `:capture_failed` for real defects;
   * writes an atomic `division_window_attempt.json` sidecar per seed —
     `RIGHT_CENSORED` (no trace files, written before any trace write
     path is reached) or `COMPLETED` (written only after both trace files
     are already safely promoted, carrying their sha256 hashes,
     provider/source identity, onset/completion ticks, and horizon);
   * enforces mutual exclusivity at write time
     (`attempt_record_completed_missing_hash` /
     `attempt_record_censored_has_hash`);
   * refuses to silently re-attempt a seed with an existing
     `RIGHT_CENSORED` record unless `opts.force_reattempt=true`.
   `extract_dual_division_window_seeds.m` now tracks censored seeds
   separately from `failed_seeds` — a right-censored outcome never
   triggers the driver's aggregate-throw.
4. **Cohort selector/auditor** — new
   `scripts/l2_event/division_cohort_selector.py`:
   * resolves each seed's outcome from a real `division_window_attempt.json`
     when present, or backfills a `COMPLETED` record (never a
     `RIGHT_CENSORED` one) from an already-validated trace pair via the
     existing `validate_dual_division_canary`;
   * raises `CohortContractError` on any mutual-exclusivity violation
     (censor + trace files, completed + missing files, unknown status,
     malformed JSON);
   * builds a contiguous-ascending-attempt ledger from
     `candidate_seed_start`, separating `gap_seeds` (never attempted) from
     `premature_seeds` (real completions that exist but occur after a
     gap, preserved but not yet selectable);
   * reclassifies a `RIGHT_CENSORED` record whose own horizon does not
     match the required `max_search_ticks=100000` as an invalid censor
     (`invalid_censor_seeds`), i.e. an unresolved gap, never a silently
     accepted short-horizon censor;
   * detects duplicate/aliased trace content and mixed
     `dnadamage_source_resolved_sha256` across the cohort;
   * selects the first `required_completed_windows` `COMPLETED` seeds in
     ascending order **only from the contiguous prefix**, and reports
     `attempted_count`/`completed_count`/`completion_fraction`
     descriptively (never gating);
   * returns `next_seed_to_attempt` — the exact next seed the ascending
     stream must attempt.
5. **Downstream consumers** — `scripts/l2_event/ftsz_pre_division_evidence.py`'s
   `audit_pre_division_evidence` gains an optional `selected_seeds`
   parameter (and `--use-cohort-selector` CLI flag) that restricts the
   missing/invalid/deficit computation to the Cytokinesis cohort
   selector's selected seed set instead of the legacy
   `range(REQUIRED_N_SEEDS)`; default behavior (no argument) is
   byte-for-byte unchanged, so every pre-existing caller/test is
   unaffected. `scripts/l2_event/prepare_cytokinesis_cohort.py`'s
   `build_missing_seed_specs`/`prepare_cohort` gain the equivalent
   optional `seed_universe` parameter with the same backward-compatible
   default.
6. **Docs** — `docs/phase_f/l2_event/event_registry.yaml`'s Cytokinesis
   entry gets an additive `UPDATE 2026-09-08` prose note explaining the
   contract; new
   `docs/phase_f/l2_event/DIVISION_WINDOW_MIGRATION.md` documents the
   exact current attempt-ledger state and every outstanding backfill step
   (see below).

## Deliberately NOT touched, and why

* **`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`** — an earlier draft
  of this change added an additive `event_sweep_blocked_on`/`notes` note
  to Cytokinesis's row (no `N_seeds`/`M_ticks` change). That edit was
  **reverted** after discovering it breaks
  `tests/scripts/test_l22_evidence_portability.py::test_audit_succeeds_from_a_temp_root_with_no_local_artifacts_tree`
  — the tracked `docs/phase_f/l2_event/evidence_index.json`'s integrity
  check hashes the *entire* catalog file, so ANY edit to it (even in an
  unrelated `EVENT_CLASS` row) invalidates the 19 PASS/1 FAIL/2
  MISSING_EVIDENCE Design-A tally this task requires stay green. Since
  the task's own instructions do not require a catalog edit ("as
  needed"), and the full contract semantics are already
  machine-loadable from `division_window_spec.json` +
  `event_registry.yaml`, the catalog was left byte-identical to base.
* **No MATLAB relaunch, no raw trace rewrite** — every check below was
  run read-only against existing files; no `.mat` file was created,
  deleted, or modified by this session.

## Test/lint results (this session, WSL canonical venv)

* `tests/scripts/test_division_window_spec.py` — 23 passed (16 preexisting
  + 7 new selection-contract accessor tests).
* `tests/scripts/test_division_window_selection_contract_static.py` (new)
  — 6 passed.
* `tests/scripts/test_extract_dual_division_window_static.py` — 33 passed
  (31 preexisting, 2 updated for the new `censored` output/error branch,
  9 new censoring/attempt-record assertions).
* `tests/scripts/test_division_cohort_selector.py` (new) — 21 passed,
  covering every inversion the task named: skipping a censored seed/gap,
  counting censor toward N, noncontiguous ledger, mixed horizons/source
  hashes, censor-with-trace-files, completed-without-both-files,
  selecting a later completion while an earlier seed is omitted, and a
  pre-50k-horizon completed trace remaining valid under H=100k.
* `tests/scripts/test_prepare_cytokinesis_cohort.py` — 5 passed (4
  preexisting + 1 new `seed_universe` test).
* `tests/scripts/test_ftsz_pre_division_evidence.py` — 26 passed
  (unchanged; new `selected_seeds` parameter is additive/optional).
* `tests/scripts/test_validate_dual_division_canary.py` — unchanged,
  passing (reused as-is by the new selector).
* Combined targeted run: **129 passed**.
* Full `l2_event`/`division`/`cytokinesis`/`ftsz`-scoped sweep: **379
  passed, 17 skipped**, 1 pre-existing unrelated failure
  (`test_shared_evidence_index_is_known_stale_for_ribosome_assembly_after_this_promotion`
  — confirmed, by reverting to base `701b991` and rerunning in isolation,
  to fail identically before any change on this branch; caused by an
  unrelated RibosomeAssembly registry-hash drift already present at base).
* `tests/scripts/test_l22_evidence_portability.py::test_audit_succeeds_from_a_temp_root_with_no_local_artifacts_tree`
  — **PASS**, tally `{'PASS': 19, 'FAIL': 1, 'MISSING_EVIDENCE': 2}`
  (the required 19/1/2 integrity, confirmed unaffected by this branch).
* `ruff check` on every new/modified Python file — clean.
* `python -c "import json; json.load(...)"` /
  `python -c "import yaml; yaml.safe_load(...)"` — both edited JSON/YAML
  docs parse cleanly.

## Honest operational backfill still needed (see DIVISION_WINDOW_MIGRATION.md for full detail)

Mechanical audit of the real on-disk state (surveyed this session across
`main-integrate`, `bulk-division-a/b/c`, `fix-dual-cyt-window`):

* **20 completed pairs exist** (seeds 0-5, 17, 34-46) but only **6 count
  toward the cohort today** (seeds 0-5) — the historical 3-parallel-worker
  extraction methodology assigned disjoint seed *ranges* per worker
  (0-2/17/34-46-ish), which is NOT the ascending-attempt-from-0 contract
  this branch preregisters. Seeds 17 and 34-46 are genuinely `COMPLETED`
  and are **preserved, never invalidated** — they become selectable the
  moment seeds 6-16 and 18-33 are attempted.
* **Seeds 6 and 18**: reported (plan.md, commit `701b991`) to have failed
  a 100000-tick diagnostic, but **no mechanically-verifiable artifact**
  (log, hash-bound attempt record) for either exists in any searched
  location. Per the task's explicit instruction, these are left as open
  gaps with an exact backfill command (`DIVISION_WINDOW_MIGRATION.md`
  §3-4) — **never fabricated** as `RIGHT_CENSORED` from the unbindable
  narrative alone.
* A live, fully-validated (`division_cohort_selector.py --search-root
  ...`) run against the real worktrees was attempted this session but did
  not complete within a reasonable window when accessed cross-filesystem
  (WSL `/mnt/e/...` DrvFS mount over an NTFS drive) — see
  `DIVISION_WINDOW_MIGRATION.md`'s operational note. The state reported
  above and in that document was independently established via direct
  filesystem survey (fast) and is structurally validated by this branch's
  own passing unit tests against an equivalent synthetic ledger shape.

## Ready for review

Clean, isolated diff (see `git status`/`git diff` on this branch against
`701b991`); no unrelated files touched; no raw trace bytes touched; no
catalog `N_seeds`/`M_ticks` changed. Recommended reviewer focus: the
MATLAB extractor's mutual-exclusivity/atomicity additions (static-tested
only, never executed against a real simulation this session) and the
cohort selector's contiguity/selection algorithm (fully unit-tested).
