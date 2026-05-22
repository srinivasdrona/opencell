# Karr Process - MacromolecularComplexation

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/MacromolecularComplexation.m`
**WholeCellModelID:** `Process_MacromolecularComplexation`
**Karr functional area:** protein-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat`
**OpenCell status (per karr_execution_plan §2):** STUBBED

---

## Verbatim docstring extract

```
Macromolecular complexation

@wholeCellModelID Process_MacromolecularComplexation
@name             Macromolecular complexation
@description
  Biology
  ===============
  An important step in the synthesis of functional enzymes is the
  stochiometric formation of macromolecular complexes. Macromolecular
  complexation is kinetically fast, and energetically favorable.
  Consequently, the model assumes that complexation is limited only by
  subunit availability, and proceeds to completion rapidly. In addition,
  we assume that each complex forms with the same specific rate.

  Knowledge Base
  ===============
  As of 8/17/2010 the M. genitalium knowledge base contained 155
  macromolecular complexes involving 262 protein monomer species and 5 RNA
  species, and 277 links between protein/RNA/complex subunit species and
  complexes. Of these 155 complexes, detailed information is available on
  the formation of 6, and these six complexes are formed in other processes.
  The remaining 149 are formed by this process. The following table lists
  several statistics about the macromolecular complexation network.

     Statistic                                      Value
     ===========================================    ===========
     Mean no. subunit species per complex           1.8 +/- 3.2
     Min, Max no. subunits species per complex      1 - 34
     Mean no. subunits per complex                  5 +/- 15.6
     Min, Max no. subunits per complex              2 - 192
     Mean no. complexes per monomer species         1 +/ 0.1
     Min, Max no. complexes per monomer species     1 - 2
     No. subunits participating in >1 complexes     5
     No. subunits which are themselves complexes    5
     No. complexes formed in this process            149
     No. complexes formed in other processes          6

  Representation
  ===============
  Two properties are used to represent the counts of the 149 macromolecular
  complexes formed by this process (complexs), and of free macromolecular
  complex subunits (substrates).

  Four properties are used to represent the structure of the macromolecular
  complex - subunit network: complexComposition, complexNetworks,
  substrates2complexNetworks, and complexs2complexNetworks. complexComposition
  is an adjancency matrix between subunits and complexes populated from the
  knowledge base; entries contain the number of subunits of each type in each
  complex. complexNetworks is cell array containing the clustering of
  complexComposition built by findNonInteractingRowsAndColumns called by
  initializeConstants; each entry represents a disconnected part of the
  macromolecular complex - subunit network, which can be simulated separate from
  all other disconnected parts. substrates2complexNetworks and
  complexs2complexNetworks represent mappings between substrates and complexs
  and the disconnected parts of the macromolecular complex - subunit network
  stored in complexNetworks.

  Initialization
  ===============
  Macromolecular complexes are initialized up to the amounts of RNA and
  protein subunits initialized by other processes.

  Simulation
  ===============
  Macromolecular complexes are formed assuming:
  1) Complexation is highly energetically favorable and
  2) Complexation is fast, and thus
  3) Macromolecular complexes are formed to completion; that is until
     there are insufficient free monomers to form additional complexes.

  Complexes are formed according to Monte Carlo simulation for
  each independent protein complex network (previously established by
  initializeConstants and stored in complexNetworks,
  substrates2complexNetworks, and complexs2complexNetworks). First,
  we use mass-action kinetics to compute the relative formation rate of
  each complex. Specifically we compute the relative formation rate as
  the product of the concentration of all monomers raised to the power of
  their stoichiometries within the complex. Second we stochastically form
  complexes according the computed formation rates. This is repeated until
  no further complexes can form.

Author: Jonathan Karr, jkarr@stanford.edu
Author: Markus Covert, mcovert@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 1/4/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Rna.*`, `complex.counts`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: None explicitly named in header.
- Key parameters with values:
- `Mean no. subunit species per complex           1.8 +/- 3.2`
- `Mean no. subunits per complex                  5 +/- 15.6`
- `substrates2complexNetworks, and complexs2complexNetworks. complexComposition`
- `all other disconnected parts. substrates2complexNetworks and`
- `complexs2complexNetworks represent mappings between substrates and complexs`
- `substrates2complexNetworks, and complexs2complexNetworks). First,`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? No additional subtlety beyond the explicit Representation/Simulation/Algorithm sections in the header.
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? No companion `.m` file is explicitly named in the header.

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
