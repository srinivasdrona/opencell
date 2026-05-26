# Track-NaN-A REDO Status

1. **Verdict**: PARTIAL

2. **Anti-tautology self-check**

```python
# scripts/canary_csvs_to_e2_pkl.py
klass = lookup.polymer_class(substrate)
mw = lookup.mw_g_per_mol(substrate)
sums[tick][klass] += float(count) * float(mw)  # <- sum(count * MW)

mass_da = polymer_masses.get(tick, PolymerMassByTick(0.0, 0.0, 0.0))
state["dna_mass_g"] = mass_da.dna_da / AVOGADRO
state["rna_mass_g"] = mass_da.rna_da / AVOGADRO
state["protein_mass_g"] = mass_da.protein_da / AVOGADRO
```

No path in code computes `dna_mass_g/rna_mass_g/protein_mass_g` from `cell_dry_mass_g * constant`.

3. **MW source (path + key/field)**
- `data/karr_fixtures/karr_native_m1.npz` -> `substrate_molecular_weight` aligned to `data/karr_fixtures/karr_native_m1.json` -> `ids.substrate_wcm_585`.
- `data/karr_fixtures/karr_native_m2.npz` -> `rna_molecular_weight` aligned to `data/karr_fixtures/karr_native_m2.json` -> `ids.gene_wcm_525`.
- `data/karr_fixtures/karr_native_m3.npz` -> `molecular_weight` aligned to `data/karr_fixtures/karr_native_m3.json` -> `ids.protein_wcm_482`.
- `data/karr_fixtures/parameters.json` does not contain the per-substrate MW table needed for this bridge.

4. **Classification source (file + mechanism)**
- Primary RNA classification: `data/karr_fixtures/karr_native_m2.json` -> `ids.gene_wcm_525` + `ids.gene_types_525` (`mRNA/tRNA/rRNA/sRNA` => RNA).
- Primary protein classification: `data/karr_fixtures/karr_native_m3.json` -> `ids.protein_wcm_482`.
- Conservative fallback (in `opencell/data/substrate_mass_classes.py`): explicit chromosome-like DNA IDs (`CHROMOSOME*`, `DNA_CHROM*`, `DNA_STRAND*`), plus narrow RNA/protein name patterns.
- Overlap resolution is single-label per substrate row (no double counting).

5. **What counts as DNA/RNA/protein mass**
- DNA mass: only substrates classified as DNA and having finite positive MW.
- RNA mass: only substrates classified as RNA and having finite positive MW.
- Protein mass: substrates classified as protein and having finite positive MW (includes monomers and recognized oligomer names with MW in fixtures).
- Exclusions: unclassified substrates (`other`) and any substrate with missing/nonpositive MW.

6. **Sanity check output**
- `substrates_full.csv` checks:
  - unique substrates: `805`
  - rows at tick `0`: `805`
- Snapshot inspection from regenerated `data/phase_e/v6_trajectory_32400s_post_strip.pkl`:
  - tick `0`: dna=`0.0000`, rna=`0.0000`, protein=`0.0167`
  - tick `5000`: dna=`0.0000`, rna=`0.0000`, protein=`0.0161`
  - tick `10000`: dna=`0.0000`, rna=`0.0000`, protein=`0.0161`
  - tick `20000`: dna=`0.0000`, rna=`0.0000`, protein=`0.0161`
  - tick `32000`: dna=`0.0000`, rna=`0.0000`, protein=`0.0161`
- Note: the requested index probe `[0, 50, 100, 200, 320]` maps to ticks above because fixture snapshots are 100-tick stride.
- Diagnostic: across the entire CSV there are **no nonzero DNA/RNA-class substrate rows** under fixture-backed classification (`nonzero rows by class: {'protein': 369474}`).

7. **Scorecard KP17/18/19 rows**
- **Not re-run**. Per your smell gate (`fractions wildly off`), I stopped before re-scoring and documented the mismatch cause instead of publishing misleading KP rows.

8. **Commits (SHAs + 1-line each)**
- `98abcf1` - `feat(data): substrate mass-class classification + MW lookup`
- `4d3ce32` - `feat(bridge): compute dna/rna/protein mass from substrate counts × MW (no tautology)`
- `ba74a24` - `phase-e: regenerate post-strip pkl with substrate-derived mass fractions`

9. **Branch push status**
- Pushed with force lease:
  - `git push -u origin fix/nan-mass-fractions --force-with-lease`
  - remote update: `cf713f3...ba74a24 (forced update)`

10. **Anything weird**
- `parameters.json` has mass fractions and scalar mass params, but not the needed per-substrate MW vector.
- `substrates_full.csv` appears substrate-store centric; RNA/DNA polymer populations needed for KP17/18 are not present as nonzero substrate rows in this artifact.
- `cell_dry_mass_g` in the canary key CSV is much larger than the reference fixture’s `cell_dry_mass_reference_g`, making polymer fractions especially sensitive to missing class populations.
