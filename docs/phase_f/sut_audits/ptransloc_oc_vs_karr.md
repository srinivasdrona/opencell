# ProteinTranslocation OC vs Karr Parity Audit

## DAP Intent
Contract:
- Required behavior: determine whether OpenCell's `opencell/vivarium/karr_protein_translocation.py:307-457` is algorithmically equivalent to Karr's `evolveState` in `src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinTranslocation.m:305-370`.
- Why this matters: the L2.2 substrate-stress divergence is only exculpatory if OC preserved Karr's control flow under low-substrate regimes.
- Done = a verification artifact that fully maps Karr steps, RNG draws, and insufficient-substrate behavior onto the OC port and states a justified verdict.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode: relying on the checked-in Karr doc extract or fixture semantics while missing the actual `evolveState` loop shape, especially its per-copy randomization and break-on-first-failure behavior.
- What would falsify this audit: any later recovery of a different authoritative Karr `ProteinTranslocation.m` body that changes lines 305-370 materially.

PM sanity-check:
- I treated the upstream CovertLab WholeCell source as authoritative for Karr line citations because the literal local prompt path `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinTranslocation.m` is absent from this worktree, while `docs/karr_extracts/process/22_ProteinTranslocation.md` contains only the header/docstring.

## Inventory of existing artifacts
- [A01] path=docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md | kind=doc | role=defines Beat-1..5 audit discipline and the required inversion check.
- [A02] path=docs/prompts/DESIGN_TEMPLATE.md | kind=doc | role=provides the inventory and baseline-facts structure reused here.
- [A03] path=docs/prompts/COMPOSITION_MANDATE_v2.md | kind=doc | role=authoritative slot-composition rule for this deliverable.
- [A04] path=docs/karr_extracts/process/22_ProteinTranslocation.md | kind=doc | role=local Karr header/docstring extract and provenance pointer to the canonical MATLAB source path.
- [A05] path=CovertLab/WholeCell:src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinTranslocation.m | kind=code | role=authoritative Karr `evolveState` body used for line-by-line parity citations because the prompt-named local path is missing.
- [A06] path=opencell/vivarium/karr_protein_translocation.py | kind=code | role=OpenCell implementation under audit; `next_update` is the comparison target.
- [A07] path=scripts/matlab/serialize_chromosome_state.m | kind=code | role=reference-only chromosome serializer used to confirm that chromosome surfaces are irrelevant to this process.
- [A08] path=STATUS_ptransloc_sut_parity.md | kind=status | role=checkpoint log for the audit beats and self-check.

Beat-4 inversion for inventory:
- What critical artifact could still be missing from this list? A locally vendored copy of `ProteinTranslocation.m` with edits relative to upstream.
- What check did you run to reduce that risk? Searched the worktree for `ProteinTranslocation.m`, `classdef ProteinTranslocation`, and the exact prompt path; only the doc extract was present locally, so Karr line citations were anchored to the canonical upstream source instead.
- What could be wrong in the artifacts we listed? `docs/karr_extracts/process/22_ProteinTranslocation.md` is not sufficient for parity because it preserves the header but not the `evolveState` body; claims about control flow therefore cite [A05], not [A04]. No data artifact is treated as an evidence anchor in this audit.

