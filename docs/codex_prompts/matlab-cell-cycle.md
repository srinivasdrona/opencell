# MATLAB cell-cycle reference trajectory

Runs `scripts/matlab/extract_cell_cycle_trajectory.m` for one full Karr cell cycle (~32400 ticks ≈ 9 hours biological time). Snapshots every 100 ticks.

**Phase E validation gold standard.**

## MATLAB invocation
```
matlab -batch "cd 'E:\opencell-worktrees\matlab-cell-cycle'; run('scripts/matlab/extract_cell_cycle_trajectory.m')"
```

Expected wall: 1-3 hours. **DO NOT time-box.**

## Standard preamble
Overwrite STATUS.md with "MATLAB cell-cycle trajectory started at <timestamp>" as first action.
Commit-or-stop on failure.

## What to do

1. Start MATLAB. Script prints progress every 100 ticks with ETA.
2. Every ~10 minutes, update STATUS.md with the latest "[cell_cycle] tick X / 32400" line (heartbeat — let orchestrator see progress).
3. Script auto-terminates when `sim.state('Geometry').pinched == true` (cell divided). May happen before 32400 ticks.
4. When MATLAB exits, verify `data/m1_sources/karr_native/cell_cycle_trajectory.mat` exists.
5. h5py-check: should have `snapshots/tick` array of ~325 entries.
6. DO NOT commit (gitignored, 100-500MB).

## If MATLAB fails midway

The script has try/catch and saves partial trajectory. A partial 5000-tick trajectory is still useful — don't discard it. Report failure point in STATUS.

Time-box: NONE.
