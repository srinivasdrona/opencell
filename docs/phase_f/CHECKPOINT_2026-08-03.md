# OpenCell checkpoint — 2026-08-03

This is the dated status snapshot for the formal milestone checkpoint before
any Cytokinesis Canary-D retry, N=50 sweep, or new process implementation.
Definitions live in `docs/phase_f/L_LADDER_CANONICAL.md`; this file records
state, not definitions.

## Executive state

- **28 Karr processes** remain the process denominator.
- **L2.2 Design-A evidence:** 14 PASS / 4 FAIL / 4 MISSING_EVIDENCE across
  the 22 in-scope rows; aggregate `NON_GREEN`.
- **L2.5:** no currently certified pair set. Historical `15/256` and related
  tracker counts predate the honest lower-gate rebuild and are not accepted
  checkpoint evidence.
- **L3:** not started.

No work above L2 resumes until the blockers below have terminal, reviewed
dispositions and the lower-gate evidence is regenerated on the final tree.

## Lower gates

| Gate | Checkpoint status |
|---|---|
| L1a | 28/28 aliveness baseline |
| L1b | 28/28 method/wiring conformance |
| L2.0 | 28/28 static schema |
| L2.0a | 403/403 allocator-input cases |
| L2.1 | 19 GENUINE, 2 COINCIDENTAL, 6 UNINFORMATIVE, 1 FAIL |
| L2.2 | 14 PASS, 4 FAIL, 4 MISSING_EVIDENCE |
| L2.4 | PASS, 100 ticks x 4 seeds |
| L2.5 | not currently certified |

L2.1's non-genuine categories are not all implementation failures: stochastic,
event, windowed and condition-gated processes require the applicable fidelity
profile. `ChromosomeCondensation` remains the one literal L2.1 FAIL.

## L2.2 PASS rows

The current mechanically re-derived PASS rows are:

- DNARepair
- Metabolism
- ProteinDecay
- ProteinFolding
- ProteinModification
- ProteinProcessingI
- ProteinTranslocation
- ReplicationInitiation
- RNADecay
- RNAModification
- RNAProcessing
- Transcription
- Translation
- tRNAAminoacylation

Authority: `docs/phase_f/l2_2_design_a/evidence_index.json`. Re-derive before
using these counts after any source/evaluator change.

## Open per-process dispositions

### DNASupercoiling

The canonical N=50 row remains `FAIL / PRIMARY_INSUFFICIENT_SAMPLES`
(17 OpenCell and 24 Karr nonzero events; floor 30). The preregistered N=100
diagnostic is powered and consistent, but is supplemental and non-gating.

### Replication

The literal topology restart branch is **not integrated** and N=50 is denied.
Several source semantics are independently improved (merge/unwind primitives,
position getters, bound/free pool ownership, occlusion caps and SSB fork-gap
scoping), but the real per-tick path still does not reproduce Karr's exact
initiation/termination event set. The remaining blocker is the isolated
per-tick advance-budget reconstruction and its interaction with the topology
state machine. Bypass diagnostics are causality probes, not acceptance.

### ProteinProcessingII

The natural row remains `H12_OBSERVED_REGIME` and non-green. A genuine-MATLAB,
real-Karr-RandStream canary for `transferase_capacity_scarce` completed across
20 seeds with two outcomes and zero invariant violations. It is explicitly
non-gating and cannot close `transferase_fires` or unblock L2.5. Full `mnrnd`
evidence is blocked because Statistics Toolbox is not installed.

### MacromolecularComplexation

The network-2 `CONDITION_GATED_CANDIDATE` is hardened, portable and
non-operative. Lifecycle reachability is `UNRESOLVED`; the candidate changes
no verdict and does not unblock L2.5.

### RibosomeAssembly

The adapter is structural and unregistered. Seed 0 is M4-complete and now
hash-bound to the accepted legacy-`mnrnd` compatibility shim. Structural smoke
is `NOT_APPLICABLE`; the real gate refuses at 1/50 seeds. Seeds 1-49 and the
gate-mode cohort driver remain missing.

### Cytokinesis

The adapter is structural and unregistered. Canary B (bad process) and Canary
C (completion not observed within 2,000 ticks) failed safely. Canary D reached
tick 25,361 before exposing the pre-existing `mnrnd` shim defect. The shim is
fixed and version/hash-bound; Canary A was regenerated under it. Canary D
retry is deliberately paused at this checkpoint.

### FtsZPolymerization

Reframed from event-class to an honest no-hint windowed diagnostic. The one
available MAT-family seed/100-tick canary is non-vacuous and invariant-clean,
but terminates `INSUFFICIENT_ENSEMBLE`; it cannot PASS at N=1. Forty-nine more
MAT-family seeds and a preregistered Karr-only null are required before any
live catalog reclassification.

### DNADamage

A synthetic mechanism-stress profile is preregistered but unexecuted. It is
explicitly non-biological and non-phenotypic: UVB/gamma values are derived
from Karr fixture rates solely to provide statistical mechanism support.
No-stimulus remains `NOT_APPLICABLE`; unsupported rare reaction kinds cannot
become zero-equals-zero passes. No live registry/catalog change exists.

## Event extractor checkpoint

The shared extractor/launcher is integrated and fail-closed:

- fixed absolute tick coordinates;
- corrupt-file regeneration instead of crash/skip;
- token/prior-hash-bound atomic replacement;
- nonzero MATLAB failure propagation;
- anchor onset/completion metadata;
- Cytokinesis projection v2 without full-Chromosome serialization;
- runtime `mnrnd` shim version/hash binding.

Ribosome Canary A, failure Canary B and short-anchor Canary C have passed.
The long Cytokinesis Canary D has not completed successfully.

## What is intentionally paused

Until this checkpoint is closed:

- no Cytokinesis Canary-D retry;
- no N=50 extraction/sweep;
- no L2.5 denominator or pair execution;
- no L3 design/pilot;
- no live adoption of FtsZ, DNADamage or condition-gated catalog proposals.

## Source-of-truth map

- Ladder definitions: `docs/phase_f/L_LADDER_CANONICAL.md`
- L2.2 mechanical verdicts:
  `docs/phase_f/l2_2_design_a/evidence_index.json`
- H12 evidence: `docs/phase_f/l2_2_design_a/h12/h12_evidence_index.json`
- Event routing/evidence: `docs/phase_f/l2_event/event_registry.yaml`,
  `docs/phase_f/l2_event/evidence_index.json`
- This dated checkpoint: `docs/phase_f/CHECKPOINT_2026-08-03.md`

The following older trackers remain historical inputs, not current authority,
until explicitly reconciled: `docs/phase_f/l2_2_design_a/L2_2_GATE_TRACKER.md`,
`docs/phase_f/L2_5_PAIR_TRACKER.md`, and
`docs/phase_e/PROCESS_STATUS_ALL_29.md`.

