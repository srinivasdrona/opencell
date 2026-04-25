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

## Current Status (2026-04-23, **397 tests passing**, hybrid solver + first-run demo done)

### Hybrid Solver + First-Run Demo (DONE — Phase 3 capstone)

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
