# L2.5 Pair Matrix

## 1. Executive summary

- Total processes: 28
- Total pairs: 378
- Shared-pool pairs: 256
- Disjoint pairs: 122
- Tier 1 pairs (must-pass priority): 183
- Tier 2 pairs (should-pass): 72
- Tier 3 pairs (informational): 1
- L2.5.2 honest-required shared pairs (all shared-pool pairs): 256
- Catalog filter mode: `fallback:in_scope_L2_2` from `docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`
- Source digest: `d2f21834ce0f93192b0194fdcd9716686327f63a5b9fb3f9a05fdd0c5e3eddbb`
- Deterministic generated_at: `2017-04-19T05:18:11Z`

## 2. Pair complexity breakdown

| Complexity | Count | Description |
|---|---:|---|
| stochastic ↔ stochastic | 211 | Both sides use distributional oracle (CAUSE_1-7 taxonomy) |
| deterministic ↔ stochastic | 43 | One side bit-identity, other distributional |
| deterministic ↔ deterministic | 2 | Both sides bit-identity (strictest) |
| **Total honest-required** | **256** | All shared-pool pairs |

## 3. Pair count matrix

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

## 4. Tier 1 pair list

| process_A | process_B | oracle_type_a | oracle_type_b | pair_oracle_complexity | substrates_overlap | enzymes_overlap | monomers_overlap | complexs_overlap | rnas_overlap | total |
|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|
| ProteinFolding | ProteinTranslocation | distributional | distributional | stochastic_stochastic | 5 | 0 | 482 | 0 | 0 | 487 |
| ProteinFolding | ProteinModification | distributional | distributional | stochastic_stochastic | 4 | 0 | 482 | 0 | 0 | 486 |
| ProteinModification | ProteinTranslocation | distributional | distributional | stochastic_stochastic | 4 | 0 | 482 | 0 | 0 | 486 |
| RNAModification | RNAProcessing | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 347 | 350 |
| DNARepair | Metabolism | distributional | distributional | stochastic_stochastic | 197 | 1 | 0 | 0 | 0 | 198 |
| Translation | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 24 | 1 | 0 | 0 | 37 | 62 |
| ProteinFolding | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 3 | 0 | 52 | 2 | 0 | 57 |
| ProteinTranslocation | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 5 | 0 | 52 | 0 | 0 | 57 |
| Metabolism | ProteinDecay | distributional | distributional | stochastic_stochastic | 53 | 0 | 0 | 0 | 0 | 53 |
| RNAModification | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 10 | 0 | 0 | 0 | 37 | 47 |
| RNAModification | Translation | distributional | distributional | stochastic_stochastic | 6 | 0 | 0 | 0 | 37 | 43 |
| RNAProcessing | Translation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 37 | 42 |
| RNAProcessing | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 37 | 42 |
| DNADamage | DNARepair | distributional | distributional | stochastic_stochastic | 39 | 0 | 0 | 0 | 0 | 39 |
| Metabolism | RNADecay | distributional | distributional | stochastic_stochastic | 39 | 0 | 0 | 0 | 0 | 39 |
| Metabolism | RNAModification | distributional | distributional | stochastic_stochastic | 29 | 1 | 0 | 0 | 0 | 30 |
| Metabolism | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 30 | 0 | 0 | 0 | 0 | 30 |
| ProteinDecay | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 28 | 0 | 0 | 0 | 1 | 29 |
| ProteinDecay | Translation | distributional | distributional | stochastic_stochastic | 26 | 0 | 0 | 0 | 1 | 27 |
| Metabolism | Translation | distributional | distributional | stochastic_stochastic | 26 | 0 | 0 | 0 | 0 | 26 |
| ProteinDecay | RNADecay | distributional | distributional | stochastic_stochastic | 26 | 0 | 0 | 0 | 0 | 26 |
| RNADecay | Translation | distributional | distributional | stochastic_stochastic | 23 | 1 | 0 | 0 | 0 | 24 |
| RNADecay | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 24 | 0 | 0 | 0 | 0 | 24 |
| DNADamage | Metabolism | distributional | distributional | stochastic_stochastic | 21 | 0 | 0 | 0 | 0 | 21 |
| RNADecay | RNAModification | distributional | distributional | stochastic_stochastic | 20 | 0 | 0 | 0 | 0 | 20 |
| Metabolism | ProteinModification | distributional | distributional | stochastic_stochastic | 15 | 1 | 0 | 0 | 0 | 16 |
| Metabolism | Replication | distributional | distributional | stochastic_stochastic | 16 | 0 | 0 | 0 | 0 | 16 |
| ProteinDecay | RNAModification | distributional | distributional | stochastic_stochastic | 9 | 0 | 0 | 0 | 7 | 16 |
| DNARepair | Replication | distributional | distributional | stochastic_stochastic | 13 | 2 | 0 | 0 | 0 | 15 |
| ProteinDecay | ProteinModification | distributional | distributional | stochastic_stochastic | 14 | 0 | 0 | 0 | 0 | 14 |
| ProteinDecay | RNAProcessing | distributional | distributional | stochastic_stochastic | 7 | 0 | 0 | 0 | 7 | 14 |
| Metabolism | Transcription | distributional | distributional | stochastic_stochastic | 12 | 0 | 0 | 0 | 0 | 12 |
| Metabolism | ProteinFolding | distributional | distributional | stochastic_stochastic | 11 | 0 | 0 | 0 | 0 | 11 |
| ProteinDecay | ProteinFolding | distributional | distributional | stochastic_stochastic | 11 | 0 | 0 | 0 | 0 | 11 |
| ProteinModification | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 10 | 0 | 0 | 0 | 0 | 10 |
| Replication | Transcription | distributional | distributional | stochastic_stochastic | 9 | 0 | 0 | 0 | 0 | 9 |
| ProteinDecay | Replication | distributional | distributional | stochastic_stochastic | 8 | 0 | 0 | 0 | 0 | 8 |
| ProteinDecay | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 3 | 8 |
| RNAModification | Transcription | distributional | distributional | stochastic_stochastic | 8 | 0 | 0 | 0 | 0 | 8 |
| RNAProcessing | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 3 | 8 |
| ChromosomeSegregation | RibosomeAssembly | bit_identity | distributional | deterministic_stochastic | 5 | 2 | 0 | 0 | 0 | 7 |
| DNARepair | ProteinDecay | distributional | distributional | stochastic_stochastic | 7 | 0 | 0 | 0 | 0 | 7 |
| DNARepair | RNAModification | distributional | distributional | stochastic_stochastic | 7 | 0 | 0 | 0 | 0 | 7 |
| DNARepair | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 7 | 0 | 0 | 0 | 0 | 7 |
| Metabolism | ProteinTranslocation | distributional | distributional | stochastic_stochastic | 7 | 0 | 0 | 0 | 0 | 7 |
| Metabolism | RNAProcessing | distributional | distributional | stochastic_stochastic | 7 | 0 | 0 | 0 | 0 | 7 |
| ProteinDecay | ProteinTranslocation | distributional | distributional | stochastic_stochastic | 7 | 0 | 0 | 0 | 0 | 7 |
| ProteinDecay | Transcription | distributional | distributional | stochastic_stochastic | 7 | 0 | 0 | 0 | 0 | 7 |
| ProteinModification | RNADecay | distributional | distributional | stochastic_stochastic | 7 | 0 | 0 | 0 | 0 | 7 |
| ProteinModification | Translation | distributional | distributional | stochastic_stochastic | 7 | 0 | 0 | 0 | 0 | 7 |
| ProteinTranslocation | RNAProcessing | distributional | distributional | stochastic_stochastic | 7 | 0 | 0 | 0 | 0 | 7 |
| Replication | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 7 | 0 | 0 | 0 | 0 | 7 |
| Cytokinesis | FtsZPolymerization | distributional | distributional | stochastic_stochastic | 3 | 3 | 0 | 0 | 0 | 6 |
| DNARepair | Transcription | distributional | distributional | stochastic_stochastic | 6 | 0 | 0 | 0 | 0 | 6 |
| ProteinTranslocation | Replication | distributional | distributional | stochastic_stochastic | 6 | 0 | 0 | 0 | 0 | 6 |
| RNADecay | Transcription | distributional | distributional | stochastic_stochastic | 6 | 0 | 0 | 0 | 0 | 6 |
| RNAProcessing | Replication | distributional | distributional | stochastic_stochastic | 6 | 0 | 0 | 0 | 0 | 6 |
| Transcription | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 6 | 0 | 0 | 0 | 0 | 6 |
| ChromosomeCondensation | DNARepair | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | DNASupercoiling | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | Metabolism | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | ProteinDecay | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | ProteinFolding | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | ProteinTranslocation | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | RNAProcessing | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | Replication | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | ReplicationInitiation | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | tRNAAminoacylation | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeSegregation | FtsZPolymerization | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeSegregation | Metabolism | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeSegregation | ProteinDecay | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeSegregation | ProteinTranslocation | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeSegregation | RNAProcessing | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeSegregation | Translation | bit_identity | distributional | deterministic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNARepair | DNASupercoiling | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNARepair | ProteinFolding | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNARepair | ProteinModification | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNARepair | ProteinTranslocation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNARepair | RNAProcessing | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNARepair | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | Metabolism | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | ProteinDecay | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | ProteinFolding | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | ProteinTranslocation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | RNAProcessing | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | Replication | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| DNASupercoiling | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| FtsZPolymerization | Metabolism | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| FtsZPolymerization | ProteinDecay | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| FtsZPolymerization | ProteinTranslocation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| FtsZPolymerization | RNAProcessing | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| FtsZPolymerization | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| FtsZPolymerization | Translation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| Metabolism | ProteinProcessingII | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| Metabolism | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| Metabolism | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinDecay | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinFolding | RNAProcessing | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinFolding | Replication | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinFolding | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinFolding | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinModification | RNAModification | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinModification | Replication | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinTranslocation | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinTranslocation | Transcription | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinTranslocation | Translation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ProteinTranslocation | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| RNAModification | Replication | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| RNAProcessing | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| RNAProcessing | Transcription | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| Replication | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ReplicationInitiation | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| RibosomeAssembly | Translation | distributional | distributional | stochastic_stochastic | 5 | 0 | 0 | 0 | 0 | 5 |
| ChromosomeCondensation | ProteinModification | bit_identity | distributional | deterministic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| ChromosomeCondensation | Transcription | bit_identity | distributional | deterministic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| ChromosomeSegregation | DNASupercoiling | bit_identity | distributional | deterministic_stochastic | 3 | 1 | 0 | 0 | 0 | 4 |
| ChromosomeSegregation | Replication | bit_identity | distributional | deterministic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| DNASupercoiling | ProteinModification | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| DNASupercoiling | Transcription | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| FtsZPolymerization | Replication | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| HostInteraction | TerminalOrganelleAssembly | bit_identity | bit_identity | deterministic_deterministic | 0 | 4 | 0 | 0 | 0 | 4 |
| Metabolism | ProteinProcessingI | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| ProteinDecay | ProteinProcessingI | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| ProteinFolding | Transcription | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| ProteinModification | RNAProcessing | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| ProteinModification | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| ProteinModification | Transcription | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| ProteinProcessingI | RNADecay | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| Replication | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| Replication | Translation | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| ReplicationInitiation | Transcription | distributional | distributional | stochastic_stochastic | 4 | 0 | 0 | 0 | 0 | 4 |
| ChromosomeCondensation | ChromosomeSegregation | bit_identity | bit_identity | deterministic_deterministic | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeCondensation | Cytokinesis | bit_identity | distributional | deterministic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeCondensation | FtsZPolymerization | bit_identity | distributional | deterministic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeCondensation | RNAModification | bit_identity | distributional | deterministic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeCondensation | RibosomeAssembly | bit_identity | distributional | deterministic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeCondensation | Translation | bit_identity | distributional | deterministic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeSegregation | Cytokinesis | bit_identity | distributional | deterministic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeSegregation | DNARepair | bit_identity | distributional | deterministic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeSegregation | ProteinFolding | bit_identity | distributional | deterministic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeSegregation | ReplicationInitiation | bit_identity | distributional | deterministic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeSegregation | Transcription | bit_identity | distributional | deterministic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ChromosomeSegregation | tRNAAminoacylation | bit_identity | distributional | deterministic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | DNARepair | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | DNASupercoiling | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | Metabolism | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | ProteinDecay | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | ProteinFolding | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | ProteinTranslocation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | RNAProcessing | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | Replication | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | Translation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Cytokinesis | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| DNADamage | ProteinDecay | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| DNADamage | RNADecay | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| DNARepair | FtsZPolymerization | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| DNARepair | RNADecay | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| DNARepair | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| DNARepair | Translation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| DNASupercoiling | FtsZPolymerization | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| DNASupercoiling | RNAModification | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| DNASupercoiling | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| DNASupercoiling | Translation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| FtsZPolymerization | ProteinFolding | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| FtsZPolymerization | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| FtsZPolymerization | Transcription | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| FtsZPolymerization | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ProteinDecay | ProteinProcessingII | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ProteinFolding | RNAModification | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ProteinFolding | Translation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ProteinProcessingI | Translation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ProteinProcessingI | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ProteinTranslocation | RNAModification | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| RNADecay | Replication | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| RNAModification | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ReplicationInitiation | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| ReplicationInitiation | Translation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| RibosomeAssembly | Transcription | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| RibosomeAssembly | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |
| Transcription | Translation | distributional | distributional | stochastic_stochastic | 3 | 0 | 0 | 0 | 0 | 3 |

