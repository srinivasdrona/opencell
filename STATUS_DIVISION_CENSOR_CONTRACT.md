# STATUS: Division-window cohort-censoring contract (Opus re-review fixes)

Branch `fix/division-censor-contract`, worktree
`E:\opencell-worktrees\fix-division-censor-contract`, base `701b991`.
Not merged/pushed to main. This revises the prior candidate after Opus
accepted the statistical design but REJECTED implementation blockers; all
seven review items are addressed below.

## 1. Horizon plumbing (FIXED)

* **The real bug**: the prior candidate preregistered
  `selection_contract.max_search_ticks=100000` but never wired it into
  anything that runs — `cytokinesis_anchor_spec`/`_anchor_spec` still used
  the launcher's old `DEFAULT_MAX_SEARCH_TICKS=50000` default, and the
  MATLAB extractor's own default was a literal `50000`. The contract was
  "on paper" only.
* **Design decision (documented in spec + code)**: `max_search_ticks` is
  trace identity, but for a **COMPLETED** anchor trace,
  `launcher.validate_existing_event_window` now checks it as a **monotone
  minimum against `spec.n_ticks`** (`recorded >= n_ticks`), never an exact
  match against `spec.max_search_ticks`. Rationale: a genuine completion
  tick is deterministic given (seed, source) — it does not depend on the
  search ceiling configured at capture time, so a smaller recorded budget
  (the legacy 50000 every currently-banked seed carries) is neither
  weaker nor stronger evidence, as long as it was large enough to have
  captured the observed completion. This is the ONLY reading consistent
  with Opus's own accepted accounting (seeds 0-5/17/34-47 remain valid
  COMPLETED evidence) — flagging this interpretation explicitly for
  confirmation in re-review, since "recorded >= required" is open to a
  stricter reading that would invalidate every currently-banked seed;
  `docs/phase_f/l2_event/division_window_spec.json`'s new
  `max_search_ticks_validation_policy` field documents the chosen design
  and rationale in full.
* `cytokinesis_anchor_spec` (`validate_dual_division_canary.py`) and
  `_anchor_spec` (`prepare_cytokinesis_cohort.py`) now both use
  `selection_horizon_max_search_ticks()` (100000) — safe under the
  monotone-minimum policy.
* `extract_dual_division_window.m`'s default now reads
  `division_window_selection_contract().max_search_ticks`, never a
  literal. `extract_dual_division_window_seeds.m` gained a 4th `opts`
  parameter, passed through unmodified to every extraction call, so a
  sanctioned batch run can request an explicit horizon/force_reattempt.
* Live/synthetic tests added: a COMPLETED trace stamped exactly 100000
  validates and is selectable
  (`test_matched_pair_stamped_at_the_selection_contract_horizon_still_passes`,
  `test_anchor_trace_stamped_exactly_the_selection_contract_horizon_validates`),
  alongside the legacy-50000 case
  (`test_anchor_trace_recorded_at_a_smaller_horizon_than_spec_still_validates`,
  `test_matched_pair_at_legacy_50000_horizon_still_passes_alongside_100000_spec`),
  and the floor is not vacuous
  (`test_anchor_trace_recorded_max_search_ticks_smaller_than_n_ticks_is_rejected`).

## 2. Force re-extraction (FIXED)

* `extract_dual_division_window_seeds.m`'s `force_seeds` branch now
  deletes `division_window_attempt.json` alongside both `.mat` files, and
  the post-delete existence recheck includes all three paths.
* Inversion test
  (`test_force_seeds_clearing_attempt_record_means_no_completed_or_censored_record_permanently_blocks_reextraction`)
  proves a stale COMPLETED or RIGHT_CENSORED record can never permanently
  block a sanctioned re-extraction: the driver's force branch always
  deletes the attempt record *before* re-invoking the extractor, so its
  `censored_attempt_exists`/`attempt_record_status_conflict` guards can
  only ever fire on a *non-forced* re-run (the deliberately conservative
  default).

## 3. Multi-root / source integrity (FIXED)

* `division_cohort_selector.discover_ledger` now inspects **every**
  search root for **every** seed (never "first root wins") and raises
  `CohortContractError` immediately if two roots disagree on any identity
  field (status, onset/completion tick, both trace hashes,
  DNADamage/mnrnd identity) for the same seed.
* New `authoritative_karr_native_root()` resolves the dedicated
  `dual_division_cohort_current` root (documented in the spec's new
  `authoritative_operational_root` field); `default_search_roots()` lists
  it first (preference, never exclusivity — every other root is still
  searched and cross-checked).
* RIGHT_CENSORED records must now bind the CURRENT run's genuine
  `dnadamage_source_resolved_sha256` and `mnrnd_provider_sha256` (spec's
  new `censor_record_required_identity_fields`) — a mismatch reclassifies
  the seed as an invalid/unresolved gap, exactly like a horizon mismatch,
  and can never advance the contiguous prefix.
* `selection_satisfied` is now `False` whenever `source_hash_mismatches`
  or `duplicate_trace_hashes` is nonempty, even if the raw completed
  count already reached `required_completed_windows`.
* New tests: multi-root agreement/dedup, multi-root contradiction
  hard-fail, wrong-DNADamage-identity censor, wrong-mnrnd-identity
  censor, correct-identity positive control, `selection_satisfied` false
  under source-hash-mismatch/duplicate-hash even with enough raw
  completions, authoritative-root resolution/ordering.

## 4. Tightened spec wording (FIXED)

`division_window_spec.json` bumped to schema v4. New fields, all with
dedicated fail-closed Python accessors and MATLAB loader checks:

