# Karr Process - FtsZPolymerization

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/FtsZPolymerization.m`
**WholeCellModelID:** `Process_FtsZPolymerization`
**Karr functional area:** cytokinesis
**OpenCell fixture:** `data/karr_fixtures/per_process/FtsZPolymerization_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
FtsZPolymerization

@wholeCellModelID Process_FtsZPolymerization
@name             FtsZPolymerization
@description

In the cytosol, FtsZ can exist in one of multiple states: inactivated monomer,
deactivated monomer (GDP bound), activated monomer (GTP bound), nucleated
(dimer of two activated monomers), or elongated (polymer of three or more
activated monomers). FtsZ molecules move between these states at rates
obtained from Chen et al. 2005 and Surovtsev et al. 2008.

The maximum polymer length is a fittable parameter. We currently use 9 (40nm),
the lower end of the range given for E. coli in Anderson 2004.

FtsZ polymerization is modeled using a set of differential equations
modified from that described in Surovtsev et al. 2008, involving the
activation, nucleation, and elongation of FtsZ polymers.
The main modifications were that the equations were simplified to not
include annealing and cyclization of FtsZ polymers.

Solving the equations results in a real-valued distribution of monomers and
filament lengths at each time step. This process discretizes the distribution
at each time step for compatibility with the rest of the simulation.

References
===============
1. Surovtsev, I.V., Morgan, J.J., Lindahl, P.A. (2008). Kinetic Modelling of the
   Assembly, Dynamic Steady State, and Contraction of the FtsZ Ring in
   Prokaryotic Cytokinesis. Plos CB 4: 1-19. [PUB_0164]
2. Chen, Y., Bjornson, K., Redick, S.D., Erickson, H.P. (2005). A rapid
   fluorescence assay for ftsZ assembly indicates cooperative assembly with a
   dimer nucleus. Biophysical journal 88: 505-514. [PUB_0200]
3. Li, Z., Trimble, M.J., Brun, Y.V., Jensen, G.J. (2007). The structure of
   FtsZ filaments in vivo suggests a force-generating role in cell division.
   EMBO 26: 4694-4708. [PUB_0611]
4. Anderson, D.E., Gueiros-Filho, F.J., Erickson, H.P. (2004). Assembly
   Dynamics of FtsZ Rings in Bacillus subtilis and Escherichia coli and
   Effects of FtsZ-Regulating Proteins. Journal of Bacteriology 186:
   5775-5781. [PUB_0217]

Author: Jayodita Sanghvi, jayodita@stanford.edu
Author: Jared Jacobs, jmjacobs@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 9/9/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `CellGeometry.*`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_224_MONOMER`
- Key parameters with values:
- Not explicitly quantified in the header beyond symbolic algorithm expressions.
- Any algorithm subtlety that an implementer would miss reading only the @description summary? No additional subtlety beyond the explicit Representation/Simulation/Algorithm sections in the header.
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? No companion `.m` file is explicitly named in the header.

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
