# STATUS batch-a-deep

## Beat 1 - SUT inspection

- Read in order:
  - `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md`
  - `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md`
  - `docs/prompts/COMPOSITION_MANDATE_v2.md`
  - task prompt / quoted catalog entries
- Read surfaces requested by task:
  - `opencell/vivarium/karr_protein_processing_i.py`
  - `opencell/vivarium/karr_protein_processing_ii.py`
  - `tests/vivarium/_l2_2_design_a_runner_helpers.py:830-870`
  - `tests/vivarium/_l2_2_design_a_runner_helpers.py:_run_protein_decay_tick`
  - `tests/vivarium/l2_2_design_a_runner.py:600-650`

## Contract

- Wire only `ProteinProcessingI` and `ProteinProcessingII` into the L2.2 Design-A runner.
- Catalog is authoritative:
  - bucket=`TRIVIAL_RNG`
  - `M_ticks=20`
  - `N_seeds=50`
  - input=`[substrates, enzymes, monomers]`
  - output=`[substrates, monomers]`
  - primary=`monomers`
  - artifact=`per_process_traces_v2`
- Dispatcher must not pass `trace_hint`.
- Known laundering alarm to document, not fix: `W1=0.0 + KS p=1.0 = Macromol pattern`.

## Findings

- `tests/vivarium/_l2_2_design_a_runner_helpers.py` does not currently import or construct either process.
- `_oracle_dispatch()`, `_required_ensemble_keys()`, `_format_ensemble_oracle()`, and `_tick_dispatch()` do not currently support either process.
- `tests/vivarium/l2_2_design_a_runner.py` does not currently include either process in `_process_sample_process()`, `_observable_wids()`, or the per-sample state wiring inside `run_design_a()`.
- Workspace-local `data/m1_sources/karr_native/` does not contain the 50-seed mats for either process.
- Shared data root `E:/opencell/data/m1_sources/karr_native/` does contain 50 seeds for both:
  - `per_process_traces_v2_s000..s049/ProteinProcessingI_100ticks.mat`
  - `per_process_traces_v2_s000..s049/ProteinProcessingII_100ticks.mat`
- The v2 trace schema for these two processes is not a literal `monomers` channel:
  - `ProteinProcessingI` before/after keys: `boundEnzymes`, `enzymes`, `processedMonomers`, `substrates`, `unprocessedMonomers`
  - `ProteinProcessingII` before/after keys: `boundEnzymes`, `enzymes`, `processedMonomers`, `signalSequenceMonomers`, `substrates`, `unprocessedMonomers`
- The existing generic `l2_replay_common.observable_store_path("monomers", ...)` maps to the unprocessed monomer store (`protein.unprocessed_counts` when present, else `protein.counts`), so the most consistent Design-A interpretation of catalog `monomers` for these two processes is `unprocessedMonomers`.
- `ProteinProcessingII` also emits `signalSequenceMonomers`, but catalog output scope is still only `substrates` and `monomers`; that extra channel should remain non-gating and out of this wiring.
- Template choice remains `_run_protein_decay_tick`: overlay substrates + enzymes + monomers from oracle-before, refresh allocator views, call `next_update()` without `trace_hint`, apply delta, project substrates + monomers back out.

## Expected smoke caveat

- Historical note from task: substrate-cliff secondary FAILs are expected for `ProteinProcessingI/II`.
- L2.2 gate for this task is primary channel `monomers`, so any substrate-only smoke concern should be documented, not treated as a blocker.

## Beat 2 - dispatchers

- Added helper-layer support in `tests/vivarium/_l2_2_design_a_runner_helpers.py` for:
  - `ProteinProcessingI`
  - `ProteinProcessingII`
- Added:
  - legacy oracle loaders mapping Design-A `monomers` to `unprocessedMonomers`
  - v2 ensemble formatting support for both processes
  - shared-root fallback to `E:/opencell/data/m1_sources/karr_native` for both processes
  - cached process constructors
  - `_run_protein_processing_i_tick()`
  - `_run_protein_processing_ii_tick()`
  - `_tick_dispatch()` entries
- Verification:
  - `bin/oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q`
  - result: `37 passed`

## Beat 3 - wire runner

- Wired `tests/vivarium/l2_2_design_a_runner.py` for both processes:
  - `_process_sample_process()`
  - `_observable_wids()`
  - `run_design_a()` sample-state branch for `oracle_before_monomers` / `oracle_after_monomers`
- Tightened `tests/vivarium/test_l2_2_design_a_runner_catalog.py` so `SUPPORTED_PROCESSES` explicitly includes:
  - `ProteinProcessingI`
  - `ProteinProcessingII`
- Verification:
  - `bin/oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q`
  - result: `37 passed`

## Beat 4 - inversion

- Added `tests/vivarium/test_l2_2_design_a_runner_protein_processing_anticheat.py`.
- Falsifiers added per process:
  - primary-channel anti-laundering: tick helper must not replay `oracle_after_monomers`
  - distance falsifier: runner must fail when `monomers` is forced to a large wrong vector while `substrates` still match
- Verification:
  - `bin/oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q`
  - result: `41 passed`
- Notes:
  - The synthetic distance falsifiers intentionally use a low-variance oracle surface so null-bootstrap spread stays small and the monomer mismatch is decisively gateable.
  - The new synthetic tests emit SciPy precision-loss warnings for skew/kurtosis on nearly constant arrays; pytest remains green and the warnings are non-blocking.

## Beat 5 - smoke gates

- Command:
  - `bin/oc-py.cmd tests/vivarium/l2_2_design_a_runner.py --process ProteinProcessingI --seeds 50 --ticks 10 --bootstrap-B 200 --output-dir tests/vivarium/artifacts/l2_2_design_a/ProteinProcessingI_batch_a_smoke`
  - `bin/oc-py.cmd tests/vivarium/l2_2_design_a_runner.py --process ProteinProcessingII --seeds 50 --ticks 10 --bootstrap-B 200 --output-dir tests/vivarium/artifacts/l2_2_design_a/ProteinProcessingII_batch_a_smoke`

### ProteinProcessingI

- output_dir: `tests/vivarium/artifacts/l2_2_design_a/ProteinProcessingI_batch_a_smoke`
- verdict: `PASS`
- canonical_seed_count: `50`
- primary channel: `monomers`
- primary verdict: `SEED_NOISE`
- primary W1: `0.0`
- primary KS p-value: `1.0`
- primary threshold: `1.0`
- warnings: `[]`
- note:
  - LAUNDERING ALARM documented only: primary channel shows the Macromol pattern (`W1=0.0` + `KS p=1.0`).
  - No fix applied per task instruction.

### ProteinProcessingII

- output_dir: `tests/vivarium/artifacts/l2_2_design_a/ProteinProcessingII_batch_a_smoke`
- verdict: `PASS`
- canonical_seed_count: `50`
- primary channel: `monomers`
- primary verdict: `INSUFFICIENT_SAMPLES`
- primary W1: `0.0`
- primary KS p-value: `1.0`
- primary threshold: `1.0`
- warnings: `[]`
- note:
  - LAUNDERING ALARM documented only: primary channel again shows the Macromol pattern (`W1=0.0` + `KS p=1.0`).
  - The primary channel has only `27` nonzero samples in the smoke run, so runner verdict is `INSUFFICIENT_SAMPLES` on the primary while overall process verdict remains `PASS` via the secondary substrate channel.
  - Substrate-cliff secondary concerns remain expected/non-blocking for this task.
