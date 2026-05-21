<overview>
OpenCell — open-source whole-cell simulation of *M. genitalium* in Python. This session pivoted M1 metabolism off iPS189 onto Karr's native FBA matrices, shipped a per-reaction validation oracle that PASSED (median |log2 ratio| = 0.96 over 196 rxns), wrapped M1 as a 1-second-tick vivarium Process (chassis tick proof), cleaned up all iPS189 surface area, and started M2 — pivoting it from "nucleotide biosynthesis" (now redundant inside Karr's full FBA) to **transcription** as the natural next-real-process layer.
</overview>

<history>

1. **User: "start with closing the 7x gap"** (from prior session, summarised)
   - Closed structurally: snapshot enzyme bounds are post-step (proven by 34/504 of Karr's stored fluxs violating them). Mode D rewritten dropping enzyme bounds + BIG=1e3; Mode E added as gold-standard oracle. Committed as `c5244f2`. (Pre-compaction summary.)

2. **User: "what is a deviation from the complete cell simulation?"**
   - Listed honest deviations: static snapshot vs dynamic loop (#1), 1/7 modules done, deterministic vs stochastic, no spatial geometry, oracle pivot from wet-lab μ to Karr-vs-Karr, unmodeled processes Karr himself dropped, *M. genitalium* itself a deviation from "a cell".

3. **User: "don't update the framing... do we proceed to M2 or is there any further debugging needed?"**
   - Recommended NOT proceeding: M1 not actually validated (only re-instrumented), no dynamic-loop chassis. Two pre-M2 todos: per-reaction oracle + vivarium wrapper.

4. **User: "yeah, do that"**
   - Started building per-reaction oracle. Built ID mapping table iPS189→Karr WCM IDs.

5. **User: "wait, why are we still using iPS189? can't we use the data from Karr directly?"**
   - Good catch. Explained: iPS189 was a months-old compromise from before MAT extraction worked. Now redundant. Recommended pivot.

6. **User: "no, let's shift to Karr"**
   - Built `scripts/karr_native_ingest_m1.py` extracting Karr's FBA snapshot to `data/karr_fixtures/karr_native_m1.{json,npz}`.
   - Built `opencell/m1/karr_metabolism.py` (KarrMetabolismModel + solve_fba + per_reaction_comparison).
   - Rewrote `scripts/m1_per_reaction_oracle.py` as Karr-vs-Karr (no mapping table).
   - Result: biomass = 0.039/h vs stored 0.076/h (0.514×); per-reaction median |log2 ratio| = **0.96** over 196 rxns, threshold <1.0 → **PASSED**.
   - 7 new tests in `tests/m1/test_karr_metabolism.py`; 460/460 total. Committed.

7. **User: "start the wrapper"**
   - Built `opencell/vivarium/karr_m1.py` with `KarrMetabolismProcess` + `build_karr_m1_engine`.
   - 4 chassis tests in `tests/vivarium/test_karr_m1_chassis.py`. Initial drift assertion failed because t=0 is initial-state default, not predicted; tightened to `arr[1:]`. 464/464 pass. Committed as `041caab`.

8. **User: "clean-up iPS189 and start with M2"**
   - Deleted: `opencell/m1/central_carbon.py`, `tests/m1/test_central_carbon.py`, `data/karr_fixtures/iPS189_m1.json`, `data/m1_sources/iPS189.xml`, `scripts/{karr_a4f_*,m1_inspect_*,m1_validate}.py`, `artifacts/{M1_validation,karr_a4f_*}.{json,jsonl}`, `docs/phase5/M1_validation_report.md`. Updated `opencell/m1/__init__.py` to re-export Karr-native API. 452/452 pass. Committed.
   - **Flagged a rethink**: "M2 nucleotides" is now redundant since Karr-native M1 covers ALL of Karr's FBA (including nucleotide synthesis, AAS, lipids, cofactors). Suggested M2 → transcription.

9. **User: "pick up transcription"**
   - Probed MAT: found Process_Transcription.parameters.rnaPolymeraseElongationRate (50 nt/s), fittedConstants.transcriptionUnitBindingProbabilities (335,), KB.knowledgeBase.genes (525) with halfLife/synthesisRate/expression/length, transcriptionUnits (335).
   - Built `scripts/karr_native_ingest_m2.py`. **Unit bug**: synthesisRate is per-MINUTE not per-second; predicted 123 vs expression 2.05 (60× off). Fixed: carry both per-min and per-s arrays.
   - Realized synthesisRate is *fitted* to make expression come out right, so naive oracle is tautological. Reframed M2 as **v1 = Karr-prescribed-rates module** (Mode-E pattern); v2 deferred = derive synthesis from polymerase mechanics.
   - Built `opencell/m2/transcription.py` (KarrTranscriptionModel + step_analytical + ntp_consumption_per_s) and `opencell/vivarium/karr_m2.py` (KarrTranscriptionProcess + build_karr_m2_engine).
   - Wrote 6 tests in `tests/m2/test_transcription.py` and 3 in `tests/vivarium/test_karr_m2_chassis.py`.
   - **BLOCKED**: directories `opencell/m2/` and `tests/m2/` weren't created on disk by the parallel `New-Item` (it ran but the create-file calls said "Parent directory does not exist"). Test run errored with `ImportError: cannot import name 'transcription' from 'opencell.m2' (unknown location)`.

</history>

<work_done>

**Files created/modified this session (committed):**
- `opencell/m1/karr_metabolism.py` — Karr-native FBA model
- `opencell/m1/__init__.py` — re-exports Karr-native API
- `opencell/vivarium/karr_m1.py` — KarrMetabolismProcess + build_karr_m1_engine
- `opencell/vivarium/__init__.py` — exports vivarium adapters (now also m2)
- `scripts/karr_native_ingest_m1.py` — extractor for M1 fixture
- `scripts/m1_per_reaction_oracle.py` — Karr-vs-Karr oracle harness
- `data/karr_fixtures/karr_native_m1.{json,npz}` — committed M1 fixture (~123 KB)
- `tests/m1/test_karr_metabolism.py` — 7 tests
- `tests/vivarium/test_karr_m1_chassis.py` — 4 tests
- `artifacts/M1_per_reaction_oracle.json`, `docs/phase5/M1_per_reaction_oracle.md`
- `plan.md`, mirrored to session-state
- DELETED iPS189 surface area (see history #8)

**Files created this session for M2 (NOT yet committed, mid-flight):**
- `scripts/karr_native_ingest_m2.py` — ran successfully, produced fixture
- `data/karr_fixtures/karr_native_m2.{json,npz}` — exists on disk
- `opencell/m2/transcription.py` — written but **module dir `opencell/m2/` does NOT exist on disk** (PowerShell New-Item parallel race); needs re-creation
- `opencell/m2/__init__.py` — same issue, dir missing
- `opencell/vivarium/karr_m2.py` — created OK
- `tests/m2/test_transcription.py` — written but **`tests/m2/` does NOT exist on disk**, needs re-creation
- `tests/vivarium/test_karr_m2_chassis.py` — created OK
- `tests/m2/__init__.py` — needs creation

**Commits made this session:**
- `1c47527` (or similar) — Karr-native M1 + per-reaction oracle
- `041caab` — M1 vivarium chassis
- (cleanup commit hash not captured in summary) — iPS189 deletion

**Test counts evolution:** 453 → 460 (+M1 oracle) → 464 (+chassis) → 452 (-iPS189 cleanup, removed 12)

**Currently working on:** M2 transcription. Process and tests **written** but the M2 module/test directories were never actually created on disk (the New-Item ran but the create-file calls all reported "Parent directory does not exist" except for `karr_m2.py` and `test_karr_m2_chassis.py` which went under existing dirs). The fixture extractor ran successfully.

**Last test run result (failed at collection):**
```
ImportError: cannot import name 'transcription' from 'opencell.m2' (unknown location)
```
Because `opencell/m2/` doesn't exist on disk.

</work_done>

<technical_details>

**The M1 structural finding (from prior session, still core):** Karr's snapshot `fbaEnzymeBounds` are **post-step** (free-enzyme count after substrate binding), proven because 34/504 of Karr's *own* stored `fluxs` violate them by up to 100×. Therefore static FBA on the snapshot is structurally bounded at ~51% of Karr's stored growth. We accept this and validate per-reaction instead.

**Karr's MAT data layout:**
- `m["data"].metabolism` — has all 504-FBA matrices and index maps
- `m["data"].states.State_MetabolicReaction.dump.fluxs` (645,) — Karr's runtime gold-standard solution, 253 nonzero
- `m["data"].states.State_MetabolicReaction.dump.{growth, growth0, meanInitialGrowthRate, doublingTime}` — runtime scalars
- `m["data"].processes.Process_Transcription.{parameters, fittedConstants}` — has elongation rate + 335 TU binding probabilities
- `kb["data"].knowledgeBase.genes` (525) — mat_struct array; iterated in Python (slow but works); each gene has `wholeCellModelID, symbol, type, halfLife, length (start/end), expression(3), synthesisRate(3), essential, ...`
- `kb["data"].knowledgeBase.transcriptionUnits` (335) — promoter info, gene refs

**Critical unit conventions in Karr's KB:**
- `halfLife` is in **MINUTES**
- `synthesisRate` is in **transcripts/MINUTE**
- Decay = ln(2)/halfLife is per-minute
- At steady state: `expression[i, j] = synthesisRate[i, j] / decay_rate[i]` exactly (Karr fits synthesisRate to make this hold)
- → **per-gene "predict expression from synthesisRate" is tautological**; need polymerase-mechanics derivation for an honest oracle (M2 v2)

**Index mapping FBA-504 vs full-645:**
- `met.reactionIndexs_fba` (336,) maps FBA conversion col index → 645-rxn space
- `met.fbaReactionIndexs_metabolicConversion` (336,) maps to first 336 of 504 FBA cols
- Per-FBA-column WCM ID: `fba_col_rxn_wcm_id[fba_idx_metab_conv[i]] = rxn_wcm_ids_645[rxn_idx_fba[i]]`
- 168 FBA cols (336-503) are exchange pseudo-reactions, no WCM ID

**The biomass column** is FBA col 502 (`obj=+1000`), with 35 small parsimony penalties of -5.31e-9 on internal-limited-exchange cols.

**`scipy.io.loadmat` quirk:** Use `struct_as_record=False, squeeze_me=True`. Iterating mat_struct objects: use `_fieldnames` to enumerate. mat_struct arrays of structs (e.g. `genes[0]`) accessed by index.

**MATLAB invocation pattern:** `& "E:\MATLAB\bin\matlab.exe" -batch "addpath('E:/opencell/scripts/matlab'); extract_karr_targeted('E:/opencell/data/m1_sources/WholeCell', 'E:/opencell/data/m1_sources/karr_flat')"`. Don't use relative paths or cd.

**`import import` typo fix** still required at `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/FtsZPolymerization.m` line 134. WholeCell/ is gitignored.

**PowerShell parallel-tool ordering quirk:** `New-Item -ItemType Directory` and subsequent `create` calls in the same response can race. The directory creation succeeded but the create calls saw the parent missing. **Solution: do New-Item in its own response, verify, then issue creates.**

**Vivarium emit timing:** First emit is t=0 initial-state defaults, not the first tick's predicted output. Tighten "stable across ticks" assertions to `arr[1:]`.

**Vivarium ports schema:** `_updater='set'` for replace-state ODE values, `_updater='accumulate'` for stochastic count deltas. Process keys must NOT collide with store paths.

**.venv-wsl invocation:** Always run Python via `wsl bash -lc 'source /mnt/e/opencell/.venv-wsl/bin/activate && python ...'`. PowerShell heredocs into WSL break — write Python to a script file.

**Full test suite runtime:** ~10-11 minutes (645s).

**M2 v1/v2 staging:**
- v1 (in flight): Karr-prescribed-rates module. dRNA/dt = s − k·RNA, both s and k from KB. Round-trips to expression by construction. Validates extraction + integrator only.
- v2 (deferred): derive s_i from RNA polymerase counts × `transcriptionUnitBindingProbabilities` × elongation rate × promoter mechanics. Compare against Karr's fitted s_i as independent oracle.

**Substrate writeback gap:** Both M1 and M2 vivarium wrappers don't yet write back substrate-count deltas in Karr's 1686-element metabolite×compartment count vector. M2 writes ATP/CTP/GTP/UTP placeholder substrates only. Real cross-process state mapping requires `fba_sub_idx_substrates` → 585 → 1686 chain; deferred to integrator/M3 territory.

**SQL todos table FK constraint:** Cannot rename a todo's id directly (`UPDATE todos SET id='new' WHERE id='old'`) — fails on FK. Workaround: mark old as blocked/done, INSERT new, redirect deps.

</technical_details>

<important_files>

- `opencell/m1/karr_metabolism.py`
   - Core M1 module (Karr-native FBA solver). Loaded from JSON+NPZ fixture.
   - Key API: `load_default()`, `solve_fba(model, use_full_objective=True, sense='max', big=1e3)`, `per_reaction_comparison(model, v)`, `KarrMetabolismModel.fba_col_for_wcm_id(wcm_id)`.
   - Snapshot fbaEnzymeBounds intentionally dropped; documented in module docstring.

- `opencell/m1/__init__.py`
   - Re-exports Karr-native API only (iPS189 gone).

- `opencell/vivarium/karr_m1.py`
   - `KarrMetabolismProcess` (1s tick) + `build_karr_m1_engine`. Reads `substrates`, writes `metabolic_reaction.{fluxs (645-dict), growth_per_s, growth_per_h}`. Substrate writeback is placeholder.

- `opencell/m2/transcription.py` ⚠️ **WRITTEN BUT DIR DOESN'T EXIST ON DISK**
   - `KarrTranscriptionModel` dataclass (525 genes + 335 TUs).
   - `step_analytical(model, rna_counts, dt_s, condition=1)` — closed-form integration of dRNA/dt = s − k·RNA. Handles k=0 branch (linear accumulation).
   - `ntp_consumption_per_s(model, condition=1)` — total nt/s × length, split 1/4 per NTP (uniform composition; real composition is M2 v2).

- `opencell/m2/__init__.py` ⚠️ **WRITTEN BUT DIR DOESN'T EXIST**

- `opencell/vivarium/karr_m2.py` ✅ **EXISTS ON DISK**
   - `KarrTranscriptionProcess` writes `rna.counts` (525-dict) + `substrates.{ATP,CTP,GTP,UTP}` deltas (accumulate).
   - `build_karr_m2_engine` standalone harness.

- `opencell/vivarium/__init__.py`
   - Updated to export both `karr_m1` and `karr_m2` symbols.

- `scripts/karr_native_ingest_m1.py`
   - One-shot extractor producing `data/karr_fixtures/karr_native_m1.{json,npz}`. Run after MATLAB re-extraction.

- `scripts/karr_native_ingest_m2.py`
   - Iterates 525 genes + 335 TUs. Carries both per-min and per-s rates. Validated against dnaN sample (RNA_ss = 2.05 = expression[1]).

- `scripts/m1_per_reaction_oracle.py`
   - Karr-vs-Karr oracle. Acceptance: median |log2 ratio| < 1. Result: 0.96 PASSED.

- `tests/m1/test_karr_metabolism.py` (7 tests)
- `tests/vivarium/test_karr_m1_chassis.py` (4 tests)
- `tests/m2/test_transcription.py` ⚠️ **WRITTEN BUT DIR DOESN'T EXIST**
- `tests/vivarium/test_karr_m2_chassis.py` ✅ **EXISTS** (currently failing collection due to m2 dir missing)

- `data/karr_fixtures/karr_native_m1.{json,npz}` — 123 KB, committed
- `data/karr_fixtures/karr_native_m2.{json,npz}` — 55 KB, NOT yet committed

- `plan.md` and session-state mirror — updated through end of M1 chassis. M2 entry NOT yet added.

</important_files>

<next_steps>

**Immediate (resume point):**

1. **Recreate the missing M2 directories on disk** (parallel-tool race ate them):
   ```powershell
   New-Item -ItemType Directory -Path E:\opencell\opencell\m2 -Force
   New-Item -ItemType Directory -Path E:\opencell\tests\m2 -Force
   ```
   Verify with `Test-Path` before re-creating files.

2. **Re-create the four files that failed:**
   - `E:\opencell\opencell\m2\transcription.py` (full content in summary above; ~150 lines; KarrTranscriptionModel dataclass + load_default + step_analytical + ntp_consumption_per_s)
   - `E:\opencell\opencell\m2\__init__.py` (re-exports)
   - `E:\opencell\tests\m2\__init__.py` (empty)
   - `E:\opencell\tests\m2\test_transcription.py` (6 tests: fixture_counts, arrays_finite_and_nonneg, steady_state_round_trip, step_analytical_reaches_steady_state, step_analytical_preserves_steady_state, ntp_consumption_per_s_positive)

3. **Run M2 tests:**
   ```
   wsl bash -lc 'source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell && pytest tests/m2 tests/vivarium/test_karr_m2_chassis.py -v --tb=short'
   ```
   Expect 9 tests to pass.

4. **Run full suite** (~11 min): expect 461 passing (452 + 6 m2 + 3 m2 chassis).

5. **Update SQL todo `m2-transcription`:** mark `done` with finding summary.

6. **Update `plan.md` + session-state mirror** with M2 v1 entry and v2 deferred work.

7. **Commit M2 v1** with message describing the v1/v2 staging.

**After M2 v1 ships:**
- Compose M1 + M2 in a single Engine; verify both tick together (chassis composition test).
- Decide next: M2 v2 (polymerase mechanics) vs M3 translation vs the deferred substrate-state mapping work that real cross-process flux balance needs.

**Open questions / blockers:**
- `m1-extract-per-process-fixtures` still pending (would ship MAT fixtures for M3-M7 oracles in advance).
- The 1686-element metabolite×compartment count vector mapping is needed before M1 + M2 can do real shared-substrate flux. Not blocking M2 v1.
- `import import` typo fix in WholeCell MATLAB still not upstreamed.

</next_steps>