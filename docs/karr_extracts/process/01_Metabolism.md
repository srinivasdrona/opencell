# Karr Process - Metabolism

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Metabolism.m`
**WholeCellModelID:** `Process_Metabolism`
**Karr functional area:** transport-and-metabolism
**OpenCell fixture:** `data/karr_fixtures/per_process/Metabolism_flat.mat`
**OpenCell status (per karr_execution_plan §2):** DONE-v1

---

## Verbatim docstring extract

```
Metabolism

@wholeCellModelID Process_Metabolism
@name             Metabolism
@description
  Biology
  ===============
  To grow and replicate cells must uptake or produce their building blocks and
  intermediate energy stores, particularly nucleic and amino acids and lipids,
  as well as secrete metabolites such as modified nucleic acids which it
  cannot catabolize and extract usable material or energy from. Furthermore,
  the import/synthesis and export/breakdown of metabolites must be carefully
  matched to the metabolic demands of the cell to ensure that cellular
  processes aren't limited by too few metabolites or poisoned by too many
  metabolites.

  This process simulates
  - the uptake of nutrients from the external environment
  - the processing of imported nutrients to intermediate energy forms (ATP,
    GTP) and macromolecule building blocks (dNTPs, NTPs, and amino acids)
  - the assembly of lipids, their insertion into the membrane, and their
    maturation within the membrane
  - the catabolism of byproducts of macromolecule assembly and degradation
  - the export to the external environment of uncatabolizable chemicals such
    as modified nucleobases

  Knowledge Base
  ===============
  M. genitalium metabolism was reconstructed from a variety of sources,
  including flux-balance analysis metabolic models of other bacterial species
  and the reaction kinetics database SABIO-RK, and was organized into 641
  reactions in the knowledge base. These reactions are loaded into this process
  by the initializeConstants method.

     Object       No.
     ==========   ===
     substrates   580
     enzymes      100
     reactions    641
       chemical   433
       transport  208

  Representation
  ===============
  The properties substrates and enzymes represent the counts of metabolites
  and metabolic enzymes.

  fbaReactionStoichiometryMatrix represents the stoichiometry and compartments
  of metabolites and biomass in each of the 641 chemical/transport reactions,
  exchange pseudoreactions, and biomass production pseudoreaction.
  fbaReactionCatalysisMatrix represents the enzyme which catalyzes each
  reaction. fbaEnzymeBounds represents the foward and backward kcat of the
  catalyzing enzyme of each reaction. fbaReactionBounds represents the maximal
  import and export rates of each  metabolite. fbaObjective indicates which
  reaction represents the biomass production pseudoreaction. fbaRightHandSide
  is a vector of zeros representing the change in concentration over time of
  each metabolite and biomass. metabolismProduction is redundant with the
  biomass production reaction in fbaReactionStoichiometryMatrix.
  metabolismProduction is calculated by summing the metabolic demands of all
  the other processes over the entire cell cycle. The table below lists the
  units of several properties of this process.

     Property                       Units
     ===========================    ==============================
     fbaEnzymeBounds                molecules/enzyme/s
     fbaReactionBounds              molecules/(gram dry biomass)/s
     metabolites                    molecules
     enzymes                        molecules
     stepSizeSec                    s
     lowerBounds                    reactions/s
     upperBounds                    reactions/s
     growth                         cell/s
     biomassComposition             molecules/cell
     metabolismProduction           molecules/cell
     chamberVolume                  L
     setValues                      molecules/chamber
     growthAssociatedMaintanence

  Initialization
  ===============
  The simulation is initialized with 1 cell weight of macromolecules and
  water, and few free metabolites by the simulation class' initializeState
  method. In addition this process is initialized to a positive growth rate of
  approximately log(2)/cellCycleLength computing using the flux-balance
  analysis model implemented in evolveState.

  Simulation
  ===============
  Transport and metabolism are modeled using the constraint-based method
  flux-balance analysis (FBA). Briefly, FBA assumes that bacteria have evolved
  to maximize growth, and poses transport and metabolism as the optimization
  of cellular building block and energy production subject to available
  nutrients, and allowed chemical reactions. FBA models are typically
  constrained by experimentally measured transport and diffusion rates. In
  addition to these constraints, we constrain constrain our FBA process by our
  model's predicted enzyme abundances, and by experimentally measured kinetic
  parameters. These additional constraints yield a more accurate model of
  transport and metabolism. Furthermore, we use our other processes to obtain a
  more extensive and accurate metabolic objective than used in earlier FBA
  models. The optimization problem specific by FBA is posed as a linear
  optimization problem, and solving using one of several publically available
  linear programming packages.

  Algorithm
  ++++++++++++++++
  1. Compute reaction bounds based on
    - enzyme kinetics,
    - enzyme availability
    - maximal metabolite exchange rates
    - external metabolite availability
    - protein availability
  2. Computes optimal reaction fluxes which maximize biomass production
  3. Computes integer-valued production of biomass components, and export of
     byproducts
  4. Updates amounts of biomass components and byproducts

  References
  ===============
  1. Orth JD, Thiele I, Palsson BO (2010). What is flux balance analysis?
     Nat Biotechnol. 28(3):245-8 [PUB_0687].
  2. Thiele I, Palsson BO (2010). A protocol for generating a
     high-quality genome-scale metabolic reconstruction. Nat Protoc.
     5(1): 93-121. [PUB_0686].
  3. Covert MW, Xiao N, Chen TJ, Karr JR (2008). Integrating metabolic,
     transcriptional regulatory and signal transduction models in
     Escherichia coli. Bioinformatics. 24(18):2044-50. [PUB_0684].
  4. Covert MW, Knight EM, Reed JL, Herrgard MJ, Palsson BO (2004).
     Integrating high-throughput and computational data elucidates
     bacterial networks. Nature. 429 (6987): 92-6. [PUB_0618].
  5. Covert MW, Palsson BO (2003). Constraints-based models: regulation
     of gene expression reduces the steady-state solution space. J Theor
     Biol. 221(3): 309-25. [PUB_0685].

Author: Jonathan Karr, jkarr@stanford.edu
Author: Markus Covert, mcovert@stanford.edu
Author: Jayodita Sanghvi, jayodita@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 3/22/2011
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Mass.*`, `MetabolicReaction.*`, `Time.*`, `Stimulus.*`, `Metabolite.*`, `CellMass.*`, `CellGeometry.*`, `Rna.*`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: None explicitly named in header.
- Key parameters with values:
- `substrates   580`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? To grow and replicate cells must uptake or produce their building blocks and
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? `Simulation.initializeState`

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
