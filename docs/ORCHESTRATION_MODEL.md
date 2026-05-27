# Orchestration Model Progression: Phase 0 → Phase 4

> Cross-project decision logged 2026-05-27 at
> `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` under slug
> `orchestration-model-progression-phase-0-to-4`. This file is the
> repo-side companion with technical detail and worked examples.

## Why this document exists

The OpenCell project's PM-side orchestration model has changed shape
five times across ~3 weeks of active build. Each transition was
**failure-driven** — the prior phase was concretely hitting a wall
that the next phase resolved. Capturing the sequence prevents two
regressions:

1. Reverting to an earlier phase out of habit when codex slots go idle.
2. Skipping ahead to phase 5 (peer PMs) before the coordination cost
   is justified by workload.

## The phases

### Phase 0 — Pure main context (pre-codex)

Single Copilot context, sequential design + cross-model critique rounds
+ initial OpenCell planning. No delegation, no parallel work.

**Born here, survives all later phases**:
- `plan.md` as canonical artifact.
- `DECISIONS.md` as cross-session memory.
- CHECKPOINT.md cadence.
- Operator-confirmation discipline before any code change with
  ambiguous direction.

**Transition trigger to Phase 1**: design stabilized; time to build.
Not a failure — natural lifecycle.

### Phase 1 — Main context for design + critiques + initial infra

Copilot does everything end-to-end: design, prompt-writing, code edits,
test runs, build loops. Single-threaded, no parallelism. Heavy use of
Copilot premium models (Sonnet/Opus) for the full mechanical loop.

**Transition trigger to Phase 2**: prompt-write + execution + test-loop
in one Copilot context burned premium tokens on mechanical work that
didn't need Sonnet/Opus reasoning. The expensive cognition was the
*planning*, not the *typing*.

### Phase 2 — Main + codex sessions for parallel work on one main branch

Codex CLI introduced for mechanical execution. Copilot stays as PM:
writes prompts, reviews STATUS, makes taste calls. Single main branch
for all work; codex sessions cd into the main repo, make changes,
commit, and exit.

**Innovations born here**:
- `delegate-to-codex` skill (single source of truth for codex prompt
  conventions).
- WSL venv mandate (born after ≥4 silent failures of
  `python.exe`-from-PATH).
- STATUS file as the codex↔PM contract.

**Transition trigger to Phase 3**: the 28-process swarm-dead diagnosis
phase. Firing 28 parallel codex sessions against a single main branch
caused constant collisions on shared files (`process_status.md`,
`karr_composite.py`). Two codex sessions writing to the same file
in parallel produced merge conflicts that took longer to resolve than
the underlying work.

### Phase 3 — Kanban model with worktree-per-track (current)

Each codex track gets its own `git worktree add` off a known base
branch (today: `trackA/wave2-base`). Lanes:

| Lane | Purpose | Example tracks |
|---|---|---|
| `biology` | Karr-process fixes, fidelity work | `trackF-trna`, `triage-pp1-fix` |
| `infra` | Tracers, fixtures, build/test infra | `trackB-trajectory-pilot`, `trackB-optionB-flat` |
| `bugs` | Cross-cutting bug fixes | (planned: bugs 8 + 9) |
| `docs` | Documentation, manifests, plans | `docs-matlab-manifest` |

**Innovations born here**:
- `tracks` SQL table (per-session) tracking each worktree's
  branch, PID, status, and lane.
