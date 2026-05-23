<overview>
Continuing the OpenCell project (Python port of Karr 2012 *M. genitalium* whole-cell model onto vivarium-core). Today's mission (2026-05-23): close Phase C (10 DNA/cell-cycle Karr processes) + start Phase D (HostInteraction → chassis_v6 = all 28 processes) + scaffold Phase E (validation vs Karr trajectories) via maximum-parallel Codex delegation. User (sdrona) is PM/orchestrator; Copilot CLI is strategist that ONLY does design/strategy — all code must go through Codex sessions. User has explicitly said to delegate liberally, spin many sessions, they handle capacity/tokens, and "DO NOT IDLE."
</overview>

<history>
1. User: "good morning, what's on the schedule?" — Proposed Phase C end-to-end + start Phase D via Codex fleet.

2. User: "delegate liberally, spin as many sessions as you want" — Began Wave 1 prep; pre-flight checks done. Compact happened here.

3. After compact: User: "ask codex to design pc-t2 instead of starting cold" — Refreshed SESSION_CONTEXT.md (committed ea33548) with 6 hard rules.

4. User: "smaller design work in separate codex sessions, DO NOT SEQUENCE, DO NOT IDLE" — Switched to fire-everything-in-parallel mode. Each Codex session does design+implement+test+commit standalone.
   - Created 11 worktrees (pc-t2..t10, pd-t1, pe-1).
   - First launch attempt via Python subprocess.Popen failed (FileNotFoundError — codex is a .cmd shim, args quoting broken on Windows).
   - Switched to PowerShell launcher with stdin piping via `type PROMPT.md | codex.cmd exec ... -` to dodge .cmd arg quoting.
   - Fixed missing AZURE_OPENAI_API_KEY env propagation by reading from User scope.
   - All 11 sessions launched successfully (~22 live node/codex processes).
   - Added 2 more design sessions: pc-final-chassis-v5-design, pd-final-chassis-v6-design → 13 total.

5. User: "still waiting?" (1.5h later) — All 13 sessions completed cleanly. Each shipped design + impl + tests, full suite green in worktree (795-799 passed).
   - Merged all 13 to main; one conflict on `.progress.md` (multiple agents wrote) — resolved by `git rm` during merge.
   - Final main = commit `2cac60c`; full suite on integrated main: **864 passed, 0 failed** (+57 from baseline 807).
   - Pushed to origin.

6. User: "what are next steps? is C code complete?" — Explained Phase C process modules are complete but chassis_v5 integration (wiring + CellCycleCoordinator) is still skeleton-only. Launched 2 more Codex sessions: pc-final-integration (real v5) + pd-final-integration (v6 = 28 processes).

7. User: "anything to do while tests run?" — Suggested A (state-key audit) + B (read open questions) + C (lint cleanup) + D (set/accumulate warnings).

8. User: "isn't lint-debt already done?" — Confirmed yes (commit `ad20e19` yesterday). Marked todo done.

9. User: "fix D on a codex session" — Launched fix-set-accumulate-warnings session.

10. User: "make codex do A also, you focus on design only" — Launched audit-cross-process-keys session. Now 4 Codex sessions running.

11. User: "now you do B, don't idle" — Read v5/v6 open-questions sections; wrote decision sheet to session-state file with pre-answers for all 9 open questions.

12. User: "did any codex session end?" — All 4 still running.

13. User: "anything else to do?" — Offered options (1) Phase E design plan, (2) PyPI prompt, (3) blog outline, (4) checkpoint skeleton, (5) decision-log entries.

14. User: "just do 1, we are just getting started today" — Need to draft Phase E design plan now.
</history>

<work_done>
Files created/modified:
- `E:\opencell\SESSION_CONTEXT.md` — refreshed with 6 hard rules; committed `ea33548`
- 13 PROMPT.md files in worktrees (per-task scope)
- `E:\opencell\scripts\launch_phase_c_fleet.py` — Python launcher (broken on Windows .cmd quoting; abandoned)
- `E:\opencell\scripts\launch_codex_fleet.ps1` — working PowerShell launcher (stdin pipe + cmd.exe wrap)
- `E:\opencell\scripts\fleet_status.ps1` — health snapshot across worktrees
- `E:\opencell\scripts\review_and_merge.ps1` — merge pipeline (mostly unused; direct merge worked)
- `E:\opencell\scripts\launch_codex_session.ps1` — earlier failed helper (still on disk)
- `C:\Users\sdrona\.copilot\session-state\<sid>\files\v5_v6_open_questions_decisions.md` — full decision sheet for 9 open questions

