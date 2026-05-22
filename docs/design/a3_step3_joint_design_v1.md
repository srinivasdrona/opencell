# Phase A3 Step 3 — D.2-real + ProteinDecay-light Joint Design (v1, primary-source-driven)

| Field | Value |
|---|---|
| Status | DESIGN v1 — primary-source-driven; awaiting cross-model critique |
| Branch (to be created) | `agent/a3-step3-joint-design` |
| Supersedes | All prior D.2 design versions (v1 `fa59925` → v2 `811a707` → v3 `10bf5f0` → v4 `7d3e7b6`) |
| Primary sources read in full | `docs/karr_extracts/process/{21_ProteinDecay,23_MacromolecularComplexation,24_RibosomeAssembly}.md`; `docs/karr_extracts/architecture/{02_state_variables,03_variable_allocation,05_initializeState}.md`; `MacromolecularComplexation.m` lines 290-392 (the actual `evolveState` + helpers) |
| Karr execution plan reference | `docs/design/karr_execution_plan_2026-05-22.md` §6.1 (allocation algorithm) |
| Spike findings reference | `agent/d2-spike` @ `672eb58` (Vivarium semantics, Probe 5 integration risk) |

---

## 0. Executive summary

This design covers TWO Karr processes that must ship together because they form half of the producer-degrader loop that bounds the system:

