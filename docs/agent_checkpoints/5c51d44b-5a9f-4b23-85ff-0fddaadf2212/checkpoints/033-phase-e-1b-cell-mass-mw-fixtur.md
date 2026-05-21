<overview>
OpenCell whole-cell simulation of *M. genitalium* in Python on Karr 2012 WCM data + vivarium-core. Currently in **Phase E.1b**: extending the validation harness with phenotype #9 (cell mass at SS = Karr's 3.94e-15 g). Required MATLAB re-extraction to add per-substrate, per-RNA molecular weights to the Python fixtures so that a `cell_mass.py` aggregator can compute chassis dry mass and compare to Karr's stored target. User also requested a **new TODO** to fully evict MATLAB runtime dependency by exporting all needed Karr KB fields to Python-readable formats with annotations.
</overview>

<history>
1. **User: "fix it before moving on"** — fixed `Glck`-skipped test → `TX_GLCPTS` PTS spot-check. Amended commit `0cc8d16` (591/591).

2. **User: "great, what next?"** → "what about testing first..." → "let's build before testing"
   - Conceded test-first is correct based on plan Risk #1 (integration debt).

3. **User: "scan the phenotypes, make the list of testifiable ones first"**
   - Classified Karr's 28 phenotypes: 8 🟢, 6 🟡, 14 🔴.

4. **User: "what is the effort needed to flip the 6 yellow to green?"** → "can we flip 9 and 14 easily and then test all 10?"
   - Verified deps; #9 mass + #14 per-AA practical, #11/#12 circular.

5. **User: "yup, update the plan todos... start with E.1a and 1b"**
   - Pushed back: ship 8 first, then E.1a, then E.1b.

6. **User: "agree, go ahead"**
   - Built E.0 harness: targets fixture, `opencell/analysis/phenotypes.py`, 8 tests + xfail #4 (TX_GLCPTS), `scripts/phase_e_report.py`. Committed `ff53231` (599 + 1 xfail).

7. **User: "are the exact matches due to hard coded values?"**
   - Caught real bug: #5/#6 had `predicted=target` literal — tautology.

8. **User: "yeah, reclassify"**
   - Rewrote p5/p6 to read engine state, compare to model arrays independently. Renamed category `chassis_invariant` → `chassis_wiring`. Amended `c12d68f` (599 + 1 xfail).

