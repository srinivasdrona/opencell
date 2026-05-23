# PROMPT — Audit: Bypass-with-Implicit-Precondition Patterns

## Context

OpenCell is a Python whole-cell model on `vivarium-core`. We just found a
catastrophic substrate cascade caused by an implicit-precondition failure:

- `karr_transcription_v3` and `karr_translation_v3` deliberately bypass
  `KarrAllocationStep` (defensible architectural choice given their internal
  kinetic machinery)
- That bypass was safe **only if** `karr_metabolism` produced NTPs/AAs at
  matching rates
- `karr_metabolism` never emitted substrate deltas
- Result: ungated consumption + no production = pools go negative

The **pattern** is: "Module X has its own internal accounting / availability
checks, so it doesn't need to participate in shared bookkeeping mechanism Y."
Such decisions are often defensible in isolation, but every one of them
carries an **implicit precondition** about what the partner module(s) must do.
When the precondition silently fails, the bug is catastrophic and invisible
to local unit tests.

Your job is to find every other place in the OpenCell codebase where this
pattern occurs.

## Read these for context first

- `E:\opencell-worktrees\substrate-leak-diagnosis\STATUS.md` — the original
  cascade finding
- `E:\opencell-worktrees\substrate-leak-diagnosis\docs\diagnostics\substrate_leak_report.md` — empirical evidence
- `E:\opencell\opencell\vivarium\karr_composite.py` — chassis builder (read
  `build_karr_chassis_v6` around lines 1700-1920 to understand the wiring
  pattern)
- `E:\opencell\opencell\vivarium\karr_allocation_step.py` — the bypassed
  bookkeeping mechanism

## Investigation scope

Search **only** within these directories (do NOT scan WSL venvs,
node_modules, .git, etc.):

- `E:\opencell\opencell\vivarium\` (all `karr_*.py`)
- `E:\opencell\opencell\` (any other Python modules)
- `E:\opencell\tests\` (for indications of fixture-injection masking)

## Patterns to hunt

For each candidate, report: filepath, line range, pattern type, severity
estimate (HIGH/MED/LOW with reasoning).

### Pattern A — Process emits shared-store deltas but is not enrolled in allocation

Already-known instances (confirm and find more):
- `karr_transcription_v3`: emits NTP deltas direct, not enrolled (KNOWN, being fixed)
- `karr_translation_v3`: emits AA deltas direct, not enrolled (KNOWN, being fixed)

To find more: grep all `karr_*.py` files for `return ... "substrates":` or
`update["substrates"] =` or `update.setdefault("substrates", ...)` and
cross-reference against the `consumer_processes` list at
`karr_composite.py:1362-1391` AND the v6 rebuild at lines 1894-1907.

### Pattern B — Process consumes a substrate it does NOT request

Similar to the `karr_protein_folding` K/MN/NA mismatch found by GPT-5.5
analysis. A process IS enrolled in allocation, but its request calculator
underrequests relative to what its update actually consumes.

To find: cross-reference each enrolled process's request calculator
(`karr_request_calculators.py`) against the wids appearing in negative
deltas in their `next_update` return.

### Pattern C — "Internal state machinery" claims that hide a contract

Comments or docstrings saying things like "this process manages its own X" or
"availability is enforced internally" or "uses Karr's original cost model" —
look for these in karr_*.py files. Each one is a candidate implicit
precondition.

### Pattern D — Test fixtures with magic large numbers

In `tests/`, look for patterns like:
- `state["substrates_allocated"][p.name][...] = 5_000.0` (infinite ATP)
- Per-tick substrate injection in test setups
- Mocked or stubbed `KarrAllocationStep`

These fixtures mask the kind of bug we just hit. Each one is a place where
the unit test does not exercise the realistic flow.

### Pattern E — Producer/consumer pairs where the producer is silent

Look for `update["X"] = {...}` consumer patterns where no process anywhere
emits matching production updates to the same store. Example: if 5 processes
consume `dnaA_complexes` but no process produces them, that's the same class
of bug as our metabolism gap.

### Pattern F — Counters / accumulators that can drift

Any state that only goes one way (only consumed, only produced) without
periodic reset or reconciliation. These can leak silently over long runs.

## Investigation guardrails

1. **READ ONLY.** Do not modify any source files. You may write to your own
   STATUS.md and report file.
2. **Cite specific file:line references** for every finding. Vague "this
   module probably has an issue" is not actionable.
3. **Rank by severity.** A pattern instance that affects 100 molecules/tick
   matters less than one affecting 100,000/tick. Estimate magnitude where you
   can.
4. **Distinguish defensible from bug.** Not every bypass is wrong. If a
   bypass has its precondition actually satisfied, note it as "defensible,
   precondition currently met" rather than as a bug.
5. **Cross-reference against the known fix.** If you find that the in-flight
   `agent/substrate-cascade-fix` work would already address an item, note that
   so we don't double-fix.

## Output

Write a single report to `docs/audits/bypass_precondition_audit.md` in your
worktree. Structure:

1. **Executive summary**: top-N severity-ranked findings
2. **Pattern A findings**: table with filepath, lines, magnitude estimate,
   severity, recommended action
3. **Pattern B findings**: same table format
4. **Pattern C findings**: same
5. **Pattern D findings**: same  (focus on tests/ dir)
6. **Pattern E findings**: same
7. **Pattern F findings**: same
8. **Patterns to add to the catalog**: any pattern types you discover that
   weren't in this list but should be hunted for in future audits
9. **Coverage notes**: what you searched, what you skipped, why

Also write a STATUS.md summary at the worktree root.

## Budget

- **Token budget**: 60k
- **Wall time**: ~60-90 min
- **Files expected to change**: 2 (audit report + STATUS.md). NO source
  modifications.

## Hard guardrails

1. Do NOT modify source files
2. Do NOT run tests
3. Do NOT launch other agents or processes
4. If you find an active leak in flight (not just a pattern instance), STOP
   and add a HIGH-PRIORITY-ALERT section at the top of STATUS.md
5. Coverage is more important than depth — find ALL pattern instances even
   if your magnitude estimates are rough

## Output verification

Before finishing, verify your audit report:
- Every cited file:line actually exists and matches your claim
- Severity rankings are consistent (HIGH > MED > LOW, with reasoning)
- The executive summary at top matches the detail tables below
