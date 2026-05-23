# Phase C Final Integration - Refinement Notes

## Step A Inventory (pc-t1..pc-t10)

| Module | Class | Required `__init__` params (non-default) | `ports_schema` top-level keys | `chromosome.*` read/write | `cell.*` read/write | Allocation consumer substrates |
|---|---|---|---|---|---|---|
| `karr_replication_initiation.py` (pc-t1) | `KarrReplicationInitiationProcess` | none (`fixture_path` defaulted) | `chromosome`, `protein`, `substrates`, `requests`, `substrates_allocated` | Reads: `dnaa_complex_count`, `supercoiled`, `replication_state`; Writes: `dnaa_complex_count`, `replication_state` | none | `ATP`, `H2O` |
| `karr_replication.py` (pc-t2) | `KarrReplicationProcess` | none (`fixture_path` + chromosome fixture defaulted) | `chromosome`, `substrates`, `requests`, `substrates_allocated` | Reads: `replication_state`, `fork_position_bp`; Writes: `replication_state`, `fork_position_bp`, `events.replication_complete` | none | `DATP`, `DCTP`, `DGTP`, `DTTP`, `ATP` |
| `karr_dna_supercoiling.py` (pc-t3) | `KarrDNASupercoilingProcess` | none (`fixture_path` defaulted) | `chromosome`, `protein`, `substrates`, `requests`, `substrates_allocated` | Reads: `supercoil_density`, `replication_state`; Writes: `supercoil_density`, `supercoiled` | none | `ATP` |
| `karr_chromosome_condensation.py` (pc-t4) | `KarrChromosomeCondensationProcess` | none (`fixture_path` defaulted) | `chromosome`, `substrates`, `requests`, `substrates_allocated` | Reads: `replication_state`, `forks_passing`, `smc_bound_count`, `condensation_level`; Writes: `smc_bound_count`, `condensation_level` | none | `ATP`, `H2O` |
| `karr_chromosome_segregation.py` (pc-t5) | `KarrChromosomeSegregationProcess` | none (`fixture_path` defaulted) | `chromosome`, `substrates`, `protein`, `requests`, `substrates_allocated` | Reads: `replication_state`, `supercoiled`, `segregation_progress`, `segregation_complete`, `daughter_pole_positions`; Writes: `segregation_progress`, `segregation_complete`, `daughter_pole_positions`, `cell_cycle_event` | none | `GTP`, `H2O` |
| `karr_dna_damage.py` (pc-t6) | `KarrDNADamageProcess` | none (`fixture_path` defaulted) | `chromosome` | Reads: `damage_sites`, `fork_positions`, `replication_state`; Writes: `damage_sites`, `replication_stall_flag` | none | none (no allocation contract for this module) |
| `karr_dna_repair.py` (pc-t7) | `KarrDNARepairProcess` | none (`fixture_path` defaulted) | `chromosome`, `protein`, `substrates`, `requests`, `substrates_allocated` | Reads: `damage_sites`; Writes: `damage_sites` (set replacement), `repair_count`, `repair_count_by_pathway` | none | `ATP`, `DATP`, `DCTP`, `DGTP`, `DTTP` |
| `karr_ftsz_polymerization.py` (pc-t8) | `KarrFtsZPolymerizationProcess` | none (`fixture_path` defaulted) | `cell`, `substrates`, `requests`, `substrates_allocated` | none | Reads: `ftsz_ring_count`; Writes: `ftsz_ring_count`, `ftsz_ring_complete` | `GTP` |
| `karr_cytokinesis.py` (pc-t9) | `KarrCytokinesisProcess` | none (`fixture_path` defaulted) | `cell`, `chromosome`, `substrates`, `requests`, `substrates_allocated` | Reads: `segregation_progress` | Reads: `ftsz_ring_complete`, `division_progress`, `division_complete`; Writes: `division_progress`, `division_complete` | `GTP` |
| `karr_terminal_organelle_assembly.py` (pc-t10) | `KarrTerminalOrganelleAssemblyProcess` | none (`fixture_path` defaulted) | `protein`, `cell` | none | Reads: `terminal_organelle_components_assembled`; Writes: `terminal_organelle_components_assembled`, `terminal_organelle_count` | none (no allocation contract for this module) |

## Ports-name conflicts found before wiring

1. `pc-t2` writes `chromosome.fork_position_bp` while `pc-t6` reads `chromosome.fork_positions`.
   Resolution: chassis topology maps `karr_dna_damage` chromosome port to a dedicated bridge store (`chromosome_for_damage`) and coordinator writes synced `fork_positions` there from canonical `fork_position_bp`.

2. `pc-t4` reads `chromosome.forks_passing`, but no Phase C process emits that key.
   Resolution: coordinator computes and writes `forks_passing` into `chromosome_for_condensation` from per-tick fork deltas.

3. Design text used `supercoiling_density`; implementation uses `supercoil_density`.
   Resolution: chassis wiring keeps canonical key `supercoil_density` used by process implementations.

4. Design text used `cell.division_event_count`; implementation currently exposes `cell.division_progress` + `cell.division_complete`.
   Resolution: v5 tests use `division_complete` timing; no synthetic event counter key introduced in v5.
