| process | file:line (delta logic) | class | evidence (verbatim deciding line) | one-line justification | uncap verdict |
|---|---|---|---|---|---|
| chromosome_condensation | `opencell/vivarium/karr_chromosome_condensation.py:373,398` | RATE_OR_GATE | `n_bound = max(0, min(bound_delta_smc_adp, n_binding_max))`<br>`substrate_delta[self.atp_wid] = substrate_delta.get(self.atp_wid, 0.0) - float(n_bound)` | Allocation becomes `n_binding_max`, which gates how many binding events fire before stoichiometric drain is emitted. | REVIEW |
| chromosome_segregation | `opencell/vivarium/karr_chromosome_segregation.py:358,372` | RATE_OR_GATE | `max_events = min(`<br>`self.gtp_wid: float(-self.gtp_cost),` | Allocation only gates whether the segregation step can fire; the emitted drain is a fixed event cost, not `-allocation`. | REVIEW |
| cytokinesis | `opencell/vivarium/karr_cytokinesis.py:574,578` | RATE_OR_GATE | `if self._rng.random() <= self.rate_ftsz_gtp_hydrolysis and water_available >= hydrolysis_cost:`<br>`substrate_delta[self.water_wid] -= float(hydrolysis_cost)` | Allocated water gates per-edge hydrolysis events, and the returned substrate delta is the stoichiometry of those realized events. | REVIEW |
| dna_damage | `opencell/vivarium/karr_dna_damage.py:298,363` | INERT | `update: dict[str, Any] = {"requests": requests_update}`<br>`return update` | `substrates_allocated` is declared in schema but never read in `next_update`, and no `substrates` delta is emitted at all. | NO-EFFECT |
| dna_repair | `opencell/vivarium/karr_dna_repair.py:1434,441` | RATE_OR_GATE | `scale = min(scale, have / need)`<br>`substrate_delta[wid] = substrate_delta.get(wid, 0.0) - value` | Allocation rescales repair throughput across pathways, then the emitted drain is stoichiometry of the gated repairs. | REVIEW |
| dna_supercoiling | `opencell/vivarium/karr_dna_supercoiling.py:556,637` | RATE_OR_GATE | `limited_g_total, limited_t_total = self._limit_events_by_atp(`<br>`for wid, delta in self._substrate_delta(atp_used).items()` | Allocation first caps topoisomerase event totals via ATP/H2O budget, then emits stoichiometry for the ATP actually spent. | REVIEW |
| ftsz_polymerization | `opencell/vivarium/karr_ftsz_polymerization.py:541,554` | RATE_OR_GATE | `out[self.substrate_index_gtp] = self._allocated_or_state(`<br>`delta = np.rint(np.asarray(after, dtype=np.float64) - np.asarray(before, dtype=np.float64)).astype(` | Allocated GTP is injected as the limiting pool for the transition/ODE path, and the returned delta comes from the gated before/after substrate state. | REVIEW |
| macromolecular_complexation | `opencell/vivarium/karr_macromolecular_complexation.py:210,244` | RATE_OR_GATE | `sub_counts = np.array(` <br>`delta_substrates = -(self.complex_composition @ new_complexes)` | Allocation is treated as the substrate pool for stochastic complex formation, so a higher ceiling can change complex counts before stoichiometric drain is emitted. | REVIEW |
| metabolism | `opencell/vivarium/karr_metabolism.py:600,602` | CEILING | `consumed = min(-delta, alloc_budget)`<br>`allocated_delta[sid] = -consumed` | Negative writeback is clamped directly against the allocated budget and only the clamped amount is emitted. | SAFE |
| protein_decay_light | `opencell/vivarium/karr_protein_decay_light.py:1061` | INERT | `"substrates_allocated": {`<br>`update["substrates"] = substrate_update` | The port is declared, but the file never reads `states.get("substrates_allocated", ...)`; emitted substrate deltas come from `total_sub_deltas` instead. | NO-EFFECT |
| protein_folding | `opencell/vivarium/karr_protein_folding.py:412,289` | RATE_OR_GATE | `max_bind = min(max_bind, int(substrate_pool[sidx] // req))`<br>`substrate_delta[self.substrate_idx_atp] -= int(atp_consumed)` | Allocated substrates become an integer pool that limits ion binding and ATP-dependent folding events before stoichiometric deltas are formed. | REVIEW |
| protein_modification | `opencell/vivarium/karr_protein_modification.py:350,268` | RATE_OR_GATE | `progress = float(np.min(limits))`<br>`substrate_delta = self.reaction_stoich @ reaction_fluxes` | Allocation is converted into reaction-progress limits, then substrate drain is stoichiometry of the gated modification fluxes. | REVIEW |
| protein_processing_i | `opencell/vivarium/karr_protein_processing_i.py:233,274` | RATE_OR_GATE | `min(` <br>`water_remaining // 2,`<br>`substrate_delta[self.substrate_idx_water] -= total_processed + cleavage_count` | Allocated water gates cleavage/deformylation event counts, and the returned delta is the stoichiometry of those realized events. | REVIEW |
| protein_processing_ii | `opencell/vivarium/karr_protein_processing_ii.py:392,428` | RATE_OR_GATE | `transformations[indices] = np.minimum(current, allocated)`<br>`substrate_delta[self.substrate_index_water] -= peptidase_events` | Allocation is redistributed into bounded transformation counts, then substrate drain follows the realized transformations. | REVIEW |
| protein_translocation | `opencell/vivarium/karr_protein_translocation.py:401,433` | RATE_OR_GATE | `if atp_per_monomer > atp_remaining:`<br>`self.atp_wid: -float(atp_spent),` | Allocated ATP/GTP/H2O are decremented as per-monomer translocation events are admitted, so the ceiling gates event throughput. | REVIEW |
| replication | `opencell/vivarium/karr_replication.py:1141,1337,1357` | RATE_OR_GATE | `catalytic_atp_events = min(` <br>`scale = float(np.clip(min(limiting_ratios) if limiting_ratios else 1.0, a_min=0.0, a_max=1.0))`<br>`substrates_next[wid] = float(substrates_next.get(wid, 0.0) - float(amount))` | Both replay and non-replay paths turn allocation into capped ATP/dNTP event counts or fork-advance scale factors before emitting stoichiometric drain. | REVIEW |
| replication_initiation | `opencell/vivarium/karr_replication_initiation.py:742,767,776` | RATE_OR_GATE | `n_events = min(self._free_dnaa_adp, atp_pool)`<br>`n_events = min(n_events, max(0, int(np.floor(available_water))))`<br>`substrate_delta[self.water_wid] = substrate_delta.get(self.water_wid, 0) - n_events` | Allocation is converted into capped activation/hydrolysis event counts before stoichiometric substrate deltas are written. | REVIEW |
| ribosome_assembly | `opencell/vivarium/karr_ribosome_assembly.py:366,313` | RATE_OR_GATE | `n_form = int(min(rna_limit, monomer_limit, gtp_limit, h2o_limit))`<br>`self.substrate_wid_gtp: float(-total_gtp_hydrolyzed),` | Allocation gates how many particles can assemble, and the returned drain is the GTP/H2O cost of those realized assemblies. | REVIEW |
| rna_decay | `opencell/vivarium/karr_rna_decay.py:363,380` | RATE_OR_GATE | `if water_remaining < required:`<br>`substrate_delta = decay_events @ self.decay_reactions` | Allocated water gates which decay events survive the sampling loop, then the process emits stoichiometry for those kept events. | REVIEW |
| rna_modification | `opencell/vivarium/karr_rna_modification.py:562,281` | RATE_OR_GATE | `limit = int(np.min(avail // req))`<br>`substrate_delta = self.reaction_stoich @ reaction_fluxes` | Allocation becomes per-reaction substrate limits, and the returned delta is stoichiometry of the gated modification fluxes. | REVIEW |
| rna_processing | `opencell/vivarium/karr_rna_processing.py:403,284` | RATE_OR_GATE | `min(` <br>`float(np.min(substrate_limits)),`<br>`substrate_delta = self.reaction_stoich @ processing_events` | Allocation is converted into per-class substrate limits that cap processing event counts before stoichiometric drain is emitted. | REVIEW |
| transcription_v3 | `opencell/vivarium/karr_transcription_v3.py:182,186` | CEILING | `consumed = min(per_ntp_need, budget)`<br>`out[ntp] = float(-rounded)` | Each NTP delta is a direct clamp of desired demand against allocated budget. | SAFE |
| translation_v3 | `opencell/vivarium/karr_translation_v3.py:274,326,346` | CEILING | `consumed = min(need, budget)`<br>`consumed = min(float(translation_energy), gtp_limit, water_limit)`<br>`substrate_update[_SUBSTRATE_GTP_WID] = float(-energy_delta)` | Both amino-acid drain and energy-cycle drain are emitted only after direct `min(desired, budget)` clamps. | SAFE |
| trna_aminoacylation | `opencell/vivarium/karr_trna_aminoacylation.py:386,270` | RATE_OR_GATE | `reaction_limits = np.minimum(rounded_enzyme_limits, non_enzyme_limits)`<br>`substrate_delta = self.reaction_stoich @ reaction_events_by_rxn` | Allocation feeds reaction-limit calculations that determine realized aminoacylation events before stoichiometric drain is emitted. | REVIEW |

