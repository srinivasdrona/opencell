Implemented on branch `trackF/trajectory-fixtures` in commit `bac5276` (`feat(validation): add trajectory-derived replay fixtures for truncated processes`).

### Delivered
- New builder script: [scripts/build_replay_fixtures_from_trajectory.py](E:/opencell-worktrees/trackB-trajectory-fixtures/scripts/build_replay_fixtures_from_trajectory.py)
- New quality test: [tests/unit/test_replay_fixture_quality_from_trajectory.py](E:/opencell-worktrees/trackB-trajectory-fixtures/tests/unit/test_replay_fixture_quality_from_trajectory.py)
- New trajectory fixture README: [README_trajectory_fixtures.md](E:/opencell-worktrees/trackB-trajectory-fixtures/data/karr_fixtures/per_process_replay/README_trajectory_fixtures.md)
- New status report: [STATUS_trackB_trajectory.md](E:/opencell-worktrees/trackB-trajectory-fixtures/STATUS_trackB_trajectory.md)
- 5 generated fixtures:
  - [Transcription_from_trajectory.npz](E:/opencell-worktrees/trackB-trajectory-fixtures/data/karr_fixtures/per_process_replay/Transcription_from_trajectory.npz)
  - [Translation_from_trajectory.npz](E:/opencell-worktrees/trackB-trajectory-fixtures/data/karr_fixtures/per_process_replay/Translation_from_trajectory.npz)
  - [RNADecay_from_trajectory.npz](E:/opencell-worktrees/trackB-trajectory-fixtures/data/karr_fixtures/per_process_replay/RNADecay_from_trajectory.npz)
  - [Replication_from_trajectory.npz](E:/opencell-worktrees/trackB-trajectory-fixtures/data/karr_fixtures/per_process_replay/Replication_from_trajectory.npz)
  - [ReplicationInitiation_from_trajectory.npz](E:/opencell-worktrees/trackB-trajectory-fixtures/data/karr_fixtures/per_process_replay/ReplicationInitiation_from_trajectory.npz)

### Verification
- Ran:
  - `py -3.12 scripts/build_replay_fixtures_from_trajectory.py --all-truncated`
  - `py -3.12 -m pytest tests/unit/test_replay_fixture_quality_from_trajectory.py -v`
- Result: **5/5 tests passed**.
- Extracted regime: `324` snapshots, `323` pairs, uniform `effective_dt_sec = 100.0`.

### Notes captured
- Documented isolated-vs-integration validation framing and tolerance guidance.
- Documented trajectory limitation: missing RNA/ProteinMonomer count channels in this export; extractor falls back to flat-fixture baseline for those channels.
- Existing truncated `_100ticks.mat` files were not modified.

### Option B follow-up
- Added flat snapshot builder: [scripts/build_replay_fixtures_from_flat.py](E:/opencell-worktrees/trackB-trajectory-fixtures/scripts/build_replay_fixtures_from_flat.py)
- Added flat fixture quality test: [tests/unit/test_replay_fixture_quality_from_flat.py](E:/opencell-worktrees/trackB-trajectory-fixtures/tests/unit/test_replay_fixture_quality_from_flat.py)
- Added flat fixture README: [README_flat_fixtures.md](E:/opencell-worktrees/trackB-trajectory-fixtures/data/karr_fixtures/per_process_replay/README_flat_fixtures.md)
- Added trajectory-script warning for Replication/ReplicationInitiation chromosome-state gap in [build_replay_fixtures_from_trajectory.py](E:/opencell-worktrees/trackB-trajectory-fixtures/scripts/build_replay_fixtures_from_trajectory.py)
- Generated flat-derived fixtures:
  - [Replication_from_flat.npz](E:/opencell-worktrees/trackB-trajectory-fixtures/data/karr_fixtures/per_process_replay/Replication_from_flat.npz) — 4,024 bytes
  - [ReplicationInitiation_from_flat.npz](E:/opencell-worktrees/trackB-trajectory-fixtures/data/karr_fixtures/per_process_replay/ReplicationInitiation_from_flat.npz) — 18,131 bytes
  - [ChromosomeCondensation_from_flat.npz](E:/opencell-worktrees/trackB-trajectory-fixtures/data/karr_fixtures/per_process_replay/ChromosomeCondensation_from_flat.npz) — 2,197 bytes
  - [DnaSupercoiling_from_flat.npz](E:/opencell-worktrees/trackB-trajectory-fixtures/data/karr_fixtures/per_process_replay/DnaSupercoiling_from_flat.npz) — 2,698 bytes
- Verification run (WSL venv):
  - `python -m pytest tests/unit/test_replay_fixture_quality_from_flat.py tests/unit/test_replay_fixture_quality_from_trajectory.py -v`
  - Result: **9/9 passed**
- Chromosome-state coverage gap is now closed for the four chromosome-focused replay fixtures via flat snapshot-oracle outputs and explicit chromosome payload capture (`initial__chromosome`).
