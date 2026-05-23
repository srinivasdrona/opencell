# Phase C Final - build_karr_chassis_v5 Integration Design

Status: design-only skeleton for integration handoff

## Goal

Design a new `build_karr_chassis_v5` composite that keeps `build_karr_chassis_v4` intact and additively wires:

- 17 already integrated v4 Karr processes
- 10 Phase C processes
  - already merged: `ReplicationInitiation` (pc-t1)
  - landing in parallel: pc-t2 to pc-t10

Total in v5 target scope: 27 of 28 Karr processes (`HostInteraction` remains v6).

## Assumptions For This Design

- v5 keeps the v4 request-calculator plus allocation-step pattern.
- Phase C process modules follow current naming and expose process names consistent with Karr process labels.
- This document is a chassis integration design; it does not introduce biology beyond Karr extracts and existing v4 conventions.

## Process Inventory (27 Karr Processes)

Tick/order legend:

- `S0`: request-calculator steps populate `requests`
- `S1`: `karr_allocation_step` writes `substrates_allocated`
- `P`: all Karr Processes tick in Vivarium parallel mode (read previous-tick committed state + current allocation)
- `S2`: `cell_cycle_coordinator` commits phase-gating state transitions for next tick

| Name | Module path | Ports written | Ports read | Substrate consumption | Depends on (state from other process) | Ticks/order |
|---|---|---|---|---|---|---|
| Metabolism | `opencell/vivarium/karr_metabolism.py` | `metabolic_reaction`, `substrates` | `substrates` | produces/consumes broad metabolite pool (585 WIDs) | upstream demand from all consumers via shared `substrates` | `P` |
| Transcription (v3) | `opencell/vivarium/karr_transcription_v3.py` | `rna`, `substrates` | `complex`, `tx_rate_fold_change`, `substrates` | ATP/CTP/GTP/UTP | RNAP availability (`complex`), regulation fold-change | `P` |
| Translation (v3) | `opencell/vivarium/karr_m3_v3.py` | `protein`, `substrates` | `rna`, `complex`, `substrates` | ATP/GTP + amino acids | ribosome counts (`complex`), transcript abundance (`rna`) | `P` |
| MacromolecularComplexation (D2 real) | `opencell/vivarium/karr_d2_real.py` | `complex` (+ internal requests) | `substrates`, `complex`, `substrates_allocated` | ATP/GTP/H2O classically allocated | shared substrates and complex counts | `P` |
| ProteinDecay-light | `opencell/vivarium/karr_protein_decay_light.py` | `protein`, `rna`, `complex`, `substrates` (+ internal requests) | `complex`, `substrates_allocated` | ATP/H2O | shared complex counts; allocation result | `P` |
| tRNAAminoacylation | `opencell/vivarium/karr_trna_aminoacylation.py` | `rna`, `substrates` | `rna`, `protein`, `substrates_allocated` | ATP + amino acids and cofactors | tRNA pools (`rna`), synthetases (`protein`) | `P` |
| RibosomeAssembly | `opencell/vivarium/karr_ribosome_assembly.py` | `complex`, `rna`, `protein`, `substrates` | `rna`, `protein`, `substrates_allocated` | GTP/H2O | rRNA + ribosomal proteins | `P` |
| TranscriptionalRegulation | `opencell/vivarium/karr_transcriptional_regulation.py` | `tf_binding`, `tx_rate_fold_change` | `protein` | none direct (regulatory) | TF protein abundance | `P` |
| RNAProcessing | `opencell/vivarium/karr_rna_processing.py` | `rna`, `substrates` | `rna`, `protein`, `substrates_allocated` | ATP/GTP + ions/water (per reaction set) | enzyme proteins + immature RNA | `P` |
| RNAModification | `opencell/vivarium/karr_rna_modification.py` | `rna`, `substrates` | `rna`, `protein`, `substrates_allocated` | methyl/energy cofactors (allocated substrate set) | modified-state RNA species | `P` |
| ProteinProcessingI | `opencell/vivarium/karr_protein_processing_i.py` | `protein`, `substrates` | `protein`, `substrates_allocated` | H2O | nascent/unprocessed proteins | `P` |
| ProteinProcessingII | `opencell/vivarium/karr_protein_processing_ii.py` | `protein`, `substrates` | `protein`, `substrates_allocated` | pathway substrates (allocated) | processed/intermediate proteins | `P` |
| ProteinModification | `opencell/vivarium/karr_protein_modification.py` | `protein`, `substrates` | `protein`, `substrates_allocated` | modification cofactors (allocated) | unmodified protein states | `P` |
| ProteinFolding | `opencell/vivarium/karr_protein_folding.py` | `protein`, `substrates` | `protein`, `substrates_allocated` | ATP + Fe2+ + Mg2+ + Zn2+ | unfolded proteins + chaperone context | `P` |
| ProteinTranslocation | `opencell/vivarium/karr_protein_translocation.py` | `protein`, `substrates` | `protein`, `substrates_allocated` | ATP | translocatable proteins + location state | `P` |
| ProteinActivation | `opencell/vivarium/karr_protein_activation.py` | `protein` | `activation_substrates`, `stimuli`, `protein` | uses activation substrate pool | stimuli + regulated protein set | `P` |
| ReplicationInitiation (pc-t1) | `opencell/vivarium/karr_replication_initiation.py` | `chromosome.dnaa_complex_count`, `chromosome.replication_state`, `protein.counts`, `substrates`, `requests` | `chromosome.supercoiled`, `chromosome.dnaa_complex_count`, `protein.counts`, `substrates_allocated` | ATP + H2O (DnaA ATP/ADP cycle) | supercoiling gate from DNASupercoiling | `P` |
| Replication (pc-t2) | `opencell/vivarium/karr_replication.py` | `chromosome.fork_positions`, `chromosome.replication_state`, `chromosome.replication_complete`, `chromosome.polymerized_nt`, `substrates`, `requests` | `chromosome.replication_state`, `chromosome.supercoiling_density`, `chromosome.damage_sites`, `substrates_allocated` | dATP/dCTP/dGTP/dTTP + ATP/NAD (ligase/helicase) | initiation trigger, supercoiling, damage/repair status | `P` |
| DNASupercoiling (pc-t3) | `opencell/vivarium/karr_dna_supercoiling.py` | `chromosome.supercoiling_density`, `chromosome.supercoiled`, `substrates`, `requests` | `chromosome.fork_positions`, `chromosome.replication_state`, `chromosome.topology_regions`, `substrates_allocated` | ATP (gyrase/topo IV) | replication fork progression and topology regions | `P` |
| ChromosomeCondensation (pc-t4) | `opencell/vivarium/karr_chromosome_condensation.py` | `chromosome.condensation_state`, `chromosome.smc_bound_sites`, `substrates`, `requests` | `chromosome.fork_positions`, `chromosome.replication_state`, `substrates_allocated` | ATP/H2O (SMC binding cycle) | replication displacement of SMCs | `P` |
| ChromosomeSegregation (pc-t5) | `opencell/vivarium/karr_chromosome_segregation.py` | `chromosome.segregation_progress`, `chromosome.segregation_complete`, `chromosome.segregation_state`, `substrates`, `requests` | `chromosome.replication_complete`, `chromosome.supercoiled`, `chromosome.condensation_state`, `substrates_allocated` | GTP (segregation ATPase/GTPase equivalents) | replication complete + supercoiling + condensation | `P` |
| DNADamage (pc-t6) | `opencell/vivarium/karr_dna_damage.py` | `chromosome.damage_sites`, `chromosome.damage_burden`, optional `stimuli` coupling | `chromosome.replication_state`, `stimuli` | low direct (damage generation is mostly state event) | replication stage and stress/stimulus context | `P` |
| DNARepair (pc-t7) | `opencell/vivarium/karr_dna_repair.py` | `chromosome.damage_sites`, `chromosome.repair_progress`, `chromosome.repair_complete`, `substrates`, `requests` | `chromosome.damage_sites`, `chromosome.replication_state`, `protein`, `substrates_allocated` | ATP, NAD, dNTP patch synthesis, H2O | lesions from DNADamage + repair enzymes in `protein` | `P` |
| FtsZPolymerization (pc-t8) | `opencell/vivarium/karr_ftsz_polymerization.py` | `cell.ftsz_ring_state`, `cell.ftsz_ring_progress`, `cell.ftsz_ring_complete`, `substrates`, `requests` | `protein.counts`, `cell.geometry`, `substrates_allocated` | GTP (activation/polymer turnover) | FtsZ monomer pool from translation/protein state | `P` |
| Cytokinesis (pc-t9) | `opencell/vivarium/karr_cytokinesis.py` | `cell.division_state`, `cell.septum_progress`, `cell.division_event_count`, `cell.division_complete`, `substrates`, `requests` | `cell.ftsz_ring_complete`, `chromosome.segregation_complete`, `chromosome.replication_complete`, `cell.gate_allow_cytokinesis`, `substrates_allocated` | ATP/GTP (ring cycle + constriction support) | hard gate from coordinator + chromosome completion flags | `P` |
| TerminalOrganelleAssembly (pc-t10) | `opencell/vivarium/karr_terminal_organelle_assembly.py` | `cell.terminal_organelle_state`, `cell.terminal_organelle_progress`, `protein.location` deltas | `protein`, `cell.division_state`, `stimuli`, `substrates_allocated` | low-to-medium ATP/cofactor demand (localization/assembly) | division stage and required organelle proteins | `P` |

