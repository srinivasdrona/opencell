# OpenCell checkpoint - 2026-08-11

This is the formal bookkeeping checkpoint before the next parallel closure
wave. Definitions remain in `docs/phase_f/L_LADDER_CANONICAL.md`; this file
records measured state and the work authorized only after operator go-ahead.

## Executive state

- **28 Karr processes** remain the denominator.
- **L2.1:** 16 GENUINE / 5 COINCIDENTAL / 6 UNINFORMATIVE / 1 FAIL.
- **L2.2:** 14 PASS / 4 FAIL / 4 MISSING_EVIDENCE across 22 in-scope
  processes; aggregate `NON_GREEN`.
- **L2.4:** PASS for the implemented v1 gate at 100 ticks x 4 seeds.
- **L2.5:** not started. The operator explicitly reaffirmed that L2.5 will not
  begin while L2.1 or L2.2 remains open.
- **L3:** not started.

The L2.2 index was regenerated on the current tree after the shared
runner/helper/projection hashes changed. All 14 formerly stale PASS rows were
rerun against 50-seed Karr evidence and recertified. The authoritative audit is
`integrity: OK`.

## Current lower-gate scoreboard

| Gate | Current status |
|---|---|
| L1a | 28/28 aliveness baseline |
| L1b | 115/115 runtime methods; 28/28 wiring rows |
| L2.0 | static schema gate and self-tests implemented |
| L2.0a | 403/403 allocator-input cells matched at tick 0 |
| L2.1 | 16 GENUINE / 5 COINCIDENTAL / 6 UNINFORMATIVE / 1 FAIL |
| L2.2 | 14 PASS / 4 FAIL / 4 MISSING_EVIDENCE |
| L2.4 | PASS, 100 ticks x 4 seeds, implemented v1 scope |
| L2.5 | not started / not certified |

### L2.1 non-green rows

- Literal FAIL: `ChromosomeCondensation`.
- COINCIDENTAL: `DNARepair`, `Metabolism`, `ProteinDecay`, `Replication`,
  `TranscriptionalRegulation`.
- UNINFORMATIVE: `ChromosomeSegregation`, `Cytokinesis`, `DNADamage`,
  `HostInteraction`, `RNAModification`, `RibosomeAssembly`.

The non-genuine rows need active-window evidence and, only where activity still
does not match, process-code correction. Repeating the same inactive first-100
trace is not a valid closure strategy.

### L2.2 non-green rows

FAIL:

- `Replication` - source semantics have been repaired; the N=50 gate must be
  rerun on the corrected code.
- `MacromolecularComplexation` - the early 100-tick cohort misses naturally
  reachable network-2 Monte Carlo competition; targeted active windows are
  required.
- `ProteinProcessingII` - the natural cohort never exercises
  `transferase_fires`; synthetic evidence remains non-gating.
- `DNASupercoiling` - 200 unique seeds exist, but the proposed occurrence-rate
  guard is too weak and even accepts zero OC activity.

MISSING_EVIDENCE:

- `RibosomeAssembly` - a separate, hash-bound 50-seed L2.event PASS exists;
  it must be bridged into the authoritative L2.2 index.
- `Cytokinesis` - one valid 4,000-tick event seed exists; 49 more and a
  cohort-wide span maximum are required.
- `FtsZPolymerization` - only early 100-tick traces exist; no division-anchored
  cohort exists.
- `DNADamage` - existing traces are no-stimulus/vacuous; the OC port also lacks
  `hollidayJunctions`.

## Existing MATLAB evidence inventory

File count is not seed count: many files are byte-identical copies across
worktrees.

| Process | Unique usable evidence | Disposition |
|---|---|---|
| Replication | 50 unique 100-tick seeds | sufficient for rerun |
| MacromolecularComplexation | 50 early seeds + one later lifecycle scan | wrong window for network-2 gate |
| ProteinProcessingII | 50 early seeds | no transferase branch coverage |
| DNASupercoiling | 200 unique seeds | data sufficient; metric insufficient |
| RibosomeAssembly | 50 event-window seeds | sufficient; gate already PASS |
| Cytokinesis | 1 valid 4,000-tick event seed | 49 missing |
| FtsZPolymerization | early 100-tick traces only | 0 usable division windows |
| DNADamage | 100-tick + full-cycle no-stimulus traces | wrong condition |

## Ten-track closure wave

No track below is launched until the operator explicitly gives the go-ahead.

### L2.1

1. **L21-CHROMCOND:** fix the literal `ChromosomeCondensation` bit-identity
   failure.
2. **L21-ACTIVE-WINDOWS:** mechanically locate active Karr windows for the five
   COINCIDENTAL and six UNINFORMATIVE rows, rerun bit identity, and split
   trace-window gaps from real code gaps.

### L2.2

3. **L22-REPLICATION:** rerun the corrected Replication port at N=50/M=100.
4. **L22-MACROMOL:** extract/gate 50 active network-2 windows.
5. **L22-PPII:** obtain source-faithful transferase-active evidence and resolve
   the real `mnrnd` execution path.
6. **L22-DNAS:** preregister and implement a sparse-event acceptance rule that
   rejects zero/strong underactivity; evaluate the existing N=200 cohort.
7. **L22-RIBOSOME:** bridge the existing L2.event PASS into L2.2 authority.
8. **L22-CYTOKINESIS:** extract seeds 1-49 and establish the cohort-wide
   onset-to-pinch span.
9. **L22-FTSZ:** extract 50 pre-division windows and run the windowed gate.
10. **L22-DNADAMAGE:** port `hollidayJunctions` and extract source-backed
    stimulus-conditioned Karr traces as two sub-lanes under one process owner.

## Orchestration and tracking

- One coordinator owns `plan.md`, the SQL `tracks` table, shared catalogs and
  evidence indexes.
- Each implementation/extraction runs as a detached process in one isolated
  worktree and writes one structured `STATUS_<track>.md`.
- No separate progress-manager agents: they would duplicate state and create
  another reconciliation layer.
- Shared runner/helper/projection/catalog files are frozen during sweeps.
- MATLAB-heavy tracks may queue on license/RAM capacity, but their code,
  inventory and preregistration work can proceed concurrently.
- Shared indexes are regenerated once by the coordinator after process
  evidence lands.

## Source-of-truth map

- Ladder: `docs/phase_f/L_LADDER_CANONICAL.md`
- L2.2 index: `docs/phase_f/l2_2_design_a/evidence_index.json`
- L2.event index: `docs/phase_f/l2_event/evidence_index.json`
- L2.5 scope: `docs/phase_f/L2_5_SCOPE_RATIFICATION.md`
- Operational state: repo `plan.md` + session SQL `tracks`

