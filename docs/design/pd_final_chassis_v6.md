# Phase D Final Design - `build_karr_chassis_v6` (28/28 processes)

## Scope

This document defines the integration design for **chassis_v6**, whose only new biological process vs chassis_v5 is:

- `HostInteraction` (`pd-t1`, currently in parallel)

When `pc-final` lands chassis_v5 (27 processes), v6 adds HostInteraction as the 28th process and becomes the complete Karr process chassis.

Design-only deliverable. No Python execution and no tests run in this turn.

## Source Alignment Notes

- This repo currently contains:
  - `docs/karr_extracts/process/27_HostInteraction.md`
  - `docs/karr_extracts/process/28_TerminalOrganelleAssembly.md`
- The request text references `28_HostInteraction.md` and `27_TerminalOrganelleAssembly.md`.
- This design follows the **content** (HostInteraction depends on TerminalOrganelleAssembly), not the filename index mismatch.

## What Is New vs Chassis_v5

### 1. New process: HostInteraction (`pd-t1`)

Add one process entry:

- process key (proposed): `karr_host_interaction`
- Karr process: `Process_HostInteraction`
- functional dependency: terminal organelle state assembled by `TerminalOrganelleAssembly` (pc-t10)

Primary state target is `host` (boolean host-interaction flags), with protein dependencies from existing proteome stores.

### 2. CellCycleCoordinator policy update: host-adhesion gate question

Karr extract indicates HostInteraction computes host booleans from rule logic:

1. adherence depends on terminal organelle + adhesion protein expression
2. TLR activation depends on adherence + ligand expression
3. NF-kB depends on TLR combinations
4. inflammatory response depends on NF-kB or MG_075

The extract does **not** state that adhesion gates replication progression or growth flux. Therefore v6 design recommendation:

- default policy: **non-gating**
  - HostInteraction emits host-state observables only
  - CellCycleCoordinator does not block replication/cytokinesis/growth on adhesion
- optional feature flag (off by default): `host_adhesion_gates_division`
  - if enabled later, gate only the final division event, not metabolic growth

This keeps base behavior faithful to current extract evidence while preserving a controlled future hook.

## Expected Chassis_v6 Process Inventory (28)

Proposed process key skeleton (exact names can be normalized when `pc-final` merges):

1. `karr_m1`
2. `karr_replication_initiation`
3. `karr_replication`
4. `karr_dna_damage`
5. `karr_dna_repair`
6. `karr_dna_supercoiling`
7. `karr_chromosome_condensation`
8. `karr_chromosome_segregation`
9. `karr_transcription_v3`
10. `karr_transcriptional_regulation`
11. `karr_rna_processing`
12. `karr_rna_modification`
13. `karr_rna_decay`
14. `karr_trna_aminoacylation`
15. `karr_translation_v3`
16. `karr_protein_processing_i`
17. `karr_protein_processing_ii`
18. `karr_protein_modification`
19. `karr_protein_folding`
20. `karr_protein_activation`
21. `karr_protein_decay_light`
22. `karr_protein_translocation`
23. `karr_d2_real`
24. `karr_ribosome_assembly`
25. `karr_ftsz_polymerization`
26. `karr_cytokinesis`
27. `karr_terminal_organelle_assembly`
28. `karr_host_interaction`

## HostInteraction Integration Wiring

### New/updated stores

- `host.is_bacterium_adherent` (bool/int)
- `host.is_tlr_activated` (vector/bool map)
- `host.is_nfkb_activated` (bool/int)
- `host.is_inflammatory_response_activated` (bool/int)

Reads from existing stores (chassis_v5-origin):

- `protein.counts` (adhesion and ligand proteins)
- `terminal_organelle.*` (assembly completeness / required components)
- optionally `stimuli` if pd-t1 implementation uses the same pattern as other signaling processes

### Allocation impact

Per extract, HostInteraction is rule-based qualitative state logic; no new substrate allocation consumer is required in baseline v6. `KarrAllocationStep` consumer set remains unchanged unless pd-t1 implementation introduces explicit substrate use.

### Step/flow impact

- Keep existing request-calculator flow unchanged.
- CellCycleCoordinator gains a read-only view of `host.*` for emit/trace.
- Optional gated-division branch remains behind explicit flag.

## Phase E.1 Validation Hookup (Trajectory)

The following modules are expected to land in parallel by pe-1:

- `opencell/validation/karr_trajectory.py`
- `opencell/validation/trajectory_compare.py`

They are not present in this worktree yet; v6 integration contract should be:

1. `build_karr_chassis_v6(..., emit_step_s=1.0)` emits all scorecard observables each tick.
2. `karr_trajectory.py` extracts canonical observable vectors from the engine trajectory, including:
   - growth and key fluxes
   - RNA/protein totals and distributions
   - replication/cytokinesis event timeline
   - host booleans
3. `trajectory_compare.py` computes bucket-aware tolerance checks and report artifacts.

Required v6 emit observables to expose for the Phase E.1 adapter:

- `metabolic_reaction.growth_per_s`
- `metabolic_reaction.fluxs.*`
- `rna.counts.*`
- `protein.counts.*`
- `substrates.*` and/or `m1_pools.*`
- `chromosome.*` replication/cycle state
- `ftsz.*` ring/cytokinesis state
- `terminal_organelle.*`
- `host.*`
- `events.division` (or equivalent terminal event marker)

## 28-Phenotype Scorecard Skeleton (Store Mapping)