## New Stores Added In v5

v4 stores remain unchanged. v5 additively introduces `chromosome` and `cell`.

```python
{
    "chromosome": {
        # replication finite state machine (sole-writer set semantics where applicable)
        "replication_state": {
            "_default": "idle",  # idle|initiating|elongating|complete
            "_updater": "set",
            "_emit": True,
        },
        "replication_complete": {
            "_default": False,
            "_updater": "set",
            "_emit": True,
        },
        "fork_positions": {
            "left_nt": {"_default": 0, "_updater": "set", "_emit": True},
            "right_nt": {"_default": 0, "_updater": "set", "_emit": True},
        },
        "polymerized_nt": {
            "_default": 0.0,
            "_updater": "accumulate",
            "_emit": True,
        },
        # replication-initiation state (pc-t1-compatible)
        "dnaa_complex_count": {
            # key space set by process fixture site IDs (R1..R5 + non-OriC boxes)
            "<site_id>": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
        },
        # topology and condensation
        "supercoiled": {"_default": True, "_updater": "set", "_emit": True},
        "supercoiling_density": {"_default": -0.06, "_updater": "set", "_emit": True},
        "topology_regions": {
            "unreplicated": {"_default": 0.0, "_updater": "set", "_emit": False},
            "daughter_a": {"_default": 0.0, "_updater": "set", "_emit": False},
            "daughter_b": {"_default": 0.0, "_updater": "set", "_emit": False},
        },
        "condensation_state": {
            "_default": "uncondensed",  # uncondensed|condensing|condensed
            "_updater": "set",
            "_emit": True,
        },
        "smc_bound_sites": {
            "<region_id>": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
        },
        # damage and repair
        "damage_sites": {
            # sparse map: "<position_or_segment_id>:damage_type" -> count
            "<damage_id>": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
        },
        "damage_burden": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
        "repair_progress": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
        "repair_complete": {"_default": False, "_updater": "set", "_emit": True},
        # segregation
        "segregation_state": {
            "_default": "unsegregated",  # unsegregated|segregating|segregated
            "_updater": "set",
            "_emit": True,
        },
        "segregation_progress": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
        "segregation_complete": {"_default": False, "_updater": "set", "_emit": True},
    },
    "cell": {
        "cycle_phase": {
            "_default": "initiation",  # initiation|elongating|complete|segregating|dividing|divided
            "_updater": "set",
            "_emit": True,
        },
        "tick_index": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
        # coordinator gate written as sole-writer set
        "gate_allow_cytokinesis": {"_default": False, "_updater": "set", "_emit": True},
        # FtsZ/cytokinesis observables
        "ftsz_ring_state": {
            "_default": "idle",  # idle|forming|constricting|complete
            "_updater": "set",
            "_emit": True,
        },
        "ftsz_ring_progress": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
        "ftsz_ring_complete": {"_default": False, "_updater": "set", "_emit": True},
        "division_state": {
            "_default": "not_dividing",  # not_dividing|dividing|divided
            "_updater": "set",
            "_emit": True,
        },
        "septum_progress": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
        "division_complete": {"_default": False, "_updater": "set", "_emit": True},
        "division_event_count": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
        # geometry + terminal organelle state used by Phase C endpoints
        "geometry": {
            "volume": {"_default": 1.0, "_updater": "set", "_emit": False},
            "diameter": {"_default": 1.0, "_updater": "set", "_emit": False},
            "pinched_diameter": {"_default": 1.0, "_updater": "set", "_emit": False},
        },
        "terminal_organelle_state": {
            "_default": "single",  # single|duplicating|polarized|partitioned
            "_updater": "set",
            "_emit": True,
        },
        "terminal_organelle_progress": {
            "_default": 0.0,
            "_updater": "accumulate",
            "_emit": True,
        },
    },
}
```

