# OPEN-1 count audit STATUS

started at 2026-05-22 (see git history for exact run start)
updated at 2026-05-22 20:02:00 +05:30

task: Resolve OPEN-1 (D.2 WID count discrepancy: 147 vs 149 vs 151)

counts found:
- source1 (docstring claim): 149 MC + 2 RibAsm = 151
- source2 (d2-stub fixture union): 147 MC + 2 RibAsm = 149
- source3 (live ProteinComplex formationProcesses cross-check): 147 MC + 2 RibAsm = 149
- source2 vs source3 WID-level diff: none

conclusion:
- Canonical for current fixtures is 149 total D.2-owned WIDs (147 + 2).
- No fixture-extraction mismatch detected; discrepancy is docstring/design-claim-side.
- Proposed one-line design fix (not applied): replace "149 + 2 = 151" with
  "147 + 2 = 149 (per live fixtures)".

files changed:
- scripts/audit_d2_wid_count.py
- docs/design/open1_d2_wid_count_2026-05-22.md
- STATUS.md

blockers:
- none
