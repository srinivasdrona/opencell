# OpenCell Post-L5 Roadmap

**Status:** RATIFIED (Day 32, 2026-06-18) — comprehensive post-L5 plan
based on operator strategic review.
**Authority:** when L5 is green, this document drives the next phases.
**Precondition:** L5 chassis validated. Nothing here happens before that.

This document consolidates:
- Use cases (defensible + rejected)
- Architectural reorganization plan
- ML infrastructure roadmap
- Use-case-specific deliverables
- Publication plan
- Discipline rules
- Sequencing recommendation

---

## Part 1: Defensible Post-L5 use cases (ranked)

These are the use cases opencell can credibly support. Ranked by
defensibility — how confident we are the claim holds up to scrutiny.

| # | Use case | Defensibility | What it needs |
|---|---|---|---|
| 1 | **Reproducible WCM tool / Karr 2012 modernization** | Highest | L5 green + README rewrite (E1) |
| 2 | **Bio-AI Hello World benchmark** | High | Tensor emitter + benchmark spec + frozen test sets |
| 3 | **Systems biology educational tool** | High | Jupyter tutorials + course-ready notebooks (D5) |
| 4 | **Synthetic data factory for surrogate model architecture validation** | High | Tensor emitter + distributed execution (in C) |
| 5 | **Interventional sandbox / OpenAI Gym environment** | High | Intervention API (D1) + Gym wrapper (D2) |
| 6 | **Causal discovery benchmark** (distinctive entry, NOT "first") | Medium-High | Causal graph export + benchmark API + metrics (D3) |
| 7 | **Multi-scale dynamical system benchmark (RNNs/SSMs/Neural ODEs)** | Medium | Frozen test sets + baseline scores (D4) |
| 8 | **PINN methodology testing** | Medium | Conservation metric exports (framed as "test-validated", NOT "perfect") |
| 9 | **Mutagenesis study design** (in silico predictions) | Medium | Knockout workflow + report generator (D6) |
| 10 | **Multi-omics pipeline validation** | Medium | Synthetic ground-truth datasets (D7) |
| 11 | **Safety testing for generative biology** | Low-Medium | Genome variant injection + comparator (D8, later) |
| 12 | **Architectural methodology paper substrate** (L-ladder + anti-laundering) | High | Methodology writeup (E3) |

---

## Part 2: Use cases EXPLICITLY REJECTED (do not pursue)

These came up during strategic review and did NOT survive critique.
Document them here so future-us doesn't reintroduce them.

| Use case | Why rejected | Mitigation when asked |
|---|---|---|
| Differentiable hybrid neural-mechanistic architectures | JAX was deliberately removed; pure NumPy can't do autograd | Point to jax-md, jaxley, equinox-bio |
| Direct bacterial→human transfer learning (mTOR analogue) | Bacterial stringent response is functionally analogous but structurally different from mTOR | Frame opencell as ML architecture validation, not biological transfer source |
| Drug discovery / target prioritization | Kinetic parameters not biologically accurate; would mislead pharma | "In silico target prioritization is not opencell's lane; closer to OpenTargets" |
| Direct human disease modeling | M. genitalium ≠ human cells; Frankenstein parameters don't transfer | Point to vEcoli or eventually mammalian WCMs |
| Universal complex-systems engine | Architectural pattern generalizes; opencell-the-software does not | "The Vivarium pattern generalizes; opencell is biology-specific" |
| Economics / agent-based modeling | Mesa, NetLogo, Repast purpose-built for ABM | Point to Mesa |
| Microgrid / supply chain / smart city simulators | GridLAB-D, SimPy, SUMO have validated domain physics | Point to domain-specific frameworks |
| "First realistic causal discovery benchmark in biology" | Sachs 2005, DREAM, CausalBench predate | Use "distinctive new entry in the landscape" |
| GPU-accelerated drug screens | Workload-dependent; CPU ensembles competitive for hybrid det/stoch | Already de-scoped; don't reintroduce |
| Autonomous parameter-reconciliation agent | Multi-year research problem; we use human-in-the-loop | Already de-scoped; don't reintroduce |

