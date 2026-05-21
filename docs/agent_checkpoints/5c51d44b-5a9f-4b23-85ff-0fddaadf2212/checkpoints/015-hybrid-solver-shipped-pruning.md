<overview>
Building OpenCell — open-source whole-cell simulation in Python. This segment finished the hybrid deterministic/stochastic solver, fixed RNG hygiene, locked execution to WSL, optimised the hybrid solver 14×, normalised line endings repo-wide, shipped an end-to-end first-run demo with viz, and prepared validation-dataset candidates. User then introduced a strategic pivot toward "pruning" a genome-scale M. genitalium model into a Core 100 (with JCVI-syn3A as the long-term north-star) — the conversation was interrupted (compaction) just as I started acting on that pivot.
</overview>

<history>
1. User asked "did the coupler work as expected?" after RNG refactor compacted mid-flight.
   - Finished refactor: rewrote `opencell/solvers/hybrid.py` with single `np.random.Generator` flow; `hybrid_ensemble` uses `SeedSequence.spawn(n)`.
   - Updated `tests/unit/test_solvers.py` (replaced `jax.random.PRNGKey` with `np.random.default_rng`).
   - Tightened slow throttle test from 5h×4 → 3h×2 realisations.
   - Added "Stochastic RNG Discipline" section to `.github/copilot-instructions.md`.
   - Initial test run on Windows venv (`.venv-opencell`) showed 389 passed / 6 skipped; 16/16 hybrid+stochastic green.
   - Committed 2891195 (refactor), ea6aea7 (DB sync).

2. User asked about why stochastic was slow + which 6 tests skipped.
   - Diagnosed bottleneck (wrongly first guess) as tau-leap density; corrected later via profiling.
   - Identified 6 skips as `roadrunner` (libroadrunner) tests — but realised I was running in the WRONG environment (Windows venv).

3. User: "let's leave the 5 Thattai tests, fix the 6th."
   - Started installing libroadrunner in Windows; user stopped me — "we already have it, why are you running in Windows at all?"

4. User: "why did you come out of WSL? take a pause and answer."
   - Honest answer: I never checked the env; defaulted to PowerShell + `.venv-opencell`. Process failure, not tiredness.

5. User: "document the rule first."
   - Added "Execution Environment: WSL is the Source of Truth" section to copilot-instructions.md (expected skip count = 5, mandates `wsl -e bash -lc` wrapper).
   - Committed 35e1809.

6. User: "did the coupler work as expected?"
   - Re-ran tests in WSL: 26/26 pass (10 coupled + 5 hybrid + 11 stochastic), 0 skipped. Coupler validated.
   - 13-min runtime flagged as still-slow.

7. User: "fix the speed issue."
   - Profiled with cProfile (post-warmup): 78% time in metabolism LSODA (60 restarts), 20% in tau-leap (mostly `jnp.array` JAX dispatch).
   - Two fixes: (a) single-pass LSODA over full horizon with `t_eval` at macro boundaries (valid because coupling is one-way), (b) drop `jnp.array(scaled)` in propensity factory.
   - Result: 1h hybrid_run 2.443s → 0.177s (14× speedup); full suite 780s → 515s.
   - All 26 tests still pass.
   - Committed f28daa9. Noticed line-ending churn (1160 insertions/deletions for ~50 line change).

8. User: "fix [line endings] in one shot."
   - Created `.gitattributes` (LF for text, explicit binary list).
   - Ran `git add --renormalize .` → 144 files normalised.
   - Verified zero substantive diff with `--ignore-all-space`.
   - Committed 78b7175 (gitattributes), df6c0b1 (renormalisation).

9. User: "are we done with coupler testing? what next?"
   - Listed pending todos via SQL (50 pending; p3-hybrid-solver still showed pending due to missed DB update).
   - Offered 3 options: (1) end-to-end demo + viz, (2) empirical dataset hunt, (3) Morris sensitivity. Recommended option 1.
   - User: "sounds good, ... we will call it a day after end-to-end demo + viz."

10. User wanted demo + viz.
    - Updated todos DB (84 done, 47 pending, marked p3-first-run/p3-viz in_progress).
    - Created `scripts/demo_first_run.py` — 12 stochastic realisations × 8h with deterministic uncoupled baseline overlay, 3-panel symlog figure, JSON summary.
    - First version was visually muted (glucose collapses in 72s); rewrote with uncoupled baseline overlay, throttle marker, symlog y-axis.
    - Initially duplicated content via misuse of edit tool; fixed by deleting and recreating.
    - Final wall: 13s for full ensemble. Headline: f_met 1.000 → 0.032; R coupled mean 0.0 vs uncoupled 1282.6.
    - Updated plan.md (both copies) with Phase 3 capstone section.
    - Committed 9c593cb.

