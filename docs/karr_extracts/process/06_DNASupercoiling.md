# Karr Process - DNASupercoiling

**Source file:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/DNASupercoiling.m`
**WholeCellModelID:** `Process_DNASupercoiling`
**Karr functional area:** DNA-replication-and-maintenance
**OpenCell fixture:** `data/karr_fixtures/per_process/DNASupercoiling_flat.mat`
**OpenCell status (per karr_execution_plan §2):** NOT-STARTED

---

## Verbatim docstring extract

```
DNASupercoiling

@wholeCellModelID Process_DNASupercoiling
@name             DNA Supercoiling
@description
  Biology
  ===========
  DNA gyrase and topoisomerase IV each use 2 ATP to induce 2
  negative
  supercoils each time they act. Occasionally, topoisomerase IV can also
  induce positive supercoils but that is not considered in our model.
  Topoisomerase I acts to induce positive supercoils. Gyrase, topoisomerase
  IV, and topoisomerase I act at rates of 1.2, 2.5, and 1 strand passing
  events per second respectively.

  We use a calculation of the DNA's linking number (LK) in order to track
  the supercoiling of the DNA.  The &delta;LK is the difference between the
  current level of DNA supercoiling and the relaxed level of DNA
  supercoiling. The LKrelaxed is defined as number of base pairs/10.5, in which
  10.5 is the number of bases per turn in a relaxed double helix. As the
  replication loops move, the LKcurrent deviates from this relaxed state,
  and gyrases and topoisomerases help bring the DNA back to the relaxed
  state. The superhelical density, or specific linking number density,
  &sigma;<sub>sp</sub>, is defined as the:
     (LKcurrent - LKrelaxed)/LKrelaxed. 
  The activity of gyrases and topoisomerases depends on the &sigma;<sub>sp</sub>
  of the DNA. Although there is likely a more complex relationship between the
  DNA supercoiling and enzyme activity, we model the enzyme activity as a
  combination of step functions and logistic functions. 
  Topoisomerase IV can only act if &sigma;<sub>sp</sub> is
  higher than 0. Topoisomerase I can only act if &sigma;<sub>sp</sub> is lower
  than zero. Gyrase can only act if &sigma;<sub>sp</sub> is higher than -0.1.
  Within, the regions where gyrase and topoI are allowed to act, we apply
  a logistic function describing the probability of activity, centered
  around equilibrium sigma, -0.06. For TopoI, the probability of activity
  approaches 1 as the sigma gets more positive. For gyrase, the
  probability of activity approaches 1 as
  
  We model up to three regions on the chromosomes and track their LKs
  separately. Before replication, "unreplicated DNA" is the only region
  present. The enzymes may act on the chromosome affecting the LKcurrent,
  and experimentally it has been shown that the enzymes would obtain an
  LKcurrent such that the steady state &sigma;<sub>sp</sub> is =-0.06. As the
  replication loop progresses, "unreplicated DNA" is the region downstream of
  the two replication loops.  The number of bases in this region decreases
  during replication, meaning that the LKrelaxed decreases. The LKcurrent then,
  is too high, and must be brought down towards the LKrelaxed by inducing
  negative supercoils.
  
  The second and third regions are the replicated DNA upstream of the
  replication loops on each of the two chromosomes. As new uncoiled DNA is
  formed, it is already coiled, but gyrases and topoisomerases can continue
  to act on this DNA, ideally maintaining the steady state &sigma;<sub>sp</sub>.
  After replication is complete, these two regions are the only two that exist.
  
  It is essential that the &detlta;LK in the region downstream of the replication
  loops be brought down to 0 by the end of replication.
  
  Another consideration is the processivity of the enzymes when bound to the
  DNA. Topoisomerase IV is highly processive and will stay bound to the DNA
  as long as the &sigma;<sub>sp</sub> is greater than zero. Topoisomerase I is
  not highly processive, and essentially acts on the DNA and falls back off
  right away gyrase will stay bound to the DNA for about 30-60 seconds. We model
  gyrase processivity as a poisson distribution with &lambda; = 45 seconds.
  
  In this process, we go through all free gyrases and topoisomerases in
  random order,  determine what regions they can bind in, and randomly bind
  them to a large enough open position on the DNA. We adjust the linking
  number based on all enzyme actions, and account for the usage of ATP. We
  also track the processivity of gyrase and topoisomerase IV, and unbind
  them from the DNA when appropriate.
  
  If replication is in progress, we first knock off any enzymes that the
  replication loop collides into.

  There is an effect of supercoiling on the probabilities of gene 
  transcription (Peter 2004). While fold change at differnt sigmas have
  been calculated for many E. coli genes, here, for simplicity, we are
  only including the effects on the 5 supercoiling genes: gyrB, gyrA,
  parC, parE, and topA. These genes exist in 3 transcription units. Peter
  2004 has data for the fold change of expression of each of these genes
  are various values of sigma (ranging from sigma -0.06-0.02) at various 
  experimental conditions. Due to the limited data and large variation within
  the data, we have decided to use a linear fit of the fold change data and 
  extrapolate the linear fit within the sigma range of -0.08 to 0.07 where 
  the linear fit seems reasonable. Outside of this range, we estimate a
  constant fold change of expression. While there is a separate set of
  data for each of the 5 genes, our model requires a single probability
  of transcription for each transcription unit. The data for the first
  gene in each transcription unit is used (gyrB, and parE). TopA is
  transcribed with genes that are not supercoiling related. The
  expression of those genes (MG_119, 120, 121) will also get affected by 
  this process. The general trend is that gyrase and topoIV will have an
  increased expression when sigma is higher than the equilibrium, and
  that topoI will have a higher expression when sigma is lower than the
  equilibrium. Fold changes for gyrase will vary between 0.14 and 6.57.
  Fold changes for topoIV will vary between 0.98 and 1.14. Fold changes
  for topoI will vary between 0.042 and 1.15. 
  
  References
  ===============
  1. Ullsperger, C., Cozzarelli, N.R. (1996). Contrasting enzymatic activities
     of topoisomerase IV and DnA gyrase from Escherichia coli. Journal of Bio
     Chem 271: 31549-31555. [PUB_0236]
  2. Dekker, N.H., Viard, T., Bouthier de la Tour, C., Duguet, M., Bensimon,
     D., Croquette, V. (2003). Thermophilic Topoisomerase I on a single DNA
     molecule. Journal of molecular biology 329: 271-282. [PUB_0502]
  3. Gore, J., Bryant, Z., Stone, M.D., Nollmann, M., Cozzarelli, N.R.,
     Bustamante, C. (2006). Mechanochemical analysis of DNA gyrase using rotor
     bead tracking. Nature 439: 100-104. [PUB_0751]
  4. Bates, A. (2006). DNA Topoisomerases: Single Gyrase Caught in the Act.
     Current Biology 16: 204-206. [PUB_0752]
  5. Peng, H., Marians, K.J. (1995). The Interaction of Escherichia coli
     Topoisomerase IV with DNA. Journal of Biological Chemistry 42:
     2528625290. [PUB_0694]
  6. Wang, J. (1996) DNA Topoisomerases. Annual Reviews 65: 635-692. [PUB_0693]
  7. Peter, B.J., Arsuaga, J., Breier, A.M., Khodursky, A.B., Brown,
     P.O., Cozzarelli, N.R. (2004) Genomic transcriptional response to loss
     of chromosomal supercoiling in Escherichia coli. Genome Biology 5:
     1-13. [PUB_0920]