---

## Part 3: Architectural reorganization (Phase 1, ~4-5 weeks)

See `docs/specs/POST_L5_REFACTOR_PLAN.md` for the detailed plan.

Headline: core/ vs models/ split. Mechanical reorganization, NOT a re-port.
Vivarium-core already IS the engine; we just need to extract our own
generic primitives (allocator, sparse store, replay harness) from the
biology-mixed locations they currently live in.

**Critical**: Budget 4-5 weeks externally. Test harness contamination
(1000+ LOC of biology threaded through) tends to expand during the split.
Don't promise 2-3 weeks to anyone.

---

## Part 4: ML infrastructure (Phase 2, ~4-6 weeks)

Bolt-on infrastructure for the data factory use cases. Already documented
in plan.md Post-L5 section. Headline items:

| Component | Effort | Notes |
|---|---|---|
| Tensor emitter (Zarr/HDF5/Parquet) | 1-2 weeks | Schema in `docs/specs/DATA_EMIT_SCHEMA.yaml` is the contract |
| Distributed execution (Ray/Dask) | 1-2 weeks | Required for 10k+ run datasets |
| Automated calibration loop | 2-4 weeks | Bayesian opt / GA for parameter tuning |
| DNN surrogate base class | 1 week | PyTorch Process wrapper |
| Data layout spec | 2-3 days | Mostly done via the DATA_EMIT_SCHEMA spec |
| Multi-timescale orchestration | 1 week | See risks section below |

---

## Part 5: Use-case-specific deliverables (Phase 3-5, ~6-12 weeks)

These convert architectural foundation into shippable artifacts.

### D1. Intervention API implementation (~1 week, builds on `INTERVENTION_API.md`)

- Knockout: gene-level disable, propagates to dependent reactions
- Throttle: enzyme rate scaling
- Nutrient shift: environmental substrate override
- Time-windowed perturbation scheduler
- Combinatorial intervention experiments
- Validation tests: lethal knockouts should fail to divide

### D2. OpenAI Gym environment wrapper (~1-2 weeks)

Backend-agnostic base class:
```python
class VivariumGymEnv(gym.Env):
    def __init__(self, simulator, action_space_def, observation_space_def, reward_fn):
        ...
```
Thin biology-specific subclass:
```python
class MGenitaliumEnv(VivariumGymEnv):
    action_space = ...  # knockouts (discrete) + throttles (continuous)
    observation_space = ...  # state vector
    reward_fn = ...  # cell-cycle completion, growth rate
```

### D3. Causal discovery benchmark (~2-4 weeks)

- Export ground-truth causal DAG from model code as `causal_graph.json`
- `opencell.causal.Benchmark` API for external researchers
- Standard intervention sets: single/double knockouts, environmental shifts, time-varying
- Train/test splits with held-out interventions
- Metrics: SHD, F1 on edges, AUROC, intervention transferability
- Optional: simple GitHub-based leaderboard

### D4. Multi-scale dynamical system benchmark (~1 week, bundle with D3)

- Frozen test sets at multiple timescales (seconds, minutes, hours)
- Metrics for sequence-modeling architectures (MSE, autocorrelation, long-horizon)
- Baseline scores: LSTM, Transformer, Mamba, Neural ODE, S4

### D5. Educational / tutorial materials (~1-2 weeks)

- "Run your first M. genitalium simulation" Jupyter notebook
- Comparison notebooks: opencell vs Karr MATLAB on canonical phenotypes
- Course module: 6-8 lectures worth
- Sandbox exercises (run perturbations, see what happens)

### D6. Mutagenesis study design tool (~1-2 weeks)

- CLI / notebook workflow: "predict outcome of knocking out gene X under condition Y"
- Output: predicted phenotype + confidence interval + comparison to wild-type
- Optional: comparison against published M. gen knockout studies

### D7. Multi-omics pipeline validation datasets (~1 week, DEFERRED — speculative)

- Generate omics-style outputs (transcriptomics, proteomics, metabolomics snapshots)
- Document as synthetic ground-truth datasets for omics integration pipelines
- Build only when demand emerges

