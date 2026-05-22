# Karr Process - ProteinTranslocation

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinTranslocation.m`
**WholeCellModelID:** `Process_ProteinTranslocation`
**Karr functional area:** protein-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/ProteinTranslocation_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
Translocate Proteins

@wholeCellModelID Process_ProteinTranslocation
@name             Protein translocation
@description
  Biology
  ===============
  Proteins are produced in the cytoplasm, and integral membrane proteins,
  lipoproteins, and extracellular proteins must be translocated into and
  through the cell membrane to reach their intended destination. These three
  types of proteins are recognized by the translocation machinery through
  N-terminal signal sequences. Integral membrane proteins are first
  recognized by the signal recognition particle (SRP) which in turn delivers
  them to the the preprotein translocase and pore. Lipoproteins and
  extracellular proteins are recognized directly by the preprotein translocase
  and pore. After association with the preprotein translocase, proteins are
  pushed through the preprotein translocation pore by an ATP-dependent,
  step-wise mechanism. After insertion into/through the membrane lipoprotein
  and extracellular protein signal peptides are cleaved (see Protein
  Processing II process).

  This process simulates protein translocation into and through the cell
  membrane involving four enzymes:
  - signal recognition particle
  - signal recognition particle receptor
  - translocase ATPase
  - translocase pore

  Knowledge Base
  ===============
  We assigned each protein monomer and complex to one of the localizations:
  - Integral membrane
  - Lipoprotein
  - Cytoplasmic
  - Extracellular
  - Terminal oganelle, cytoplasmic
  - Terminal organelle, integral membrane

  The localization of each protein, and the signal peptide length of
  lipoproteins and secreted proteins was compiled from several sources:
  - Computational prediction of membrane spanning domains and signal peptides
    - Phobius [PUB_0262]
    - PrediSi [PUB_0255]
    - SignalP-HMM [PUB_0263]
    - SignalP-NN [PUB_0263]
    - SOSUI [PUB_0261, PUB_0264]
    - SPdb database of observed signal peptides [PUB_0253]
  - Mass-Spec determination of the N-terminal residue of each protein [PUB_0280]
  - Databases of protein localization: BRENDA [PUB_0570], DBSubLoc [PUB_0573],
    EchoBase [PUB_0574], GenoBase [PUB_0386], PSortDB [PUB_0572], and UniProt
    [PUB_0096]
  - Primary literature of the composition of the terminal organelle [PUB_0088,
    PUB_0089, PUB_0091, PUB_0092, PUB_0093, PUB_0406, PUB_0407, PUB_0408, PUB_0409]
  - Primary literature [PUB_0284, PUB_0303]

  Additionally, we tried unsuccessfully to include computational predictions
  from these sources:
  - SecretomeP  didn't predicted any secreted peptides [PUB_0252]
  - LipPred     had CGI and bad request errors [PUB_0254]
  - SIG-Pred    found no signal sequences [PUB_0255]
  - sigcleave   unclear what it returns [PUB_0257]
  - TatFind     identified no Tat signal peptides [PUB_0258]
  - PilFind     identified no type IV pilin-like signal peptides [PUB_0259]
  - SPEPLip     provides no easy way to query on genome-scale [PUB_0260]

  Roughly 25% of M. genitalium proteins require translocation.
    Localization         No. Monomers
    =================    ============
    Cytosol              363
    Integral membrane     82
    Lipoprotein           14
    Secreted              20
    -----------------    ------------
    Total                479

  Representation
  ===============
  The substrates, enzymes, and monomers properties represent the counts of
  metabolites, translocation enzymes, and protein. The substrates and enzymes
  properties have compartment dimension length 1, meaning that the process only
  accesses the counts of each metabolite and enzyme in the relevant
  compartment. The monomers property has compartment dimension length 5,
  meaning it accesses protein monomers in all compartments of the simulation.
  Although it is known that protein translocation proceeds in discrete steps,
  this process doesn't not represent any intermediate states of protein
  translocation. The process treats protein translocation as an all-or-nothing
  event.

  monomerSRPPathways is a boolean which represents whether or not each protein
  monomer requires the signal recognition particle (SRP) and its receptor to
  translocate. This variable is true for integral membrane proteins, and false
  otherwise. monomerLengths represents the number of amino acids in each
  protein monomer species.
  ceil(monomerLengths/preproteinTranslocase_aaTranslocatedPerATP) represents
  the ATP cost of the translocase to translocate each monomer.
  SRP_GTPUsedPerMonomer represents the GTP cost to translocate each integral
  membrane protein.

  Initialization
  ===============
  All protein monomers are initialized to the mature state, and in their
  correct localization. This is achieved by the simulation class
  initializeState method.

  Simulation
  ===============
  In a randomized order, for each protein monomer across all species that
  requires translocation
  1. Calculate amount of ATP, GTP, SRP, and translocase required to
     translocate the single monomer.
  2. Terminate if insufficient resources exist to translocate the monomer.
  3. Update the counts of ATP, GTP, ADP, GDP, Pi, H2O, and H+.
  4. Decrement the counts of available SRP and translocase
  5. Increment the count of the monomer in its localized compartment.
     Decrement the count of the monoemr in the cytosol compartment.

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 7/30/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `monomer.counts`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_072_DIMER`, `MG_297_MONOMER`
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
