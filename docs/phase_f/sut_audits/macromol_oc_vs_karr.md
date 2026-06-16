# MacromolecularComplexation OC vs Karr Static SUT Parity Audit

## DAP Intent

Contract:
- Required behavior: determine whether `opencell/vivarium/karr_macromolecular_complexation.py::next_update` is algorithmically faithful to Karr's `MacromolecularComplexation.evolveState`, using only read-only evidence and line-cited source anchors.
- Why this matters: the L2.2 substrate-stress divergence is only exonerating if OC and Karr are running the same algorithm.
- Done = a reader can trace each Karr algorithmic step, each Karr RNG draw, and each substrate-exhaustion branch to the OC implementation and see a defensible verdict.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode: treating OC's high-level cluster decomposition as parity while missing that the OC Monte Carlo kernel forms multiple copies per iteration and therefore changes low-substrate behavior.
- What would falsify this contract statement: a checked-out primary `MacromolecularComplexation.m` showing different helper bodies than the verbatim excerpt used here, or an OC code path that preserves one-copy-per-iteration semantics after all.

PM sanity-check sentence:
- I am treating algorithmic parity as control-flow, mass-balance, and RNG-semantic parity, not superficial similarity in cluster structure alone.

## Inventory of Existing Artifacts

- [A01] path=`docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md` | kind=doc | role=authoring contract for Beats 1-5 and required INTENT / VERIFICATION framing.
- [A02] path=`docs/prompts/DESIGN_TEMPLATE.md` | kind=doc | role=source of the mandatory inventory and baseline-facts section structures used by this audit.
- [A03] path=`docs/prompts/COMPOSITION_MANDATE_v2.md` | kind=doc | role=authoritative slot-composition rule; confirms source constraints take priority over existing-code imitation.
- [A04] path=`opencell/vivarium/karr_macromolecular_complexation.py` | kind=code | role=OC implementation under audit; contains `_closed_form_bounds`, `_per_cluster_mc`, and `next_update`.
- [A05] path=`scripts/matlab/serialize_chromosome_state.m` | kind=code | role=checks whether this process has any chromosome-state coupling worth tracking; it does not.
- [A06] path=`docs/design/a3_step3_joint_design_v1.md` | kind=doc | role=fallback evidence anchor preserving verbatim excerpts of Karr `evolveState` and helper bodies because the prompt-specified MATLAB file is absent from this worktree.
- [A07] path=`data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat` | kind=trace | role=fixture used by OC for network partitioning and stoichiometry; content verified to load with `scipy.io.loadmat`, yielding 210 substrates, 147 complexes, a `(210, 147)` composition matrix, and 2 disconnected networks.
- [A08] path=`STATUS_macromol_sut_parity.md` | kind=status | role=beat log for this audit, including the source-read summary and self-check outcome.

Inventory Beat-4 inversion:
- Critical missing artifact: the prompt-specified primary source `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/MacromolecularComplexation.m` is not present in this checkout.
- Check run to reduce that risk: filesystem search plus `git ls-tree -r HEAD -- <exact-path>` both returned no tracked copy at the required path.
- What could be wrong in listed artifacts: [A06] could be an inaccurate transcription of the missing MATLAB source; [A07] could exist but contain malformed fixture payloads. [A07] content was verified by loading and inspecting its key fields. [A06] cannot be independently re-verified in this checkout and is therefore a documented evidence limitation.

## Baseline Facts and Constraints

- Hard constraints from task context:
  - Read-only audit only: no code edits, no MATLAB invocation, no tests.
  - Deliverables are markdown only: `docs/phase_f/sut_audits/macromol_oc_vs_karr.md` and `STATUS_macromol_sut_parity.md`.
  - The required answer is algorithmic parity, not a redesign proposal.
- Fidelity constraints from the source material:
  - Karr's top-level algorithm is explicitly cluster-partitioned: cluster 1 uses `buildProteinComplexs_bounds`; clusters 2..N use `buildProteinComplexs_montecarlokinetic`; after that Karr either returns early on zero `newComplexs` or applies one matrix multiply for substrate depletion (`docs/design/a3_step3_joint_design_v1.md:89-117`).
  - The preserved Karr Monte Carlo helper forms one complex copy per loop iteration, subtracts one stoichiometric column, and recomputes probabilities before the next draw (`docs/design/a3_step3_joint_design_v1.md:137-157`).
