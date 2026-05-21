# OpenCell — Copilot Instructions

<!-- pm-os:inheritance:start -->
## PM OS — session bootstrap (mandatory, read first)

**At session start, view these three files before doing any work:**
- `D:\OneDrive - Microsoft\.pm-os\PREFERENCES.md` — operator working style, scaling philosophy, auto-onboarding policy
- `D:\OneDrive - Microsoft\.pm-os\DECISIONS.md` — cross-project decision log
- `D:\OneDrive - Microsoft\.pm-os\INBOX.md` — capture-first items pending processing

Templates (read on demand): `D:\OneDrive - Microsoft\.pm-os\templates\` — `prd.md`, `experiment.md`, `retro.md`.

Project alias: `opencell`   |   Type: `research`

> Path note: hardcoded absolute paths above are correct for this machine. On a different machine the profile lives at `$env:OneDrive\.pm-os` — resolve via PowerShell rather than relying on `%OneDrive%` in markdown (it isn't expanded).
<!-- pm-os:inheritance:end -->

## Project Context
OpenCell is an open-source whole-cell simulation in Python/JAX.
This file defines agent behavior for all AI-assisted work on this project.

## Skill Profiles
Load the appropriate skill profile from `.github/skills/` based on the task type.
See plan.md "Agent Skill Profiles" section for full definitions.

## Mandatory Rules

### Execution Environment: WSL is the Source of Truth
All development, test runs, and scripts for this project run in **WSL**
with the venv at `/mnt/e/opencell/.venv-wsl`. The Windows-side venv
(`.venv-opencell`) is incidental, incomplete (e.g. `libroadrunner` is
Linux-only in our stack), and running pytest there silently skips the
oracle cross-check tests — which are the whole point of having an
oracle.

Hard rules for any command that executes Python/pytest/scripts:
- **Always** wrap with `wsl -e bash -lc "cd /mnt/e/opencell && source
  .venv-wsl/bin/activate && <command>"`. Never invoke `python` or
  `pytest` directly from a PowerShell prompt.
- A passing `pytest` summary that shows `skipped` > 0 must be audited
  with `-rs` before trusting it. In this project the expected skip
  count for a correctly-run suite is **5** (Thattai paper-cache tests
  only). Any number other than 5 means the environment is wrong
  (usually: you're on the Windows venv and `roadrunner` didn't import).
- File edits via the `view`/`edit`/`create` tools can use Windows paths
  (`E:\opencell\...`) -- those are fine, they touch the same filesystem.
  The WSL-only rule applies to **execution**, not editing.
- Remember the WSL fs-sync quirk (5-15s) after a Windows-side edit
  before the file is visible to the Linux venv.

### State Sync Protocol (canonical state lives in the repo, not the agent)
Two artifacts MUST be kept in sync between the per-session scratch and the
repo (which is the durable record across sessions):

| Scratch (per-session)                                              | Canonical (repo, committed)         |
|--------------------------------------------------------------------|-------------------------------------|
| `~/.copilot/session-state/<session-id>/plan.md`                    | `E:\opencell\plan.md`               |
| Session SQL DB (`todos`, `todo_deps` tables)                       | `E:\opencell\opencell_tasks.db`     |

When to sync (any one triggers a full sync of BOTH artifacts):
1. **End of every checkpoint** (before the runtime auto-checkpoints).
2. **After completing any todo or marking one blocked** (status changes
   are the most valuable thing to persist).
3. **Before the user closes the session or asks "where are we?"** —
   if a repo-state question is being asked, the repo state had better be current.
4. **Whenever plan.md has been edited in the session-state copy** and
   more than ~3 todos have changed status since the last sync.

How to sync:
- `plan.md`: `Copy-Item` (Windows) or `cp` (WSL) the session-state file
  over `E:\opencell\plan.md`, then `git add plan.md && git commit`.
- `opencell_tasks.db`: dump session DB to JSON, replay into the E-drive
  DB inside a transaction, back up the old DB first. Use the helper
  pattern in `scripts/sync_tasks_db.py` (build it on first sync) so
  it's a one-command operation, not ad-hoc Python each time.
