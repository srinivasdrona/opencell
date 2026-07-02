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

`require_oc_counterpart` = every method that does process-specific work and must
have an OpenCell counterpart. Framework overrides are verified once at the
chassis level; property accessors are exempt.

| Category | Count | Completeness rule |
|---|---:|---|
| `biology_contract` (evolveState, calcResourceRequirements_Current/_LifeCycle) | 112 | require OC counterpart |
| `process_specific_helper` (formulateFBA, unwindAndPolymerizeDNA, …) | 65 | require OC counterpart |
| `init_contract` (initializeConstants/State + variants) | 31 | require (fixture-load allowed for once-at-t0 init) |
| `biology_substep` (evolveState_* sub-steps) | 14 | require OC counterpart |
| **REQUIRE OC COUNTERPART (total)** | **222** | — |
| `framework_override` (copyFromState/copyToState/getDryWeight…) | 76 | verified at chassis level |
| `property_getter_setter` (get.*/set.*) | 30 | exempt |
| **Class methods (excl. constructor)** | **328** | — |

## Per-process completeness target

`require` = methods requiring a verified OC counterpart; `total` = all class
methods (excl. constructor).

| Process | require | total |
|---|---:|---:|
| ReplicationInitiation | 30 | 31 |
| DNARepair | 14 | 15 |
| Metabolism | 14 | 15 |
| Replication | 14 | 41 |
| FtsZPolymerization | 10 | 10 |
| ProteinDecay | 10 | 15 |
| Cytokinesis | 7 | 8 |
| DNADamage | 7 | 8 |
| DNASupercoiling | 7 | 8 |
| ProteinActivation | 7 | 11 |
| Transcription | 7 | 12 |
| TranscriptionalRegulation | 7 | 10 |
| ChromosomeCondensation | 6 | 7 |
| MacromolecularComplexation | 6 | 10 |
| ProteinFolding | 6 | 10 |
| ProteinModification | 6 | 10 |
| RNAModification | 6 | 10 |
| RNAProcessing | 6 | 10 |
| RibosomeAssembly | 6 | 10 |
| tRNAAminoacylation | 6 | 12 |
| ChromosomeSegregation | 5 | 6 |
| HostInteraction | 5 | 6 |
| ProteinProcessingI | 5 | 9 |
| ProteinProcessingII | 5 | 9 |
| ProteinTranslocation | 5 | 9 |
| RNADecay | 5 | 10 |
| TerminalOrganelleAssembly | 5 | 6 |
| Translation | 5 | 10 |

## Regenerating

```bash
python scripts/build_karr_method_inventory.py          # regenerate JSON
python scripts/build_karr_method_inventory.py --check   # CI: fail if stale
```