9. **User: "start"** → started E.1a (per-AA pool stability).
   - Probed: with default chassis, pools collapse from 1.0 init. With `dynamic_bounds + throttle + enable_pool_replenishment`, max drift over 20s = 4.7e-4 over 20 AAs.
   - Added `measure_aa_pool_stability` extractor reading `engine.state.get_value()["m1_pools"]` (NOT timeseries — emitter doesn't capture m1_pools).
   - Added test `test_p9_aa_pool_stability_over_20s`, target tol_rel=0.005, new category `closed_loop`.
   - Result: 8 PASS + 1 XFAIL / 9; full suite 600 + 1 xfail (12:36). Committed `f94f5eb`.

10. **User (CURRENT): "start E.1b... MATLAB available locally, go ahead. Also add TODO to extract all MATLAB deps to Python-readable format"** (IN PROGRESS)
    - Added `matlab-full-eviction` todo (id 182).
    - Probed fixtures: M3 has `molecular_weight`; M1/M2 lack RNA/substrate MWs in npz.
    - Found `metabolism.substrateMolecularWeights[585]` already in `sim_fitted_targeted.mat`.
    - For RNA MW: extended `extract_karr_targeted.m` with new `extract_rna_state` helper that dumps `State_Rna.molecularWeights[2428]`, `matureIndexs[347]`, plus walks KB to expose `kb_gene_to_tu_index[525]` + `kb_tu_wholeCellModelIDs[335]`.
    - Re-ran MATLAB at `E:\MATLAB\bin\matlab.exe` from `data/m1_sources/WholeCell` → produced `rnas_targeted.mat` (n_mature=347, gene<->TU map 525→335).
    - Extended `karr_native_ingest_m1.py` (schema v1→v2): added `substrate_molecular_weight[585]`, `enzyme_molecular_weight[104]` to npz; State_Mass aggregates (`cellInitialDryWeight=3.93e-15`, `cell_dry_total_mass_g=3.944e-15`, `rnaWt[6]`) to JSON `stored_runtime`.
    - Extended `karr_native_ingest_m2.py` (schema v1→v2): added `rna_molecular_weight[525]` per gene. Policy: lookup TU MW via gene→TU map → State_Rna mature MW dict, split equally across polycistronic member genes. For 43 non-mRNA genes (tRNA/rRNA/sRNA) where mature TU absent, fall back to `length_nt × 339.5 Da`.
    - Re-ingested both; M2 now has 525/525 RNA MWs (482 from TU + 43 fallback).
    - **NOT YET DONE**: build `opencell/analysis/cell_mass.py` aggregator, add extractor `measure_cell_dry_mass`, add p10 target + test, update report script, run tests, commit.
</history>

<work_done>

**Files modified (uncommitted, in-flight E.1b):**
- `scripts/matlab/extract_karr_targeted.m` — added `extract_rna_state` helper at end (after `safeFlatten`); call from main body section "10. M2 RNA-state targeted dump". Walks KB for gene<->TU mapping (avoids MAX_DEPTH issue from safeFlatten).
- `scripts/karr_native_ingest_m1.py` — schema bump to `karr_native_m1__v2`. Added per-substrate/enzyme MW arrays to npz; State_Mass aggregates to JSON `stored_runtime`.
- `scripts/karr_native_ingest_m2.py` — schema bump to `karr_native_m2__v2`. Added gene-level RNA MW array via TU map + sequence-length fallback for non-mRNA. Coverage 525/525.
- `data/karr_fixtures/karr_native_m1.json` + `.npz` — regenerated (v2).
- `data/karr_fixtures/karr_native_m2.json` + `.npz` — regenerated (v2).
- `data/m1_sources/karr_flat/rnas_targeted.mat` — NEW, MATLAB output (gitignored).
- `data/m1_sources/karr_flat/sim_fitted_targeted.mat` etc. — refreshed by MATLAB run.

**Work completed (committed):**
- [x] Phase E.0 phenotype harness (commit `c12d68f`, 599 + 1 xfail) — reclassified after tautology fix
- [x] Phase E.1a per-AA pool stability test (commit `f94f5eb`, 600 + 1 xfail)

**Work in progress (E.1b — NOT YET COMMITTED):**
- [x] MATLAB script extension + rerun for `rnas_targeted.mat` with MWs + gene<->TU map
- [x] M1 ingestion v2 (substrate MWs + State_Mass targets)
- [x] M2 ingestion v2 (per-gene RNA MWs with fallback)
- [ ] Build `opencell/analysis/cell_mass.py` aggregator
- [ ] Add `measure_cell_dry_mass` extractor in `phenotypes.py`
- [ ] Add p10 target to `karr_phenotype_targets.json`
- [ ] Add test `test_p10_cell_dry_mass`
- [ ] Update `scripts/phase_e_report.py` extractor list
- [ ] Run Phase E tests; run full suite; commit

**Pending todos:**
- [ ] `e2-decision-point` — D.2 vs M5 vs v2 decision
- [ ] `matlab-full-eviction` (NEW, id 182) — full Karr KB → Python-readable export with annotations

**Test status:** 600 passed + 1 xfailed as of `f94f5eb` (last full suite run). After M1/M2 fixture regeneration, MUST verify no test breaks because old code reading these fixtures might not yet handle new keys (should be additive only, but verify).
</work_done>

<technical_details>

**Karr's State_Mass aggregates (from MAT, now in M1 fixture stored_runtime):**
- `cellInitialDryWeight` = 3.93e-15 g (the published target)
- `cell_per_compartment[6]` = [1.239e-14, 0, 0, 7.78e-16, 2.43e-17, 1.54e-17]
- `cellDry_per_compartment[6]` = [3.127e-15, 0, 0, 7.78e-16, 2.43e-17, 1.54e-17]
- `cellDry_total` = 3.9446e-15 g
- `rnaWt[6]` = [1.715e-16, 0, ...]
- `dryWeightFractionRNA` = 0.0930
- 6 compartments: c, d, e, m, tc, tm (cytosol, dna, extracellular, membrane, terminal-c, terminal-m)

**RNA MW gene-to-TU mapping (the hard part):**
- KB has 525 genes (482 mRNA + 36 tRNA + 3 rRNA + 4 sRNA), 335 TUs.
- `gene_to_tu_index[525]` (1-based) gives each gene's primary TU.
- State_Rna stores 2428 = roughly 7 forms × 347 mature species in `wholeCellModelIDs`.
- `matureIndexs[347]` (1-based) indexes into the 2428-vector to get mature MWs.
- Polycistronic TUs: split TU MW equally across member genes so summing chassis per-gene-counts × per-gene-MW reconstructs TU mass at SS (assumes equal counts in member genes — true at SS since they're co-transcribed).
- Non-mRNA fallback: `length_nt × 339.5 Da` (avg NMP MW). 43 genes use this. rRNA dominates RNA mass so this matters.

**MATLAB safeFlatten MAX_DEPTH issue:**
- `kb.genes(i).transcriptionUnits` is a cell ref `{className_str, idxUint32}` — gets cut by MAX_DEPTH.
- Workaround: explicit walk in `extract_rna_state` reading `g.transcriptionUnits{2}(1)` directly.
- KB load uses `load('data/knowledgeBase.mat')` from inside MATLAB cwd = WholeCell dir.

**Fixture regeneration sequence (E.1b workflow):**
1. `& "E:\MATLAB\bin\matlab.exe" -batch "addpath('E:\opencell\scripts\matlab'); extract_karr_targeted(pwd, 'E:\opencell\data\m1_sources\karr_flat'); exit"` from `data/m1_sources/WholeCell` (PowerShell)
2. `python scripts/karr_native_ingest_m1.py` (WSL with venv)
3. `python scripts/karr_native_ingest_m2.py` (WSL with venv)
4. (TODO) Verify downstream tests still pass

**Cell mass aggregator formula (planned):**
```python
def compute_cell_dry_mass_g(state, m1, m2, m3) -> float:
    NA = 6.02214076e23
    sub_mw = m1.raw["..."]  # not yet in raw; load from npz
    sub_total = sum(state["substrates"][sid] * sub_mw[i] for i, sid in enumerate(sub_ids))
    rna_total = sum(state["rna"]["counts"][g] * m2.rna_molecular_weight[i] for i,g in ...)
    prot_total = sum(state["protein"]["counts"][p] * m3.molecular_weight[i] for i,p in ...)
    return (sub_total + rna_total + prot_total) / NA
```

**Open question on cell mass tolerance:**
- Target = 3.944e-15 g. Chassis aggregator may not match exactly because:
  (a) substrate counts at chassis init are 1.0 placeholder vs Karr's snap[c=0] (NOT in shared store at engine init even with dynamic_bounds — `m1_pools` only has 24 demand keys; the other 561 substrates remain at 1.0 in `state["substrates"]`).
  (b) some macromolecules (lipids, complexes, DNA) NOT in chassis → expect ~70% recovery.
- Recommend tolerance: `tol_rel=0.30` (allow 30% gap) and document as a "partial chassis coverage" finding, OR target only the components we have (substrate cytosol mass + RNA mass + protein mass at Karr's stoichiometry) ≈ subset of dry mass.
- Honest framing: this is a `closed_loop`-grade test where partial chassis means partial mass. Could split into two phenotypes: `p10_substrate_mass`, `p11_macromolecule_mass`, both vs Karr's stored sub-totals.

**Environment:**
- WSL distro `Ubuntu-22.04`, venv `.venv-wsl`, MATLAB at `E:\MATLAB\bin\matlab.exe`.
- WholeCell MATLAB sources: `E:\opencell\data\m1_sources\WholeCell` (must be cwd for MATLAB script — does its own `setPath()`).
- Re-ingest the M3 too if needed; current M3 fixture has `molecular_weight[482]` already (no v2 bump needed unless touched).
</technical_details>

<important_files>

- `scripts/matlab/extract_karr_targeted.m` 🔄 MODIFIED (uncommitted)
  - The MATLAB extractor for Karr's MAT files. Section 10 + new `extract_rna_state` helper produces `rnas_targeted.mat`.
  - Substrate MWs: line ~125 wishlist had `substrateMolecularWeights` — already extracted, just newly exposed in Python.
  - `extract_rna_state` at end of file walks KB for gene<->TU.

- `scripts/karr_native_ingest_m1.py` 🔄 MODIFIED (uncommitted)
  - Schema `karr_native_m1__v2`. Added `substrate_molecular_weight`, `enzyme_molecular_weight` to npz. Added State_Mass aggregates to JSON `stored_runtime`.
  - Lines ~58-65: MW extraction. Lines ~70-80: State_Mass dump. Lines ~155-170: stored_runtime dict.

- `scripts/karr_native_ingest_m2.py` 🔄 MODIFIED (uncommitted)
  - Schema `karr_native_m2__v2`. Adds `rna_molecular_weight[525]` via TU map + sequence-length fallback. Loads new `rnas_targeted.mat`.
  - Lines ~22-28: paths. Lines ~95-160: gene<->TU map walking and MW assignment with fallback policy.

- `opencell/analysis/phenotypes.py` ✅ COMMITTED at f94f5eb
  - Will need new `measure_cell_dry_mass()` extractor. Pattern: build engine, read state, sum × MWs / NA.

- `data/karr_fixtures/karr_phenotype_targets.json` ✅ COMMITTED at f94f5eb
  - Schema `karr_phenotype_targets__v1`. Will need new `p10_cell_dry_mass_g` entry.
  - Existing categories: `fba_prediction`, `chassis_wiring`, `closed_loop`. Cell mass is `closed_loop`.

- `tests/phaseE/test_karr_phenotypes.py` ✅ COMMITTED at f94f5eb
  - Will need new `test_p10_cell_dry_mass` test function.

- `scripts/phase_e_report.py` ✅ COMMITTED at f94f5eb
  - Extractors list lines ~44-58. Will need new entry for p10.

- `opencell/m1/karr_metabolism.py` ✅ EXISTING (unchanged)
  - `KarrMetabolismModel` dataclass. The `raw` field carries the JSON metadata; the npz arrays are loaded via `load_default()`. Need to verify if loader currently exposes the new MW keys, OR access them directly via `np.load` of the npz path.

- `opencell/m2/transcription.py` ✅ EXISTING
  - `KarrTranscriptionModel` dataclass. Need to verify it exposes `rna_molecular_weight` from npz (likely needs a small loader edit to read the new key).

- `opencell/m3/translation.py` ✅ EXISTING
  - Already has `molecular_weight` array (482,). Verify attribute name matches loader.

- `data/m1_sources/karr_flat/rnas_targeted.mat` ⚠️ NEW ARTIFACT (gitignored)
  - 2428 entries × MW/length/halfLife/decayRates. matureIndexs[347]. KB gene<->TU map.

- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md`
  - Should be updated after E.1b commit.

**Git state:**
- HEAD = `f94f5eb` Phase E.1a
- Uncommitted: matlab script, both ingestion scripts, regenerated M1/M2 fixtures.

</important_files>

<next_steps>

**Immediate (resume E.1b):**

1. **Verify M1/M2 model loaders expose new MW arrays.** Likely need:
   - `opencell/m1/karr_metabolism.py` `load_default()` to add `substrate_molecular_weight`, `enzyme_molecular_weight` to model fields (or access via direct npz load).
   - `opencell/m2/transcription.py` model dataclass to add `rna_molecular_weight` field + loader assignment.

2. **Create `opencell/analysis/cell_mass.py`** with `compute_cell_dry_mass_g(engine_state, m1, m2, m3)`:
   - substrate_mass = Σ state["substrates"][sid] * substrate_mw_by_sid[sid]
   - rna_mass = Σ state["rna"]["counts"][gene] * rna_mw_by_gene[gene]
   - protein_mass = Σ state["protein"]["counts"][p] * prot_mw_by_p[p]
   - return (sum) / 6.02214076e23

3. **Add `measure_cell_dry_mass()` extractor** in `opencell/analysis/phenotypes.py`:
   - Build engine in dynamic_bounds + throttle + replenishment mode (same as p9).
   - For substrate slice, use `m1_pools` for the 24 demand keys + `m1_proc._sub_state[:, 0]` for the rest (since shared store has them at 1.0). Better: read `m1_proc._sub_state` directly post-init for the absolute cytosol counts.
   - Actually simplest: at init, the `_sub_state` IS Karr's snapshot (cytosol). Just need to expose it. Could do `engine.processes["m1_karr"]._sub_state[:, 0]`.

4. **Probe expected mass first** before committing to a tolerance. Run aggregator at engine init, see what fraction of 3.944e-15 we get. If we get ~70%, set partial tolerance with documented gap. If we get ~95%, tighter tolerance.

5. **Add p10 target** to `karr_phenotype_targets.json`:
   ```json
   "p10_cell_dry_mass_g": {
     "category": "closed_loop",
     "target": 3.944640855678535e-15,
     "tol_rel": 0.30,  // adjust per probe result
     "unit": "g",
     "note": "..."
   }
   ```

6. **Add test** in `tests/phaseE/test_karr_phenotypes.py`.

7. **Update `scripts/phase_e_report.py`** extractor list.

8. **Run pytest tests/phaseE/ -v** → expected: 9 PASS + 1 xfail.

9. **Run full suite** to verify M1/M2 fixture v2 doesn't break existing tests (downstream code may need access to new fields but shouldn't fail since they're additive).

10. **Commit Phase E.1b.** Suggested message:
    `Phase E.1b: phenotype #10 cell dry mass + MW fixture re-extract (601 + 1 xfail)`

11. **Update plan.md** with E.1b completion + the new `matlab-full-eviction` todo.

12. **Mark `e1b-mass-integrator` done**, surface the new `matlab-full-eviction` todo to the user for prioritization.

**Then: E.2 decision point** + the new MATLAB-eviction work.

**Open questions:**
- What tolerance is honest? Need probe result first.
- Should we split into p10_substrate_mass + p11_protein_mass + p12_rna_mass for diagnostic granularity? Lean toward NO for now (one aggregate test); add component breakdown only if the aggregate fails.
- Are M2/M3 model loaders happy with the v2 schema bump? Need to grep for `karr_native_m2__v1` / similar string assertions.

</next_steps>