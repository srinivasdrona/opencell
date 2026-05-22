# MATLAB per-process trace extraction — batch C (processes 15-21)

Runs `scripts/matlab/extract_per_process_traces_batch_c.m` for: Translation, ProteinProcessingI, ProteinProcessingII, ProteinModification, ProteinFolding, ProteinActivation, ProteinDecay.

## MATLAB invocation
```
matlab -batch "cd 'E:\opencell-worktrees\matlab-traces-c'; run('scripts/matlab/extract_per_process_traces_batch_c.m')"
```

## Standard preamble
Overwrite STATUS.md with "MATLAB traces batch C started at <timestamp>" as first action.

## Verify 7 .mat files for the 7 processes above. DO NOT commit. Time-box 60 min.
