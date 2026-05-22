# Karr Process - ChromosomeSegregation

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ChromosomeSegregation.m`
**WholeCellModelID:** `Process_ChromosomeSegregation`
**Karr functional area:** DNA-replication-and-maintenance
**OpenCell fixture:** `data/karr_fixtures/per_process/ChromosomeSegregation_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
Chromosome Segregation

@wholeCellModelID Process_ChromosomeSegregation
@name             Chromosome Segregation
@description
  Biology
  ======================
  Chromosome segregation in Mycoplasma genitalium has not been well described.
  Chromosome segregation in M. genitalium is believed to result from two
  factors
  - entropically favorable segregation throughout DNA replication
  - four chromosome segregation proteins which act to decatenate the
    chromosomes following the completion of replication
  Little is known about the times at which these two factors contribute to
  chromosome segregation.

  Bacterial chromosome segregation is believed to be entropically favorable
  and occur during replication (Bloom et al. 2010, Jun et al. 2006). That is,
  its believed to be entropically unfavorable for two chromosomes to be
  located near each other, and so as the replication fork moves, the
  replicated DNA molecules migrate away from each other toward the poles. We
  assume that by the end of replication the chromosomes have already migrated
  toward the poles.

  Four proteins are believed to be involved in chromosome decatenation in M.
  genitalium:
  - MG_470_MONOMER  nucleotide binding domain protein CobQ/CobB/MinD/ParA
  - MG_221_OCTAMER  MraZ
  - MG_387_MONOMER  GTP binding protein Era
  - MG_384_MONOMER  GTPase Obg
  The specific function, kinetics, and metabolic costs of these proteins are
  not known. Furthemore, because M. genitalium contains a reduced complement
  of segregation proteins, it is difficult to infer their functions from
  studies of other bacterial species.

  Knowledge Base
  ======================
  The knowledge base contains the value of the gtpCost parameter.

  Representation
  ======================
  The substrates and enzymes properties represent the counts of available
  metabolites and segregation enzymes. gtpCost represents the energetic
  (GTP) cost of chromosome segregation. The segregation status of the
  chromosomes is represented as a boolean properties (segregated) of the
  Chromosome class.

  Initialization
  ======================
  Chromosome initializes to a state with 1 chromosome (which obviously
  hasn't yet segregated from the second chromosome which will be later
  produced).

  Simulation
  ======================
  Because little is known about the molecular biology of chromosome
  segregation, we have chosen to implement this process as a simple boolean
  rule: chromosome segregation can occur if:
  - the chromosome is replicated
  - the chromosome is properly supercoiled
  - there is at least one free molecule of each segregation proteins, and
  - there is at least gtpCost free GTP molecules

  Note, although the Glass et al. gene essentiality study suggests that the
  cobQ/cobB/minD/parA gene is non-essential, we model this gene as essential
  because we don't know its specific function and how the other segregation
  proteins compensate in its absence.

  References
  ======================
  1. Bloom, K., Joglekar, A. (2010). Towards building a chromosome segregation
     machine. Nature 463: 446-456.
  2. Jun, S., Mulder, B. (2006). Entropy-driven special organization of highly
     confined polymers: Lessons for the bacterial chromosome. PNAS 103:
     12388-12393.
  3. Glass, J.I., Assad-Garcia, N., Alperovich, N., Yooseph, S., Lewis, M.R.,
     Maruf, M., Hutchison III, C.A., Smith, H.O., Venter, J.C. (2006).
     Essential genes of a minimal bacterium. PNAS 103: 425-430.

Author: Jayodita Sanghvi, jayodita@stanford.edu
Author: Jonathan Karr, jkarr@stanford.edu
Author: Jared Jacobs, jmjacobs@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 7/7/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): Not explicitly enumerated in header/code-level bindings.
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_221_OCTAMER`, `MG_384_MONOMER`, `MG_387_MONOMER`, `MG_470_MONOMER`
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
