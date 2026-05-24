# Bug 2 Fix: Real Karr Substrate Initial Counts

## Summary
Seeded the chassis v5/v6 shared `substrates` store from Karr's native M1 dynamics snapshot instead of the all-1.0 placeholder. `_M1_SUBSTRATE_DEFAULT = 1.0` remains as a defensive fallback for IDs missing from the snapshot map.

## NPZ inspection
- Array name: `substrates_snapshot`
- Shape: `(585, 3)`
- Dtype: `float64`
- NPZ files observed: `['substrates_snapshot', 'enzymes_snapshot', 'substrate_idx_fba_sub0', 'substrate_idx_fba_cmp0', 'substrate_idx_external_exch_0', 'substrate_idx_internal_lim_0', 'fba_rxn_idx_metab_conv', 'fba_rxn_idx_external_exch', 'fba_rxn_idx_internal_exch', 'fba_rxn_idx_internal_lim_exch', 'fba_rxn_idx_internal_unlim_exch', 'fba_rxn_idx_biomass_production', 'fba_rxn_idx_biomass_exchange', 'bounds_dynamic_no_protein', 'bounds_dynamic_with_protein']`
- First three substrate rows:
  - `[0.00000000e+00 2.79999999e-11 0.00000000e+00]`
  - `[0.00000000e+00 0.00000000e+00 0.00000000e+00]`
  - `[0.00000000e+00 0.00000000e+00 0.00000000e+00]`
- Column semantics: `data/karr_fixtures/karr_native_m1_dynamics.json` interpretation says `cols=[cytosol, extracellular, membrane]` for `substrates_snapshot`. Existing dynamic-mode loader confirms this by copying `dyn.substrates_snapshot` into `_sub_state` and reading `idx, _CYTOSOL_COMPARTMENT_0` as the shared cytosol default in `opencell/vivarium/karr_metabolism.py`.

## Substrate ID ordering
- `len(m1_model.raw["ids"]["substrate_wcm_585"]) == 585`
- `dyn.substrates_snapshot.shape[0] == 585`
- Ordering follows the same pattern as the dynamic-mode loader: enumerate `model.raw["ids"]["substrate_wcm_585"]` and use the row index into `dyn.substrates_snapshot`.
- Spot checks from row order:
  - `ATP`: index 29, cytosol `36234.0`
  - `GTP`: index 295, cytosol `36234.0`
  - `H2O`: index 297, cytosol `309737899.0`
  - `AD`: index 8, cytosol `0.0`
  - `URA`: index 558, cytosol `0.0`

## Code changes
- `opencell/vivarium/karr_composite.py:35`: import `calc_flux_bounds` as `cfb` to reuse `load_default_dynamics()`.
- `opencell/vivarium/karr_composite.py:97-114`: add `_KARR_CYTOSOL_COMPARTMENT_0` and `_load_karr_initial_substrate_counts()`.
- `opencell/vivarium/karr_composite.py:1444-1447`: seed M1 substrates from snapshot cytosol counts, falling back to `_M1_SUBSTRATE_DEFAULT`.
- `opencell/vivarium/karr_composite.py:10,22`: update module docstring references from placeholder counts to shared snapshot counts.
- Diff summary: 1 file changed, 24 insertions, 3 deletions.

## Test results
### Import smoke
```text
import ok
```

### B1 + B2 (target)
The requested test file is not present in this worktree, so pytest could not collect the named B1/B2 tests:

```text
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0 -- /mnt/e/opencell/.venv-wsl/bin/python
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: /mnt/e/opencell-worktrees/bug2-fix
configfile: pyproject.toml
plugins: anyio-4.13.0, hypothesis-6.152.1, jaxtyping-0.3.9, cov-7.1.0
collecting ... ERROR: file or directory not found: tests/integration/test_chassis_v6_biology_firing.py::test_b1_substrate_sanity_no_negative_core_substrates

collected 0 items

============================ no tests ran in 2.16s =============================
```

Manual equivalent checks against `build_karr_chassis_v6()` and a 5000-second engine run:

```text
core_initial {'ATP': 36234.0, 'GTP': 36234.0, 'H2O': 309737899.0, 'AD': 0.0, 'URA': 0.0}
core_final {'ATP': -2041988.5, 'GTP': -2041909.5, 'H2O': 309737601.0, 'AD': 0.0, 'URA': 0.0}
negative_core {'ATP': -2041988.5, 'GTP': -2041909.5}
```

- B2: GREEN by manual equivalent, observed `core_initial = {'ATP': 36234.0, 'GTP': 36234.0, 'H2O': 309737899.0, 'AD': 0.0, 'URA': 0.0}` and at least one of ATP/GTP/H2O is greater than 100.0.
- B1: RED by manual equivalent, observed `core_values = {'ATP': -2041988.5, 'GTP': -2041909.5, 'H2O': 309737601.0, 'AD': 0.0, 'URA': 0.0}`.

