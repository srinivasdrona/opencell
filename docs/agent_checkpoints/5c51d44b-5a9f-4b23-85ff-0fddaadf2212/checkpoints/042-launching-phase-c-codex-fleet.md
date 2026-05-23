<overview>
Continuing the OpenCell project — a Python port of Karr 2012's whole-cell model of *M. genitalium* onto vivarium-core. The user (sdrona) is PM/orchestrator; Copilot CLI is strategist that designs Karr-faithful modules and delegates implementation to Codex CLI sessions running in parallel worktrees. Today's mission (2026-05-23) is to ship Phase C (10 DNA + cell-cycle Karr processes) end-to-end via maximum-parallel Codex delegation, then start Phase D (HostInteraction + chassis_v6 = all 28 processes) and Phase E (validation vs Karr's published trajectories). User has explicitly said to delegate liberally and spin as many Codex sessions as needed — they'll handle capacity and tokens.
</overview>

<history>
1. User said "good morning, let's target another big day, what's on the schedule?"
   - Queried opencell_tasks.db for pending todos (19 pending — Phase C T2-T10, C final, D T1, D final, E1-E4, plus llm-log-pypi and l4-methods-paper)
   - Proposed: ship Phase C end-to-end + start Phase D, with pc-t2 Replication as the design-heavy headline task and 4-5 structurally Phase-B-like turns (t3, t4, t8, t10) launched in parallel via Codex
   - Asked: same orchestration pattern as yesterday?

2. User answered "Yes, same pattern"
   - Started reading Phase C primary sources: `docs/design/phase_c_overview.md`, `docs/karr_extracts/process/03_Replication.md`, `docs/design/pc_turn1_replication_initiation.md`
   - Discovered the prior summary was incorrect: pc_turn{2..10}.md design docs are NOT in repo — only pc_turn1 exists. So all design + implementation must be delegated fresh
   - Verified per-process trace MAT files exist for all Phase C processes
   - Confirmed Replication.m source file is missing from repo (gitignored WCM source not synced into main path), but the docstring extract is sufficient

3. User said "delegate to codex liberally wherever you can, spin as many sessions as you want, I'll handle capacity and tokens"
   - Read delegate-to-codex SKILL.md thoroughly (all sections: preamble, decomposition, progress contract, handoff, pre-flight, failure modes)
   - Pre-flight: AZURE_OPENAI_API_KEY confirmed set, codex-cli 0.133.0 confirmed
   - Inventoried `opencell/vivarium/karr_*.py` (24 files — chassis_v4 complete, pc-t1 ReplicationInitiation at 476 LOC)
   - Worktree base `E:\opencell-worktrees` exists (has stale d2-design-v2, karr-extracts, v2-chassis-swap dirs from yesterday)
   - Wrote `SESSION_CONTEXT.md` at repo root with 6 hard rules (Karr-fidelity, WSL venv ONLY, accumulate-only, KarrAllocationStep contract, commit-or-STATUS, no regressions) + reference file list + branch policy + DoD checklist
   - Attempted to commit it — turned out SESSION_CONTEXT.md already existed and git reported "nothing to commit" (the create tool reported "already exists" but git saw no diff — likely identical content). Did NOT verify whether the on-disk file matches what I tried to write.
   - Was about to launch Wave 1 Codex sessions when the compact event happened.
</history>

<work_done>
Files updated:
- `E:\opencell\SESSION_CONTEXT.md` — attempted create, file already existed (status unclear; may or may not contain the intended 6-rule contract; needs verification)

Work completed:
- [x] Surveyed pending todos and confirmed Phase C is the priority
- [x] Confirmed orchestration pattern (same as yesterday, with liberal delegation)
- [x] Read pc-t1 design + phase_c_overview + Replication docstring extract
- [x] Pre-flight check: AZURE_OPENAI_API_KEY, codex-cli 0.133.0, worktree dir
- [ ] **IN PROGRESS**: Wave 1 Codex launch (8 sessions: pc-t2, t3, t4, t6, t8, t10, pd-t1, pe-1)
- [ ] Wave 2: pc-t5, pc-t7, pc-t9 (depend on Wave 1 outputs)
- [ ] Wave 3: pc-final chassis_v5, pd-final chassis_v6
- [ ] Phase E.1 trajectory match against cell_cycle_trajectory.mat
- [ ] End-of-day: plan/tasks sync + checkpoint + blog post

Repo state at compact:
- main @ `ad20e19` (Merge agent/lint-debt)
- Working tree clean
- 17 of 28 Karr processes shipped (chassis_v4 + pc-t1)
- ~720 tests pass, 0 fail, CI strict
- 100 MB Karr cell_cycle_trajectory.mat already extracted (validation gold standard, gitignored at `data/m1_sources/karr_native/cell_cycle_trajectory.mat`)
</work_done>

<technical_details>

## Wave 1 launch plan (8 parallel Codex sessions)

Each session pattern:
1. Create worktree: `git worktree add E:\opencell-worktrees\<task-name> -b agent/<task-name>`
2. Copy SESSION_CONTEXT.md if not synced
3. Write prompt file with: mandatory preamble (tool fallback + WSL venv mandate + commit-or-STATUS + stale-STATUS overwrite) + progress contract + Karr primary source pointers + scope + chassis pattern reference + test plan + DoD
4. Launch async detached: `codex exec --dangerously-bypass-approvals-and-sandbox -C <worktree> -o STATUS.md <prompt>`
5. Monitor via `scripts/codex_status.ps1`

Wave 1 turns (all independent of each other; only depend on already-shipped pc-t1 + chassis_v4):
- **pc-t2 Replication** — Karr-light scope: fork advancement counter, bulk dNTP/energy demand per Karr trace rates, defer SSB/Okazaki/ligase to v2. Reads `chromosome.replication_state == "initiating"` from pc-t1.
- **pc-t3 DNASupercoiling** — TopoII, gyrase, topoIV; supercoiling state machine
- **pc-t4 ChromosomeCondensation** — SMC complex condensation
- **pc-t6 DNADamage** — UV/oxidative/alkylation damage event sites
- **pc-t8 FtsZPolymerization** — Z-ring formation at midcell
- **pc-t10 TerminalOrganelleAssembly** — M. genitalium-specific polar adhesion organelle
- **pd-t1 HostInteraction** — adhesion to host epithelium (independent of Phase C state)
- **pe-1 scaffolding** — load cell_cycle_trajectory.mat, design comparison framework

## Critical delegation rules (must be in every prompt)

1. **WSL venv ONLY**: `/mnt/e/opencell/.venv-wsl/bin/python` and pytest. Never `py -3.12` or Windows `python` — phantom ModuleNotFoundError on the project's own package, chains into hours of pip dep hell.
2. **Vivarium accumulate-only**: every per-tick writer emits deltas via `_updater: "accumulate"`. Mixed set+accumulate broken (probe 4 empirical proof from yesterday).
3. **KarrAllocationStep protocol**: write `requests.<proc>.<sub>`, read `substrates_allocated.<proc>.<sub>`, emit accumulate-delta on `substrates.<sub>`.
4. **Tool-availability fallback**: WSL may lack rg/fd/jq/gh — fall back to grep -rn / find / python json / git+curl. Missing tool ≠ abort.
5. **Stale STATUS**: first action overwrite STATUS.md with fresh "task started" header.
6. **Commit-or-STATUS**: NEVER exit silently. Even partial STATUS > no STATUS.
7. **Progress contract**: `.progress.md` heartbeat every 5 files or 10 min.

## Codex CLI quirks (2026-05-22 lessons)

- `codex exec resume --last` does NOT accept `-C` or `-s` flags; set cwd via `Set-Location` first
- Use `--dangerously-bypass-approvals-and-sandbox` (operator pre-authorized) for WSL subprocess + network access; standard `-s workspace-write` blocks `wsl -e bash -lc`
- `codex_status.ps1` flags stale STATUS by comparing mtime to stdout activity + HEAD commit (catches inherited-STATUS-from-prior-worktree silent-failure mode)
- Context handoff: at 200k tokens Codex auto-compacts (lossy); `HANDOFF_AUTO.md` watcher fires same threshold; if fresh, do clean session reset NOT `resume --last`
- HANDOFF_AUTO.md state file at `~/.codex/.tmp/context_handoff_watch_state.json` — clear if stale >24h

## Phase C architectural pattern (from pc-t1)

- New stores: `chromosome.<feature>` (dnaa_complex_count keyed by site, replication_state machine, fork_positions, damage_sites, supercoiled bool)
- New Step type: `CellCycleCoordinator` runs at tick boundary after processes; triggers state transitions (initiation, completion, division)
- Discrete events on long timescales (replication init fires ONCE per ~10000-tick cell cycle); chassis_v4 architecture handles this with the new chromosome state store
- Existing v3/v4 wiring: M2v3/M3v3 delta-emit, KarrAllocationStep, ProteinDecay-light, plus 17 Phase A3.3+B processes

## Karr-light scope rule (must document in each file's docstring)

For processes too complex to port fully in one Codex turn:
- Per-tick RATES match Karr's per-process trace data (`per_process_traces/<Process>_100ticks.mat`)
- Bulk state changes (fork advancement counter) not per-nucleotide mechanics
- Document deferred mechanism explicitly as "v2 scope" in file docstring
- Chassis MUST still close mass balance — light ≠ fictional

## Unresolved/uncertain

- Did SESSION_CONTEXT.md actually get written? Need to view it before launching Wave 1
- Old worktrees from yesterday (`d2-design-v2`, `karr-extracts`, `v2-chassis-swap`) still exist at `E:\opencell-worktrees\` — may need cleanup before creating new ones with same names, but pc-* / pd-* / pe-* are fresh names so no collision
- Replication.m source file missing from `data\m1_sources\WholeCell\src\...\Replication.m` — Karr extract is the only primary source available for pc-t2 Codex; if Codex needs the full source it must fail-back to per_process_traces/Replication_100ticks.mat parameter dump
- Bandwidth/cost: user said "I'll handle it" but 8 parallel Codex sessions × ~30 min × premium provider is non-trivial — proceed without further confirmation

</technical_details>

<important_files>

- `E:\opencell\SESSION_CONTEXT.md` 
  - Shared context for all Codex sessions today; defines 6 hard rules (Karr-fidelity, WSL venv only, accumulate-only, KarrAllocationStep, commit-or-STATUS, no regressions). 
  - Status uncertain — `create` reported "already exists"; needs `view` to verify content matches intent before launching Wave 1.

- `E:\opencell\opencell\vivarium\karr_replication_initiation.py` (476 LOC)
  - Phase C v1 pattern — the canonical reference for all pc-t* Codex sessions. Shows chromosome state stores, 9-substep ordered execution, KarrAllocationStep wiring, accumulate updaters, initiation trigger detection.

- `E:\opencell\opencell\vivarium\karr_allocation_step.py`
  - Request/allocate protocol. All Phase C processes consuming shared substrates must follow this pattern.

- `E:\opencell\opencell\vivarium\karr_composite.py` (1069 LOC)
  - Chassis assembly. `build_karr_chassis_v4` is the current integration point. Phase C will add `build_karr_chassis_v5` (all 27 processes minus HostInteraction).

- `E:\opencell\docs\design\pc_turn1_replication_initiation.md` (160 lines)
  - The pattern for Phase C turn design docs. pc-t2..t10 will be drafted by Codex sessions themselves (not me) since user wants liberal delegation.

- `E:\opencell\docs\design\phase_c_overview.md` (94 lines)
  - Authoritative Phase C scope: 10 turns + final, architecture additions (chromosome state store, CellCycleCoordinator Step), what's in/out of scope. Read first by every Codex session.

- `E:\opencell\docs\karr_extracts\process\03_Replication.md` (235 lines)
  - Verbatim Karr docstring for Replication.m: 8 random-ordered subfunctions (initiateReplication, unwindAndPolymerizeDNA, freeAndBindSSBs, dissociateFreeSSBComplexes, initiateOkazakiFragment, terminateOkazakiFragment, terminateReplication, ligateDNA). Primary source for pc-t2.

- `E:\opencell\docs\karr_extracts\process\{04..28}_*.md`
  - Verbatim docstrings for remaining 9 Phase C processes + HostInteraction + TerminalOrganelle. Each pc-t* / pd-t1 Codex session reads its own.

- `E:\opencell\scripts\codex_status.ps1`
  - Live-visibility helper for parallel sessions: file count + stdout idle + STATUS staleness detection. Will use this every 5-10 min during the parallel run.

- `C:\Users\sdrona\.copilot\skills\delegate-to-codex\SKILL.md`
  - The full delegation pattern: mandatory preamble (lines 122-185), decomposition heuristic (191-208), progress contract (210-230), handoff enforcement (291-361), pre-flight (363-383).

- `E:\opencell\data\m1_sources\karr_native\cell_cycle_trajectory.mat` (100 MB, gitignored)
  - Phase E validation gold standard. 32400-tick (~9 hour) Karr run with 324 snapshots. pe-1 session will scaffold the comparison framework against this.

- `E:\opencell\data\m1_sources\karr_native\per_process_traces\<Process>_100ticks.mat` (28 files)
  - Bit-identical evolveState traces per process. Each Codex session uses its corresponding trace to validate per-tick rates.

- `E:\opencell\plan.md` and `E:\opencell\opencell_tasks.db`
  - Orchestrator-owned. Codex sessions must NOT modify these. Will sync at end of day.

</important_files>

<next_steps>

Immediate actions (in this order):

1. **View** `E:\opencell\SESSION_CONTEXT.md` to verify content matches the 6-rule contract I intended to write. If not, edit/recreate.

2. **Launch Wave 1 = 8 parallel Codex sessions**. For each task in {pc-t2, pc-t3, pc-t4, pc-t6, pc-t8, pc-t10, pd-t1, pe-1}:
   - `git -C E:\opencell worktree add E:\opencell-worktrees\<task> -b agent/<task>` (clean up stale worktree dirs first if needed)
   - Write a per-task prompt file with: mandatory preamble + Karr primary source pointers + scope (light/full + deferred mechanism list) + chassis pattern reference (point at `karr_replication_initiation.py`) + 5-7 test plan + DoD + commit message format
   - Launch detached: `codex exec --dangerously-bypass-approvals-and-sandbox -C <worktree> -o STATUS.md "$(prompt)"` via powershell async detached mode
   - Track shellIds for status polling

3. **Monitor cadence**: every 8-10 min run `scripts/codex_status.ps1` per worktree; stop any session with stdout idle >5 min AND no file growth

4. **As Wave 1 sessions complete**: 
   - Review STATUS.md per task
   - Run full test suite on each worktree to verify no regressions
   - Merge to main with `git merge --no-ff agent/<task>` + push
   - Update tasks db (status → done) 

5. **Launch Wave 2** (pc-t5 Segregation, pc-t7 Repair, pc-t9 Cytokinesis) once their dependencies (pc-t2 Replication, pc-t6 DNADamage, pc-t8 FtsZ) have landed on main

6. **Wave 3**: pc-final (build_karr_chassis_v5 + 10000-tick partial cell-cycle test) and pd-final (chassis_v6 = all 28 processes)

7. **End-of-day**: sync plan.md + opencell_tasks.db, write checkpoint, draft Day 8 blog post (single flowing dialogue style per yesterday's user feedback), push everything to origin/main

Open questions to consider once Wave 1 lands:
- Is Replication-light scope (fork counter, bulk demand, defer SSB/Okazaki/ligase) Karr-faithful enough to satisfy Phase E.1 trajectory match? May need to revisit if pe-1 reveals trajectory drift >10%.
- Should llm-log-pypi-package be slotted in as a side-quest if Codex bandwidth has slack?

</next_steps>