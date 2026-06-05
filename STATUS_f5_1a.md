# STATUS_f5_1a

Outcome: IN_PROGRESS

## Live Log (UTC)
- 2026-06-05T09:06:00Z Started F5.1a. Read `SESSION_CONTEXT.md`, `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md`, and `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md`; scoped task to a single-file MATLAB extractor parameterization plus one smoke run.
- 2026-06-05T09:06:00Z Beat 1 contract: extend `scripts/matlab/extract_per_process_traces_v2.m` with optional `seed`, preserve seed=0 behavior, write seed-specific output subdirectory, and stamp metadata with the requested seed.
- 2026-06-05T09:06:00Z Beat 4 pre-mortem initialized for FAILURE_MODE_1..7; explicit checks planned for seed plumbing, default-path preservation, smoke artifact shape, non-overwrite behavior, MATLAB boot errors, and temp probe cleanup.
- 2026-06-05T09:06:00Z Baseline repo check: worktree clean before edits.
- 2026-06-05T09:06:00Z Baseline reference check: `data/m1_sources/karr_native/per_process_traces_v2/Translation_100ticks.mat` is absent in this worktree, so "unchanged" will be verified as absent-before and absent-after unless the smoke run creates it unexpectedly.
- 2026-06-05T09:06:00Z Applied the narrow Beat 3 MATLAB diff in `scripts/matlab/extract_per_process_traces_v2.m`: added `seed` arg/default, seed-based default `output_subdir`, threaded `seed_simulation(sim, seed)`, and updated `metadata.rng_seed`.
- 2026-06-05T09:08:00Z Corrected a default-order bug introduced during the first patch: `seed` initialization now runs before the default `output_subdir` logic so the existing 1-3 argument call shapes remain valid.
- 2026-06-05T09:11:00Z Beat 4 code checks before MATLAB: exactly one `seed_simulation(sim, seed)` call site in the main body; helper definition unchanged; default `output_subdir` branch preserves `per_process_traces_v2` for `seed == 0`.
- 2026-06-05T09:12:00Z Literal acceptance smoke command failed at MATLAB dispatch with `Unrecognized function or variable 'extract_per_process_traces_v2'` from repo root. Treating this as path/bootstrap infra, capturing stderr, and proceeding with a no-code-change verification command that explicitly adds `scripts/matlab` to the MATLAB path.
- 2026-06-05T09:14:00Z Fallback MATLAB smoke run succeeded for `Translation`, `seed=1`, `n_ticks=100`; stdout reported save path `data/m1_sources/karr_native/per_process_traces_v2_s001/Translation_100ticks.mat`.
- 2026-06-05T09:15:00Z `bin\oc-py.cmd _tmp_verify.py` passed: `states_before/monomers` and `states_after/monomers` datasets each have shape `(1, 100)`, every tick payload has shape `(1, 482)`, `total_sum=208.0`, `total_rate=2.08`, `nonzero_proteins=89`, `max_per_protein=7.0`, `metadata.rng_seed=1`.
- 2026-06-05T09:15:00Z Seed-0 overwrite guard: `data/m1_sources/karr_native/per_process_traces_v2/Translation_100ticks.mat` remained absent before and after the smoke run, so no seed-0 artifact was modified or overwritten in this worktree.
- 2026-06-05T09:17:00Z Deleted temporary verification probe `_tmp_verify.py`; no `_tmp_*` files remain.
- 2026-06-05T09:17:00Z Confirmed `STATUS_f5_1a.md` is matched by `.gitignore` rule `STATUS_*.md`; it will be force-added for the required final commit.

## Notes
- The Beat 3 contract from the task prompt is being followed exactly except for the local baseline condition that the seed-0 `per_process_traces_v2` reference file is missing in this worktree at start.

## Commands Run
- Literal acceptance command from task prompt:
  `& "E:\MATLAB\bin\matlab.exe" -batch "cd 'E:\opencell-worktrees\l22-f5-translation-calibration'; extract_per_process_traces_v2({'Translation'}, [], 100, 1)"`
