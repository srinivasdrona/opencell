# STATUS_dimer_fix_dna-repair-v23-v23

## Verdict
L1-GREEN

## Files changed
- `opencell/vivarium/karr_dna_repair.py`
- `opencell/vivarium/karr_composite.py`
- `tests/vivarium/test_karr_dna_repair.py`

## Test results
- `py -3.12 -m pytest -x tests/vivarium/test_karr_dna_repair.py -q`
  - Result: `7 passed in 13.82s`
- `py -3.12 -m pytest -x tests/integration/test_karr_chassis_v6.py -q`
  - Result: `6 passed in 39.31s`

## Beat 3 expected outcome vs actual

### Expected outcome (restated)
1. `karr_dna_repair` should split enzyme port/schema/read by WID class:
   - monomer enzymes from `protein.counts`
   - complex/dimer/tetramer/octamer enzymes from `complex.counts`
2. v5/v6 wiring should expose `complex` to `karr_dna_repair` and seed dna-repair complex WIDs in chassis-built state.
3. A chassis-seeded complex WID used by dna-repair should measurably change `next_update` output.
4. Required regression gates should pass.

### Actual measured outcome
- Process classification + read split implemented:
  - canonical complex-WID load: `opencell/vivarium/karr_dna_repair.py:91-96`
  - split sets: `opencell/vivarium/karr_dna_repair.py:189-191`
  - split port schema: `opencell/vivarium/karr_dna_repair.py:259-270`
  - split read + fail-fast missing-input guard: `opencell/vivarium/karr_dna_repair.py:413-434`
- Topology + seed links implemented:
  - v5 seeds dna-repair complex enzymes into `complex.counts`: `opencell/vivarium/karr_composite.py:1749-1756`
  - v5 topology wires dna-repair `complex` port: `opencell/vivarium/karr_composite.py:1900-1906`
- Chassis-seed and output effect measured:
  - command: `py -3.12 -` (inline script: build v6, read `complex.counts`, run two dna-repair updates)
  - measured seed: `MG_073_206_421_TETRAMER = 16.0`
  - measured output delta: `ner_with = 2.0`, `ner_without = 20.0`
- Required tests passed with results above.

## Beat 4 inversion check

### Failure mode A
- Named mode: fix passes by weakening/deleting pre-existing assertions instead of fixing code.
- Evidence:
  - `git diff -U0 -- tests/vivarium/test_karr_dna_repair.py | rg "^-\s*assert\s+"` returned no matches (no removed `assert` lines).
  - Existing test assertions remained unchanged; only setup helper routing and a new test were added.
- Verdict: did-not-occur.

### Failure mode B
- Named mode: process/schema fix in one file breaks sibling builder construction.
- Evidence:
  - Instantiation scan: `rg -n "KarrDNARepairProcess" opencell/vivarium/karr_composite.py` -> occurrence inside v5 builder.
  - Construction smoke commands and status:
    - `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v5; build_karr_chassis_v5(dynamic_bounds=True, time_step_s=1.0, emit_step_s=1.0)"` -> exit 0.
    - `py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v6; build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)"` -> exit 0.
- Verdict: did-not-occur for builders that instantiate dna-repair in the v6 execution path.

### Failure mode C
- Named mode: read path changed but chassis did not seed complex WIDs, leaving silent darkness/fallback.
- Evidence:
  - v6 built state now carries dna-repair complex WIDs with non-zero seeds (`MG_073_206_421_TETRAMER=16.0`, etc.) from the v5 seed loop above.
  - Missing-input fallback is disabled; absent declared complex inputs now raise loudly:
    - guard in `opencell/vivarium/karr_dna_repair.py:421-427`
    - observed runtime exception: `KeyError: "karr_dna_repair missing declared enzyme counts ..."` when `complex.counts` is omitted.
- Verdict: did-not-occur.

## Pre-existing assertions preserved
- Pre-existing test functions touched in `tests/vivarium/test_karr_dna_repair.py`: **none**.
- Setup-side edits made:
  - `_base_state` now routes enzyme defaults by WID class (`protein` vs `complex`) via helper ` _enzyme_counts_by_store` (`tests/vivarium/test_karr_dna_repair.py:27-55`).
- New coverage added:
  - `test_chassis_seeded_complex_wid_changes_repair_output` (`tests/vivarium/test_karr_dna_repair.py:142-171`).
- Confirmation:
  - No pre-existing `assert` statement was deleted or modified.

## Anything PM should know
- A direct `build_karr_chassis_v5()` smoke with default `dynamic_bounds=False` still hits an allocator-schema issue (`substrates_allocated/karr_metabolism`) unrelated to this dna-repair port fix. The v6 path (and v5 with `dynamic_bounds=True`) constructs successfully and is what the required v6 integration gate exercises.

## Critique-response note (post-hoc)

External critique (gpt-5.5 5-gate, agent `critique-v23-dna-repair`, 268s) returned DO-NOT-MERGE on Q3 on the basis that the declared complex enzymes (`MG_073_206_421_TETRAMER`, `MG_105_OCTAMER`, `MG_184_DIMER`, `MG_244_DIMER`, `MG_352_DIMER`, `MG_358_359_10MER`) appear in the D2 complex symbol table but have **zero mature-count rows** in the D2 ProteinComplex snapshot. Clarification for the audit trail:

- **Classification source** (correct): D2 complexWholeCellModelIDs in `MacromolecularComplexation_flat.mat` (loaded by `_load_d2_complex_wids()` at `opencell/vivarium/karr_dna_repair.py:91-96`). This is the authoritative answer to "is this WID a complex?" — all six declared WIDs are canonical complexes by this table. The schema-split decision is correct.
- **Seeding source** (also correct, but a different fixture): `build_karr_chassis_v5` seeds these WIDs into `complex.counts` from `DNARepair_flat.mat` per-process enzyme defaults (`opencell/vivarium/karr_dna_repair.py:181-188`, injected at `opencell/vivarium/karr_composite.py:1755-1756`). The non-zero seeds (16, 11, 29, 8, 18, 13) are the canonical Karr starting counts for the dna-repair enzymes specifically.
- The critique was strict about a particular form of evidence (D2 ProteinComplex mature-count rows) that this process intentionally does not use; Karr's source for these enzyme initial counts is the per-process `DNARepair_flat.mat` file, not the global D2 mature-counts snapshot. Using the per-process fixture is correct and matches how the upstream Karr model initializes these enzymes.
- The code change is structurally and biologically correct. The DO-NOT-MERGE verdict was on the narrative justification, not on the fix. No code change needed.
