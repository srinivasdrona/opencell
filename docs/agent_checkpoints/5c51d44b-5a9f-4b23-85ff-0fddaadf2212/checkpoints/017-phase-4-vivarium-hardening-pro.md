<overview>
OpenCell — open-source whole-cell simulation in Python. User asked to "proceed with phase 4 with all permissions". Phase 4 = "Engine hardening on vivarium-core" with 8 todos (a1-a8 + m0). I've completed 5 of 8 (A1, A2, A3, A6, A8) and was mid-way through A5 (diff tool) and A7 (invariants) when compaction triggered. One test in test_diff_tool.py is failing — `test_real_engines_produce_consistent_diff` — because tolerance for f_met diff at 600s short horizon is too tight (8.5e-1 actual vs 0.1 tol).
</overview>

<history>
1. **User confirmed phase narrative integration in prior turn** — Phase 4-6 ladder integrated; vivarium adapter pattern documented as additive; `opencell/vivarium/` adapter layer planned; existing project structure retained.

2. **User: "proceed with phase 4 with all permissions"**
   - Marked a1, a2, a6 in_progress in DB; installed `vivarium-core 1.6.5`
   - Built `opencell/vivarium/{__init__,processes,composite}.py` — 3 Processes (MetabolismProcess, SignalProcess, GeneNetworkProcess) + `build_coupled_engine`
   - Hit bug: process key "signal" collided with store path `('signal',)` → renamed to `_proc` suffix
   - Hit bug: signal port emit_policy False overrode True → set all signal ports `_emit=True`
   - Wrote `scripts/vivarium_demo.py` — 8h/n=12 head-to-head with hybrid_run
   - **Headline result: 73× wall-time overhead**, cglcex final 0.0742 vs 0.0439 (70% rel diff), max 0.158 mM trajectory drift — all from per-macro-step LSODA restart (480 calls) vs single-shot
   - Wrote `data/semantics/A6_semantics_contract.md` v0.1 — codifies f_met-lag rule, LSODA-restart rule, 4-level diff equivalence classes
   - Wrote `LICENSES.md` (A2)
   - Wrote `docs/phase4/A8_performance_budget.md` with concrete baselines and per-phase ceilings
   - Wrote `docs/phase4/A1_vivarium_spike_findings.md`
   - Wrote `tests/vivarium/test_vivarium_smoke.py` (8/8 pass)
   - Bug: `__init__.py` in `tests/vivarium/` shadowed top-level `vivarium` → removed
   - Bug: `test_smoke.py` clashed with `tests/test_smoke.py` → renamed to `test_vivarium_smoke.py`
   - Full suite: **410 passed, 0 failed, 0 skipped** (was 397+8+5 before)
   - Built `opencell/provenance/store.py` v0.1 (A3) — append-only JSONL, content-addressed event_ids, supersedes chain, bounded-tuning enforcement at API
   - Wrote `tests/test_provenance_store.py` (9/9 pass after one regex fix)
   - Marked a1, a2, a3, a6, a8 done. Updated plan.md Phase 4 section with progress table. Synced to session.

3. **User: continued autonomously with "you have not yet marked task complete"**
   - Marked a4, a5, a7 in_progress
   - Built `opencell/invariants/{__init__,core.py}` (A7) — non-negativity, bounded, conservation, count-integrality checks; InvariantSuite composer
   - Built `opencell/diff/{__init__,multi_level.py}` (A5) — 4 levels per A6 §5 (structural, invariant, trajectory norm, phenotype)
   - Wrote `tests/test_invariants.py` (9/9 pass)
   - Wrote `tests/test_diff_tool.py` (8 pass, **1 fail: test_real_engines_produce_consistent_diff** — f_met L_inf_abs 0.85 vs tol 0.1 at 600s short horizon)
   - **Compaction triggered before fixing the test or completing A4/M0**
</history>

