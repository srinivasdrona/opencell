# MATLAB initializeState extraction

Runs `scripts/matlab/extract_initial_states.m`. Fresh `initializeState()` outputs per process.

## MATLAB invocation
```
matlab -batch "cd 'E:\opencell-worktrees\matlab-initial-states'; run('scripts/matlab/extract_initial_states.m')"
```

Expected wall: 5-15 min.

## Standard preamble
Overwrite STATUS.md with "MATLAB initial-states extraction started at <timestamp>" as first action.

## Verify ~28 `<process>_init.mat` files in `data/m1_sources/karr_native/initial_states/`. Some processes may fail (logged as WARN); that's fine. DO NOT commit (gitignored).

Time-box: 20 min.