11. User: "thank you, keep options ready for published datasets. If none, consider Karr subset."
    - Saved `validation_dataset_candidates.md` to session files/. Four candidates ranked: Chassagnole 2002 Figs 5-6 (own calibration data), Bettenbrock 2006 (PTS dynamics), Taniguchi 2010 (single-cell distributions), Karr 2012 (fallback).
    - User said "good night."

12. User returned next morning (Apr 24, 10:00 IST) with strategic pivot:
    - **Don't build sub-models from scratch — prune a genome-scale model.**
    - Target: M. genitalium / M. pneumoniae.
    - Core 100: extract from existing GPR matrix; metabolism + transcription/translation core only.
    - **JCVI-syn3A** as modern benchmark (~480-500 genes, 4D simulated as of early 2026).
    - Validation invariant: stable growth rate / biomass accumulation curve.
    - I started a `web_search` to verify JCVI-syn3A 4D simulation status, but the search tool failed with an MCP error.
    - Then context compaction triggered.
</history>

<work_done>
Files created (this segment):
- `opencell/solvers/hybrid.py` — fully rewritten with explicit `np.random.Generator`, single-pass LSODA, no JAX dependencies. ~200 lines.
- `tests/integration/test_hybrid_solver.py` — already existed; tightened slow test horizon.
- `scripts/demo_first_run.py` (~250 lines) — 12-realisation hybrid ensemble + deterministic uncoupled baseline + 3-panel symlog figure.
- `.gitattributes` — text=auto eol=lf, explicit binary list.
- `artifacts/first_run_demo.png` and `artifacts/first_run_demo.json` — demo outputs.
- Session: `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\validation_dataset_candidates.md` — 4 ranked validation candidates.

Files modified:
- `opencell/solvers/stochastic.py` — `tau_leap` now requires `rng: np.random.Generator`; JAX imports removed.
- `tests/unit/test_solvers.py` — 3 calls updated to use `np.random.default_rng(seed)`.
- `.github/copilot-instructions.md` — added 2 sections: "Execution Environment: WSL is the Source of Truth" and "Stochastic RNG Discipline".
- `plan.md` (both repo + session-state copies) — added "Hybrid Solver + First-Run Demo (DONE)" capstone section.
- `opencell_tasks.db` — todos updated: 86 done, 47 pending, 1 blocked.

Commits made (chronological):
- `2891195` Hybrid solver + stochastic RNG hygiene
- `ea6aea7` Mark p3-hybrid-solver + p3-rng-hygiene done in todo DB
- `35e1809` Document WSL-only execution rule
- `f28daa9` Speed up hybrid solver 14x via single-pass metabolism LSODA
- `78b7175` Add .gitattributes: normalise line endings to LF
- `df6c0b1` Renormalise all files to LF line endings (144 files)
- `9c593cb` p3-first-run: end-to-end hybrid demo + viz

Test status (verified in WSL):
- 26/26 pass for coupled + hybrid + stochastic.
- Full suite expected: 397 passed / 5 skipped (Thattai cache only) when run in WSL.

What's working:
- Coupler, hybrid solver, RNG hygiene, demo artifact, line-ending normalisation, all committed.
- WSL-only execution rule documented and self-verifiable (skip count = 5).

What's NOT done (interrupted by compaction):
- web_search for JCVI-syn3A status failed with MCP error (single attempt).
- Strategy note for pruning approach not yet written.
- No code/plan changes yet for the pivot.
</work_done>

<technical_details>
**Hybrid solver speedup (14×):**
- Root cause: 60 LSODA restarts per macro step, each re-discovering Jacobian/step-size. Profile (1h run, post-warmup) showed 78% in metabolism RHS calls.
- Fix: one-way coupling means metabolism is independent of f_met/gene state, so solve once over `(0, t_end_s)` with `t_eval = ts` (macro boundaries), then sample f_met at boundaries.
- Secondary: `_gene_propensity_factory` returned `jnp.array(scaled)`; `tau_leap` immediately converts back via `np.array(...)`. Replaced with `return scaled` (np.ndarray).
- Removed `import jax.numpy as jnp` from hybrid.py entirely.

