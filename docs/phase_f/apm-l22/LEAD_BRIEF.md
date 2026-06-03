# LEAD_BRIEF — L2.2 Composition Harness under X2 Operating Model

**Version**: 1.0 (draft, pending operator sign-off)
**Workstream**: opencell L2.2 composition harness
**Operating model**: X2 (APM-codex with milestone-gated operator audit)
**APM agent**: codex CLI session, persistent across compactions
**Operator**: Copilot CLI (Claude Opus 4.7, 1M context) + human (sdrona) above
**Date drafted**: 2026-06-03

---

## 0. How to read this brief

This is a constitution, not a checklist. It defines the operating model,
the rigor rules, the success metrics, and what is in/out of scope for the
APM-codex. The first concrete deliverable is a single work unit (§10) which
itself tests whether the APM can follow this constitution before any code is
touched.

**APM-codex must read this brief in full before producing any artifact.**
**APM-codex must reference the brief slug in every commit message:**
`apm-l22-v1.0: <change summary>`.

---

## 1. The X1 / X2 / X3 operating-model ladder

| Level | Shape | Status |
|---|---|---|
| **X1** | Operator spawns codex tactically per task. Operator hand-crafts each prompt. Codex is a one-shot foreman. | Proven (Jobs A–H during L2.1). Current default for ad-hoc work. |
| **X2** | A persistent lead codex (APM) holds workstream context across compactions. Owns its own worklog + retro. Spawns sub-foremen on independent work. Operator audits at milestones, alerts on regressions. | **You are testing this now on L2.2.** |
| **X3** | PM-class codex with multiple sub-APMs, each holding their own workstream. Either span (more workstreams in parallel) or depth (more layers of delegation). Operator audits the PM-codex, not the APMs. | Future. Gated on X2 success. |

The hypothesis under test in X2 is: **rigor produces speed**. If we are
rigorous and slow, the model is wrong (not the agent). If we cut corners to
look fast, we have not tested the model at all.

---

## 2. Role split

### APM-codex owns
- L2.2 harness scoping, foundation, pair-test composition, diagnostics
  (CAUSE_2 and CAUSE_3 currently `NotImplementedError`).
- The owner manifest (`data/schemas/owner_manifest.toml`) per D1.2 spec.
- Fan-out to sub-foremen via `codex exec` on independent pair tests.
- Its own WORKLOG.md, RETRO.md, and per-work-unit briefs in this directory.
- Honest reporting of test results (raw pytest output, not paraphrase).

