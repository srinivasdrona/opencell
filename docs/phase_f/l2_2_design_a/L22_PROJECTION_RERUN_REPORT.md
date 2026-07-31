# L2.2 Design-A Rerun After Projection-Helper Fix — Report

*Revised per Opus5 conditional-ACCEPT review of commit `1624523`. See
"Corrections from Opus5 review" at the end for exactly what changed and
why.*

**Baseline: the current tree at `514a696`** (`fix(l2.2): correct
strand_1..strand_4 catalog token off-by-one in chromosome projections`),
worktree `E:\opencell-worktrees\l22-projection-rerun`, branch
`agent/l22-projection-rerun`. This report does **not** compare against the
older `e86afb7` (`l22-final-sweep`) baseline report — that comparison is
irrelevant to what this task actually changed and is retracted from this
report (see corrections section). Every per-process verdict and numeric
figure below is compared against, and shown to be unchanged from, the tree
already committed at `514a696` itself.

**Trigger:** `514a696` modified
`tests/vivarium/_l2_2_design_a_runner_helpers.py`
(`_chromosome_projection_component`), a shared runner-helper dependency
whose sha256 is hashed into every process's `sweep_provenance.json`
completion sentinel. Diffing the commit
(`git show 514a696 -- tests/vivarium/_l2_2_design_a_runner_helpers.py`)
shows the fix touches **only** the `delta_value_sum_strand_<N>` branch —
used exclusively by Replication's `primary_projection`. No other in-scope
process's `primary_projection` references a `strand_<N>` token. So the
fix's own numeric effect lands only on Replication (excluded from this
rerun, see below); for every other process this is purely a sentinel
(provenance bookkeeping) invalidation, not a change to any actual
comparison math.

**Nothing under `*.py`/`*.yaml`/`*.toml` (biology, runner, metrics,
thresholds, catalog, evidence schema) was modified in this task.** One
test file gained one new regression test (see §5); no other test was
touched. Only gitignored raw oracle `.mat`/live-evidence data was copied
from the accepted `l22-final-sweep` source, existing tooling was invoked,
and generated tracked evidence/report/index/provenance/status files were
written.

## 1. Raw-oracle + live-evidence population (proof)