- Existing implementation facts, single-component only:
  - OC loads substrate IDs, complex IDs, stoichiometry, and network mappings from the `.mat` fixture during process construction (`opencell/vivarium/karr_macromolecular_complexation.py:53-77`, `:162-174`).
  - OC `next_update` reads only `substrates_allocated[self.name]`, floors/clips counts to nonnegative integers, and returns immediately if all allocated substrate counts are zero (`opencell/vivarium/karr_macromolecular_complexation.py:214-224`).
  - OC handles cluster 1 with `_closed_form_bounds` and all other clusters with `_per_cluster_mc`, then emits substrate deltas as `-(complexComposition @ new_complexes)` and positive complex deltas on `complex.counts` (`opencell/vivarium/karr_macromolecular_complexation.py:226-265`).
  - OC does not read or write chromosome state; the serializer script is specific to chromosome-primary gates (`scripts/matlab/serialize_chromosome_state.m:12-14`, `:21-35`).
- Known failure candidates and anti-patterns:
  - OC's `_per_cluster_mc` introduces an extra Poisson draw and may form multiple complexes in one loop iteration (`opencell/vivarium/karr_macromolecular_complexation.py:134-145`), which is not present in the preserved Karr helper (`docs/design/a3_step3_joint_design_v1.md:149-156`).
  - Because of that Poisson step, OC's configurable `rate_constant` changes formed-count magnitude, whereas in Karr the common rate constant only affects relative weights and cancels out of categorical selection.

Baseline Beat-4 inversion:
- Inferred rather than proven fact: `docs/design/a3_step3_joint_design_v1.md:89-157` is a verbatim copy of the missing MATLAB source.
- What would invalidate it: if a later checkout of `MacromolecularComplexation.m` disagrees with those excerpts, especially in the Monte Carlo helper body, this audit must be rerun against the primary file.

## 1. Algorithm Summary

**Karr.** Karr initializes a zero `newComplexs` vector, fills the no-competition network (cluster 1) deterministically with the stoichiometric upper bound for each complex, then iterates each remaining disconnected network independently with a Monte Carlo loop. In each Monte Carlo iteration it recomputes collision-theory relative rates from the current free-subunit pool, draws exactly one complex according to the cumulative probability vector, forms exactly one copy of that complex, subtracts the corresponding stoichiometric column from the current subunit pool, and repeats until no complex remains formable. If no complexes were formed in any cluster, the function returns; otherwise it adds `newComplexs` to `this.complexs` and subtracts `this.complexComposition * newComplexs` from `this.substrates` (`docs/design/a3_step3_joint_design_v1.md:89-117`, `:126-157`).

**OC.** OC also partitions the system by disconnected network and uses a deterministic closed-form bound for cluster 1, but its competitive helper `_per_cluster_mc` does not mirror Karr's one-copy-at-a-time loop. After computing upper bounds and collision-theory rates, it samples a complex index with `rng.choice`, then samples a Poisson count for that chosen complex, clips the sampled count to the current upper bound, and subtracts all sampled copies in one shot before the next rate recomputation. After processing each cluster, OC emits negative substrate deltas from `complexComposition @ new_complexes` and positive deltas on `complex.counts` (`opencell/vivarium/karr_macromolecular_complexation.py:80-148`, `:214-265`).

## 2. Step-by-Step Mapping

