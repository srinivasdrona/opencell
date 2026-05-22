# Karr Process - ProteinProcessingII

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinProcessingII.m`
**WholeCellModelID:** `Process_ProteinProcessingII`
**Karr functional area:** protein-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/ProteinProcessingII_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
Protein Processing II

@wholeCellModelID Process_ProteinProcessingII
@name             Protein Processing II
@description
  Biology
  ===============
  Proteins are produced in the cytoplasm, and integral membrane proteins,
  lipoproteins, and extracellular proteins must be translocated into and
  through the cell membrane to reach their intended destination. To be
  recognized by the translocation machinery lipoprotein and secreted proteins
  contain type II N-terminal signal sequences, which are typically 10-15 amino
  acids long and positively charged. Following translocation lipoproteins must
  be anchored to the outter leaflet of the cell membrane by the addition of
  diacylglyceryl by diacylglyceryl transferase (Lgt, MG_086) to what will
  become the C-terminal cysteine, and their signal sequence must be cleaved by
  signal peptidase II (LspA, MG_210) at lipoboxes (L[ASI][GA]C). M. genitalium
  does not contain an apolipoprotein transacylase [PUB_0655, PUB_0656,
  PUB_0657]. The signal peptides of secreted proteins is similarly cleaved.

  This process simulates lipoprotein and secreted protein maturation:
  - diacylglyceryl transfer  Lgt (MG_086) catalyzes transfer of
    diacylglycerol group to sulfhydryl group of lipobox cysteine
    [PUB_0654].
  - signal peptide cleavage  LspA (MG_210) cleaves lipoprotein at
    lipobox cysteine [PUB_0654].

  Knowledge Base
  ===============
  The localization of each protein, and the signal peptide type and length of
  lipoproteins and secreted proteins was compiled from several sources (see
  protein translocation process). The information was organized in the
  knowledge base, and is the type of each signal peptide is encoded in the
  this process's lipoproteinMonomerIndexs, secretedMonomerIndexs, and
  unprocessedMonomerIndexs properties by initializeConstants.

  Representation
  ===============
  The substrates and enzymes represents the counts of available metabolites
  and diacylglyceryl transferase and signal peptidase enzymes.
  unprocessedMonomers, processedMonomers, and signalSequenceMonomers represent
  the counts of unanchored, uncleaved protein monomers; anchored, cleaved
  protein monomers; and the separted, free signal sequences. This process does
  not represent any intermediate states in the anchoring and cleavage of lipo-
  and secreted proteins. This process consideres anchoring and cleavage to be
  an all-or-nothing event.

  The lipoproteinMonomerIndexs and secretedMonomerIndexs properties represent
  the indices of lipo-and secreted proteins and their released signal
  sequences within unprocessedMonomers, processedMonomers, and
  signalSequenceMonomers. unprocessedMonomerIndexs indicating the indices of
  non-lipo-, non-secreted proteins and their released signal sequences (not
  used in simulation; only allocated for convenience and parallelism) within
  unprocessedMonomers, processedMonomers, and signalSequenceMonomers.

  Initialization
  ===============
  All protein monomers are initialized to the mature state. This is
  accomplished by the simulation class initializeState method.

  Simulation
  ===============
  1. Compute the maximum number of peptides that can be processed based on the
     availability of metabolites, and of the two enzymes.
  2. Randomly select peptides to be processed, weighted by the counts of each
     protein species.
  3. Update the counts of unprocessed and processed proteins monomers.
     Decrement the counts of available metabolites and enzyme activity.
  4. Compute the maximum number of peptides which don't require anchoring that
     can be processed based on the availability of signal peptidase II
     activity.
  5. Randomly select peptides to be cleaved, weighted by the counts of
     each protein species.
  6. Update the counts of unprocessed and processed proteins monomers.
     Decrement the counts of available signal peptidase II activity.
  7. Transition proteins which don't requiring anchoring or cleavage (eg.
     cytosolic and integral membrane proteins). That is set processedMonomers
     equal to its sum with unprocessedMonomers for these monomers, and set
     unprocessedMonomers to zero for these monomers.

  References
  ===============
  1. Chambaud I, Wrblewski H, Blanchard A (1999). Interactions between
     mycoplasma lipoproteins and the host immune system. Trends
     Microbiol. 7(12): 493-9. [PUB_0654].
  2. Chambaud I, Heilig R, Ferris S, Barbe V, Samson D, Galisson F,
     Moszer I, Dybvig K, Wroblewski H, Viari A, Rocha EP, Blanchard A
     (2001). The complete genome sequence of the murine respiratory
     pathogen. Mycoplasma pulmonis. Nucleic Acids Res. 29(10):2145-53.
     [PUB_0655]
  3. Muhlradt PF, Kiess M, Meyer H, Sssmuth R, Jung G (1997). Isolation,
     structure elucidation, and synthesis of a macrophage stimulatory
     lipopeptide from Mycoplasma fermentans acting at picomolar
     concentration. J Exp Med. 185(11):1951-8. [PUB_0656].
  4. Piec G, Mirkovitch J, Palacio S, Muhlradt PF, Felix R (1999). Effect
     of MALP-2, a lipopeptide from Mycoplasma fermentans, on bone
     resorption in vitro. Infect Immun. 67(12):6281-5. [PUB_0657].
  5. Sankaran K, Wu HC (1994). Lipid modification of bacterial
     prolipoprotein. Transfer of diacylglyceryl moiety from
     phosphatidylglycerol. J Biol Chem. 269(31):19701-6. [PUB_0266]

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 8/9/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `monomer.counts`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_086_MONOMER`, `MG_210_MONOMER`
- Key parameters with values:
- Not explicitly quantified in the header beyond symbolic algorithm expressions.
- Any algorithm subtlety that an implementer would miss reading only the @description summary? lipoproteins, and extracellular proteins must be translocated into and
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? `Simulation.initializeState`

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
