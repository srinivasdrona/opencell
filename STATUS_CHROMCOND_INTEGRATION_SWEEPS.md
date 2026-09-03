# STATUS: ChromCond integration recertification (Sept-2, post-DNADamage-merge)

**Scope owned:** merge the accepted ChromCond candidate (`0196a81` on
`integrate/l21-chromcond-sept2`) with the independently-accepted DNADamage
closure now on `main` (`dfbf40f`, then `5468bc8`), then close the L2.2
recertification blocker for real. Branch is **not** pushed and **not**
merged to `main`.

**UPDATED RESULT (round 3, see §10 below): Opus 5 ACCEPTED the round-2
candidate but required five non-blocking follow-ups closed before merge.
All five closed with evidence (hidden-scan promotion + inversion proof,
corrected attribution, corrected docstring, tightened wiring anchors,
scorecard root-cause fix). See §10 for the full account; §§1-9 are
preserved as the round-1/round-2 record.**

**Round 2 summary: the round-1 "genuine blocker" was the wrong diagnosis of
the right symptom. The actual problem was that ChromCond's fix edited two
files SHARED by the whole L2.2 harness
(`tests/vivarium/l2_replay_common.py`, `opencell/util/matlab_rng.py`),
mechanically invalidating provenance for far more than the six named
consumers -- re-sweeping only six could never have restored integrity. Fix:
isolate ChromCond's two needed additions into new, narrowly-scoped,
ChromosomeCondensation-only modules; restore both shared files byte-for-byte
to main. `scripts/l22_evidence/generator.py audit` now reports
`integrity: OK` at the accepted `PASS=18/FAIL=2/MISSING_EVIDENCE=2` with
ZERO re-sweep and ZERO evidence/index edit. See §9 for the full account;
§§1-8 below are preserved as the round-1 record.**

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

---

## 9. ROUND 2 — the blocker removed via isolation, not waived (this session)

**Directive received:** "the cross-worktree blocker is not an acceptable
endpoint because changing shared `tests/vivarium/l2_replay_common.py`
mechanically invalidates 19 L2.2 rows, and re-sweeping only six cannot
restore integrity. Apply the smallest correct refactor instead." This
diagnosis was correct and sharper than round 1's framing — round 1 treated
"re-sweep the six" as the only path to green and, finding it blocked,
stopped there. The actual fix does not touch any evidence.

### 9.1 Merge