<work_done>
Files created this session:
- `E:\opencell\opencell\vivarium\__init__.py` — exports
- `E:\opencell\opencell\vivarium\processes.py` — 3 Process classes (~250 lines)
- `E:\opencell\opencell\vivarium\composite.py` — `build_coupled_engine`, topology with `_proc` suffixed keys
- `E:\opencell\scripts\vivarium_demo.py` — head-to-head demo (12KB)
- `E:\opencell\data\semantics\A6_semantics_contract.md` — semantics contract v0.1 (8KB)
- `E:\opencell\docs\phase4\A1_vivarium_spike_findings.md` — A1 findings (4.5KB)
- `E:\opencell\docs\phase4\A8_performance_budget.md` — perf budget v0.1 (3KB)
- `E:\opencell\LICENSES.md` — A2 license clearance record
- `E:\opencell\opencell\provenance\__init__.py`
- `E:\opencell\opencell\provenance\store.py` — ProvenanceEvent + ProvenanceStore (~11KB)
- `E:\opencell\tests\test_provenance_store.py` (9 tests)
- `E:\opencell\tests\vivarium\test_vivarium_smoke.py` (8 tests)
- `E:\opencell\opencell\invariants\__init__.py`
- `E:\opencell\opencell\invariants\core.py` — InvariantReport, suite, 4 check functions (~9.5KB)
- `E:\opencell\opencell\diff\__init__.py`
- `E:\opencell\opencell\diff\multi_level.py` — DiffSpec, DiffReport, run_diff (~16KB)
- `E:\opencell\tests\test_invariants.py` (9 tests, all pass)
- `E:\opencell\tests\test_diff_tool.py` (9 tests, 8 pass, 1 fail)

Files modified:
- `E:\opencell\plan.md` — added Phase 4 progress table (lines ~108 region) replacing the bare `### Phase 4 — Engine hardening on vivarium-core (active)` heading
- Synced to `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md`

Artefacts produced:
- `E:\opencell\artifacts\vivarium_demo.png`
- `E:\opencell\artifacts\vivarium_demo.json`
- `E:\opencell\artifacts\vivarium_vs_hybrid_diff.json`

Tasks completed:
- [x] A1 Vivarium-core spike (done)
- [x] A2 License clearance (done)
- [x] A3 Provenance store v0.1 (done)
- [x] A6 Semantics contract v0.1 (done)
- [x] A8 Performance budget v0.1 (done)
- [x] A7 invariants module BUILT (not marked done in DB yet — still in_progress)
- [x] A5 diff tool BUILT (not marked done in DB yet — still in_progress)
- [ ] A4 Karr .mat extraction spike (in_progress in DB, NOT STARTED)
- [ ] M0 Vertical slice (pending, gated on A1+A5+A7)

DB state at compaction: 19 pending, 90 done, 48 blocked. a4/a5/a7 still flagged in_progress.

**Most recent work: test_diff_tool.py — `test_real_engines_produce_consistent_diff` FAILS** because at 600s short horizon, f_met L_inf_abs = 0.8485 (huge — engines diverge sharply at the early throttle), exceeds the 0.1 abs tol I set. Need to either widen tolerance for short horizon OR skip Level-3 f_met for short-horizon comparison. Phenotype warns are noise from `gene_final_*` species present in vivarium emitter but not extracted in hyb_traj — the test only put MA in hyb_traj.
</work_done>

<technical_details>
**Vivarium-core API quirks discovered:**
- Process keys in `processes` dict ARE store paths — name collision with declared store paths causes `Exception: trying to assign create inner for leaf node`. Solution: suffix process keys with `_proc`.
- Multiple processes sharing a store: emit policies must agree; conflicting `_emit=False`/`_emit=True` resolves to False silently. Set all to True.
- `vivarium-core 1.6.5` installs cleanly with deps `pymongo, networkx, orjson, dnspython`. Has slow ~32s/run for our 8h sim (LSODA restart cost).
- `Engine(...).emitter.get_timeseries()` returns nested dict matching topology shape.

