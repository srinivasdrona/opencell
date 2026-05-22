# Karr Process - Replication

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/Replication.m`
**WholeCellModelID:** `Process_Replication`
**Karr functional area:** DNA-replication-and-maintenance
**OpenCell fixture:** `data/karr_fixtures/per_process/Replication_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
Replication

@wholeCellModelID Process_Replication
@name             Replication
@description
  Biology
  =================
  DNA replication by replisomes is initiated by DnaA complex formation near
  the oriC and proceeds bidirectionally from oriC to terC in the 5'->3'
  direction along leading strand as well as in Okazaki fragments in the 5'->3'
  direction along lagging strands. This process models the locations, kinetics,
  and biochemistry of all the replication proteins:
  - replicative DNA helicase
  - DNA primase
  - DNA polymerase core
  - Beta-clamp loading complex / gamma complex
  - Beta-clamp
  - DNA ligase
  - single stranded binding proteins

  The exact mechanism replication initiation in M. genitalium is unknown.
  Furthermore, because M. genitalium does not contain a DnaC homolog it is
  difficult to infer M. genitalium repliciation initiation from studies of
  other bacterial species.

  Knowledge Base
  =================
  The knowledge base contains data curated from the literature and databases:
  - the chromosome DNA sequence
  - the DNA footprints of all replication proteins
  - DNA binding protein displacement reactions (that is which proteins can
    displace which other proteins from the chromosome)
  - values of various structural and kinetic parameters
  - subunit composition of the replication proteins

  Representation
  =================
  The properties substrates, enzymes, and boundEnzymes represent the counts of
  free metabolites, free replication proteins, and chromosally-bound
  replication proteins. The chromosomes property polymerizedRegions represents
  the regions of the chromosomes which have been polymerized (and the
  base-pairing of strands). The chromosomes property strandBreaks represents
  strand breaks 5' to each base. The chromosomes property complexBoundSites
  represents represents the specific chromosomal location of all chromosomally
  bound proteins.

  Spatial Model
  +++++++++++++++++
  - Helicase is centered on the boundary between ssDNA and dsDNA. The position
    over which it is centered is the next position to be melted.
  - Polymerase core is centered on the boundary between ssDNA and dsDNA. The
    position over which it is centered is the next position to be polymerized.
  - There is no gap between the helicase and polymerase core or between the
    polymerase core and the beta clamp.
  - Backup beta clamps bind slightly upstream of the start site of Okazaki
    fragments such that there will be no gap between the polymerase and beta
    clamp, and the polymerase core will be centered on the Okazaki fragment
    start site
  - At replication initiation a the mother strands are separated such that the
    leading polymerase cores are centered at oriC+-1 and the helicases are
    slightly (11 nt) ahead
  - During replication initiation (and the final step of replication after the
    last Okazaki fragment has completed) the lagging polymerase and primase
    are accounted for as part of a complex on the leading strand (containing
    also the helicase, leading polymerase, gamma complex, and leading beta
    clamp). At all other times, the lagging polymerase, lagging beta clamp,
    and primase are accounted for as a complex on a different strand. This
    allows us to separately keep track of the leading and lagging polymerase
    positions.
  - Backup beta clamps can't binding until half of the previous Okazaki
    fragment has been polymerized
  - In general there will be approximately 1 Okazaki fragment length gap
    between the progess of DNA polymerase on the leading and lagging strands

  Initialization
  =================
  The mother chromosome is initialized by the Chromosome class and
  several processes:
  - completely synthesized
  - mother strands base pairing
  - undamged, except methylated at restriction/modification sites (DNA repair
    process)
  - bound by various proteins
    - SMCs (DNA condensation)
    - RNA polymerase (Transcription)
    - Transcription factors (Transcriptional regulation)
    - Topoisomerases (supercoiling)
    - DnaA (replication initiation)

  Simulation
  =================
  The simulation consists of 8 subfunctions executed in a random order:
  - Initiate replication (initiateReplication)
    If DnaA complex assembled at OriC and sufficient protein and metabolites,
    unwind small segment of DNA and binding helicase, primase, polymerase,
    gamma complex, and beta clamp to chromosomes. Associate all proteins with
    the leading strand. Chromosome will take care of dissassembly of the
    DnaA complex. ReplicationInitiation will take care of dissociating the
    released DnaA-ATP polymers.

  - Advance replisomes: unwind and polymerize DNA, release SSBs (unwindAndPolymerizeDNA)
    1. If first Okazaki fragment starting, associate primase, lagging polymerase
       with lagging strand.
    2. Advance leading and lagging polymerases and helicases up to limits
       1. Polymerase and primase kinetics
       2. Available dNTP for polymerization and energy for unwinding
       3. Prevent leading strand progressing if no SSBs bound to lagging
          strand
       4. Accessibility of upstream regions to helicase and polymerases
       5. Don't polymerize leading strand past terC or lagging strands past
          ends of Okazaki fragments
       6. Don't allow the leading strand and helicase to go way beyond the
          lagging strand progress.
       7. Pause progress is RNA polymerase is encountered.
          If the replication loop (helicase) hits an RNAP, polymerization
          pauses, the RNAP falls off, and its transcript is degraded. If it's
          a head-on collision, the replication loop will not proceed for some
          unknown amount of time (a fittable parameter). If it's a codirec-
          tional collision, polymerization will continue at full speed the
          following time step. (Mirkin 2004, Mirkin 2006, Mirkin 2007).
          If occupied by RNA-polymerase, then calculate "occupied DNA" by base
          polymerase is currently on -9 through +2. (Neidhardt 1990).

  - Bind SSBs (freeAndBindSSBs)
    Bind free SSB 4mers to stochastically to deterministically selected
    positions within single-stranded regions as SSB 8mers

  - Dissociate free SSB 8mers into 2 SSB 4mers (dissociateFreeSSBComplexes)
    Dissociate released SSB 8mers into 2 SSB 4mers

  - Initiate Okazaki fragment by bind beta-clamp (initiateOkazakiFragment)
    Binding beta-clamp just downstream of the start position of the next
    Okazaki fragment. Requires that
    - There is beta-clamp monomer to form new beta-clamp dimer on chromosome
    - There is energy for the gamma-complex to form the new beta-clamp
    - The position is accessible to the beta-clamp
    - The leading helicase has already passed the position
    - The lagging strand is at least 1/2 done with the current Okazaki
      fragment

  - Terminate Okazaki fragment by releasing beta-clamp (terminateOkazakiFragment)
    Release beta-clamp and associate lagging primase and polymerase with
    backup beta-clamp (or if terminating the last Okazaki fragment,
    associate the lagging primase and with the leading strand machinery).
    Mark end of Okazaki fragment as having a single strand break to be ligated
    by ligase.
    Occurs if:
    - Okazaki fragment finished polymerizing
    - SSBs bound to lagging strand
    - Lagging backup beta-clamp bound
    - Leading machinery has advanced beyond the Okazaki fragment start site

  - Terminate replication (terminateReplication)
    Release bound replisomes from leading strands. Mark terC as having single
    strand breaks to be ligated by ligase. Occurs if:
    - Polymerization completed for both leading and lagging strands
    - Lagging strand ligated (except for last ligation at terC which will
      occur after the execution of this subfunction)

  - Ligate DNA (ligateDNA)
    Stochastically ligate single strand breaks up to
    - Ligase kinetics
    - Ligase availability
    - NAD availability

  References
  =================
  1. Mirkin, E.V., Mirkin, S.M. (2007). Replication fork stalling at natural
     impediments. Microbiology and molecular biology reviews 71: 13-35.
  2. Mirkin, E.V., Mirkin, S.M. (2005). Mechanisms of
     Transcription-replication collisions in bacteria. molecular and cellular
     biology 25: 888-895.
  3. Mirkin, E.V., Roa, D.C., Nudler, E., Mirkin, S.M. (2006). Transcription
     regulatory elements are punctuation marks for dna replication. PNAS 103:
     7276-7281.
  4. Miyata, M. "Cell Division". Molecular biology and pathogenicity of
     mycoplasmas. Razin, S., Herrmann, R. Kluwer Academic/Plenum Publishers,
     2002. 117-130.
  5. Rudolph, C.J., Dhillon, P., Moore, T., Lloyd, R.G. (2007). Avoiding and
     resolving conflicts between DNA replication and transcription. DNA Repair
     6: 981-993.
  6. McGlynn, P., Guy, C.P. (2008). Replication forks blocked by protein-DNA
     complexes have limited stability in vitro. J. Mol. Biol. 381: 249-255.
  7. Kozlov AG and Lohman TM. (2002). Kinetic Mechanism
     of Direct Transfer of Escherichia coli SSB Tetramers between
     Single-Stranded DNA Molecules. Biochemistry. 41 (39): 11611-11627.
     [PUB_0856]
  8. Kunzelmann S, Morris C, Chavda AP, Eccleston JF, Webb MR (2010).
     Mechanism of Interaction between Single-Stranded DNA Binding Protein
     and DNA. Biochemistry 49(5): 843-52. [PUB_0857]
  9. Roy R, Kozlov AG, Lohman TM, Ha T (2009). SSB protein diffusion on
     single-stranded DNA stimulates RecA filament formation. Nature.
     461(7267):1092-7. [PUB_0858]

Author: Jayodita Sanghvi, jayodita@stanford.edu
Author: Jonathan Karr, jkarr@stanford.edu
Author: Jared Jacobs, jmjacobs@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 8/19/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Chromosome.*`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_001_DIMER`, `MG_001_MONOMER`, `MG_091_OCTAMER`, `MG_091_TETRAMER`, `MG_094_HEXAMER`, `MG_250_MONOMER`, `MG_254_MONOMER`
- Key parameters with values:
- Not explicitly quantified in the header beyond symbolic algorithm expressions.
- Any algorithm subtlety that an implementer would miss reading only the @description summary? The simulation consists of 8 subfunctions executed in a random order:
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? No companion `.m` file is explicitly named in the header.

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
