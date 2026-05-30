# Python Drift Report

Schema is treated as reference; Python declarations are audited as drift candidates.

- Total processes audited: 28
- Total field checks: 224
- Total drifts (non-match): 224

## Top Drifts

- `ChromosomeCondensation` `process.class`: `value_mismatch` (schema='ChromosomeCondensation', python='KarrChromosomeCondensationProcess')
- `ChromosomeSegregation` `process.class`: `value_mismatch` (schema='ChromosomeSegregation', python='KarrChromosomeSegregationProcess')
- `Cytokinesis` `process.class`: `value_mismatch` (schema='Cytokinesis', python='KarrCytokinesisProcess')
- `DNADamage` `enzymes.free.count`: `value_mismatch` (schema={'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs assignment not found'}, python=0)
- `DNADamage` `enzymes.free.wids`: `value_mismatch` (schema={'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs assignment not found'}, python=[])
- `DNADamage` `process.class`: `value_mismatch` (schema='DNADamage', python='KarrDNADamageProcess')
- `DNADamage` `substrates.count`: `value_mismatch` (schema=2, python=0)
- `DNADamage` `substrates.wids`: `value_mismatch` (schema=['UVB_radiation', 'gamma_radiation'], python=[])
- `DNARepair` `process.class`: `value_mismatch` (schema='DNARepair', python='_DamageSite')
- `DNASupercoiling` `process.class`: `value_mismatch` (schema='DNASupercoiling', python='KarrDNASupercoilingProcess')
- `HostInteraction` `process.class`: `value_mismatch` (schema='HostInteraction', python='KarrHostInteractionProcess')
- `MacromolecularComplexation` `process.class`: `value_mismatch` (schema='MacromolecularComplexation', python='MacromolecularComplexationProcess')
- `Metabolism` `process.class`: `value_mismatch` (schema='Metabolism', python='KarrMetabolismProcess')
- `ProteinActivation` `process.class`: `value_mismatch` (schema='ProteinActivation', python='KarrProteinActivationProcess')
- `ProteinFolding` `enzymes.free.count`: `value_mismatch` (schema=5, python=0)
- `ProteinFolding` `enzymes.free.wids`: `value_mismatch` (schema=['MG_238_MONOMER', 'MG_305_MONOMER', 'MG_019_DIMER', 'MG_201_DIMER', 'MG_392_393_21MER'], python=[])
- `ProteinFolding` `process.class`: `value_mismatch` (schema='ProteinFolding', python='KarrProteinFoldingProcess')
- `ProteinModification` `process.class`: `value_mismatch` (schema='ProteinModification', python='KarrProteinModificationProcess')
- `ProteinProcessingI` `process.class`: `value_mismatch` (schema='ProteinProcessingI', python='KarrProteinProcessingIProcess')
- `ProteinProcessingII` `process.class`: `value_mismatch` (schema='ProteinProcessingII', python='KarrProteinProcessingIIProcess')
- `ProteinTranslocation` `process.class`: `value_mismatch` (schema='ProteinTranslocation', python='KarrProteinTranslocationProcess')
- `RNADecay` `enzymes.free.count`: `value_mismatch` (schema=2, python=0)
- `RNADecay` `enzymes.free.wids`: `value_mismatch` (schema=['MG_104_MONOMER', 'MG_083_MONOMER'], python=[])
- `RNADecay` `process.class`: `value_mismatch` (schema='RNADecay', python='RnaDecayLightProcess')
- `RNADecay` `substrates.count`: `value_mismatch` (schema={'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}, python=1)
- `RNADecay` `substrates.wids`: `value_mismatch` (schema={'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}, python=['H2O'])
- `RNAModification` `process.class`: `value_mismatch` (schema='RNAModification', python='KarrRNAModificationProcess')
- `RNAProcessing` `process.class`: `value_mismatch` (schema='RNAProcessing', python='KarrRNAProcessingProcess')
- `Replication` `process.class`: `value_mismatch` (schema='Replication', python='KarrReplicationProcess')
- `ReplicationInitiation` `process.class`: `value_mismatch` (schema='ReplicationInitiation', python='KarrReplicationInitiationProcess')
- `RibosomeAssembly` `process.class`: `value_mismatch` (schema='RibosomeAssembly', python='KarrRibosomeAssemblyProcess')
- `TerminalOrganelleAssembly` `process.class`: `value_mismatch` (schema='TerminalOrganelleAssembly', python='_LocalizationReaction')
- `Transcription` `process.class`: `value_mismatch` (schema='Transcription', python='KarrTranscriptionProcess')
- `Transcription` `substrates.count`: `value_mismatch` (schema=12, python=4)
- `Transcription` `substrates.wids`: `value_mismatch` (schema=['ATP', 'CTP', 'GTP', 'UTP', 'AMP', 'CMP', 'GMP', 'UMP', 'ADP', 'PPI', 'H2O', 'H'], python=['ATP', 'CTP', 'GTP', 'UTP'])
- `TranscriptionalRegulation` `process.class`: `value_mismatch` (schema='TranscriptionalRegulation', python='KarrTranscriptionalRegulationProcess')
- `Translation` `process.class`: `value_mismatch` (schema='Translation', python='KarrTranslationProcess')
- `tRNAAminoacylation` `process.class`: `value_mismatch` (schema='tRNAAminoacylation', python='KarrTRNAAminoacylationProcess')
- `ChromosomeCondensation` `enzymes.bound.shape`: `missing_python_decl` (schema=[1, 2], python=None)
- `ChromosomeCondensation` `enzymes.free.count`: `missing_python_decl` (schema=2, python=None)
- `ChromosomeCondensation` `enzymes.free.shape`: `missing_python_decl` (schema=[1, 2], python=None)
- `ChromosomeCondensation` `enzymes.free.wids`: `missing_python_decl` (schema=['MG_213_214_298_6MER', 'MG_213_214_298_6MER_ADP'], python=None)
- `ChromosomeCondensation` `substrates.count`: `missing_python_decl` (schema=5, python=None)
- `ChromosomeCondensation` `substrates.shape`: `missing_python_decl` (schema=[1, 5], python=None)
- `ChromosomeCondensation` `substrates.wids`: `missing_python_decl` (schema=['ATP', 'ADP', 'PI', 'H2O', 'H'], python=None)
- `ChromosomeSegregation` `enzymes.bound.shape`: `missing_python_decl` (schema=[1, 5], python=None)
- `ChromosomeSegregation` `enzymes.free.count`: `missing_python_decl` (schema=5, python=None)
- `ChromosomeSegregation` `enzymes.free.shape`: `missing_python_decl` (schema=[1, 5], python=None)
- `ChromosomeSegregation` `enzymes.free.wids`: `missing_python_decl` (schema=['MG_470_MONOMER', 'MG_221_OCTAMER', 'MG_387_MONOMER', 'MG_384_MONOMER', 'MG_203_204_TETRAMER'], python=None)
- `ChromosomeSegregation` `substrates.count`: `missing_python_decl` (schema=5, python=None)

## Full Field Audit

| process | field | drift_kind | schema_value | python_value |
|---|---|---|---|---|
| `ChromosomeCondensation` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 2]` | `None` |
| `ChromosomeCondensation` | `enzymes.free.count` | `missing_python_decl` | `2` | `None` |
| `ChromosomeCondensation` | `enzymes.free.shape` | `missing_python_decl` | `[1, 2]` | `None` |
| `ChromosomeCondensation` | `enzymes.free.wids` | `missing_python_decl` | `['MG_213_214_298_6MER', 'MG_213_214_298_6MER_ADP']` | `None` |
| `ChromosomeCondensation` | `process.class` | `value_mismatch` | `'ChromosomeCondensation'` | `'KarrChromosomeCondensationProcess'` |
| `ChromosomeCondensation` | `substrates.count` | `missing_python_decl` | `5` | `None` |
| `ChromosomeCondensation` | `substrates.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `ChromosomeCondensation` | `substrates.wids` | `missing_python_decl` | `['ATP', 'ADP', 'PI', 'H2O', 'H']` | `None` |
| `ChromosomeSegregation` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `ChromosomeSegregation` | `enzymes.free.count` | `missing_python_decl` | `5` | `None` |
| `ChromosomeSegregation` | `enzymes.free.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `ChromosomeSegregation` | `enzymes.free.wids` | `missing_python_decl` | `['MG_470_MONOMER', 'MG_221_OCTAMER', 'MG_387_MONOMER', 'MG_384_MONOMER', 'MG_203_204_TETRAMER']` | `None` |
| `ChromosomeSegregation` | `process.class` | `value_mismatch` | `'ChromosomeSegregation'` | `'KarrChromosomeSegregationProcess'` |
| `ChromosomeSegregation` | `substrates.count` | `missing_python_decl` | `5` | `None` |
| `ChromosomeSegregation` | `substrates.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `ChromosomeSegregation` | `substrates.wids` | `missing_python_decl` | `['GTP', 'GDP', 'H', 'H2O', 'PI']` | `None` |
| `Cytokinesis` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 4]` | `None` |
| `Cytokinesis` | `enzymes.free.count` | `missing_python_decl` | `4` | `None` |
| `Cytokinesis` | `enzymes.free.shape` | `missing_python_decl` | `[1, 4]` | `None` |
| `Cytokinesis` | `enzymes.free.wids` | `missing_python_decl` | `['MG_224_9MER_GTP', 'MG_224_9MER_GDP', 'MG_224_MONOMER_GDP', 'MG_224_MONOMER_GTP']` | `None` |
| `Cytokinesis` | `process.class` | `value_mismatch` | `'Cytokinesis'` | `'KarrCytokinesisProcess'` |
| `Cytokinesis` | `substrates.count` | `missing_python_decl` | `3` | `None` |
| `Cytokinesis` | `substrates.shape` | `missing_python_decl` | `[1, 3]` | `None` |
| `Cytokinesis` | `substrates.wids` | `missing_python_decl` | `['PI', 'H2O', 'H']` | `None` |
| `DNADamage` | `enzymes.bound.shape` | `missing_python_decl` | `[2]` | `None` |
| `DNADamage` | `enzymes.free.count` | `value_mismatch` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs assignment not found'}` | `0` |
| `DNADamage` | `enzymes.free.shape` | `missing_python_decl` | `[2]` | `None` |
| `DNADamage` | `enzymes.free.wids` | `value_mismatch` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs assignment not found'}` | `[]` |
| `DNADamage` | `process.class` | `value_mismatch` | `'DNADamage'` | `'KarrDNADamageProcess'` |
| `DNADamage` | `substrates.count` | `value_mismatch` | `2` | `0` |
| `DNADamage` | `substrates.shape` | `missing_python_decl` | `[1, 48]` | `None` |
| `DNADamage` | `substrates.wids` | `value_mismatch` | `['UVB_radiation', 'gamma_radiation']` | `[]` |
| `DNARepair` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 15]` | `None` |
| `DNARepair` | `enzymes.free.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `DNARepair` | `enzymes.free.shape` | `missing_python_decl` | `[1, 15]` | `None` |
| `DNARepair` | `enzymes.free.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `DNARepair` | `process.class` | `value_mismatch` | `'DNARepair'` | `'_DamageSite'` |
| `DNARepair` | `substrates.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `DNARepair` | `substrates.shape` | `missing_python_decl` | `[1, 277]` | `None` |
| `DNARepair` | `substrates.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `DNASupercoiling` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 3]` | `None` |
| `DNASupercoiling` | `enzymes.free.count` | `missing_python_decl` | `3` | `None` |
| `DNASupercoiling` | `enzymes.free.shape` | `missing_python_decl` | `[1, 3]` | `None` |
| `DNASupercoiling` | `enzymes.free.wids` | `missing_python_decl` | `['DNA_GYRASE', 'MG_203_204_TETRAMER', 'MG_122_MONOMER']` | `None` |
| `DNASupercoiling` | `process.class` | `value_mismatch` | `'DNASupercoiling'` | `'KarrDNASupercoilingProcess'` |
| `DNASupercoiling` | `substrates.count` | `missing_python_decl` | `5` | `None` |
| `DNASupercoiling` | `substrates.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `DNASupercoiling` | `substrates.wids` | `missing_python_decl` | `['ATP', 'ADP', 'PI', 'H2O', 'H']` | `None` |
| `FtsZPolymerization` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 11]` | `None` |
| `FtsZPolymerization` | `enzymes.free.count` | `missing_python_decl` | `11` | `None` |
| `FtsZPolymerization` | `enzymes.free.shape` | `missing_python_decl` | `[1, 11]` | `None` |
| `FtsZPolymerization` | `enzymes.free.wids` | `missing_python_decl` | `['MG_224_MONOMER', 'MG_224_MONOMER_GDP', 'MG_224_MONOMER_GTP', 'MG_224_2MER_GTP', 'MG_224_3MER_GTP', 'MG_224_4MER_GTP...` | `None` |
| `FtsZPolymerization` | `process.class` | `missing_python_decl` | `'FtsZPolymerization'` | `None` |
| `FtsZPolymerization` | `substrates.count` | `missing_python_decl` | `5` | `None` |
| `FtsZPolymerization` | `substrates.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `FtsZPolymerization` | `substrates.wids` | `missing_python_decl` | `['GDP', 'GTP', 'PI', 'H2O', 'H']` | `None` |
| `HostInteraction` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 15]` | `None` |
| `HostInteraction` | `enzymes.free.count` | `missing_python_decl` | `15` | `None` |
| `HostInteraction` | `enzymes.free.shape` | `missing_python_decl` | `[1, 15]` | `None` |
| `HostInteraction` | `enzymes.free.wids` | `missing_python_decl` | `['MG_075_MONOMER', 'MG_149_MONOMER', 'MG_191_MONOMER', 'MG_192_MONOMER', 'MG_200_MONOMER', 'MG_217_MONOMER', 'MG_218_...` | `None` |
| `HostInteraction` | `process.class` | `value_mismatch` | `'HostInteraction'` | `'KarrHostInteractionProcess'` |
| `HostInteraction` | `substrates.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `HostInteraction` | `substrates.shape` | `missing_python_decl` | `[2]` | `None` |
| `HostInteraction` | `substrates.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `MacromolecularComplexation` | `enzymes.bound.shape` | `missing_python_decl` | `[2]` | `None` |
| `MacromolecularComplexation` | `enzymes.free.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `MacromolecularComplexation` | `enzymes.free.shape` | `missing_python_decl` | `[2]` | `None` |
| `MacromolecularComplexation` | `enzymes.free.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `MacromolecularComplexation` | `process.class` | `value_mismatch` | `'MacromolecularComplexation'` | `'MacromolecularComplexationProcess'` |
| `MacromolecularComplexation` | `substrates.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `MacromolecularComplexation` | `substrates.shape` | `missing_python_decl` | `[1, 210]` | `None` |
| `MacromolecularComplexation` | `substrates.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `Metabolism` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 104]` | `None` |
| `Metabolism` | `enzymes.free.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs assignment not found'}` | `None` |
| `Metabolism` | `enzymes.free.shape` | `missing_python_decl` | `[1, 104]` | `None` |
| `Metabolism` | `enzymes.free.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs assignment not found'}` | `None` |
| `Metabolism` | `process.class` | `value_mismatch` | `'Metabolism'` | `'KarrMetabolismProcess'` |
| `Metabolism` | `substrates.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs assignment not found'}` | `None` |
| `Metabolism` | `substrates.shape` | `missing_python_decl` | `[3, 585]` | `None` |
| `Metabolism` | `substrates.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs assignment not found'}` | `None` |
| `ProteinActivation` | `enzymes.bound.shape` | `missing_python_decl` | `[2]` | `None` |
| `ProteinActivation` | `enzymes.free.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `ProteinActivation` | `enzymes.free.shape` | `missing_python_decl` | `[2]` | `None` |
| `ProteinActivation` | `enzymes.free.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `ProteinActivation` | `process.class` | `value_mismatch` | `'ProteinActivation'` | `'KarrProteinActivationProcess'` |
| `ProteinActivation` | `substrates.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `ProteinActivation` | `substrates.shape` | `missing_python_decl` | `[6, 10]` | `None` |
| `ProteinActivation` | `substrates.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `ProteinDecay` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 9]` | `None` |
| `ProteinDecay` | `enzymes.free.count` | `missing_python_decl` | `9` | `None` |
| `ProteinDecay` | `enzymes.free.shape` | `missing_python_decl` | `[1, 9]` | `None` |
| `ProteinDecay` | `enzymes.free.wids` | `missing_python_decl` | `['MG_355_HEXAMER', 'MG_239_HEXAMER', 'MG_457_HEXAMER', 'MG_183_MONOMER', 'MG_324_MONOMER', 'MG_391_HEXAMER', 'MG_208_...` | `None` |
| `ProteinDecay` | `process.class` | `missing_python_decl` | `'ProteinDecay'` | `None` |
| `ProteinDecay` | `substrates.count` | `missing_python_decl` | `1` | `None` |
| `ProteinDecay` | `substrates.shape` | `missing_python_decl` | `[1, 53]` | `None` |
| `ProteinDecay` | `substrates.wids` | `missing_python_decl` | `['ATP']` | `None` |
| `ProteinFolding` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `ProteinFolding` | `enzymes.free.count` | `value_mismatch` | `5` | `0` |
| `ProteinFolding` | `enzymes.free.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `ProteinFolding` | `enzymes.free.wids` | `value_mismatch` | `['MG_238_MONOMER', 'MG_305_MONOMER', 'MG_019_DIMER', 'MG_201_DIMER', 'MG_392_393_21MER']` | `[]` |
| `ProteinFolding` | `process.class` | `value_mismatch` | `'ProteinFolding'` | `'KarrProteinFoldingProcess'` |
| `ProteinFolding` | `substrates.count` | `missing_python_decl` | `1` | `None` |
| `ProteinFolding` | `substrates.shape` | `missing_python_decl` | `[1, 11]` | `None` |
| `ProteinFolding` | `substrates.wids` | `missing_python_decl` | `['ADP']` | `None` |
| `ProteinModification` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 3]` | `None` |
| `ProteinModification` | `enzymes.free.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs assignment not found'}` | `None` |
| `ProteinModification` | `enzymes.free.shape` | `missing_python_decl` | `[1, 3]` | `None` |
| `ProteinModification` | `enzymes.free.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs assignment not found'}` | `None` |
| `ProteinModification` | `process.class` | `value_mismatch` | `'ProteinModification'` | `'KarrProteinModificationProcess'` |
| `ProteinModification` | `substrates.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs assignment not found'}` | `None` |
| `ProteinModification` | `substrates.shape` | `missing_python_decl` | `[1, 15]` | `None` |
| `ProteinModification` | `substrates.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs assignment not found'}` | `None` |
| `ProteinProcessingI` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 2]` | `None` |
| `ProteinProcessingI` | `enzymes.free.count` | `missing_python_decl` | `2` | `None` |
| `ProteinProcessingI` | `enzymes.free.shape` | `missing_python_decl` | `[1, 2]` | `None` |
| `ProteinProcessingI` | `enzymes.free.wids` | `missing_python_decl` | `['MG_106_DIMER', 'MG_172_MONOMER']` | `None` |
| `ProteinProcessingI` | `process.class` | `value_mismatch` | `'ProteinProcessingI'` | `'KarrProteinProcessingIProcess'` |
| `ProteinProcessingI` | `substrates.count` | `missing_python_decl` | `4` | `None` |
| `ProteinProcessingI` | `substrates.shape` | `missing_python_decl` | `[1, 4]` | `None` |
| `ProteinProcessingI` | `substrates.wids` | `missing_python_decl` | `['H2O', 'H', 'MET', 'FOR']` | `None` |
| `ProteinProcessingII` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 2]` | `None` |
| `ProteinProcessingII` | `enzymes.free.count` | `missing_python_decl` | `2` | `None` |
| `ProteinProcessingII` | `enzymes.free.shape` | `missing_python_decl` | `[1, 2]` | `None` |
| `ProteinProcessingII` | `enzymes.free.wids` | `missing_python_decl` | `['MG_210_MONOMER', 'MG_086_MONOMER']` | `None` |
| `ProteinProcessingII` | `process.class` | `value_mismatch` | `'ProteinProcessingII'` | `'KarrProteinProcessingIIProcess'` |
| `ProteinProcessingII` | `substrates.count` | `missing_python_decl` | `5` | `None` |
| `ProteinProcessingII` | `substrates.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `ProteinProcessingII` | `substrates.wids` | `missing_python_decl` | `['H2O', 'diacylglycerolCys', 'PG160', 'SNGLYP', 'H']` | `None` |
| `ProteinTranslocation` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 4]` | `None` |
| `ProteinTranslocation` | `enzymes.free.count` | `missing_python_decl` | `4` | `None` |
| `ProteinTranslocation` | `enzymes.free.shape` | `missing_python_decl` | `[1, 4]` | `None` |
| `ProteinTranslocation` | `enzymes.free.wids` | `missing_python_decl` | `['MG_0001_048', 'MG_297_MONOMER', 'MG_072_DIMER', 'MG_055_170_277_464_476_20MER']` | `None` |
| `ProteinTranslocation` | `process.class` | `value_mismatch` | `'ProteinTranslocation'` | `'KarrProteinTranslocationProcess'` |
| `ProteinTranslocation` | `substrates.count` | `missing_python_decl` | `7` | `None` |
| `ProteinTranslocation` | `substrates.shape` | `missing_python_decl` | `[1, 7]` | `None` |
| `ProteinTranslocation` | `substrates.wids` | `missing_python_decl` | `['ATP', 'GTP', 'ADP', 'GDP', 'H', 'H2O', 'PI']` | `None` |
| `RNADecay` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 2]` | `None` |
| `RNADecay` | `enzymes.free.count` | `value_mismatch` | `2` | `0` |
| `RNADecay` | `enzymes.free.shape` | `missing_python_decl` | `[1, 2]` | `None` |
| `RNADecay` | `enzymes.free.wids` | `value_mismatch` | `['MG_104_MONOMER', 'MG_083_MONOMER']` | `[]` |
| `RNADecay` | `process.class` | `value_mismatch` | `'RNADecay'` | `'RnaDecayLightProcess'` |
| `RNADecay` | `substrates.count` | `value_mismatch` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `1` |
| `RNADecay` | `substrates.shape` | `missing_python_decl` | `[1, 39]` | `None` |
| `RNADecay` | `substrates.wids` | `value_mismatch` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `['H2O']` |
| `RNAModification` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 13]` | `None` |
| `RNAModification` | `enzymes.free.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs assignment not found'}` | `None` |
| `RNAModification` | `enzymes.free.shape` | `missing_python_decl` | `[1, 13]` | `None` |
| `RNAModification` | `enzymes.free.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs assignment not found'}` | `None` |
| `RNAModification` | `process.class` | `value_mismatch` | `'RNAModification'` | `'KarrRNAModificationProcess'` |
| `RNAModification` | `substrates.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs assignment not found'}` | `None` |
| `RNAModification` | `substrates.shape` | `missing_python_decl` | `[1, 29]` | `None` |
| `RNAModification` | `substrates.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs assignment not found'}` | `None` |
| `RNAProcessing` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `RNAProcessing` | `enzymes.free.count` | `missing_python_decl` | `5` | `None` |
| `RNAProcessing` | `enzymes.free.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `RNAProcessing` | `enzymes.free.wids` | `missing_python_decl` | `['MG_367_DIMER', 'MG_139_DIMER', 'MG_0003_465', 'MG_110_MONOMER', 'MG_425_DIMER']` | `None` |
| `RNAProcessing` | `process.class` | `value_mismatch` | `'RNAProcessing'` | `'KarrRNAProcessingProcess'` |
| `RNAProcessing` | `substrates.count` | `missing_python_decl` | `7` | `None` |
| `RNAProcessing` | `substrates.shape` | `missing_python_decl` | `[1, 7]` | `None` |
| `RNAProcessing` | `substrates.wids` | `missing_python_decl` | `['ATP', 'GTP', 'ADP', 'GDP', 'PI', 'H2O', 'H']` | `None` |
| `Replication` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 13]` | `None` |
| `Replication` | `enzymes.free.count` | `missing_python_decl` | `13` | `None` |
| `Replication` | `enzymes.free.shape` | `missing_python_decl` | `[1, 13]` | `None` |
| `Replication` | `enzymes.free.wids` | `missing_python_decl` | `['REPLISOME', 'DNA_POLYMERASE_2CORE_BETA_CLAMP_GAMMA_COMPLEX_PRIMASE', 'DNA_POLYMERASE_CORE_BETA_CLAMP_GAMMA_COMPLEX'...` | `None` |
| `Replication` | `process.class` | `value_mismatch` | `'Replication'` | `'KarrReplicationProcess'` |
| `Replication` | `substrates.count` | `missing_python_decl` | `16` | `None` |
| `Replication` | `substrates.shape` | `missing_python_decl` | `[1, 16]` | `None` |
| `Replication` | `substrates.wids` | `missing_python_decl` | `['DATP', 'DCTP', 'DGTP', 'DTTP', 'ATP', 'CTP', 'GTP', 'UTP', 'PPI', 'H2O', 'H', 'NAD', 'NMN', 'ADP', 'AMP', 'PI']` | `None` |
| `ReplicationInitiation` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 15]` | `None` |
| `ReplicationInitiation` | `enzymes.free.count` | `missing_python_decl` | `15` | `None` |
| `ReplicationInitiation` | `enzymes.free.shape` | `missing_python_decl` | `[1, 15]` | `None` |
| `ReplicationInitiation` | `enzymes.free.wids` | `missing_python_decl` | `['MG_469_1MER_ADP', 'MG_469_1MER_ATP', 'MG_469_2MER_1ATP_ADP', 'MG_469_2MER_ATP', 'MG_469_3MER_2ATP_ADP', 'MG_469_3ME...` | `None` |
| `ReplicationInitiation` | `process.class` | `value_mismatch` | `'ReplicationInitiation'` | `'KarrReplicationInitiationProcess'` |
| `ReplicationInitiation` | `substrates.count` | `missing_python_decl` | `5` | `None` |
| `ReplicationInitiation` | `substrates.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `ReplicationInitiation` | `substrates.wids` | `missing_python_decl` | `['ATP', 'ADP', 'PI', 'H2O', 'H']` | `None` |
| `RibosomeAssembly` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 6]` | `None` |
| `RibosomeAssembly` | `enzymes.free.count` | `missing_python_decl` | `6` | `None` |
| `RibosomeAssembly` | `enzymes.free.shape` | `missing_python_decl` | `[1, 6]` | `None` |
| `RibosomeAssembly` | `enzymes.free.wids` | `missing_python_decl` | `['MG_329_MONOMER', 'MG_335_MONOMER', 'MG_387_MONOMER', 'MG_384_MONOMER', 'MG_143_MONOMER', 'MG_442_MONOMER']` | `None` |
| `RibosomeAssembly` | `process.class` | `value_mismatch` | `'RibosomeAssembly'` | `'KarrRibosomeAssemblyProcess'` |
| `RibosomeAssembly` | `substrates.count` | `missing_python_decl` | `5` | `None` |
| `RibosomeAssembly` | `substrates.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `RibosomeAssembly` | `substrates.wids` | `missing_python_decl` | `['GTP', 'GDP', 'PI', 'H2O', 'H']` | `None` |
| `TerminalOrganelleAssembly` | `enzymes.bound.shape` | `missing_python_decl` | `[6, 4]` | `None` |
| `TerminalOrganelleAssembly` | `enzymes.free.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs assignment not found'}` | `None` |
| `TerminalOrganelleAssembly` | `enzymes.free.shape` | `missing_python_decl` | `[6, 4]` | `None` |
| `TerminalOrganelleAssembly` | `enzymes.free.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs assignment not found'}` | `None` |
| `TerminalOrganelleAssembly` | `process.class` | `value_mismatch` | `'TerminalOrganelleAssembly'` | `'_LocalizationReaction'` |
| `TerminalOrganelleAssembly` | `substrates.count` | `missing_python_decl` | `8` | `None` |
| `TerminalOrganelleAssembly` | `substrates.shape` | `missing_python_decl` | `[2, 8]` | `None` |
| `TerminalOrganelleAssembly` | `substrates.wids` | `missing_python_decl` | `['MG_191_MONOMER', 'MG_192_MONOMER', 'MG_217_MONOMER', 'MG_218_MONOMER', 'MG_312_MONOMER', 'MG_317_MONOMER', 'MG_318_...` | `None` |
| `Transcription` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 6]` | `None` |
| `Transcription` | `enzymes.free.count` | `missing_python_decl` | `6` | `None` |
| `Transcription` | `enzymes.free.shape` | `missing_python_decl` | `[1, 6]` | `None` |
| `Transcription` | `enzymes.free.wids` | `missing_python_decl` | `['MG_249_MONOMER', 'MG_282_MONOMER', 'MG_141_MONOMER', 'MG_027_MONOMER', 'RNA_POLYMERASE', 'RNA_POLYMERASE_HOLOENZYME']` | `None` |
| `Transcription` | `process.class` | `value_mismatch` | `'Transcription'` | `'KarrTranscriptionProcess'` |
| `Transcription` | `substrates.count` | `value_mismatch` | `12` | `4` |
| `Transcription` | `substrates.shape` | `missing_python_decl` | `[1, 12]` | `None` |
| `Transcription` | `substrates.wids` | `value_mismatch` | `['ATP', 'CTP', 'GTP', 'UTP', 'AMP', 'CMP', 'GMP', 'UMP', 'ADP', 'PPI', 'H2O', 'H']` | `['ATP', 'CTP', 'GTP', 'UTP']` |
| `TranscriptionalRegulation` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `TranscriptionalRegulation` | `enzymes.free.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `TranscriptionalRegulation` | `enzymes.free.shape` | `missing_python_decl` | `[1, 5]` | `None` |
| `TranscriptionalRegulation` | `enzymes.free.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `TranscriptionalRegulation` | `process.class` | `value_mismatch` | `'TranscriptionalRegulation'` | `'KarrTranscriptionalRegulationProcess'` |
| `TranscriptionalRegulation` | `substrates.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `TranscriptionalRegulation` | `substrates.shape` | `missing_python_decl` | `[2]` | `None` |
| `TranscriptionalRegulation` | `substrates.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs literals could not be parsed from MATLAB source'}` | `None` |
| `Translation` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 16]` | `None` |
| `Translation` | `enzymes.free.count` | `missing_python_decl` | `16` | `None` |
| `Translation` | `enzymes.free.shape` | `missing_python_decl` | `[1, 16]` | `None` |
| `Translation` | `enzymes.free.wids` | `missing_python_decl` | `['MG_173_MONOMER', 'MG_142_MONOMER', 'MG_196_MONOMER', 'MG_089_DIMER', 'MG_026_MONOMER', 'MG_451_DIMER', 'MG_433_DIME...` | `None` |
| `Translation` | `process.class` | `value_mismatch` | `'Translation'` | `'KarrTranslationProcess'` |
| `Translation` | `substrates.count` | `missing_python_decl` | `26` | `None` |
| `Translation` | `substrates.shape` | `missing_python_decl` | `[1, 26]` | `None` |
| `Translation` | `substrates.wids` | `missing_python_decl` | `['ALA', 'ARG', 'ASN', 'ASP', 'CYS', 'GLN', 'GLU', 'GLY', 'HIS', 'ILE', 'LEU', 'LYS', 'MET', 'PHE', 'PRO', 'SER', 'THR...` | `None` |
| `tRNAAminoacylation` | `enzymes.bound.shape` | `missing_python_decl` | `[1, 58]` | `None` |
| `tRNAAminoacylation` | `enzymes.free.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs depends on inherited/runtime state; literal append is partial'}` | `None` |
| `tRNAAminoacylation` | `enzymes.free.shape` | `missing_python_decl` | `[1, 58]` | `None` |
| `tRNAAminoacylation` | `enzymes.free.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'enzymeWholeCellModelIDs depends on inherited/runtime state; literal append is partial'}` | `None` |
| `tRNAAminoacylation` | `process.class` | `value_mismatch` | `'tRNAAminoacylation'` | `'KarrTRNAAminoacylationProcess'` |
| `tRNAAminoacylation` | `substrates.count` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs depends on inherited/runtime state; literal append is partial'}` | `None` |
| `tRNAAminoacylation` | `substrates.shape` | `missing_python_decl` | `[1, 30]` | `None` |
| `tRNAAminoacylation` | `substrates.wids` | `missing_python_decl` | `{'EXTRACTOR_FAILED': 'substrateWholeCellModelIDs depends on inherited/runtime state; literal append is partial'}` | `None` |
