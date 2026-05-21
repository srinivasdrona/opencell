<overview>
The user ("Tehol") is building "OpenCell" — an open-source whole-cell computational simulation in Python/JAX. This session continued Phase 1 implementation (completing data layer, orchestrator, and remaining components), processed external reviewer feedback, switched the dev environment from Windows to WSL, and began the critical Phase 1→2 Gate tests using a published textbook micro-model (Alon 2006 / Thattai 2001) instead of synthetic parameters. The gate tests validate that our simulation engine can reproduce a known analytical solution before we build real biology on top.
</overview>

<history>
1. Resumed Phase 1 implementation (data layer commit was in progress)
   - Created `orchestrator/router.py` (tier-based model routing with temperature policy)
   - Created `orchestrator/cost_tracker.py` (per-call token/cost logging to SQLite)
   - Created `benchmarks/bench_coupling.py` (2-model Producer+Consumer coupling benchmark)
   - Wrote comprehensive tests in `tests/unit/test_data_layer.py` (23 new tests)
   - Fixed bug: `models or DEFAULT_MODELS` — empty dict `{}` is falsy in Python, changed to `models if models is not None else DEFAULT_MODELS`
   - Fixed contracts.py schema path: was pointing to `orchestrator/schemas/` but schemas are at `data/schemas/`
   - Result: 91 tests passing, committed as `08f67b0`

2. Built remaining Phase 1 components
   - Created `orchestrator/panel.py` (expert panel with claim graphs, DOI verification)
   - Created `orchestrator/pipeline.py` (sub-model build workflow coordinator)
   - Created `analysis/observation.py` (observation model: OD600, qPCR assay mappings)
   - Created `core/validation.py` (validation harness with mass conservation, positivity, doubling time validators)
   - Created `core/replay.py` (single-step delta ledger for debugging)
   - Created `core/io_manifests.py` (module I/O manifest registry)
   - Created `tools/naked_numbers_lint.py` (AST lint for hardcoded biology numbers)
   - Created 6 agent skill profiles in `.github/skills/`
   - Created `docs/benchmark-charter.md` (rejection criteria)
   - Created `.github/PULL_REQUEST_TEMPLATE/biology_model.md`
   - Updated `.github/workflows/ci.yml` to tiered CI (lint → unit → property → scientific → gate)
   - Created `data/versioning.py` (content-hashed parameter snapshots)
   - Result: 114 tests passing, committed as `78945ef` and `6c7e516`

3. User asked about CI running on Ubuntu when developing on Windows
   - Explained GitHub Actions runners are Linux-based
   - Discussed WSL vs Windows vs GPU devbox options
   - User checked internal CWS devbox configs (all ad-tech, none suitable)
   - User decided on WSL Ubuntu 22.04 on local machine

4. Set up WSL development environment
   - Confirmed Ubuntu-22.04 WSL distro available (Python 3.10 default)
   - User installed Python 3.12 via deadsnakes PPA (needed sudo)
   - Created `.venv-wsl` venv with Python 3.12.13
   - Installed all dependencies via `pip install -e ".[dev]"`
   - **114 tests passed on WSL on first run — zero code changes needed**
   - Updated SESSION_CONTEXT.md and plan.md to reflect WSL as primary dev environment
   - Committed as `6c7e516` and `2fcf142`

5. User shared blog post request — wrote Day 1 blog post
   - Created `docs/blog/2026-04-22-4500-lines-before-lunch.md` (Tehol/Bugg dialogue)
   - Committed as `0a4997b`

6. User asked about GitHub webpage — explained repo is local-only, never pushed
   - User decided to keep it local for a couple more days

7. User shared external reviewer feedback (next morning, Session 3)
   - Reviewer provided 5 strategic critiques across 3 messages
   - **Identifier Crosswalk Trap**: Agreed it's real but premature for toy cell → DEC-002
   - **Solver Coupling Artifacts**: Agreed — need sync-interval sweep test (TODO)
   - **AI Panel Hallucination**: Already addressed in our design
   - **CPU JAX Compilation Wall**: Known, fine for toy cell
   - **LangGraph for Orchestration**: Rejected with detailed rationale → DEC-001
   - Additional recommendations (contract-driven dev, DVC, Docker): Already implemented
   - JAX tips (jit + lax.scan): Noted for Phase 2
   - Created formal decision documents: `decisions/dec-001-no-langgraph.md`, `decisions/dec-002-crosswalk-phase2.md`
   - Updated `decisions/_decision_index.yaml` with both decisions
   - Added External Review Findings table to SESSION_CONTEXT.md
   - Committed as `58ecd92`

