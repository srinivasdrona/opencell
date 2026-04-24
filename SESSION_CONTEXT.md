# OpenCell — Session Context (for AI continuity)

> This file captures context that lives in conversation memory but not in plan.md.
> Read this at the start of every new session.
> **UPDATE this file at every checkpoint** (i.e. whenever a meaningful chunk of
> work concludes — not only at session boundaries). It is a living document.

## Update Policy
At every checkpoint (and definitely at session end / when the user wraps up), append:
1. What changed since the last entry (decisions, files modified, todos completed)
2. Any new user preferences or corrections discovered
3. Updated tool/access status (DB access, installs, API keys)
4. Current blockers and what's ready next
5. Anything learned that would be lost without writing it down

The session-state checkpoint folder (`C:\Users\sdrona\.copilot\session-state\<id>\checkpoints\`)
holds the runtime's auto-managed checkpoints; this file is the **human-curated**
counterpart and should track the same milestones at higher signal density.

## Session Log
### Session 1 — 2026-04-21
- **Duration**: ~2 hours of planning and review
- **What happened**: Initial brainstorming → plan creation → 4 rounds of cross-model critique (Opus 4.6, GPT-5.2, GPT-5.4, Opus 4.7) → incorporated all 66 findings → added resilience techniques → moved sensitivity analysis up → cloud-first AI strategy → persistent task DB → this context file
- **Key moment**: AI caught fabricating cost estimates and tok/s numbers. Led to credibility policy (mark VERIFIED vs UNVERIFIED)
- **Files created**: plan.md, opencell_tasks.db, SESSION_CONTEXT.md
- **No code written yet** — still in planning/review phase
- **Next**: User will stew on the plan, get DB access, read Karr 2012 paper, then decide start date

### Session 1 (continued) — 2026-04-21
- **What happened**: Discussed agent skills (bio-researcher, numerical-modeler, etc.), searched for existing frameworks (BioAgents, CrewAI, PySCeS, Tellurium). Decided: lightweight skill profiles as markdown files, no framework dependency. Then explored "what does utter failure look like?" — identified that "confidently wrong" is the most dangerous failure mode. Discovered that NONE of 4 critique rounds (66 findings) caught the need for analytical test cases. Added Phase 1→2 Gate (8 gate checks including hand-calculable micro-model, atom audit, unit trace, reference frame declarations, PySCeS/Tellurium cross-validation, thermodynamic feasibility). Added 6 agent skill profile definitions to AI strategy section.
- **Key insight**: Sophistication bias — all AI reviewers focused on advanced validation (Sobol, sensitivity analysis, multi-model panels) and missed the most basic check: "can you solve 1 gene on paper?" Caught by PM asking "are we missing rookie mistakes?"
- **Files updated**: plan.md (added ~100 lines: gate section + skills section), opencell_tasks.db (now 101 todos, 127 deps)
- **New decisions**: 
  - Skills are `.github/skills/{name}.md` files, not a framework
  - Phase 1→2 gate is BLOCKING — cannot start Phase 2 until all 8 checks pass
  - PySCeS/Tellurium added as reference oracles (not previously in plan)

### Session 2 — 2026-04-22
- **Duration**: ~3 hours of implementation
- **What happened**: Built ALL of Phase 1. Scaffolded project, installed deps, implemented core IR, solvers (JAX+SciPy+tau-leaping), engine, resilience (guards/sentinels/crash bundles/checkpoints), data layer (loader/SBML/schemas/contracts), orchestrator (router/panel/pipeline/cost tracker), observation model, validation harness, delta ledger replay, I/O manifests, naked numbers lint, skill profiles, benchmark charter, PR checklist template, tiered CI, data versioning. Switched dev environment from Windows to WSL (Ubuntu 22.04).
- **Key stats**: 114 tests passing, 7 git commits on `main`, ~4,500 lines of production code
- **Files created**: 40+ source files (see git log for full list)
- **Git commits**:
  1. `90ef686` — feat: scaffold project structure
  2. `b798adf` — feat: implement core IR, units, compartments, state, environment, resource ledger
  3. `c1be196` — feat: implement ODE solvers (JAX + SciPy), tau-leaping, sub-model base
  4. `1ad09f7` — feat: implement engine, guards, sentinels, crash bundle, manifest, checkpoint
  5. `08f67b0` — feat: implement data layer, orchestrator router/cost tracker, coupling benchmark
  6. `78945ef` — feat: complete Phase 1 — panel, pipeline, observation, validation, replay, manifests, skills
  7. `6c7e516` — chore: switch to WSL, update docs, add CI tiers and data versioning
  8. `0a4997b` — blog: Day 1 — 4,500 Lines Before Lunch
- **Environment switch**: Windows `.venv-opencell` → WSL `.venv-wsl` (Ubuntu 22.04, Python 3.12.13). All 114 tests pass on both. WSL is now primary.
- **Phase 1 status**: COMPLETE (all tasks done except p1-db-access which is blocked on user action)
- **Not yet pushed to GitHub** — user wants to keep it local for a couple more days
- **Blockers**: p1-db-access (BRENDA/BioCyc API keys) — needs user action
- **Next session**: Phase 1→2 Gate (8 analytical validation checks), then Phase 2 (toy cell sub-models)

### Sessions 3–N (backfill from runtime checkpoints 3–16, ~2026-04-22 → 2026-04-24)
Backfilled retroactively because earlier policy said "every session" not "every checkpoint" — gap closed here. Each bullet matches a runtime checkpoint by title.

- **CP 3 — Plan critique incorporation and resilience.** Round-2 cross-model critique findings (54 total, 23 newly caught) folded in. Resilience layer added: guards, sentinels, crash bundles, checkpoint-based recovery.
- **CP 4 — Phase 1 core implementation sprint.** All 40+ Phase 1 source files written: IR, units, compartments, state, environment, resource ledger, ODE solvers (JAX+SciPy), tau-leaping, sub-model base, engine, data layer, orchestrator, observation model, validation harness, delta ledger replay. 114 tests green.
- **CP 5 — Gate tests and external review.** Phase 1→2 gate (8 analytical validation checks) executed; first external review pass (5 strategic critiques — see "External Review Findings" section below).
- **CP 6 — Parameter verification system and PDF fetch.** Param-verification harness + PDF ingestion harness. First end-to-end pull of a kinetic constant from a paper PDF into the verification queue.
- **CP 7 — Phase 1 gates closed, Thattai APPROVED.** All 8 gate checks passed. Thattai-Oudenaarden 2001 toy gene network validated as the first analytic oracle. Phase 1 officially closed; Phase 2 entry granted.
- **CP 8 — Param-extractor skill and SBML manifest tool.** `param-extractor` agent skill profile shipped. SBML manifest tool generates checked-in manifests from source SBML (provenance pre-cursor).
- **CP 9 — SBML metadata auto-fill and GitHub mirror.** Metadata auto-fill walker for SBML annotations. Repo mirrored to GitHub (sdrona-ms account).
- **CP 10 — Correctness guardrails + pivot to direct SBML simulation.** Correctness guardrails layer (mass balance, sign checks, conservation). **Pivot:** drop hand-coded RHS for Chassagnole; use libroadrunner to simulate the original SBML directly. Reduces translation-error surface area to zero for vetted SBML models.
- **CP 11 — Metabolism sub-model with SBML simulation.** Chassagnole 2002 fully integrated via libroadrunner SBML path. Reproduces published steady-state cglcex / pyruvate / ATP within tolerance. First "publication oracle" passed end-to-end.
- **CP 12 — Vilar transcription model selected.** Vilar 2002 stochastic gene network selected as the second oracle. Engine extension for stochastic-on-deterministic coupling identified as next blocker.
- **CP 13 — Vilar transcription model and reproducibility audit.** Vilar implemented with tau-leap. Full reproducibility audit pass (RNG seeding, manifest determinism). Both Chassagnole and Vilar reproduce published phenotypes independently.
- **CP 14 — Hybrid solver and RNG hygiene.** First hybrid (deterministic ODE × stochastic tau-leap) solver landed. RNG hygiene rules formalised (seed routing, no global state).
- **CP 15 — Hybrid solver shipped, pruning pivot.** Hybrid solver shipped to main, demo run produces coupled Chassagnole+Vilar trajectory. **Pivot:** start pruning superseded scaffolding (the JAX-only path is no longer the primary).
- **CP 16 — Strategic pivot to vivarium-core chassis.** After 3 rounds of adversarial critique on the "build our own modular chassis" plan, pivoted to using **vivarium-core** as the chassis. Rationale: don't compete with an existing modular framework; integrate with it. Phase 4 redefined as "Engine hardening on vivarium-core" with the a1–a8 + m0 + m0.5 todo set. Old `p4-*`/`p5-*`/`p6-*` todos marked `blocked` (superseded).
- **CP 17 — Phase 4 vivarium hardening progress.** Mid-Phase-4 checkpoint capturing partial progress (a1, a2, a3, a6, a8 done; a4, a5, a7 in-flight; m0 pending). Detailed below in the next entry.

### Session N — 2026-04-24 (Phase 4 closed)
- **Duration**: ~5 hours of implementation
- **What happened**: Completed all of Phase 4 (Engine hardening on vivarium-core) end-to-end. A1 vivarium spike → A2 license clearance → A3 provenance store → A4 Karr `.mat` extraction spike → A5 multi-level diff tool → A6 semantics contract → A7 invariants module → A8 performance budget → M0 closed-loop vertical slice → M0.5 multi-Process scaling profiler. Each item produced code + tests + a findings doc.
- **Headline numerical findings**:
  - A1: vivarium-core wraps `hybrid_run` cleanly; 73× wall-time overhead at 8h × 60s macro_dt (480 macro steps).
  - M0: M0-C decision adopted — larger macro_dt cuts overhead 25.7×→8.3× at 1h. f_met 1-step lag formalised as known Vivarium parallel-scheduler property.
  - M0.5: noop scaling exponent **b=0.75 sub-linear** (Vivarium scheduler is fine), metab scaling exponent **b=0.99 linear** at **15.6 s/Process flat regardless of N**. LSODA spin-up is the wall, not Vivarium.
  - A4: Karr `.mat` mechanics pass, semantics fail. First numeric leaf = `3707764736` (a MATLAB handle, not biology). M-phase ingestion path must read `.m` source first, `.mat` second.
- **Key decisions**:
  - **vivarium-core IS the chassis going forward** (with M0-A persist-LSODA as a deferred backlog item for ensemble work).
  - **m0a-persist-lsoda** added to Phase 5 backlog — required before any ensemble (≥100 realisations) or sweep (>30 parameter points). Not a blocker for M1.
  - **Fused-ODE scheduler shelved** — scheduler isn't the bottleneck.
  - **Phase 5 entry conditions all met** — M1 (central carbon + energy charge) ready to start.
- **Files added (this session)**:
  - `opencell/{vivarium,diff,invariants,provenance}/` — 4 new packages
  - `opencell/vivarium/{processes,composite}.py` — 3 Process adapters + `build_coupled_engine`
  - `opencell/diff/multi_level.py` — A5 4-level diff tool
  - `opencell/invariants/core.py` — A7 InvariantSuite + 4 checks
  - `opencell/provenance/store.py` — A3 append-only JSONL store
  - `data/semantics/A6_semantics_contract.md`
  - `data/karr_fixtures/MetabolicReaction.mat`
  - `docs/phase4/{A1,A4,A8,M0,M05}_*.md` — 5 findings notes
  - `LICENSES.md` — A2 license clearance record
  - `scripts/{vivarium_demo,karr_mat_spike,m0_vertical_slice,m05_multiproc_scaling}.py`
  - `tests/{vivarium/test_vivarium_smoke,test_provenance_store,test_invariants,test_diff_tool}.py` — 44 new tests
  - `artifacts/{vivarium_demo,vivarium_vs_hybrid_diff,karr_a4_walk,karr_a4_provenance,M0_vertical_slice,M05_multiproc_scaling}.{json,jsonl,png}`
- **Key stats**: **437 tests passing** (was 410), 0 failed, 0 skipped. Test count: +27 net (44 added; some pre-existing skips re-enabled).
- **vivarium-core API quirks discovered**:
  - Process keys in the `processes` dict ARE store paths — name collision with declared store paths causes `Exception: trying to assign create inner for leaf node`. Solution: suffix process keys with `_proc`.
  - Multiple processes sharing a store: `_emit` policies must agree; conflicting `False`/`True` resolves to False silently. Set all to True.
  - `tests/vivarium/__init__.py` SHADOWS top-level `vivarium` package when pytest puts tests root on sys.path. Solution: no `__init__.py` in test subdirs.
- **Phase 4 status**: ✅ **CLOSED**
- **Next session**: Begin Phase 5 with M1 (central carbon + energy charge, ~30 enzymes). Or tackle M0-A persist-LSODA early if user wants ensemble work in M1.

### Session N+1 — 2026-04-25 (A4-followthrough: M-phase ingestion path proven)
- **What happened**: Did the A4 follow-through the user requested ("we need to read the .mat files before we start the ingestion"). Closed two unknowns left dangling by A4.
- **Headline findings**:
  - **The `.mat` test fixtures are MATLAB *object* dumps** (CellState class instances saved via `save('-v7',...,'fixture')` then header-rewritten — see `src_test/+sim/CellStateFixture.m`). scipy.io reads the struct shell but cannot reconstruct MATLAB classes — so the `s0/s1/s2/arr` quartet seen in A4 are `SparseMat` object internals, not biology. **Wrong source for ingestion.** Confirmed by `scripts/karr_a4f_compare.py` across 3 different state classes (Time, Host, MetabolicReaction) with declared field counts of 1/4/2 — all collapse to the same opaque quartet.
  - **The right source is `data/parameters.json`** (5238 B, fully human-readable JSON, complete process+state parameter manifest). Units NOT in JSON; recovered from matching `src/+state/*.m` and `src/+process/*.m` source comments.
  - **Mutual-consistency cross-check passes 0.00%**: `ln(2)/MetabolicReaction.meanInitialGrowthRate = 32400.7s` vs `Time.cellCycleLength = 32400.0s`. Two independent fields in the JSON manifest agree to 4 sig figs — strong evidence the manifest is internally consistent.
- **Files added**:
  - `data/karr_fixtures/parameters.json` — Karr's manifest (sha256-tracked)
  - `data/karr_fixtures/karr_parameters_unit_map.yaml` — unit recovery, source-cited
  - `data/karr_fixtures/m_source/{Time,MetabolicReaction,Host,Parameter,CellStateFixture,CircularSparseMat}.m`
  - `data/karr_fixtures/{Time,Host}.mat` — additional state fixtures (now known to be opaque)
  - `scripts/karr_a4f_compare.py` — proves `.mat` opacity is structural across classes
  - `scripts/karr_a4f_ingest.py` — ingestion driver (parameters.json → unit map → A3 store)
  - `scripts/_find_karr_params.py`, `scripts/_find_serializer.py`, `scripts/_list_karr_m.py` — discovery scripts
  - `artifacts/karr_a4f_comparison.json` — quantitative `.mat` evidence
  - `artifacts/karr_a4f_provenance.jsonl` — **18 real Karr parameters ingested into A3**
  - `docs/phase4/A4F_karr_m_source_followthrough.md` — findings doc
- **Confidence buckets in the 18 events**: 4 verified (all `Time.*` — `.m` source has `(s)` comments), 1 inferred (with cross-check), 13 UNVERIFIED (units guessed by name; flagged loudly, must be reviewed before kinetic use).
- **Deferred (intentionally)**: `data/knowledgeBase.mat` (3.95 MB, likely also a MATLAB object dump). Not opened. Wait until M1+ hits a kinetic constant not in `parameters.json`, then either Octave-extract or re-derive from primary literature.
- **Implication for Phase 5**: M-phase ingestion is no longer a research question. The path is `parameters.json` → unit map YAML → `ProvenanceStore.record_measured`. Each M-phase subsystem extends the unit map with verified entries.
- **DB**: `a4f-karr-m-source` marked done.

### Session N+2 — 2026-04-25 (M0-A persistent LSODA: runtime spike addressed)
- **What happened**: Built `PersistentMetabolismProcess` to fix the 73× Vivarium overhead measured in A1. The fix: hold `scipy.integrate.ode(rhs).set_integrator('lsoda')` on the Process across `next_update` calls, advance at absolute `t` incrementally, resync only on detected external store writes.
- **Headline numbers** (`artifacts/M0A_persistent_lsoda.json`):
  - 600s × 10s macro_dt: restart 18.5× → persistent **1.03×** (parity with hybrid_run baseline). Speedup **18.0×**.
  - 600s × 60s: restart 6.0× → persistent 1.15×. Speedup 5.2×.
  - 3600s × 60s: restart 28.5× → persistent **1.58×**. Speedup **18.0×**.
  - 3600s × 120s: restart 15.9× → persistent 2.78×. Speedup 5.7×.
  - **Persistent path overhead never exceeds 3× even at the most-stepped configuration.** The 73× spike is gone.
- **Correctness validation (4 tests, all pass)**:
  - **Gold-standard test**: persistent path matches a single full-horizon `solve_ivp` LSODA call to **max relative diff < 1e-4 across all 18 species, with zero resyncs.** Empirically validates that Chassagnole is autonomous and absolute-time stepping is correct (rubber-duck blocking concern resolved).
  - Persistent is closer to the gold standard than restart is.
  - External-write triggers exactly one resync; post-resync segment matches a fresh LSODA solve from the perturbed state at the same absolute t.
  - Speedup is real and reproducible.
- **A6 amendment**: LSODA-restart rule (~0.1 mM / 8h drift) now applies *only at resync boundaries*. With pure one-way coupling the persistent path matches a single full-horizon solve to LSODA tolerance.
- **Files added**:
  - `opencell/vivarium/persist.py` — the new Process
  - `opencell/vivarium/composite.py` — added `persistent_metabolism: bool = False` flag to `build_coupled_engine`
  - `opencell/vivarium/__init__.py` — export
  - `tests/vivarium/test_persistent_lsoda.py` — 4 tests
  - `scripts/m0a_benchmark.py` — benchmark driver
  - `artifacts/M0A_persistent_lsoda.{json,png}` — quantitative results
  - `docs/phase4/M0A_persistent_lsoda.md` — findings doc
- **Test stats**: **441 passed** (was 437, +4 new persistent LSODA tests, no regressions).
- **Design notes** (rubber-duck critique addressed):
  - **Time semantics**: integrator advances at absolute `t`, never resets. SBML `_build_env` does inject `t` so for non-autonomous future models we'd need a guard. Gold-standard test is the canary.
  - **External-write detection**: `np.allclose(store_y, cached_y, rtol=1e-12, atol=1e-15)`. Revision-counter approach deferred until M-phase has multiple writers to metabolites.
  - **API choice**: scipy.integrate.ode (older API) over LSODA class — cleaner support for continue+occasional reset.
  - **`nsteps=10000`** in set_integrator: scipy default of 500 caused reproducible failure at t=120 in the engine context. Bumped as a safety bound.
- **DB**: `m0a-persist-lsoda` marked done. 15 pending todos remain (M1-M7, L1-L4, E1-E2, Z1-Z2).
- **What this unblocks**: Karr-scale ensembles (≥100 realisations) viable on a single machine. M0.5's "≈14 days for 100-run ensemble" is invalidated. Phase 5 M1+ subsystems can be benchmarked at small `macro_dt` without engine-bottleneck concern. Phase 6 sweeps/screens no longer gated.
- **Next session**: M1 (central carbon + energy charge). The runtime question is settled; the ingestion path is settled (parameters.json → unit map → A3 store from A4F). All Phase 5 entry conditions met for the *first real subsystem*.
- **What happened**: Did the A4 follow-through the user requested ("we need to read the .mat files before we start the ingestion"). Closed two unknowns left dangling by A4.
- **Headline findings**:
  - **The `.mat` test fixtures are MATLAB *object* dumps** (CellState class instances saved via `save('-v7',...,'fixture')` then header-rewritten — see `src_test/+sim/CellStateFixture.m`). scipy.io reads the struct shell but cannot reconstruct MATLAB classes — so the `s0/s1/s2/arr` quartet seen in A4 are `SparseMat` object internals, not biology. **Wrong source for ingestion.** Confirmed by `scripts/karr_a4f_compare.py` across 3 different state classes (Time, Host, MetabolicReaction) with declared field counts of 1/4/2 — all collapse to the same opaque quartet.
  - **The right source is `data/parameters.json`** (5238 B, fully human-readable JSON, complete process+state parameter manifest). Units NOT in JSON; recovered from matching `src/+state/*.m` and `src/+process/*.m` source comments.
  - **Mutual-consistency cross-check passes 0.00%**: `ln(2)/MetabolicReaction.meanInitialGrowthRate = 32400.7s` vs `Time.cellCycleLength = 32400.0s`. Two independent fields in the JSON manifest agree to 4 sig figs — strong evidence the manifest is internally consistent.
- **Files added**:
  - `data/karr_fixtures/parameters.json` — Karr's manifest (sha256-tracked)
  - `data/karr_fixtures/karr_parameters_unit_map.yaml` — unit recovery, source-cited
  - `data/karr_fixtures/m_source/{Time,MetabolicReaction,Host,Parameter,CellStateFixture,CircularSparseMat}.m`
  - `data/karr_fixtures/{Time,Host}.mat` — additional state fixtures (now known to be opaque)
  - `scripts/karr_a4f_compare.py` — proves `.mat` opacity is structural across classes
  - `scripts/karr_a4f_ingest.py` — ingestion driver (parameters.json → unit map → A3 store)
  - `scripts/_find_karr_params.py`, `scripts/_find_serializer.py`, `scripts/_list_karr_m.py` — discovery scripts
  - `artifacts/karr_a4f_comparison.json` — quantitative `.mat` evidence
  - `artifacts/karr_a4f_provenance.jsonl` — **18 real Karr parameters ingested into A3**
  - `docs/phase4/A4F_karr_m_source_followthrough.md` — findings doc
- **Confidence buckets in the 18 events**: 4 verified (all `Time.*` — `.m` source has `(s)` comments), 1 inferred (with cross-check), 13 UNVERIFIED (units guessed by name; flagged loudly, must be reviewed before kinetic use).
- **Deferred (intentionally)**: `data/knowledgeBase.mat` (3.95 MB, likely also a MATLAB object dump). Not opened. Wait until M1+ hits a kinetic constant not in `parameters.json`, then either Octave-extract or re-derive from primary literature.
- **Implication for Phase 5**: M-phase ingestion is no longer a research question. The path is `parameters.json` → unit map YAML → `ProvenanceStore.record_measured`. Each M-phase subsystem extends the unit map with verified entries.
- **DB**: `a4f-karr-m-source` marked done. 16 pending todos remain (M0-A backlog, M1-M7, L1-L4, E1-E2, Z1-Z2).
- **Next session**: User picks Option B (M0-A persist-LSODA, ensemble enabler) or Option A (M1 central carbon + energy charge, first real subsystem). Ingestion path is de-risked either way.


- **GitHub**: sdrona-ms (personal). Do NOT use sdrona_microsoft (enterprise/managed)
- **Role**: Product manager who codes on the side, biology novice (Wikipedia-level knowledge)
- **Communication style**: Challenges assumptions, catches fabricated numbers, values honesty over confidence
- **Blog persona**: **Tehol** (the user) and **Bugg** (the AI) — characters from Erikson's *Malazan Book of the Fallen*. All blog posts are written as conversations between them. Tehol is the visionary PM asking the hard questions; Bugg is the competent-but-fallible servant doing the work
- **Preferences**: Named Python venvs (not generic `.venv`), Windows paths with backslashes
- **Machine**: Lenovo 11EVS09B00, Intel i7-10700, 64GB RAM, NO discrete GPU, E: drive workspace
- **Python**: Use 3.12 (not 3.14 — too new for JAX/COBRApy)
- **Corporate env**: Microsoft (fareast.corp.microsoft.com), SSL proxy may cause cert errors
- **Dev environment**: **WSL (Ubuntu 22.04)** is the primary dev environment as of Session 2. Use `.venv-wsl` venv, NOT `.venv-opencell` (Windows). See "Development Environment" section below.

## Key Decisions Made (with rationale)
1. **Cloud-first AI strategy** — local 14B models on CPU are too slow (est. 2-5 tok/s). Cloud for all tiers unless GPU acquired
2. **AI panels are evidence extractors, NOT decision-makers** — critical decisions need human approval
3. **v1.0 = framework + toy cell benchmark** (publishable standalone). **v2.0 = M. genitalium** (separate timeline TBD)
4. **Toy cell = coupled-solver benchmark**, NOT a biologically coherent organism. 3 core sub-models (metab + txn + tln), division cut
5. **Write-exclusion replaced with resource allocation / partition-merge** (Karr 2012 approach)
6. **Rejected LangChain/LangGraph** — wrong abstraction for our 2-person workflow. Documented as DEC-001 with explicit revisit triggers. External reviewer agreed modules are correct, disagreed on implementation strategy. We chose simplicity + zero framework dependency.
7. **Temperature is task-specific** — 0 for code/extraction, 0.3-0.5 for literature search
8. **Cost estimates are UNVERIFIED** — marked as such in plan. Will refine with actual data from cost_tracker.py
9. **Sensitivity analysis moved up** — OAT in Phase 2, Morris in Phase 3, Sobol in Phase 6
10. **Identifier crosswalk deferred to Phase 2** — toy cell uses synthetic IDs. Documented as DEC-002. Real crosswalk (KEGG↔BioCyc↔UniProt) starts when we pick M. genitalium reactions.

## External Review Findings (Session 3, 2026-04-23)
An external reviewer provided 5 strategic critiques. Summary of actions:

| Finding | Our Response | Action |
|---------|-------------|--------|
| Identifier crosswalk is a sub-project | Agree, but premature for toy cell | DEC-002: defer to Phase 2 |
| Coupling artifacts from operator splitting | Agree — add sync-interval sweep test | TODO: add to gate tests |
| AI panel hallucination by consensus | Already addressed — panels are evidence extractors, not decision-makers | No action needed |
| CPU JAX compilation wall | Known tradeoff — fine for toy cell, Colab T4 for v2.0 | Monitor |
| LangGraph for orchestration | Rejected — our pipeline is simpler and sufficient | DEC-001 documented |
| Use `jax.jit` + `lax.scan` for perf | Good tip — Diffrax handles JIT; adopt `lax.scan` in Phase 2 custom loops | Note for Phase 2 |
| Contract-driven development (Pydantic schemas) | Already built — SubModelContract, IOManifest, JSON Schema validation | No action needed |
| Data versioning (DVC) | Already built — content-hashed snapshots in `data/versioning.py` | No action needed |
| Containerization | Already have Dockerfile + manifest.py — need end-to-end golden-run test | TODO: test Docker build |

## Credibility Policy
- AI (me) was caught fabricating cost estimates and tok/s performance numbers
- All quantitative claims must be labeled VERIFIED or UNVERIFIED
- "I don't know" is preferred over plausible-sounding guesses
- Benchmark before claiming

## Database Access Status
- **BRENDA**: Registered (dronasrinivas@gmail.com), web portal works, SOAP API failed (activation delay). PASSWORD NEEDS CHANGING (was exposed in earlier chat)
- **BioCyc**: Not yet accessed, needs subscription (~$100-150/yr) or institutional access
- **KEGG**: Free API (3 req/s), no redistribution
- **UniProt/GenBank**: Free, open
- **Karr 2012**: Free on GitHub (~1,900 params) — primary fallback

## Development Environment
- **Primary**: WSL Ubuntu 22.04 (Python 3.12.13)
- **Venv**: `.venv-wsl` at `/mnt/e/opencell/.venv-wsl` (or `E:\opencell\.venv-wsl` from Windows)
- **Activation**: `wsl -d Ubuntu-22.04 -- bash -c "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell && <command>"`
- **Legacy Windows venv**: `.venv-opencell` — still works but NOT primary. Use only if WSL is unavailable.
- **Why WSL**: Linux matches CI runners (Ubuntu), JAX GPU support is Linux-only, no Windows path quirks
- **Same files**: WSL sees `E:\opencell` as `/mnt/e/opencell` — same git repo, same plan.md, no duplication
- **Caveat**: `/mnt/` I/O is slower than native Linux filesystem. Fine for our codebase size.

## What's NOT installed yet
- Ollama (optional — only if GPU acquired)
- GitHub CLI (needed for repo push)

## Cross-Model Audit History
- **Round 1**: Claude Opus 4.6 + GPT-5.2 → 25+ findings, all incorporated
- **Round 2**: GPT-5.4 + Claude Opus 4.7 → 54 findings total, all incorporated (23 were initially missed, caught via systematic cross-check)
- Full findings in `opencell_tasks.db` → `review_findings` table

## Project Files
- `E:\opencell\plan.md` — Master plan (~1220 lines, Phase 4 progress table updated)
- `E:\opencell\opencell_tasks.db` — Persistent task DB (159 todos: 16 pending, 95 done, 48 blocked)
- `E:\opencell\SESSION_CONTEXT.md` — This file
- `E:\opencell\LICENSES.md` — A2 license clearance record (Phase 4)
- `E:\opencell\data\semantics\A6_semantics_contract.md` — Semantics contract for engine equivalence (Phase 4)
- `E:\opencell\docs\phase4\` — Phase 4 findings: A1, A4, A8, M0, M05
- `E:\opencell\artifacts\` — Phase 4 quantitative artefacts (vivarium_demo.png, M0_vertical_slice.json, M05_multiproc_scaling.json, etc.)

## First Steps When Resuming
1. Read this file and plan.md
2. Activate WSL venv:
```bash
wsl -d Ubuntu-22.04 -- bash -c "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell && python -m pytest tests/ -q --tb=short"
```
3. Check ready tasks in persistent DB:
```python
import sqlite3
db = sqlite3.connect(r'E:\opencell\opencell_tasks.db')
db.execute("""
    SELECT id, title FROM todos t WHERE t.status = 'pending' AND NOT EXISTS (
        SELECT 1 FROM todo_deps td JOIN todos dep ON td.depends_on = dep.id
        WHERE td.todo_id = t.id AND dep.status != 'done'
    ) ORDER BY id
""").fetchall()
```

---

## Session N+3 (2026-04-25) — M0-A shipped, M1 halted on parameter synthesis

### M0-A persistent LSODA — DONE
- `opencell/vivarium/persist.py::PersistentMetabolismProcess` holds
  `scipy.integrate.ode` + LSODA across `next_update` calls.
- Headline: 1h x 60s overhead 28.5x -> 1.58x (18x speedup); 600s x 10s
  at parity (1.03x) with hybrid_run baseline.
- 4 tests pass; full suite 441 passing (was 437).
- A6 LSODA-restart rule revised to apply only at resync boundaries.
- Findings: `docs/phase4/M0A_persistent_lsoda.md`.
- `m0a-persist-lsoda` -> done. Ensembles/sweeps no longer gated.

### M1 central carbon — HALTED, user directive enforced
- Began design with rubber-duck critique; got strong design (pFBA +
  ODE energy-charge wrapper, hard adenylate conservation, AK as fast
  kinetic, 5-criterion validation oracle).
- Started writing `opencell/m1/central_carbon.py` with hand-curated
  reaction table + invented flux bounds + invented biomass coefficients
  + invented validation thresholds.
- **User HARD-STOPPED**: "no hand listing of parameters, please. if you
  are stuck somewhere, ask me and we will get the params from a pdf
  manually, but DO NOT create or synthesis any values for M1."
- Deleted all M1 code dirs (`opencell/m1/`, `tests/m1/`). Kept
  `docs/phase5/` and produced
  `docs/phase5/M1_BLOCKED_parameter_inventory.md` listing every value
  needed and every PDF the user must provide to unblock.
- Identified Suthers 2009 iPS189 = DOI 10.1371/journal.pcbi.1000285
  (PMC2633051, open access) as the canonical reaction-list source.
- `m1-central-carbon` -> blocked.

### Where to resume
- User to provide / authorise fetch of Suthers 2009 supplementary
  (reaction list + biomass), Karr 2012 supplementary (initial
  concentrations + EC target), and BRENDA AK K_eq citation.
- M0-A is done; running ensembles/sweeps on Chassagnole+Vilar is now
  cheap and unblocked. Could be the next visible artefact while M1
  parameters are being procured.

---

## Session N+3 addendum (2026-04-25) — M1 unblocked via GitHub

User pushback: "why are you unable to get the data from existing
GitHub repos?" was correct. Reversed earlier overcautious "blocked"
status in 3 GitHub fetches:

- `git clone https://github.com/CovertLab/WholeCell` -> data/m1_sources/WholeCell/
  (knowledgeBase.mat opaque without MATLAB, but parameters.json and
  simulation outputs accessible).
- `git clone https://github.com/CovertLab/WholeCellKB` -> data/m1_sources/WholeCellKB/
  with public/fixtures/data.xlsx (1.7 MB, 20 sheets) and data.sql
  (8.2 MB, full DB dump with public_evidence provenance rows).
- Suthers 2009 PLoS supplementary s005 -> iPS189.xml (232 KB SBML,
  350 reactions, R_Biomass with 61 reactants, all glycolysis +
  fermentation present).

PMC supplementary direct downloads remain blocked by JavaScript
proof-of-work challenge but not needed: WholeCellKB has the same data
in queryable form. `data/m1_sources/iPS189.xml` parsed cleanly with
libsbml (0 errors). `WholeCellKB/data.xlsx` Reactions sheet
confirms Adk1 Keq=1.0 with kinetic form Vmax*AMP/(Km+AMP).

M1 todo status: blocked -> pending. New plan doc:
`docs/phase5/M1_sourced_inventory.md` lists every M1 input with its
GitHub source path / commit SHA. Zero synthesis required to proceed.

Next: build `scripts/karr_a4f_ingest_m1.py` to convert sources
into a single sourced JSON (`iPS189_m1.json`) the M1 Vivarium
Process can consume.

## Session N+4 (2026-04-25 cont.) — M1 ingest + LP infeasibility fixed

**M1 central-carbon FBA module is green (12/12).** The LP infeasibility
flagged at the previous checkpoint was caused by treating COBRA
boundary species (suffix _b, e.g. M_glc_D_b) as quasi-steady-state.
COBRA convention exempts _b species from S v = 0 — they are the
system sinks/sources for exchange reactions. Fix: `CentralCarbonModel`
now exposes `balanced_species_mask` and `boundary_species`; `pfba`
imposes `S v = 0` only on non-boundary rows; the mass-balance test
checks the same restricted set. With the fix:

- `pfba(model, "R_ATPM", "max")` is feasible; max ATPM exceeds the
  Karr-sourced NGAM lower bound (8.39 mmol_ATP/(gDW·h)).
- Glycolytic flux non-zero and directional; total flux finite.
- 12/12 `tests/m1/test_central_carbon.py` pass; full suite
  427 pass / 6 skip / 1 fail. The 1 fail is the **pre-existing**
  `ModuleNotFoundError: vivarium.core` from
  `opencell\vivarium\processes.py` (env-only — vivarium-core
  not installed in the active venv); unrelated to M1.

**Files changed this session:**
- `opencell/m1/central_carbon.py` — added `boundary_species`,
  `balanced_species_mask`, masked LP rows in `pfba` (LP1 + LP2).
- `tests/m1/test_central_carbon.py` — `test_steady_state_mass_balance`
  asserts on the masked S only.

**No-synthesis status:** intact. `test_no_hardcoded_numerics_in_module`
green; all bounds still flow from `data/karr_fixtures/iPS189_m1.json`.

**DB:** `m1-central-carbon` → done.

**Next:**
1. Extract initial intracellular concentrations from
   `data/m1_sources/WholeCell/data/Simulation_fitted.mat` via
   `scipy.io.loadmat` (deferred from prior session).
2. Build the Vivarium Process wrapper
   `opencell/vivarium/m1_metabolism.py` on the M0-A persistent-LSODA
   pattern (gated on getting `vivarium-core` reinstalled in venv).
3. Five-criterion validation oracle + `scripts/m1_validate.py` →
   `artifacts/M1_validation.json`.
4. Findings doc `docs/phase5/M1_central_carbon.md`.

## Session N+5 (2026-04-25 cont.) — Karr comparison published, MAT-deserialization gap documented

**Question asked: "are you running tests in WSL venv?".**  No — earlier I was running them through .venv-opencell\Scripts\python.exe (Windows).  Switched to .venv-wsl (Linux).  Full suite under WSL: **453 passed, 1 warning, 0 failures.**  vivarium-core IS installed there — the previous "1 fail" was an artifact of probing the wrong venv.

**Question asked: "are MAT files open source?".**  The WholeCell repo (data/m1_sources/WholeCell/) is MIT-licensed and we now have the full 182 MB / 187 .m source tree (re-cloned without sparse-checkout).  But Simulation_fitted.mat and knowledgeBase.mat are serialized MATLAB *class instances* (mcos blobs).  scipy.io.loadmat returns (s0,s1,s2,arr) opaque structures.  pymatreader exposes __function_workspace__ but warns "Complex objects (like classes) are not supported."  Installed Octave (apt) and tried with the WholeCell src on the path — Octave hung indefinitely because the class hierarchy transitively imports CPLEX 12.2 (commercial), GLPK-MEX (binary), Java libs, MySQL JDBC.  In practice: deserializing those .mat files requires the full MATLAB toolchain + a commercial CPLEX license.  This is a real, documented gap in how Karr et al. published their data.

**Karr-vs-OpenCell comparison published.**  scripts/m1_validate.py runs pFBA on the full 350-reaction iPS189 SBML (libsbml) with three modes:
- **Mode A** literal Karr setup (parameters.json bounds + NGAM 8.39 + zinc transporter opened): biomass μ = 0.
- **Mode B** Mode A with irreversibility relaxed on non-Karr-overridden reactions: μ ≈ 542 / glucose -13.34 / ATPM 8.39 — proves LP machinery is correct.
- **Mode C** fully open, no NGAM: same as B.

Karr published targets (sourced):
- meanInitialGrowthRate = 2.1393e-5 cell/s = 0.077 h⁻¹ (WCKB `Misc. parameters` Parameter_0151, `is_experimentally_constrained: true`)
- NGAM = 8.39 mmol_ATP/(gDW·h) (WCKB Parameter_0093 + parameters.json)
- GAM = 59.81 mmol_ATP/gDCW (WCKB Parameter_0092)
- exchangeRateUpperBound_carbon = 12.0; _noncarbon = 20.0

Outputs: `artifacts/M1_validation.json` (schema_v2), `docs/phase5/M1_validation_report.md`.  No values were synthesized.

**libroadrunner status (asked: "are we still validating against libroadrunner?"):**  Yes for kinetic ODE models — Chassagnole metabolism overlay (~1e-6 rel agreement) and Vilar transcription overlay both still in artifacts/.  But libroadrunner integrates ODEs from SBML; it does NOT solve FBA LPs, so it is not the right oracle for M1.  For M1 the proper oracle is Karr's published steady-state values, which is exactly what M1_validation.json compares against.

**Next:**
1. Augment iPS189 with sourced transporter fixes (BiGG / KEGG canonical reversibility) one reaction at a time, each with provenance.  Goal: Mode A predicts μ > 0 within an order of magnitude of Karr's 0.077 h⁻¹.
2. Add `test_m1_validation_artifact_exists_and_has_provenance` to `tests/m1/` to lock in the artifact contract.
3. Build Vivarium Process wrapper for M1 on the M0-A persistent-LSODA pattern.


## Session N+6 (2026-04-24 evening) — pivots, MATLAB extraction script ready

**User questions and outcomes this session:**

1. **"so, against the published targets, only one value is matching. is that correct?"**
   Confirmed.  Of the 4 published Karr targets, only NGAM (8.39 mmol_ATP/(gDW·h))
   matches — and only because we enforce it as a hard lb on the LP.  Zero
   *independent* quantities agree.  Documented in
   `artifacts/M1_validation.json` interpretation block.

2. **"what is this augment expected to do?"** (referring to `m1-ips189-augment`)
   Explained: the augment was meant to add BiGG/KEGG-sourced transporter
   reversibility fixes one reaction at a time until Mode A predicts μ > 0.
   Acceptance: μ within an order of magnitude of Karr's 0.077 h⁻¹.  Offered
   alternative: switch to **iJW145** (Wodke 2013), a published Mycoplasma
   genome-scale model.

3. User chose iJW145 path → I corrected myself: **iJW145 is M. pneumoniae,
   not M. genitalium.**  Karr's 0.077 h⁻¹ target is M.genitalium-specific;
   iJW145 cannot give an apples-to-apples comparison.  User then dropped
   iJW145 ("not comfortable with synthesising data to test").

4. **"if I can get access to MATLAB, will we be able to get the data?"**
   Answer: yes — and CPLEX is **not** required for *extraction* (only for
   *simulation*).  MATLAB Online is free.  Extraction script writes plain
   MAT v7 files that scipy.io.loadmat reads directly.

5. **"prepare it. I will create the online account on the side."**
   Authored:

   - `scripts/matlab/extract_karr_mats.m` (~13 KB, ~310 lines).  Walks
     every property of every WholeCell `.mat` via `struct(obj)` +
     metaclass introspection fallback; sentinel-stubs Java handles and
     function handles; breaks handle cycles; writes `*_flat.mat` (v7) +
     `manifest.json` with sha256/release/timestamp; tolerates per-file
     errors (continues; logs to manifest).  Includes Octave-fallback JSON
     encoder.
   - `scripts/matlab/README.md` runbook: account signup → upload
     WholeCell folder (or `git clone` inside MATLAB Online) → one
     command `extract_karr_mats(pwd, fullfile(pwd,'karr_flat'))` →
     download `karr_flat/` zip → unzip into
     `data/m1_sources/karr_flat/` (gitignored; only `manifest.json`
     committed) → verify with `scipy.io.loadmat`.
   - **Smoke test passed**: ran in Octave 6.4 against the 3 small
     `data/karr_fixtures/*.mat` files.  All 3 round-tripped through
     scipy successfully (top-level field `fixture` accessible after
     deserialization).

**M1 todos final state for today:**

| id | status | notes |
|---|---|---|
| `m1-central-carbon` | done | 12/12 tests, no-synthesis guard intact |
| `m1-karr-validation` | done | 3-mode comparison published; 0/4 targets independent agreement |
| `m1-ips189-augment` | blocked | superseded by Karr MAT extraction path |
| `m1-ijw145-ingest` | blocked | dropped (M.pneumoniae, not M.gen) |
| `m1-matlab-extract-script` | done | script + README + smoke test green |
| `m1-karr-flat-ingest` | pending | unblocks once user uploads MATLAB Online output |

**Tests:** 453 / 453 still green under WSL venv.  No code in
`opencell/` changed this session.

**Blog post:** `docs/blog/2026-04-24-the-morning-we-stopped-being-the-only-ones.md`
covers (a) the morning vivarium-core pivot via 4 rounds of adversarial
critique, and (b) the evening M1 honest-negative + MATLAB Online
unblock.

**Where to resume tomorrow:**
1. User runs `extract_karr_mats` in MATLAB Online → downloads
   `karr_flat/` zip → unzips into `data/m1_sources/karr_flat/`.
2. Author `scripts/m1_karr_flat_ingest.py` to parse the flat MAT
   structures for: fitted biomass composition, fitted kinetic rates,
   the actual stoichiometry matrix used by Karr's metabolism process,
   exchange caps, NGAM/GAM, growth rate target.  Each value gets a
   provenance entry (source file + path within struct + sha256).
3. Re-run `scripts/m1_validate.py` with Karr-fitted-S as Mode D.
   Acceptance: ≥3 of 4 Karr published targets agree within 10%.
4. If acceptance met → flip `m1-karr-flat-ingest` → done; begin
   `m1-vivarium-process` (Vivarium Process wrapper for M1 on
   M0-A persistent-LSODA pattern).
5. If not met → diagnose discrepancy per "operational failure branch"
   in plan.md (negative result becomes the publication).


## Session N+7 (2026-04-25 00:00) — Karr MAT extraction unblocked locally; Mode D published; still 0/4 honest

**User trigger:** `wake up! I installed MATLAB locally in E:/, I hope this will fastrack our data extraction`.

**What changed:**

1. **Local MATLAB R2026a available at `E:\MATLAB\bin\matlab.exe`** (trial license, no CPLEX). Replaces the MATLAB-Online plan in N+6. Run via `& 'E:\MATLAB\bin\matlab.exe' -batch ...`.

2. **Single typo blocked load:** `import import edu.stanford...` on line 134 of `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/FtsZPolymerization.m`. Older MATLAB tolerated; R2026a rejects. Fixed in place; WholeCell/ is gitignored so the fix is local-only (todo: upstream PR to CovertLab/WholeCell).

3. **Generic walker hung:** `extract_karr_mats.m` from N+6 hit handle-graph cycles (every Process back-references its Simulation; states reference each other). Cycle-detection key was wrong → combinatorial explosion → hang.

4. **Targeted extractor shipped:** `scripts/matlab/extract_karr_targeted.m` (~280 lines) — pulls only named properties (sim.parameters, fittedConstants, options, all 28 processes' getParameters/getFittedConstants, deep dump of Metabolism's 24 named FBA properties + full 174-property manifest, 16 states), bounded depth 4-6. Runs in ~3 min. Outputs `data/m1_sources/karr_flat/sim_fitted_targeted.mat` (362 KB) + `knowledgeBase_targeted.mat` (12 MB), both gitignored, both `scipy.io.loadmat`-readable.

5. **Mode D added to `scripts/m1_validate.py` (schema_v3):** loads `metabolism.fbaReactionStoichiometryMatrix` (376×504), `fbaReactionBounds` (504×2), `fbaObjective` (504-vec) directly from the targeted MAT and maximises biomass via HiGHS.

   - Result: **μ = 0.0109 /h vs Karr published 0.077 /h** — off by ~7×.
   - Net independent agreement: **still 0/4**. The NGAM/GAM/cellCycleLength values reported by Mode D match Karr's published values **by definition** — they are read from the MAT, not predicted. Honest interpretation now states this in the artifact and report.
   - Critical insight: the gap is NOT 'iPS189 vs Karr's curated network' — both stoichiometry and bounds are now Karr's own. Likely missing inputs: (a) the 35 small (-5.31e-9) penalty terms in `fbaObjective` dropped during diagnosis, (b) `fbaEnzymeBounds` (kinetic flux ceilings, extracted but not applied), (c) the dynamic nature of Karr's metabolism process (substrate/enzyme amounts update each sim-second from the other 27 processes; static snapshot may not be at biomass-max steady state).

6. **User pushback caught a misleading framing:** I initially described NGAM/GAM/cellCycleLength matching `bit-for-bit`. That is tautological since we read those numbers out of the MAT. Artifact, report and interpretation rewritten to call out what is read vs predicted explicitly.

7. **Tests:** 453/453 still pass under .venv-wsl (11m13s).

**Commits this session:**
- `6dace00` — phase5: targeted Karr MAT extractor (R2026a) + M1 Mode D — Karr's own fitted FBA, 0/1 independent agreement.

**Todos updated:**
- `m1-karr-flat-ingest` → done.
- New: `m1-mode-d-close-gap` (pending). Acceptance: μ within 25% of 0.077/h, OR documented reason why static-snapshot FBA cannot reach published μ.
- New: `m1-extract-per-process-fixtures` (pending, deferred until M2 begins).

**Where to resume:** investigate Mode D 7× gap. Order of attempts: (i) restore the small-penalty objective terms, (ii) apply `fbaEnzymeBounds` as additional flux ceilings, (iii) check whether the static snapshot is even *meant* to FBA-equilibrate to μ — read the relevant chunk of Karr's `Metabolism.m` `evolveState` method. If none reach 25%, that is itself a valid finding and the M1 acceptance criterion needs revising.

