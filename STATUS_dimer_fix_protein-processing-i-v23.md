# STATUS — dimer_fix_protein-processing-i-v23

## Verdict
L1-GREEN

## Files changed
- `opencell/vivarium/karr_protein_processing_i.py`
- `opencell/vivarium/karr_composite.py`
- `tests/vivarium/test_karr_protein_processing_i.py`

## Test results
- `py -3.12 -m pytest -x tests/vivarium/test_karr_protein_processing_i.py -q` -> **8 passed** (exit 0)
- `py -3.12 -m pytest -x tests/integration/test_karr_chassis_v6.py -q` -> **6 passed** (exit 0)

## Verification
### Beat 3 expected outcome (restated)
From chassis-built state, `MG_106_DIMER` is seeded in `complex.counts`, `karr_protein_processing_i` is wired to a `complex` port, `next_update` reads `MG_106_DIMER` from `complex.counts`, and PP1 output changes measurably from that seed.

### Beat 3 actual evidence
- Chassis seed check: `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v6; c=build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0); s=c['state']; print('complex_MG106', s.get('complex',{}).get('counts',{}).get('MG_106_DIMER')); print('protein_enzyme_MG106', s.get('protein',{}).get('enzyme_counts',{}).get('MG_106_DIMER'));"` printed `complex_MG106 22.0` and `protein_enzyme_MG106 None`.
- Process observable check: `tests/vivarium/test_karr_protein_processing_i.py::test_chassis_seeded_complex_enzyme_drives_processing_output` asserts non-zero chassis seed at `state["complex"]["counts"]["MG_106_DIMER"]` and then asserts exact processed output equals `min(1000, floor(seed * deformylase_specific_rate))`.

### Beat 4 inversion failure mode and evidence
1. Inversion named: fix passes while leaving old protein path authoritative for `MG_106_DIMER`.
   - Evidence not triggered:
     - `opencell/vivarium/karr_protein_processing_i.py` classifies enzyme WIDs against canonical complex fixtures (`_canonical_complex_wids`) and assigns `MG_106_DIMER` to `complex_enzyme_wids`.
     - `ports_schema()` now declares PP1 `complex.counts` for complex enzymes and PP1 protein enzyme stores for monomer enzymes.
     - `_read_enzyme_counts()` fail-fast checks missing complex/protein enzyme WIDs and reads `MG_106_DIMER` from `complex.counts`.
     - `opencell/vivarium/karr_composite.py` seeds `MG_106_DIMER` in `complex_counts` and removes it from `protein_enzyme_init` in both v4 and v5 builders.
2. Inversion named: sibling builder breakage outside the required pytest gate.
   - Evidence not triggered (Strong Gate 2 evidence):
     - Builder instantiation enumeration: `rg -n 'KarrProteinProcessingIProcess|def build_karr_chassis_v[0-9]+' opencell/vivarium/karr_composite.py` shows instantiation in `build_karr_chassis_v4` and `build_karr_chassis_v5` (v6 composes v5).
     - Smoke commands + exit status:
       - `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v4; build_karr_chassis_v4()"` -> exit 0
       - `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v5; build_karr_chassis_v5(dynamic_bounds=True)"` -> exit 0
       - `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v6; build_karr_chassis_v6()"` -> exit 0

Verdict: **matched**.

## Pre-existing assertions preserved
Touched pre-existing test functions in `tests/vivarium/test_karr_protein_processing_i.py` and unchanged pre-existing assertions:

### `test_no_unprocessed_no_action`
- `tests/vivarium/test_karr_protein_processing_i.py:80` -> `assert p.next_update(1.0, state) == {}` (unchanged)

### `test_deformylase_always_required`
- `tests/vivarium/test_karr_protein_processing_i.py:94` -> `assert p.next_update(1.0, state) == {}` (unchanged)
- `tests/vivarium/test_karr_protein_processing_i.py:98` -> `assert float(update["protein"]["processed_counts"][non_cleavage_wid]) == 10.0` (unchanged)

### `test_met_cleavage_subset`
- `tests/vivarium/test_karr_protein_processing_i.py:114` -> `assert float(no_map_update["protein"]["processed_counts"].get(cleavage_wid, 0.0)) == 0.0` (unchanged)
- `tests/vivarium/test_karr_protein_processing_i.py:115` -> `assert float(no_map_update["protein"]["processed_counts"].get(non_cleavage_wid, 0.0)) == 5.0` (unchanged)
- `tests/vivarium/test_karr_protein_processing_i.py:116` -> `assert float(no_map_update["substrates"].get(met_wid, 0.0)) == 0.0` (unchanged)
- `tests/vivarium/test_karr_protein_processing_i.py:121` -> `assert float(with_map_update["protein"]["processed_counts"].get(cleavage_wid, 0.0)) == 5.0` (unchanged)
- `tests/vivarium/test_karr_protein_processing_i.py:122` -> `assert float(with_map_update["substrates"].get(met_wid, 0.0)) == 5.0` (unchanged)

### `test_mass_conservation`
- `tests/vivarium/test_karr_protein_processing_i.py:143` -> `assert total_unprocessed_delta == -total_processed` (unchanged)
- `tests/vivarium/test_karr_protein_processing_i.py:157` -> `assert float(update["substrates"][water_wid]) == -(total_processed + cleaved_processed)` (unchanged)
- `tests/vivarium/test_karr_protein_processing_i.py:158` -> `assert float(update["substrates"][formate_wid]) == total_processed` (unchanged)
- `tests/vivarium/test_karr_protein_processing_i.py:159` -> `assert float(update["substrates"][methionine_wid]) == cleaved_processed` (unchanged)

### `test_enzyme_kinetics_limit`
- `tests/vivarium/test_karr_protein_processing_i.py:173` -> `assert float(update["protein"]["processed_counts"][cleavage_wid]) == 6.0` (unchanged)

### `test_deterministic_with_seed`
- `tests/vivarium/test_karr_protein_processing_i.py:190` -> `assert p1.next_update(1.0, s1) == p2.next_update(1.0, s2)` (unchanged)

No pre-existing assertion was weakened or deleted.

## PM notes
- I observed an exploratory failure for `build_karr_chassis_v5()` with default args (`dynamic_bounds=False`) unrelated to this PP1 port/read patch (`substrates_allocated.karr_metabolism` updater absence). The required sibling smoke for PP1 used the successful construction path `build_karr_chassis_v5(dynamic_bounds=True)` and v6 (which composes v5 in that mode) remains green.
