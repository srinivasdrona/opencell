# Karr Process - ProteinActivation

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinActivation.m`
**WholeCellModelID:** `Process_ProteinActivation`
**Karr functional area:** protein-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/ProteinActivation_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
Protein Activation

@wholeCellModelID Process_ProteinActivation
@name             Protein Activation
@description
  Biology
  ================================
  The activity of proteins and other macromolecules can be modulated by other
  molecules such as free metabolites (and pseudo metabolites we've represented
  as stimuli) both at the enzymatically active site, and at more distant
  allosteric sites. This regulation helps proteins, and thereby the cell,
  respond to changes in the internal and external environments, and maintain
  homeostasis. From a network perspective, this regulation can give rise
  to positive and negative feedback loops.

  This process models protein regulation by transitioning proteins between
  enzymatically active (simulation properties matureMonomers and
  matureComplexs) and inactive states (simulation properties inactiveMonomers
  and inactiveComplexs) according to boolean regulatory rules built from the
  primary literature. Regulatory rules are evaluated independently for each
  compartment. Proteins for which we have not implemented a regulatory
  rule are assumed to always remain in the enyzmatically active state.

  Knowledge Base
  ================================
  As of 8/9/2010 the M. genitalium knowledge base includes regulatory rules
  for six proteins:
  - MG_085_HEXAMER  HPr(Ser) kinase/phosphatase
  - MG_101_MONOMER  Uncharacterized HTH-type transcriptional regulator
  - MG_127_MONOMER  Spx subfamily protein
  - MG_205_DIMER    heat-inducible transcription repressor HrcA, putative
  - MG_236_MONOMER  ferric uptake repressor
  - MG_409_DIMER    phosphate transport system regulatory protein PhoU,
                    putative

  Boolean activation rule syntax
  ++++++++++++++++++++++++++++++++
  - Boolean activation rules must evaluate to true or false where true
    indicates that the protein species is active, and false indicates
    the protein species is inactive. That is protein species are
    activated/inactivated in an all-or-nothing fashion for each
    compartment.
  - Using Whole Cell Model IDs boolean rules can contain references to
    counts/concentrations of several kinds of objects:
    - stimuli                    count                (simulation.stimuli)
    - metabolites                concentration (mM)   (simulation.metabolites)
    - mature protein monomers    concentration (mM)   (simulation.matureIndexs)
    - mature protein complexes   concentration (mM)   (simulation.matureComplexIndexs)
    That is, Whole Cell Model IDs of knowledge base objects contained
    within boolean rules will replaced by the current value or
    concentration in mM of the corresponding knowledge base object before
    evaluation of the boolean rule
  - Boolean activation rules permit the operators: |, &, +, -, !, <, >, <=, >=, ==
  - Boolean activation rules permit parenthesis for grouping
  - Boolean activation rules permit spaces

  Examples
  - objectID1 > val1
  - objectID1 <= val1
  - objectID1 == val1 | objectID2>conc2
  - objectID1 == val1 | !(objectID2>conc2 & objectID3<=conc3 & (objectID4+object5)<conc5)

  Representation
  ================================
  The substrates and inactivatedSubstrates properties represent the counts of
  enzymatically active proteins in each compartment (all of the compartments
  in the simulation are separately mapped to this process). stimuli represents
  the  values of external perturbations and pseudo free metabolites
  (simulation property stimuli), free metabolites, and macromolecules which
  affect the activity of the proteins.

  activationRules represents the boolean regulatory rules governing each of
  the proteins in substrates. The activation rule for each protein is
  evaluated independently for each compartment. Boolean rules are transcoded
  to MATLAB syntax from the syntax described above during initializeConstants.
  Boolean rules are evaluated using the MATLAB eval command in a workspace
  where variables having the names of whole cell model ids of the stimuli are
  defined and set to the value/concentration of the corresponding stimulus.

  Initialization
  ================================
  The same boolean regulatory rules that are evaluated during the simulation
  are evaluated during initialization. Proteins for which their regulatory
  rule evaluates to false are initialized to the inactive state
  (inactivatedSubstrates); proteins for which their regulatory rule evaluates to
  true are initialized to the active state (substrates). This is achieved by
  calling the evolveState method.

  Simulation
  ================================
  For each compartment
    1. Use scaleComponents to compute the concentrations of objects (except
       stimuli objects) mapped to the process's stimuli property.
    2. Assign to local variables named with the stimuli Whole Cell Model IDs
       values equal that of the corresponding object (for stimuli objects) or
       the concentration (for all other objects) of the corresponding object
       computed in (1).
    3. Evaluate boolean regulatory rule of each protein using the MATLAB eval
       command.
    4. Update substrates and inactivatedSubstrates properties based on (3).
       Proteins whose boolean regulation rule evaluates to false are
       transitioned from substrates to inactivatedSubstrates. Proteins whose
       boolean regulation rule evaluates to true undergo the opposite
       transition.
  End

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 8/9/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `CellGeometry.*`, `monomer.counts`, `complex.counts`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_085_HEXAMER`, `MG_101_MONOMER`, `MG_127_MONOMER`, `MG_205_DIMER`, `MG_236_MONOMER`, `MG_409_DIMER`
- Key parameters with values:
- `- objectID1 <= val1`
- `- objectID1 == val1 | objectID2>conc2`
- `- objectID1 == val1 | !(objectID2>conc2 & objectID3<=conc3 & (objectID4+object5)<conc5)`
- `4. Update substrates and inactivatedSubstrates properties based on (3).`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? rule are assumed to always remain in the enyzmatically active state.
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? No companion `.m` file is explicitly named in the header.

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
