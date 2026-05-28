# Karr Fidelity Scorecard (Per-Process Replay, Tick 0)

`PASS=19 PARTIAL=1 FAIL=0 SKIP=17`

Bands:
- PASS: `max_rel < 1e-6` OR `max_abs < 1e-9`
- PARTIAL: `max_rel < 0.05`
- FAIL: otherwise
- SKIP: no adapter, truncated fixture, mirror fixture, or structural mismatch

| Process | Status | n_ticks tested | properties compared | max_abs | max_rel | top-disagreement property | reason |
|---|---:|---:|---:|---:|---:|---|---|
| ChromosomeCondensation | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| ChromosomeCondensation_from_flat | SKIP | 0 | 0 | - | - | - | No process-class mapping found. |
| ChromosomeSegregation | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| Cytokinesis | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| DNADamage | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| DNARepair | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| DNASupercoiling | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| DnaSupercoiling_from_flat | SKIP | 0 | 0 | - | - | - | No process-class mapping found. |
| FtsZPolymerization | PARTIAL | 1 | 2 | 2 | 0.000551724 | substrates | - |
| HostInteraction | SKIP | 0 | 0 | - | - | - | No Vivarium adapter available for replay in Track-A. |
| MacromolecularComplexation | PASS | 1 | 4 | 0 | 0 | boundEnzymes | - |
| Metabolism | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| ProteinActivation | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| ProteinDecay | SKIP | 0 | 0 | - | - | - | Structural mismatch: no comparable properties. |
| ProteinFolding | PASS | 1 | 5 | 0 | 0 | boundEnzymes | - |
| ProteinModification | PASS | 1 | 5 | 0 | 0 | boundEnzymes | - |
| ProteinProcessingI | PASS | 1 | 5 | 0 | 0 | boundEnzymes | - |
| ProteinProcessingII | PASS | 1 | 5 | 0 | 0 | boundEnzymes | - |
| ProteinTranslocation | PASS | 1 | 4 | 0 | 0 | boundEnzymes | - |
| RNADecay | SKIP | 0 | 0 | - | - | - | 1-tick mirror (states_before == states_after); awaiting Track-B MATLAB re-extract. |
| RNADecay_from_trajectory | SKIP | 0 | 0 | - | - | - | No process-class mapping found. |
| RNAModification | PASS | 1 | 5 | 0 | 0 | boundEnzymes | - |
| RNAProcessing | PASS | 1 | 5 | 0 | 0 | boundEnzymes | - |
| Replication | SKIP | 0 | 0 | - | - | - | 1-tick mirror (states_before == states_after); awaiting Track-B MATLAB re-extract. |
| ReplicationInitiation | SKIP | 0 | 0 | - | - | - | 1-tick mirror (states_before == states_after); awaiting Track-B MATLAB re-extract. |
| ReplicationInitiation_from_flat | SKIP | 0 | 0 | - | - | - | No process-class mapping found. |
| ReplicationInitiation_from_trajectory | SKIP | 0 | 0 | - | - | - | No process-class mapping found. |
| Replication_from_flat | SKIP | 0 | 0 | - | - | - | No process-class mapping found. |
| Replication_from_trajectory | SKIP | 0 | 0 | - | - | - | No process-class mapping found. |
| RibosomeAssembly | PASS | 1 | 5 | 0 | 0 | boundEnzymes | - |
| TerminalOrganelleAssembly | SKIP | 0 | 0 | - | - | - | No Vivarium adapter available for replay in Track-A. |
| Transcription | SKIP | 0 | 0 | - | - | - | 1-tick mirror (states_before == states_after); awaiting Track-B MATLAB re-extract. |
| Transcription_from_trajectory | SKIP | 0 | 0 | - | - | - | No process-class mapping found. |
| TranscriptionalRegulation | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| Translation | SKIP | 0 | 0 | - | - | - | 1-tick mirror (states_before == states_after); awaiting Track-B MATLAB re-extract. |
| Translation_from_trajectory | SKIP | 0 | 0 | - | - | - | No process-class mapping found. |
| tRNAAminoacylation | PASS | 1 | 2 | 0 | 0 | boundEnzymes | - |
