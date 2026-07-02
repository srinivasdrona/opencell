# Karr Per-Process Method Inventory (ground truth)

**Purpose:** the authoritative enumeration of every method each Karr 2012
process class defines. This is the substrate for the **L1b method-completeness
gate**: the OpenCell port must implement a verified counterpart for every
Karr method that does real work — no Karr method may be silently dropped.

- Machine-readable: [`karr_process_methods.json`](karr_process_methods.json)
- Generator (reproducible): [`scripts/build_karr_method_inventory.py`](../../scripts/build_karr_method_inventory.py)
- Drift check (CI): `python scripts/build_karr_method_inventory.py --check`

## Provenance

Verified on 2026-07-03 by **four independent parsers**:

| Parser | Technique | Count |
|---|---|---:|
| orchestrator A | flat single-pass regex | 305 |
| orchestrator B | comment-strip + continuation-join, per-line regex | 333 |
| Haiku sub-agent | char-level comment state machine, line-by-line | 333 |
| **codex gpt-5.4-mini** | **block-stack scope tracker** (authoritative) | **328** |

They converged on the class-method set except for **6 entries**, all resolved by
direct source inspection:

| Method | Resolution |
|---|---|
| `FtsZPolymerization.diff` (L449) | file-local function **after** `classdef end` — NOT a class method — **excluded** |
| `FtsZPolymerization.jacobian` (L500) | file-local function after classdef — **excluded** |
| `MacromolecularComplexation.buildProteinComplexs_montecarlokinetic` (L334) | file-local function after classdef — **excluded** |
| `MacromolecularComplexation.buildProteinComplexs_rates_collisionTheory` (L360) | file-local function — **excluded** |
| `MacromolecularComplexation.buildProteinComplexs_bounds` (L390) | file-local function — **excluded** |
| `Metabolism.calcGrowthRate` (L1266-67) | real class method, multi-line signature — **included** (flat-regex parsers missed it) |

The excluded file-local helpers are still ported — *inside* their parent method
(`integrateODEs`, the complexation build) — so they are not dropped, only not
tracked as top-level methods. Block-stack scoping (record a `function` only
while the block stack holds both `classdef` and `methods`) is what distinguishes
class methods from file-local helpers.

## Classification

Two orthogonal dimensions are recorded per method:

**1. `category`** — what kind of method it is (structural):

| Category | Count | Meaning |
|---|---:|---|
| `biology_contract` | 112 | evolveState, calcResourceRequirements_Current/_LifeCycle |
| `process_specific_helper` | 65 | one-class helpers (formulateFBA, unwindAndPolymerizeDNA, …) |
| `init_contract` | 31 | initializeConstants/State + variants |
| `biology_substep` | 14 | evolveState_* sub-steps |
| `framework_override` | 76 | base Process.m plumbing overridden per process |
| `property_getter_setter` | 30 | get.*/set.* accessors |

**2. `port_requirement`** — whether OC must implement a per-process runtime port,
computed by **call-graph reachability** (is the method reachable via `this.<m>`
calls from `evolveState`/`calcResourceRequirements_Current`, vs only from
init/fitting roots):

| port_requirement | Count | Rule |
|---|---:|---|
| **`runtime_port_required`** | **115** | reachable from evolveState/calcResourceRequirements_Current → **MUST have a per-process OC runtime port** |
| `init_fixture_or_logic` | 68 | init method → fixture-load OK for once-at-t0 init; real logic required for per-cell-cycle init |
| `fitting_fixture_inherited` | 38 | offline fitting (FitConstants / FBA build) → outputs inherited via fixtures; verify provenance once, not per-process |
| `uncalled_no_port` | 1 | defined but never called in Karr source (`ReplicationInitiation.sampleDnaABoxes`) → no port needed |
| `chassis_level` | 76 | framework override → verified once at chassis level |
| `exempt_accessor` | 30 | property accessor → exempt |
| `needs_manual_resolution` | 0 | all resolved |

**The true per-process runtime-port target is 115** (not the naive 222 biology-
category count). The 68 init + 38 fitting are covered via fixtures (OC loads
Karr's fitted knowledge base rather than re-running the offline fitting/init).

### The three-layer resource framework (why lifecycle ≠ allocator)

Karr embeds allocation in `Simulation.evolveState` and fitting in `FitConstants`
(offline). OC split these, so the two Karr resource-requirement methods map to
different OC layers:

| Karr method | Role | OC representation | Validated by |
|---|---|---|---|
| `calcResourceRequirements_Current` | per-tick request | `RequestCalculator*` classes + `KarrAllocationStep` | L2.0a (allocator arithmetic) |
| `calcResourceRequirements_LifeCycle` | offline fitting: biomass objective + expression bounds | fitted outputs inherited via fixtures (`biomass_col`, `fba_rxn_idx_biomass_production`, `metabolism_new_production`) | fixture provenance |
| *(none — `KarrAllocationStep` is OC-only)* | per-tick allocation, refactored out of `Simulation.evolveState` | standalone Vivarium Step | L2.0a + L2.4 |

OC's allocator is a **per-tick** Step; `calcResourceRequirements_LifeCycle` is an
**offline fitting** method — they are different layers, and the allocator does
NOT satisfy lifecycle. Lifecycle's *outputs* are inherited via fixtures.

Six methods with no in-file dot-caller were resolved by source evidence (see
`orphan_resolutions` in the JSON): `formulateFBA` (FBA.m build) and
`calcStateTransitionProbabilities` (FitConstants) → fitting; three DnaA-box
state queries → runtime; `sampleDnaABoxes` → dead code.

## Per-process runtime-port target

`run` = runtime_port_required (the real per-process OC port target);
`init` = init_fixture_or_logic; `fit` = fitting_fixture_inherited.

| Process | run | init | fit |
|---|---:|---:|---:|
| ReplicationInitiation | 22 | 6 | 1 |
| DNARepair | 10 | 2 | 2 |
| Replication | 10 | 3 | 1 |
| FtsZPolymerization | 7 | 2 | 1 |
| ProteinDecay | 7 | 2 | 1 |
| DNADamage | 4 | 2 | 1 |
| Metabolism | 4 | 2 | 8 |
| TranscriptionalRegulation | 4 | 2 | 1 |
| ChromosomeCondensation | 3 | 2 | 1 |
| Cytokinesis | 3 | 2 | 2 |
| DNASupercoiling | 3 | 3 | 1 |
| ProteinActivation | 3 | 3 | 1 |
| RNAProcessing | 3 | 2 | 1 |
| RibosomeAssembly | 3 | 2 | 1 |
| Transcription | 3 | 2 | 2 |
| 13 simpler processes | 2 each | 2–3 | 1 |

## Regenerating

```bash
python scripts/build_karr_method_inventory.py          # regenerate JSON
python scripts/build_karr_method_inventory.py --check   # CI: fail if stale
```
