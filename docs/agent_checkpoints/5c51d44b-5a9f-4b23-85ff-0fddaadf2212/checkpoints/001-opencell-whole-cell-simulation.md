<overview>
The user wants to build "OpenCell" — an open-source whole-cell computational simulation of a living cell in Python, starting with a toy cell (~50 genes), scaling to Mycoplasma genitalium (~525 genes). The project includes a novel AI agent orchestration system with multi-model expert panels for biological decisions, local/cloud hybrid model routing, and formal data contracts. We completed extensive planning and brainstorming across biology, software architecture, AI agent design, hardware assessment, and cost optimization. No implementation has started yet — the user decided to sleep on the plan before beginning Phase 1.
</overview>

<history>
1. User asked about the simplest living cell and whether complete simulations exist
   - Researched via web search: Mycoplasma genitalium (~525 genes), Karr et al. 2012 whole-cell model
   - Identified key bottlenecks: data gaps, compute cost, multi-scale integration, validation, scaling, software engineering
   - User chose "just answer in chat" rather than a formal plan or software project

2. User proposed collaborating on building a complete cell simulation
   - Clarified preferences through multiple ask_user interactions:
     - Language: Python (recommended for ecosystem)
     - Organism: Start with toy model (~50 genes), then scale to M. genitalium
     - Approach: Hybrid (Karr-style architecture, modernized with JAX/ML)
   - Discussed why no successor to Karr 2012 exists after 14 years (data problems, funding mismatch, academic incentives)
   - Discussed what Copilot can automate (~60-70% of software engineering)

3. User asked about multi-agent architecture and expert panels
   - Designed 6 agent roles: Biology Researcher, Data Curator, Math Modeler, Software Engineer, Validator, Literature Agent
   - Identified Biology Researcher and Math Modeler as strongest candidates for expert panels
   - Proposed multi-LLM strategy with different models for different roles

4. User asked about cost optimization with multiple LLMs including Gemini, Grok
   - Designed 4-tier cost strategy: Critical ($$$) → Implementation ($$) → Routine ($) → Bulk (¢)
   - Estimated total project LLM cost: ~$1,200-2,500 all-cloud, or ~$300-500 hybrid
   - Identified Gemini's 1M context and Grok's web search as unique advantages

5. User asked about running everything on local models (Gemma 4 31B etc.)
   - Assessed local-only vs hybrid tradeoffs
   - Recommended hybrid: 80% local for routine work, cloud only for expert panels
   - Estimated costs: $50-100 all-local, $300-500 hybrid (recommended)

6. User asked to check machine specs for local LLM viability
   - Ran systeminfo (after resolving pwsh installation issue): Intel i7-10700, 64GB RAM, Intel UHD 630 (no dedicated GPU), 930GB disk on E: drive
   - Assessed: 64GB RAM is excellent for loading models; no GPU means CPU-only inference at ~5-12 tok/s for ≤14B models
   - Recommended models: Phi-4 14B, Qwen 3 14B, Gemma 4 12B via Ollama

7. User asked to update plan with local/cloud model strategy
   - Added Hardware Profile section, Tiered Model Routing, Model-to-Role Assignment, Local Infrastructure (Ollama), Expert Panel Architecture, Cost Breakdown to plan.md

8. User raised 4 unresolved architecture questions (agent communication, conflict resolution, data contracts, custom agent system)
   - Agent communication: Dual-format specs — markdown (rationale) + SBML Level 3 (machine-readable)
   - Conflict resolution: Biology-first 4-level escalation ladder (math adapts → biology approves → empirical test → human decides)
   - Data contracts: JSON Schema (CI-enforced), reuse existing standards (SBML, SED-ML, SBOL)
   - Orchestrator: Two-layer architecture — copilot-instructions.md (declarative) + pipeline.py (imperative)
   - Added all to plan with 7 new todos, updated project structure

9. User asked about yeast cell simulation
   - Researched: No complete yeast whole-cell simulation exists. Only partial models (Yeast9 GEM, MIL-CELL, scYeast)
   - Yeast is ~500-1000x more complex than M. genitalium (eukaryote, 6000 genes, 7+ organelles)
   - Confirmed M. genitalium is the right first target

10. User noticed E. coli model exists (Covert Lab wcEcoli) and asked about implementing it
    - Reviewed CovertLab/WholeCellEcoliRelease README from GitHub
    - Recommended Option B: use as validation benchmark, not fork
    - Proposed as stretch goal (Phase 7+), not replacing current roadmap

11. User asked to move all work to E: drive and add stretch goals
    - Created E:\opencell\ directory
    - Added 4 stretch goals: A) E. coli, B) Yeast, C) Agent orchestration framework, D) Drug & evolution simulation
    - Copied plan to E:\opencell\plan.md (primary location)

