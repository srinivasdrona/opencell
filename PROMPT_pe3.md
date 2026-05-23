# Phase E.3 — Discrepancy Analysis & Disposition

You are a Codex session. Read `SESSION_CONTEXT.md` first.

## Token budget
**~40k**. Mostly parsing + classification + writing. Minimal new code (~150 lines in `discrepancy_analysis.py`). 4 commits expected.

## Design source (READ FIRST)
`docs/design/phase_e3_discrepancy_analysis.md` defines:
- The `Discrepancy` dataclass + `Hypothesis` / `Disposition` literals
- The 7-rule classification heuristics (first match wins; overrides allowed with documented evidence)
- FIX-NOW handling (queue follow-up branches; don't fix in this turn)
- BLOCK-RELEASE conditions
- v1.1 todo emission into `opencell_tasks.db` (with schema migration if needed)
- Output format for `E3_discrepancy_log.md`
- 5 test functions

**Implement as specified.** Do not re-design.

## Prerequisites
- `docs/phase_e/E1_match_report.md` exists with PASS verdict
- `docs/phase_e/E2_scorecard.md` exists with N/28 PASS where N ≥ 10
- `opencell_tasks.db` accessible (path: repo root)

If missing, STOP. E.3 cannot run without E.1 + E.2 outputs.

## Hard rules
- This turn is ANALYSIS-ONLY. Do NOT fix any flagged discrepancy in the same turn. FIX-NOW dispositions become queued follow-up branches (named `agent/pe-3-fix-<source>`); they're documented but not executed.
- Use the 7-rule classifier as default; you MAY override per-row with documented evidence in `hypothesis_evidence`.
- Every DEFER-TO-V1.1 row MUST result in a real INSERT into `opencell_tasks.db`. Verify by reading back.
- 0 BLOCK-RELEASE is the happy path. If you classify anything as BLOCK-RELEASE, also write a remediation recommendation; the release is gated until resolved.
- Narrow pytest only.

## Acceptance
- Every FAIL from E.1+E.2 has a row in `E3_discrepancy_log.md`
- 0 BLOCK-RELEASE rows (else release blocked)
- All DEFER-TO-V1.1 rows have corresponding `opencell_tasks.db` entries with `milestone='v1.1'`
- All 5 tests in `test_e3_discrepancy_analysis.py` pass
- Verdict line on first line of report: `E3 ACCEPT=N FIX=M DEFER=K BLOCK=0 VERDICT=PROCEED`

## STATUS.md
Milestones per the design's commit checkpoints (skeleton, log written, todos emitted, tests pass).

Begin by reading the design doc end-to-end, then parse E1 + E2 reports.
