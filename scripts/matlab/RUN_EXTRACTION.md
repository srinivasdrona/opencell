# Run MATLAB Extraction (`extract_everything_v1.m`)

## 1) Prerequisites

- MATLAB: **R2026a** installed locally (as stated by operator context).
- Valid MATLAB license for the full run window (no mid-run expiry).
- WholeCell source present at one of:
  - `data/m1_sources/WholeCell`
  - `_tmp_WholeCell`
- Expected toolbox:
  - **Statistics and Machine Learning Toolbox** (needed for several trace chunks; script will skip affected chunks if unavailable).
  - Optimization/Parallel toolboxes are optional for this orchestrator (not required by default chunks).

## 2) Pre-flight Checks

### Verify MATLAB starts and version

```powershell
matlab -batch "disp(version); disp(version('-release'));"
```

### Verify license is valid

```powershell
matlab -batch "disp(['MATLAB license test: ', num2str(license('test','MATLAB'))]);"
```

### Verify toolbox availability

```powershell
matlab -batch "addpath('scripts/matlab'); extract_everything_v1([],[],[],[],{'toolbox_check_only'});"
```

### Verify WholeCell source path is discoverable

```powershell
matlab -batch "p={'data/m1_sources/WholeCell','_tmp_WholeCell'}; ok=false; for i=1:numel(p), if exist(fullfile(p{i},'data','Simulation_fitted.mat'),'file')==2, ok=true; disp(['Found: ',p{i}]); end, end; if ~ok, error('WholeCell source not found'); end"
```

## 3) Invocation

## Output filename conventions (used by the master script)

- Per-process traces:
  - `data/m1_sources/karr_native/per_process_traces_v2_sNNN/<Process>_<ticks>ticks.mat`
- Per-tick Metabolism LP oracle:
  - `data/karr_fixtures/matlab_ground_truth/per_tick/metab_flux_per_tick_sNNN_tTTT.mat`
- Tick-1 Metabolism oracle:
  - `data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_sNNN_tick1.mat`
- Ensembles:
  - `data/m1_sources/karr_native/ensembles/<process>/seed_NNN/<Process>_<ticks>ticks.mat`
- Flat/targeted outputs:
  - `data/karr_fixtures/per_process/*_flat.mat`
  - `data/m1_sources/karr_flat/*.mat`

### Full default run (extract all configured chunks, skip existing files)

```powershell
matlab -batch "addpath('scripts/matlab'); extract_everything_v1"
```

### P0-first phased run (recommended)

```powershell
matlab -batch "addpath('scripts/matlab'); extract_everything_v1(0,49,1,100,{'per_process_traces_v2','metab_flux_tick1','metab_flux_per_tick'})"
```

### P1 follow-up phased run

```powershell
matlab -batch "addpath('scripts/matlab'); extract_everything_v1(0,49,1,100,{'per_process_fixtures','transcription_ensemble','translation_ensemble','initial_states','fitted_constants','karr_m1_dynamics','karr_m1_flux_growth','karr_targeted','karr_m2v2','karr_m3v2','protein_complexes','m3_metabolite_vocab'})"
```

### P2 / long-horizon example (manual extension)

```powershell
matlab -batch "addpath('scripts/matlab'); extract_everything_v1(0,49,1,500,{'metab_flux_per_tick'})"
```

## 4) Expected Runtime (rough)

- **P0** (50 seeds, 100 ticks):
  - `per_process_traces_v2` completion + metabolism tick1/per-tick: ~9-24 hours total.
- **P1**:
  - flat/targeted/ensemble/initial/fitted bundles: ~2-8 hours total.
- **P2**:
  - long-horizon metabolism and full-cycle work: from ~12 hours to multi-day, depending scope.

Runtime depends heavily on CPU, disk, and toolbox availability.

## 5) Expected Output Size (rough)