## 5. Tier 2 pair list

| process_A | process_B | oracle_type_a | oracle_type_b | pair_oracle_complexity | substrates_overlap | enzymes_overlap | monomers_overlap | complexs_overlap | rnas_overlap | total |
|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|
| ProteinFolding | ProteinProcessingI | distributional | distributional | stochastic_stochastic | 2 | 0 | 482 | 0 | 0 | 484 |
| ProteinFolding | ProteinProcessingII | distributional | distributional | stochastic_stochastic | 2 | 0 | 482 | 0 | 0 | 484 |
| ProteinProcessingI | ProteinProcessingII | distributional | distributional | stochastic_stochastic | 2 | 0 | 482 | 0 | 0 | 484 |
| ProteinProcessingI | ProteinTranslocation | distributional | distributional | stochastic_stochastic | 2 | 0 | 482 | 0 | 0 | 484 |
| ProteinProcessingII | ProteinTranslocation | distributional | distributional | stochastic_stochastic | 2 | 0 | 482 | 0 | 0 | 484 |
| ProteinModification | ProteinProcessingI | distributional | distributional | stochastic_stochastic | 1 | 0 | 482 | 0 | 0 | 483 |
| ProteinModification | ProteinProcessingII | distributional | distributional | stochastic_stochastic | 1 | 0 | 482 | 0 | 0 | 483 |
| ProteinModification | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 2 | 0 | 52 | 0 | 0 | 54 |
| ProteinProcessingI | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 2 | 0 | 52 | 0 | 0 | 54 |
| ProteinProcessingII | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 2 | 0 | 52 | 0 | 0 | 54 |
| RNAModification | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 3 | 5 |
| ChromosomeCondensation | DNADamage | bit_identity | distributional | deterministic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeCondensation | ProteinProcessingI | bit_identity | distributional | deterministic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeCondensation | ProteinProcessingII | bit_identity | distributional | deterministic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeCondensation | RNADecay | bit_identity | distributional | deterministic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeSegregation | DNADamage | bit_identity | distributional | deterministic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeSegregation | ProteinModification | bit_identity | distributional | deterministic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeSegregation | ProteinProcessingI | bit_identity | distributional | deterministic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeSegregation | ProteinProcessingII | bit_identity | distributional | deterministic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeSegregation | RNADecay | bit_identity | distributional | deterministic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ChromosomeSegregation | RNAModification | bit_identity | distributional | deterministic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | DNADamage | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | ProteinModification | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | ProteinProcessingI | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | ProteinProcessingII | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | RNADecay | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | RNAModification | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| Cytokinesis | Transcription | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | DNASupercoiling | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | FtsZPolymerization | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | ProteinFolding | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | ProteinProcessingI | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | ProteinProcessingII | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | ProteinTranslocation | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | RNAModification | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | RNAProcessing | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | Replication | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | Transcription | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | Translation | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNARepair | ProteinProcessingI | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNARepair | ProteinProcessingII | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNASupercoiling | ProteinProcessingI | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNASupercoiling | ProteinProcessingII | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNASupercoiling | RNADecay | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| FtsZPolymerization | ProteinModification | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| FtsZPolymerization | ProteinProcessingI | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| FtsZPolymerization | ProteinProcessingII | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| FtsZPolymerization | RNADecay | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| FtsZPolymerization | RNAModification | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinFolding | RNADecay | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingI | RNAModification | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingI | RNAProcessing | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingI | Replication | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingI | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingI | Transcription | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | RNADecay | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | RNAModification | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | RNAProcessing | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | Replication | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | Transcription | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | Translation | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinProcessingII | tRNAAminoacylation | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| ProteinTranslocation | RNADecay | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| RNADecay | RNAProcessing | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| RNADecay | ReplicationInitiation | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| RNADecay | RibosomeAssembly | distributional | distributional | stochastic_stochastic | 2 | 0 | 0 | 0 | 0 | 2 |
| DNADamage | ProteinModification | distributional | distributional | stochastic_stochastic | 1 | 0 | 0 | 0 | 0 | 1 |
| HostInteraction | Metabolism | bit_identity | distributional | deterministic_stochastic | 0 | 1 | 0 | 0 | 0 | 1 |

