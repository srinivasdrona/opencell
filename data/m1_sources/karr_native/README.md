# Karr-native MATLAB extractions

This directory holds large data assets extracted from running Karr's MATLAB WCM directly on this machine. These files are **gitignored** because of their size — they are reproducible via the scripts in `scripts/matlab/`.

## Provenance

- **MATLAB version**: see `scripts/matlab/regenerate_metabolism_dynamics.m` for the canonical bootstrap pattern (`setPath()` + `load('data/Simulation_fitted.mat')`).
- **WCM source**: `data/m1_sources/WholeCell/` (the Covert Lab repo bundled with OpenCell).
- **Generated**: 2026-05-22 evening, on the operator's machine while a test MATLAB license was active.

## Contents (when populated)

### `per_process_traces/`
Per-process bit-identical validation traces. For each of Karr's 28 processes, 100 ticks of `evolveState()` were captured with frozen inputs.

Each `<process_name>_100ticks.mat` file contains:
- `states_before`: (n_ticks, n_state_vars) — input state at tick boundary
- `evolveState_emitted`: (n_ticks, n_emit_vars) — what evolveState produced
- `states_after`: (n_ticks, n_state_vars) — output state after evolveState applied
- `metadata`: tick step, RNG seed, frozen-input mask

### `cell_cycle_trajectory.mat`
Full Karr-WCM cell cycle reference (~32,400 ticks at Δt=1s ≈ 9 hours biological). State snapshots every 100 ticks (~325 snapshots total).

### `initial_states/`
Fresh `initializeState()` outputs per process.

### `fitted_constants.mat`
Karr's `fitConstants()` output — the fitted parameter values from his optimization step.

## Regeneration

Run the scripts in `scripts/matlab/`. Each is a separate MATLAB invocation; they can run in parallel.

```powershell
matlab -batch "run('scripts/matlab/extract_per_process_traces_batch_a.m')"  # processes 1-7
matlab -batch "run('scripts/matlab/extract_per_process_traces_batch_b.m')"  # processes 8-14
matlab -batch "run('scripts/matlab/extract_per_process_traces_batch_c.m')"  # processes 15-21
matlab -batch "run('scripts/matlab/extract_per_process_traces_batch_d.m')"  # processes 22-28
matlab -batch "run('scripts/matlab/extract_cell_cycle_trajectory.m')"
matlab -batch "run('scripts/matlab/extract_initial_states.m')"
matlab -batch "run('scripts/matlab/extract_fitted_constants.m')"
```
