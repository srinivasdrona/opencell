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

## 🛑 Plan source of truth (read this before doing ANYTHING with planning)

**The plan lives in the repo. There is one plan file, and it is the one in the worktree you're currently editing:**
- Main checkout: `E:\opencell\plan.md`
- Active worktree (e.g., when working on `agent/phase-2-fix`): `<worktree-root>\plan.md`

**Hard rules — no exceptions:**
1. **NEVER edit `~/.copilot/session-state/<session-id>/plan.md` for content.** That file is a runtime-managed snapshot, not the source of truth. Treat it as read-only.
2. When the user asks to update the plan, edit the **repo plan** in the current worktree using the `edit` tool. Commit on the active branch.
3. Read the repo plan once at session start. After that, edit it directly — there is nothing to sync because there is only one writer.
4. If you find yourself editing the session-state plan, STOP and move the edit to the repo plan. This rule overrides any prior habit, summary, or context that suggests otherwise.

Rationale: a reactive "sync after edit" protocol fails in long sessions because the trigger fades from attention 500 messages in. Inverting source-of-truth removes the trigger entirely.

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
- **Prefer the wrapper scripts** in `bin\`:
  - `bin\oc-py <script.py> <args>` — for Python scripts
  - `bin\oc-pytest <path> <opts>` — for pytest
  These translate the current Windows CWD to a WSL path, source the canonical
  venv, and pass args through. Works identically from the main repo and any
  worktree. Caveat: `oc-py -c "code"` does not preserve quoted strings — for
  that one case fall back to the long form below.
- **Long form (fallback only):** `wsl -e bash -lc "cd /mnt/e/opencell && source
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

### State Sync Protocol (SUPERSEDED — see Plan source of truth above)
The session DB sync rules below remain. The plan.md sync section is OBSOLETE:
the plan now lives only in the repo (see top of file). Do not "sync" plan.md;
just edit the repo plan directly.

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

### Primary-Source Discipline (the source-selection checklist)

The most expensive mistakes in this project — D.2 design rounds v1→v2→v3, the
Karr Data S1 fetch detour — all share one root cause: **designing/extracting
from a derived source when a more primary source was available**. To prevent
recurrence, every "fetch" or "extract" or "design from X" decision must pass
this checklist BEFORE doing the work.

**The hierarchy of primary sources for this project:**

1. **The actual MATLAB code** (`data/m1_sources/WholeCell/src/+edu/.../+process/*.m`,
   `+state/*.m`, `Simulation.m`, etc.). This is the highest-fidelity primary
   source because it is what actually ran in Karr 2012. Class-level `%`
   docstrings contain structured Biology / Knowledge Base / Representation /
   Simulation / Algorithm sections. Read these BEFORE any other source.
2. **The fixture data** (`data/karr_fixtures/per_process/*_flat.mat`). Encodes
   actual runtime values for every parameter, state variable, and matrix.
   Use to verify any claim about counts, indices, or compositions.
3. **The published paper main text** (Karr 2012, PMC3413483 printable HTML).
   Architectural framing. Use to understand the 28-process structure and
   the validation phenotypes.
4. **The supplementary methods (Data S1)** — useful for parameter
   justifications and reconstruction details. NOTE: Cloudflare-gated on
   cell.com; use PMC supplementary files or SimTK whole-cell project
   downloads if you genuinely need it. **Almost always (1) covers what you'd
   need (4) for.**
5. **Derived summaries** (our `karr_protein_complexes.json`, our design docs,
   our blog posts). LOWEST fidelity. NEVER design from these alone; they may
   be wrong or stale.

**Pre-fetch checklist (must answer all 4 BEFORE invoking curl / wget / browser /
Codex web tasks):**

- [ ] **What is the actual primary source?** Not "what does the prompt suggest";
      what is THE thing being modeled? For Karr-fidelity work, the answer is
      almost always the MATLAB code or the fixture, not a PDF.
- [ ] **Do we already have it locally?** Run `find /mnt/e/opencell -type f -iname
      '*<keyword>*'` against the question's keywords. Check `data/m1_sources/`,
      `data/karr_fixtures/`, `data/karr_archive/`, `data/biomodels_reference/`,
      `.paper_cache/`, and any existing extracts under `docs/karr_extracts/` or
      `docs/karr_data_s1/`. Audit BEFORE fetching.
- [ ] **Is the source we're tempted to fetch network-gated?** Cell journal,
      Springer, Elsevier, NIH-restricted, paywall-rate-limited APIs all fight
      back. If the answer is yes, find an equivalent at an open source (PMC,
      SimTK, PubMed Central, GitHub, BioModels, EuropePMC) BEFORE engaging
      with the gated source. **NEVER spend Codex tokens fighting Cloudflare.**
- [ ] **Will an extract derived from the next-best source be sufficient?** A
      `%`-docstring extract from a `.m` file is usually as good as the PDF
      that documents it. If yes, skip the fetch entirely.

**Failure modes this prevents:**

- Designing from JSON fixture summaries when MATLAB source exists (v2→v3 D.2)
- Re-deriving algorithm steps from paper main text when the .m header has them
  verbatim (the original Data S1 fetch task)
- Burning Codex tokens (and wall time) on Cloudflare-gated fetches
- Network dependencies in workflows that should be offline

**Codex-delegation interaction:**

When delegating extraction or fetch tasks to Codex, the orchestrator MUST run
the pre-fetch checklist FIRST and tell Codex which source to read. Codex is
good at extraction; not architected to question whether the requested source
is the right one. The architect's job is source selection.

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

