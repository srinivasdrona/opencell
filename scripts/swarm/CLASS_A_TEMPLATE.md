# Swarm Pilot — Class A per-process auditor master prompt template

This is a **template**. The launch script substitutes `{{PROCESS_NAME}}`, `{{PROCESS_PY_PATH}}`, `{{PROCESS_MATLAB_PATH}}`, `{{FIXTURE_MAT}}`, `{{FIXTURE_JSON}}`, `{{FIXTURE_NPZ}}` for each of the 28 instantiations. Process enumeration lives in `scripts/swarm/class_a_targets.json` (authored by launcher).

Each instantiation runs in its own worktree branch `swarm/class-a/{{PROCESS_NAME}}` for parallel safety. The reducer agent aggregates all 28 branch outputs into the single mega-PR.

---

# Swarm Class A — Audit `{{PROCESS_NAME}}`

## Environment & failure-mode contract (read first)

### Tool availability
Windows-with-WSL. Fall back from `rg`/`fd`/`jq`/`gh` to `grep -rn`/`find`/`python -c`/`git+curl`. Missing tool is not a reason to abort.

### Python interpreter (CRITICAL)
```
wsl -e bash -lc "cd /mnt/e/opencell-worktrees/swarm-class-a-{{PROCESS_NAME}} && source /mnt/e/opencell/.venv-wsl/bin/activate && <command>"
```
Never Windows `py -3.12` or `python` — different interpreter, ModuleNotFoundError on `opencell`.

### Commit-or-stop semantics
Blocked for ANY reason → write `STATUS.md` before exit with: (1) what attempted, (2) exact stuck point + error, (3) fallback tried, (4) suggested next move. Silent exits unacceptable.

### Stale STATUS warning
First action: overwrite `STATUS.md` with `# task started <ISO timestamp>` header.

## Branch and worktree
- Worktree: `E:\opencell-worktrees\swarm-class-a-{{PROCESS_NAME}}` / `/mnt/e/opencell-worktrees/swarm-class-a-{{PROCESS_NAME}}`
- Branch: `swarm/class-a/{{PROCESS_NAME}}` (created off `main` at the post-sprint-0 commit)
- Land as a single commit on this branch. Do NOT push, do NOT merge — the reducer will collect all 28 branches into one mega-PR.

## What this task IS

You are auditing **one** Karr 2012 M. genitalium process — `{{PROCESS_NAME}}` — against its MATLAB counterpart. You produce findings (no fixes), invariant tests, a Karr-differential test, and an activity-monitor entry. The goal is to surface bugs that have been masked by integration-level wiring breaks, NOT to fix them.

## What this task IS NOT

- **Not a fix task.** Document bugs in `findings.json`; do NOT modify production code. Modifying or adding tests under `tests/swarm/class_a/` and new files under `opencell/validation/swarm/` IS allowed.
- **Not a multi-process audit.** Stay scoped to `{{PROCESS_NAME}}`. Cross-process concerns (allocator enrollment seam, pipeline graph, etc.) are Class B, intentionally NOT your job.
- **Not a refactoring task.** No restructuring of the process file even if it would be cleaner.

## Source materials

| Source | Path | Purpose |
|---|---|---|
| Python implementation | `{{PROCESS_PY_PATH}}` | THE code under audit |
| MATLAB counterpart | `karr2012/src/+edu/+stanford/+covert/+cell/+sim/+process/{{PROCESS_MATLAB_PATH}}` | Reference; ground truth on math |
| Karr fixture (.mat) | `data/karr_fixtures/per_process/{{FIXTURE_MAT}}` | Per-tick inputs+outputs from MATLAB sim |
| Karr fixture (JSON) | `data/karr_fixtures/per_process/{{FIXTURE_JSON}}` | Schema for the .mat |
| Karr fixture (.npz) | `data/karr_fixtures/per_process/{{FIXTURE_NPZ}}` | Numpy-friendly if present |
| Replay harness | `opencell/validation/replay.py` (sprint0) | Drive 1-tick replay |
| Predicate library | `opencell/validation/predicates.py` (sprint0) | Use in biology-firing test |
| Allocator guards | `opencell/vivarium/karr_allocation_step.py` (sprint0) | Understand current `ASSERT_POSITIVE_COUNTS` contract |

Reference for vEcoli per-process test pattern (read for shape, do NOT copy biology):
- `https://github.com/CovertLab/vEcoli/blob/master/ecoli/processes/protein_degradation.py` — look for `def test_protein_degradation`
- `https://github.com/CovertLab/vEcoli/blob/master/ecoli/library/data_predicates.py` — upstream of sprint0's predicates

