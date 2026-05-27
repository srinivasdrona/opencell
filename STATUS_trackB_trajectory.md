# STATUS Track-B Trajectory Fixtures

Date: 2026-05-27
Branch: `trackF/trajectory-fixtures`

## Scope completed

- Added `scripts/build_replay_fixtures_from_trajectory.py` (no MATLAB dependency).
- Generated 5 trajectory-derived replay fixtures:
  - `Transcription_from_trajectory.npz`
  - `Translation_from_trajectory.npz`
  - `RNADecay_from_trajectory.npz`
  - `Replication_from_trajectory.npz`
  - `ReplicationInitiation_from_trajectory.npz`
- Added trajectory-derived quality test:
  - `tests/unit/test_replay_fixture_quality_from_trajectory.py`
- Added trajectory fixture framing doc:
  - `data/karr_fixtures/per_process_replay/README_trajectory_fixtures.md`

## Extraction summary

All 5 processes extracted from `cell_cycle_trajectory.mat` with:

- `n_snapshots = 324`
- `n_pairs = 323`
- `effective_dt_sec` regime: uniform `100.0` seconds between snapshots

| Process | n_snapshots | n_pairs | dt regime (s) | fixture size (bytes) | substrate max abs delta |
|---|---:|---:|---|---:|---:|
| Transcription | 324 | 323 | [100.0] | 10580 | 41174.0 |
| Translation | 324 | 323 | [100.0] | 16526 | 41174.0 |
| RNADecay | 324 | 323 | [100.0] | 22963 | 41174.0 |
| Replication | 324 | 323 | [100.0] | 7717 | 41174.0 |
| ReplicationInitiation | 324 | 323 | [100.0] | 6426 | 41174.0 |

## Known anomalies / limitations

Trajectory export includes dynamic `Metabolite_counts` and `ProteinComplex_counts`, but does not include `Rna_counts` or `ProteinMonomer_counts` channels used by some enzyme/bound-enzyme mappings.

Applied behavior in extractor:

- Missing trajectory channels fall back to per-process flat fixture baseline vectors.
- This primarily affects RNA/monomer-dependent enzyme channels.
- Substrate channels remain trajectory-dynamic and non-trivial across all 5 processes.

Process-specific notes:

- `Transcription`: monomer enzyme/bound-enzyme components are baseline fallback.
- `Translation`: RNA + monomer enzyme/bound-enzyme components are baseline fallback; `monomers` channel remains baseline (all-zero vector in flat fixture).
- `RNADecay`: monomer enzyme/bound-enzyme components are baseline fallback.
- `Replication`: monomer enzyme/bound-enzyme components are baseline fallback; complex components are trajectory-dynamic.
- `ReplicationInitiation`: monomer enzyme/bound-enzyme components are baseline fallback; complex components are trajectory-dynamic.

## Validation status

Command:

```powershell
py -3.12 -m pytest tests/unit/test_replay_fixture_quality_from_trajectory.py -v
```

Result:

- 5 collected
- 5 passed
- 0 failed

## Notes for future MATLAB rerun

When MATLAB access is restored, rerun `scripts/matlab/extract_per_process_traces_fix.m` to regenerate isolated per-tick fixtures and cross-compare:

- isolated evidence channel (`*_100ticks.mat`)
- integration-coupled trajectory channel (`*_from_trajectory.npz`)
