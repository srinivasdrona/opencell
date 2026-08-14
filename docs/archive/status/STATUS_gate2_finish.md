# STATUS_gate2_finish

Chunk 1 complete and committed next: stoichiometry is now wired for the five process-specific reaction surfaces, and state-ref validation is wired for all 28 processes. Constants coverage and the integration test are still pending for chunk 2.

Current gate run:

```text
GATE 2 (OC vs spec): FAIL — diverge_cells=31, not_exposed_cells=29, processes=28
Matrix:
Process                     Vocab        Stoich   StateRefs  Constants
--------------------------  -----------  -------  ---------  -----------
ChromosomeCondensation      CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
ChromosomeSegregation       CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
Cytokinesis                 CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
DNADamage                   CONFORM      DIVERGE  DIVERGE    NOT_EXPOSED
DNARepair                   CONFORM      DIVERGE  DIVERGE    NOT_EXPOSED
DNASupercoiling             CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
FtsZPolymerization          CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
HostInteraction             CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
MacromolecularComplexation  CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
Metabolism                  NOT_EXPOSED  CONFORM  DIVERGE    NOT_EXPOSED
ProteinActivation           CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
ProteinDecay                CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
ProteinFolding              CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
ProteinModification         CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
ProteinProcessingI          CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
ProteinProcessingII         CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
ProteinTranslocation        CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
Replication                 CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
ReplicationInitiation       CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
RibosomeAssembly            CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
RNADecay                    CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
RNAModification             CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
RNAProcessing               CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
TerminalOrganelleAssembly   CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
Transcription               CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
TranscriptionalRegulation   CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
Translation                 DIVERGE      CONFORM  DIVERGE    NOT_EXPOSED
tRNAAminoacylation          CONFORM      CONFORM  DIVERGE    NOT_EXPOSED
Details:
ChromosomeCondensation [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna, ProteinMonomer, ProteinComplex] (count=4)
  - oc_ports=[boundEnzymes, chromosome, enzymes, requests, substrates, substrates_allocated] (count=6)
ChromosomeCondensation [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
ChromosomeSegregation [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna] (count=2)
  - oc_ports=[boundEnzymes, chromosome, complex, enzymes, protein, requests, substrates, substrates_allocated] (count=8)
ChromosomeSegregation [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
Cytokinesis [state_refs] DIVERGE
  - missing_in_oc=[Rna, ProteinMonomer, ProteinComplex] (count=3)
  - oc_ports=[boundEnzymes, cell, chromosome, enzymes, ftsZRing, geometry, requests, substrates, substrates_allocated] (count=9)
Cytokinesis [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
DNADamage [stoich] DIVERGE
  - species_mismatches=[DNADamage_AD_FAPyAD_hydroxyl_radical: missing_species=[AD, FAPyAD, H, gamma_radiation, hydroxyl_radical] (count=5) extra_species=[H2O] (count=1), DNADamage_AD_oxo8AD_hydroxyl_radical: missing_species=[AD, gamma_radiation, hydroxyl_radical, oxo8AD] (count=4) extra_species=[H2O] (count=1), DNADamage_CSN64CSN_CSN64CSN_dewar_UVB_radiation: missing_species=[CSN64CSN, CSN64CSN_dewar, UVB_radiation] (count=3), DNADamage_CSN64THY_CSN64THY_dewar_UVB_radiation: missing_species=[CSN64THY, CSN64THY_dewar, UVB_radiation] (count=3), DNADamage_CSNCSN_cyclobutane_CSNCSN_UVB_radiation: missing_species=[CSN, UVB_radiation, cyclobutane_CSNCSN] (count=3), DNADamage_CSNTHY_CSN64THY_UVB_radiation: missing_species=[CSN, CSN64THY, THY, UVB_radiation] (count=4), DNADamage_CSNTHY_cyclobutane_CSNTHY_UVB_radiation: missing_species=[CSN, THY, UVB_radiation, cyclobutane_CSNTHY] (count=4), DNADamage_CSN_CSN_GLYC_hydroxyl_radical: missing_species=[CSN, CSN_GLYC, gamma_radiation, hydroxyl_radical] (count=4) extra_species=[H, H2O] (count=2), DNADamage_CSN_ho5CSN_hydroxyl_radical: missing_species=[CSN, gamma_radiation, ho5CSN, hydroxyl_radical] (count=4) extra_species=[H2O] (count=1), DNADamage_DHURA_ho5Hydantoin_hydroxyl_radical: missing_species=[DHURA, gamma_radiation, ho5hydantoin] (count=3), DNADamage_GN_FAPyGN_hydroxyl_radical: missing_species=[FAPyGN, GN, H, gamma_radiation, hydroxyl_radical] (count=5) extra_species=[H2O] (count=1), DNADamage_GN_oxo8GN_hydroxyl_radical: missing_species=[GN, gamma_radiation, hydroxyl_radical, oxo8GN] (count=4) extra_species=[H2O] (count=1), +20 more] (count=32)
  - surface=reaction_small_molecule_stoich:reaction_small_molecule_stoich reaction_ids:spec.vocabularies.reactionWholeCellModelIDs(order fallback) species:substrate_wids
DNADamage [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna, ProteinMonomer, ProteinComplex] (count=4)
  - oc_ports=[boundEnzymes, chromosome, enzymes, requests, substrates, substrates_allocated] (count=6)
DNADamage [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
DNARepair [stoich] DIVERGE
  - species_mismatches=[AP_endonuclease: missing_species=[DR5P, dRibose5P_dRibose5P] (count=2), AP_lyase: missing_species=[DR5P, dRibose5P_dRibose5P] (count=2), DNAProcessiveCleavage_dAMP: missing_species=[dApdAp] (count=1), DNAProcessiveCleavage_dCMP: missing_species=[dCpdCp] (count=1), DNAProcessiveCleavage_dGMP: missing_species=[dGpdGp] (count=1), DNAProcessiveCleavage_dTMP: missing_species=[dTpdTp] (count=1), DNA_RM_EcoD_Methylation: missing_species=[AD, m6AD] (count=2), DNA_RM_EcoD_Restriction: missing_species=[DR5P, dRibose5P_dRibose5P] (count=2), DNA_RM_MunI_Methylation: missing_species=[AD, m6AD] (count=2), DNA_RM_MunI_Restriction: missing_species=[DR5P, dRibose5P_dRibose5P] (count=2), DNA_ligation_repair: missing_species=[DR5P, dRibose5P_dRibose5P] (count=2), DNA_polymerization_dATP_repair: missing_species=[DAMP, dApdAp] (count=2), +17 more] (count=29)
  - surface=reaction_small_molecule_stoich:reaction_small_molecule_stoich reaction_ids:reaction_wids species:substrate_wids; reaction_small_molecule_stoich:reaction_small_molecule_stoich reaction_ids:spec.vocabularies.reactionWholeCellModelIDs(order fallback) species:substrate_wids
DNARepair [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna] (count=2)
  - oc_ports=[boundEnzymes, chromosome, complex, enzymes, protein, requests, substrates, substrates_allocated] (count=8)
DNARepair [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
DNASupercoiling [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna] (count=2)
  - oc_ports=[boundEnzymes, chromosome, complex, enzymes, protein, requests, substrates, substrates_allocated, tx_rate_fold_change] (count=9)
DNASupercoiling [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
FtsZPolymerization [state_refs] DIVERGE
  - missing_in_oc=[Rna, ProteinMonomer, ProteinComplex] (count=3)
  - oc_ports=[boundEnzymes, cell, enzymes, requests, substrates, substrates_allocated] (count=6)
FtsZPolymerization [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
HostInteraction [state_refs] DIVERGE
  - missing_in_oc=[Rna, ProteinComplex] (count=2)
  - oc_ports=[boundEnzymes, cell, enzymes, protein, substrates] (count=5)
HostInteraction [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
MacromolecularComplexation [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna, ProteinMonomer] (count=3)
  - oc_ports=[boundEnzymes, complex, complexs, enzymes, requests, substrates, substrates_allocated] (count=7)
MacromolecularComplexation [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
Metabolism [vocab] NOT_EXPOSED
  - substrates: NOT_EXPOSED (expected=585, actual=0, attr='allocation_substrate_wids') note=OC exposes metabolism substrates through the FBA model rather than a flat 585-WID list, so a comparable flat substrate surface is not exposed.
Metabolism [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna, ProteinMonomer, ProteinComplex, CellMass] (count=5)
  - oc_ports=[boundEnzymes, enzymes, metabolic_reaction, substrates] (count=4)
Metabolism [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
ProteinActivation [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna, ProteinComplex] (count=3)
  - oc_ports=[boundEnzymes, enzymes, inactivatedSubstrates, protein, stimuli, substrates] (count=6)
ProteinActivation [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
ProteinDecay [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry] (count=1)
  - oc_ports=[boundEnzymes, complex, complexs, enzymes, monomers, polypeptide, protein, requests, rna, substrates, substrates_allocated] (count=11)
ProteinDecay [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
ProteinFolding [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna] (count=2)
  - oc_ports=[boundEnzymes, complex, enzymes, foldedMonomers, protein, substrates, substrates_allocated, unfoldedMonomers] (count=8)
ProteinFolding [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
ProteinModification [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna] (count=2)
  - oc_ports=[boundEnzymes, complex, enzymes, modifiedMonomers, protein, requests, substrates, substrates_allocated, unmodifiedMonomers] (count=9)
ProteinModification [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
ProteinProcessingI [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna] (count=2)
  - oc_ports=[boundEnzymes, complex, enzymes, processedMonomers, protein, requests, substrates, substrates_allocated, unprocessedMonomers] (count=9)
ProteinProcessingI [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
ProteinProcessingII [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna, ProteinComplex] (count=3)
  - oc_ports=[boundEnzymes, enzymes, processedMonomers, protein, requests, substrates, substrates_allocated, unprocessedMonomers] (count=8)
ProteinProcessingII [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
ProteinTranslocation [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna] (count=2)
  - oc_ports=[boundEnzymes, complex, enzymes, monomers, protein, requests, substrates, substrates_allocated] (count=8)
ProteinTranslocation [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
Replication [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna, ProteinMonomer, ProteinComplex] (count=4)
  - oc_ports=[boundEnzymes, chromosome, enzymes, requests, substrates, substrates_allocated] (count=6)
Replication [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
ReplicationInitiation [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna, ProteinComplex, CellMass] (count=4)
  - oc_ports=[boundEnzymes, chromosome, enzymes, protein, requests, substrates, substrates_allocated] (count=7)
ReplicationInitiation [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
RibosomeAssembly [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry] (count=1)
  - oc_ports=[boundEnzymes, complex, complexs, enzymes, monomers, protein, requests, rna, substrates, substrates_allocated] (count=10)
RibosomeAssembly [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
RNADecay [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, ProteinMonomer, ProteinComplex] (count=3)
  - oc_ports=[boundEnzymes, enzymes, requests, rna, substrates, substrates_allocated] (count=6)
RNADecay [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
RNAModification [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry] (count=1)
  - oc_ports=[boundEnzymes, complex, enzymes, modifiedRNAs, protein, requests, rna, substrates, substrates_allocated, unmodifiedRNAs] (count=10)
RNAModification [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
RNAProcessing [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry] (count=1)
  - oc_ports=[boundEnzymes, complex, enzymes, processedRNAs, protein, requests, rna, substrates, substrates_allocated, unprocessedRNAs] (count=10)
RNAProcessing [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
TerminalOrganelleAssembly [state_refs] DIVERGE
  - missing_in_oc=[Rna, ProteinComplex] (count=2)
  - oc_ports=[boundEnzymes, cell, enzymes, protein, substrates] (count=5)
TerminalOrganelleAssembly [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
Transcription [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, ProteinMonomer, ProteinComplex, Chromosome] (count=4)
  - oc_ports=[boundEnzymes, enzymes, rna, substrates] (count=4)
Transcription [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
TranscriptionalRegulation [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna, Chromosome] (count=3)
  - oc_ports=[boundEnzymes, complex, enzymes, protein, substrates, tf_binding, tx_rate_fold_change] (count=7)
TranscriptionalRegulation [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
Translation [vocab] DIVERGE
  - substrates: DIVERGE (expected=26, actual=20, attr='allocation_substrate_wids') missing_in_oc=[FMET, GDP, GTP, H, H2O, PI] (count=6)
Translation [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry, Rna] (count=2)
  - oc_ports=[complex, protein, substrates] (count=3)
Translation [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
tRNAAminoacylation [state_refs] DIVERGE
  - missing_in_oc=[CellGeometry] (count=1)
  - oc_ports=[aminoacylatedRNAs, boundEnzymes, complex, enzymes, freeRNAs, protein, requests, rna, substrates, substrates_allocated] (count=10)
tRNAAminoacylation [constants] NOT_EXPOSED
  - Constant validation not yet wired in this chunk.
```
