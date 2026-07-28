# L2.2 Depth-200 Oracle Regeneration — DNARepair, ProteinDecay, ReplicationInitiation

**Scope:** DNARepair, ProteinDecay, ReplicationInitiation — the three
`design_a_per_tick`-harness processes whose `PROCESS_CATALOG.yaml` entries
require `M_ticks: 200`.

**Worktree:** `E:\opencell-worktrees\l22-depth200`,
branch `agent/l22-depth200`, cut from local `main` `7b6aa80`.

This report documents why these three processes' accepted 50-seed oracle
sets are being regenerated at genuine 200-tick depth, what evidence grounds
the plan, the (deliberately unusual) filename-vs-content semantics chosen,
and the archive of the 150 old 100-tick files being superseded. It is
written and committed *before* the long MATLAB regeneration run, per the
task's required commit cadence.

## 1. Root cause

`docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml` requires `M_ticks: 200`
for DNARepair, ProteinDecay, and ReplicationInitiation (all `harness_type:
design_a_per_tick` — a genuine per-tick trajectory requirement, not an
event-window trick like RibosomeAssembly/FtsZPolymerization, which use
`tick_offset` at the *same* `n_ticks` depth to capture a later window). The
accepted 50-seed oracle `.mat` sets for these three processes on disk
(and in every preserved oracle worktree checked) carry only 100 ticks. A
real L2.2 sweep at `M=200` for any of these three fails at runtime:

```
Requested 200 ticks, but oracle only provides 100.
```

raised by `tests/vivarium/l2_2_design_a_runner.py`'s `_normalize_seed_axis`,
which compares the requested `M_ticks` against the actual array depth
(`arr.shape[1]`) of the loaded `.mat` file — a real content check, not a
metadata label check.

## 2. Source worktrees

Per task instruction, raw accepted 100-tick files were sourced from
preserved oracle worktrees (not re-derived) and copied — never
modifying the source roots:

| Process | Source worktree |
|---|---|
| DNARepair | `E:\opencell-worktrees\l22-full-extract` |
| ReplicationInitiation | `E:\opencell-worktrees\l22-full-extract` |
| ProteinDecay | `E:\opencell-worktrees\l22-stale5-regen` |

Both source worktrees were confirmed git-clean before copying. Their
`scripts/matlab/extract_per_process_traces_v2.m` files are byte-identical
to this worktree's (`git diff --no-index`, no output — the extractor is a
tracked file with no worktree-local modifications anywhere, so "current
extractor" is unambiguous here). Their `data/m1_sources/WholeCell/` trees
were confirmed byte-identical to each other via `robocopy /L /E` (list-only
diff): 859 files, 125,778,037 bytes, zero New/Newer/Older/EXTRA mismatches.
This worktree's own `WholeCell` tree was then copied from `l22-full-extract`
via `robocopy /E` (888 files incl. subdirectories beyond `src/`, ~199.63 MB,
0 mismatches/failures reported) — so all 150 real 200-tick extractions in
this task share one single WholeCell source tree, identical to both
processes' original 100-tick extraction sources.

## 3. Filename-vs-content semantics: the "relabel" design

`tests/vivarium/_l2_2_design_a_runner_helpers.py` resolves oracle files via
**literal `_100ticks.mat` string concatenation** in
`_v2_canonical_seed0_mat_path`/`_v2_suffixed_seed_mat_path`/`_v2_seed_mat_path`
— the loader's filename lookup is **not parameterized by actual tick
count**. Meanwhile `scripts/matlab/extract_per_process_traces_v2.m` names
its output `<Process>_<n_ticks>ticks.mat` based on the real `n_ticks`
argument passed to it, and no-ops (skips) if that exact output path already
exists.

Consequence: a genuine, source-faithful 200-tick extraction naturally
writes `<Process>_200ticks.mat` — a filename the loader will never look
for. Per task requirement #3 ("if naming hardcodes `_100ticks` while
metadata is 200, document this legacy naming explicitly; do not create
parallel unrecognized names"), the chosen design is:

