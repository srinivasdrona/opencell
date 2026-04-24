# A8 — Performance budget per phase (v0.1, 2026-04-24)

> Measured baselines, not aspirations. Updated whenever a benchmark
> moves > 30%; CI tracks regression on the headline numbers.

## Reference workload

* Cell: Chassagnole 2002 metabolism + Vilar 2002 gene network, coupled
  one-way (`f_met` from PTS uptake flux).
* Horizon: 8 simulated hours.
* Macro timestep: 60 s (480 macro steps).
* Ensemble: n=12, base_seed=20260423.
* Hardware: dev workstation (single CPU thread per realisation, no GPU).

## Phase 4 baseline (A1 measured, 2026-04-24)

| Engine | Per-realisation wall | Total wall (n=12) | Ratio vs ref |
|---|---|---|---|
| `hybrid_run` (single-shot LSODA + tau-leap) | **0.45 s** | 5.42 s | 1.0× (reference) |
| Vivarium-core engine (3 Processes, restart per macro step) | 33.06 s | 396.74 s | **73×** |

The 73× is dominated by LSODA restart cost (~70× of the 73×). It is
classified as a known design question for M0, **not** a Vivarium tax.

## Budgets (hard ceilings, not goals)

| Phase | Workload | Budget | Rationale |
|---|---|---|---|
| **4** (Engine hardening) | Reference workload through Vivarium | ≤ 75× `hybrid_run` | Current measured 73× is the line; M0 must not regress. |
| **4** (M0 vertical slice) | Smallest bidirectional loop, n=12, 8h | ≤ 60 s/realisation | Allows a developer to iterate without coffee breaks. |
| **5** (M1 central carbon) | M0 + ~20 metabolic reactions, n=12, 4h | ≤ 5 min/realisation | Still iteration-friendly. Forces ODE choice review if exceeded. |
| **5** (M4 translation) | M0 + M1 + M2 + M3 + M4, n=12, 4h | ≤ 30 min/realisation | Ribosome-loaded gene pool dominates. |
| **5** (M7 Karr validation, full M. genitalium) | Full network, single realisation, full cell cycle | ≤ Karr MATLAB reference (10 h) | Karr's own runtime is the natural ceiling; we should not be slower than the artifact we're porting. |

## Tracking

* **CI gate (Phase 4):** `pytest -m perf_budget` runs a 30-minute Vivarium
  ensemble and asserts wall time < 75 × `hybrid_run` reference. The
  reference wall is re-measured per-CI-run on the same job to absorb
  hardware noise. Will be added before M1 starts.
* **Phase-end review:** every M-phase completion writes a row to a
  cumulative table in this file. We do not silently regress.

## Profiling notes from A1

* `MetabolismProcess.next_update` is the hot path. 480 calls × ~70 ms
  = ~33 s per realisation. Inside each call: ~95% LSODA, ~5%
  port serialisation.
* `GeneNetworkProcess.next_update`: ~2-3 ms per call when f_met is low
  (rare events); negligible cost overall.
* `SignalProcess.next_update`: ~50 µs per call; negligible.
* Vivarium emitter overhead: ~2-3 % of total — not the bottleneck.

## Decisions deferred to M0 (each has perf consequences)

* (M0-A) Persist LSODA between calls → projected ~5× recovery.
* (M0-B) Switch to fixed-step RK4 with stability check → projected
  ~3× recovery.
* (M0-C) Increase macro timestep to 300 s with sub-stepping inside
  metabolism → projected ~10× recovery, but degrades f_met resolution.

The decision is biological (how often does f_met meaningfully change?),
not just numerical. M0 must measure and choose with both axes in view.