## The 5-dimensional checklist

For each dimension, evidence must be specific (`file:line` or `fixture[tick]:key`).

### D1: Activity firing
Does the process actually run when the chassis ticks?
- Is it a `Step` or a `Process`? Are step subclasses registered via `_mark_instance_as_step`? (Bug 1 reference)
- Are its update ports wired in the chassis composer? `grep` for the class name in `opencell/vivarium/composers/` and `opencell/vivarium/karr_chassis_v6.py`.
- Does its `next_update` / `evolve_state` actually mutate state, or only write emit-only diagnostic ports? (Bug 6a reference)

### D2: Allocator enrollment
If this process consumes or produces any shared substrate (anything in the `substrates` port), is it enrolled in `KarrAllocationStep`'s consumer list?
- `grep` for the process name in `KarrAllocationStep.__init__` and its `consumer_processes` list.
- If it writes `substrates` deltas directly (bypassing the allocator), flag Severity = HIGH. (B1 reference; will be addressed in Track A.)

### D3: Karr math fidelity
Spot-check 3 to 5 numerical hot loops in the Python file against the MATLAB counterpart:
- Unit conversion errors (counts vs concentrations vs mole fractions)
- Off-by-one indexing (MATLAB 1-indexed, Python 0-indexed)
- Sign errors in stoichiometry
- Missing terms (Python simplified what MATLAB summed)
- RNG semantics: if random, is seeding consistent with Karr's pattern?

Not expected to verify every line. Pick the highest-risk loops (tight inner loops, matrix arithmetic, molecule-count updates).

### D4: Pipeline integrity
For each port this process reads or writes, does the producer/consumer on the other side actually exist?
- Writes `foo_counts` → who reads it? `grep` the chassis.
- Reads `bar_counts` → who writes it? Does the writer fire BEFORE this process in the schedule?
- Orphan outputs and missing inputs both count as findings.

### D5: Initial state
At `t=0`, does the process start from values matching the Karr fixture's tick-0 row?
- Use the replay harness to load `{{FIXTURE_MAT}}` and inspect tick 0.
- Compare against the process's default config + the chassis's `initial_state`.
- Mismatches at t=0 propagate forever — flag any non-trivial deviation.

## Required output artifacts

All 4 artifacts live in `opencell/validation/swarm/class_a/{{PROCESS_NAME}}/`. Create the directory.

### Artifact 1: `findings.json`

```json
{
  "process_name": "{{PROCESS_NAME}}",
  "audited_at": "<ISO>",
  "audited_against_python_sha": "<git rev-parse HEAD of the process file>",
  "audited_against_matlab_path": "{{PROCESS_MATLAB_PATH}}",
  "findings": [
    {
      "dimension": "D1|D2|D3|D4|D5",
      "severity": "LOW|MEDIUM|HIGH",
      "confidence": "LOW|MEDIUM|HIGH",
      "title": "<short>",
      "evidence_file": "<path>",
      "evidence_line": <int or null>,
      "fixture_evidence": "<fixture_key[tick]=value, or null>",
      "description": "<2-4 sentences>",
      "suggested_canary": "<test that would catch this on regression>"
    }
  ]
}
```

If a dimension has no issues, emit a placeholder with `severity=LOW, title="no findings", description="<one sentence on what you checked>"`. Distinguishes clean audits from skipped ones.

### Artifact 2: `tests/swarm/class_a/test_{{PROCESS_NAME}}_biology_fires.py`

Use `opencell.validation.predicates` + `vivarium.core.composition.simulate_process`:

```python
"""Biology-firing canary for {{PROCESS_NAME}} (swarm pilot Class A).

Asserts that when the process runs for N ticks against a synthetic but
biologically-plausible initial state, the relevant biology actually fires:
monotonicity invariants, non-negativity, stoichiometric balance.
"""
from opencell.validation.predicates import (
    monotonically_increasing, monotonically_decreasing, all_nonnegative,
)
from vivarium.core.composition import simulate_process
# ... import the process under test

def test_{{PROCESS_NAME}}_fires():
    proc = ...
    initial = {...}
    data = simulate_process(proc, {"total_time": 100, "initial_state": initial})
    # Assert at minimum:
    # - one quantity this process is RESPONSIBLE for actually changes
    # - all molecule counts stay non-negative
    # - any conservation law local to this process holds
    ...
```

3 to 5 invariants this process's biology guarantees. Inline-comment each assertion's biological reason.

