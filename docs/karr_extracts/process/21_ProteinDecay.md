# Karr Process - ProteinDecay

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinDecay.m`
**WholeCellModelID:** `Process_ProteinDecay`
**Karr functional area:** protein-synthesis-and-maturation
**OpenCell fixture:** `data/karr_fixtures/per_process/ProteinDecay_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
Protein Decay

@wholeCellModelID Process_ProteinDecay
@name             Protein Decay
@description
  Biology
  ===========
  Poisson simulation of protein damage, repair, and decay mediated by
  - chaperone: clpB chaperone refolds/disaggregates proteins by an
    energy-dependent mechanism
  - proteases: lon, ftsH; each is believed to processively cleave
    peptides into smaller peptides of approximately 20 amino acids
    - ftsH: cleaves peptides with tmRNA stalled translation proteolysis
      tag; parameterized by
      - fragment length (aa)
      - kinetic rate (cleaves/s)
      - energy per cleavage (ATP/cleavage)
    - lon: cleaves all other peptides; parameterized by
      - fragment length (aa)
      - kinetic rate (cleaves/s)
      - energy per cleavage (ATP/cleavage)
  - several peptidases: the specific functions and kinetics of the
    individual peptidases are unknown and not modelled; decay proceeds as
    long as at least one of each peptidase is present

1. Misfold proteins
   - Protein misfolding is modeled as a poisson process
     with a small rate constant
2. Refold cytosolic proteins
   - Occurs if clpB is present
3. Decay macromolecular complexes
   - Model decay is poisson process with rate parameter given by the
     inverse weighted average half life of the complex's subunits
   - Salvage bound prosthetic groups
   - Mark subunits as damaged to be degraded by either the
     protease/peptidase or ribonuclease machinery
4. Decay protein monomers and proteolysis tagged polypeptides
   - Model selection of monomers that decay as poisson process with rate
     parameters equal to the decay rates (ln(2)/half life as computed by
     the N-end rule) of the monomers.
   - Execute decay reactions as long as the following are available
     - Lon/FtsH protease for normal / ribosome-stalled peptides
     - Complete peptidase complement
     - Water for hydrolysis of peptide bonds

  Knowledge Base
  ===============
  The knowledge base contains implements the N-end rule which predicts the
  half life of every protein monomer based on the average experimentally
  measured (in E. coli) protein half lives for each possible N-terminal amino
  acid. Exceptions:
  - signal sequences are assumed to have 0 half life
  - proteolysis tagged polypeptides are assumed to have 0 half life

  The knowledge base predicts the half lives of complexes as the weighted mean
  of that of their constituent protein monomers and RNAs.

  The knowledge base ProteinMonomer and ProteinComplex classes also computes
  hydrolytic degradation reactions of every protein monomer and complex:
  - the (modified) amino acids released by hydrolytic cleavage of every
    protein monomer
  - water required for hydrolytic peptide bond cleavage
  - prosthetic groups released by cleavage

  The ProteinMonomer class is also used to compute hydrolytic degradation
  reactions for proteolysis tagged polypeptides.

  Representation
  ===============
  The substrates, enzymes, monomers, RNAs, and complexs properties represent
  the counts of metabolites, proteases and peptidases, protein monomers,
  damaged RNAs, protein complexes. The substrates and enzymes properties have
  only 1 compartment (cytosol). The monomers, RNAs, and complexs properties
  have 5 compartments. The monomers and complexs properties represent all
  forms of proteins (nascent, mature, damaged, folded, misfolded, etc.)

  abortedSequences represents the sequences of every proteolysis tagged
  monomer in the cytosol.

  The process contains intermediate representation of protein complex
  degradation, but not of protein monomer degradation, misfolding, or
  refolding. Degrading complexes are broken up into the constituent RNAs and
  monomers, and these components are marked as "damaged" and recognized by RNA
  and protein monomer degradation as molecules with 0 half life. Protein
  monomer degradation is treated as an all-or-nothing event that either
  proceeds to complete with a time step or doesn't progress at all.

  proteinMisfoldingRate represents the rate at which every protein misfolds in
  seconds.

  monomerDecayRates and complexDecayRates represent the decay rate of each
  protein monomer and complex species in seconds. misfolded and damaged
  proteins, signal sequences, and proteolysis tagged polypeptides have 0 half
  lives. All other proteins have positive half lives.

  monomerDecayReactions and complexDecayReactions represent the metabolites
  required and released by hydrolytic cleavage of protein monomers and the
  break down of macromolecular complexes into their constituent subunits and
  sequestered prosthetic groups. monomerDecayReactions and
  complexDecayReactions are computed by the knowledge base ProteinMonomer and
  ProteinComplex classes.

  Initialization
  ===============
  All protein monomers and complexs are initialized to the mature state. This
  is accomplished by the simulation class initializeState method.

  Simulation
  ===============
  This process models misfolding, refolding, and protein monomer and complex
  degradation as an enyzme-dependent (excepct misfolding) poisson processes
  with rate parameter:
     lambda = proteins .* decayRates * stepSizeSec

  Algorithm
  +++++++++++++++
  Each of misfolding, refolding, protein complex degradation, proteolysis
  tagged monomer degradation, and protein monomer degradation use a variant of
  the algorithm:

  1. Stochastically select proteins to misfold/refolding/degrade based on
     poission distribution with
        lambda = proteins .* rates * stepSizeSec
  2. Limit refolding/degradation by availability of water and energy
  3. Limit protein refolding/degradation by available enzyme activity
     a. Refolding requires ClpB
     b. Protein monomer degradation requires Lon protease and 6 peptidases
     c. Proteolysis tagged polypeptide degradation requires FtsH protease and
        6 peptidases
  4. Update counts of proteins
  5. Update counts of metabolic reactants and byproducts of protein
     refolding/degradation

  Compartments
  +++++++++++++++
  - Misfolding: occurs in all compartments
  - Refolding: occurs only in compartments where ClpB is present, that is the
    cytosol (and terminal organelle cytosol)
  - Complex degradation: occurs only in compartments where the protein decay
    machinery (Lon protease and peptidases) are presents, that is the cytosol
    (and terminal organelle cytosol)
  - Proteolysis tagged polypeptide degradation: only exist in cytosol, and are
    only degraded their (assumes they are accessible from within the cytosol
    to the integral membrane FtsH protease)
  - Protein monomer degradation:  occurs only in compartments where the Lon
    protease and peptidases are present, that is the cytosol.

Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 8/4/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `Polypeptide.*`, `Metabolite.*`, `Rna.*`, `monomer.counts`, `complex.counts`, `Rna.counts`
- Outputs produced (state variables written): `monomer.counts`, `complex.counts`
- Catalysts/enzymes referenced by MG_id: `MG_020_MONOMER`, `MG_046_DIMER`, `MG_183_MONOMER`, `MG_208_DIMER`, `MG_239_HEXAMER`, `MG_324_MONOMER`, `MG_355_HEXAMER`, `MG_391_HEXAMER`, `MG_457_HEXAMER`
- Key parameters with values:
- `parameters equal to the decay rates (ln(2)/half life as computed by`
- `- signal sequences are assumed to have 0 half life`
- `- proteolysis tagged polypeptides are assumed to have 0 half life`
- `and protein monomer degradation as molecules with 0 half life. Protein`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? monomer degradation is treated as an all-or-nothing event that either
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? `Simulation.initializeState`

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
