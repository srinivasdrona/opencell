# MATLAB fitConstants extraction

Runs `scripts/matlab/extract_fitted_constants.m`. Karr's fitted parameter values.

## MATLAB invocation
```
matlab -batch "cd 'E:\opencell-worktrees\matlab-fitted-constants'; run('scripts/matlab/extract_fitted_constants.m')"
```

Expected wall: 5-15 min.

## Standard preamble
Overwrite STATUS.md with "MATLAB fitted-constants extraction started at <timestamp>" as first action.

## Verify `data/m1_sources/karr_native/fitted_constants.mat` exists. h5py-check `fitted` struct has entries for 6-12 of the 28 processes. DO NOT commit (gitignored).

Time-box: 20 min.
