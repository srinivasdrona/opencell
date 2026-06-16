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
