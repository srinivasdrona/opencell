# Karr Process - RNADecay

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RNADecay.m`
**WholeCellModelID:** `Process_RNADecay`
**Karr functional area:** RNA-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/RNADecay_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
RNA Decay

@wholeCellModelID Process_RNADecay
@name             RNA Decay
@description
  Biology
  ===============
  In presence of ribonucleases such as ribonuclease R (MG_104_MONOMER) RNAs
  have relatively short half lives compared to that of other macromolecules
  (eg. protein, DNA) and the M. genitalium cell cycle length. The relatively
  short half lives of RNAs enables the small M. genitalium with its very small
  pool of RNAs and particularly mRNAs to sample a broader range of
  configurations of the RNA pool over a shorter period that would be possible
  with longer half lifes. This helps the cell more finely tune the expression
  of proteins, more efficiently execute cell-cycle dependent events, and
  respond to the external environment. This enhanced fitness due to short RNA
  half lifes comes at a large energetic cost however.

  In addition to ribonucleases, aminoacylated RNAs require peptidyl tRNA
  hydrolase (MG_083_MONOMER) to release their conjugated amino acids.

  This process decays all species of RNA, and at all maturation states
  including aminoacylated states.

  Knowledge Base
  ===============
  The knowledge base contains experimentally measured half lifes of many RNA
  species measured largely in E. coli and mapped to M. genitalium by homology.
  These half lifes are refined, by simulation.fitConstants to make them
  consistent with other experimental data used to fit the model. Prior to
  fitting missing half lifes are imputed either as the average of that of all
  measured RNA species.

     Type   Avg Half Life (m)
     ====   =================
     mRNA   4.5 +/- 2.0
     rRNA   150
     sRNA   89
     tRNA   45

  Representation
  ===============
  The substrates, enzymes, and RNAs properties represent the counts of
  metabolites, ribonuclease R and peptidyl tRNA hydrolase enzymes, and RNAs.
  This process contains no intermediate representation of RNA degradation; RNA
  degradation is treated as an all-or-nothing event that either proceeds to
  complete with a time step or doesn't progress at all.

  decayRates represents the decay rate of each RNA species in seconds.
  decayRates is informed by experimentally measured RNA half lifes organized
  in the knowledge base, and fit by simulation.fitConstants. decayReactions
  represents the metabolites required to decay each RNA species, and the
  metabolic byproducts of the decay of each RNA species. decayReactions is
  computed by the knowledge RNA classes based on the sequence, processing, and
  modifications of each RNA species.

  Initialization
  ===============
  All RNAs are initialized to the mature state. This is accomplished by the
  simulation class initializeState method.

  Simulation
  ===============
  This process models RNA decay as an enyzme-dependent poisson process with
  rate parameter:
    lambda = RNAs .* decayRates * stepSizeSec

  Algorithm
  +++++++++++++++
  1. Stochastically select RNAs to decay based on poission distribution with
     lambda = RNAs .* decayRates * stepSizeSec
  2. (Ignore limits to decay posed by availability of metabolite reactants
     since the only reactant is water, and water is abundantly available)
  3. Limit RNA decay by available enzyme activity
     a. All RNAs require ribonuclease R to decay
     b. Additionally, only decay aminoacylated tRNAs up to the limit of
        available peptidyl tRNA hydrolase activity.
  4. Update counts of RNAs
  5. Update counts of metabolic byproducts of RNA decay

Author: Markus Covert, mcovert@stanford.edu
Author: Jayodita Sanghvi, jayodita@stanford.edu
Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 7/30/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Transcript.*`, `Metabolite.*`, `Rna.*`, `Rna.counts`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_083_MONOMER`, `MG_104_MONOMER`
- Key parameters with values:
- `mRNA   4.5 +/- 2.0`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? degradation is treated as an all-or-nothing event that either proceeds to
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? `Simulation.fitConstants`, `Simulation.initializeState`

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
