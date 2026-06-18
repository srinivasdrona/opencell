# Post-L5 Reorganization Plan: core/ vs models/ split

**Status:** PLANNED WORK (deferred until L5 chassis is validated).
**NOT a re-port.** A mechanical reorganization that takes ~4-5 weeks.
**Author:** agent + operator, 2026-06-18 (Day 32)

## Why this document exists

The architectural audit (Day 32, 2026-06-18) found that opencell's biggest
lock-in is the missing `core/` vs `models/` split. Currently all code is in
`opencell/vivarium/karr_*.py`, mixing engine mechanics (allocator, replay
harness, sparse store) with biology (28 process implementations).

This document captures the reorganization plan so future-us doesn't think
it's a re-port, and budgets time honestly when the work begins.

## Why post-L5, not now

1. **Biology earns the architecture credibility.** Audit recommendation:
   "Ship M. gen WCM that works (L5 green) → Ship the Gym env → Ship the
   tensor emitter → THEN publish methodology papers → THEN people start
   asking about generalization." Reorganizing now is the academic-incentive
   trap (architecture before biology).

2. **Vivarium did the hardest structural work for us.** The engine/biology
   split is partially there because we used Vivarium-core as a library
   rather than building our own engine. The remaining contamination is
   bounded (allocator, store, harness, constants).

3. **Doing the cheap things now prevents expensive retrofits later.**
   Already done as of Day 32: renamed `species_pools → state_groups`,
   extracted constants to `m_gen_constants.py`, wrote Intervention API
   spec, wrote data emit schema spec, wrote reference data manifest schema,
   added naming discipline rule. ~4 hours of work prevented ~2 weeks of
   post-L5 pain.

## Target architecture

```
opencell/
├── core/                          # GENERIC (engine, mechanisms, contracts)
│   ├── __init__.py
│   ├── allocator.py               # SharedPoolAllocator (was KarrAllocationStep)
│   ├── sparse_store.py            # SparseTripletStore (generic version of ChromosomeStore)
│   ├── intervention.py            # InterventionEngine (per docs/specs/INTERVENTION_API.md)
│   ├── validation/                # ReplayHarness, oracle-leakage detector, L-ladder runners
│   │   ├── replay_harness.py
│   │   ├── oracle_leakage_detector.py
│   │   └── l_ladder_runner.py
│   └── emitter/                   # tensor emitter (per docs/specs/DATA_EMIT_SCHEMA.yaml)
│       ├── zarr_emitter.py
│       └── hdf5_emitter.py
│
├── models/                        # BIOLOGY (organism-specific)
│   └── m_genitalium/              # M. genitalium specific
│       ├── __init__.py
│       ├── constants.py           # (currently opencell/m_gen_constants.py)
│       ├── chromosome.py          # MGenChromosome wrapping core/sparse_store
│       ├── processes/             # the 28 process implementations
│       │   ├── transcription.py
│       │   ├── translation.py
│       │   └── ... (28 files renamed from karr_*.py)
│       ├── fixtures/              # fixture loaders
│       ├── interventions.py       # MGenInterventionPresets (gene_knockout, etc.)
│       └── biology_replay.py      # biology-specific replay assertions
│
└── adapters/                      # OPTIONAL (RL, ML pipelines)
    └── gym_env.py                 # VivariumGymEnv (post-L5 deliverable)
```

## What moves where

| Current location | New location | Notes |
|---|---|---|
| `opencell/vivarium/karr_allocation_step.py` | `core/allocator.py` (class renamed `SharedPoolAllocator`) + `models/m_genitalium/processes/allocator_adapter.py` (thin biology shim) | Rename + parameterize allocator with substrate WID list |
| `opencell/state/chromosome_store.py` | `core/sparse_store.py` (generic `SparseTripletStore`) + `models/m_genitalium/chromosome.py` (11 named fields specific to MGen) | Field names stay biology; the store mechanism is generic |
| `tests/vivarium/l2_replay_common*.py` (~1000 LOC) | `core/validation/replay_harness.py` (generic) + `models/m_genitalium/biology_replay.py` (biology assertions) | **HIGHEST RISK item — see below** |
| `tests/vivarium/_l2_2_design_a_*` | `core/validation/composition_harness.py` + `models/m_genitalium/composition_assertions.py` | Same pattern as L2.1 harness split |
| `opencell/m_gen_constants.py` | `models/m_genitalium/constants.py` | Just a move |
| `opencell/vivarium/karr_*.py` (28 process files) | `models/m_genitalium/processes/*.py` (28 files, renamed) | Mechanical rename + import updates |
| `_OBS_STORE_PATHS` dict | `models/m_genitalium/state_paths.py` | Move; harness imports from biology layer |
| `opencell/vivarium/karr_composite.py` | `models/m_genitalium/composite.py` | Rename; uses `core/allocator` + `models/m_genitalium/processes/*` |