| Step | Karr `evolveState` / helper | OC `next_update` / helper | Verdict |
|---|---|---|---|
| 1. Initialize per-tick complex delta vector | `newComplexs = zeros(size(this.complexs));` in original `evolveState` lines 290-293, preserved at `docs/design/a3_step3_joint_design_v1.md:92-93`. | `new_complexes = np.zeros(len(self.complex_wids), dtype=np.int64)` at `opencell/vivarium/karr_macromolecular_complexation.py:226`. | EQUIVALENT |
| 2. Obtain current free-subunit pool for this tick | Karr reads `this.substrates`, which the simulation has already populated before `evolveState`; no normalization happens inside the function. The top-level use sites are preserved at `docs/design/a3_step3_joint_design_v1.md:96-97`, `:105`. | OC reads `states["substrates_allocated"][self.name]`, floors and clips to nonnegative integers, and short-circuits on an all-zero pool at `opencell/vivarium/karr_macromolecular_complexation.py:216-224`. | OC_SIMPLIFIED |
| 3. Deterministic no-competition cluster | Karr sends cluster 1 through `buildProteinComplexs_bounds(...)` in original lines 294-298, preserved at `docs/design/a3_step3_joint_design_v1.md:95-99`, with the bound formula at `:126-128`. | OC identifies `cluster_idx == 1`, slices the stoichiometry matrix, and calls `_closed_form_bounds(...)` at `opencell/vivarium/karr_macromolecular_complexation.py:234-237`; the bound formula is implemented at `:80-90`. | EQUIVALENT |
| 4. Extra guard branch on cluster-1 overconsumption | No corresponding branch in the preserved Karr code; the deterministic bound is accepted as-is. | OC adds a safety hedge: if `stoich @ in_cluster` would exceed `sub_avail`, it falls back to `_per_cluster_mc(...)` at `opencell/vivarium/karr_macromolecular_complexation.py:238-242`. | OC_SIMPLIFIED |
| 5. Loop over competitive disconnected networks | Karr loops `for i = 2:length(this.complexNetworks)` and fills each network with `buildProteinComplexs_montecarlokinetic(...)` in original lines 300-307, preserved at `docs/design/a3_step3_joint_design_v1.md:100-107`. | OC loops over all networks, skips empty network slices, and dispatches clusters `>= 2` to `_per_cluster_mc(...)` at `opencell/vivarium/karr_macromolecular_complexation.py:228-246`. | EQUIVALENT |
| 6. Recompute collision-theory rates from the current pool | Karr helper recomputes `cumprob = buildProteinComplexs_rates_collisionTheory(...)` every iteration and breaks when `cumprob(1)` is `NaN` (`docs/design/a3_step3_joint_design_v1.md:143-147`, `:166-171`). | OC recomputes `ub`, then per-complex rates from the current `available` pool each iteration, zeros rates where `ub == 0`, and breaks when `total_rate <= 0` (`opencell/vivarium/karr_macromolecular_complexation.py:104-132`). | EQUIVALENT |
| 7. Randomly choose which complex forms next | Karr draws one uniform variate `randStream.rand()`, compares it to `cumprob`, and selects the first matching complex (`docs/design/a3_step3_joint_design_v1.md:149-152`). | OC samples one categorical choice `rng.choice(n_cpx, p=(rates / total_rate))` at `opencell/vivarium/karr_macromolecular_complexation.py:134`. | EQUIVALENT |
| 8. Decide how many copies are formed in that iteration | Karr increments the selected complex by exactly one copy and subtracts exactly one stoichiometric column before looping (`docs/design/a3_step3_joint_design_v1.md:154-156`). | OC samples `sampled = rng.poisson(rates[chosen])`, clips to `ub[chosen]`, coerces zero upward to `1` when `ub[chosen] > 0`, and may subtract multiple stoichiometric columns in one iteration (`opencell/vivarium/karr_macromolecular_complexation.py:135-145`). | DIVERGENT |
| 9. Stop when nothing formed anywhere | Karr explicitly returns if `~any(newComplexs)` in original lines 309-312, preserved at `docs/design/a3_step3_joint_design_v1.md:109-112`. | OC has an early zero-substrate return at `:223-224`; otherwise it returns empty filtered deltas if `new_complexes` remains all zero after the cluster loop (`opencell/vivarium/karr_macromolecular_complexation.py:252-265`). | OC_SIMPLIFIED |
| 10. Apply mass-balance update | Karr performs `this.complexs = this.complexs + newComplexs; this.substrates = this.substrates - this.complexComposition * newComplexs;` in original lines 314-315, preserved at `docs/design/a3_step3_joint_design_v1.md:114-116`, `:175-180`. | OC computes `consumed = stoich @ in_cluster` per cluster, then emits final `delta_substrates = -(self.complex_composition @ new_complexes)` and positive complex deltas on `complex.counts` at `opencell/vivarium/karr_macromolecular_complexation.py:248-265`. | EQUIVALENT |

## 3. RNG Draw Inventory

| Karr draw | OC draw | Match |
|---|---|---|
| `randStream.rand()` once per Monte Carlo iteration to pick the next complex from the cumulative probability vector; it controls **which complex** forms next (`docs/design/a3_step3_joint_design_v1.md:149-152`). | `rng.choice(n_cpx, p=(rates / total_rate))` once per OC Monte Carlo iteration to pick the next complex; it controls **which complex** forms next (`opencell/vivarium/karr_macromolecular_complexation.py:134`). | YES |
| No second stochastic draw for multiplicity. Karr always forms exactly one copy of the selected complex per iteration (`docs/design/a3_step3_joint_design_v1.md:154-156`). | `rng.poisson(rates[chosen])`, then `min(sampled, ub[chosen])`, with a forced floor to `1` when `ub[chosen] > 0` and the Poisson sample is zero; it controls **how many copies** form before rates are recomputed (`opencell/vivarium/karr_macromolecular_complexation.py:135-145`). | NO |