- **P0**:
  - Additional seeded v2 traces to close gaps: ~0.17 GB.
  - Metabolism per-tick 50x100 oracle files: ~0.2-0.6 GB.
- **P1**:
  - Flat/targeted additions: ~0.2-1.0 GB.
- **P2**:
  - 500-tick metabolism: ~1-3 GB.
  - Full-cycle process bundles: ~10-80 GB (single seed), much larger for multi-seed.

## 6) Verification (Post-run)

### File-count checks

```powershell
# Seeded v2 traces (expect near 50 * process_count files for chosen scope)
(Get-ChildItem data/m1_sources/karr_native/per_process_traces_v2_s* -Recurse -Filter *_100ticks.mat).Count

# Metabolism per-tick oracle files (for 50x100 target expect 5000)
(Get-ChildItem data/karr_fixtures/matlab_ground_truth/per_tick -Filter *.mat).Count
```

### Spot-check MAT payload fields

```powershell
matlab -batch "s=load('data/karr_fixtures/matlab_ground_truth/metab_flux_allocated_state_s000_tick1.mat'); disp(isfield(s,'flux')); disp(isfield(s,'bounds')); disp(isfield(s,'growth'));"
```

### Spot-check one trace metadata

```powershell
matlab -batch "s=load('data/m1_sources/karr_native/per_process_traces_v2_s000/Metabolism_100ticks.mat'); disp(s.metadata.process_name); disp(s.metadata.n_ticks);"
```

Optional future helper (`bin\oc-py scripts/verify_extractions.py`) can be added later; not required for this runbook.

## 6a) Quote-safe / slot-coordinated invocation (commands with embedded quotes)

`matlab -batch "<command>"` breaks silently when `<command>` itself
contains embedded double-quoted strings (e.g. `jsonencode(...)` output or
any literal JSON) -- the quotes get stripped or the argument truncated
somewhere in the PowerShell/cmd -> `matlab.exe` argv chain, and MATLAB
either errors or silently runs a truncated command with no diary and no
output. This bit both `run_l22_seed_shards.ps1` (which now hard-fails with
an explicit error rather than corrupting silently) and, more seriously, the
DNADamage genuine-corpus re-extraction (Sept-2 review item 8), which needed
embedded JSON in its command.

For any such command, or whenever multiple parallel worktree agents share
this host's MATLAB license, use the tracked helper instead of `matlab -batch`
directly:

```powershell
scripts\tools\run_matlab_slot.ps1 -Tag "my_job" -Slots 4 `
  -MatlabCommand "addpath('scripts/matlab'); <your command, quotes and all>"
```

It writes the command verbatim to a scratch `.m` file (so no shell ever
re-tokenizes embedded quotes) and invokes MATLAB with the minimal, quote-free
`run('<scratch path>')`, while also acquiring one of `-Slots` file-locked
concurrency slots under `artifacts/matlab_slots/` (self-contained, no
dependency on any path outside this repo). See the script's own
`Get-Help scripts\tools\run_matlab_slot.ps1 -Full` for details.

## 7) Troubleshooting

- License expiry mid-run:
  - Symptom: abrupt MATLAB errors about license checkout.
  - Action: renew license, rerun same command; script is idempotent and resumes by skipping existing outputs.

- Missing Statistics Toolbox:
  - Symptom: warnings from `requireToolbox`, trace chunks skipped.
  - Action: install/enable toolbox or run only chunks not requiring it.

- Disk full:
  - Symptom: save failures/write errors.
  - Action: free disk; rerun same command (already-complete chunks are skipped).

- RAM ceiling / MATLAB crash on heavy chunks:
  - Symptom: process termination on long or large extraction sections.
  - Action: run phased chunks (P0 then P1), narrow `dataTypes`, or reduce seed/tick span, then continue.

- WholeCell root not found:
  - Symptom: errors about missing `Simulation_fitted.mat`.
  - Action: place WholeCell source in `data/m1_sources/WholeCell` or `_tmp_WholeCell`, rerun.

