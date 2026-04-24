# A6 — Simulation Semantics Contract (v0.1, drafted 2026-04-24)

> **Status:** Draft from A1 findings. Will be tightened by M0 vertical-slice
> work. Every coupled simulation in OpenCell must conform to this contract
> or document its deviation explicitly.

## Why this document exists

The "did simulation X reproduce simulation Y?" question has no answer
without a shared specification of *what each simulation actually computed*.
A1 (Vivarium spike) made this concrete: the same Chassagnole+Vilar coupled
cell, run through `hybrid_run` and through `Engine`, produced cglcex final
values of **0.044** and **0.074 mM** respectively — a 70% relative
difference — even though both use identical biology, identical solvers,
identical RNG hygiene, and identical macro timestep. The root cause is
**solver-restart semantics**, not biology. A diff tool that doesn't
distinguish these axes will report noise.

## Scope

This contract covers the **engine-level semantics** that affect numerical
reproducibility but are usually implicit. It does *not* cover the
biology-level model semantics (rate laws, units, etc.); those are owned
by `opencell/models/` and the parameter cards.

## Section 1 — State ontology

### 1.1 Variable kinds

Every simulated variable is exactly one of:

| Kind | Examples | Updater | Floating? |
|---|---|---|---|
| **Concentration** | Chassagnole metabolites (mM) | `set` | Yes (float64) |
| **Count** | Vilar mRNAs / proteins (molecules/cell) | `accumulate` | Integer-valued; stored as float64 for emit |
| **Derived signal** | `f_met` | `set` | Yes (float64) |
| **Rate observable** | `v_pts` (mM/s) | `set` | Yes (float64) |

### 1.2 Naming

* Variable names are case-sensitive and identical to the canonical SBML
  identifier (e.g. `cglcex`, `MA`, `R`).
* No abbreviation, no plural-vs-singular drift across modules.
* Cross-module variables (e.g. `f_met` shared by signal and gene) live
  in a *single* store; there is no per-process shadow copy.

### 1.3 Units

Every port variable carries an implicit unit declared in module docs:

* Metabolites: **mM** (concentration).
* Counts: **molecules per cell**.
* Time: **seconds** at the engine boundary; sub-models that natively
  compute in hours (Vilar) convert internally.
* Rates: **per second**.

A6 v0.2 will move from "implicit declared" to "first-class unit on each
port spec" once `pint` integration patterns settle.

## Section 2 — Time and scheduler

### 2.1 Engine clock

The Vivarium `Engine` clock advances in **seconds**. Every Process must
declare its `time_step` in seconds. Sub-models with native non-second
time bases convert at the boundary; the conversion factor is asserted
at module load (e.g. `SECONDS_PER_HOUR = 3600.0`).

### 2.2 Macro timestep `macro_dt_s`

For Phase 4 / M0 we use a **single global macro timestep** for all
processes. Rationale: the Chassagnole+Vilar coupling has no fast/slow
separation that demands multi-rate scheduling; uniform stepping makes
the diff tool tractable. Multi-rate is M-phase-late scope.

### 2.3 Within-step ordering and the "f_met of record" convention

Vivarium's default scheduler advances **all processes in parallel** for
a `macro_dt_s` segment, then commits all updates simultaneously at the
boundary. This implies:

> **Rule (f_met lag):** At step `n`, `GeneNetworkProcess` reads
> `signal.f_met` written at the end of step `n-1`. There is exactly
> **one macro_dt_s lag** between the metabolic state that produced
> `f_met` and the gene-network step that consumes it.

`hybrid_run` differs: it computes `f_met` from the *just-completed*
metabolism segment and feeds it into the *same-step* gene segment
(zero-step lag). For one-way coupling this difference is bounded; for
M0's bidirectional coupling, the lag becomes the interesting object,
and we will tighten this rule rather than eliminate it.

### 2.4 Solver-restart semantics

> **Rule (LSODA restart cost):** `MetabolismProcess.next_update` calls
> `solve_ivp(LSODA, ...)` afresh each macro step. Each restart loses
> the adaptive-stepsize history. Cumulative drift relative to a
> single-shot `solve_ivp` over the full horizon is **on the order of
> 0.1 mM per 8 hours of simulated time** at default tolerances
> (`atol=1e-9, rtol=1e-6`).