## Summary

1. Count per class
- `CEILING`: 3
- `AMOUNT`: 0
- `RATE_OR_GATE`: 19
- `INERT`: 2
- `UNRESOLVED`: 0

2. AMOUNT / RATE_OR_GATE processes
- `AMOUNT`: none
- `RATE_OR_GATE`: `chromosome_condensation`, `chromosome_segregation`, `cytokinesis`, `dna_repair`, `dna_supercoiling`, `ftsz_polymerization`, `macromolecular_complexation`, `protein_folding`, `protein_modification`, `protein_processing_i`, `protein_processing_ii`, `protein_translocation`, `replication`, `replication_initiation`, `ribosome_assembly`, `rna_decay`, `rna_modification`, `rna_processing`, `trna_aminoacylation`

3. What breaks if the ceiling is raised
- `chromosome_condensation`: a larger ceiling can raise `n_binding_max`, allowing more SMC binding events and therefore more ATP/H2O drain on that tick.
- `chromosome_segregation`: a larger ceiling can flip the segregation hydrolysis gate on, causing the process to spend a full fixed GTP/H2O event when it otherwise would not.
- `cytokinesis`: a larger ceiling can let more FtsZ edge-hydrolysis events fire, increasing water consumption and byproduct release.
- `dna_repair`: a larger ceiling can raise the repair-throughput scale factor, increasing realized repair counts and the stoichiometric drain tied to those repairs.
- `dna_supercoiling`: a larger ceiling can admit more gyrase/topoIV ATP-consuming events, changing both linking-number evolution and ATP/H2O drain.
- `ftsz_polymerization`: a larger ceiling changes the limiting GTP pool used by the transition/integration path, enabling more polymerization-state transitions and corresponding substrate drain.
- `macromolecular_complexation`: a larger ceiling can allow more complexes to form inside a network cluster, increasing stoichiometric reactant drain.
- `protein_folding`: a larger ceiling increases cofactor/ATP event capacity, producing more substrate drain through additional realized folding events.
- `protein_modification`: a larger ceiling increases per-reaction substrate limits, allowing more modification progress and more stoichiometric substrate drain.
- `protein_processing_i`: a larger ceiling increases cleavage/deformylation capacity, raising water consumption and byproduct release.
- `protein_processing_ii`: a larger ceiling increases allowable transformations, raising water/PG160 consumption and associated product release.
- `protein_translocation`: a larger ceiling admits more ATP/GTP/H2O-backed translocation events, increasing hydrolysis drain alongside transported-protein throughput.
- `replication`: a larger ceiling can increase allowed fork advance and ATP/ligase events, so DNA synthesis drain and chromosome advancement rise together.
- `replication_initiation`: a larger ceiling admits more DnaA activation/inactivation hydrolysis events, increasing substrate turnover inside initiation logic.
- `ribosome_assembly`: a larger ceiling admits more ribosome assembly events, increasing GTP/H2O hydrolysis and assembled-particle output.
- `rna_decay`: a larger ceiling lets more sampled decay events survive the water gate, increasing both RNA loss and substrate stoichiometry output.
- `rna_modification`: a larger ceiling raises reaction substrate limits, increasing modification fluxes and corresponding stoichiometric drain.
- `rna_processing`: a larger ceiling raises processing-event limits, increasing processing throughput and stoichiometric drain.
- `trna_aminoacylation`: a larger ceiling raises aminoacylation reaction limits, increasing reaction events and stoichiometric drain.