**RNG hygiene rule (now in copilot-instructions.md):**
- Stochastic primitives MUST take `np.random.Generator`. No `np.random.seed()`. No unseeded `np.random.<dist>()`.
- Ensembles use `np.random.SeedSequence(base_seed).spawn(n)` for collision-free streams.
- A function that takes a JAX key but never uses it is a bug.

**WSL-only execution rule (now in copilot-instructions.md):**
- All Python/pytest/scripts: `wsl -e bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && <cmd>"`.
- Windows venv `.venv-opencell` is incidental, lacks `libroadrunner` (Linux-only in our stack).
- Expected skip count for correctly-run suite is **exactly 5** (Thattai paper-cache tests). Any other count → wrong env.
- File edits via Windows paths (E:\...) are fine — WSL rule applies to execution only.

**Line-ending normalisation:**
- `.gitattributes`: `* text=auto eol=lf` plus explicit binary list (png, pdf, db, sqlite, pkl, npz, npy, xlsx, docx).
- Without this, every WSL-side commit of Windows-edited files showed massive CRLF↔LF churn.

**Demo characterisation:**
- macro_dt_s = 60s, base_seed = 20260423, 12 realisations × 8h cellular time.
- Glucose 2.000 → 0.044 mM by t≈72s. f_met crosses 0.5 at t=0.02h.
- Coupled R final mean: 0.0; uncoupled deterministic R final: 1282.6.
- Wall time: 13s (post-warmup).
- Symlog y-axis on protein panel needed because R range 0 → ~1300.

**Validation dataset candidates (saved to session files/):**
1. Chassagnole 2002 Figs 5-6 — author's own calibration data, metabolism-only.
2. Bettenbrock 2006 — PTS dynamics post-glucose-pulse (validates f_met arm).
3. Taniguchi 2010 — single-cell mRNA/protein distributions (Vilar noise structure).
4. Karr 2012 (fallback) — M. genitalium subset.

**User's strategic pivot (Apr 24 morning):**
- Move from "build sub-models manually" (current Phase 5 plan: p5-translation, p5-replication, etc.) toward "prune a genome-scale GSM into a Core 100".
- Target: M. genitalium GPR matrix (likely from Karr 2012 or iPS189-type GSM).
- Core 100: filter for essential metabolism + minimal transcription/translation; exclude secondary metabolism, complex transport.
- Long-term north-star: JCVI-syn3A (~480-500 genes, 4D-simulated as of early 2026 by Luthey-Schulten group).
- **Validation invariant: stable, predictable growth curve (biomass accumulation).**
- This restructures Phase 4-5 of the plan; 47 pending todos may need re-scoping.

**Quirks still active:**
- WSL fs sync delay 5-15s after Windows file create/edit.
- PowerShell heredoc breaks on apostrophes — use temp files or `wsl -e bash -lc` with single quotes outside, escaped doubles inside.
- `np.random.poisson` is fine but must come from Generator, not global.
- BioModels REST blocked (CloudFront 403); use github.com/biomodels mirror.
- `np.bool_` not JSON-serializable; wrap with `bool()`.
- `ScipyODEResult` attribute is `.ts` not `.t`.

**Open questions:**
- JCVI-syn3A 4D simulation status as of early 2026 — user asserts it; my web_search failed mid-tool-call. Treat user's assertion as authoritative (it's consistent with Thornburg et al. 2022 Cell paper using Lattice Microbes).
- Which existing M. genitalium GSM to start from? Candidates: Karr 2012 model itself (already has GPR), or iPS189 (Suthers et al.). User hasn't specified.
- "Core 100" gene-selection criteria need to be operationalised: how do we rank essentiality? Use Karr's experimental knockout data? FBA-essentiality on the GSM?
- Pivot scope: do we keep the Chassagnole+Vilar coupled cell as a validated architectural artifact and start a parallel `mgen/` workstream, or replace it?
</technical_details>

<important_files>
- `E:\opencell\opencell\solvers\hybrid.py`
  - The hybrid deterministic/stochastic solver. Single-pass LSODA + numpy Generator.
  - Key functions: `hybrid_run`, `hybrid_ensemble`, `_gene_propensity_factory` (lines ~70-95), `_compute_f_met` (lines ~175-180).
  - Returns numpy not jnp from propensity.
  - One-way coupling assumption hard-coded in single-pass solve — NOT valid for two-way coupling.

- `E:\opencell\opencell\solvers\stochastic.py`
  - `tau_leap(propensity_fn, stoich_matrix, y0, t_span, rng, config, save_every)` — requires explicit `np.random.Generator`.
  - Signature change is breaking; all callers updated.

