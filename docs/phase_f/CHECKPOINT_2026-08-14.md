# OpenCell checkpoint - 2026-08-14

This checkpoint closes the operator-authorized ten-track L2.1/L2.2 wave at the
current external-tool boundary. It records measured gate state, merged
deliverables, isolated partial work, and the exact unblock required before the
remaining rows can close.

## Executive state

- **L2.1:** 22 GENUINE / 5 MISSING_ACTIVE_EXTRACTION / 1 FAIL.
- **L2.2:** 16 PASS / 3 FAIL / 3 MISSING_EVIDENCE; `integrity: OK`.
- **L2.4:** PASS for the implemented v1 scope at 100 ticks x 4 seeds.
- **L2.5:** not started. It remains blocked until L2.1 and L2.2 close.
- **Ten-track wave:** 2 fully closed; 8 still open.
- **Global blocker:** installed MATLAB R2026a trial licenses are expired
  (`License Manager Error -10.2`).

No detached process remains running.

## Gate scoreboard

| Gate | Current status |
|---|---|
| L1a | 28/28 |
| L1b | 115/115 runtime methods; 28/28 wiring rows |
| L2.0a | 403/403 allocator-input cells at tick 0 |
| L2.1 | 22 GENUINE / 5 MISSING_ACTIVE_EXTRACTION / 1 FAIL |
| L2.2 | 16 PASS / 3 FAIL / 3 MISSING_EVIDENCE |
| L2.4 | PASS, 100 ticks x 4 seeds, implemented v1 scope |
| L2.5 | not started / not certified |

## Ten-track disposition

### Fully closed

1. **L22-REPLICATION**
   - Current-tree N=50 rerun: PASS.
   - Primary chromosome channel PASS; substrates and bound enzymes SEED_NOISE.
   - Evidence merged at `bef0a3f`.

2. **L22-RIBOSOME-BRIDGE**
   - Existing hash-bound L2.event N=50 PASS now mechanically feeds L2.2.
   - Shared index moved RibosomeAssembly from MISSING to PASS.
   - Bridge/evidence merged through `fa56fb0` / `5a52aa9`.

### Open - MATLAB-derived state/windows required

3. **L21-CHROMCOND**
   - Exact `mcg16807` behavior and 20-call warmup were reconstructed on the
     process branch.
   - Remaining missing datum: chromosome/process state immediately before
     `ChromosomeCondensation.initializeState()`, currently trapped in an opaque
     MCOS fixture.
   - Partial RNG work remains isolated because merging the shared RNG module
     staled ProteinTranslocation L2.2.

4. **L21-ACTIVE-WINDOWS**
   - Active-window-aware rubric merged at `6059f8b`.
   - Six former non-genuine rows became GENUINE:
     DNARepair, Metabolism, ProteinDecay, Replication, RNAModification,
     RibosomeAssembly.
   - Five rows still need active extraction:
     TranscriptionalRegulation, ChromosomeSegregation, Cytokinesis, DNADamage,
     HostInteraction.

5. **L22-MACROMOL**
   - Active-window audit, loader and resumable extractor prepared.
   - Early 100-tick cohort is the wrong window; network-2 becomes active later.
   - Preparation merged at `9b7d4ab`; real cohort blocked by MATLAB licensing.

6. **L22-PPII**
   - Process-isolated active-window runner merged at `4d68ec1`; shared
     `h12.py` remains byte-identical.
   - 28/50 natural transferase-active windows verified as H12_CONFIRMED.
   - Remaining 22 later windows require real MATLAB/Statistics Toolbox
     execution without the project `mnrnd` shim.

7. **L22-DNAS**
   - Frozen N=200 sparse gate exposed real distinct-seed underactivity.
   - Eight branch-only follow-ups ported visible MATLAB release, binding,
     activity-order, ATP, persistence, initialization and chromosome binding
     semantics.
   - Visible candidate arithmetic now matches MATLAB, but Karr's unbound result
     depends on hidden chromosome state/caches absent from stored traces.
   - Branch remains isolated; merging partial shared-runner changes would stale
     closed evidence.

8. **L22-CYTOKINESIS**
   - One valid 4,000-tick seed; seed 1-49 resumable plan prepared.
   - Cohort-wide span survey remains 1/50.
   - Preparation merged at `75b9721`; extraction blocked by license.

9. **L22-FTSZ**
   - Direct fail-closed entrypoint and 50-seed extraction command prepared.
   - No usable division-anchored trace exists.
   - Preparation merged at `cdb9a08`; extraction blocked by license.

10. **L22-DNADAMAGE**
    - `hollidayJunctions` ported.
    - Source-backed UVB/gamma cohort planner and extractor override prepared.
    - Preparation merged at `7779dc4`; real stimulus cohort blocked by license.

## Important integration discipline learned

Three valid process-local changes were intentionally removed from main because
they modified shared hash-bound files and invalidated already-green evidence:

- Macromol process-root override in the shared Design-A helper;
- PPII active-window support inside shared `h12.py`;
- ChromosomeCondensation `mcg16807` support inside shared `matlab_rng.py`.

The useful work remains on isolated process branches. Any eventual integration
must either stay process-local or be followed by a coordinated recertification
of every affected row.

## External unblock

The only installed MATLAB executable is `E:\MATLAB\bin\matlab.exe`. It fails
before startup with:

```text
MathWorks Licensing Error 10
Your license for MATLAB has expired.
Error Code: -10.2
```

Restoring a valid MATLAB license unlocks:

- five L2.1 active extractions;
- ChromosomeCondensation pre-warmup state serialization;
- MacromolecularComplexation active cohort;
- PPII remaining 22 windows;
- DNAS hidden chromosome-state extraction;
- Cytokinesis seeds 1-49;
- FtsZ 50-seed pre-division cohort;
- DNADamage stimulus-conditioned cohort.

## Tracking

The SQL `tracks` registry is authoritative for operational state:

- `merged`: Replication, Ribosome bridge.
- `blocked`: the other eight tracks.

No progress-manager agents are required. The coordinator remains the sole
writer for shared catalogs and evidence indexes.

## Source-of-truth map

- Ladder: `docs/phase_f/L_LADDER_CANONICAL.md`
- L2.2 index: `docs/phase_f/l2_2_design_a/evidence_index.json`
- L2.event index: `docs/phase_f/l2_event/evidence_index.json`
- Ten-track launch checkpoint: `docs/phase_f/CHECKPOINT_2026-08-11.md`
- This closeout checkpoint: `docs/phase_f/CHECKPOINT_2026-08-14.md`
- Operational state: `plan.md` + SQL `tracks`

