# RibosomeAssembly OC vs Karr Static SUT Parity Audit

## DAP Intent

Contract:
- Required behavior: determine whether `opencell/vivarium/karr_ribosome_assembly.py::next_update` is algorithmically faithful to Karr's `RibosomeAssembly.evolveState` at lines 301-340 of the canonical MATLAB source.
- Why this matters: the RibosomeAssembly SUT can only exonerate downstream divergence if OpenCell preserved Karr's per-particle order, catalytic-enzyme gate, stoichiometric bound, and sequential depletion behavior.
- Done = a reader can trace every Karr `evolveState` step, every RNG draw, and every state gate onto the OC implementation and see a justified verdict.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode: declaring parity because OC randomizes 30S/50S order and matches hydrolysis stoichiometry, while missing that OC turns catalytic GTPase presence into a per-particle capacity limit.
- Secondary failure mode: overreacting to MATLAB's 1-based `randperm` versus NumPy's 0-based permutation even though the indexing difference is cosmetic if the permutation is applied correctly.

PM sanity-check:
- I am treating `E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\RibosomeAssembly.m` as the canonical Karr source because the prompt-named relative path is not populated inside this worktree even though the same relative path exists in the main checkout.

## Inventory of Existing Artifacts

- [A01] path=`docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md` | kind=doc | role=defines the Beat-1..5 audit discipline used for this deliverable.
- [A02] path=`E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\RibosomeAssembly.m` | kind=code | role=canonical Karr source for `evolveState`; used for all Karr algorithm line citations in this audit.
- [A03] path=`opencell/vivarium/karr_ribosome_assembly.py` | kind=code | role=OpenCell implementation under audit; `next_update` is the comparison target.
- [A04] path=`docs/karr_extracts/process/24_RibosomeAssembly.md` | kind=doc | role=local Karr header/docstring extract and provenance pointer to the canonical MATLAB source path.
- [A05] path=`tests/vivarium/test_karr_ribosome_assembly.py` | kind=code | role=existing OC verification surface; checked for what parity properties are and are not covered.
- [A06] path=`data/karr_fixtures/per_process/RibosomeAssembly.json` | kind=data | role=local fixture manifest confirming substrate index ordering, 30S/50S complex indices, and the six named GTPase indices consumed by the port.
- [A07] path=`STATUS_ribosome_assembly_sut_parity.md` | kind=status | role=live audit log and exit artifact required by session rules.

Beat-4 inversion for inventory:
- Critical missing artifact in this worktree: the prompt-specified relative path `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RibosomeAssembly.m` is absent locally.
- Check run to reduce that risk: `rg --files -g 'RibosomeAssembly.m'`, `Get-ChildItem data\m1_sources -Recurse -Filter RibosomeAssembly.m`, and `git ls-tree -r HEAD -- data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RibosomeAssembly.m` all returned no worktree-tracked mirror, while `Test-Path E:\opencell\...\RibosomeAssembly.m` succeeded.
- What could still be wrong: the main checkout copy could differ from a not-yet-materialized worktree mirror. Claims about Karr control flow therefore cite [A02], not [A04].

## Baseline Facts and Constraints

