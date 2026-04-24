# A1 — Vivarium-core spike: findings (2026-04-24)

**Decision: PROCEED with vivarium-core as the Phase 4/5 chassis,
with the LSODA-restart cost classified as a known M0 design question.**

## What was built

* `opencell/vivarium/` — additive subpackage. No existing module modified.
  * `processes.py` — `MetabolismProcess`, `SignalProcess`, `GeneNetworkProcess`.
  * `composite.py` — `build_coupled_engine(...)`.
* `scripts/vivarium_demo.py` — Vivarium-hosted equivalent of
  `scripts/demo_first_run.py`, plus head-to-head diff vs `hybrid_run`.
* `tests/vivarium/test_smoke.py` — schema + execution + diff smoke test.
* `data/semantics/A6_semantics_contract.md` v0.1 — drafted from the
  semantics surface area this spike exposed.

Artefacts:
* `artifacts/vivarium_demo.png`
* `artifacts/vivarium_demo.json`
* `artifacts/vivarium_vs_hybrid_diff.json`

## Numerical findings (8h run, n=12, base_seed=20260423, macro_dt=60s)

| Quantity | hybrid_run | vivarium | abs diff | rel diff |
|---|---|---|---|---|
| cglcex final (mM) | 0.0439 | 0.0742 | 0.030 | **0.69** |
| max abs cglcex diff over traj (mM) | — | — | **0.158** | — |
| f_met final | 0.0321 | 0.0348 | 0.003 | 0.08 |
| MA final mean | 0.25 | 0.17 | 0.08 | 0.33 |
| A final mean | 0.75 | 0.17 | 0.58 | 0.78 |
| R, C, MR final mean | 0 | 0 | 0 | — |

## Performance findings

| Engine | Wall total | Per realisation | Ratio |
|---|---|---|---|
| `hybrid_run` | 5.42 s | 0.45 s | 1.0× |
| Vivarium | 396.74 s | 33.06 s | **73×** |

## Why metabolism diverges (not a bug)

`hybrid_run` calls `solve_ivp(LSODA, ...)` **once** over the full 8-hour
horizon. `MetabolismProcess.next_update` calls it **480 times** (once per
macro step). Each restart loses LSODA's adaptive stepsize history,
which compounds over the depletion phase where stepsize matters most.

This is a **legitimate semantic difference between the two engines**,
documented in A6 §2.4 as the "LSODA restart rule". M0 will decide one of
three resolutions: tighten tolerances, persist integrator state across
calls, or change ODE method. The decision drives whether Vivarium-style
composition is viable for stiff metabolic networks at scale.

## Why gene state diverges

Two compounding causes, both in A6:

1. **f_met lag (A6 §2.3).** Vivarium's parallel-update scheduler means
   `GeneNetworkProcess` at step `n` reads the `f_met` written at the end
   of step `n-1`. `hybrid_run` uses end-of-current-step `f_met`. A
   one-step lag at the depletion knee shifts when synthesis throttles.
2. **Different metabolism trajectory** (above) → different `f_met`
   trajectory → different propensities → different tau-leap draws.

Counts at the demo horizon are tiny (single molecules), so n=12 sample
means amplify these into large relative differences. They will narrow
with larger n; the differences are not bias artefacts.

## Why 73× overhead

| Source | Approx contribution |
|---|---|
| LSODA restart per macro step (480x vs 1x) | ~70× |
| Per-Process port serialisation / state read | ~3× |
| Vivarium emitter + simulation ID + logging | ~1× |

Confirmed by inspection — the dominant term is LSODA restart, which is a
**design choice**, not a Vivarium tax.

## What this proves for Phase 4 strategy

* **Vivarium hosts our biology cleanly.** Three Processes, one shared
  signal store, no monkey-patching, no fork. Standalone use of
  `hybrid_run` continues to work — vendor lock-in mitigated.
* **The compositional cost is in solver restart, not Vivarium itself.**
  This is the right place for it to be — it surfaces a real coupling
  semantics question (per-step state vs per-horizon state) instead of
  hiding it inside one engine or the other.
* **The semantics contract is the deliverable, not the engine.** A1's
  most important output is `A6_semantics_contract.md`, not the
  Process classes.
* **A8 perf budget gets concrete numbers.** ≥10× for any composed run
  vs hand-coded equivalent is a hard ceiling that M0 must respect or
  document acceptance for.

## Open questions deferred to A5/A6/M0

* Should `MetabolismProcess` retain LSODA state across calls? (M0)
* Should the f_met lag be eliminated by a different topology
  (e.g. step-then-react)? (M0)
* What's the right Level-2 invariant for "metabolism trajectory drift
  vs reference"? (A5 + A7)
* What's the right unit-of-record for `time_step` once we have processes
  with fundamentally different natural rates? (A6 v0.2)