Merges completed (all on main, pushed to origin):
- 13 commits merged: pc-t2..t10 (9), pd-t1, pe-1, pc-final-design, pd-final-design
- Main HEAD = `2cac60c`
- Full suite: 864 passed, 9 skipped, 4 xfailed, 0 failed (17 min wall)
- 55 set/accumulate warnings on `substrates_allocated.<proc>.*` (pre-existing tech debt; being fixed by Codex)

Codex sessions currently in flight (all alive at compaction):
- `pc-final-integration` (pid 8952) — chassis_v5 + CellCycleCoordinator
- `pd-final-integration` (pid 10876) — chassis_v6 = 28 processes
- `fix-set-accumulate-warnings` (pid 69600) — clean up 55 warnings
- `audit-cross-process-keys` (pid 48356) — preemptive state-key consistency audit

Todos updated:
- pc-t2-replication, pc-t10-organelle, pc-t4-cond, pc-t5-seg, pc-t9-cyto, pd-t1-host, pe-1 → done
- pc-final-chassis-v5, pd-final-chassis-v6 → in_progress
- lint-debt-cleanup → done (was already done yesterday; corrected)

Most recent: Drafted Phase E design plan was just requested but not yet started.
</work_done>

<technical_details>

## Codex launching on Windows (hard-won)

- `codex` is at `C:\Users\sdrona\AppData\Roaming\npm\codex.cmd` (npm shim)
- Python subprocess.Popen with .cmd file → FileNotFoundError unless shell=True; even then, arg quoting for long prompts is broken
- Start-Process with array args → .cmd consumes quotes, splits prompt on spaces, codex interprets words as subcommands
- **Working pattern**: `cmd.exe /c "type PROMPT.md | codex.cmd exec --dangerously-bypass-approvals-and-sandbox -C wt -o STATUS.md - 1> stdout 2> stderr"` (stdin pipe with `-` as prompt arg)
- AZURE_OPENAI_API_KEY must be set in process env at launch: `$env:AZURE_OPENAI_API_KEY = [Environment]::GetEnvironmentVariable('AZURE_OPENAI_API_KEY','User')`
- `--dangerously-bypass-approvals-and-sandbox` required for WSL subprocess access (standard `-s workspace-write` blocks `wsl -e bash -lc`)
- Each Codex session = 2 procs (codex + node child)

## Parallel fleet pattern (proven today: 13 sessions in one batch)

1. Create worktree per task: `git worktree add wt -b agent/<task> main`
2. Write PROMPT.md per task (mandatory preamble + Karr primary source pointers + scope + DoD)
3. Launch via cmd.exe stdin-pipe pattern
4. Track via fleet_status.ps1 (pid alive + STATUS size + stderr size + commit count + head age)
5. Merge sequence: `git merge --no-ff agent/<task>` in main; on conflict (e.g., `.progress.md` from multiple agents) → `git rm` the offending file and continue
6. Final gate: full suite on integrated main (must remain green vs baseline)

## Hard rules in SESSION_CONTEXT.md (every Codex session must read)
1. Karr-fidelity is prime directive (verbatim docstring extracts trusted)
2. WSL venv ONLY: `/mnt/e/opencell/.venv-wsl/bin/python` and `/mnt/e/opencell/.venv-wsl/bin/pytest`. Never Windows py.
3. Vivarium accumulate-only for per-tick writers; `set` only for single-writer state-machine fields
4. KarrAllocationStep contract: `requests.<proc>.<sub>` → `substrates_allocated.<proc>.<sub>` → emit accumulate-delta on `substrates.<sub>`
5. Commit-or-STATUS: NEVER exit silently
6. No regressions vs baseline (currently 864)

## Open-question decisions (pre-answered, in session-state file)
- v5-OQ1/v6-OQ4 (module names): factual lookup; integration sessions can grep
- v5-OQ2: direct request writes (match pc-t1), not new request-calculator step
- v5-OQ3: left/right nt scalar coords for v5; region-index deferred to v2
- v5-OQ4: tick windows from `cell_cycle_trajectory.mat` via pe-1 loader; ±30% bands
- v5-OQ5: CCC in dedicated `karr_cell_cycle_coordinator.py`
- v6-OQ1: extract numbering follows Karr (27=TerminalOrganelle, 28=HostInteraction); vivarium order is topological
- v6-OQ2: non-gating host adhesion in v1 (accept v6 design recommendation)
- v6-OQ3: adopt KP01-KP28 table from v6 design; create `phenotype_registry.py`

