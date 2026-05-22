# Karr Process - RibosomeAssembly

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RibosomeAssembly.m`
**WholeCellModelID:** `Process_RibosomeAssembly`
**Karr functional area:** protein-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/RibosomeAssembly_flat.mat`
**OpenCell status (per karr_execution_plan §2):** STUBBED

---

## Verbatim docstring extract

```
Assemble Ribosomes

@wholeCellModelID Process_RibosomeAssembly
@name             Ribosomal Assembly
@description
  Biology
  ===============
  Assembly of the 30S and 50S ribosomal particles is a special case of
  macromolecular complexation in which subunits are incorporated in a
  stereotyped pattern [PUB_0660, PUB_0661], and which requires six
  energy-dependent GTPases  EngA, EngB, Era, Obg, RbfA, and RbgA. The
  exact energy requirement of each GTPase is unknown. Here we assume that
  each GTPase that has been reported to be required to form each
  ribosomal particle requires 1 GTP per particle. 

  Knowledge Base
  ===============
  The 30S and 50S ribosomal particles are represented as complexes in the
  knowledge base. Their RNA and protein subunit composition was curated from
  the literature, and is stored in association with the complexes in the
  knowledge base. This composition is loaded by initializeConstants into this
  process's proteinComplexRNAComposition and proteinComplexMonomerComposition
  properties.

  Representation
  ===============
  substrates, enzymes, RNAs, monomers, and complexs represent the counts of
  free metabolites (eg. ATP, ADP, Pi, H2O, H+), the ribosomal assembly
  GTPases, the amounts of RNA and protein monomer ribosomal subunits, and the
  30S and 50S ribosomal particles. The process doesn't represent any
  intermediate state of ribosomal particle assembly; ribosomal particle
  assembly is assumed to be an all-or-nothing process on the time scale of
  this process. That is, we make the simplifying assumption that either a
  ribosomal particle completely forms within a single time step, or no
  progress in assembly of that particle is made during that time step.

  proteinComplexRNAComposition and proteinComplexMonomerComposition represent
  the RNA and protein monomer composition of the 30S and 50S ribosomal
  subunits. complexationCatalysisMatrix represents the GTPases required to
  form each ribosomal particle.

  Initialization
  ===============
  The process is initialized to a state with the maximal number of formed
  ribosomal particles given the amounts of initialized RNA and protein
  monomers. That is, the process is initialized to a state where insufficient
  RNA and protein monomers are available to form additional ribosomal subunits.

  Simulation
  ===============
  In a randomized order over particles, for each ribosomal particle:
  1. Calculate the maximum number of particles that can form based on
     available RNA and protein monomer subunits, GTPases, and GTP.
  2. Increment the number of ribosomal particles. Decrement the numbers of RNA
     and protein monomer subunits, and GTP and water. Increment the counts of
     the byproducts of GTP hydrolysis (GDP, Pi, H).

  This makes the simplying assumption that ribosomal assembly is fast compared
  to the 1s time scale of this process, and is energetically favorable such
  that in the presence of saturating enzymes and energy, ribosomal assembly is
  limited by the subunit availability.

  References
  ===============
  1. Nierhaus KH (1991). The assembly of prokaryotic ribosomes.
     Biochimie. 76(3):739-55.[PUB_0660]
  2. Culver GM (2003). Assembly of the 30S ribosomal subunit.
     Biopolymers. 68(2):234-49. [PUB_0661]

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 1/4/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Rna.*`, `Rna.counts`, `monomer.counts`, `complex.counts`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_143_MONOMER`, `MG_329_MONOMER`, `MG_335_MONOMER`, `MG_384_MONOMER`, `MG_387_MONOMER`, `MG_442_MONOMER`
- Key parameters with values:
- Not explicitly quantified in the header beyond symbolic algorithm expressions.
- Any algorithm subtlety that an implementer would miss reading only the @description summary? assembly is assumed to be an all-or-nothing process on the time scale of
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? No companion `.m` file is explicitly named in the header.

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
