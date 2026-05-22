# Karr Process - RNAProcessing

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RNAProcessing.m`
**WholeCellModelID:** `Process_RNAProcessing`
**Karr functional area:** RNA-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/RNAProcessing_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
RNAProcessing

@wholeCellModelID Process_RNAProcessing
@name             RNA Processing
@description
  Biology
  ==================
  Transcription produces mono- as well as polycistronic RNAs.
  Following transcription polycistronic rRNA, tRNA, and tmRNA transcripts are
  cleaved, modified, and aminoacylated. First, 45S rRNA transcripts are
  cleaved by ribonuclease III (MG_367_DIMER) into 5S, 16S, and 23S rRNA
  precursors [PUB_0038, PUB_0039]. Next these precursors are cleaved at their
  3' and 5' ends by ribonuclease J and RsgA [PUB_0038]. Similarly the 5' ends
  of each tRNA and tmRNA species are cleaved by ribonuclease P [PUB_0039,
  PUB_0649]. Ribonuclease III also cleaves scRNA at two sites [PUB_0039].
  Second, 13 enzymes formylate, lysidinate, methylate, pseudouridylate, and
  thiolate 86 specific rRNA and tRNA bases. Third 19 tRNA synthetases
  conjugate 19 amino acids to 37 tRNA and tmRNA species, and 2 tRNA
  transferases complete the aminoacylation of the formylmethionine and
  glutamine tRNAs.

  rRNA, tRNA, and tmRNA cleavage, modification, and aminoacylation are modeled
  motivated by mass-action kinetics. First, the maximum rate of maturation of
  each RNA species is calculated based on (1) the abundance of immature
  transcripts, (2) the abundance of substrates and enzymes required to cleave
  or modify each RNA species, and (3) the experimentally measured kinetic rate
  of each enzyme required to cleave or modify each RNA species. Second, RNA
  maturations are randomly selected according to the calculated maximum rates.
  Finally, steps (1) and (2) are repeated until insufficient resources are
  available to mature additional RNAs.

  This process simulates the cleavage of polycistronic r/s/t RNA transcripts
  into individual genes:
  - 30S RNA        -> pre 16/17S RNA, p23S RNA, 9S RNA    RNAseIII (MG_367)
  - pre 16/17S RNA -> 16S RNA                             5' end:rnjA (MG_139); 3' end:rsgA (MG_110)
  - p23S RNA       -> 23S RNA                             5' end:rnjA (MG_139), deaD (MG_425)
  - 9S RNA         ->  5S RNA
  - 3' end tRNA precursors                                RNAseIII (MG_367)
  - 5' end tRNA precursors                                RNaseP (MG_0003, MG_465)
  - scRNA (MG_0001) precusors                             RNAseIII (MG_367)
  - 5' end tmRNA precursors                               RNaseP (MG_0003, MG_465)

  Reactions
  ++++++++++++++++++
  DeaD           phosphorolytic                      3.6.4.13
  RsgA           phosphorolytic                      3.6.5.2, 3.6.1.-
  RNAaseIII      hydrolytic       endoribonuclease   3.1.26.3
  RNAseP         hydrolytic       endoribonuclease   3.1.26.5
  RNAseJ         hydrolytic       endoribonuclease   3.1.27.2

  Cofactors
  ++++++++++++++++++
  DeaD           Mg2+                [PUB_0071]
  RsgA       (1) Zn2+                [PUB_0096]
  RNAaseIII      Mg2+                [PUB_0039]
  RNAseJ     (2) Zn2+                [PUB_0096]
  RNAseP     (3) Mg2+ or (3) Mn2+    [PUB_0012, PUB_0013, PUB_0043]

  Kinetics:
  ++++++++++++++++++
  DeaD       1.48   1/s   B. subtilis  [PUB_0688]
  RsgA       0.2917 1/s   E. coli      [PUB_0103]
  RNAseP     0.027  1/s   B. subtilis  [PUB_0013]
  RNAseP     6      1/s   B. subtilis  [PUB_0690]
  RNAseIII   7.7    1/s   E. coli      [PUB_0691]
  RNAseJ     0.37   1/s   B. subtilis  [PUB_0692]

  Energy-Dependence
  ++++++++++++++++++
  DeaD       2.37  ATP  1/rxn   B. subtilis  [PUB_0069] (210 ATP/min B. subtilis [PUB_0069])/(1.48 rxn/s B. subtilis  [PUB_0688])
  RsgA       1     GTP  1/rxn   E. coli      [PUB_0103]

  Knowledge Base
  ==================
  The transcription unit organization was predicted by mapping the
  experimentally determined genome organization of M. pnemoniae by Gell et al
  [Table S5 "Suboperons", PUB_0418] onto the M. genitalium genome by homology
  with 4 modifications:
  - r/s/tRNAs were organized into transcription units according to their
    "reference operons" (table s4)
  - All mRNAs Gell Serrano et al did not assign to a suboperon because of
    insufficient evidence (low quality expression data), were assigned to
    their own transcription units. None of these mRNAs are located within
    suboperons.
  - All 5 mRNA genes which don't have homologs in M. pneumoniae were assigned
    to their own transcription units. These occur outside other transcription
    units.
  - Genes which have undergone rearrangements between M. pnuemoniae and M.
    genitalium were assigned to their own transcription units

  The promoter (-35 and -10 boxes and TSS) for each transcription unit was set
  predicted for its 3' gene by Weiner et al [PUB_0411].

  The composition of each transcription unit, and the location of its -35 and
  -10 boxes and TSS relative to the start coordinate of the 3' gene was stored
  in the knowledge base, and it used by the TranscriptionUnit and Gene classes
  to compute the sequences of transcription unit, gene, and intergenic
  segment.

  The kinetics and energy requirement of each RNA processing enzyme are
  organized as parameters in the knowledge base. These values were curated
  several papers [PUB_0069, PUB_0103, PUB_0688, PUB_0690, PUB_0691, PUB_0692].

  Representation
  ==================
  substrates and enzymes represent the counts of metabolites and RNA
  processing enzymes. unprocessedRNAs, processedRNAs, and intergenicRNAs
  represent counts of RNAs. unprocessedRNAs represents the counts of nascent
  RNAs produced by the RNA polymerase. processedRNA represents the counts of
  r/s/tRNA precursors produced from cleavage of nascent transcripts, and mRNAs
  that remain joined as transcription units. intergenic RNAs represents the
  counts of RNA segments between r/s/tRNA genes in transcripts that are
  released during the processing of these transcripts.

  enzymeSpecificRate_* are the kcats of the five RNA processing enzymes. We
  assume that each enzyme has the same kcat for all reactions it catalyzes.
  enzymeEnergyCost_* are the amount of ATP required by the phosphorolytic RNA
  processing enzymes (DeaD and Rsga) per cleavage reaction.

  rna.nascentRNAMatureRNAComposition, rna.intergenicRNAMatrix,
  reactantByproductMatrix, and catalysisMatrix are adjacency matrices.
  nascentRNAMatureRNAComposition represents the the processed RNAs that arise
  from each unprocessed RNA (eg. the r/s/t RNAs that arise from transcripts
  containing multiple genes). intergenicRNAMatrix represents the intergenic
  RNA segments that arise from the cleavage of r/s/tRNA transcripts into their
  individual genes. reactantByproductMatrix represents the amounts of
  metabolites required to cleave each polycistronic transcript, and the
  metabolic byproducts of their cleavage. catalysisMatrix represents the
  amount of enzyme required to cleave each polycistronic transcript.

  Initialization
  ==================
  All RNAs are initialized to the mature state. This is accomplished by the
  simulation class initializeState method.

  Simulation
  ==================
  For each RNA class (mRNA, rRNA, sRNA, tRNA) in a random order:
  1. Determine maximum number of RNAs that can be processed based on available
     - RNA processing enzymes and their kinetics
     - free metabolites
     - RNAs that need processing
  2. Randomly select among unprocessed RNAs proportional to count
  3. Update state:
     a. Decrement unprocessed RNAs
     b. Increment processed RNAs, intergenic RNAs
     c. Decrement metabolic reactants
     d. Increment metabolic byproducts%

  References
  ==================
  1. Gell M, van Noort V, Yus E, Chen WH, Leigh-Bell J, Michalodimitrakis K,
     Yamada T, Arumugam M, Doerks T, Khner S, Rode M, Suyama M, Schmidt S,
     Gavin AC, Bork P, Serrano L (2009). Transcriptome complexity in a
     genome-reduced bacterium. Science. 326(5957): 1268-71. [PUB_0418]
  2. Weiner J 3rd, Herrmann R, Browning GF (2000). Transcription in Mycoplasma
     pneumoniae. Nucleic Acids Res. 28: 4488-96. [PUB_0411].
  3. Cordin O, Banroques J, Tanner NK, Linder P (2006). The DEAD-box protein
     family of RNA helicases. Gene. 367: 17-37. [PUB_0069]
  4. Himeno H, Hanawa-Suetsugu K, Kimura T, Takagi K, Sugiyama W, Shirata S,
     Mikami T, Odagiri F, Osanai Y, Watanabe D, Goto S, Kalachnyuk L, Ushida
     C, Muto A (2004). A  novel GTPase activated by the small subunit of
     ribosome. Nucleic Acids Res. 32 (17): 5303-9. [PUB_0103]
  5. Theissen B, Karow AR, Khler J, Gubaev A, Klostermeier D (2008).
     Cooperative binding of ATP and RNA induces a closed conformation in a
     DEAD box RNA helicase. Proc Natl Acad Sci U S A. 105(2): 548-53.
     [PUB_0688]
  6. Xiao S, Scott F, Fierke CA, Engelke DR (2002). Eukaryotic ribonuclease P:
     a plurality of ribonucleoprotein enzymes. Annu Rev Biochem. 71: 165-89.
     [PUB_0690]
  7. Amarasinghe AK, Calin-Jageman I, Harmouch A, Sun W, Nicholson AW (2001).
     Escherichia coli ribonuclease III: affinity purification of
     hexahistidine-tagged enzyme and assays for substrate binding and
     cleavage. Methods Enzymol. 342: 143-58. [PUB_0691]
  8. Niranjanakumari S, Day-Storms JJ, Ahmed M, Hsieh J, Zahler NH, Venters
     RA, Fierke CA (2007). Probing the architecture of the B. subtilis RNase P
     holoenzyme active site by cross-linking and affinity cleavage. RNA.
     13(4): 521-35. [PUB_0692]

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 1/4/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Rna.*`, `Rna.counts`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_110_MONOMER`, `MG_139_DIMER`, `MG_367_DIMER`, `MG_425_DIMER`
- Key parameters with values:
- `thiolate 86 specific rRNA and tRNA bases. Third 19 tRNA synthetases`
- `transcripts, (2) the abundance of substrates and enzymes required to cleave`
- `or modify each RNA species, and (3) the experimentally measured kinetic rate`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? maturations are randomly selected according to the calculated maximum rates.
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? `Simulation.initializeState`

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
