# Phase E.3 — Discrepancy Analysis & Disposition Design

**Status**: design ready  
**Prereq**: E.1 + E.2 reports committed  
**Branch**: `agent/pe-3-discrepancy-analysis`  
**Wall-time**: 30-45 min Codex (mostly writing; some classification logic + v1.1 todo emission)

## 1. Goal

For every E.1 observable FAIL and every E.2 KP FAIL, produce a structured row in
`docs/phase_e/E3_discrepancy_log.md` containing: what diverged, hypothesized
cause, and disposition for v1.0 release. Emit v1.1 todos for DEFER items.

## 2. Module layout

```
opencell/validation/
  discrepancy_analysis.py    # classify(fail_row) -> Discrepancy, emit_v11_todo(disp)
docs/phase_e/
  E3_discrepancy_log.md      # output artifact
opencell_tasks.db            # extended with v1.1-milestone todos
tests/validation/
  test_e3_discrepancy_analysis.py
```

## 3. Discrepancy dataclass

```python
from dataclasses import dataclass
from typing import Literal

Hypothesis = Literal[
    "karr-light-scope",        # we deliberately reduced this process to light-mode
    "missing-biology",         # whole pathway/process not modeled
    "parameter-drift",         # calibration off — values wrong but mechanism right
    "allocation-timing",       # chassis wiring bug — substrate accounting drifts
    "extraction-bug",          # extractor formula wrong; chassis output is fine
    "biology-beyond-karr",     # we model it but Karr didn't measure it
    "stochastic-noise",        # within run-to-run variation; not a real fail
]

Disposition = Literal[
    "ACCEPT",        # known limit, xfail/qualitative, OK for v1.0
    "FIX-NOW",       # surgical fix in this turn or a same-day follow-up turn
    "DEFER-TO-V1.1", # logged as v1.1 todo, won't gate v1.0 release
    "BLOCK-RELEASE", # release cannot ship until this is resolved
]

@dataclass(frozen=True)
class Discrepancy:
    source: str               # "E1::cell_dry_mass_g" or "E2::KP07"
    bucket: str               # bucket from E.1/E.2 row
    opencell_value: float | str
    karr_value: float | str
    rel_err: float | None
    hypothesis: Hypothesis
    hypothesis_evidence: str  # 1-3 sentence justification
    disposition: Disposition
    fix_now_action: str | None    # only if disposition == FIX-NOW
    v11_todo_id: str | None       # only if DEFER-TO-V1.1
    notes: str = ""
```

## 4. Classification heuristics

Codex applies these in order. First match wins.

1. **bucket == biology-beyond-Karr AND status == qualitative** → `hypothesis=biology-beyond-karr`, `disposition=ACCEPT`
2. **source process is Karr-light** (presence of `_LIGHT_MODE = True` in module, or known-light list: `KarrProteinDecayLight`, the Karr-light flavors of supercoiling/condensation per `karr_execution_plan_2026-05-22.md`) → `hypothesis=karr-light-scope`, `disposition=DEFER-TO-V1.1`
3. **rel_err > 5.0 (>500%)** in a non-incomplete bucket → `hypothesis=allocation-timing` or `extraction-bug`, **`disposition=FIX-NOW`** (this is large enough to point at a bug, not biology)
4. **rel_err between 0.3 and 5.0**, bucket is validation-and-organism-scaling → `hypothesis=parameter-drift`, `disposition=DEFER-TO-V1.1`
5. **rel_err between 0.001 and 0.3**, bucket is opencell-tooling (strict bucket FAIL) → `hypothesis=extraction-bug` (most likely) or `allocation-timing`, `disposition=FIX-NOW`
6. **BLOCKED status** (extractor returned None) → `hypothesis=missing-biology`, `disposition=DEFER-TO-V1.1`
7. **Anything else** → `hypothesis=parameter-drift`, `disposition=DEFER-TO-V1.1`

Codex MAY override these with explicit reasoning per row. Heuristics are defaults,
not mandates. Document any override in `hypothesis_evidence` field.

## 5. FIX-NOW handling

If classification yields `FIX-NOW` for ≥1 discrepancy:
- Codex DOES NOT make the code fix in this turn (E.3 is analysis only)
- Each FIX-NOW becomes a `agent/pe-3-fix-<source>` follow-up branch (queued, not launched)
- The discrepancy log row has `fix_now_action="see agent/pe-3-fix-<source>"`
- Operator decides whether to launch fix-up turns or escalate to BLOCK-RELEASE

If a FIX-NOW remains unfixed at E-final time, it becomes a BLOCK-RELEASE.

## 6. BLOCK-RELEASE conditions

A discrepancy is BLOCK-RELEASE if (and only if):
- It's a FAIL in the opencell-tooling bucket that affects ≥3 other phenotypes (cascade-blocker)
- OR it represents a violation of mass-balance / energy-balance invariants
- OR it's a regression vs E.1 scaffold output (something that used to work, now doesn't)

E.3 is allowed to declare 0 BLOCK-RELEASE items (the happy path). If Codex finds
one, it MUST also document a recommended remediation; release is on hold until
resolved.