## Baseline facts and constraints
- Hard constraints from the task: read-only audit, no MATLAB invocation, no tests, no code edits, and output limited to markdown artifacts.
- Source-provenance constraint: the prompt-named local Karr path is absent from this worktree, so the audit uses the upstream Karr source for `evolveState` line citations and the local doc extract only for provenance context.
- Karr single-component facts: `evolveState` builds a cumulative count vector over cytosolic translocating monomers, draws one global `randperm` over total copies, processes one selected monomer copy at a time, and `break`s on the first insufficient-resource check (`ProteinTranslocation.m:307-368`).
- Karr single-component facts: enzyme availability is converted to rate-scaled capacities with `translocaseSpecificRate * stepSizeSec / preproteinTranslocase_aaTranslocatedPerATP` and `stepSizeSec`, not consumed as raw enzyme counts (`ProteinTranslocation.m:321-322`).
- OC single-component facts: `next_update` ignores `timestep`, reads ATP/GTP/H2O from `substrates_allocated`, derives enzyme availability from raw count stores, and processes species in two phases (`karr_protein_translocation.py:307-429`).
- OC single-component facts: `_load_fixture` excludes `MG_191_MONOMER` and `MG_192_MONOMER` before building the translocatable set (`karr_protein_translocation.py:22-23, 189-192`), whereas Karr remaps terminal-organelle compartments onto cytosol or membrane and keeps all non-cytosolic monomers in `monomerIndexs_translocating` (`ProteinTranslocation.m:198-203`).
- Known anti-pattern: the Karr header text says `monomerSRPPathways` is true for integral-membrane proteins (`ProteinTranslocation.m:89-97`), but the executable code sets it from `signalSequenceType in {'lipoprotein','secretory'}` (`ProteinTranslocation.m:203`). The audit therefore trusts executable code over docstring prose.
- Chromosome-surface fact: the reference serializer only serializes chromosome sparse-matrix fields such as `polymerizedRegions`, `linkingNumbers`, and `strandBreaks` (`serialize_chromosome_state.m:21-34`); neither implementation touches chromosome state, so chromosome serialization is out of scope for this audit.

Beat-4 inversion for baseline facts:
- Which baseline "fact" is inferred rather than proven? That the upstream CovertLab `ProteinTranslocation.m` body matches the intended local source path named in the prompt.
- What would invalidate it? Recovery of a different local `data/m1_sources/WholeCell/.../ProteinTranslocation.m` with materially different lines 305-370.

## 1. Algorithm summary
Karr `evolveState` computes the total cytosolic queue of translocating monomer copies, samples a single random permutation over those individual copies, and then walks the permutation one selected copy at a time. For each selected monomer copy it computes translocase/SRP/ATP/GTP/water costs, checks those costs against current substrate pools and rate-scaled enzyme capacities, stops immediately on the first insufficiency, and otherwise moves exactly one monomer from cytosol to its destination compartment while updating ATP/GTP hydrolysis byproducts (`ProteinTranslocation.m:307-368`).

OpenCell `next_update` first reconstructs a species-level queue from `protein.unprocessed_counts` plus `protein.location`, then reads only allocator-granted ATP/GTP/H2O budget and raw enzyme counts. It processes SRP-path species first and direct-path species second, randomizing only species order within each phase, computing the same per-monomer ATP/GTP/hydrolysis formula but then translocating the maximum feasible number of copies for a species in a batch, updating `protein.location`, `protein.unprocessed_counts`, and substrate deltas in aggregate (`karr_protein_translocation.py:307-457`).

## 2. Step-by-step mapping

