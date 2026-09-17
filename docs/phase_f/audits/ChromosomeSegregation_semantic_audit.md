# ChromosomeSegregation Semantic Audit

Process: `ChromosomeSegregation`
Authority: primary `ChromosomeSegregation.m`, current
`karr_chromosome_segregation.py`, and current shared-state schemas.
Scope: strict documentation completeness.

## Current implementation status

The former continuous/optional-TopoIV description is stale. Current OC is a
literal one-shot port: it requires all five enzymes, including
`MG_203_204_TETRAMER` (TopoIV), requests the fixture `gtpCost`, checks the
supercoiling and allocation gates, sets `chromosome.segregated = true`, and
applies exact `GTP + H2O -> GDP + PI + H` stoichiometry.

## Claim table

| Claim ID | Category | Documented claim and evidence | Verdict |
|---|---|---|---|
| CHRSEG-S1-01 | S1 | GTP and H2O are the complete consume set (`ChromosomeSegregation.m:201-207`; OC `karr_chromosome_segregation.py:472-478`). | VERIFIED |
| CHRSEG-S2-01 | S2 | The consume path exists only when the literal event gate opens. | VERIFIED |
| CHRSEG-S3-01 | S3 | GDP, PI, and H are the complete product set (`ChromosomeSegregation.m:208-210`; OC `:473-479`). | VERIFIED |
| CHRSEG-S4-01 | S4 | MATLAB request gating is not-segregated + fully replicated + all enzymes; supercoiling is intentionally added only in `evolveState` (`ChromosomeSegregation.m:179-202`). OC preserves that split (`karr_chromosome_segregation.py:449-470`). | VERIFIED |
| CHRSEG-S4-02 | S4 | Both sides require every one of the five fixture enzymes. OC sets `required_enzyme_wids = list(self.enzyme_wids)` and evaluates all of them (`karr_chromosome_segregation.py:257-259,396-410`). | VERIFIED |
| CHRSEG-S4-03 | S4 | The event is literal and one-shot: MATLAB and OC latch `segregated` and apply the same `gtpCost` vector (`ChromosomeSegregation.m:204-210`; OC `:472-485`). | VERIFIED |
| CHRSEG-S4-04 | S4 | `segregation_progress`, completion/event, and pole fields are derived compatibility projections of the literal boolean, not an independent continuous model (`karr_chromosome_segregation.py:309-333,481-491`). | VERIFIED |
| CHRSEG-S4-05 | S4 | No process-specific `calcFluxBounds` path exists. | VERIFIED |
| CHRSEG-S5-01 | S5 | The five energy species are routed as direct per-WID cytosolic deltas with no compartment merge in this process. | VERIFIED |
| CHRSEG-S6-01 | S6 | OC reads allocated GTP/H2O only and does not fall back to the global pool (`karr_chromosome_segregation.py:463-470`). | VERIFIED |
| CHRSEG-S6-02 | S6 | The in-process request reaches allocation, but too late for the same `next_update` call to consume it. Empirical probe: tick-1 request `5`, allocation `10`, process-observed grant `0`; tick-2 process-observed grant `10`. This is a one-tick request-to-consumption lag versus Karr's same-tick request → allocation → evolve contract. | CODE_DEVIATES |
| CHRSEG-S6-03 | S6 | Shared `boundEnzymes` leaves use `accumulate` here but `set` in DNASupercoiling (`karr_chromosome_segregation.py:333-343`; `karr_dna_supercoiling.py:1043-1049`), producing an incompatible-updater warning. | CODE_DEVIATES |

## Aggregate counts

- VERIFIED: 10
- ROW_WRONG: 0
- CODE_DEVIATES: 2
- MISSING: 0

## Open implementation deviations

- ChromosomeSegregation observes the grant generated from its tick-1 request
  only on tick 2.
- The cross-process `boundEnzymes` updater conflict remains open. It is
  separate from, and does not negate, the literal five-enzyme gate/event/stoich
  implementation.

## Documentation corrections completed

- Removed the stale supercoiling-in-request claim.
- Removed the stale optional/OC-only TopoIV claim.
- Removed the stale continuous-projection deviation.
- Added the empirically established one-tick request-to-consumption lag.
- Added the real shared-state updater conflict without misclassifying the
  literal event implementation.
