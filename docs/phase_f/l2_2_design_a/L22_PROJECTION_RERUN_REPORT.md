# L2.2 Design-A Rerun After Projection-Helper Fix — Report

**Base commit:** `514a696` (`fix(l2.2): correct strand_1..strand_4 catalog
token off-by-one in chromosome projections`), worktree
`E:\opencell-worktrees\l22-projection-rerun`, branch
`agent/l22-projection-rerun`.
**Prior baseline this supersedes:** `docs/phase_f/l2_2_design_a/L22_DESIGN_A_BASELINE_REPORT.md`
(commit `e86afb7`, base `f1784d0`, worktree `l22-final-sweep`).
**Trigger:** `514a696` modified
`tests/vivarium/_l2_2_design_a_runner_helpers.py`
(`_chromosome_projection_component`, a shared runner-helper dependency
hashed into every process's `sweep_provenance.json`), so its sha256
changed for the whole tree. This stales **all 18** `design_a_per_tick`
sentinels simultaneously (`STALE_SWEEP_PROVENANCE`/`STALE_VS_TREE`, `helpers`
key), regardless of whether a given process's own biology/oc_module
changed. Verified directly (`sweep.py status` before any run showed all 18
rows: `sweep_provenance.json source hash for 'helpers' is stale/unknown vs
current tree`).
**Nothing under `*.py`/`*.yaml`/`*.toml` (biology, runner, metrics,
thresholds, catalog, evidence schema, tests, hooks) was modified in this
task.** Only gitignored raw oracle `.mat`/live-evidence data was copied
from the accepted `l22-final-sweep` source, existing tooling was invoked,
and generated tracked evidence/report/index/provenance files were written.

## 1. Raw-oracle + live-evidence population (proof)

Accepted source: `E:\opencell-worktrees\l22-final-sweep`
(commit `e86afb7`, itself the already-consolidated depth200/stale5/clean11
merge — the task's "already consolidated" source).

- **Generic 16-process × 50-seed v2 matrix**
  (`data/m1_sources/karr_native/per_process_traces_v2[_s001..s049]`):
  copied via `robocopy /E` per seed directory, then **fully hash-verified**
  file-by-file (SHA-256) against the source: **801/801 files match, 0
  mismatches, 0 missing, 0 extra** (16 processes × 50 seeds + 1 canonical
  no-suffix mirror = 801; includes the accepted 200-tick DNARepair /
  ProteinDecay / ReplicationInitiation traces already baked into this raw
  set). `V2_TRACE_MANIFEST.json` hash-matches the source byte-for-byte.
  This tree is gitignored; the copy is local-disk only.
- **Specialized ensembles** (`ensembles/{transcription,translation}`, 50
  seeds each): already git-tracked and current in this worktree (no copy
  needed); spot-verified byte-identical (SHA-256) against the source for
  both `transcription/seed_000` and `translation/seed_010`.
- **Live evidence root** (`artifacts/l2_2_gates/`, gitignored): copied
  wholesale from the accepted source (180 files, 28.95 MB, 0 mismatches)
  so that (a) all 18 processes' prior `sweep_provenance.json` sentinels are
  present for the staleness check to evaluate honestly, and (b)
  Replication's prior evidence is available to be left untouched rather
  than absent.
- **Pre-run staleness confirmation:** `sweep.py status` on the populated
  tree reported all 18 rows `IN_PROGRESS_OR_UNKNOWN` with reason
  `sweep_provenance.json source hash for 'helpers' is stale/unknown vs
  current tree` for every process — mechanically confirming the "all 18
  sentinels staled by the projection-helper hash change" premise before
  any rerun happened.
- `sweep.py plan --processes <17-list>` confirmed the exact per-process
  `seeds=50` and catalog `M_ticks` depth (20/50/100/200) for all 17
  requested processes before launch — matching `PROCESS_CATALOG.yaml`
  exactly, no overrides.

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
untouched on disk. It stays stale per the mechanical staleness check and
FAILs for an additional, real reason below (source-topology gap), pending
the separate `l22-replication-topology` Phase-B port (source-faithful
Okazaki-fragment topology) referenced in `514a696`'s commit message. This
is not an omission — it is the explicit scope boundary of this task.

Run window: 2026-07-31 18:11 IST → 22:22 IST (~4h11m wall,
`--max-workers 3`, bounded 3-lane `ThreadPoolExecutor`, existing
hardened locks/atomic-swap/staleness semantics, unmodified). Live-memory
sampled via `ps aux`/`free -h` at ~10-minute intervals throughout: per-job
RSS observed in the 0.4–1.0 GiB range (peak ~1.02 GiB, DNARepair), 3
concurrent jobs at a time; system-wide `used` memory never exceeded ~3
GiB out of 31 GiB available — well under any safety ceiling. No job was
killed or intervened on.

**Result: `RAN_EXIT_0: 17` / 17 requested — 0 kills, 0 non-zero exits.**

| Process | Ticks | Duration | Notes |
|---|---:|---:|---|
| ProteinProcessingI | 20 | 4m49s | |
| ProteinProcessingII | 20 | 4m52s | |
| Translation | 100 | 18m55s | |
| tRNAAminoacylation | 50 | 12m47s | |
| ProteinTranslocation | 100 | 22m24s | |
| RNAModification | 100 | 29m21s | |
| RNAProcessing | 100 | 30m59s | |
| ProteinFolding | 100 | 30m52s | |
| DNASupercoiling | 100 | 34m52s | |
| Transcription | 100 | 31m38s | |
| MacromolecularComplexation | 100 | 32m08s | |
| ProteinModification | 100 | 46m15s | |
| Metabolism | 20 | 58m52s | within expected 55–65m window |
| DNARepair | 200 | 59m40s | |
| RNADecay | 100 | 65m43s | |
| ReplicationInitiation | 200 | 74m56s | |
| ProteinDecay | 200 | 102m00s | within expected ~107m window |

Every job wrote a fresh `sweep_provenance.json` completion sentinel
binding `sidecar_hashes` for every fixed authority/sidecar file, plus the
**current** (post-`514a696`) runner/helper/catalog/`oc_module` source
hashes and `evaluator_schema_version` — this is what makes the new
sentinels valid against the fixed projection helper going forward.

## 3. Mechanically re-derived verdicts (`evidence_index.json`, NOT the
runner's self-reported `stored_verdict`)

`generator.py generate` → 22 rows (18 `design_a_per_tick` + 4
`event_class`), **aggregate_verdict = NON_GREEN**.

```
PASS: 14   FAIL: 4   MISSING_EVIDENCE: 4
```

`generator.py audit` → `integrity: OK`, identical tally reproduced from
the tracked index (mechanical re-derivation, not trust of the stored
field).

**PASS (14):** DNARepair, Metabolism, ProteinDecay, ProteinFolding,
ProteinModification, ProteinProcessingI, ProteinTranslocation, RNADecay,
RNAModification, RNAProcessing, ReplicationInitiation, Transcription,
Translation, tRNAAminoacylation.

**FAIL (4), with mechanical reasons:**
- **DNASupercoiling** — `PRIMARY_INSUFFICIENT_SAMPLES`: channel
  `chromosome` component `linkingNumbers.delta_nnz` has `n_oc=17,
  n_karr=24`, below `MIN_NONZERO_EVENTS=30` on at least one side. Honest
  insufficient-power FAIL, not a biology mismatch. **This is a
  regression relative to the `e86afb7` baseline, which PASSed
  DNASupercoiling cleanly** — see the net-effect discussion below for why
  (a since-landed false-green-closure fix, not anything from this
  task's strand-token trigger or this task's own actions).
- **MacromolecularComplexation**, **ProteinProcessingII** (2) —
  `SENTINEL_FAIL: PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE demotion
  claimed without valid machine-checked h12_evidence_ref (h12 artifact
  verdict != H12_CONFIRMED, got 'H12_OBSERVED_REGIME')` — the catalog's
  convergence-demotion claim is not backed by a `H12_CONFIRMED` artifact,
  so it is treated as non-green rather than trusted at face value.
- **Replication** — **stale, explicitly, not silently accepted as
  green or hidden as passing.** Reasons on the row (verbatim from the
  mechanical index):
  - `STALE_VS_TREE: input tests/vivarium/_l2_2_design_a_runner_helpers.py
    sha256 changed since evidence was generated (recorded=a60a3de8c440..,
    current=d0657a1e2a55..)`
  - `STALE_SWEEP_PROVENANCE: helpers source changed since evidence was
    generated (recorded=a60a3de8c440.., current=d0657a1e2a55..)`
  - `STALE_SWEEP_PROVENANCE: oc_module source changed since evidence was
    generated (recorded=e250d519ec35.., current=8becff08ec37..)`
  - Plus 4 real `PRIMARY_ACTIVITY_MISSING` findings (channel `chromosome`,
    `polymerizedRegions.delta_nnz`/`delta_value_sum_strand_{1,2,3}`): OC
    shows **zero** nonzero observations on all four components while Karr
    shows 420/3118/4155/4265 respectively — OC never exhibits this
    primary activity at all. This is the real, pre-existing
    source-topology gap (`514a696`'s commit message: "Phase B ports the
    source-faithful Okazaki fragment topology next") that the strand-token
    fix alone does not close — it corrects the *comparison*, not the
    underlying missing OC topology. **This row is intentionally left
    exactly as copied from `l22-final-sweep`; it was never rerun in this
    task and its FAIL/stale status is not a new regression from this
    session — it is the accurate current state, now correctly and legibly
    flagged as stale rather than silently trusted.**

**MISSING_EVIDENCE (4, event_class harness, by design — no event harness
exists yet):** Cytokinesis, DNADamage, FtsZPolymerization,
RibosomeAssembly.

**Net effect on the 17 reran processes, relative to the prior baseline's
per-process verdicts for the same set** (baseline = `e86afb7`,
`PASS(9)`/`FAIL(9)`/`MISSING(4)`, per `L22_DESIGN_A_BASELINE_REPORT.md`;
of the 9 baseline PASSes, 8 belong to the 17-process rerun set —
Replication was the 9th and was not rerun):

Verified by diffing `514a696`'s actual code change: the strand-token fix
touches **only** the `delta_value_sum_strand_<N>` branch of
`_chromosome_projection_component` (`git show 514a696 -- tests/vivarium/_l2_2_design_a_runner_helpers.py`).
That token is used **exclusively** by Replication's
`primary_projection` (`polymerizedRegions.delta_value_sum_strand_1..4`).
No other in-scope process's `primary_projection` references a
`strand_<N>` token (DNARepair uses `delta_nnz`/`repair_event_present`;
DNASupercoiling uses plain `linkingNumbers.delta_value_sum`/`delta_nnz`;
ReplicationInitiation's primary channel is `complexs`, not
`chromosome`). **So none of the 17 reran processes' own comparison
math changed because of the strand-token fix itself** — the fix's
direct effect lands only on Replication, the one process this task
deliberately does not rerun.

What actually moved the 17 reran rows relative to the `e86afb7` baseline
is the cumulative effect of the **26 commits** that landed between
`e86afb7` and `514a696` (`git log --oneline e86afb7..514a696`), most
of which are unrelated in mechanism to the strand-token fix but are
part of the same frozen current tree this rerun correctly picks up for
the first time since baseline:

- **7 flips FAIL→PASS:** RNADecay, RNAModification, RNAProcessing,
  Transcription (baseline `PRIMARY_CHANNEL_VACUOUS` case-sensitivity bug,
  fixed by `8f82d3a fix(l2.2): evaluator-only re-derivation - P0
  channel-alias + P2 zero-activity guard`); ProteinFolding,
  ProteinProcessingI, tRNAAminoacylation (baseline `SENTINEL_FAIL` for
  missing machine-checked `h12_evidence_ref`, now backed by a
  `H12_CONFIRMED` artifact from the H12 framework built out and
  hardened across `c5aa78c`..`227faa1`).
- **1 flip PASS→FAIL (regression relative to baseline, verified
  genuine, not caused by this task's code):** **DNASupercoiling** — baseline
  (`e86afb7`) PASSed with a clean row (no reasons); now FAILs
  `PRIMARY_INSUFFICIENT_SAMPLES` (`n_oc=17, n_karr=24`, below
  `MIN_NONZERO_EVENTS=30`). DNASupercoiling's `primary_projection`
  contains no `strand_<N>` token, so this is **not** an effect of the
  strand-token fix. It is consistent with `ece4658 fix(l2.2): Opus5
  follow-up - RESULT_SCHEMA_VERSION + close primary low-sample
  false-green`, which closed a false-green loophole for low sample
  counts between baseline and now — i.e. DNASupercoiling's baseline
  PASS was likely a false green under the old (now-closed) loophole,
  and this rerun is the first time the corrected, stricter check has
  been applied to it. This is flagged here as an honest finding, not
  swept under "remains FAIL."
- **2 unchanged FAIL:** MacromolecularComplexation, ProteinProcessingII
  — still read `H12_OBSERVED_REGIME` (not `H12_CONFIRMED`) under the
  same hardened H12 framework.
- **7 unchanged PASS:** DNARepair, Metabolism, ProteinDecay,
  ProteinModification, ProteinTranslocation, ReplicationInitiation,
  Translation.

Net PASS count for the 17-process set: 8 (baseline) → 14 (now) = +6,
matching 7 up − 1 down. None of this was tuned in this task — every
verdict is the mechanical evaluator output against the frozen,
unmodified-by-this-task thresholds/catalog/evaluator/H12 code already
present in the `514a696` tree; this task only supplied the raw
oracle/evidence inputs and invoked the existing tooling.

**Fresh-clone/bundle audit:** `generator.py bundle` mirrored all 18
processes' authority + sidecar files (144 files, 17 rerun + Replication
unchanged) into the tracked `evidence_bundle/`. `git status` on
`evidence_bundle/Replication/` shows **zero diff** — proof Replication's
tracked row was not touched. `generator.py audit` against the bundle
reproduces the identical `PASS:14 / FAIL:4 / MISSING_EVIDENCE:4` tally,
confirming the tracked bundle truthfully mirrors the live sweep output.

## 4. Full evidence test suite

`bin\oc-pytest tests/scripts/test_l22_evidence_{anticheat,
ast_completeness,channel_names_parity,generator,populate,portability,
sweep,verdict}.py -q`: **516 passed, 0 failed** (1437.97s / 23m58s). No
test files were modified for this task (frozen per instructions); all
pass cleanly against the fresh 17-process rerun evidence and the
untouched Replication row.

## 5. Bottom line

- 17/17 requested `design_a_per_tick` processes ran to completion under
  the frozen (post-projection-fix) source at their real catalog
  `N_seeds=50`/`M_ticks` depths (20/50/100/200 per bucket); 0 crashes, 0
  kills, 0 forced-invalid reruns. Memory stayed well within bounds
  throughout (observed peak ~1.0 GiB per job, ~3 GiB system-wide).
- Replication was **not** rerun; its prior evidence is preserved
  byte-for-byte and now surfaces as an honestly-stale, still-FAILing row
  with both the mechanical source-hash reason and the real
  source-topology reason spelled out — not silently carried forward as
  green, not hidden, not deleted.
- Mechanically re-derived (generator.py, not the runner's self-report):
  **14 PASS / 4 FAIL / 4 MISSING** (event_class, by design). **Aggregate
  remains NON_GREEN** — no threshold, catalog, or evaluator logic was
  touched to force green. Relative to the `e86afb7` baseline, the
  17-process rerun set moved from 8 PASS/9 FAIL to 14 PASS/3 FAIL (net
  +6): 7 processes flip FAIL→PASS (RNADecay/RNAModification/
  RNAProcessing/Transcription from an already-landed case-sensitivity
  fix; ProteinFolding/ProteinProcessingI/tRNAAminoacylation from the
  since-hardened H12 framework now backing their convergence claims with
  `H12_CONFIRMED` artifacts), and **1 process regresses PASS→FAIL**
  (DNASupercoiling, from an already-landed false-green-closure fix on
  low sample counts — verified **not** attributable to the strand-token
  fix itself, since DNASupercoiling's primary projection contains no
  `strand_<N>` token). The strand-token fix's own code change affects
  only Replication's specific `delta_value_sum_strand_<N>` computation
  — the one process this task does not rerun.
- Full `l22_evidence` test suite: 516/516 passed, 0 failures — no stale
  snapshot assertions needed updating this time.
- Raw MATs, per-job runner logs (`artifacts/l2_2_gates/_sweep_logs/*.log`),
  and this session's temp/lock state remain on disk (gitignored) in this
  worktree for Opus 5 review.