- Verification smoke command used after the path/bootstrap failure:
  `& "E:\MATLAB\bin\matlab.exe" -batch "cd 'E:\opencell-worktrees\l22-f5-translation-calibration'; addpath(fullfile(pwd, 'scripts', 'matlab')); extract_per_process_traces_v2({'Translation'}, [], 100, 1)"`
- h5py verification command:
  `bin\oc-py.cmd _tmp_verify.py`

## Verification Data
- New artifact: `data/m1_sources/karr_native/per_process_traces_v2_s001/Translation_100ticks.mat`
- Monomer dataset shape: `(1, 100)` for both `states_before` and `states_after`
- Per-tick monomer payload shape: `(1, 482)`
- total_sum: `208.0`
- total_rate: `2.08`
- nonzero_proteins: `89`
- max_per_protein: `7.0`
- metadata.rng_seed: `1`

## Failure Mode Disposition
- `FAILURE_MODE_1: SEED_NOT_THREADED` — Disposition: prevented. Grep after edit showed one active call site in the main body and it is `seed_simulation(sim, seed)`.
- `FAILURE_MODE_2: DEFAULT_BEHAVIOR_REGRESSED` — Disposition: prevented in code. `seed` now defaults before the `output_subdir` block, and the `seed == 0` branch still selects `per_process_traces_v2`.
- `FAILURE_MODE_3: SEED_ZERO_RNG_DIFFERENT_FROM_OLD` — Disposition: unchanged by patch. The script still calls the same `seed_simulation` helper; only the caller-provided argument is parameterized.
- `FAILURE_MODE_4: SMOKE_TEST_PRODUCES_EMPTY_TRACE` — Disposition: prevented. Verification showed positive monomer signal with `total_rate=2.08`, `total_sum=208.0`, and `nonzero_proteins=89` which exceeds the `>= 30` floor.
- `FAILURE_MODE_5: OUTPUT_OVERWRITES_SEED_0_TRACE` — Disposition: prevented. MATLAB stdout reported `_s001` in the save path, and the seed-0 target path remained absent before and after the run.
- `FAILURE_MODE_6: MATLAB_BOOT_TIMEOUT` — Disposition: partial infra deviation only. MATLAB launched successfully; the literal command failed on path resolution, not boot/runtime-path setup. The fallback `addpath(...)` smoke completed successfully without code changes.
- `FAILURE_MODE_7: TEMP_PROBES_LEFT_BEHIND` — Disposition: prevented. `_tmp_verify.py` was deleted after verification and before commit.

## Acceptance Checklist
- [x] `scripts/matlab/extract_per_process_traces_v2.m` compiled in MATLAB as part of the fallback smoke run.
- [ ] Literal acceptance command succeeded exactly as written.
- [x] New seed-1 artifact exists at `data/m1_sources/karr_native/per_process_traces_v2_s001/Translation_100ticks.mat` and is non-empty.
- [x] Seed-0 reference target was not modified; local baseline is absent-before and absent-after.
- [x] h5py verification passed for monomer signal and `metadata.rng_seed == 1`.
- [ ] Commit created.
- [ ] `STATUS_f5_1a.md` finalized with commit SHA.
- [ ] Working tree clean.

## Deviations From Beat 3 Contract
- The intended code diff stayed within the Beat 3 contract in `scripts/matlab/extract_per_process_traces_v2.m`.
- Environmental deviation 1: the literal MATLAB acceptance command from repo root did not resolve `extract_per_process_traces_v2` on MATLAB's path, so verification used an `addpath(fullfile(pwd, 'scripts', 'matlab'))` wrapper without modifying MATLAB infrastructure.
- Environmental deviation 2: the seed-0 `per_process_traces_v2/Translation_100ticks.mat` reference file was absent in this worktree both before and after the run, so overwrite protection was verified as absence-preserved rather than hash-preserved.