Merged `main`'s `5468bc8` (`chore: record ChromCond recertification
strategy`, a 29-line `plan.md`-only handoff commit — confirmed via `git show
--stat`) into `integrate/l21-chromcond-sept2`. Zero conflicts.

### 9.2 Root cause, confirmed mechanically (not assumed)

`git diff <merge-base> HEAD -- tests/vivarium/l2_replay_common.py` showed
exactly one addition: `apply_count_update`'s new `_apply_chromosome_update`
branch (from ChromCond commit `1faa115`, "Fix hidden chromosome replay
carryover"). Cross-checking `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`
confirmed the six processes named in round 1 (Replication,
ReplicationInitiation, DNARepair, DNASupercoiling, DNADamage, Cytokinesis)
are exactly the in-scope processes whose `output_channels` include
`chromosome` — the only rows whose *verdict* could behaviorally change.

But `scripts/l22_evidence/schema.py`'s `HARNESS_DEPENDENCY_FILES =
{"design_a_per_tick": {"l2_replay_common": L2_REPLAY_COMMON_MODULE}}`
registers that file's hash as a provenance dependency for **all 18**
`design_a_per_tick` rows (not just the six), plus explicitly for DNADamage
via `PROCESS_DEPENDENCY_FILES["DNADamage"]["l2_replay_common_module"]`. A
second, independent divergence was found the same way:
`opencell/util/matlab_rng.py` (ChromCond added an `mcg16807` generator mode
directly onto the shared `MatlabRandStream` class — 172 insertions on the
existing class, not a separate file) is registered as
`PROCESS_DEPENDENCY_FILES["ProteinTranslocation"]["util_matlab_rng_module"]`.
Verified this second one was genuinely ChromCond-attributable and not a
pre-existing main issue: `git show 5468bc8:opencell/util/matlab_rng.py`'s
SHA-256 (`5c2a982aa874...`) exactly matches ProteinTranslocation's tracked
`sweep_provenance.json["source_hashes"]["util_matlab_rng_module"]` — i.e.
main's own file was never stale; only this branch's edit made it so.

Net effect before the fix: regenerating the index fresh (never committed)
showed `FAIL: 19, MISSING_EVIDENCE: 2, PASS: 1` versus the accepted
`PASS: 18, FAIL: 2, MISSING_EVIDENCE: 2` — 17 rows more stale than the "six"
framing accounted for, entirely via `STALE_SWEEP_PROVENANCE`/`STALE_VS_TREE`
hash mismatches on the two shared files, none of it a real verdict change.

### 9.3 Fix: two ChromosomeCondensation-only extraction modules

**`tests/vivarium/_chromcond_replay_apply.py`** (new) —
`apply_chromcond_replay_update(state, update)`: calls the restored, plain
`apply_count_update` for the standard channels, then applies
`update["chromosome"]` onto `state["chromosome"]` with the exact semantics
ChromCond's hidden-replay proof needs (numeric leaves accumulate; sparse
non-numeric structures replace via `copy.deepcopy`, matching what the
now-removed branch did). Wired into:
- `tests/vivarium/test_karr_chromosome_condensation_l2_replay.py`'s
  `_apply_update` (unconditional — file is ChromosomeCondensation-only).
- `scripts/probe_l2_1_strict_rubric.py` and
  `tests/vivarium/test_l2_1_strict_rubric.py`'s shared 28-process loop,
  special-cased on `name == "ChromosomeCondensation"`; every other process
  keeps calling the plain, restored `apply_count_update` exactly as before.
- The three committed `tmp/` diagnostic probes that called
  `apply_count_update` directly: `chromcond_hidden_mismatch_probe.py`,
  `chromcond_hidden_mismatch_full_scan.py`,
  `chromcond_export_hidden_tick7_exact_surface.py` (all three confirmed
  ChromosomeCondensation-only via `name = "ChromosomeCondensation"` at their
  top).

**`opencell/util/chromcond_mcg_rand.py`** (new) — `ChromCondMcgRandStream`,
a fully self-contained MATLAB `RandStream('mcg16807')` shim, extracted
verbatim from the chromcond-modified `MatlabRandStream` (constructor,
`rand`/`randi`/`randperm`/`randsample`/`get_state`/`set_state`, and the
state encode/decode helpers matching MATLAB's non-obvious `State` property
representation). This follows an existing precedent already in the
codebase: `opencell/vivarium/karr_protein_decay_light.py` already has its
own private `_Mcg16807` class for its own (lower-fidelity, "replay-only")
needs — each mcg16807 consumer here gets its own dedicated shim rather than
sharing one. Before deleting the shared-class version, verified byte-exact
numerical equivalence between `ChromCondMcgRandStream(seed)` and the old
`MatlabRandStream(seed, generator="mcg16807")` across 4 seeds and every
method (`rand`, `randi`, `randperm`, `randsample` with/without replacement,
state round-trip) via a throwaway comparison script (deleted after passing).
Wired into:
- `opencell/vivarium/karr_chromosome_condensation.py`'s production RNG
  instantiation — a 2-line diff (`git diff 803089b --
  opencell/vivarium/karr_chromosome_condensation.py`): import swap plus
  `self._rng = ChromCondMcgRandStream(seed)`.
- The two committed `tmp/` probes that constructed
  `MatlabRandStream(seed, generator="mcg16807")` directly:
  `chromcond_prewarmup_replay_probe.py`, `chromcond_tick0_direct_store_probe.py`.
- A new dedicated test file `tests/util/test_chromcond_mcg_rand.py` — the
  mcg16807 golden-vector tests, split out of `tests/util/test_matlab_rng.py`
  (whose diff vs main was a pure +117/-0 addition, confirmed via
  `git diff --stat`, so the split cleanly restores that file byte-for-byte
  too, exactly like the shared production files).

**Restored byte-for-byte to main** (confirmed via `git diff FETCH_HEAD`
returning nothing for each): `tests/vivarium/l2_replay_common.py`,
`opencell/util/matlab_rng.py`, `tests/util/test_matlab_rng.py`.

### 9.4 Verification

| Check | Result |
|---|---|
| `test_hidden_chromosome_replay_applies_sparse_replacements` (the accepted 0/100 hidden scan proof) | **PASS** |
| ChromCond full suite (`test_karr_chromosome_condensation*.py`, `test_matlab_rng.py`, `test_chromcond_mcg_rand.py`) | **33 passed, 3 xpassed**, 0 skipped |
| `test_l2_1_strict_rubric.py` (all 28 processes) | **28 passed**; ChromosomeCondensation = GENUINE (also independently confirmed via direct `scripts/probe_l2_1_strict_rubric.py` scoreboard run: `karr_active=66/100, oc_fired=66, fire_rate=1.0, verdict=GENUINE`, matching the pinned value) |
| `test_l2_2_strict_rubric.py` + `tests/scripts/test_l22_evidence_generator.py` | **12 passed**, 0 failed (both previously-failing evidence-index-audit tests now pass) |
| `scripts/l22_evidence/generator.py audit` | **`integrity: OK`**, tally `PASS: 18, FAIL: 2, MISSING_EVIDENCE: 2` — exactly the accepted baseline, achieved with **zero re-sweep and zero edit** to `evidence_index.json`/`evidence_bundle/` |
| `tests/integration/test_l1b_verify_wiring.py` | **19 passed** |
| `tests/test_provenance_store.py` + `tests/provenance/test_dna_damage_provenance_chain.py` (isolated) | **9 + 4 passed**; the combined-invocation cross-file failure is the same pre-existing editable-install import-caching artifact documented in §5, unrelated to this fix |
| `ruff check` on all new/touched files | clean (5 pre-existing `ANN001`/`ANN202` findings in `tmp/chromcond_tick0_direct_store_probe.py` at an untouched inline function, confirmed present in the file before this session's edits via `git show 803089b:... \| ruff check -`) |
| `git diff FETCH_HEAD -- docs/phase_f/l2_2_design_a/` | **empty** — zero evidence bundle/index changes |
| `git diff FETCH_HEAD -- tests/vivarium/l2_replay_common.py opencell/util/matlab_rng.py` | **empty** — zero shared-harness-file changes |

### 9.5 Why isolation was possible here (no compromise needed)

Both of ChromCond's needed additions are consumed exclusively by
ChromosomeCondensation itself: the chromosome-merge branch only ever
matters when `update["chromosome"]` is present, which only six processes'
updates ever carry, and of those six only ChromosomeCondensation's own
tests/probes routed through the generic `apply_count_update` in a way that
needed the new semantics (the other five's committed L2.1/L2.2 evidence was
generated, and remains valid, against the plain generic accumulate). The
`mcg16807` generator is instantiated by exactly one production call site
(`karr_chromosome_condensation.py:472`) and referenced nowhere else in
production code. No call chain required the shared files to carry
ChromCond's changes; isolation fully preserves the hidden-replay proof.

### 9.6 Commits this session

- `5006a5f` — merge `dfbf40f` into `integrate/l21-chromcond-sept2` (round 1).
- `803089b` — provenance log + round-1 STATUS (round 1).
- (this commit) — merge `5468bc8`; isolation refactor (new
  `_chromcond_replay_apply.py`, `chromcond_mcg_rand.py`,
  `test_chromcond_mcg_rand.py`; restore `l2_replay_common.py`,
  `matlab_rng.py`, `test_matlab_rng.py` to main; wire the six consumer
  files); provenance log entry; this STATUS update.

Not pushed. Not merged to `main`.

### 9.7 Recommendation for the independent Opus 5 reviewer (superseding §8)

1. The L2.2 evidence board is fully re-certified at the accepted baseline
   with integrity OK — no re-sweep, no evidence edit, no waiver.
2. `tests/vivarium/l2_replay_common.py` and `opencell/util/matlab_rng.py`
   are byte-for-byte identical to `main`; this branch carries zero risk to
   any other process's accepted L2.2 provenance.
3. ChromosomeCondensation's own accepted fidelity results (0/100 hidden
   mismatch, L2.1 GENUINE, strict rubric) are unchanged and independently
   re-verified in this session.
4. This branch is ready for merge review on its own technical merits; no
   outstanding L2.2 blocker remains attributable to this integration.

---

## 10. ROUND 3 — Opus 5 ACCEPTED; closing its five non-blocking follow-ups (this session)

**Directive received:** Opus 5 accepted the round-2 candidate. Repository
policy requires clearing five follow-ups before merge: (1) promote the
hidden scan to a committed regression test proven sensitive to the fixed
bug; (2) correct misleading attribution in the strict-rubric files; (3)
correct `_chromcond_replay_apply.py`'s docstring; (4) tighten the wiring
YAML anchors; (5) investigate the pre-existing `karr_fidelity_scorecard.py`
ChromosomeCondensation FAIL. Merged `main`'s `5468bc8` first (plan.md-only
handoff commit, confirmed via `git diff --stat`; zero conflicts).

### 10.1 Promoted the hidden scan + inversion proof (item 1)

Replaced `test_karr_chromosome_condensation_l2_replay.py`'s old ticks-(0,1)-
only `test_hidden_chromosome_replay_applies_sparse_replacements` with two
full-100-tick tests built on a shared `_run_hidden_chromosome_replay_scan`
helper (rebuilds fresh oracle-fed state every tick, mirroring the promoted
`tmp/chromcond_hidden_mismatch_full_scan.py` methodology):

- `test_hidden_chromosome_replay_full_100tick_scan_zero_mismatches`:
  asserts the mismatched-tick list is empty. **PASS** (0/100).
- `test_hidden_chromosome_replay_full_100tick_scan_inverts_to_38_mismatches_when_spurious_draw_reintroduced`:
  a per-run `process._bind_smc_sites_literal` monkeypatch reinstates the
  exact extra `randsample(n_bound, n_bound, replace=False, ones)` draw
  commit `a52a8c1` removed, immediately before the real bind call (matching
  the original bug's call position). Asserts `mismatched_ticks[0] == 7` and
  `len(mismatched_ticks) == 38`. **PASS** (both exact values reproduced).

Both wrapped in a module-level `try/except FileNotFoundError` around
`resolve_trace_path` (computed once, `_CHROMCOND_TRACE_PATH`) and
`@pytest.mark.skipif(_CHROMCOND_TRACE_PATH is None, ...)` — the same
repo-standard pattern already used by e.g.
`tests/scripts/test_l2_event_adapters.py`'s `_RA_TRACE.exists()`, so CI/
fresh-clone environments (no sibling `E:/opencell` or `/mnt/e/opencell`
checkout to fall back to) skip cleanly instead of erroring.

Verified: `bin\oc-pytest tests/vivarium/test_karr_chromosome_condensation_l2_replay.py -v --collect-only`
confirms exactly 3 tests; full run: **3 passed** (160s).

### 10.2 Corrected misleading attribution (item 2)

Directly verified whether the name-gated chromosome applier actually
affects the strict rubric's verdict for ChromosomeCondensation, rather than
assuming: ran the rubric's exact per-tick classification loop twice, once
calling the plain shared `apply_count_update` and once calling
`apply_chromcond_replay_update`, via a throwaway script (deleted after).
Result: **byte-identical** `verdict`/`bit_identity_failures`/`karr_active`/
`oc_fired_on_karr_active`/`fire_rate` either way (both: GENUINE,
`bit_identity_failures=0`, `karr_active=66/100`, `fire_rate=1.0`). Root
cause: this rubric's bit-identity check only ever projects
`substrates`/`enzymes`/`boundEnzymes` (never `chromosome` itself), so how
`apply_count_update` merges a `chromosome` update key is provably inert
here.

Fix: removed the `if name == "ChromosomeCondensation": ... else: ...`
special-casing entirely from `scripts/probe_l2_1_strict_rubric.py` and
`tests/vivarium/test_l2_1_strict_rubric.py` — both now call the plain,
restored `apply_count_update` unconditionally for every process, including
ChromosomeCondensation, exactly as before ChromCond touched anything.
Removed the now-unused `_chromcond_replay_apply` import from both files.
Corrected the misleading `EXPECTED_VERDICTS` comment ("after the shared
replay applier started preserving hidden chromosome sparse replacements")
to attribute the real cause: commit `a52a8c1`'s production RNG fix (removal
of the spurious extra draw), with the direct-verification finding recorded
inline so a future reader doesn't have to re-derive it.

Verified: `test_l2_1_strict_rubric.py` full run **28/28 passed**;
`scripts/probe_l2_1_strict_rubric.py`'s scoreboard re-run shows the
identical 18 GENUINE / 6 UNINFORMATIVE / 4 COINCIDENTAL breakdown,
ChromosomeCondensation still `karr_active=66/100, oc_fired=66,
fire_rate=1.0, GENUINE`.

### 10.3 Corrected `_chromcond_replay_apply.py`'s docstring (item 3)

The prior docstring claimed the shared `apply_count_update` "treats every
nested dict recursively as an accumulate-in-place delta ... which silently
corrupts chromosome sparse replacements." False: `apply_count_update`'s
channel loop only ever iterates a fixed list (`substrates`/`protein`/`rna`/
`complex`/`boundEnzymes`/`enzymes`) and never reads or writes
`update["chromosome"]` at all — confirmed by re-reading the restored,
main-identical function body. It does not corrupt the chromosome structure;
it ignores it completely, leaving `state["chromosome"]` untouched by the
update. Rewrote the module and function docstrings to state this correctly:
the real problem is that a hidden-replay harness relying on the plain
function would compare Karr's real post-tick chromosome trace against OC's
still-pre-tick (never-updated) state — not exercising `next_update`'s
actual chromosome writeback at all, rather than seeing corrupted data. Also
updated the docstring's scope note to reflect item 2's finding (inert for
the strict rubric; the rubric files no longer import this module at all).

### 10.4 Tightened `ChromosomeCondensation.yaml` anchors (item 4)

`git diff FETCH_HEAD -- data/schemas/per_process_wiring/ChromosomeCondensation.yaml`
showed every `opencell/vivarium/karr_chromosome_condensation.py` anchor
recomputed to `676-791` (or similar wrong-by-15-to-22-lines spans) for
`next_update`, and `799-938` for `_sample_smc_binding_no_hints` (actual AST
span `815-861` — the recorded end drifted 77 lines past the real function
boundary, into the unrelated `_sample_smc_binding_fallback`). Six different
narrow-note sub-entries (ATP/water/ADP/Pi/H substrate deltas, "writes
ATP/H2O request values") had all been collapsed onto the same wrong
`next_update` span — the classic signature of a regeneration tool falling
back to "whole enclosing function" without verifying it even found the
right boundary.

Recomputed every anchor from the current source via Python's `ast` module
(`class KarrChromosomeCondensationProcess: 440-2021`, `__init__: 462-487`,
`_load_fixture: 489-536`, `_load_trace_anchor: 598-621`,
`ports_schema: 646-689`, `next_update: 691-813`,
`_sample_smc_binding_no_hints: 815-861`; `_build_available_intervals:
1748-1774` and `_allocated_or_state: 1916-1922` were already exactly
correct, confirmed unchanged). Attempted to give the 6 narrow-note
sub-entries their own exact single-line spans (e.g. `769-769` for the ATP
delta write); discovered `scripts/l1b_verify_wiring.py --strict-anchors`
requires the anchor's own symbol (`def next_update`) within ±5 lines of the
anchor span, which is structurally incompatible with a line-exact anchor
deep inside a 122-line function. Verified this is a **pre-existing,
repo-wide** limitation, not something introduced here or specific to
ChromosomeCondensation: `scripts/l1b_verify_wiring.py --strict-anchors`
(no `--process` filter) fails **25 of 28 processes**, including everything
whose `composite_wiring`/`composite_registration` anchors point into the
same giant `build_karr_chassis_v5` composite function. Used the correct,
*accurate* whole-function AST span for those 6 sub-entries instead (still a
real fix — the recorded span is now right, not merely wide) rather than
inventing single-line precision the tool's own model can't verify.

For `karr_composite.py` (confirmed byte-identical to `main` via
`git diff FETCH_HEAD`, so any content correction here is orthogonal to
ChromCond): discovered `main`'s own two anchors were themselves already
imprecise — `composite_wiring` (`2115-2120`) mostly pointed at the
*preceding* `karr_dna_supercoiling` block (the real
`"karr_chromosome_condensation": {` block is `2120-2125`); `composite_registration`
(`2312-2312`) pointed at `"karr_protein_processing_i": pp1_proc,`, not
ChromosomeCondensation at all (the real
`"karr_chromosome_condensation": condensation_proc,` line is `2320`).
Fixed both to the verified-correct `2120-2125` and `2320-2320`.

Verified: standard (non-strict, actually-enforced) L1b gate —
`bin\oc-py scripts/l1b_verify_wiring.py --process ChromosomeCondensation` —
**PASS**; repo-wide standard gate **27/28 PASS** (only pre-existing,
unrelated `DNADamage`); `tests/integration/test_l1b_verify_wiring.py`
**19/19 passed**. `--strict-anchors` for ChromosomeCondensation still fails
only on the two composite anchors, for the same reason as 24 other
processes — disclosed, not fixed (out of this integration's scope; would
require restructuring how the tool anchors sub-locations inside the single
giant composite-assembly function repo-wide).

### 10.5 Investigated the `karr_fidelity_scorecard.py` FAIL (item 5)

`docs/phase_e/karr_fidelity_scorecard.md` (as tracked before this session)
showed `ChromosomeCondensation | FAIL | ... | max_abs=3 | max_rel=1 |
enzymes`. Reproduced directly (not assumed): built a diagnostic script
loading `data/karr_fixtures/per_process_replay/ChromosomeCondensation.npz`
and running the process against it exactly as the scorecard does. Found
`fixture.inputs["enzymes"] == fixture.outputs["enzymes"]` (and
`boundEnzymes`, and `substrates`) **identically across all 100 recorded
ticks** — a pure mirror fixture, not real recorded Karr activity. The real,
non-mirror 100-tick trace for this process already exists and is used by
the L2.1/strict-rubric gates (66/100 ticks active, GENUINE) — this
scorecard's separate, older `per_process_replay/` fixture format was simply
never re-extracted for ChromosomeCondensation.

**Reproduced on `main`, not merely inferred from an unchanged-file diff:**
temporarily swapped `opencell/vivarium/karr_chromosome_condensation.py` for
`main`'s pre-ChromCond version (`git show FETCH_HEAD:... >
opencell/vivarium/karr_chromosome_condensation.py`, candidate version
backed up first) and re-ran the identical diagnostic. Result: **the exact
same `next_update` output** (`{'enzymes': {'MG_213_214_298_6MER': 3.0,
'MG_213_214_298_6MER_ADP': -3.0}, ...}`) — byte-for-byte identical to the
candidate's output. Restored the candidate file immediately after
(`git diff --stat` confirmed empty, i.e. exact restoration). This proves
the FAIL is 100% pre-existing and attributable to the stale mirror fixture,
not to anything ChromCond changed.

Fixed via the explicitly-sanctioned "route based on source-backed
applicability" path (not a waiver): added `"ChromosomeCondensation"` to
`scripts/karr_fidelity_scorecard.py`'s `DIAGNOSTIC_MIRROR_PROCESSES` with a
detailed, evidence-citing comment — the exact same treatment already given
to `Transcription`/`Translation`/`RNADecay`/`Replication`/
`ReplicationInitiation` for the identical "1-tick mirror, awaiting Track-B
MATLAB re-extract" reason. Added regression coverage in
`tests/integration/test_karr_fidelity_scorecard.py`:
`test_chromosome_condensation_is_honestly_skipped_as_mirror_fixture`
(pins the SKIP + mirror-reason classification) and
`test_chromosome_condensation_fixture_is_still_a_pure_mirror` (fails loudly,
by design, the day a real re-extraction lands and this fixture stops being
a mirror — a deliberate tripwire against the classification silently going
stale). Removed `"ChromosomeCondensation"` from the pre-existing
`test_karr_fidelity_scorecard_known_processes_not_fail`'s PASS/PARTIAL-
required list (that expectation was built on the wrong premise that this
fixture carried real data).

**Found but explicitly NOT touched (confirmed unrelated, out of scope):**
`FtsZPolymerization` shows a genuinely different, non-mirror fixture
mismatch (`enzymes`/`substrates` really do differ pre/post in its fixture)
and remains a separate, pre-existing FAIL in the same test — confirmed via
`git diff FETCH_HEAD` that its process file and fixture are byte-identical
to `main`. Left this assertion in the test file unmodified; the test
therefore still reports 1 failure (`FtsZPolymerization`), honestly
disclosed rather than silently worked around.

**Side effect found and reverted:** an early exploratory
`bin\oc-py scripts/karr_fidelity_scorecard.py --help` invocation (the
script has no `argparse`; any invocation runs the full scorecard with
`write_outputs=True` by default) regenerated and rewrote
`docs/phase_e/karr_fidelity_scorecard.md` and
`artifacts/karr_fidelity_scorecard.json` wholesale. Diffing the
regeneration revealed those two committed artifacts are themselves
significantly stale relative to the current tree across roughly 20
unrelated processes (real, pre-existing execution failures such as
`"karr_dna_repair missing declared enzyme counts"`,
`'numpy.ndarray' object has no attribute 'get'` for ProteinActivation,
etc.) — none of it caused by this session. Reverted both files via
`git checkout HEAD --` to avoid introducing an unrelated, out-of-scope
diff; the verifiable, regression-safe fix lives in the test file, not in
regenerating stale committed report artifacts.

Verified: `tests/integration/test_karr_fidelity_scorecard.py` **2 passed,
1 failed** (the disclosed, pre-existing, unrelated `FtsZPolymerization`
row) — confirmed via `git status --porcelain` that no scorecard doc/json
artifacts remain modified.

### 10.6 Full gate rerun (item 6)

| Check | Result |
|---|---|
| ChromCond + RNG + strict-rubric + evidence-generator suite (7 files) | **74 passed, 3 xpassed** |
| `scripts/l22_evidence/generator.py audit` | **integrity: OK**, `PASS=18/FAIL=2/MISSING_EVIDENCE=2` — unchanged, zero evidence/index edits |
| `tests/integration/test_l1b_verify_wiring.py` | **19 passed** |
| `tests/integration/test_karr_fidelity_scorecard.py` | **2 passed, 1 failed** (pre-existing, unrelated `FtsZPolymerization`, disclosed in §10.5) |
| `ruff check` on every file touched this round | clean, except `scripts/karr_fidelity_scorecard.py`'s 30 pre-existing findings (confirmed identical count/content in `main`'s own version via a throwaway diff — untouched, unrelated to this session's ~20-line addition) |
| `tests/test_provenance_store.py` + `tests/provenance/test_dna_damage_provenance_chain.py` (isolated) | **9 + 4 passed**; combined-invocation failure is the same pre-existing editable-install import-caching artifact documented in §5, reconfirmed here, unrelated to this round |
| `git status --porcelain` | only the 7 intentionally-touched files (plus the provenance log and this STATUS update) |

### 10.7 Commits this round

- `5006a5f`, `803089b` — round 1 (merge + provenance/STATUS).
- `1e4d413` — round 2 (isolation refactor).
- (this commit) — merge `16eb0be`; close all five Opus follow-ups (hidden-
  scan promotion + inversion test, corrected attribution, corrected
  docstring, tightened wiring anchors, scorecard mirror-fixture fix +
  regression tests); provenance log entry; this STATUS update.

Not pushed. Not merged to `main`.

### 10.8 Exact findings for re-review

1. **Hidden scan**: 0/100 (accepted) and 38/100 (inversion, first
   divergence tick 7) both now proven on the committed L2.1 test surface,
   not merely a `tmp/` script.
2. **Attribution**: GENUINE is caused by the production RNG fix
   (`a52a8c1`), NOT the chromosome applier; the applier is inert for the
   strict rubric and has been removed from both rubric files.
3. **Docstring**: corrected; the shared `apply_count_update` ignores
   `chromosome`, it does not corrupt it.
4. **Wiring anchors**: all `karr_chromosome_condensation.py` anchors now
   AST-accurate; both `karr_composite.py` anchors corrected past even
   `main`'s pre-existing imprecision. `--strict-anchors` for the two
   composite anchors remains unsatisfied — a disclosed, pre-existing,
   repo-wide (25/28) limitation, not a ChromosomeCondensation-specific gap
   and not introduced by this integration.
5. **Scorecard**: root cause proven (stale mirror fixture, reproduced
   identically on `main`), fixed via the sanctioned mirror-process
   reclassification, two regression tests added. `FtsZPolymerization`'s
   separate, pre-existing, unrelated FAIL in the same test is disclosed,
   not fixed.
6. **No verdict was hand-edited, no threshold weakened, no evidence
   fabricated anywhere in this round.**