Accepted source: `E:\opencell-worktrees\l22-final-sweep`
(commit `e86afb7`, itself the already-consolidated depth200/stale5/clean11
merge — the task's "already consolidated" source).

- **Generic 16-process × 50-seed v2 matrix**
  (`data/m1_sources/karr_native/per_process_traces_v2[_s001..s049]`):
  copied via `robocopy /E` per seed directory, then **fully hash-verified**
  file-by-file (SHA-256) against the source: **801/801 files match, 0
  mismatches, 0 missing, 0 extra** (16 processes × 50 seeds + 1 canonical
  no-suffix mirror = 801). `V2_TRACE_MANIFEST.json` hash-matches the
  source byte-for-byte. This tree is gitignored; the copy is local-disk
  only.
- **Specialized ensembles** (`ensembles/{transcription,translation}`, 50
  seeds each): already git-tracked and current in this worktree (no copy
  needed); spot-verified byte-identical (SHA-256) against the source for
  both `transcription/seed_000` and `translation/seed_010`.
- **Live evidence root** (`artifacts/l2_2_gates/`, gitignored): copied
  wholesale from the accepted source (180 files, 28.95 MB, 0 mismatches)
  so that all 18 processes' prior evidence/sentinels would be present for
  the sweep tooling to evaluate honestly, and so Replication's prior
  evidence would be available to leave untouched rather than absent.

## 2. Forced rerun — 17/18 processes (Replication excluded)

```
scripts/l22_evidence/sweep.py run --force --max-workers 3 --processes \
  DNARepair,DNASupercoiling,MacromolecularComplexation,Metabolism,ProteinDecay,\
  ProteinFolding,ProteinModification,ProteinProcessingI,ProteinProcessingII,\
  ProteinTranslocation,RNADecay,RNAModification,RNAProcessing,\
  ReplicationInitiation,Transcription,Translation,tRNAAminoacylation
```

**Replication was deliberately excluded from `--processes`** — its prior
copied evidence (and `sweep_provenance.json` sentinel) is left completely
untouched on disk. It stays stale, pending its own separate rerun after
the `l22-replication-topology` Phase-B source-topology port referenced in
`514a696`'s commit message.

**Run window: 2026-07-31 18:11 IST → 22:13 IST** (per `sweep_report.json`'s
`generated_at`; corrected from an earlier, imprecise 22:22 IST figure),
`--max-workers 3`, bounded 3-lane `ThreadPoolExecutor`, existing hardened
locks/atomic-swap/staleness semantics, unmodified. **Result:
`RAN_EXIT_0: 17` / 17 requested — 0 kills, 0 non-zero exits.**

Memory was informally monitored during the run via ad hoc `ps aux`/
`free -h` polls (not a retained telemetry artifact/log file) — no OOM,
kill, or intervention was observed at any sampled point. **The specific
peak/range figures cited in an earlier draft of this report (e.g. "~1.0
GiB per job, ~3 GiB system-wide") were informal observations only, not
captured to disk, and are UNVERIFIED post-hoc** — they cannot be
independently re-derived now and should not be read as measured,
retained telemetry. The only durable, verifiable facts are: 17/17 jobs
exited 0, and no job was killed or restarted mid-run.

| Process | Ticks | Duration | Notes |
|---|---:|---:|---|
| ProteinProcessingI | 20 | 4m49s | |
| ProteinProcessingII | 20 | 4m52s | |
| tRNAAminoacylation | 50 | 12m47s | |
| Translation | 100 | 18m55s | |
| ProteinTranslocation | 100 | 22m24s | |
| RNAModification | 100 | 29m21s | |
| ProteinFolding | 100 | 30m52s | |
| RNAProcessing | 100 | 30m59s | |
| Transcription | 100 | 31m38s | |
| MacromolecularComplexation | 100 | 32m08s | |
| DNASupercoiling | 100 | 34m52s | |
| ProteinModification | 100 | 46m15s | |
| Metabolism | 20 | 58m52s | within expected 55–65m window |
| DNARepair | 200 | 59m40s | |
| RNADecay | 100 | 65m43s | |
| ReplicationInitiation | 200 | 74m56s | |
| ProteinDecay | 200 | 102m00s | within expected ~107m window |

## 3. Zero numeric blast radius (empirical proof, not assertion)

Diffing the tracked bundle between parent commit `514a696` and this rerun
(`git diff 514a696 1624523 -- docs/phase_f/l2_2_design_a/evidence_bundle/<Process>/latest/result.json`)
for all 17 reran processes:

- **16 of 17 processes: the diff is exactly one line — the `timestamp`
  field.** Every other field (all per-tick projections, W1 distances,
  `verdict`, `warnings`) is byte-identical to what was already tracked at
  `514a696` before this task touched anything.
- **Metabolism (1 of 17): the diff is telemetry only** — GLPK solver
  internals (`iterations`, `wall_time_s` per LP-solve category:
  `adv_pse`, `adv_pse_presolve`, `adv_std`, `std_pse`) vary run-to-run as
  expected for a non-deterministic external solver, plus the timestamp.
  `attempts`/`failures`/`successes`/`total_solves` and the `verdict` are
  identical.

This empirically proves the rerun changed **no** comparison outcome for
any of the 17 processes: rerunning under the fixed helper reproduced
bit-for-bit the same evidence that was already sitting in the tree at
`514a696`. This is expected and consistent with §2's dependency analysis
(the fix's code path is never exercised by these 17 processes' primary
projections) — it is not a coincidence.

## 4. Mechanically re-derived verdicts — unchanged, not a rerun-driven shift

`generator.py generate` (today, against the fresh rerun evidence) → 22
rows, **aggregate_verdict = NON_GREEN**:

```
PASS: 14   FAIL: 4   MISSING_EVIDENCE: 4
```

**This is not a new result.** The evidence_index.json already tracked in
the repo at `514a696` (generated hours before that commit, and never
regenerated by it) already recorded this exact tally, this exact
per-process FAIL set, and this exact set of reasons — because the frozen,
untouched test `tests/scripts/test_l22_evidence_generator.py::test_real_sweep_evidence_today_reflects_evaluator_v3_rederivation`
already hardcodes `{PASS: 14, FAIL: 4, MISSING_EVIDENCE: 4}` with FAIL
rows `{MacromolecularComplexation, ProteinProcessingII, Replication,
DNASupercoiling}`, and that test was already part of the tree at
`514a696`, passing before this task began. This task's rerun did not
change any verdict; it replaced stale sentinels with fresh, valid ones
carrying identical numbers (§3).

**PASS (14):** DNARepair, Metabolism, ProteinDecay, ProteinFolding,
ProteinModification, ProteinProcessingI, ProteinTranslocation, RNADecay,
RNAModification, RNAProcessing, ReplicationInitiation, Transcription,
Translation, tRNAAminoacylation.

**FAIL (4), with mechanical reasons — all pre-existing, none new:**
- **DNASupercoiling** — `PRIMARY_INSUFFICIENT_SAMPLES`: channel
  `chromosome` component `linkingNumbers.delta_nnz` has `n_oc=17,
  n_karr=24`, below `MIN_NONZERO_EVENTS=30`. **This is not a regression
  and not new.** It is the same, already-adjudicated canonical state
  documented in `docs/phase_f/l2_2_design_a/L22_DNAS_POWER_N100_REPORT.md`:
  a supplemental N=100 seed-extension diagnostic (seeds 50–99, hash-
  verified extraction) found `POWERED_AT_N100` (31/42 nonzero events at
  N=100, both ≥30), but Opus5's own prior ACCEPT/Option C review ruled
  this diagnostic **supplemental and non-gating** — the canonical
  DNASupercoiling row correctly remains FAIL/underpowered at the frozen
  N=50 evidence gate, with no catalog N change and no canonical rerun.
  This report does not reopen that decision.
- **MacromolecularComplexation**, **ProteinProcessingII** (2) —
  `SENTINEL_FAIL: PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE demotion
  claimed without valid machine-checked h12_evidence_ref (h12 artifact
  verdict != H12_CONFIRMED, got 'H12_OBSERVED_REGIME')`.
- **Replication** — excluded from this rerun; stale, pending its own
  topology-port rerun. See §6 for exactly what can and cannot be claimed
  about its row.

**MISSING_EVIDENCE (4, event_class harness, by design — no event harness
exists yet):** Cytokinesis, DNADamage, FtsZPolymerization,
RibosomeAssembly.

## 5. `sweep_status.json` correction + new regression test

**An earlier version of this evidence commit (`1624523`) committed a
`sweep_status.json` snapshot generated at 18:08 IST — 3 minutes BEFORE the
`sweep.py run` invocation that started at 18:11 IST.** That pre-run
snapshot showed all 18 processes as `IN_PROGRESS_OR_UNKNOWN`, even though
the same commit's `sweep_report.json` recorded 17 successful `RAN_EXIT_0`
jobs. This was caught by external review, not by this task's own process.

Fixed in this closeout: `sweep.py status` was re-run against the current
tree, producing a fresh, accurate snapshot:

```
DONE_VALID_EVIDENCE: 17
IN_PROGRESS_OR_UNKNOWN: 1   (Replication — correctly still stale, not rerun)
```

All 17 reran processes now show `DONE_VALID_EVIDENCE verdict=PASS`
(the runner's own self-reported `stored_verdict`, distinct from — and not
a substitute for — the mechanically re-derived `evidence_index.json`
verdict in §4; e.g. DNASupercoiling's runner self-reports `verdict=PASS`
while the mechanical evaluator FAILs it for insufficient samples — this
is expected and by design, not a discrepancy).

**Regression test added** (`tests/scripts/test_l22_evidence_sweep.py::test_committed_sweep_status_is_not_a_stale_pre_run_snapshot`):
cross-checks the tracked `sweep_report.json` against the tracked
`sweep_status.json` — every process the report records as
`RAN_EXIT_0`/`SKIPPED_VALID` must show `DONE_VALID_EVIDENCE` in the
status snapshot, and the status snapshot's `generated_at` must not
predate the report's. This test would have failed against the
pre-correction commit and passes now. No other test was touched; the
existing hardcoded-tally test in `test_l22_evidence_generator.py`
continues to pass unmodified (§4) and did not need fixing.

## 6. Headline result: the main audit was repaired from stale to valid

This is the actual, verifiable value this task delivered — re-derived
fresh, right now, against real artifacts (not asserted):

**At `514a696`, before this task's rerun**, a *fresh* `generator.py
generate` run against the tracked bundle **as it existed at that commit**
(extracted via `git archive 514a696`, run through the unmodified,
current-tree `generator.py` today) reports:

```
FAIL: 18   MISSING_EVIDENCE: 4   (PASS: 0)
```

Every one of the 18 `design_a_per_tick` rows fails with `STALE_VS_TREE`/
`STALE_SWEEP_PROVENANCE` (`helpers` hash mismatch: `recorded=a60a3de8c440..,
current=d0657a1e2a55..`); Replication additionally shows an `oc_module`
hash mismatch and its 4 `PRIMARY_ACTIVITY_MISSING` reasons. This is the
direct, reproduced confirmation of the "all 18 sentinels staled" premise
this task started from — not merely asserted this time, but regenerated
from the actual pre-rerun bundle content.

**After this task's rerun (17 processes) + this closeout's corrections**,
the same command against the current tracked bundle reports:

```
PASS: 14   FAIL: 4   MISSING_EVIDENCE: 4
```

— i.e. **audit went from FAIL:18 (all stale, unusable) to the correct,
already-expected FAIL:4/PASS:14 state (§4), with `generator.py audit`
against both the live evidence root and the tracked bundle reporting
`integrity: OK`.** The rerun's contribution is exactly this: converting
18 invalid (stale) sentinels into 17 valid ones with unchanged numbers
(§3), while Replication remains honestly excluded and stale.

## 7. Replication — excluded, stale; old counts are not current evidence

Replication's row was **not** rerun and its evidence directory is
byte-for-byte the copy taken from `l22-final-sweep` at the start of this
task (confirmed via `git status --short` showing zero diff on
`evidence_bundle/Replication/` across this task's commits). Its sentinel
carries explicit `STALE_VS_TREE`/`STALE_SWEEP_PROVENANCE` reasons for
**both** `helpers` (the strand-token fix) **and** `oc_module`
(`recorded=e250d519ec35.., current=8becff08ec37..`).

That `oc_module` mismatch is itself the reason the specific activity
counts recorded on this row (OC showing zero nonzero observations on
`polymerizedRegions.delta_nnz`/`delta_value_sum_strand_{1,2,3}` against
Karr's 420/3118/4155/4265) **must not be presented as describing
Replication's current behavior.** `git log --oneline e86afb7..514a696`
shows two Replication-specific fixes (`d4da839 fix(replication): align
isolated activity gate with live replisome state`, `29a5a83 fix
(replication): stop idle-gate from masking active Karr replisome in
per-process replay`) landed in the same window as the strand-token fix —
both touch Replication's own `oc_module`, which is exactly what the
sentinel's `oc_module` mismatch is flagging. The counts on this row
predate those fixes as well as the strand-token fix; they are historical
artifacts of when that evidence was generated, not a current
characterization of Replication's behavior under the tree as it stands
today. **The correct and complete statement is: Replication is excluded
from this task's scope, its evidence is stale, and it awaits its own
rerun after the separate topology port — no claim about its current
numeric behavior is made or should be inferred from this row.**

## 8. `evidence_index.json` regenerated against the portable tracked bundle

The version of `evidence_index.json` in the initial `1624523` commit was
generated with `evidence_root` resolving to the live, gitignored
`artifacts/l2_2_gates/` tree (present locally at generation time), so its
`evidence_root`/`evidence_dir` fields pointed at paths that do not exist
in a fresh clone. Regenerated explicitly against the tracked bundle:

```
generator.py generate --evidence-root docs/phase_f/l2_2_design_a/evidence_bundle
```

`evidence_root` now reads `docs/phase_f/l2_2_design_a/evidence_bundle`
and every row's `evidence_dir` is bundle-relative
(e.g. `docs/phase_f/l2_2_design_a/evidence_bundle/DNARepair/latest`).
**`content_hash` is unchanged** (`6c99381519abe65fc5cd22f39482a133ac5d8e5fb811f0acecb77b22ddd241f1`)
— `evidence_root`/`evidence_dir` are excluded from the content-hash
computation by design, confirming this regeneration changed only
presentation/portability, not data. `generator.py audit` against both
the live evidence root and the tracked bundle explicitly both report
`integrity: OK` with the identical `PASS:14/FAIL:4/MISSING_EVIDENCE:4`
tally.

## 9. Full evidence test suite

`bin\oc-pytest tests/scripts/test_l22_evidence_{anticheat,
ast_completeness,channel_names_parity,generator,populate,portability,
sweep,verdict}.py -q`: **517 passed, 0 failed** (516 from the original
rerun commit + 1 new regression test from §5). No pre-existing test was
modified; only one new test was added.

## 10. Bottom line

- 17/17 requested `design_a_per_tick` processes ran to completion at
  their real catalog `N_seeds=50`/`M_ticks` depths; 0 crashes, 0 kills.
  Run window 18:11 → 22:13 IST. Memory was watched informally during the
  run with no incident observed, but no telemetry was retained — specific
  peak/usage figures are not claimed as verified.
- **The rerun changed no verdict and no comparison numeric.** All 16
  non-Metabolism reran processes' `result.json` are byte-identical to
  what was already tracked at `514a696` except the `timestamp` field;
  Metabolism differs only in non-deterministic GLPK solver telemetry.
  Mechanically re-derived tally: **14 PASS / 4 FAIL / 4 MISSING**,
  identical to the tally already implied by the frozen, untouched test
  suite before this task began.
- **What the rerun actually repaired: audit validity.** A fresh
  `generator.py generate` against the pre-rerun bundle (as it existed at
  `514a696`) reports `FAIL: 18` (every sentinel stale). After this task's
  rerun, the same command against the current bundle reports the correct
  `PASS:14/FAIL:4/MISSING:4`, and `audit` reports `integrity: OK` against
  both the live evidence root and the tracked bundle. That is the real,
  verifiable deliverable of this task.
- DNASupercoiling's FAIL is the same, already-adjudicated
  `PRIMARY_INSUFFICIENT_SAMPLES` state covered by the accepted,
  supplemental (non-gating) N100 power diagnostic — not a new regression
  from this task.
- Replication remains excluded and stale pending its own topology-port
  rerun; its row's specific activity counts predate not only the
  strand-token fix but also two additional Replication-specific
  `oc_module` fixes in the same commit window, and must not be read as
  describing its current behavior.
- `sweep_status.json` corrected from an accidentally-committed pre-run
  snapshot to a fresh post-run snapshot (17 `DONE_VALID_EVIDENCE`, 1
  `IN_PROGRESS_OR_UNKNOWN`); a new regression test guards this class of
  mistake going forward.
- `evidence_index.json` regenerated with portable, bundle-relative
  `evidence_dir` paths; `content_hash` unchanged, proving this was a
  presentation-only fix.
- Full `l22_evidence` test suite: 517/517 passed (516 + 1 new).
- Aggregate remains **NON_GREEN**. No threshold, catalog, evaluator, or
  biology code was touched, and no claim of aggregate green is made.

## Corrections from Opus5 review (what changed from the original `1624523` report, and why)

1. **Removed the entire "net effect vs `e86afb7` baseline" narrative**,
   including the claimed "+6 net PASS" framing and the characterization
   of DNASupercoiling as "a regression relative to baseline." That
   comparison was against a different worktree's old snapshot and was not
   the relevant comparison for what this task did. The relevant, now
   directly-verified comparison is against `514a696` itself (§3, §4),
   which shows **zero verdict change** from the rerun.
2. **Corrected the run-window end time** from an imprecise "22:22 IST" to
   the authoritative `sweep_report.json` `generated_at` value, "22:13
   IST."
3. **Withdrew the specific memory peak/range figures** as unverified —
   they were informal, non-retained observations, not measured telemetry.
4. **Corrected Replication's framing**: its quoted activity counts are
   explicitly labeled as pre-rerun/pre-fix (and pre-two-other-fixes)
   artifacts, not current evidence, per §7.
5. **Added the actual headline finding** (§6): a fresh audit at `514a696`
   empirically FAILs all 18 sentinels; this task's rerun repairs that to
   the correct `PASS:14/FAIL:4/MISSING:4` state. This is a stronger, more
   precisely evidenced claim than the original report's framing.
6. **Fixed the previously-undetected stale `sweep_status.json`** (§5) and
   added a regression test against recurrence.
7. **Regenerated `evidence_index.json` against the portable tracked
   bundle** (§8) so its embedded paths are usable from a fresh clone.
