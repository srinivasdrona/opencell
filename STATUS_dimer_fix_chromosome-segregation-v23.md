# STATUS — dimer fix chromosome segregation v23

## Verdict
L1-CHANGES-NEEDED

## Files changed
- `opencell/vivarium/karr_chromosome_segregation.py`
- `opencell/vivarium/karr_composite.py`
- `tests/vivarium/test_karr_chromosome_segregation.py`
- `tests/integration/test_karr_chassis_v6.py`
- `tests/unit/test_karr_chromosome_segregation_strict_zero.py`

## What was fixed
- Closed the declaration→read path gap in `KarrChromosomeSegregationProcess`:
  - Added canonical WID classification from fixture-backed complex sets (MacromolecularComplexation + RibosomeAssembly + fixed RNAP/ribosome IDs).
  - Split enzyme schema by class (`protein.counts` for monomer inputs, `complex.counts` for complex inputs).
  - Split gating read path by class.
  - Added fail-fast behavior for missing declared required inputs (no silent zero default).
- Closed topology link for this process in chassis:
  - Added `complex` topology wiring for `karr_chromosome_segregation` in `build_karr_chassis_v5` (inherited by v6).
- Closed seed link for this process in chassis-built state:
  - Seeded segregation complex enzyme WIDs in chassis `complex.counts` from segregation fixture enzyme counts (`MG_221_OCTAMER` and peers), using max(existing, fixture_seed).
- Updated test setup routing (setup-side only) so required complex enzymes are written to `complex.counts`.
- Added explicit tests for:
  - missing required complex input raises;
  - v6 chassis complex-seed gate (`MG_221_OCTAMER > 0`) and measurable effect on segregation progress.

## Test results
- `py -3.12 -m pytest -x tests/vivarium/test_karr_chromosome_segregation.py -q`
  - **8 passed**
- `py -3.12 -m pytest -x tests/integration/test_karr_chassis_v6.py -q`
  - **7 passed**
- Additional safety check:
  - `py -3.12 -m pytest -x tests/unit/test_karr_chromosome_segregation_strict_zero.py -q`
  - **1 passed**

## Beat 3 expected outcome (restated) and actual
Expected:
- Chassis-built v6 state has non-zero `complex.counts["MG_221_OCTAMER"]` for chromosome segregation dependency.
- With replication/supercoiling/allocation gates satisfied, segregation emits positive progress using that chassis-seeded complex path.
- Required regression suites pass.

Actual:
- Verified in `tests/integration/test_karr_chassis_v6.py::test_v6_chromosome_segregation_complex_seed_gate_and_effect`:
  - asserts `complex_seed > 0.0` for `MG_221_OCTAMER` in `build_karr_chassis_v6(...)["state"]["complex"]["counts"]`.
  - asserts positive `segregation_progress` in `next_update` with same chassis-seeded state.
  - asserts no progression when that complex count is zeroed in a control copy.
- Both required pytest commands passed with the counts above.

## Beat 4 inversion checks
### Inversion mode 1
"Fix passes while a hidden protein fallback still tolerates wrong complex wiring."

Evidence:
- `KarrChromosomeSegregationProcess` now classifies required inputs and reads complex-required WIDs from `complex.counts` only.
- `tests/vivarium/test_karr_chromosome_segregation.py::test_missing_required_complex_input_raises_keyerror` proves missing required complex input raises loudly.

Result: **did not materialize**.

### Inversion mode 2
"Fix satisfies prompt by weakening/deleting existing behavioral assertions in tests."

Evidence:
- Existing assertion lines in pre-existing test functions were not edited.
- Only setup routing helper was updated, and new tests were added.

Result: **did not materialize**.

### Inversion mode 3
"Fix works in v6 tests but breaks sibling builders through schema/topology mismatch."

Evidence (Rule 6 strong-gate enumeration + smoke commands):
- Builder surface enumeration (`rg -n "KarrChromosomeSegregationProcess|build_karr_chassis_v[0-9]\(" opencell/vivarium/karr_composite.py`) shows process instantiation in `build_karr_chassis_v5`, with `build_karr_chassis_v6` wrapping v5.
- `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v6; build_karr_chassis_v6()"` -> **exit 0**.
- `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v5; build_karr_chassis_v5()"` -> **exit 1** with `updater is absent at path ('substrates_allocated', 'karr_metabolism')`.

Result: **could not prove full sibling-builder success** (v5 construction fails in this branch context on allocator/metabolism updater path).

## Pre-existing assertions preserved
Touched pre-existing test functions in `tests/vivarium/test_karr_chromosome_segregation.py`:
- **None** (only `_base_state` setup helper was edited; a new test function was added).

Pre-existing `assert ...` statements in existing test functions:
- **All preserved unchanged** (no deletions, no tolerance widening, no directional weakening).

Inversion failure mode triggered:
- **No assertion-preservation inversion triggered** (no pre-existing assertion weakened or removed).

## Anything PM should know
- The L1 dimer/complex-port chain for `karr_chromosome_segregation` is closed in process code + v5/v6 topology + v6 integration coverage, and required regression gates are green.
- Rule-6 sibling-builder smoke surfaced a pre-existing/parallel failure path in direct `build_karr_chassis_v5()` construction (`substrates_allocated/karr_metabolism` updater absence), so this report stays at `L1-CHANGES-NEEDED` rather than green.
