# Pre-staged Codex prompts for post-pb-final batch launch

When pb-final merges, the orchestrator will launch these 8 sessions in parallel from this single staging directory. Pre-written here to eliminate design-time latency at launch.

## Launch pattern

For each prompt below:
1. `git worktree add E:\opencell-worktrees\<name> -b agent/<name> main`
2. Copy the corresponding `<name>.md` to `<worktree>\.codex_prompt.md`
3. Launch `codex exec` as async session `codex-<name>`

## The 8 sessions

| Name | Worktree | Wall estimate |
|---|---|---|
| matlab-traces-a | matlab-traces-a | 30 min |
| matlab-traces-b | matlab-traces-b | 30 min |
| matlab-traces-c | matlab-traces-c | 30 min |
| matlab-traces-d | matlab-traces-d | 30 min |
| matlab-cell-cycle | matlab-cell-cycle | 1-3 hours |
| matlab-initial-states | matlab-initial-states | 10 min |
| matlab-fitted-constants | matlab-fitted-constants | 10 min |
| lint-debt | lint-debt | 30-60 min |

All 8 run in parallel. Expected total wall: ~3 hours bounded by cell-cycle.
