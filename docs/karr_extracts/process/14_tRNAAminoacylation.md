# Karr Process - tRNAAminoacylation

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/tRNAAminoacylation.m`
**WholeCellModelID:** `Process_tRNAAminoacylation`
**Karr functional area:** RNA-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/tRNAAminoacylation_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
tRNA Aminoacylation

@wholeCellModelID Process_tRNAAminoacylation
@name             tRNA Aminoacylation
@description
  Biology
  ===============
  In biological systems tRNAs serve as mediators between the ribosome and
  the amino acids which forms peptide polymers. In this process we
  simulate the conjugation of amino acids to the tRNAs which deliver them
  to the ribosome. Additionally we simulate the aminoacylation of the
  tmRNA which similarly delivers the amino acid alanine to stalled
  ribosomes.

  Knowledge Base
  ===============
  As of 8/11/2010 the M. genitalium knowledge base contains 39 tRNA
  aminoacylation reactions involving
  - 37 aminoacylation reactions, each assuming a cost of 1 ATP per
    aminoacylation
  - 2 transfer reactions
  - 36 tRNAs and 1 tmRNA
  - 21 enzymes
  - 20 amino acid substrates and 10 additional substrates

  The reaction kinetics stored in the knowledge base were compiled
  several sources including SABIO-RK [PUB_0100].

  Note: Unlike knowledge base representation, for transfer reactions
  reactionStoichiometryMatrix doesn't include the already conjugated
  amino acid on the left-hand-side or the the ultimate conjugated amino
  acid on the right-hand-side.

  Representation
  ===============
  substrates represents the counts of free metabolites available for tRNA
  aminoacylation. enzymes represents the counts of proteins available to
  catalyze tRNA aminoacylation reactions. freeRNAs and aminoacylatedRNAs
  represent the counts of free, unaminoacylated and aminocylated RNAs. We do
  not represent intermediate states in the aminoacylation of tRNAs.  The
  molecular weights of the unaminoacylated and aminocylated tRNAs are computed
  by the knowledge base RNA classes.

  reactionStoichiometryMatrix, reactionModificationMatrix,
  reactionCatalysisMatrix, and enzymeBounds represent the tRNA aminoacylation
  reactions. reactionStoichiometryMatrix represents the free metabolites
  required for  each reaction. reactionModificationMatrix represents the tRNA
  aminoacylated by each reaction. reactionCatalysis represents the enzyme
  required to aminoacylate each tRNA. enzymeBounds represents the kcat of the
  catalyzing enzyme of each reaction. Note: reactionStoichiometryMatrix here
  is slightly modified from that computed by the super class: amino acids
  conjugated to tRNAs before and after transfer reactions have been removed
  from the left- and righ-hand-side of reactionStoichiometryMatrix.

  Initialization
  ===============
  tRNAs are all initialized to the aminoacylated state.

  Simulation
  ===============
  Uses greedy algorithm to simulate tRNA aminacylation (complexation of
  tRNAs with the specific amino acids that aminoacylate them).
  1. Deterministically activate tRNAs up to the minimum of free tRNAs and
     amino acids, proportional to free tRNAs
  2. Stoichastically activate residual tRNAs using residual amino acids
     with probabilities proportional to remaining free tRNAs

     While(true)
       1. Calculate numbers of protein monomers that can be modified based on
          substrate, enzyme, and unmodified protein monomer availability and
          kinetics.
       2. Randomly select protein monomer to modify weighted by limits
          calculated in step (1).
       3. Update substrates, enzymes, unmodified protein monomers
       4. Repeat until insufficient resources to further modify protein
          monomers
     End

Author: Markus Covert, mcovert@stanford.edu
Author: Jayodita Sanghvi, jayodita@stanfod.edu
Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 8/11/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Rna.*`, `Rna.counts`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_005_DIMER`, `MG_021_DIMER`, `MG_035_DIMER`, `MG_036_DIMER`, `MG_113_DIMER`, `MG_126_DIMER`, `MG_136_DIMER`, `MG_251_DIMER`, `MG_253_MONOMER`, `MG_266_MONOMER`, `MG_283_DIMER`, `MG_292_TETRAMER`, `MG_334_MONOMER`, `MG_345_MONOMER`, `MG_365_MONOMER`, `MG_375_DIMER`, `MG_378_MONOMER`, `MG_455_DIMER`, `MG_462_MONOMER`
- Key parameters with values:
- `- 20 amino acid substrates and 10 additional substrates`
- `3. Update substrates, enzymes, unmodified protein monomers`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? 2. Randomly select protein monomer to modify weighted by limits
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? No companion `.m` file is explicitly named in the header.

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