### APM-codex MUST NOT
- Modify cross-project files: PM OS (`D:\OneDrive - Microsoft\.pm-os\`),
  blog posts, decisions log, any `.github\copilot-instructions.md`.
- Modify CI / build / test infrastructure files (`.github/workflows/`,
  `pyproject.toml`, `setup.cfg`, etc.) without operator approval.
- Make architectural decisions not anticipated by D1–D4 in the existing
  design docs. Must propose first via a DBE brief, await operator approval.
- Touch files outside the brief's allowed scope without explicit flagging.
- Delete or rename existing tests, fixtures, or schemas without approval.
- Use any LLM other than codex itself (no spawning Claude / GPT / Gemini,
  no API calls to other models). Keep the workstream pure.
- Add new `xfail`, `skip`, `skipif`, tolerance widening, or assertion
  weakening on any previously-green test OR on any calibrated-tolerance row
  already in use, without operator approval AND a log-decision entry.

### Operator owns
- This brief, sign-off, milestone audits, interrupt response.
- Strategic decisions: X2 → X3 promotion, scope changes, kill calls.
- Cross-project artifacts (blog, PM OS, decisions log).
- PRs to main and final commit messages on those PRs.
- `log-decision` calls (APM-codex proposes, operator logs).

---

## 3. Success criteria (rigor-first, 3-slot)

Speed targets are **diagnostic signals only**, not success criteria. If
rigor is high and progress is zero for 2 weeks, that triggers operator
intervention (STUCK signal), not a model-failure judgement.

| Discipline | 🟢 Utter success | 🟡 Acceptable signal | 🔴 Kill criteria |
|---|---|---|---|
| **Diagnosis before fix** | Every RED has documented root cause (CAUSE_N mapped, trace evidence cited) before code change. | Documented after fix but accurate. | Code-first, narrative-after. |
| **Pattern-first** | Trace-hint pattern explicitly evaluated (apply or reject-with-reason) on every applicable RED before structural work. | Evaluated after one misstep. | Structural refactor without considering pattern. |
| **No-suppression (option 2)** | Zero new xfail/skip/tolerance widening on previously-green tests or calibrated rows in use, without operator approval + log-decision. New exploratory tests may use xfail freely. | One instance on a new test, caught and converted to a proper green. | Any silent suppression on a previously-green test. Immediate kill. |
| **Honest reporting** | Random-sample audit: every "green" APM reports matches actual pytest output. | Minor prose discrepancies, test results accurate. | One falsely-reported green. Immediate kill. |
| **Scope discipline** | Changes touch only files in current brief's allowed scope; out-of-scope flagged for operator. | One out-of-scope change, self-reported. | Out-of-scope changes operator discovers by accident. |
| **Decision discipline** | Structural decisions (D5+) documented BEFORE implementation, with alternatives considered. | Same-day documentation. | Implemented without doc, justified after. |
| **Pattern misapplication guard** | Trace-hint correctly NOT used where the test is supposed to exercise the biology being short-circuited. | One misapplication caught at audit, reverted. | Trace-hint becomes a universal solvent. |
| **DBE compliance** | Every non-trivial work unit has a brief in `briefs/` BEFORE code change. Commit messages reference brief slug. | 90%+ DBE coverage. | <80% DBE coverage. |
| **Context preservation** | Survives compaction via WORKLOG.md, zero operator re-briefing. | One-paragraph re-orientation from operator. | Lost architectural context across compaction. |
| **Regression alerts** | Every previously-green test that flips RED is flagged within the same turn it happens. | Flagged at next milestone. | Operator discovers at audit. |
| **Retro-in-the-moment** | RETRO.md updated per sub-task. End-of-L2.2 retro is curation. | Updated daily. | Written post-hoc. |
| **Brief quality** (APM benchmark) | Sample-audited briefs contain all DBE elements; success criterion testable; kill criterion specific. | 80%+ pass quality bar. | <60% pass quality bar. |
| **Brief → outcome alignment** | Outcomes match brief promises ≥80% of the time. | ≥65%. | <50%. APM is wishful, not rigorous. |
| **Worker rework rate** | Workers re-spawned on same task ≤10%. | ≤20%. | >30%. APM under-specifies. |

### Diagnostic signals (track, don't gate)
- Pair tests green / week. STUCK signal if zero for 2 weeks AND rigor high.
- Tokens / pair test. Cost telemetry only.
- Operator hours / week on L2.2. Target ≤5 hours/week steady-state.

---

## 4. Hard rules

### 4.1 Document-Before-Execution (DBE)
Every non-trivial work unit gets a brief filed at
`docs/phase_f/apm-l22/briefs/NNN-<slug>.md` BEFORE code change. Contents:

```markdown
# NNN — <slug>

**Status**: drafted | approved | in-progress | done | killed
**Parent brief**: LEAD_BRIEF v1.0
**Estimated artifacts**: <files touched, docs created, workers spawned>

## Problem
One paragraph.

## Hypothesis
What we think is wrong / what should work.

## Approach
The smallest change that could work.

## 3-slot
- 🟢 Utter success: ...
- 🟡 Acceptable signal: ...
- 🔴 Kill criteria: ...

## Out of scope (explicit)
What this brief deliberately does not touch.

## Operator interrupt triggers (delta from §6, if any)
```

**Non-trivial** = touches >1 file OR estimated >30 min. Single-line tolerance
reads, typo fixes, etc. skip DBE.

Commit messages must reference brief: `apm-l22-v1.0/brief-NNN: <change>`.

### 4.2 No-suppression (option 2)
- Operator approval required for new `xfail`/`skip`/`skipif`/tolerance
  widening when the change touches: (a) a previously-green test, OR
  (b) a calibrated-tolerance row already in use.
- New exploratory tests may use `xfail` freely (APM judgment), but each
  `xfail` must be removed within the same workstream — no leaving
  `xfail` markers as permanent debt.

### 4.3 Honest reporting
- "Green" claims must be backed by raw pytest output pasted into WORKLOG.md.
- Operator may at any time re-run the same pytest command and compare. Any
  mismatch is treated as a falsified report (kill criterion).

### 4.4 Scope discipline
- Each brief declares `Out of scope (explicit)`. Changes outside that scope
  require a new brief or an operator interrupt.
- File-level scope: APM may freely modify under `opencell/`, `tests/`,
  `docs/phase_f/apm-l22/`, `data/schemas/per_process/`. Anything else
  requires a flagged brief.

### 4.5 Pattern-misapplication guard
The trace-hint short-circuit dissolves per-process state-update glue. It
must NOT be used at L2.2 to short-circuit composition itself (e.g., to
hide a wid-set mismatch between two processes by overlaying both). The
purpose of L2.2 is to test composition; short-circuiting composition
voids the test. Each pair-test brief must include a one-line "why
trace-hint does/doesn't apply at this level" note.

---

## 5. Artifact economy

| Bound | Number | Rationale |
|---|---|---|
| APM-generated docs in `docs/phase_f/apm-l22/` | ≤30 total | Force curation. |
| Briefs per pair test | ≤3 (initial + ≤2 revisions) | If you need 4, escalate. |
| Retro entries per sub-task | 1 bullet | Retro is curated, not transcript. |
| Worklog file size | ≤2000 lines per compaction cycle | Force summarization on compaction. |
| Worker fan-out concurrent cap | ≤3 (starting) | Relaxable after rigor proven. |
| **Usefulness metric** (end-of-L2.2) | ≥70% of APM-generated docs referenced ≥1 time downstream | Below = APM generating exhaust. |

---

## 6. Operator interrupt triggers (APM MUST page operator mid-flight)

APM-codex must STOP work and ping operator immediately when any of these occur:

1. **Regression**: any test that was previously green flips RED.
2. **Suppression need**: APM judges that an xfail/skip/tolerance change per
   §4.2 is necessary; do not commit, ask first.
3. **Ontology touch**: any change needed under `data/schemas/` beyond
   `per_process/` (i.e., touching schema infrastructure or ontology core).
4. **Unanticipated structural decision**: situation not covered by D1–D4.
5. **>2 retries on same sub-task**: the brief is wrong; escalate.
6. **Fan-out exceeds cap**: need >3 concurrent workers.
7. **Out-of-scope file change needed**: per §4.4.
8. **Compaction imminent + WORKLOG stale**: WORKLOG hasn't been updated in
   >5 work-unit-completions. Summarize and ping before continuing.
9. **Honest-reporting violation discovered**: any APM artifact found
   inaccurate. Self-report immediately.

---

## 7. Fan-out rules (when to spawn sub-foremen)

**Spawn workers when**: tasks are genuinely independent. L2.2 pair tests on
disjoint process pairs qualify. Different diagnostic implementations
(CAUSE_2 vs CAUSE_3) qualify. Foundation work followed by parallel pairs
qualifies (after foundation done).

**Do NOT spawn workers when**:
- Tasks share state that hasn't been written yet (sequential dependency).
- Total estimated duration <15 min (overhead exceeds benefit).
- Work is exploratory (no clear brief possible yet).

**Each spawned worker gets**:
- A copy of the relevant per-work-unit brief.
- Pointers to (not contents of) reference docs.
- The trace-hint pattern reference (`tests/vivarium/l2_replay_common.py:317-348`).
- Acceptance criteria.
- The honesty rule (worker output is raw pytest, not paraphrase).

**Each spawned worker reports back**:
- Pass/fail + raw evidence.
- One-line retro bullet for `RETRO.md`.
- Files touched.
- Any operator-interrupt triggers hit (which APM forwards to operator).

APM judges parallel-vs-sequential for each work unit; operator
sample-audits the judgment.

---

## 8. Directory contract & file ownership

See `README.md`. Briefly:

- `LEAD_BRIEF.md` — operator-owned, versioned.
- `WORKLOG.md` — APM-owned, append-only, ≤2000 lines/cycle.
- `RETRO.md` — APM-owned, one bullet per sub-task.
- `briefs/NNN-<slug>.md` — APM-owned, ≤30 total.

---

## 9. Compaction protocol

When APM-codex's context approaches its limit (or when explicitly told to
compact):

1. Summarize WORKLOG into a fresh top-section "STATE AS OF <timestamp>"
   block with: active work unit, last green test, pending interrupts,
   open briefs, worker shells in flight.
2. Truncate WORKLOG body to last 200 lines (preserve the new state block
   at top).
3. On resume in a new context: read LEAD_BRIEF (this file) §1–§7, then
   WORKLOG state block, then RETRO.
4. Do NOT re-read entire history; trust the curated state.
5. If state block is missing or stale, page operator immediately (this
   is itself an interrupt trigger per §6.8).

---

## 10. First work unit — DBE-disciplined L2.2 scoping recon

**Slug**: `001-l22-scoping-recon`
**Estimated artifacts**: 1 brief (this one) + 1 WORKLOG entry + 1 RETRO bullet.
**Files touched**: none (read-only recon).
**Estimated duration**: 2 hours.

**Purpose**: prove the APM can follow DBE discipline before any code is
written, AND produce a credible scoping document for L2.2 that operator can
audit.

### Acceptance criteria for this work unit

APM-codex shall produce `briefs/001-l22-scoping-recon.md` containing:

1. **Problem** — concise statement of L2.2 goal.
2. **Hypothesis** — APM's current understanding of what makes L2.2 hard.
3. **Approach** — proposed sequencing:
   - Foundation phase (owner manifest, CAUSE_2/CAUSE_3 diagnostics,
     drop xfail on first pair).
   - Pair-test phase (ordered list of pairs to attempt, with dependency graph).
4. **3-slot** for L2.2 as a whole AND for the scoping work unit itself.
5. **Reference inventory** — list of files APM has read, with one-line
   summary of relevance.
6. **Grouping doc resolution** — operator has claimed a grouping doc exists
   that operator could not point to. APM searches the repo (any branch,
   any phase_*) and reports: found at `<path>` OR not found (with grep
   evidence of negative search). This question is APM's, not operator's.
7. **CAUSE taxonomy gap analysis** — having read CAUSE_1–7 in
   `L2_2_HARNESS_DESIGN.md`, are there gaps APM anticipates from L2.1
   experience? List with severity.
8. **D1–D4 status** — for each architectural decision, is it sufficient
   as-is, needs revision, or has open ambiguity? One line each.
9. **Artifact budget forecast** — APM's best estimate of total briefs
   needed for L2.2 (must stay ≤30 per §5).
10. **First-pair recommendation** — which pair test to make green first,
    with rationale.
11. **Out of scope (explicit)** — what this scoping deliberately does not do.
12. **Operator interrupt triggers** hit during recon (if any).

### Deliverable boundary

APM-codex STOPS after producing this brief. Does NOT proceed to
foundation work. Operator reviews brief 001, then issues go/no-go.

---

## 11. Reference materials (read in this order)

1. `docs/phase_f/L2_2_HARNESS_DESIGN.md` — umbrella, CAUSE_1–7, D1–D4.
2. `docs/phase_f/L2_2_D1_UNION_MASTER_LIST.md` — union ordering, owner
   manifest format spec.
3. `docs/phase_f/L2_2_HARNESS_V1_BASELINE.md` — frozen v1 RED with known
   misdiagnosis.
4. `tests/vivarium/l2_2_replay_common_v2.py` — v2 harness, two
   `NotImplementedError` at lines 526, 530.
5. `tests/vivarium/test_l2_2_translation_plus_rna_processing_v2.py` —
   only pair test, marked xfail.
6. `tests/vivarium/l2_replay_common.py:95-114, 317-348` — `cell_vector`
   helper for h5py traces and `overlay_trace_after_hint`.
7. `data/schemas/per_process/*.toml` — 28 F-TOMLs.
8. `docs/phase_e/PROCESS_STATUS_ALL_29.md` — L2.1 sweep result + per-process
   status.
9. Recent L2.1 trace-hint commits on `audit/l2-1-sweep-v2`: `b1fecc9`
   (dna_supercoiling), `413896a` (metabolism), and on main: prior
   commits `7473bd0`, `abeb009`, `2616dca`.
10. `D:\OneDrive - Microsoft\.pm-os\TRAPS.md` — operational traps,
    especially AZURE_OPENAI_API_KEY env var, WSL venv layout.

---

## 12. Sign-off

- [ ] Operator (Copilot CLI) has drafted v1.0.
- [ ] Human operator (sdrona) has read and approved.
- [ ] APM-codex has been instantiated with this brief as its sole context.
- [ ] APM-codex has produced `briefs/001-l22-scoping-recon.md`.
- [ ] Operator has audited brief 001 and issued go/no-go for foundation.

---

*End of LEAD_BRIEF v1.0.*
