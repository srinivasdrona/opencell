# STATUS_L22_PPII

## Scope

Target process: `ProteinProcessingII`

Authoritative contract:

```yaml
name: ProteinProcessingII
bucket: TRIVIAL_RNG
M_ticks: 20
N_seeds: 50
primary_channel: monomers
karr_artifact: per_process_traces_v2
```

Guardrails applied for this pass:

- Read and followed:
  - `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md`
  - `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md`
  - `docs/prompts/COMPOSITION_MANDATE_v2.md`
- Read project/task context:
  - `.github/copilot-instructions.md`
  - `docs/phase_f/CHECKPOINT_2026-08-11.md`
- Read core source/evidence:
  - `data/karr_vendored_source/ProteinProcessingII.m`
  - `docs/phase_f/l2_2_design_a/h12/H12_REPORT.md`
  - `docs/phase_f/l2_2_design_a/h12/perturbation/PROTEINPROCESSINGII_MNRND_SHIM_DETERMINATION_2026-08-05.md`
  - `docs/phase_f/audits/ProteinProcessingII_semantic_audit.md`
  - `docs/karr_extracts/process/17_ProteinProcessingII.md`
  - `docs/karr_extracts/process/22_ProteinTranslocation.md`
  - `E:\\opencell-mirrors\\WholeCell\\src\\+edu\\+stanford\\+covert\\+cell\\+sim\\+process\\ProteinTranslocation.m`

Non-negotiable constraints preserved:

- Do **not** substitute `scripts/matlab/mnrnd.m` for genuine Statistics Toolbox semantics in any gating MATLAB/H12 path.
- Do **not** promote the synthetic Scenario B canary as gating evidence.
- Do **not** edit shared catalog/index.
- Use WSL wrappers for Python execution.

## Inventory Before Any New MATLAB

### Existing gating/status artifacts

- Authoritative current status:
  - `docs/phase_f/l2_2_design_a/evidence_index.json`
  - Current row remains `green: false`, `mechanical_verdict: FAIL`
  - Reasons include stale sweep inputs and:
    - `SENTINEL_FAIL: ... h12 artifact verdict != H12_CONFIRMED (got 'H12_OBSERVED_REGIME')`
- Stale pass-looking bundle:
  - `docs/phase_f/l2_2_design_a/evidence_bundle/ProteinProcessingII/latest/`
  - Not authoritative for current gate state.

### Existing H12 / canary trail

- Primary natural-trace H12 artifact:
  - `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_h12.json`
- Non-gating perturbation artifacts:
  - `docs/phase_f/l2_2_design_a/h12/perturbation/ProteinProcessingII_h12_perturbation.json`
  - `docs/phase_f/l2_2_design_a/h12/perturbation/ProteinProcessingII_h12_scenario_b_perturbation_canary.json`
- Determination locking the shim/non-gating conclusion:
  - `docs/phase_f/l2_2_design_a/h12/perturbation/PROTEINPROCESSINGII_MNRND_SHIM_DETERMINATION_2026-08-05.md`

### Existing natural trace corpus

Shared natural 50-seed traces exist at:

- `E:\opencell-worktrees\main-integrate\data\m1_sources\karr_native\per_process_traces_v2\ProteinProcessingII_100ticks.mat`
- `E:\opencell-worktrees\main-integrate\data\m1_sources\karr_native\per_process_traces_v2_s001..\s049\ProteinProcessingII_100ticks.mat`
- Matching upstream translocation traces:
  - `...\ProteinTranslocation_100ticks.mat` in the same 50 directories

No later natural `ProteinProcessingII_*.mat` windows were found in the shared
`karr_native` tree. No existing PPII full-cycle event scan artifact was found.

### Operational preflight

- `E:\MATLAB\bin\matlab.exe` exists.
- Shared MATLAB lock path `E:\opencell-worktrees\.opencell-matlab-lock` was
  absent at inspection time, so this turn was **not** blocked on lock
  contention.

## Source-Faithful Karr Lifecycle Conditions

### ProteinTranslocation -> ProteinProcessingII handoff

From `ProteinTranslocation.m`:

- `ProteinTranslocation` operates on `this.monomer.processedIIndexs`, not on a
  synthetic side pool.
- It moves processed-I monomers from cytosol into their destination
  compartment:
  - extracellular proteins -> extracellular compartment
  - lipoproteins -> membrane compartment
- It writes the updated processed-I cube back to simulation state via
  `this.monomer.counts(this.monomer.processedIIndexs, :, :) = this.monomers`.

