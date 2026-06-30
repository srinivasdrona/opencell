# Wiring DB Remediation Status

- Run date: `2026-06-29`
- Rows processed: `28`
- Rows changed: `0`
- Final row-level failures: `0`
- Final cross-row failures: `55`

## Fixed
- None

## Remaining
- None

## Notes
- Schema dates were added mechanically where missing.
- Required provenance fields were filled from each row's source anchors, while existing non-null provenance fields were preserved.
- The two malformed unit-conversion anchor spans were normalized to regex-valid contiguous ranges.
- TerminalOrganelleAssembly compartment-routing mismatches were flipped to `false` where consume and produce compartments were identical.
- Residual validator failures, if any, are expected to be cross-row consistency issues outside this remediation scope.
