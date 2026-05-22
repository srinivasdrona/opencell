# Karr Process - ReplicationInitiation

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ReplicationInitiation.m`
**WholeCellModelID:** `Process_ReplicationInitiation`
**Karr functional area:** DNA-replication-and-maintenance
**OpenCell fixture:** `data/karr_fixtures/per_process/ReplicationInitiation_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
ReplicationInitiation

@wholeCellModelID Process_ReplicationInitiation
@name             ReplicationInitiation
@description
  Biology
  =======================================
  Chromosomal replication begins with the formation of large DnaA-ATP
  polymers, totaling approximately 30 DnaA molecues, at several sites denoted
  R1-5 near the OriC. This process simulates the binding and unbinding of
  DnaA-ATP and DnaA-ADP to these and 2000 additional sites throughout the
  chromosome throughout the cell cycle. Although binding occurs throughout the
  cell cycle, due to the cell's limited amount of DnaA, the titration affects
  of the additional 2000 sites, and the cooperativity of DnaA polymerization
  at the OriC sites, DnaA complexation formation at the OriC only occurs
  approximately 2/3 through the cell cycle, providing robust control of
  replication initiation.

  DnaA Boxes (Mycoplasma genitalium)
  =======================================
  All the DnaA box positions based on the M. genitalium motif described in
  Cordova 2002. 
  - 9mer sites (high affinity) are the exact matches of the motif (and reverse
    complement). 
  - 8mer sites (medium affinity) are matches of the motif (and reverse
    complement) with 1 incorrect base. 

  We assume that in the oriC, 5 boxes are present: one 9mer, three
  8mers, and one 7mer, to mimic E. coli's R1-R4, R5. These boxes should reside
  between MG_469 and MG_470 (bases: 578581-579224). There are 9 (8-9mer) boxes
  in this region, but we only recognize 4, so we ignore the boxes at positions
  578837, 578855, 578881, 578966, and 579139.

  R5 is a 7mer, so it is a very weak binder of DnaA. Essentially it is only
  bound by cooperativity given the presence of the initiator complex. Since we
  do not know its exact mechanism/purpose we say it just binds after the
  complex is formed, and its binding triggers initiation.

  Knowledge Base
  =======================================
  The DnaA boxes are represented in the knowledge base as genomic features and
  loaded into this class by the initializeConstants method. The knowledge base
  also contains the footprint sizes of the DnaA complexes; these are used by
  the chromosomes object to determine whether DnaA complexes can bind to
  specific chromosomal regions.

  Representation
  =======================================
  The substrates, enzymes, and boundEnzymes properties represent the counts of
  free metabolites, free DnaA, and DnaA bound to the chromosome. The
  complexBoundSites property of the chromosomes object represent the specific
  chromosomal locations of bound DnaA. The ATP/ADP bound and polymerization
  status of each bound DnaA molecule is indicated by the specific identity of
  the bound DnaA complex (DnaA-ATP 1-7 mer; DnaA-ADP + DnaA-ATP 0-6 mer).   

  Initialization
  =======================================
  The process is initialized to a steady state by the initializeState method.
  The steady state (amounts of free, 8mer/9mer bound DnaA-AxP) is found using
  non-linear constrained optimization where we try to identify a state which
  is a stable point and which maximizes the amount of 9-mer bound ATP. In the
  initializeState method we make the simplifications that there is no free
  DnaA (all DnaA is ATP or ADP bound) and that there are no DnaA polymers at
  the functional R1-4 OriC boxes.

  Simulation
  =======================================
  This process follows the general ideas in Atlas et al. 2008. The process
  consists of several subfunctions executed in a deterministic order:
  - Activate free DnaA to DnaA-ATP (activateFreeDnaA)
    Deterministically form DnaA-ATP complexes upto the limit of available DnaA
    monomers and ATP. The kinetics of DnaA activation are not known, and are
    not modeled.
  - Dissociate free DnaA-ATP polymers into monomers and hydrolyze ATPs (inactivateFreeDnaAATP)
  - polymerized DnaA-ATP (polymerizeDnaAATP)
    If chromosomes are supercoiled, stochastically polymerize R1-4 DnaA boxes
    (which are bound by DnaA-ATP monomers/polymers (of up to length 6)) by 1
    additional DnaA-ATP molecule at rate
      kbATP * numFreeDnaAATP / V * C
    where C is a cooperativity constant which depends on the polymerization
    status of the other R1-4 boxes
  - polymerized DnaA-ADP (polymerizeDnaAADP)
    Similar to DnaA-ATP polymerization, but with slower kinetic rate, kbADP
  - Bind DnaA-ATP (bindDnaAATP)
    Stochastically bind DnaA-ATP to free DnaA boxes at rate
      kbATP * numFreeDnaAATP / V
  - Bind DnaA-ADP (bindDnaAADP)
    Similar to DnaA-ATP binding, but with slower kinetic rate, kbADP
  - Stochastically release bound DnaA-ATP with uniform probability (releaseDnaAAxP)
    Stochastically release bound DnaA-ATP monomers, and stochastically
    depolymerize R1-4 boxes (except those which have polymer lengths equal to
    the minimum of that over the R1-4 boxes) at rate kd1ATP.
  - Stochastically release bound DnaA-ADP with uniform probability (releaseDnaAAxP)
    Stochastically release bound DnaA-ADP monomers, and stochastically
    depolymerize R1-4 boxes at rate kd1ADP.
  - Reactivate free DnaA from free DnaA-ADPs (reactivateFreeDnaAADP)
    Deterministically reactivate free DnaA-ATP from free DnaA-ATP a rate
       numFreeDnaAADP * (k_Regen * membraneConc) /
                      (K_Regen_P4 + membraneConc)

  Replication-dependent bound DnaA-ATP inactivation is modeled differently
  here than by Atlas et al 2008. Atlas et, 2008 included a global term for the
  effect of active beta-clamps on bound DnaA-ATP inactivation. Because this
  model is evaluated as part of a larger model and in particular the exact
  position of active beta-clamps are known, we are able to model the local
  affects of beta-clamps on bound DnaA-ATP, which is to release the bound
  protein from DNA. However, because we cannot distinguish free DnaA-ATP from
  DnaA-ATP released by beta-clamps we only model the release of these proteins
  from the DNA, and not their hydrolysis to DnaA-ADP.

  References
  =======================================
  1. Atlas, J.C., Nikolaev, E.V., Browning, S.T., Shuler, M.L. (2008).
     Incorporating genome-wide DNA sequence information into a dynamic
     whole-cell model of E. coli: application to DNA replication. Systems
     Biology, IET 2: 369-382.
  2. Browning, S.T., Castellanos, M., Shuler, M.L. (2004). Robust control of
     Initiation of prokaryotic chromosome replication: essential considerations
     for a minimal cell. Biotechnology and Bioengineering 88: 575-584.
     All rate constants are from Browning (2004).
  3. Cordova, C.M.M., Lartigue, C., Sirand-Pugnet, P., Renaudin, J., Cunha,
     R.A.F., Blanchard, A. (2002). Identification of the origin of replication
     of the Mycoplasma pulmonis chromosome and its use in oriC replicative
     plasmids. Journal of Bacteriology 184: 5426-5435.
  4. Margulies, C., Kaguni, J.M. (1996). Ordered and sequential binding of DnaA
     protein to oriC, the chromosomal origin of escherichia coli. Journal of
     biological chemistry 271: 17035-17040.

Author: Jayodita Sanghvi, jayodita@stanford.edu
Author: Jonathan Karr, jkarr@stanford.edu
Author: Jared Jacobs, jmjacobs@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 8/10/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Mass.*`, `CellMass.*`, `CellGeometry.*`, `Chromosome.*`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_469_MONOMER`
- Key parameters with values:
- `the minimum of that over the R1-4 boxes) at rate kd1ATP.`
- `depolymerize R1-4 boxes at rate kd1ADP.`
- `All rate constants are from Browning (2004).`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? non-linear constrained optimization where we try to identify a state which
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? `Simulation.initializeState`

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
