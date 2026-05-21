<overview>
OpenCell whole-cell sim of *M. genitalium* in Python on Karr 2012 WCM data + vivarium-core. This segment shipped **Phase A** (port of Karr's `calcFluxBounds` rules 1-5 with bit-for-bit MATLAB oracle parity, +13 tests) and **Phase B** (dynamic-bounds chassis mode: M1 reads M2/M3 demand from shared `substrates` store into private `(585,3)` compartmented state, +13 tests). Test count 502 → 528. Now mid-build on **Phase C** (per-AA M3 deltas, two-store topology with `m1_pools`, substrate-aware throttling in M2/M3) — got rubber-duck critique, started extraction of 722-metabolite vocab, blocked on MATLAB CWD issue.
</overview>

<history>
1. **User: "carry on"** (resume after Phase A commit `482fdf5` for central-dogma demo + Phase A test fixes)
   - Fixed `KarrMetabolismModel` to expose `catalysis` field; replaced `m1.raw_catalysis()` with `m1.catalysis` in tests; switched `np.maximum`/`minimum` → `np.fmax`/`fmin` for MATLAB NaN-tolerant semantics.
   - Tests: 13/13 pass. Full WSL suite: 515 passed (502 → 515).
   - Committed Phase A (rules 1-5 calcFluxBounds port).

2. **User: "carry on" → "phase 3" → corrected to "phase c"**
   - Inventoried existing chassis: `KarrMetabolismProcess` solves static FBA; M2 writes NTP deltas; M3 writes `AA_total` placeholder; flat `substrates` store with `_default=1.0`.
   - First rubber-duck critique caught fundamental flaw: my proposed `S@v` writeback is mathematically zero (LP enforces `S@v=0`). Real coupling must come from M1 **reading** M2/M3 demand into private state.
   - **Phase B implemented:**
     - Added `lb_override`/`ub_override` to `solve_fba` (no in-place mutation).
     - Rewrote `KarrMetabolismProcess` with `dynamic_bounds=False` default + `dynamic_bounds=True` mode: holds private `_sub_state(585,3)`, `_enz_state(104)`, drains cytosol from shared-store deltas each tick via `_KARR_DEMAND_KEYS` (4 NTPs + 20 AAs), recomputes bounds, solves with overrides.
     - Added `m1_dynamic_diagnostics` emit-only port.
     - Updated composer with `dynamic_bounds` kwarg.
     - 3 bugs caught & fixed: lazy `_prev_shared` init missed first delta (init at 1.0 in `__init__`); growth check should skip t=0 emit; NaN warning in bound-change counter (`np.not_equal` instead of `np.abs(diff) > tol`).
     - 13/13 Phase B tests pass.
     - Wrote `scripts/demo_central_dogma_dynamic.py`; honest finding: ATP/GTP cytosol drains in 1s (M2 has no substrate awareness — Phase C motivator); CTP/UTP cytosol = 0 in Karr's snapshot (fast-turnover); AAs flat (M3 only writes `AA_total` placeholder).
   - Full WSL suite: 528/528 pass.
   - Committed Phase B.

3. **User: "phase c"**
   - Audited M1 enzyme(104) ↔ M3 protein monomer(482) overlap: 25/104 are direct monomers; 79/104 are complexes (DIMER/TRIMER/TETRAMER/HEXAMER/PENTAMER/OCTAMER + 22MER + 192MER). Wiring M3→enzymes properly needs `proteinComplexComposition` extraction.
   - Second rubber-duck critique on Phase C scope. Key findings adopted:
     - **Don't overload `substrates`** with both counts and deltas — keep two separate stores: `m1_pools` (M1 sole writer, `set` updater) and `substrates` (M2/M3 deltas, `accumulate`).
     - `S@v=0` objection is correct; `m1_pools` is cleaner than fake production write-back.
     - **Throttle must scale the integrator's synth rate**, not just emitted deltas. Linear throttle by min-pool fraction.
     - Existing tests will break: `test_karr_m3_chassis.py`, `test_karr_central_dogma_chassis.py` (both reference `AA_total`).
     - Defer dynamic enzymes + rule 6 to Phase D.
   - Started C.1 (per-AA deltas): probed M3 fixture — `base_counts(482, 722)` exists but **the 722 column→ID map is NOT in fixture**. Only 31/722 columns are nonzero (the metabolite consumption columns).
   - Wrote `scripts/matlab/extract_m3_metabolite_vocab.m` to extract the 722 IDs.
   - **Ran MATLAB extractor — FAILED** with "data/sim_fitted_targeted.mat not found; run from repo root". MATLAB CWD wasn't repo root.
</history>

<work_done>
**Files created/modified this segment:**

Phase A finalization (committed):
- `opencell/m1/karr_metabolism.py` — added `catalysis` field to `KarrMetabolismModel` dataclass; added `lb_override`/`ub_override` to `solve_fba` (Phase B prep).
- `opencell/m1/calc_flux_bounds.py` — switched to `np.fmax`/`np.fmin` for NaN-tolerant max/min; wrapped Rule 1 in `np.errstate(invalid="ignore")`.
- `tests/m1/test_calc_flux_bounds.py` — `m1.raw_catalysis()` → `m1.catalysis`; NaN-safe diff helper.
- `opencell/m1/__init__.py` — exports `M1DynamicsInputs`, `load_default_dynamics`, `compute_bounds`, `calc_flux_bounds` submodule.

Phase B (committed):
- `opencell/vivarium/karr_m1.py` — full rewrite: dual-mode (static/dynamic), `_KARR_DEMAND_KEYS` constant, `_CYTOSOL_COMPARTMENT_0=0`, `_diagnostics_schema()`, drain-on-delta loop, `m1_dynamic_diagnostics` port.
- `opencell/vivarium/karr_composite.py` — `dynamic_bounds=False` kwarg threaded through `build_karr_m1_m2_m3_engine`.
- `tests/m1/test_dynamic_bounds_chassis.py` — 13 Phase B tests.
- `scripts/demo_central_dogma_dynamic.py` — companion to static demo, with helper-derived snapshot pool checks (no hardcoded biology).
- `artifacts/demo_central_dogma_dynamic.{json,png}` — demo outputs.

Phase C (in progress, NOT committed):
- `scripts/matlab/extract_m3_metabolite_vocab.m` — small MATLAB extractor for 722-metabolite vocab. **FAILED on CWD.**

**Test status:**
- Phase A: 13/13 ✅
- Phase B: 13/13 ✅
- Full suite: 528/528 ✅ (502 baseline + 13 Phase A + 13 Phase B)

**Phase C work completed:**
- [x] Audit of M1↔M3 enzyme overlap (25/104 monomer / 79/104 complex)
- [x] Rubber-duck critique with adopted findings
- [x] MATLAB extractor written
- [ ] MATLAB extractor RUN (blocked: CWD)
- [ ] M3 wrapper rewrite (per-AA deltas)
- [ ] `m1_pools` shared port + dual-store topology
- [ ] M2/M3 throttling in `step_analytical`
- [ ] Update broken tests (`test_karr_m3_chassis.py`, `test_karr_central_dogma_chassis.py`)
- [ ] Update demo C4 checks (no-demand → drained)
- [ ] Run full suite + commit
</work_done>

<technical_details>

**Phase C critique-driven design (adopted):**

Two-store topology:
- `m1_pools` — authoritative cytosol counts, M1 SOLE writer, `_updater: "set"`. M2/M3 read for throttle.
- `substrates` (existing) — demand deltas, M2/M3 writers `accumulate`. M1 still reads to drain `_sub_state`.
- M2/M3 read from `m1_pools`, NOT `substrates`, for the throttle source-of-truth.

Throttle math (linear, scales integrator):
```
f = min over s in {NTPs or AAs} of clamp(pool[s] / (consumption_rate[s] * dt), 0, 1)
synth_eff = f * synth_rate_per_s
state_next = step_analytical(synth=synth_eff, ...)
delta_eff[s] = -consumption_rate[s] * f * dt   # written to substrates
```
Apply `f` to BOTH the integrator update AND the substrate-delta emission. Hard-step would create chatter.

**722-metabolite vocab gap (Phase C blocker):**
- M3's `base_counts` is `(482, 722)` — per-monomer composition over Karr's metabolite vocabulary.
- The 722 column→WCM-ID list is NOT in any fixture. Only `protein_wcm_482`, `gene_wcm_482`, `compartment_wcm_482` are saved.
- `Metabolite.wholeCellModelIDs` from `sim.state('Metabolite')` should give it (might match the 585 substrate IDs or be a superset including compartment expansion).
- Need to extract from MATLAB.
- `data/karr_fixtures/karr_native_m3.npz` keys: `mature_index_4820, length_aa, half_life_s, decay_rate_per_s, molecular_weight, compartment_index, counts_mature, synth_rate_per_s, base_counts`.

**MATLAB extraction commands:**
- Run from repo root: `& 'E:\MATLAB\bin\matlab.exe' -batch "addpath('scripts/matlab'); extract_m3_metabolite_vocab"`
- The extractor I wrote does `if exist('data/sim_fitted_targeted.mat', 'file') ~= 2 → error` because MATLAB launched from `E:\` instead of `E:\opencell`. **Fix: cd to repo root before launching MATLAB, or pass `-sd`.**
- Trial license is fine.

**M1↔M3 enzyme audit results:**
- 25/104 enzymes are direct monomers in M3's 482-protein space (no _MONOMER suffix overlap).
- 79/104 enzymes are complexes:
  - 40 DIMER, 25 MONOMER (modified, e.g., MG_124_MONOMER_ox), 14 TETRAMER, 6 HEXAMER, 2 TRIMER, 1 OCTAMER + ~12 hetero-complexes (PENTAMER mostly), 1 22MER, 1 192MER.
- **Phase D needs**: `proteinComplexComposition` matrix from MATLAB to assemble 79 complex counts from monomer counts + stoichiometry.

**Phase B finding catalogue (do not regress):**
- Karr's snapshot has cytosol ATP=GTP=36234 each, CTP=UTP=0 (fast turnover).
- M2 demand under chassis tick consumes ~36k of each NTP per second → ATP/GTP drain to 0 in 1 tick; CTP/UTP stay clamped at 0.
- AAs flat in shared store because M3 still emits only `AA_total`.
- `n_active_bounds_changed` is 369 every tick (rules 4/5 dominate).

**LP/FBA gotchas:**
- `S @ v = 0` for all 376 rows (RHS is all zeros) — LP enforces. Naive `S @ v` writeback is a no-op.
- Exchange columns: positive flux = uptake (consumes external pool); negative = secretion. Biomass row: net consumes NTPs/AAs.
- 376 FBA-substrate rows = 368 real + 7 internal-exch constraints + 1 biomass pseudo-row.

**Existing tests that will break in C.1:**
- `tests/vivarium/test_karr_m3_chassis.py` lines 23 (`assert "AA_total" in schema["substrates"]`), 37-41 (asserts `aa[-1] < 0` against `_total_aa_per_s` from `aa_consumption_per_s`).
- `tests/vivarium/test_karr_central_dogma_chassis.py` lines 84-88 (same pattern).
- `scripts/demo_central_dogma_dynamic.py` C4 checks (`no-demand-stays-flat`).

**M3 chassis test relies on:**
- `aa_consumption_per_s(model)["_total_aa_per_s"]` — the bulk total. Already exists.
- `aa_consumption_per_s(model)["_per_metabolite_per_s_722"]` — per-722 vector. Already computed.
- `model.length_aa`, `model.synth_rate_per_s`, `model.base_counts` — all in fixture.

**M2 chassis test:**
- `tests/vivarium/test_karr_m2_chassis.py` — assumes M2 doesn't read pools. Will need throttle-aware update or default-disabled throttle path.

**Environment:**
- WSL venv: `wsl bash -c "source .venv-wsl/bin/activate && python ..."`
- Full WSL test suite: ~12-13 min (now 528 tests).
- MATLAB: `& 'E:\MATLAB\bin\matlab.exe' -batch "..."` from PowerShell. Trial license OK. CWD matters.
- Local Windows venv lacks scipy.

**Commit message style:**
Use file-based: `git commit -F .git-commit-msg.tmp` (PowerShell breaks long `-m` chains). Always include `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.

</technical_details>

<important_files>

- `opencell/vivarium/karr_m1.py` ✅ Phase B (committed)
  - Dual-mode KarrMetabolismProcess. Phase C will modify: M2/M3 stop writing to drain channel, M1 publishes `m1_pools` port.
  - Lines 28-50: `_KARR_DEMAND_KEYS` constant (4 NTPs + 20 AAs in Karr's 585 ID space). `_CYTOSOL_COMPARTMENT_0=0`.
  - Lines 100-130: `_diagnostics_schema()` — 5 scalars + per-demand cytosol fields.
  - Lines 175-235: `_dynamic_update()` — drain loop, `compute_bounds`, FBA solve with overrides.

- `opencell/vivarium/karr_m2.py` (existing, will modify in C.2)
  - Lines 71-90: `next_update` runs `step_analytical` with full `synth_rate_per_s`. Phase C will add throttle factor `f` from `m1_pools` reads.

- `opencell/vivarium/karr_m3.py` (existing, will modify in C.1+C.2)
  - Lines 50-58: schema declares `AA_total`. Phase C: replace with 20-AA dict using metabolite_722_ids.
  - Lines 71-77: writes `AA_total` delta. Phase C: write 20 per-AA deltas.

- `opencell/m3/translation.py` (existing)
  - Lines 120-132: `aa_consumption_per_s` returns `_total_aa_per_s` + `_per_metabolite_per_s_722`. Phase C: add per-AA dict mapping known AA WCM IDs to consumption.

- `opencell/m2/transcription.py` (existing)
  - Lines 96-129: `step_analytical` (analytical first-order ODE). Phase C: add optional `synth_scale: float` parameter.
  - Lines 132-148: `ntp_consumption_per_s` — ATP/CTP/GTP/UTP via uniform 1/4 split (placeholder; M2 v2 has real composition).

- `opencell/vivarium/karr_composite.py` (committed Phase B)
  - Phase C: drop `AA_total` initial-state seed (line ~70 in current file); add `m1_pools` initial state; thread throttle param.

- `tests/vivarium/test_karr_m3_chassis.py`
  - Lines 23, 37-41: hardcoded `AA_total` asserts. Phase C: rewrite to per-AA assertions.

- `tests/vivarium/test_karr_central_dogma_chassis.py`
  - Lines 83-88: hardcoded `AA_total` asserts. Phase C: rewrite.

- `scripts/matlab/extract_m3_metabolite_vocab.m` ✅ NEW (uncommitted, NOT YET RUN)
  - Will extract 722-metabolite vocab → `data/m1_sources/karr_flat/m3_metabolite_vocab.mat`.
  - **Currently fails on CWD** — needs MATLAB launched from `E:\opencell`, not `E:\`. Fix: change PowerShell command to `cd E:\opencell; & 'E:\MATLAB\bin\matlab.exe' -batch "..."` (already does this) — actual issue may be that MATLAB ignores PowerShell's CWD. Try `-sd "E:\opencell"` flag or absolute path in script.

- `scripts/demo_central_dogma_dynamic.py` ✅ Phase B (committed)
  - C3-NTP checks honest about ATP/GTP drain vs CTP/UTP staying-zero.
  - C4-AA checks "no-demand-stays-flat" (regression guard for Phase C wiring). Phase C: flip to "drained".

- `data/karr_fixtures/karr_native_m1_dynamics.{json,npz}` ✅ Phase A
  - M1DynamicsInputs source. `compute_bounds()` derives bounds from this.

- `data/karr_fixtures/karr_native_m3.json` (existing)
  - M3 model fixture; lacks 722-metabolite ID list. Phase C: add `metabolite_wcm_722` to ids block once extracted.

</important_files>

<next_steps>

**Immediate (resume here):**

1. **Re-run MATLAB vocab extractor with absolute path:**
   ```powershell
   cd E:\opencell
   & 'E:\MATLAB\bin\matlab.exe' -sd 'E:\opencell' -batch "addpath('scripts/matlab'); extract_m3_metabolite_vocab"
   ```
   Or modify the .m to use absolute path. Verify `data/m1_sources/karr_flat/m3_metabolite_vocab.mat` produced.

2. **Write Python ingester** that loads the .mat, finds the 20 standard AA columns by WCM ID matching against `_KARR_DEMAND_KEYS[4:]` (the 20 AAs), and writes `metabolite_wcm_722` array into the M3 fixture (regenerate `karr_native_m3.json` or save a side-car JSON).

3. **Update `opencell/m3/translation.py`:**
   - `aa_consumption_per_s()` returns dict with `ALA, ARG, ..., VAL` keys (using base_counts × synth_rate × col_idx for each AA WCM ID).

4. **Update `opencell/vivarium/karr_m3.py`:**
   - Schema: replace `AA_total` with the 20 AA WCM IDs.
   - `next_update`: write per-AA deltas.

5. **Add `m1_pools` shared port:**
   - In `karr_m1.py` dynamic mode: schema declares `m1_pools` (set updater) for the 24 demand keys; `next_update` writes `_sub_state[idx, 0]` each tick.
   - In `karr_m2.py` and `karr_m3.py`: schema declares `m1_pools` read-only; on tick, compute throttle factor `f` from `m1_pools` values and consumption rates, pass to `step_analytical(..., synth_scale=f)` and to delta emission.

6. **Update integrators:**
   - `transcription.step_analytical(model, rna_counts, dt_s, condition=1, synth_scale=1.0)` — multiply `s_per_s` by `synth_scale`.
   - `translation.step_analytical(model, protein_counts, dt_s, synth_scale=1.0)` — same.

7. **Update composer `build_karr_m1_m2_m3_engine`:**
   - Drop `AA_total` from initial substrates.
   - Add `m1_pools` initial state seeded from M1's snapshot if `dynamic_bounds=True`.
   - Add topology entries for `m1_pools` on all three processes.
   - Add `enable_throttle: bool = False` kwarg (default off for back-compat with existing 528 baseline; tests opt in).

8. **Fix existing broken tests:**
   - `tests/vivarium/test_karr_m3_chassis.py` lines 23, 37-41.
   - `tests/vivarium/test_karr_central_dogma_chassis.py` lines 83-88.
   - Demo `scripts/demo_central_dogma_dynamic.py` C4 checks.

9. **Add new Phase C tests (~10):**
   - M3 schema has 20 AA keys, no `AA_total`.
   - M3 per-AA delta sums match `_total_aa_per_s` ± tolerance.
   - `m1_pools` port populated; M1 sole writer.
   - Throttle off (default): integrators identical to today.
   - Throttle on, abundant pools: f≈1, integrators within tol of unthrottled.
   - Throttle on, depleted pool: f→0, RNA/protein integration freezes; deltas → 0.
   - Two-store separation: `substrates` accumulates negative deltas; `m1_pools` set-writes.

10. **Run full WSL suite, commit Phase C.**

11. **Document Phase D scope** in commit message (proteinComplexComposition extraction, dynamic enzymes, rule 6).

**Open questions:**
- Whether `metabolite_722_ids` will exactly match `substrate_wcm_585` plus 137 dups, or be a different vocabulary. Determines ingester logic.
- Should throttle be default-on or default-off? Default-off is back-compat-safe but the dynamic demo loses its main motivation. Suggest: default-off, dynamic demo enables both `dynamic_bounds=True` and `enable_throttle=True`.

**SQL todos:**
- `m1-substrate-writeback` already marked done (Phase B).
- Phase C is its own scope (not currently a separate todo) — could add `m1-phase-c-throttle` if needed.

</next_steps>