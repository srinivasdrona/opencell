# L2.2 Design-A Frozen-Source Rebaseline — Final Report

**Base commit:** `f1784d0` (local `main`), worktree
`E:\opencell-worktrees\l22-final-sweep`, branch `agent/l22-final-sweep`.
**Run window:** 2026-07-29 22:47 UTC → 2026-07-30 03:08 UTC (~4h21m wall,
`--max-workers 3`, all 18 jobs `RAN_EXIT_0`).
**Nothing under `*.py`/`*.yaml`/`*.toml` (biology, runner, metrics,
thresholds, catalog, evidence schema, tests, hooks) was modified.** Only
gitignored raw oracle `.mat` data was copied, existing tooling was invoked,
and generated tracked evidence/report/index/provenance files were written.

## 1. Raw oracle population (proof)

Source: `E:\opencell-worktrees\l22-evidence-gate` (consolidated 16 generic
processes in `per_process_traces_v2[_s001..s049]` v2 layout + specialized
`ensembles/{transcription,translation}`, including the accepted 200-tick
DNARepair/ProteinDecay/ReplicationInitiation traces).

- `scripts/l22_evidence/populate.py --source evidence_gate=<path>` (dry run):
  all 18 `design_a_per_tick` processes reported `RESOLVED` (16 at `v2`
  layout, Transcription/Translation at `ensembles` layout), no
  `SPLIT_CONFLICT`/`INSUFFICIENT_DATA`/`MANIFEST_MISMATCH`.
- `--apply`: copied exactly **800 files** (16 processes × 50 seeds) from
  `evidence_gate`; Transcription/Translation's `ensembles/` seed files were
  already fully present in the `current` tree (0 files copied for them —
  "handled by population/current source" per task framing).
- `--check-destination`, scoped to the 16 generic (non-ensemble) processes:
  **exact 16×50 matrix, no missing files, no unexpected extras** (one
  pre-existing, explicitly-named, ignored stray
  `per_process_traces_v2_s001/Translation_100ticks.mat` — a known artifact
  documented in `populate.py`'s `KNOWN_PRE_EXISTING_V2_EXTRAS`, harmless
  since `load_karr_oracle` always prefers Translation's 50-seed `ensembles/`
  layout by seed count).
- No `per_process_traces_v2_s000/` directory exists (verified directly;
  confirms the no-competing-`_s000` policy).
- Raw `.mat` data under `data/m1_sources/karr_native/` is gitignored
  (`.gitignore:38`); only `oracle_population_manifest.json` (sha256 per
  copied file, per-source git SHA) is tracked and committed.
- **Preflight — all 18 `load_karr_oracle(process)` calls, before the
  sweep:** `canonical_seed_count == 50` and `warnings == []` for every one
  of the 18 `design_a_per_tick` processes (DNARepair, DNASupercoiling,
  MacromolecularComplexation, Metabolism, ProteinDecay, ProteinFolding,
  ProteinModification, ProteinProcessingI, ProteinProcessingII,
  ProteinTranslocation, RNADecay, RNAModification, RNAProcessing,
  Replication, ReplicationInitiation, Transcription, Translation,
  tRNAAminoacylation). Catalog M_ticks matched `sweep.py plan`'s per-process
  depth (20/50/100/200 per bucket) confirmed before launch.

## 2. Sweep execution

`scripts/l22_evidence/sweep.py run --max-workers 3` (bounded 3-lane
`ThreadPoolExecutor`, existing hardened locks/atomic-swap/staleness
semantics, unmodified). WSL: 16 vCPU / 31GiB RAM available; observed
combined RSS across all concurrent job processes stayed in the
0.6–2.6 GiB range throughout the entire run (far under the 24 GiB safety
ceiling); no job was killed or intervened on.

| Process | Ticks | Duration | Notes |
|---|---:|---:|---|
| ProteinProcessingI | 20 | 5m16s | |
| ProteinProcessingII | 20 | 5m48s | |
| ProteinTranslocation | 100 | 22m30s | |
| tRNAAminoacylation | 50 | 13m34s | |
| Translation | 100 | 19m06s | |
| MacromolecularComplexation | 100 | 33m17s | |
| DNASupercoiling | 100 | 39m06s | |
| ProteinFolding | 100 | 31m30s | |
| Transcription | 100 | 30m34s | |
| RNAModification | 100 | 28m34s | |
| Replication | 100 | 33m41s | |
| RNAProcessing | 100 | 32m00s | |
| Metabolism | 20 | 58m16s | within expected 55–65m window |
| ProteinModification | 100 | 47m36s | |
| DNARepair | 200 | 63m21s | |
| RNADecay | 100 | 66m07s | |
| ReplicationInitiation | 200 | 81m32s | |
| ProteinDecay | 200 | 107m27s | memory stayed bounded (~0.6GiB), no leak |

**Sentinel/hash discipline:** every job wrote a `sweep_provenance.json`
completion sentinel binding `sidecar_hashes` for every fixed authority/
sidecar file, the current runner/helper/catalog/`oc_module` source hashes,
and `evaluator_schema_version`; `run_sweep` result: `RAN_EXIT_0: 18` (see
`docs/phase_f/l2_2_design_a/sweep_report.json`), 0 failures, 0 forced
overrides, 0 resumed-as-`DONE_VALID` skips (every job was a genuine cold
rerun against the freshly populated oracle).