| Karr step | OC step | Verdict |
|---|---|---|
| `ProteinTranslocation.m:307` builds `monomersNeedingTranslocation = cumsum(...)` from the cytosolic counts of every translocating monomer species. | `karr_protein_translocation.py:325-338` builds a species-level `cytoplasmic_counts` dict from `protein.unprocessed_counts` gated by `protein.location`, with a fallback that ignores location labels if the first pass is empty. | `OC_SIMPLIFIED` |
| `ProteinTranslocation.m:309-312` returns immediately when no translocating cytosolic work exists. | `karr_protein_translocation.py:339-340` returns `{}` when no queued cytoplasmic counts remain after reconstruction. | `EQUIVALENT` |
| `ProteinTranslocation.m:318-322` snapshots ATP/GTP/H2O plus rate-scaled translocase and SRP capacities from current state. | `karr_protein_translocation.py:342-359` snapshots ATP/GTP/H2O from `substrates_allocated` and enzyme availability from raw count stores; `timestep` is discarded at line 308 and no `translocaseSpecificRate`-based capacity conversion occurs. | `DIVERGENT` |
| `ProteinTranslocation.m:324-325` draws one `randperm` over the total number of translocating monomer copies, so every copy participates in a single mixed random order. | `karr_protein_translocation.py:301-305, 418-429` uses `_rng.permutation(len(wids))` on species lists separately for SRP and direct phases. | `DIVERGENT` |
| `ProteinTranslocation.m:327-330` maps the current random draw back to one monomer copy via the cumulative sum and selects exactly one `idx_monomer`. | `karr_protein_translocation.py:376-383` iterates one species at a time and computes costs once per species, not once per monomer copy. | `DIVERGENT` |
| `ProteinTranslocation.m:332-337` computes `ceil(length/aaPerATP)`, SRP flag cost, ATP cost, GTP cost, and water cost for the selected monomer copy. | `karr_protein_translocation.py:381-384` computes the same per-monomer ATP, GTP, and hydrolysis quantities from `atp_cost_by_wid` and `srp_gtp_cost_per_monomer`. | `EQUIVALENT` |
| `ProteinTranslocation.m:339-347` halts the whole loop on the first selected monomer whose required translocase/SRP/ATP/GTP/water cost cannot be met. | `karr_protein_translocation.py:388-400, 419-429` computes the maximum feasible batch size for the current species and halts a phase only when that batch size is zero; if SRP phase halts, direct phase is skipped entirely. | `DIVERGENT` |
| `ProteinTranslocation.m:349-353` moves exactly one monomer copy from cytosol to its destination compartment in the `this.monomers` matrix. | `karr_protein_translocation.py:405, 436-443` accumulates a species-level batch count, decrements `protein.unprocessed_counts`, and sets the species `protein.location` to the destination without maintaining a per-compartment monomer matrix. | `OC_SIMPLIFIED` |
| `ProteinTranslocation.m:355-360` decrements local ATP/GTP/H2O and rate-scaled translocase/SRP capacities by exactly one monomer copy's cost. | `karr_protein_translocation.py:402-415` decrements substrate and enzyme trackers by the whole batched `translocate_count`, using raw pore/ATPase/SRP/SRP-receptor counts rather than Karr's rate-scaled capacities. | `DIVERGENT` |
| `ProteinTranslocation.m:362-368` writes ATP/GTP/H2O consumption and ADP/GDP/Pi/H+ production back to the substrate vector after each successful monomer move. | `karr_protein_translocation.py:434-456` emits the same substrate/byproduct stoichiometry in aggregate after all successful batches complete. | `EQUIVALENT` |

## 3. RNG draw inventory
- Karr `ProteinTranslocation.m:325`: `this.randStream.randperm(monomersNeedingTranslocation(end))`. Distribution/control: uniform permutation without replacement over all translocating monomer copies; controls the full global processing order of individual copies. OC counterpart: `karr_protein_translocation.py:301-305`, called from `:376` and `:419-428`, uses `self._rng.permutation(len(wids))`. Distribution/control: uniform permutation without replacement over species IDs within one phase; controls species order, not copy order. Match: `DIFFERENT_DISTRIBUTION`.
- Karr `evolveState` has no additional stochastic draws. OC `next_update` likewise has no additional draws inside `next_update` beyond `_ordered_wids`. Match: `YES`.