- Hard constraints from the task: read-only audit only, no MATLAB invocation, no test edits, markdown deliverables only, and exact line-cited parity between Karr and OC.
- Source-provenance fact: the Karr code examined for this audit is the canonical main-checkout file `E:\opencell\...\RibosomeAssembly.m`, whose `evolveState` body is at lines 301-340 and whose helper `getGtpPerComplex` is at lines 366-367.
- Karr single-component facts: `evolveState` returns immediately only when GTP is zero, randomizes the 30S/50S processing order with one `randStream.randperm`, computes `gtpPerComplex = sum(this.complexationCatalysisMatrix(:,i))`, bounds `newComplexs` by GTP, H2O, rRNA counts, and monomer counts, gates on `all(this.enzymes(this.complexationCatalysisMatrix(:,i)))`, then updates complexes, RNAs, monomers, and substrate hydrolysis products in place before considering the next particle. (`RibosomeAssembly.m:301-340`, `:366-367`)
- Karr fixture facts: the process has exactly two ribosomal particles and six named assembly GTPases, with `complexationCatalysisMatrix` assigning the 30S and 50S GTPase sets separately during `initializeConstants`. (`RibosomeAssembly.m:191-193`; `data/karr_fixtures/per_process/RibosomeAssembly.json` scalar keys `fixture/complexIndexs_30S_ribosome`, `fixture/complexIndexs_50S_ribosome`, `fixture/enzymeIndexs_*`, `fixture/substrateIndexs_*`)
- OC single-component facts: `next_update` reads allocator-granted GTP and H2O, returns early if either is non-positive, randomizes `self.complex_wids` with `self._rng.permutation`, computes RNA, monomer, and GTPase limits, applies local sequential depletion to `gtp_alloc`, `h2o_alloc`, `rna_pool`, and `monomer_pool`, then emits aggregate deltas through `_build_update`. (`opencell/vivarium/karr_ribosome_assembly.py:239-323`, `:325-372`)
- OC-specific suspect pattern: `_particle_resource_limits` computes a `gtpase_limit` from the counts of catalytic enzymes via `_stoich_limit_from_pool`, which means the port treats GTPases as a multiplicity bound rather than a pure presence gate. (`opencell/vivarium/karr_ribosome_assembly.py:57-72`, `:239-262`, `:342-355`)
- Test-surface fact: existing tests cover no-GTP gating, randomized 30S/50S order, hydrolysis byproducts, mass conservation, and chassis wiring, but the helper `_build_state` scales GTPase counts with `n_30s_capacity` and `n_50s_capacity`, so the tests currently encode the OC enzyme-capacity interpretation instead of Karr's presence-only enzyme gate. (`tests/vivarium/test_karr_ribosome_assembly.py:29-81`, `:111-216`)

Beat-4 inversion for baseline facts:
- Which baseline "fact" is inferred rather than proven? That reading the canonical main-checkout file is an acceptable substitute for the missing worktree mirror of the same relative path.
- What would invalidate it? Discovery of a different `RibosomeAssembly.m` under the worktree-local `data/m1_sources/WholeCell/...` path with materially different lines 301-340.

## 1. Algorithm Summary

**Karr.** Karr's `evolveState` is a two-particle greedy loop. If the current GTP count is zero it returns immediately. Otherwise it draws one `randperm` over the 30S and 50S particle indices, and for each selected particle computes `gtpPerComplex` as the number of required GTPases. It then calculates `newComplexs = floor(min([GTP / gtpPerComplex; H2O / gtpPerComplex; RNAs(required); monomers(required)]))`. If `newComplexs` is zero, or if any required catalytic enzyme is absent, Karr skips that particle. Otherwise it adds `newComplexs` to the particle count, subtracts the consumed RNA and monomer subunits, and applies the fixed substrate stoichiometry `[-1; 1; 1; -1; 1] * newComplexs * gtpPerComplex` before moving to the next particle in the permutation. (`RibosomeAssembly.m:301-340`, `:366-367`)

**OC.** OpenCell also runs a one-pass loop over the two particle indices in randomized order and performs local sequential depletion before the second particle is considered. It computes `gtp_per_particle` from the same catalysis matrix, limits formation by allocated GTP and H2O, subtracts RNA and monomer pools in place, and emits the same GDP/Pi/H byproduct pattern through `_build_update`. The key algorithmic difference already visible from the source is that OC's limit calculation includes a `gtpase_limit` based on catalytic-enzyme counts, so catalytic GTPases are treated as a consumable-like capacity bound even though Karr uses them only as an all-present/all-absent gate. (`opencell/vivarium/karr_ribosome_assembly.py:239-323`, `:325-372`)

## 2. Step-by-Step Mapping

