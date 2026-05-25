# Track-B Replay Fixture Pipeline Summary

- Built `scripts/build_replay_fixtures.py` to convert MATLAB per-tick traces into replay-ready fixtures.
- Converter emits `data/karr_fixtures/per_process_replay/<Process>.npz` and `<Process>.json`.
- Output keys follow replay loader hints: `state_before__<prop>` and `states_after__<prop>`.
- Manifest includes `n_ticks`, `process_name`, `rng_seed`, `snapshot_properties`, `source_mat`, `schema_version`.
- Added loader extension in `opencell/validation/replay.py` to auto-prefer replay fixtures when available.
- Loader still falls back to legacy `data/karr_fixtures/per_process/` fixtures for processes without replay artifacts.
- Added unit coverage in `tests/unit/test_build_replay_fixtures.py` for stacking, manifest write, and variable-shape skipping.
- Added integration coverage in `tests/integration/test_replay_fixture_loaded.py` for Cytokinesis, ChromosomeCondensation, Transcription.
- Artifact decision: checked in replay artifacts for 3 representative processes because total size is ~6 KB (<5 MB threshold).
- Converter usage (single): `py -3.12 scripts/build_replay_fixtures.py --process Cytokinesis`
- Converter usage (all): `py -3.12 scripts/build_replay_fixtures.py --all`
- Pitfall observed: some native traces in this environment have 1-tick `states_before` and empty `states_after`.
- Converter handles this uniformly by warning, broadcasting single-tick inputs to `n_ticks`, and mirroring missing outputs from `state_before`.
- Validation: `py -3.12 -m pytest tests/unit/test_build_replay_fixtures.py tests/integration/test_replay_fixture_loaded.py -q --ignore=tests/gates` passed.