### D8. Safety testing for generative biology (DEFERRED — speculative)

- Genome variant injection API
- Simulate proposed minimal genome designs before synthesis
- Cite as use case but don't build until demand emerges

---

## Part 6: Publication / documentation artifacts (Phase 6, ongoing)

### E1. README rewrite (DO IMMEDIATELY — pre-L5)

**Drop these stale claims:**
- "GPU-accelerated"
- "Python/JAX"
- Any tier-1-organism claims beyond M. genitalium

**Replace with:**
> "Open-source whole-cell simulation framework built on Vivarium-core.
> Pure Python (NumPy/SciPy), CPU-native. M. genitalium reference, with
> explicit L-ladder validation, anti-laundering detection, and intervention
> API. Designed for ML method validation, causal discovery benchmarking,
> and reproducible Bio-AI research."

### E2. Biology validation paper (the canonical citation)

- "Validated open M. genitalium whole-cell model in Python on vivarium-core"
- ≥10/28 Karr phenotypes within error bars (L5 target)
- Discrepancy analysis if <10/28
- This becomes the "if you use opencell, cite this" paper

### E3. Architectural methodology paper (separate publication)

- L-ladder as domain-agnostic validation methodology
- Anti-laundering detection as benchmark integrity safety net
- Vivarium Process contract as composable simulator architecture
- Citations: Vivarium-core, IHME vivarium, Sachs 2005, DREAM, etc.
- **CRITICAL**: publish AFTER biology paper. Methodology needs the biology
  to give it demonstrated credibility. Reversed order is academic-incentive trap.

### E4. Causal benchmark paper (if D3 ships)

- Benchmark spec, baseline scores, leaderboard documentation
- Cite Sachs, DREAM, CausalBench; position opencell as distinctive entry
- Co-publishable with D3 release

### E5. Dev practice writeup (optional, low-priority)

- Tehol/Bugg blog series as case study in AI-augmented development
- "Lessons from Day 1 to L5" retrospective

---

## Part 7: Critical things to NOT do

These are guardrails against patterns that would damage opencell's
credibility or pull it off-mission:

1. **Don't reintroduce JAX to chase differentiability.** Already removed
   deliberately. If someone wants differentiable bio, point to jax-md /
   jaxley.
2. **Don't tear up the L2.5 → L5 roadmap to chase generalization.**
   Biology first, methodology papers later. Cross-domain framing
   explains why the architecture was right; it does NOT change what
   opencell does.
3. **Don't build abstract base classes for non-existent siblings.** YAGNI.
   Generalize when there are two of something.
4. **Don't claim "first," "universal," "perfect," or "hungry community."**
   All four are hype patterns. Walk them back to load-bearing versions.
5. **Don't position as drug discovery / direct human disease tool.**
   Frankenstein parameters mean any biological insight transferred to
   human disease is uncalibrated speculation.
6. **Don't position opencell-the-software as portable to non-biology
   domains.** The pattern is portable; the codebase is biology-specific.
7. **Don't promise the 2-3 week post-L5 refactor externally.** Budget 4-5
   weeks; ship faster as bonus.
8. **Don't skip the cheap-things-now bundle.** ✅ Already done as of Day 32.

---

## Part 8: Risks & gotchas

### Multi-timescale stale-read risk

We currently use uniform 1-second timesteps. Vivarium supports
per-process timesteps via deltas merged atomically. The delta contract
is **safe at uniform timesteps** but has known failure modes if processes
declare different timesteps:

1. **Stale reads during fast cycles.** Slow process reads stale substrate
   counts because fast process changed them between reads. Deltas remain
   correct but algorithmic decisions can over-commit.
2. **Allocator timing mismatch.** Should the allocator run at fast or
   slow timestep? Fast = waste; slow = over-consumption between allocations.
3. **Integer-rounding accumulation.** Fast process at `+0.3/tick × 10
   ticks` floors to 3 vs `round(0.3) × 10 = 0`. Different rounding paths
   produce different totals.
