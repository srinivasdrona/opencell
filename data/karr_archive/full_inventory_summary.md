# Karr .mat Full Inventory Summary

Generated: 2026-04-26T10:59:39.115840+00:00
Source dir: `data/m1_sources/karr_flat/`
Total leaves: **4837** across **8** files

Consumed by ingest scripts: **238** / 4837

## `knowledgeBase_targeted.mat`

- Leaves: **1451**  (consumed: 20)
- Total ndarray bytes: **53,871**
- Kinds: `empty`=183, `ndarray`=213, `string`=814, `string_array`=182, `struct`=40, `struct_array`=19

### Top-20 largest leaves

| nbytes | dtype | shape | path |
|---:|---|---|---|
| 29,712 | float64 | [1857, 2] | `data.knowledgeBase.reactionBounds` |
| 12,600 | float64 | [525, 3] | `data.knowledgeBase.maxGeneExpression` |
| 5,776 | float64 | [722] | `data.knowledgeBase.metaboliteMolecularWeights` |
| 3,200 | float64 | [20, 20] | `data.knowledgeBase.proteinMonomers[0].DIWV` |
| 482 | uint8 | [482] | `data.knowledgeBase.proteinMonomerNTerminalMethionineCleavages` |
| 62 | uint8 | [62] | `data.knowledgeBase.geneticCodeTRNAs` |
| 42 | uint16 | [21] | `data.knowledgeBase.aminoAcidIndexs` |
| 32 | uint16 | [4, 4] | `data.knowledgeBase.genome.pairwiseExtinction` |
| 32 | uint16 | [4, 4] | `data.knowledgeBase.genes[0].pairwiseExtinction` |
| 32 | uint16 | [4, 4] | `data.knowledgeBase.transcriptionUnits[0].pairwiseExtinction` |
| 32 | uint16 | [4, 4] | `data.knowledgeBase.genomeFeatures[0].pairwiseExtinction` |
| 32 | uint16 | [4, 4] | `data.knowledgeBase.mRNAGenes[0].pairwiseExtinction` |
| 32 | uint16 | [4, 4] | `data.knowledgeBase.rRNAGenes[0].pairwiseExtinction` |
| 32 | uint16 | [4, 4] | `data.knowledgeBase.sRNAGenes[0].pairwiseExtinction` |
| 32 | uint16 | [4, 4] | `data.knowledgeBase.tRNAGenes[0].pairwiseExtinction` |
| 26 | uint16 | [13] | `data.knowledgeBase.modifiedNMPIndexs` |
| 24 | float64 | [3] | `data.knowledgeBase.genes[0].expression` |
| 24 | float64 | [3] | `data.knowledgeBase.genes[0].synthesisRate` |
| 24 | float64 | [3] | `data.knowledgeBase.mRNAGenes[0].expression` |
| 24 | float64 | [3] | `data.knowledgeBase.mRNAGenes[0].synthesisRate` |

## `metabolism_dynamics.mat`

- Leaves: **36**  (consumed: 19)
- Total ndarray bytes: **64,318**
- Kinds: `ndarray`=36

### Top-20 largest leaves

