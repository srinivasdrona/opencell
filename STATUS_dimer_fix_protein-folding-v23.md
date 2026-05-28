# STATUS - dimer fix protein-folding v23

## Verdict
L1-GREEN

## Files changed
- opencell/vivarium/karr_protein_folding.py
- opencell/vivarium/karr_composite.py
- tests/vivarium/test_karr_protein_folding.py

## Test results
- `py -3.12 -m pytest -x tests/vivarium/test_karr_protein_folding.py -q` -> **9 passed** in 11.07s (exit 0)
- `py -3.12 -m pytest -x tests/integration/test_karr_chassis_v6.py -q` -> **6 passed** in 38.89s (exit 0)

## Beat 3 expected outcome (restated)
Expected: `karr_protein_folding` complex chaperones are seeded in chassis `complex.counts`, wired through topology, and consumed through a split read path (`complex` for complex WIDs, `protein` for monomer WIDs); process/unit and v6 integration gates pass.

Observed evidence:
- Process schema now declares `complex.counts` for complex enzyme WIDs and `protein.counts` only for monomer enzyme WIDs: `opencell/vivarium/karr_protein_folding.py:184-215`.
- Read path now splits by WID class and fails loudly on missing declared inputs (no silent `dict.get(..., 0)` for enzymes): `opencell/vivarium/karr_protein_folding.py:300-344`.
- Topology now wires `karr_protein_folding` to `complex` in both chassis builders that instantiate it (`v4`, `v5`): `opencell/vivarium/karr_composite.py:1250-1254`, `opencell/vivarium/karr_composite.py:1851-1855`.
- Chassis seeds process complex chaperones from ProteinFolding fixture enzyme counts into `complex.counts`: `opencell/vivarium/karr_composite.py:1151-1158`, `opencell/vivarium/karr_composite.py:1752-1759`.
- Chassis-seed gate test proves seeded complex chaperone affects output: `tests/vivarium/test_karr_protein_folding.py:99-123`.

## Beat 4 inversion (restated)
Inversion named: the fix could pass by changing setup/tests while leaving production read path permissive (fallback/default-zero), so the silent-darkness bug class still ships.

Evidence inversion did not occur:
- Production code now enforces split stores and raises `KeyError` if declared enzyme WIDs are absent from their required store (`protein.counts` vs `complex.counts`), preventing silent-default masking: `opencell/vivarium/karr_protein_folding.py:300-344`.
- Added chassis-seed regression explicitly toggles one seeded complex chaperone from non-zero to zero and verifies folding blocks, confirming output depends on real `complex.counts` input instead of test-only setup fiction: `tests/vivarium/test_karr_protein_folding.py:104-123`.
- Required regression gates are green (see Test results).

## Rule 6 sibling-builder safety (Strong Gate 2 evidence)
Builder instantiations found by grep/context:
- `build_karr_chassis_v4` (contains `p_fold_proc = KarrProteinFoldingProcess(...)`)
- `build_karr_chassis_v5` (contains `p_fold_proc = KarrProteinFoldingProcess(...)`)
- `build_karr_chassis_v6` wraps `build_karr_chassis_v5` and therefore constructs that process path.

Smoke commands and exit statuses:
- `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v4; build_karr_chassis_v4()"` -> exit 0
- `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v5; build_karr_chassis_v5(dynamic_bounds=True)"` -> exit 0
- `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v6; build_karr_chassis_v6()"` -> exit 0

Additional note:
- `build_karr_chassis_v5()` with default args (without `dynamic_bounds=True`) currently fails with pre-existing allocator updater wiring (`('substrates_allocated','karr_metabolism')` updater absent). This is outside the folding-port change and unchanged by this patch.

## Pre-existing assertions preserved
Touched pre-existing test functions in `tests/vivarium/test_karr_protein_folding.py`: **none**.

Evidence:
- Existing test-function bodies and their `assert ...` lines were not edited.
- Diff in this file is limited to setup helper routing (`_build_state`) plus one new additive regression test (`test_chassis_seeded_complex_chaperone_controls_folding`).
- No pre-existing assertion was weakened, deleted, tolerance-widened, or replaced.

Inversion failure mode triggered: **No**.

## PM notes
- Complex chaperone seeds now come from `ProteinFolding_flat.mat` `enzymes` values for the process-owned complex WIDs (`MG_019_DIMER`, `MG_201_DIMER`, `MG_392_393_21MER`), which gives non-zero chassis seed values and closes the seed->port->read chain for this bug class.
