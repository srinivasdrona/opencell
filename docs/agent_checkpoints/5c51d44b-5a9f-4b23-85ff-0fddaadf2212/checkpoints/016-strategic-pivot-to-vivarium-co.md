<overview>
OpenCell — open-source whole-cell simulation in Python. This session navigated a major strategic pivot from "build sub-models manually" to "port Karr 2012 M. genitalium to Python on vivarium-core, subsystem-by-subsystem, with LLM-assisted methodology as a secondary documented contribution." Four rounds of adversarial critique (three external/user-supplied + one from GPT-5.4 rubber-duck) progressively sharpened the plan, surfacing the central insight that **coupled simulation semantics — not subsystem porting — is the hard problem.** The user's final ask is to integrate this pivot into the original phased plan structure (which was Phase 1 manual model → Phase 2 published-paper sub-models → Phase 3 integration), confirming that the existing first 2 phases are completed work and this is the natural Phase 4+, plus assessment of whether vivarium-core requires restructuring the project layout.
</overview>

<history>
1. User asked which simplest cell, complete simulation status — covered earlier sessions; established Karr 2012 as published WCM; OpenCell project began here.

2. (Many earlier sessions, summarized in prior compactions) — Built coupled Chassagnole+Vilar model, hybrid solver, tau-leap, RNG hygiene, demo, validation_dataset_candidates.md.

3. User pivoted to "prune Karr's M. genitalium to a Core 100" with growth-rate as invariant (start of this session segment).
   - Pushed back: 100 is arbitrary, GSMs lack kinetics, growth-rate alone is weak validation, chassis claims to syn3A overpromise, frozen artefact value of Chassagnole+Vilar.

4. User accepted subsystem approach over gene-count, asked for a survey + scale-up plan.
   - Launched explore agent for source inventory (M. genitalium, E. coli, eukaryote, Python ecosystem). 31-min, 45 tool calls, ~20KB report.
   - Survey saved to `session/files/source_inventory_2026-04-24.md`.
   - **Headline finding: Covert Lab's wcEcoli is already a working Python WCM validated against Chassagnole + Thattai (our same anchors). vivarium-core is the only modular framework matching our "reusable modules" goal. wcEcoli's successor is being ported into the vivarium-collective org.**

5. User asked: "is vivarium-core shared/reusable? what would we achieve?"
   - Inspected vivarium-collective GitHub org (~90 repos, Apache 2.0, PyPI, mature CI). Confirmed wcEcoli successor moving there.

6. User asked deeper question: "what are we trying to do here? be objective."
   - Honest answer: three roles (User of vivarium / Contributor to vivarium / Independent framework). Forced clarification of project identity (Goal X model vs Y research vs Z learning).

7. User asked: "drug discovery? mutation studies? be realistic."
   - Drug discovery = overpromise; honest framing is in silico target prioritisation. Mutation studies (knockout screens, synthetic lethality) = genuinely feasible.

8. User showed first external critique (LLM-generated) arguing JAX/differentiability/GPU as moats.
   - Graded: 1 valid strategic insight, 1 valid gap (data curation), 1 oversold (differentiability is open research), 1 partial (GPU). Pushed back hard on JAX claim — we removed JAX last week.

9. User showed second external critique pivoting to "DX over differentiability + provenance store + reproducibility benchmark."
   - Graded as significant improvement that quietly substitutes science project for tooling project. Recommended: keep model as goal, tooling as means.

10. User showed third critique: Karr is fragile mirage; sociological adoption wall (XKCD 927); plumbing trap; niche-of-niche; vivarium lock-in.
    - Most damaging point: **Covert Lab themselves did not port Karr to Python** — they built wcEcoli for E. coli instead. Acknowledged but user pushed back coherently: "no one funds porting MATLAB→Python; that doesn't mean it's wrong."

11. User clarified actual motivation: deep interest in cell biology, build subsystem-by-subsystem in Python, **long-term goal: use LLMs for real scientific progress, not boilerplate.**
    - Provided honest feasibility assessment: feasible 18-30 months part-time with LLM help, 60-70% probability of meaningful publishable outcome.