| nbytes | dtype | shape | path |
|---:|---|---|---|
| 14,040 | float64 | [3, 585] | `snapshot_substrates` |
| 8,064 | float64 | [2, 504] | `#refs#.b.bounds` |
| 8,064 | float64 | [2, 504] | `#refs#.c.bounds` |
| 8,064 | float64 | [2, 504] | `#refs#.d.bounds` |
| 8,064 | float64 | [2, 504] | `bounds_dynamic_no_protein` |
| 8,064 | float64 | [2, 504] | `bounds_dynamic_with_protein` |
| 2,944 | float64 | [1, 368] | `substrate_indexs_fba` |
| 2,688 | float64 | [1, 336] | `fba_rxn_idx_metab_conv` |
| 992 | float64 | [1, 124] | `fba_rxn_idx_external_exch` |
| 992 | float64 | [1, 124] | `substrate_indexs_external_exch` |
| 832 | float64 | [1, 104] | `snapshot_enzymes` |
| 336 | float64 | [1, 42] | `fba_rxn_idx_internal_exch` |
| 280 | float64 | [1, 35] | `fba_rxn_idx_internal_lim_exch` |
| 280 | float64 | [1, 35] | `substrate_indexs_internal_lim` |
| 82 | uint16 | [41, 1] | `#refs#.d.desc` |
| 66 | uint16 | [33, 1] | `#refs#.d.name` |
| 64 | uint16 | [32, 1] | `#refs#.c.desc` |
| 58 | uint16 | [29, 1] | `#refs#.c.name` |
| 56 | float64 | [1, 7] | `fba_rxn_idx_internal_unlim_exch` |
| 52 | uint16 | [26, 1] | `x_source_sim` |

## `protein_complexes.mat`

- Leaves: **28**  (consumed: 20)
- Total ndarray bytes: **56**
- Kinds: `empty`=5, `ndarray`=7, `string`=9, `string_array`=4, `struct`=1, `struct_array`=2

### Top-20 largest leaves

| nbytes | dtype | shape | path |
|---:|---|---|---|
| 8 | int64 | [] | `data.complexes[0].idx` |
| 8 | int64 | [] | `data.complexes[0].numSubunits` |
| 8 | int64 | [] | `data.complexes[0].numDistinctSubunits` |
| 8 | int64 | [] | `data.complexes[0].dnaFootprint` |
| 8 | float64 | [] | `data.complexes[0].density` |
| 8 | int64 | [] | `data.complexes[0].monomers[0].coefficient` |
| 8 | int64 | [] | `data.complexes[0].monomers[0].molecule_idx_1based` |

## `proteins_targeted.mat`

- Leaves: **26**  (consumed: 25)
- Total ndarray bytes: **7,158,680**
- Kinds: `ndarray`=20, `string_array`=5, `struct`=1

### Top-20 largest leaves

| nbytes | dtype | shape | path |
|---:|---|---|---|
| 6,960,080 | uint16 | [4820, 722] | `data.baseCounts` |
| 57,840 | uint16 | [4820, 6] | `data.counts` |
| 38,560 | float64 | [4820] | `data.halfLives` |
| 38,560 | float64 | [4820] | `data.decayRates` |
| 38,560 | float64 | [4820] | `data.molecularWeights` |
| 9,640 | uint16 | [4820] | `data.lengths` |
| 4,820 | uint8 | [4820] | `data.compartments` |
| 964 | uint16 | [482] | `data.matureIndexs` |
| 964 | uint16 | [482] | `data.nascentIndexs` |
| 964 | uint16 | [482] | `data.processedIIndexs` |
| 964 | uint16 | [482] | `data.processedIIIndexs` |
| 964 | uint16 | [482] | `data.foldedIndexs` |
| 964 | uint16 | [482] | `data.inactivatedIndexs` |
| 964 | uint16 | [482] | `data.boundIndexs` |
| 964 | uint16 | [482] | `data.misfoldedIndexs` |
| 964 | uint16 | [482] | `data.damagedIndexs` |
| 964 | uint16 | [482] | `data.signalSequenceIndexs` |
| 964 | uint16 | [482] | `data.kb_geneIndex` |
| 8 | int64 | [] | `data.translation_ribosomeElongationRate` |
| 8 | float64 | [] | `data.translation_tmRNABindingProbability` |

## `rnas_targeted.mat`

- Leaves: **23**  (consumed: 22)
- Total ndarray bytes: **3,610,108**
- Kinds: `empty`=1, `ndarray`=16, `object`=1, `string_array`=4, `struct`=1

### Top-20 largest leaves

