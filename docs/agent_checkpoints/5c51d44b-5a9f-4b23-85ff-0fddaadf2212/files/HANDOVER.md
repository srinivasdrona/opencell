# Handover — OpenCell, session 5c51d44b (UPDATED 2026-05-22 01:16 IST)

**Prior session ID:** `5c51d44b-5a9f-4b23-85ff-0fddaadf2212`
**Origin:** `https://github.com/srinivasdrona/opencell` (main = `a14e5c2`; active branch = `agent/d2-design-v3` @ `6269a4c`)

---

## ⚡ TOMORROW MORNING — do these in order, before anything else

1. **Open** https://github.com/srinivasdrona/opencell/tree/agent/d2-design-v3/docs/design/d2_complex_assembly.md — read v3 end-to-end (~1 hr). Also skim `artifacts/d2_v3_evidence.md` for the extracted facts the design rests on.

2. **Two parallel cross-model critiques** (the gate that has caught every prior round):
   - **Claude Sonnet rubber-duck.** Prompt: *"Read this design doc. List every claim that should have a citation but doesn't, every algorithm step without a worked example, every oracle target whose units I haven't double-checked. Don't be polite — find what's wrong."*
   - **GPT-5.4 cross-model.** Prompt: *"v2 of this design had 4 BLOCKERs called out at the top. For each one, independently verify v3 actually fixes it (not just rephrases it). Then look for new BLOCKERs we haven't named yet. Pay particular attention to the open finding about RIBOSOME_30S_IF3 / RIBOSOME_70S ownership decision (b)."*
   - Log BOTH via:
     ```bash
     python scripts/log_llm_interaction.py \
       --role cross_model_critique --model <sonnet|gpt-5.4> \
       --task-summary "D.2 v3 design critique — <model>" \
       --output-summary "<verdict + N BLOCKERs surfaced>" \
       --linked-commits 10bf5f0 \
       --linked-todo d2-design-v3-rework \
       --supersedes sha256:c6ef222365dee48d8772e9f59d3f9fc313738e4e94d6d45a6e07c691297045a2 \
       --tags d2,design,critique-round-3 \
       --verification-status <verified|rejected|pending>
     ```

3. **Two outcomes, decide accordingly:**
   - **(i) minor / approved:** Merge `agent/d2-design-v3` → `main` (no-ff). Mark `d2-design-v3-rework` done in BOTH `session DB` and `opencell_tasks.db`. Unblock `d2-complex-assembly` (implementation phase). Delete the worktree.
   - **(ii) new BLOCKERs surfaced:** v4 rework on the same branch — NEW commits, not amend. Re-run the same two critiques on v4. Don't be afraid of a v4; cheaper than implementing the wrong v3.

---

## 0. First three things the next agent must do (if not the same operator)

1. **Read these files in order** (do not skip):
   - `.github/copilot-instructions.md` — WSL-execution rule, LLM Interaction Logging rule, State Sync Protocol
   - `plan.md` — current phase + BLOCKERs (start at "Current Status" header near line 400)
   - `BOOTSTRAP.md` — if on a fresh machine
   - `docs/agent_checkpoints/5c51d44b-.../checkpoints/index.md` — checkpoint trail
   - This file
2. **Verify env before any execution**:
   ```bash
   wsl -e bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && pytest tests/m1/ -q --no-header"
   # expect: 70 passed
   ```
   If that fails, re-run `./scripts/bootstrap.sh` inside WSL.
3. **Log your first LLM-influenced commit** via `scripts/log_llm_interaction.py` per the LLM Interaction Logging rule. The discipline is new — don't drop it.

---

## 1. State of the repo

| Asset | Value |
|---|---|
| `main` HEAD | `0d0881c` (matches `origin/main`) |
| Branch worktrees | only `main` (d2-design-v2 worktree was removed, branch still exists locally but is stale and destructive — do not merge as-is) |
| Test baseline (WSL) | 610 passed, 4 xfailed, 0 failed, 0–5 skipped depending on Thattai cache |
| CI on GitHub | lint advisory, strict only on `opencell/provenance/llm_log.py` + `tests/provenance/` |
| Todos | 200 total (18 pending / 124 done / 58 blocked) — both stores synced |
| LLM log | `data/provenance/llm_interactions.jsonl` — 1 entry so far (bootstrap of the logging infra itself) |

### Recent commits (most recent first)

```
0d0881c  fix(deps): declare vivarium-core; loud Windows-vs-WSL warning
8a57788  docs(d2): D.2 design doc + mature subset fixture to main
59fcd88  ci: lint fixes; project-wide ruff advisory
2c67ba8  todos: reconcile session DB and repo DB (199 todos synced)
626715a  todos: 10 LLM-log extensibility gaps
517e7cf  feat(provenance): LLM interaction logging infrastructure
1b1cb21  feat(provenance): session checkpoint archive (49 files)
1bbc820  docs: BOOTSTRAP.md + scripts/bootstrap.sh
ddda0fe  docs: rename GitHub handle sdrona-ms -> srinivasdrona
e922bb4  Blog 2026-04-27: the cycle counter that never fired
```