From `ProteinProcessingII.m`:

- `copyFromState` reads `this.monomer.counts(this.monomer.processedIIndexs,
  this.monomerCompartments)` into `this.unprocessedMonomers`.
- Therefore the real natural prerequisite for any PPII activity is:
  **processed-I lipoprotein/secretory monomers must already exist in their
  destination compartments when PPII runs.**

### PPII branch structure from source

`ProteinProcessingII.evolveState` has three biologically distinct phases:

1. Non-lipoprotein / non-secreted pass-through:
   - unconditional
   - moves `unprocessedMonomerIndexs` directly into `processedMonomers`
2. Early-return gate:
   - if no unprocessed lipoprotein/secreted monomers exist, PPII returns
3. Coupled lipoprotein/secretory processing:
   - block 1: lipoprotein transferase + peptidase
   - block 2: residual secretory peptidase-only cleanup

The H12 sentinel specifically cares about the closed-form branch tag
`transferase_fires`, which requires:

- `transferase_demand > 0`
- and the H12 `regime_valid` guard to hold:
  - peptidase capacity >= peptidase demand
  - transferase capacity >= transferase demand
  - water >= peptidase demand
  - `PG160 >= transferase_demand`

If water or `PG160` are insufficient, Karr falls into the scarcity/rationing
path that uses `this.randStream.mnrnd(...)`. That path is biologically real but
does **not** satisfy the current natural-trace H12 closed-form confirmation
requirement.

## Corrected Existing-Data Findings

## Important correction

An earlier probe conclusion that the entire 50-seed 100-tick natural corpus was
all-zero for PPII target occupancy was wrong. Re-reading the shared traces
directly from WSL against the actual HDF5 layout shows real natural PPII target
activity inside the existing 100-tick corpus.

### What is true for the authoritative 20-tick H12 cohort

The current H12 artifact is still honestly non-confirming:

- first `20` ticks: `0/50` seeds exercise regime-valid `transferase_fires`
- this is why the stored verdict remains `H12_OBSERVED_REGIME`

### What is true in the broader existing 100-tick corpus

Across the shared natural `ProteinProcessingII_100ticks.mat` 50-seed corpus:

- `50/50` seeds show some PPII target occupancy (`lipoprotein or secretory`)
  within 100 ticks
- earliest any-target `unprocessedMonomers` tick: `3`
- `44/50` seeds show lipoprotein transferase demand within 100 ticks
- earliest lipoprotein-demand tick: `35`
- first-demand histogram:
  - tick `35`: 2 seeds
  - `36`: 1
  - `37`: 6
  - `38`: 9
  - `39`: 3
  - `40`: 10
  - `41`: 5
  - `43`: 4
  - `44`: 4
- seeds with no lipoprotein demand by tick 100:
  - `1, 4, 8, 11, 20, 41`

When the stricter H12 closed-form guard is applied to those same natural 100
ticks:

- `28/50` seeds already contain at least one regime-valid natural transferase
  window within 100 ticks
- earliest regime-valid transferase tick: `37`
- first regime-valid transferase ticks observed as late as `99`
- `22/50` seeds are still not covered by tick 100:
  - `0, 1, 4, 7, 8, 9, 11, 12, 14, 16, 17, 18, 20, 25, 28, 30, 31, 32, 33, 36, 41, 49`

Those `22` uncovered seeds split into:

- `6` seeds with **no lipoprotein demand by tick 100**:
  - `1, 4, 8, 11, 20, 41`
- `16` seeds with **lipoprotein demand present but no regime-valid transferase
  window by tick 100**:
  - `0, 7, 9, 12, 14, 16, 17, 18, 25, 28, 30, 31, 32, 33, 36, 49`

At first lipoprotein-demand ticks, the dominant natural blocker is not enzyme
capacity. It is metabolite scarcity:

- every invalid first-demand tick failed `PG160 >= transferase_demand`
- `20` of those also failed `water >= peptidase_demand`
- no observed first-demand failure was due to peptidase or transferase enzyme
  rate limits

This matters because the true search target is **not** just “first lipoprotein
appears”. It is “first tick where lipoprotein demand is present and the natural
closed-form water/PG160 guard is satisfied”.

## Earliest Natural Active Window From Existing Data

Using existing source + shared traces:

- earliest secretory-only PPII target occupancy appears at ticks `3-4`
- earliest lipoprotein demand appears at tick `35`
- earliest regime-valid natural transferase window appears at tick `37`