12. User: "update the plan, todos, and session_context."
    - Wrote new "Strategic Direction (2026-04-24)" section atop plan.md (both copies).
    - Marked 48 superseded p2-p6/chassagnole todos as `blocked` with reason.
    - Inserted 19 new todos under Phase A/M/L/E/Z structure.
    - Wired dependencies. Added resolution block to validation_dataset_candidates.md.

13. User showed fourth critique (most actionable): build Simulation Diff Tool first, integration debt is real, no-tuning-vs-phenotype-target tension, LLM verification tax.
    - Adopted 5 of 5 actionable items. Added A5 (diff tool) as hard prereq for M-phase. Added project principles. Pushed back on solo-penalty pessimism.

14. User: "now critique with GPT 5.4."
    - Launched rubber-duck task with model=gpt-5.4.
    - **GPT-5.4 surfaced the central blind spot: coupled simulation semantics is the hard problem; M0 vertical slice required before M1.** Plus 5 more substantive findings (semantics contract, invariant verification, performance budget, multi-level diff, L-phase stealing oxygen).

15. User answered the 3 contested questions: (1) no timelines, (2) bounded tuning by independently-verified biological ranges, (3) standalone tooling opportunistic not focal.
    - Applied all 13 critique adoptions to plan.md. Stripped time horizons. Added A6 (semantics contract), A7 (invariant verification), A8 (performance budget), M0 (vertical slice). Restructured A5 as 4-level diff. Tightened A2/A3/A4. Subordinated L-phase. Reframed Chassagnole+Vilar as active coupling torture rigs. Updated all M-phase descriptions with bounded-tuning policy.
    - Final DB: 85 done · 24 pending · 48 blocked.

16. User's final ask (this turn, before compaction):
    - Confirm that prior phased plan completed Phases 1 + 2.
    - Integrate the current pivot into that phased structure for coherence (manual model → published papers → integration was the original arc; new pivot is the next natural stage).
    - Assess whether moving to vivarium-core requires restructuring the project layout, or if existing structure can be retained.
    - **NOT YET ANSWERED — context compaction triggered.**
</history>

