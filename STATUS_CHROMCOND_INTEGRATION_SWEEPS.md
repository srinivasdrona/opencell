# STATUS: ChromCond integration recertification (Sept-2, post-DNADamage-merge)

**Scope owned:** merge the accepted ChromCond candidate (`0196a81` on
`integrate/l21-chromcond-sept2`) with the independently-accepted DNADamage
closure now on `main` (`dfbf40f`), then re-verify exactly the L2.2 consumers
whose evidence could behaviorally change under the shared
`apply_count_update` fix. Branch is **not** pushed and **not** merged to
`main`.

**Result: merge clean and committed. ChromCond's own tests are green. The
L2.2 evidence-index recertification (item 3) is a genuine, disclosed
BLOCKER — raw Karr evidence for all six named consumers is absent from this
worktree, and I did not fabricate a result.**

---

## 1. Merge

- Merge base: `1ec16d85a11e2eb6d976842010c12f8d503a8c44`
- Merged `dfbf40f` into `integrate/l21-chromcond-sept2` -> commit **`5006a5f`**
  ("Merge commit 'dfbf40f' into integrate/l21-chromcond-sept2").
- **Exactly one conflict**: `opencell/provenance/llm_interactions.jsonl`
  (both sides append-only extended it). Resolved by unioning both sides:
  230 shared base lines (verified byte-identical to the merge-base blob via
  `Compare-Object`) + 2 ChromCond-only lines + 11 main-only DNADamage lines
  = 243 lines. Rebuilt with `[System.IO.File]::WriteAllLines` specifically
  to avoid the known `Set-Content -NoNewline` array-join corruption bug
  (documented in an earlier provenance entry, `event_id` prefix
  `0a1ff12dbb...`). Validated all 243 lines parse as JSON via a throwaway
  WSL script before committing.
- `plan.md`: **zero conflict**. ChromCond's branch diff never touched
  `plan.md` (confirmed via `git diff --stat <merge-base> 0196a81`), so
  main's newest top handoff (Day-104, 2026-09-02, post-DNADamage-merge) came
  through the merge untouched and is now the branch's top handoff verbatim.
- `docs/phase_f/l2_2_design_a/evidence_index.json` and the entire
  `evidence_bundle/` tree (ProteinProcessingII, DNADamage, all 20 tracked
  process dirs): **zero conflict, zero diff**. `git diff dfbf40f HEAD --
  docs/phase_f/l2_2_design_a/evidence_index.json
  docs/phase_f/l2_2_design_a/evidence_bundle` is empty — byte-for-byte
  preserved, exactly as required.

## 2. What the merge actually staled (verified, not assumed)