- Commit messages for sync commits should say "Sync plan.md: <what changed>"
  or "Sync tasks DB: <N> done, <M> pending" so the git log is a
  human-readable progress journal.

What NOT to sync:
- Don't push session DB rows for tables the agent doesn't own
  (e.g., `review_findings` is project-wide and may have been edited
  by other sessions or tools — leave alone).
- Don't blindly overwrite if the repo DB has todo IDs unique to it;
  always run a "what would I lose?" diff first.

### No Naked Biology Numbers
Every biological constant in model code MUST reference a parameter ID from the data layer.
Hardcoded literals allowed ONLY for: 0, 1, tolerances, array shapes.

### Unit Discipline
All values entering the IR must pass through pint unit validation.
Sub-models must declare their reference frame (per-cell, per-volume, per-gDW).

### Stochastic RNG Discipline
Stochastic primitives (tau-leap, SSA, any sampling helper) **must** accept
an explicit `np.random.Generator` (or JAX `PRNGKey` if they actually use
one). Hard rules:
- **Never** call `np.random.seed()` — it mutates process-global state and
  silently clobbers any other RNG-using code in the same process.
- **Never** call unseeded `np.random.<distribution>()` — same reason.
- Callers derive independent streams via
  `np.random.SeedSequence(base_seed).spawn(n)`; ensembles must use this
  (or equivalent) so two parallel realisations cannot collide.
- A function that takes a JAX key but never uses it is a bug; remove the
  parameter or use it.

### Evidence Provenance
Every nontrivial biological claim must have:
- DOI citation
- Quoted evidence snippet with page/figure/table location
- Experimental conditions (temperature, pH, strain, medium)
- Uncertainty distribution

### LLM Interaction Logging
Significant LLM exchanges that shape the repo MUST be logged to
`data/provenance/llm_interactions.jsonl` via `scripts/log_llm_interaction.py`.
The forward-capture log is the methodology audit trail for the L4 paper
and any later reproducibility claims.

**What to log** (cumulative — log if ANY apply):
- Cross-model critique exchanges (e.g., Opus reviewed by GPT-5.4 or vice versa)
- Sub-agent / background-agent dispatches that produced committed artifacts
- Design decisions that change scope, architecture, or strategy
- Reversals of prior decisions ("we previously decided X; now Y because Z")
- Bug-pattern derivations worth naming (MCOS handle-cycle, etc.)

**What NOT to log**: routine view/grep/edit work, debug iterations within
a single coherent task, anything the system prompt forbids verbatim.

**How to log** — single CLI invocation, idempotent on content:

```bash
python scripts/log_llm_interaction.py \
    --role main_agent \
    --model claude-opus-4.7 \
    --task-summary "<one line>" \
    --output-summary "<what was produced>" \
    --linked-todo <todo-id> \
    --linked-commits <sha1>,<sha2> \
    --linked-artifacts <path1>,<path2> \
    --verification-status verified \
    --verification-notes "<test counts, hash matches>"
```

**Cadence**: log at the same moment you commit. A commit that is
LLM-influenced should be accompanied by a log entry referencing its SHA.
See `opencell/provenance/llm_log.py` for the full schema. Append-only,
content-addressed (`event_id = sha256:<hex>`); corrections happen via a
new entry with `--supersedes <prior-event-id>`.

### Temperature Policy
- Temperature 0: code generation, parameter extraction, data formatting
- Temperature 0.3-0.5: literature search, hypothesis generation
- Never above 0.5 for any task

### Decision Registry
All biology/model decisions go in `decisions/` as structured YAML.
CI enforces: changing behavior tied to a decision must reference or supersede it.

### PR Checklist (Biology/Model PRs)
1. Which assumptions changed?
2. Which parameters changed?
3. Which modules/species affected?
4. Which invariants re-run?
5. Did estimated parameter count increase?

## Credibility Policy
- Mark all estimates as VERIFIED or UNVERIFIED
- Say "I don't know" rather than fabricate
- Benchmark before claiming performance numbers
- Cite sources for all biological facts