## 7. v1.1 todo emission

For each DEFER-TO-V1.1 row, Codex inserts into `opencell_tasks.db` (existing SQLite,
schema unchanged):

```sql
INSERT INTO todos (id, title, description, status, created_at, milestone)
VALUES (
  'v11-pe3-<short-slug>',     -- e.g. 'v11-pe3-kp25-ko-sweep'
  '<phenotype label> v1.1 calibration',
  '<hypothesis_evidence + reproduction recipe>',
  'pending',
  CURRENT_TIMESTAMP,
  'v1.1'
);
```

If `opencell_tasks.db` doesn't have a `milestone` column yet, Codex adds one
(`ALTER TABLE todos ADD COLUMN milestone TEXT`) in the same turn.

## 8. Output artifact

`docs/phase_e/E3_discrepancy_log.md`:

```markdown
# Phase E.3 — Discrepancy Log

**Generated**: <iso-date>  
**Repo HEAD**: <sha>  
**Inputs**: E.1 report (<E1_sha>), E.2 scorecard (<E2_sha>)  

## Roll-up

| Disposition | Count |
|---|---|
| ACCEPT (xfail/qual) | N |
| FIX-NOW | M |
| DEFER-TO-V1.1 | K |
| BLOCK-RELEASE | 0 |

**Verdict**: PROCEED-TO-E-FINAL | BLOCK-PENDING-FIXES

## By hypothesis

| Hypothesis | Count | Bucket spread |
|---|---|---|
| karr-light-scope | N | ... |
| missing-biology | N | ... |
| parameter-drift | N | ... |
| allocation-timing | N | ... |
| extraction-bug | N | ... |
| biology-beyond-karr | N | ... |

## Per-discrepancy detail

### E2::KP07 — mRNA short-horizon stability (opencell-tooling)

- **Diverged**: opencell std/mean = 0.42; Karr expectation < 0.30 (tol = 0.30; rel_err = 0.40)
- **Hypothesis**: extraction-bug
- **Evidence**: visual inspection of trajectory shows a single 100s window included a transient at division event; extractor should exclude division ±50s window.
- **Disposition**: FIX-NOW
- **Fix action**: see `agent/pe-3-fix-kp07-window` (queued)

### E1::fork_position_norm — bulk replication progress
... (per row)
```

One-line stdout summary: `E3 ACCEPT=N FIX=M DEFER=K BLOCK=0 VERDICT=PROCEED`

## 9. Test plan

```python
def test_e3_inputs_present():
    """E.1 and E.2 reports must exist before E.3 runs."""
    assert Path("docs/phase_e/E1_match_report.md").exists()
    assert Path("docs/phase_e/E2_scorecard.md").exists()

def test_e3_all_fails_dispositioned():
    """Every FAIL in E.1 or E.2 has a row in E.3 with explicit disposition."""
    e1_fails = parse_e1_fails()
    e2_fails = parse_e2_fails()
    e3_log = parse_e3_log()
    for fail in e1_fails + e2_fails:
        assert any(row.source == fail.source for row in e3_log), \
            f"{fail.source} missing from E3 log"
        # AND every row has a disposition (no nulls)
    assert all(row.disposition in get_args(Disposition) for row in e3_log)

def test_e3_no_block_release():
    """Happy-path gate: zero BLOCK-RELEASE entries."""
    e3_log = parse_e3_log()
    blockers = [r for r in e3_log if r.disposition == "BLOCK-RELEASE"]
    assert len(blockers) == 0, f"Release blocked by: {[r.source for r in blockers]}"

def test_e3_defer_todos_emitted():
    """Every DEFER-TO-V1.1 row has a corresponding row in opencell_tasks.db."""
    e3_log = parse_e3_log()
    defers = [r for r in e3_log if r.disposition == "DEFER-TO-V1.1"]
    conn = sqlite3.connect("opencell_tasks.db")
    db_v11 = {r[0] for r in conn.execute(
        "SELECT id FROM todos WHERE milestone = 'v1.1'"
    )}
    for row in defers:
        assert row.v11_todo_id in db_v11, f"todo {row.v11_todo_id} not in db"

def test_e3_report_emitted():
    assert Path("docs/phase_e/E3_discrepancy_log.md").exists()
```

## 10. Acceptance criteria

- 100% of E.1/E.2 fails have an explicit disposition
- 0 BLOCK-RELEASE entries (else loop back to fix-up turns before E-final)
- All DEFER-TO-V1.1 entries have rows in `opencell_tasks.db` with `milestone='v1.1'`
- `E3_discrepancy_log.md` committed

## 11. Codex turn brief

Branch: `agent/pe-3-discrepancy-analysis`  
Token budget: 40k (parsing + classification + writing; minimal new code)  
Commit checkpoints:
1. `discrepancy_analysis.py` skeleton (parsers + classifier) → commit
2. Run classifier against E.1+E.2 reports, write E3_discrepancy_log.md → commit
3. Emit v1.1 todos into opencell_tasks.db (schema migration if needed) → commit
4. Tests passing → final commit