## CellCycleCoordinator Step Design

### When it fires

- Runs once per tick at boundary `S2`, after process updates are committed for that tick.
- Reads committed `chromosome.*` and `cell.*` outputs from all processes.
- Writes only coordinator-owned phase and gate leaves (`cell.cycle_phase`, `cell.gate_allow_cytokinesis`, and optional deterministic normalization of `chromosome.replication_state`).

### State transitions enforced

Coordinator FSM:

1. `initiation -> elongating`
- condition: `chromosome.replication_state in {"initiating", "elongating"}` and forks moved from origin
- action: set `cell.cycle_phase = "elongating"`

2. `elongating -> complete`
- condition: `chromosome.replication_complete is True` OR both forks at/over terC bounds
- action: set `chromosome.replication_state = "complete"` and `cell.cycle_phase = "complete"`

3. `complete -> segregating`
- condition: replication complete and segregation has started (`chromosome.segregation_state == "segregating"` or progress > 0)
- action: set `cell.cycle_phase = "segregating"`

4. `segregating -> dividing`
- condition: `chromosome.replication_complete AND chromosome.segregation_complete AND cell.ftsz_ring_complete`
- action: set `cell.gate_allow_cytokinesis = True` and `cell.cycle_phase = "dividing"`

5. `dividing -> divided`
- condition: `cell.division_complete is True`
- action: set `cell.cycle_phase = "divided"`, increment one-time terminal observable via process-owned `division_event_count`

