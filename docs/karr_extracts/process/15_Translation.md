# Karr Process - Translation

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Translation.m`
**WholeCellModelID:** `Process_Translation`
**Karr functional area:** protein-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/Translation_flat.mat`
**OpenCell status (per karr_execution_plan §2):** DONE-v1

---

## Verbatim docstring extract

```
Translation

@wholeCellModelID Process_Translation
@name             Translation
@description
  Biology
  ===============
  Translation is the first step in the synthesis of function proteins whereby
  the ribosome, accessory enzymes, and tRNAs transcode mRNAs and produce
  amino acid polymers. Following translation proteins must be matured to
  become fully functional:
   1. Protein Processing I: N-terminal methionine deformylation and cleavage
   2. Protein Translocation: Translocation of integral membrane proteins,
      lipoproteins, and secreted proteins into and through the cell membrane
   3. Protein Processing II: Diacylglyceryl addition to lipoproteins. Signal
      sequence cleavage of lipo- and secreted proteins.
   4. Protein Folding: Folding and prosthetic group coordination of proteins.
   5. Protein Modification: Addition of covalently attached chemical groups to
      proteins.
   6. Macromolecular Complexation: Incorporation of protein monomers into
      larger macromolecular assemblies.
   7. Ribosome Assembly: Special case of macromolecular complexation of the
      ribosome which requires GTPases.
   8. Terminal Organelle Assembly: Special case of translocation which
      sequesters several protein species in a membrane-bound bleb referred to
      as the terminal organelle.
   9. Protein Activation: Functional activation and inactivation of proteins
      in response to their surrounding chemical environment.

  Translation begins with the recruitment of the 30S and 50S ribosomal
  particles and initiation factor 3 (IF3) to an mRNA molecule. Next the
  ribosomal particles assembly into a 70S ribosome on the mRNA molecule with
  the help of initiation factors. Third the ribosome polymerizes amino
  acids with the help of elongation factors. Finally release factor
  (MG_258) recognizes the stop codon UAG, release factor hydolyzes the
  peptidyl tRNA bond and dissociates, ribosome recycling factor
  dissociates the E-site tRna, elongation factor G release the release
  factor and 50S ribosome, and initiation factor 3 dissociates the 30S
  ribosome, P-site tRNA, and mRNA.

  When a ribosome stalls its lastest tRNA is expelled and replaced by the
  tRNA-like domain of a tmRNA molecule. Next the mRNA-like domain of the tmRNA
  expels the bound mRNA. Third the ribosome resumes polymerization, now
  using the tmRNA's mRNA-like domain as its template. This results in the
  production of an amino acid polymer containing a C-terminal proteolysis tag.
  Finally, the proteolysis tag will be recognized by the protein degradation
  machinery, and the amino acid polymer will be degraded into its individual
  component amino acids.

  This process simulates protein translation by ribosomes and acessory
  initiation, elongation, and termination factors. The process also simulates
  the identification of stalled ribosomes by the tmRNA, the replacement of the
  tRNA and mRNA with the tmRNA, and the synthesis of the proteolysis tag
  encoded by the tmRNA's mRNA-like domain.

  Knowledge Base
  ===============
  The knowledge base contains the region of the genome each mRNA species
  corresponds to, and the location of the tmRNA mRNA-like domain on the
  genome. This information is converted into a sequence of tRNAs which are
  required to polymerize each protein and proteolysis tag by the knowledge
  base class' computeTRNASequences method.

  Representation
  ===============
  The properties substrates, enzymes, monomers, mRNAs, freeTRNAs,
  aminoacylatedTRNAs, and aminoacylatedTMRNA represents the counts of
  metabolites, translation enzymes, nascent peptides, mature mRNAs, free
  tRNAs, aminoacylated tRNAs, and aminoacylated tmRNAs.

  monomerTRNASequences and tmRNAProteolysisTagTRNASequence represent the
  sequences of tRNAs required to polymerize each protein and proteolysis tag.
  These tRNA sequences are computed from the DNA sequence of the mRNA gene /
  tmRNA gene by the knowledge  base classs' computeTRNASequences method.

  ribosomeStates represents the state/pseudostate (actively translating, free,
  non-existent) of each ribosome. boundMRNAs indicates the mRNA
  species each actively translating ribosome is bound to. The non-existent
  pseudostate is used to keep track of elements in ribosomeStates
  and boundMRNAs which have been allocated.
  nascentMonomerLengths and proteolysisTagLengths represeent
  the position of actively  translating ribosomes on mRNAs, and if stalled on
  a tmRNA.

  Initialization
  ===============
  All protein monomers are initialized to the mature state, and in their
  correct localization. This is achieved by the simulation class
  initializeState method.

  Ribosomes are initialized to their steady state:
  - Each ribosome is randomly assigned (without replacement) to mRNA species,
    weighted by the current expression of the mRNAs,.
  - Each ribosome is randomly assigned to positions within the assigned mRNA
    with uniform probably.
  - No ribosomes are initialized to the stalled state, since the expected
    occupancy is negligible. No tmRNAs are initialized to the bound state.

  tRNAs and tmRNAs are initialized to the aminoacyated state by
  simulation.initializeState.

  Simulation
  ===============
  Evolves the states of ribosomes among two states:
  - actively translating
  - free

  Transition to from the free state to the actively translating state is
  allowed when
  - ribosome binding factor A is present
  - initiation factors (IF-1, IF-2, and IF-3) are present
  - one unit of energy (GTP) is available.
  At this time the ribosome binds an mRNA randomly with uniform probability.

  At the next iteration the initiation factors are released when the first
  amino acid, f-methionine binds and elongation begins, assuming that
  elongation factors (EF-tu, TS, and G) and energy (GTP) is available.

  ASSUMPTION made here is that one of each is sufficient for each ribosome,
  but need a separate set for each ribosome. So each ribosome can only
  translate if a full set exists for it. Also, for cases in which
  translation of a peptide finishes partway through the time step, the EFs
  are free, but haven't added the complexity of another ribosome being able
  to take up EFs partway through the timestep.

  Finally, once all amino acids of a protein have been translated,
  termination occurs if
  - at least one terminator (RF-1) available
  - at least one recycling factor available
  - at least one elongation factor G available
  - at least one trigger factor available
  - energy is available.
  The ribosome will be available to bind mRNA at the following iteration.

  Ribosomes are created in the free state.

  Algorithm
  +++++++++++++++
  1. Up to limit of elongation factors, randomly select actively translating
     ribosomes to elongate.
  2. Up to limit of initiation factors and energy, randomly select ribosomal
     particles to initiatate. These ribosome will be able to start elongating
     at the next time step. Randomly select mRNA species for each initiating
     mRNA to bind to, weighted by the counts of each mRNA species. Update
     ribosomeStates, boundMRNAs. Update substrates.
  3. Allocate available amino acids and energy among actively translating
     ribosomes. Update ribosome nascentMonomerLengths, or
     proteolysisTagLengths for stalled ribosomes with the number of
     polymerized bases. Update substrates.
  4. If ribosome has reached end of (t)mRNA and termination factors
     available, increase count of protein and dissolve (t)mRNA-ribosome
     complex. Update substrates.
  5. If ribosome hasn't advanced, then with a small probability transition
     ribosome to stalled state. Expel mRNA and replace with tmRNA. Update
     ribosomeStates. Update substrates.

  References
  ===============
  1. Petry S, Weixlbaumer A, Ramakrishnan V (2008). The termination of
     translation. Curr Opin Struct Biol. 18(1):70-7. [PUB_0226].

Author: Markus Covert, mcovert@stanford.edu
Author: Jayodita Sanghvi, jayodita@stanfod.edu
Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 1/4/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Polypeptide.*`, `Ribosome.*`, `Rna.*`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_026_MONOMER`, `MG_059_MONOMER`, `MG_083_MONOMER`, `MG_089_DIMER`, `MG_142_MONOMER`, `MG_173_MONOMER`, `MG_196_MONOMER`, `MG_258_MONOMER`, `MG_433_DIMER`, `MG_435_MONOMER`, `MG_451_DIMER`
- Key parameters with values:
- `5. If ribosome hasn't advanced, then with a small probability transition`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? amino acid polymers. Following translation proteins must be matured to
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? `Simulation.initializeState`

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