12. User asked about drug interaction simulation capabilities
    - Detailed what the model enables: drug target identification, resistance mutation scanning, fitness cost analysis, evolutionary trajectory prediction, combination therapy design
    - User chose to add as Stretch Goal D (spin-off project applicable to M. genitalium and E. coli)

13. User asked for final housekeeping check before starting
    - Pre-flight check: Python 3.14 + 3.12 available, Git 2.53, Node 22.20, Ollama NOT installed
    - User noted Python 3.12 is available; instructed to use named venvs with 3.12
    - User decided to sleep on the plan before starting implementation

14. User asked for cross-model plan review and book recommendations
    - Launched two background rubber-duck agents: one via Claude Opus, one via GPT-5.2
    - GPT-5.2 review completed with detailed findings (see technical details below)
    - Claude Opus review still running when conversation was paused
    - Provided curated reading list (biology, scientific computing, software engineering books + key papers)
</history>

<work_done>
Files created:
- E:\opencell\plan.md — The master plan document (~700+ lines, ~35KB). Contains: vision, project structure, 6 implementation phases with 53 tasks, hardware profile, AI agent strategy (tiered routing, expert panels, cost breakdown), agent communication specs, conflict resolution protocol, data contracts, orchestrator architecture, technical decisions table, biological sub-models summary, success criteria, and 4 stretch goals.

- C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md — Session copy (synced with E: drive version)

SQL state:
- 53 todos in `todos` table across 6 phases (14 in P1, 10 in P2, 7 in P3, 6 in P4, 8 in P5, 8 in P6)
- 68 dependencies in `todo_deps` table
- All todos status: 'pending' (none started)
- First ready todo: `p1-repo-setup` (only task with no dependencies)

Work completed:
- [x] Research on simplest cells, existing simulations, bottlenecks
- [x] Technology stack decisions (Python, JAX, COBRApy, SBML, etc.)
- [x] Multi-agent architecture design (6 roles, 4 tiers, expert panels)
- [x] Hardware assessment (i7-10700, 64GB RAM, no GPU, 930GB disk)
- [x] Cost optimization strategy ($310-625 hybrid local/cloud)
- [x] Agent communication protocol (dual-format: markdown + SBML)
- [x] Conflict resolution protocol (biology-first, 4-level ladder)
- [x] Data contracts design (JSON Schema, CI-enforced)
- [x] Orchestrator architecture (copilot-instructions.md + pipeline.py)
- [x] Stretch goals defined (E. coli, Yeast, Agent framework, Drug simulation)
- [x] Pre-flight environment check
- [x] GPT-5.2 plan review completed
- [ ] Claude Opus plan review (agent "plan-critique" was still running)
- [ ] Implementation not started

No implementation code has been written yet.
</work_done>

<technical_details>
### Key Architecture Decisions
- **Language**: Python 3.12 (user confirmed 3.12 available; 3.14 too new for JAX/COBRApy wheels)
- **Venvs**: Must be named when created (user requirement)
- **GPU compute**: JAX in CPU mode (no dedicated GPU); Colab/cloud GPU as fallback for heavy runs
- **ODE solver**: Diffrax (JAX-based) + SciPy fallback; must handle stiff systems
- **Stochastic solver**: Custom tau-leaping for low-copy-number molecules
- **Hybrid solver**: Mixed deterministic-stochastic for coupled sub-models
- **Data format**: YAML for parameters (human-readable), HDF5 for simulation output, SBML Level 3 for model exchange
- **Packaging**: pyproject.toml (PEP 621), Apache 2.0 license
- **CI/CD**: GitHub Actions (free for open source)
- **Docs**: MkDocs + Material theme

### AI Agent Architecture
- **6 agent roles**: Biology Researcher, Data Curator, Math Modeler, Software Engineer, Validator, Literature Agent
- **4 tiers**: Critical (cloud panels: Opus+GPT-5+Grok), Standard (local writer + cloud reviewer), Routine (local only), Bulk (local only)
- **Local models via Ollama**: Phi-4 14B (~8GB), Qwen 3 14B (~8GB), Gemma 4 12B (~7GB) — total ~30GB disk
- **Expert panels**: Multi-model debate → moderator synthesis → cached decision (never re-debated)
- **Cross-model review**: Writer and reviewer always use different LLMs to catch model-specific blind spots
- **Estimated cost**: $310-625 total for entire project