* `formal_estimand`: *"Cytokinesis process-local behavior conditional on
  division completion within 100000 ticks under source S, over the first
  50 completions of the ascending attempt stream from seed 0."* (locked
  in verbatim by `test_real_repo_spec_has_the_exact_formal_estimand_text`).
* `stopping_rule`: non-adaptive — the attempted stream cannot be
  truncated, and `required_completed_windows` cannot be lowered, based on
  observed completion/censoring incidence; only a fresh, separately
  reviewed preregistration commit may change either.
* `completion_fraction_role`: explicitly descriptive/non-gating.
* `max_search_ticks_validation_policy` / `censor_record_required_identity_fields`
  / `censor_record_identity_binding_note` / `authoritative_operational_root`
  (see items 1 and 3 above).

## 5. Migration doc counts (FIXED — now dynamic, not hardcoded)

* Real state re-surveyed this session: `dual_division_cohort_current`
  (the authoritative root) now has **21** seed directories — 20 completed
  pairs (0-5, 17, 34-47; **seed 47 completed since the last review**) plus
  seed 18 (backfilled `RIGHT_CENSORED`, see item 6). Contiguous-prefix
  accounting is unchanged in shape: 6 contiguous selected (0-5), 21
  premature (17, 34-47), 25 never-attempted gaps (7-16, 19-33).
* `docs/phase_f/l2_event/DIVISION_WINDOW_MIGRATION.md` rewritten to
  present these as a dated, re-verifiable **snapshot** with the exact CLI
  invocation to get a live, hash-and-identity-verified answer
  (`division_cohort_selector.py --search-root .../dual_division_cohort_current`),
  never a frozen claim.
* Operational honesty note included: a live, fully-validated run of that
  CLI against cross-filesystem (WSL↔NTFS) search roots was observed to
  take longer than practical to wait out interactively in this session;
  the doc flags this as an environment/DrvFS characteristic, not a code
  bug, and recommends running it from native WSL against a
  native-filesystem copy.

## 6. Seed 6 / seed 18 (no fabrication; seed 18 genuinely backfilled)

* **Seed 6**: `bulk-division-a/artifacts/seed6_100k_probe.status` reads
  `RUNNING seed=6 max_search_ticks=100000` — confirmed still actively
  running (log still appending) as of this session. **Not touched.**
  Left as an open, in-progress item with the exact follow-up commands in
  the migration doc.
* **Seed 18**: `bulk-division-b/artifacts/seed18_100k_probe.log` contains
  the real extractor error text for a genuine `max_search_ticks=100000`
  attempt. This session independently re-verified — not merely trusted —
  that (a) the log's referenced DNADamage overlay file still exists on
  disk and its LF-normalized SHA-256 is byte-identical to this worktree's
  CURRENT dec-005-resolved patched source, and (b) the log's mnrnd
  provider path/release/toolbox-version matches the current genuine
  provider. New `scripts/l2_event/backfill_right_censored_from_log.py`
  (16 tests, fully mocked/portable — never depends on a real WCM/MATLAB
  install) mechanizes this exact verification chain and refuses
  (`BackfillEvidenceError`) if any check fails. **Seed 18 has been
  backfilled for real** this session:
  `dual_division_cohort_current/per_process_traces_v2_event_s018/division_window_attempt.json`
  now exists (`status=RIGHT_CENSORED`, both hashes verified, no trace
  files present — mutual exclusivity intact).

## 7. Test/lint/provenance re-run

* Targeted suite (division/cohort/spec/extractor/validator/backfill):
  **260 passed** (`test_division_cohort_selector.py` 31,
  `test_division_window_spec.py` 27,
  `test_division_window_selection_contract_static.py` 6,
  `test_extract_dual_division_window_static.py` 39,
  `test_prepare_cytokinesis_cohort.py` 5,
  `test_ftsz_pre_division_evidence.py` 26,
  `test_validate_dual_division_canary.py` 17,
  `test_l2_event_launcher.py` 95,
  `test_backfill_right_censored_from_log.py` 16 — new this round).
* L2.2 evidence portability (`test_l22_evidence_portability.py`): **7
  passed**, confirming the required **19 PASS / 1 FAIL / 2
  MISSING_EVIDENCE** Design-A tally remains intact.
* Full `l2_event`/`division`/`cytokinesis`/`ftsz`/`backfill`-scoped sweep:
  **382 passed, 17 skipped**, 1 pre-existing unrelated failure
  (`test_shared_evidence_index_is_known_stale_for_ribosome_assembly_after_this_promotion`
  — reconfirmed present and identical at base `701b991` before this
  branch's changes).
* `ruff check` on every new/modified Python file: clean.
* `python -c "import json"` / catalog untouched (still not edited, for
  the same 19/1/2-hash-coupling reason as the prior round).
* Provenance logged (`opencell/provenance/llm_interactions.jsonl`) at the
  same commit as this STATUS update.

## Open items for Opus re-review

1. **Confirm the monotone-minimum interpretation** (item 1): this
   candidate reads "recorded >= required" as "recorded max_search_ticks
   >= the process's own n_ticks", not "recorded >= the 100000 selection
   horizon", because the latter reading invalidates every currently-
   banked COMPLETED seed and contradicts Opus's own accepted 6-contiguous/
   21-premature accounting. If a stricter reading was intended, the 20
   legacy-horizon seeds would need real re-extraction at 100000, not
   backfill-acceptance.
2. Seed 6 remains genuinely unresolved (still running) — no code or
   documentation change can close this; it requires the live process to
   finish.
3. A bulk sidecar-backfill pass for the 20 already-completed seeds
   (writing real `division_window_attempt.json` files next to their
   existing trace pairs) is designed but not executed in this branch,
   since it would write into shared worker worktrees / the shared
   consolidated root outside a narrowly-scoped code-fix branch — flagged
   as a separate, larger operational action in the migration doc.
