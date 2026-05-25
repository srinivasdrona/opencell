# Track A4 L3 Vector Completeness Summary

## Scope
- Completed only in the requested paths: `karr_dna_supercoiling.py`, `karr_protein_translocation.py`, `karr_request_calculators.py`, `karr_composite.py`, and tests.
- No allocator helper/L5 changes, no key renames, no new process enrollments.

## DNASupercoiling
- Substrate IDs added to request vector: `H2O`.
- Substrate IDs added to consumer enrollment: `H2O`.
- Core edits:
- `opencell/vivarium/karr_dna_supercoiling.py`: fixture parsing and WID wiring for water (`substrateIndexs_water`), request/allocated schema now includes `H2O`, event budget now uses `min(allocated ATP, allocated H2O)`, and substrate deltas now include `H2O` consumption 1:1 with ATP hydrolysis.
- `opencell/vivarium/karr_composite.py`: supercoiling allocator enrollment now `[ATP, H2O]` and allocation substrate universe includes `H2O` for this process in the v6 builder.
- Stoichiometry source:
- Karr hydrolysis semantics already used in process (`ATP -> ADP + Pi`); this change adds the missing hydrolysis water co-substrate at 1:1 ATP:H2O.

## ProteinTranslocation
- Substrate IDs added to request vector: `GTP`, `H2O` (alongside existing `ATP`).
- Substrate IDs added to consumer enrollment: `ATP`, `GTP`, `ADP`, `GDP`, `PI`, `H2O`, `H`.
- Core edits:
- `opencell/vivarium/karr_protein_translocation.py`: fixture parsing now loads all 7 substrate WIDs plus `SRP_GTPUsedPerMonomer`; strict allocated-resource reads now used for ATP/GTP/H2O (no allocated-zero fallback); `next_update` now emits:
  - `ATP` negative, `ADP` positive
  - `GTP` negative, `GDP` positive (SRP pathway)
  - `H2O` negative
  - `PI` positive
  - `H` positive
- `opencell/vivarium/karr_request_calculators.py`: translocation request calculator now requests ATP+GTP+H2O.
- `opencell/vivarium/karr_composite.py`: translocation allocator enrollment now uses full 7-channel vector in both chassis enrollment blocks touched in this worktree.
- Stoichiometry source:
- `docs/karr_extracts/process/22_ProteinTranslocation.md:122-125`:
  - step 1 includes ATP+GTP requirement,
  - step 3 updates ATP/GTP/ADP/GDP/Pi/H2O/H+.

## Tick-level Mass-Balance Sanity
- DNASupercoiling hydrolysis cycle now tracks ATP and H2O co-consumption with ADP+Pi production (ATP:H2O = 1:1 for each ATP hydrolyzed).
- ProteinTranslocation hydrolysis cycles now track:
- ATP branch: `ATP + H2O -> ADP + Pi + H`
- GTP branch: `GTP + H2O -> GDP + Pi + H`
- Combined per tick: consumed substrates (`ATP`, `GTP`, `H2O`) and produced products (`ADP`, `GDP`, `PI`, `H`) have consistent signs and magnitudes for hydrolysis accounting.

## Tests Added
- `tests/integration/test_dna_supercoiling_h2o_enrollment.py`
  - asserts request vector includes `H2O`
  - asserts allocator grants `H2O`
  - asserts process consumes `H2O` with ATP-coupled sign and 1:1 magnitude
- `tests/integration/test_protein_translocation_full_vector.py`
  - asserts all 7 substrate channels are enrolled for translocation
  - asserts signed deltas: ATP/GTP/H2O negative, ADP/GDP/PI/H positive

## Verification
- Targeted tests:
  - `py -3.12 -m pytest tests/vivarium/test_karr_dna_supercoiling.py tests/vivarium/test_karr_protein_translocation.py tests/integration/test_dna_supercoiling_h2o_enrollment.py tests/integration/test_protein_translocation_full_vector.py -q`
- Required unit suite:
  - `py -3.12 -m pytest tests/unit -q --ignore=tests/gates`
  - Result: `354 passed, 11 skipped`.

## Additional L3 Gaps Observed During This Sweep
- No new L3 allocator-vector gaps were introduced or expanded in touched scope.
- Existing non-scope items in allocator audits (outside DNASupercoiling/ProteinTranslocation) were not modified here.