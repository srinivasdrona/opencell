# STATUS_gate_transcription

## C1 design (MATLAB extractor)
- File: `scripts/matlab/extract_transcription_ensemble.m`
- Snapshot channels captured (boundary snapshots only):
  - `substrates` (12-vector in Karr Transcription state)
  - `enzymes` (6-vector)
  - `boundEnzymes` (6-vector)
  - `RNAs` (335-vector)
- Rationale:
  - All four are process-state snapshots available directly on the MATLAB process object.
  - No delta-like channels were added.
  - Snapshots are captured with F3 semantics: `copyFromState` at global tick boundaries (before any process-local `evolveState` and after all process writes are applied).
- Output path:
  - `data/m1_sources/karr_native/ensembles/transcription/seed_<NNN>/Transcription_100ticks.mat`
  - `data/m1_sources/karr_native/ensembles/transcription/MANIFEST.json`

## C1 verification (seed_000 snap-eq)
All selected channels satisfy snap-eq >= 99%.

| channel | len@t0 | matches | total | snap-eq rate |
|---|---:|---:|---:|---:|
| RNAs | 335 | 99 | 99 | 100.00% |
| boundEnzymes | 6 | 99 | 99 | 100.00% |
| enzymes | 6 | 99 | 99 | 100.00% |
| substrates | 12 | 99 | 99 | 100.00% |

## C2 ensemble generation (50 seeds)
- Command run: MATLAB batch over `seed_list=0:49`, `n_ticks=100`.
- Manifest check: 50/50 seeds present, 0 missing.
- Timing (from manifest, generated seeds 1..49):
  - total generated wall-time: 835.303 s
  - mean per generated seed: 17.047 s
  - min/max per generated seed: 15.297 s / 34.162 s
- Batch wall-time (seed_000 reused + seeds 1..49 generated): ~851.1 s (~14.2 min).

## C3 + C4 wiring summary
- C3 runner file: `tests/vivarium/_l2_2_transcription_ensemble_runner.py`
  - Uses `opencell.vivarium.karr_transcription.KarrTranscriptionProcess` (v1).
  - Uses `load_fitted_init_from_mat` (fitted init applied to `substrates`, `enzymes`, `boundEnzymes`).
  - Writes `data/opencell_ensembles/transcription/seed_<NNN>/Transcription_100ticks.npz` + per-seed metadata + MANIFEST.
- C4 gate file: `tests/vivarium/test_l2_2_transcription.py`
  - Seeds: N=50, ticks=100.
  - Per-channel per-tick KS + W1, Bonferroni with `_GLOBAL_ALPHA=0.01`.
  - `substrates` uses `wasserstein_over_wid_intersection` before aggregation.
  - Writes:
    - `data/opencell_ensembles/transcription/comparison_report.json`
    - `data/opencell_ensembles/transcription/ks_failures.csv`
    - `data/opencell_ensembles/transcription/wasserstein_failures.csv`

## Gate run + verdict
Command:
- `bin\oc-pytest tests/vivarium/test_l2_2_transcription.py -q`

Result:
- FAIL (distributional mismatch)
- `ks_failure_count=381`
- `wasserstein_failure_count=396`

Per-channel verdict:

| channel | KS fails | W1 fails | KS p_bonf min | W1 max | W1 threshold max | verdict |
|---|---:|---:|---:|---:|---:|---|
| substrates | 100 | 100 | 7.929e-27 | 8729.06 | 1139.14 | FAIL |
| enzymes | 98 | 100 | 9.452e-18 | 1.92 | 1.012 | FAIL |
| boundEnzymes | 83 | 96 | 7.929e-25 | 2.76 | 0.9911 | FAIL |
| RNAs | 100 | 100 | 7.929e-27 | 783.40 | 1.8931 | FAIL |

Tick-0 sanity (fitted-init wiring):

| channel | tick0 W1 | tick0 KS p_bonf | note |
|---|---:|---:|---|
| substrates (intersection) | 4709.98 | 7.929e-27 | large mismatch remains |
| enzymes | 0.52 | 6.326e-04 | small absolute W1; fitted init is wired |
| boundEnzymes | 0.00 | 1.000 | exact at tick 0 |
| RNAs | 783.38 | 7.929e-27 | large baseline mismatch |

## Substrate intersection (Karr 12 vs OC 4)
- Intersection used in gate: `ATP`, `CTP`, `GTP`, `UTP`
- Dropped Karr WIDs (8):
  - `AMP`, `CMP`, `GMP`, `UMP`, `ADP`, `PPI`, `H2O`, `H`
- Dropped OC WIDs: none

## Commit SHAs
- C1: `53650d7` — `feat(l2.2-gate-transcription): C1 MATLAB extractor with snapshot-clean semantics`
- C2: `3cdbe23` — `feat(l2.2-gate-transcription): C2 50-seed Transcription ensemble manifest`
- C3: `e4304e8` — `feat(l2.2-gate-transcription): C3 Python ensemble runner with fitted init`
- C4: `fe5a2f7` — `feat(l2.2-gate-transcription): C4 distributional gate test`
- C5: (this commit) `test(l2.2-gate-transcription): full gate run — VERDICT in STATUS`

## Honest interpretation
- The snapshot-clean extraction contract is satisfied (100% snap-eq for all selected channels).
- Fitted-init is correctly injected for enzyme channels (tick-0 `boundEnzymes` exact; `enzymes` tick-0 W1 small).
- Despite that, Transcription v1 OpenCell dynamics are distributionally far from Karr across the 50-seed ensemble, especially for `substrates` and `RNAs`.
- This is a truthful RED gate: extraction/harness plumbing is functioning, but Karr-vs-OC fidelity for Transcription is currently insufficient under this L2.2 distributional criterion.
