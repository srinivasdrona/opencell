# STATUS_L22_PPII_ISOLATED

## Outcome

- Added a process-local PPII active-window runner at
  `scripts/l22_evidence/ppii_active_windows.py`.
- Kept `scripts/l22_evidence/h12.py` byte-identical and unedited.
- Ported the sibling branch's covered-28 manifest into this worktree at
  `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_active_window_manifest.covered28.json`.
- Verified all 28 covered entries against the current live natural traces in
  `E:\opencell-worktrees\main-integrate\data\m1_sources\karr_native\...`.
- Added focused tamper / staleness / default-isolation tests.
- Remaining 22 seeds stay an explicit real-MATLAB-license extraction gap.

Terminal status for this turn: `READY_FOR_FULL50_MANIFEST_WHEN_MATLAB_RETURNS`.

## Why This Exists

The sibling implementation (`wave-l22-procii`, through `53b5981`) proved the
useful mechanism, but it added manifest/slice support directly to shared
`scripts/l22_evidence/h12.py`. Main reverted that because changing shared
`h12.py` staled `ProteinFolding`, `ProteinProcessingI`, and
`tRNAAminoacylation` H12 support.

This isolated reimplementation preserves the useful part while leaving shared
H12 untouched:

- manifest parsing and per-seed hash binding now live in
  `scripts/l22_evidence/ppii_active_windows.py`
- trace slicing now happens there too
- prediction / compare / verdict logic still comes from unchanged shared
  `scripts/l22_evidence/h12.py`

## Deliverables

### 1. Isolated process-local runner

Committed in `53b5304`:

- `scripts/l22_evidence/ppii_active_windows.py`

What it does:

- parses `h12_trace_window_manifest_v1` manifests for `ProteinProcessingII`
- hash-binds each source trace before reading any slice
- validates source MAT structure against the expected process / seed / tick span
- slices the requested 20-tick window out of the source 100-tick trace
- re-derives the first regime-valid `transferase_fires` tick from the current
  source trace using the unchanged shared `h12.PREDICTORS["ProteinProcessingII"]`
- reuses shared `h12.compare_predictions(...)` and `h12.decide_verdict(...)`
- emits a NON-GATING validation artifact/report that records:
  - manifest hash
  - generator hash
  - unchanged shared `h12.py` hash
  - fixture hash
  - per-seed source-trace hashes
  - per-seed first-transferase-tick verification
  - exact-match / branch-coverage totals
  - `shared_h12_promotion_ready` (false for covered-28 because 22 seeds remain missing)

Important isolation detail:

- the runner accepts source traces outside this worktree and still cross-checks
  them against the tracked `oracle_population_manifest.json` by deriving the
  relative `data/m1_sources/karr_native/...` suffix from the real path. That
  was required because this isolated worktree only contains a stub local
  `karr_native` tree, while the live current PPII traces are in
  `main-integrate`.

### 2. Ported covered-28 manifest

Committed in `53b5304`:

- `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_active_window_manifest.covered28.json`

Manifest facts:

- schema: `h12_trace_window_manifest_v1`
- process: `ProteinProcessingII`
- window length: `20`
- covered seeds: `28`
- uncovered seeds: `22`
- source population root:
  `../../../../../main-integrate/data/m1_sources/karr_native`

The file is the sibling branch's covered-28 manifest, ported into this
worktree and left pointed at the live current trace corpus it was actually
validated against.

### 3. Focused regression tests

Committed in `53b5304`:

- `tests/scripts/test_ppii_active_windows.py`

Coverage added:

- synthetic manifest + slice loading through the new process-local runner
- CLI output path / non-gating report behavior
- tamper fail-closed on source-trace hash mismatch
- staleness fail-closed on shared `h12.py` hash drift
- default-isolation check that the tracked canonical
  `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_h12.json` still points at
  the current shared `h12.py` hash

## Verification

### Shared H12 remained untouched

- `git diff -- scripts/l22_evidence/h12.py`
  - result: empty diff
- `git hash-object -- scripts/l22_evidence/h12.py`
  - current blob hash: `96967eac123274f3dbe59a08dfcd1b43667ecedf`
- the tracked canonical
  `docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_h12.json` still records
  shared predictor hash
  `aee4b9b89219284c9cd570d4208f39e95a89d657f3604c683a9908fdf883fd10`, and the
  new isolation test confirms that still matches on-disk `h12.py`

### Tests

Run via WSL wrappers:

- `.\bin\oc-pytest.cmd tests/scripts/test_ppii_active_windows.py -q`
  - `5 passed`
- `.\bin\oc-pytest.cmd tests/scripts/test_ppii_active_windows.py tests/scripts/test_h12_artifact.py tests/scripts/test_h12_anticheat.py -q`
  - `30 passed`

### Real covered-28 validation run

Run via WSL wrapper:

- `.\bin\oc-py.cmd scripts/l22_evidence/ppii_active_windows.py --manifest docs/phase_f/l2_2_design_a/h12/ProteinProcessingII_active_window_manifest.covered28.json --out tmp/ppii_active_window_validation.covered28.json`

Observed result:

- `seeds=28/50`
- `window_verdict=H12_CONFIRMED`
- `shared_h12_promotion_ready=False`
- every covered entry re-derived the recorded
  `first_regime_valid_transferase_tick`
- every covered entry cross-checked `match` against
  `docs/phase_f/l2_2_design_a/oracle_population_manifest.json`

The generated report lives at:

- `tmp/ppii_active_window_validation.covered28.json`

It is intentionally untracked; the tracked status + manifest + tests are the
durable record for this turn.

## Remaining Gap

Still missing from full closure:

- seeds `0, 1, 4, 7, 8, 9, 11, 12, 14, 16, 17, 18, 20, 25, 28, 30, 31, 32, 33, 36, 41, 49`

Why they remain open:

- the current shared natural corpus still only gives 100-tick PPII traces
- those 22 seeds need later natural windows beyond tick 100
- per task contract, I did not run MATLAB here
- the sibling branch already narrowed the blocker to real MATLAB licensing, and
  this isolated runner is now ready to consume the future 50-entry manifest
  without any shared H12 hash change

## Commit

- `53b5304` — `feat: isolate PPII active-window validation`

## Uncommitted Progress File

- `STATUS_L22_PPII_ISOLATED.progress.md`