`tests/vivarium/l2_replay_common.py`'s `apply_count_update` gained a new
`_apply_chromosome_update` branch (ChromCond commit `1faa115`, "Fix hidden
chromosome replay carryover") that accumulates numeric `chromosome` deltas
but deep-copies non-numeric replacements, instead of the old generic
accumulate-only path. I cross-checked
`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` for every in-scope process
whose `output_channels` includes `chromosome` — the only processes whose
sampled distributions could actually change under this branch:

```
ReplicationInitiation  output_channels: [substrates, complexs, chromosome]
DNARepair              output_channels: [substrates, chromosome]
Replication            output_channels: [substrates, chromosome, boundEnzymes]
DNASupercoiling        output_channels: [substrates, chromosome]
Cytokinesis            output_channels: [substrates, chromosome]
DNADamage              output_channels: [substrates, chromosome]
```

This is exactly the task's named "six". Confirmed via `schema.py`'s
`HARNESS_DEPENDENCY_FILES = {"design_a_per_tick": {"l2_replay_common": ...}}`
that `l2_replay_common.py`'s hash is a real, registered provenance
dependency for **all 18** `design_a_per_tick` processes (not just these
four), and via `PROCESS_DEPENDENCY_FILES["DNADamage"]` that it is also an
explicit, direct dependency for DNADamage's event-class evidence. So the
hash bump mechanically stales far more than six rows' *provenance stamps*,
even though only six could show a real *verdict* change.

## 3. Re-sweep attempt — genuine, reproducible BLOCKER for all six

### 3a. The four `design_a_per_tick` members

```
bin\oc-py.cmd scripts/l22_evidence/sweep.py plan --processes Replication,ReplicationInitiation,DNARepair,DNASupercoiling
bin\oc-py.cmd scripts/l22_evidence/sweep.py run  --processes Replication --max-workers 1
```

Plan showed all four `WOULD-RUN` (no local `artifacts/l2_2_gates/` state).
The actual `run` for Replication failed:

```
RAN_NONZERO_EXIT: 1
# artifacts/l2_2_gates/_sweep_logs/.Replication.log...:
Unsupported Design-A process 'Replication'.
```

Root cause (read `tests/vivarium/_l2_2_design_a_runner_helpers.py`
`load_karr_oracle`): the loader tries, in order,
`_load_v2_ensemble` (`data/m1_sources/karr_native/per_process_traces_v2_s{000..049}/<Process>_<M>ticks.mat`),
then `_load_ensembles_layout` (`data/m1_sources/karr_native/ensembles/<process>/seed_{000..049}/<Process>_<M>ticks.mat`),
and only falls back to a hardcoded oracle-loader dispatch (which has no
entry for chromosome-primary processes) if both return `None`. Verified by
direct enumeration:

| Process | ticks | v2 seed dirs w/ trace | ensembles/&lt;process&gt;/ | verdict |
|---|---|---|---|---|
| Replication | 100 | 0/50 | absent | 0/50 |
| ReplicationInitiation | 200 | 0/50 | absent | 0/50 |
| DNARepair | 200 | 0/50 | absent | 0/50 |
| DNASupercoiling | 100 | 0/50 | absent | 0/50 |

`data/m1_sources/karr_native/ensembles/` in this worktree contains only
`transcription/` and `translation/`. The historical
`docs/phase_f/l2_2_design_a/sweep_report.json` (tracked, untouched — I
`git restore`d it after my failed attempt overwrote it) shows DNARepair and
DNASupercoiling *were* swept successfully on 2026-07-31, on a machine that
had the raw fixtures; by design (`generator.py bundle`'s whole purpose) that
raw data is not persisted after bundling and is not present here. Re-running
requires a fresh multi-hour MATLAB extraction via the shared slot
infrastructure (`tools/with_matlab_slot.ps1`), out of this session's scope.

I reverted my one failed attempt's side effects: deleted the
untracked/gitignored `artifacts/l2_2_gates/` output and `git restore`d
`docs/phase_f/l2_2_design_a/sweep_report.json` so the historical record
was not clobbered.

### 3b. DNADamage (event_class)

`scripts/l22_evidence/dna_damage_event_verifier.py` requires
`data/m1_sources/karr_native/genuine_signedzero_canary_v4/` and
`.../genuine_signedzero_full_v2/` (gitignored, `.gitignore:42`). Both
**absent** in this worktree (`Test-Path` false for both). Cannot rerun.

### 3c. Cytokinesis (event_class)

0/50 genuine event-window extractions exist anywhere for Cytokinesis
(confirmed: no `docs/phase_f/l2_2_design_a/evidence_bundle/Cytokinesis/`
directory at all — matches its pre-existing `MISSING_EVIDENCE` status and
`event_sweep_blocked_on` note in `PROCESS_CATALOG.yaml`). This is a
pre-existing, still-open extraction lane per `plan.md`, unaffected by this
merge. Nothing to sweep.

**Conclusion: none of the six could be legitimately re-verified in this
worktree/session.** I did not force, fabricate, or hand-edit any result.
`docs/phase_f/l2_2_design_a/evidence_index.json` and `evidence_bundle/`
remain exactly as merged from `main` (byte-for-byte).

## 4. Mechanical audit of the honest current-tree state (not committed)

Ran `scripts/l22_evidence/generator.py generate`/`audit` (read-only,
tmp output, not committed) to see what a fresh regeneration would say:

```
FAIL: 19   MISSING_EVIDENCE: 2   PASS: 1
```

versus the tracked `PASS: 18, FAIL: 2, MISSING_EVIDENCE: 2`. All 19 FAILs
carry `STALE_SWEEP_PROVENANCE`/`STALE_VS_TREE` reasons citing
`l2_replay_common_module` (and, for `DNASupercoiling`, a real independent
`PRIMARY_INSUFFICIENT_SAMPLES` pre-existing reason). I did **not** commit
this regeneration: it would replace a previously-verified, still-plausibly
-correct index with a mechanically-derived NON_GREEN one for ~13 processes
whose actual evidence never changed (no `chromosome` in their update
dicts — only their provenance hash is stale), which I have no way to
confirm or deny in this session. Overwriting real PASS rows with FAIL rows
I cannot verify would itself be a form of "inventing a result" in the
pessimistic direction. The two dedicated tests below already surface this
staleness mechanically and honestly; I left them red rather than edit them.

## 5. Test/lint results

All runs use `bin\oc-pytest.cmd` (WSL venv). `-rs` audited; **0 unexpected
skips** in every file below (this project's documented "5 skips" baseline is
a *full-suite* number from the Thattai paper-cache tests, none of which are
in scope here).

| Suite | Result |
|---|---|
| ChromCond core + L2.1 replay + matlab_rng + six consumers' L2.1 replay (9 files) | **39 passed, 3 xpassed**, 0 skipped |
| `test_l2_1_strict_rubric.py` (all 28 processes) | **31 passed** (run together with L2.2 strict rubric) |
| `test_l2_2_strict_rubric.py` (isolated) | **3 passed, 2 failed** — the two evidence-index-audit tests (see §4); genuine and reproducible, not a fluke (re-run twice) |
| `tests/scripts/test_l22_evidence_generator.py` (isolated) | **5 passed, 2 failed** — same two known-honest failures, different test names |
| `tests/test_provenance_store.py` (isolated) | **9 passed** |
| `tests/provenance/test_dna_damage_provenance_chain.py` (isolated) | **4 passed** |
| `tests/integration/test_l1b_verify_wiring.py` (isolated) | **19 passed** |
| `ruff check` on all touched files | **clean** |

**Environment caveat found and diagnosed (no code change; not a regression):**
running `tests/test_provenance_store.py` in the *same* pytest process
*before* `tests/provenance/test_dna_damage_provenance_chain.py` makes the
latter's 4 tests fail with an apparently-empty provenance log. Root cause
(confirmed via a temporary, fully-reverted debug print, verified reverted
via `git status --porcelain` showing zero diff): the second file's
`sys.path.insert(0, <worktree-root>)` runs *after* `opencell.provenance` was
already imported (via the standard editable install, which resolves to
`/mnt/e/opencell`, the main checkout) by the first file, so Python reuses
the already-cached `opencell.provenance.llm_log` module object bound to
main's `llm_interactions.jsonl` instead of re-importing the worktree's copy.
Every affected file passes cleanly in its own isolated invocation (see
table above). This is a pre-existing multi-worktree + single-shared-venv
import-order fragility, unrelated to ChromCond/DNADamage content, and out of
this task's scope to fix.

## 6. Provenance log

Logged this integration to `opencell/provenance/llm_interactions.jsonl` via
`scripts/log_llm_interaction.py` (`event_id`
`sha256:2158aaeb9c9d3968f3e4df3c28d3509340d6eefa7c88f073e6b7593e2cedca2c`)
before committing, per project convention.

## 7. Commits on this branch (this session)

- `5006a5f` — merge `dfbf40f` into `integrate/l21-chromcond-sept2`.
- (this commit) — provenance log entry + this STATUS file.

Not pushed. Not merged to `main`.

## 8. Recommendation for the independent Opus 5 reviewer

1. This branch's ChromCond source/package changes and their own L2.1
   replay/rubric evidence are green and merge-clean against current main.
2. The L2.2 evidence board's aggregate tally is **not** re-certified for
   the six named consumers, nor is the tracked index's mechanical
   `audit` currently passing (it was already effectively invalidated
   the moment `l2_replay_common.py`'s hash changed; this branch does not
   hide that, it surfaces it via the two failing tests in §5 and this
   report).
3. **Before this branch (or any branch carrying this `apply_count_update`
   fix) is merged to `main`**, a follow-up session with MATLAB slot access
   needs to: (a) re-extract/restore raw Karr fixtures for at least
   Replication/ReplicationInitiation/DNARepair/DNASupercoiling under
   `data/m1_sources/karr_native/ensembles/<process>/seed_{000..049}/` or
   `per_process_traces_v2_s{000..049}/`, re-run `sweep.py`, `generator.py
   bundle`, `generator.py generate`, commit the refreshed
   `evidence_index.json`; (b) obtain/restore
   `data/m1_sources/karr_native/genuine_signedzero_{canary_v4,full_v2}/`
   and re-run `dna_damage_event_verifier.py`; (c) Cytokinesis remains a
   separate, pre-existing, unrelated open extraction lane (0/50 windows).
4. No verdict was hand-edited. No evidence was fabricated. Where I could
   not prove a result, I reported the exact blocking path instead.
