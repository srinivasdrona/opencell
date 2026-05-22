# Karr Process - Transcription

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Transcription.m`
**WholeCellModelID:** `Process_Transcription`
**Karr functional area:** RNA-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/Transcription_flat.mat`
**OpenCell status (per karr_execution_plan §2):** DONE-v1

---

## Verbatim docstring extract

```
Transcription

@wholeCellModelID Process_Transcription
@name             Transcription
@description
  Biology
  ===============
  Transcription is the first step in the synthesis of functional gene
  products where RNA polymerase and several accessory enzymes translate
  transcription units, or regions of the DNA containing 1 or more genes, into
  RNA molecules. Following transcription the RNA molecules follow one of
  two pathways:
  - mRNAs are used as templates for translation (see translation process)
  - r/s/tRNAs which are transcribed as molecules containing multiple genes are
    cleavaged into their individual genes (see RNA processing process), are
    modified at several bases (see RNA modification process) to improve their
    stability and enhance their catalytic activity, and finally act as
    ribozymes (r/sRNAs) or as adaptors between mRNAs and the amino acids they
    code for (tRNAs).

  Transcription begins with the recruitment of RNA polymerase to a promoter
  with the help of the sigma initiation factor and possiblity transcription
  factors. Next elongation factors are recruited, RNA begins to be
  polymerized, and sigma factor is released. Finally the RNA polymerase
  reaches  a terminator at the the end of the transcription unit, and
  with the help of termination factors releases the polymerized RNA and
  dissociates from the DNA. Termination in E. coli occurs via either a
  Rho-dependent (50%) or Rho-independent mechanism (50%). Rho-dependent
  termination is catalyzed by the hexameric ATP-dependent helicase Rho.
  Rho is not essential in B. subtilis [PUB_0234]. Rho-independent
  termination occur via the intrinsic properties RNA which disrupt RNA
  polymerase-DNA binding. Terminator hairpins are not predicted in M.
  genitalium. In E. coli termination is incompetition with
  antitermination. However antitermination has not been reported in any
  mcyoplasma [PUB_0182].

  As soon as the RNA begins to polymerized, even prior to termination, the
  mRNA transcripts may be bound by ribosomes and polymerized. For simplicity,
  our model doesn't represent this phenomenon.

  Knowledge Base
  ===============
  The transcription unit structure was compiled from several sources:
  - Primary reports of cotranscribed genes [PUB_0176, PUB_0182, PUB_0186,
    PUB_0188, PUB_0188, PUB_0244, PUB_0247, PUB_0248, PUB_0249, PUB_0251]
  - OperonDB database of cotranscribed genes [PUB_0250]
  - Conservation of gene order across multiple species
  - Related function of adjacent genes
  - Expression levels as measured by microarrays of adjacent genes [PUB_0569]
  - Strandedness of adjacent genes
  - Weiner, Hermann, and Browning computational model of promoters and
    transcription unit start sites [PUB_0411]

  The transcription unit structure is organized in the knowledge base, and is
  loaded into this process by the initializeConstants method.

  The knowledge base also contains the measured expression and half-lives of
  many transcripts. These values are loaded by initializeConstants and fit by
  simulation.fitConstants to be consistent with other processes.

  Representation
  ===============
  substrates, enzymes, boundEnzymes, and RNAs represent the counts of
  metabolites, free transcription enzymes, transcription enzymes bound to RNAs
  and RNA polymerases, and nascent RNAs.

  rnaPolymerases.states represents the current state / pseudostate (actively
  transcribing, specifically bound, non-specifically bound, free,
  non-existent) of each RNA polymerase, where each state is indicated by the
  enumeration:
  - rnaPolymeraseActivelyTranscribingValue
  - rnaPolymeraseSpecificallyBoundValue
  - rnaPolymeraseNonSpecificallyBoundValue
  - rnaPolymeraseFreeValue
  - rnaPolymeraseNotExistValue (state exists as a way to account for memory
    allocated for future RNA polymerases)
  For actively transcribing polymerases rnaPolymerases.states also represents
  the position of the polymerase along the transcription unit.

  That is entries of rnaPolymerases.states with the following values
  corresponding to these states:
    >= RNAPolymerases.activelyTranscribingValue: RNA polymerases position on genome actively transcribing
    == RNAPolymerases.specificallyBoundValue:    RNA polymerase specifically bound
    == RNAPolymerases.nonSpecificallyBoundValue: RNA polymerase non-specifically bound
    == RNAPolymerases.freeValue:                 RNA polymerase free
    == RNAPolymerases.notExistValue:             RNA polymerase doesn't exist

  transcripts.boundTranscriptionUnits represents the particular transcription
  unit to which each actively transcribing and specifically bound polymerase
  is bound.

  rnaPolymeraseStateExpectations represents the expected occupancies of the
  RNA polymerase states.

  transcriptionUnitBindingProbabilities represents the relative affinity of
  RNA polymerases for the promoters of each transcription unit.
  transcriptionFactorBindingProbFoldChange represents the fold change affect of
  transcription factors on the relative affinities of the RNA polymerse for
  the promoters. RNA polymerases are assigned to
  transcription units weighted by the product of
  transcriptionUnitBindingProbabilities and
  transcriptionFactorBindingProbFoldChange.

  Initialization
  ===============
  All RNAs are initialized to the mature state. This is implemented by the
  simulation class initializeState method.

  RNA polymerases are initialized to their steady state:
  - Each RNA polymerase is randomly assigned (with replacement) to one of the
    actively transcribing, specifically bound, non-specifically bound, or free
    states weighted by the expected occupancy of each state
    (rnaPolymeraseStateExpectations)
  - Actively transcribing and specifically bound polymerases randomly assigned
    to transcription units weighted by their transcription rates
    (transcriptionUnitBindingProbabilities)
  - Each transcription unit to which an actively transcribing polymerase has
    been assigned is divided into 1 segment for each polymerase
  - Actively transcribing polymerases randomly assigned to positions within
    the assigned segment of their assigned transcription unit (positions near
    the segment border are not allowed to prevent polymerases from being too
    close to each other) with uniform probably.

  Simulation
  ===============
  Evolves the state of RNA polymerase using a markov chain model with four
  states:
  - actively translating
  - specifically bound
  - non-specifically bound
  - free

  Transition probabilities are designed to maintain the occupancy of each
  state within a narrow window around their expected values. Transition
  probability are determined by four logistic control functions. These can
  be tuned with the constants
  - rnaPolymeraseStateExpectations

  RNA polymerase are created in the free state.

  Actively transcribing state:
  1. Release sigma factor if after first second of elongation
  2. Elongate transcript according to nucleic acid limits (substrates)
     if elongation factors are available
  3. If transcription complete and termination factor available
     - release transcript
     - transition RNA polymerase to free state
     - increment gene expression
     Otherwise remain in active state

  Specifically bound State:
  - Can transition to active, specifically bound, non-specifically bound,
    or free states
  - Transition into state only if a free sigma factor is available
    1. Decrement number of free sigma factors
    2. Pick a transcription unit (tu) to bind to according to
    Expression transcription unit i~prob(ribosome releases tu i|ribosome active)
                     =prob(ribosome within RNA polymerase elongation rate bases of length of tu i|ribosome active)
                     =prob(ribosome within RNA polymerase elongation rate bases of length of tu i|ribosome active, bound to tu i)*prob(ribosome bound to tu i|ribosome active)
                     =[(RNA polymerase transcription rate)/(length of tu i)] * [(length of tu i)*prob(binding tu i|binding)]
    prob(binding tu i | binding)~expression tu i

  Non-specifically bound state:
  - Can transition to specifically bound, non-specifically bound, or free
    states

  Free state:
  - Can transition to specifically bound, non-specifically bound, or free
    states

  Algorithm
  +++++++++++++++
  1. Randomly transition RNA polymerases among activlely transcribing,
     specifically bound, non-specifically, bound, and free states weighted by
     state transition probabilities. Update rnaPolymerases.states.
  2. Randomly assign RNA polymerases entering the specifically bound to
     specific transcription units weighted by the product of
     transcriptionUnitBindingProbabilities and
     transcriptionFactorBindingProbFoldChange. Update
     transcripts.boundTranscriptionUnits.
  3. Assign RNA polymerase entering the actively transcribing state sigma
     factors. Update enzymes and boundEnzymes.
  4. Simulate RNA polymerization by actively transcribing RNA polymerases with
     the aid of elongation factors. Allocate available nucleic acids among the
     actively transcribing RNA polymerases. Release sigma factors from RNA
     polymerases that started at the beginning of the transcription unit and
     progressed. Update rnaPolymerases.states. Update substrates. Update enzymes
     and boundEnzymes.
  5. If termination factors are available dissociate RNA polymerases which
     have reached the terminus of the transcription they're bound to, and
     release RNAs. Update rnaPolymerases.states and
     transcripts.boundTranscriptionUnits. Increment RNAs.

  References
  ===========
  1. McClure, W. R. 1985. Mechanism and control of transcription
     initiation in prokaryotes. Annu. Rev. Biochem. 54:171-204.
     [PUB_0775]
  2. Ciampi MS (2006). Rho-dependent terminators and transcription
     termination. Microbiology. 152(9):2515-28 [PUB_0233].
  3. Nudler E, Gottesman ME (2002). Transcription termination and
     anti-termination in E. coli. Genes Cells. 7(8):755-68. [PUB_0662]
  4. Washio T, Sasayama J, Tomita M (1998). Analysis of complete genomes
     suggests that many prokaryotes do not rely on hairpin formation in
     transcription termination. Nucleic Acids Res. 26(23):5456-63
     [PUB_0234]
  5. Peterson JD, Umayam LA, Dickinson T, Hickey EK, White O (2001). The
     Comprehensive Microbial Resource. Nucleic Acids Res. 29(1):123-5.
     [PUB_0182]
  6. Shepherd N, Dennis P, Bremer H (2001). Cytoplasmic RNA Polymerase in
     Escherichia coli. J Bacteriol. 183(8): 2527-34. [PUB_0784]
  7. Klumpp S, Hwa T (2008). Growth-rate-dependent partitioning of RNA
     polymerases in bacteria. Proc Natl Acad Sci U S A. 105(21):
     20245-50. [PUB_0785]
  8. Grigorova IL, Phleger NJ, Mutalik VK, Gross CA (2006). Insights into
     transcriptional regulation and sigma competition from an equilibrium
     model of RNA polymerase binding to DNA. Proc Natl Acad Sci U S A.
     103(14): 5332-7. [PUB_0786]

Author: Markus Covert, mcovert@stanford.edu
Author: Jayodita Sanghvi, jayodita@stanford.edu
Author: Jonathan Karr, jkarr@stanford.edu
Affiliation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 1/4/2010

TODO: require Mg2+ or Mn2+ as cofactor for transcription
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `RNAPolymerase.*`, `Transcript.*`, `Metabolite.*`, `Rna.*`, `Rna.counts`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_027_MONOMER`, `MG_141_MONOMER`, `MG_249_MONOMER`, `MG_282_MONOMER`
- Key parameters with values:
- `2. Elongate transcript according to nucleic acid limits (substrates)`
- `2. Randomly assign RNA polymerases entering the specifically bound to`
- `7. Klumpp S, Hwa T (2008). Growth-rate-dependent partitioning of RNA`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? - Conservation of gene order across multiple species
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? `Simulation.fitConstants`, `Simulation.initializeState`

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