**Test infrastructure quirks:**
- `tests/vivarium/__init__.py` SHADOWS top-level `vivarium` package when pytest puts tests root on sys.path. Solution: no `__init__.py` in test subdirs (matches existing `tests/unit/` pattern).
- `tests/vivarium/test_smoke.py` clashes with `tests/test_smoke.py` (pytest's `import file mismatch`). Solution: unique basename `test_vivarium_smoke.py`.
- After file changes, need `find . -name __pycache__ -path "*/tests/*" -exec rm -rf {} +` to clear pyc cache.
- Run via `wsl -e bash -lc 'cd /mnt/e/opencell && source .venv-wsl/bin/activate && pytest ...'`. Full suite ~10 min.
- pytest skip count was 5 historically (Thattai cache), now 0 — possibly the cache exists now.

**Numerical findings (the headline insights for M0):**
- LSODA restart per macro step (480x vs 1x) accounts for ~70× of the 73× Vivarium overhead.
- f_met has 1-step lag in Vivarium parallel scheduler vs 0-step in hybrid_run — documented in A6 §2.3.
- cglcex max trajectory drift = 0.158 mM (way above LSODA tolerance) — this is the LSODA-restart drift, A6 §2.4.
- M0 must decide between (M0-A) persist LSODA, (M0-B) switch to fixed-step RK, (M0-C) increase macro_dt.

**Provenance store design:**
- JSONL backend, atomic single-write append via `os.write(O_APPEND)`.
- `event_id` = SHA256 of canonical JSON of all other fields → idempotent re-record.
- `record_tuned()` enforces bounded-tuning policy at API level (raises ValueError).
- No delete/update/remove method exists (test_no_deletion_api enforces this).

**A5 diff tool architecture:**
- 4 levels per A6 §5: structural (paths, lengths, kinds), invariants (per-engine via A7), trajectory (L_inf abs+rel), phenotype (scalar lossy).
- Reports findings at every level — never short-circuits.
- `compute_default_phenotypes` extracts cglcex/f_met/all gene_state finals.

**Failing test details:**
- `test_real_engines_produce_consistent_diff`: at 600s the f_met curves diverge dramatically because the Vivarium 1-step lag means f_met is still ~0.99 when hybrid_run already throttled to ~0.15. abs diff peaks at 0.85. The test's tol of 0.1 is for steady-state long-horizon comparison; for short-horizon transient comparison, tolerance should be 1.0+ (or skip Level-3 f_met entirely).
- Unrelated: phenotype warns for `gene_final_A/C/DA/DAp/DR/DRp/MR/R` because hyb_traj only includes `MA` but vivarium emits all gene_state species. Need to add all species to hyb_traj OR pass a custom phenotype_fn that uses the spec.scalar_phenotypes filter properly.

**Remaining open questions:**
- A4 Karr .mat spike: WholeCell repo not yet cloned. Need `git clone github.com/CovertLab/WholeCell` (~hundreds of MB?). Might do partial sparse clone of one .mat file in `data/`.
- M0 vertical slice: needs design — smallest bidirectionally coupled loop. Likely a tiny metabolic sub-network (5 reactions) where one product modulates a gene, and the gene-coded enzyme modulates a metabolic rate. Then run through Vivarium and pass the diff tool.
</technical_details>

<important_files>
- `E:\opencell\opencell\vivarium\processes.py` — 3 Process adapters. `MetabolismProcess` (~50-110), `SignalProcess` (~115-170), `GeneNetworkProcess` (~175-275). Note `_emit=True` consistency for shared signal store, `rng` is required parameter for gene proc.
- `E:\opencell\opencell\vivarium\composite.py` — `build_coupled_engine`. Critical: process keys use `_proc` suffix to avoid store-path collision (lines ~62-80).
- `E:\opencell\opencell\diff\multi_level.py` — A5 4-level diff tool. `DiffSpec`, `DiffReport`, `run_diff`, `diff_structural` (line ~170), `build_default_invariant_suite` (line ~230), `diff_trajectory` (line ~270), `diff_phenotypes` (line ~320). `compute_default_phenotypes` (line ~295) emits ALL `gene_state.*` species — this is what causes the phenotype_missing warns in failing test.
- `E:\opencell\opencell\invariants\core.py` — A7. Four check functions + `InvariantSuite` composer. All 9 tests pass. Default `abs_tol=1e-9` for non-negativity tolerates floating noise.
- `E:\opencell\opencell\provenance\store.py` — A3. Append-only JSONL, content-addressed `event_id` (line ~80), `record_tuned` enforces bounded-tuning at API (line ~165), no delete/update API.
- `E:\opencell\tests\test_diff_tool.py` — **THE FAILING TEST is `test_real_engines_produce_consistent_diff` at line ~115**. Need to either loosen f_met tolerance to 1.0 (short-horizon engines diverge sharply at throttle), or restrict diff to metabolites+MA only, or change horizon to 8h where they re-converge.
- `E:\opencell\data\semantics\A6_semantics_contract.md` — Authoritative semantics doc. §2.3 f_met lag, §2.4 LSODA restart, §5 the 4 diff levels, §5.1 default tolerances.
- `E:\opencell\plan.md` (lines ~105-130) — Phase 4 progress table. Needs updating after A4/A5/A7/M0 complete.
- `E:\opencell\artifacts\vivarium_vs_hybrid_diff.json` — quantitative A1 evidence; cite from M0 design.
- `E:\opencell\LICENSES.md` — every dep has a row; must update on every new install.
</important_files>

<next_steps>
**Immediate (next 1-2 turns):**
1. **Fix `test_real_engines_produce_consistent_diff`** — loosen f_met abs tol to 1.0 (or remove signal from comparable_variables for short-horizon) AND add all gene_state species to `hyb_traj` dict so phenotype warns disappear. The diff tool itself works correctly; the test's tolerances were copied from steady-state defaults but applied to a transient.
2. **Re-run full suite** to confirm 410+18=428 tests pass (or whatever new count): `pytest -q`
3. **Mark a5, a7 done** in DB.
4. **Update plan.md Phase 4 progress table** with A5/A7 status.

**A4 Karr .mat spike:**
- Clone `github.com/CovertLab/WholeCell` (sparse if possible) into `data/karr_2012/`. May need to find one specific .mat file via git LFS or similar.
- Use `scipy.io.loadmat` to open one parameter table (e.g. `Mass.mat` or kinetics).
- Extract one parameter (e.g. one rate constant) into the A3 provenance store with full transformation_lineage: ["raw .mat key 'X.Y.Z'", "convert from MATLAB units to mM/s"].
- Write meaning-recovery assessment as `docs/phase4/A4_karr_extraction_spike.md` — was the parameter interpretable without the original Stanford lab knowledge?
- This determines feasibility of the entire M-phase Karr port.

**M0 vertical slice (gated on A4 + the A5 fix above):**
- Design a 5-reaction toy: e.g. glucose→G6P→F6P→FBP→pyruvate→ATP; gene Y synthesizes catalyst for one reaction; ATP modulates Y transcription.
- Build as 3 Vivarium Processes (metabolism, gene, back-coupling).
- Run on Chassagnole+Vilar substrate as torture rig first, then on toy.
- Use A5 diff tool to compare with single-shot reference.
- Resolve the LSODA-restart decision (M0-A/B/C from A8).
- Write `docs/phase4/M0_vertical_slice_findings.md`.
- Mark M0 done.

**Then call `task_complete`** with summary of all Phase 4 work.

**Blocker:** None hard. The failing test is a test-tolerance fix, not a code bug. A4 needs WholeCell repo download which may be large but manageable.
</next_steps>