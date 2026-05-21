<overview>
OpenCell — open-source whole-cell simulation of *M. genitalium* in Python on Karr's WCM data + vivarium-core chassis. This session segment shipped the **central-dogma demo** validating the M1+M2+M3 chassis with self-consistency checks, then began **Phase A: porting Karr's `calcFluxBounds()`** to enable dynamic FBA bounds from substrate/enzyme snapshots. Two rubber-duck critique passes (with GPT-5.4 as the second reviewer) refined the plan; A.5 overlap audit cleared the path (all 4 NTPs + 20 AAs are in M1's FBA substrate space). Port + tests are written but **NOT YET RUN**.
</overview>

<history>

1. **User: "let's try one demo, be thorough to verify we are not checking against hard coded values"**
   - Built `scripts/demo_central_dogma.py` (E2E run of M1+M2+M3 vivarium engine, 60s simulated, 11 self-consistency checks).
   - All 11 checks PASS. Substrate writebacks match helper functions to machine epsilon (1.2e-15 for NTPs, 0 for AA), conservation invariants exact (M2v2: 1750 nt/s = 35×50; M3v2: 896 aa/s = 56×16), M3 v2/v1 ratio = 23.02× confirms documented finding, initial state matches model attrs exactly.
   - Committed: `482fdf5`.

2. **User: "sure go ahead" (proceed with substrate writeback / calcFluxBounds port)**
   - Explored Karr's `Metabolism.m::calcFluxBounds` (lines 1318-1402): 6 bound-derivation rules.
   - Inventoried existing M1 fixture: `S`, `lb`/`ub`, `obj`, `enz_bounds`, `catalysis(504,104)`, all `fba_idx_*` selector arrays already present. Missing: `enzymes(104)` snapshot, `substrates(585,3)` snapshot, several index maps.
   - Proposed Phase A (rules 1-5 + writeback) / Phase B (rule 6) split, asked for confirmation.

3. **User: "critique this approach"**
   - Invoked rubber-duck (default model). Found 3 blocking issues:
     - Snapshot `fluxs_stored` is a known-bad oracle (post-step enzymes).
     - `Δs = S @ v` would corrupt 8/376 rows (368 substrates + 7 internal-exch constraints + 1 biomass).
     - Flat 585-key substrate store incompatible with rule 4 (needs per-compartment).
   - Reframed plan: Phase A = port + MATLAB-bounds oracle only; Phase B = compartmented store + writeback.

4. **User: "critique with GPT 5.4 now"**
   - Invoked rubber-duck with `model: gpt-5.4`. Added 5 more concerns:
     - `cell_dry_mass` must be in API now (rule 4).
     - Rule 5 indexing trap (MATLAB column-major linear indexing into (585,3)).
     - Phase B is "demand-coupling" not bidirectional closure (M2/M3 don't read substrates).
     - Per-rxn flux parity too strong; use objective+biomass+feasibility primary.
     - **Critical**: overlap audit needed — claimed UTP not in M1's mapped rows (later proved wrong by my own re-investigation).

5. **User: "Proceed with revised plan: Phase A + A.5 (audit), defer B and C"**
   - First Python audit attempt was wrong: I treated `fba_sub_idx_substrates` (indices into 376 FBA-rows) as if they were 585-substrate indices. Showed UTP, 8/20 AAs as "missing" — false alarm.
   - Realized the actual FBA-row → 585-substrate-ID mapping (`substrateIndexs_fba` from MATLAB) was missing from our M1 fixture entirely. A.5 collapsed into A's MATLAB extraction.
   - Built `scripts/matlab/extract_karr_m1_dynamics.m`, ran via local MATLAB — succeeded. Output `data/m1_sources/karr_flat/metabolism_dynamics.mat` (HDF5 v7.3).
   - Built `scripts/karr_native_ingest_m1_dynamics.py` to convert .mat → fixture + run audit. Audit cleared all blockers: ATP/CTP/GTP/UTP all in M1 cytosol; all 20 AAs in M1 (cytosol; some bi-compartmented); only `AA_total` is the placeholder.
   - Built `opencell/m1/calc_flux_bounds.py` (rules 1-5, rule 6 raises NotImplementedError).
   - Built `tests/m1/test_calc_flux_bounds.py` (12 tests: oracle parity, rule directionality, perturbation panel parity, audit assertions).
   - **Tests NOT YET RUN. Likely API mismatch: tests reference `m1.raw_catalysis()` method which doesn't exist on KarrMetabolismModel.**

</history>

<work_done>

**Files created (committed `482fdf5`):**
- `scripts/demo_central_dogma.py` — 60s E2E demo with 11 self-consistency checks; all PASS; produces `artifacts/demo_central_dogma.{json,png}`.

**Files created (NOT yet committed) for Phase A:**
- `scripts/matlab/extract_karr_m1_dynamics.m` — MATLAB extractor: pulls snapshot substrates(585,3), enzymes(104), `cellDryMass`, all index maps, MATLAB `calcFluxBounds(applyProteinBounds=false)` output (504,2), with-protein version, perturbation panel (P1=zero first enzyme, P2=zero first external substrate, P3=zero first internal-lim substrate).
- `scripts/karr_native_ingest_m1_dynamics.py` — converts .mat → `data/karr_fixtures/karr_native_m1_dynamics.{json,npz}`; runs overlap audit; writes findings to JSON's `audit` block.
- `scripts/_inspect_m1_dynamics.py` — debug script for HDF5 v7.3 .mat structure.
- `data/karr_fixtures/karr_native_m1_dynamics.json` — fixture metadata + audit.
- `data/karr_fixtures/karr_native_m1_dynamics.npz` — substrates_snapshot, enzymes_snapshot, all index maps, bounds_dynamic_no_protein, bounds_dynamic_with_protein.
- `data/m1_sources/karr_flat/metabolism_dynamics.mat` — gitignored MATLAB output.
- `opencell/m1/calc_flux_bounds.py` — `M1DynamicsInputs` dataclass + `load_default_dynamics()` + `compute_bounds(...)` implementing rules 1-5; rule 6 raises NotImplementedError.
- `tests/m1/test_calc_flux_bounds.py` — 12 tests (loader dims, compartment_extracellular=1, FBA-substrate uniqueness, **oracle parity vs MATLAB no-protein bounds**, rule-3-off widens bounds, rule-4 zero-external→zero-uptake, rule-5 zero-internal→zero-lower, rule-1 zero-enzyme→zero-catalysed, rule-6 raises, P1/P2/P3 perturbation oracles, audit block).

**Tasks completed:**
- [x] Central-dogma demo (committed)
- [x] Two rubber-duck critique passes for calcFluxBounds plan
- [x] MATLAB extractor + run
- [x] Python ingest + overlap audit
- [x] `calc_flux_bounds.py` Phase A port written
- [x] Test file written

**Tasks NOT done:**
- [ ] Run `pytest tests/m1/test_calc_flux_bounds.py` — likely fails on `m1.raw_catalysis()` (method doesn't exist; need to check `KarrMetabolismModel`)
- [ ] Fix likely test failures (catalysis access)
- [ ] Run full WSL suite (expected 502 → 514+)
- [ ] Commit Phase A
- [ ] Plan/SQL todo updates

</work_done>

<technical_details>

**Demo design — no hardcoded biology values:**
- C3 NTP / C4 AA writeback: compared to `tx.ntp_consumption_per_s(model)` / `tl.aa_consumption_per_s(model)` outputs (helper-derived, not magic numbers).
- C7/C8 mechanism conservation: `total_*_polymerization_per_s()` vs `N_active × elongation_rate` (both from same fixture scalars).
- C5 dimensions read from `model.{n_genes, n_proteins, rxn_wcm_ids_645}`.
- C11 initial state matches `model.expression` / `model.counts_mature`.
- Only literal numbers: tolerances + the documented [10,50] band for v1↔v2 ratio (from `translation_v2.py` docstring).

**Karr `calcFluxBounds` 6 rules:**
1. Enzyme kinetic: `kcat × catalysis @ enzymes`
2. Enzyme presence: catalysed reactions with `rxnEnzymes ≤ 0` → [0,0]
3. Directionality: clamp metabolicConversion + biomassExchange + biomassProduction + internalExchange to static `fbaReactionBounds`
4. External metabolite: `upper[ext] = min(upper, sub[ext_idx, extracellular]/dt)`; also `lower/upper[ext] = static_bnd × cellDryMass`
5. Internal metabolite: `lower[int_lim] = max(lower, -sub[int_lim_idx, cytosol]/dt)`
6. Protein bounds: zero reactions with missing limitable proteins/complexes (DEFERRED to Phase C)

**MATLAB linear indexing trap:**
- `substrateIndexs_fba = sub2ind([585 3], sub_idx, cmp_idx)` produces 1-based column-major linear indices.
- Conversion to 0-based: `sub0 = (lin_1based - 1) % 585`, `cmp0 = (lin_1based - 1) // 585`.
- For rule 5: MATLAB's `substrates(this.substrateIndexs_internalExchangedLimitedMetabolites)` uses LINEAR indexing on a substrate-only index vector; per Metabolism.m semantics this lands on cytosol slice (indices < 585 → column 1). Python port uses `substrates[idx, 0]` explicitly.

**HDF5 v7.3 `.mat` files:**
- `scipy.io.loadmat` does NOT read v7.3 (uses HDF5). Must use `h5py`.
- v7.3 transposes 2D arrays vs MATLAB display: `(585, 3)` MATLAB → `(3, 585)` H5; `(504, 2)` MATLAB → `(2, 504)` H5. Always `.T` after read.
- Struct array elements stored as `#refs#/<letter>/<field>` references.

**Overlap audit results (real mapping):**
- ATP, CTP, GTP, UTP: all in cytosol (compartment 0).
- 20 standard AAs: all in cytosol; GLN, LYS, PHE, TRP, TYR also in extracellular (compartment 1).
- AA_total: NOT in 585 ID space — confirmed placeholder M3 invented.
- M1↔M2/M3 coupling is real for all NTPs and all AAs.

**Fixture row-class breakdown:**
- 376 FBA-substrate rows = 368 real substrates + 7 internal-exch constraints + 1 biomass pseudo-row.
- For Phase B writeback: only mutate the 368 real rows (use `substrate_idx_fba_sub0` + `substrate_idx_fba_cmp0` to map back to (585, 3) space).

**Snapshot scalars from MATLAB:**
- `cellDryMass = 3.94464e-15` (from `sum(this.mass.cellDry)`)
- `stepSizeSec = 1.0`
- `compartmentIndexs_extracellular = 2` (1-based) → 1 (0-based) — extracellular is column 1, cytosol is column 0, membrane is column 2.

**Likely test failure:** `tests/m1/test_calc_flux_bounds.py` uses `m1.raw_catalysis()` but `KarrMetabolismModel` has no such method. The catalysis matrix is in `m1.raw["..."]` or as a top-level attribute? Need to check — likely should use direct npz access or an existing attribute. The fixture .npz has `catalysis` as a top-level array but `KarrMetabolismModel` dataclass doesn't include it (it has `enz_bounds` but not `catalysis`).

**Environments:**
- Local Windows venv lacks scipy; use `wsl bash -c "source .venv-wsl/bin/activate && python ..."`.
- MATLAB via `& 'E:\MATLAB\bin\matlab.exe' -batch "addpath('...'); fn(args)"` — trial license OK.
- Full WSL suite ~12-13 min; current count 502/502.

**Decisions made:**
- Phase A scope: port rules 1-5, MATLAB-bounds oracle (NOT `fluxs_stored`), no chassis wiring.
- Phase B (deferred): compartmented substrate store, explicit row-class writeback, RHS-zero invariant assertion.
- Phase C (deferred): rule 6 + dynamic enzymes from M3 protein counts.
- Renamed Phase B from "loop closure" to "demand coupling" (M2/M3 don't read substrates yet).

</technical_details>

<important_files>

- `opencell/m1/calc_flux_bounds.py` ✅ NEW (uncommitted)
   - The Phase A core port. `M1DynamicsInputs` dataclass, `load_default_dynamics()`, `compute_bounds(...)` with rules 1-5; rule 6 raises NotImplementedError.
   - Lines 116-189 contain the rule implementations. Rule 5 line 184: uses cytosol slice `[int_sub, 0]` with comment explaining MATLAB linear indexing semantics.

- `tests/m1/test_calc_flux_bounds.py` ✅ NEW (uncommitted, NOT YET RUN)
   - 12 tests against MATLAB oracle. Lines 84, 99, 114, 130, 144, 187, 204, 220 reference `m1.raw_catalysis()` which **likely doesn't exist** — first thing to verify/fix on resume.
   - Perturbation tests load `#refs#/b/bounds`, `#refs#/c/bounds`, `#refs#/d/bounds` directly from .mat via h5py.

- `scripts/matlab/extract_karr_m1_dynamics.m` ✅ NEW (uncommitted)
   - MATLAB extractor — successfully ran. Pulls snapshot substrates/enzymes/cellDryMass + index maps + 504×2 MATLAB calcFluxBounds output (with and without protein bounds) + 3-element perturbation panel.

- `scripts/karr_native_ingest_m1_dynamics.py` ✅ NEW (uncommitted)
   - Converts .mat to fixture; runs overlap audit; writes audit findings to JSON.

- `data/karr_fixtures/karr_native_m1_dynamics.{json,npz}` ✅ NEW (uncommitted)
   - The Phase A fixture. NPZ has substrates_snapshot, enzymes_snapshot, sub/cmp index breakouts, fba_rxn_idx_*, bounds_dynamic_no_protein, bounds_dynamic_with_protein.

- `scripts/demo_central_dogma.py` ✅ COMMITTED `482fdf5`
   - Reference for how to compose engine + write self-consistency checks. Pattern to mirror for Phase B feedback tests.

- `opencell/m1/karr_metabolism.py` (existing, MUST inspect on resume)
   - Has `KarrMetabolismModel` dataclass. Need to see if `catalysis` is an attribute or only in `raw`/npz. Lines 42-56 dataclass definition — `catalysis` is NOT in the field list. Tests use `m1.raw_catalysis()` which doesn't exist. Need to either add a method/property or change tests to load catalysis directly from npz.

- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Metabolism.m` (read-only)
   - Karr source. Lines 1318-1402: calcFluxBounds. Line 724: substrateIndexs_fba = sub2ind. Line 299: compartmentIndexs_extracellular = 2.

- `plan.md` (E:\opencell + session-state mirror) — needs Phase A entry on next commit.

</important_files>

<next_steps>

**Immediate next step (resume point):**

1. **Check `KarrMetabolismModel` for catalysis access:**
   ```
   view E:\opencell\opencell\m1\karr_metabolism.py
   ```
   The dataclass currently has `enz_bounds` but NOT `catalysis`. The npz fixture has `catalysis` at top level. Either:
   - **Option A** (preferred): Add `catalysis: np.ndarray` field to `KarrMetabolismModel` dataclass + update `load_default()` to read it from npz.
   - **Option B**: Change tests to load catalysis directly: `np.load(km.DEFAULT_FIXTURE_JSON.parent / 'karr_native_m1.npz')['catalysis']`.
   - Going with Option A is cleaner (one source of truth).

2. **Run the Phase A test file:**
   ```
   wsl bash -c "source .venv-wsl/bin/activate && python -m pytest tests/m1/test_calc_flux_bounds.py -v 2>&1 | tail -40"
   ```
   Fix any failures. The oracle parity test is the critical one (`test_compute_bounds_matches_matlab_oracle_no_protein`).

3. **Run full WSL suite:**
   ```
   wsl bash -c "source .venv-wsl/bin/activate && python -m pytest --tb=short -q 2>&1 | tail -8"
   ```
   Expected: 502 → 514 (12 new tests).

4. **Git commit Phase A:**
   ```
   git add -A
   git commit -F .git-commit-msg.tmp  # use file-based commit (Windows PowerShell breaks long -m chains)
   ```
   Message themes: dynamic bounds port (rules 1-5), MATLAB-bounds oracle, overlap audit findings (NTPs+AAs all in M1 FBA space), rule 6 deferred, no chassis wiring yet.

5. **Update plan.md + SQL todos:**
   - Mark Phase A done.
   - Add Phase B (compartmented store + writeback) and Phase C (rule 6 + dynamic enzymes) as next.

**After Phase A commit, propose Phase B to user:**
- Migrate `substrates` store to `(substrate_id, compartment_id)` keys.
- Explicit row-class writeback: `Δs[368 real rows] = S[368, :] @ v × dt`, ignore 7 constraint + 1 biomass row.
- Wire dynamic bounds + writeback into `KarrMetabolismProcess`.
- Add RHS-zero invariant assertion.
- Replace existing "stable at SS" tests with feedback assertions (extracellular depletion → tighter uptake).
- Honestly label as "demand coupling" until M2/M3 also read substrates.

**Open questions:**
- Does the LP solution under MATLAB-derived dynamic bounds match Karr's `fluxs_stored`? Not part of Phase A tests but worth documenting (the documented post-step-enzymes inconsistency suggests not).
- Phase C rule 6 needs monomer/complex assembly mapping audit before dynamic enzymes from M3 can work (only some of M1's 104 enzymes are simple monomers).

</next_steps>