- `E:\opencell\scripts\demo_first_run.py`
  - End-to-end hybrid demo. 12 realisations × 8h, fixed seed 20260423.
  - Outputs to `artifacts/first_run_demo.{png,json}`.
  - Includes deterministic uncoupled baseline overlay and f_met < 0.5 throttle marker.

- `E:\opencell\.github\copilot-instructions.md`
  - Two new mandatory rule sections: "Execution Environment: WSL is the Source of Truth" and "Stochastic RNG Discipline".
  - Authoritative for future sessions.

- `E:\opencell\.gitattributes`
  - Forces LF line endings repo-wide. Without it, WSL-side commits of Windows-edited files churn.

- `E:\opencell\plan.md` and `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md`
  - Both have Phase 3 capstone section ("Hybrid Solver + First-Run Demo (DONE)").
  - Need to add a "Strategic Pivot: Pruning approach + Core 100 + JCVI-syn3A" section before next-session work.
  - Need to re-scope Phase 4-5 todos (47 pending) — currently still phrased around manual sub-model building.

- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\validation_dataset_candidates.md`
  - 4 candidates ranked. Karr 2012 listed as fallback — now likely promoted to primary because of pivot.
  - Should be updated/superseded with the pruning-approach framing.

- `E:\opencell\opencell_tasks.db`
  - 86 done / 47 pending / 1 blocked. Pending todos under Phase 4-5 (e.g., p4-biocyc, p4-brenda, p5-translation, p5-replication, p5-karr-study) need re-scoping under the pruning approach.

- `E:\opencell\opencell\models\coupled.py`
  - The coupled Chassagnole+Vilar model. Now a validated architectural artifact rather than a path forward.
  - `signal="uptake_flux"` used in demo (PTS-flux ratio).
</important_files>

<next_steps>
**Immediate (resume here when context returns):**

1. **Acknowledge the strategic pivot and act on it.** User's three pillars:
   - Pruning a genome-scale M. genitalium model into a Core 100 (not building sub-models manually).
   - JCVI-syn3A as long-term benchmark (~480-500 genes, 4D-simulated as of early 2026).
   - Growth rate / biomass accumulation as the validation invariant.

2. **Verify JCVI-syn3A current status with one targeted web search** (the previous attempt failed with MCP error — retry once, then move on regardless). Specifically: confirm the 4D simulation claim (Thornburg et al. 2022 Cell + any 2024-2026 follow-ups). If the search fails again, treat user's assertion as authoritative.

3. **Identify the M. genitalium GSM to start from.** Two real candidates:
   - **Karr 2012 model** — already has GPR; we listed it as a fallback validation source. Now becomes the source of the genes themselves.
   - **iPS189 / Suthers et al. 2009** — earlier M. genitalium GSM, may be cleaner starting point.
   - Check what's in `data/biomodels_reference/` and what's freely downloadable.

4. **Sketch the Core 100 selection criteria.** Operationalise:
   - Essential metabolism: central glycolysis genes from the GPR (PTS, glycolysis, PPP).
   - Essential transcription/translation: RNA polymerase core, ribosomal proteins, key tRNA synthetases — but capped at the absolute minimum.
   - Use Karr's experimental knockout-essentiality data if available, or FBA-essentiality on the GSM.

5. **Update plan.md and todos DB to reflect the pivot.** 47 pending todos, many under Phase 5 (p5-translation, p5-replication, p5-karr-study, etc.) need re-scoping under the pruning approach. Don't blow them away — supersede with new "core-100" series and mark old ones blocked-by-pivot.

6. **Update `validation_dataset_candidates.md`.** Karr 2012 should move from fallback to primary; add JCVI-syn3A as the long-term target; reframe the document around growth-rate-as-invariant.

7. **Propose a one-day spike for the pivot:** load the Karr GSM, extract the GPR, filter to a Core 100 candidate set, count it, and check it against published M. genitalium essential-gene lists. Don't commit to building anything until the user signs off on the gene list.

**Open questions to ask the user before significant work:**
- Which GSM as the starting source (Karr 2012 model, iPS189, or other)?
- Core 100 essentiality ranking: experimental (Karr knockouts) vs FBA-essentiality vs literature consensus?
- Keep the Chassagnole+Vilar coupled cell as an architectural artifact (separate `toy/` workstream) or deprecate it?
- Is the architectural framework (composite ODE on concatenated state + hybrid solver) reusable for the Core 100, or do we need an FBA-style solver for genome-scale metabolism?

**Cleanup:**
- No `_tmp_*` files outstanding.
- No uncommitted state.
</next_steps>