### Agent Communication & Data Contracts
- **Dual-format specs**: Markdown (WHY: rationale) + SBML (WHAT: machine-readable model)
- **Standards**: SBML Level 3, SED-ML, JSON Schema for internal YAML files
- **Validation pipeline**: contracts.py validates → CI blocks malformed data on PRs
- **Conflict resolution**: Biology wins → Math adapts solver → Biology approves approximation → Empirical test → Human decides

### GPT-5.2 Review Key Findings (completed)
1. **Reproducibility is underspecified** — need run manifests, lockfiles, deterministic mode, seed discipline, AI decision logging
2. **JAX defaults to float32** — must explicitly use float64 for stiff ODE stability
3. **RNG discipline** — need centralized PRNGKey schedule, not naive seed use
4. **Scalability risk** — must use data-oriented design (arrays/pytrees, sparse stoichiometry), not Python object graphs
5. **Testing gaps** — need property-based testing (Hypothesis), fuzz testing for SBML/JSON parsers, golden run regression tests, benchmark tracking (asv)
6. **Checkpoint/restart** — blocking for long simulations; store state + RNG keys + solver internals
7. **Schema versioning** — need migration strategy and version governance
8. **API stability policy** — need SemVer, changelog (towncrier), deprecation timeline
9. **Top 5 risks**: numerical instability, reproducibility debt, architecture not data-oriented, scope creep, data provenance/licensing
10. **Recommended Phase 1 additions**: reproducible run manifest, contract fuzz/property tests, benchmark + validation harness

### Claude Opus Review (agent "plan-critique")
- Was still running when user ended conversation. Should be read with `read_agent agent_id="plan-critique"` at start of next session.

### Environment Details
- **OS**: Windows 11 Enterprise Insider Preview (Build 26220)
- **Machine**: Lenovo 11EVS09B00
- **CPU**: Intel i7-10700 (8C/16T @ 2.9GHz)
- **RAM**: 64GB DDR4
- **GPU**: Intel UHD 630 (integrated only, 1GB shared)
- **Disk**: E: drive ~930GB free
- **Python**: 3.14.0 (primary) + 3.12 available (use this for project)
- **Git**: 2.53.0
- **Node**: 22.20.0
- **Ollama**: NOT installed yet (needed by Phase 2)
- **pwsh**: Installed during session (was missing initially, now works)
- **Domain**: fareast.corp.microsoft.com (Microsoft corporate machine)

### Gotchas
- PowerShell 6+ (pwsh) was not initially installed — all powershell tool calls failed until user installed it manually
- Python 3.14 is very new; scientific packages (JAX, COBRApy) may not have wheels — use 3.12 instead
- E: drive is the working drive; C: drive session state folder is auto-managed by Copilot CLI
- The `opencell` folder already existed at E:\opencell from a previous state but was empty except for plan.md
</technical_details>

<important_files>
- E:\opencell\plan.md
   - The master plan document for the entire project (~700 lines, ~35KB)
   - Created and iteratively updated throughout the session
   - Contains: vision, project structure tree, 6 phases (53 tasks), hardware profile, AI agent strategy, agent communication protocol, conflict resolution, data contracts with JSON Schema examples, orchestrator architecture with code samples, technical decisions table, biological sub-models summary, success criteria, and 4 stretch goals
   - Key sections: Project Structure (line ~25), Implementation Phases (line ~174), Hardware Profile (line ~259), AI Agent Strategy (line ~271), Agent Communication (line ~387), Conflict Resolution (line ~425), Data Contracts (line ~462), Orchestrator (line ~539), Stretch Goals (line ~653)

- C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md
   - Session copy of the plan, synced from E:\opencell\plan.md
   - Copilot CLI reads this automatically; must stay in sync with E: drive version
</important_files>

<next_steps>
Immediate (before starting implementation):
1. **Read the Claude Opus review** — agent "plan-critique" may have completed. Run `read_agent agent_id="plan-critique"` to retrieve findings.
2. **Synthesize both reviews** — combine GPT-5.2 and Opus findings, present key gaps to user, update plan.md accordingly.
3. **Address GPT-5.2's recommended Phase 1 additions**: reproducible run manifests, property-based testing, benchmark harness — these should be added as new todos.

When user says "start":
4. **Begin p1-repo-setup** — scaffold E:\opencell\ with full project structure, pyproject.toml, CI/CD, README, LICENSE, etc.
5. **Create Python 3.12 venv** — named venv (user requirement), install core dependencies
6. **Install Ollama** — needed by Phase 2 for local model agents, but can be done during Phase 1

Key blockers/questions:
- User wants to review the plan overnight before implementation begins
- Ollama not yet installed (not blocking Phase 1 but needed by Phase 2)
- Need to verify JAX/Diffrax/COBRApy compatibility with Python 3.12
- Claude Opus review results may surface additional plan changes
</next_steps>