---

## Orchestrator verification (Copilot, read all 19 RATE_OR_GATE rows against source)

Codex's RATE_OR_GATE label is over-conservative. Re-reading each process's
consumption block against a tighter, decisive invariant —
**`consumption(WID) <= allocation(WID)` for every substrate** — every one of the
19 satisfies it. The `min(...)` in each row always includes an allocation-derived
term, OR the drain is a greedy budget loop that stops when the allocation is
exhausted, OR a fixed per-event cost gated on `allocation >= cost`. None can
consume more than it was allocated.

| process | bounding mechanism (verified line) | consume <= alloc? |
|---|---|---|
| chromosome_condensation | `n_binding_max = max(0, min(max_binding_energy, free_smc))`; ATP drain `= -n_bound <= n_binding_max` | yes |
| chromosome_segregation | fixed `-gtp_cost`, gated on `max_events >= 1` (`max_events = floor(gtp_avail/cost)`) | yes |
| cytokinesis | per-edge loop fires only `if water_available >= hydrolysis_cost`, decrements it | yes |
| dna_repair | `actual_repairs = _bounded_repairs(available=allocated)`; drain = stoich(repairs) | yes |
| dna_supercoiling | `_limit_events_by_atp(available_atp=hydrolysis_budget)` caps events | yes |
| ftsz_polymerization | ODE step chosen by `_last_nonnegative_solution_idx` (stops before GTP pool<0) | yes |
| macromolecular_complexation | explicit hedge: `if (stoich @ in_cluster) > sub_avail: fall back to MC` | yes |
| protein_folding | `max_bind = min(max_bind, substrate_pool[sidx] // req)` | yes |
| protein_modification | `progress = min(substrate_pool / total_consumed)`; drain = progress*consumed | yes |
| protein_processing_i | `cleavage_limit = min(..., water_remaining // 2)`; water decremented per stage | yes |
| protein_processing_ii | `transformations = min(current, multinomial(n=available_int))` | yes |
| protein_translocation | greedy loop `break`s when `atp/gtp/h2o_remaining` exhausted | yes |
| replication | `catalytic_atp_events = min(bio, remaining_atp, remaining_h2o)`; `used_dntp = min(need, dntp_available)` | yes |
| replication_initiation | `n_events = min(free_dnaa_adp, atp_pool)`; `min(n_events, floor(available_water))` | yes |
| ribosome_assembly | `n_form = min(rna_limit, monomer_limit, gtp_limit, h2o_limit)`; `gtp_alloc -= n_form*cost` | yes |
| rna_decay | greedy `while` loop `break`s when `water_remaining < required` | yes |
| rna_modification | `limit = min(avail // req)` (avail = allocated substrates) | yes |
| rna_processing | `num_reactions = floor(min(total_rnas, enzyme_limits, substrate_limits))` | yes |
| trna_aminoacylation | `reaction_limits = min(rounded_enzyme_limits, non_enzyme_limits)` | yes |

