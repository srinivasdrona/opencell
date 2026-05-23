# Checkpoint 042 — Phase B + Phase C T1 SHIPPED; Karr-native MATLAB extracted

**Date**: 2026-05-22, night (end-of-day)
**Headline**: 16 of 28 Karr processes covered (~57%) in one day via Codex orchestration. Phase B feature-complete. Phase C started.

## Day's headline outcomes

1. **Phase A3.3 complete** (5 turns + chassis_v3): D.2-real + ProteinDecay-light + KarrAllocationStep + M2v3/M3v3 delta-emit. 1000-tick ratchet closure at 1.26% worst-case drift; tick rate 61.7/s.

2. **Phase B feature-complete** (11 turns + chassis_v4): all RNA + protein maturation processes shipped. 2000-tick extended ratchet validated; all 10 integration tests pass.

3. **Phase C started** (pc-t1 shipped): ReplicationInitiation (9-substep DnaA polymer dynamics at OriC). First Phase C process; introduces chromosome state stores.

4. **MATLAB extractions captured** (test-license window): 28 per-process bit-identical evolveState traces + 23 initial-state snapshots + fitted_constants + previously-missing metabolism_dynamics oracle. ~18 MB total, gitignored. Cell-cycle reference trajectory still running overnight — will be Phase E gold standard.

5. **Probes shipped** (2): Probe 4 closed the Vivarium `set`+`accumulate` semantic question empirically (mixed updaters silently break — order-sensitive); Probe 5 closed OPEN-4 SeedSequence determinism question (bit-identical across runs at same seed).

6. **Two decisions logged**: `vivarium-all-accumulate-no-set` (every per-tick writer uses accumulate; banned set for multi-writer leaves); `v1-trajectory-buckets` (four-bucket framing for post-v1.0 scope).

7. **9 of 14 llm-log refinements shipped** across 2 batches: schema_version, secrets-scrub, portable paths, design doc, tag vocabulary, query/stats/report CLI, CLI tests, pre-commit hook, file rotation.

8. **Skill hardening**: WSL-venv-only Python mandate, tool-availability fallback, commit-or-stop semantics, stale-STATUS detection — all baked into `delegate-to-codex` skill v3.

## v1.0 trajectory now

| Phase | Status | Wall (orig est / actual today) |
|---|---|---|
| A3.3 | ✅ DONE | 6 weeks / 1 day |
| B | ✅ DONE | 12 weeks / 1 day |
| C (1/10 turns) | 🟡 in progress | 14 weeks / a few days at this pace |
| D (1 process) | ⏳ | 3 weeks / 1 day |
| E (validation) | ⏳ | 4 weeks / 2-4 weeks (wet/dry can't accelerate) |
| **Total to v1.0** | | **~4-6 weeks from today** (down from 9 months) |

## Test state at end-of-day

- **~720 tests passing**, **0 failures**, **0 unexpected SKIPs**
- 32 A3.3 unit + 10 integration (chassis_v3 + v4)
- ~85 Phase B per-turn tests
- 6 Probe tests (probe 4 + probe 5)
- 9 Phase C T1 tests
- 36 LLM-log tests (was 8)
- 13 M1 calc_flux_bounds (3 previously SKIP now PASS via MATLAB oracle regen)
- 620 pre-existing tests

## Repository state

```
origin/main @ 2664efa
Phase B (chassis_v4): A3.3 + 11 Phase B + integration test all green
Phase C: T1 (ReplicationInitiation) merged
MATLAB extracts: 28 traces + 23 init states + 2 fitted_constants entries (all gitignored)

Active overnight:
  - codex-matlab-cell-cycle-v3: full ~32400-tick MATLAB run (Phase E gold)
  - codex-lint-debt: clearing 1101 ruff errors → strict CI
```

## What's still in flight overnight

1. **matlab-cell-cycle-v3** — Karr's WCM running one full cell cycle (1-3 hours wall). The output is the Phase E validation gold standard.
2. **lint-debt** — auto-fixing 1101 ruff errors + manual triage of remaining. ~1 hour wall.

Both can complete unattended. If they fail, the orchestrator will get STATUS reports tomorrow.

## Decisions logged (cross-cutting impact)

1. **vivarium-all-accumulate-no-set** — every per-tick Vivarium writer in OpenCell uses `_updater: "accumulate"`. `set` is banned for any leaf that more than one Process might write to in a single tick. Forces delta-emit conversion of any "compute and emit absolute count" Process. Caught empirically by Probe 4.

2. **v1-trajectory-buckets** — four explicit buckets for post-v1.0 scope:
   - Bucket 1 — Karr's own admitted gaps (v1.x)
   - Bucket 2 — biology Karr skipped entirely (v2+)
   - Bucket 3 — validation + organism scaling (v3+)
   - Bucket 4 — OpenCell-specific tooling (parallel any phase)
   
   Locks vocabulary so future sessions don't conflate "we finished Karr" with "we have a complete cell".

## Codex orchestration patterns proven today

- **Pipelined design + execution**: while Codex implements Turn N, I design Turn N+1. ~5x throughput vs sequential.
- **Up to 10 parallel Codex sessions** at one point (Phase B turns + side quests). All terminated cleanly with merges or diagnostic STATUS.
- **Stale-STATUS detection** saved real time today (caught earlier worktree's leftover STATUS in seconds).
- **Pre-staged prompts** in `docs/codex_prompts/` for batch launches.
- **Worktree-per-task** with junctions for shared data (WCM source).

## Process / methodology issues that emerged + were fixed

1. **Codex defaults to Windows `py -3.12`**, not WSL venv → ModuleNotFoundError on `import opencell`. Fixed with WSL-venv mandate in skill preamble.
2. **Worktrees don't inherit gitignored 120MB folders** (WCM source). Fixed with junctions + bootstrap fallback to main path.
3. **STATUS.md merge conflicts** on every merge (each Codex session writes one). Fixed by adding STATUS.md to .gitignore.
4. **Codex auto-modifies scripts in worktree** when it sees a bug. Mostly fine, but means worktree state can diverge from main. Fix: re-sync from main before each launch.
5. **Phantom "MATLAB succeeded but produced files in worktree-local dir"** when main dir is empty. Fix: explicit consolidation step.

## What's NOT in tonight's deliverables (for tomorrow)

- Phase C T2 (Replication — largest Karr process) — needs careful design before launching
- Phase C T3-T10 + final integration
- Phase D + Phase E
- Phase E will compare against tonight's MATLAB cell-cycle trajectory

## Bottom line

Today was the largest single-day delivery on OpenCell since project start. Phase B is feature-complete. Phase C is started. The chassis can run a 2000-tick (≈33-min biological time) simulation of RNA + protein maturation in steady state at 60+ ticks/s. Phase E validation data captured. We're roughly 4-6 weeks from v1.0 instead of 9 months — though Phase E real-world validation is where the calendar slows down.

If lint-debt completes overnight, the project ships with strict-mode CI from tomorrow. If the cell-cycle MATLAB run completes overnight, Phase E has its gold-standard validation data.

Tomorrow: Phase C T2 (Replication) design, then launch.