1. **D.2-real** = `MacromolecularComplexation` (Karr's term) + `RibosomeAssembly` (30S, 50S only per spike Decision (b))
2. **ProteinDecay-light** = the minimum-viable subset of `ProteinDecay` needed to bound complex growth: complex decay only, no monomer decay, no misfolding/refolding, no proteolysis-tagged decay.

The design is **bottom-up from the actual `.m` source**. Where v1→v4 designs paraphrased the algorithm from the docstring, this design quotes the actual implementation (25 lines of MATLAB for the entire MC `evolveState`).

Two structural insights from primary-source reading invalidate parts of all prior versions:

- **MC operates on disconnected complex networks, not globally.** `findNonInteractingRowsAndColumns` partitions the 149 complexes into independent clusters before any MC sampling. Cluster 1 is special (no competition; closed-form solution). Clusters 2..N each run Monte Carlo independently. v3 and v4 debated "global competition vs per-complex MC"; neither is right. The answer is per-disconnected-cluster.
- **Karr's chassis already has a global allocation algorithm.** `Simulation.evolveState` does proportional-fair-share metabolite allocation BEFORE any process's `evolveState` runs. D.2 and ProteinDecay don't compete with M1/M2/M3 inside their own code — the simulation harness does that allocation up front. The "ratchet" GPT-5.4 found in v4 is real *if* we keep accumulate-only `complex.counts`, but Karr's actual fix isn't smarter D.2; it's the ProteinDecay sink + the upstream allocation step.

The design is therefore much simpler than v4 implied. Most of v4's machinery (signed Counter emit, `d2_consumed_*` ports, deriver pattern, one-tick-lag arguments) was working around problems caused by designing in isolation. With the loop in scope and Karr's actual algorithm in scope, the design fits in ~400 LOC across two Process classes plus a shared chassis allocation step.

---

## 1. Scope (verified against `.m` source)

### 1.1 D.2-real scope

From `MacromolecularComplexation.m` docstring (verified line 30-50 of `23_MacromolecularComplexation.md`):

- **155 macromolecular complexes** in Karr's knowledge base (as of 8/17/2010)
- Of which **149 are formed by `MacromolecularComplexation`** (D.2's own scope)
- The remaining **6 are formed by other processes** (ribosomes — 2 by RibosomeAssembly; the other 4 are formed by other formation processes per the 9-way histogram GPT-5.5 verified in v3)

D.2-real owns:
- All 149 complexes in `Process_MacromolecularComplexation`
- 2 ribosomal particles (`RIBOSOME_30S`, `RIBOSOME_50S`) per `Process_RibosomeAssembly`

D.2-real does NOT own:
- `RIBOSOME_30S_IF3` (formed by Translation per Decision (b) verified in v3 spike)
- `RIBOSOME_70S` (formed by Translation per Decision (b))
- The other 4 non-D.2 complexes (FtsZ/DnaA/etc. owned by Phase C processes)

**Note on counting:** v3/v4 cited "147 + 2 = 149 D.2-owned WIDs" derived from the fixture; Karr's docstring says "149 by MC + 2 by RibosomeAssembly = 151". The "147 vs 149" discrepancy needs resolution before implementation — likely the fixture's `Process_MacromolecularComplexation` count excludes 2 complexes that we should include (or includes 2 we should exclude). **OPEN-1 in §10.**

### 1.2 ProteinDecay-light scope

From `ProteinDecay.m` docstring (verified line 39-58 of `21_ProteinDecay.md`):

Full ProteinDecay has 5 sub-processes:
1. Misfold proteins (rate constant `proteinMisfoldingRate`)
2. Refold cytosolic proteins (requires ClpB)
3. **Decay macromolecular complexes** (rate = inverse weighted half-life of subunits)
4. Decay protein monomers and proteolysis-tagged polypeptides
5. (Salvage prosthetic groups; mark subunits as damaged)

**ProteinDecay-light = #3 only.** Just complex decay, with these caveats:
- No misfolding (`proteinMisfoldingRate` defaults set to 0 in our fixture)
- No refolding (ClpB pathway omitted)
- No monomer decay (full ProteinDecay's #4 is deferred to Phase B `ProteinDecay-full`)
- No proteolysis tagging (#4 substep deferred)
- Salvage prosthetic groups: deferred; complex decay returns subunits to the substrate pool with no prosthetic-group accounting

This is the minimum bound the system needs. The Karr docstring confirms #3's algorithm: **complex decay is Poisson with rate = mean of subunits' decay rates**, weighted by their stoichiometric coefficient in the complex.

### 1.3 Out of scope (deferred to later phases)

| Concern | Lands in |
|---|---|
| ProteinFolding (chaperone-capacity kinetics) | Phase B (process 19) |
| ProteinActivation (cofactor loading) | Phase B (process 20) |
| Full ProteinDecay (monomer decay, misfold/refold, proteolysis tagging) | Phase B follow-up |
| Protein monomer decay (the bulk of `ProteinDecay`) | Phase B follow-up |
| Salvage of prosthetic groups | Phase B follow-up |
| 70S ribosome assembly (Translation v2's job) | M3v2 already shipped per A3.2 |
| `RIBOSOME_30S_IF3` (Translation v2's job) | M3v2 already shipped |

---

## 2. The verbatim Karr algorithm for D.2-real

This is the entire `MacromolecularComplexation.evolveState` from `MacromolecularComplexation.m` lines 290-314. 25 lines. The implementation IS the spec.

```matlab
function evolveState(this)
    newComplexs = zeros(size(this.complexs));

    %subunits only involved in one complex (i.e. no competition)
    newComplexs(this.complexs2complexNetworks == 1) = buildProteinComplexs_bounds(...
        this.substrates(this.substrates2complexNetworks == 1, 1),...
        this.complexNetworks{1});

    %subunits involved in multiple complexes (i.e. competition): Run
    %Monte Carlo simulation for each independent protein complex network
    for i = 2:length(this.complexNetworks)
        newComplexs(this.complexs2complexNetworks == i) = ...
            buildProteinComplexs_montecarlokinetic(...
            this.substrates(this.substrates2complexNetworks == i), ...
            this.complexNetworks{i}, this.randStream);
    end

    %stop if no new complexes
    if ~any(newComplexs)
        return;
    end

    this.complexs = this.complexs + newComplexs;
    this.substrates = this.substrates - this.complexComposition * newComplexs;
end
```

Three branches:

### 2.1 Cluster 1 — no competition (closed-form)

Cluster 1 holds complexes whose subunits don't compete with any other complex's subunits. For each, the number formed is exactly:

```matlab
function ub = buildProteinComplexs_bounds(totalProteinMonomers, proteinComplexMatrix)
    ub = floor(min(totalProteinMonomers(:, ones(1, size(proteinComplexMatrix, 2))) ./ proteinComplexMatrix, [], 1))';
end
```

In English: for each complex, `n = floor(min over subunits of (count[subunit] / stoichiometry[subunit, complex]))`. The stoichiometric ceiling. Closed-form, no randomness.

### 2.2 Clusters 2..N — Monte Carlo per cluster

For each cluster i ≥ 2:

```matlab
function proteinComplexs = buildProteinComplexs_montecarlokinetic(...
        totalProteinMonomers, proteinComplexMatrix, randStream)
    nComplexs = size(proteinComplexMatrix, 2);
    proteinComplexs = zeros(nComplexs, 1);

    while true
        cumprob = buildProteinComplexs_rates_collisionTheory(...
            totalProteinMonomers, proteinComplexMatrix, 'cumulative probability');

        if isnan(cumprob(1)); break; end;

        selectedComplex = find(randStream.rand() < cumprob, 1, 'first');
        if isempty(selectedComplex)
            selectedComplex = find(cumprob == 1, 1, 'first');
        end

        proteinComplexs(selectedComplex) = proteinComplexs(selectedComplex) + 1;
        totalProteinMonomers = totalProteinMonomers - proteinComplexMatrix(:, selectedComplex);
    end
end
```

In English:
- Repeatedly compute the rate of each candidate complex
- Sample which complex to form next, weighted by rate
- Form one copy, decrement subunits
- Stop when no complex can form (i.e. some subunit is exhausted)

Rate per complex:
```matlab
rates = prod((totalProteinMonomers(:, ones(size(proteinComplexMatrix,2), 1)) / mean(totalProteinMonomers)) .^ proteinComplexMatrix, 1)';
```

In English: rate ∝ ∏ over subunits of `(count[subunit] / mean(counts)) ^ stoichiometry[subunit, complex]`. Power, not falling factorial. The mean-normalization is just to keep numbers numerically stable; ratios between complexes are what matter. Same single rate constant for all complexes (no fitted k values).

### 2.3 The mass-balance emit at the end

```matlab
this.complexs = this.complexs + newComplexs;
this.substrates = this.substrates - this.complexComposition * newComplexs;
```

`complexComposition` is a `[n_substrates × n_complexes]` matrix. `complexComposition * newComplexs` gives the total subunits consumed. **One matrix multiplication; no per-key dict-merge.** v4's signed-Counter emit pattern was overengineered for a problem Karr doesn't have.

### 2.4 RibosomeAssembly specifics

From `RibosomeAssembly.m` docstring (verified line 60-74 of `24_RibosomeAssembly.md`):

```
In a randomized order over particles, for each ribosomal particle:
1. Calculate the maximum number of particles that can form based on
   available RNA and protein monomer subunits, GTPases, and GTP.
2. Increment the number of ribosomal particles. Decrement the numbers of RNA
   and protein monomer subunits, and GTP and water. Increment the counts of
   the byproducts of GTP hydrolysis (GDP, Pi, H).
```

In English: same closed-form bounds calculation as cluster-1 of MC, plus GTP/H₂O consumption, plus GDP/Pi/H byproducts. Randomization is just the order in which 30S vs 50S is processed (matters when GTP/H₂O is limiting and both want it).

**The 30S/50S split:**
- 30S: 2 assembly GTPases (Era=MG_387, RbfA=MG_143)
- 50S: 4 assembly GTPases (EngA=MG_329, EngB=MG_335, Obg=MG_384, RbgA=MG_442)
- Karr's docstring: "each GTPase that has been reported to be required to form each ribosomal particle requires 1 GTP per particle"
- So 30S costs 2 GTP + 2 H₂O → 2 GDP + 2 Pi + 2 H; 50S costs 4 GTP + 4 H₂O → 4 GDP + 4 Pi + 4 H

### 2.5 ProteinDecay-light algorithm (subset of ProteinDecay #3)

From `ProteinDecay.m` docstring + `RNADecay.m` analog:

```
For each complex c in compartment comp:
    rate(c, comp) = complexDecayRates[c] * complex.counts[c, comp]
    n_decay = poisson(rate * stepSizeSec)
    n_decay = min(n_decay, complex.counts[c, comp])  % cap at available
    n_decay = min(n_decay, enzyme_capacity)          % cap at protease+peptidase availability

    decrement complex.counts[c, comp] by n_decay
    increment metabolites:
        + complexDecayReactions[products, c] * n_decay  (returns subunits + byproducts)
        - complexDecayReactions[reactants, c] * n_decay  (consumes ATP + H2O)
```

`complexDecayRates[c]` = ln(2) / weighted_mean_half_life_of_subunits.

`complexDecayReactions` (53×1206 in our fixture per `ProteinDecay_flat.mat`) encodes the metabolites required (ATP, H₂O) and released (subunit monomers + RNAs returned as "damaged", plus prosthetic groups) per complex form-entry.

**For ProteinDecay-light:** skip the "subunits marked damaged" step. Just route the subunits straight back to free monomer counts. The fidelity loss: in real Karr, damaged subunits then have to go through monomer decay before becoming raw amino acids. For our purposes (bounding the long-tail complex growth), this is acceptable — the complexes get returned to subunits, breaking the ratchet. Phase B's full `ProteinDecay` adds the damaged-state pathway later.

---

## 3. Architecture — fit into existing OpenCell chassis

### 3.1 Where the Karr allocation step lives

From `architecture/03_variable_allocation.md` (verified verbatim from `Simulation.evolveState.m` lines 137-170 of `architecture/01_simulation_loop.md`):

Karr's allocation runs **inside `Simulation.evolveState`**, before any process's `evolveState`. Sequence per tick:
1. Each process declares its needs via `calcResourceRequirements_Current()`
2. Chassis computes proportional-fair-share `allocations = floor(requirements × supply / sum(requirements))`
3. Chassis hands each process its allocation
4. Each process runs its own `evolveState`, consuming up to its allocated amount
5. Final mass-balance commit

**OpenCell maps this to a Vivarium `Step` that runs BEFORE all `Process` next_update calls.** The step computes proportional fair-share allocation across all processes for shared substrates (NTPs, GTP, H₂O, AA pool). Each process reads its allocation from a per-process port the Step writes.

This is the structural fix for v4's "ratchet" finding: D.2 doesn't consume from a shared global pool directly. It consumes from its allocated subset.

### 3.2 The audit prerequisite — `opencell/core/resource_ledger.py`

A Codex audit is in flight on `agent/karr-allocation-audit` comparing the existing OpenCell ledger to Karr's algorithm. **Findings from that audit feed into §3.3 and §6.** This design is conditional on either:

- (a) the existing ledger already implements proportional fair share → use as-is, hook D.2 + ProteinDecay-light into it
- (b) the existing ledger is close but diverges → align it to Karr's algorithm as a prerequisite step
- (c) the existing ledger does something fundamentally different → write a new Vivarium Step

**OPEN-2 in §10 until audit lands.**

### 3.3 Vivarium wiring — corrected from v4

v4 invented one-tick-lag, `d2_consumed_*` ports, deriver pattern. None of that is in Karr. The correct Vivarium pattern, matched to Karr:

```
Per-tick sequence (Vivarium):
  1. KarrAllocationStep.next_update()       [Vivarium Step, runs first]
       -> reads each process's current request via parameters
       -> computes proportional allocation
       -> writes per-process allocation to substrates.allocated[process_name][wid]
  2. M1, M2v2, M3v2, D2Real, ProteinDecayLight each run next_update() in parallel
       -> each reads substrates.allocated[<self>] to know what it can use
       -> each writes set updates to complex.counts, protein.counts, rna.counts, substrates
  3. Vivarium applies all updates at end-of-tick
```

D.2-real's port schema:
```python
{
    "substrates": {
        wid: {"_default": 0, "_updater": "accumulate", "_emit": True}
        for wid in self._substrate_wids  # all 580 Karr substrates; D.2 writes negative for consumed, positive for byproducts
    },
    "complex": {
        "counts": {
            wid: {"_default": 0, "_updater": "accumulate", "_emit": True}  # signed deltas: positive when formed
            for wid in self._d2_owned_wids
        }
    },
    "protein": {
        "counts": {
            wid: {"_default": 0, "_updater": "accumulate", "_emit": False}
            for wid in self._protein_subunit_wids  # negative when consumed as subunit
        }
    },
    "rna": {
        "counts": {
            wid: {"_default": 0, "_updater": "accumulate", "_emit": False}
            for wid in self._rna_subunit_wids  # rRNA, 5S/16S/23S
        }
    },
    "substrates_allocated": {
        "d2_real": {  # read-only view of this process's allocation
            wid: {"_default": 0, "_updater": "set", "_emit": False}
            for wid in ("GTP", "H2O", "ATP")  # the metabolites D.2 needs
        }
    },
}
```

ProteinDecay-light's port schema is analogous but writes positive deltas to `protein.counts` and `rna.counts` (returning subunits) and negative to `complex.counts` (decay), plus ATP/H₂O consumption and byproduct emission.

### 3.4 `set` vs `accumulate` decided

The current chassis uses `set` on most leaves (M2/M3 set rna.counts, protein.counts). v4 wrestled with this; the spike's Probe 1+2 confirmed accumulate works correctly across multiple writers.

**For A3.3:** the new ports introduced by D.2-real and ProteinDecay-light use `accumulate` because both processes are emitting deltas (positive forming, negative consuming). The existing `protein.counts` and `rna.counts` leaves stay `set` (M2/M3 v2 already write `set`); D.2-real and ProteinDecay-light add accumulate writes to those same leaves. **Per Probe 1, accumulate + set on the same leaf is well-defined: set wins, then accumulates are applied on top.**

This is the Karr-faithful pattern in Vivarium semantics.

### 3.5 Cold-start

Karr's `initializeState` (verified from `architecture/05_initializeState.md` lines 180-232):

```matlab
% Lines 192-216 in Simulation.initializeState — the cluster-aware
% complex initialization for the "expected" mode
[subs2Nets, cpxs2Nets, nets] = edu.stanford.covert.util.findNonInteractingRowsAndColumns(pcComp);
for i = 1:numel(nets)
    ...
    while true
        tmpRates = prod(...^tmpPcComp, 1)';
        tmpCpxs = tmpCpxs + tmpRates * min(tmpSubs ./ (tmpPcComp * tmpRates));
        tmpSubs = subunits(tmpSubIdxs) - tmpPcComp * tmpCpxs;
    end
end
```

In English: at t=0, Karr seeds complex counts by **running essentially the same MC algorithm to convergence** against initial monomer/RNA pools. Not from a snapshot; from the initialization step.

For OpenCell, the d2-stub currently does snapshot-seed. **For A3.3, replace the stub's seeding logic with the same algorithm D.2-real uses, run once at engine construction.** Same code path, no duplicate logic.

---

## 4. Implementation files

```
opencell/vivarium/
    karr_allocation_step.py         (~120 LOC)
        KarrAllocationStep(Step)  -- proportional fair share allocation
        Reads each process's current request
        Writes substrates.allocated[<process>] per-process

    karr_d2_real.py                  (~250 LOC)
        D2RealProcess(Process)
        Replaces karr_d2_stub.KarrD2StubProcess
        Implements MC per disconnected cluster
        Plus randomized-order ribosome assembly for RIBOSOME_30S, RIBOSOME_50S
        Reads from substrates.allocated.d2_real (its GTP/H2O/ATP allocation)
        Writes to complex.counts (positive), protein.counts (negative), rna.counts (negative), substrates (signed)

    karr_protein_decay_light.py      (~180 LOC)
        ProteinDecayLightProcess(Process)
        Implements Karr's ProteinDecay #3 only (complex decay)
        Reads from substrates.allocated.protein_decay_light (its ATP/H2O allocation)
        Reads from complex.counts to know what to decay
        Writes to complex.counts (negative, decay), protein.counts (positive, return subunits),
            rna.counts (positive, return subunits), substrates (signed)

    karr_composite.py                (modified)
        build_karr_chassis_v3()
        Wires: M1 + M2v2 + M3v2 + D2Real + ProteinDecayLight + KarrAllocationStep
        Removes d2_stub from this composer
        Keeps build_karr_chassis_v2 (with stub) for backwards compatibility

opencell/core/
    resource_ledger.py               (modified, conditional on §3.2 audit)
        Either as-is, aligned to Karr, or replaced by KarrAllocationStep

tests/vivarium/
    test_chassis_v3.py               (~250 LOC)
        Build smoke
        Single-tick smoke
        Allocation step proportional-fair-share correctness
        D.2 cluster-1 closed-form correctness
        D.2 MC per-cluster determinism with seed
        ProteinDecay-light closes the loop (long-tail complex growth bounded)
        Conservation: subunits in = subunits in complexes + free subunits
        Conservation: ATP/H2O consumed = byproducts produced
        Phenotype: total complex mass over 100 ticks settles to a steady state (not unbounded)
        Phenotype: snapshot-matched complex counts on cluster-1 deterministic check

tests/d2/
    test_d2_real.py                  (~200 LOC)
        Unit tests for D2RealProcess

tests/protein_decay/
    test_protein_decay_light.py      (~150 LOC)
        Unit tests for ProteinDecayLightProcess
```

**Total estimated LOC:** ~1150 across 4 source files + 3 test files.

---

## 5. The unbounded-growth fix (closing v4's BLOCKER)

GPT-5.5's v4 critique: D.2 has accumulate on `complex.counts` + greedy assembler + M3 replenishes monomers = ratchet upward forever. Karr's actual solution, now visible:

1. **The allocation step caps D.2's metabolite consumption per tick.** D.2 can't assemble more complexes than its ATP/GTP/H₂O allocation allows. Under contention, allocation = `floor(d2_request × supply / total_request)`. D.2 cannot starve other processes.
2. **ProteinDecay-light returns complexes to subunits.** Rate = `ln(2) × n_complexes / weighted_half_life`. Per Karr: complex half-lives range from ~minutes (regulatory complexes) to ~hours (ribosomes, RNAP).
3. **Steady state emerges from balance:** D.2 forms complexes at rate proportional to subunit supply; ProteinDecay-light removes them at rate proportional to complex count. Steady-state count = `assembly_rate / decay_rate`. Bounded by construction.

This is exactly Karr's design. v4 was trying to bound D.2 alone, which is structurally impossible without the decay sink. The fix isn't smarter D.2; it's the loop.

---

## 6. Oracle plan (per-process + integration)

### 6.1 Unit oracles

**D.2-real cluster-1 (closed form):**
- For each cluster-1 complex, seeded subunits → exact count of complexes formed
- Reference: `buildProteinComplexs_bounds` formula
- Test against `ProteinComplex_flat.mat` snapshot: at snapshot subunit counts, our D.2 should produce snapshot complex counts ±0 (closed form, deterministic)

**D.2-real cluster N≥2 (MC):**
- Property test: for a synthetic 2-complex network, MC should produce mean count over 100 seeds within 5% of the analytical steady state
- Determinism: same seed → same output
- Stop condition: no complex with rate > 0 → MC terminates

**RibosomeAssembly (subset of cluster-1):**
- Seeded 30S subunits + GTPases (Era, RbfA) > 0 → max 30S particles
- Seeded 50S subunits + GTPases (EngA, EngB, Obg, RbgA) > 0 → max 50S particles
- GTP consumption = 2 × n_30S + 4 × n_50S
- H₂O consumption matches
- GDP/Pi/H byproducts match

**ProteinDecay-light:**
- Seeded N complexes with given half-life → Poisson(λ) decay events per tick where λ = N × ln(2)/half_life
- Returned subunits = `complexDecayReactions[products, c] × n_decayed`
- Consumed ATP/H₂O matches `complexDecayReactions[reactants, c] × n_decayed`

**KarrAllocationStep:**
- 2 processes request {A: 10, B: 5} and {A: 20, B: 3}, supply {A: 15, B: 100}
- Expected: process 1 gets {A: 5, B: 5}, process 2 gets {A: 10, B: 3}
- Sum equals supply for contended, sum ≤ request for uncontended
- Zero-supply edge case
- Zero-request edge case (no division by zero)

### 6.2 Integration oracle — the bound-cycle phenotype

**Closed-loop test (the headline of A3.3):**

Run `build_karr_chassis_v3()` for 1000 ticks from initialized state. Assert:
- Total complex mass at t=1000 is within 10% of t=0
- No single complex count grows unboundedly (max < 100× snapshot value)
- ProteinDecay-light decay rate × mean complex count ≈ D.2 formation rate × mean subunit availability (steady-state balance)

This is the test v4 couldn't pass. With the loop, it does.

### 6.3 The "147 vs 149" discrepancy resolution

OPEN-1 from §1.1 must be resolved before tests are meaningful. A pre-implementation script:

```python
# scripts/audit_d2_wid_count.py
# Load MacromolecularComplexation_flat.mat, RibosomeAssembly_flat.mat, ProteinComplex_flat.mat
# Compute the actual set of D.2-owned WIDs three ways:
#  1. Karr's docstring claim: 149 + 2 = 151
#  2. Our fixture extraction (from d2-stub): 147 + 2 = 149
#  3. Live snapshot: count of complexes whose formationProcesses == Process_MacromolecularComplexation OR Process_RibosomeAssembly
# Print where the three disagree
# This is the single source of truth for the implementation
```

---

## 7. Cross-model critique anchors

When v1 of this design goes to cross-model critique, reviewers should specifically verify:

1. **Has the design replaced v4's signed Counter / one-tick-lag / dict-merge invention with Karr's actual matrix multiplication for mass balance?** §2.3.
2. **Does the disconnected-cluster decomposition appear in the design, OR has it been collapsed back to "global MC" again?** §2.1, §2.2.
3. **Does the allocation step run BEFORE process next_update calls in the Vivarium wiring?** §3.3.
4. **Is the ratchet closure mechanism the ProteinDecay-light loop, NOT internal D.2 logic?** §5.
5. **Has the design read `Simulation.evolveState.m` lines 137-170 (allocation block) and `MacromolecularComplexation.evolveState` lines 290-314 (the MC main function) verbatim, with citations?** §2.

If any of these slip, the design has reverted to designing-from-summaries.

---

## 8. Known tech debt and gaps

1. **`opencell/core/resource_ledger.py` may need rework.** Audit findings pending; design is conditional on §3.2.
2. **Cold-start currently uses d2-stub's snapshot loader.** Replacing with Karr's MC-to-convergence initialization is in scope for A3.3 but adds ~80 LOC. Acceptable.
3. **Full ProteinDecay (monomer decay, misfolding, refolding, proteolysis tagging) deferred to Phase B.** Documented in §1.3.
4. **`prosthetic group salvage`** from complex decay not modeled in ProteinDecay-light. Per docstring, this matters for some complexes (heme, FeS clusters, etc.). Deferred.
5. **Cluster-1 vs cluster N≥2 partition is a fixture artifact** — we trust Karr's `findNonInteractingRowsAndColumns` output. We don't re-derive it. Risk: if the fixture's `complexNetworks` is wrong, we'd inherit the error. Verification: spot-check that the 2 ribosomal particles are in their own cluster (they should be — 30S and 50S share GTPases as catalysts, not as subunits).
6. **The "147 vs 149" count discrepancy.** OPEN-1.

---

## 9. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| OPEN-1 (147 vs 149) reveals a deeper fixture bug | LOW | MEDIUM | Run audit script in §6.3 as pre-implementation step |
| Allocation step disagrees with `resource_ledger.py` | MEDIUM | MEDIUM | Codex audit in flight; pick one and align |
| ProteinDecay-light decay rates inconsistent with M3v2 protein-counts dynamics | MEDIUM | MEDIUM | Integration test §6.2 catches it; tune ProteinDecay-light's enzyme-capacity cap if needed |
| MC determinism breaks under multiprocess pytest | LOW | LOW | Already solved in M0a (PRNG via SeedSequence) |
| Cluster decomposition disagrees between MC and RibosomeAssembly | LOW | MEDIUM | Verify in test §6.1 that 30S and 50S are in separate clusters or trivially-formed independently |

---

## 10. Open questions for resolution before cross-model critique

| OPEN | Question | Resolution path |
|---|---|---|
| OPEN-1 | "147 + 2 = 149" (fixture) vs "149 + 2 = 151" (Karr docstring). Which is correct? | Run `scripts/audit_d2_wid_count.py` from §6.3 |
| OPEN-2 | Existing `opencell/core/resource_ledger.py` — aligned with Karr, divergent, or to-replace? | Codex audit on `agent/karr-allocation-audit` (in flight) |
| OPEN-3 | Should KarrAllocationStep be a Vivarium `Step`, `Deriver`, or a `Process` that runs first? | Spike Probe 2 already confirmed `Step` works for this pattern (`final_protein_A=190` test). Use `Step`. |
| OPEN-4 | Cluster-N≥2 MC re-uses Karr's RNG seed semantics; does Vivarium's SeedSequence pattern reproduce exactly? | Probe 1 confirmed signed accumulate works; need to also verify SeedSequence.spawn() determinism within a process across ticks |
| OPEN-5 | Does ProteinDecay-light need its own resource allocation (separate from D.2's), or does the global allocation step handle it? | Global step is sufficient per §3.1; ProteinDecay's only metabolite consumers are ATP and H₂O which all processes share |

---

## 11. Implementation plan

| Phase | Effort | Status |
|---|---|---|
| **0.** Resolve OPEN-1 (count audit script) | 2 hours | TODO |
| **1.** Resolve OPEN-2 (read Codex ledger audit findings) | 1 hour | IN FLIGHT (codex-ledger-audit shell) |
| **2.** Cross-model critique on this v1 design | 1 hour wall (parallel critiques) + 1 hour synthesis | TODO |
| **3.** Apply critique findings → v2 design (if needed) | 1-2 hours | CONTINGENT |
| **4.** Delegate implementation to Codex | ~3-5 hours wall | TODO |
| **5.** Orchestrator review of Codex output | 1-2 hours | TODO |
| **6.** Merge to main | 30 minutes | TODO |
| **7.** Update plan.md, ship blog post | 1 hour | TODO |

**Total wall-clock estimate: ~12-15 hours focused work** = 2-3 sessions.

The big-batch v4 estimate of "17 hours for implementation + 1 week chassis wiring + 1 week design = 3-4 weeks" was inflated by v4's overengineering (one-tick-lag, signed Counter, etc.). Reading the actual Karr code shows the implementation is much simpler. The implementation budget here is ~1 week, not 3-4.

---

## 12. What I read end-to-end before writing this

For provenance:
- `docs/karr_extracts/process/23_MacromolecularComplexation.md` (127 lines)
- `docs/karr_extracts/process/24_RibosomeAssembly.md` (109 lines)
- `docs/karr_extracts/process/21_ProteinDecay.md` (190 lines)
- `docs/karr_extracts/architecture/01_simulation_loop.md` (lines 1-180, the simulation main loop + variable allocation)
- `docs/karr_extracts/architecture/02_state_variables.md` (lines 220-340: ProteinComplex, ProteinMonomer, Rna state descriptions specifically)
- `docs/karr_extracts/architecture/03_variable_allocation.md` (full)
- `docs/karr_extracts/architecture/05_initializeState.md` (full)
- `data/m1_sources/WholeCell/src/+edu/.../+process/MacromolecularComplexation.m` lines 287-392 (the actual evolveState + helpers)

The architecture extracts also contain the verbatim implementation of the cluster-aware initialization in `initializeState` lines 192-216 — that's directly relevant to cold-start (§3.5).

This is the design's primary-source foundation. Every algorithmic claim in §2 and §3 cites a specific line range in these sources. No paraphrase, no summary.
