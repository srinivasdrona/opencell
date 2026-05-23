# Cross-Process Key Matrix

- Generated (UTC): 2026-05-23T04:50:09Z
- Source scan rows (expanded): 2416
- Matrix rows (compressed): 61
- Scope: `chromosome.*`, `cell.*`, `substrates.*`, `requests.*`, `substrates_allocated.*`
- Expanded machine-readable scan: `docs/design/_cross_process_key_scan.json`

| Process | Module | Leaf Path | _default | _updater | Role | Notes |
|---|---|---|---|---|---|---|
| pc-t1-ref | `opencell/vivarium/karr_replication_initiation.py` | `chromosome.dnaa_complex_count.<site_id>` | `0` | `accumulate` | `writes` | count=2283; sample=DnaA_box_0001, DnaA_box_0002, DnaA_box_0003, DnaA_box_0004, DnaA_box_0005, DnaA_box_0006 |
| pc-t1-ref | `opencell/vivarium/karr_replication_initiation.py` | `chromosome.replication_state` | `'idle'` | `set` | `reads` |  |
| pc-t1-ref | `opencell/vivarium/karr_replication_initiation.py` | `chromosome.supercoiled` | `True` | `set` | `reads` |  |
| pc-t1-ref | `opencell/vivarium/karr_replication_initiation.py` | `requests.karr_replication_initiation.<wid>` | `0.0` | `set` | `writes` | count=2; sample=ATP, H2O |
| pc-t1-ref | `opencell/vivarium/karr_replication_initiation.py` | `substrates.<wid>` | `0.0` | `accumulate` | `writes` | count=5; sample=ADP, ATP, H, H2O, PI |
| pc-t1-ref | `opencell/vivarium/karr_replication_initiation.py` | `substrates_allocated.karr_replication_initiation.<wid>` | `0.0` | `accumulate` | `writes` | count=2; sample=ATP, H2O |
| pc-t2 | `opencell/vivarium/karr_replication.py` | `chromosome.events.replication_complete` | `0.0` | `accumulate` | `writes` |  |
| pc-t2 | `opencell/vivarium/karr_replication.py` | `chromosome.fork_position_bp.left` | `0.0` | `accumulate` | `both` |  |
| pc-t2 | `opencell/vivarium/karr_replication.py` | `chromosome.fork_position_bp.right` | `0.0` | `accumulate` | `both` |  |
| pc-t2 | `opencell/vivarium/karr_replication.py` | `chromosome.replication_state` | `'idle'` | `set` | `reads` |  |
| pc-t2 | `opencell/vivarium/karr_replication.py` | `requests.karr_replication.<wid>` | `0.0` | `set` | `writes` | count=5; sample=ATP, DATP, DCTP, DGTP, DTTP |
| pc-t2 | `opencell/vivarium/karr_replication.py` | `substrates.<wid>` | `0.0` | `accumulate` | `writes` | count=16; sample=ADP, AMP, ATP, CTP, DATP, DCTP |
| pc-t2 | `opencell/vivarium/karr_replication.py` | `substrates_allocated.karr_replication.<wid>` | `0.0` | `accumulate` | `writes` | count=5; sample=ATP, DATP, DCTP, DGTP, DTTP |
| pc-t3 | `opencell/vivarium/karr_dna_supercoiling.py` | `chromosome.replication_state` | `'idle'` | `set` | `reads` |  |
| pc-t3 | `opencell/vivarium/karr_dna_supercoiling.py` | `chromosome.supercoil_density` | `-0.06` | `accumulate` | `reads` |  |
| pc-t3 | `opencell/vivarium/karr_dna_supercoiling.py` | `chromosome.supercoiled` | `True` | `set` | `writes` |  |
| pc-t3 | `opencell/vivarium/karr_dna_supercoiling.py` | `requests.karr_dna_supercoiling.<wid>` | `0.0` | `set` | `writes` | count=1; sample=ATP |
| pc-t3 | `opencell/vivarium/karr_dna_supercoiling.py` | `substrates.<wid>` | `0.0` | `accumulate` | `writes` | count=5; sample=ADP, ATP, H, H2O, PI |
| pc-t3 | `opencell/vivarium/karr_dna_supercoiling.py` | `substrates_allocated.karr_dna_supercoiling.<wid>` | `0.0` | `accumulate` | `writes` | count=1; sample=ATP |
| pc-t4 | `opencell/vivarium/karr_chromosome_condensation.py` | `chromosome.condensation_level` | `0.9498557194969237` | `accumulate` | `reads` |  |
| pc-t4 | `opencell/vivarium/karr_chromosome_condensation.py` | `chromosome.forks_passing` | `False` | `set` | `reads` |  |
| pc-t4 | `opencell/vivarium/karr_chromosome_condensation.py` | `chromosome.replication_state` | `'idle'` | `set` | `reads` |  |
| pc-t4 | `opencell/vivarium/karr_chromosome_condensation.py` | `chromosome.smc_bound_count` | `78.0` | `accumulate` | `reads` |  |
| pc-t4 | `opencell/vivarium/karr_chromosome_condensation.py` | `requests.karr_chromosome_condensation.<wid>` | `0.0` | `set` | `writes` | count=2; sample=ATP, H2O |
| pc-t4 | `opencell/vivarium/karr_chromosome_condensation.py` | `substrates.<wid>` | `0.0` | `accumulate` | `writes` | count=5; sample=ADP, ATP, H, H2O, PI |
| pc-t4 | `opencell/vivarium/karr_chromosome_condensation.py` | `substrates_allocated.karr_chromosome_condensation.<wid>` | `0.0` | `accumulate` | `writes` | count=2; sample=ATP, H2O |
| pc-t5 | `opencell/vivarium/karr_chromosome_segregation.py` | `chromosome.cell_cycle_event` | `'none'` | `set` | `writes` |  |
| pc-t5 | `opencell/vivarium/karr_chromosome_segregation.py` | `chromosome.daughter_pole_positions.left` | `0.0` | `accumulate` | `reads` |  |
| pc-t5 | `opencell/vivarium/karr_chromosome_segregation.py` | `chromosome.daughter_pole_positions.right` | `0.0` | `accumulate` | `reads` |  |
| pc-t5 | `opencell/vivarium/karr_chromosome_segregation.py` | `chromosome.replication_state` | `'idle'` | `set` | `reads` |  |
| pc-t5 | `opencell/vivarium/karr_chromosome_segregation.py` | `chromosome.segregation_complete` | `False` | `set` | `reads` |  |
| pc-t5 | `opencell/vivarium/karr_chromosome_segregation.py` | `chromosome.segregation_progress` | `0.0` | `accumulate` | `reads` |  |
| pc-t5 | `opencell/vivarium/karr_chromosome_segregation.py` | `chromosome.supercoiled` | `True` | `set` | `reads` |  |
| pc-t5 | `opencell/vivarium/karr_chromosome_segregation.py` | `requests.karr_chromosome_segregation.<wid>` | `0.0` | `set` | `writes` | count=2; sample=GTP, H2O |
| pc-t5 | `opencell/vivarium/karr_chromosome_segregation.py` | `substrates.<wid>` | `0.0` | `accumulate` | `writes` | count=5; sample=GDP, GTP, H, H2O, PI |
| pc-t5 | `opencell/vivarium/karr_chromosome_segregation.py` | `substrates_allocated.karr_chromosome_segregation.<wid>` | `0.0` | `accumulate` | `writes` | count=2; sample=GTP, H2O |
| pc-t6 | `opencell/vivarium/karr_dna_damage.py` | `chromosome.damage_sites` | `[]` | `accumulate` | `both` |  |
| pc-t6 | `opencell/vivarium/karr_dna_damage.py` | `chromosome.fork_positions` | `{'left': None, 'right': None}` | `set` | `writes` |  |
| pc-t6 | `opencell/vivarium/karr_dna_damage.py` | `chromosome.replication_stall_flag` | `0.0` | `accumulate` | `writes` |  |
| pc-t6 | `opencell/vivarium/karr_dna_damage.py` | `chromosome.replication_state` | `'idle'` | `set` | `writes` |  |
| pc-t7 | `opencell/vivarium/karr_dna_repair.py` | `chromosome.damage_sites` | `[]` | `set` | `reads` |  |
| pc-t7 | `opencell/vivarium/karr_dna_repair.py` | `chromosome.repair_count` | `0.0` | `accumulate` | `writes` |  |
| pc-t7 | `opencell/vivarium/karr_dna_repair.py` | `chromosome.repair_count_by_pathway.<pathway>` | `0.0` | `accumulate` | `writes` | count=4; sample=ber, hr, ner, nhej_like |
| pc-t7 | `opencell/vivarium/karr_dna_repair.py` | `requests.karr_dna_repair.<wid>` | `0.0` | `set` | `writes` | count=5; sample=ATP, DATP, DCTP, DGTP, DTTP |
| pc-t7 | `opencell/vivarium/karr_dna_repair.py` | `substrates.<wid>` | `0.0` | `accumulate` | `writes` | count=5; sample=ATP, DATP, DCTP, DGTP, DTTP |
| pc-t7 | `opencell/vivarium/karr_dna_repair.py` | `substrates_allocated.karr_dna_repair.<wid>` | `0.0` | `accumulate` | `writes` | count=5; sample=ATP, DATP, DCTP, DGTP, DTTP |
| pc-t8 | `opencell/vivarium/karr_ftsz_polymerization.py` | `cell.ftsz_ring_complete` | `False` | `set` | `writes` |  |
| pc-t8 | `opencell/vivarium/karr_ftsz_polymerization.py` | `cell.ftsz_ring_count` | `390.0` | `accumulate` | `reads` |  |
| pc-t8 | `opencell/vivarium/karr_ftsz_polymerization.py` | `requests.karr_ftsz_polymerization.<wid>` | `0.0` | `set` | `writes` | count=1; sample=GTP |
| pc-t8 | `opencell/vivarium/karr_ftsz_polymerization.py` | `substrates.<wid>` | `0.0` | `accumulate` | `writes` | count=5; sample=GDP, GTP, H, H2O, PI |
| pc-t8 | `opencell/vivarium/karr_ftsz_polymerization.py` | `substrates_allocated.karr_ftsz_polymerization.<wid>` | `0.0` | `set` | `writes` | count=1; sample=GTP |
| pc-t9 | `opencell/vivarium/karr_cytokinesis.py` | `cell.division_complete` | `False` | `set` | `reads` |  |
| pc-t9 | `opencell/vivarium/karr_cytokinesis.py` | `cell.division_progress` | `0.0` | `accumulate` | `reads` |  |
| pc-t9 | `opencell/vivarium/karr_cytokinesis.py` | `cell.ftsz_ring_complete` | `False` | `set` | `writes` |  |
| pc-t9 | `opencell/vivarium/karr_cytokinesis.py` | `chromosome.segregation_progress` | `0.0` | `accumulate` | `writes` |  |
| pc-t9 | `opencell/vivarium/karr_cytokinesis.py` | `requests.karr_cytokinesis.<wid>` | `0.0` | `set` | `writes` | count=1; sample=GTP |
| pc-t9 | `opencell/vivarium/karr_cytokinesis.py` | `substrates.<wid>` | `0.0` | `accumulate` | `writes` | count=4; sample=GTP, H, H2O, PI |
| pc-t9 | `opencell/vivarium/karr_cytokinesis.py` | `substrates_allocated.karr_cytokinesis.<wid>` | `0.0` | `accumulate` | `writes` | count=1; sample=GTP |
| pc-t10 | `opencell/vivarium/karr_terminal_organelle_assembly.py` | `cell.terminal_organelle_components_assembled.<wid>` | `0.0` | `accumulate` | `writes` | count=8; sample=MG_191_MONOMER, MG_192_MONOMER, MG_217_MONOMER, MG_218_MONOMER, MG_312_MONOMER, MG_317_MONOMER |
| pc-t10 | `opencell/vivarium/karr_terminal_organelle_assembly.py` | `cell.terminal_organelle_count` | `0.0` | `accumulate` | `reads` |  |
| pd-t1 | `opencell/vivarium/karr_host_interaction.py` | `(module missing)` | `n/a` | `n/a` | `n/a` | opencell.vivarium.karr_host_interaction |
