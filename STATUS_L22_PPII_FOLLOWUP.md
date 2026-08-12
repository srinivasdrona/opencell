# STATUS_L22_PPII_FOLLOWUP

## Outcome

- Loader/tests/manifests for the existing natural-coverage slice are complete.
- Full 50-seed closure is blocked externally on MATLAB licensing, not on the
  Python/H12 loader path.
- Terminal status for this turn: `READY_FOR_MATLAB_22`.

## Work Completed

### 1. H12 loader now supports explicit per-seed active-window manifests

Committed in `7f3d153`:

- `scripts/l22_evidence/h12.py`
  - added opt-in `--trace-window-manifest`
  - default no-manifest behavior remains the legacy canonical birth-window
    path, so every other process stays byte-identical unless this flag is used
  - manifest entries are hash-bound and carry:
    - `seed`
    - `process`
    - `trace_path`
    - `trace_sha256`
    - `trace_schema`
    - `trace_tick_start` / `trace_tick_end`
    - `window_tick_start` / `window_tick_end`
    - `window_length_ticks`
  - artifacts now record
    `oracle_trace_window_manifest_ref` when manifest mode is used
- `tests/scripts/test_h12_trace_window_manifest.py`
  - synthetic loader/CLI coverage for manifest-backed slicing and artifact
    provenance

Targeted WSL-wrapper verification on that chunk:

- PASS:
  - `.\bin\oc-pytest.cmd tests/scripts/test_h12_trace_window_manifest.py tests/scripts/test_h12_artifact.py tests/scripts/test_h12_anticheat.py -q`
  - summary: `29 passed`
- Unrelated baseline failure when broadening to
  `tests/scripts/test_h12_evidence_wiring.py`:
  - `MacromolecularComplexation.closed_form_dominant` is currently
    `candidate`, while the test still asserts
    `confirmed_biology_validated`
  - not introduced here and left untouched

### 2. Built the existing-data active-window manifest for the 28 covered seeds

Created:

- `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_active_window_manifest.covered28.json`

Manifest facts:

- schema: `h12_trace_window_manifest_v1`
- process: `ProteinProcessingII`
- window length: `20`
- source population root:
  `/mnt/e/opencell-worktrees/main-integrate/data/m1_sources/karr_native`
- covered seeds: `28`
- uncovered seeds still requiring later search: `22`
- manifest sha256 (raw file bytes):
  `d881863068df9ef88492eea931dafec7277c276119d1c185e0bc0f675480d3c8`

Selection policy used for the covered-28 entries:

- if the first regime-valid `transferase_fires` tick fit entirely inside the
  100-tick trace, the 20-tick window starts at that tick
- if the first regime-valid tick was later than tick `81`, the window is
  tail-aligned to ticks `81-100` and records the actual
  `first_regime_valid_transferase_tick` explicitly in the entry metadata
- no trace bytes were duplicated; every covered entry references the existing
  shared 100-tick trace plus a 20-tick slice contract

Covered seeds / first regime-valid transferase tick:

- `2:44, 3:38, 5:44, 6:38, 10:44, 13:73, 15:42, 19:95, 21:39, 22:52, 23:39, 24:78, 26:37, 27:90, 29:74, 34:83, 35:99, 37:42, 38:95, 39:73, 40:44, 42:62, 43:42, 44:45, 45:39, 46:40, 47:44, 48:78`

Still uncovered after the shared 100-tick corpus:

- `0, 1, 4, 7, 8, 9, 11, 12, 14, 16, 17, 18, 20, 25, 28, 30, 31, 32, 33, 36, 41, 49`

Manifest validation performed through the real loader/predictor path:

- `.\bin\oc-py.cmd tmp/ppii_scan_v3.py`
  - re-confirmed `28/50` covered and the same first-tick map above
- `.\bin\oc-py.cmd tmp/build_ppii_covered28_manifest.py`
  - generated the manifest
  - loaded it via `h12.load_trace_window_manifest(...)`
  - reloaded each 20-tick slice via `h12.load_oracle_seed(..., trace_window=...)`
  - re-ran `predict_protein_processing_ii(...)`
  - confirmed every one of the 28 selected windows still contains a real
    regime-valid `transferase_fires` tick

### 3. Re-verified the missing-data / MATLAB blocker

Natural-trace inventory check:

- searched
  `E:\opencell-worktrees\main-integrate\data\m1_sources\karr_native`
  recursively for `ProteinProcessingII*.mat`
- result: only the canonical `per_process_traces_v2` seed-0 file and
  `per_process_traces_v2_s001..s049` 100-tick files exist
- no pre-existing later fixed-window natural PPII traces were found

MATLAB lock/license check:

- found a stale empty lock directory from the earlier pass:
  `E:\opencell-worktrees\.opencell-matlab-lock`
- verified no live `matlab` process existed
- removed the stale lock directory
- reacquired the lock atomically for a fresh probe and removed it in `finally`
- probe command:
  - `E:\MATLAB\bin\matlab.exe -batch "disp('PPII_L22_LICENSE_PROBE'); disp(version);"`
- measured result on 2026-08-12:
  - `MathWorks Licensing Error 10`
  - `Your license for MATLAB has expired.`
  - exit failure before any extraction could begin

## Why Full Closure Did Not Land

The remaining source/tool blocker is now precise:

1. The shared natural trace tree only contains 100-tick PPII traces.
2. `22/50` seeds still need later natural search beyond tick `100` to find the
   first `transferase_demand > 0 && regime_valid` tick.
3. The only source-faithful way to extract those later windows on this machine
   is real MATLAB/Karr execution without routing through `scripts/matlab/mnrnd.m`
   or the synthetic Scenario B canary.
4. That real MATLAB path is currently unavailable because MATLAB itself will
   not start: license expired (`Licensing Error 10`).

Because of that external blocker, I could not honestly:

- extract the missing 22 later natural windows
- extend the manifest to all 50 seeds
- rerun the real H12 producer on a complete 50-entry active-window manifest
- promote `ProteinProcessingII_h12.json` from `H12_OBSERVED_REGIME` to
  `H12_CONFIRMED`

## Next Exact Step Once MATLAB Is Restored

1. Reacquire `E:\opencell-worktrees\.opencell-matlab-lock`.
2. Use the no-shim MATLAB path only:
   - temp-copy `scripts/matlab`
   - remove only `mnrnd.m` from that temp copy
   - run `extract_per_process_traces_v2(..., tick_offset, 'fixed')` from the
     temp directory so toolbox `mnrnd` is used
3. Search the 22 uncovered seeds in later fixed windows beyond tick `100` for
   the first `transferase_demand > 0 && regime_valid` tick.
4. Capture or reference exactly 20 ticks from that absolute tick for each
   remaining seed.
5. Extend the manifest from covered-28 to full-50.
6. Rerun:
   - `.\bin\oc-py.cmd scripts/l22_evidence/h12.py ProteinProcessingII --trace-window-manifest <full_manifest>`
7. Only if that full run returns complete branch coverage may the row become
   `H12_CONFIRMED`.

## Current Mechanical Truth

- Loader support: complete
- Test support: complete for the loader/CLI chunk
- Existing-data manifest support: complete for the 28 seeds already covered by
  natural 100-tick traces
- Remaining blocker: expired local MATLAB license
- Turn result: `READY_FOR_MATLAB_22`