| Karr step | OC step | Verdict |
|---|---|---|
| `RibosomeAssembly.m:302-305` returns immediately only when `substrates(gtp) == 0`. | `karr_ribosome_assembly.py:327-332` returns immediately when allocated GTP or allocated H2O is non-positive. | `OC_SIMPLIFIED` |
| `RibosomeAssembly.m:307-310` draws `randStream.randperm(numel(this.complexWholeCellModelIDs))` and iterates the permuted particle indices. | `karr_ribosome_assembly.py:340-341` iterates `self._rng.permutation(len(self.complex_wids))` and uses the permuted zero-based indices to select `self.complex_wids[int(cidx)]`. | `EQUIVALENT` |
| `RibosomeAssembly.m:312-313` computes `gtpPerComplex = this.getGtpPerComplex(i)`, and helper `getGtpPerComplex` is `sum(this.complexationCatalysisMatrix(:,i))` at `:366-367`. | `karr_ribosome_assembly.py:110-113` precomputes `n_gtpases_per_particle[wid] = int(np.sum(self.complexation_catalysis[:, idx]))`, then `:348` reads that value as `gtp_per_particle`. | `EQUIVALENT` |
| `RibosomeAssembly.m:315-327` bounds `newComplexs` by `floor(min([GTP / cost; H2O / cost; RNAs(required); monomers(required)]))`; catalytic enzymes are not part of this `min(...)` expression. | `karr_ribosome_assembly.py:342-355` computes `rna_limit`, `monomer_limit`, `gtpase_limit`, `gtp_limit`, and `h2o_limit`, then sets `n_form = min(rna_limit, monomer_limit, gtpase_limit, gtp_limit, h2o_limit)`. | `DIVERGENT` |
| `RibosomeAssembly.m:328-330` uses catalytic enzymes only as a binary gate: skip when `newComplexs == 0` or `~all(this.enzymes(this.complexationCatalysisMatrix(:,i)))`. | OC has no separate `all-present` enzyme gate; instead `_particle_resource_limits` folds catalytic-enzyme counts into `gtpase_limit`, so `n_form` is capped by the minimum catalytic-enzyme count even when every required enzyme is present. (`karr_ribosome_assembly.py:257-262`, `:342-355`) | `DIVERGENT_BUG` |
| `RibosomeAssembly.m:333` increments the selected particle count by `newComplexs`. | `karr_ribosome_assembly.py:359` stores `n_form` into `n_formed[particle_wid]`, and `_build_update` emits positive `complex.counts` deltas at `:301-323`. | `EQUIVALENT` |
| `RibosomeAssembly.m:335-336` subtracts consumed RNA and monomer subunits immediately, before the next particle is considered. | `karr_ribosome_assembly.py:363-370` subtracts the same RNA and monomer stoichiometry from local `rna_pool` and `monomer_pool` before the loop advances. | `EQUIVALENT` |
| `RibosomeAssembly.m:338` immediately updates the substrate vector with `[-1; 1; 1; -1; 1] * newComplexs * gtpPerComplex`, so remaining GTP/H2O for the next particle are reduced in sequence. | `karr_ribosome_assembly.py:360-361` immediately decrements local `gtp_alloc` and `h2o_alloc`, while `_build_update` later emits `GTP=-n`, `H2O=-n`, `GDP=+n`, `PI=+n`, `H=+n` at `:303-310`. Because GTP/H2O are reduced inside the loop, sequential depletion is preserved even though the delta emission is deferred. | `EQUIVALENT` |
| Karr's loop simply continues when a particle is infeasible and exits with no writes if neither particle forms. (`RibosomeAssembly.m:328-339`) | OC continues on `n_form <= 0` and `_build_update` returns `{}` when `n_formed` is all zeros. (`karr_ribosome_assembly.py:355-357`, `:301-323`) | `EQUIVALENT` |

## 3. RNG Draw Inventory

- Karr `RibosomeAssembly.m:308`: `this.randStream.randperm(numel(this.complexWholeCellModelIDs))`. Distribution/control: one uniform permutation without replacement over the two particle indices; it controls whether 30S or 50S gets first claim on shared GTP/H2O in that tick. OC counterpart: `karr_ribosome_assembly.py:340`, `self._rng.permutation(len(self.complex_wids))`. Distribution/control: one uniform permutation without replacement over the two zero-based particle indices; it controls the same first-claim order. Match: `YES`.
- The 1-based MATLAB versus 0-based NumPy index convention is cosmetic here because OC applies the permuted integer directly to `self.complex_wids` and the corresponding composition columns, so the permutation semantics are preserved. (`RibosomeAssembly.m:307-310`; `karr_ribosome_assembly.py:340-348`, `:363-369`)
- No additional stochastic draws appear in Karr `evolveState`, and no additional RNG calls appear in OC `next_update`. Match: `YES`. (`RibosomeAssembly.m:301-340`; `karr_ribosome_assembly.py:325-372`)

## 4. Substrate-Availability Handling Comparison

**Karr when substrate is insufficient from the start.**
- If GTP is exactly zero, Karr returns immediately before any permutation or particle work. (`RibosomeAssembly.m:302-305`)
- If GTP is positive but H2O, RNA, or monomer availability is limiting, Karr still iterates the randomized particle order, computes `newComplexs`, and simply `continue`s on any particle whose `floor(min(...))` is zero. (`RibosomeAssembly.m:307-330`)
- Missing catalytic enzymes behave the same way: the particle is skipped, but catalytic-enzyme counts do not reduce `newComplexs`; they only determine whether `all(...)` is true. (`RibosomeAssembly.m:323-330`)