8. User asked about Azure AI Foundry
   - Researched Foundry capabilities (1,900+ models, serverless API, batch mode)
   - Recommended as Phase 2 consideration for expert panel, not needed now
   - Integration would be ~20 lines in router.py

9. User asked about blockers for Phase 1→2 Gate tests
   - Checked DB — only 2 gate todos existed, needed all 8
   - Created 8 gate test todos (g1-micro-derive through g1-thermo) with dependencies
   - No blockers identified — all infrastructure ready

10. User said "let's begin" — started Gate G1.1
    - Created initial micro-model derivation with synthetic parameters
    - Rubber-duck critique found 5 blocking issues: mRNA/protein size inconsistency, missing Pi species, thermodynamic incompleteness, ATP-independent rates
    - **User's key insight**: "Instead of making up params, why can't we use a published micro-model?"
    - Rewrote entire derivation using Alon (2006) / Thattai & van Oudenaarden (2001)
    - Published E. coli constitutive gene expression model with measured parameters
    - Includes exact analytical solution (both transient and steady-state) and stochastic variance formula

11. Began Gate G1.2 implementation
    - Created `opencell/models/micro_model.py` with analytical solution functions
    - Created `tests/gates/test_micro_model.py` with gate tests for G1.2, G1.3, and stochastic
    - Fixed import errors (function is `solve_ode` not `solve_ode_jax`)
    - Fixed API mismatches (SciPy returns ys as (n_species, n_steps), need transpose)
    - **Tests NOT YET RUN after fixes** — compaction happened before verification
</history>

<work_done>
Files created this session:
- `opencell/orchestrator/router.py` — tier-based model routing with temperature policy
- `opencell/orchestrator/cost_tracker.py` — per-call token/cost logging to SQLite
- `opencell/orchestrator/panel.py` — expert panel with claim graphs
- `opencell/orchestrator/pipeline.py` — sub-model build workflow coordinator
- `opencell/analysis/observation.py` — observation model (OD600, qPCR)
- `opencell/core/validation.py` — validation harness (conservation, positivity, doubling)
- `opencell/core/replay.py` — single-step delta ledger debugger
- `opencell/core/io_manifests.py` — module I/O manifest registry
- `opencell/data/versioning.py` — content-hashed parameter snapshots
- `opencell/models/micro_model.py` — Alon/Thattai micro-model with analytical solutions
- `benchmarks/bench_coupling.py` — 2-model coupling benchmark
- `tools/naked_numbers_lint.py` — AST lint for hardcoded biology numbers
- `docs/benchmark-charter.md` — rejection criteria document
- `docs/biology/micro_model_derivation.md` — analytical derivation (rewritten with published params)
- `docs/blog/2026-04-22-4500-lines-before-lunch.md` — Day 1 blog post
- `.github/skills/biology-researcher.md` — skill profile
- `.github/skills/numerical-modeler.md` — skill profile
- `.github/skills/software-architect.md` — skill profile
- `.github/skills/data-engineer.md` — skill profile
- `.github/skills/biology-validator.md` — skill profile
- `.github/skills/blog-writer.md` — skill profile
- `.github/PULL_REQUEST_TEMPLATE/biology_model.md` — PR checklist
- `decisions/dec-001-no-langgraph.md` — formal decision document
- `decisions/dec-002-crosswalk-phase2.md` — formal decision document
- `tests/unit/test_data_layer.py` — 23 tests for data layer + orchestrator
- `tests/unit/test_phase1_remaining.py` — 23 tests for remaining Phase 1
- `tests/gates/__init__.py` — gate test package
- `tests/gates/test_micro_model.py` — gate tests G1.2, G1.3, stochastic (NOT YET VERIFIED)

Files modified:
- `opencell/orchestrator/contracts.py` — fixed schema path to `data/schemas/`
- `.github/workflows/ci.yml` — tiered CI (lint → unit → property → scientific → gate)
- `decisions/_decision_index.yaml` — added DEC-001 and DEC-002
- `SESSION_CONTEXT.md` — WSL env, Session 2+3 logs, external review findings table
- `plan.md` — added current status header