4. **Multi-tick atomicity.** Fast process hits depletion mid-tick while
   slow process already committed. Vivarium doesn't naturally roll back
   or throttle mid-tick.

**Mitigation if/when we go multi-timescale:**
- Run allocator at the fastest process's timestep (over-allocate, reconcile)
- Use floating-point internal counts; round only at boundaries
- Add `validate_no_negative_after_composition` invariant check
- Document per-process "tolerable stale-read horizon"
- Validate L5 chassis FIRST at uniform timesteps, then measure drift
  when introducing multi-timescale

**Why this matters now:** even though we're uniform-1s today, this risk
must be documented so future-us doesn't introduce multi-timescale before
the validation harness can measure the drift.

### Test harness contamination

The 1000+ LOC of biology-specific replay infrastructure
(`tests/vivarium/l2_*_replay_common*.py`) is the single biggest item in
the post-L5 reorganization. Realistic worst case: 1-2 weeks to split
cleanly. Tedium expands.

### L2.5 deterministic-deterministic pairs

The L2.5 acceptance rubric (`docs/phase_f/L2_5_ACCEPTANCE_RUBRIC.md`)
now requires bit-identity oracle on deterministic processes. This is
STRICTER than the original "exclude them" plan. Day 32 evidence: the
ChromosomeCondensation+ChromosomeSegregation pair FAILED on first run,
exposing a real allocator double-spend bug that L2.1 single-process
testing could never have caught. This is the L-ladder working as designed.

---

## Part 9: Sequencing recommendation

```
NOW (this week, pre-L5):
├─ A1-A6: Cheap-things bundle (✅ DONE Day 32)
├─ E1: README rewrite (drop JAX/GPU claims) — PENDING
└─ L2.5 → L5 biology work continues unchanged

POST-L5 (after L5 green):
├─ Phase 1 (4-5 weeks): Mechanical reorganization
│  └─ core/ vs models/ split (see POST_L5_REFACTOR_PLAN.md)
├─ Phase 2 (4-6 weeks): ML infrastructure (C)
│  └─ Tensor emitter, distributed execution, surrogate base class
├─ Phase 3 (2-3 weeks): Foundational deliverables
│  ├─ D1: Intervention API implementation
│  └─ D2: Gym env wrapper
├─ Phase 4 (3-5 weeks): Benchmark deliverables
│  ├─ D3: Causal discovery benchmark
│  └─ D4: Multi-scale dynamical system benchmark
├─ Phase 5 (2-3 weeks): User-facing tools
│  ├─ D5: Educational materials
│  └─ D6: Mutagenesis design tool
└─ Phase 6 (ongoing): Publications
   ├─ E2: Biology paper (primary, first)
   ├─ E3: Methodology paper (AFTER biology lands)
   ├─ E4: Benchmark papers (with each D3/D4 release)
   └─ E5: Dev-practice writeup (optional)

DEFERRED / SPECULATIVE (don't build until demand):
├─ D7: Multi-omics validation datasets
└─ D8: Safety testing for generative biology
```

---

## Part 10: Realistic user / impact picture

**Active users at maturity:** 200-1,000
- Bio-ML grad students
- WCM researchers
- Systems biology educators
- Niche Bio-AI startups
- Internal Microsoft Research interest

**Citation impact:**
- High if biology + methodology + benchmark papers all ship
- Modest if only biology validation paper

**Educational compounding:** meaningful over decades if D5 lands in coursework

**Highest-leverage long-term:** methodology paper (E3) — L-ladder and
anti-laundering pattern could be cited in climate, traffic, supply chain
modeling work over years. Don't ship E3 before E2.

---

## Provenance

- Day 32 (2026-06-18): Initial roadmap drafted from operator strategic
  review session. Consolidates 12 defensible use cases, 10 rejected,
  8 deliverables, 5 publications, 8 anti-patterns, multi-timescale risk
  documentation.
- Cheap-things bundle (A1-A6) closed same day via commits `7de2141`,
  `3f2204a`, `da8e1bf`.
- README rewrite (E1) pending.