Coverage note:
- Karr's preserved MacromolecularComplexation excerpt contains no `randperm`, `mnrnd`, `poissrnd`, or other RNG calls besides the single `randStream.rand()` in the competitive helper.

## 4. Substrate-Availability Handling

**Karr when substrate is insufficient from the start.**
- In the deterministic cluster, `buildProteinComplexs_bounds` returns `0` for any complex whose limiting subunit count is below stoichiometric need (`docs/design/a3_step3_joint_design_v1.md:126-128`).
- In competitive clusters, Karr recomputes `cumprob` from the current pool and exits the loop when `cumprob(1)` is `NaN`, which is the preserved "no further complexes can form" termination condition (`docs/design/a3_step3_joint_design_v1.md:143-147`).

**Karr when substrate runs out mid-iteration.**
- Karr never consumes multiple copies at once. After each selected complex, it subtracts exactly one stoichiometric column (`docs/design/a3_step3_joint_design_v1.md:154-156`), then the next loop iteration recomputes rates and either chooses another still-feasible complex or terminates.
- This means substrate exhaustion is checked after every single complex-formation event.

**OC when substrate is insufficient from the start.**
- OC floors/clips the allocated pool and returns immediately if the entire pool is zero (`opencell/vivarium/karr_macromolecular_complexation.py:218-224`).
- Within `_per_cluster_mc`, OC computes `ub = _closed_form_bounds(...)` and exits when no upper bound is positive; it also forces rates for `ub == 0` complexes to zero before selecting anything (`opencell/vivarium/karr_macromolecular_complexation.py:104-132`).

**OC when substrate runs out mid-iteration.**
- OC may consume more than one copy of the selected complex before reconsidering the rest of the network because it draws `sampled = rng.poisson(rates[chosen])`, clips it to `ub[chosen]`, and subtracts `stoich[:, chosen] * n_form` in one step (`opencell/vivarium/karr_macromolecular_complexation.py:135-145`).
- Only after that bulk subtraction does the next loop iteration recompute rates and upper bounds.

**Verdict.**
- DIVERGENT. Karr's substrate-limited behavior is one-copy-at-a-time with a feasibility check after every single assembly event (`docs/design/a3_step3_joint_design_v1.md:149-156`), while OC can consume several copies in one iteration before re-evaluating feasibility (`opencell/vivarium/karr_macromolecular_complexation.py:135-145`). That difference is exactly the kind of regime-bounded branch that can show up when free subunits are scarce.

## 5. Overall Verdict

**DIVERGENT_BUG**

Documented divergences:
1. Karr forms exactly one complex copy per competitive-loop iteration, but OC samples a Poisson multiplicity and may form multiple copies before rates are recomputed (`docs/design/a3_step3_joint_design_v1.md:149-156`; `opencell/vivarium/karr_macromolecular_complexation.py:135-145`).
2. OC therefore introduces an extra RNG draw that Karr does not have, so the stochastic process is not distributionally identical even when both start from the same allocated pool (`docs/design/a3_step3_joint_design_v1.md:149-156`; `opencell/vivarium/karr_macromolecular_complexation.py:134-145`).
3. OC's `rate_constant` materially affects the number of complexes formed because it sets the Poisson mean, while Karr's common specific rate only affects relative selection weights inside the categorical draw and does not create an extra multiplicity dimension (`docs/design/a3_step3_joint_design_v1.md:166-171`; `opencell/vivarium/karr_macromolecular_complexation.py:97`, `:122-145`, `:159`).
4. OC contains an extra cluster-1 fallback branch to the divergent Monte Carlo helper if the closed-form result appears to overconsume (`opencell/vivarium/karr_macromolecular_complexation.py:238-242`); that branch is not present in the preserved Karr code.

Fix todo:
- Replace OC's Poisson multiplicity path with Karr's one-copy-per-iteration competitive loop, keeping only the categorical complex-selection draw and immediate single-copy substrate subtraction.

Evidence caveat:
- The primary MATLAB file named in the prompt is absent from this worktree. The Karr side of this audit therefore relies on the preserved verbatim excerpt in `docs/design/a3_step3_joint_design_v1.md:89-157`. That is sufficient to reject parity on the Monte Carlo kernel, but the audit should still be rerun against the primary `.m` file if it is later restored locally.

## 6. Implications for Regime-Bounded Label

Recommendation:
- Keep `regime_bounded`.
- Document that the current OC implementation is not a faithful port of Karr's competitive Monte Carlo kernel under substrate limitation.
- Do not upgrade to `confirmed_biology_validated` yet, because the observed low-substrate divergence can plausibly arise from this algorithmic mismatch even before considering any α-mismatch in the stress test setup.