Git commits on `main` (this session):
1. `08f67b0` — feat: data layer, orchestrator router/cost tracker, coupling benchmark
2. `78945ef` — feat: complete Phase 1 — panel, pipeline, observation, validation, replay, manifests, skills
3. `6c7e516` — chore: switch to WSL, update docs, add CI tiers and data versioning
4. `0a4997b` — blog: Day 1 — 4,500 Lines Before Lunch
5. `2fcf142` — chore: end-of-session context update
6. `58ecd92` — docs: document external review findings and decisions DEC-001, DEC-002
7. (uncommitted) — micro_model.py, micro_model_derivation.md, test_micro_model.py

Current state:
- 114 tests passing (verified on both Windows and WSL)
- Gate test file created but NOT YET RUN after API fixes
- Phase 1 infrastructure: COMPLETE
- Phase 1→2 Gate: IN PROGRESS (G1.1 done, G1.2 implementation created but unverified)

Todo DB status: 45 done, 61 pending (including 8 gate tests), 1 blocked (p1-db-access)
</work_done>

<technical_details>
### Solver API (critical for gate tests)
- JAX solver: `from opencell.solvers.ode import solve_ode, ODESolverConfig` — NOT `solve_ode_jax`
- `solve_ode(rhs, y0, t_span, args, config, saveat)` → returns `ODEResult` with `.ts` and `.ys` (n_steps, n_species)
- SciPy solver: `from opencell.solvers.ode_scipy import solve_ode_scipy` 
- `solve_ode_scipy(rhs, y0, t_span, config, t_eval)` → returns `ScipyODEResult` with `.ys` as **(n_species, n_steps)** — needs `.T` transpose
- RHS signature: JAX uses `f(t, y, args)`, SciPy uses `f(t, y)` — different!

### WSL Development Environment
- **Primary**: WSL Ubuntu 22.04, Python 3.12.13
- **Venv**: `.venv-wsl` at `/mnt/e/opencell/.venv-wsl`
- **Activation**: `wsl -d Ubuntu-22.04 -- bash -c "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell && <command>"`
- **Legacy**: `.venv-opencell` (Windows, Python 3.12.10) still works but NOT primary
- **Same files**: WSL sees `E:\opencell` as `/mnt/e/opencell` — no duplication
- **I/O caveat**: `/mnt/` is slower than native Linux fs, fine for our codebase

