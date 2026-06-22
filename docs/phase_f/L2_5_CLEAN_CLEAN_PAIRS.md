# Clean-vs-clean L2.5 pair audit

## Cleanliness by process
  out ChromosomeCondensation           DIRTY
  out ChromosomeSegregation            CLEAN
   in Cytokinesis                      CLEAN
   in DNADamage                        CLEAN
   in DNARepair                        CLEAN
   in DNASupercoiling                  DIRTY
   in FtsZPolymerization               DIRTY
  out HostInteraction                  CLEAN
   in MacromolecularComplexation       CLEAN
   in Metabolism                       DIRTY
  out ProteinActivation                CLEAN
   in ProteinDecay                     DIRTY
   in ProteinFolding                   CLEAN
   in ProteinModification              DIRTY
   in ProteinProcessingI               CLEAN
   in ProteinProcessingII              CLEAN
   in ProteinTranslocation             CLEAN
   in RNADecay                         DIRTY
   in RNAModification                  CLEAN
   in RNAProcessing                    CLEAN
   in Replication                      DIRTY
   in ReplicationInitiation            DIRTY
   in RibosomeAssembly                 CLEAN
  out TerminalOrganelleAssembly        DIRTY
   in Transcription                    DIRTY
  out TranscriptionalRegulation        DIRTY
   in Translation                      DIRTY
   in tRNAAminoacylation               CLEAN

## Counts (all 28 L2.5 processes)
  Total L2.5 processes : 28
  Clean (no trace_hint): 15
  Dirty (has trace_hint): 13
  Clean processes: ['ChromosomeSegregation', 'Cytokinesis', 'DNADamage', 'DNARepair', 'HostInteraction', 'MacromolecularComplexation', 'ProteinActivation', 'ProteinFolding', 'ProteinProcessingI', 'ProteinProcessingII', 'ProteinTranslocation', 'RNAModification', 'RNAProcessing', 'RibosomeAssembly', 'tRNAAminoacylation']
  (For reference, L2.2 in-scope clean subset: ['Cytokinesis', 'DNADamage', 'DNARepair', 'MacromolecularComplexation', 'ProteinFolding', 'ProteinProcessingI', 'ProteinProcessingII', 'ProteinTranslocation', 'RNAModification', 'RNAProcessing', 'RibosomeAssembly', 'tRNAAminoacylation'])

## Pair counts (shared-pool only, overlap > 0)
  total shared-pool pairs : 256
  clean x clean           : 67  <-- TRUE BIOLOGY VALIDATION SET
  clean x dirty           : 134
  dirty x dirty           : 55

## Clean x clean pair list (sorted by overlap desc)
| process_A | process_B | overlap |
|---|---|---:|
| ProteinFolding | ProteinTranslocation | 487 |
| ProteinFolding | ProteinProcessingI | 484 |
| ProteinFolding | ProteinProcessingII | 484 |
| ProteinProcessingI | ProteinProcessingII | 484 |
| ProteinProcessingI | ProteinTranslocation | 484 |
| ProteinProcessingII | ProteinTranslocation | 484 |
| RNAModification | RNAProcessing | 350 |
| MacromolecularComplexation | ProteinFolding | 147 |
| ProteinFolding | RibosomeAssembly | 57 |
| ProteinTranslocation | RibosomeAssembly | 57 |
| ProteinProcessingI | RibosomeAssembly | 54 |
| ProteinProcessingII | RibosomeAssembly | 54 |
| RNAModification | tRNAAminoacylation | 47 |
| RNAProcessing | tRNAAminoacylation | 42 |
| DNADamage | DNARepair | 39 |
| RNAProcessing | RibosomeAssembly | 8 |
| ChromosomeSegregation | RibosomeAssembly | 7 |
| DNARepair | RNAModification | 7 |
| DNARepair | tRNAAminoacylation | 7 |
| ProteinTranslocation | RNAProcessing | 7 |
| ChromosomeSegregation | ProteinTranslocation | 5 |
| ChromosomeSegregation | RNAProcessing | 5 |
| DNARepair | ProteinFolding | 5 |
| DNARepair | ProteinTranslocation | 5 |
| DNARepair | RNAProcessing | 5 |
| ProteinFolding | RNAProcessing | 5 |
| ProteinFolding | tRNAAminoacylation | 5 |
| ProteinTranslocation | tRNAAminoacylation | 5 |
| RNAModification | RibosomeAssembly | 5 |
| ChromosomeSegregation | Cytokinesis | 3 |
| ChromosomeSegregation | DNARepair | 3 |
| ChromosomeSegregation | ProteinFolding | 3 |
| ChromosomeSegregation | tRNAAminoacylation | 3 |
| Cytokinesis | DNARepair | 3 |
| Cytokinesis | ProteinFolding | 3 |
| Cytokinesis | ProteinTranslocation | 3 |
| Cytokinesis | RNAProcessing | 3 |
| Cytokinesis | RibosomeAssembly | 3 |
| Cytokinesis | tRNAAminoacylation | 3 |
| DNARepair | RibosomeAssembly | 3 |
| ProteinFolding | RNAModification | 3 |
| ProteinProcessingI | tRNAAminoacylation | 3 |
| ProteinTranslocation | RNAModification | 3 |
| RibosomeAssembly | tRNAAminoacylation | 3 |
| ChromosomeSegregation | DNADamage | 2 |
| ChromosomeSegregation | ProteinProcessingI | 2 |
| ChromosomeSegregation | ProteinProcessingII | 2 |
| ChromosomeSegregation | RNAModification | 2 |
| Cytokinesis | DNADamage | 2 |
| Cytokinesis | ProteinProcessingI | 2 |
| Cytokinesis | ProteinProcessingII | 2 |
| Cytokinesis | RNAModification | 2 |
| DNADamage | ProteinFolding | 2 |
| DNADamage | ProteinProcessingI | 2 |
| DNADamage | ProteinProcessingII | 2 |
| DNADamage | ProteinTranslocation | 2 |
| DNADamage | RNAModification | 2 |
| DNADamage | RNAProcessing | 2 |
| DNADamage | RibosomeAssembly | 2 |
| DNADamage | tRNAAminoacylation | 2 |
| DNARepair | ProteinProcessingI | 2 |
| DNARepair | ProteinProcessingII | 2 |
| ProteinProcessingI | RNAModification | 2 |
| ProteinProcessingI | RNAProcessing | 2 |
| ProteinProcessingII | RNAModification | 2 |
| ProteinProcessingII | RNAProcessing | 2 |
| ProteinProcessingII | tRNAAminoacylation | 2 |
