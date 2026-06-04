# STATUS — GATE_A Translation L2.2 (Honest First Signal)

## Scope + Verdict
- Task objective completed: F1 wired into runner, F2 wired into gate comparator, OC ensemble regenerated, full gate run executed, verdict reported without threshold/channel tampering.
- Gate result: **FAIL** (expected/acceptable for first honest signal).
- Pytest assertion payload: `ks_failure_count=398`, `wasserstein_failure_count=400`.

## F1 Wiring (Runner)
File: `tests/vivarium/_l2_2_ensemble_runner.py`

- Added fitted-init plumbing imports + seed MAT root constants for Translation ensembles at lines 29-57.
- Added per-seed MAT resolver `_karr_seed_mat_path` at lines 80-81.
- Added `_build_fitted_channel_map` using fixture Karr WIDs + process OC WIDs (substrates/enzymes/boundEnzymes) at lines 84-102.
- Added `_apply_fitted_init` calling `load_fitted_init_from_mat(...)` then `overlay_observable_into_state(...)` before tick 0 at lines 105-127.
- Wired fitted-init injection into seed execution path in `_run_translation_seed(...)` at lines 180-189.

Behavioral effect:
- Each OC seed now starts from that seed's corresponding Karr `states_before[0]` projection rather than cold schema zeros for fitted channels.

## F2 Wiring (Gate Comparator)
File: `tests/vivarium/test_l2_2_translation.py`

- Added `l2_replay_common` imports for `load_fixture_channel_wids` and `wasserstein_over_wid_intersection` at line 18.
- Added substrate-specific WID-aware loading/projection helpers at lines 116-242.
- `_build_substrates_intersection_samples()` now routes every seed/tick substrate compare through `wasserstein_over_wid_intersection(...)`, then aggregates projected vectors for KS/W1 population tests (lines 165-242).
- Added intersection consistency guards (same intersection and dropped sets across all seed/tick) at lines 205-221.
- Added metadata checks for per-seed OC WID maps (lines 245-254).
- `_build_sample_cube()` now applies intersection path only to `substrates`; other observables retain existing comparator path (lines 297-327).
- Added audit payload into `comparison_report.json` as `substrates_intersection_audit` (line 443).

## Tick-0 W1 Table (Pre vs Post Wiring)
Pre values are inferred from the pre-wiring artifact set used by `STATUS_l22_translation_v1.md` (`git show 80acebe^:data/opencell_ensembles/translation/wasserstein_failures.csv`).
Post values are measured from current run (`data/opencell_ensembles/translation/wasserstein_failures.csv`).

| observable | pre tick-0 W1 | post tick-0 W1 | delta |
|---|---:|---:|---:|
| substrates | 164692961.10000002 | 318.2600000000001 | -164692642.84 |
| enzymes | 826.08 | 13.06 | -813.02 |
| boundEnzymes | 289.92 | 38.08 | -251.84 |
| monomers | 16175.0 | 16175.0 | 0.00 |
| ribosome_state_active_count | 0.0 | 0.0 | 0.00 |
| ribosome_bound_mrnas_nonzero_count | 0.0 | 0.0 | 0.00 |
| ribosome_mrna_positions_sum | 0.0 | 0.0 | 0.00 |

## Gate Verdict by Channel (Post Wiring)
Source: `data/opencell_ensembles/translation/comparison_report.json` + failure CSVs from this run.

| observable | KS fail ticks | min Bonferroni p | W1 fail ticks | W1 max | verdict |
|---|---:|---:|---:|---:|---|
| substrates | 100 | 1.38763142299857e-26 | 100 | 23771.06 | FAIL |
| enzymes | 100 | 1.38763142299857e-26 | 100 | 31.64 | FAIL |
| boundEnzymes | 98 | 1.38763142299857e-26 | 100 | 38.08 | FAIL |
| monomers | 100 | 1.38763142299857e-26 | 100 | 16176.3 | FAIL |
| ribosome_state_active_count | 0 | 1.0 | 0 | 0.0 | PASS (non-comparable NaN-derived channel in runner) |
| ribosome_bound_mrnas_nonzero_count | 0 | 1.0 | 0 | 0.0 | PASS (non-comparable NaN-derived channel in runner) |
| ribosome_mrna_positions_sum | 0 | 1.0 | 0 | 0.0 | PASS (non-comparable NaN-derived channel in runner) |

Global gate verdict:
- `overall_pass = false`
- `ks_failure_count = 398`
- `wasserstein_failure_count = 400`

## Substrate WID Intersection Audit
From `comparison_report.json -> substrates_intersection_audit`:
- Karr substrate WIDs: 26
- OC substrate WIDs: 20
- Intersection WIDs: 20 (the amino-acid set)
- Dropped Karr WIDs: `FMET, GTP, GDP, PI, H2O, H`
- Dropped OC WIDs: none

## Commands + Runtime
- Regen command:
  - `bin\oc-py.cmd tests/vivarium/_l2_2_ensemble_runner.py --seeds 0:49 --force`
  - Wall-time: **65.752 s**
- Gate command:
  - `bin\oc-pytest tests/vivarium/test_l2_2_translation.py -q`
  - Full output captured at `data/opencell_ensembles/translation/gate_pytest_output.txt`

## Commit SHAs
1. `97db3bc` — `feat(l2.2-gate-translation): wire fitted_init into ensemble runner`
2. `e1dba87` — `feat(l2.2-gate-translation): apply WID intersection to substrates comparator`
3. `80acebe` — `regen(l2.2-gate-translation): re-run OC ensemble under fitted-init`
4. (this status + gate-run commit SHA added below after commit)

## Honest Interpretation
- The dominant artifacts targeted by this task are now removed from the measured surface:
  - Cold-start artifact reduced strongly on fitted channels (enzymes/boundEnzymes).
  - Substrate width mismatch is now explicitly handled via WID intersection with auditable dropped IDs.
  - Gate executes end-to-end with Bonferroni machinery unchanged (`_GLOBAL_ALPHA=0.01`).
- Residual failures are therefore meaningful fidelity gaps, with one known caveat:
  - `monomers` remains unchanged at tick-0 W1 (16175), consistent with previously documented semantic mismatch (delta-vs-absolute surface) rather than the F1/F2 artifacts.
  - The three ribosome summary channels still read as PASS because v1 runner emits NaN-backed non-comparable values; they should not be interpreted as biological agreement.
- Mechanism vs 4th-bug assessment:
  - For substrates/enzymes/boundEnzymes, the remaining gap is now mostly mechanism fidelity (real Karr-vs-OC behavior differences after artifact removal).
  - A likely 4th unresolved bug class remains on channel semantics/coverage (`monomers` delta-vs-absolute and summary-channel NaN comparability), which should be treated as measurement-surface debt, not evidence of agreement.
- Bottom line: this is an honest first L2.2 signal for Translation on the current gate surface; remaining divergence is mostly mechanism/surface mismatch, not the eliminated cold-start/WID-width artifacts.