### Micro-Model (Gate G1.1/G1.2) — Key Details
- **Model**: Constitutive gene expression (Alon 2006, Box 1.1 / Thattai 2001)
- **Parameters**: E. coli mid-range from Thattai Table 1: α_m=0.2/min, β_m=0.5/min, α_p=0.5/min, β_p=0.005/min
- **Steady state**: m*=0.4 copies/cell, p*=40.0 copies/cell
- **Analytical transient**: m(t) = m_ss·(1-e^(-β_m·t)), p(t) = p_ss·[1+(β_p·e^(-β_m·t)-β_m·e^(-β_p·t))/(β_m-β_p)]
- **Stochastic**: burst size b=1.0, Var(p)≈79.6, Fano≈1.99 (super-Poissonian)
- **Timescale separation**: 100× (mRNA 2min vs protein 200min) — mildly stiff
- **Why not synthetic params**: Rubber-duck found 5 blocking issues (50nt mRNA can't encode 50aa protein, missing Pi, etc.)

### External Review Decisions
- **DEC-001**: Rejected LangGraph — lightweight pipeline sufficient. Revisit if 5+ autonomous agents needed.
- **DEC-002**: Identifier crosswalk deferred to Phase 2 — toy cell uses synthetic IDs.
- **Actionable from review**: Add coupling-artifact sync-interval sweep to gate tests; test Docker build e2e.

### Bug Fixes This Session
- `models or DEFAULT_MODELS` → `models if models is not None else DEFAULT_MODELS` (empty dict is falsy)
- Schema path in contracts.py: `Path(__file__).parent / "schemas"` → `Path(__file__).parent.parent / "data" / "schemas"`
- `solve_ode_jax` doesn't exist → function is `solve_ode` from `opencell.solvers.ode`
- SciPy `ys` shape is (n_species, n_steps), not (n_steps, n_species)

### Key Decisions Carried Forward
- Blog persona: Tehol (user) and Bugg (AI) from Malazan Book of the Fallen
- All blog posts are Tehol-Bugg dialogues
- Credibility policy: mark VERIFIED vs UNVERIFIED, say "I don't know"
- Git config: user.name="Srinivas Drona", user.email="dronasrinivas@gmail.com"
- Repo is LOCAL ONLY — user wants to wait before pushing to GitHub
- Azure AI Foundry noted as Phase 2 consideration for expert panel API calls
</technical_details>

<important_files>
- `E:\opencell\docs\biology\micro_model_derivation.md`
   - THE critical gate document — analytical derivation with published parameters
   - Rewritten this session from synthetic to Alon/Thattai published params
   - Contains exact steady-state, transient solution, stochastic variance, verification criteria

- `E:\opencell\opencell\models\micro_model.py`
   - MicroModelParams dataclass with published E. coli parameters
   - `m_exact(t)` and `p_exact(t)` analytical solution functions
   - `m_ss`, `p_ss`, `burst_size`, `protein_variance_ss` properties
   - Created this session, NOT YET TESTED

- `E:\opencell\tests\gates\test_micro_model.py`
   - Gate tests G1.2 (solver vs analytical), G1.3 (JAX vs SciPy), stochastic
   - Fixed API calls but NOT YET RUN after fixes — this is the immediate next step
   - Classes: TestGateG12 (4 tests), TestGateG13 (1 test), TestMicroModelStochastic (1 test, marked slow)

- `E:\opencell\opencell\solvers\ode.py`
   - JAX/Diffrax ODE solver — `solve_ode()` function
   - Returns ODEResult with .ts and .ys (n_steps, n_species)
   - Key: uses `saveat` parameter for output timepoints, `args` passed to RHS

- `E:\opencell\opencell\solvers\ode_scipy.py`
   - SciPy reference solver — `solve_ode_scipy()` function
   - Returns ScipyODEResult with .ys as **(n_species, n_steps)** — DIFFERENT from JAX!
   - Uses `t_eval` parameter (not `saveat`)

- `E:\opencell\SESSION_CONTEXT.md`
   - Living context document — updated with WSL env, Session 2+3 logs, review findings
   - Must be updated at end of every session

- `E:\opencell\plan.md`
   - Master plan (~1230 lines) — added current status header this session
   - Gate tests defined at lines 301-318 (G1.1-G1.8)

- `E:\opencell\decisions\dec-001-no-langgraph.md`
   - Formal decision rejecting LangGraph with rationale and revisit triggers
   
- `E:\opencell\decisions\dec-002-crosswalk-phase2.md`
   - Formal decision deferring identifier crosswalk to Phase 2
</important_files>

<next_steps>
## Immediate (in progress when compaction hit)
1. **Run gate tests** — `tests/gates/test_micro_model.py` has been fixed for API but NOT YET VERIFIED:
   ```bash
   wsl -d Ubuntu-22.04 -- bash -c "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell && python -m pytest tests/gates/test_micro_model.py -v --tb=short -m 'gate and not slow'"
   ```
2. If tests fail, debug solver API mismatches (especially SciPy ys shape transpose)
3. Once passing, commit micro_model.py + test_micro_model.py + derivation doc

## Remaining Gate Tests (G1.4 through G1.8)
4. **G1.4 Atom balance** — separate test using coupling benchmark (not micro-model, since micro-model has no atom tracking)
5. **G1.5 Unit trace** — feed pint Quantities through full pipeline
6. **G1.6 Reference frame** — CI check for cross-frame reads without conversion
7. **G1.7 PySCeS oracle** — simulate micro-model in PySCeS, compare (need to install PySCeS)
8. **G1.8 Thermodynamic feasibility** — verify flux direction consistent with ΔG

## After Gate Tests Pass
- Commit all gate tests
- Phase 2: Toy cell sub-models (metabolism, transcription, translation)
- Add coupling-artifact sync-interval sweep (from external review)
- Test Docker build end-to-end

## Blocked
- `p1-db-access` — user needs to register BRENDA, configure API keys
- GitHub push — user wants to wait a couple more days
</next_steps>