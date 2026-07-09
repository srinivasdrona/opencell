# Karr Input Taxonomy

## Part A

- `stimuli`: process-local stimulus vocabulary keyed by `stimuliWholeCellModelIDs` in the base class declaration (`Process.m:110`).
- `substrates`: process-local substrate vocabulary keyed by `substrateWholeCellModelIDs` in the base class declaration (`Process.m:111`).
- `enzymes`: process-local enzyme vocabulary keyed by `enzymeWholeCellModelIDs` in the base class declaration (`Process.m:112`).
- `boundEnzymes`: the process-local bound-enzyme state paired to the enzyme vocabulary (`Process.m:252`).
- `localStateNames`: annotated local state property list exposed through the `localStateNames` getter (`Process.m:79`, `Process.m:980`).
- `globalStateNames`: shared simulation state objects referenced through base `storeObjectReferences` / `states` wiring (`Process.m:299`, `Process.m:306`).
- `fittedConstantNames`: annotated fitted-constant property list exposed through the `fittedConstantNames` getter (`Process.m:78`, `Process.m:966`).
- `fixedConstantNames`: annotated fixed-constant property list exposed through the `fixedConstantNames` getter (`Process.m:77`, `Process.m:947`).

## Part B

| Process | stimuli | substrates | enzymes | boundEnzymes | localStateNames | globalStateNames | fittedConstantNames | fixedConstantNames |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ChromosomeCondensation | 0 | 5 | 2 | ∅ | 4 | 7 | 0 | 7 |
| ChromosomeSegregation | 0 | 5 | 5 | ∅ | 4 | 7 | 0 | 6 |
| Cytokinesis | 0 | 3 | 4 | ✓ | 4 | 8 | 0 | 8 |
| DNADamage | 0 | KB | KB | ∅ | 4 | 7 | 0 | 21 |
| DNARepair | 0 | KB | KB | ∅ | 4 | 7 | 0 | 35 |
| DNASupercoiling | 0 | 5 | 3 | ✓ | 4 | 8 | 0 | 25 |
| FtsZPolymerization | 0 | 5 | 11 | ∅ | 4 | 6 | 0 | 14 |
| HostInteraction | 0 | 0 | 15 | ∅ | 4 | 7 | 0 | 5 |
| MacromolecularComplexation | 0 | KB | 0 | ∅ | 5 | 6 | 0 | 9 |
| Metabolism | 0 | KB | KB | ∅ | 4 | 9 | 2 | 26 |
| ProteinActivation | KB | KB | 0 | ∅ | 5 | 6 | 0 | 6 |
| ProteinDecay | 0 | KB | 9 | ∅ | 7 | 7 | 0 | 18 |
| ProteinFolding | 0 | KB | KB | ∅ | 8 | 6 | 0 | 9 |
| ProteinModification | 0 | KB | KB | ∅ | 6 | 6 | 0 | 14 |
| ProteinProcessingI | 0 | 4 | 2 | ∅ | 6 | 6 | 0 | 8 |
| ProteinProcessingII | 0 | 5 | 2 | ∅ | 7 | 6 | 0 | 7 |
| ProteinTranslocation | 0 | 7 | 4 | ∅ | 5 | 6 | 0 | 11 |
| Replication | 0 | 16 | 13 | ✓ | 4 | 7 | 0 | 19 |
| ReplicationInitiation | 0 | 5 | 15 | ✓ | 4 | 8 | 0 | 17 |
| RibosomeAssembly | 0 | 5 | 6 | ∅ | 7 | 6 | 0 | 8 |
| RNADecay | 0 | KB | 2 | ∅ | 5 | 7 | 0 | 8 |
| RNAModification | 0 | KB | KB | ∅ | 6 | 6 | 0 | 15 |
| RNAProcessing | 0 | 7 | 5 | ∅ | 7 | 6 | 0 | 14 |
| TerminalOrganelleAssembly | 0 | KB | KB | ∅ | 4 | 6 | 0 | 16 |
| Transcription | 0 | 12 | 6 | ✓ | 5 | 9 | 1 | 8 |
| TranscriptionalRegulation | 0 | 0 | KB | ∅ | 4 | 8 | 0 | 11 |
| Translation | 0 | 26 | 16 | ✓ | 9 | 8 | 0 | 7 |
| tRNAAminoacylation | 0 | KB | KB | ∅ | 6 | 6 | 0 | 14 |