### Cytokinesis gate

Hard gate is exactly:

`replication_complete AND segregation_complete AND ftsz_ring_complete`

If false, coordinator forces `cell.gate_allow_cytokinesis = False`.

## Execution Order Rationale

Design keeps Karr one-second lag semantics and v4 allocation pattern:

1. `S0` request calculators
- existing v4 request calculators stay unchanged.
- phase C request production can be:
  - direct process-owned writes to `requests.<proc_name>`, or
  - a future `request_calculator_phase_c` aggregate step.

2. `S1` `karr_allocation_step`
- unchanged mechanism, expanded consumer list to include phase C substrate consumers.
- continues proportional fair-share clipping under scarcity.

3. `P` process tick
- all 27 Karr processes tick in Vivarium parallel mode on the same `time_step_s`.
- each process reads previous committed state and current allocation.

4. `S2` `cell_cycle_coordinator`
- runs last to enforce cross-process phase ratchet and write next-tick gates.

Why this order:

- preserves allocation-first constraint for substrate consumers.
- avoids same-tick ordering races between replication/segregation/cytokinesis processes.
- keeps v4 behavior stable and additive.

## Substrate-Allocation Conflict Analysis

Key competition domains in v5:

| Consumer class | Main substrates | Relative demand vs Phase A/B | Notes |
|---|---|---|---|
| Replication (pc-t2) | dATP, dCTP, dGTP, dTTP, ATP, NAD | high | dominant new burst consumer; strongest coupling to M1 pool and dNTP scarcity timing |
| DNASupercoiling (pc-t3) | ATP | medium | persistent ATP drain while forks active |
| ChromosomeCondensation (pc-t4) | ATP/H2O | low-medium | event-driven SMC binding load |
| ChromosomeSegregation (pc-t5) | GTP | low-medium | concentrated near post-replication window |
| DNARepair (pc-t7) | ATP, NAD, dNTPs | low baseline, medium under damage bursts | competes with replication for dNTPs when damage burden spikes |
| FtsZPolymerization (pc-t8) | GTP | medium near division window | overlaps with translation/ribosome GTP demand |
| Cytokinesis (pc-t9) | ATP/GTP | low-medium | gated near end-of-cycle only |
| TerminalOrganelleAssembly (pc-t10) | ATP/cofactors | low | generally minor relative to replication and translation |