<work_done>
Files modified this session:
- `E:\opencell\plan.md` — added Strategic Direction (2026-04-24) section atop, then progressively refined through 4 critique rounds. Now contains: hard-problem framing (coupled semantics), bounded-tuning policy, time horizons explicitly stripped, operational failure branch, 9 risks (integration debt + no-diff-tool + Karr dark matter promoted to top), 6 non-negotiable principles, Phase A (8 todos: A1-A8), Phase M (M0 + M1-M7 with loop-closure principle), Phase L (subordinated as captured-as-byproduct), Phase E, Phase Z, Chassagnole+Vilar promoted from frozen to active coupling torture rigs.
- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md` — synced via Copy-Item after each edit batch.
- `session/files/validation_dataset_candidates.md` — added Resolution (2026-04-24) block at top of pivot section pointing to source survey + plan.

Files created this session:
- `session/files/source_inventory_2026-04-24.md` — copied from `C:\Users\sdrona\AppData\Local\Temp\1777008273134-copilot-tool-output-593o08.txt`. Full GPT-5.4-explore-agent survey: 5 sections (M. genitalium sources, E. coli sources, eukaryotic models, Python ecosystem, recommendations + final checklist). ~20KB.

SQL DB state (`opencell_tasks.db`):
- 85 done · 24 pending · 48 blocked · total 157 todos
- 48 blocked = old `p2-*`, `p3-*`, `p4-*`, `p5-*`, `p6-*`, `chassagnole-*`, `phase2-replan-chassagnole`, `p1-db-access` — marked blocked with description suffix "SUPERSEDED 2026-04-24 pivot: replaced by Phase A/M/L/E/Z ladder on vivarium-core"
- 24 pending under new structure:
  - **Phase A (8)**: a1-vivarium-spike, a2-license-clearance, a3-provenance-store, a4-karr-mat-spike, a5-simulation-diff (4-level), a6-semantics-contract, a7-invariant-verification, a8-performance-budget
  - **Phase M (8)**: m0-vertical-slice (HARD GATE), m1-central-carbon, m2-nucleotides, m3-transcription, m4-translation, m5-replication-cellcycle, m6-regulation, m7-karr-validation
  - **Phase L (4)**: l1-matlab-port-methodology, l2-llm-param-curation, l3-adversarial-critique, l4-methods-paper (gated post-M4)
  - **Phase E (2)**: e1-wcecoli-survey (gated on M7), e2-ecoli-port (gated on E1)
  - **Phase Z (2)**: z1-eukaryote-spike, z2-knockout-screen (gated on M7)
- Dependencies wired: a5→a6, a7→a6, m0→{a1,a5,a7}, m1→m0, M-phase chained, L4→m4, E1→m7, E2→e1, Z2→m7
- Ready-to-start (no pending deps): a1, a2, a3, a6, a8, l1, l2, l3, z1

User's final ask is UNANSWERED:
- [ ] Confirm Phases 1+2 completed in original phased plan
- [ ] Integrate current pivot into the original phased structure (Phase 4+) for narrative coherence
- [ ] Assess vivarium-core impact on project structure (restructure or retain?)
</work_done>

<technical_details>
**The pivot's central insight (from GPT-5.4 rubber-duck):**
The hard problem is **coupled simulation semantics**, not subsystem porting. Every plan element must serve the question "what does it mean for two hybrid whole-cell simulations to be 'the same enough'?" This reframes A5 (diff tool) as downstream of A6 (semantics contract), and M0 (vertical slice with bidirectional coupling) as a hard gate before M1 (central carbon).

**Bounded-tuning policy (final form):**
Biological parameters tunable only within independently-verified biological ranges (BRENDA/SABIO/primary lit). Range must be sourced and recorded in provenance store BEFORE tuning. No range = no tuning. Solver tolerances and numerical step sizes tunable freely. We publish discrepancies where ranges cannot accommodate Karr's values.

**Operational failure branch:**
If v0.9 cannot reach ≥10/28 phenotypes under bounded-tuning, the deliverable becomes the discrepancy analysis itself — publishable negative result.

**Chassagnole+Vilar promotion:**
Was "frozen regression artefact"; now "active coupling torture rigs" — actively used to break A5/A6/A7/M0 before M. genitalium does. Tune the engine until the toy survives, not for biological match.

**Source inventory key facts (from explore agent):**
- Karr 2012 WholeCell: github.com/CovertLab/WholeCell, MIT, MATLAB. Active (Feb 2026). 1000 reactions / 470 genes / 428 metabolites. Binary `.mat` files require scipy.io.loadmat + reverse-engineering (multi-week).
- WholeCellKB: github.com/CovertLab/WholeCellKB, MIT, Django/Python. wholecellkb.stanford.edu live. Better Python-friendly access path.
- iPS189 (Suthers 2009): bigg.ucsd.edu/models/iPS189, SBML, FBA-only (no kinetics). Clean structural scaffold.
- JCVI-syn3A / Lattice Microbes: github.com/Luthey-Schulten-Lab/Lattice_Microbes. Tightly coupled to runtime, license unclear, NOT a portable target.
- wcEcoli: github.com/CovertLab/wcEcoli, "Other" license (verify), Python, ACTIVE Apr 2026. Validated against Chassagnole + Thattai (same anchors as us).
- vivarium-core: Apache 2.0, PyPI install, mature CI (pylint/pytest/mypy/docs), Process/Store/Composite/Topology/Hierarchy abstraction. ~90 repos in vivarium-collective org including vEcoli (wcEcoli successor port).
- COBRApy: GPL-2.0 (copyleft) — avoid for kinetic engine.
- Tellurium/libroadrunner: Apache 2.0 / "Other" — already use libroadrunner.
- No published kinetic eukaryotic WCM exists.

**Critical sequencing (post-GPT-5.4):**
a1, a2, a3 → a4, a6 → a5 (built on Chassagnole+Vilar) → a7 → a8 → m0 (closed-loop vertical slice on Chassagnole+Vilar substrate) → m1+ subsystem extensions (each closing prior loop).

**De-scoped claims (do not revive without evidence):**
- Differentiable JAX/Diffrax engine at WCM scale (open research; we removed JAX last week because numpy was faster at our scale)
- GPU drug screens (workload-dependent; CPU competitive for our hybrid det/stoch)
- Autonomous agent parameter curation (multi-year research; replaced with human-in-loop provenance)
- "Drug discovery" framing (overpromise; in silico target prioritisation is honest)
- Eukaryote completeness (no precedent exists)

**Project principles (non-negotiable, in plan.md):**
1. Bounded-tuning policy
2. Coupled-semantics first (A6 + M0 before subsystems)
3. Loop-closure = subsystem completion
4. Append-only provenance (minimum normalization day one; junk-heap warning)
5. LLM failure modes are first-class outputs
6. Chassagnole+Vilar as coupling torture rigs

**Verification economics rule:** if LLM verification time exceeds 4× creation time, revisit workflow. L1/L2 must track this metric.

**Prior phased plan structure (per user's question, NOT YET CONFIRMED):**
The original plan had Phase 1-6. Phase 1 (gates closed, Thattai approved per checkpoint 007) and Phase 2 (?) appear to be done per user's claim. Phase 3 is where we shipped hybrid solver + first-run demo (checkpoints 014, 015). User's question implies the original arc was: P1 manual model → P2 published-paper sub-models (Chassagnole + Vilar) → P3 integration (coupling + hybrid solver). Current pivot would naturally be Phase 4+ in that arc. Need to verify by reading prior checkpoints.

**Vivarium-core structural impact (unanswered question):**
vivarium-core is `pip install`-able and works alongside any existing Python package layout. Our solvers can be wrapped as Vivarium Processes via adapter modules without restructuring `opencell/` directory. The principle from earlier: "standalone solver modules kept usable independently with optional Vivarium adapters to avoid lock-in." So existing structure can be retained; A1 spike adds a thin `opencell/vivarium/` adapter layer alongside existing modules.

**Environment quirks still active:**
- WSL is execution source of truth (`.venv-wsl`). Windows venv `.venv-opencell` lacks libroadrunner.
- Expected pytest skip count = 5 (Thattai paper-cache only). Any other count = wrong env.
- WSL fs sync delay 5-15s after Windows file create/edit.
- `.gitattributes` enforces LF line endings; without it, WSL-side commits churn massively.
- libroadrunner Linux-only in our stack.
- `np.bool_` not JSON-serializable; wrap with `bool()`.
- BioModels REST blocked (CloudFront 403); use github.com/biomodels mirror.
- PowerShell heredoc breaks on apostrophes — use temp files.
</technical_details>

<important_files>
- `E:\opencell\plan.md` (1450+ lines)
  - Authoritative project plan. Top section is Strategic Direction (2026-04-24) covering: hard problem framing, target, secondary goal, chassis decision, de-scoped claims, time horizons stripped, operational failure branch, 9 risks, 6 non-negotiable principles, Phase A (A1-A8), Phase M (M0 hard gate + M1-M7), Phase L (subordinated), Phase E, Phase Z, Chassagnole+Vilar coupling torture rigs section.
  - Lines 1-150: complete pivot rewrite. Lines 150+: original status section (Hybrid Solver done, Coupled model done, Transcription done) preserved unchanged.
  - **Needs update next session**: integrate pivot into original phased numbering (Phase 4+); answer vivarium-core structural impact question.

- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\plan.md`
  - Mirror of E:\opencell\plan.md. Synced via Copy-Item after every edit batch. Same content.

- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\source_inventory_2026-04-24.md`
  - Full explore-agent survey of M. genitalium / E. coli / eukaryotic / Python ecosystem sources. ~20KB. Authoritative reference for source/license decisions. Has Section 5 recommendations + final checklist.

- `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\validation_dataset_candidates.md`
  - Original 4-candidate dataset triage (Chassagnole/Bettenbrock/Taniguchi/Karr). Now has Resolution (2026-04-24) block at top of pivot section pointing to plan.md and source_inventory.

- `E:\opencell\opencell_tasks.db`
  - SQLite todo DB. 85 done · 24 pending · 48 blocked. New structure: a1-a8, m0-m7, l1-l4, e1-e2, z1-z2 with dependencies wired. Old p2-p6/chassagnole todos blocked with SUPERSEDED reason.

- `E:\opencell\opencell\solvers\hybrid.py`
  - Hybrid det/stoch solver. Single-pass LSODA + numpy Generator. ~200 lines. One-way coupling assumption hard-coded — NOT valid for two-way coupling that M0 will require. Will need refactor when M0 starts.

- `E:\opencell\opencell\models\coupled.py`
  - Chassagnole + Vilar coupled model. NOW REFRAMED as active coupling torture rig (not frozen). Will be the substrate for A5/A6/A7/M0 stress testing.

- `E:\opencell\.github\copilot-instructions.md`
  - Has WSL-only execution rule + Stochastic RNG Discipline rule. Future addition needed: adversarial-critique workflow (L3 todo).

- `E:\opencell\.gitattributes`
  - LF line ending enforcement. Critical for WSL/Windows interop.

- Session checkpoints/index.md (15 prior checkpoints in session folder)
  - Need to read 007 (Phase 1 gates closed) and any Phase 2/3 checkpoints to answer user's "did we complete Phases 1+2?" question accurately.
</important_files>

<next_steps>
**User's final ask is unanswered — must resume here next session:**

1. **Confirm completion status of Phases 1+2 in the original phased plan.**
   - Read prior checkpoints, especially 007 (Phase 1 gates closed, Thattai approved), and look for Phase 2 completion markers.
   - Read original Phase 1-6 structure from plan.md (lines past ~150, if still present, or from checkpoint 001).
   - Verify whether the user's mental model "P1 manual model done → P2 published-paper sub-models done → P3 integration done → P4 = current pivot" matches the actual plan.

2. **Integrate the pivot into the original phased numbering for narrative coherence.**
   - User's preference: "the previous plan in phases was more coherent."
   - Likely solution: rename current Phase A → Phase 4 (Vivarium foundations + semantics contract), Phase M → Phase 5 (M. genitalium subsystems on vivarium), Phase L → captured-as-byproduct (no phase number), Phase E → Phase 6 (E. coli stretch), Phase Z → Phase 7 (aspirational).
   - Update plan.md heading and SQL todo IDs accordingly (a1→p4-vivarium-spike, m0→p5-vertical-slice, etc.) — OR keep a/m/l/e/z IDs but document phase mapping.
   - Update validation_dataset_candidates.md and any other artefacts referencing the pivot phase letters.

3. **Answer the vivarium-core structural impact question.**
   - Short answer (already established in plan): existing `opencell/` structure can be retained. Add thin `opencell/vivarium/` adapter layer. Solvers wrapped as Processes via adapters; standalone modules remain usable. No directory restructure required.
   - Long answer: outline the adapter pattern concretely — `opencell/vivarium/processes/metabolism.py`, `opencell/vivarium/processes/transcription.py`, etc., wrapping existing `opencell/models/*` modules. Topology files in `opencell/vivarium/topologies/`. This answers A1 (vivarium-spike) before we start it.

**After answering those three:**
- User signaled "before we start" — implying ready to begin execution after these clarifications.
- Critical-path next concrete sequence (post-clarification): a3 (provenance store v0.1) → a4 (karr .mat extraction spike) → a6 (semantics contract) → a5 (4-level diff tool) → a7 (invariant verification) → m0 (closed-loop vertical slice on Chassagnole+Vilar) → m1.
- Ready-to-start with no pending deps: a1, a2, a3, a6, a8 (foundations); l1, l2, l3 (lightweight methodology logging); z1 (aspirational, defer).
- Most leverage first action: **a1 (vivarium spike)** — confirms chassis viability; OR **a3 (provenance store)** which gates a4 (karr extraction spike).

**Open questions for user:**
- Once Phase numbering integrated, do we rename SQL todo IDs (a1 → p4-1) or keep alphabetic with phase mapping table?
- For A1 vivarium spike, target: reproduce first_run_demo through Vivarium, OR something smaller (just wrap one solver as a Process)?
</next_steps>