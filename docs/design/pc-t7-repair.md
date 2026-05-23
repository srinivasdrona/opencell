# Phase C Turn 7 - DNARepair (pc-t7-repair)

**Status**: design ready (Karr-light v1)  
**Estimated wall**: 40 min  
**Karr process**: `Process_DNARepair`

## Primary source references

1. `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/DNARepair.m`
2. `docs/karr_extracts/process/05_DNARepair.md` (task prompt lists `08_DNARepair.md`, but repository extract is `05_DNARepair.md`)
3. `data/karr_fixtures/per_process/DNARepair_flat.mat`
4. `data/m1_sources/karr_native/per_process_traces/DNARepair_100ticks.mat`

## Scope

### In scope (Karr-light v1)

- Implement `opencell/vivarium/karr_dna_repair.py` that repairs `chromosome.damage_sites` emitted by pc-t6 (or pre-seeded by tests).
- Map lesion classes to pathway groups:
  - `abasic_site`, `damaged_base` -> BER
  - `intrastrand_crosslink` -> NER
  - `double_strand_break` -> HR
  - `single_strand_break` and unknown break-like labels -> NHEJ-like fallback
- Per tick, compute pathway capacities from fixture enzyme bounds and available enzyme counts.
- Request ATP + dNTPs (`DATP`, `DCTP`, `DGTP`, `DTTP`) through `KarrAllocationStep` contract.
- Bound repairs by allocated substrate amounts.
- Remove repaired entries from `damage_sites` and emit `repair_count` deltas.
- Emit `repair_count_by_pathway` deltas for BER/NER/HR/NHEJ-like.

### Deferred to v2

- Full DNA-state mechanics across all 8 Karr DNA damage arrays (`abasicSites`, `damagedBases`, `strandBreaks`, etc.).
- Per-site neighborhood/protein-occupancy exclusion rules from `DNARepair.m`.
- Randomized subfunction order parity with MATLAB `evolveState`.
- Explicit DisA binding/unbinding dynamics.
- Restriction/modification submodel.
- NAD/NMN/H2O/H handling for full small-molecule stoichiometry (v1 only enforces ATP+dNTP allocation per task scope).

## Algorithm (v1)

1. Canonicalize `chromosome.damage_sites` into a list of records (`site_id`, `damage_type`, metadata).
2. Bucket sites by pathway.
3. Compute pathway catalytic capacities (events/s) from fixture reaction subsets:
   - BER: `reactionIndexs_BER`
   - NER: `reactionIndexs_NER`
   - HR: `reactionIndexs_HR_dsbr`
   - NHEJ-like: `reactionIndexs_ligation` (ligase-only fallback)
4. Draw desired repairs per pathway from Poisson(capacity * dt), capped by available lesions.
5. Convert desired repairs to substrate requests using pathway ATP costs (from fixture stoich) + dNTP patch lengths:
   - NER length from fixture `NER_UvrABC_IncisionMargin3 + NER_UvrABC_IncisionMargin5 + 1`
   - HR length from fixture `HR_PolA_ResectionLength`
   - BER/NHEJ-like default single-base patch.
6. Read `substrates_allocated.<process>` (fallback to `substrates` when standalone tests run without allocation step).
7. Scale desired repairs down if allocated substrates are insufficient.
8. Select that many damage sites per pathway, remove them from `damage_sites`, emit accumulate deltas:
   - `chromosome.repair_count`
   - `chromosome.repair_count_by_pathway.{ber,ner,hr,nhej_like}`
   - `substrates.{ATP,DATP,DCTP,DGTP,DTTP}` negative deltas
9. Emit next-tick requests based on current desired repair workload.

## State ports and schema

- `chromosome.damage_sites`: dynamic sparse lesion collection; v1 uses `_updater: "set"` to publish repaired-site removal atomically.
- `chromosome.repair_count`: `_updater: "accumulate"`
- `chromosome.repair_count_by_pathway.*`: `_updater: "accumulate"`
- `protein.counts.<enzyme_wid>`: read-only enzyme availability
- `substrates.<wid>`: `_updater: "accumulate"`
- `requests.karr_dna_repair.<wid>`: `_updater: "set"`
- `substrates_allocated.karr_dna_repair.<wid>`: `_updater: "accumulate"`

## Substrate consumption model

Tracked allocation substrates:

- `ATP`
- `DATP`, `DCTP`, `DGTP`, `DTTP`

Per repair event (v1):

- ATP component: derived from fixture stoich contributions of pathway reaction subset on ATP row.
- dNTP component: patch length distributed by fixed fractions (equal quarter split for v1 aggregate).

## Test plan

1. Process instantiates and exposes required pathway + substrate defaults (chassis_v4-compatible tick defaults).
2. One-tick positive repair delta when lesions + substrate allocation are present.
3. Allocation contract honored: insufficient allocation reduces realized repairs and substrate deltas.
4. 100-tick steady-state (empty lesions) matches Karr trace behavior (no net changes within tolerance).
5. No NaN / negative-count regressions in repeated ticks.
6. Pathway routing: mixed lesion types increment expected `repair_count_by_pathway` keys.

## Open questions

1. Task prompt references `docs/karr_extracts/process/08_DNARepair.md`, but repository contains `05_DNARepair.md`.
2. Native `DNARepair_100ticks` trace in current baseline is quiescent (all-zero deltas), so v1 calibrates dynamic rates from fixture enzyme bounds rather than per-pathway nonzero trace fits.
3. pc-t6 lesion payload shape is not yet merged; v1 parser accepts list/dict forms and tests pre-populate directly.
