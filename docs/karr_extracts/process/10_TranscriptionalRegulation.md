# Karr Process - TranscriptionalRegulation

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/TranscriptionalRegulation.m`
**WholeCellModelID:** `Process_TranscriptionalRegulation`
**Karr functional area:** RNA-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/TranscriptionalRegulation_flat.mat`
**OpenCell status (per karr_execution_plan §2):** L1-green

---

## Verbatim docstring extract

```
Transcriptional Regulation

@wholeCellModelID Process_TranscriptionalRegulation
@name             Transcriptional Regulation
@description
  Biology
  ==============
  The the rate of transcription of each transcription unit is known to be
  regulated by proteins referred to as transcription factors which modulate
  the affinity of the RNA polymerase for each promoter. Transcription factors
  can both positively and negatively modulate RNA polymerase - promoter
  affinity. Transcription factors can stabilize RNA polymerase - promoter
  complexes by contributing additional negative free energy to the complex by
  providing an additional surface for the RNA polymerase binding.
  Transcription factors can destabilize RNA polymerase - promoter complexes
  for example by sterically blocking promoters and preventing the RNA
  polymerase from binding promoters.

  This process simulates the binding of transcription factors to the promoters
  of each transcription unit (affinity), as well as the affect of the
  transcription factors on the recruiment of the RNA polymerase to each
  promoter (activity). The process was built using experimentally observed fold
  change expression effect of each transcription factor on each promoter.

  Affinity
  ++++++++++++++
  Binds enzymes to promoters assuming:
  1) Transcription factors have high affinity for promoters
  2) Transcription factors bind promoters rapidly
  3) Transcription factors bind promoters stably over time
  4) Only 1 copy of a transcription factor can bind each promoter
  5) Transcription factors only compete within their species for
     promoters. That is for each transcription unit we assume each
     transcription factor species binds a distinct promoters region.

  Consequently, at each time step we simulate that each free
  transcription factor binds randomly binds unoccupied promoters (no copy
  of that transcription factor is already bound to the promoter). Random
  transcription factor-promoter binding is weighted by the affinity of
  each transcription factor for each promoter.

  Because transcription factor-promoter affinities are generally not
  experimentally observed, we base them on the transcription factor fold
  change activities.

  Activity
  ++++++++++++++
  The effect of bound transcription factors on the recruitment of RNA
  polymerase and the expression of transcription units is simulated here
  and incorporated into the calculation of the RNA polymerase
  transcription unit promoter binding probabilities in the transcription
  process. Specifically, the wild-type average RNA polymerase
  transcription unit promoter binding probabilities are multiplied by the
  binding probability fold change effects simulated in this process.

  The RNA polymerase binding probability fold change is simulated for
  each promoter as the product of the observed expression fold change
  effects of each bound transcription factor. When a promoter is bound by
  a single transcription factor, the net RNA polymerase binding
  probability fold change is the observed expression fold change of that
  transcription factor. When a promoter is bound by multiple
  transcription units, the net RNA polymerase binding probability fold
  change is given by the product of the individual fold change effects of
  the bound transcription factors.

  Knowledge Base
  ==============
  The list of transcriptional regulatory relationships is maintained in the
  the knowledge base. As of 8/10/2010, it contained 31 such relationships
  between 5 transcription factors and 29 transcription units containing 37
  genes. The knowledge base was built from a variety of literature sources
  and databases including:
  - PUB_0096
  - PUB_0110
  - PUB_0112
  - PUB_0196
  - PUB_0418-20
  - PUB_0433-8
  - PUB_0505

  Initialization
  =================
  Because we assume that transcription factors have high affinity for DNA and
  bind DNA stably, we initialize as many transcription factors as possible to
  the promoter-bound state. We randomly assign transcription factors to
  promoters using their relative affinities.

  Simulation
  ==============
  For each kind of transcription factor, bind any free transcription factors
  to promoters that aren't already occupied by this kind of transcription
  factor. Choose the binding sites randomly, weighted by the transcription
  factor's affinity to them.

  References
  ==============
  1) Lacramioara Bintu and Nicolas E Buchler and Hernan G Garcia and
     Ulrich Gerland and Terence Hwa, Jane Kondev and Rob Phillips (2005).
     Transcriptional regulation by the numbers: models. Curr Opin Genet
     Dev. 15:116-24.
  2) Lacramioara Bintu and Nicolas E Buchler and Hernan G Garcia and
     Ulrich Gerland and Terence Hwa, Jane Kondev and Rob Phillips (2005).
     Transcriptional regulation by the numbers: applications. Curr Opin
     Genet Dev. 15:125-35.

Author: Jonathan Karr, jkarr@stanford.edu
Author: Jared Jacobs, jmjacobs@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 10/19/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `RNAPolymerase.*`, `Chromosome.*`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_101_MONOMER`, `MG_127_MONOMER`, `MG_205_DIMER`, `MG_236_MONOMER`, `MG_428_DIMER`
- Key parameters with values:
- Not explicitly quantified in the header beyond symbolic algorithm expressions.
- Any algorithm subtlety that an implementer would miss reading only the @description summary? transcription factor binds randomly binds unoccupied promoters (no copy
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? No companion `.m` file is explicitly named in the header.

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
