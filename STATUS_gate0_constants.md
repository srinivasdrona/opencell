# STATUS — Gate 0 constants

## Scope
- Additive only: create `scripts/matlab/gate0_dump_process_constants.m`
- Additive only: create `scripts/gate0_verify_constants.py`
- Additive only: generate `data/karr_input_spec/_gate0_source_constants.json`

## Files created
- `scripts/matlab/gate0_dump_process_constants.m`
- `data/karr_input_spec/_gate0_source_constants.json`
- `STATUS_gate0_constants.md`

## Progress
- Read `SESSION_CONTEXT.md` and existing Gate 0 stoichiometry dumper/comparator patterns.
- Read `scripts/matlab/gate0_inventory_constants.m` and fixture extraction references for constant name handling.
- Worktree note: repo is on `main` with unrelated pre-existing dirty/untracked files; left untouched.
- Implemented the MATLAB dumper using live getter-resolved `fixedConstantNames` / `fittedConstantNames`, `local_leaf_name(class(p))` process keys, and exact numeric sparse nonzero encoding via `find(M)` / `M(idx)`.
- Sanity check on the generated JSON: `28` processes, `366` fixed names, `3` fitted names, `368` unique constants. The `369` raw-name total collapses to `368` unique constants because `Transcription.transcriptionUnitBindingProbabilities` appears in both fixed and fitted lists.
- Live-source variance from the prompt/inventory summary: three declared cell constants are not pure `cellstr` and were dumped as strict general cells (`DNADamage.reactionVulnerableMotifs`, `MacromolecularComplexation.complexNetworks`, `Replication.primaseBindingLocations`) to preserve source fidelity.

## MATLAB run
- Command:
  `& "E:\MATLAB\bin\matlab.exe" -batch "cd('E:\opencell'); addpath('E:\opencell\scripts\matlab'); gate0_dump_process_constants('data/karr_input_spec/_gate0_source_constants.json')"`
- Result: exit `0`.
- Output summary: dumped all `28` processes and wrote `data/karr_input_spec/_gate0_source_constants.json` with `368` unique constants.

## Comparator verdict
- Pending.

## Commits
- Checkpoint 1: pending
- Checkpoint 2: pending
