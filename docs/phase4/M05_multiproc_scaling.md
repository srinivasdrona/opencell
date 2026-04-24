# M0.5 — Multi-Process scaling profiler

**Status:** done.
**Run script:** `scripts/m05_multiproc_scaling.py`
**Artefact:** `artifacts/M05_multiproc_scaling.json`
**Settles:** the question raised by Phase 4 review — "M0-C is a knob, not a fix; what does the curve look like at scale?"

## Method

Two rigs swept over `N` Processes, fixed horizon 600 s, macro_dt 60 s
(10 macro steps):

* **noop** rig: `N` no-op Processes sharing a single store, each
  reading and writing 4 floats per macro step. Isolates **pure scheduler
  + state-marshalling cost**.
* **metab** rig: `N` independent `MetabolismProcess` instances each
  integrating Chassagnole metabolism on its own substores. Captures
  **per-Process LSODA spin-up cost × N**.

Wall time is fit as `wall ≈ a · N^b` to extract a scaling exponent.

## Headline numbers

| Rig   | N=1   | N=2    | N=4    | N=8     | N=16    | N=32    | scaling **b** |
|-------|-------|--------|--------|---------|---------|---------|---------------|
| noop  | 0.012 s | 0.018 s | 0.030 s | 0.054 s | 0.092 s | 0.179 s | **0.75 (sub-linear)** |
| metab | 15.6 s  | 30.7 s  | 61.9 s  | 125.6 s | 240.8 s | (n/a)   | **0.99 (linear)** |

Per-Process cost:

* noop: 1.17 ms → 0.56 ms per Process (drops as N grows — bulk dispatch amortises).
* metab: **15.6 s per Process, regardless of N.**

## Verdict

**The Vivarium scheduler is not the bottleneck.** The marshalling cost
is real but sub-linear (b = 0.75) and tiny in absolute terms.

**LSODA spin-up is.** Per-Process metabolism cost is essentially constant
in N (variance < 5%) and dominates wall time by 4 orders of magnitude
over scheduler cost. This means **vivarium-core is a fair chassis** —
the headline 73× / 25× overheads from A1 / M0 were never about Vivarium
itself; they were about Vivarium *not knowing* that LSODA could persist
state across macro steps.

## Projection to Karr scale (~16 metab-like Processes)

Linear extrapolation (b ≈ 1, no economies of scale):

| Horizon | Wall per realisation (16 procs) | Notes |
|---|---|---|
| 600 s   | ~250 s        | development runs, fine |
| 1 h     | ~25 min       | smoke testing, fine    |
| 8 h     | ~3.3 h        | overnight, acceptable for single realisations |
| 8 h × 100 ensemble | ~14 days | **not viable** without M0-A |
| 8 h × 1000 ensemble | ~140 days | **not viable**, period |

**Single-realisation Karr work is feasible on M0-C alone.**
**Ensemble Karr work (statistics, parameter sweeps) requires M0-A.**

This matches the Phase 4 caveat: "Phase 5 / M1 is fine; full Karr
needs more." M0.5 quantifies "more": for ensembles ≥ 100 realisations
or sweeps over more than ~30 parameter points, the LSODA-restart cost
becomes the wall.

## Decisions

1. **M1 (central carbon + energy charge) proceeds on M0-C** without M0-A.
   At ~5-7 Processes × 8h, the projection is ~2 hours per realisation —
   tolerable for development.

2. **M0-A is added to Phase 5 backlog as a hard prerequisite for any
   ensemble or sweep work.** The required engineering: a
   `PersistentLSODAProcess` mixin that stashes solver state
   (`y`, `dydt`, internal step history) on the Process instance between
   `next_update` calls. Vivarium 1.6.5's Process API does not block
   this — the Process *is* the natural state owner — but it does not
   advertise the pattern either. Reference: `scipy.integrate.ode`
   class-based interface (not `solve_ivp`) supports this directly.

3. **Fused-ODE scheduler (M0-B' alternative) is shelved.** With b ≈ 0.75
   on noop and b ≈ 1.0 on metab, fusing would only reduce N for the
   scheduler, not for LSODA. The expected speedup is small relative to
   M0-A, at much higher engineering cost.

4. **Performance budget A8 v0.1 is updated implicitly:** ensemble
   workloads are *not* in the v0.1 budget; an A8 v0.2 must add an
   "ensemble class" with M0-A as the gate.

## Why this is enough to close M0.5

The original M0.5 question was: "Does M0-C buy us enough at 16
Processes (Karr-scale) or do we need M0-A / fused-ODE before M1?"

Answer, evidence-based:

* **At Karr-scale single realisation: yes, M0-C is enough.** ~3.3 h
  per 8h sim is acceptable.
* **At ensemble scale: no.** M0-A is required.
* **Fused-ODE is not the right intervention.** Scheduler isn't the
  bottleneck.

M1 may proceed; M0-A is now a tracked prerequisite for ensemble work,
not a blocker for the next subsystem.