| nbytes | dtype | shape | path |
|---:|---|---|---|
| 3,506,032 | uint16 | [2428, 722] | `data.baseCounts` |
| 19,424 | float64 | [2428] | `data.molecularWeights` |
| 19,424 | float64 | [2428] | `data.halfLives` |
| 19,424 | float64 | [2428] | `data.decayRates` |
| 19,424 | float64 | [2428] | `data.expression` |
| 14,568 | uint8 | [2428, 6] | `data.counts` |
| 4,856 | uint16 | [2428] | `data.lengths` |
| 2,100 | uint32 | [525] | `data.kb_gene_to_tu_index` |
| 694 | uint16 | [347] | `data.matureIndexs` |
| 694 | uint16 | [347] | `data.processedIndexs` |
| 694 | uint16 | [347] | `data.boundIndexs` |
| 694 | uint16 | [347] | `data.misfoldedIndexs` |
| 694 | uint16 | [347] | `data.damagedIndexs` |
| 694 | uint16 | [347] | `data.aminoacylatedIndexs` |
| 670 | uint16 | [335] | `data.nascentIndexs` |
| 22 | uint16 | [11] | `data.intergenicIndexs` |

## `sim_fitted_targeted.mat`

- Leaves: **3176**  (consumed: 45)
- Total ndarray bytes: **21,982,458**
- Kinds: `empty`=38, `ndarray`=858, `object`=3, `string`=1892, `string_array`=84, `struct`=300, `struct_array`=1

### Top-20 largest leaves

| nbytes | dtype | shape | path |
|---:|---|---|---|
| 6,960,080 | uint16 | [4820, 722] | `data.states.State_Mass.dump.monomer.baseCounts` |
| 3,506,032 | uint16 | [2428, 722] | `data.states.State_Mass.dump.rna.baseCounts` |
| 2,263,950 | int16 | [585, 645, 3] | `data.metabolism.reactionStoichiometryMatrix` |
| 2,263,950 | int16 | [645, 585, 3] | `data.metabolism.reactionCoenzymeMatrix` |
| 1,741,464 | int16 | [1206, 722] | `data.states.State_Mass.dump.complex.baseCounts` |
| 1,516,032 | float64 | [376, 504] | `data.metabolism.fbaReactionStoichiometryMatrix` |
| 633,150 | uint8 | [525, 201, 6] | `data.states.State_Mass.dump.complex.proteinComplexComposition` |
| 338,625 | uint8 | [645, 525] | `data.metabolism.reactionModificationMatrix` |
| 325,832 | uint8 | [676, 482] | `data.states.State_Mass.dump.chromosome.reactionMonomerCatalysisMatrix` |
| 182,175 | uint8 | [525, 347] | `data.states.State_Mass.dump.rna.matureRNAGeneComposition` |
| 175,875 | uint8 | [525, 335] | `data.states.State_Mass.dump.rna.nascentRNAGeneComposition` |
| 161,728 | float64 | [722, 28] | `data.states.State_Mass.dump.metabolite.processBiomassProduction` |
| 161,728 | float64 | [722, 28] | `data.states.State_Mass.dump.metabolite.processByproduct` |
| 161,728 | float64 | [722, 28] | `data.states.State_Metabolite.dump.processBiomassProduction` |
| 161,728 | float64 | [722, 28] | `data.states.State_Metabolite.dump.processByproduct` |
| 135,876 | uint8 | [676, 201] | `data.states.State_Mass.dump.chromosome.reactionComplexCatalysisMatrix` |
| 116,245 | uint8 | [347, 335] | `data.states.State_Mass.dump.rna.nascentRNAMatureRNAComposition` |
| 67,080 | uint8 | [645, 104] | `data.metabolism.reactionCatalysisMatrix` |
| 57,840 | uint16 | [4820, 6] | `data.states.State_Mass.dump.monomer.counts` |
| 52,416 | uint8 | [504, 104] | `data.metabolism.fbaReactionCatalysisMatrix` |

