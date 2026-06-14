# L2.2 chromosome-primary projections — design

Branch: `design/l22-chrom-projections`
Date: 2026-06-14
Operator-authored (codex delegation died on quoting bugs; operator picked up).

## Inputs

- New `Chromosome` serializer: `scripts/matlab/serialize_chromosome_state.m`
  (commit `0ff0bb5`). Captures 11 properties as sparse (positions, strands, values, shape) triples per tick.
- Verified-real chrom smoke: `data/m1_sources/karr_native/per_process_traces_chrom_smoke/DNASupercoiling_10ticks.mat`. Showed real per-tick deltas (fork advance 500 bp / 4 ticks, linkingNumbers updating at fork positions).
- SUT inspection (4 .m files in `data/m1_sources/.../+process/`).

## What each process WRITES to chromosome state (from SUT grep)

### DNASupercoiling
- Primary write: `c.linkingNumbers = CircularSparseMat(...)` (`DNASupercoiling.m:503`).
- Reads only: monomerBoundSites, complexBoundSites, damagedSites.

### DNADamage
- Calls `this.chromosome.setSiteDamaged(...)` (`DNADamage.m:559`) which mutates ONE of `{gapSites, abasicSites, damagedSugarPhosphates, damagedBases, intrastrandCrossLinks, strandBreaks, hollidayJunctions}` depending on the damage-type enum. All 7 fields are possible primary writes; in any single tick typically 1-2 of them move.

### Replication
- `c.setRegionUnwound(...)` (`Replication.m:658-659, 904-905`) — modifies `polymerizedRegions`.
- `c.setRegionPolymerized([leadingPos; 1 2]', ...)` (`Replication.m:935-936`) — replication-fork advance, modifies `polymerizedRegions`.
- Does NOT directly write `linkingNumbers` (those are derived/updated by DNASupercoiling).

### DNARepair
- `c.damagedBases(...) = 0/iMet` (`DNARepair.m:824-825, 972`) — clears damage / sets methylation.
- `c.abasicSites(...) = 0/1` (`DNARepair.m:973`) — toggles BER intermediates.
- `c.strandBreaks(...) = 1` (`DNARepair.m:1009, 1019, 1048, 1075`) — creates SSBs during BER nick stage.
- `c.damagedSugarPhosphates(...) = 0` (`DNARepair.m:1010, 1020, 1047, 1074`) — clears damaged sugar-phosphates.
- `c.gapSites(...) = 1` (`DNARepair.m:1049, 1076`) — creates gaps during repair.

## Dynamics evidence (from DNASupercoiling 10-tick smoke, seed 0)

Per `bin\oc-py.cmd` inspection of `per_process_traces_chrom_smoke/DNASupercoiling_10ticks.mat`:

