# Karr Process - TerminalOrganelleAssembly

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/TerminalOrganelleAssembly.m`
**WholeCellModelID:** `Process_TerminalOrganelleAssembly`
**Karr functional area:** host-interaction
**OpenCell fixture:** `data/karr_fixtures/per_process/TerminalOrganelleAssembly_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
Assemble Terminal Organelle

@wholeCellModelID Process_TerminalOrganelleAssembly
@name             Terminal Organelle Assembly
@description
  Biology
  ===============
  The terminal organelle is a 300 x 80 nm membrane-bound bleb believed to
  be involved in several processes including motility, adhesion,
  replication, and cytokinesis. The terminal organelle is electron lucent 
  and non-fibrillar and enriched for adhesins and adhesin accessory proteins 
  which help the adhesins localize to the terminal organelle. The terminal 
  organelle has been investigated in several studies by Mitchell Balish at
  Miami University of Ohio and Duncan Krause of the University of Georgia. In
  particular, they have examined the composition and assembly of the electron
  dense (protein) portion of the terminal organelle, and have examined the
  duplication and migration to the opposite pole of the daughter terminal
  organelle during cell division. Pich et al have studied the regulation of
  terminal organelle duplication.

  The terminal organelle is composed of 8 proteins.
  - HMW1-3
  - MgPa
  - P32, P65, P110, P200

  These 8 proteins assemble in a stereotyped order; that is, there is a
  heirarchical pattern to the assembly of the terminal organelle: several
  proteins require other proteins to be already localized in the terminal
  organelle to be incorporated into the terminal organelle, and two proteins
  HMW1 and HMW2 require the other either to already been incorporated in the
  terminal organelle, or free in the cytoplasm to be incorporated into the
  terminal organelle. No kinetic information has been reported on terminal
  organelle assembly.

  During replication a second organelle is believed to duplicate from the
  first organelle and migrate toward the opposite pole.

  Knowledge Base
  ===============
  The hierarchical pattern of terminal organelle assembly among the 8 proteins
  is encoded in 10 reactions in the knowledge base.

  Representation
  ===============
  Proteins are incorporated according to one of two patterns:
  - cytoplasm -> terminal organelle cytoplasm
  - membrane  -> terminal organelle membrane

  The counts of terminal organelle proteins are represented by the substrates
  property. Because proteins are only incorporated in two patterns, the
  substrates property has two compartments: one to represent the
  unincorporated compartment of each protein (cytoplasm/membrane) and a
  second for the incorporated compartment of each protein (terminal organelle
  cytoplasm/membrane).

  The hierarchical pattern of terminal organelle assembly is represented in
  this process by localizationReactions and localizationSubstrates.
  localizationSubstrates represents the protein translocated by each of the
  10 reactions. localizationReactions represents the proteins (and the
  compartment in which the protein must be located) required for each
  translocation reaction to proceed.

  Initialization
  ===============
  Terminal organelle proteins are all initialized into the terminal organelle
  compartments.

  Simulation
  ===============
    1. Compute which reactions can proceed based on the amounts of
       unincorporated and incorporated proteins.
    2. Compute which proteins can localize to the terminal organelle based on
       step (1).
    3. Incorporate the proteins that can localize into the terminal organelle.
    4. Repeat steps 1-3 until no additional proteins can localize.

  References
  ===============
  1. Structure, function, and assembly of the terminal organelle of
     Mycoplasma pneumoniae (2001). FEMS Microbiology Letters. 198: 1-7.
  2. Cellular engineering in a minimal microbe: structure and assembly of
     the terminal organelle of Mycoplasma pneumoniae (2004). Mol
     Microbiol. 51(4): 917-24.
  3. Razin S, Jacobs E (1992). Mycoplasma adhesion. J Gen Microbiol.
     138(3): 407-22. [PUB_0088].
  4. Balish (2006). Subcellular structures of mycoplasmas. Front Biosci.
     11: 2017-27. [PUB_0407]
  5. Chaudhry R, Varshney AK, Malhotra P (2007). Adhesion proteins of
     Mycoplasma pneumoniae. Front Biosci. 12: 690-9. [PUB_ 0406]
  6. Balish MF, Krause DC (2006). Mycoplasmas: A Distinct Cytoskeleton
     for Wall-Less Bacteria. J Mol Microbiol Biotechnol. 11(3-5): 244-55.
     [PUB_0091]
  7. Pich OQ, Burgos R, Querol E, Pinol J (2009). P110 and P140 
     cytadherence-related proteins are negative effectors of terminal 
     organelle duplication in Mycoplasma genitalium. PLoS One. 4 (10):
     e7452. [PUB_0794].
  8. Pich OQ,Burgos R,Ferrer-Navarro M,Querol E,Pinol J (2008). 
     Role of Mycoplasma genitalium MG218 and MG317 cytoskeletal proteins in 
     terminal organelle organization, gliding motility and cytadherence. 
     Microbiology. 154 (Pt 10): 3188-98. [PUB_0803]
  9. Boonmee A, Ruppert T, Herrmann R (2009). The gene mpn310 (hmw2) from 
     Mycoplasma pneumoniae encodes two proteins, HMW2 and HMW2-s, which
     differ in size but use the same reading frame. FEMS Microbiol Lett.
     290(2): 174-81. [PUB_0804]

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 1/4/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Stimulus.*`, `Metabolite.*`, `Rna.*`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_191_MONOMER`, `MG_192_MONOMER`, `MG_217_MONOMER`, `MG_218_MONOMER`, `MG_312_MONOMER`, `MG_317_MONOMER`, `MG_318_MONOMER`, `MG_386_MONOMER`
- Key parameters with values:
- `HMW1 and HMW2 require the other either to already been incorporated in the`
- `3. Incorporate the proteins that can localize into the terminal organelle.`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? These 8 proteins assemble in a stereotyped order; that is, there is a
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? No companion `.m` file is explicitly named in the header.

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