- 4-slot codex ceiling (empirically: more than 4 parallel codex
  sessions saturate the PM's review bandwidth — and Azure compaction).
- "Template-after-lander" discipline (the first member of a fanout
  lands solo; its STATUS becomes the literal template for the rest).
- Worktree base-merge ritual: when sibling branches need to see each
  other's artifacts, merge them into the shared base (`wave2-base`)
  before firing the downstream tracks.

**Transition trigger to Phase 4**: PP1 and PP2 would have collided on
`karr_composite.py:1606` (the enzyme init dict) if fired in parallel
under phase-3 rules. Template-after-lander discipline accidentally
avoided the collision but a generalized rule beats luck. Also the
4-bucket todo state model (`pending/in_progress/done/blocked`) is too
coarse to surface "design ready but waiting for slot" vs "exec done
but test pending" vs "tested but bugs found" — those three are very
different states with very different next-actions.

### Phase 4 — Multi-stage kanban with conflict-pair detection (now forming)

The kanban stages a track passes through:

```
needs-user  →  design-codex  →  design-codex-flight  →  design-done
             ↓
        exec-ready  →  exec-flight  →  exec-done
             ↓
        test-flight  →  test-done
             ↓
        bugs-found  ──┐  (loops back to design-codex or exec-ready)
             ↓        │
        merge-ready  ─┘
             ↓
        merged
```

Plus terminal states: `blocked`, `dropped`.

**Track-level fields beyond Phase 3**:
- `files_touched TEXT` — comma-separated paths each track will modify.
  Used for conflict-pair detection before launching a new codex slot.
- `depends_on TEXT` — track IDs this one waits on. Allows DAG of
  tracks; ready-set excludes anything with an unsatisfied dep.
- `user_question TEXT` — set when status=needs-user; cleared on
  resolve. Surfaces what's blocked on operator input.

**"Queen pass" cadence**: at the top of every meaningful PM turn
(user prompt, scheduled poll completion, codex landing notification),
the PM runs a single pass:

1. Scan `tracks` for state changes.
2. Promote anything ready (`landed → merge-ready → merged`).
3. Check codex slot capacity (≤4).
4. For each ready+non-blocked track, check conflict-pair vs in-flight;
   launch what's safe.
5. Brief operator on state changes.

**Codex-foreman pattern**: for proven-template fanouts (e.g.,
PP2+ProteinModification after PP1 lands), the PM delegates the
mechanical fanout to a Codex session that itself launches N child
codex workers, polls them, and aggregates STATUS into one summary.
PM reads one summary instead of N. Used only when the taste-calls are
already made and the work is genuinely template-mechanical.

**Innovations born here**:
- Split "needs design" into `design-codex` (clear right answer, codex
  produces) vs `needs-user` (taste call, PM asks operator).
- `files_touched` + `depends_on` columns on the `tracks` table.
- Queen-pass discipline as the synchronous PM heartbeat.
- Foreman pattern for proven-template fanouts.

### Phase 5 — Peer Copilot PMs (considered, deferred)

Two Copilot CLI sessions in two terminals, each owning a disjoint
lane (e.g., PM-A = biology, PM-B = infra/docs). Coordination via:
- Shared filesystem (committed code, DECISIONS.md, optional STATE.md).
- Operator as eventual-consistency synchronizer.

**Why deferred**: coordination cost is high. Each Copilot session has
its own SQLite, its own context window, no in-memory state sharing.
Two PMs working separate lanes for <2 hr of pure-parallel work doesn't
recover the setup + sync overhead. Revisit when:
- ≥2 lanes are genuinely independent for ≥2 hours.
- Operator has bandwidth to attention-switch between PMs without
  losing thread.
- Premium-request budget can absorb 2× concurrent burn.

## Invariants across all phases

These have not changed and should not change without an explicit
decision:

| Invariant | Born in | Why |
|---|---|---|
| STATUS_*.md as codex↔PM contract | Phase 2 | Codex stdout is volatile; the file is the durable artifact. |
| `plan.md` / `DECISIONS.md` as cross-session memory | Phase 0 | OneDrive-synced; survives session loss; auditable. |
| WSL venv mandate in every Python prompt | Phase 2 | Windows-PATH `python.exe` lacks the editable install — ≥4 silent failures forced this rule. |
| 4-slot codex ceiling | Phase 3 | PM review bandwidth + Azure compaction error rate. |
| Confirmation-discipline before user-input gates | Phase 0 | Operator-trust is the contract; "ask before assuming" is non-negotiable. |
| Track-F template (4-commit shape: diagnose → fix → verify → status) | Phase 3 | Reproducible, reviewable, reverts cleanly. |
| Worktree-per-track for any parallel work | Phase 3 | Eliminates merge conflicts at source. |

## How to recognize you've regressed a phase

| Symptom | Likely regression | Fix |
|---|---|---|
| Copilot is writing test code itself | 4 → 1 | Delegate to codex. |
| Two codex sessions touching same file | 4 → 2 | Check `files_touched` before launching; sequence them. |
| `plan.md` getting overwritten by codex's working notes | any → 0 | Codex should write STATUS_*.md, not edit plan.md. |
| `pytest` failing with `ModuleNotFoundError` on project package | 2 lapse | WSL venv mandate not pasted into prompt. |
| 5+ codex sessions in flight | 4 → loose | Enforce ceiling; queue overflow. |
| PM does taste call without asking operator | 3/4 → 0 | Surface as `needs-user` track, halt until operator answers. |

## Open questions (Phase 4 implementation, as of 2026-05-27)

1. Should design tasks default-route to codex (with "stop and ask if
   ambiguous" guard), or default to PM-filter-first? Tradeoff: codex
   speed vs wasted-codex-session cost on bad routing.
2. When codex finds a bug during testing: spawn a new sub-track and
   exit, or fix in same session? Tradeoff: kanban cleanliness vs
   wall-clock latency.

These will be resolved before the `tracks` table schema migration to
Phase 4 form.