This is the post-v1.0 inventory skeleton. IDs are stable placeholders for validation harness wiring (`KP01..KP28`), with final paper-label normalization to be finalized in Phase E.

| ID | Phenotype (skeleton label) | Primary chassis_v6 store(s) |
|---|---|---|
| KP01 | Growth rate | `metabolic_reaction.growth_per_s` |
| KP02 | Doubling time | `time`, `events.division`, `metabolic_reaction.growth_per_s` |
| KP03 | Flux-oracle agreement | `metabolic_reaction.fluxs.*` |
| KP04 | Glucose uptake (PTS) | `metabolic_reaction.fluxs.TX_GLCPTS`, `substrates.*` |
| KP05 | Total mRNA abundance | `rna.counts.*` |
| KP06 | Total protein abundance | `protein.counts.*` |
| KP07 | mRNA short-horizon stability | `rna.counts.*` trajectory |
| KP08 | protein short-horizon stability | `protein.counts.*` trajectory |
| KP09 | Amino-acid pool stability | `m1_pools.*` and/or `substrates.*` |
| KP10 | Cell dry mass | `substrates.*`, `rna.*`, `protein.*`, `complex.*`, `chromosome.*` |
| KP11 | Replication initiation timing | `chromosome.replication_state`, `time` |
| KP12 | Replication duration | `chromosome.fork_positions`, `chromosome.replication_state` |
| KP13 | Cytokinesis duration | `ftsz.ring_state`, `cytokinesis.*`, `events.division` |
| KP14 | dNTP vs replication coupling | `substrates.dNTP*`, `chromosome.fork_positions` |
| KP15 | DNA-binding occupancy dynamics | `chromosome.complex_bound_sites` |
| KP16 | DNA content doubling | `chromosome.polymerized_regions` / DNA mass proxy |
| KP17 | DNA mass fraction | `chromosome.*`, `cell_mass.*` |
| KP18 | RNA mass fraction | `rna.*`, `cell_mass.*` |
| KP19 | Protein mass fraction | `protein.*`, `complex.*`, `cell_mass.*` |
| KP20 | Metabolite concentration profile | `substrates.*`, `cell_geometry.volume` |
| KP21 | ATP/GTP production-use balance | `metabolic_reaction.fluxs.*`, `requests.*`, `substrates_allocated.*` |
| KP22 | Energy discrepancy phenotype | `metabolic_reaction.fluxs.*`, aggregate energy ledger store |
| KP23 | Burst-like protein synthesis stats | `protein.counts.*` trajectory |
| KP24 | mRNA/protein distribution shape | `rna.counts.*`, `protein.counts.*` |
| KP25 | Gene essentiality accuracy | multi-run outcomes from `events.division`, viability flags |
| KP26 | Single-gene disruption phenotype class | cycle-state + viability event traces |
| KP27 | Host adhesion competence | `host.is_bacterium_adherent`, `terminal_organelle.*`, `protein.counts.*` |
| KP28 | Host immune activation cascade | `host.is_tlr_activated`, `host.is_nfkb_activated`, `host.is_inflammatory_response_activated` |

## 32400-Tick Full Cell-Cycle Integration Test Plan

### Target

- run length: `32400` ticks (`dt=1s`)
- expected: full cycle completes and one division event observed

### Suggested test phases

1. Build v6 and assert all 28 process keys present.
2. Run to 32400 ticks with emit stride suitable for trajectory compare.
3. Assert event ordering:
   - replication initiation occurs before replication completion
   - cytokinesis precedes division event
   - exactly one division event in the window
4. Extract scorecard observables (`KP01..KP28`) and pass to trajectory compare.

### Per-bucket tolerances (v1-trajectory-buckets)

| Bucket | Meaning | Tolerance policy for 32400-tick test |
|---|---|---|
| `opencell-tooling` | wiring, invariants, event plumbing | strict: exact event ordering; relative error <= 0.1% for wiring totals |
| `karr-known-incomplete` | known structural gaps vs Karr | xfail/expected-fail allowed; bounded drift window, e.g. 0.4x-2.5x ratio depending phenotype |
| `validation-and-organism-scaling` | condition/unit/organism scaling mismatch risk | medium: 10%-30% relative tolerance, phenotype-specific |
| `biology-beyond-Karr` | qualitative extensions beyond published quantitative target | qualitative checks (boolean/state sequence), no numeric fail-gate in v1 |

This bucketing keeps one full-cycle test useful in CI while preserving honest structural-gap accounting.

## Performance Budget

Assumption from prior chassis_v4 benchmark: **~62 ticks/s**.

- `32400 / 62 = 522.58 s` (~8.71 min, about 8m 43s)

Practical CI budget recommendation for the full-cycle test:

- hard timeout: 12 minutes (single run)
- expected wall time: ~9 minutes
- conclusion: **viable for CI**, with room for emit/compare overhead

## Orchestrator Open Questions

1. Confirm final filename/numbering convention for HostInteraction vs TerminalOrganelleAssembly extracts (`27/28` mismatch).
2. Confirm whether `CellCycleCoordinator` should keep host adhesion as non-gating in v1 (recommended) or add optional gate immediately.
3. Confirm canonical `KP01..KP28` labels for Phase E scorecard so pe-1 comparator and pd-final tests share IDs.
4. Confirm exact process key names expected by `pc-final` for phase-C and RNADecay processes before implementation starts.
