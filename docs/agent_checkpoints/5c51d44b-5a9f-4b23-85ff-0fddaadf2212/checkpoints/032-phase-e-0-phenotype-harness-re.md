<overview>
OpenCell whole-cell sim of *M. genitalium* in Python on Karr 2012 WCM data + vivarium-core. After Phase D.0/D.1 (fixture extraction) shipped, the user steered toward **test-first** before more building. Phase E.0 = phenotype validation harness shipped (8 phenotypes, 7 pass + 1 expected xfail). User then sharply caught that #5/#6 were tautologies (`predicted=target` literally) — currently fixing those to be wiring-fidelity tests against the actual chassis engine state.
</overview>

<history>
1. **User: "which is the skipped test? why is it skipped?"** (after D.1 commit on `0cc8d16`)
   - Identified `test_glucose_uptake_sign_convention` skipped on missing `Glck` rxn.
   - Probed Karr KB: actual rxn is `TX_GLCPTS` (PTS): extracellular GLC −1 + cytosolic PEP −1 → cytosolic G6P +1 + cytosolic PYR +1.
   - Rewrote test to pin TX_GLCPTS structurally. 17/17 pass, 0 skips.
   - Amended commit `0cc8d16`.

2. **User: "great, what next?"**
   - Surveyed plan + pending todos.
   - Proposed 4 options: (1) D.2 wire D.0/D.1 into chassis, (2) M4 non-FBA process, (3) M2/M3 v2 mechanics, (4) Phase E validation. Recommended option 1.

3. **User: "what about testing first... will you agree if I propose the opposite?"**
   - Switched position based on the argument's merit (plan Risk #1 = integration debt; loop closure required; failure branch is publishable; cost low). Test-first is correct.

4. **User: "What if I say let's build before testing?"**
   - Held position; conceded only if user pointed to a phenotype we can't even produce. Asked for compromise: scan 28 phenotypes, classify each as testable-now vs structurally blocked.

5. **User: "scan the phenotypes, make the list of testifiable ones first"**
   - Drew Karr 2012's 28 phenotypes from paper structure (no enumerated list in repo).
   - Classified: 8 🟢 testable now, 6 🟡 partial, 14 🔴 structurally blocked.

6. **User: "what is the effort needed to flip the 6 yellow to green?"**
   - Honest sizing: #9 mass=½ day, #14 per-AA=hours, #11/#12 half-life=weeks (circular), #13 NTP arch=trivial, #10 ATP-budget=½–1 day. Realistic: 10-12 testable.
   - Recommended reclassifying #11/#12 as red.

7. **User: "can we flip 9 and 14 easily and then test all 10? will that have any dependencies?"**
   - Verified deps: per-AA M3 deltas already exposed (`opencell/vivarium/karr_m3.py`); MW arrays missing from M1/M2 fixtures (need MATLAB re-extract).
   - Proposed: E.0 harness + 8 green; E.1a per-AA test; E.1b mass aggregator.

8. **User: "yup, update the plan todos... start with E.1a and 1b, we will test all 10 in one go. do you agree or should we test the first 8 and then flip 9 and 14 to test separately?"**
   - Pushed back: test 8 first (smaller blast radius, faster feedback, surfaces chassis bugs before fixture re-extract).

9. **User: "agree, go ahead"**
   - SQL inserted Phase E todos (e0, e1a, e1b, e2) with deps.
   - Probed chassis: stored growth=2.119e-5/s, LP gives 1.089e-5/s (0.51× ceiling); TX_GLCPTS LP=0 vs stored 2725; M2/M3 SS counts (41327 mRNA, 16177 protein).
   - Created `karr_phenotype_targets.json`, `opencell/analysis/phenotypes.py`, `tests/phaseE/test_karr_phenotypes.py`, `scripts/phase_e_report.py`.
   - Ran tests: 7 pass + 1 xfail. Full suite: 591→599 passed + 1 xfailed. No regressions.
   - Committed Phase E.0 on `ff53231`.

10. **User: "are the exact matches due to hard coded values?"** (CURRENT)
    - Caught real bug: #5/#6 extractors had `predicted=target` literally (same Python variable). Fake tests, not just circular.
    - Honest classification produced; #7/#8 are real-but-trivial (drift=0 by math at SS, tests wiring not biology).

