# Phase C Overview — DNA Replication + Cell Cycle

**Status**: phase overview · **Phase C wall-clock estimate**: ~14 weeks · **Covers**: 10 of 28 Karr processes (the DNA-related half + cell-cycle machinery)

## Phase C scope (10 processes)

| Turn | Karr process | OpenCell purpose | Estimated wall |
|---|---|---|---|
| pc-t1 | ReplicationInitiation | DnaA-ATP/ADP polymer dynamics at OriC; initiates replication ~2/3 through cell cycle | 40 min |
| pc-t2 | Replication | Polymerase elongation; leading + lagging strand; ~580 kb chromosome | 60 min (largest Phase C process) |
| pc-t3 | DNASupercoiling | TopoII, gyrase, topoIV; supercoiling state management | 30 min |
| pc-t4 | ChromosomeCondensation | SMC complex; condensation during replication | 25 min |
| pc-t5 | ChromosomeSegregation | Origin + terminus separation; SMC + topoII | 25 min |
| pc-t6 | DNADamage | UV, oxidative, alkylation damage; ~few events per cell cycle | 25 min |
| pc-t7 | DNARepair | Base excision, nucleotide excision, mismatch repair, recombination | 40 min |
| pc-t8 | FtsZPolymerization | Z-ring formation at midcell; required for division | 30 min |
| pc-t9 | Cytokinesis | Cell division mechanics; chromosome partitioning verification | 30 min |
| pc-t10 | TerminalOrganelleAssembly | Polar adhesion organelle (M. genitalium-specific structure) | 35 min |
| pc-final | build_karr_chassis_v5 | Phase A + B + C integration + cell-cycle ratchet test (~10000 ticks = one cell cycle) | 60 min |

**Total wall-clock for Phase C**: ~6-7 hours of Codex orchestration + 3-4 hours of design + 1-2 hours of debugging = **~12-14 hours active work** spread over Phase C's nominal 14-week wall-clock (i.e., we'll spend most of Phase C waiting for runs, designing follow-ons, and validating against Karr's published cell-cycle trajectories).

## Why DNA processes are different from Phase B

Phase B was all RNA + protein dynamics — relatively "fast" (μs-ms reaction timescales, easily abstracted to per-tick Δt=1s). Phase C introduces:

1. **Discrete events on a long timescale**: replication initiation happens ONCE per cell cycle (~10,000 ticks). DnaA polymerization at OriC has cooperative dynamics.
2. **Chromosomal state**: a single long sequence (~580 kb). Replication forks have position state. Damage and repair operate at specific positions.
3. **Cell-cycle coordination**: division must wait for replication to complete; replication must wait for DnaA threshold; supercoiling tension feeds back into replication speed.

Existing chassis_v4 architecture handles this with one addition: a **chromosomal state store**. Likely `genome.state.<region>` keyed by genomic coordinates (or by feature: OriC, terC, individual genes).

## Architecture additions in Phase C

### New stores

```
genome.state.<position_or_feature>      # chromosomal state machine
chromosome.replication_state             # idle | initiating | elongating | complete
chromosome.fork_positions                # (left_fork, right_fork) — only meaningful during elongation
chromosome.dnaa_complex_count            # count of DnaA molecules at OriC
chromosome.damage_sites                  # list of (position, damage_type)
ftsz.ring_state                          # idle | forming | constricting | divided
```

### New Step

`CellCycleCoordinator(Step)` — runs at tick boundary AFTER all processes evaluate. Checks:
- Has the DnaA threshold been reached at OriC? → Trigger replication initiation
- Have both forks reached terC? → Trigger replication complete
- Is replication complete + FtsZ ring constricted? → Trigger cytokinesis
- Has cytokinesis completed? → End simulation (or reset for next cell cycle if doing multi-cycle runs)

## Out of scope for Phase C

- Multi-cell simulation (Phase C delivers ONE cell cycle; multi-cycle / population dynamics is Phase E+)
- Detailed nucleosome dynamics (M. genitalium has no histones; not an issue)
- Methylation patterns (Karr models this; we may defer to a Phase E refinement if time permits)
- Plasmid replication (M. genitalium has no plasmids)

## Phase C completion criteria

After pc-final ships:
- **17 of 28 Karr processes covered** (Phases A3.3 + B) → **27 of 28** (Phases A3.3 + B + C)
- chassis_v5 runs one complete cell cycle (Karr-published average: ~9 hours = ~32,400 ticks at Δt=1s, but Phase C MVP may target a faster Δt or a representative ~10,000-tick subset)
- Mass-conservation passes across the full cycle
- Cell division produces 2 daughter cells with chromosome distributed correctly
- The 27 processes covered are everything EXCEPT `HostInteraction` (Phase D's one process)

## What Phase C does NOT validate

- Comparison to Karr's published phenotypes (that's Phase E)
- Cross-organism portability (out of scope for v1.0)
- Sensitivity analysis (Phase E + post-v1.0)

## Phase D preview

| Turn | Process | Description |
|---|---|---|
| pd-t1 | HostInteraction | M. genitalium adhesion to host epithelium; receptor binding |
| pd-final | build_karr_chassis_v6 | All 28 processes integrated |

Phase D is small (1 real process + integration). ~3 weeks wall-clock.

## Phase E preview (after pd-final)

- Replicate Karr's published cell-cycle trajectories
- Match ≥10 of his 28 quantitative phenotypes within published error bars
- Discrepancy analysis where we differ
- ~4 weeks wall-clock

## Bottom line

Phase C is where OpenCell becomes a "whole cell" simulator instead of a "metabolism + RNA + protein subsystem" simulator. The architectural patterns (Vivarium chassis + accumulate updaters + KarrAllocationStep) are proven. The new challenge is **long-timescale discrete events** (replication initiation, cytokinesis) coordinated with the fast-timescale Phase A/B processes. We'll address this via a CellCycleCoordinator Step.