---

## 2. Active threads (in priority order)

### 2A. D.2 design v3 rework — TOP PRIORITY, IN PROGRESS (updated 2026-05-22)
- **Todo:** `d2-design-v3-rework` (pending, active)
- **Current status:** started on branch/worktree `agent/d2-design-v3` with source-truth methodology shift.
- **Evidence generated:** `artifacts/d2_v3_evidence.{json,md}` from `_flat.mat` sources.
- **Design docs added/updated:** `docs/design/d2_v3_compliance_checklist_2026-05-22.md`, `docs/design/d2_v3_source_truth_working_spec.md`, and v3 section at top of `docs/design/d2_complex_assembly.md`.

### 2A.1 Tomorrow first three things
1. Open `agent/d2-design-v3` HEAD on GitHub and use that permalink for critique context.
2. Run two critique passes in parallel: Sonnet (hand-wavy/missing-citation pass) and GPT-5.4 (BLOCKER-fix verification + new BLOCKER hunt). Log both via `scripts/log_llm_interaction.py`.
3. If critique is minor-only, merge v3 and mark `d2-design-v3-rework` done; if critique returns BLOCKERs, do v4 on the same branch before any D.2 implementation.
- **Input:** `docs/design/d2_complex_assembly.md` (v2, on main) has 4 BLOCKERs called out in its own table near the top
- **Output:** a v3 design that fixes those 4 BLOCKERs; same file, same location; preserves v2 as a section labeled "Superseded approach" rather than deleted
- **Critical anti-pattern**: this is a *design* deliverable, NOT a code deliverable. Do NOT create `opencell/processes/d2_complex_assembly.py` or any other implementation file. Implementation happens only after v3 design is approved.
- **Companion fixture**: `data/karr_fixtures/d2_mature_subset.json` (22 KB, already on main) — read for ground truth on anchor complexes and global aggregates
- **Estimated effort**: 2–4 hours of focused design work
- **Suggested approach**: write the v3 doc, then send to a cross-model critique (GPT-5.4 or whichever model is available on the next subscription) using the same pattern that surfaced the v2 BLOCKERs. Log the critique via `scripts/log_llm_interaction.py`.

### 2B. Remote machine bootstrap — UNFINISHED
- A separate Copilot CLI session (GPT-5.3 Codex on the user's "remote" Windows machine, drive D:) tried to pick up the repo and stalled because git, Python, and WSL were all missing
- The user is installing dependencies on that machine
- That session's transcript is in `files/paste-1779382164439.txt` (3181 lines, captured into this session's `files/` and will be archived)
- **Decision pending**: should the remote session resume the work, or should the user kill it and stay on this machine? The remote-machine agent had begun proposing implementation code for D.2 BLOCKERs blind, which is the wrong direction (see 2A — D.2 is design, not implementation)

### 2C. Possible subscription switch (user-initiated)
- User is considering switching from Microsoft-enterprise Copilot to personal Pro
- If that happens, this current session ends and a new one starts under a different account
- Model loss: `claude-opus-4.7-1m-internal` → likely `claude-opus-4.7` (1M → 200K context)
- Plan: `/compact` will fire more aggressively; SESSION_CONTEXT.md trimming may become necessary

---

## 3. Open decisions waiting on user

| ID | Question | Default if user silent |
|---|---|---|
| `d2-strategy` | Who drafts D.2 v3? Current agent / next session / cross-model critique? | Current agent if still active; otherwise next session reads §2A and proceeds |
| `remote-machine` | Continue remote attempt or abandon? | Abandon — env setup cost exceeds benefit |
| `subscription` | Switch to personal Pro? | Stay on current until decision made; don't switch mid-session |
| `llm-log-backfill` | Backfill prior sessions from `session_store` into the log? | Defer — forward capture only until 3–6 months of real use |
| `bug-pattern-registry` | Create `docs/bug_patterns.md` with MCOS-handle-cycle as first entry? | Defer to critique gap #7 — not blocking |

---

## 4. Gotchas the next agent must know

### 4A. WSL is the source of truth — Windows venv lies
- The Windows venv silently skips oracle tests; correct baseline is `skipped == 5` (Thattai cache only)
- See `.github/copilot-instructions.md` → "Execution Environment"
- See `BOOTSTRAP.md` top section (loud warning added in commit `0d0881c`)

### 4B. State Sync Protocol drift is real
- The session DB and `opencell_tasks.db` diverged 142 statuses worth before today's reconciliation
- A `scripts/sync_tasks_db.py` helper is mentioned in `copilot-instructions.md` but doesn't exist yet
- Drift will recur unless the sync is automated or ritualised

