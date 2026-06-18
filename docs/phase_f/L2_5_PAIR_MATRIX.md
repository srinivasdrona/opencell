# L2.5 Pair Matrix

## 1. Executive summary

- Total processes: 28
- Total pairs: 378
- Shared-pool pairs: 256
- Disjoint pairs: 122
- Tier 1 pairs (must-pass priority): 183
- Tier 2 pairs (should-pass): 72
- Tier 3 pairs (informational): 1
- L2.5.2 honest-required shared pairs (catalog-filtered): 211
- Catalog filter mode: `fallback:in_scope_L2_2` from `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`
- Source digest: `d2f21834ce0f93192b0194fdcd9716686327f63a5b9fb3f9a05fdd0c5e3eddbb`
- Deterministic generated_at: `2017-04-19T05:18:11Z`

## 2. Pair count matrix

```text
Idx Process                      1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17  18  19  20  21  22  23  24  25  26  27  28
  1 ChromosomeCondensation     -   3   3   2   5   5   3   0   0   5   0   5   5   4   2   2   5   2   3   5   5   5   3   0   4   0   3   5
  2 ChromosomeSegregation      3   -   3   2   3   4   5   0   0   5   0   5   3   2   2   2   5   2   2   5   4   3   7   0   3   0   5   3
  3 Cytokinesis                3   3   -   2   3   3   6   0   0   3   0   3   3   2   2   2   3   2   2   3   3   3   3   0   2   0   3   3
  4 DNADamage                  2   2   2   -  39   2   2   0   0  21   0   3   2   1   2   2   2   3   2   2   2   2   2   0   2   0   2   2
  5 DNARepair                  5   3   3  39   -   5   3   0   0 198   0   7   5   5   2   2   5   3   7   5  15   5   3   0   6   0   3   7
  6 DNASupercoiling            5   4   3   2   5   -   3   0   0   5   0   5   5   4   2   2   5   2   3   5   5   5   3   0   4   0   3   5
  7 FtsZPolymerization         3   5   6   2   3   3   -   0   0   5   0   5   3   2   2   2   5   2   2   5   4   3   5   0   3   0   5   3
  8 HostInteraction            0   0   0   0   0   0   0   -   0   1   0   0   0   0   0   0   0   0   0   0   0   0   0   4   0   0   0   0
  9 MacromolecularComplexation   0   0   0   0   0   0   0   0   -   0   0   0 147   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0
 10 Metabolism                 5   5   3  21 198   5   5   1   0   -   0  53  11  16   4   5   7  39  30   7  16   5   5   0  12   0  26  30
 11 ProteinActivation          0   0   0   0   0   0   0   0   0   0   -   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0
 12 ProteinDecay               5   5   3   3   7   5   5   0   0  53   0   -  11  14   4   3   7  26  16  14   8   5   8   0   7   0  27  29
 13 ProteinFolding             5   3   3   2   5   5   3   0 147  11   0  11   - 486 484 484 487   2   3   5   5   5  57   0   4   0   3   5
 14 ProteinModification        4   2   2   1   5   4   2   0   0  16   0  14 486   - 483 483 486   7   5   4   5   4  54   0   4   0   7  10
 15 ProteinProcessingI         2   2   2   2   2   2   2   0   0   4   0   4 484 483   - 484 484   4   2   2   2   2  54   0   2   0   3   3
 16 ProteinProcessingII        2   2   2   2   2   2   2   0   0   5   0   3 484 483 484   - 484   2   2   2   2   2  54   0   2   0   2   2
 17 ProteinTranslocation       5   5   3   2   5   5   5   0   0   7   0   7 487 486 484 484   -   2   3   7   6   5  57   0   5   0   5   5
 18 RNADecay                   2   2   2   3   3   2   2   0   0  39   0  26   2   7   4   2   2   -  20   2   3   2   2   0   6   0  24  24
 19 RNAModification            3   2   2   2   7   3   2   0   0  30   0  16   3   5   2   2   3  20   - 350   5   3   5   0   8   0  43  47
 20 RNAProcessing              5   5   3   2   5   5   5   0   0   7   0  14   5   4   2   2   7   2 350   -   6   5   8   0   5   0  42  42
 21 Replication                5   4   3   2  15   5   4   0   0  16   0   8   5   5   2   2   6   3   5   6   -   5   4   0   9   0   4   7
 22 ReplicationInitiation      5   3   3   2   5   5   3   0   0   5   0   5   5   4   2   2   5   2   3   5   5   -   3   0   4   0   3   5
 23 RibosomeAssembly           3   7   3   2   3   3   5   0   0   5   0   8  57  54  54  54  57   2   5   8   4   3   -   0   3   0   5   3
 24 TerminalOrganelleAssembly   0   0   0   0   0   0   0   4   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   -   0   0   0   0
 25 Transcription              4   3   2   2   6   4   3   0   0  12   0   7   4   4   2   2   5   6   8   5   9   4   3   0   -   0   3   6
 26 TranscriptionalRegulation   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   0   -   0   0
 27 Translation                3   5   3   2   3   3   5   0   0  26   0  27   3   7   3   2   5  24  43  42   4   3   5   0   3   0   -  62
 28 tRNAAminoacylation         5   3   3   2   7   5   3   0   0  30   0  29   5  10   3   2   5  24  47  42   7   5   3   0   6   0  62   -
```

