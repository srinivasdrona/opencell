# STATUS: A6 ProteinTranslocation allocator enrollment

## Scope
Implemented A6 enrollment for `KarrProteinTranslocationProcess` in allocator paths, including dedicated request calculator wiring and v3/v4 enrollment tests.

## Files changed
- `opencell/vivarium/karr_protein_translocation.py`
  - Added `allocation_substrate_wids` (ATP/GTP/ADP/GDP/PI/H2O/H).
  - Added `protein.unprocessed_counts` port exposure for pending translocation queue input.
  - Updated translocation update path to consume queue-aware pending demand and emit substrate/protein deltas under allocator budget.
- `opencell/vivarium/karr_request_calculators.py`
  - Added `RequestCalculatorPTransloc`.
  - Exported in module `__all__`.
- `opencell/vivarium/karr_composite.py`
  - Wired PTransloc allocation enrollment and request calculator in `build_karr_chassis_v3` and `build_karr_chassis_v4`.
  - Added same request-calculator wiring into v5 path used by v6 smoke.
  - Updated PTransloc consumer/allocation substrate wiring to use `allocation_substrate_wids`.
- `tests/integration/test_ptransloc_enrollment_v3_v4.py`
  - Added v3/v4 consumer enrollment + request-calculator wiring assertions.

## Test results
Command:
`pytest tests/integration/test_ptransloc_enrollment_v3_v4.py tests/integration/test_allocator_enrollment_v3_v4.py tests/integration/test_chassis_v6_biology_firing.py -q --tb=short`

Result:
- `14 passed, 1 xfailed`

## 200-tick smoke
Command:
`python scripts/run_chassis_v6_32400t.py --seed 42 --biological-seconds 200 --out-dir /tmp/ptransloc_smoke --fresh`

Observed:
- `karr_protein_translocation.csv`: `10444` bytes, `185` lines.
- `request_calculator_protein_translocation.csv`: `52` lines.

Delta vs wave2-base context:
- `karr_protein_translocation.csv`: `21 B (header-only)` -> `10,444 B`.