So the earliest plausible natural active search window is not “somewhere after
100”; it begins in the **mid-30s**. The current H12 miss is specifically a
birth-window problem (`M_ticks=20`), not a proof that natural transferase
biology is absent from the 100-tick source-faithful corpus.

## Targeted Extraction Plan

### What the data says to do

1. Keep the existing shared 100-tick natural traces as the source of truth for
   the already-covered `28` seeds.
2. Search only the remaining `22` uncovered seeds beyond tick `100`.
3. Search for the first tick satisfying the actual H12 closure condition:
   - `transferase_demand > 0`
   - `regime_valid == True`
4. Extract a fixed `20`-tick window starting at that seed-specific first valid
   tick.

### Exact source-faithful MATLAB extraction shape

Extractor contract already supports fixed later windows:

```matlab
extract_per_process_traces_v2(process_names, output_subdir, n_ticks, seed, tick_offset, 'fixed')
```

For PPII this should be used in two stages:

1. Search stage for the 22 uncovered seeds:
   - run `ProteinProcessingII` later fixed windows in chunks beyond tick 100
   - suggested first chunk: `tick_offset=100`, `n_ticks=100`
   - continue with `tick_offset=200`, `300`, ... only for still-uncovered seeds
2. Capture stage:
   - once seed `s` first hits regime-valid transferase at absolute tick `t_s`,
     extract a dedicated active window with:
     - `seed = s`
     - `tick_offset = t_s - 1`
     - `n_ticks = 20`
     - `window_contract = 'fixed'`

That preserves:

- source-faithful Karr simulation
- the authoritative `M_ticks: 20`
- explicit tick provenance via `metadata.tick_offset`, `tick_start`, `tick_end`

### Why not use the synthetic Scenario B canary

Because Scenario B is deliberately scarcity-constructed and non-gating:

- it is not the natural 50-seed evidence path
- it does not close the natural H12 `transferase_fires` requirement
- it must remain a non-gating support artifact only

### Why not use the project `mnrnd` shim for H12 closure

Because the genuine MATLAB Scenario B / scarcity semantics are bound to
WholeCell `RandStream.mnrnd` -> MATLAB Statistics Toolbox `mnrnd`, and the
project shim consumes RNG differently. Swapping it in would change the
per-seed realization and would not be valid closure evidence.

## Mechanical Verdict Blocker

I do **not** have a final mechanical green verdict this turn.

The shortest exact blocker is now two-part:

1. **Source/data blocker**
   - the existing shared natural corpus only gives regime-valid transferase
     windows for `28/50` seeds by tick 100
   - later natural windows for the remaining `22` seeds have not yet been
     extracted
2. **Tooling blocker**
   - `scripts/l22_evidence/h12.py` is currently hard-wired to load only the
     canonical birth-window traces:
     - seed 0: `data/m1_sources/karr_native/per_process_traces_v2/<Process>_100ticks.mat`
     - seeds 1-49: `per_process_traces_v2_s###/<Process>_100ticks.mat`
   - it then truncates to the first `M_ticks` rows
   - there is no current manifest/CLI support for consuming per-seed later
     fixed windows honestly

So even if the missing 22 later windows were extracted immediately, the current
mechanical H12 producer cannot consume them without a scoped loader/input-manifest
extension.

## Shortest Executable Unblock

1. Add an explicit non-default trace-manifest input path to
   `scripts/l22_evidence/h12.py` so it can read a reviewer-visible list of
   per-seed later-window `.mat` files instead of only the birth-window
   canonical paths.
2. Under the shared MATLAB lock, search the 22 uncovered seeds in 100-tick
   fixed windows beyond tick 100 until each seed reaches its first natural
   regime-valid transferase tick.
3. Extract one 20-tick fixed active window per seed at `tick_offset=t_s-1`.
4. Re-run ProteinProcessingII H12 against that 50-file manifest.
5. Regenerate `docs/phase_f/l2_2_design_a/evidence_index.json` and inspect
   whether the PPII row clears `SENTINEL_FAIL`.

## Bottom Line

- The current first-20 natural cohort still does **not** support
  `H12_CONFIRMED`.
- Natural transferase-active biology is already present much earlier than the
  full-cycle canary implied:
  - earliest demand: tick `35`
  - earliest regime-valid transferase: tick `37`
- Existing source-faithful 100-tick traces already cover `28/50` seeds for the
  actual H12 closure condition.
- The honest remaining job is not “invent a canary”; it is:
  - extract later natural windows for the remaining `22` seeds
  - and teach the H12 loader to consume those later fixed windows mechanically.