## 3. Tier 1 pair list

| process_A | process_B | substrates_overlap | enzymes_overlap | monomers_overlap | complexs_overlap | rnas_overlap | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| ProteinFolding | ProteinTranslocation | 5 | 0 | 482 | 0 | 0 | 487 |
| ProteinFolding | ProteinModification | 4 | 0 | 482 | 0 | 0 | 486 |
| ProteinModification | ProteinTranslocation | 4 | 0 | 482 | 0 | 0 | 486 |
| RNAModification | RNAProcessing | 3 | 0 | 0 | 0 | 347 | 350 |
| DNARepair | Metabolism | 197 | 1 | 0 | 0 | 0 | 198 |
| Translation | tRNAAminoacylation | 24 | 1 | 0 | 0 | 37 | 62 |
| ProteinFolding | RibosomeAssembly | 3 | 0 | 52 | 2 | 0 | 57 |
| ProteinTranslocation | RibosomeAssembly | 5 | 0 | 52 | 0 | 0 | 57 |
| Metabolism | ProteinDecay | 53 | 0 | 0 | 0 | 0 | 53 |
| RNAModification | tRNAAminoacylation | 10 | 0 | 0 | 0 | 37 | 47 |
| RNAModification | Translation | 6 | 0 | 0 | 0 | 37 | 43 |
| RNAProcessing | Translation | 5 | 0 | 0 | 0 | 37 | 42 |
| RNAProcessing | tRNAAminoacylation | 5 | 0 | 0 | 0 | 37 | 42 |
| DNADamage | DNARepair | 39 | 0 | 0 | 0 | 0 | 39 |
| Metabolism | RNADecay | 39 | 0 | 0 | 0 | 0 | 39 |
| Metabolism | RNAModification | 29 | 1 | 0 | 0 | 0 | 30 |
| Metabolism | tRNAAminoacylation | 30 | 0 | 0 | 0 | 0 | 30 |
| ProteinDecay | tRNAAminoacylation | 28 | 0 | 0 | 0 | 1 | 29 |
| ProteinDecay | Translation | 26 | 0 | 0 | 0 | 1 | 27 |
| Metabolism | Translation | 26 | 0 | 0 | 0 | 0 | 26 |
| ProteinDecay | RNADecay | 26 | 0 | 0 | 0 | 0 | 26 |
| RNADecay | Translation | 23 | 1 | 0 | 0 | 0 | 24 |
| RNADecay | tRNAAminoacylation | 24 | 0 | 0 | 0 | 0 | 24 |
| DNADamage | Metabolism | 21 | 0 | 0 | 0 | 0 | 21 |
| RNADecay | RNAModification | 20 | 0 | 0 | 0 | 0 | 20 |
| Metabolism | ProteinModification | 15 | 1 | 0 | 0 | 0 | 16 |
| Metabolism | Replication | 16 | 0 | 0 | 0 | 0 | 16 |
| ProteinDecay | RNAModification | 9 | 0 | 0 | 0 | 7 | 16 |
| DNARepair | Replication | 13 | 2 | 0 | 0 | 0 | 15 |
| ProteinDecay | ProteinModification | 14 | 0 | 0 | 0 | 0 | 14 |
| ProteinDecay | RNAProcessing | 7 | 0 | 0 | 0 | 7 | 14 |
| Metabolism | Transcription | 12 | 0 | 0 | 0 | 0 | 12 |
| Metabolism | ProteinFolding | 11 | 0 | 0 | 0 | 0 | 11 |
| ProteinDecay | ProteinFolding | 11 | 0 | 0 | 0 | 0 | 11 |
| ProteinModification | tRNAAminoacylation | 10 | 0 | 0 | 0 | 0 | 10 |
| Replication | Transcription | 9 | 0 | 0 | 0 | 0 | 9 |
| ProteinDecay | Replication | 8 | 0 | 0 | 0 | 0 | 8 |
| ProteinDecay | RibosomeAssembly | 5 | 0 | 0 | 0 | 3 | 8 |
| RNAModification | Transcription | 8 | 0 | 0 | 0 | 0 | 8 |
| RNAProcessing | RibosomeAssembly | 5 | 0 | 0 | 0 | 3 | 8 |
| ChromosomeSegregation | RibosomeAssembly | 5 | 2 | 0 | 0 | 0 | 7 |
| DNARepair | ProteinDecay | 7 | 0 | 0 | 0 | 0 | 7 |
| DNARepair | RNAModification | 7 | 0 | 0 | 0 | 0 | 7 |
| DNARepair | tRNAAminoacylation | 7 | 0 | 0 | 0 | 0 | 7 |
| Metabolism | ProteinTranslocation | 7 | 0 | 0 | 0 | 0 | 7 |
| Metabolism | RNAProcessing | 7 | 0 | 0 | 0 | 0 | 7 |
| ProteinDecay | ProteinTranslocation | 7 | 0 | 0 | 0 | 0 | 7 |
| ProteinDecay | Transcription | 7 | 0 | 0 | 0 | 0 | 7 |
| ProteinModification | RNADecay | 7 | 0 | 0 | 0 | 0 | 7 |
| ProteinModification | Translation | 7 | 0 | 0 | 0 | 0 | 7 |
| ProteinTranslocation | RNAProcessing | 7 | 0 | 0 | 0 | 0 | 7 |
| Replication | tRNAAminoacylation | 7 | 0 | 0 | 0 | 0 | 7 |
| Cytokinesis | FtsZPolymerization | 3 | 3 | 0 | 0 | 0 | 6 |
| DNARepair | Transcription | 6 | 0 | 0 | 0 | 0 | 6 |
| ProteinTranslocation | Replication | 6 | 0 | 0 | 0 | 0 | 6 |
| RNADecay | Transcription | 6 | 0 | 0 | 0 | 0 | 6 |
| RNAProcessing | Replication | 6 | 0 | 0 | 0 | 0 | 6 |
| Transcription | tRNAAminoacylation | 6 | 0 | 0 | 0 | 0 | 6 |
| ChromosomeCondensation | DNARepair | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | DNASupercoiling | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | Metabolism | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | ProteinDecay | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | ProteinFolding | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | ProteinTranslocation | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | RNAProcessing | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | Replication | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | ReplicationInitiation | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | tRNAAminoacylation | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeSegregation | FtsZPolymerization | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeSegregation | Metabolism | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeSegregation | ProteinDecay | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeSegregation | ProteinTranslocation | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeSegregation | RNAProcessing | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeSegregation | Translation | 5 | 0 | 0 | 0 | 0 | 5 |
| DNARepair | DNASupercoiling | 5 | 0 | 0 | 0 | 0 | 5 |
| DNARepair | ProteinFolding | 5 | 0 | 0 | 0 | 0 | 5 |
| DNARepair | ProteinModification | 5 | 0 | 0 | 0 | 0 | 5 |
| DNARepair | ProteinTranslocation | 5 | 0 | 0 | 0 | 0 | 5 |
| DNARepair | RNAProcessing | 5 | 0 | 0 | 0 | 0 | 5 |
| DNARepair | ReplicationInitiation | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | Metabolism | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | ProteinDecay | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | ProteinFolding | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | ProteinTranslocation | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | RNAProcessing | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | Replication | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | ReplicationInitiation | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | tRNAAminoacylation | 5 | 0 | 0 | 0 | 0 | 5 |
| FtsZPolymerization | Metabolism | 5 | 0 | 0 | 0 | 0 | 5 |
| FtsZPolymerization | ProteinDecay | 5 | 0 | 0 | 0 | 0 | 5 |
| FtsZPolymerization | ProteinTranslocation | 5 | 0 | 0 | 0 | 0 | 5 |
| FtsZPolymerization | RNAProcessing | 5 | 0 | 0 | 0 | 0 | 5 |
| FtsZPolymerization | RibosomeAssembly | 5 | 0 | 0 | 0 | 0 | 5 |
| FtsZPolymerization | Translation | 5 | 0 | 0 | 0 | 0 | 5 |
| Metabolism | ProteinProcessingII | 5 | 0 | 0 | 0 | 0 | 5 |
| Metabolism | ReplicationInitiation | 5 | 0 | 0 | 0 | 0 | 5 |
| Metabolism | RibosomeAssembly | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinDecay | ReplicationInitiation | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinFolding | RNAProcessing | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinFolding | Replication | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinFolding | ReplicationInitiation | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinFolding | tRNAAminoacylation | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinModification | RNAModification | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinModification | Replication | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinTranslocation | ReplicationInitiation | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinTranslocation | Transcription | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinTranslocation | Translation | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinTranslocation | tRNAAminoacylation | 5 | 0 | 0 | 0 | 0 | 5 |
| RNAModification | Replication | 5 | 0 | 0 | 0 | 0 | 5 |
| RNAProcessing | ReplicationInitiation | 5 | 0 | 0 | 0 | 0 | 5 |
| RNAProcessing | Transcription | 5 | 0 | 0 | 0 | 0 | 5 |
| Replication | ReplicationInitiation | 5 | 0 | 0 | 0 | 0 | 5 |
| ReplicationInitiation | tRNAAminoacylation | 5 | 0 | 0 | 0 | 0 | 5 |
| RibosomeAssembly | Translation | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | ProteinModification | 4 | 0 | 0 | 0 | 0 | 4 |
| ChromosomeCondensation | Transcription | 4 | 0 | 0 | 0 | 0 | 4 |
| ChromosomeSegregation | DNASupercoiling | 3 | 1 | 0 | 0 | 0 | 4 |
| ChromosomeSegregation | Replication | 4 | 0 | 0 | 0 | 0 | 4 |
| DNASupercoiling | ProteinModification | 4 | 0 | 0 | 0 | 0 | 4 |
| DNASupercoiling | Transcription | 4 | 0 | 0 | 0 | 0 | 4 |
| FtsZPolymerization | Replication | 4 | 0 | 0 | 0 | 0 | 4 |
| HostInteraction | TerminalOrganelleAssembly | 0 | 4 | 0 | 0 | 0 | 4 |
| Metabolism | ProteinProcessingI | 4 | 0 | 0 | 0 | 0 | 4 |
| ProteinDecay | ProteinProcessingI | 4 | 0 | 0 | 0 | 0 | 4 |
| ProteinFolding | Transcription | 4 | 0 | 0 | 0 | 0 | 4 |
| ProteinModification | RNAProcessing | 4 | 0 | 0 | 0 | 0 | 4 |
| ProteinModification | ReplicationInitiation | 4 | 0 | 0 | 0 | 0 | 4 |
| ProteinModification | Transcription | 4 | 0 | 0 | 0 | 0 | 4 |
| ProteinProcessingI | RNADecay | 4 | 0 | 0 | 0 | 0 | 4 |
| Replication | RibosomeAssembly | 4 | 0 | 0 | 0 | 0 | 4 |
| Replication | Translation | 4 | 0 | 0 | 0 | 0 | 4 |
| ReplicationInitiation | Transcription | 4 | 0 | 0 | 0 | 0 | 4 |
| ChromosomeCondensation | ChromosomeSegregation | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeCondensation | Cytokinesis | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeCondensation | FtsZPolymerization | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeCondensation | RNAModification | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeCondensation | RibosomeAssembly | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeCondensation | Translation | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeSegregation | Cytokinesis | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeSegregation | DNARepair | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeSegregation | ProteinFolding | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeSegregation | ReplicationInitiation | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeSegregation | Transcription | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeSegregation | tRNAAminoacylation | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | DNARepair | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | DNASupercoiling | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | Metabolism | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | ProteinDecay | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | ProteinFolding | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | ProteinTranslocation | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | RNAProcessing | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | Replication | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | ReplicationInitiation | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | RibosomeAssembly | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | Translation | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | tRNAAminoacylation | 3 | 0 | 0 | 0 | 0 | 3 |
| DNADamage | ProteinDecay | 3 | 0 | 0 | 0 | 0 | 3 |
| DNADamage | RNADecay | 3 | 0 | 0 | 0 | 0 | 3 |
| DNARepair | FtsZPolymerization | 3 | 0 | 0 | 0 | 0 | 3 |
| DNARepair | RNADecay | 3 | 0 | 0 | 0 | 0 | 3 |
| DNARepair | RibosomeAssembly | 3 | 0 | 0 | 0 | 0 | 3 |
| DNARepair | Translation | 3 | 0 | 0 | 0 | 0 | 3 |
| DNASupercoiling | FtsZPolymerization | 3 | 0 | 0 | 0 | 0 | 3 |
| DNASupercoiling | RNAModification | 3 | 0 | 0 | 0 | 0 | 3 |
| DNASupercoiling | RibosomeAssembly | 3 | 0 | 0 | 0 | 0 | 3 |
| DNASupercoiling | Translation | 3 | 0 | 0 | 0 | 0 | 3 |
| FtsZPolymerization | ProteinFolding | 3 | 0 | 0 | 0 | 0 | 3 |
| FtsZPolymerization | ReplicationInitiation | 3 | 0 | 0 | 0 | 0 | 3 |
| FtsZPolymerization | Transcription | 3 | 0 | 0 | 0 | 0 | 3 |
| FtsZPolymerization | tRNAAminoacylation | 3 | 0 | 0 | 0 | 0 | 3 |
| ProteinDecay | ProteinProcessingII | 3 | 0 | 0 | 0 | 0 | 3 |
| ProteinFolding | RNAModification | 3 | 0 | 0 | 0 | 0 | 3 |
| ProteinFolding | Translation | 3 | 0 | 0 | 0 | 0 | 3 |
| ProteinProcessingI | Translation | 3 | 0 | 0 | 0 | 0 | 3 |
| ProteinProcessingI | tRNAAminoacylation | 3 | 0 | 0 | 0 | 0 | 3 |
| ProteinTranslocation | RNAModification | 3 | 0 | 0 | 0 | 0 | 3 |
| RNADecay | Replication | 3 | 0 | 0 | 0 | 0 | 3 |
| RNAModification | ReplicationInitiation | 3 | 0 | 0 | 0 | 0 | 3 |
| ReplicationInitiation | RibosomeAssembly | 3 | 0 | 0 | 0 | 0 | 3 |
| ReplicationInitiation | Translation | 3 | 0 | 0 | 0 | 0 | 3 |
| RibosomeAssembly | Transcription | 3 | 0 | 0 | 0 | 0 | 3 |
| RibosomeAssembly | tRNAAminoacylation | 3 | 0 | 0 | 0 | 0 | 3 |
| Transcription | Translation | 3 | 0 | 0 | 0 | 0 | 3 |

