# STATUS — L2.2 Ensemble Loader

## Catalog Universals (authoritative wiring contract)
```yaml
universals:
  N_seeds: 50
  default_M_ticks: 100
  karr_source_pattern: "data/m1_sources/karr_native/per_process_traces_v2_s{NNN}/{Process}_100ticks.mat"
  karr_source_seed_0_legacy: "data/m1_sources/karr_native/per_process_traces_v2/{Process}_100ticks.mat"
  karr_extractor: "scripts/matlab/extract_per_process_traces_v2.m"
```

## Live Log (UTC)
- 2026-06-08T07:32:04Z — Loaded required prompt docs (`DELIBERATE_ACTION_PREFIX_v2.md`, `FIX_TEMPLATE_L2_REPLAY.md`, `COMPOSITION_MANDATE_v2.md`) and the authoritative process catalog.
- 2026-06-08T07:32:04Z — Audited `tests/vivarium/_l2_2_design_a_runner_helpers.py` and `tests/vivarium/l2_2_design_a_runner.py` to pin the current oracle-loader contract and call site.
- 2026-06-08T07:32:04Z — Probed on-disk Karr layouts: legacy replay fixtures exist, `ensembles/transcription|translation/seed_000..049` are populated with `MANIFEST.json`, and catalog-layout `per_process_traces_v2_s{NNN}` is currently partial (`per_process_traces_v2_s001/Translation_100ticks.mat` present).
- 2026-06-08T07:32:04Z — Verification sweep: `bin\\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q` => `25 passed`.

## Beat 1 — Contract
- Required behavior: `load_karr_oracle(process)` must source Karr data according to the catalog’s `per_process_traces_v2` family when an ensemble exists, while remaining compatible with the runner’s existing dict contract.
- Done criterion: Translation and Transcription load N-seed canonical Karr data when available, partial v2 ensembles load defensively, and missing ensembles fall back to legacy single-seed NPZ with an explicit degraded-mode warning.

## Beat 1 — Current Surface
- Current loader signature: `load_karr_oracle(process: str) -> dict[str, Any]`.
- Current return contract: dict with `process`, `oracle_path`, `canonical_seed_count`, `n_ticks_available`, and per-channel tensors shaped `(seed, tick, dim)` under keys such as `before_substrates`, `after_substrates`, `before_bound_enzymes`, `after_monomers`, `before_rnas`.
- Current call site: `tests/vivarium/l2_2_design_a_runner.py` loads the oracle once in `run_design_a(...)`, then `_normalize_seed_axis(...)` either indexes real ensemble seeds or repeats a single seed across requested OC seeds.
- Current source selection: per-process single-seed loaders only, all hardwired to `data/karr_fixtures/per_process_replay/{Process}.npz`.

## Beat 1 — Disk Layout Audit
- Catalog v2 layout: `data/m1_sources/karr_native/per_process_traces_v2_s{NNN}/{Process}_100ticks.mat`.
- Current observed v2 status: partial/present-in-progress; at audit time `per_process_traces_v2_s001/Translation_100ticks.mat` exists, so the new loader must tolerate sparse seed availability and return only present seeds.
- Specialized legacy ensemble layout: `data/m1_sources/karr_native/ensembles/transcription/seed_NNN/Transcription_100ticks.mat` and `data/m1_sources/karr_native/ensembles/translation/seed_NNN/Translation_100ticks.mat`, both with parent `MANIFEST.json`.
- Legacy fallback layout: `data/karr_fixtures/per_process_replay/{Process}.npz` for existing single-seed replay fixtures.

## Beat 1 — Proposed Precedence
1. `per_process_traces_v2_s{NNN}` catalog layout.
2. `ensembles/<process>/seed_NNN` specialized pre-catalog layout.
3. Legacy `per_process_replay/{Process}.npz` fallback with `canonical_seed_count = 1` and `KARR_LEGACY_SINGLE_SEED_FALLBACK`.

## Pending
- Beat 2 — add `_load_v2_ensemble(process_name, max_seeds=50)`.
- Beat 3 — add `_load_ensembles_layout(process_name, max_seeds=50)`.
- Beat 4 — wire precedence into `load_karr_oracle`.
- Beat 5 — run full validation plus Translation/Metabolism smoke gates.

## Beat 2 — v2 Loader
- Added HDF5 MATLAB-cell resolution for `states_before/<channel>` and `states_after/<channel>` datasets, plus seed stacking across present `per_process_traces_v2_s{NNN}` files.
- `_load_v2_ensemble(process_name, max_seeds=50)` now returns `None` when zero seed MATs exist and otherwise returns the existing oracle dict shape with `canonical_seed_count = <present seeds>`.
- Added synthetic unit coverage in `tests/vivarium/test_l2_2_design_a_ensemble_loader.py` for 0-seed, 1-seed, and 3-seed v2 layouts.
- Verification: `bin\\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q` => `28 passed`.

## Beat 3 — Specialized Ensembles Loader
- Added `_load_ensembles_layout(process_name, max_seeds=50)` for `data/m1_sources/karr_native/ensembles/<process_lower>/seed_NNN/<Process>_100ticks.mat`.
- Loader cross-checks `MANIFEST.json` when present for seed count and observable schema before formatting the oracle dict.
- Real-disk Translation coverage added: the loader reads the existing 50-seed ensemble, returns `canonical_seed_count = 50`, and explicitly records `mRNAs` as a missing ensemble input channel supplemented from legacy NPZ.
- Verification: `bin\\oc-pytest.cmd tests/vivarium/test_l2_2_design_a*.py -q` => `29 passed`.
