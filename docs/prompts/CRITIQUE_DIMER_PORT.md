# CRITIQUE_DIMER_PORT — canonical 5-gate critique rubric for dimer-port fix-class

This file is the canonical template for the **external critique** step on any dimer-port bug-class fix (Karr process migrating complex enzyme reads from `protein.counts` → `complex.counts`). Pair it with `FIX_TEMPLATE_DIMER_PORT.md` (which constrains the *fix*) — this file constrains the *critique that gates the fix before merge*.

Default model: `gpt-5.5`. Mini-tier models tend to gloss the multi-hop judgment in Gates 3 and 5; reserve mini for first-pass triage in large fanouts only.

## Inputs to the critique agent

The launching shell must supply:
- **Process name** (e.g., `karr_protein_modification`)
- **Branch + commit SHA** of the fix
- **Diff path** (canonical pre-staged location: `E:\opencell-worktrees\critique-arena\<slug>.diff`)
- **Repo path** (`E:\opencell`)
- **Process module path** (e.g., `E:\opencell\opencell\vivarium\karr_protein_modification.py`)
- **Chassis composite path** (`E:\opencell\opencell\vivarium\karr_composite.py`)
- **All test roots that exercise the process** (see Gate 4 — there are typically THREE):
  - `tests/vivarium/test_<process>.py` (chassis-fixture per-process)
  - `tests/unit/test_<process>_strict_zero.py` (minimal-state no-fallback paranoia)
  - `tests/integration/test_karr_chassis_v6.py` (whole-chassis smoke)

## Reference bug — what Q3/Q5 failure looks like (pp1 finding)

On `pp1-v23`, the external critique caught a real bug the self-verdict missed:
- Line 145-146: process declared its dimer (`MG_106_DIMER`) in BOTH `protein.counts` AND `protein.enzyme_counts` (a side store). Schema split.
- Line 274-281: silent fallback — if read from `enzyme_counts` returned `None`, fell through to `counts` without raising. Builders that didn't seed `enzyme_counts` would silently read 0 from `counts` and mis-step instead of failing loud.
- Q3 (schema completeness): FAIL.
- Q5 (fail-fast): WEAK.
- Remediation: drop the dedicated substore; single source of truth on `complex.counts`; loud `KeyError` on miss.

Every critique on a new dimer-port fix must explicitly probe for the pp1 shape (side-store + conditional fallback).

## The 5 gates

### Gate 1 — Preservation (Q1)
Does the diff edit any pre-existing test assertion **RHS** (the expected value)?
- **Setup-side LHS edits are allowed** (adding a seeded value to the state dict, mocking a port, providing a previously-missing substore like `"complex": {"counts": ...}`).
- **RHS edits are forbidden** unless the prior assertion was provably wrong, in which case the critique must surface the proof.

Output: list every RHS edit (`file:line, before → after`) and judge ALLOWED / VIOLATION.

### Gate 2 — Rule 6 (sibling-builder safety) + Rule 7 (schema completeness)
- **Rule 6**: For every chassis builder that instantiates this process (v3, v4, v5, v6), reconstruct the construction smoke test yourself — do not trust the commit message:
  - `cd E:\opencell; py -3.12 -c "from opencell.vivarium.karr_composite import build_karr_chassis_v3; build_karr_chassis_v3()"`
  - `build_karr_chassis_v4()`
  - `build_karr_chassis_v5(dynamic_bounds=True)`
  - `build_karr_chassis_v6()`
  - Report exit status + any stderr per builder.
- **Rule 7**: For each WID class migrated from `protein.counts` → `protein.complex_counts`, grep the process module for residual reads from the OLD store:
  - `grep -nE "protein\.counts\[['\"](MG_[^'\"]+)['\"]\]" <process_module>`
  - Cross-reference matched WIDs against the WID list the diff added to `complex_counts` ports. Any WID in BOTH = schema split, Q3 risk.
  - Also look for side stores beyond `counts` and `complex_counts` (e.g., `enzyme_counts`, `processed_counts`) — same pattern as pp1's `enzyme_counts`.

Verdict: count == 0 + all 4 builds exit 0 = **STRONG**. Any nonzero or any build failure = **WEAK** or **FAIL**.

