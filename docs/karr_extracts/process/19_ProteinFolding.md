# Karr Process - ProteinFolding

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinFolding.m`
**WholeCellModelID:** `Process_ProteinFolding`
**Karr functional area:** protein-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/ProteinFolding_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
Protein Folding

@wholeCellModelID Process_ProteinFolding
@name             Protein Folding
@description
  Biology
  ==============
  Protein folding is the process whereby proteins which are produced as linear
  amino acid polymers relax to their most energetically favorable, and often
  more compact and catalytically active configuration. Some proteins relax
  quickly and spontaneously to their free energy minimum, while other proteins
  require chaperones to help them achieve their folded configuration more
  quickly. Additionally, some proteins coordinate prosthetic groups such as
  metal ions and other small molecules during this protein rearrangement
  process. Prosthetic groups may help stabilize the protein's catalytically
  active configuration, or may perform folding process.

  In addition to protein chaperones, membrane protein folding may be assisted
  by phosphatidyl ethanolamine (PE) and phosphatidyl glycerol (PG) [PUB_0646].
  This effect is not currently modeled by this process.

  This process simulates
  1. Prosthetic group complexation
     - Inorganic ions: Fe2, Fe3, K, Mg, Mn, Na, Zn
  2. Protein folding, where required mediated by ATP-dependent chaperone(s)
     [PUB_0014, PUB_0644]:
     a. Trigger factor (Tig, MG_238_MONOMER)  Highly expressed protein which
        possibly interacts with the L23 subunit of every ribosome,
        co-translationally assisting in the early folding every protein
        [PUB_0014, PUB_0644]. Binds vacant ribosomes with half-life of 11 s
        [PUB_0005]; binds ribosome-peptide complexes with half-life of 15-50 s
        [PUB_0005]; remains associated with the peptide for a up to more
        seconds after peptide release from the ribosome [PUB_0005]. Trigger
        factor-50S ribosome affinity: KD=1 ?M [PUB_0005]. We model trigger as
        required for the proper folding of all proteins.
     b. Chaperone (DnaK, MG_305_MONOMER)  Folds 5-18% of proteins [PUB_0014,
        PUB_0644]. Typically folds proteins > 30 kDa, typically in less than 2
        min [PUB_0014, PUB_0644]. Binds backbone of short, linear, unfolded,
        hydrophobic peptide segments [PUB_0014, PUB_0644]. ATP hydrolysis and
        peptide release catalyzed by GrpE (MG_201_DIMER) [PUB_0014, PUB_0644].
        Regulated by co-chaperone DnaJ (MG_019_DIMER) which interacts with the
        peptide side chains [PUB_0014, PUB_0644].
     c. Chaperonin (GroEL, GroES, MG_392_393_21MER)  Folds 10-15% proteins by
        ATP-dependent mechanism [PUB_0014, PUB_0644]. Typically folds proteins
        20-60 kDa in size [PUB_0014, PUB_0644] with half-life > 10 min
        [PUB_0014, PUB_0644], 30-60 s [PUB_0389].

  Knowledge Base
  ==============
  The chaperones (except Tig, which all protein monomers require) and
  prosthetic groups required to fold each protein were reconstructed from the
  literature (see following sections), organized into the knowledge base, and
  are retrieved from the knowledge base in initializeConstants. Where known
  the stoichiometry of each prosthetic group was stored in the knowledge base;
  prosthetic groups with unreported stoichiometry are indicated with
  stoichiometry values of -1.

  Chaperones
  ++++++++++++++
  The chaperone requirements for the folding of each protein were compiled
  for other bacteria (see sources below), and mapped to M. genitalium by
  homology.

      Tig    may interact with all nascent peptides at the ribosome
             polypeptide exit site [PUB_0005, PUB_0009, PUB_0388] and assist
             in early folding. Binds vacant ribosomes with half-life of 11 s
             [PUB_0005]; binds ribosome-peptide complexes with half-life of
             15-50 s [PUB_0005]; remains associated with the peptide for a
             up to more seconds after peptide release from the ribosome
             [PUB_0005]. Trigger factor-50S ribosome affinity: KD=1 ?M
             [PUB_0005]. We model trigger as required for the proper folding
             of all proteins.
      DnaK   Deuerling et al performed a proteome-scale search for DnaK
             substrates in E. coli [PUB_0388]
      GroEL  Kerner et al performed a proteome-scale search for GroEL
             substrates in E. coli [PUB_0389] and Endo and Kurusu performed
             a proteome-scale search for GroEL substrates in B. subtilis
             [PUB_0391]
      FtsH   may act as molecule chaperone for membrane proteins
             [PUB_0014]. Several other functions have also been associated
             with FtsH. To date no proteome-scale studies of FtsH activity
             has been performed, and FtsH's chaperone substrates are not
             well characterized. Conequently we chose not to model FtsH as
             a molecular chaperone, but rather a protease.

  Substrates of SecB, a molecular chaperone not present in M. genitalium, have
  also been identified on proteome-scale in E. coli [PUB_0390].

  The reconstruction found that complexes typically require no chaperones to
  fold, with the notable exception of MG_392_393_21MER (which itself is a
  chaperone), which requires four.

  Prosthetic groups
  ++++++++++++++
  Reaction coenzymes and prosthetic groups were reconstructed from several
  sources including the databases BioCyc [PUB_0006], BRENDA [PUB_0570],
  GenoBase [PUB_0386], Kinetikon [PUB_0571], Metal-MaCiE [PUB_0387], and
  UniProt [PUB_0096] and the primary literature [PUB_0131]. These sources
  frequently report protein prosthetic groups as a list of chemical species
  (eg. metal ions) which can each fill the same prosthetic group role. We
  simplified these ambiguous lists of possible prosthetic groups to a single
  chemical species by choosing the most common chemical species according to
  cell composition (Na+, K+ > Mg2+, Cl- > Fe2+, Fe3+ > Ca2+ > Mn2+ > Cu2+ >
  Mo6+, Zn2, Co2, Ni2 [PUB_0393, PUB_0394, PUB_0395]), or the species with the
  highest protein affinity (Irving-Williams Series, Mn2+ < Fe2+, Fe3+ < Co2+ <
  Ni2+ < Cu2+ > Zn2+ [PUB_0404]).

  Roughly 20% of the monomers and 1% of the complexes bind at least one
  prosthetic group.

  Representation
  ==============
  substrates, enzymes, unfoldedMonomers, unfoldedComplexs, foldedMonomers, and
  foldedComplexs represent the counts of free metabolites, chaperones,
  unfolded protein monomers, unfolded protein complexes, folded protein
  monomers, and folded protein complexes. Each of these component types have
  been mapped from the several compartments of the simulation class to one
  pseudo compartment in this process. That is this process only "sees" the
  counts of metabolites, chaperones, and protein monomers and complexes that
  are relevant to protein folding. The process contains no intermediate
  representation of protein folding, that is protein folding is simulated as a
  all-or-nothing process that either does not occur or proceeds to completion
  within a single time step.

  The proteinChaperoneMatrix and proteinProstheticGroupMatrix are adjacency
  matrices which represent the chaperone and prosthetic groups each protein
  monomer and complex requires to achieve its catalytically active
  configuration. Where the stoichiometry of a prosthetic group is unknown and
  indicated in the knowledge base with the value -1, here we assume a
  stoichiometry of 1 and set the element of proteinProstheticGroupMatrix
  accordingly.

  Initialization
  ==============
  All protein monomers and complexes are initialized to the mature state. This
  is accomplished by the simulation class initializeState method.

  Simulation
  ==============
  As with the other protein maturation processes, protein folding is modeled as
  as all-or-nothing process at the single time-step level. A protein only
  proceeds through this phase if its chaperones (if any) and any prosthetic
  group ions are all present in the same time step. Chaperone kinetics are not
  well characterized, and are not currrently modeled. Proteins that require
  neither prosthetic groups nor chaperones are considered folded after one
  time step.

  Algorithm
  ++++++++++++++
  While(true)
    1. Calculate numbers of proteins that can fold based on prosthetic group,
       chaperone, and unfolded protein availability.
    2. Randomly select proteins to fold weighted by limits calculated in step
       (1).
    3. Update counts of prosthetic groups, chaperones, and unfolded and folded
       proteins.
    4. Repeat until insufficient resources to further fold proteins
  End

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 1/4/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Metabolite.*`, `monomer.counts`, `complex.counts`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_019_DIMER`, `MG_201_DIMER`, `MG_238_MONOMER`, `MG_305_MONOMER`
- Key parameters with values:
- `factor-50S ribosome affinity: KD=1 ?M [PUB_0005]. We model trigger as`
- `[PUB_0005]. Trigger factor-50S ribosome affinity: KD=1 ?M`
- `substrates in E. coli [PUB_0388]`
- `substrates in E. coli [PUB_0389] and Endo and Kurusu performed`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? all-or-nothing process that either does not occur or proceeds to completion
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? `Simulation.initializeState`

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