### Decisive safety conclusion

The invariant **∀ process, ∀ WID: consumption ≤ allocation** holds for all 24
consumers (19 above + 3 CEILING + 2 INERT emit nothing from allocation; AMOUNT=0).
Given that, removing the `min(1.0)` cap is pool-safe by construction:

1. Karr's proportional allocator in oversupply distributes the ENTIRE pool:
   `Σ_p allocation_p(WID) = pool(WID)` (since `allocation = req * pool / Σreq`).
2. Each process consumes `≤ allocation`.
3. Therefore `Σ_p consumption_p(WID) ≤ Σ_p allocation_p(WID) = pool(WID)` → the
   pool never goes negative.
4. Uncapping raises each allocation toward Karr's value; `consume ≤ allocation`
   is preserved (raising a bound cannot violate `x ≤ bound`). The only behavioral
   change is that processes previously starved to `request` by the cap can now
   consume up to their true biology — i.e. move TOWARD Karr.

This proves **safety** (no over-drain / no pool-negative). It does NOT by itself
prove **correctness** (that OC's biology given Karr's allocation reproduces Karr's
per-process consumption) — that depends on faithful enzyme limits / RNG / rate
constants, which is exactly what the L2.1-strict no-hint + L2.2 tests verify.
Hence: static audit = safety proof; regression = correctness confirmation.