## Cost estimate (realistic, not optimistic)

| Work item | Effort | Risk |
|---|---|---|
| Allocator rename + biology shim | 1 day | LOW |
| Sparse store generalization | 2-3 days | LOW |
| Constants move | 1 day | LOW |
| Process file moves + import updates | 2-3 days | MEDIUM (large diff, easy to break tests) |
| **Replay harness split** | **1-2 weeks** | **HIGH** (1000 LOC, biology threaded through, edge cases will surface) |
| Composition harness split | 3-5 days | MEDIUM |
| Composite rename | 1 day | LOW |
| Documentation update | 1 day | LOW |
| Test re-validation | 2-3 days | MEDIUM (run full L1-L5 suite to confirm no regressions) |
| **Total** | **4-5 weeks** | |

**The 1-2 week replay harness item is the bottleneck.** ~1000 LOC of test
infrastructure with biology projections (WID assumptions, store path mappings,
chromosome field knowledge) woven through. Splitting it cleanly while
preserving every test is mechanical-but-tedious, and tedium expands.

DO NOT promise faster than 4-5 weeks externally. If it lands faster, great.

## Out of scope for this reorganization

- Multi-organism support (just enables it; doesn't ADD a second organism)
- Tensor emitter implementation (separate Post-L5 item)
- Distributed execution (separate Post-L5 item)
- JAX migration (separate, much later)
- Calibration loop (separate Post-L5 item)

## Order of operations

1. **Move constants** (1 day, no behavior change) — safest first step
2. **Move processes** (2-3 days) — biggest diff but mechanical
3. **Rename allocator with shim** (1 day) — preserves all current behavior
4. **Generalize sparse store** (2-3 days) — chromosome.py becomes thin wrapper
5. **Split composition harness** (3-5 days) — smaller surface than replay harness
6. **Split replay harness** (1-2 weeks) — the big one, save for last
7. **Update docs + naming** (1-2 days)
8. **Re-run L1-L5 full validation** (2-3 days)

After step 1, each step can be its own PR with full test pass as the merge gate.

## Tripwires to enforce during the build (now)

These rules prevent the reorganization from getting larger:

1. **Don't add new code under `opencell/vivarium/` that's not biology-specific.**
   If a new generic mechanism is needed, put it under a new `opencell/core/`
   directory immediately (it will eventually move there anyway).

2. **Don't name new generic primitives `Karr*` or `M*`.** Per Hard Rule 17
   (naming discipline) in SESSION_CONTEXT.md.

3. **Don't hardcode new biology constants outside `m_gen_constants.py`.**
   If you need a new biology constant, add it to the constants file.

4. **Don't add new TOML fields that use biology-specific names.**
   `state_groups`, `observables`, `chromosome` are biology-neutral.
   `species_pools` was renamed; don't introduce similar terms.

## Success criteria

When this reorganization is complete:

1. `import opencell.core` succeeds without importing any biology
2. A chemist (or test) can use `core/allocator` for a non-biology simulation
3. All L1-L5 tests pass on the reorganized code
4. The `models/` tree is the only place biology terms appear
5. `m_gen_constants.py` is the only place organism-specific numbers appear
6. The Intervention API spec is implemented in `core/intervention.py`
7. Documentation reflects the new structure

## What this enables (the payoff)

Once done, opencell becomes:

- **Year 2**: Someone emails "can your L-ladder methodology be used for a
  tumor microenvironment simulator?" Answer: "core/ is domain-agnostic,
  write your own models against the Vivarium contract."
- **Year 3**: Microsoft Bio-AI team uses the intervention API + Gym env
  pattern for synthetic biology design platform. opencell becomes
  the substrate.
- **Year 5**: Climate modeling group adapts the L-ladder for inter-model
  comparison. Methodology paper cited in climate research.

None of these require changing scope today. They require not actively
closing these doors during implementation. This reorganization is the
door-keeping artifact.
