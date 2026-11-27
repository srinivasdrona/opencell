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
| CHRSEG-S1-01 | S1 | GTP and H2O are the complete consume set (`ChromosomeSegregation.m:201-207`; OC `karr_chromosome_segregation.py:497-503`). | VERIFIED |
| CHRSEG-S2-01 | S2 | The consume path exists only when the literal event gate opens. | VERIFIED |
| CHRSEG-S3-01 | S3 | GDP, PI, and H are the complete product set (`ChromosomeSegregation.m:208-210`; OC `:473-479`). | VERIFIED |
| CHRSEG-S4-01 | S4 | MATLAB request gating is not-segregated + fully replicated + all enzymes; supercoiling is intentionally added only in `evolveState` (`ChromosomeSegregation.m:179-202`). OC preserves that split (`karr_chromosome_segregation.py:444-520`). | VERIFIED |
| CHRSEG-S4-02 | S4 | Both sides require every one of the five fixture enzymes. OC sets `required_enzyme_wids = list(self.enzyme_wids)` and evaluates all of them (`karr_chromosome_segregation.py:257-259,400-414`). | VERIFIED |
| CHRSEG-S4-03 | S4 | The event is literal and one-shot: MATLAB and OC latch `segregated` and apply the same `gtpCost` vector (`ChromosomeSegregation.m:204-210`; OC `:497-511`). | VERIFIED |
| CHRSEG-S4-04 | S4 | `segregation_progress`, completion/event, and pole fields are derived compatibility projections of the literal boolean, not an independent continuous model (`karr_chromosome_segregation.py:325-372,505-511`). | VERIFIED |
| CHRSEG-S4-05 | S4 | No process-specific `calcFluxBounds` path exists. | VERIFIED |
| CHRSEG-S5-01 | S5 | The five energy species are routed as direct per-WID cytosolic deltas with no compartment merge in this process. | VERIFIED |
| CHRSEG-S6-01 | S6 | OC reads allocated GTP/H2O only and does not fall back to the global pool (`karr_chromosome_segregation.py:486-494`). | VERIFIED |
| CHRSEG-S6-02 | S6 | Production is split into a request-only Process phase, `KarrAllocationStep`, and a post-allocation evolution Step. An eligible cell consumes the grant and segregates in the same `Engine.update(1.0)`. | VERIFIED |
| CHRSEG-S6-03 | S6 | The request phase no longer declares duplicate `enzymes`/`boundEnzymes` leaves; enzyme presence is read from canonical protein/complex stores, eliminating the prior updater conflict. | VERIFIED |

## Aggregate counts

- VERIFIED: 12
- ROW_WRONG: 0
- CODE_DEVIATES: 0
- MISSING: 0

## Implementation fidelity result

- No known ChromosomeSegregation implementation deviation remains on the
  audited request, allocation, transition, stoichiometry, enzyme, and
  shared-store surfaces.

## Documentation corrections completed

- Removed the stale supercoiling-in-request claim.
- Removed the stale optional/OC-only TopoIV claim.
- Removed the stale continuous-projection deviation.
- Closed the one-tick request-to-consumption lag with explicit pre/post
  allocation phases.
- Removed unused duplicate enzyme ports and the updater conflict.
