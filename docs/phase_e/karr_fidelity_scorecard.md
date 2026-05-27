# Karr Fidelity Scorecard (Per-Process Replay, Tick 0)

`PASS=15 PARTIAL=1 FAIL=0 SKIP=12`

Bands:
- PASS: `max_rel < 1e-6` OR `max_abs < 1e-9`
- PARTIAL: `max_rel < 0.05`
- FAIL: otherwise
- SKIP: no adapter, truncated fixture, mirror fixture, or structural mismatch

| Process | Status | n_ticks tested | properties compared | max_abs | max_rel | top-disagreement property | reason |
|---|---:|---:|---:|---:|---:|---|---|
| ChromosomeCondensation | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| ChromosomeSegregation | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| Cytokinesis | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| DNADamage | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| DNARepair | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| DNASupercoiling | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| FtsZPolymerization | PARTIAL | 1 | 2 | 2 | 0.000551724 | substrates | - |
| HostInteraction | SKIP | 0 | 0 | - | - | - | No Vivarium adapter available for replay in Track-A. |
| MacromolecularComplexation | PASS | 1 | 4 | 0 | 0 | boundEnzymes | - |
| Metabolism | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| ProteinActivation | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| ProteinDecay | SKIP | 0 | 0 | - | - | - | Replay execution failed: 'complex' |
| ProteinFolding | SKIP | 0 | 0 | - | - | - | Replay execution failed: 'unfolded_counts' |
| ProteinModification | SKIP | 0 | 0 | - | - | - | Replay execution failed: 'unmodified_counts' |
| ProteinProcessingI | PASS | 1 | 5 | 0 | 0 | boundEnzymes | - |
| ProteinProcessingII | PASS | 1 | 5 | 0 | 0 | boundEnzymes | - |
| ProteinTranslocation | PASS | 1 | 4 | 0 | 0 | boundEnzymes | - |
| RNADecay | SKIP | 0 | 0 | - | - | - | 1-tick mirror (states_before == states_after); awaiting Track-B MATLAB re-extract. |
| RNAModification | SKIP | 0 | 0 | - | - | - | Replay execution failed: 'rna' |
| RNAProcessing | PASS | 1 | 5 | 0 | 0 | boundEnzymes | - |
| Replication | SKIP | 0 | 0 | - | - | - | 1-tick mirror (states_before == states_after); awaiting Track-B MATLAB re-extract. |
| ReplicationInitiation | SKIP | 0 | 0 | - | - | - | 1-tick mirror (states_before == states_after); awaiting Track-B MATLAB re-extract. |
| RibosomeAssembly | PASS | 1 | 5 | 0 | 0 | boundEnzymes | - |
| TerminalOrganelleAssembly | SKIP | 0 | 0 | - | - | - | No Vivarium adapter available for replay in Track-A. |
| Transcription | SKIP | 0 | 0 | - | - | - | 1-tick mirror (states_before == states_after); awaiting Track-B MATLAB re-extract. |
| TranscriptionalRegulation | PASS | 1 | 3 | 0 | 0 | boundEnzymes | - |
| Translation | SKIP | 0 | 0 | - | - | - | 1-tick mirror (states_before == states_after); awaiting Track-B MATLAB re-extract. |
| tRNAAminoacylation | SKIP | 0 | 0 | - | - | - | Replay execution failed: 'rna' |