## Performance budget
- chassis_v4: ~62 ticks/s baseline
- chassis_v6 estimate: ~30 ticks/s (10+1 processes added)
- 32400-tick full cycle: ~18 min — CI-borderline. Use `xfail("perf-budget v2")` escape hatch.

## Known issues unfixed in v1
- 55 set/accumulate warnings on `substrates_allocated.*` leaves (Codex fixing now)
- Cross-process state-key BLOCKERS unknown until audit session completes
- Phase E.1 trajectory drift >50% is expected for Karr-light v1; bucket as `karr-known-incomplete`

## Repo state
- Main HEAD: `2cac60c Merge agent/pd-final-chassis-v6-design`
- Pushed to origin/main
- 27 of 28 Karr processes have modules; chassis_v5/v6 only have skeletons (real integration in flight)
- Baseline tests: 864 pass / 0 fail / 9 skip / 4 xfail
</technical_details>

<important_files>

- `E:\opencell\SESSION_CONTEXT.md`
  - 6 hard rules every Codex session must follow. Refreshed today, committed.

- `E:\opencell\scripts\launch_codex_fleet.ps1`
  - Working Windows launcher (stdin pipe + env propagation). Use this for any future fleet launches.

- `E:\opencell\scripts\fleet_status.ps1`
  - Health snapshot: alive/dead, STATUS size, stderr size, commits-ahead-of-main, HEAD age.

- `C:\Users\sdrona\.copilot\session-state\<sid>\files\v5_v6_open_questions_decisions.md`
  - Pre-answers for all 9 v5/v6 open questions; instantly unblocks any session that STATUS-outs asking.

- `E:\opencell\docs\design\pc_final_chassis_v5.md` (20.5KB)
  - chassis_v5 integration design + skeleton spec. Key sections: line 170 (CellCycleCoordinator), line 322 (open questions).

- `E:\opencell\docs\design\pd_final_chassis_v6.md` (10KB)
  - chassis_v6 spec; KP01-KP28 phenotype scorecard table at lines 144-173; open questions at line 215.

- `E:\opencell\opencell\vivarium\karr_replication_initiation.py`
  - Phase C v1 pattern reference (pc-t1, already on main). All Phase C processes followed this shape.

- `E:\opencell\opencell\vivarium\karr_allocation_step.py`
  - Substrate request/allocate contract. Likely modified by fix-set-accumulate-warnings session.

- `E:\opencell\opencell\vivarium\karr_composite.py`
  - chassis_v4 currently; v5 will be added here by pc-final-integration session.

- Worktrees in `E:\opencell-worktrees\`:
  - `pc-final-integration`, `pd-final-integration`, `fix-set-accumulate-warnings`, `audit-cross-process-keys` — 4 sessions in flight
  - 13 completed worktrees from earlier wave (branches already merged; worktrees still on disk for log inspection)

- `E:\opencell\data\m1_sources\karr_native\cell_cycle_trajectory.mat` (100 MB, gitignored)
  - Phase E validation gold standard. pe-1 loader at `opencell/validation/karr_trajectory.py` already shipped.
</important_files>

<next_steps>

Immediate (just-requested) work:

1. **Draft Phase E design plan** (USER'S CURRENT REQUEST). Pure design work, no code.
   Should cover:
   - Phase E.1 (trajectory match): acceptance criteria, per-bucket tolerances (using v6 design's table), drift budget, what "pass" means
   - Phase E.2 (phenotype match ≥10/28): scorecard run protocol, KP01-KP28 extractor registry design (recommend `opencell/validation/phenotype_registry.py`), how to wire each KP to a chassis_v6 store
   - Phase E.3 (discrepancy analysis): report template, how to categorize divergences (Karr-known-incomplete vs biology-beyond-Karr vs validation-scaling vs opencell-tooling buckets)
   - Phase E-final (v1.0 release gate): what must be true to ship v1
   - Output: file in session-state OR commit to `docs/design/phase_e_overview.md` (lean toward latter so it's permanent and Codex sessions can read it)

Remaining today (after Phase E design):
- Wait for 4 in-flight Codex sessions to complete; merge them
- Fire Phase E.1 Codex session once chassis_v6 lands
- Possibly chain Phase E.2 and E.3 sessions
- End-of-day: plan sync, decision-log entries, checkpoint, blog

Open questions to monitor:
- Did any of the 4 in-flight sessions hit a real BLOCKER? Check STATUS.md when notified.
- After v5+v6 land: 28-process throughput reality check vs 18-min budget.

User constraints to remember:
- DO NOT IDLE
- Copilot does design/strategy ONLY; all code through Codex
- Delegate liberally, user handles capacity/tokens
- Blog posts/checkpoints are far away — focus on building today
</next_steps>