Author: Jayodita Sanghvi, jayodita@stanford.edu
Author: Jared Jacobs, jmjacobs@stanford.edu
Author: Jonathan Karr, jkarr@stanford.edu
Affilitation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 11/18/2010
```

---

## OpenCell mapping notes (post-extract)

- Algorithm complexity (rough): **complex**. Header describes a multi-stage constrained/stochastic algorithm with several coupled steps.
- Inputs required (state variables read): `RNAPolymerase.*`, `Rna.*`
- Outputs produced (state variables written): Not explicitly enumerated in `copyToState`; base `Process` substrate/enzyme synchronization applies.
- Catalysts/enzymes referenced by MG_id: `MG_122_MONOMER`
- Key parameters with values:
- `IV, and topoisomerase I act at rates of 1.2, 2.5, and 1 strand passing`
- `around equilibrium sigma, -0.06. For TopoI, the probability of activity`
- `probability of activity approaches 1 as`
- `LKcurrent such that the steady state &sigma;<sub>sp</sub> is =-0.06. As the`
- `gyrase processivity as a poisson distribution with &lambda; = 45 seconds.`
- `data for each of the 5 genes, our model requires a single probability`
- Any algorithm subtlety that an implementer would miss reading only the @description summary? We use a calculation of the DNA's linking number (LK) in order to track
- Cross-reference: does the docstring mention companion `.m` files (e.g., utility classes, helper kinetics)? No companion `.m` file is explicitly named in the header.

---

## Verification

- [x] Source `.m` file exists at the cited path
- [x] Verbatim section preserves all `%`-prefixed content from the top comment block
- [x] OpenCell fixture path verified to exist
- [x] Process is in the 28-process list per karr_execution_plan §3
