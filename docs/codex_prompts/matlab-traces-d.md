# MATLAB per-process trace extraction — batch D (processes 22-28)

Runs `scripts/matlab/extract_per_process_traces_batch_d.m` for: ProteinTranslocation, MacromolecularComplexation, RibosomeAssembly, FtsZPolymerization, Cytokinesis, HostInteraction, TerminalOrganelleAssembly.

## MATLAB invocation
```
matlab -batch "cd 'E:\opencell-worktrees\matlab-traces-d'; run('scripts/matlab/extract_per_process_traces_batch_d.m')"
```

## Standard preamble
Overwrite STATUS.md with "MATLAB traces batch D started at <timestamp>" as first action.

## Verify 7 .mat files. Note: HostInteraction may have unusual state and may error during evolveState — that's expected per Karr's design, log error in STATUS but treat as success of batch.

DO NOT commit. Time-box 60 min.
