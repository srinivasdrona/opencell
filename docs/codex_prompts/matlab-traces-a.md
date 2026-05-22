# MATLAB per-process trace extraction — batch A (processes 1-7)

Runs `scripts/matlab/extract_per_process_traces_batch_a.m` for: Metabolism, ReplicationInitiation, Replication, DNADamage, DNARepair, DNASupercoiling, ChromosomeCondensation.

## MATLAB invocation
```
matlab -batch "cd 'E:\opencell-worktrees\matlab-traces-a'; run('scripts/matlab/extract_per_process_traces_batch_a.m')"
```

Expected wall: 20-40 min.

## Standard preamble
Overwrite STATUS.md with "MATLAB traces batch A started at <timestamp>" as first action.
Commit-or-stop: capture stderr + write diagnostic STATUS on failure.
.codex_* files gitignored.

## What to do

1. Run MATLAB. Capture stdout/stderr.
2. Verify 7 .mat files exist in `data/m1_sources/karr_native/per_process_traces/`:
   - Metabolism_100ticks.mat, ReplicationInitiation_100ticks.mat, Replication_100ticks.mat, DNADamage_100ticks.mat, DNARepair_100ticks.mat, DNASupercoiling_100ticks.mat, ChromosomeCondensation_100ticks.mat
3. h5py-check top-level keys per file.
4. DO NOT commit .mat files (gitignored).
5. STATUS reports per-file existence + size + h5py keys + any per-process errors.

Time-box: 60 min.