### Artifact 3: `tests/swarm/class_a/test_{{PROCESS_NAME}}_matches_karr.py`

Use `opencell.validation.replay` for single-tick replay:

```python
"""Karr-differential canary for {{PROCESS_NAME}} (swarm pilot Class A)."""
from opencell.validation.replay import (
    load_per_process_fixture, replay_one_tick, assert_replay_match,
)

def test_{{PROCESS_NAME}}_matches_karr_at_tick_N():
    fixture = load_per_process_fixture("{{PROCESS_NAME}}")
    proc = ...
    actual = replay_one_tick(proc, fixture, tick_index=N)
    expected = {k: fixture.outputs[k][N] for k in [...]}
    assert_replay_match(actual, expected, rtol=..., atol=...)
```

Pick `N` from a steady-state region of the original MATLAB sim (100 to 1000 typically). Document tolerance with a comment citing what dominates residual (RNG, FP order, intentional deviation).

If the test cannot pass even at loose tolerance, mark `@pytest.mark.xfail(strict=True, reason="<gap>")` AND log a HIGH-severity D3 finding. xfail only when deviation is genuinely outside tolerance budget.

### Artifact 4: `opencell/validation/swarm/class_a/{{PROCESS_NAME}}/activity_monitor.json`

```json
{
  "process_name": "{{PROCESS_NAME}}",
  "monitors": [
    {
      "observable": "<port.subkey>",
      "expected_state": "should_change_within_window",
      "window_ticks": <int>,
      "biological_justification": "<one sentence>"
    }
  ]
}
```

1 to 3 entries. Each names something that, in a healthy cell over N ticks, this process MUST cause to change. Reducer aggregates all 28 into a global `expected_active_set` — if any go silent at chassis runtime, "beautiful corpse" is happening.

## Verify

```bash
wsl -e bash -lc "cd /mnt/e/opencell-worktrees/swarm-class-a-{{PROCESS_NAME}} && source /mnt/e/opencell/.venv-wsl/bin/activate && python -m pytest tests/swarm/class_a/ -v --timeout=120"
```

Both new tests must run (pass, or xfail with documented reason). Errors block your commit.

## Commit

Single commit on `swarm/class-a/{{PROCESS_NAME}}`:
```
git add opencell/validation/swarm/class_a/{{PROCESS_NAME}}/ tests/swarm/class_a/test_{{PROCESS_NAME}}_*.py
git commit -m "swarm class-a: audit {{PROCESS_NAME}}

5-dimensional audit per swarm pilot scope (audit-and-ratchet phase).
Findings: <N total, H HIGH, M MEDIUM, L LOW>.

Adds:
- findings.json
- test_{{PROCESS_NAME}}_biology_fires.py (<N> invariants)
- test_{{PROCESS_NAME}}_matches_karr.py (1 replay test, tick=N, <pass/xfail>)
- activity_monitor.json (<N> observables)

Findings-only: no production code modified. Bug fixes planned by
reducer's bugs_to_fix.md + operator triage gate.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

Do NOT push. Do NOT merge. The reducer collects all 28 branches.

## STATUS.md output

```markdown
# Swarm Class A — {{PROCESS_NAME}} — STATUS
Started: <ISO>
Completed: <ISO or N/A>

## Findings summary
- D1 (activity firing):   <N> findings (HIGH=<n>, MED=<n>, LOW=<n>)
- D2 (allocator):         <N> findings (...)
- D3 (Karr math):         <N> findings (...)
- D4 (pipeline):          <N> findings (...)
- D5 (init state):        <N> findings (...)

## Artifacts
- findings.json:                   <path>
- test_*_biology_fires.py:         <path> (<N> tests, <pass count>)
- test_*_matches_karr.py:          <path> (<pass/xfail>, tick=<N>, tol=<rtol>)
- activity_monitor.json:           <path> (<N> observables)

## Commit SHA: <sha>

## Notes for the reducer
- <cross-process patterns the reducer should weigh in class_b_scope_proposal>
- <uncertainties or coin-flips made>

## Blockers / follow-ups
- <none, or list>

## Progress log
- <ISO> task started
- ...
```

## Discipline reminders
- **Findings only. No fixes.** If editing `opencell/vivarium/karr_<process>.py`, STOP and revert.
- **Stay scoped to {{PROCESS_NAME}}.** Cross-process concerns are Class B.
- **No new infrastructure.** Use sprint0's `predicates`, `replay`, existing test conventions.
- **Empty findings are valid.** A clean audit beats padded findings.
