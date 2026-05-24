# Bug 3 Fix: Enable Dynamic FBA Bounds

## Edit confirmation
- Changed default dynamic-bounds flag for v6 chassis builder at:
  - `opencell/vivarium/karr_composite.py:1852`
- Exact change:
  - Before: `dynamic_bounds: bool = False`
  - After: `dynamic_bounds: bool = True`

## Diff summary
- Files changed: 1
- Net functional delta: single-line default flip in `build_karr_chassis_v6(...)`
- Verified no chassis-path caller forces static mode unexpectedly:
  - `grep -R -n --include='*.py' 'dynamic_bounds=False' opencell tests`
  - Matches found only in tests that intentionally exercise static mode:
    - `tests/m1/test_dynamic_bounds_chassis.py` (comment/regression guard)
    - `tests/vivarium/test_karr_metabolism_pools_throttle.py`
    - `tests/vivarium/test_karr_pool_replenishment.py`

## Test results

### 1) Import sanity
- Command: `from opencell.vivarium.karr_composite import build_karr_chassis_v6`
- Result: `import ok`

### 2) Smoke integration
- Command: `pytest tests/integration/test_karr_chassis_v6.py -v`
- Result: PASS
- Summary: `6 passed in 55.34s`
- Log: `bug3_smoke.log`

### 3) Dynamic-mode unit suites
- Command: `pytest tests/m1/test_dynamic_bounds_chassis.py tests/vivarium/test_karr_metabolism_pools_throttle.py tests/vivarium/test_karr_pool_replenishment.py -v`
- Result: PASS
- Summary: `40 passed in 37.33s`
- Log: `bug3_dyn_units.log`

### 4) Biology canary (5000 ticks)
- Command: `pytest tests/integration/test_chassis_v6_biology_firing.py -v`
- Result: PARTIAL
- Summary: `2 failed, 4 passed, 1 xfailed in 238.91s (0:03:58)`
- Log: `bug3_biology.log`

Per-gate outcomes (A1/A2/A3/B1/B2/C1/D1):
- A1: PASS
- A2: FAIL
- A3: PASS
- B1: FAIL
- B2: PASS
- C1: PASS
- D1: XFAIL (unchanged)

## Canary metrics and deltas (deterministic run, seed=0)
Source: `bug3_metrics.log` (same v6 build path and 5000-tick setup)

- A1 evidence:
  - `newly_expressed=386`
- A2 evidence:
  - `output_pool_increased=0` (fail criterion)
  - `mature_pool_increased=257`
- A3 evidence:
  - `max_MG_469=1.84894495047`
  - `max_MG_469_MONOMER=0`
- B1/B2 substrate values:
  - Initial core: `{'AD': 0.0, 'URA': 0.0, 'ATP': 36234.0, 'GTP': 36234.0, 'H2O': 309737899.0}`
  - Final core: `{'AD': 0.0, 'URA': 0.0, 'ATP': -2041988.5, 'GTP': -2041909.5, 'H2O': 309737601.0}`
  - Negative core at end: `{'ATP': -2041988.5, 'GTP': -2041909.5}`
- C1 ATP delta trajectory:
  - Status: **varying** (not constant)
  - `std=12.6856460225`
  - `min=-437.5`, `max=-400`
  - `first_delta=-437.5`, `last_delta=-400`
  - `unique_delta_count=4`
- D1 evidence:
  - `max_oric_bound_total=0`

## Infeasible-LP / NaN diagnostics
- Searched logs (`bug3_smoke.log`, `bug3_dyn_units.log`, `bug3_biology.log`, `bug3_metrics.log`) for `infeasible`, `RuntimeError`, `NaN`.
- No LP infeasibility exceptions observed during these runs.

## Performance note
- Current canary runtime (pytest): `238.91s`.
- Prior static-era canary reference in `STATUS_biology_firing_test.md`: `210.35s`.
- Observed delta: about `+28.56s` (~`+13.6%`) slower versus that prior reference run.
