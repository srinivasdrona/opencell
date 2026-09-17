# TranscriptionalRegulation Semantic Audit

Process: `TranscriptionalRegulation`
Authority: primary `TranscriptionalRegulation.m`, current
`karr_transcriptional_regulation.py`, and chassis topology.
Scope: strict documentation completeness.

## Classification correction

TranscriptionalRegulation is **stochastic**, not deterministic. MATLAB selects
free promoter sites through affinity-weighted random chromosome binding
(`TranscriptionalRegulation.m:348-379`). OC implements the same weighted random
binding family with explicit chromosome RNG handling
(`karr_transcriptional_regulation.py:1340-1570`). This process therefore
requires stochastic/distributional fidelity evidence.

## Claim table

| Claim ID | Category | Documented claim and evidence | Verdict |
|---|---|---|---|
| TR-S1-01 | S1/S3 | Both consume and produce substrate sets are empty; this process updates binding/fold-change state rather than substrate stoichiometry. | VERIFIED |
| TR-S4-01 | S4 | MATLAB and OC both perform affinity-weighted random binding among accessible free sites; the row now explicitly classifies the process as stochastic. | VERIFIED |
| TR-S4-02 | S4 | Current OC includes polymerization, third-party footprint, damage, and self-overlap accessibility checks; the old “missing accessibility gate” audit claim is stale (`karr_transcriptional_regulation.py:1340-1467`). | VERIFIED |
| TR-S4-03 | S4 | OC retains site-by-copy occupancy for both chromosome columns in `tf_bound_promoters`, matching MATLAB's two-column site surface (`TranscriptionalRegulation.m:405-407`; OC `:719-727,1577-1587,1632-1640`). | VERIFIED |
| TR-S4-04 | S4 | OC's column-0 fold-change product and `otherActivities` multiplier match the corresponding MATLAB formula for that column (`TranscriptionalRegulation.m:381-399`; OC `:1597-1629`). | VERIFIED |
| TR-S5-01 | S5 | MATLAB emits an `nTU x 2` fold-change matrix, while OC emits one scalar per TU from column 0 (`TranscriptionalRegulation.m:383-399`; OC `:1599-1603,1657-1659`). | CODE_DEVIATES |
| TR-S5-02 | S5 | MATLAB writes newly bound TF footprints into shared chromosome occupancy through `bindProteinToChromosome`; OC updates its own `tf_bound_promoters` but not shared monomer/complex bound-site arrays. | CODE_DEVIATES |
| TR-S5-03 | S5 | Production topology maps only `protein`, `complex`, `tf_binding`, and `tx_rate_fold_change` (`karr_composite.py:2071-2076`). It omits `chromosome`, authoritative `tf_bound_promoters`/`bound_tfs`, and `enzymes`/`boundEnzymes` writeback, so the chassis does not supply or persist the implemented binding state surfaces. | CODE_DEVIATES |
| TR-S6-01 | S6 | MATLAB has an identically zero request hook; OC omits the request-calculator. The row correctly treats this allocator difference as structural/resource-equivalent. | VERIFIED |
| TR-S6-02 | S6 | MATLAB's binding draws use the shared chromosome randStream. OC autonomous execution uses a continuously advancing local stand-in; only replay with a per-tick ledger restores Karr's interleaved stream position (`karr_transcriptional_regulation.py:690-717`). | CODE_DEVIATES |
| TR-S6-03 | S6 | MATLAB performs a binding sweep during `initializeState`; OC first binds during normal `next_update` (`TranscriptionalRegulation.m:325-331`). | CODE_DEVIATES |
| TR-S6-04 | S6 | No process-specific `calcFluxBounds` or scheduler-order edge exists. | VERIFIED |

## Aggregate counts

- VERIFIED: 7
- ROW_WRONG: 0
- CODE_DEVIATES: 5
- MISSING: 0

## Open implementation deviations

- Autonomous RNG stream provenance differs from Karr's shared/interleaved
  chromosome stream.
- Production topology omits chromosome, authoritative binding state, and
  enzyme/bound-enzyme writeback ports.
- TF footprints are not written back to shared chromosome occupancy.
- Downstream fold-change collapses MATLAB's two columns to chromosome copy 0.
- No MATLAB-equivalent t=0 pre-binding sweep.

## Documentation corrections completed

- Removed the deterministic implication and recorded affinity-weighted random
  binding.
- Removed the stale accessibility omission.
- Separated two-column site occupancy (implemented) from two-column downstream
  fold-change emission (not implemented).
- Added the production topology/state-surface defect.
- Replaced derived-source provenance with the primary MATLAB source.
