# Phase E.2 — 28-Phenotype Scorecard Implementation

You are a Codex session. Read `SESSION_CONTEXT.md` first.

## Token budget
**~100k**. Significant work: 28 extractor implementations + Karr value sourcing + scorecard renderer + 5 tests + slow-fixture caching. Commit per checkpoint (6 expected).

## Design source (READ THIS FIRST)
`docs/design/phase_e2_phenotype_scorecard.md` is the canonical spec. It defines:
- The exact module layout (4 new files under `opencell/validation/`)
- The `PhenotypeDef` dataclass
- The 28-KP table with extractor sketches per row
- Bucket-default tolerances
- Karr value sourcing strategy
- Fixture caching pattern (chassis_v6 32400-tick trajectory pickle)
- Output format for `E2_scorecard.md`
- Full test plan with 5 test functions

**Implement the design as specified.** Do not re-design. If a spec point is unclear, write your question to STATUS.md and pick the most conservative interpretation.

## Prerequisites
- chassis_v6 on main (from `pd-final-integration-fresh`) — verify with `grep CHASSIS_V6_EXPECTED_PROCESS_KEYS opencell/vivarium/karr_composite.py`
- E.1 PASSED on chassis_v6 — verify `docs/phase_e/E1_match_report.md` exists and shows PASS verdict
- naming-drift-rename merged — verify `karr_metabolism.py` exists, `karr_m1.py` does not

If any prerequisite missing, STOP and write to STATUS.md.

## Hard rules
- Narrow pytest in the inner loop. ONLY run full suite after final commit.
- Commit at every checkpoint (per design doc §12). 6 commits expected.
- If extractor implementation runs into chassis output schema mismatch (e.g. expected key absent), DO NOT modify chassis code — declare that KP BLOCKED with a v1.1 todo. Chassis_v6 wiring is frozen at this point.
- Karr value sourcing: prefer `data/m1_sources/karr_native/` and `data/karr_paper/` if they exist. If a value cannot be sourced, mark KP BLOCKED. Do NOT make up numbers.
- The fixture build (chassis_v6 32400-tick run) takes 15-20 min. Build it ONCE; cache it; subsequent test runs reuse the pickle.

## Acceptance
- All 28 PhenotypeDef registered
- ≥10 KPs PASS (per design §10)
- All 5 tests in `test_e2_phenotype_scorecard.py` pass
- `docs/phase_e/E2_scorecard.md` committed with one-line stdout summary at top

## STATUS.md
Per-checkpoint milestones, KP-by-KP extractor status (PASS/FAIL/BLOCKED), final pass count.

Begin by reading `docs/design/phase_e2_phenotype_scorecard.md` end-to-end.