- `linkingNumbers`: tick 0 → 1 nonzero (pos=1, strand=1, val=51931). Tick 5 → 3 nonzero (pos=334+579766 strand 1, pos=334 strand 2 — replication fork advancing). Tick 9 → 3 nonzero (pos=834+579266 strand 1, pos=834 strand 2). **Field is dynamic**: per-tick deltas in count + value, tracks fork progression.
- `polymerizedRegions`: tick 0 → 1 nonzero ([1, 1]=580076 = full chromosome length). Tick 5 → 3 nonzero. Tick 9 → 3 nonzero. **Field is dynamic**: tracks replicated region length per strand.
- `monomerBoundSites`, `complexBoundSites`: 1-3 nonzero entries per tick, dynamic (protein-DNA binding/unbinding).
- All damage fields (strandBreaks, gapSites, abasicSites, damagedBases, intrastrandCrossLinks, hollidayJunctions): 0 nonzero across all 10 ticks (DNASupercoiling doesn't write damage; seed 0 baseline has no damage events).

## Projection proposals

All proposals follow the same naming convention: `<chromosome_field>.<aggregate>`
where aggregate is one of:
- `delta_nnz`: how many entries changed between before/after for this tick
- `delta_value_sum`: sum of value-deltas for changed entries
- `delta_value_sum_strand_1` / `_strand_2` / `_strand_3` / `_strand_4`: per-strand sum for processes where strand-leading-vs-lagging matters
- `event_present`: boolean (any change at all this tick)

### 1. DNASupercoiling — NEW

```yaml
primary_projection: [linkingNumbers.delta_value_sum, linkingNumbers.delta_nnz]
primary_distance: per_component_scaled
```

**Justification:**
- `linkingNumbers` is the ONLY field DNASupercoiling writes directly (`c.linkingNumbers = ...` line 503).
- `delta_value_sum` captures the magnitude of LK change per tick (how many supercoils were added/removed by topoisomerase action).
- `delta_nnz` captures whether the change is concentrated (1 region) or spread (multiple regions affected).
- `per_component_scaled` because event_density: moderate and the two components have different natural scales (sum can be ±10⁴, nnz is small int).
- Closed-form-dominant: NO — DNASupercoiling has a true randperm + half-up branch (catalog note line 188), so we expect honest stochastic variance.

### 2. DNADamage — NEW

```yaml
primary_projection: [damage_event_present, damagedBases.delta_nnz, abasicSites.delta_nnz, strandBreaks.delta_nnz, damagedSugarPhosphates.delta_nnz, intrastrandCrossLinks.delta_nnz, hollidayJunctions.delta_nnz, gapSites.delta_nnz]
primary_distance: hurdle_event_rate_plus_conditional_scaled_distance
```

**Justification:**
- DNADamage's `setSiteDamaged` mutates one of 7 fields depending on damage type. To avoid the gate becoming insensitive to any single damage-type drift, gate per-field deltas.
- `damage_event_present` is the hurdle indicator (did ANY damage occur this tick); event_density=sparse means most ticks are zero.
- The 7 per-field `delta_nnz` components are the conditional-on-event distance.
- `hurdle_event_rate_plus_conditional_scaled_distance` exactly matches the pattern used for DNARepair (the structurally analogous sparse-events process).
- No closed-form path; honest stochastic via independent reactions per the catalog rationale.

### 3. Replication — REPLACE

```yaml
# BEFORE (designed against placeholder-chromosome assumption)
primary_projection: [delta_fork_position_bp.left, delta_fork_position_bp.right, replication_state, replication_complete_fired_this_tick]
primary_distance: per_component_scaled

# AFTER (real polymerizedRegions data now available)
primary_projection: [polymerizedRegions.delta_value_sum_strand_1, polymerizedRegions.delta_value_sum_strand_2, polymerizedRegions.delta_value_sum_strand_3, polymerizedRegions.delta_value_sum_strand_4, polymerizedRegions.delta_nnz]
primary_distance: per_component_scaled
```

**Verdict: REPLACE.**

**Justification:**
- The previous projection ASSUMED chromosome data was unusable and proposed synthesizing fork positions from substrate (NTP) consumption: `floor(max(0, ATP_before - ATP_after) / 2)` on elongation ticks. That synthesis is now obsolete — `polymerizedRegions` carries the actual fork state.
- `polymerizedRegions` values ARE the polymerized region lengths per (position, strand). Strand 1 is leading (right fork), strand 2 is lagging (right fork), strands 3-4 are the left fork pair. Per-strand sums preserve the asymmetry between leading and lagging synthesis.
- `delta_nnz` captures fork-splitting events (when a single region splits into multiple as replication proceeds past a binding site).
- `replication_state` and `replication_complete_fired_this_tick` from the prior design were Replication-process-internal flags, not chromosome state — they map cleanly onto whether `polymerizedRegions.delta_value_sum_total > 0` and whether the sum has reached `2 * chrLen`. Both are now redundant with the per-strand sums.
- `per_component_scaled` retained for the same reason as the prior design: 4 per-strand components + 1 count have different natural scales.

### 4. DNARepair — REPLACE

```yaml
# BEFORE
primary_projection: [repair_event_present, repair_count_by_pathway.ber_delta, repair_count_by_pathway.ner_delta, repair_count_by_pathway.hr_delta, repair_count_by_pathway.nhej_like_delta]
primary_distance: hurdle_event_rate_plus_conditional_scaled_distance

# AFTER
primary_projection: [repair_event_present, damagedBases.delta_nnz, strandBreaks.delta_nnz, gapSites.delta_nnz, abasicSites.delta_nnz, damagedSugarPhosphates.delta_nnz]
primary_distance: hurdle_event_rate_plus_conditional_scaled_distance
```

**Verdict: REPLACE.**

**Justification:**
- The previous `repair_count_by_pathway.<ber|ner|hr|nhej_like>_delta` projection assumed those pathway counts could be synthesized from substrate deltas alone. The DNARepair SUT doesn't actually expose pathway-level counts as state — they were inferable from the BER/NER/HR/NHEJ enzyme activity, but only via fragile substrate-delta inversion.
- Now we have direct chromosome state: `damagedBases` count drops as BER/NER clear lesions, `strandBreaks` and `gapSites` increase as BER incises and excises, `abasicSites` toggle through the BER intermediate state, `damagedSugarPhosphates` clear during the repair cycle. These 5 fields are the natural per-tick signature of repair activity.
- `repair_event_present` retained as the hurdle indicator (any chromosome state change at all this tick).
- `hurdle_event_rate_plus_conditional_scaled_distance` retained — DNARepair is event_density:sparse, same structural shape.

## Catalog patch (4 entries)

See commit on this branch.

## Open questions / known limitations

1. **DNADamage smoke not run yet.** Dynamics evidence is from SUT inference only. The proposed 8-component projection may shrink after smoke shows some fields are always 0 (e.g. `hollidayJunctions` is canonically a homologous-recombination state, may not be written by DNADamage's setSiteDamaged path). Wiring delegation should drop trivially-zero components from the projection.

2. **DNARepair smoke not run yet.** Same — `damagedSugarPhosphates` may move trivially-rarely; could drop if smoke shows 0/50 seeds touch it.

3. **Replication chromosome side-effects.** Replication's `setRegionPolymerized` MAY trigger downstream `linkingNumbers` updates via DNASupercoiling-process side-effects. If so, Replication's smoke may pick up linkingNumbers deltas not directly attributable to it. **Recommendation:** if this shows up as cross-contamination during smoke, restrict Replication to `polymerizedRegions.*` projection components only (drop any linkingNumbers cross-talk).

4. **Strand convention.** I assumed strands 1-2 = right fork (leading+lagging), strands 3-4 = left fork. This is from reading `leadingStrandIndexs = [1 4]` and `laggingStrandIndexs = [3 2]` in Replication.m line 226-227. Wiring delegation should double-check by inspecting nnz progression on strands 1+4 (leading) vs 2+3 (lagging) in the chrom smoke once MATLAB finishes the Replication seeds.

5. **closed_form_dominant.** None of the 4 chromosome-primary processes are closed-form-dominant per their SUT designs:
   - DNASupercoiling: randperm + half-up branch.
   - DNADamage: independent stochastic reactions per damage type.
   - Replication: Poisson Okazaki + randperm queue.
   - DNARepair: rand>0.5 branch in setSiteDamageRepair selection.

   So none of them should be promoted to `closed_form_dominant: confirmed` preemptively. Smoke should produce real W1 with seed_noise floor.

## Recommendation for follow-up

When MATLAB completes the full re-extract, fire 4 wiring delegations in 2 pairs:

1. Pair A (codex + kimi): DNASupercoiling on codex, DNADamage on kimi.
2. Pair B (after A merges): Replication on codex, DNARepair on kimi.

Each wiring delegation gets the catalog block as input (verbatim) plus the worked
example of `_project_metabolism_substrate_cube` from main, and is told NOT to
redesign the projection — only implement.
