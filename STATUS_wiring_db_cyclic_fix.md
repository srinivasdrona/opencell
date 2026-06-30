# STATUS: Wiring DB cyclic ordering fix

Date: 2026-06-30

## Completed

- Verified the canonical order exception for `tRNAAminoacylation` vs `Translation` from the MATLAB simulation loop anchor.
- Corrected `data/schemas/per_process_wiring/Translation.yaml` so `Translation` now declares `hard_after: [tRNAAminoacylation]` instead of an inverted `hard_before` edge.
- Kept `data/schemas/per_process_wiring/tRNAAminoacylation.yaml` unchanged because it already matched the canonical direction.

## Next

- Validation passed for cyclic ordering: `0 cyclic ordering` in `tmp/validate_after_cyclic.txt`.
- Regenerated `data/schemas/per_process_wiring/_combined.yaml` from the corrected row set.