### 4C. MCOS handle-cycle bug class (cost us two sessions)
- Naive MATLAB metaclass walkers chase the Process↔Simulation↔State handle web forever
- Fix: cycle-cut at handle boundaries (`sprintf('<handle:%s:%dx%d>', class(v), size(v,1), size(v,2))`) instead of recursing
- See `scripts/matlab/extract_per_process_fixtures.m` lines ~140–300 for the working pattern
- Worth registering as the seed entry of a `bug_patterns.md` if time permits (todo: not yet logged)

### 4D. Object-dtype npz bloat
- When ingesting MATLAB MCOS sentinel-laden cell trees into NumPy, object-dtype arrays will pickle to tens of MB
- Filter object-dtype before npz emission; keep keys in `array_keys` JSON metadata; keep full payload in `_flat.mat` audit trail
- Pattern: `scripts/extract_per_process_fixtures.py::extract_one_from_flat`

### 4E. Lint debt
- `ruff check opencell/ tests/` reports 1101 pre-existing errors (mostly ANN201, UP017, E501)
- CI lint step is `|| true` advisory project-wide; strict only on `opencell/provenance/llm_log.py` and `tests/provenance/`
- Todo `lint-debt-cleanup` (pending) scopes this as a 4–6 hour mechanical sweep
- Don't add new lint errors to the strict surface

### 4F. PowerShell heredoc-to-WSL is brittle
- `wsl bash -lc "python -c \"...\""` with quotes fights PowerShell escaping repeatedly
- Pattern that works: write the Python to a temp file, then `wsl bash -lc "python /mnt/c/.../tmp.py"`
- Worth investing in a small helper if I keep hitting this

---

## 5. Files that are session-scratch (not yet archived)

These live in `~/.copilot/session-state/5c51d44b-.../files/` and will be picked up by the next run of `scripts/archive_session_state.py`:

| File | Purpose | Action by next agent |
|---|---|---|
| `HANDOVER.md` | this doc | preserve; re-archive into repo when session ends |
| `paste-1779382164439.txt` | remote agent transcript (GPT-5.3 Codex attempt) | read only if §2B is revisited |
| `agent_d2_design_doc_status.md` | older d2 status | reference if revisiting d2 history |
| `agent_d2_design_v2_status.md` | older d2 status | reference if revisiting d2 history |
| `agent_m1_per_process_fixtures_status.md` | m1 fixture work record | historical |
| `agent_p10_partition_status.md` | older partition work record | historical |
| `e2_decision.md` | E.2 decision artifact | reference for chassis-swap context |
| `source_inventory_2026-04-24.md` | inventory snapshot | reference |
| `validation_dataset_candidates.md` | validation choices | reference |

---

## 6. How to resume — concrete first prompt

If continuing on the same machine in a new session:

> Read `BOOTSTRAP.md`, `.github/copilot-instructions.md`, `plan.md` (Current Status section onward), and `docs/agent_checkpoints/5c51d44b-.../files/HANDOVER.md`. Then verify the env with `wsl -e bash -lc "cd /mnt/e/opencell && source .venv-wsl/bin/activate && pytest tests/m1/ -q"` (expect 70 passed). Once verified, your scope is the D.2 design v3 rework (todo: `d2-design-v3-rework`). Read `docs/design/d2_complex_assembly.md` end-to-end, then write v3 as a new section that supersedes v2's broken sections, addressing the 4 BLOCKERs explicitly. Do not write any implementation code — design only.

If continuing on a new machine:

> Same as above, but first follow `BOOTSTRAP.md` from §1 to run `scripts/bootstrap.sh` in WSL. Confirm the dependency-fix from commit `0d0881c` is present (`grep vivarium-core pyproject.toml`).

---

## 7. What this session accomplished

For accurate provenance, listed here so the next agent doesn't redo any of it:

- ✅ Pushed repo to GitHub (`srinivasdrona/opencell`) — 8 commits
- ✅ `BOOTSTRAP.md` + `scripts/bootstrap.sh` — fresh-machine setup
- ✅ Agent checkpoint archive script + initial snapshot (49 files committed)
- ✅ LLM interaction logging infrastructure (`opencell/provenance/llm_log.py`, CLI wrapper, 8 tests, `.github/copilot-instructions.md` rule)
- ✅ 10 deferred todos for LLM-log framework extensibility
- ✅ Session vs repo todo reconciliation (199 todos in sync, both stores)
- ✅ CI fixes (lint on new files strict; project-wide advisory; `lint-debt-cleanup` todo logged)
- ✅ D.2 design v2 doc cherry-picked to main from stale `agent/d2-design-v2` branch
- ✅ `vivarium-core` dep declared (was the cause of remote machine's failed test run)
- ✅ This handover document

---

*This document is the durable record. plan.md and SESSION_CONTEXT.md are the long-term history. session_store and the agent_checkpoints/ archive are forensic.*