## 4. Tier 2 pair list

| process_A | process_B | substrates_overlap | enzymes_overlap | monomers_overlap | complexs_overlap | rnas_overlap | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| ProteinFolding | ProteinProcessingI | 2 | 0 | 482 | 0 | 0 | 484 |
| ProteinFolding | ProteinProcessingII | 2 | 0 | 482 | 0 | 0 | 484 |
| ProteinProcessingI | ProteinProcessingII | 2 | 0 | 482 | 0 | 0 | 484 |
| ProteinProcessingI | ProteinTranslocation | 2 | 0 | 482 | 0 | 0 | 484 |
| ProteinProcessingII | ProteinTranslocation | 2 | 0 | 482 | 0 | 0 | 484 |
| ProteinModification | ProteinProcessingI | 1 | 0 | 482 | 0 | 0 | 483 |
| ProteinModification | ProteinProcessingII | 1 | 0 | 482 | 0 | 0 | 483 |
| ProteinModification | RibosomeAssembly | 2 | 0 | 52 | 0 | 0 | 54 |
| ProteinProcessingI | RibosomeAssembly | 2 | 0 | 52 | 0 | 0 | 54 |
| ProteinProcessingII | RibosomeAssembly | 2 | 0 | 52 | 0 | 0 | 54 |
| RNAModification | RibosomeAssembly | 2 | 0 | 0 | 0 | 3 | 5 |
| ChromosomeCondensation | DNADamage | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeCondensation | ProteinProcessingI | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeCondensation | ProteinProcessingII | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeCondensation | RNADecay | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeSegregation | DNADamage | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeSegregation | ProteinModification | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeSegregation | ProteinProcessingI | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeSegregation | ProteinProcessingII | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeSegregation | RNADecay | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeSegregation | RNAModification | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | DNADamage | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | ProteinModification | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | ProteinProcessingI | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | ProteinProcessingII | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | RNADecay | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | RNAModification | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | Transcription | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | DNASupercoiling | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | FtsZPolymerization | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | ProteinFolding | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | ProteinProcessingI | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | ProteinProcessingII | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | ProteinTranslocation | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | RNAModification | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | RNAProcessing | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | Replication | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | ReplicationInitiation | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | RibosomeAssembly | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | Transcription | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | Translation | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | tRNAAminoacylation | 2 | 0 | 0 | 0 | 0 | 2 |
| DNARepair | ProteinProcessingI | 2 | 0 | 0 | 0 | 0 | 2 |
| DNARepair | ProteinProcessingII | 2 | 0 | 0 | 0 | 0 | 2 |
| DNASupercoiling | ProteinProcessingI | 2 | 0 | 0 | 0 | 0 | 2 |
| DNASupercoiling | ProteinProcessingII | 2 | 0 | 0 | 0 | 0 | 2 |
| DNASupercoiling | RNADecay | 2 | 0 | 0 | 0 | 0 | 2 |
| FtsZPolymerization | ProteinModification | 2 | 0 | 0 | 0 | 0 | 2 |
| FtsZPolymerization | ProteinProcessingI | 2 | 0 | 0 | 0 | 0 | 2 |
| FtsZPolymerization | ProteinProcessingII | 2 | 0 | 0 | 0 | 0 | 2 |
| FtsZPolymerization | RNADecay | 2 | 0 | 0 | 0 | 0 | 2 |
| FtsZPolymerization | RNAModification | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinFolding | RNADecay | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingI | RNAModification | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingI | RNAProcessing | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingI | Replication | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingI | ReplicationInitiation | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingI | Transcription | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | RNADecay | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | RNAModification | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | RNAProcessing | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | Replication | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | ReplicationInitiation | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | Transcription | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | Translation | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | tRNAAminoacylation | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinTranslocation | RNADecay | 2 | 0 | 0 | 0 | 0 | 2 |
| RNADecay | RNAProcessing | 2 | 0 | 0 | 0 | 0 | 2 |
| RNADecay | ReplicationInitiation | 2 | 0 | 0 | 0 | 0 | 2 |
| RNADecay | RibosomeAssembly | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | ProteinModification | 1 | 0 | 0 | 0 | 0 | 1 |
| HostInteraction | Metabolism | 0 | 1 | 0 | 0 | 0 | 1 |

