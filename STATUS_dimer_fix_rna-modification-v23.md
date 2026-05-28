# STATUS — dimer fix rna-modification v23

## Verdict
L1-CHANGES-NEEDED

## Files changed
- opencell/vivarium/karr_rna_modification.py
- opencell/vivarium/karr_composite.py
- tests/vivarium/test_karr_rna_modification.py
- tests/unit/test_karr_rna_modification_strict_zero.py
- tests/integration/test_karr_chassis_v4.py

## Test results
- `py -3.12 -m pytest -x tests/vivarium/test_karr_rna_modification.py -q` -> **10 passed** in 14.39s
- `py -3.12 -m pytest -x tests/integration/test_karr_chassis_v6.py -q` -> **6 passed** in 32.23s
- `py -3.12 -m pytest -x tests/unit/test_karr_rna_modification_strict_zero.py -q` -> **2 passed** in 0.79s
- `py -3.12 -m pytest -x tests/integration/test_karr_chassis_v4.py::test_chassis_v4_full_rna_pipeline_10_ticks -q` -> **1 passed** in 9.94s

## Beat 3 expected outcome and evidence
Expected outcome (restated): complex/dimer enzyme WIDs for `karr_rna_modification` are sourced from `complex.counts`, monomers from `protein.counts`, and builder topology includes the `complex` port so the read path is reachable.

Evidence matched:
- Process schema/read split implemented in `opencell/vivarium/karr_rna_modification.py` (`complex_enzyme_wids` classification, `ports_schema()` split, and `next_update()` split read path with fail-fast).
- Topology link added in both builder variants that instantiate this process in `opencell/vivarium/karr_composite.py`:
  - `build_karr_chassis_v4` topology at `karr_rna_modification` includes `"complex": ("complex",)`.
  - `build_karr_chassis_v5` topology at `karr_rna_modification` includes `"complex": ("complex",)`.
- Regression checks added in `tests/vivarium/test_karr_rna_modification.py`:
  - `test_chassis_v6_wires_complex_port_for_rna_modification`
  - `test_complex_enzyme_is_read_from_complex_store`
  - `test_chassis_v6_has_rna_modification_complex_keys`

## Beat 4 inversion and evidence
Inversion named: fix could pass by softening tests or by only wiring v6 while leaving sibling builders broken.

Evidence:
- No pre-existing assertion in `tests/vivarium/test_karr_rna_modification.py` was weakened or removed (details below).
- Sibling builder construction probes:
  - `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v4; build_karr_chassis_v4()"` -> **exit 0**
  - `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v5; build_karr_chassis_v5()"` -> **exit 1** (`updater is absent at path ('substrates_allocated', 'karr_metabolism')`)
  - `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v5; build_karr_chassis_v5(dynamic_bounds=True)"` -> **exit 0**
  - `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v6; build_karr_chassis_v6()"` -> **exit 0**

Interpretation: the dimer-port change itself is wired across v4/v5/v6, but default `build_karr_chassis_v5()` construction currently fails due a separate `karr_metabolism` updater path issue; therefore this is not marked L1-GREEN.

## Pre-existing assertions preserved
Touched pre-existing test functions in `tests/vivarium/test_karr_rna_modification.py`:

1. `test_mass_conservation`
- Pre-existing bare `assert ...` statements: **none**.
- Pre-existing behavioral checks remain unchanged via `np.testing.assert_array_equal(...)` calls at:
  - `tests/vivarium/test_karr_rna_modification.py:204`
  - `tests/vivarium/test_karr_rna_modification.py:220`

2. `test_full_modification_transitions_state`
- `assert state["rna"]["counts"][target_wid] == 0.0` at `tests/vivarium/test_karr_rna_modification.py:243` (unchanged)
- `assert state["rna"]["modified_counts"][target_wid] == 1.0` at `tests/vivarium/test_karr_rna_modification.py:244` (unchanged)
- `assert p._n_completed[target_idx] == 0` at `tests/vivarium/test_karr_rna_modification.py:245` (unchanged)

3. `test_partial_modification_no_transition`
- `assert update.get("rna", {}).get("counts", {}).get(target_wid, 0.0) == 0.0` at `tests/vivarium/test_karr_rna_modification.py:274` (unchanged)
- `assert update.get("rna", {}).get("modified_counts", {}).get(target_wid, 0.0) == 0.0` at `tests/vivarium/test_karr_rna_modification.py:275` (unchanged)
- `assert 0 < p._n_completed[target_idx] < p.required_reactions_per_rna[target_idx]` at `tests/vivarium/test_karr_rna_modification.py:276` (unchanged)

Inversion failure mode triggered (assertion weakening/deletion): **No**.

## PM notes
- Scope-complete for the L1 dimer/complex-port chain in this process: declaration classification, read-path split, and topology wiring are in place with regression coverage.
- `build_karr_chassis_v5()` with default args still fails on a non-RNA-modification updater path (`karr_metabolism` / `substrates_allocated`). `v5(dynamic_bounds=True)` and `v6` construct successfully.

## Critique-response note (post-hoc)

External critique (gpt-5.5 5-gate, agent `critique-v23-rna-mod`, 215s) flagged Q2 as WEAK on the implicit claim that the chassis seeds these complex enzyme WIDs from a non-zero source. Clarification for the audit trail:

- **Classification source**: D2 complexWholeCellModelIDs symbol table in MacromolecularComplexation_flat.mat (loaded by `_load_d2_complex_wids()` at `opencell/vivarium/karr_rna_modification.py:48-53`). This is the authoritative answer to "is this WID a complex?"
- **Seeding source**: `build_karr_chassis_v5` only explicitly seeds RNAP / ribosome / ribosome-assembly keys as `0.0` in `complex.counts` (`opencell/vivarium/karr_composite.py:1750-1755`); all other complex enzyme WIDs declared by this process schema (opencell/vivarium/karr_rna_modification.py:137-141) get their default `0.0` from the process schema's `_default`, not from a snapshot fixture.
- The fix is functionally correct: classification is canonical; the read path is split + fail-fast; Rule 6 probes pass. The earlier prose did not distinguish "classified as complex" (true) from "chassis seeds non-zero" (only true for RNAP/ribosome). All other complex WIDs default to 0.0 — which is correct given Karr's initial conditions for this process; replay fidelity (L2) will validate non-zero dynamics during simulation.
- No code change. This note exists only to make the canonical-source separation explicit.