11. **User: "yeah, reclassify"** (CURRENT — work in progress)
    - Rewrote `measure_mrna_total_chassis_wiring` and `measure_protein_total_chassis_wiring` to build engine, read state, compare to model independently.
    - Updated `karr_phenotype_targets.json` to rename keys p5/p6 and reclassify p5-p8 as `chassis_wiring` (not `chassis_invariant`).
    - Updated test file: docstring, renamed test functions p5/p6 (now `_chassis_wiring` suffix).
    - **NOT YET DONE**: re-run pytest, update `scripts/phase_e_report.py` extractors map, run full suite, amend commit.
</history>

<work_done>
**Files modified (uncommitted, in-flight reclassification):**
- `opencell/analysis/phenotypes.py` — replaced `measure_mrna_total_roundtrip`/`measure_protein_total_roundtrip` with `measure_mrna_total_chassis_wiring`/`measure_protein_total_chassis_wiring` that build engine, call `engine.state.get_value()`, sum chassis state independently of model. Updated `__all__`.
- `data/karr_fixtures/karr_phenotype_targets.json` — renamed p5/p6 keys, reclassified all four (p5-p8) as `chassis_wiring`, updated `rationale` field, tightened p5/p6 tol_rel to 0.001.
- `tests/phaseE/test_karr_phenotypes.py` — updated docstring, renamed `test_p5_mrna_total_roundtrip` → `test_p5_mrna_total_chassis_wiring` (and p6). Tests now pass `engine.state.get_value()`-derived counts vs `m2.expression.sum()` separately.

**Files NOT yet updated (pending in current task):**
- `scripts/phase_e_report.py` — `extractors` list still references old function names `ph.measure_mrna_total_roundtrip` / `ph.measure_protein_total_roundtrip`. Will fail when run.

**Work completed (committed):**
- [x] Fix `Glck` skipped test → `TX_GLCPTS` PTS spot-check (amended `0cc8d16`)
- [x] Phase E phenotype scan (28 phenotypes classified)
- [x] Phase E.0 harness shipped (`ff53231`): targets fixture + extractors + 8 tests + report script. 599 pass + 1 xfail.

**Work in progress:**
- [ ] Reclassify #5/#6 from tautology to wiring-fidelity test (CODE done, NEEDS verification + report-script update + re-run + amend)