## 3. Mechanically re-derived verdicts (evidence_index.json, NOT the
runner's self-reported `stored_verdict`)

`generator.py generate --verify-input-files` → 22 rows (18
`design_a_per_tick` + 4 `event_class`), **aggregate_verdict = NON_GREEN**.

```
FAIL: 9   MISSING_EVIDENCE: 4   PASS: 9
```

**PASS (9):** DNARepair, DNASupercoiling, Metabolism, ProteinDecay,
ProteinModification, ProteinTranslocation, Replication,
ReplicationInitiation, Translation (Translation carries a non-blocking
`SEED_ALIGNMENT_DIAGNOSTIC` warning — shift=+47 on channel=monomers,
observed_w1=0.006671 vs shifted_w1=0.006165 — informational only, does not
change verdict).

**FAIL (9), with mechanical reasons:**
- `MacromolecularComplexation`, `ProteinFolding`, `ProteinProcessingI`,
  `ProteinProcessingII`, `tRNAAminoacylation` (5): `SENTINEL_FAIL:
  PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE demotion claimed without a
  machine-checked h12_evidence_ref` — OC matches the Karr oracle exactly on
  its primary channel, but the catalog's `closed_form_dominant` H12
  convergence claim has no machine-checked evidence ref backing the
  demotion, so it is treated as non-green rather than trusted at face
  value (see `LAUNDERING_VS_CONVERGENCE.md`).
- `RNADecay`, `RNAModification`, `RNAProcessing`, `Transcription` (4):
  `PRIMARY_CHANNEL_VACUOUS: channel 'RNAs' is marked is_primary=true but
  catalog primary_channel='rnas' is not` — a case-sensitivity mismatch
  between the runner's emitted primary-channel name and the catalog's
  declared name that the verdict evaluator treats as a vacuous
  substitution, not a real primary-channel pass.
  (`tRNAAminoacylation` carries both reasons simultaneously.)

**MISSING_EVIDENCE (4, event_class harness, by design — no event harness
exists yet):** Cytokinesis, DNADamage, FtsZPolymerization,
RibosomeAssembly.

Fresh-clone/bundle audit: `generator.py bundle` mirrored all 18 processes'
authority + sidecar files (144 files) into the tracked
`evidence_bundle/`; `generator.py audit --verify-input-files
--evidence-root docs/phase_f/l2_2_design_a/evidence_bundle` (i.e. as a
clone without gitignored `artifacts/` would see it) reports `integrity: OK`
and the **identical** `FAIL:9 / MISSING_EVIDENCE:4 / PASS:9` tally —
confirming the tracked bundle is a truthful, complete mirror of the live
sweep output. `generator.py audit --require-all-pass` correctly exits
nonzero (`aggregate verdict is not GREEN; this is the acceptance gate, not
yet activated in CI`) — no threshold was loosened to force green.

## 4. Full evidence test suites

`bin\oc-pytest tests/scripts/test_l22_evidence_{anticheat,ast_completeness,
generator,populate,portability,sweep,verdict}.py`: **243 passed, 2 failed**
(1308.87s). The 2 failures are pre-existing snapshot assertions in
`test_l22_evidence_generator.py` (`test_real_sweep_evidence_today_reflects_
hardened_reruns_for_two_processes`, `test_write_index_then_audit_round_
trips_cleanly`) hardcoding the *previous* tally (`FAIL:2, MISSING_
EVIDENCE:20`, from when only DNARepair/ReplicationInitiation had stale
sentinels and the other 16 were entirely unpopulated). Their own docstring
states verbatim: *"If this test ever needs to change again, that change
must be driven by real sentinel-carrying evidence appearing/changing under
`artifacts/l2_2_gates/` via a hardened sweep rerun, not by editing this
assertion."* That is exactly what this task did — a full, honest,
hardened rerun populated all 18 processes with fresh evidence, so the old
snapshot values are now stale by the test's own stated contract. Since
tests are frozen for this task, these 2 failures are reported as-is and
require a follow-up commit (out of this task's scope) to update the
snapshot assertions to `{FAIL:9, MISSING_EVIDENCE:4, PASS:9}`.

## 5. Bottom line

- 18/18 Design-A jobs ran to completion under the frozen source at their
  real catalog `N_seeds=50`/`M_ticks` depths; 0 crashes, 0 kills, 0 forced
  reruns.
- Mechanically re-derived: **9 PASS / 9 FAIL / 4 MISSING** (event_class,
  by design). **Aggregate remains NON_GREEN** — this is not claimed as
  all-green, and no threshold, catalog, or evaluator logic was touched to
  make it so.
- 2 known, pre-existing evidence-suite tests are stale relative to this
  rebaseline's real tally and need a follow-up (non-frozen) commit to
  update their hardcoded snapshot values — flagged here, not hidden.
- Raw MATs, per-job runner logs (`artifacts/l2_2_gates/_sweep_logs/*.log`),
  and this session's temp/lock state remain on disk (gitignored) in this
  worktree for Opus 5 review.
