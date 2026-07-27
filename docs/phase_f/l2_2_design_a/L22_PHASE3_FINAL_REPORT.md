# L2.2 Full Multi-Seed Extraction — Phase 3 Final Report

Phase 3 of the L2.2 genuine multi-seed Karr oracle extraction (see
`L22_FULL_EXTRACTION_SCOPE.md` for Phase 1 scope derivation and
`L22_PHASE2_PREFLIGHT_REPORT.md` for the seed-1 schema preflight that gated
this run). This report documents the seeds 2-49 extraction for the 11
production processes that passed Phase 2 preflight, and the final
validation of the complete 50-seed set (seed0 canonical + seed1 + seeds2-49)
for those processes.

## Result: 11/16 production processes fully extracted to 50 seeds; 5 remain BLOCKED (unchanged from Phase 2, correctly not touched in Phase 3)

## MATLAB run

- Command: `scripts/matlab/run_l22_seed_shards.ps1 -Processes <11 passing processes> -Seeds "2-49" -Workers 2`
- Extractor: `data/m1_sources/WholeCell/.../extract_per_process_traces_v2.m` (same script/hash validated in Phase 2 preflight; no extractor changes between Phase 2 and Phase 3)
- MATLAB: `E:\MATLAB\bin\matlab.exe` (R2026a Update 2, trial license), invoked via `-batch`, one process per worker at a time, diary-wrapped per seed-job
- Workers: 2 (bounded parallel, per task requirement "start with 2"). No license contention observed (both stderr logs empty for the full run) — did not need to escalate to 4.
- Seed jobs: 11 processes × 48 seeds (2-49) = **528 seed-job files**, sharded 24 seeds/worker (disjoint output directories `per_process_traces_v2_s002/` … `_s049/`, one file per process per seed dir).
- Wall clock: started 2026-07-27 20:29:47, finished 2026-07-27 21:48:31 → **≈78.7 minutes**.
- Exit code: 0 for both workers. No stderr output. `[run_l22_seed_shards] all workers finished.`

## File validation (structural, `trace_validation.validate_structural`)

Ran `python scripts/l22_extraction/report.py final --seeds 1-49 --out artifacts/l22_full_extraction/phase3_final_report.json`
(via `bin\oc-py.cmd`, WSL). This validates, for every one of the 16 production
processes: canonical seed0 + seeds 1 through 49 (seed1 was generated and
retained in Phase 2), i.e. it re-validates seed1 in addition to the new
seeds2-49, and additionally re-runs the real oracle loader
(`load_karr_oracle`) for all 16 production processes plus both specialized
ensembles.

### 11 passing production processes — all seeds 0-49 present and structurally valid

| Process | Files validated (seed0 + 1-49) | Missing/failing | `canonical_seed_count` (loader) | Loader warnings |
|---|---|---|---|---|
| DNARepair | 50/50 | 0 | 50 | none |
| DNASupercoiling | 50/50 | 0 | 50 | none |
| MacromolecularComplexation | 50/50 | 0 | 50 | none |
| Metabolism | 50/50 | 0 | 50 | none |
| ProteinModification | 50/50 | 0 | 50 | none |
| ProteinProcessingI | 50/50 | 0 | 50 | none |
| ProteinTranslocation | 50/50 | 0 | 50 | none |
| RNAModification | 50/50 | 0 | 50 | none |
| Replication | 50/50 | 0 | 50 | none |
| ReplicationInitiation | 50/50 | 0 | 50 | none |
| tRNAAminoacylation | 50/50 | 0 | 50 | none |

No `KARR_SINGLE_SEED_REUSED` warning for any of the 11 (would indicate the
loader silently fell back to reusing one seed — explicitly checked for and
absent).

### 2 specialized ensembles — unchanged, still healthy (not regenerated, per hard policy)

| Process | `canonical_seed_count` (loader) | Warnings |
|---|---|---|
| Transcription | 50 | none |
| Translation | 50 | none |

Their canonical seed0 files were **not** present in this worktree's
`per_process_traces_v2/` during this validation run (deliberately, to avoid
re-triggering the Phase-2 Transcription false-positive — see
`L22_PHASE2_PREFLIGHT_REPORT.md`), so the loader correctly took the
specialized-ensemble path directly.

### 5 blocked production processes — correctly still incomplete (seeds 2-49 not generated, by design)

Per the hard policy ("If canonical seed0 does not match a freshly generated
seed1 schema, STOP that process before launching further seeds"), these 5
processes were **not** included in the Phase 3 launcher invocation. The
final report's file validation loop (which iterates the full mechanically-derived
production set of 16, not just the 11 that passed) correctly reports their
seeds 2-49 as `file does not exist` — this is the expected, honest result,
not a regression:

| Process | Missing entries (of 48 checked, seeds 2-49) | Seed1 present? | Loader `canonical_seed_count` |
|---|---|---|---|
| ProteinDecay | 48 | yes (Phase 2) | n/a — loader falls through to single-seed/blocked path |
| ProteinFolding | 48 | yes (Phase 2) | n/a |
| ProteinProcessingII | 48 | yes (Phase 2) | n/a |
| RNADecay | 48 | yes (Phase 2) | n/a |
| RNAProcessing | 48 | yes (Phase 2) | n/a |

Total missing/failing entries across the full report: **240** (= 5 processes
× 48 seeds), matching exactly the expected gap from the 5 still-blocked
processes. Zero unexpected missing/failing entries among the 11 passing
processes or the 2 specialized ensembles.

`report.py`'s overall `result` field is `INCOMPLETE` (not `PASS`) because it
scans the entire mechanically-derived 16-process production set
unconditionally — this is intentional/correct behavior, not a tooling bug:
it surfaces the 5 still-blocked processes truthfully rather than silently
scoping them out. The blockers list in
`artifacts/l22_full_extraction/phase3_final_report.json` contains exactly
the 240 expected missing-file entries for the 5 processes carried forward
unchanged from Phase 2 preflight, and nothing else.

## Repair recommendation for the 5 blocked processes (unchanged from Phase 2; reiterated here since Phase 3 didn't touch them)

Repairing `ProteinDecay`, `ProteinFolding`, `ProteinProcessingII`, `RNADecay`,
`RNAProcessing` requires regenerating their canonical seed0 under the current
extractor's snapshot allowlist — which this task's hard policy explicitly
forbids doing unilaterally ("Canonical unsuffixed seed0 is authoritative; do
not generate or retain a competing `_s000`"). This remains a maintainer/Opus
decision, not made in this task.

## Traceability

- Extractor source SHA-256: recorded in `artifacts/l22_full_extraction/phase3_final_report.json` (`extractor_source_sha256`), matches the Phase 2 preflight's extractor hash (no extractor changes occurred between Phase 2 and Phase 3).
- Raw `.mat` files remain gitignored (per policy); this report and its JSON companion are the tracked evidence artifacts. Individual file SHA-256 and metadata (process name, n_ticks, rng_seed, tick_offset, timestamp) for every one of the 561 validated files (11×50 + 2 specialized-loader checks + carried-forward 5×2) are recorded in `artifacts/l22_full_extraction/phase3_final_report.json` under `files.<process>.<seed>`.
- Run state / per-worker logs: `artifacts/l22_full_extraction/run_state_20260728_015937.json`, `artifacts/l22_full_extraction/logs/worker{0,1}_20260728_015937.{stdout,stderr}.log` (gitignored, regenerable evidence, not committed — consistent with the existing `artifacts/` convention for run-specific logs).