## 5. Tier 3 pair list

| process_A | process_B | substrates_overlap | enzymes_overlap | monomers_overlap | complexs_overlap | rnas_overlap | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| MacromolecularComplexation | ProteinFolding | 0 | 0 | 0 | 147 | 0 | 147 |

## 6. Disjoint pair list

| process_A | process_B |
|---|---|
| ChromosomeCondensation | HostInteraction |
| ChromosomeCondensation | MacromolecularComplexation |
| ChromosomeCondensation | ProteinActivation |
| ChromosomeCondensation | TerminalOrganelleAssembly |
| ChromosomeCondensation | TranscriptionalRegulation |
| ChromosomeSegregation | HostInteraction |
| ChromosomeSegregation | MacromolecularComplexation |
| ChromosomeSegregation | ProteinActivation |
| ChromosomeSegregation | TerminalOrganelleAssembly |
| ChromosomeSegregation | TranscriptionalRegulation |
| Cytokinesis | HostInteraction |
| Cytokinesis | MacromolecularComplexation |
| Cytokinesis | ProteinActivation |
| Cytokinesis | TerminalOrganelleAssembly |
| Cytokinesis | TranscriptionalRegulation |
| DNADamage | HostInteraction |
| DNADamage | MacromolecularComplexation |
| DNADamage | ProteinActivation |
| DNADamage | TerminalOrganelleAssembly |
| DNADamage | TranscriptionalRegulation |
| DNARepair | HostInteraction |
| DNARepair | MacromolecularComplexation |
| DNARepair | ProteinActivation |
| DNARepair | TerminalOrganelleAssembly |
| DNARepair | TranscriptionalRegulation |
| DNASupercoiling | HostInteraction |
| DNASupercoiling | MacromolecularComplexation |
| DNASupercoiling | ProteinActivation |
| DNASupercoiling | TerminalOrganelleAssembly |
| DNASupercoiling | TranscriptionalRegulation |
| FtsZPolymerization | HostInteraction |
| FtsZPolymerization | MacromolecularComplexation |
| FtsZPolymerization | ProteinActivation |
| FtsZPolymerization | TerminalOrganelleAssembly |
| FtsZPolymerization | TranscriptionalRegulation |
| HostInteraction | MacromolecularComplexation |
| HostInteraction | ProteinActivation |
| HostInteraction | ProteinDecay |
| HostInteraction | ProteinFolding |
| HostInteraction | ProteinModification |
| HostInteraction | ProteinProcessingI |
| HostInteraction | ProteinProcessingII |
| HostInteraction | ProteinTranslocation |
| HostInteraction | RNADecay |
| HostInteraction | RNAModification |
| HostInteraction | RNAProcessing |
| HostInteraction | Replication |
| HostInteraction | ReplicationInitiation |
| HostInteraction | RibosomeAssembly |
| HostInteraction | Transcription |
| HostInteraction | TranscriptionalRegulation |
| HostInteraction | Translation |
| HostInteraction | tRNAAminoacylation |
| MacromolecularComplexation | Metabolism |
| MacromolecularComplexation | ProteinActivation |
| MacromolecularComplexation | ProteinDecay |
| MacromolecularComplexation | ProteinModification |
| MacromolecularComplexation | ProteinProcessingI |
| MacromolecularComplexation | ProteinProcessingII |
| MacromolecularComplexation | ProteinTranslocation |
| MacromolecularComplexation | RNADecay |
| MacromolecularComplexation | RNAModification |
| MacromolecularComplexation | RNAProcessing |
| MacromolecularComplexation | Replication |
| MacromolecularComplexation | ReplicationInitiation |
| MacromolecularComplexation | RibosomeAssembly |
| MacromolecularComplexation | TerminalOrganelleAssembly |
| MacromolecularComplexation | Transcription |
| MacromolecularComplexation | TranscriptionalRegulation |
| MacromolecularComplexation | Translation |
| MacromolecularComplexation | tRNAAminoacylation |
| Metabolism | ProteinActivation |
| Metabolism | TerminalOrganelleAssembly |
| Metabolism | TranscriptionalRegulation |
| ProteinActivation | ProteinDecay |
| ProteinActivation | ProteinFolding |
| ProteinActivation | ProteinModification |
| ProteinActivation | ProteinProcessingI |
| ProteinActivation | ProteinProcessingII |
| ProteinActivation | ProteinTranslocation |
| ProteinActivation | RNADecay |
| ProteinActivation | RNAModification |
| ProteinActivation | RNAProcessing |
| ProteinActivation | Replication |
| ProteinActivation | ReplicationInitiation |
| ProteinActivation | RibosomeAssembly |
| ProteinActivation | TerminalOrganelleAssembly |
| ProteinActivation | Transcription |
| ProteinActivation | TranscriptionalRegulation |
| ProteinActivation | Translation |
| ProteinActivation | tRNAAminoacylation |
| ProteinDecay | TerminalOrganelleAssembly |
| ProteinDecay | TranscriptionalRegulation |
| ProteinFolding | TerminalOrganelleAssembly |
| ProteinFolding | TranscriptionalRegulation |
| ProteinModification | TerminalOrganelleAssembly |
| ProteinModification | TranscriptionalRegulation |
| ProteinProcessingI | TerminalOrganelleAssembly |
| ProteinProcessingI | TranscriptionalRegulation |
| ProteinProcessingII | TerminalOrganelleAssembly |
| ProteinProcessingII | TranscriptionalRegulation |
| ProteinTranslocation | TerminalOrganelleAssembly |
| ProteinTranslocation | TranscriptionalRegulation |
| RNADecay | TerminalOrganelleAssembly |
| RNADecay | TranscriptionalRegulation |
| RNAModification | TerminalOrganelleAssembly |
| RNAModification | TranscriptionalRegulation |
| RNAProcessing | TerminalOrganelleAssembly |
| RNAProcessing | TranscriptionalRegulation |
| Replication | TerminalOrganelleAssembly |
| Replication | TranscriptionalRegulation |
| ReplicationInitiation | TerminalOrganelleAssembly |
| ReplicationInitiation | TranscriptionalRegulation |
| RibosomeAssembly | TerminalOrganelleAssembly |
| RibosomeAssembly | TranscriptionalRegulation |
| TerminalOrganelleAssembly | Transcription |
| TerminalOrganelleAssembly | TranscriptionalRegulation |
| TerminalOrganelleAssembly | Translation |
| TerminalOrganelleAssembly | tRNAAminoacylation |
| Transcription | TranscriptionalRegulation |
| TranscriptionalRegulation | Translation |
| TranscriptionalRegulation | tRNAAminoacylation |