### Gate 3 — Schema split / dual-declaration (Q3)
Inspect the process module end-to-end. For every WID handled, does it appear in exactly one schema declaration block, or in multiple? Specifically check for the **pp1 shape**: a side store like `enzyme_counts` declared alongside `counts`/`complex_counts`. Cite line numbers.

Verdict: STRONG / WEAK / FAIL.

### Gate 4 — Tests (mechanical, multi-root)
**CRITICAL**: Run all THREE test roots independently and report each pass/fail count separately. A CLEAN verdict requires all three to be green.

1. **Per-process chassis-fixture**: `cd E:\opencell; py -3.12 -m pytest tests/vivarium/test_<process>.py -q`
   - Uses fully-seeded chassis state via builder helpers.
2. **Strict-zero unit test** (if it exists — check `Get-ChildItem tests/unit/test_<process>_strict_zero.py`): `cd E:\opencell; py -3.12 -m pytest tests/unit/test_<process>_strict_zero.py -q`
   - Uses minimal hand-crafted state. **This is where read-path migrations often regress** because the fix author updates the chassis builder but forgets the strict-zero fixture. The 9-test backfill on the v23 cohort (2026-05-28) was caused by exactly this gap.
3. **Whole-chassis integration**: `cd E:\opencell; py -3.12 -m pytest tests/integration/test_karr_chassis_v6.py -q`
   - End-to-end smoke. Catches integration regressions across all chassis builders.

Verdict: all three green = **STRONG**. Any red or missing = **FAIL** with the failure cited.

If the strict-zero test fails with `KeyError: missing required complex.counts keys`, the fix is **not necessarily broken** — the test fixture may just need LHS seeding (`"complex": {"counts": {wid: 0.0 for wid in process.complex_enzyme_wids}}`). Cite the missing keys and flag as a strict-zero fixture gap (LHS-fix, not RHS-fix) so the integrator can patch it in the same swing.

### Gate 5 — Fail-fast (Q5)
Inspect the read path in the process module. If `complex_counts[WID]` is missing or returns `None`, does the process raise loud (`KeyError`, explicit assertion) or fall through silently (default 0, conditional skip, `or 0` coalesce)?

Specifically check for the **pp1 shape**: a conditional fallback from one store to another (`x = complex_counts.get(wid) or counts.get(wid)` or equivalent). Cite line numbers.

Verdict: STRONG (loud raise on miss) / WEAK (silent fallback or default) / FAIL.

## Output format (terse, machine-parseable)

```
PROCESS: <name>
COMMIT: <sha>
VERDICT: CLEAN | CHANGES-NEEDED

GATE 1 (preservation): ALLOWED | VIOLATION
  <RHS-edit citations or "none">

GATE 2 (rule 6 + rule 7):
  rule 6: v3=<exit>, v4=<exit>, v5=<exit>, v6=<exit>
  rule 7: grep count=<n>, residual WIDs=[...], side stores=[...]
  STRONG | WEAK | FAIL

GATE 3 (schema split): STRONG | WEAK | FAIL
  <cited dual-declarations or "none found">

GATE 4 (tests):
  vivarium per-process: <pass>/<total>
  unit strict-zero: <pass>/<total> (or "not present")
  integration v6: <pass>/<total>
  STRONG | FAIL

GATE 5 (fail-fast): STRONG | WEAK | FAIL
  <cited read-path lines + behavior on miss>

REMEDIATION (if not CLEAN): <specific changes needed>
```

## Discipline rules for the critique agent

- Be terse. No hedging. Cite `file:line` for every claim.
- Do not restate the rubric in the output.
- Do not edit code under critique — your role is verdict only. If you discover a strict-zero LHS gap or similar, flag it under Gate 4 with the proposed LHS patch shape; the integrator will apply it.
- Do not skip Gate 4's strict-zero check on the assumption that the v6 integration suite covers it. It does not. The strict-zero suite uses different fixture shapes.

## When to update this template

- A new failure shape is discovered that none of the 5 gates would mechanically catch → add a Gate or expand an existing one, log a decision in `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md`.
- A new test root is added to the repo that exercises the process → add it to Gate 4's enumeration.
- A new fix-class (not dimer-port) needs a critique → fork this file to `CRITIQUE_<NEW_CLASS>.md`; do not generalize this one in place.
