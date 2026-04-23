# OpenCell — Session Context (for AI continuity)

> This file captures context that lives in conversation memory but not in plan.md.
> Read this at the start of every new session.
> **UPDATE this file at the end of every session** — it is a living document.

## Session Update Policy
At the end of each session (or when the user says goodbye / wraps up), update this file with:
1. What changed this session (decisions, files modified, todos completed)
2. Any new user preferences or corrections discovered
3. Updated tool/access status (DB access, installs, API keys)
4. Current blockers and what's ready next
5. Anything learned that would be lost without writing it down

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

## User Profile
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
- `E:\opencell\plan.md` — Master plan (~1220 lines)
- `E:\opencell\opencell_tasks.db` — Persistent task DB (101 todos, 127 deps, 66 findings)
- `E:\opencell\SESSION_CONTEXT.md` — This file

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