## Part C

- Substrates: `LITERAL=16`, `KB_COMPUTED=12`.
- Enzymes: `LITERAL=19`, `KB_COMPUTED=9`.

### Substrate KB_COMPUTED cases

- `DNADamage` `DNADamage.m:279` resolvable=`True`
  - `origin_expression`: `unique([ this.substrateWholeCellModelIDs; 'DA'; 'DC'; 'DG'; 'DT'])`
- `DNARepair` `DNARepair.m:488` resolvable=`True`
  - `origin_expression`: `unique([ this.substrateWholeCellModelIDs; {additionalSubstrates.wholeCellModelID}'; 'AD'; 'CSN'; 'GN'; 'THY'])`
- `MacromolecularComplexation` `MacromolecularComplexation.m:197` resolvable=`True`
  - `origin_expression`: `this.substrateWholeCellModelIDs(this.substrates2complexNetworks > 0)`
- `Metabolism` `ReactionProcess.m:113` resolvable=`True`
  - `origin_expression`: `[ this.stimulus.wholeCellModelIDs(stimuliIndexs); this.metabolite.wholeCellModelIDs(metaboliteIndexs); this.rna.wholeCellModelIDs(this.rna.matureIndexs(rnaIndexs)); this.monomer.wholeCellModelIDs(this.monomer.matureIndexs(monomerIndexs)); this.complex.wholeCellModelIDs(this.complex.matureIndexs(complexIndexs))]`
- `ProteinActivation` `ProteinActivation.m:165` resolvable=`True`
  - `origin_expression`: `{ monomers.wholeCellModelID ... complexs.wholeCellModelID}'`
- `ProteinDecay` `ProteinDecay.m:301` resolvable=`True`
  - `origin_expression`: `unique([ this.metabolite.wholeCellModelIDs(... any(decayReaction_nascentMonomers, 2) | ... any(decayReaction_processedIMonomers, 2) | ... any(decayReaction_processedIIMonomers, 2) | ... any(decayReaction_signalSequence, 2) | ... any(decayReaction_foldedMonomers, 2) | ... any(decayReaction_matureMonomers, 2) | ... any(decayReaction_nascentComplexs, 2) | ... any(decayReaction_matureComplexs, 2)); 'ATP'; 'ADP'; 'PI'; 'H'; 'H2O'; 'NH3'; 'FOR'])`
- `ProteinFolding` `ProteinFolding.m:267` resolvable=`True`
  - `origin_expression`: `unique([... this.substrateWholeCellModelIDs; this.metabolite.wholeCellModelIDs(sum(this.proteinProstheticGroupMatrix)>0)])`
- `ProteinModification` `ReactionProcess.m:113` resolvable=`True`
  - `origin_expression`: `[ this.stimulus.wholeCellModelIDs(stimuliIndexs); this.metabolite.wholeCellModelIDs(metaboliteIndexs); this.rna.wholeCellModelIDs(this.rna.matureIndexs(rnaIndexs)); this.monomer.wholeCellModelIDs(this.monomer.matureIndexs(monomerIndexs)); this.complex.wholeCellModelIDs(this.complex.matureIndexs(complexIndexs))]`
- `RNADecay` `RNADecay.m:173` resolvable=`True`
  - `origin_expression`: `unique([simulation.state('Metabolite').wholeCellModelIDs(... any(decayReactions_nascentRNA, 1) | ... any(decayReactions_processedRNA, 1) | ... any(decayReactions_intergenicRNA, 1) | ... any(decayReactions_matureRNA, 1) | ... any(decayReactions_aminoacylatedRNA, 1)); 'H';'H2O';'NH3';'FOR'; 'ALA';'ARG';'ASN';'ASP';'CYS';'GLN';'GLU';'GLY';'HIS';'ILE';'LEU';'LYS';'MET';'PHE';'PRO';'SER';'THR';'TRP';'TYR';'VAL';'FMET'])`
- `RNAModification` `ReactionProcess.m:113` resolvable=`True`
  - `origin_expression`: `[ this.stimulus.wholeCellModelIDs(stimuliIndexs); this.metabolite.wholeCellModelIDs(metaboliteIndexs); this.rna.wholeCellModelIDs(this.rna.matureIndexs(rnaIndexs)); this.monomer.wholeCellModelIDs(this.monomer.matureIndexs(monomerIndexs)); this.complex.wholeCellModelIDs(this.complex.matureIndexs(complexIndexs))]`
