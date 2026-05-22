# Karr Process - ProteinProcessingI

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinProcessingI.m`
**WholeCellModelID:** `Process_ProteinProcessingI`
**Karr functional area:** protein-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/ProteinProcessingI_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
Protein Processing I

@wholeCellModelID Process_ProteinProcessingI
@name             Protein Processing I
@description
  Biology
  ===========
  Following translation, nascent peptides are deformylated, cleaved,
  translocated, folded, and modified. First, peptide deformylase (MG_106)
  deformylates the N-terminal formylmethionine of each nascent peptide.
  Second, methionine aminopeptidase (MG_172) cleaves the N-terminal methionine
  of 35 peptides. Second (see protein translocation process), 117 integral
  membrane, lipoproteins, and extracellular proteins bind the SecA translocase
  and are translocated into and through the plasma membrane via the
  SecYEGDF-YidC pore. Third (see protein processing II process), diacylglyceryl
  is transferred to the C-terminal cysteine of the signal sequence of each
  lipoprotein by diacylglyceryl transferase, and the signal sequence of each
  lipoprotein is cleaved by signal peptidase II. Next (see protein
  folding process), 85 peptides bind inorganic ions at particular sites
  and 64 peptides fold with the assistance of the chaperones and chaperonins
  DnaJ, DnaK, GroEL, GroES, and GrpE. All peptides require trigger factor
  to properly fold. Finally (see protein modification process), 20 peptide
  species are modified at 63 sites by 3 enzymes  serine/threonine protein
  kinase, lipoate ligase, and alpha glutamate ligase.

  This process simulates
  - N-terminal peptide deformylation, and
  - N-terminal amino acid cleavage.

  Knowledge Base
  ===========
  Every M. genitalium protein requires deformylation, and roughly 7%
  require N-terminal amino acid cleavage. N-terminal methionine cleavages were
  reconstructed by mapping N-terminal methionine cleavages observed in
  Shewanella oneidensis MR-1 [PUB_0280] onto homologous M. genitalium genes.
  The N-terminal methionine cleavage state of each protein monomer is
  organized in the knowledge base, and loaded into the
  nascentMonomerNTerminalMethionineCleavages property of this process by the
  initializeConstants method.

  Representation
  ===========
  substrates, enzymes, unprocessedMonomers, and processedMonomers represent
  the counts of metabolites, the deformylase and methionine aminopeptidase,
  and nascent and deformylated, cleaved protein monomers. The compartment
  dimension of each of these properties has length 1. That is the process only
  accesses the counts of these objects in the relevant compartments. This
  process doesn't represent any additional intermediate processed states. This
  process treats N-terminal deformylation and methionine cleavage as an
  all-or-nothing event that either proceeds to complete within a single time
  step, or does not occur at all.

  nascentMonomerNTerminalMethionineCleavages is a boolean which represents
  whether or not the N-terminal methionine of each protein monomer must be
  cleaved.

  Initialization
  ===============
  All protein monomers are initialized to the mature state. This is
  implemented by the simulation class initializeState method.

  Simulation
  ===========
  1. Compute the maximum number of peptides that can be processed based on the
     availability of the two enzymes.
  2. Randomly select peptides to be processed, weighted by the counts of each
     protein species.
  3. Update the counts of unprocessed and processed proteins monomers.
     Decrement the counts of available enzyme activity.
  4. Compute the maximum number of peptides which don't require cleavage that
     can be processed based on the availability of peptide deformylase
     activity.
  5. Randomly select peptides to be deformylated, weighted by the counts of
     each protein species.
  6. Update the counts of unprocessed and processed proteins monomers.
     Decrement the counts of available deformylase activity.

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 7/30/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `monomer.counts`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_106_DIMER`, `MG_172_MONOMER`
- Key parameters with values:
- Not explicitly quantified in the header beyond symbolic algorithm expressions.
- Any algorithm subtlety that an implementer would miss reading only the @description summary? all-or-nothing event that either proceeds to complete within a single time
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? `Simulation.initializeState`

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