### Full biology canary
The requested full biology canary file is not present in this worktree:

```text
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0 -- /mnt/e/opencell/.venv-wsl/bin/python
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: /mnt/e/opencell-worktrees/bug2-fix
configfile: pyproject.toml
plugins: anyio-4.13.0, hypothesis-6.152.1, jaxtyping-0.3.9, cov-7.1.0
collecting ... ERROR: file or directory not found: tests/integration/test_chassis_v6_biology_firing.py

collected 0 items

============================ no tests ran in 1.25s =============================
```

Per-assertion result:
- A1: NOT RUN, test file absent from worktree.
- A2: NOT RUN, test file absent from worktree.
- A3: NOT RUN, test file absent from worktree.
- B1: RED by manual equivalent as above.
- B2: GREEN by manual equivalent as above.
- C1: NOT RUN, test file absent from worktree.
- D1: NOT RUN, test file absent from worktree.

### v6 smoke test (regression check)
PASS:

```text
tests/integration/test_karr_chassis_v6.py::test_v6_builds PASSED         [ 16%]
tests/integration/test_karr_chassis_v6.py::test_v6_one_tick PASSED       [ 33%]
tests/integration/test_karr_chassis_v6.py::test_v6_short_run_100s PASSED [ 50%]
tests/integration/test_karr_chassis_v6.py::test_v6_cpk_002_resolved PASSED [ 66%]
tests/integration/test_karr_chassis_v6.py::test_v6_cpk_003_resolved PASSED [ 83%]
tests/integration/test_karr_chassis_v6.py::test_v6_allocation_consumers_include_rna_decay_not_host_interaction PASSED [100%]

============================== 6 passed in 48.63s ==============================
```

### Dynamic-bounds tests (regression check)
PASS:

```text
tests/m1/test_dynamic_bounds_chassis.py::test_static_mode_default_and_unchanged_schema PASSED [  7%]
tests/m1/test_dynamic_bounds_chassis.py::test_static_mode_engine_emits_no_diagnostics_port PASSED [ 15%]
tests/m1/test_dynamic_bounds_chassis.py::test_static_mode_two_tick_flux_unchanged PASSED [ 23%]
tests/m1/test_dynamic_bounds_chassis.py::test_compute_bounds_does_not_mutate_inputs PASSED [ 30%]
tests/m1/test_dynamic_bounds_chassis.py::test_solve_fba_overrides_do_not_mutate_model PASSED [ 38%]
tests/m1/test_dynamic_bounds_chassis.py::test_dynamic_mode_schema_includes_diagnostics PASSED [ 46%]
tests/m1/test_dynamic_bounds_chassis.py::test_dynamic_mode_initial_internal_state_matches_snapshot PASSED [ 53%]
tests/m1/test_dynamic_bounds_chassis.py::test_dynamic_mode_first_tick_bounds_match_matlab_oracle PASSED [ 61%]
tests/m1/test_dynamic_bounds_chassis.py::test_dynamic_mode_drains_cytosol_from_shared_store_delta PASSED [ 69%]
tests/m1/test_dynamic_bounds_chassis.py::test_dynamic_mode_clamps_cytosol_at_zero PASSED [ 76%]
tests/m1/test_dynamic_bounds_chassis.py::test_dynamic_mode_isolated_from_shared_store_for_non_demand_keys PASSED [ 84%]
tests/m1/test_dynamic_bounds_chassis.py::test_dynamic_mode_end_to_end_60s_growth_positive PASSED [ 92%]
tests/m1/test_dynamic_bounds_chassis.py::test_dynamic_mode_end_to_end_atp_drains_under_m2_demand PASSED [100%]

============================= 13 passed in 26.88s ==============================
```

## Deviations from spec
- Test logs were written in the worktree (`bug2_fix_b1b2.log`, `bug2_full.log`, `bug2_smoke.log`, `bug2_dynamic_bounds.log`, `bug2_manual_5000.log`) instead of `/tmp` because this session forbids `/tmp` file operations.
- The requested biology canary file `tests/integration/test_chassis_v6_biology_firing.py` is absent from this worktree, so those pytest tests could not be collected. I ran manual B1/B2-equivalent checks and the available regression tests instead.

## Risks / known issues
- B1-equivalent manual check still has negative ATP/GTP after 5000 seconds. AD/URA did not go negative in this run.
- Because `dynamic_bounds` remains `False` as required, static-mode LP behavior is not rewired beyond shared initial substrate counts.
- Vivarium engine builds print `Simulation ID` / `Created` informational lines during manual checks; no unexpected engine-build warnings were observed.