## 6. Tier 3 pair list

| process_A | process_B | oracle_type_a | oracle_type_b | pair_oracle_complexity | substrates_overlap | enzymes_overlap | monomers_overlap | complexs_overlap | rnas_overlap | total |
|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|
| MacromolecularComplexation | ProteinFolding | distributional | distributional | stochastic_stochastic | 0 | 0 | 0 | 147 | 0 | 147 |

## 7. Disjoint pair list

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

## 8. Per-process pair count

| process | shared_pool_partners | honest_required_partners |
|---|---:|---:|
| ChromosomeCondensation | 22 | 22 |
| ChromosomeSegregation | 22 | 22 |
| Cytokinesis | 22 | 22 |
| DNADamage | 22 | 22 |
| DNARepair | 22 | 22 |
| DNASupercoiling | 22 | 22 |
| FtsZPolymerization | 22 | 22 |
| HostInteraction | 2 | 2 |
| MacromolecularComplexation | 1 | 1 |
| Metabolism | 23 | 23 |
| ProteinActivation | 0 | 0 |
| ProteinDecay | 22 | 22 |
| ProteinFolding | 23 | 23 |
| ProteinModification | 22 | 22 |
| ProteinProcessingI | 22 | 22 |
| ProteinProcessingII | 22 | 22 |
| ProteinTranslocation | 22 | 22 |
| RNADecay | 22 | 22 |
| RNAModification | 22 | 22 |
| RNAProcessing | 22 | 22 |
| Replication | 22 | 22 |
| ReplicationInitiation | 22 | 22 |
| RibosomeAssembly | 22 | 22 |
| TerminalOrganelleAssembly | 1 | 1 |
| Transcription | 22 | 22 |
| TranscriptionalRegulation | 0 | 0 |
| Translation | 22 | 22 |
| tRNAAminoacylation | 22 | 22 |

## 9. Methodology

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
