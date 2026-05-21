<overview>
OpenCell whole-cell sim of *M. genitalium* in Python on Karr 2012 WCM data + vivarium-core. This segment closed the **Phase C.1** sub-task: replaced M3's `AA_total` placeholder with 20 per-amino-acid deltas keyed by Karr's standard-AA WCM IDs, unblocking the M3→M1 demand handshake under dynamic-bounds. The 722-metabolite vocab gap was closed by extracting the column→ID map from the MATLAB knowledgeBase. 528/528 tests pass. Commit is staged but **not yet finalized** due to a PowerShell pipeline error.
</overview>

<history>
1. **User: "I meant phase c"** (from prior segment) — was already mid-Phase C with MATLAB extractor blocked on CWD.

2. **This segment: continuing Phase C.1** (per-AA deltas)
   - Found `sim_fitted_targeted.mat` actually lives at `data/m1_sources/karr_flat/`, not `data/`.
   - Iteratively fixed `scripts/matlab/extract_m3_metabolite_vocab.m` through 4 MATLAB runs as struct paths revealed themselves: `s.data` not `s.sim` → `data.states` not `data.ProteinMonomer` → `State_ProteinMonomer` not `ProteinMonomer` → discovered State objects only carry `wholeCellModelID, name, stateNames`, NOT the 722 metabolite IDs.
   - Pivoted to `data.metabolism.substrateWholeCellModelIDs` (585 IDs, matches M1 vocab — wrong size for M3's 722).
   - Pivoted to `knowledgeBase_targeted.mat` via Python `scipy.io.loadmat` — found `kb.metabolites` (722 mat_structs, each with `.wholeCellModelID`), `kb.aminoAcidIndexs` (21 entries: 20 standard AAs + FMET, 1-based MATLAB indexing).
   - Extracted directly in Python (`_probe_kb.py`), wrote `data/karr_fixtures/karr_native_m3_vocab.json` with the 722 WCM IDs + AA col indices.
   - Verified: 20-AA row-sum matches `length_aa` for 449/482 proteins (33 with diffs ≤11 due to modified/non-standard residues — tolerable).

3. **Implemented Phase C.1 surgically** (per-AA deltas only; deferred m1_pools + throttle to follow-up commit):
   - `opencell/m3/translation.py`: added `aa_wcm_ids`, `aa_col_indices` fields to `KarrTranslationModel`; `load_default()` now reads vocab JSON (raises if missing); `aa_consumption_per_s()` returns 20 per-AA floats keyed by WCM ID + back-compat keys; added `synth_scale=1.0` to `step_analytical()`.
   - `opencell/m2/transcription.py`: added `synth_scale=1.0` to `step_analytical` + `ntp_consumption_per_s` (throttle hook for next sub-step).
   - `opencell/vivarium/karr_m3.py`: schema declares 20 AA WCM IDs (no `AA_total`); `next_update` writes `-rate_a * dt` per AA.
   - `opencell/vivarium/karr_composite.py`: dropped `AA_total` placeholder seed (the 20 AA IDs already live in M1's 585 substrate vocab).
   - Updated `tests/vivarium/test_karr_m3_chassis.py` and `test_karr_central_dogma_chassis.py` to assert 20-AA per-key behavior.
   - Updated `scripts/demo_central_dogma.py` C4 check + figure to per-AA.
   - Updated `scripts/demo_central_dogma_dynamic.py` C4: flipped from "no-demand stays flat" (Phase B regression guard) to "drained-from-snapshot".

4. **Validation**:
   - 38/38 targeted tests pass (M3 chassis + composite + dynamic-bounds).
   - Full WSL suite: **528/528 passing in 12:42**.
   - Dynamic demo: ALA 8303→8172, GLU 9518→9378, LYS 15094→14840 over horizon. All checks pass.

5. **Commit attempt FAILED**: `git add -A; git commit -F .git-commit-msg.tmp 2>&1 | tail -10` — `tail` is not a PowerShell cmdlet. The `git add -A` ran (files are staged) but `git commit` may not have. Last verified state: `git status --short` shows all files staged with `A`/`M` markers, HEAD still at `255125b` (Phase B). **The Phase C.1 commit is staged but not committed yet.**
</history>

<work_done>
**Files created/modified this segment:**

NEW:
- `data/karr_fixtures/karr_native_m3_vocab.json` (11.2 KB) — 722 metabolite WCM IDs, aminoAcidIndexs (0-based), 20 standard-AA WCM IDs, water/hydrogen/fmet indices.
- `scripts/matlab/extract_m3_metabolite_vocab.m` — MATLAB extractor (kept for regeneration; the actual extraction this segment used the Python `scipy.io.loadmat` path on `knowledgeBase_targeted.mat`).

MODIFIED:
- `opencell/m3/translation.py` — added `AA_WCM_IDS` constant, `_load_aa_vocab()`, model fields `aa_wcm_ids`/`aa_col_indices`, per-AA `aa_consumption_per_s()`, `synth_scale` arg.
- `opencell/m2/transcription.py` — added `synth_scale` arg to `step_analytical` + `ntp_consumption_per_s` (lines ~96-148).
- `opencell/vivarium/karr_m3.py` — full rewrite of schema + `next_update` for 20-AA writeback.
- `opencell/vivarium/karr_composite.py` — dropped `AA_total` seed from `initial_substrates`; updated docstring.
- `tests/vivarium/test_karr_m3_chassis.py` — assertions on 20 AA keys + bulk reconstruction tolerance (line 24 + 37-50).
- `tests/vivarium/test_karr_central_dogma_chassis.py` — per-AA assertions in `test_shared_substrates_carry_m2_and_m3_consumption` (lines 63-89).
- `scripts/demo_central_dogma.py` — C4 per-AA check + figure panel.
- `scripts/demo_central_dogma_dynamic.py` — C4 flipped from regression guard to drained-from-snapshot.
- `artifacts/demo_central_dogma_dynamic.json` — regenerated from demo run.

DELETED (cleanup): `_find_aa_cols.py`, `_probe_kb.py`.

**Tests:**
- Targeted suite (38 tests): all pass.
- Full WSL suite: **528/528 pass** (no test count change; existing 13 Phase A + 13 Phase B + 4 chassis-composition tests retained).

**Work completed:**
- [x] MATLAB extractor unblocked (CWD path)
- [x] 722 metabolite vocab extracted (Python via knowledgeBase_targeted.mat)
- [x] Per-AA M3 deltas wired
- [x] Tests updated, full suite passing
- [x] Demos updated, dynamic demo verified to drain AA pools
- [x] Commit message drafted at `.git-commit-msg.tmp`
- [x] Files staged via `git add -A`
- [ ] **Commit NOT FINALIZED** — `git commit -F .git-commit-msg.tmp` failed because `| tail -10` is invalid PowerShell. Files remain staged.
</work_done>

<technical_details>

**722-metabolite vocab extraction path (definitive):**
- Source: `data/m1_sources/karr_flat/knowledgeBase_targeted.mat`.
- Python: `scipy.io.loadmat(path, squeeze_me=True, struct_as_record=False)`.
- Access: `m['data'].knowledgeBase.metabolites` → 722-array of mat_structs, each with `.wholeCellModelID` (string).
- `kb.aminoAcidIndexs`: 21-element 1-based MATLAB index array (20 standard AAs + FMET at position 21). Order: ALA, ARG, ASN, ASP, CYS, GLN, GLU, GLY, HIS, ILE, LEU, LYS, MET, PHE, PRO, SER, THR, TRP, TYR, VAL, FMET.
- `kb.fmethionineIndexs` = 295 (1-based) → col 294 (0-based) → "FMET".
- Other useful indexes: `waterIndexs`, `hydrogenIndexs`, `methionineIndexs`, `cysteineIndexs`.
- The `sim_fitted_targeted.mat` (`data.states.State_ProteinMonomer`) only has `x_class, wholeCellModelID, name, stateNames` — no metabolite IDs. The vocab MUST come from knowledgeBase, not sim.

**Per-AA verification gotcha:**
- Sum of 20 AA `base_counts` columns equals `length_aa` for 449/482 proteins; 33 proteins have diffs up to 11 (modified residues, diacylglycerol-cysteine, etc.). Tests use `<= |total| * 1.001` tolerance and `> 0.85` lower bound for the bulk-from-per-AA reconstruction (FMET + modifications account for the gap).

**FMET handling decision (stated in code):**
- Code comment in `translation.py`: "FMET is excluded; M1's substrate vocabulary does carry FMET separately but central-dogma chassis treats FMET demand as MET (initiator-methionine consumption is one-per-protein-per-synth)." — i.e., we did NOT add FMET to the 20 keys; this leaves a known small under-counting visible in `_total_aa_per_s` vs sum-of-20.

**The 20 AA WCM IDs are already in Karr's 585 substrate vocab** — verified because `_KARR_DEMAND_KEYS` in karr_m1.py contains them (with `if sid in self._sub_id_to_idx` filter). So no extra placeholder schema key is needed in the composer.

**PowerShell quirk that broke the commit:**
- `tail` is not a PowerShell cmdlet. Use `Select-Object -Last N` instead. `git commit -F file.tmp` should be run without piping to tail. The `2>&1 | tail -10` after `git commit` failed; need to re-run `git commit -F .git-commit-msg.tmp` cleanly. **The .tmp file was deleted at the end of the failed command.**

**Commit-message file template** is documented elsewhere in the project: always include `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.

**Test runtime:** Full WSL suite is 12-13 min (528 tests).

**Phase C remaining (NOT this commit):**
- C.2 m1_pools shared port (M1 sole writer, set updater) for 24 demand keys.
- C.3 Substrate-aware throttle in M2/M3 driven by m1_pools (`synth_scale` is already wired; just need m1_pools reads + min-pool fraction calc).
- C.4 New tests for throttle behaviour.
- D.0 proteinComplexComposition extraction (79 of 104 enzymes are complexes).

**Phase B regression guard now flipped (notable behaviour change):**
- Phase B's dynamic demo asserted "no AA demand → flat AA pools" as a deliberate regression guard for the Phase C wiring. This is now correctly inverted to "drained-from-snapshot" (proven: ALA 8303→8172 over demo horizon).
</technical_details>

<important_files>

- `data/karr_fixtures/karr_native_m3_vocab.json` ✅ NEW (staged)
  - 722 metabolite WCM IDs + AA col indices. Required by `m3.translation.load_default()`.

- `opencell/m3/translation.py` ✅ MODIFIED (staged)
  - Lines 1-50: module docstring + AA_WCM_IDS constant (20-tuple, no FMET).
  - Lines 80-105: `_load_aa_vocab()` — raises if vocab JSON missing.
  - Lines 130-160: `step_analytical(..., synth_scale=1.0)` — chassis throttle hook.
  - Lines 165-195: `aa_consumption_per_s()` returns dict with 20 per-AA floats + `_total_aa_per_s` + `_per_metabolite_per_s_722`.

- `opencell/m2/transcription.py` ✅ MODIFIED (staged)
  - Lines ~96-148: `step_analytical` and `ntp_consumption_per_s` gain `synth_scale=1.0`.

- `opencell/vivarium/karr_m3.py` ✅ MODIFIED (staged)
  - Schema: 20 AA WCM IDs from `model.aa_wcm_ids`.
  - `next_update`: writes `{aa: -rate_a * timestep for aa in aa_ids}`.
  - `build_karr_m3_engine`: initial substrates from `proc.aa_ids`.

- `opencell/vivarium/karr_composite.py` ✅ MODIFIED (staged)
  - Dropped `AA_total` placeholder seed; updated topology docstring.

- `tests/vivarium/test_karr_m3_chassis.py` ✅ MODIFIED (staged)
  - Asserts no `AA_total` key; 20 AA keys present; per-AA delta vs helper; bulk reconstruction tolerance.

- `tests/vivarium/test_karr_central_dogma_chassis.py` ✅ MODIFIED (staged)
  - `test_shared_substrates_carry_m2_and_m3_consumption` checks per-AA negative deltas.

- `scripts/demo_central_dogma.py` ✅ MODIFIED (staged)
  - C4 check is per-AA; figure panel plots engine-sum vs helper-bulk.

- `scripts/demo_central_dogma_dynamic.py` ✅ MODIFIED (staged)
  - C4 flipped from "no-demand stays flat" to "drained-from-snapshot".

- `scripts/matlab/extract_m3_metabolite_vocab.m` ✅ NEW (staged)
  - MATLAB regeneration path; CWD fixed to `data/m1_sources/karr_flat/sim_fitted_targeted.mat`. Note: this script doesn't actually produce the vocab JSON — that was done by inline Python. Keep for documentation/future regen.

- `opencell/vivarium/karr_m1.py` (UNCHANGED)
  - `_KARR_DEMAND_KEYS` already contains the 20 AA WCM IDs in Karr's 585 space; M1's dynamic-bounds drain loop now picks up the per-AA M3 writes automatically. This is why the demo C4 flip works without M1 modifications.

- `data/karr_fixtures/karr_native_m1_dynamics.json` (UNCHANGED but contains stale `AA_total` reference at line 58 in a name field — harmless metadata; not consumed by `_KARR_DEMAND_KEYS`).
</important_files>

<next_steps>

**IMMEDIATE (resume here):**

1. **Re-create commit message file** (was deleted by failed command). Then run:
   ```powershell
   cd E:\opencell
   # Recreate .git-commit-msg.tmp with the same content (see below)
   git commit -F .git-commit-msg.tmp
   Remove-Item .git-commit-msg.tmp
   git log --oneline -3
   ```
   The commit message body should match what was in the prior `create` call (Phase C.1 description with full provenance). All files are already staged via `git add -A`. Do NOT pipe `git commit` through `| tail` — PowerShell doesn't have `tail`; use `| Select-Object -Last N` or just let it print fully.

2. **Verify commit landed** with `git log --oneline -1` showing a Phase C.1 commit on top of `255125b`.

**Then proceed with Phase C remaining (separate commits):**

3. **C.2 — m1_pools shared port:**
   - In `karr_m1.py` dynamic mode: add `m1_pools` schema (set updater) for the 24 demand keys; in `_dynamic_update`, write `_sub_state[idx, 0]` per tick.
   - Add to `karr_m1.py::build_karr_m1_engine` and composer: declare `m1_pools` topology entry on M1, M2, M3.
   - Composer: seed `m1_pools` initial state from M1 snapshot.

4. **C.3 — Throttle in M2/M3:**
   - M2/M3 read `m1_pools` (read-only), compute `f = min over s in demand_set of clamp(pool[s] / (consumption_rate[s] * dt), 0, 1)`.
   - Pass `synth_scale=f` to `step_analytical` AND apply `f` to substrate-delta emission.
   - Add `enable_throttle: bool = False` kwarg to composer for back-compat.

5. **C.4 — New tests (~10):**
   - m1_pools port populated; M1 sole writer.
   - Throttle off: integrators identical to today.
   - Throttle on, abundant pools: f≈1, behaviour ≈ unthrottled.
   - Throttle on, depleted pool: f→0, integration freezes; deltas → 0.

6. **D.0 (later) — Extract `proteinComplexComposition` matrix from MATLAB** for the 79 enzyme complexes (DIMER/TRIMER/etc.).

**Open questions:**
- Default for `enable_throttle`: off recommended (back-compat with 528 baseline; demo can opt-in).
- FMET handling: currently subsumed into MET demand implicitly (FMET excluded from 20-key set). Revisit if biomass calibration suffers.

**SQL todos:** Phase C is one logical unit; no DB todo updates needed unless adding granular tracking.

**Commit message body to recreate** (Phase C.1, ~3.4KB) — see prior conversation for verbatim text. Key points to preserve: 722-vocab gap closure path (knowledgeBase_targeted.mat → kb.metabolites/aminoAcidIndexs → vocab JSON), library changes summary, test/demo updates, 528/528 pass, Phase C remaining roadmap.
</next_steps>