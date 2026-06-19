# Phase E-final — v1.0 Release

You are a Codex session. Read `SESSION_CONTEXT.md` first.

## Token budget
**~60k**. CHANGELOG assembly + release notes draft + README polish + tag/release ops. ~3 commits + 1 tag.

## Design source (READ FIRST)
`docs/design/phase_e_final_release_gate.md` defines:
- 7 hard gates (G1-G7) — ALL must pass; FAIL any one → no tag
- Release artifact assembly (CHANGELOG, RELEASE_NOTES, README quickstart)
- Tag + GitHub Release commands
- Soft gates (blog, PyPI, methods paper) — non-blocking
- Failure handling (write E_final_HOLD.md, no tag)

**Follow the design.** Do not deviate.

## Prerequisites
- `docs/phase_e/E1_match_report.md` exists with PASS verdict
- `docs/phase_e/E2_scorecard.md` exists with ≥10/28 PASS
- `docs/phase_e/E3_discrepancy_log.md` exists with `VERDICT=PROCEED`
- CI green on main: `gh run list --branch main --limit 1 --json conclusion -q '.[0].conclusion'` == `success`

If any prereq missing, STOP. v1.0 cannot ship until all three Phase E reports are committed and CI is green.

## Order
1. Verify G1-G7. STOP on any FAIL. Write report → commit.
2. Assemble CHANGELOG.md
3. Draft RELEASE_NOTES_v1.0.md
4. Polish README.md
5. Commit: "Prepare v1.0.0 release"
6. `git tag -a v1.0.0 -m "..."` + `git push origin v1.0.0`
7. `gh release create v1.0.0 --notes-file RELEASE_NOTES_v1.0.md --latest`
8. (Optional, timeboxed 20min) Draft `docs/blog/v1_0_announcement.md`
9. Write `docs/phase_e/E_final_summary.md`
10. Final commit: "v1.0.0 released"

## Hard rules
- Step 6 + 7 MUST succeed before step 9-10. If `gh release create` fails, revert step 5 commit, write `E_final_HOLD.md`, STOP.
- Soft gates (PyPI, methods paper) are EXPLICITLY OUT OF SCOPE. If you find yourself spending time on them, stop and just defer to v1.1 todos.
- This is a release turn — no behavior changes to opencell code. Only release artifacts.
- CHANGELOG must be human-readable: group by section, drop commit hashes, write in past tense.
- RELEASE_NOTES must include a working install + run snippet that the user can copy-paste.

## Acceptance
- v1.0.0 git tag pushed to origin
- GitHub Release page live with notes
- `docs/phase_e/E_final_summary.md` committed listing all gate results + release URL
- All E_final tests in `tests/release/test_e_final_gates.py` pass (if invoked with `-m release`)

## STATUS.md
Gate-by-gate PASS/FAIL, release URL once created, soft-gate disposition.

Begin by reading the design doc and running G1-G7.