**Pending:**
- [ ] E.1a per-AA pool stability test (#14)
- [ ] E.1b MW fixture re-extract + mass aggregator + cell mass test (#9)
- [ ] E.2 decision point (D.2 vs M5 vs v2)

**Test status:**
- D.0: 20/20, D.1: 17/17, Phase E.0: 7 pass + 1 xfail (pre-reclassification)
- Full suite (last clean): 599 passed + 1 xfailed in 12:36 (WSL)
- After reclassification: untested. Risk: chassis engine state read may have key/index differences from model arrays → could expose real wiring discrepancies.
</work_done>

<technical_details>

**Phenotype classification (5 categories produced this session):**
- 🟢 Testable now (8): growth, glucose uptake, AA uptake, ATP production, per-gene mRNA, per-protein, total RNA mass, total protein mass.
- 🟡 Partial (6 → realistically 4 after honest reclassification): cell mass doubling, ATP budget by process, NTP pool stability, AA pool stability. (#11/#12 mRNA/protein half-life are circular — should be 🔴.)
- 🔴 Structurally blocked (14, including reclassified 11/12): complex counts (need D.2), replication/cycle (need M5), v2 mechanism phenotypes, volume model, knockout harness, cell shape (out of scope).

**Karr phenotype targets (extracted this session):**
- `growth_per_s` = 2.1192692552e-5 (stored runtime)
- `doublingTime_h` = 13.107243 (stored runtime)
- `cell_dry_mass_g` = 3.944640855678535e-15
- `cellCycleLength` = 32400s (~9h, from parameters.json)
- `replicationDuration` = 15571s
- `cytokinesisDuration` = 3869s
- `meanInitialGrowthRate` = 2.1393e-5/s
- TX_GLCPTS stored flux = 2725 (predicted by LP = 0 — structural gap)

**Chassis structural ceilings:**
- LP at static snapshot reproduces only ~0.51× of stored growth (Karr's enzyme bounds are post-step; 34/504 of his stored fluxs violate them). Documented in `tests/m1/test_karr_metabolism.py:test_lp_solves_and_biomass_within_2x_of_stored` with bounds `0.45 < ratio < 0.6`.
- Median |log2(pred/stored)| oracle: 0.96 over 196 nonzero rxns (passes <1.0 bar).
- TX_GLCPTS is in the 504 FBA col set BUT solves to 0 because PEP supply is throttled at snapshot (PTS lives in non-FBA M4-M28). Marked `xfail(strict=True)` in Phase E.

**Engine-state read pattern (new code in `phenotypes.py`):**
```python
from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine
engine = build_karr_m1_m2_m3_engine(time_step_s=1.0, emit_step_s=1.0)
# horizon=0: just init, no update
state = engine.state.get_value()
chassis_total = float(sum(state["rna"]["counts"].values()))
```
The composer (`karr_composite.py:209-212`) populates `rna_init` from `m2.expression[i, condition]` and `prot_init` from `m3.counts_mature`. Engine state read gives chassis-side view; comparison to independently summed model array catches composer/topology bugs.

**WHY the original p5/p6 were fake (root cause):**
Both `measure_mrna_total_roundtrip` and `measure_protein_total_roundtrip` had `predicted=target=float(m2.expression[...].sum())` — same Python variable assigned twice. Cannot fail. Caught by user, not by code review.

**WHY p7/p8 are still legitimate (real-but-trivial):**
They DO call `engine.update(20)` and read time-series. Drift=0 is mathematically correct because M2/M3 v1 use closed-form `dRNA/dt = s − k·RNA` at SS where s = k·RNA → dRNA = 0. Tests catch integrator wiring bugs, not biology. Reclassified to `chassis_wiring` honest framing.

**Honest categorisation in targets fixture:**
- `fba_prediction`: real prediction vs Karr ground truth.
- `chassis_wiring`: catches composer/integrator bugs but not biology. Become biology tests once v2 mechanics replace prescribed-rate models.
- (Removed term `chassis_invariant` — was misleading.)

**Karr KB compartment vocabulary (6 total):** c, d, e, m, tc, tm. Metabolism uses 3: c, e, m (index 0, 1, 2).

**Environment:**
- WSL distro: `Ubuntu-22.04` (NOT plain `Ubuntu`); venv: `.venv-wsl`
- Activation: `cd /mnt/e/opencell && source .venv-wsl/bin/activate`
- Full test suite: ~12:30 wall (599 tests as of `ff53231`)
- PowerShell pipe `|` inside `python -c '...'` interpreted by PowerShell — always use script files (Set-Content + run + Remove-Item pattern)
- PowerShell `;` chaining + `tail` is broken because `tail` doesn't exist on Windows. Use `wsl ... | tail` inside one bash invocation, or just print full output.
- CRLF/LF warnings are normal at git add — files normalize at commit.

**Open questions:**
- Will reclassified p5/p6 still pass after reading engine state? Composer may be exact (same source array) → predicted ≈ target with rel_err ~1e-15 → passes 0.001 tol. Or there could be subtle discrepancies (e.g., float roundtrip, `_M1_SUBSTRATE_DEFAULT` interfering).
- Will full suite still hold at 599+1xfail?
- For E.1b, MATLAB script edit: need to add `kb.metabolites.molecularWeight` and `kb.transcriptionUnits.molecularWeight` extraction. MATLAB R2026a quirk: `strjoin` on cells with non-char fails (defensive loop required).
</technical_details>

<important_files>

- `opencell/analysis/phenotypes.py` 🔄 MODIFIED (uncommitted)
  - Phenotype extractors. Lines ~99-150 (rewritten): `measure_mrna_total_chassis_wiring`, `measure_protein_total_chassis_wiring`, helper `_run_engine_for(horizon_s)`.
  - `__all__` updated to new names.
  - **Risk:** `engine.state.get_value()` may need different API call; verify on next pytest run.

- `data/karr_fixtures/karr_phenotype_targets.json` 🔄 MODIFIED (uncommitted)
  - Schema `karr_phenotype_targets__v1`. Eight phenotypes with target values, tolerances, and category.
  - p5/p6 keys renamed to `_chassis_wiring`; p5-p8 all classified `chassis_wiring`.
  - `rationale` field updated to reflect honest framing.

- `tests/phaseE/test_karr_phenotypes.py` 🔄 MODIFIED (uncommitted)
  - 8 pytest cases. p5/p6 functions renamed; assertions read from extractor result objects.
  - p4 has `@pytest.mark.xfail(strict=True, reason="STRUCTURAL GAP: TX_GLCPTS...")`.
  - Docstring updated to describe `chassis_wiring` category.

- `scripts/phase_e_report.py` ⚠️ STALE (uncommitted, NEEDS UPDATE)
  - Lines 53-54: `extractors` list still references old `ph.measure_mrna_total_roundtrip` / `ph.measure_protein_total_roundtrip`.
  - **WILL FAIL** until updated to use `_chassis_wiring` versions.

- `opencell/vivarium/karr_composite.py` ✅ EXISTING (key reference)
  - Lines 209-212: composer populates `rna_init`/`prot_init` from m2/m3 model arrays.
  - Lines 239-249: `initial_state` dict structure shows `state["rna"]["counts"]`, `state["protein"]["counts"]` as dict[gene_wid, float].
  - Engine built via `Engine(processes={...}, topology={...}, initial_state=...)`.

- `opencell/m1/karr_metabolism.py` ✅ EXISTING (key reference)
  - `solve_fba(model, ...)` returns `(v_504, info)` with `info["biomass_flux_per_s"]`.
  - `per_reaction_comparison(model, v, nonzero_only=False)` returns rows with `predicted`/`karr_stored` keys.
  - `model.fba_col_for_wcm_id(wcm_id)`, `model.reaction_wcm_id_to_645_index(wcm_id)`.

- `opencell/vivarium/karr_m3.py` ✅ EXISTING (per-AA already wired for E.1a)
  - 20 AA WIDs (ALA, ARG, ASN, ...) written to `substrates` store as per-AA deltas.
  - Phase C.1 work already exposed this.

- `data/karr_fixtures/karr_native_m1.json` ✅ EXISTING
  - `stored_runtime`: growth_per_s, growth_per_h, doublingTime_h, etc.

- `data/karr_fixtures/karr_native_m3.npz` ✅ EXISTING
  - Has `molecular_weight` array for proteins. M1 and M2 npz fixtures lack equivalent (target of E.1b re-extract).

- `scripts/matlab/extract_karr_targeted.m` ⚠️ NEEDS EDIT in E.1b
  - Add `kb.metabolites.molecularWeight` to M1 fixture export and `kb.transcriptionUnits.molecularWeight` to M2 fixture export.

- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md` 🔄 MODIFIED
  - "Current Status" updated to 599 tests + Phase E.0 section.
  - Header at line 404 (now ~414).

</important_files>

<next_steps>

**Immediate (resume in-flight reclassification):**

1. **Update `scripts/phase_e_report.py`** — change extractors map entries:
   ```python
   ("p5_mrna_total_chassis_wiring", lambda: ph.measure_mrna_total_chassis_wiring(m2)),
   ("p6_protein_total_chassis_wiring", lambda: ph.measure_protein_total_chassis_wiring(m3)),
   ```

2. **Re-run Phase E tests:**
   ```
   wsl -d Ubuntu-22.04 -- bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && python -m pytest tests/phaseE/ -v 2>&1 | tail -15"
   ```
   - Expected: 7 pass + 1 xfail. If p5/p6 fail, the wiring discrepancy IS the meaningful finding — document and decide whether to widen tolerance or fix wiring.

3. **Re-run report script** to verify table renders and confirm pass/fail.

4. **Run full suite** (~12:30) to confirm no regressions.

5. **Amend commit `ff53231`** with reclassification fix. Suggested title: `Phase E.0: phenotype validation harness + first report (599 + 1 xfail)` (unchanged); body should add note about reclassification of p5-p8 from `chassis_invariant` to `chassis_wiring` after user caught the tautology.

**Then proceed to E.1a (per-AA pool stability):**
- New extractor `measure_per_aa_pool_stability(horizon_s=20)` reading 20 AA WIDs from `state["substrates"]`.
- New target entry in JSON.
- New test in `test_karr_phenotypes.py` (parametrized over the 20 AAs OR aggregate).
- ~1-2 hours.

**Then E.1b (mass aggregator):**
- Edit `scripts/matlab/extract_karr_targeted.m`, re-run MATLAB to refresh M1+M2 fixtures with MW arrays.
- Re-run `scripts/karr_native_ingest_m1.py` and `karr_native_ingest_m2.py` (bump schema versions).
- New `opencell/analysis/cell_mass.py`.
- New extractor + test. ~½ day.

**Then E.2 decision point** based on 10-phenotype report.

**Open question:** does the user want me to keep `tests/phaseE/test_karr_phenotypes.py` as 8 separate test functions or convert to `pytest.parametrize`? Current style is explicit per-test for readability; OK to keep.
</next_steps>