Interaction with existing A/B consumers:

- ATP: already heavily loaded by transcription/translation/protein maturation; Phase C adds sustained supercoiling + burst replication loads.
- GTP: existing translation/ribosome loads now share with FtsZ and segregation windows.
- dNTPs: mostly new contention from replication and repair; expected to be a primary pacing signal for cycle timing.

Expected magnitude summary:

- high: replication dNTP demand, ATP at elongation peak
- medium: translation/transcription baseline + FtsZ window + topology control
- low: terminal organelle and steady maintenance background

Fair-share behavior:

- `KarrAllocationStep` already implements proportional clipping and floor-to-int allocations.
- under scarcity, phase progression should slow naturally via lower allocations rather than violating mass balance.

## 10000-Tick Partial Cell-Cycle Integration Test Plan

This is an integration contract plan (not implemented in this design session).

### Runtime profile

- run: 10,000 ticks at `time_step_s=1`
- output probes every tick for:
  - `chromosome.replication_state`
  - `chromosome.fork_positions`
  - `chromosome.replication_complete`
  - `chromosome.segregation_complete`
  - `cell.ftsz_ring_complete`
  - `cell.division_state`
  - `cell.division_event_count`
  - substrate panels: ATP/GTP + dNTP quartet

### Success criteria (initial windows, to lock to incoming pc-t2..t10 traces)

| Observable | Expected window | Pass band |
|---|---|---|
| initiation reached (`replication_state` enters `initiating`) | ticks 5800-7000 | within window |
| elongation active (`replication_state == elongating`) | ticks 6200-8200 | sustained >500 ticks |
| replication completion | around tick 8000 | 7600-8600 |
| segregation completion | after replication complete | replication_complete + 200 to +1200 ticks |
| FtsZ ring complete | before division | no later than tick 9000 |
| division event | around tick 9000 | 8700-9400 and fires once |

### A6 semantics-contract tolerance bands

Use A6 defaults for numeric comparisons against expected traces:

- concentration class: `L_inf abs <= 0.2`, `L_inf rel <= 0.05`
- derived-signal class: `L_inf abs <= 0.05`, `L_inf rel <= 0.10`
- count class (ensemble mean when stochastic): `L_inf abs <= 5`, `L_inf rel <= 0.5`

For discrete phase transitions (string states), evaluate by tick-window assertions instead of numeric norms.

## Migration Path From v4

v4 remains callable and unchanged:

- keep `build_karr_chassis_v4` exactly as-is for current tests and downstream users.
- add new builder as additive entrypoint: `build_karr_chassis_v5`.
- do not replace v4 imports or `__all__` until pc-t2..t10 modules and integration tests are merged.

Suggested uplift sequence:

1. land phase C process modules independently (pc-t2..pc-t10)
2. add v5 wiring in a dedicated integration commit
3. keep dual-path builders (`v4`, `v5`) through at least one release cycle
4. only deprecate v4 after `test_no_regression_vs_chassis_v4` passes in CI

## Open Questions For Orchestrator Lift

1. confirm final module filenames and class names for pc-t2..pc-t10 to avoid integration rename churn
2. decide whether phase C requests are direct process writes or new request-calculator step(s)
3. confirm canonical chromosome coordinate schema (`left/right nt` vs richer region-index representation)
4. confirm target tick windows from per-process traces for replication completion and division
5. decide where to host final `CellCycleCoordinator` (inside `karr_composite.py` or dedicated module)


