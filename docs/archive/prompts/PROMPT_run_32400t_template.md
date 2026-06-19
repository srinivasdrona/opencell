# 32,400-tick OpenCell run — ensemble member, seed __SEED__

## Goal

Run our chassis_v6 simulation for one complete *M. genitalium* cell cycle (32,400 ticks of biological time on `agent/phase-2-fix` HEAD `b9de5a9`) with deterministic seed **__SEED__**. This is **one of 4 parallel ensemble members** (seeds 42/43/44/45). Each member runs independently in its own worktree; no coordination needed.

Capture trajectories of every quantity in `E:\opencell\PASS_CRITERIA_32400t.md` for downstream grading against Karr 2012.

## Hard rules

- 130k token ceiling. Compact + STATUS before crossing (even mid-run).
- Commit incrementally to your branch.
- **DO NOT pause to ask the user questions.** Pick safe default, document, proceed.
- Untracked `.codex*.log` / `.launch*.ps1` files: gitignored.
- Work in worktree **`__WORKTREE__`** on branch **`__BRANCH__`**. **`b9de5a9` must be an ancestor of HEAD** AND `git diff b9de5a9 HEAD -- opencell/` must be empty (no opencell/ code changes since b9de5a9; commits since then are docs/prompts only). Verify with:
  - `git merge-base --is-ancestor b9de5a9 HEAD` (exit 0)
  - `git diff b9de5a9 HEAD -- opencell/` (empty output)
  If either check fails, write blocker to STATUS and stop. DO NOT rebase.
- Use the project venv: `E:\opencell\.venv-opencell\Scripts\python.exe`.
- This is a long run (~9–16 hours). The other 3 ensemble members are sharing the box — expect CPU contention. Don't try to optimize speed; just complete.

## What "32,400 ticks" means

- Karr 2012 cell cycle ≈ 32,400 seconds biological time at Δt=1s.
- Our chassis steps at our own timestep. Inspect chassis_v6 config to determine our timestep.
  - If 1s: 32,400 ticks.
  - If 2s: 16,200 ticks.
  - **Whatever the chassis is configured for, simulate 32,400 s biological**. Document the math in STATUS.

## Setup

1. `git merge-base --is-ancestor b9de5a9 HEAD` (must exit 0) AND `git diff b9de5a9 HEAD -- opencell/` must be empty. If either fails, write blocker to STATUS and stop.
2. `python -m pytest tests/integration/test_chassis_v6_substrate_drainers.py` → must pass.
3. Seed is **__SEED__**. Set this in the simulation entrypoint (numpy + python `random` + any RNG the chassis uses).
4. Output dir: `artifacts/run_32400t_seed__SEED__/`.

## What to emit

Per-tick or per-N-tick CSVs (down-sample if total > 500 MB; document sampling rate):

| File | Contents |
|---|---|
| `artifacts/run_32400t_seed__SEED__/key_substrates.csv` | The 7 quantities in PASS_CRITERIA (ATP/GTP/CTP/UTP, dNTPs, 20 AAs, total RNA, total protein, mass, volume) per tick. **THIS IS THE MOST IMPORTANT OUTPUT.** |
| `artifacts/run_32400t_seed__SEED__/substrates_full.csv` | All 805 substrates per tick. Compress with gzip if > 500 MB. |
| `artifacts/run_32400t_seed__SEED__/replication_events.csv` | Replication initiation tick, fork progression, completion tick. |
| `artifacts/run_32400t_seed__SEED__/division_event.json` | Division tick + final state at division (if reached). |
| `artifacts/run_32400t_seed__SEED__/conservation.csv` | Per-tick `unattributed_delta` for all substrates (sanity). |
| `artifacts/run_32400t_seed__SEED__/process_traces/<proc>.csv` | Per-process substrate delta trace (every 10 ticks is fine). |
| `artifacts/run_32400t_seed__SEED__/manifest.json` | Full run config: HEAD SHA, **seed=__SEED__**, timestep, tick count, biological seconds, wall-clock duration, Python version, library versions. |

## Diagnostic level

Use the same diagnostic level as the 1000t canary on this branch. Don't disable diagnostics to gain speed — we need the conservation trace to detect any cascade regression mid-run.

## During the run

Print progress to stdout AND to `.codex_run_seed__SEED__.log` every 1000 ticks: tick number, ATP count, total mass, wall-clock elapsed, ETA. This lets the operator monitor without interrupting.

## After the run

Write `STATUS_run_seed__SEED__.md`:
- HEAD SHA, **seed=__SEED__**, timestep, total ticks, biological seconds simulated.
- Wall-clock duration.
- Did it complete? Crash mid-run? Cell never replicated? Document.
- Key milestones: replication initiation tick, replication completion tick, division tick (if any).
- Final ATP, total mass, total RNA, total protein.
- Conservation: max `|unattributed_delta|` over the whole run.
- Per-process exception count.
- Files produced (paths + sizes).
- Verdict: `complete-ready-for-grading` | `partial-needs-investigation` | `crashed`.

Commit everything you can (use git-lfs if available for large CSVs; otherwise commit only the summaries and document large-file local paths in STATUS).

## What you must NOT do

- Don't modify any code in `opencell/` package. This is a pure run. If something is broken, write a blocker and stop.
- Don't disable the drainer regression test.
- Don't grade results — that's the next Codex session's job.
- Don't try to coordinate with the other 3 ensemble members. They're independent.

## Token budget

130k ceiling. Compact + STATUS before crossing, even mid-run.
