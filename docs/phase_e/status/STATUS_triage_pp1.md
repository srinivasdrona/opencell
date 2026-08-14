# PP1 triage outcome: 35B -> 24840B at 1000t

Fix-only triage for `karr_protein_processing_i` completed on branch `triage/protein-processing-i`.

## Diagnose anchor (already published)

- Diagnose STATUS: `E:\opencell-worktrees\swarm-dead-protein_processing_i\STATUS_dead_protein_processing_i.md` (see sections 6 and 7).
- Source evidence carried into this fix:
  - `C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\PROCESS_STATUS_ALL_28.md` row 16 (`R12`, verdict `(c)`, `MG_106_DIMER` not seeded in PP1 gate store).
  - PP2 sibling pattern (reads `protein.enzyme_counts`): `opencell/vivarium/karr_protein_processing_ii.py:159,199`.
  - Composite enzyme init site (PP2 already seeded there): `opencell/vivarium/karr_composite.py:1606` (diagnose reference line), now extended for PP1 in this branch.

## Commits landed

1. `5607075` — `fix(pp1): seed deformylase + aminopeptidase enzymes; read from enzyme_counts`
2. `d4c7b58` — `test(pp1): integration guard that pp1 writes deltas at tick 1`
3. `status(pp1): triage outcome + canary delta` (this STATUS file)

## File-by-file diff summary

- `opencell/vivarium/karr_protein_processing_i.py`
  - Switched PP1 enzyme port usage to `protein.enzyme_counts` and added backward-compatible fallback to `protein.counts` when `enzyme_counts` is absent (`:110`, `:145-152`).
- `opencell/vivarium/karr_composite.py`
  - Extended `protein_enzyme_init` to include PP1 enzymes and seeded:
    - `MG_106_DIMER = 22.0`
    - `MG_172_MONOMER = 38.0`
    - with inline provenance comment `# from PP1_flat.mat enzymes column` (both v4/v5 builder paths: `:1146-1147`, `:1744-1745`).
- `tests/integration/test_pp1_runs.py`
  - Added integration guard that builds `chassis_v6`, verifies PP1 enzyme seed presence, seeds one PP1 precursor, runs <=5 ticks, and asserts PP1 produces a positive `protein.processed_counts` delta.

## Verification

- Targeted test (requested):
  - Command:
    - `wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/triage-protein-processing-i && pytest tests/integration/test_pp1_runs.py -xvs"`
  - Result: `PASSED` (`1 passed`).

- Full integration sweep:
  - Requested command with `--timeout=120` failed at CLI parse because pytest-timeout plugin is not installed in this environment.
  - Executed:
    - `wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/triage-protein-processing-i && pytest tests/integration/ -x"`
  - Outcome: stopped on pre-existing failure:
    - `tests/integration/test_karr_chassis_v3.py::test_d2_and_decay_both_active`
  - Control check at pre-fix base commit `c681d83` (`HEAD~2` detached worktree) reproduces the same failure, confirming this is not introduced by PP1 fix.

- 1000t canary (requested):
  - Run command:
    - `wsl bash -lc "source /mnt/e/opencell/.venv-wsl/bin/activate && cd /mnt/e/opencell-worktrees/triage-protein-processing-i && python scripts/run_chassis_v6_32400t.py --seed 42 --biological-seconds 1000 --out-dir artifacts/canary_pp1_fix --fresh"`
  - Runtime note: simulation completed to tick `1000/1000`; script then failed in manifest `git rev-parse` under WSL worktree path translation.
  - Trace proof command:
    - `wsl bash -lc "ls -la /mnt/e/opencell-worktrees/triage-protein-processing-i/artifacts/canary_pp1_fix/process_traces/karr_protein_processing_i.csv && wc -l /mnt/e/opencell-worktrees/triage-protein-processing-i/artifacts/canary_pp1_fix/process_traces/karr_protein_processing_i.csv"`
  - Result:
    - size: `24840` bytes
    - lines: `525`

## Canary delta vs still-dead reference

- Before (still-dead proof point): `E:\opencell\artifacts\canary_1000t_wave2_post_trna_20260527_121742\process_traces\karr_protein_processing_i.csv`
  - `35` bytes, `1` line (header only).
- After this fix: `artifacts/canary_pp1_fix/process_traces/karr_protein_processing_i.csv`
  - `24840` bytes, `525` lines.
