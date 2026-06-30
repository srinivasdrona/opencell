# STATUS: Wiring DB Cross-Row Validation

Date: 2026-06-30

## Completed

- Ran `scripts/build_wiring_db.py --validate-only` against the merged 28 per-process wiring rows.
- Regenerated `data/schemas/per_process_wiring/_combined.yaml` from the current row set.
- Added `scripts/inspect_wiring_db.py` to compute per-row coverage, provenance, audit-hook, dependency, and roster summaries.
- Wrote `docs/phase_f/WIRING_DB_SUMMARY_2026-06-30.md`.
- Captured validator output in `tmp/wiring_db_validate_only.txt`.

## Key Results

- Coverage: 28/28 process rows present.
- Schema version: all rows declare `schema_version: 1.0`.
- Schema date: only `Metabolism` declares `schema_date: 2026-06-29`; the other 27 rows are missing `schema_date`.
- Provenance: 4 rows have complete required provenance fields (`Metabolism`, `ProteinProcessingI`, `Translation`, `tRNAAminoacylation`).
- Audit hooks: A1/A2/A3/A4 are surfaced on all 28 rows; A3b (consumption-clip mention) is 0/28.
- Cross-row consistency: 53 reciprocal dependency mismatches, 2 cyclic ordering violations, 0 missing canonical rows.
- Row-level validation issues remain for missing `schema_date`, incomplete provenance, malformed unit-conversion anchors in `FtsZPolymerization` and `ProteinModification`, and compartment-routing mismatch booleans in `TerminalOrganelleAssembly`.

## Follow-Up

- P0: fix row-level validation failures before calling the DB authoritative.
- P1: reconcile reciprocal dependency mismatches across process owners.
- P2: normalize schema-date and deviation handling once the blocking row issues are cleared.