1. Extract genuinely at `n_ticks=200` (real MATLAB run, `tick_offset=0`,
   200 consecutive ticks from `t=0` — not a windowed/offset trick) into a
   fresh path, `<Process>_200ticks.mat` — zero collision with the existing
   `_100ticks.mat` file, so no pre-deletion step is needed before
   generation (unlike the stale5 regen's schema-drift case).
2. **Relabel** (rename) that real 200-tick file over the legacy
   `<Process>_100ticks.mat` filename the loader hardcodes — only after
   `trace_validation.validate_structural(..., expected_n_ticks=200)`
   confirms both `metadata.n_ticks == 200` and the actual channel arrays
   carry ≥200 ticks. The `_100ticks.mat` suffix is therefore a **legacy
   filename label only**; its content is genuinely 200 ticks after
   relabeling. This is implemented in
   `scripts/l22_extraction/depth200_regen.py`
   (`relabel_seed_to_legacy_filename`/`relabel_all`), which refuses to
   relabel any file that fails that structural/depth verification.

No new, loader-unrecognized filename is ever created or left behind; no
`per_process_traces_v2_s000/` directory is ever created (canonical seed 0
always lives in the unsuffixed `per_process_traces_v2/` directory).

## 4. Archive of the 150 old 100-tick files being superseded

Before any of the 150 old files is overwritten, `scripts/l22_extraction/
archive_depth200.py` recorded SHA256/size/original-mtime for every one of
them (both this worktree's copy and the corresponding preserved-worktree
source, cross-checked to confirm exact match), plus extractor/WholeCell
identity. Full manifest (gitignored, regenerable):
`artifacts/l22_depth200_regen/archive_old_100tick_sets.json`.

Summary:

| Process | Seed count | All 50 present & match source | Seed-0 SHA256 | Seed-0 size (bytes) | Seed-0 original mtime (UTC) |
|---|---|---|---|---|---|
| DNARepair | 50 | true | `c3d73b8a0a9e39fffe0b8adba9e6914145f466ae520abb102b793386c940942d` | 10,649,080 | 2026-07-13T03:57:55.520862 |
| ProteinDecay | 50 | true | `1c4d5c58818129f3dece0bb87f81d52f60ff7d3ecee700947c68e72c503b28b4` | 2,379,255 | 2026-07-27T22:32:53.678970 |
| ReplicationInitiation | 50 | true | `0c61c816e3903e771550e674db36fedaa76a546687891a99e46f163703550c0f` | 10,213,104 | 2026-07-13T09:17:49.621763 |

(Per-seed hashes for all 150 files are in the full JSON manifest, not
duplicated here.)

Extractor blob identity (git SHA1 of
`scripts/matlab/extract_per_process_traces_v2.m`, current HEAD, unambiguous
since it is byte-identical and unmodified across this worktree and both
source worktrees): `4a40e3938f5c66d126576f10582c48db861ea950`.

MATLAB version probed at archive time (`E:\MATLAB\bin\matlab.exe`, trial
license): `26.1.0.3251617 (R2026a) Update 2`.

### Honest historical-identity caveat

As with the stale5 regen, **no historical manifest pinning the exact
extractor commit or WholeCell source-tree hash used to generate the
original 100-tick files (in `l22-full-extract`/`l22-stale5-regen`) exists
anywhere in this repository.** What is verified above is (a) the *current*
extractor is byte-identical across all three worktrees involved, and (b)
the WholeCell tree copied into this worktree is byte-identical to the tree
in `l22-full-extract` at archive time. Neither claim proves the tree/
extractor state at the *original* 100-tick generation time was identical to
today's — only that no divergence has been introduced since, as far as this
repository's git history and worktree state show. This is a high-confidence
circumstantial match, not a certified per-run provenance pin.

### Old-set loader health, confirmed before overwrite

Per task requirement #2, `scripts/l22_extraction/preflight.py`'s
`loader_report()` was run against all three processes' old (100-tick) sets
**before** any file was touched. All three returned:

```
ok: true, canonical_seed_count: 50, n_ticks_available: 100, warnings: []
```

confirming the old sets were fully healthy and loader-serviceable at
100 ticks prior to this regeneration.

## 5. Tooling: reused and minimally extended

Per task requirement #4, no new script duplicates existing functionality;
one new narrowly-scoped module was added, one existing report module
extended non-breakingly:

- **`scripts/l22_extraction/depth200_regen.py`** (new). Closed allowlist
  `DEPTH200_PROCESSES = (DNARepair, ProteinDecay, ReplicationInitiation)`;
  `REAL_N_TICKS = 200`; `LEGACY_FILENAME_N_TICKS_LABEL = 100`. Reuses
  `seed0_regen.build_seed0_matlab_command` directly for the seed-0 MATLAB
  command and `launcher.plan_extraction` directly for seeds ≥ 1 planning —
  no reimplementation of either. Adds only the allowlist enforcement, path
  builders for the real (`_200ticks.mat`) vs. legacy (`_100ticks.mat`)
  filenames, and the relabel logic (§3) that this task specifically
  requires and that no existing module provides.
- **`scripts/l22_extraction/archive_depth200.py`** (new). Archive-manifest
  builder analogous to `archive_stale5.py`, adapted for this task's 3×50
  file set and two-source-worktree mapping.
- **`scripts/l22_extraction/report.py`** (extended, non-breaking). Added an
  optional `expected_n_ticks: int = 100` parameter to `build_final_report()`
  (default preserves existing behavior for every other process), threaded
  only into the two `validate_structural(...)` calls — never into path
  resolution, since the *filename* must stay `_100ticks.mat` regardless of
  real content depth (§3). Added a matching `--expected-n-ticks` CLI flag
  to the `final` subcommand, for use in this task's post-regeneration
  verification pass (`--expected-n-ticks 200`).
- `scripts/matlab/run_l22_seed_shards.ps1` (existing, unmodified) will be
  reused as-is for seeds 1-49 generation (`-NTicks 200`); it already
  supports a configurable tick count.

No changes were made to `PROCESS_CATALOG.yaml`, the L2.2 runner, process
biology/model code, metrics, thresholds, verdict pins, or `plan.md`/status
files.

## 6. Tests

- `tests/scripts/test_l22_depth200_regen.py` (new, 13 tests): allowlist
  enforcement, path builders (real vs. legacy filename), seed-0 MATLAB
  command construction, seeds-≥1 plan delegation, relabel
  success/failure/aggregation cases (wrong tick count, missing real file,
  structural-validation failure all correctly refused).
- `tests/scripts/test_l22_archive_depth200.py` (new, 4 tests): honest
  missing-file reporting, match/mismatch detection against source
  worktrees, default process/seed coverage.
- `tests/scripts/test_l22_report_final.py` (+1 test): confirms
  `expected_n_ticks` defaults to 100 (no behavior change for existing
  callers) and correctly flags a tick-count mismatch when set to 200
  against synthetic 100-tick fixtures.

All new/modified test files pass together with the full pre-existing L2.2
extraction test suite (`test_l22_seed0_regen.py`, `test_l22_launcher_planning.py`,
`test_l22_archive_stale5.py`, `test_l22_trace_validation.py`,
`test_l22_derive_scope.py`): **71 passed, 0 failed, 0 skipped**. `ruff
check` is clean on all new/modified files.

## 7. Regeneration plan (canary → full run → relabel → final verification)

1. **Canary**: one process, seed 0 + seed 1 at `n_ticks=200`, 1 MATLAB
   worker. Verify metadata tick count ≥ 200, real channel-array tick depth
   ≥ 200, schema consistent, required channels present, structural
   validation passes, then relabel and confirm `loader_report()` can serve
   the relabeled file at the new depth.
2. **Full run**: extend to all three processes × seeds 0-49, 1 MATLAB
   worker initially (2 only if system load permits at run time — never
   killing or contending with the concurrently active Metabolism FVA
   Python runner or any other process). Resumable via the existing
   plan/skip-if-exists logic.
3. **Relabel** all 150 real 200-tick files onto their legacy
   `_100ticks.mat` filenames via `depth200_regen.relabel_all`.
4. **Final verification**: exactly seeds 0-49 present per process, no
   `_s000` anywhere, `report.py final --expected-n-ticks 200` PASS,
   identical channel schema/width across all 50 seeds per process,
   distinct (non-duplicate) seed hashes, `loader_report()`
   `canonical_seed_count=50`/`warnings=[]` at the new depth, and a bounded
   smoke check that the L2.2 runner can request `M=200` for these three
   processes without the depth error (not a full expensive OC sweep).

Results of steps 1-4 will be appended to this report (or a companion final
evidence report) once the MATLAB regeneration run completes.

## 8. Out of scope / unaffected

This regeneration touches only local worktree copies of these three
processes' `.mat` traces (gitignored `data/m1_sources/karr_native/`, per
existing convention — raw bytes are never committed). It does not modify:
the primary checkout's canonical files, `PROCESS_CATALOG.yaml`, the L2.2
runner, the loader's filename-resolution logic, any process biology/model
code, metrics, thresholds, verdict pins, or `plan.md`/status files. The
concurrently active Metabolism FVA Python runner (elsewhere, CPU-heavy, no
MATLAB) is unaffected and was never contended with or terminated.