**OC when substrate is insufficient from the start.**
- OC returns immediately when allocated GTP or allocated H2O is non-positive, which is a stricter entry gate than Karr's GTP-only early return. (`karr_ribosome_assembly.py:327-332`)
- If both allocated substrates are positive, OC computes per-particle limits and `continue`s when `n_form <= 0`, matching Karr's no-write behavior for infeasible particles. (`karr_ribosome_assembly.py:342-357`)
- The divergence is in the enzyme branch: OC's `gtpase_limit` makes catalytic-enzyme counts part of the resource floor, so "enzyme insufficient" can reduce `n_form` below the Karr value instead of acting as a simple present/absent gate. (`karr_ribosome_assembly.py:257-262`, `:342-355`)

**Sequential depletion under shared GTP/H2O scarcity.**
- Karr updates `this.substrates` inside the loop, so whichever particle appears first in `randperm` gets first claim on shared GTP and H2O. (`RibosomeAssembly.m:307-338`)
- OC preserves that order sensitivity by decrementing local `gtp_alloc` and `h2o_alloc` immediately after each successful particle, even though it emits the accumulated deltas only after the loop. (`karr_ribosome_assembly.py:359-361`, `:301-323`)
- Therefore the user-specified pre-mortem risk about deferred Vivarium deltas does not materialize here: OC's aggregate emission is architecture-different, but the local sequential depletion semantics are preserved.

**Verdict on substrate handling.**
- `DIVERGENT_BUG`. Shared-substrate competition is ported faithfully enough, but catalytic-enzyme scarcity is not. In Karr, one copy of each required GTPase is sufficient to catalyze multiple particle assemblies in a tick as long as GTP/H2O and subunits remain; in OC, the same state is capped at the minimum catalytic-enzyme count because `gtpase_limit` is folded into `n_form`. That is an algorithmic mismatch, not a documentation choice. (`RibosomeAssembly.m:323-330`; `karr_ribosome_assembly.py:257-262`, `:342-355`)

## 5. Overall Verdict

**DIVERGENT_BUG**

Load-bearing findings:
1. OC includes catalytic-enzyme counts in the per-particle `min(...)` bound, while Karr does not. Karr treats GTPases as a binary `all-present` gate only. (`RibosomeAssembly.m:323-330`; `karr_ribosome_assembly.py:342-355`)
2. The single Karr RNG draw is ported correctly in shape: `randperm` versus `permutation` is a cosmetic 1-based versus 0-based indexing difference, not the source of divergence. (`RibosomeAssembly.m:307-310`; `karr_ribosome_assembly.py:340-341`)
3. OC preserves Karr's sequential depletion of shared GTP/H2O despite emitting Vivarium deltas at the end of the loop, so the substrate-ordering semantics are not the broken part of the port. (`RibosomeAssembly.m:333-338`; `karr_ribosome_assembly.py:359-361`, `:301-323`)
4. Existing tests do not protect the Karr enzyme contract and instead build GTPase counts proportional to the desired formation capacity, which matches the current OC bug. (`tests/vivarium/test_karr_ribosome_assembly.py:46-56`)

Recommended fix shape:
- Remove `gtpase_limit` from the `n_form` minimum.
- Replace it with a separate presence-only gate equivalent to `all(required_gtpase_counts > 0)`.
- Add a parity test where each required GTPase is present at count `1`, RNA/monomer pools support multiple assemblies, and GTP/H2O support multiple assemblies; Karr semantics predict more than one particle can still form in that tick.

## 6. Implications

- The current OC `next_update` is not a faithful port of Karr's `RibosomeAssembly.evolveState`, so the SUT should not be cited as source-parity-clean until the catalytic-enzyme rule is corrected.
- This is a bug rather than a documented design deviation: the OC file docstring and tests describe all-or-nothing ribosome formation, but nowhere document a catalytic-enzyme-count capacity cap. (`opencell/vivarium/karr_ribosome_assembly.py:75-83`; `tests/vivarium/test_karr_ribosome_assembly.py:151-175`)
- Adjacent risk outside the strict SUT: `RequestCalculatorRibAsm.next_update` calls `estimate_formable_without_substrates`, which reuses the same `gtpase_limit` logic. Even after fixing `next_update`, allocator requests would remain too low in the same enzyme-scarce regimes unless that helper is corrected as well. (`opencell/vivarium/karr_ribosome_assembly.py:264-278`; `opencell/vivarium/karr_request_calculators.py:210-225`)
