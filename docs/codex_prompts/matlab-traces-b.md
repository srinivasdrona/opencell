# MATLAB per-process trace extraction — batch B (processes 8-14)

Runs `scripts/matlab/extract_per_process_traces_batch_b.m` for: ChromosomeSegregation, Transcription, TranscriptionalRegulation, RNAProcessing, RNAModification, RNADecay, tRNAAminoacylation.

## MATLAB invocation
```
matlab -batch "cd 'E:\opencell-worktrees\matlab-traces-b'; run('scripts/matlab/extract_per_process_traces_batch_b.m')"
```

## Standard preamble
Overwrite STATUS.md with "MATLAB traces batch B started at <timestamp>" as first action.

## Verify 7 .mat files

In `data/m1_sources/karr_native/per_process_traces/`: ChromosomeSegregation, Transcription, TranscriptionalRegulation, RNAProcessing, RNAModification, RNADecay, tRNAAminoacylation (each `_100ticks.mat`).

DO NOT commit. Time-box 60 min.
