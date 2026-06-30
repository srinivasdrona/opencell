# Wiring DB Reciprocal Fix Status

- Run date: `2026-06-30`
- Reciprocal mismatches before: `53`
- Reciprocal mismatches after: `0`
- Residual cyclic ordering: `2`
- Missing rows: `0`

## Fixed

- Reconciled the reciprocal wiring mismatches across `25` row files.
- Wrote the triage table to `docs/phase_f/WIRING_DB_RECIPROCAL_TRIAGE.md`.
- Captured the post-fix validator output in `tmp/validate_after_reciprocal.txt`.
- Regenerated `data/schemas/per_process_wiring/_combined.yaml`.

## Manual Review Needed

- `Translation hard_before tRNAAminoacylation`: manual review needed: out-of-scope sibling session.
- `tRNAAminoacylation hard_before Translation`: manual review needed: out-of-scope sibling session.

## Notes

- Bucket A rows removed the deliberate Metabolism asymmetry edges from producer rows.
- Bucket B rows restored shared-metabolite consumers on the consumer side.
- Bucket C rows removed over-claimed producer edges where the consumer row has no direct stoichiometric handoff.
