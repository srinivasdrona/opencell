# Karr Process - RNAModification

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RNAModification.m`
**WholeCellModelID:** `Process_RNAModification`
**Karr functional area:** RNA-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/RNAModification_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
RNA Modification

@wholeCellModelID Process_RNAModification
@name             RNA Modification
@description
  Biology
  ==================
  This process simulates r/tRNA modifications including
  - rRNA methylation                                       MG_252_DIMER, MG_346_DIMER, MG_380_MONOMER, MG_463_MONOMER
  - rRNA pseudouridation                                   MG_209_MONOMER, MG_370_MONOMER
  - tRNA methylation                                       MG_347_DIMER, MG_445_DIMER
  - tRNA pseudouridation                                   MG_182_DIMER
  - tRNA lysidine synthetase                               MG_084_TETRAMER
  - tRNA sulfur transfer                                   MG_295_MONOMER, MG_372_MONOMER
  - tRNA uridine 5-carboxymethylaminomethyl modification   MG_008_379_TETRAMER

  These modifications are believe to help RNAs fold properly and achieve their
  catalytically active structure. The modifications are also believed to
  improve RNA stability. In addition some tRNA modifications, namely the
  modifications near the wobble position are believed to enhance codon
  recognition. These modifications are enzymatically catalyzed by 13 proteins.

  Knowledge Base
  ==================
  As of 8/11/2010 the M. genitalium knowledge base contained 91 RNA
  modification reactions involving 38 RNAs and 13 enzymes. Each of the 38
  RNAs is involved in 1-7 reactions. All other RNAs require no
  modification and are guaranteed to progress through this phase of RNA
  maturation in a single time step.

  The knowledge base representation of the stoichiometry of RNA
  modification reactions includes both the unmodified nucleic acid of the
  unmodified RNA on the left-hand-side and the modified nucleic acid of
  the resulting modified RNA on the right-hand-side.

  Representation
  ==================
  The counts of unmodified and fully modified RNAs are represented by the
  unmodifiedRNAs and modifiedRNAs properties. Intermediate modified
  states (RNAs which have some, but not all of their requisite
  modifications) are not represented here. The molecular weights of the
  unmodified and fully modified RNAs are computed by the knowledge base RNA
  classes.

  This process uses the reactionModificationMatrix, reactionCatalysisMatrix,
  reactionStoichiometryMatrix, and enzymeBounds properties to represent the
  modifications required to mature each RNA. These properties are
  initialized from the knowledge base by initializeConstants.
  reactionModificationMatrix represents the RNA modified by each reaction.
  reactionCatalysisMatrix represents the enzyme which catalyzes each reaction.
  enzymeBounds represents the kcat of the enzyme for each reaction.
  reactionStoichiometryMatrix represents the free metabolites reactants and
  products of each reaction. Note reactionStoichiometryMatrix used in this
  reaction is different from that of the superclass. The
  reactionStoichiometryMatrix used here does not include either the unmodified
  nucleic acid of the unmodified RNA on the left-hand-side of reactions or the
  modified nucleic acid of the resulting modified RNA on the right-hand-side
  of reactions; these nucleic acids are represented within the unmodified and
  modified RNAs. For this process to mature a RNA, each of the reactions which
  modifies that RNA must proceed.

  Initialization
  ==================
  All RNAs are initialized to the mature state. This is accomplished by the
  simulation class initializeState method.

  Simulation
  ==================
  While(true)
    1. Calculate numbers of RNAs that can be modified based on
       substrate, enzyme, and unmodified RNA availability and kinetics.
    2. Randomly select RNA to modify weighted by limits calculated in
       step (1).
    3. Update substrates, enzymes, unmodified RNAs
    4. Repeat until insufficient resources to further modify RNAs
  End

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 8/10/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Rna.*`, `Rna.counts`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_084_TETRAMER`, `MG_182_DIMER`, `MG_209_MONOMER`, `MG_252_DIMER`, `MG_295_MONOMER`, `MG_346_DIMER`, `MG_347_DIMER`, `MG_370_MONOMER`, `MG_372_DIMER`, `MG_372_MONOMER`, `MG_380_MONOMER`, `MG_445_DIMER`, `MG_463_MONOMER`
- Key parameters with values:
- `3. Update substrates, enzymes, unmodified RNAs`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? modifies that RNA must proceed.
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? `Simulation.initializeState`

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