- `TerminalOrganelleAssembly` `TerminalOrganelleAssembly.m:182` resolvable=`True`
  - `origin_expression`: `sort(this.substrateWholeCellModelIDs__)`
- `tRNAAminoacylation` `tRNAAminoacylation.m:185` resolvable=`True`
  - `origin_expression`: `[this.substrateWholeCellModelIDs; 'GLN']`

### Enzyme KB_COMPUTED cases

- `DNADamage` `ReactionProcess.m:139` resolvable=`True`
  - `origin_expression`: `{ ... this.rna.wholeCellModelIDs{this.rna.matureIndexs(enzymeRNAIndexs)} ... this.monomer.wholeCellModelIDs{this.monomer.matureIndexs(enzymeMonomerIndexs)} ... this.complex.wholeCellModelIDs{this.complex.matureIndexs(enzymeComplexIndexs)}}'`
- `DNARepair` `DNARepair.m:500` resolvable=`True`
  - `origin_expression`: `unique([this.enzymeWholeCellModelIDs; 'MG_105_OCTAMER'])`
- `Metabolism` `ReactionProcess.m:139` resolvable=`True`
  - `origin_expression`: `{ ... this.rna.wholeCellModelIDs{this.rna.matureIndexs(enzymeRNAIndexs)} ... this.monomer.wholeCellModelIDs{this.monomer.matureIndexs(enzymeMonomerIndexs)} ... this.complex.wholeCellModelIDs{this.complex.matureIndexs(enzymeComplexIndexs)}}'`
- `ProteinFolding` `ProteinFolding.m:288` resolvable=`True`
  - `origin_expression`: `unique([ this.enzymeWholeCellModelIDs this.monomer.wholeCellModelIDs{this.monomer.matureIndexs(proteinMonomerChaperoneIndexs)} this.complex.wholeCellModelIDs{this.complex.matureIndexs(proteinComplexChaperoneIndexs)} ])`
- `ProteinModification` `ReactionProcess.m:139` resolvable=`True`
  - `origin_expression`: `{ ... this.rna.wholeCellModelIDs{this.rna.matureIndexs(enzymeRNAIndexs)} ... this.monomer.wholeCellModelIDs{this.monomer.matureIndexs(enzymeMonomerIndexs)} ... this.complex.wholeCellModelIDs{this.complex.matureIndexs(enzymeComplexIndexs)}}'`
- `RNAModification` `ReactionProcess.m:139` resolvable=`True`
  - `origin_expression`: `{ ... this.rna.wholeCellModelIDs{this.rna.matureIndexs(enzymeRNAIndexs)} ... this.monomer.wholeCellModelIDs{this.monomer.matureIndexs(enzymeMonomerIndexs)} ... this.complex.wholeCellModelIDs{this.complex.matureIndexs(enzymeComplexIndexs)}}'`
- `TerminalOrganelleAssembly` `ReactionProcess.m:139` resolvable=`True`
  - `origin_expression`: `{ ... this.rna.wholeCellModelIDs{this.rna.matureIndexs(enzymeRNAIndexs)} ... this.monomer.wholeCellModelIDs{this.monomer.matureIndexs(enzymeMonomerIndexs)} ... this.complex.wholeCellModelIDs{this.complex.matureIndexs(enzymeComplexIndexs)}}'`
- `TranscriptionalRegulation` `TranscriptionalRegulation.m:197` resolvable=`True`
  - `origin_expression`: `unique({ monomers.wholeCellModelID... complexs.wholeCellModelID}')`
- `tRNAAminoacylation` `tRNAAminoacylation.m:206` resolvable=`True`
  - `origin_expression`: `[ this.enzymeWholeCellModelIDs; this.rna.wholeCellModelIDs(this.rna.matureIndexs(this.rna.matureTRNAIndexs)); 'MG_0004']`

## Part D

- A fixture taxonomy that only tracks `*WholeCellModelIDs` would miss `globalStateNames`, `localStateNames`, `fittedConstantNames`, and `fixedConstantNames`; all four are present in the MATLAB source and required to describe non-vocabulary fidelity inputs.
- Ambiguous / unresolved parses:
  - None.