This is a real semantic difference, not a bug. A1 measured it. M0 will
decide whether to:

* (a) Accept the drift and tighten tolerances when it matters
  (compositional purity, expensive but honest),
* (b) Add a stateful LSODA process that retains the integrator
  between calls (faster, but blurs the Process boundary), or
* (c) Use an ODE method whose restart cost is lower (e.g. fixed-step
  RK).

Decision deferred to M0; A5 diff tool must report this drift as
Level-2 invariant violation, not silent.

### 2.5 RNG discipline

Unchanged from existing repo rule (see
`.github/copilot-instructions.md` § Stochastic RNG discipline):

* One `np.random.Generator` per realisation, threaded explicitly.
* No bare seeds passed across module boundaries.
* Ensembles use `SeedSequence(base_seed).spawn(n)`.
* Vivarium adapter passes the `Generator` through process parameters;
  `next_update` consumes it but does not mutate it.

## Section 3 — Initial conditions

### 3.1 Source of truth

Initial state is built **once**, by the composite builder, from the
sub-model `initial_y` arrays. Per-port `_default` values exist only as a
schema-level safety net; if there is ever a mismatch between
`_default` and the engine's `initial_state`, the latter wins and a
warning is raised in M0 work.

### 3.2 Stationarity not assumed

Neither metabolism nor the gene network is initialised at steady state
for the demo (`cglcex = 2 mM` is a depletion experiment, not a steady
glucose pool). Steady-state initialisation, if required, must be
explicit and use `opencell/analysis/steady_state.py`.

## Section 4 — Coupling semantics

### 4.1 One-way (current)

`signal.f_met = f_met_fn(observable, observable_init)` where the
observable is either `cglcex` (concentration) or `v_pts` (uptake flux).
`f_met` modulates the **6 synthesis fluxes** of the Vilar gene network
only. It does **not** scale degradation, complex formation, or DNA
binding. This is biological commitment, not numerical.

### 4.2 Bidirectional (M0 target)

M0 will introduce a small back-coupling: gene state (e.g. translated
catalysts) modifies a metabolic reaction rate. The semantics contract
will then add a **back-coupling lag rule** mirroring §2.3 and an
explicit ordering choice (Strang split vs Lie split vs implicit
midpoint).

## Section 5 — Equivalence classes (what the diff tool checks)

The A5 diff tool computes 4 levels:

1. **Structural diff** — port names, units, updaters, topology shape.
   Two simulations are *structurally equivalent* iff every port and
   every store path agree by name and kind.
2. **Invariant diff** — non-negativity, mass/charge balance,
   conservation laws (A7). Reported per timestep.
3. **Trajectory norm diff** — L2 / L_inf norms over the trajectory of
   each declared comparable variable. Tolerances are per-variable,
   declared in this contract.
4. **Phenotype diff** — final-state scalars and Karr-style phenotype
   bins. Most aggressive lossy compression of the trajectory; useful
   for cross-engine diffs that are not expected to be bitwise.

### 5.1 Default tolerances (Chassagnole+Vilar engine compare)

| Variable kind | L_inf abs | L_inf rel |
|---|---|---|
| Concentration (free metabolite) | 0.2 mM | 0.05 |
| Concentration (PTS feed) | 0.05 mM | 0.05 |
| Derived signal (`f_met`) | 0.05 | 0.10 |
| Count (mean over ensemble n>=12) | 5 molecules | 0.5 |

Bounds reflect the LSODA-restart drift documented in §2.4 and the
ensemble shot noise of n=12 stochastic runs. They are *engine-compare*
bounds, not biology-validation bounds.

## Section 6 — Things explicitly NOT in this contract (yet)

* Multi-rate scheduling and event detection.
* Division / partitioning of state at cell division.
* Spatially resolved compartments.
* Non-Markovian processes (delays, age structure).
* Heterogeneous parameter populations across cells.

These will appear in v0.2+ as M0 / M5 / Z work demands.