## 4. Substrate-availability handling
- Karr computes current `atp`, `gtp`, `water`, `translocases`, and `SRPs` once at the top of `evolveState` (`ProteinTranslocation.m:318-322`). For each randomly selected monomer copy it computes `monomerTranslocaseCost`, `monomerSRPCost`, `monomerATPCost`, `monomerGTPCost`, and `monomerWaterCost` (`ProteinTranslocation.m:332-337`), then immediately `break`s if any one of those costs exceeds the remaining local tracker (`ProteinTranslocation.m:339-346`). Because the random order is over individual copies, substrate or capacity exhaustion mid-iteration stops the whole process at the first failing copy, even if cheaper copies remain later in the permutation.
- OC computes `atp_remaining`, `gtp_remaining`, and `h2o_remaining` from `substrates_allocated` (`karr_protein_translocation.py:342-345`) and returns early only when ATP or H2O are already nonpositive (`karr_protein_translocation.py:345-346`). Inside `attempt_phase`, it converts the current species into a feasible batch size by taking the minimum allowed by ATP, GTP, H2O, pore, ATPase, and optionally SRP/SRP-receptor availability (`karr_protein_translocation.py:388-398`). If that batch size is positive, OC consumes as many copies of that species as possible in one shot (`karr_protein_translocation.py:402-415`); if the batch size is zero, it halts the current phase (`karr_protein_translocation.py:399-400`), and an SRP-phase halt prevents any direct-path phase from running (`karr_protein_translocation.py:418-429`).
- Verdict: `DIVERGENT`. Karr is a per-copy stop-on-first-failure algorithm over one mixed permutation (`ProteinTranslocation.m:324-347`), while OC is a per-species max-batch algorithm over two ordered phases (`karr_protein_translocation.py:365-429`). Under low substrate or enzyme budgets, OC can partially drain a species in a single step where Karr would have moved only one copy, and OC's fixed SRP-before-direct phase ordering can suppress direct-path translocation that Karr could still realize if direct copies appear earlier in the global permutation.

## 5. Overall verdict
**DIVERGENT_DOCUMENTED**

Documented divergences:
- Karr randomizes individual monomer copies in one mixed permutation (`ProteinTranslocation.m:324-330`); OC randomizes species separately in SRP and direct phases (`karr_protein_translocation.py:301-305, 365-429`).
- Karr converts enzyme counts into rate-scaled capacities using `translocaseSpecificRate` and `stepSizeSec` (`ProteinTranslocation.m:321-322`); OC discards `timestep` (`karr_protein_translocation.py:307-308`) and uses raw enzyme counts instead (`karr_protein_translocation.py:356-359, 395-398`).
- Karr executes one monomer copy per successful loop iteration (`ProteinTranslocation.m:327-368`); OC bulk-translocates `min(count, max_from_substrates, max_from_enzymes)` copies per species (`karr_protein_translocation.py:388-415`).
- Karr updates the compartment-resolved `this.monomers` matrix and includes all remapped non-cytosolic monomers (`ProteinTranslocation.m:198-203, 349-353`); OC excludes two terminal-organelle monomers at load time (`karr_protein_translocation.py:22-23, 189-192`) and represents movement as `protein.location` plus `unprocessed_counts` deltas (`karr_protein_translocation.py:436-456`).
- Karr reads actual substrate pools from `this.substrates` (`ProteinTranslocation.m:318-320`); OC reads only allocator-granted substrate budget from `substrates_allocated` (`karr_protein_translocation.py:315, 342-345`).

Conclusion:
- The OC implementation is not a faithful line-by-line port of Karr's `evolveState`.
- Therefore the day-29 low-substrate divergence cannot be dismissed as "same algorithm, different alpha" on the basis of static source parity alone.

## 6. Implications for regime-bounded label
- Recommendation: keep `regime_bounded`.
- Reason: the source audit found concrete algorithmic divergences that are relevant precisely in substrate-limited regimes: copy-level versus species-level randomization, one-at-a-time versus batched execution, rate-scaled versus raw enzyme capacity, and different handling of mid-iteration insufficiency (`ProteinTranslocation.m:321-347`; `karr_protein_translocation.py:342-429`).
- Follow-on documentation note: any future label upgrade should wait for either a faithful OC re-port of Karr `evolveState` or empirical evidence that the documented divergences are biologically and numerically negligible across the bounded-stress regime.
