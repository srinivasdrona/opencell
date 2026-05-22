# Karr Process - ProteinModification

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinModification.m`
**WholeCellModelID:** `Process_ProteinModification`
**Karr functional area:** protein-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/ProteinModification_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
Protein Modification

@wholeCellModelID Process_ProteinModification
@name             Protein Modification
@description
  Biology
  ==================
  This process simulates protein modifications including
  - Adductions:
     - Ser/Thr/Tyr phosphorylation   (MG_109_DIMER)
     - lipoate ligation              (MG_270_MONOMER)
  - Ligations:
     - C-terminal glutamate ligation (MG_012_MONOMER)

  Many protein require covalent modifications to function properly. These
  modifications are enzymatic catalyzed.

  Knowledge Base
  ==================
  In this model of M. genitalium, there are currently 16 proteins that require
  phosphorylation at anywhere from one to 11 sites each. Only one protein
  requires lipoate ligation (pdhC), and only one requires glutamate ligation
  (rplF). All other proteins require no modification and are guaranteed to
  progress through this phase of protein maturation in a single time step.

  The knowledge base representation of the stoichiometry of protein
  monomer modification reactions includes both the unmodified amino acid
  of the unmodified protein monomer on the left-hand-side and the
  modified amino acid of the resulting modified protein monomer on the
  right-hand-side.

  Representation
  ==================
  The counts of unmodified and fully modified proteins are represented by the
  unmodifiedMonomers and modifiedMonomers properties. Intermediate modified
  states (proteins which have some, but not all of their requisite
  modifications) are not represented here. The molecular weights of the
  unmodified and fully modified protein mononomers are computed by the
  knowledge base protein monomer class.

  This process uses the reactionModificationMatrix, reactionCatalysisMatrix,
  reactionStoichiometryMatrix, and enzymeBounds properties to represent the
  modifications required to mature each protein. These properties are
  initialized from the knowledge base by initializeConstants.
  reactionModificationMatrix represents the protein monomer modified by each
  reaction. reactionCatalysisMatrix represents the enzyme which catalyzes each
  reaction. enzymeBounds represents the kcat of the enzyme for each reaction.
  reactionStoichiometryMatrix represents the free metabolites reactants and
  products of each reaction. Note reactionStoichiometryMatrix used in this
  reaction is different from that of the superclass. The
  reactionStoichiometryMatrix used here does not include either the unmodified
  amino acid of the unmodified protein monomer on the left-hand-side of
  reactions or the modified amino acid of the resulting modified protein
  monomer on the right-hand-side of reactions; these amino acids are
  represented within the unmodified and modified protein monomers. For this
  process to mature a protein monomer, each of the reactions which modifies
  that protein monomer must proceed.

  Initialization
  ==================
  All protein monomers are initialized to the mature state. This is
  accomplished by the simulation class initializeState method.

  Simulation
  ==================
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

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 1/4/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `monomer.compartments`, `compartment.terminalOrganelleCytosolIndexs`, `compartment.cytosolIndexs`, `compartment.terminalOrganelleMembraneIndexs`, `compartment.membraneIndexs`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_012_MONOMER`, `MG_109_DIMER`, `MG_270_MONOMER`
- Key parameters with values:
- `3. Update substrates, enzymes, unmodified protein monomers`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? that protein monomer must proceed.
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? `Simulation.initializeState`

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