## `transcription_v2_targeted.mat`

- Leaves: **55**  (consumed: 50)
- Total ndarray bytes: **17,867**
- Kinds: `ndarray`=44, `object`=1, `string`=4, `string_array`=5, `struct`=1

### Top-20 largest leaves

| nbytes | dtype | shape | path |
|---:|---|---|---|
| 5,360 | float64 | [335, 2] | `data.rnap_transcriptionFactorBindingProbFoldChange` |
| 5,360 | float64 | [335, 2] | `data.rnap_supercoilingBindingProbFoldChange` |
| 2,680 | float64 | [335] | `data.kb_tu_lengths` |
| 1,340 | int32 | [335] | `data.tr_transcriptionUnitFivePrimeCoordinates` |
| 670 | uint16 | [335] | `data.tr_transcriptionUnitLengths` |
| 670 | uint16 | [335] | `data.pt_tr_transcriptionUnitLengths` |
| 640 | int32 | [80, 2] | `data.rnap_positionStrands` |
| 335 | uint8 | [335] | `data.tr_transcriptionUnitDirections` |
| 160 | int16 | [80] | `data.rnap_states` |
| 160 | int16 | [80] | `data.rnap_states_vec` |
| 160 | int16 | [80] | `data.pt_rnaPolymerases_states` |
| 32 | float64 | [4] | `data.rnap_stateExpectations` |
| 32 | float64 | [4] | `data.rnap_stateOccupancies` |
| 32 | float64 | [4] | `data.pt_rnaPolymerases_stateExpectations` |
| 8 | int64 | [] | `data.rnap_activelyTranscribingIndex` |
| 8 | int64 | [] | `data.rnap_specificallyBoundIndex` |
| 8 | int64 | [] | `data.rnap_nonSpecificallyBoundIndex` |
| 8 | int64 | [] | `data.rnap_freeIndex` |
| 8 | int64 | [] | `data.rnap_activelyTranscribingValue` |
| 8 | int64 | [] | `data.rnap_specificallyBoundValue` |

## `translation_v2_targeted.mat`

- Leaves: **42**  (consumed: 37)
- Total ndarray bytes: **25,574**
- Kinds: `ndarray`=34, `string`=4, `string_array`=3, `struct`=1

### Top-20 largest leaves

| nbytes | dtype | shape | path |
|---:|---|---|---|
| 14,568 | uint8 | [2428, 6] | `data.rna_counts` |
| 4,856 | uint16 | [2428] | `data.rna_lengths` |
| 964 | uint16 | [482] | `data.pt_polypeptide_monomerLengths` |
| 964 | uint16 | [482] | `data.poly_monomerLengths` |
| 694 | uint16 | [347] | `data.rna_matureIndexs` |
| 694 | uint16 | [347] | `data.rna_processedIndexs` |
| 670 | uint16 | [335] | `data.rna_nascentIndexs` |
| 482 | uint8 | [482] | `data.rib_nMRNAsBound` |
| 482 | uint8 | [482] | `data.pt_mRNAs` |
| 272 | uint16 | [136] | `data.rib_boundMRNAs` |
| 272 | uint16 | [136] | `data.rib_mRNAPositions` |
| 136 | uint8 | [136] | `data.rib_states` |
| 136 | uint8 | [136] | `data.rib_tmRNAPositions` |
| 136 | uint8 | [136] | `data.rib_states_vec` |
| 36 | uint8 | [36] | `data.pt_freeTRNAs` |
| 36 | uint8 | [36] | `data.pt_aminoacylatedTRNAs` |
| 24 | float64 | [3] | `data.rib_stateOccupancies` |
| 16 | uint8 | [16] | `data.pt_enzymes` |
| 16 | uint8 | [16] | `data.pt_boundEnzymes` |
| 8 | int64 | [] | `data.rib_activeIndex` |
