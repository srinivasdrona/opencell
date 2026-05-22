# Karr Architecture - fitConstants

**Primary source:** `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+util/FitConstants.m`

---

## Verbatim extract - class header docstring

```
FitConstants

Introduction
================================================
This class is the last stage in fitting the simulation. The purpose of
this class is to resolve conflicts among the experimental data separately
used to parameterize each of the processes, as well as to calculate the
biomass composition / production used to parameterize the flux-balance
analysis (FBA) metabolic model. Furthermore, the goal of this class is to
resolve these conflicts in a way which keeps the values of the parameters
as close to their experimental observed values as possible.

Fitting workflow
================================================
This class is the last, of several stages, of simulation fitting:
1. Collect parameter values from literature and databases
2. Fit free parameters over individual processes
   - Fit chromosome condensation parameters to recapitulate observed
     average SMC spacing
   - Fit repliciation initiation cooperativity constants to
     recapitulate desired repliciation initiation duration (observed
     cell cycle length - calculated replication duration - simulation
     cytokinesis duration)
3. Fit free parameters over groups of processes
4. Fit dry weight fractions to accomodate a full chromosome
   replicated by the end of the replication phase (which is before the
   end of the cytokinesis phase)
   - Increase DNA dry weight fraction
   - Decrease all other dry weight fractions
5. Fit parameters over entire model. Find set of parameter values
   closest to their experimentally measured values which satisfy
   several joint parameter constraints. Until convergence,
   - Calculate biomass composition, production, and unaccounted enegry
     consumption ("dark enegry")
   - Calculate constraints using chosen geneExpressionRobustness
   - Satisfy constriants heuristically
   - Solve non-linear constrained optimization problem

Remaining unconstrained free parameters
================================================
The fitting work flow identifies and/or adjusts the value of every
parameter in the simulation with 5 exceptions:
- proteinMisfoldingRate
- tmRNABindingProbability
- geneExpressionRobustness
- initialFractionNTPsInRNAs
- initialFractionAAsInMonomers

These are the only truly free parameters across the entire simulation.

Parameter conflict resolution
================================================
In particular, the goal of this class is to resolve conflicts among
several pieces of experimental data, and to do so in a least squares
sense:
- gene expression
- protein expression
- RNA weight fractions
- NMP composition
- AA composition
- gene sequences
- protein sequences
- transcription unit structure
- RNA half lives
- tRNA synthetase, transferase rates
- RNA polymerase elongation rate
- Ribosome elongation rate
- RNA polymerase state expectations
- cell cycle length
- cell cycle phase lengths
- genetic code
- protein complex composition
- enzyme kinetics (enzymeBounds)
- transport rates (reactionBounds)

Stated more formally, the goal of this class is to the identify the set
of gene expression, NMP composition, AA composition, RNA weight
fractions, and RNA decay rates which satisfy several linear and
non-linear constraints and minimze their sum of squares deviation from
their experimentally observed values. Stated mathmetatically,

Minimize
  ||W*(z - experimentalZ)||_2 =
  z'*W*W*z - 2*z'*W*W*experimentalZ + experimentalZ'*W*W*experimentalZ

          (rnaExpression)
Where z = (nmpComposition)
          (aaComposition)
          (rnaWeightFractions)
          (rnaDecayRates)

Subject to:
- normalization                                            ones * rnaExp  = 1
                                                          ones * nmpComp  = 1
                                                           ones * aaComp  = 1
                                                       ones * rnaWtFracs  = 1
- RNA type distribution                                          mRNAExp  = I_mRNA * rnaExp
                                                                 rRNAExp  = I_rRNA * rnaExp
                                                                 sRNAExp  = I_sRNA * rnaExp
                                                                 tRNAExp  = I_tRNA * rnaExp
                                     mRNAMWs * mRNAExp / rnaMWs * rnaExp  = rnaWtFracs(mRNAWtFracIdxs)
                                     rrnaMWs * rRNAExp / rnaMWs * rnaExp  = rnaWtFracs(rRNAWtFracIdxs)
                                     srnaMWs * sRNAExp / rnaMWs * rnaExp  = rnaWtFracs(sRNAWtFracIdxs)
                                     trnaMWs * tRNAExp / rnaMWs * rnaExp  = rnaWtFracs(tRNAWtFracIdxs)
- Monomer expression                                              monExp  = matureRNAGeneComp(mRNAIdxs, :) * rnaExp /
                                                                            (ones * matureRNAGeneComp(mRNAGeneIdxs, :) * rnaExp)
- NMP Composition                rnaBaseCnts * rnaExp / rnaLens * rnaExp  = nmpComp
- AA Composition                   monAACnts * monExp / monLens * monExp  = aaComp
- Doubling lower bounds                                     ribosome exp >= min exp for protein doubling
                                                      RNA polymerase exp >= min exp for RNA doubling
                                                transcription factor exp >= min exp for RNA doubling
                                                  translation factor exp >= min exp for protein doubling
                                                                tRNA exp >= min exp for protein doubling
                                                     tRNA synthetase exp >= min exp for protein doubling
                                                                        ...
- FtsZ expression: held to value used to calculate cytokinesis duration
- DnaA expression: held to value used to fit replication initiation
  duration
- Topoisomerase I / gyrase expression: constrained to produce observed
  steady-state superhelical density

That is we pose the problem as one of non-linear constrianed
optimization, and use the MATLAB fmincon routine to identify the optimal
parameter set, z. Linear constraints are implemented as pairs of
matrices, A, and right-hand sides representing equality and inequality
constriants. Dependent linear constraints are automatically removed.
Non-linear constraints are implemented as class methods, are calculated
in part using the calcResourceRequirements_LifeCycle methods of the
processes through the calcResourceRequirements method of this class.

However, because fmincon has troubling identifying solutions
which satisfy all of the non-linear constraints, before executing fmincon
we first hueristically identify a consistent set of parameter values:
- transcription unit expression <- average expression of genes in
  transcription unit; RNA weight fractions ./ RNA fraction
  molecular weights
- transcription unit decay rate <- average decay rate of genes in
  transcription unit
- NMP composition <- transcription unit sequences *
  transcription unit expression
- AA composition <- protein monomer sequences *
  transcription unit composition(mRNAs, :) * transcription unit
  expression

The initial heuristic procedure modifies RNA expression, NMP and AA
composition, and rRNA half lives. The initial heuristic procedure doesn't
modify RNA weight fractions or m/s/tRNA half lives.

Biomass composition, production calculation
================================================
During, and following fitting we calculated the biomass composition,
production, byproduct secretion, and unaccounted energy consumption. See
documentation above calcResourceRequirements method for units and
normalization conditions. Biomass production - byproducts forms the FBA
objective. Biomass composition is used by to initialize the cell prior to
simulation.

Assumptions
================================================
- uniform protein half lives
- RNA half lives are for free species
- RNA expression includes free and bound RNA species
- bound RNA, protein (eg. by RNA polymerase, DNA) has same half life
  as free RNA, protein

Author: Jonathan Karr, jkarr@stanford.edu
Affiliation: Covert Lab, Department of Bioengineering, Stanford University
Last updated: 3/22/2011
```

## Verbatim extract - `FitConstants.run`

```
function this = run(this)
            %import classes
            import edu.stanford.covert.cell.sim.constant.Condition;
            import edu.stanford.covert.util.ComputationUtil;
            import edu.stanford.covert.util.ConstantUtil;
            
            %references
            sim = this.simulation;
            
            %toggle off warnings
            warningStatus = warning('query', 'WholeCell:warning');
            warning('off', 'WholeCell:warning');
            
            %seed random number generator
            seed = sim.seed;
            stateSeeds = zeros(size(sim.states));
            processSeeds = zeros(size(sim.processes));
            sim.applyOptions('seed', 0);
            sim.seedRandStream();
            for i = 1:numel(sim.states)
                o = sim.states{i};
                stateSeeds(i) = o.seed;
                o.seed = 0;
                o.seedRandStream();
            end
```
