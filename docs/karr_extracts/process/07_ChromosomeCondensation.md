# Karr Process - ChromosomeCondensation

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ChromosomeCondensation.m`
**WholeCellModelID:** `Process_ChromosomeCondensation`
**Karr functional area:** DNA-replication-and-maintenance
**OpenCell fixture:** `data/karr_fixtures/per_process/ChromosomeCondensation_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
ChromosomeCondensation

@wholeCellModelID Process_ChromosomeCondensation
@name             Chromosome Condensation
@description
  Biology
  =====================================================================
  Chromosome segregation requires that the DNA be highly compacted.
  Structural maintenance of chromosome (SMC) complexes are "V" shaped
  proteins (with an head and two legs) that induce positive supercoils in
  double stranded DNA (Porter et al., 2004). The complexes are believed to
  work with a lock and key mechanism in which first DNA is looped around
  the legs of the SMC complex, and then an ATP is bound between the two
  tails to lock the SMC complex in place. The complexes bind and clamp the
  DNA causing many loops in the DNA and compacting it. The loops around
  each leg occupy 90bp. A loop of about 450bp forms between the two SMC
  complex legs (Jensen and Shapiro, 2003, Strick and Kawaguchi, 2004).
  Further, it has been inferred that there is about 1 SMC complex per every
  7000bp (Jensen and Shapiro, 2003).

  The initial chromosome is bound by SMC complexes averaging 7000bp spacing.
  As the replication loop proceeds, the SMC complexes that it encounters
  are displaced.  Once the DNA has been replicated, SMC complexes are
  randomly bound to the DNA such that their spacing averages 7000bp. Each
  SMC complex occupies 630bp, and no two SMC complexes can occupy the same
  space. Both the decision of whether an SMC complex will bind at a given
  time point and the binding location are random. SMC complexes do not fall
  off the chromosomes unless due to the force of the replication loop. The
  two chromosomes are tracked separately.

  Knowledge Base
  =====================================================================
  The knowledge base contains the values of the parameters: smcSepNt and
  smcSepProbCenter. The knowledge base also contains the measured DNA
  footprint of each SMC complex. These footprints are loaded by the
  Chromosome class from the knowledge base. This class retrieves the
  footprint from the Chromosome class.

  Representation
  =====================================================================
  substrates, enzymes, and boundEnzymes represent the counts of free
  metabolites, free SMC complexes, and chromosome-bound SMC complexes. The
  chromosomes property represents the specific base positions where the
  chromosome-bound SMC complexes are located.

  enzymeDNAFootprints represents the experimentally measured DNA footprint of each
  SMC complex. smcSepNt represents the experimentally observed average SMC
  complex spacing  [PUB_0517]. smcSepProbCenter is a parameter which controls
  the SMC binding probability transfer function. smcSepProbCenter is not an
  experimentally measured quantity. Rather, its value is pinned by several
  constraints: implemented in the ChromosomeCondensation_Test class
  testCalculateBindingPositionWithinRegion and testInitializeStateConverged
  methods. These constraints are:
  - Consistent with an SMC density of approximately 1/smSepNt
  - Consistent with fast binding of multiple SMCs to large unbound regions
  - Consistent with slow binding of SMCs to small unbound regions

  Algorithm
  =====================================================================
  1. Calculate expected number of SMC complexes that should bind chromosomes
     a. Calculate regions where SMCs can bind (regions either between SMC
        complexes or between SMC complexes and replication bubble)
     b. Compute the expected number of binding complexes as the ratio of the
        sum of the lengths of the regions to the average SMC spacing
  2. For 1 to minimum of free SMC complexs, ATP, and expected number of SMCs
     that that should bind chromosome
     A. Calculate regions where SMCs can bind (regions either between SMC
        complexes or between SMC complexes and replication bubble)
        a. Starting coordinate
        b. Chromosomes
        c. Lengths
        d. Probability of SMC binding each region
     B. Pick a region for SMC complex to bind
     C. Pick a position within region for SMC complex to bind
     D. Form SMC-ADP complex:
        a. Decrement SMC. Increment SMC-ADP
        b. Decrement ATP, H2O. Increment PI, H.
     E. Bind SMC-ADP complex to chromosome
        a. Decrement free SMC-ADP complex
        b. Increment bound SMC-ADP complex

  The probability that an SMC complex binds a region of length L is given by
  the step function
    p(L) = 1/smcSepNt * max(0, L/2-smcSepProbCenter)

  The conditional probability that an SMC complex binds a position within
  region assuming that the SMC complex is binding the region is given by
   p(x) = 1/(L-2*smcSepProbCenter)  if x>smcSepProbCenter and x<L-smcSepProbCenter,
          0                         otherwise

  References
  =====================================================================
  1. Ullsperger, C., Cozzarelli, N.R. (1996). Contrasting enzymatic activities
     of topoisomerase IV and DnA gyrase from Escherichia coli. Journal of Bio
     Chem 271: 31549-31555.
  2. Dekker, N.H., Viard, T., Bouthier de la Tour, C., Duguet, M., Bensimon,
     D., Croquette, V. (2003). Thermophilic Topoisomerase I on a single DNA
     molecule. Journal of molecular biology 329: 271-282.
  3. Gore, J., Bryant, Z., Stone, M.D., Nollmann, M., Cozzarelli, N.R.,
     Bustamante, C. (2006). Mechanochemical analysis of DNA gyrase using rotor
     bead tracking. Nature 439: 100-104.
  4. Bates, A. (2006). DNA Topoisomerases: Single Gyrase Caught in the Act.
     Current Biology 16: 204-206.
  5. Jensen, R.B, Shapiro, L. (2003). Cell-Cycle-Regulated Expression and
     Subcellular Localization of the Caulobacter crescentus SMC Chromosome
     Structural Protein. Journal of Bacteriology 185: 3068-3075. [PUB_0517]
  6. Strick, T.R., Kawaguchi, T. (2004). Real-time detection of single-molecule
     DNA compaction by condensing I. Current biology 14: 874-880.
  7. Tadesse, S., Mascarenhas, J., Kosters, B., Hasilik, A., Graumann, P.L.
     (2005). Genetic interaction of the SMC complex with topoisomerase IV in
     Bacillus subtilis. Microbiology 151: 3729-3737.
  8. Bloom, K., Joglekar, A. (2010). Towards building a chromosome segregation
     machine. Nature 463: 446-456.
  9. Porter, I.M., Khoudoli, G.A., Swedlow, J.R. (2004). Chromosome
     condensation: DNA compaction in real time. Current Biology 14: 554-556.

Author: Jayodita Sanghvi, jayodita@stanford.edu
Author: Jonathan Karr, jkarr@stanford.edu
Author: Jared Jacobs, jmjacobs@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 6/9/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Chromosome.*`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: None explicitly named in header.
- Key parameters with values:
- `p(L) = 1/smcSepNt * max(0, L/2-smcSepProbCenter)`
- `p(x) = 1/(L-2*smcSepProbCenter)  if x>smcSepProbCenter and x<L-smcSepProbCenter,`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? randomly bound to the DNA such that their spacing averages 7000bp. Each
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? No companion `.m` file is explicitly named in the header.

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
