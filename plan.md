# OpenCell: Open-Source Whole-Cell Simulation

## Strategic Direction (2026-04-24, four rounds of adversarial critique converged)

**The hard problem (single most important framing, GPT-5.4 critique):**
The hard part of this project is **coupled simulation semantics** — defining
what it means for two hybrid whole-cell simulations to be "the same enough."
Subsystem porting is downstream of this. Every other plan element exists to
serve the semantics question.

**Target:** Validated open M. genitalium whole-cell model in Python on
`vivarium-core`, reproducing ≥10 of Karr 2012's 28 published phenotypes
within his error bars *under our bounded-tuning policy* (see Principles).
A *modern, accessible, reproducible* Python implementation of a model that
has been locked in MATLAB for over a decade.

**Secondary goal (the methodology contribution, captured-as-byproduct):**
LLM-assisted scientific software construction as a documented workflow.
**Not a parallel program** — emerges from M-phase work, written up after
M4 minimum. Treating L as co-equal to M is self-sabotage for solo effort.

**Chassis decision: build on `vivarium-core` (Apache 2.0, PyPI, ~90 active
ecosystem repos, wcEcoli's successor moves there).** Our solvers become
Vivarium Processes. We do *not* build a competing framework. Standalone
solver modules are kept usable independently with optional Vivarium adapters
to avoid lock-in.

**Explicitly de-scoped (claims that did not survive critique):**
- "Differentiable JAX/Diffrax engine" — at WCM scale this is open research,
  not engineering. We removed JAX from the codebase last week (numpy faster
  at our scale).
- "GPU-vectorised drug screens" — workload-dependent, doesn't survive our
  profiling. CPU ensembles are competitive for hybrid det/stoch.
- "Autonomous agent that reconciles parameter contradictions" — multi-year
  research problem. Replaced with human-in-the-loop provenance tooling.
- "Drug discovery" — overpromise. *In silico target prioritisation* is the
  honest framing. We are not a pharma pipeline.
- "First/full eukaryote WCM" — no published precedent exists; no candidate
  organism has the required curated parameters. Aspirational only.

**Time horizons:** explicitly not tracked. The project takes the time it
takes. Milestones are gated on quality, not calendar. Visible artefacts
every few iterations are the rhythm; cadence is whatever sustains
momentum without forcing premature closure.

**Operational failure branch:** if v0.9 cannot reach ≥10/28 phenotypes
under the bounded-tuning policy, the deliverable becomes the discrepancy
analysis itself: where Karr's model is reproducible, where it isn't, what
that implies about the original. This is a publishable negative result,
not a failure of the project.

**Key risks (in priority order):**
1. **Integration debt.** Subsystems built in isolation will not survive
   coupling. Mitigation: each M-phase subsystem must close a feedback loop
   with prior subsystems; "done" means the loop closes, not that the
   subsystem runs alone.
2. **No diff tool = debugging nightmare.** When Python output diverges
   from Karr's MATLAB, we need an automated species-by-species,
   timestep-by-timestep comparator. Mitigation: A5 builds this *before*
   any subsystem port begins.
3. **Karr "dark matter".** Original MATLAB has hand-tuned fudge factors
   not in the published papers. A clean port may fail to reproduce
   phenotypes for this reason alone. Mitigation: see Project Principle
   on Karr discrepancies (below). Do not tune to match.
4. Attrition (>70% failure rate for ambitious solo projects). Mitigation:
   ship visible artefact every 2-3 months. First-run demo is the pattern.
5. Scope creep. Mitigation: write *out-of-scope* list per subsystem.
6. Validation gap (no wet-lab partner). Mitigation: validate against Karr's
   *published* predictions; mark unvalidated outputs explicitly.
7. Karr code interpretation. Mitigation: contact wholecellteam@stanford
   when ambiguous; the original authors are reachable.
8. Parameter explosion. Mitigation: provenance store from day one; never
   trust LLM-generated parameters without source-doc cross-check.
9. **LLM as crutch / verification tax.** If we spend more time auditing
   LLM output than creating, the LLM provides no leverage. Mitigation:
   L1/L2 explicitly track verification time and hallucination rate as
   metrics. If verification ratio exceeds 4:1 we revisit the workflow.

**Project principles (non-negotiable):**
- **Bounded-tuning policy.** Biological parameters may only be tuned
  within independently-verified biological ranges (BRENDA/SABIO ranges,
  primary literature, ranges from independent measurements in related
  organisms). The range itself must be sourced and recorded in the
  provenance store *before* any tuning occurs. No range = no tuning.
  Solver tolerances and numerical step sizes are tunable freely. We
  publish the discrepancy where ranges cannot accommodate Karr's values.
- **Coupled-semantics first.** A6 (semantics contract) and M0 (vertical
  slice) precede subsystem buildout. Component accumulation without
  proven coupling is anti-pattern.
- **Loop-closure is the definition of subsystem completion.** A subsystem
  that runs alone but breaks when coupled is not done.
- **Append-only provenance from day one.** Minimum normalization (units,
  IDs, source type, scope, lineage) required at insert; higher-level
  schema may evolve. "Schema deferred" wholesale is how junk heaps form.
- **LLM failure modes are first-class outputs.** Any L-track writeup
  must document where LLMs failed, not just where they succeeded.
- **Chassagnole + Vilar are coupling torture rigs**, not frozen reference
  fixtures. Use them to break A5/A6/A7/M0 *before* M. genitalium does.

### Phase Narrative (continuous arc, pre- and post-pivot)

The project arc was always: validate manual sub-models against published
oracles → integrate them → harden the engine for a real cell → port
M. genitalium → publish. The 2026-04-24 pivot **does not change the arc**;
it sharpens what Phases 4-6 actually require, having learned from Phases
1-3 what coupled simulation actually demands.

| Phase | Theme | Status |
|---|---|---|
| 1 | Foundation: solvers, units, oracles, gates, parameter-verification | ✅ Closed |
| 2 | Toy sub-models against published papers (Chassagnole 2002, Vilar 2002, Thattai-Oudenaarden) | ✅ Closed |
| 3 | Integration: coupled cell + hybrid det/stoch solver + first-run demo | ✅ Closed |
| **4** | **Engine hardening on vivarium-core (a1–a8 + m0 + m0.5): semantics contract, multi-level diff, invariants, performance budget, closed-loop vertical slice, multi-Process scaling profiler** | ✅ Closed (2026-04-24) |
| **5** | **M. genitalium subsystems extending the closed loop (M0-A backlog + M1–M7)** | 🟢 Ready to begin |
| **6** | **Validation, methodology writeup, stretch goals (E. coli, knockout screens)** | ⏸ Gated on Phase 5 |

Old Phase 4-6 todos (`p4-*`, `p5-*`, `p6-*`) from the pre-pivot plan are
**superseded** by the Phase 4-6 work below — marked `blocked` in the DB
with reason "superseded by 2026-04-24 pivot". Kept for traceability.

Todo IDs use short codes (`a1`, `m0`, etc.) for convenience. Mapping:
**Phase 4 = a1–a8 + m0 + m0.5 (all done)**, **Phase 5 = m0a backlog + m1–m7**, **Phase 6 = l1–l4 + e1–e2 + z1–z2**.

### Project structure impact of vivarium-core

**The existing `opencell/` package layout stays. Vivarium-core is additive,
not a rewrite.**

What we have works as-is:
- `opencell/solvers/` (LSODA, tau-leap, hybrid) — keep, expose as
  Vivarium Processes via thin adapters.
- `opencell/models/` (sbml_model, chassagnole, transcription, coupled) —
  keep as standalone biology; wrap in Processes for composition.
- `opencell/extraction/`, `opencell/curation/`, `opencell/manifest/` —
  feed the A3 provenance store; structure unchanged.
- `tests/` (unit, integration, gates, scientific, validation,
  differential, property) — all keep applying. Add a `tests/vivarium/`
  for Process-level tests.
- `scripts/` — paper reproducibility scripts unchanged. New
  `scripts/vivarium_demo.py` will replicate the first-run demo through
  Vivarium during A1.

What gets added:
- `opencell/vivarium/` — Process adapters wrapping our solvers and
  models. Each adapter is ~50 lines (port specs + `next_update` shim).
- `opencell/diff/` — multi-level diff tool (A5).
- `opencell/invariants/` — Karr-independent physics checks (A7).
- `opencell/provenance/` — append-only parameter store (A3).
- `data/semantics/` — A6 semantics contract documents.

What we explicitly **do not** restructure:
- The `models` ↔ `solvers` ↔ `extraction` separation is sound; vivarium
  Processes sit *on top*, they don't replace internal layering.
- No mass file moves. No package renames. No import-path changes.
- Standalone use (without Vivarium) remains a first-class entry point —
  protects against vendor lock-in.

The optionality is concrete: if Vivarium-core's API churns badly or the
project moves to process-bigraph (v2.0), we swap `opencell/vivarium/`
adapters; everything else is untouched.

### Phase 4 — Engine hardening on vivarium-core (active)

**Phase 4 progress (2026-04-24)**

| Todo | Status | Deliverables |
|---|---|---|
| **A1 Vivarium-core spike** | ✅ done | `opencell/vivarium/{processes,composite}.py`, `scripts/vivarium_demo.py`, `tests/vivarium/test_vivarium_smoke.py` (8/8), artefacts `vivarium_demo.{png,json}` + `vivarium_vs_hybrid_diff.json`, findings note `docs/phase4/A1_vivarium_spike_findings.md`. **Headline:** Vivarium hosts our biology cleanly; 73× wall-time overhead is dominated by per-macro-step LSODA restart, classified as M0 design question, not Vivarium tax. |
| **A2 License clearance** | ✅ done | `LICENSES.md`. Critical-path stack (vivarium-core Apache 2.0, libroadrunner Apache 2.0, numpy/scipy/pint/pypdf BSD-3) all CLEAR. COBRApy explicitly avoided for kinetic core (GPL-2.0). Karr WholeCell + WholeCellKB confirmed MIT, ready for A4 ingestion. |
| **A3 Provenance store v0.1** | ✅ done | `opencell/provenance/store.py` + `__init__.py`. Append-only JSONL, content-addressed event_ids, supersedes chain, bounded-tuning policy enforced at the API level (record_tuned validates range). 9/9 tests including idempotency, no-deletion-API, history-preservation. |
| **A6 Semantics contract v0.1** | ✅ done | `data/semantics/A6_semantics_contract.md`. Codifies state ontology (5 variable kinds), updater rules, time-unit conventions, the **f_met-lag rule** (Vivarium 1-step lag vs hybrid_run 0-step lag), the **LSODA-restart rule** (~0.1 mM drift per 8h), RNG discipline, 4-level diff equivalence classes with default tolerances. |
| **A8 Performance budget v0.1** | ✅ done | `docs/phase4/A8_performance_budget.md`. Reference-workload baseline measured (`hybrid_run` 0.45 s/realisation; Vivarium 33 s/realisation = 73×). Per-phase budgets through M7. M0-A/B/C decision menu for the LSODA-restart cost. |
| **A4 Karr .mat extraction spike** | ✅ done | `scripts/karr_mat_spike.py`, `data/karr_fixtures/MetabolicReaction.mat` (sha256 `817585b3…`), `artifacts/karr_a4_walk.json`, `artifacts/karr_a4_provenance.jsonl`, findings `docs/phase4/A4_karr_extraction_spike.md`. **Headline:** mechanics pass, semantics fail. The `.mat` alone yields opaque uint32 leaves (first leaf = `3707764736`, almost certainly a MATLAB handle, not biology). M-phase ingestion path must read `.m` source first, `.mat` second. |
| **A5 Simulation Diff Tool (4-level)** | ✅ done | `opencell/diff/multi_level.py` + `__init__.py`. Levels 1-4 per A6 §5: structural (paths/lengths/kinds), invariants (per-engine via A7), trajectory L_inf abs+rel, phenotype scalar. Reports findings at every level — never short-circuits. 18/18 tests including integration test that asserts the tool *correctly surfaces* the A6 §2.3 f_met-lag disagreement. |
| **A7 Invariant verification module** | ✅ done | `opencell/invariants/core.py` + `__init__.py`. Four checks (non-negativity, bounded fractions, mass conservation, count integrality) + `InvariantSuite` composer. 9/9 tests. Default `abs_tol=1e-9` tolerates floating noise without masking real violations. Consumed by A5 Level 2. |
| **M0 Closed-loop vertical slice** | ✅ done | `scripts/m0_vertical_slice.py`, `artifacts/M0_vertical_slice.json`, findings `docs/phase4/M0_vertical_slice_findings.md`. **Headlines:** (1) 4/4 (horizon × macro_dt) configurations pass diff Level 1-4 with A7 invariants intact on both engines. (2) **M0-C adopted**: larger macro_dt cuts overhead 25.7×→8.3× at 1h horizon — Vivarium tax is per-macro-step LSODA spin-up, controllable. (3) f_met 1-step lag formalised as known Vivarium parallel-scheduler property under M0 tolerance. **Phase 5 entry conditions all met.** |
| **M0.5 Multi-Process scaling profiler** | ✅ done | `scripts/m05_multiproc_scaling.py`, `artifacts/M05_multiproc_scaling.json`, findings `docs/phase4/M05_multiproc_scaling.md`. **Crystal-clear headline:** Vivarium scheduler is fine (noop b=0.75 sub-linear). **LSODA spin-up is the wall** (metab b=0.99 linear, 15.6 s/Process regardless of N). Karr-scale single-realisation ≈ 3.3 h per 8h sim — viable on M0-C. Karr-scale ensembles (≥100 realisations) ≈ 14 days — **not viable without M0-A persistent-LSODA, now tracked as Phase 5 backlog item m0a-persist-lsoda.** |

**Phase 4 closed.** Test count: 410 → 437 (+27). All Phase 5 entry conditions documented and met.
- A1: Vivarium-core spike — install, wrap existing hybrid solver as a
  Process, reproduce the first-run demo through Vivarium.
- A2: License clearance for *critical-path only* — vivarium-core
  (Apache 2.0 ✓), libroadrunner, BiGG iPS189. wcEcoli/syn3A licenses
  deferred to E1/Z prereqs (not on critical path now).
- A3: Provenance store v0.1 — append-only event log; minimum normalization
  on insert (units, IDs, source type/DOI, scope, transformation lineage);
  higher-level schema deferred but not absent. SBML/SED-ML identifier
  alignment where applicable. The "Git-for-Parameters" foundation.
- A4: Karr `.mat` extraction spike — open one file, extract one
  parameter table into A3 with full provenance. Outcome includes a
  *meaning recovery* assessment, not just successful array extraction
  ("we got the numbers but don't know what units/conditions" = fail).
- A5: **Multi-level Simulation Diff Tool** — naive trajectory diffing
  fails on hybrid stochastic systems. Build four diff levels:
    1. **State-mapping diff** — species names/units/topology equivalence
    2. **Invariant diff** — conservation, non-negativity, accounting
    3. **Event-log diff** — discrete events (division, replication init)
    4. **Observable/phenotype diff** — Karr's 28 measurables
  Hard prereq for M-phase. Built and stress-tested on Chassagnole+Vilar.
- A6: **Simulation-semantics contract** (NEW, GPT-5.4 surfaced) —
  explicit document defining state ontology, units, scheduler/update
  ordering, RNG control, division/partitioning rules, IC generation,
  phenotype evaluation windows. Without this A5 diffs noise. Drafted
  before A5 implementation.
- A7: **Invariant verification module** (NEW) — Karr-independent physics
  checks: mass balance, charge/redox balance where applicable,
  non-negativity, volume/concentration consistency, transcription/
  translation bookkeeping. Runs on every coupled simulation; CI-gated.
- A8: **Performance budget** (NEW) — wall-clock and memory targets per
  M-phase. Profiling gates per phase. Karr MATLAB takes ~10h per cell
  cycle; we should target ≤ that and aim better. CI-scale short
  integration benchmarks track regression.

### Phase 5 — M. genitalium subsystems extending the closed loop (gated on Phase 4)

**Phase 5 entry status (2026-04-25):** A4-followthrough closed.
**M-phase ingestion path is de-risked**: Karr's `data/parameters.json`
→ `data/karr_fixtures/karr_parameters_unit_map.yaml` (unit recovery
from `.m` source comments) → `ProvenanceStore.record_measured`. Proven
end-to-end with 18 real parameters in `artifacts/karr_a4f_provenance.jsonl`,
including a mutual-consistency cross-check
(`ln(2)/MetabolicReaction.meanInitialGrowthRate = 32400.7s` vs
`Time.cellCycleLength = 32400.0s`, 0.00% rel err). `.mat` test fixtures
are MATLAB object dumps (state snapshots, not parameter tables) and are
not the ingestion source. `data/knowledgeBase.mat` deferred until an
M-phase subsystem demands a parameter not in `parameters.json`. See
`docs/phase4/A4F_karr_m_source_followthrough.md`.

**M0: Closed-loop vertical slice (NEW, hard gate before M1).**
Smallest possible bidirectionally coupled loop on vivarium-core:
tiny metabolic module (≤5 reactions) ↔ transcription of a couple of its
enzymes ↔ translation ↔ resource consumption feedback both ways.
Invariant checks enabled. Observable diff against an analytic or
hand-computed reference. Not a subsystem — a proof that the engine
carries the biology under coupling. **No M1+ work begins until M0 holds
under stress on Chassagnole+Vilar substrate.**

After M0, subsystems extend the closed loop — they are not parallel
tracks. Each "completes" only when invariants hold and the prior loop
still closes. Validation oracles below are the *additional* checks.

**Backlog (gated on need, not on M1):**
- ~~**M0-A Persistent LSODA Process mixin** (`m0a-persist-lsoda`)~~ ✅
  **done (2026-04-25)**. `opencell/vivarium/persist.py::PersistentMetabolismProcess`.
  Holds `scipy.integrate.ode(rhs).set_integrator('lsoda')` across
  `next_update` calls; advances at absolute `t` incrementally; resyncs
  only on detected external store writes. **Headline:** Vivarium
  overhead at 1h × 60s drops 28.5× → 1.58× (18× speedup). At 600s × 10s
  the persistent path is at parity with the `hybrid_run` baseline (1.03×).
  4 tests: gold-standard match to single-shot full-horizon LSODA
  (max rel diff < 1e-4 across 18 species, zero resyncs), resync
  correctness, persistence-vs-restart correctness, speedup sanity guard.
  A6 LSODA-restart rule revised: applies only at resync boundaries.
  See `docs/phase4/M0A_persistent_lsoda.md`. Ensembles and sweeps are
  no longer gated.

**Subsystems (extend the closed loop one at a time):**
- M1: Central carbon + energy charge (~20-30 enzymes from iPS189 + Karr
  kinetics). Validation: ATP/ADP ratio matches measured M. genitalium values.
  **🟡 FBA core green + Karr comparison published 2026-04-25** —
  `opencell/m1/central_carbon.py` runs pFBA on a 42-rxn central-carbon
  subnet (12/12 tests pass, no-synthesis guard intact).  `scripts/m1_validate.py`
  runs pFBA on the FULL 350-reaction iPS189 with Karr's parameters.json
  bounds + WCKB Misc.parameters growth-rate target (0.077 h⁻¹) and writes
  `artifacts/M1_validation.json` + `docs/phase5/M1_validation_report.md`
  with a 3-mode comparison.  Honest finding: under Karr's literal bounds
  raw iPS189 cannot grow (Mode A μ = 0); with irreversibility relaxed it
  grows freely (Mode B μ ≈ 542).  Of 4 Karr published targets, **0
  independent quantities agree** (NGAM "match" is tautological — set as
  hard `lb`).  The gap is the curated transporter/reversibility fixes
  Karr's group encoded in their MAT files (serialized MATLAB class
  instances; require MATLAB stack + CPLEX 12.2 to *run* but only MATLAB
  itself to *extract*).
  - **2026-04-24 evening pivot**: dropped the iPS189-self-augmentation
    path and the iJW145-substitution path (M.pneumoniae, not M.gen) per
    user "no synthesis" rule.  New approach: extract Karr's fitted MAT
    files via free MATLAB Online (no CPLEX needed for extraction, only
    for simulation).  Authored `scripts/matlab/extract_karr_mats.m`
    + `scripts/matlab/README.md` runbook.  Smoke-tested end-to-end:
    MATLAB → flat MAT v7 → `scipy.io.loadmat` → field access works.
  - **2026-04-25 00:00 breakthrough**: user installed MATLAB R2026a
    locally on `E:\MATLAB\` (trial license, no CPLEX).  Generic
    extractor hung on Simulation_fitted.mat (handle-graph cycles).
    Pivoted to `scripts/matlab/extract_karr_targeted.m` — pulls only
    named properties (28 processes' fitted constants, Metabolism's
    24 named FBA properties + 174-property manifest, 16 states),
    bounded depth.  Runs in ~3min; outputs `sim_fitted_targeted.mat`
    (362 KB) + `knowledgeBase_targeted.mat` (12 MB), both
    scipy-readable.  Local-only typo fix needed: `import import` →
    `import` on line 134 of `FtsZPolymerization.m` (R2026a stricter).
  - **2026-04-25 morning structural finding (gap closed)**: Investigation
    of Mode D's 7× gap exposed a deeper truth.  Karr's stored runtime
    solution (`state.MetabolicReaction.dump.fluxs`, 645-vector with
    253 nonzero entries, range [-1e6, 1e6]) **violates his own snapshot
    `fbaEnzymeBounds` in 34 of 504 reactions, by up to 100×**.  This
    proves the snapshot enzyme bounds are POST-step (free-enzyme count
    after substrate binding tightened it), NOT the bounds Karr used
    during the LP solve.  Including snapshot enzyme bounds → μ ~135×
    too low; dropping them and using BIG=1e3 (Karr's natural per-cell-
    per-sec ceiling) → **μ = 0.039 /h vs Karr stored 0.076 /h, ratio
    0.51× (within 2×)**.  This is the best a static snapshot can do.
  - **Mode E added**: reads Karr's stored runtime values directly from
    the MAT (`growth = 2.119e-5 /s = 0.076 /h`, `growth0 = 2.139e-5 /s`,
    `meanInitialGrowthRate = 2.139e-5 /s`, `doublingTime = 47186 s`,
    full 645-element flux vector).  This is the **gold-standard
    validation oracle** for downstream M1 module comparisons.
  - **Implication for M1 validation strategy**: stop deriving μ from
    static-snapshot FBA — structurally bounded.  Instead, validate
    downstream M1 modules against Karr's stored per-reaction fluxes.
    Tracked as `m1-per-reaction-oracle` todo.  Schema_v4 published
    with 5-mode comparison; 453/453 tests still green.
  - **2026-04-25 afternoon — M1 pivoted to Karr-native (iPS189 dropped)**:
    Recognised that `opencell/m1/central_carbon.py` was still built on
    iPS189 (Suthers 2009 SBML) with Karr params bolted on top — a
    months-old compromise from before MAT extraction worked.  With
    Karr's full FBA matrices now in hand, that compromise is moot and
    actively obstructive (forced an iPS189→Karr-WCM-ID mapping table
    to even *attempt* per-reaction validation).  Built:
    `scripts/karr_native_ingest_m1.py` extracts the FBA snapshot
    (S 376×504, RHS, lb/ub, full obj, enz_bounds, fluxs[645], all
    index maps, 645 reaction WCM IDs, 585 substrate WCM IDs, 104
    enzyme WCM IDs, per-FBA-column WCM IDs for the 336 metabolic-
    conversion cols) into committed fixture
    `data/karr_fixtures/karr_native_m1.{json,npz}` (~123 kB total).
    `opencell/m1/karr_metabolism.py` is the new Karr-native model
    (drops snapshot enzyme bounds, BIG=1e3, full Karr objective with
    biomass +1000 + 35 parsimony penalties).
  - **`m1-karr-native-oracle` PASSED**: predicted vs stored per-reaction
    median |log2 ratio| = **0.96** over 196 comparable reactions
    (threshold <1.0).  Biomass 0.0392 /h vs stored 0.0763 /h = 0.514×
    (the structural snapshot ceiling, identical to Mode D).  No ID
    mapping table required — Karr-vs-Karr.  Per-reaction oracle is now
    a 7-test pytest module (`tests/m1/test_karr_metabolism.py`) +
    `artifacts/M1_per_reaction_oracle.json` + 25-row top-disagreement
    table in `docs/phase5/M1_per_reaction_oracle.md`.
  - **Strategic effect**: M1 now lives in the same ID space as Karr's
    other 27 processes, unblocking the vivarium dynamic-loop chassis
    (`m1-vivarium-process` next).  iPS189 module retained for a
    separate cleanup commit (`m1-cleanup-ips189`) to keep diffs
    reviewable.  460 tests (453 + 7 new) pass.
  - **`m1-vivarium-process` PASSED**: `opencell/vivarium/karr_m1.py`
    wraps M1 as a 1-second-tick `KarrMetabolismProcess` plus a
    `build_karr_m1_engine` harness.  Ports: writes `metabolic_reaction.fluxs`
    (645-dict by WCM ID), `metabolic_reaction.growth_per_{s,h}`; reads
    `substrates` (585-dict by WCM ID, placeholder).  100-step in-vacuo
    run completes; biomass stable across ticks (snapshot FBA is
    time-invariant); all 645 fluxes finite; predicted biomass matches
    standalone solver to relative tol 1e-9.  Substrate-delta writeback
    is deliberately deferred (needs fba_sub_idx_substrates -> 1686 count
    mapping; M2/integrator territory).  464/464 tests pass.
  - **Chassis is healthy**: M2..M7 can now plug into the same Vivarium
    Engine using shared `metabolic_reaction.fluxs`, `substrates`,
    `enzymes`, `rna`, `protein` stores.  Next: start M2 nucleotide
    biosynthesis as the second Process on this chassis.
- M2: Nucleotide biosynthesis (~15 enzymes). Validation: NTP pool sizes vs
  Karr's reported steady-state.
- M3: Transcription of metabolic enzymes (RNAP + σ-factor + the genes
  from M1+M2). Validation: mRNA abundance distribution.
- M4: Translation (ribosome + tRNA synthetases + elongation, abstracted).
  Closes most important loop: enzymes are *produced*, not parameter-fixed.
  Validation: protein copies + emergent growth rate.
- M5: DNA replication + cell cycle (DnaA, polymerase, division trigger).
  Validation: doubling time ≈ 12h for M. genitalium.
- M6: Regulation (TFs, attenuation). Validation: induction/repression
  responses match Karr's predictions.
- M7: Karr-equivalent v1.0 — union spans Karr's 28 quantitative
  phenotypes. Validation: replicate ≥10 of them within Karr's error bars.

### Phase 6 — Validation, methodology writeup, stretch goals (gated on Phase 5)

**6a. LLM-for-science methodology (captured-as-byproduct of Phase 5,
NOT a parallel program)**
- L1: Real-time methods notes during M-phase — prompting patterns, failure
  modes, verification time, hallucination rate. Lightweight log, not
  separate research.
- L2: LLM-assisted parameter curation captured incrementally as A3/M-phase
  parameters land. Same provenance store; metric tags on entries.
- L3: Adversarial critique workflow already documented in
  copilot-instructions.md; refine as we use it.
- L4: Methods paper — drafted *after* M4 minimum. No standalone L work
  before M4. Must document failures explicitly.

**6b. E. coli stretch (after M7)**
- E1: wcEcoli ingestion — parameter survey, license, ingestion adapter.
- E2: E. coli sub-systems on the same chassis.

**6c. Aspirational / deferred**
- Z1: Eukaryote spike (Yeast central carbon + cell cycle, demonstration).
- Z2: In silico knockout/synthetic-lethality screen on M. genitalium v1.0.

### Coupling torture rigs (active testbeds, not frozen)

- `opencell/models/coupled.py` (Chassagnole + Vilar) — **promoted** from
  frozen-regression to *active coupling stress substrate*. Used to break
  A5 (multi-level diff), A6 (semantics contract), A7 (invariants), and
  M0 (closed-loop vertical slice) **before** M. genitalium does. Cheapest
  place to discover engine bugs. Not living biology; do not tune for
  biological match — tune the engine until the toy survives.
- `scripts/demo_first_run.py` — onboarding demo. Same status: regression
  artefact, not science.

---

## Current Status (2026-05-25 ~13:45 IST, **SPRINT 0 LANDED ON BRANCHES; AUDIT-AND-RATCHET PHASE BEGINS**)

### TL;DR
After Day 10 wrap (Bug 5 + Bug 6 landed on `main` at `40f96c5`), three research agents (vEcoli infra, wcEcoli methodology, WCM validation literature 2018-2026) converged on five durable Covert Lab validation patterns. The literature also confirmed nobody in the field has a MATLAB→Python differential test harness — our per-process `*_flat.mat` fixtures uniquely enable this.

**Sprint 0 complete** (three branches, ready to merge):
| Branch | SHA | What it ships |
|---|---|---|
| `sprint0/predicates` | `0757402` | `opencell/validation/predicates.py` — vEcoli's `data_predicates` ported verbatim (10 public predicate functions + tests) |
| `sprint0/allocator-guards` | `38fe273` | `ASSERT_POSITIVE_COUNTS` + `NegativeCountsError` in `KarrAllocationStep` (3 checkpoints; would have caught Bug 1, Bug 2 at first tick) |
| `sprint0/replay-harness` | `1b79452` | `opencell/validation/replay.py` — generic solver-replay harness over `data/karr_fixtures/per_process/*_flat.mat` + smoke test |

These now form the foundation for the **audit-and-ratchet phase** (decision `swarm-audit-before-track-a`, 2026-05-25).

### Audit-and-ratchet phase plan

```
Sprint 0 (DONE)
   ├ predicates.py    ← vEcoli pattern
   ├ allocator guards ← wcEcoli pattern (3-checkpoint negative-count)
   └ replay harness   ← wcEcoli pattern (solver-replay differential)
        │
        ▼
[merge sprint0 trio → main]
        │
        ▼
Swarm pilot — Class A: 28 per-process auditors (findings-only, parallel batches)
   each agent produces:
   (1) findings.json     — diagnostic findings
   (2) test_<p>_biology_fires.py — invariants via simulate_process
   (3) test_<p>_matches_karr.py  — solver-replay against fixture
   (4) activity_monitor.json — observables for global expected_active_set
        │
        ▼
Reducer (1 agent)
   produces:
   - swarm_report.md
   - expected_active_set.json
   - bugs_to_fix.md
   - class_b_scope_proposal.md   ← scope informed by Class A findings
        │
        ▼
GPT-5.5 critique gate  ← per decision swarm-pilot-cross-model-critique-gate
   sharp 3-Q prompt: structural flaws / wrong-redundant seams / symptoms of deeper bugs
        │
        ▼
Operator + Copilot review session  → locks Class B scope
        │
        ▼
Class B fleet (TBD count, scope from review) → Reducer round 2 → final swarm_report
        │
        ▼
Triage gate (operator + Copilot)  → fix-fleet queue
        │
        ▼
Track A (TX/TL allocator enrollment, the B1 fix)
   benefits inherited:  guards + replay + prioritized bug context
```

Single mega-PR for swarm Class A test files + report — 28 PRs would be process overhead with no review value.

### Sprint 0 strategic context

Convergent finding across all three Phase 0 research agents: the most portable patterns are (1) `ASSERT_POSITIVE_COUNTS` runtime guards at allocator boundaries, (2) `data_predicates` invariant library, (3) per-process biology-firing tests using `simulate_process`, (4) solver replay for differential validation, (5) `find_limiting_metabolites` + `expected_set` for "beautiful corpse" detection. Sprint 0 ships patterns 1, 2, 4 as foundation; the swarm pilot's 28 class-A agents will author patterns 3 and 5 across all 28 processes.

Decisions recorded today: `swarm-audit-before-track-a`, `swarm-pilot-cross-model-critique-gate` (both cross-cutting, 2026-05-25).

---

## Prior Status (2026-05-25 ~00:30 IST, **BUG 5 + BUG 6 LANDED ON MAIN; TRACK A IS THE B1 BLOCKER**)

### TL;DR
All four Bug 5 commits (protein maturation pipeline) and all three Bug 6
commits (FBA writeback to shared substrate pool) are merged into `main` at
`40f96c5`. Regression on `main`: **338 passed, 1 failed (B1, known-pending),
2 xfailed in 17m30s.**

Bug 5 closed the protein maturation chain: Translation → unprocessed →
PP I (processed) → PP II (unfolded) → Karr step 7 (mature). Bug 6 closed
the shared-substrate writeback: M1's LP solution now writes signed deltas
back to 368 mapped cytosol rows with per-tick M1/M2v3/M3v3 ATP attribution.

Bug 5+6 alone do **not** fix B1 (substrate-negativity). The Stage 2
diagnostic proves it: M1's LP net flux for ATP/CTP/GTP/UTP is ~0; the
drain comes from TX (M2v3) and TL (M3v3) writing `substrates` deltas
directly, unconstrained, because they are **not enrolled in the allocator**.
This is **Track A** — the next sprint.

### Commits landed today (2026-05-24)
| Bug | SHA | Effect |
|---|---|---|
| 5A | `bbfab3c` | Zero-init unprocessed/unfolded protein pools |
| 5B | `a2da0eb` | PP I writes `processed_counts`; PP II reads it, writes `unfolded_counts`; Karr step 7 non-lipo pass-through |
| 5C | `6e4f0d1` | Translation routes to `unprocessed_counts` (closes the pipeline) |
| 5D | `50ec5fc` | Canary `test_chassis_v6_protein_maturation_pipeline.py` (2 PASS + 1 XFAIL pending Bug 6) |
| 6b | `b69e7ca` | Stoichiometric demand-pool headroom caps in M1 LP bounds (preventive; `clamped_reactions=0` until Track A) |
| 6a S1 | `c697075` | LP writeback for 24 demand keys, positive only |
| 6a S2 | `ecde4e4` | Full signed writeback for 368 mapped cytosol rows + ATP attribution diagnostic; NTP non-negativity converted to diagnostic-only prints |
| 6a fix | `be2d401` | Stage 1 canary relaxed for Stage 2 signed-writeback contract |
| merge | `40f96c5` | `agent/bug6` → `main` (no-ff) |

### Process wins this sprint
- **Parallel codex fleet pattern**: independent worktrees, each with an
  async pwsh PID watcher (`Get-Process -Id $pid; sleep 60; loop`) that
  fires a `system_notification` on codex exit. Replaces the
  poll-and-idle anti-pattern that had been silently stretching wall-clock.
- **Tier-1 must include `tests/integration/`** for any commit touching
  `ports_schema` or `_dynamic_update` keys. Caught chassis_v4 staleness
  after 5B; would have caught Stage 1 canary breakage after Stage 2 if
  the rule had been in the Stage 2 prompt.
- **Codex `git push` retry hang remediation**: if `git log --oneline -1`
  on the worktree shows the expected commit exists, kill the codex pwsh
  by PID. Local push is non-essential for feature worktrees.
- **`codex exec resume --last` does not inherit `--dangerously-bypass`**.
  Must use fresh `codex exec` with full flags each turn; rely on
  `SESSION_CONTEXT.md` for continuity. Patch queued for the
  `delegate-to-codex` skill.

### Known-pending: Track A (next sprint)
**Minimum scope**: enroll TX (`karr_transcription_v3.py`, M2v3) and TL
(`karr_translation_v3.py`, M3v3) in the allocator. Scale each process's
activity by `allocated / demanded` NTP ratio instead of writing
unbounded substrate deltas.

**Acceptance criteria**:
1. `test_b1_substrate_sanity_no_negative_core_substrates` passes.
2. The NTP non-negativity asserts in `tests/integration/test_bug6a_stage2_canary.py`
   lines ~94-135 (currently diagnostic prints) re-hardened to `assert`.
3. Bug 6b's `clamped_reactions` becomes non-zero under tight NTP supply
   (proves the cap actually engages).

**Estimate**: 600-1000 LOC, 2-3 codex turns, 1-2h wall-clock. Risk:
TX/TL inner loops likely assume unlimited NTP supply; Karr-spec
attention required on which sub-reactions consume which NTPs.

### Next-session queue
1. Track A minimum (TX + TL allocator enrollment).
2. Bug 8 (TL energy accounting — ATP/GTP coupling per Karr spec) —
   becomes easier once Track A constrains TL by NTP availability.
3. Bug 9 (protein decay coupling) — same pattern as TX/TL.
4. Push `main` to `origin/main` (currently 87 commits ahead).
5. Patch `delegate-to-codex` skill (resume flag inheritance, git-push
   hang, parallel-fleet pattern, Tier-1-includes-integration rule).
6. First honest 28-KP Karr scorecard after Track A lands.

### Carried over from prior sprint (still true)
- 28-KP scorecard infrastructure already exists at
  `data/karr_fixtures/karr_phenotype_targets.json` +
  `opencell/validation/karr_reference_values.py` +
  `tests/phaseE/test_karr_phenotypes.py`. Inventory in
  `REFERENCE_INFRASTRUCTURE_INVENTORY.md`.
- Local `cell_cycle_trajectory.mat` is compartment-unresolvable; grade
  against published Karr 2012 figure-level targets, not local MAT.
- Karr-cycle wall-time on current code: ~25 ticks/sec single-core
  (~30 min for 45k ticks). Expect 3-8× slowdown once all 28 processes
  are fully integrated at Karr granularity (1.5-3h projected).

---

## Prior Status (2026-05-24 ~08:55, **THREE BUGS ROOT-CAUSED, ONE IS OUR REGRESSION, TEST-FIRST FIX SEQUENCE**)

### TL;DR
The 4-seed × 32,400t ensemble surfaced (not fixed) **three serious bugs** the 1000t canary missed:
1. **TX/TL run at timestep=0** — `karr_transcription.csv` and `karr_translation.csv` have ZERO rows across 32,400 ticks. Root cause: `_mark_instance_as_step(processes[new_key])` at `karr_composite.py:1873`, introduced 7 hours before discovery in commit `b51819d` ("Step 6: align v6 consumer step identity"). **This is our own self-regression** — we diagnosed `is_step==True → timestep=0` in `artifacts/cascade_fix_v5/step1_verdict.md` and then introduced it in the very next commit.
2. **Substrate init = 1.0** — `_M1_SUBSTRATE_DEFAULT = 1.0` at line 96 + `_updater: accumulate` on substrates store ⇒ ATP/AD/URA start at value `1`, then accumulate deltas. AD ends at -29,999,999 (1000/tick drain × 30k ticks).
3. **Static metabolism** — `dynamic_bounds: bool = False` at line 1831. Metabolism emits constant flux every tick, identical across all 4 seeds to 10 decimal places.

Conservation holding at 3.6e-9 was metabolism-only-in-a-closed-loop math, not biology. The cascade-fix work passed a math check, not a biology check.

### What's running now (4 Codex sessions, 2026-05-24 08:55)
| Session | PID | Worktree | Task |
|---|---|---|---|
| **Biology-firing test author** | 18832 | `biology-firing-test` | Author `test_chassis_v6_biology_firing.py` — 6 assertions across central dogma / substrate sanity / metabolism dynamics. Must FAIL on current HEAD as proof it's a valid canary. |
| **Bug 1 constraint analysis** | 20808 | `bug1-constraint` | Read-only: what test/flow-dep motivated `_mark_instance_as_step`? What breaks if we remove it? Rate fix candidates. |
| **Bug 2 init pipeline trace** | 16000 | `bug2-init-trace` | Read-only: where SHOULD Karr initial substrate counts come from? Is there a disconnected init path? `_updater: accumulate` semantics audit. |
| **Bug 3 dynamic FBA feasibility** | 4608 | `bug3-fba-feasibility` | Read-only: is `_dynamic_update` implemented + tested? Can we just flip the flag? Risk matrix. |

Expected: ~8 min for test author, ~10-15 min for the three investigations.

### Fix sequence (decided 2026-05-24 08:42, replaces all prior cascade-fix sequencing)
**Front-load investment to raise per-fix confidence from ~30% to ~70%:**
1. **Biology-firing test** authored + verified to FAIL on current HEAD. (in flight)
2. **Three read-only investigations** complete with file:line citations. (in flight)
3. **Bug 1 fix** with corrected understanding of flow-dep constraint, validated by biology test going green on TX/TL assertions. NEVER batch with bugs 2/3.
4. **Bug 2 fix** with init pipeline corrected, validated by substrate-sanity assertions going green.
5. **Bug 3 fix** only if Q2 in `STATUS_bug3_fba_feasibility.md` says dynamic path is real; otherwise file as separate workstream.
6. **Then** re-run 32,400t ensemble against the 28-KP scorecard.

### Why the cascade-fix conservation check was misleading
- Metabolism in static mode + TX/TL at dt=0 + substrate accumulate semantics = a closed deterministic ledger that trivially balances.
- The 1000t canary only checked substrate-cascade math, not "is biology firing".
- V4 lesson reinforced: **always verify Codex metrics against raw CSV.** Three diagnostic Codex sessions returned correct ROOT CAUSE lines; raw-CSV verification confirmed them in 5 min.

### Reference data verdict (from karr-triage)
- Local `cell_cycle_trajectory.mat` is real 324-snapshot series but **compartment-unresolvable** (no metaboliteIDs lookup).
- Per-process `*_100ticks.mat` are 100-tick slices, not full-cycle.
- Verdict: `local-data-insufficient` → grade against published Karr 2012 figure-level targets, not local MAT.
- But this is moot until bugs are fixed.

---

## Prior Status (2026-05-24 ~05:25, ENSEMBLE RUNNING + REFERENCE INFRASTRUCTURE FOUND)

### What's running right now (5 parallel Codex sessions)
| Session | PID | Worktree | Status |
|---|---|---|---|
| **Ensemble seed=42** | 21384 | `phase-2-fix` | Running 32,400-tick |
| **Ensemble seed=43** | 8236 | `run-seed-43` | Running 32,400-tick |
| **Ensemble seed=44** | 22272 | `run-seed-44` | Running 32,400-tick |
| **Ensemble seed=45** | 22152 | `run-seed-45` | Running 32,400-tick |
| **Karr-triage** | 7772 | `karr-triage` | Investigating static-trajectory anomaly |

Expected wall-clock: 9-16 hours for ensemble (CPU contention with 4 parallel runs).

### Critical finding: reference infrastructure already exists (Copilot search, 05:23)
The PASS_CRITERIA_32400t.md draft (18 criteria) was reinventing what we already have:
- **`data/karr_fixtures/karr_phenotype_targets.json`** — **28-KP scorecard with tolerances** (KP01-KP28).
- **`opencell/validation/karr_reference_values.py`** — populated `KARR_REFERENCE_VALUES` dict for all 28 KPs.
- **`opencell/validation/trajectory_compare.py`** + **`karr_trajectory.py`** — comparison tooling already built.
- **`tests/phaseE/test_karr_phenotypes.py`** — phenotype tests likely already wired.
- **`data/karr_fixtures/per_process/*_flat.mat`** — 44 per-process flat dumps (CellMass 1MB, Metabolism 0.6MB, Translation 0.55MB, etc.) — likely the REAL per-tick trajectory data, not the static `cell_cycle_trajectory.mat`.
- **`data/phase_e/v6_trajectory_32400s.pkl`** + `_post_alloc.pkl` — previous 32,400-tick OpenCell runs (pre-cascade-fix; useful for delta).

Documented in `E:\opencell\REFERENCE_INFRASTRUCTURE_INVENTORY.md`. The grading prompt (`PROMPT_grade_32400t.md`) has been rewritten to use the 28-KP scorecard, not the reinvented 18 criteria.

### Earlier reference-extraction (Karr-reference Codex, completed 05:14)
- Verdict: `partial-with-gaps`. 36 quantity CSVs at `E:\opencell-worktrees\karr-reference\data\reference\`.
- **Caveat**: the extracted trajectories show near-static values (ATP 46→1, mass +0.28%, no division). This is either bad aggregation or wrong source file. Karr-triage is investigating.

### Sequence & Gates (revised after finding existing infrastructure)
1. ⏳ Ensemble runs complete (4 seeds) — wall-clock ~9-16hr.
2. ⏳ Karr-triage completes → decide whether `cell_cycle_trajectory.mat` is salvageable or use `per_process/*_flat.mat`.
3. **GATE 1 (coverage)**: confirm KP01-KP28 are reachable from our ensemble outputs.
4. **GATE 2 (pre-flight grading)**: launch grading Codex against existing 28-KP scorecard + any new per-tick refs from triage.
5. **GATE 3 (interpretation)** — based on ensemble scorecard:
   - PASS (≥21/28): ship the result. Refactor A becomes v1.1 hygiene.
   - PARTIAL with conservation FAILs: Path A justified by data → refactor → re-run.
   - PARTIAL with biology FAILs in B/D-tier: real biology gap. Different work.
   - FAIL across tiers: post-mortem before more work.
6. Possibly: refactor A → re-run ensemble → re-grade.

### Hardcoding audit (2026-05-24, in response to user question)
- ❌ No `clip`/`clamp`/floor on substrate counts in production code.
- ❌ No "if negative → small positive" anywhere in simulation path.
- ⚠️ `max(0.0, allocated.get(...))` patterns in consumer processes are defensive clamps on **allocator grants** (no-op if allocator is sane).
- ⚠️ **Drainer whitelist IS a thumb on the scale for diagnostics** (not for biology): could let a real failure slip past unflagged at tick 18,000+. Path A is the real fix.
- ⚠️ Regression-test threshold `cum_store_delta < -100 over 100t` could mask a slow drain.
- ⚠️ Old PASS_CRITERIA bands (±20% / ±50%) superseded by the 28-KP scorecard's per-KP tolerances.

### Worktrees & branches
| Worktree | Branch | HEAD | State |
|---|---|---|---|
| `E:\opencell-worktrees\substrate-cascade-fix` | `agent/substrate-cascade-fix` | `f13d517` | Cascade fix validated |
| `E:\opencell-worktrees\phase-2-fix` | `agent/phase-2-fix` | `4c2c389` | Seed=42 running |
| `E:\opencell-worktrees\run-seed-43` | `agent/run-seed-43` | `fecd178` | Seed=43 running |
| `E:\opencell-worktrees\run-seed-44` | `agent/run-seed-44` | `6001e97` | Seed=44 running |
| `E:\opencell-worktrees\run-seed-45` | `agent/run-seed-45` | `99cb880` | Seed=45 running |
| `E:\opencell-worktrees\karr-reference` | `agent/karr-reference` | `faaa4f1` | Partial extraction done |
| `E:\opencell-worktrees\karr-triage` | `agent/karr-triage` | `9240cdb` | Investigating static-trajectory anomaly |

### Risks still open
- 4 parallel CPU-bound runs may extend wall-clock to 16hr+ from baseline ~9hr.
- `cell_cycle_trajectory.mat` may be unsalvageable; per_process/*_flat.mat extraction needed.
- Drainer whitelist may quietly hide a substrate's biological role at full cycle scale.
- Karr supplements (`.xls`) on disk are anti-bot HTML placeholders, not real data.

---

## Prior status (2026-05-24 ~04:50, PASS-CRITERIA PIVOT — cascade fixed, now benchmarking before claiming victory)

### Pivot rationale (the soul-searching moment, 2026-05-24)
After 10 days of plumbing (cascade fix v5, phase-2 rebase, drain triage, Phase-C whitelist) we asked: *if biology holds at 32,400t, does that mean anything?* Honest answer: **no, not without comparison to Karr 2012's published trajectories.** "ATP growing at 1397/tick" sounds great until you ask "is that the right number?" Decision: extract Karr reference trajectories + define quantitative pass criteria BEFORE the 32,400-tick run, so the run produces a scorecard, not a vibe.

### What's done (cascade fix arc, 2026-05-23 → 05-24)
- ✅ **Cascade fix v5** — V4 root cause was an import-path divergence (sys.path bug, `diagnose_substrate_leak.py` was importing from main repo not worktree). Raw CSV verified: 100t ATP cum drift = -1, AAs perfectly conserved.
- ✅ **Phase-2 combined rebased on cascade-fix** (HEAD `58bfe21`): 60/60 tests, `|unattributed_delta|` ~1e-8, ATP grows ~1397/tick from metabolism production (verified in raw CSV, not a clamp).
- ✅ **Drain triage**: 14 negative-drain substrates characterized. 6 stoichiometric (H/PI/ADP/GDP — expected energy cycle). 8 M1-internal (AD, NH3, URA, SNGLYP, LIPOYLLYS, pTHR, pSER, THY, GN, AHCYS — owned by `karr_metabolism`, drain at steady ~1000/tick from M1 sinks with no replenisher in chassis).
- ✅ **Phase-C whitelist** (HEAD `b9de5a9`): `opencell/vivarium/known_metabolite_drainers.py` + regression test `test_chassis_v6_substrate_drainers.py`. **DIAGNOSTIC-ONLY** — NOT imported by simulation code. Verdict: `ready-for-32400t`.

### Hardcoding audit (2026-05-24, in response to user question)
- ❌ No `clip`/`clamp`/floor on substrate counts in production code.
- ❌ No "if negative → small positive" anywhere in simulation path.
- ⚠️ `max(0.0, allocated.get(...))` patterns in consumer processes are defensive clamps on **allocator grants** (allocations can't be negative). No-op if allocator is sane. Doesn't manufacture biology.
- ⚠️ **Drainer whitelist IS a thumb on the scale for diagnostics** (not for biology): if a whitelisted substrate crashes to zero at tick 18,000 and breaks downstream biology, our regression test won't flag it. Path A (store-semantics refactor) is the real fix; whitelist is triage so we can benchmark today.
- ⚠️ Regression-test threshold `cum_store_delta < -100 over 100t` could mask a real-biology substrate draining at -99/100t.
- ⚠️ PASS_CRITERIA bands (±20% PASS, ±50% PARTIAL) are wide; Karr-ref extraction will let us tighten to ±1σ of Karr's own variance.

### In flight (2026-05-24 04:49)
- 🟡 **Karr-reference Codex** (PID 20556, branch `agent/karr-reference`): extracting trajectories from local `E:\opencell\data\m1_sources\karr_native\cell_cycle_trajectory.mat` (100MB, MATLAB v7.3 HDF5, ~325 snapshots over 32,400 ticks). Output: per-quantity CSVs at `data/reference/karr_2012_<q>.csv` + manifest + overview PNG + STATUS. (V1 of this Codex wasted cycles trying to scrape simtk.org; killed and relaunched with local-data prompt.)
- 📄 **PASS_CRITERIA_32400t.md** drafted at `E:\opencell\PASS_CRITERIA_32400t.md`: 18 criteria across 6 tiers (A. cell growth, B. energy, C. replication, D. translation, E. conservation, F. performance). 3-tier scoring (PASS/PARTIAL/FAIL). OVERALL PASS = ≥14/18 PASS AND zero FAIL in A1/A2/E3. Numerical bands pending Karr-ref extraction.

### Next (sequenced)
1. ⏳ Karr-ref Codex completes → review STATUS, tighten PASS_CRITERIA bands to ±1σ Karr.
2. 🔜 Launch 32,400-tick run Codex on `agent/phase-2-fix` HEAD `b9de5a9`.
3. 🔜 Quantitative grading Codex parses CSV + Karr ref → scorecard → verdict.

### Risks still open
- Karr tick = 1s; some of our processes step at 2s. Time-alignment needed before grading.
- Karr `snapshots` group structure unknown (`#refs#`-indirect); Codex must explore.
- 32,400-tick run is ~9 hours wall-clock in diagnostic mode. May need lighter diagnostic.
- Drainer whitelist may quietly hide one substrate's biological role; Path A still owed.

### Worktrees & branches
| Worktree | Branch | HEAD | State |
|---|---|---|---|
| `E:\opencell-worktrees\substrate-cascade-fix` | `agent/substrate-cascade-fix` | `f13d517` | Cascade fix validated |
| `E:\opencell-worktrees\phase-2-fix` | `agent/phase-2-fix` | `b9de5a9` | Phase-C done, ready-for-32400t |
| `E:\opencell-worktrees\karr-reference` | `agent/karr-reference` | (Codex active) | Extracting reference trajectories |

---

## Prior Status (2026-05-24 01:21 IST, hyp-validation done, fix-did-not-execute in flight)

### Hypothesis validation results (PID 20388, completed 01:20)

- **H1 REFUTED** — drift is monotonic (-437.5/tick for ATP, every tick) NOT a tick-1 cliff. Init at 1.0 is additive only.
- **H2 REFUTED** — substrate store has 805 keys, all 585 expected M1 wids present at tick 0.
- **H5 REFUTED** — no `set` updater on shared substrates port.
- **H7 CONFIRMED** — chassis_v6 has **29 processes, not 28**. Extra: `karr_transcriptional_regulation`.
- **H8 REFUTED** — wid naming consistent across modules.

**Smoking gun in the data**: deltas are CONSTANT per tick (-437.5 ATP/tick at tick 1, tick 2, tick 5, ... tick 100). The consumer is not even partially throttled by allocation. Full unmodified consumption every tick. The fix is being structurally bypassed at runtime even though tests pass.

### fix-did-not-execute results (01:21 IST)

- **C1 REFUTED** — imports do resolve to the correct worktree
- **C2 CONFIRMED** — `proc.parameters["write_substrate_deltas"] = False` has NO runtime effect (vivarium Process freezes parameters post-init)
- **C3 CONFIRMED** — 29 processes vs 28 (extra: `karr_transcriptional_regulation`)
- **C4 CONFIRMED** — `karr_transcription`/`karr_translation` flow deps = `None`; they do NOT depend on `karr_allocation_step`

### Phase-3 drain triage complete (03:36 IST)

Codex (HEAD `df9428b`, STATUS at `STATUS_phase3_drain_triage.md`) characterized the 14 drainers:

**Resolution of -1M mystery**: NOT a floor clamp, NOT a one-shot bug. It's a steady **-1000/tick** M1 metabolic sink (AD `TX_AD ~ -999.6`, NH3 `NH3eq = -1000`, URA `DeoD8 = -1000`). Initial pool was `1.0` placeholder, not `1e6`. So `-1M` = -1000/tick × 1000 ticks. Coincidence.

**All 14 drains**: 100% owned by `karr_metabolism` (with +24 H from protein_modification — negligible). Conservation perfect for every one.

**Classification**:
- 6 STOICHIOMETRIC (energy/redox cycle expected): H, PI, ADP, GDP (mirror ATP/GTP production)
- 8 UNKNOWN (steady metabolic sinks, no replenisher in shared store): AD, NH3, URA, SNGLYP, LIPOYLLYS, pTHR, pSER, THY, GN, AHCYS

**32,400t linear extrapolation**: all 8 UNKNOWNs would project deep negative. Not a crash (conservation holds, ATP/AAs healthy) but a diagnostic eyesore.

**Codex recommendation: FIX_BEFORE_32400T**. Architectural reason: chassis_v6 exposes all 585 M1 species into the shared cross-process substrate ledger when only true cross-process resources (NTPs, AAs, etc.) should live there. M1-internal species (AD, URA, AHCYS, etc.) should be private/internal diagnostics.

### Decision point — paused for user

Two paths:
- **Path A (architectural)**: refactor chassis to restrict shared `substrates` writes to allocation-keyed cross-process resources only. Bigger change. Per Codex recommendation.
- **Path B (pragmatic)**: kick off 32,400-tick now. Cascade is solved (ATP grows, AAs conserved, conservation holds). The negative M1-internals are pre-existing chassis design debt, not introduced by recent fixes. Cell-growth signals are clean. Accept diagnostic noise for now; do architectural cleanup separately.
- **Path C**: minimal whitelist — add regression test that ignores known M1-internal species, run 32,400-tick. Smaller than A, less hygienic than B.

Currently no Codex running. Awaiting user direction.

### Current branch state

- `agent/substrate-cascade-fix` HEAD `f13d517` — cascade fix validated, ready to merge to main
- `agent/phase-2-fix` HEAD `df9428b` — phase-2 + cascade-fix rebased + drain-triage docs, validated, ready to merge after cascade-fix
- 32,400-tick run NOT yet triggered

### Phase-2-combined validated 100t + 1000t (03:24 IST)

Codex (PID 4604, HEAD `58bfe21`) rebased onto cascade-fix HEAD `f13d517` cleanly, 60/60 tests pass, both canaries clean:
- ATP cum: +1,397,399 over 1000 ticks (~1397/tick growth) — production now flows from metabolism (Bug 4 commits work as intended)
- All NTPs / AAs healthy
- **Conservation holds**: `unattributed_delta` cumulative ~1e-8 across ALL 805 substrates over 1000 ticks
- Codex verdict: `clean-ready-for-32400t`

### 14 substrates with negative cumulative drain (potential 32400t blockers)

Three hit exactly **-1,000,000** (looks floor-clamped): `AD`, `NH3`, `URA`. Others:
- `ADP` -1.4M (mirrors ATP gain — energy cycle, expected)
- `GDP` -516K (mirrors GTP gain — expected)
- `H` (proton) -1.7M
- `PI` (inorganic phosphate) -1.4M (mirrors PPi → 2Pi → consumed)
- `AHCYS` -2.6K, `GN` -4.3K, `LIPOYLLYS` -13.6K
- `pSER` -11K, `pTHR` -12K, `SNGLYP` -562K, `THY` -4.6K

Action: launch analyst Codex to (a) check initial pool size for each, (b) determine if drains are stoichiometric/expected vs floor-clamping bugs, (c) extrapolate to 32400t, (d) recommend proceed-now vs fix-first.

Direct re-run of 100-tick canary on cascade-fix v4 HEAD revealed:
- **v4's claimed "ATP min=0, delta -1 then 0" was WRONG** — Codex's parser misread the CSV
- **Reality: -437.5/tick ATP consumption, identical to pre-fix**
- 1000t canary's "regression" verdict was CORRECT

### Deep probe of v4 state (Copilot direct, 02:40 IST)

All v4 runtime state is correct:
- `write_substrate_deltas=False` ✅, `is_step()=True` ✅, flow deps set ✅, topology wired ✅
- Direct call to `proc.next_update(...)` returns NO substrates (gating logic works)
- **But the simulation NEVER calls our instance's `next_update`** (prints in source don't fire)
- The per_process CSV STILL attributes -437.5 ATP/tick to `karr_transcription`

This is the smoking gun for one of:
- V1: vivarium Engine deep-copies the composite, losing our parameter override
- V2: dispatch via metaclass / Store-based / different method, bypassing our edit
- V3: CSV attribution is misleading; real emitter is elsewhere (e.g., `tx_v2` module called from another process)

### cascade-fix v5 Codex launched (PID 7896, 02:50 IST)

PROMPT: `E:\opencell-worktrees\substrate-cascade-fix\CONTINUE_PROMPT_v5.md`. Will disambiguate V1/V2/V3 via file-based logging probes, then fix root cause.

### Phase-2-fix (PID 15800) also completed
- Bug 4 (metabolism producer), D2 discard, ProteinDecay clamp all committed (e55a457, 8f2f64c, d3453aa) on branch `agent/phase-2-fix`
- STATUS_phase2.md MISSING — hit compaction failure at 199k tokens
- May or may not have substrate-cascade impact; re-test after v5 lands

### 🚨 ALARMING RESULT: cascade-fix v3 had ZERO measurable impact on the cascade

Cascade-fix v3 completed cleanly:
- Bug 1 (transcription_v3 allocation-aware): commits `07dcd7c`
- Bug 2 (translation_v3 allocation-aware): commit `297d30c`
- Bug 3 (chassis_v6 wiring): commit `a1740ba`
- All targeted tests pass: 17 (process tests) + 6 (integration) + 4 (chassis)
- **100-tick canary FAIL with IDENTICAL pre-fix numbers**: `ATP=-43750`, `LEU=-8982.83`

`-43750 = -437.5/tick × 100 ticks` means consumption proceeded at FULL rate every tick — allocation gating is still being bypassed in practice. Working hypotheses for why:
1. **H1** (init at 1.0 means tick-1 cliff regardless of gating)
2. **Wiring drift** (override didn't take effect — process kept old write_substrate_deltas=True after rename)
3. **Bug 4 dominates** so completely that even perfect 1+2+3 doesn't move the needle

### Active Codex sessions (post-audit completion)

| Session | PID | Worktree | Status | Waiter |
|---|---|---|---|---|
| ✅ bypass-precondition-audit v2 | 6420 | `E:\opencell-worktrees\bypass-precondition-audit` | DONE — 8 HIGH, 1 MED findings | exited 01:06 |
| ✅ substrate-cascade-fix v3 | 5284 | `E:\opencell-worktrees\substrate-cascade-fix` | DONE — code merged-ready, CANARY FAIL | exited 01:07 |
| 🟡 hypothesis-validation | 20388 | `E:\opencell-worktrees\hypothesis-validation` | RUNNING — H1/H2/H5/H7/H8 read-only checks | `wait-hyp-v2` |

### Audit findings (8 HIGH, 1 MED) — `E:\opencell-worktrees\bypass-precondition-audit\docs\audits\bypass_precondition_audit.md`

Already covered by cascade-fix v3 (5 HIGH): transcription/translation B/C/E patterns.

**NEW findings cascade-fix did NOT address**:
- HIGH B `karr_macromolecular_complexation.py:203` — D2 explicitly discards `substrates_allocated`, consumes raw
- HIGH D `karr_metabolism.py:267` — producer-silence (Bug 4 deferred)
- MED B `karr_protein_decay_light.py:193` — no allocation clamp

**Audit also REFUTED H6** (Pattern F clean — no `_v3` reference mismatches).

### Next decisions (pending hyp-validation results)

If H1 confirms (cliff at tick 1): fix initial conditions FIRST, then re-run canary before chasing more bypasses.
If wiring-drift confirms: re-investigate Bug 3 override mechanism (Process.parameters may be immutable post-__init__).
If neither: Bug 4 (metabolism production) becomes the only path forward.

### Diagnostic worktree (read-only, not yet merged)

- `E:\opencell-worktrees\substrate-leak-diagnosis` (branch `agent/substrate-leak-diagnosis`) — contains the 100-tick instrumented run that confirmed root cause. Files of interest: `STATUS.md`, `docs/diagnostics/substrate_leak_report.md`, `data/diagnostics/*.csv`. The diagnostic script `scripts/diagnose_substrate_leak.py` is the verification harness used by the fix Codex. Decision: keep this worktree until fix lands and final verification matches; then merge diagnostic-only changes to main.

### Cross-checks completed

- ✅ **GPT-5.5 independent analysis** (`files/gpt55_independent_leak_analysis.md` in session): converged on same root cause; added contract-ambiguity framing, initial-conditions bug, and protein_folding K/MN/NA mismatch as keepers.
- ✅ **Codex per-tick empirical confirmation**: PID 16100 100-tick instrumented probe matched static hypothesis exactly. `unattributed_delta=0` proves no hidden mutation. `karr_transcription` -43,750 each NTP, `karr_translation` -89,451 AAs, `karr_metabolism` 0 substrate emissions.

## Status (frozen pre-fix, 2026-05-24 00:30 IST, **903 tests passing**, ROOT CAUSE IDENTIFIED, fix Codex not yet launched)

### Today's headline result

**M4 milestone hit + first integrated validation pass complete + ROOT CAUSE OF SUBSTRATE CASCADE IDENTIFIED.** chassis_v6 (full 28-process composite) merged. Phase E.1, E.2, Bucket A (allocation-consumer enrollment), Bucket B (observability extensions) all merged to main. Scorecard moved 6/28 → 9/28 PASS. After Bucket A's allocation-bypass diagnosis was refuted (32400-tick before/after trajectories were bit-identical), a fanout of 5 parallel explore agents in ~5 min identified the **actual** root cause: `karr_transcription_v3` and `karr_translation_v3` (renamed to `karr_transcription` / `karr_translation` in chassis_v6) **are not enrolled in `KarrAllocationStep.consumer_processes`** but emit `{"substrates": {NTP/AA: -consumption}}` deltas directly via the `write_substrate_deltas=True` default parameter. Meanwhile `karr_metabolism` emits **zero** substrate deltas (no production side). The cascade is consumption without a source.

### ROOT CAUSE (2026-05-24 00:30) — confirmed by static analysis, Codex per-tick confirmation in flight

**Three contributing facts** all simultaneously true in chassis_v6:

1. **`karr_transcription_v3` (renamed to `karr_transcription`) is NOT in `consumer_processes`** at `karr_composite.py:1362-1388` (v5 base list) nor added at `1894-1907` (v6 rebuild). But it IS wired into the engine at `karr_composite.py:1761`. It defaults to `write_substrate_deltas=True` (`karr_transcription_v3.py:46`) and emits `{"substrates": {ntp: -per_ntp * timestep for ntp in self.consumed_substrates}}` at line 165 — ungated NTP consumption.

2. **`karr_translation_v3` (renamed to `karr_translation`) is similarly NOT in `consumer_processes`** but IS wired at `karr_composite.py:1762`. Same `write_substrate_deltas=True` default (`karr_translation_v3.py:39`), same direct delta emission at line 137 — ungated AA consumption.

3. **`karr_metabolism` emits ZERO substrate deltas.** In both static and dynamic modes it returns `fluxs`, `growth_per_s`, and `m1_pools` diagnostics — never `{"substrates": {...}}`. Reads `states["substrates"]` to set FBA bounds (`karr_metabolism.py:281-287`) but never writes back. The production side that should refill NTPs/AAs at the rate M2/M3 consume them is structurally absent.

**Math fit**: combined transcription + translation NTP/AA consumption easily produces the observed ~315 ATP units/tick drain. ATP, GTP, all dNTPs go negative because none have a source.

### Why prior debugging failed

- **Bucket A's rna_decay enrollment** affected only H2O (a tiny per-tick consumer); the big consumers (transcription_v3, translation_v3) were never touched. Bucket A fixed ~5% of the problem so trajectories were essentially identical pre/post.
- **No mass-balance regression test exists.** ~900 tests in the suite, zero assert `sum(substrate_deltas) ≈ 0` over time or substrates remain ≥ 0. Allocation-integrity tests confirmed the cycle is clean but said nothing about non-enrolled processes.
- **Narrow process tests use fixture-injected substrates** (`state["substrates_allocated"][p.name][p.atp_wid] = 5_000.0`), which masks any consumption imbalance.
- **The leak was present from chassis_v5 day one** (`write_substrate_deltas=True` defaults are weeks old) but no integrated v5 trajectory was ever compared against Karr's `cell_cycle_trajectory.mat`. E.1 was the first such comparison; the leak surfaced immediately.

### Fix path (next Codex session)

Clear, scoped fix — NOT a diagnostic ticket:

1. **Disable `write_substrate_deltas`** on `karr_transcription_v3` and `karr_translation_v3` at the chassis_v6 construction sites (parameter override).
2. **Enroll them in `consumer_processes`** with their NTP/AA wids (similar to how `karr_replication` was enrolled with `[*rep_proc.dntp_wids, rep_proc.atp_wid]`).
3. **Audit that they read `substrates_allocated[self.name]`** correctly inside their `next_update` — if not, wire it.
4. **Decide on metabolism production side**:
   - (a) v1.0 quick: enable `enable_pool_replenishment=True` on metabolism (heuristic source-term in internal state, may not flow to shared substrates — needs verification)
   - (b) v1.0 proper: translate FBA solution flux → substrate deltas in metabolism's return update
   - (c) v2 deferred: full M1 first-principles biochemistry

Option (b) is the cleanest v1.0 close. Option (a) is the smallest possible change but may not fix it.

### Tonight's diagnostic Codex (substrate-leak-diagnosis)

Currently running (PID 16100, launched 00:02:30). Will produce per-process substrate delta CSV from a 100-tick instrumented run. **Now a confirmation oracle, not a discovery tool** — explore agents already pinned the root cause statically. If Codex's CSV doesn't show transcription_v3 + translation_v3 as the top consumers and metabolism with zero substrate-store emission, we've misread something and need to re-examine. Let it run.

### Tonight's merges (2026-05-23 ~22:00, completed before root-cause discovery)
- ✅ **Bucket A merged** (`5fefe4a`): rna_decay allocation enrollment + host_interaction test-fixture cleanup. Allocation integrity = 100%. **Did NOT close BLOCK-RELEASE** (root cause was elsewhere).
- ✅ **Bucket B merged** (`3fd9edd`): observability schema extended; 5 BLOCKED KPs lifted (KP17/19/20 PASS, KP13/18 FAIL with diagnostic signal). E2_scorecard regenerated.
- ✅ **Test baseline**: 903 passed / 0 skipped / 4 xfailed.

### v1.0 scope decision (logged today)

OpenCell v1.0 is explicitly **"Karr-on-Vivarium with prescribed parameters"** — kinetic rates / half-lives / FBA bounds are taken verbatim from Karr's WCKB fixtures. Validation oracle = integration correctness, NOT independent biology. v2 = per-submodel direction (transcription/translation tractable, metabolism hard, host_interaction effectively impossible without new data). See `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` entry `v1-prescribed-rates-v2-first-principles`.

### Phase C — DNA replication + cell cycle ✅

All 10 turns + final chassis shipped (across the gap day and today's salvage cycles):

- ✅ pc-t1: ReplicationInitiation · pc-t2: Replication · pc-t3: DnaSupercoiling
- ✅ pc-t4: ChromosomeCondensation · pc-t5: ChromosomeSegregation
- ✅ pc-t6: DnaDamage · pc-t7: DnaRepair · pc-t8: FtsZPolymerization
- ✅ pc-t9: Cytokinesis · pc-t10: TerminalOrganelleAssembly
- ✅ pc-final: build_karr_chassis_v5 (27 processes wired, CellCycleCoordinator added)
- ✅ audit-cross-process-keys: full key-matrix audit; CPK-001 patched
- ✅ rna-decay: RnaDecay #13 added (process count to 28)
- ✅ fix-set-accumulate-warnings: single-declaration substrates_allocated leaves

### Phase D — Final integration to v6 ✅

- ✅ pd-t1: HostInteraction process (re-merged as `8dd146d` after 41809db lost content; lesson encoded as upcoming SESSION_CONTEXT rule 9)
- ✅ pd-final-chassis-v6: `build_karr_chassis_v6` shipped (commit `51aac1e`, 7 checkpoints, ~43 min, 145k tokens)
  - 28 process keys exposed via `CHASSIS_V6_EXPECTED_PROCESS_KEYS`
  - **Bundled with CPK-002 fix**: `chromosome.damage_sites` split into `damage_events_cumulative` + `repair_events_cumulative` (each accumulate-owned); derived view via `chromosome_views.current_damage_sites()`
  - **Bundled with CPK-003 fix**: `karr_dna_damage` now reads canonical `chromosome.fork_position_bp.left/right`
  - 5 v6 smoke tests + CPK regression tests all pass; full suite green

### Naming-drift rename ✅

Canonicalized all karr_* modules to biological names (commit `cf6a1ad`, ~14 min Codex):

- `karr_m1` → `karr_metabolism`
- `karr_m2{,_v2,_v3}` → `karr_transcription{,_v2,_v3}`
- `karr_m3{,_v2,_v3}` → `karr_translation{,_v2,_v3}`
- `karr_d2_real` → `karr_macromolecular_complexation` (class `MacromolecularComplexationProcess`)
- `karr_d2_stub` → `karr_macromolecular_complexation_stub`
- Legacy public builder APIs (`build_karr_m1_m2_engine`, etc.) preserved for backward-compat

### Phase E — Validation against Karr (E.1 + E.2 MERGED; allocation-fix + observability-ext in flight)

All four per-milestone designs drafted and merged to main (`be3d8fa`, `1b40b15`, `2884029`):

- 📝 `docs/design/phase_e2_phenotype_scorecard.md` — 28-KP table, bucketed tolerances, fixture caching
- 📝 `docs/design/phase_e3_discrepancy_analysis.md` — 7-rule classifier, v1.1 todo emission
- 📝 `docs/design/phase_e_final_release_gate.md` — 7 hard gates G1-G7 for v1.0
- 📝 `docs/design/cpk_dispositions_2026-05-23.md` — CPK-002/003 design calls (now landed in v6)

**E.1 ✅ MERGED** (commit `92f6c9a`): chassis_v6 ran full 32400 ticks vs Karr's `cell_cycle_trajectory.mat`. 1/9 observables PASS (cell_dry_mass shape OK in early ticks before going negative). Critical deliverable banked: `data/phase_e/v6_trajectory_32400s.pkl` (40996 bytes, 325 snapshots).

**E.2 ✅ MERGED** (commit `0208de7`): 28-KP phenotype scorecard implemented, `docs/phase_e/E2_scorecard.md` generated from cached E.1 trajectory (no rebuild). Pre-fix verdict: `E2_PASS=6/28, FAIL=9, BLOCKED=13`. PASSes: KP07/08/09 (mRNA/protein/AA stability), KP22/23/24 (qualitative phenotypes). FAILs: substrate/mass/replication cascade. BLOCKEDs: chassis-doesn't-emit-this-schema (each carries a v1.1 TODO id).

**E.3 not yet launched** — design ready at `docs/design/phase_e3_discrepancy_analysis.md`; deferred until AFTER allocation-consumer fix so it classifies post-cascade-fix discrepancies, not the cascade itself.

### Phase E.1 first findings (mid-flight, pre-merge — 17:30 IST)

E.1's fixture is already committed at `fdea8a2` on `agent/pe-1-real-match`; Codex is currently running checkpoint-5 full-suite verify. Pre-merge inspection of the pickle reveals chassis_v6 ran the full 32400 ticks without crashing (framework ✓) but biology is broken in three diagnosed ways, all cascading from a single root cause.

**Headline numbers** (from `data/phase_e/v6_trajectory_32400s.pkl`):
- `atp_pool`: 1.0 → -10.21M (crosses zero at tick 100, drains 315 units/tick)
- `gtp_pool`: mirrors ATP
- `dntp_pool_total`: 4.0 → 0 by tick 100 (never recovers)
- `cell_dry_mass_g`: 8.2e-16 → -3.4e-14 (negative from tick 1100)
- `replication_state_code`: stuck at 0 (idle) all 325 snapshots
- `fork_position_norm`: stuck at 0.0
- `division_detected`: False
- mRNA: 339 → 1261 (3.7×, plausible shape — plateaus ~tick 8100)
- Protein: 16272 → 91127 (5.6×, plausible ratio)

**Root cause**: the `karr_rna_decay` + `karr_host_interaction` allocation-bypass (known gap from chassis_v6 turn) consumes ATP/dNTP/H2O outside the KarrAllocationStep request/grant cycle. Over 32400 ticks the unbookmarked drain compounds to ~10M units. Replication never initiates because DnaA-ATP threshold can't be met when both ATP and dNTPs are underwater (CASCADE from the substrate bug, not an independent failure).

**This is the failure mode E.2 was designed to expose** — and E.2 exposed it cleanly (6/28 PASS predicted, 6/28 PASS actual on the same fingerprint of failing KPs).

**Consequence**: `allocation-consumer-enrollment` is **promoted from v1.x cleanup to v1.0 BLOCK-RELEASE**. v1.0 cannot ship until ATP/dNTP/mass stay non-negative across the 32400-tick run and replication advances past the idle state. `PROMPT_allocation_consumer.md` has been revised post-E.1 with these as the explicit regression target.

**Phase E sequencing locked**: `E.1 merge ✅ → E.2 launch (BEFORE-fix scorecard) ✅ → allocation-consumer Codex turn 🟢 (Bucket A, in flight) → observability extensions for tractable BLOCKEDs 🟡 (Bucket B, queued behind A's cp1) → E.2 re-run (AFTER-fix scorecard) → E.3 launch (classify residual discrepancies) → release gate`. Expected post-fix E.2 result: ~16-22 of 28 PASS (clears the ≥10/28 acceptance gate).

### Bucket A — allocation-consumer enrollment ✅ MERGED (`5fefe4a`, 2026-05-23 22:23)

- Worktree: `E:\opencell-worktrees\allocation-consumer`, branch `agent/allocation-consumer-enrollment`
- Token spend: ~113k · 4 checkpoints completed in ~107 min
- **Structural finding**: only `karr_rna_decay` needed enrollment. `karr_host_interaction` was already inside the cycle; its appearance of bypass was stale test-fixture `substrates_allocated` injection cruft (now pruned, -49 lines).
- **Diagnostic finding** (negative result): 32400-tick before/after trajectories are **identical** on ATP/dNTP/cell_dry_mass/replication. The cascade is NOT caused by the rna_decay bypass. Net substrate delta still -2.6M units. **BLOCK-RELEASE v1.0 NOT closed.**

### Bucket B — observability extensions ✅ MERGED (`3fd9edd`, 2026-05-23 22:25)

- Worktree: `E:\opencell-worktrees\observability-extension`, branch `agent/observability-extension`
- Token spend: ~165k · 6 checkpoints completed in ~43 min
- New module: `opencell/vivarium/karr_observability_step.py` — emits rna_mass_g, protein_mass_g, dna_mass_g, cytokinesis_start/complete_tick_s, per-species metabolite_pools
- **E.2 scorecard delta**: 6/28 PASS → 9/28 PASS, 13 BLOCKED → 8 BLOCKED
- Per-KP transitions:
  - KP13 cytokinesis-duration:  BLOCKED → **FAIL** (0.0s observed; division never completes — downstream of substrate leak)
  - KP17 DNA-mass:              BLOCKED → **PASS** ✅
  - KP18 RNA-mass:              BLOCKED → **FAIL** (measurable, value off Karr; transcription/decay rate fit)
  - KP19 protein-mass:          BLOCKED → **PASS** ✅
  - KP20 metabolite-profile:    BLOCKED → **PASS** ✅
- KP13/KP18 FAILs are diagnostic signal for v1.1 follow-up tickets, not BLOCK-RELEASE items.

### Skip-drift audit ✅

Independent Codex session (PID 3320, `agent/skip-drift-audit`) confirmed zero rename-caused skip drift. The historical "11 pass→skip" pattern was Thattai paper-cache environmental, not rename-related. Per user direction:
- Deleted 9 stale skeleton tests (`test_karr_chassis_v{5,6}_skeleton.py`) + 2 orphan modules (`karr_composite_v{5,6}_skeleton.py`) — commit `29f4aaa`
- Documented the 11 Thattai-cache skips as intentional in `docs/testing/known_skips.md`
- Test baseline moved from 877→896 on main repo (Thattai cache IS present here; the 11 skip only manifests in fresh worktree clones)

### Audit + cleanup sessions ✅

All read-only forensics shipped clean bills of health (no hidden landmines blocking v6/E):

- ✅ audit-merges-historical: only `41809db` was a real defect; 7 suspect 2-parent merges all false alarms (STATUS.md noise)
- ✅ audit-phase-b-fleet: only RNADecay was historically dropped; recovered via `c0640a1`
- ⏳ skip-drift-audit (PID 3320, running): investigating 11 tests that went pass→skip after rename

### Tolerance philosophy (decided today, logged as todo `per-kp-tolerance-calibration`)

**Reject global threshold ratchet** (e.g. "v6→20%→10%"). Karr's own ensemble has 30-50% CV on many KPs; claiming <10% on those is meaningless. **Tolerances are per-KP-bucketed**, not global:

| Stage | Action | Tolerance posture |
|---|---|---|
| v6 ships | "runs 32400 ticks without exploding" | 30% global (development aid) |
| E.2 first pass | Measure 28 KPs vs Karr; assign provisional bucket | Bucketed (0.1% tooling / 30% validation / 0.4-2.5× karr-incomplete / qualitative beyond-Karr) |
| E.3 classifier | Diagnose each miss: bug / calibration drift / Karr-incomplete / beyond-Karr | Bucket assignments solidified |
| v1.0 release | Ship with per-KP tolerances, NOT one number | G5 gate: ≥10/28 in validation bucket pass; zero tooling-bucket fails |
| v1.1+ ratchet | Each release tightens specific KPs as fixes land | Targeted, evidence-driven |

### Test state mid-day

- Pre-rename baseline: 883 pass / 9 skip / 4 xfail / 0 fail
- Post-rename: 872 pass / 20 skip / 4 xfail / 0 fail (11 pass→skip drift; under audit)
- **Post-chassis_v6 (current main, commit `51aac1e`)**: **877 pass / 20 skip / 4 xfail / 0 fail** (+5 v6 smoke tests)
- 0 failures, zero new UserWarnings introduced by v6
- 5 pre-existing warnings (`protein.counts.X` set-vs-accumulate) deferred to v1.1

### v1.0 trajectory (recalibrated again)

- ✅ Phase A3.3: DONE (1 day; original 6 weeks)
- ✅ Phase B: DONE (1 day; original 12 weeks)
- ✅ Phase C: DONE (yesterday + early today; ~3 days at today's pace)
- ✅ Phase D: DONE (today; ~6 hours)
- 🟡 Phase E: E.1 running now; E.2-E.3 + release gate next
- **Realistic v1.0 estimate: 1-2 weeks** (was 4-6 weeks at yesterday's projection)

### Known follow-ups (logged as todos, non-blocking for E.1)

- `skip-drift-audit-post-rename` — Codex session running now
- `v6-allocation-consumer-enrollment` — RnaDecay + HostInteraction wired in v6 topology but not enrolled as `KarrAllocationStep` consumers (Codex deliberately scoped out to avoid touching restricted modules). Fix queued post-E.1.
- `per-kp-tolerance-calibration` — bucket assignments after E.2 baseline measured
- WSL-native ext4 migration (~60-90 min, defers to post-Phase E)
- Pre-existing `protein.counts.X` collision warnings (deferred to v1.1)

### Operational lessons earned today (to bake into SESSION_CONTEXT)

- **Rule 9**: merge-conflict resolution requires `git rm <conflicted-file> + git merge --continue`, not the previous force-add pattern (lesson from 41809db re-merge)
- **Rule 10**: rename-before-wire — always canonicalize module/class names BEFORE final composite wiring lands, otherwise renames force double-touch downstream
- **Rule 11**: estimation calibration — Copilot-side design work defaults to 5-10 min (not 30-45); Codex sessions anchor to observed throughput (naming-drift: 14 min for 80-file rename, not 60-90 min)
- **Codex flag correction**: launch with `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check < PROMPT.md` (not the non-existent `--full-auto`); explicitly inherit `AZURE_OPENAI_API_KEY` from User scope before `Start-Process`

### Post-v1.0 framing (logged as `v1-trajectory-buckets`)

Four buckets for post-v1.0 scope: Karr-known-incomplete (v1.x), biology-beyond-Karr (v2+), validation-and-organism-scaling (v3+), OpenCell-specific-tooling (parallel). Future scope decisions must declare bucket.

### Historical sections (kept for provenance, not active work)

The sections below describe earlier phases — Phase D.2 design rework, MCOS extraction, p10 partition. All superseded by A3.3 and Phase B turns.

### Phase D.2 design rework loop (HISTORICAL — superseded by A3.3 joint design)

Standard practice for non-trivial design adopted this session: write → adversarial critique (Claude Sonnet rubber-duck or GPT-5.4 cross-model) → rework. Two rounds completed for D.2; v3 is the next concrete deliverable.

**Decisions resolved (apply to v3 and beyond):**
- **Q1 — oracle target:** *hybrid staged oracle*. Interface mature-only; unit-level oracles = conservation + topo + competition + 158-complex mature-supported subset + aggregate mature-only complex dry mass. Integration-level oracle (`D.2.mature + Σconsumers.bound ≈ snapshot.total` for ~10 bound-heavy anchors) deferred to post-v2-swap+M5. Drop the `J × τ` algebraic substitute argument.
- **Q2 — scope:** *split*. D.2 = MacromolecularComplexation + RibosomeAssembly only. ProteinFolding → D.3, ProteinActivation → D.4/M6 (deferred). chaperones-field corruption is no longer D.2's blocker.

**Branches:**
- `agent/d2-design-doc` @ `fa59925` — v1, 496 lines, superseded.
- `agent/d2-design-v2` @ `811a707` — v2, 770 lines + `data/karr_fixtures/d2_mature_subset.json`. Critiqued by GPT-5.4: rework with **4 BLOCKERs** for v3:
  1. Ribosome cost dissolution claim FALSE — must extract from `RibosomeAssembly.m` (30S+50S separately, 2/4 GTPases, randomized order).
  2. Scope creep — must whitelist D.2 ownership via `complex.formationProcesses` (live: 9 process IDs), exclude FtsZ/DnaA/holoenzyme/ChromCond.
  3. `_emit_update()` never emits negative deltas for consumed subcomplexes.
  4. Aggregate dry-mass oracle compares mature-only output to all-forms target (1.155e-15g vs 1.505e-15g).
  HIGH: add `complex.wholeCellModelIDs` to ARCHIVE_SPEC; reframe Q3 to D.2 ↔ M2/M3 protein/rna co-write.

**v2 verified-true headlines:** 22 ARCHIVE_SPEC paths real; 158 mature-supported subset; 10 bound-heavy anchors; mature_total = 4006 (cytosol+membrane) vs 3264 (cytosol-only).

### m1 per-process fixture extraction (BLOCKED on MCOS decode)

`agent/m1-per-process-fixtures` @ `1a4f92f`: scaffolding only. All 44 source `.mat`s are MATLAB MCOS-serialized class instances; pure-Python decoders refuse. Committed extract+validate scripts + 44 placeholders flagged `extraction_status: unparsed_mcos_payload`. Unblock options: (b1) MATLAB-in-WSL, (b2) one-off Windows-host MATLAB extract + ingest, (b3) drop per-process oracles. Not on critical path.

### Worktree convention (now standard)

Each background agent gets its own `E:\opencell-worktrees\<agent-name>` on `agent/<name>` branch. Adopted after a branch-switch race in d2-design-doc + p10-mass-partition parallel run. Active: `d2-design-v2`, `m1-per-process-fixtures`. Status files at `~/.copilot/session-state/<sid>/files/agent_<name>_status.md`.

### Phase E.1c — p10 mass-target partition (DONE — merge into `36636f6`)

p10b protein flips green (27.7% of cellDry); p10a RNA + p10c residual stay xfail with documented unblock paths. Substrate sub-target deferred. Suite: 602 passed + 4 xfailed.

---

## (Pre-checkpoint snapshot below — 2026-04-26)

### Phase E.1c — m2 per-condition snapshots (DONE — merge commit `0fb5df3`)

### Phase E.1c — m2 per-condition snapshots (DONE — merge commit `0fb5df3`)

* `karr_native_m2` schema v4: `counts_mature` is now shape `(525, 3)` (low/mean/high). Per-condition derivation: scale the single fitted-mean snapshot by `expression[:, c] / expression[:, mean]` per gene — no hardcoded values, scales mechanically to the whole-cell model.
* `opencell/m2/transcription.py`: `KARR_CONDITION_INDEX` mapping + `resolve_condition()`; `calibrated_chassis_model` accepts a condition arg. All consumers (`vivarium/karr_m2.py`, `karr_composite.py`, `analysis/phenotypes.py`) pick the column.
* Lifts the xfail on `test_compute_baseline_demand_respects_condition`. Suite: 600 passed + 2 xfailed (was 599 + 3).
* Branch `m2-per-condition-snapshots` (commit `9f8b186`) merged via `0fb5df3`.

### MATLAB Eviction (DONE — every Python workflow runs without MATLAB or .mat)

**Goal achieved:** Future contributors clone the repo and run all 8 ingest
scripts, the chassis, and the full test suite (599 + 3 xfail) without
MATLAB or any `.mat` file. MATLAB is now bootstrap-only — required only
to add new fields to the archive.

**Shipped:**
- `scripts/build_karr_archive.py` — extracts the consumed-fields whitelist
  (~100 leaves out of ~4300 total) from the 8 source `.mat` files (7 v7.0
  via `scipy.io.loadmat` + 1 v7.3 via `h5py`) into the committed archive
  `data/karr_archive/{karr_archive.npz, karr_archive_strings.json,
  karr_archive_manifest.json}` (~786 KB compressed, 143 ndarrays + 124
  string keys + per-field provenance).
- `opencell/_karr_archive.py` — namespace loader. `arc[basename].dotted.path`
  attribute access; `_StructArray` exposes parallel column-views and
  per-row iteration; `_NestedStructArray.per_parent(i)` for nested struct
  arrays (e.g. `complexes[i].monomers[j]`).
- All 8 ingest scripts refactored to use `load_karr_archive()` instead of
  `loadmat()` / `h5py.File()`. Output fixtures verified byte-identical
  (modulo `source_*` metadata labels) — see
  `data/karr_archive/fixture_hashes.json`.
- `scripts/validate_karr_archive.py` — re-runs every ingest and verifies
  output sha256 matches committed hashes (timestamp-insensitive, hashes
  array contents not zip metadata).
- `data/karr_archive/README.md` + `scripts/matlab/README.md` updated —
  MATLAB explicitly marked bootstrap-only.

**Verification:** 599 passed + 3 xfailed (unchanged from pre-eviction
baseline). Every fixture re-derived from the archive matches its
committed hash.

### Phase E.1b — Cell Dry Mass + MW Fixture Re-Extract (DONE — commit `65ca7d8`)
* M1 fixture v2 (`karr_native_m1__v2`): adds `substrate_molecular_weight[585]`, `enzyme_molecular_weight[104]` to npz; State_Mass aggregates (cellInitialDryWeight=3.93e-15 g, cellDry total=3.94e-15 g, rnaWt, dryWeightFractionRNA, 6-compartment splits) to JSON `stored_runtime`.
* M2 fixture v2 (`karr_native_m2__v2`): adds `rna_molecular_weight[525]` per gene. Policy: TU MW via gene→TU map then State_Rna mature MW (482 mRNAs); for 43 non-mRNA genes (tRNA/rRNA/sRNA where mature TU absent) fall back to `length_nt × 339.5 Da/NT` so rRNA mass is not dropped.
* `opencell/analysis/cell_mass.py`: aggregator computes substrate + RNA + protein mass (Da → g via Avogadro) with per-class breakdown.
* `phenotypes.py`: + `measure_cell_dry_mass` extractor (closed-loop config matching p9).
* `targets.json`: + `p10_cell_dry_mass_g` (closed_loop, expected_status=fail).
* Test pinned `xfail(strict=True)` documenting the chassis bug below.

**Honest finding (E.1b's contribution):** the aggregator surfaced a real M2 v1 chassis bug. M2 wires Karr's `expression[:,0]` (transcription-rate field, ~41327 normalized units) as if it were mature-RNA SS counts. Karr's actual SS mature-RNA count is **784 molecules across 347 mature species (cytosol)**. Aggregator therefore over-counts RNA mass ~53× → total ~9.7e-15 g vs target 3.94e-15 g (2.46×). Substrate side also bogus (chassis seeds 561 non-demand substrates at 1.0 placeholder vs Karr's snapshot counts). New todo `m2-counts-fix` tracks the M2 re-wiring; flips p10 green. Same pattern as p4 (PTS gap) — phenotype harness keeps surfacing structural gaps, exactly as designed.

### Phase E.0 — Phenotype Validation Harness (DONE — first report shipped)


* `data/karr_fixtures/karr_phenotype_targets.json` (`karr_phenotype_targets__v1`) -- 8 phenotypes with documented targets, tolerances, and a `category` field separating non-circular FBA-prediction tests from chassis composition invariants.
* `opencell/analysis/phenotypes.py` -- pure measurement extractors (one per phenotype) returning `PhenotypeMeasurement(predicted, target, unit, extra)` for uniform reporting.
* `tests/phaseE/test_karr_phenotypes.py` -- 8 pytest cases. #4 (TX_GLCPTS) marked `xfail(strict=True)` documenting the structural gap that PTS glucose uptake lives in non-FBA submodels (expected to flip green when M4-M28 land).
* `scripts/phase_e_report.py` -- markdown-table summariser. First report:

| # | Phenotype | Status | Predicted | Target | Detail |
|---|---|---|---|---|---|
| 1 | growth_per_s | PASS | 1.09e-5 | 2.12e-5 | 0.514x (matches known structural ceiling) |
| 2 | doubling_time_h | PASS | 17.67h | 13.11h | 1.348x |
| 3 | fba_oracle_median_log2 | PASS | 0.96 | <=1.0 | over 196 nonzero rxns |
| 4 | glc_uptake_TX_GLCPTS | XFAIL | 0 | 2725 | structural gap, needs M4-M28 |
| 5 | mrna_total_roundtrip | PASS | 41327 | 41327 | exact (M2 v1 prescriptive) |
| 6 | protein_total_roundtrip | PASS | 16177 | 16177 | exact (M3 v1 prescriptive) |
| 7 | mrna_stability_20s | PASS | 0 drift | <0.10 | chassis SS holds |
| 8 | protein_stability_20s | PASS | 0 drift | <0.10 | chassis SS holds |

**Honest assessment:** 3 fba_prediction tests are real ground-truth comparisons (#1-3); #4 is a documented structural gap. #5-8 are circular today (M2/M3 v1 round-trip prescribed Karr values by construction) -- they become real predictive tests once v2 mechanics replace prescribed rates. With #4 as the meaningful "fail" surfacing the PTS gap, the report quantifies how much of Karr's biology the chassis currently captures via M1 alone.

**Next E phases:**
- E.1a: per-AA pool stability test (#14) -- chassis already exposes per-AA via Phase C.1; just needs test wiring.
- E.1b: MW fixture re-extract + mass aggregator + cell mass test (#9) -- requires MATLAB re-run of `extract_karr_targeted.m` to add `kb.metabolites.molecularWeight` and `kb.transcriptionUnits.molecularWeight`.
- E.2: decision point on D.2 (complex assembly) vs M5 (replication) vs v2 mechanics, driven by the 10-phenotype report from E.0 + E.1.

### Phase D.0 + D.1 (DONE -- 0cc8d16)
* D.0: protein-complex composition fixture from MATLAB extract (201 complexes), `opencell/m1/protein_complexes.py` loader with recursive flattening. 20/20 tests.
* D.1: compartmented S fixture (585x645x3, nnz=2644) + supply-side calibration helper using existing `solve_fba`. 17/17 tests, including TX_GLCPTS PTS uptake spot-check and `test_baseline_NTPs_NOT_supplied_through_FBA` locking in the D.1 spike finding.

### Central Dogma Chassis (DONE — M1+M2+M3 composition)

* **M1 Karr-native FBA** (`opencell.m1.karr_metabolism`): 504-FBA, 645-rxn,
  per-reaction oracle vs Karr's stored fluxs PASSED (median |log2 ratio|
  = 0.96 over 196 rxns).  Static-snapshot FBA bounded at ~51% of stored
  growth (proven structural — Karr's snapshot enzyme bounds are
  post-step; 34/504 of his own stored fluxs violate them).
* **M2 Karr-native transcription** (`opencell.m2.transcription`): 525
  genes, dRNA/dt = s − k·RNA closed-form per 1s tick. v1 Karr-prescribed
  rates (round-trips to expression by construction). v2 = polymerase
  mechanics deferred.
* **M3 Karr-native translation** (`opencell.m3.translation`): 482 mature
  monomers, dN/dt = s − k·N closed-form per 1s tick. v1 prescribed
  rates from sim.state.ProteinMonomer (lengths, halfLives, decayRates,
  counts on matureIndexs slice into the 4820-vec state×species). 119
  immortal essentials handled (k=0 linear branch). Round-trips to
  counts_mature by construction. v2 = ribosome mechanics deferred.
* **Vivarium chassis** (`opencell.vivarium.karr_composite`):
  `build_karr_m1_m2_m3_engine` — all three processes share the
  `substrates` store. M1 declares all 585 substrate WCM IDs (read-only
  placeholder); M2 writes accumulating ATP/CTP/GTP/UTP deltas; M3 writes
  AA_total bulk delta. 4 chassis-composition tests prove growth +
  RNAs + proteins all flat at SS over 20s and shared-substrate deltas
  match expected.
* **Honest gaps still open:**
  - M1 doesn't yet read substrate writeback into FBA bounds (needs
    `calcFluxBounds()` port + 585→1686 metabolite×compartment mapping).
  - Per-AA breakdown stays as bulk AA_total (real per-metabolite mapping
    deferred to integrator pass).
  - M2 v2 (polymerase mechanics → independent oracle on synthesisRate)
    and M3 v2 (ribosome mechanics → independent oracle on synth_rate)
    not yet built.

### Hybrid Solver + First-Run Demo (DONE — Phase 3 capstone, 397-test era)

* `opencell/solvers/hybrid.py` — operator-split lockstep: LSODA on
  metabolism, tau-leap on the gene network. One-way coupling lets us
  solve metabolism once over the full horizon (single-pass LSODA),
  giving a 14× speedup vs per-macro-step restart (1h hybrid_run:
  2.44s → 0.18s post-warm-up).
* RNG hygiene: `tau_leap` requires explicit `np.random.Generator`;
  `hybrid_ensemble` uses `SeedSequence.spawn(n)` so parallel
  realisations cannot collide. Project-wide rule documented in
  `.github/copilot-instructions.md` ("Stochastic RNG Discipline").
* WSL-only execution rule documented (Windows venv silently skips the
  libroadrunner oracle tests; expected skip count is exactly 5,
  Thattai paper-cache only).
* Tests: 5 hybrid + 10 coupled + 11 stochastic = 26 green in WSL.
* `scripts/demo_first_run.py` — end-to-end artifact:
  `artifacts/first_run_demo.{png,json}`. 12 stochastic realisations
  over 8 cellular hours, with deterministic uncoupled baseline as
  dotted overlay. Shows glucose collapse at t≈72s drives f_met to
  0.03; coupled ensemble fails to start the gene network while the
  uncoupled baseline builds R into the thousands. Story: starvation
  prevents the autoregulatory feedback from engaging.

### Cross-Model Coupling (DONE — first composition)

* `opencell/models/coupled.py` — `CoupledMetabolismTranscription`
  composite ODE on concatenated state. Vilar h^-1 rescaled to s^-1
  internally. f_met=clamp(cglcex/cglcex0, 0, 1) modulates ONLY 6
  synthesis fluxes (curated indices, stoichiometry-asserted).
  Optional `signal="uptake_flux"` uses PTS flux ratio instead.
* 10 integration tests passing (RHS-equality at f_met=1, synthesis-only
  modulation, conservation, starved < fed, both signals).
* Demo `scripts/compare_coupled.py` + artifacts. Shows synthesis
  collapse as cglcex depletes (2.0 → 0.044 mM in 8h cellular time).
* Honest scope flagged: cglcex is external glucose availability,
  not energy state. Architecture demo, not validated biology.
* Reproducibility scripts updated with paper-cited Vilar bounds and
  Chassagnole methodology disclosures.

### Transcription Sub-Model — COMPLETE ✅ (2026-04-23, this checkpoint)
Second sub-model, first count-based (gene expression):

- **Engine extension**: `opencell.models.sbml_model` now supports
  per-species `hasOnlySubstanceUnits` (amount-mode species). Initial values
  handle all four (mode × initialAmount/Concentration) cases correctly
  (also fixed a latent bug for concentration-mode + initialAmount). `rhs`
  skips the volume divide for amount-mode species. Chassagnole regression
  bit-identical (cglcex(60s)=1.318993).
- **Wrapper** (`opencell/models/transcription.py`): `TranscriptionModel.load()`
  pins BIOMD0000000035 (Vilar 2002, "Mechanisms of noise resistance in
  genetic oscillators") and records BioModels ID + DOI 10.1073/pnas.092133899
  + PMID 11972055 in `provenance()`.
- **Validation oracle** (libroadrunner) across **all 9 species** over 200
  time-units (~3 oscillation periods of the activator-repressor limit cycle):
  - **Worst species max_rel_err: 9.7e-7**
  - **Median species max_rel_err: 3.0e-7**
  - Test threshold rtol=1e-3; actual is ~1000× tighter.
  - Gene-copy conservation `DA+DAp=1`, `DR+DRp=1` enforced and verified.
- **Demo script**: `scripts/compare_vilar.py --time-units 200` — OC-vs-RR
  overlay + residual log panel + per-species residuals JSON.
- **Tests added**: 9 (4 substance-units unit + 5 Vilar oracle integration).
- **Manifest**: `manifests/vilar2002.draft.yaml` auto-generated from SBML;
  paper-pairing eutils-verified.

### Metabolism Sub-Model — COMPLETE ✅ (2026-04-23, prior checkpoint)
First sub-model anchored on real biology, end-to-end working:

- **Engine** (`opencell/models/sbml_model.py`): generic SBML L2/L3 → ODE
  translator. libsbml parses; sympy.lambdify compiles every `<kineticLaw>`
  and `<assignmentRule>` MathML formula to a NumPy callable. Identifiers
  pre-bound via `local_dict` so SBML names like `S`, `E`, `I`, `Q` are not
  silently shadowed by sympy singletons. Loud failure on `<event>`,
  `<functionDefinition>`, `<rateRule>`, `<initialAssignment>`.
  Provenance: SHA-256 of SBML bytes + level/version + topology.
- **Wrapper** (`opencell/models/metabolism.py`): `MetabolismModel.load()`
  pins BIOMD0000000051 and records BioModels ID + DOI + PMID in
  `provenance()` so any simulation output traces back to eutils-verified paper.
- **Validation oracle**: libroadrunner (the de facto SBML simulator;
  Tellurium ships it). OpenCell agreement with RR across **all 18 species**:
  - Smooth 60s:   max rel err **2.5e-8**
  - Smooth 300s:  max rel err **3.3e-8**
  - **Glucose-spike perturbation (cglcex 2→4 mM at t=180s, run to 300s)**:
    max rel err **5.2e-8** — biologically correct PEP depletion
    (1.86→0.71 mM) and pyruvate buildup (3.55→4.59 mM) post-spike.
  Test threshold is rtol=1e-3; actual is ~5 orders below that.
- **Demo scripts**:
  - `scripts/run_chassagnole.py` — single OC run + provenance JSON
  - `scripts/compare_chassagnole.py --seconds {60,300}` — OC-vs-RR overlay
    + residual log panel + per-species residuals JSON
  - `scripts/spike_chassagnole.py` — two-phase spike experiment with same
    comparison artifacts; also a candidate for a perturbation integration test
- **Performance characterized**: OC is ~31× slower than RR (427 ms vs 14 ms
  for 300s sim) — pure-Python flux loop in `sbml_model.fluxes` dominates
  (52% of time). Not a bottleneck yet (0.4s for 5 min sim); planned remedies
  if needed: vectorized single-lambdify flux evaluator → cached env →
  JAX/diffrax backend.
- **Tests added**: 21 (5 formula compile + 8 Chassagnole load + 4 unsupported-
  features guards + 4 integration). PySCeS as oracle for this model is
  blocked by a PySCeS bug on csymbol-time assignment rules; libroadrunner
  is the cleaner choice and is now declared in the `oracle` extras.

### Correctness Guardrails — COMPLETE ✅ (2026-04-23, prior checkpoint)
Two new audit-grade guardrails layered onto the parameter pipeline so a
non-biologist can trust the outputs without manually verifying numbers:

- **Paper-pairing verifier** (`opencell/manifest/pairing.py`,
  `tools/verify_paper_pairing.py`): calls NCBI eutils on
  `manifest.paper.pubmed_id`, confirms the resolved DOI matches
  `manifest.paper.doi` (auto-fills when blank, loud failure / exit-4 on
  mismatch), writes structured `paper.verification` block back with
  `verified_at`, title, first_author, year, journal, and SHA-256 of the
  eutils JSON for offline-reproducible audit. Multiple PMIDs fail closed.
  29 tests. **Verified end-to-end**: Chassagnole manifest had blank DOI
  → verifier auto-filled `10.1002/bit.10288`, response_sha256 pinned.

- **PDF↔SBML cross-check guardrail** (`opencell/curation/value_match.py`
  + runner integration): when a recommendation comes from PDF extraction
  AND the manifest entry has a curated `sbml_value`, mechanically compares
  candidate.converted_value vs sbml_value with rel_tol=1% + abs_tol=1e-12.
  **DISAGREE downgrades RECOMMEND → AMBIGUOUS** so mismatches are NEVER
  silently auto-emitted as draft cards. Skips when candidate.method ==
  "biomodels_sbml" (no tautological self-verification). Cross-check is
  recorded in `CurationOutcome.cross_check` and in `card.selection_rationale`.
  18 tests (13 value-match + 5 runner integration).

### Schema Reconciliation — COMPLETE ✅
- Emitter now writes structured `paper.pubmed_id` (not regex-over-notes)
- Loader accepts `paper.pdf_cache` as fallback for top-level `cache_files`
- Loader accepts empty `paper.doi` (draft state); runner refuses to extract
  until verifier or human fills it
- Loader reads `sbml_value`, `sbml_id`, `sbml_kind` per parameter entry
- Loader exposes `paper.verification` block

### GitHub-Mirror SBML Source — DOCUMENTED ✅
BioModels HTTP API returns 403 from many environments (Cloudflare-class WAF).
Recommended primary source is now the EBI's GitHub mirror:
`git clone --depth 1 https://github.com/biomodels/<BIOMD_ID>.git`.
Documented across `tools/biomodels_manifest.py`, `.github/skills/biomodels-manifest.md`,
and `data/biomodels_reference/README.md`. Permanent reference copy of
Chassagnole SBML committed at `data/biomodels_reference/BIOMD0000000051_chassagnole2002.xml`.

### Bulk Extraction Pipeline — COMPLETE ✅ (earlier this session)
Two skills/tools built on top of `param-extractor`, completing the
deterministic ingestion stack for whole papers:

- **`biomodels-manifest`** (`opencell/manifest/`, `tools/biomodels_manifest.py`):
  ElementTree-based SBML walker with unit resolution + MIRIAM annotation
  auto-fill (biomodels_id, pubmed_id, organism via taxonomy lookup).
  36 tests. Validated end-to-end on real BIOMD0000000051 → 160-entry draft
  manifest (7 global + 135 local + 18 species, 5 unit definitions).

- **`biology-curator`** (`opencell/curation/`, `tools/curate_params.py`,
  `.github/skills/biology-curator.md`): per-paper extraction orchestrator.
  Consumes manifest YAML, runs `param-extractor` per entry, emits 5
  artifacts: DRAFT cards (RECOMMEND only, now blocked by cross-check on
  DISAGREE), arbitration queue (AMBIGUOUS), not-found queue, markdown
  coverage report, JSON run provenance. 28 tests including a Thattai 2001
  replay that proves both the success path (k_R → 0.6 min⁻¹ matching
  APPROVED card bit-for-bit) AND the safety guarantee (3 derived params
  route to NOT_FOUND, never invented). Hard constraints enforced by code:
  never invents, never auto-promotes, never resolves AMBIGUOUS silently,
  never overwrites REVIEWED/APPROVED cards even with `--force`.

### Phase 1 — CLOSED ✅
All Phase-1→Phase-2 gate tests are passing (G1.2–G1.8). 0 regressions across the campaign.

| Gate | Status | What it proves |
|---|---|---|
| G1.2 mass action | ✅ 2 tests | JAX implementation matches analytical SS |
| G1.3 stochastic | ✅ 3 tests | Gillespie matches deterministic mean |
| G1.4 atom balance | ✅ 3 tests | Conservation in closed/open systems |
| G1.5 unit trace | ✅ 8 tests | pint Quantities preserved end-to-end |
| G1.6 reference frames | ✅ 6 tests | Cross-frame detection + round-trip conversions |
| G1.7 PySCeS oracle | ✅ 4 tests | Independent 20-year-old solver agrees to 1e-3 rtol |
| G1.8 thermo feasibility | ✅ 6 tests | `ThermoFeasibilityReport` infrastructure for Phase 2 |

### Parameter-Verification System — OPERATIONAL ✅
- **Schema**: `ParameterCard` v2 with 3-state lifecycle (DRAFT → REVIEWED → APPROVED), 9 deterministic validators, mandatory biological context + provenance trail
- **Interactive review tool**: `tools/review_param.py` (4 y/n + reviewer name for review; 2 y/n + reviewer name for approve)
- **Batch helpers**: `tools/batch_review_thattai.sh`, `tools/batch_approve_thattai.sh` for the common case
- **CI gate**: `ci_gate_check()` fails build if APPROVED params have validation errors or DRAFT params used in gates without acknowledgement

### Thattai 2001 — FULLY VERIFIED ✅ (first paper with 100% APPROVED coverage)
- 4/4 parameter cards APPROVED by **Drona Srinivas** on 2026-04-23
- All values traced to **Fig. 1 caption** of the actual PDF (verified with `pypdf` extraction, hashed)
- Verbatim quote, original-value, original-unit, and transformation trail recorded on every card
- File: `data/params/micro_model_thattai2001.yaml`
- **Hallucination history preserved** in `docs/biology/micro_model_derivation.md` (3 rounds: Round 1 invented values, Round 2 invented a non-existent "Table 1", Round 3 used the real Fig. 1 caption)

### Deterministic Parameter Extraction Skill — BUILT ✅ (2026-04-23)
**The structural fix for the hallucination failure mode.** Replaces the AI-reads-PDF workflow with an auditable evidence-set pipeline.

- **Skill spec**: `.github/skills/param-extractor.md` — hard constraints (never invent, never auto-promote, never resolve ambiguity silently, never fill biological context by inference, cache provenance mandatory)
- **Library**: `opencell/extraction/` (7 modules)
  - `candidate.py` — `ExtractionCandidate` / `ExtractionResult` dataclasses with section tagging + rejection-reason audit trail
  - `text_normalize.py` — pypdf demangling (`s21`→`s^-1`, `kR 5 0.01`→`kR = 0.01`)
  - `pdf_grep.py` — regex extraction with symbol variants, scoring, English-stop-word filter
  - `units.py` — pint conversion with full transformation strings
  - `biomodels.py` — best-effort BioModels SBML lookup (corroboration only, never replacement)
  - `provenance.py` — SHA-256 file hashing
  - `pipeline.py` — orchestrator (sources tried in parallel)
- **CLI**: `tools/extract_param.py` — emits DRAFT cards only; exit codes 0/1/2 for RECOMMEND/AMBIGUOUS/NOT_FOUND
- **Tests**: `tests/unit/test_extraction.py` (29 tests) covering positive (Thattai), adversarial (refs section, `kR1` boundary, English stop-words eaten as units), provenance, units
- **Validation**: Re-extracts Thattai 2001 `kR` deterministically → `0.01 s⁻¹` → `0.6 min⁻¹`, matching the human-verified APPROVED value bit-for-bit

### Published-Model Anchoring Strategy (still in force)

**Lesson learned (Round 1+2 hallucinations)**: AI agents fabricated parameter values labeled as "Thattai 2001 Table 1" (a table that does not exist in the paper). The verification system above prevents the *labeling* failure; published-model anchoring prevents the *fabrication* failure by always comparing against a reference simulation.

| Milestone | Published model | Status |
|---|---|---|
| Phase 1→2 Gate | Thattai & van Oudenaarden 2001 | ✅ **CLOSED**, all 4 params APPROVED |
| Phase 2 Toy Cell | **Chassagnole et al. 2002** (E. coli central carbon, BIOMD0000000051) | ✅ **METABOLISM SUB-MODEL COMPLETE** — SBML→ODE engine + Chassagnole wrapper, OC-vs-libroadrunner agreement ~5e-8 across smooth + glucose-spike scenarios. Next: 2nd sub-model (transcription) + resource-ledger coupling. |
| Phase 3 Multi-Module | **Covert et al. 2008** (integrated E. coli TF + metabolism) | TBD |
| Phase 4+ Whole Cell | **JCVI-syn3A / Thornburg 2022 Cell** | TBD |
| (Original Phase 5 target) | Karr 2012 M. genitalium | Optional — JCVI-syn3A is the modern equivalent |

### Honest Status: Where We Are vs A Running Simulation

**What we HAVE:** A bulletproofed, audit-grade parameter sourcing pipeline AND
a first complete sub-model (metabolism) reading curated SBML directly,
validated against libroadrunner to ~5e-8 relative across 18 species under
both smooth (60s, 300s) and perturbation (glucose spike at t=180s)
scenarios. 378 tests. Performance baseline established (31× slower than
the C++ oracle but 0.4s for 5 min sim — not yet a bottleneck).

**What we DO NOT have yet (blockers for a multi-module cell):**
1. ~~Curated Chassagnole parameter set~~ — obviated by direct-SBML pivot
2. **Other sub-model implementations** — `transcription.py`, `translation.py`,
   `transport.py`, `degradation.py` do not exist yet. (`metabolism.py` ✅,
   `micro_model.py` ✅, `base.py` ✅.)
3. **Sub-model coupling** (`p3-coupling-impl`) — how transcription's protein
   output feeds metabolism, etc. The resource ledger exists in design only.
4. **Hybrid solver** (`solvers/hybrid.py`) — pieces (`ode.py`, `stochastic.py`,
   `ode_scipy.py`) exist; gluing does not
5. **Cell environment** (`p2-environment`) — initial conditions, medium
   composition, volumes (Chassagnole has its own embedded environment)
6. **Gene set definition** (`p2-gene-set`) — which genes are in the toy cell
7. **Identifier crosswalk** (`p2-id-crosswalk`) — KEGG ↔ BioCyc ↔ EcoCyc.
   **Blocked on `p1-db-access`** (need API keys / data dumps)
8. **Multi-module integration run** — even a "Hello World" coupled trajectory

### Immediate Next Steps (in recommended order)
1. **Write a transcription sub-model** anchored on a curated BioModels entry
   (candidate: BIOMD0000000091 / Lipniacki 2004 NF-κB or a simpler
   constitutive transcription model). Same pattern: SBML → `SbmlOdeModel`
   → wrapper recording paper-pairing.
2. **Wire metabolism + transcription via the resource ledger** so the two
   sub-models share at least one species (e.g., ATP). First multi-module
   coupled integration.
3. **Build `solvers/hybrid.py`** — operator splitting between the metabolism
   ODE block and the transcription stochastic block (tau-leaping).
4. **Phase 2 replan** — the "toy cell as ~50 designed genes" plan should
   evolve to "toy cell = stitched curated BioModels entries via resource ledger,"
   which is more tractable and equally publishable as a coupled-solver benchmark.
5. Resolve `p1-db-access` blocker (KEGG/BioCyc/EcoCyc) — needed for `p2-id-crosswalk`

### Resolved (no longer open)
- ~~Thattai 2001 parameter discrepancies~~ — resolved Round 3 from actual PDF Fig. 1 caption
- ~~Remaining Gate tests G1.4–G1.8~~ — all closed
- ~~Hand-curated parameter extraction~~ — replaced by deterministic skill
- ~~Manual prune of 160-entry Chassagnole manifest~~ — obviated by the cross-check guardrail (humans only see DISAGREE bucket, not all entries)
- ~~"How do I trust the SBML/paper pairing"~~ — resolved by `tools/verify_paper_pairing.py` with eutils + response_sha256
- ~~"How do I trust the PDF-extracted numbers"~~ — resolved by `value_match.cross_check` digit-level diff against curated SBML

## Vision
Build the first modern, open-source, GPU-accelerated whole-cell computational model — starting with a coupled-solver benchmark ("toy cell", ~50 synthetic genes), scaling to *Mycoplasma genitalium* (~525 genes). Designed to be publishable, extensible, and accessible.

### Deliverable Split
- **v1.0** — Framework + toy cell benchmark. A standalone publishable result demonstrating the architecture, coupled solvers, and agent workflow. The toy cell is explicitly a *coupled-solver benchmark*, not a biologically coherent cell.
- **v2.0** — M. genitalium whole-cell model. A separate project phase with its own timeline, gated on v1.0 success. Timeline TBD after v1.0 completion (original 20-week estimate was judged 5-10x too short by independent reviewers).

## Why This Matters
- **Drug discovery**: simulate how drugs disrupt bacterial metabolism in silico
- **Synthetic biology**: design minimal genomes computationally before building them
- **Antibiotic resistance**: model mutation-driven resistance mechanisms
- **Education**: interactive cell simulation as a teaching/learning tool
- **Open science**: replace the closed MATLAB Karr 2012 model with a modern Python/JAX implementation anyone can use and extend

## Approach
- **Language**: Python (NumPy, JAX, SciPy, BioPython, COBRApy, pint)
- **Architecture**: Modular sub-model system (inspired by Karr et al. 2012, modernized)
- **Compute**: JAX for CPU-optimized ODE solving; SciPy as reference/fallback for stiff systems; runs on local workstation or Colab GPU
- **Data**: Published parameter sets (Karr 2012, BRENDA, BioCyc, UniProt, KEGG); versioned via DVC or content-hashed snapshots
- **Validation**: Compare against Karr 2012 published results AND orthogonal experimental data; split fit targets from held-out validation targets
- **AI Agents**: Cloud-first multi-model strategy; local models optional with GPU (see below)
- **Units**: pint library for unit handling at IR boundary from day 1

---

## Project Structure

```
opencell/
├── README.md                    # Project overview, quickstart, citation info
├── LICENSE                      # Apache 2.0
├── pyproject.toml               # Modern Python packaging (PEP 621)
├── CONTRIBUTING.md              # Contribution guidelines
├── CODE_OF_CONDUCT.md           # Community standards
├── CITATION.cff                 # Citation metadata for academic use
├── GOVERNANCE.md                # Maintainer roles, decision rules, release policy
├── SECURITY.md                  # Vulnerability reporting policy
├── CHANGELOG.md                 # Keep a Changelog format, managed by towncrier
├── opencell_tasks.db            # Persistent SQLite task/dependency tracker (synced with plan.md)
├── Dockerfile                   # Reproducible environment (even if running locally)
├── uv.lock                      # Locked dependency versions (committed to repo)
│
├── .github/
│   ├── copilot-instructions.md  # Agent roles, workflow rules, constraints
│   ├── workflows/
│   │   ├── ci.yml               # Tests, linting, type checking
│   │   ├── docs.yml             # Documentation build
│   │   └── schema-validate.yml  # Validate data files against JSON Schemas
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       └── feature_request.md
│
├── docs/
│   ├── architecture.md          # System architecture & design decisions
│   ├── data-licensing.md        # Database access terms & redistribution rules
│   ├── blog/                    # Running dev blog (checkpoint entries)
│   │   ├── index.md             # Blog index (reverse chronological)
│   │   └── YYYY-MM-DD-title.md  # One entry per day/checkpoint
│   ├── biology/                 # Biological background for each sub-model
│   │   ├── metabolism.md        # Rationale, literature refs, modeling choices
│   │   ├── transcription.md
│   │   ├── translation.md
│   │   └── ...
│   ├── api/                     # Auto-generated API docs (MkDocs)
│   └── tutorials/
│       ├── quickstart.md
│       ├── adding-a-submodel.md
│       └── parameter-estimation.md
│
├── decisions/                   # Versioned expert panel decisions (with invalidation triggers)
│   ├── metabolism.md            # "Panel chose Michaelis-Menten for X because..."
│   ├── transcription.md
│   ├── _decision_index.yaml     # Decision registry: version, triggers, status
│   └── ...
│
├── src/
│   └── opencell/
│       ├── __init__.py
│       │
│       ├── core/                # Simulation engine
│       │   ├── __init__.py
│       │   ├── engine.py        # Main simulation loop & time-stepping
│       │   ├── state.py         # Cell state container (all molecular counts)
│       │   ├── ir.py            # Internal Runtime Representation (canonical in-memory model)
│       │   ├── compartments.py  # Volume, compartmentalization, counts↔concentrations
│       │   ├── environment.py   # First-class media/environment model (nutrients, pH, temperature)
│       │   ├── resource_ledger.py # Global resource allocation & partition-merge semantics
│       │   ├── units.py         # pint-based unit registry & conversion at IR boundary
│       │   ├── checkpoint.py    # Checkpoint/restart for long simulations
│       │   ├── manifest.py      # Run manifest: git SHA, seeds, solver version, etc.
│       │   ├── events.py        # Discrete event handling (division, etc.)
│       │   ├── guards.py        # Runtime invariants: positivity, bounds, conservation monitors
│       │   ├── sentinels.py     # Order-of-magnitude sanity checks for key variables
│       │   ├── crash_bundle.py  # First-bad-step diagnostic capture
│       │   └── config.py        # Simulation configuration & parameters
│       │
│       ├── models/              # Biological sub-models (pluggable)
│       │   ├── __init__.py
│       │   ├── base.py          # Abstract sub-model interface
│       │   ├── metabolism.py    # Metabolic network (FBA/kinetic)
│       │   ├── transcription.py # mRNA synthesis
│       │   ├── translation.py   # Protein synthesis
│       │   ├── replication.py   # DNA replication
│       │   ├── degradation.py   # mRNA & protein degradation
│       │   ├── transport.py     # Membrane transport
│       │   └── division.py      # Cell division & cytokinesis
│       │
│       ├── data/                # Data loading & parameter management
│       │   ├── __init__.py
│       │   ├── loader.py        # Load YAML params + SBML models
│       │   ├── sbml_io.py       # SBML import/export via libsbml
│       │   ├── brenda.py        # BRENDA enzyme kinetics scraper
│       │   ├── biocyc.py        # BioCyc pathway data parser
│       │   └── kegg.py          # KEGG pathway mapper
│       │
│       ├── estimation/          # ML-based parameter estimation
│       │   ├── __init__.py
│       │   ├── kinetics.py      # Estimate missing kinetic parameters
│       │   └── homology.py      # Transfer parameters from homologs
│       │
│       ├── solvers/             # Numerical solvers
│       │   ├── __init__.py
│       │   ├── ode.py           # ODE integrators (JAX-based)
│       │   ├── ode_scipy.py     # SciPy reference/fallback ODE solver (escape hatch for stiff systems)
│       │   ├── stochastic.py    # Gillespie / tau-leaping
│       │   └── hybrid.py        # Mixed deterministic-stochastic solver
│       │
│       ├── orchestrator/        # AI agent coordination layer
│       │   ├── __init__.py
│       │   ├── pipeline.py      # Main workflow: spec → SBML → implement → review
│       │   ├── panel.py         # Expert panel debate engine (multi-model)
│       │   ├── router.py        # Model routing: local (Ollama) vs cloud APIs
│       │   ├── contracts.py     # JSON Schema validation for data files
│       │   └── cost_tracker.py  # Per-call token/cost logging, budget alerts, CLI reports
│       │
│       ├── analysis/            # Post-simulation analysis
│       │   ├── __init__.py
│       │   ├── phenotype.py     # Phenotype prediction & comparison
│       │   ├── sensitivity.py   # Parameter sensitivity analysis (OAT, Morris, Sobol)
│       │   ├── knockout.py      # Gene knockout simulations
│       │   └── observation.py   # Observation model: map internal states → experimental assay readouts
│       │
│       └── viz/                 # Visualization
│           ├── __init__.py
│           ├── dashboard.py     # Interactive simulation dashboard
│           ├── timeseries.py    # Metabolite/protein time series plots
│           └── cell_cycle.py    # Cell cycle phase visualization
│
├── data/
│   ├── schemas/                 # JSON Schemas (data contracts)
│   │   ├── parameter_schema.json    # Enzyme parameter format
│   │   ├── gene_schema.json         # Gene annotation format
│   │   ├── reaction_schema.json     # Reaction definition format
│   │   └── simulation_config.json   # SED-ML-aligned sim config
│   ├── organisms/
│   │   ├── toy_cell/            # Toy model (~50 genes)
│   │   │   ├── genes.yaml       # Gene annotations (validated by gene_schema)
│   │   │   ├── reactions.yaml   # Reaction defs (validated by reaction_schema)
│   │   │   ├── parameters.yaml  # Kinetic params (validated by parameter_schema)
│   │   │   ├── model.sbml       # SBML Level 3 — machine-readable model
│   │   │   └── README.md
│   │   └── m_genitalium/        # Full M. genitalium
│   │       ├── genes.yaml
│   │       ├── reactions.yaml
│   │       ├── parameters.yaml
│   │       ├── model.sbml
│   │       └── README.md
│   └── external/                # Downloaded datasets (gitignored)
│       └── .gitkeep
│
├── notebooks/
│   ├── 01_quickstart.ipynb      # Getting started notebook
│   ├── 02_toy_cell.ipynb        # Toy cell walkthrough
│   ├── 03_parameter_sweep.ipynb # Parameter sensitivity
│   └── 04_drug_simulation.ipynb # Drug target simulation
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_metabolism.py
│   │   ├── test_transcription.py
│   │   ├── test_translation.py
│   │   ├── test_replication.py
│   │   ├── test_solvers.py
│   │   ├── test_ir.py           # Internal representation round-trips
│   │   └── test_contracts.py    # Schema validation tests
│   ├── property/                # Property-based tests (Hypothesis)
│   │   ├── test_conservation.py # Mass/energy conservation invariants
│   │   ├── test_sbml_roundtrip.py  # SBML import→export→import losslessness
│   │   └── test_schema_fuzz.py  # Fuzz testing for YAML/JSON parsers
│   ├── integration/
│   │   ├── test_toy_cell.py     # Full toy cell cycle
│   │   ├── test_coupled.py      # Sub-model coupling tests
│   │   └── test_orchestrator.py # Pipeline workflow tests
│   ├── regression/
│   │   ├── golden/              # Frozen-seed golden output snapshots
│   │   └── test_golden_runs.py  # Deterministic golden run comparison
│   ├── differential/
│   │   └── test_vs_scipy.py     # Cross-check our solvers vs SciPy/COPASI
│   ├── scientific/              # Scientific falsification tests (not just software invariants)
│   │   ├── test_metamorphic.py  # Metamorphic tests (e.g., 2x nutrients → ≥1.5x growth)
│   │   ├── test_synthetic_recovery.py  # Generate synthetic data from known params, recover them
│   │   └── test_rejection.py    # Failure envelope tests — verify model CAN'T produce impossible phenotypes
│   └── validation/
│       └── test_karr_comparison.py  # Compare to Karr 2012 results
│
├── benchmarks/
│   └── bench_solvers.py         # Performance benchmarks
│
└── .gitignore
```

---

## Implementation Phases

### Phase 1: Foundation (v1.0 — Weeks 1–3)
Set up project infrastructure, define the canonical runtime representation, build core simulation engine, validation harness, and data contracts. Orchestrator comes LAST — prove the science works manually first.

**1A — Repo & Environment Setup**
- **1.1** Initialize repository with project structure, packaging, CI/CD, Dockerfile, `uv.lock`
- **1.2** Dependency compatibility check — verify JAX, Diffrax, COBRApy, python-libsbml, Hypothesis, pint all install on Python 3.12. If any fail, identify fallback (build from source, pin older version, or use 3.11)
- **1.3** Set up pre-commit hooks: ruff + mypy + black
- **1.4** Data licensing audit (WEEK 0 — do first, before coding) — review KEGG, BRENDA, BioCyc, UniProt redistribution terms; document in `docs/data-licensing.md`; establish rules for fetch-scripts vs checked-in artifacts. If any source has blocking license terms, discover now, not Phase 4
- **1.5** Database access setup (start immediately, runs in parallel with other P1 work):
  - Register BRENDA account (free, academic email)
  - Check institutional BioCyc access or begin subscription (~$100-150/yr)
  - Download Karr 2012 parameter files from GitHub — our fallback data source if DB access is delayed
  - Configure cloud API keys (Anthropic, OpenAI, xAI, Google)
  - (Optional) Install Ollama + pull local models IF GPU available
- **1.6** Declare canonical environment — specify exact OS, Python version, JAX version, hardware profile for reproducibility. Local CPU vs Colab GPU will diverge subtly; document acceptable divergence thresholds
- **1.7** Write benchmark charter — define what constitutes FAILURE before writing any model code. What phenotype predictions, if wrong, would reject the model? Prevents optimizing toward easiest-to-match criteria

**1B — Internal Runtime Representation (IR)**
- **1.8** Implement `core/ir.py` — typed internal representation: species IDs, compartment enum, units, stoichiometry matrix (sparse), sub-model read/write permissions via resource allocation / partition-merge semantics (NOT write-exclusion — ATP, ribosomes, tRNAs are written by multiple sub-models). Design IR for extensibility: promoter states, partial complexes, and event queues will emerge; plan for explicit vs lumped vs rule-based state representation NOW
- **1.9** Implement `core/units.py` — pint-based unit registry. All values entering the IR must pass through unit validation. Catches unit errors at boundary, not deep in solver
- **1.10** Implement `core/compartments.py` — dynamic volume model, counts↔concentration conversions, compartment hierarchy
- **1.11** Implement `core/state.py` — cell state container backed by IR: JAX-compatible pytrees/arrays (data-oriented, not Python object graphs)
- **1.12** Implement `core/environment.py` — first-class media/environment model: nutrient concentrations, pH, temperature, growth medium composition. This is a runtime object, not a config parameter
- **1.13** Implement `core/resource_ledger.py` — global resource allocation: partition-merge semantics for shared metabolites (ATP, GTP, amino acids). Each sub-model requests resources; ledger allocates proportionally; reconciles at sync points. Based on Karr 2012 approach

**1C — Core Engine & Solvers**
- **1.14** Implement `core/engine.py` — main simulation loop with configurable time-stepping; explicit float64 policy via `jax.config.update("jax_enable_x64", True)`
- **1.15** Implement `solvers/ode.py` — JAX-based ODE integrator with adaptive stepping, stiff solver support (BDF/Radau)
- **1.16** Implement `solvers/ode_scipy.py` — SciPy reference implementation (solve_ivp with BDF). Escape hatch for stiff systems where JAX/Diffrax struggles. Also serves as correctness reference for differential testing
- **1.17** Implement `solvers/stochastic.py` — tau-leaping stochastic solver. Needed from day 1 for low-copy-number molecules (mRNA, transcription factors). NOT deferred to Phase 3
- **1.18** Implement `models/base.py` — abstract sub-model interface (initialize, evolve, validate), with declared state-slice read/write contracts via resource ledger. Sub-models declare what they CONSUME and PRODUCE; engine + ledger handle allocation
- **1.19** Build 2-model coupling benchmark — DummyProducer + DummyConsumer with shared state, operator splitting (Strang symmetric), mass conservation check, stiff-coupling stress test. NOTE: order-independence shuffle test may give false confidence — Strang splitting is only order-2 when operators commute. Document limitations

**1D — Reproducibility & Checkpoint**
- **1.20** Implement `core/manifest.py` — run manifest emitted at every run: git SHA, `uv.lock` hash, solver version, model/parameter checksums, RNG seeds (centralized PRNGKey schedule), hardware info, wall-clock metrics
- **1.21** Implement `core/checkpoint.py` — checkpoint/restart: serialize full state + RNG keys + solver internals to HDF5; resume from any checkpoint. NOTE: exact-restart claim is narrowed to same JAX/Diffrax/Python versions only — cross-version bitwise identity is not guaranteed

**1E — Data Layer & Contracts**
- **1.22** Implement `data/loader.py` — YAML/JSON parameter loading + SBML import
- **1.23** Implement `data/sbml_io.py` — SBML Level 3 import/export via `python-libsbml`. SBML is the interoperability format; internal IR is canonical. NOTE: SBML round-trip will be lossy for hybrid/stochastic/event semantics — document what survives and what doesn't
- **1.24** Define JSON Schemas for data contracts (`data/schemas/`) — enhanced with experimental conditions (temperature, pH, strain, growth medium), uncertainty distributions, DOI citations, and transformation provenance. Enforced by CI
- **1.25** Implement `orchestrator/contracts.py` — JSON Schema validation for all data files, called by CI and by pipeline before any data is committed
- **1.26** Set up data versioning — DVC or content-hashed snapshots for parameter files. Database parameters change over time; we need to know which version of BRENDA/KEGG data a result was computed against

**1F — Validation Harness & Resilience**
- **1.27** Build validation harness: conservation invariant checks, per-submodel timing, solver-step stats, structured event logs. NOTE: concrete biological validators (growth rate, essentiality) deferred to Phase 2 — can't test against unknown sub-model API
- **1.28** Set up tiered CI: fast PR checks (lint + unit + property tests), nightly scientific regression, release-grade benchmarks
- **1.29** Implement "no naked biology numbers" CI lint — AST/regex check that biological constants in model code reference a parameter ID, not a hardcoded literal. Allowlist: 0, 1, tolerances, array shapes. Tracks "estimated/borrowed parameter budget" per PR — increase requires explicit approval
- **1.30** Implement `core/guards.py` — runtime invariant monitors:
  - Concentrations/counts ≥ 0
  - Occupancies/fractions in [0,1]
  - Conserved moieties within tolerance
  - Stoichiometry net mass residual near zero
  - On first violation: log variable name, module, step, residual size (not just crash)
- **1.31** Implement `core/sentinels.py` — order-of-magnitude sanity checks. Define broad expected ranges for key variables (cell volume, ATP concentration, ribosome count, doubling time, transcription/translation rates). Catches 10x/1000x mistakes from unit errors, exponent slips, or hallucinated parameters. Ranges are intentionally loose — catch nonsense, not constrain science
- **1.32** Implement `core/crash_bundle.py` — on first NaN/Inf/assertion failure, capture diagnostic bundle: step index, simulation time, dt, RNG seed, solver stats (accepted/rejected steps), state norm, derivative norm, top-changed variables, violated invariant, last module executed, optional Jacobian condition estimate. Enables bug-class separation:
  - Exploding solver stats / tiny dt / bad conditioning → numerical bug
  - Invariant breaks but solver stats normal → biology/model logic bug
  - Abrupt impossible jump in one module → software bug
- **1.33** Implement single-step replay / delta ledger debug mode — replay exactly one step from checkpoint, print each module/reaction contribution to Δstate for any species. Shows: starting value → contributions by term/module → ending value → conservation residuals. Fastest path to answering "which module injected nonsense?"

**1G — Orchestrator (after science works manually)**
- **1.34** Implement `orchestrator/router.py` — ModelRouter with task-specific temperature policy (see Mandatory Policies)
- **1.35** Implement `orchestrator/panel.py` — ExpertPanel: evidence extractors + draft generators (NOT decision-makers). Panels produce claim graphs with evidence provenance and contradiction detection. Critical decisions require human approval + automated source verification (DOI exists + contains claimed value). Evidence snippets required: every nontrivial biological claim must store quoted excerpt with page/figure/table location alongside DOI. Non-participating moderator pattern included but unvalidated — will run ablation study after Phase 2 to verify it adds value
- **1.36** Implement `orchestrator/cost_tracker.py` — per-call token/cost logging to SQLite (`opencell_costs.db`), budget thresholds (warn at 50/75/90%), CLI: `opencell costs summary|by-phase|by-tier|by-role`
- **1.37** Implement `orchestrator/pipeline.py` — main workflow coordinator
- **1.38** Write `.github/copilot-instructions.md` — declarative agent rules
- **1.39** Implement `analysis/observation.py` — observation model: defines how internal simulation states map to experimental assay readouts (OD600 → biomass, qPCR → mRNA counts, etc.). Can't validate against experiments without this
- **1.40** Implement module I/O manifests — each sub-model declares: reads, writes, units, expected timescale, conserved quantities affected. CI checks for: undeclared writes, read/write unit mismatches, changed manifests without reviewer acknowledgement
- **1.41** Implement structured decision registry (`decisions/_decision_index.yaml`) with supersession lint — CI rule: if a PR changes behavior tied to an active decision, it must reference or supersede it. Prevents silent reversals across sessions
- **1.42** Define PR "assumption delta" checklist template — every biology/model PR must state: which assumptions changed, which parameters changed, which modules/species affected, which invariants re-run, whether estimated parameter count increased
- **1.43** Write tests for all Phase 1 components: unit, property-based (Hypothesis), SBML round-trip, schema fuzz, golden-run regression

### Phase 2: Toy Cell Sub-Models (v1.0 — Weeks 3–5)
Build a thin vertical slice for a minimal coupled-solver benchmark. Start with curated data → identifier mapping → units → environment, then implement 3 core sub-models (metabolism + transcription + translation). Division is CUT from toy cell — least tractable, unnecessary for demonstrating solver coupling. Additional sub-models (replication, degradation, transport) added only after the core 3 are coupled and working.

**Pre-Phase 2 Gate — Verify Access Ready:**
- [ ] BRENDA API access confirmed working
- [ ] BioCyc programmatic access confirmed (or fallback: use Karr 2012 data + UniProt only)
- [ ] Karr 2012 parameters loaded and schema-validated
- [ ] Cloud APIs tested end-to-end via router

**2A — Data Foundation (thin vertical slice — do FIRST)**
- **2.1** Build identifier reconciliation crosswalk — KEGG ↔ BioCyc ↔ UniProt ↔ GenBank mappings for toy cell gene/protein/metabolite set. This is a hidden blocker if deferred; identifier mismatches cause silent data errors
- **2.2** Curate toy cell parameters from literature (BRENDA, BioCyc, Karr 2012) — schema-validated via `contracts.py`. Every parameter must have: value, unit (pint-validated), source DOI, uncertainty distribution, experimental conditions
- **2.3** Minimal calibration/sensitivity spike — identify which parameters are structurally identifiable vs. practically identifiable vs. must be estimated; document in `docs/biology/calibration_notes.md`

**2B — Toy Cell Design**
- **2.4** Design toy cell gene set — Biology Expert Panel (cloud, evidence extraction mode) selects ~50 genes covering metabolism, transcription, and translation. Gene set must be designed to exercise: FBA+ODE coupling, stochastic+deterministic mixing, and at least one resource contention scenario. Frame honestly: this is a coupled-solver benchmark, not a biologically coherent organism
- **2.5** Define environment/media for toy cell — nutrient composition, uptake constraints, pH, temperature. Implemented via `core/environment.py`

**2C — Core Sub-Models (3 only, not 7)**
- **2.6** Implement `models/metabolism.py` — simplified metabolic network (glycolysis core)
  - Biology spec: `docs/biology/metabolism.md` + `decisions/metabolism.md`
  - Machine spec: `data/organisms/toy_cell/model.sbml` (metabolism section)
  - Michaelis-Menten kinetics; FBA via COBRApy treated as offline/episodic (NOT inside JAX inner loop)
  - FBA-ODE coupling contract: define sync frequency, what triggers re-solve, how fluxes are interpolated between FBA calls
  - Add thermodynamic feasibility checks: reaction directionality constraints, loopless FBA to prevent thermodynamically impossible cycles
- **2.7** Implement `models/transcription.py` — RNA polymerase-driven mRNA synthesis
  - Include polymerization primitive (RNAP elongation at nt/s, not instantaneous)
  - Stochastic for low-copy mRNAs (tau-leaping from Phase 1)
- **2.8** Implement `models/translation.py` — ribosome-driven protein synthesis
  - Include polymerization primitive (ribosome footprint, elongation at aa/s)
  - Resource contention: ribosomes are shared, allocated via resource ledger
- **2.9** Write unit tests for each sub-model in isolation + property-based invariant tests + metamorphic tests (e.g., double nutrients → growth should increase)
- **2.10** Per-sub-model OAT sensitivity analysis — vary each parameter ±10%, measure output change. Identifies which parameters each sub-model actually cares about. Takes minutes, guides curation priority: high-sensitivity params get careful curation, low-sensitivity params get rough estimates

**2D — Additional Sub-Models (after core 3 are coupled)**
- **2.11** Implement `models/degradation.py` — mRNA and protein turnover
- **2.12** Implement `models/transport.py` — simplified membrane transport
- **2.13** (DEFERRED from toy cell) `models/division.py` — added only in Phase 5 for M. genitalium. M. genitalium division biology is poorly understood (not FtsZ-driven), and division is unnecessary for demonstrating solver coupling
- **2.14** Write unit tests for additional sub-models

### Phase 3: Integration & Toy Cell Simulation (v1.0 — Weeks 5–7)
Couple sub-models and run complete toy cell benchmark. **Exit criterion: "publishable toy cell" — a standalone result demonstrating coupled solvers, resource allocation, and the framework architecture. This is v1.0.**

- **3.1** Define hybrid solver coupling scheme: operator splitting (Strang symmetric) with fixed synchronization points, explicit event ordering, resource allocation via ledger at each sync point. NOTE: Strang splitting is only order-2 accurate when operators commute; for stiff coupling, accuracy degrades. Document limitations and test with known analytical solutions
- **3.2** Implement sub-model coupling in engine (shared state via IR, time synchronization, resource allocation/partition-merge via ledger)
- **3.3** Implement `solvers/hybrid.py` — mixed deterministic-stochastic solver with the proven coupling scheme
- **3.4** Implement `core/events.py` — discrete events (replication initiation; division deferred to v2.0)
- **3.5** Run first complete toy cell benchmark simulation (with run manifest + checkpoint)
- **3.6** Build `viz/timeseries.py` and `viz/cell_cycle.py` for visualization
- **3.7** Write integration tests validating biological invariants:
  - Mass conservation, energy balance
  - Held-out phenotype checks: metabolite trends, RNA/protein ratios, ATP maintenance
  - Stochastic tests on distributions (not exact traces)
  - Metamorphic tests: 2x nutrients → growth increases; knock out essential gene → growth stops
  - Failure envelope tests: verify model CANNOT produce impossible phenotypes (negative concentrations, growth without nutrients)
- **3.8** Morris screening sensitivity analysis on coupled system — cheap global method (~100-200 simulations) that identifies important vs. unimportant parameters across the whole coupled model. Results directly guide Phase 4 parameter estimation priority
- **3.9** Create `notebooks/02_toy_cell.ipynb` tutorial
- **3.10** "Publishable toy cell" milestone gate — v1.0 release. Blog post, documentation, paper draft for JOSS or similar

### Phase 4: Data Pipeline & Parameter Estimation (v2.0 — Weeks 7–9)
Build automated data curation and ML-based parameter estimation. Gate: v1.0 must be complete first.

- **4.1** Implement `data/brenda.py` — BRENDA enzyme kinetics extraction
- **4.2** Implement `data/biocyc.py` — pathway and reaction data from BioCyc
- **4.3** Implement `data/kegg.py` — KEGG pathway mapping
- **4.4** Build full identifier reconciliation — KEGG ↔ BioCyc ↔ UniProt ↔ GenBank crosswalk for M. genitalium (~525 genes). Extend the toy cell crosswalk from 2.1
- **4.5** Implement `estimation/kinetics.py` — ML pipeline for missing parameter estimation. Parameters need uncertainty distributions (not point values); use parameter ensembles
- **4.6** Implement `estimation/homology.py` — transfer parameters from homologous organisms. WARNING: homology transfer is biologically dangerous — apply automatic confidence discounting (uncertainty penalty proportional to evolutionary distance). Never transfer at full confidence
- **4.7** Curate M. genitalium parameter set (automated + manual review, schema-validated). Auto-generate benchmark-delta reports whenever parameter data changes

### Phase 5: Scale to M. genitalium (v2.0 — Timeline TBD)
Expand all sub-models to full M. genitalium complexity. This is a separate project phase with its own timeline, gated on v1.0 success.

- **5.0** Karr reproduction study — before claiming to match Karr 2012 results, systematically understand what they did: which parameters they used, which approximations they made, which results they achieved (79% essentiality, not 80%). This is a research task, not a coding task
- **5.1** Expand metabolic network to full M. genitalium metabolism (~150 reactions)
  - Add thermodynamic feasibility: reaction directionality, loopless FBA
  - Add regime-switch modeling: stress responses, stalled metabolism, death states
- **5.2** Expand transcription model to all ~525 genes with regulation
- **5.3** Expand translation model with codon-level detail
  - CRITICAL: M. genitalium uses UGA as tryptophan (not stop codon). Translation model must handle non-standard genetic codes
- **5.4** Expand replication model with full chromosome
  - Add macromolecular machinery: replisome with polymerization primitive
- **5.5** Add protein complexes and macromolecular assembly
  - Decide state representation: explicit vs lumped vs rule-based for complexes and promoter states (decision from Phase 1 IR design)
- **5.6** Implement `models/division.py` — cell division for M. genitalium
  - Biology is poorly understood (not FtsZ-driven). Need explicit partitioning/segregation laws
  - Document scope limitations honestly
- **5.7** Implement `analysis/knockout.py` — gene essentiality predictions
- **5.8** Validate against Karr 2012 results AND orthogonal experimental data
  - Split fit targets from held-out validation targets
  - Growth rate, gene essentiality, metabolite levels
  - Observation model (`analysis/observation.py`) maps internal states to assay readouts
- **5.9** Performance optimization — JAX JIT compilation, CPU vectorization, optional GPU via Colab

### Phase 6: Analysis, Docs & Publication (v2.0 — Timeline TBD)
Polish for open-source release and academic publication.

- **6.1** Implement `analysis/sensitivity.py` — global parameter sensitivity analysis with uncertainty propagation (parameter ensembles, not just point values)
- **6.2** Implement `analysis/phenotype.py` — phenotype prediction pipeline
- **6.3** Build interactive dashboard (`viz/dashboard.py`)
- **6.4** Write comprehensive documentation (architecture, tutorials, API docs)
- **6.5** Create Jupyter notebook tutorials (quickstart, drug simulation)
- **6.6** Write paper draft (PLOS Computational Biology or Bioinformatics)
- **6.7** Benchmark performance vs. Karr 2012 MATLAB model
- **6.8** Release v2.0 on PyPI and GitHub

---

## Development Hardware Profile

| Component | Spec | Implication |
|---|---|---|
| **CPU** | Intel i7-10700 (8C/16T @ 2.9GHz) | No discrete GPU — local LLM inference will be slow (UNVERIFIED: est. 2-5 tok/s for 14B, needs benchmarking) |
| **RAM** | 64 GB DDR4 | Can load models up to ~32B quantized |
| **GPU** | Intel UHD 630 (integrated) | No CUDA — all LLM inference is CPU-only. Consider buying used RTX 3090 (~$300-400) if local models are needed |
| **Disk** | ~930 GB (E: drive) | Plenty for models (~50GB), datasets (~5GB), outputs (~50GB) |
| **Network** | Gigabit Ethernet | Fast enough for cloud API calls |

> ⚠️ **Honesty note**: CPU inference speed estimates above are NOT benchmarked. Actual performance may vary significantly. Cloud-first strategy recommended; local models are optional and only practical with a GPU.

---

## AI Agent Strategy: Cloud-First

### Design Principle
Use cloud frontier models for all AI agent tasks. Local models are optional and only recommended with a discrete GPU. AI panels are **evidence extractors and draft generators**, NOT scientific decision-makers — critical decisions require human approval with automated source verification.

### Tiered Model Routing

```
┌─────────────────────────────────────────────────────────────┐
│  TIER 1: Critical Decisions (cloud, multi-model panel)      │
│  Biology evidence extraction, architecture choices          │
│  Panel: Claude Opus + GPT-5 + Grok 3 → human approval      │
│  ~50 decisions across the project                           │
├─────────────────────────────────────────────────────────────┤
│  TIER 2: Standard Work (cloud, single model)                │
│  Sub-model code, tests, docs, parameter extraction          │
│  Writer: Sonnet/GPT-5 | Reviewer: different cloud model     │
│  ~200 tasks                                                 │
├─────────────────────────────────────────────────────────────┤
│  TIER 3: Routine Work (cloud, cheapest model)               │
│  Parse data, format YAML, schema validation, boilerplate    │
│  Agent: Haiku / GPT-4.1-mini                                │
│  ~2000+ tasks                                               │
├─────────────────────────────────────────────────────────────┤
│  TIER 4: Batch (cloud, cheapest model)                      │
│  Bulk format checks, linting, simple extractions            │
│  Agent: Haiku / GPT-4.1-mini                                │
│  ~500 tasks                                                 │
└─────────────────────────────────────────────────────────────┘

Estimated total LLM cost: NOT VERIFIED — rough estimate $300-600 based on
approximate token volumes. Will be refined after Phase 1 with actual usage data
from cost_tracker.py.
```

### Model-to-Role Assignment

| Role | Primary Model | Fallback/Panel | When |
|---|---|---|---|
| **Biology Expert Panel** | Claude Opus + GPT-5 + Grok 3 | Human approval required | Tier 1 — always multi-model |
| **Math Modeler Panel** | Claude Opus + DeepSeek R1 API | Human approval required | Tier 1 — always multi-model |
| **Software Engineer** | Sonnet / GPT-5 | Cross-model review (different model) | Tier 2 |
| **Data Curator** | Haiku / GPT-4.1-mini | Sonnet for complex extractions | Tier 3 |
| **Literature Agent** | Sonnet / GPT-5 | Gemini 2.5 Pro for long papers | Tier 2, task-specific temp |
| **Validator** | Sonnet / GPT-5 | Multi-model panel on disagreement | Tier 2 |
| **Code Review** | Different model than writer | — | Always cross-model |

### Local Model Option (GPU required)

Local models via Ollama are an optional cost optimization, practical only with a discrete GPU (e.g., RTX 3090). On CPU-only hardware (our current setup), 14B models run at an estimated 2-5 tok/s — too slow for interactive use. If a GPU is acquired:

```bash
# Install Ollama: https://ollama.com
# Pull models (~30GB total disk):
ollama pull phi4:14b          # ~8GB  — Tier 3/4 workhorse
ollama pull qwen3:14b         # ~8GB  — Tier 2 code generation
ollama pull gemma4:12b        # ~7GB  — Tier 3 literature/extraction

# Without GPU, consider smaller models:
ollama pull phi4-mini:3.8b    # ~2GB  — faster on CPU but lower quality
```

### Unified Model Router

```python
# opencell/agents/router.py
class ModelRouter:
    """Route tasks to cheapest model meeting quality requirements."""
    
    TIER_MODELS = {
        Tier.CRITICAL: [                          # Cloud multi-model panel
            "anthropic/claude-opus-4",
            "openai/gpt-5", 
            "xai/grok-3",
        ],
        Tier.STANDARD: [                          # Cloud single model + review
            "anthropic/claude-sonnet-4",           # writer
            "openai/gpt-5",                        # reviewer (always different)
        ],
        Tier.ROUTINE: ["anthropic/claude-haiku"],  # Cloud, cheapest
        Tier.BULK:    ["openai/gpt-4.1-mini"],     # Cloud, cheapest
    }
    
    def route(self, tier: Tier, needs_web=False, needs_long_ctx=False):
        if needs_web:   return "xai/grok-3"       # built-in search
        if needs_long_ctx: return "google/gemini-2.5-pro"  # 1M context
        return self.TIER_MODELS[tier]
```

### Expert Panel Architecture

For Tier 1 biological decisions, we run a multi-model evidence extraction panel. **Panels are evidence extractors and draft generators, NOT scientific decision-makers.** Critical decisions require human approval.

```
Question: "What kinetic law for glucose-6-phosphate isomerase?"
    │
    ├──► Claude Opus (persona: "Biochemist")     ──► Evidence + citations + uncertainty
    ├──► GPT-5 (persona: "Systems Biologist")    ──► Evidence + citations + uncertainty
    ├──► Grok 3 (persona: "Geneticist" + web)    ──► Evidence + citations + uncertainty
    │
    └──► Moderator (NON-PARTICIPATING model, e.g., Gemini 2.5 Pro):
         Synthesize evidence into claim graph:
           - Claims with supporting/contradicting DOIs
           - Contradiction detection (flag conflicting evidence)
           - Confidence assessment per claim
           - Draft recommendation for human review
         
         AUTO-VERIFY: Check that cited DOIs exist and contain claimed values
         FLAG FOR HUMAN: if citations are weak, missing, or conflicting
```

> ⚠️ **Unvalidated pattern**: The non-participating moderator design has no published evidence that it outperforms simple majority vote or weighted averaging. We will run an ablation study after Phase 2 to verify it adds value. If not, simplify to majority vote + human review.

Panel outputs are structured as **claim graphs**:
```yaml
claims:
  - claim: "G6PI follows ordered Bi-Bi mechanism in M. genitalium"
    evidence_for:
      - doi: "10.1016/..."
        excerpt: "Kinetic analysis showed ordered sequential mechanism"
        species: "M. genitalium"
        conditions: {temp: 37, pH: 7.4}
    evidence_against:
      - doi: "10.1074/..."
        excerpt: "Random mechanism observed in E. coli homolog"
        species: "E. coli"
    confidence: 0.7
    recommendation: "Use ordered Bi-Bi; flag for experimental verification"
    human_approved: false  # MUST be true before implementation
```

Panel decisions are versioned with invalidation triggers. A decision is re-debated ONLY when:
- New literature contradicts the original evidence (Literature Agent flags)
- Schema or IR changes affect the decision scope
- Validation tests fail in ways traced to the decision
- Organism scope changes (e.g., scaling from toy cell to M. genitalium)

### Cost Estimate (UNVERIFIED — will be refined with actual data)

> ⚠️ **Honesty note**: These cost estimates are rough approximations based on assumed token volumes and current API pricing. No arithmetic has been verified against actual usage. The cost_tracker.py module will provide real data after Phase 1. Treat these as order-of-magnitude guides, not budgets.

| Category | Est. Volume | Est. Cost | Confidence |
|---|---|---|---|
| Biology panels (Tier 1) | ~50 decisions, ~7K tokens each | ~$150-300 | Low — depends on panel rounds |
| Math panels (Tier 1) | ~20 decisions, ~7K tokens each | ~$50-100 | Low |
| Implementation (Tier 2) | ~200 tasks, ~4K tokens each | ~$50-100 | Low |
| Data curation (Tier 3) | ~2000 tasks, ~1.5K tokens each | ~$2-5 | Medium — cheapest tier |
| Batch (Tier 4) | ~500 tasks, ~1K tokens each | ~$1-3 | Medium |
| **Total** | | **~$250-500** | **Low — refine after Phase 1** |

---

## Agent Communication: Dual-Format Specs

### Principle
Biology decisions are documented in **two formats**: human-readable markdown (rationale, literature references, trade-offs) and machine-readable SBML (exact reactions, kinetics, parameters). The Software Engineer implements from SBML — no ambiguity, no translation errors.

### Spec Flow

```
Biology Expert Panel (cloud, Tier 1)
    │
    ├──► decisions/metabolism.md        ← WHY: rationale, literature, trade-offs
    │                                      (human-reviewed, cached, never re-debated)
    │
    └──► data/organisms/toy_cell/model.sbml  ← WHAT: exact reactions, kinetics
         (auto-generated from panel decision, machine-readable)
              │
              ├──► Data Curator (local, Tier 3): fills in parameter values
              │    → data/organisms/toy_cell/parameters.yaml (schema-validated)
              │
              └──► Software Engineer (local, Tier 2): implements from SBML + params
                   → src/opencell/models/metabolism.py
                        │
                        └──► Cross-Model Reviewer (cloud, Tier 2): reviews code
```

### Standards Used

| Data Type | Standard | Format | Validator |
|---|---|---|---|
| Reactions & kinetics | SBML Level 3 | XML + MathML | `python-libsbml` |
| Metabolic networks | SBML-FBC | XML | COBRApy |
| Simulation config | SED-ML | XML | `libsedml` |
| Gene annotations | UniProt/GenBank | TSV/FASTA | BioPython |
| Internal parameters | Custom (YAML) | YAML | JSON Schema (CI-enforced) |
| Simulation output | HDF5 | Binary | Schema-validated |

---

## Conflict Resolution Protocol

### Principle
**Biology is the primary source of truth, but model assumptions remain falsifiable.** If a numerically unstable ODE system is biologically correct, we fix the numerics — not the biology. However, literature biology is often incomplete, contradictory, or context-specific. When data disagree, we log contradictions, test alternatives empirically, and update assumptions based on evidence.

### Resolution Ladder

```
Level 1: Math Modeler adapts the solver (~80% of conflicts)
  ├── Stiff system → switch to implicit solver (BDF/Radau)
  ├── Timescale mismatch → quasi-steady-state approximation
  └── No biology changes needed

Level 2: Controlled simplification (~15% of conflicts)
  ├── Biology Researcher APPROVES a specific approximation
  ├── e.g., "You may lump these 3 fast reactions into one"
  ├── e.g., "You may use Hill function instead of full cooperativity"
  └── Approval documented in decisions/ with justification

Level 3: Empirical arbitration (~4% of conflicts)
  ├── Implement BOTH approaches
  ├── Simulate both, compare to experimental phenotype data
  └── Whichever matches real data better wins

Level 4: Human escalation (~1% of conflicts)
  ├── Present trade-off to user with clear options
  └── User decides, decision cached in decisions/
```

### Rules
- Math Modeler may NEVER silently change biology
- All approximations require Biology panel approval
- All conflict resolutions are documented in `decisions/` with rationale
- Resolved conflicts are cached — same conflict is never re-adjudicated

---

## Data Contracts (JSON Schemas)

### Principle
Every data file produced by any agent must pass schema validation before it can be committed. CI rejects malformed data. This prevents agents from breaking each other's assumptions.

### Parameter Schema (example)

```yaml
# data/organisms/toy_cell/parameters.yaml
schema_version: "1.0"
organism: "toy_cell"
parameters:
  - enzyme: "glucose_6_phosphate_isomerase"
    ec_number: "5.3.1.9"
    kinetic_law: "michaelis_menten"
    km:
      value: 0.5
      unit: "mM"
      source: "BRENDA"          # BRENDA | BioCyc | literature | estimated
      evidence: "direct"        # direct | homology | estimated
      doi: "10.1016/j.jbc.2003.08.012"  # Citation for this measurement
      uncertainty:
        distribution: "lognormal"  # normal | lognormal | uniform
        cv: 0.3                    # Coefficient of variation
    vmax:
      value: 120.0
      unit: "µmol/min/mg"
      source: "estimated"
      method: "homology"
    conditions:                  # Experimental context of measurement
      temperature_C: 37.0
      pH: 7.4
      strain: "M. genitalium G37"
      growth_medium: "SP-4"
    confidence: 0.85            # 0.0–1.0, how reliable this value is
    provenance:                  # How this value was derived
      raw_value: 125.0
      normalization: "per_mg_protein"
      transformation: "Lineweaver-Burk fit"
```

### JSON Schema (enforced by CI)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["schema_version", "organism", "parameters"],
  "properties": {
    "parameters": {
      "type": "array",
      "items": {
        "required": ["enzyme", "ec_number", "kinetic_law"],
        "properties": {
          "enzyme": { "type": "string" },
          "ec_number": { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+\\.\\d+$" },
          "kinetic_law": { "enum": ["michaelis_menten", "hill", "mass_action", "allosteric"] },
          "km": {
            "type": "object",
            "required": ["value", "unit", "source"],
            "properties": {
              "value": { "type": "number", "minimum": 0 },
              "unit": { "type": "string" },
              "source": { "enum": ["BRENDA", "BioCyc", "literature", "estimated"] },
              "evidence": { "enum": ["direct", "homology", "estimated"] }
            }
          },
          "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
        }
      }
    }
  }
}
```

### Validation Pipeline

```
Agent produces data file
    │
    ├──► contracts.py validates against JSON Schema
    │    ├── Pass → file accepted
    │    └── Fail → rejected with specific error, agent must fix
    │
    └──► CI (schema-validate.yml) runs on every PR
         └── Blocks merge if any data file fails validation
```

---

## Orchestrator: Workflow Coordination

### Two-Layer Architecture

**Layer 1: `.github/copilot-instructions.md`** (declarative rules, lives in repo)

Ensures any Copilot session on the repo automatically knows the workflow:
- Agent role definitions and boundaries
- Workflow constraints (no implementation without biology spec)
- Conflict resolution protocol reference
- Data contract requirements

**Layer 2: `orchestrator/pipeline.py`** (imperative coordination)

Encodes the full sub-model build workflow:

```python
class OpenCellOrchestrator:
    """Coordinates the agent workflow for building sub-models."""
    
    async def build_submodel(self, name: str):
        # Step 1: Biology panel decides modeling approach (Tier 1, cloud)
        spec = await self.biology_panel.deliberate(
            f"How should we model {name} in a minimal cell?"
        )
        save_decision(f"decisions/{name}.md", spec)
        
        # Step 2: Generate SBML from decision (Tier 2)
        sbml = await self.math_modeler.formulate(spec)
        validate_sbml(sbml)  # libsbml validation
        
        # Step 3: Curate parameters (Tier 3, local)
        params = await self.data_curator.extract(spec.enzymes)
        validate_schema(params, "parameter_schema.json")  # contract check
        
        # Step 4: Implement code (Tier 2, local)
        code = await self.engineer.implement(sbml, params)
        
        # Step 5: Cross-model review (Tier 2, cloud — different model than writer)
        review = await self.reviewer.review(code, spec)
        if review.has_issues:
            code = await self.engineer.revise(code, review)
        
        # Step 6: Validate (Tier 2)
        results = await self.validator.test(name)
        
        return results
```

### Invocation

```bash
# Build a single sub-model end-to-end:
python -m opencell.orchestrator build metabolism

# Run the full pipeline for all toy cell sub-models:
python -m opencell.orchestrator build-all --organism toy_cell

# Re-run just the data curation step:
python -m opencell.orchestrator curate --organism toy_cell --submodel metabolism
```

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python 3.12 | Best scientific ecosystem; 3.14 too new for JAX/COBRApy wheels |
| Compute strategy | JAX (CPU mode, float64) + SciPy reference/fallback + Colab/cloud GPU fallback | JIT compilation works on CPU; SciPy for stiff escapes; GPU via Colab for heavy runs |
| Floating point | float64 mandatory for core integrators | JAX defaults to float32 which causes stiff ODE instability |
| RNG discipline | Centralized PRNGKey schedule | Deterministic per-module/per-timestep key splitting, never naive seeds |
| Data architecture | Data-oriented (JAX pytrees, sparse arrays) | Avoids Python object graph overhead; enables JIT and vectorization |
| Internal representation | Typed IR (`core/ir.py`) — canonical in-memory model | SBML is import/export format, not source of truth. Designed for extensibility (promoter states, complexes) |
| State coupling | Resource allocation / partition-merge via global ledger | NOT write-exclusion — ATP, ribosomes, tRNAs are written by multiple sub-models (Karr 2012 approach) |
| Unit handling | pint library at IR boundary | Catches unit errors at data entry, not deep in solver |
| SBML role | Interoperability format (import/export, lossy) | SBML cannot represent all hybrid/stochastic/event behavior cleanly; round-trip is lossy |
| FBA strategy | Offline/episodic COBRApy, outside JAX inner loop | Crossing Python↔JAX per timestep kills JIT and performance |
| FBA-ODE coupling | Defined sync frequency, re-solve triggers, flux interpolation | Concrete contract, not vague "operator splitting" |
| Thermodynamic feasibility | Reaction directionality + loopless FBA | Prevents thermodynamically impossible cycles |
| Hybrid solver coupling | Strang symmetric operator splitting + sync points + resource reconciliation | Order-2 accurate when operators commute; limitations documented |
| Environment model | First-class runtime object (`core/environment.py`) | Media composition, nutrients, pH, temperature — not just config params |
| Observation model | Maps internal states → experimental assay readouts | Can't validate without this; OD600 → biomass, qPCR → mRNA |
| AI agent infra | Cloud-first via direct API calls; Ollama optional with GPU | No framework overhead; local models impractical on CPU-only hardware |
| Agent role | Evidence extractors + draft generators, NOT decision-makers | Critical decisions require human approval + automated DOI verification |
| Agent orchestration | Custom ModelRouter + ExpertPanel (claim graphs) + Pipeline | Tier-based routing, evidence provenance, contradiction detection |
| Agent temperature | Task-specific (see Mandatory Policies) | Determinism for code/extraction; diversity for literature search |
| Agent communication | Dual-format: Markdown (rationale) + SBML (machine spec) | Human review + machine interoperability |
| Expert panel moderator | Non-participating model (unvalidated — ablation study planned) | Prevents moderator bias; will verify adds value after Phase 2 |
| Decision versioning | Versioned with invalidation triggers + claim graphs | Prevents stale decisions; re-debated only when evidence changes |
| Conflict resolution | Biology-primary with 4-level escalation ladder | Matches real-world systems biology; assumptions remain falsifiable |
| Data contracts | JSON Schema (CI-enforced) + experimental conditions | Prevents agents from breaking each other; includes DOI, uncertainty, provenance |
| Data versioning | DVC or content-hashed snapshots | Database parameters change over time; need version tracking |
| Parameter uncertainty | Distributions + ensembles, not just point values | Structural/practical identifiability checks required |
| Homology transfer | Automatic confidence discounting by evolutionary distance | Prevents false confidence from distant homologs |
| Model exchange format | SBML Level 3 (lossy import/export) | Industry standard, interoperable with COPASI, Tellurium, COBRApy |
| Simulation description | SED-ML | Standard for reproducible simulation experiments |
| Metabolic modeling | COBRApy + custom kinetics | FBA for steady-state, kinetic for dynamics |
| ODE solver | Diffrax (JAX) + SciPy fallback (ode_scipy.py) | JAX for speed, SciPy for correctness reference and stiff fallback |
| Stochastic solver | Custom tau-leaping (Phase 1, not Phase 3) | For low-copy-number molecules; needed from day 1 |
| Sensitivity analysis | OAT (Phase 2, per sub-model) → Morris (Phase 3, coupled) → Sobol (Phase 6, publication) | Early sensitivity guides curation priority; don't over-invest in insensitive params |
| Data format | YAML for parameters, HDF5 for simulation output + checkpoints | Human-readable config, efficient storage + restart |
| Reproducibility | Run manifests + checkpoint/restart + locked dependencies + canonical environment | Publication-grade reproducibility; cross-version divergence documented |
| Testing strategy | Unit + property (Hypothesis) + golden-run + differential + stochastic + metamorphic + synthetic recovery + failure envelope | Multi-layered: correctness, invariants, regression, cross-validation, scientific falsification |
| Runtime guards | Positivity, bounds, conservation monitors + order-of-magnitude sentinels | Catch numerical instability, hallucinated params, unit errors at runtime |
| Crash diagnostics | First-bad-step crash bundle + single-step replay/delta ledger | Rapid triage: numerical vs biology vs software bug |
| Anti-hallucination | No naked biology numbers lint + evidence snippets + DOI verification | Prevents smuggling invented params into code; requires quoted evidence |
| Cross-session coherence | Structured decision registry + supersession lint + PR assumption delta checklist | Prevents silent reversals, forgotten decisions, context misses |
| CI/CD tiering | Fast PR checks, nightly scientific regression, release benchmarks | Prevents flaky CI while ensuring scientific correctness |
| Packaging | pyproject.toml (PEP 621) + uv for locking | Modern Python standard with reproducible installs |
| CI/CD | GitHub Actions | Free for open source |
| Pre-commit | ruff + mypy + black | Catches style/type issues before CI |
| Docs | MkDocs + Material theme | Clean, searchable, auto-deploys |
| License | Apache 2.0 | Permissive, patent protection |
| Deliverable split | v1.0 = framework + toy cell; v2.0 = M. genitalium | Independent milestones; v1.0 is publishable standalone |

---

## Biological Sub-Models Summary

| Sub-Model | Mathematical Framework | Key Outputs |
|-----------|----------------------|-------------|
| Metabolism | FBA + Michaelis-Menten ODEs | Metabolite concentrations, ATP/energy |
| Transcription | Stochastic (low copy) + ODE (high copy) | mRNA counts per gene |
| Translation | ODE with ribosome dynamics | Protein counts per gene |
| DNA Replication | Discrete event + ODE | Replication fork position, completion |
| Degradation | First-order kinetics | mRNA/protein half-lives |
| Transport | Michaelis-Menten | Nutrient uptake, waste export |
| Cell Division | Discrete event triggered by size/DNA | Two daughter cells |

---

## Rejected Alternatives

### LangChain / LangGraph — NOT USED

| Concern | Impact on OpenCell |
|---|---|
| **Abstraction mismatch** | They orchestrate LLM conversations, not scientific computations. Our agents route biological decisions, not chat flows |
| **Determinism** | Designed for creative/flexible agent behavior. We need temperature=0, reproducible, auditable decisions |
| **Runtime overhead** | Graph traversal and state management consume memory/CPU we need for simulation |
| **Security** | Critical vulnerabilities disclosed (March 2026 "LangDrained"). Unacceptable for a scientific project |
| **Dependency weight** | Massive dependency tree on top of our already heavy science stack (JAX, COBRApy, Diffrax) |
| **Overkill** | Our workflow is a linear pipeline with branching on failure — not a complex agent negotiation graph |

**What we need is simpler:**
```
Biology Spec (YAML/SBML) → Math Model → Code (Python/JAX) → Validate → Done
```

Our custom `pipeline.py` + `router.py` + direct API calls (via `httpx`) gives us full control over determinism, reproducibility, audit trails, and zero framework overhead. If agent complexity grows to 20+ roles with dynamic negotiation, we'll reconsider — but that's a stretch goal problem.

### Other Rejected Frameworks

| Framework | Why Rejected |
|---|---|
| **CrewAI** | Higher-level than LangGraph but same category — chat agent orchestration, not scientific pipeline |
| **AutoGen** | Microsoft's multi-agent framework — good for conversational agents, wrong abstraction for simulation |
| **Semantic Kernel** | .NET-centric, C# focus — doesn't fit our Python/JAX stack |
| **LlamaIndex** | RAG-focused — useful for literature search but not for agent orchestration |

---

## Mandatory Policies

These are non-negotiable engineering constraints applied across the entire project.

### Honesty & Credibility
- **Mark estimates vs. facts**: Every quantitative claim in the plan must be labeled as VERIFIED (benchmarked/cited) or UNVERIFIED (estimate). Do not present guesses as facts
- **Say "I don't know"**: When data is unavailable, state that explicitly rather than inventing plausible numbers
- **Benchmark before claiming**: Performance numbers, cost estimates, and timing projections must be measured, not assumed

### Determinism & Reproducibility
- **Temperature policy is task-specific**, not universal:
  - `temp=0` for: code generation, parameter extraction, schema validation, format conversion (maximum determinism)
  - `temp=0.3-0.5` for: literature search, evidence gathering (some diversity helps find more sources)
  - `temp=0` for: expert panel synthesis, conflict resolution, decision drafts (reproducible reasoning)
  - All temperature settings are logged in cost_tracker.py for audit
- **float64 mandatory** for all numerical core code: `jax.config.update("jax_enable_x64", True)` set at module import
- **Centralized RNG**: Single root `jax.random.PRNGKey(seed)` → deterministic splitting per module, per timestep. Never `numpy.random.seed()` or `random.seed()` in core code
- **Run manifests**: Every simulation run emits: git SHA, `uv.lock` hash, solver version, model checksum, parameter checksum, all RNG seeds, hardware info, wall-clock timing, AI decision-set version
- **Locked dependencies**: `uv.lock` committed to repo. `pip install` from lockfile only in CI
- **Checkpoint/restart**: All long runs checkpoint state + RNG keys + solver internals to HDF5. Resume from any checkpoint. NOTE: exact-restart claim narrowed to same JAX/Diffrax/Python versions only
- **Canonical environment**: One declared reference environment (OS, Python version, JAX version, hardware) for reproducibility claims. Divergence on other platforms (e.g., Colab GPU) must be characterized and documented

### AI Agent Discipline
- **Panels are evidence extractors, NOT decision-makers** — critical decisions require human approval
- **Automated source verification**: DOI exists AND contains claimed value (spot-check automated, full verification for Tier 1)
- **Claim graphs**: Panel outputs structured as claims with evidence for/against, confidence scores, and contradiction detection
- **Store full prompts, model IDs, raw outputs** for every LLM call — cloud models change over time
- **Non-participating moderator** in expert panels — moderator model never also serves as panelist (unvalidated pattern; ablation study after Phase 2)
- **Human review triggered** automatically when panel citations are weak, missing, or conflicting
- **Decision invalidation**: Decisions are versioned; re-debated when triggers fire (new literature, failed tests, scope change)

### Data Governance
- **License audit** for every data source before inclusion (WEEK 0 — KEGG, BRENDA, BioCyc, UniProt)
- **Data versioning**: DVC or content-hashed snapshots for all parameter files. Auto-generate benchmark-delta reports when data changes
- **Fetch scripts** for restricted data — never check in data with redistribution restrictions
- **Provenance records**: Every parameter traces back to: raw value, normalization, transformation, source DOI, experimental conditions
- **Schema versioning**: Migration strategy for when schemas change; version field in all data files
- **Identifier reconciliation**: KEGG ↔ BioCyc ↔ UniProt ↔ GenBank crosswalk maintained as first-class artifact
- **Homology transfer**: Automatic confidence discounting proportional to evolutionary distance. Never full-confidence transfer

### Code Quality
- **Pre-commit hooks**: ruff + mypy + black — no code enters repo without passing
- **Tiered CI**: Fast PR checks (lint + unit + property) → nightly scientific regression → release benchmarks
- **Scientific falsification tests**: Metamorphic tests, synthetic-data recovery, failure envelope tests — not just software invariants
- **SemVer**: CHANGELOG.md with Keep a Changelog format; deprecation timeline for public APIs
- **Structured logging**: Per-submodel timing, solver-step stats, conservation residuals, agent decision audit logs

---

## Cross-Model Audit Findings

### Round 1 (April 2026) — Claude Opus 4.6 + GPT-5.2

Plan reviewed independently by Claude Opus 4.6 and GPT-5.2. Key converging findings (both reviewers agreed) and how we addressed them:

#### Blocking Issues — Addressed

| Finding | Both? | Resolution |
|---|---|---|
| No canonical runtime representation | ✅ | Added `core/ir.py` — typed IR with species IDs, compartments, units, stoichiometry, r/w permissions |
| Hybrid solver coupling too vague | ✅ | Specified operator splitting + sync points + mass-balance reconciliation; must prove on toy benchmarks first |
| Reproducibility underspecified | ✅ | Added run manifests, checkpoint/restart, centralized RNG, locked dependencies — all in Phase 1 |
| FBA inside JAX is a perf trap | Opus | FBA is now offline/episodic, outside JAX inner loop |
| Data licensing not addressed | ✅ | Added data governance section + license audit in Phase 1 |
| "Biology is ground truth" too absolute | Opus | Changed to "biology-primary but falsifiable" with contradiction logs |

#### High-Priority Gaps — Addressed

| Finding | Resolution |
|---|---|
| Orchestrator too early, validation too late | Phase 1 reordered: IR → engine → reproducibility → validation → THEN orchestrator |
| JAX defaults float32 | Mandatory float64 policy added |
| RNG discipline missing | Centralized PRNGKey schedule added |
| SBML can't be sole source of truth | IR is canonical; SBML is import/export |
| Parameter schema too weak | Added: conditions, DOI, uncertainty distributions, provenance |
| Decision cache unsafe | Versioned decisions with invalidation triggers |
| Testing too narrow | Added: property-based (Hypothesis), golden-run, differential, stochastic, SBML round-trip |
| No checkpoint/restart | Added to Phase 1 core |
| AI panel false consensus risk | Non-participating moderator, mandatory citations, weak-source flagging |
| No volume/compartment model | Added `core/compartments.py` |
| Missing project governance | Added GOVERNANCE.md, SECURITY.md, CHANGELOG.md |

#### Accepted but Deferred

| Finding | Disposition |
|---|---|
| "Orchestrator should be a separate package" | Keep in-tree during dev; extract later if needed (Stretch Goal C) |
| "Move parameter estimation earlier" | Minimal calibration spike added to Phase 2; full estimation stays in Phase 4 |
| "CPU-only local inference may bottleneck" | Cloud-first strategy adopted; local models optional with GPU |
| "20-week timeline optimistic" | Deliverable split: v1.0 (toy cell) with open timeline, v2.0 (M.gen) timeline TBD |

### Round 2 (April 2026) — GPT-5.4 + Claude Opus 4.7

Second independent review by GPT-5.4 and Claude Opus 4.7. 54 total findings across both rounds; 23 were initially missed in synthesis and later recovered through systematic cross-check.

#### Blocking Issues — Addressed

| Finding | Reviewer(s) | Resolution |
|---|---|---|
| Write-exclusion is wrong — ATP, ribosomes, tRNAs written by multiple sub-models | Both | Replaced with resource allocation / partition-merge semantics via `core/resource_ledger.py` (Karr 2012 approach) |
| AI panels are NOT scientific decision-makers — correlated errors from temp=0 | Both | Demoted to evidence extractors + draft generators; critical decisions require human approval + automated DOI verification |
| No uncertainty/identifiability program — parameters need distributions | GPT-5.4 | Added uncertainty distributions to parameter schema; structural/practical identifiability checks in calibration spike (2.3) |
| Missing essential biology — polymerization primitives (RNAP, ribosome, replisome) | Both | Added polymerization primitives to transcription (2.7), translation (2.8), and replication (5.4) |
| Validation anchored to Karr, not reality | Both | Split fit targets from held-out validation; added orthogonal experimental data requirement; observation model added |
| 80% essentiality target harder than it sounds — Karr only achieved 79% | Opus 4.7 | Added Karr reproduction study (5.0) before claiming match; tightened success criteria |

#### High-Priority Issues — Addressed

| Finding | Resolution |
|---|---|
| Timeline 20 weeks is 5-10x too short for M.gen | Split: v1.0 (framework + toy cell), v2.0 (M.gen with TBD timeline) |
| Stochastic solver belongs in Phase 1 | Moved tau-leaping to Phase 1 (1.17) |
| No unit handling | Added pint library at IR boundary from day 1 (1.9) |
| No environment/media model | Added `core/environment.py` as first-class runtime object (1.12) |
| No observation model | Added `analysis/observation.py` — state-to-assay mapping (1.34) |
| No thermodynamic feasibility checks | Added loopless FBA + reaction directionality (2.6) |
| FBA-ODE coupling needs concrete contract | Defined sync frequency, triggers, interpolation in 2.6 |
| Build SciPy reference alongside JAX | Added `solvers/ode_scipy.py` (1.16) |
| No data versioning | Added DVC or content-hashed snapshots (1.26) |
| Toy cell is coupled-solver benchmark, not biological cell | Framed honestly throughout Phase 2; gene set exercises solver coupling, not biology |
| Temperature=0 may hurt literature search diversity | Made temperature task-specific (see Mandatory Policies) |
| M.gen uses UGA as tryptophan (not stop codon) | Flagged in translation model (5.3) |
| Task numbering duplicates (1.4, 1.5, 1.10) | Fixed — all tasks now uniquely numbered |
| 14B local models on CPU = 2-5 tok/s, not 8-12 | Switched to cloud-first strategy; local models optional with GPU |
| Cut division from toy cell | Division deferred to Phase 5 (M.gen only) |
| Karr reproduction study needed before claiming match | Added as Phase 5.0 prerequisite |
| Start with thin vertical slice, not 7 submodels | Phase 2 restructured: data→IDs→units→env→3 core submodels |
| Success criteria are gameable | Added rejection criteria + failure envelopes in testing |
| Define benchmark charter before coding | Added as Phase 1 task (1.7) |
| Redesign agents around claim graphs + evidence provenance | Expert panel outputs structured as claim graphs with DOI verification |
| Validation harness before sub-models = testing unknown API | Concrete biological validators deferred to Phase 2 |
| Reduce first target to 3 submodels (metab + txn + tln) | Phase 2 restructured: core 3 first, additional 2 after coupling works |

#### Medium-Priority Issues — Addressed

| Finding | Resolution |
|---|---|
| Operator splitting order-independence test unreliable for stiff coupling | Documented limitation; Strang splitting accuracy degrades when operators don't commute |
| Division biology under-specified for M.gen (not FtsZ-driven) | Division deferred to v2.0; scope limitations documented in 5.6 |
| Non-participating moderator pattern unvalidated | Ablation study planned after Phase 2 |
| Cost estimate has no arithmetic | Marked as UNVERIFIED; will refine with actual data from cost_tracker.py |
| Data licensing audit too late | Moved to Week 0 (Phase 1, task 1.4) |
| No regime-switch / failure-state modeling | Added to Phase 5 (5.1) — stress responses, death states |
| Tests focus on software, not scientific falsification | Added metamorphic, synthetic-data recovery, and failure envelope tests |
| No governance for curation/model edits | Added benchmark-delta reports on data changes; DVC versioning |
| Reproducibility drift across environments | Added canonical environment declaration (1.6) |
| State representation may explode at scale | IR designed for extensibility; explicit/lumped/rule-based decision in Phase 1 |
| IR rigidity risk | IR designed with growth in mind; promoter states, complexes anticipated |
| Homology parameter transfer dangerous without penalties | Added automatic confidence discounting by evolutionary distance |
| Identifier reconciliation is hidden blocker | Moved to Phase 2 (2.1), before any parameter curation |
| Checkpoint fragile across Diffrax versions | Exact-restart claim narrowed to same versions only |
| Growth rate "within 2x" too loose | Tightened (see Success Criteria) |
| SBML round-trip lossy | Documented what survives and what doesn't (1.23) |
| Visualization under-scoped | Acknowledged; will expand after v1.0 if needed |

---

## Success Criteria

### v1.0 (Framework + Toy Cell Benchmark)
1. **Toy cell benchmark runs** — coupled metabolism + transcription + translation with resource allocation, producing biologically plausible trajectories
2. **Mass and energy conservation** — no matter/energy created or destroyed (validated by property-based tests)
3. **Solver coupling demonstrated** — FBA+ODE, stochastic+deterministic, resource contention all working
4. **Reproducible** — deterministic mode gives identical results across runs (golden-run tests); stochastic mode gives consistent distributions
5. **Run manifest emitted** — every run produces a complete provenance record
6. **Checkpoint/restart works** — can resume any simulation from checkpoint (same-version only)
7. **Extensible** — adding a new sub-model requires only implementing the base interface + IR state slice + ledger registration
8. **Framework published** — v1.0 released on GitHub (sdrona-ms/opencell) with docs, tests, blog

### v2.0 (M. genitalium — Separate Phase, TBD Timeline)
9. **M. genitalium gene essentiality** — compare against Karr 2012 results and experimental data. NOTE: Karr achieved 79%; our target is ≥75% (not 80%, which would require outperforming the original). Failure envelope: if essentiality falls below 60%, model is rejected
10. **Growth rate prediction** — within ±30% of measured doubling time (~12h) OR acknowledge as qualitative if data uncertainty is too high. Previous "2x" criterion (6-32h range) was too loose
11. **Performant** — full M. genitalium cell cycle in <30 minutes on CPU, <10 minutes on GPU (Colab) [UNVERIFIED estimate]
12. **Observation model works** — can map internal states to at least 3 distinct experimental assay readouts
13. **Published** — accepted in a peer-reviewed journal

### Rejection Criteria (what constitutes FAILURE)
- Negative concentrations or negative molecule counts in simulation output
- Growth in absence of essential nutrients
- Model cannot be rejected by ANY experimental observation (overfitting)
- Energy production exceeding thermodynamic limits
- Parameter sensitivity analysis shows >50% of parameters are unidentifiable AND model still "passes" success criteria (gaming via compensating errors)

---

## Stretch Goals

These are pursued only after Phases 1–6 are complete and published.

### Stretch Goal A: E. coli Whole-Cell Model
Scale to *Escherichia coli* (~4,300 genes), validating against the Covert Lab's published wcEcoli model.

- **Complexity**: ~8x more genes than M. genitalium, ~2,700 metabolic reactions
- **Reference**: [CovertLab/WholeCellEcoliRelease](https://github.com/CovertLab/WholeCellEcoliRelease) — published in *Science* (2020), *npj Syst. Bio.* (2022)
- **What we reuse**: Their published validation data, process list, curated parameter values
- **What's new**: Our modular architecture, AI-agent-driven modeling, SBML interoperability
- **Estimated effort**: 6–12 months additional, ~$500–1,000 in cloud AI costs
- **Publication target**: *Science* or *Nature Methods*

### Stretch Goal B: Yeast (*S. cerevisiae*) Whole-Cell Model
First-ever complete whole-cell simulation of a eukaryotic organism (~6,000 genes, 7+ organelle compartments).

- **Complexity**: ~500–1,000x harder than M. genitalium (compartmentalization, chromatin, organelle dynamics)
- **Current state of the art**: Only partial models exist (Yeast9 GEM for metabolism, MIL-CELL for cell cycle)
- **New challenges**: Spatial modeling (organelle transport), chromatin/histone dynamics, multi-phase cell cycle with checkpoints
- **Estimated effort**: Multi-year project, likely requiring collaboration with experimental labs
- **Publication target**: *Cell* or *Nature* — would be a landmark achievement

### Stretch Goal C: Agent Orchestration Framework
Extract the orchestrator (ModelRouter, ExpertPanel, Pipeline) into a standalone open-source library for AI-driven scientific modeling.

- **Scope**: General-purpose multi-model debate engine with tier-based routing, caching, and conflict resolution
- **Use cases**: Any computational science project needing expert panel decisions — drug design, climate modeling, materials science
- **Publication target**: *Nature Methods* or *JOSS* (Journal of Open Source Software)

### Stretch Goal D: Drug & Evolution Simulation (Spin-off Project)
A spin-off project building on top of OpenCell to simulate drug interactions, predict resistance mutations, and model evolutionary trajectories. Applicable to any organism we model (M. genitalium, E. coli, and beyond).

- **Drug target identification**: Systematic gene knockouts to find essential enzymes with no human homolog (ideal drug targets that won't harm patients)
- **Drug effect prediction**: Inhibit target enzyme activity (reduce Vmax) and simulate cell cycle — predict whether cell dies, slows, or survives
- **Resistance mutation scanning**: Modify drug target Km/Vmax to model point mutations, identify which restore growth under drug pressure
- **Mutation fitness cost**: Compare wild-type vs mutant growth rates without drug — high fitness cost means resistance is unstable and may revert; low cost means it will spread
- **Evolutionary trajectory prediction**: Wright-Fisher population simulation under drug selection — predict most likely mutation sequence to full resistance
- **Combination therapy design**: Simulate multi-target inhibition to find drug combinations where resistance to one doesn't save the cell
- **Compensatory mutation prediction**: After resistance emerges, scan for secondary mutations that restore fitness — predict whether resistant strains will become as fit as wild-type
- **Applies to**: M. genitalium (azithromycin resistance, novel STI drug targets), E. coli (multi-drug resistance, clinical priority), and any future organism models
- **Real-world impact**: Pre-screen resistance risk before clinical trials, discover novel drug targets computationally, design resistance-proof therapies
- **Publication target**: *Nature Microbiology*, *Antimicrobial Agents and Chemotherapy*, or *PNAS*