## 7. Per-process pair count

| process | shared_pool_partners | honest_required_partners |
|---|---:|---:|
| ChromosomeCondensation | 22 | 0 |
| ChromosomeSegregation | 22 | 0 |
| Cytokinesis | 22 | 20 |
| DNADamage | 22 | 20 |
| DNARepair | 22 | 20 |
| DNASupercoiling | 22 | 20 |
| FtsZPolymerization | 22 | 20 |
| HostInteraction | 2 | 0 |
| MacromolecularComplexation | 1 | 1 |
| Metabolism | 23 | 20 |
| ProteinActivation | 0 | 0 |
| ProteinDecay | 22 | 20 |
| ProteinFolding | 23 | 21 |
| ProteinModification | 22 | 20 |
| ProteinProcessingI | 22 | 20 |
| ProteinProcessingII | 22 | 20 |
| ProteinTranslocation | 22 | 20 |
| RNADecay | 22 | 20 |
| RNAModification | 22 | 20 |
| RNAProcessing | 22 | 20 |
| Replication | 22 | 20 |
| ReplicationInitiation | 22 | 20 |
| RibosomeAssembly | 22 | 20 |
| TerminalOrganelleAssembly | 1 | 0 |
| Transcription | 22 | 20 |
| TranscriptionalRegulation | 0 | 0 |
| Translation | 22 | 20 |
| tRNAAminoacylation | 22 | 20 |

## 8. Methodology

- Input source: `data/schemas/per_process/*.toml`
- Canonical state groups: `substrates`, `enzymes`, `monomers`, `complexs`, `rnas`
- Overlap for a group = `len(set(A[group]) & set(B[group]))`
- Total overlap = sum of all 5 group overlap counts
- Classification: `shared_pool` if total overlap > 0 else `disjoint`
- Tiering: Tier 1 if `max(substrates_overlap, enzymes_overlap) >= 3`; Tier 2 if substrate/enzyme overlap is 1-2; Tier 3 if overlap is only in RNAs/monomers/complexs
- Sorting: tier (1,2,3,disjoint), then `total_overlap` desc, then `process_a`, then `process_b`
- Acceptance tie-in: see `docs/phase_f/L2_5_ACCEPTANCE_RUBRIC.md` for L2.5 pair policy.
- Regenerate command: `bin\oc-py.cmd scripts/derive_l25_pair_matrix.py`
- Check-only command: `bin\oc-py.cmd scripts/derive_l25_pair_matrix.py --check-only`
