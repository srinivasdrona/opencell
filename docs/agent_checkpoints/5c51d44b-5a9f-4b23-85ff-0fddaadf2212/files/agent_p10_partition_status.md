# Agent: p10 mass partition — DONE

- **Branch:** `agent/p10-mass-partition`
- **Commit SHA:** `0c48ce049feeb3ff973af601d12926ff7f121888`
- **Base:** `main` @ `d8201fc`

## Sub-targets added (3 + 1 consistency check)

All targets archive-derived; no hardcoded values.

| Sub-target | Target (g) | % cellDry | Status | Source |
|---|---|---|---|---|
| `p10a_dry_mass_rna_g` | 1.715e-16 | 4.35% | **xfail** | `stored_runtime.rna_wt_total_g` (= sum(rnas_targeted__counts × MW)/N_A, verified) |
| `p10b_dry_mass_protein_monomer_g` | 1.093e-15 | 27.70% | **PASS** ✅ | sum(proteins_targeted__counts[4820,6] × molecularWeights[4820]) / N_A, recomputed live |
| `p10c_dry_mass_other_residual_g` | 2.680e-15 | 67.95% | **xfail** | cellDry − p10a − p10b (residual: complexes + DNA + lipid + polysaccharide + true substrate pool) |
| `test_p10c_other_residual_target_consistency` | — | — | **PASS** ✅ | anti-fabrication guard: re-derives all three values from archive |

Existing `p10_cell_dry_mass_g` aggregate stays xfail (still 21 % vs Karr).

## Test totals

- Before: **599 pass + 3 xfail = 602**
- After: **601 pass + 5 xfail = 606** (+4 tests)
- 601 = 599 baseline + p10b + consistency check
- 5   = 3 baseline + p10a + p10c

Full suite: `pytest -q` → `601 passed, 5 xfailed in 793.80s`.

## Decisions / surprises

1. **Karr archive only publishes 2 clean per-class subtotals** (`State_Mass.cellDry` total, `State_Mass.rnaWt` per-compartment). No DNA / lipid / polysaccharide / ProteinComplex per-class breakdown is published.
2. **`snapshot_substrates` (3, 585) is unusable as a cellular substrate-count target** — values are in MATLAB-FBA-input units (cytosol H₂O at 1.4e14, ~5 orders of magnitude above any per-cell count). Documented as the reason p10c is a single residual rather than splitting out a `p10x_substrate_dry_g`. This was the user's explicit "(b) flag as a blocker rather than fabricate" path.
3. **Protein monomer target derived live** from `proteins_targeted__counts × molecularWeights / N_A`. Karr's State_Mass calc uses the same arrays, so this is faithful — just not directly published as a State_Mass field.
4. **p10b passes at chassis ratio 0.70** with `tol_rel_min=0.50`. This is the headline E.1c win — surfacing what was hidden inside the aggregate p10 xfail.
5. **Consistency test** (`test_p10c_other_residual_target_consistency`) re-derives all three sub-target values from the archive and asserts the JSON values match within float round-off (`1e-22 g`); a future hand-edit drift would fail loudly.
6. RNA derivation matches `stored_runtime.rna_wt_total_g` to ~3e-23 g (MATLAB→Python float round-off); used the stored value as canonical.

## Files touched (strictly in scope)

- `data/karr_fixtures/karr_phenotype_targets.json` — 3 entries added
- `opencell/analysis/phenotypes.py` — `_build_chassis_mass_breakdown`, `_karr_archive_protein_monomer_dry_mass_g`, `measure_dry_mass_rna_g`, `measure_dry_mass_protein_monomer_g`, `measure_dry_mass_other_residual_g`
- `tests/phaseE/test_karr_phenotypes.py` — 4 new tests
- `data/karr_archive/fixture_hashes.json` — `karr_phenotype_targets.json` hash refreshed

`validate_karr_archive.py --skip-rerun` reports "All 17 fixtures match committed hashes."

Branch not pushed, not merged.
