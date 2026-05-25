# Cross-layer observations (out of L3/L4/L6 scope)

| layer | process_name | observation | suggested_owner |
|---|---|---|---|
| L2 | DNADamage | Process topology exposes only `chromosome` and has no `requests`/`substrates_allocated` path (`opencell/vivarium/karr_composite.py:1630-1632`; `opencell/vivarium/karr_dna_damage.py:124-127`). | Composition audit (`swarm/composition`) |
| L2 | Metabolism | Direct shared-substrate writeback with no allocator enrollment (`opencell/vivarium/karr_metabolism.py:420,490`; `opencell/vivarium/karr_composite.py:1380-1409`). | Composition audit (`swarm/composition`) |
| L2 | Transcription | Direct substrate deltas (`ATP/CTP/GTP/UTP`) with no allocator request/allocated ports (`opencell/vivarium/karr_transcription.py:173-180`; `opencell/vivarium/karr_composite.py:1504-1514,1380-1409`). | Composition audit (`swarm/composition`) |
| L2 | Translation | Direct amino-acid substrate deltas with no allocator enrollment (`opencell/vivarium/karr_translation.py:137-140`; `opencell/vivarium/karr_composite.py:1510-1514,1380-1409`). | Composition audit (`swarm/composition`) |
| L5 | ChromosomeCondensation | `_allocated_or_state` falls back to global `substrates` when allocation is zero (`opencell/vivarium/karr_chromosome_condensation.py:244-245,326-335`). | L5 helper-semantics agent (`swarm/l5-semantics`) |
| L5 | ChromosomeSegregation | `_allocated_or_state` zero-allocation fallback to global pool (`opencell/vivarium/karr_chromosome_segregation.py:213,272-273`). | L5 helper-semantics agent (`swarm/l5-semantics`) |
| L5 | Cytokinesis | `_allocated_or_state` fallback allows zero-grant progression (`opencell/vivarium/karr_cytokinesis.py:205,265-270`). | L5 helper-semantics agent (`swarm/l5-semantics`) |
| L5 | DNARepair | `_allocated_or_state` fallback path on tracked substrates (`opencell/vivarium/karr_dna_repair.py:286,547-554`). | L5 helper-semantics agent (`swarm/l5-semantics`) |
| L5 | Replication | `_allocated_or_state` fallback on zero-grant substrates (`opencell/vivarium/karr_replication.py:185,267-271`). | L5 helper-semantics agent (`swarm/l5-semantics`) |
| L5 | ReplicationInitiation | `_allocated_or_state` fallback on ATP/H2O (`opencell/vivarium/karr_replication_initiation.py:212-213,274-283`). | L5 helper-semantics agent (`swarm/l5-semantics`) |
| L5 | RNAProcessing | Reads allocated counts only when positive and otherwise uses baseline substrate state (`opencell/vivarium/karr_rna_processing.py:242`). | L5 helper-semantics agent (`swarm/l5-semantics`) |
| L5 | tRNAAminoacylation | Allocation read path falls back to global substrate pool on zero allocations (`opencell/vivarium/karr_trna_aminoacylation.py:125-132`). | L5 helper-semantics agent (`swarm/l5-semantics`) |
| L5 | ProteinFolding | `_allocated_or_free` fallback behavior on zero allocations (`opencell/vivarium/karr_protein_folding.py:159,234-239`). | L5 helper-semantics agent (`swarm/l5-semantics`) |
| L5 | ProteinModification | Zero-allocation fallback to global substrate pool (`opencell/vivarium/karr_protein_modification.py:147-153`). | L5 helper-semantics agent (`swarm/l5-semantics`) |
| L5 | ProteinProcessingI | Allocated-or-baseline substrate read fallback (`opencell/vivarium/karr_protein_processing_i.py:143,241-247`). | L5 helper-semantics agent (`swarm/l5-semantics`) |
