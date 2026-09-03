# STATUS: L2.1 ChromosomeCondensation Restart

Result: NARROWER BLOCKER

I recovered the exact MATLAB-visible pre-warmup surface and hash-bound it, but I did not close `ChromosomeCondensation` to bit-identical / `GENUINE` in this turn. The remaining failure is now localized to the literal warmup / first no-hint bind semantics, and live MATLAB validation of the warmup endpoint is temporarily blocked by occupied shared MATLAB slots.

## Context loaded

- Read:
  - `SESSION_CONTEXT.md`
  - `PROMPT.md`
  - `PROMPT_FOLLOWUP.md`
  - `PROMPT_MATLAB_RESTART.md`
  - `STATUS_L21_CHROMCOND_FOLLOWUP.md`
  - latest available checkpoint `docs/phase_f/CHECKPOINT_2026-08-11.md`
- The task prompt references `docs/phase_f/CHECKPOINT_2026-08-14.md`, but that file is not present in this worktree.

## Preserved worktree state

- I preserved the existing dirty tree and did not discard any in-flight work.
- Existing task-related edits still include:
  - `opencell/vivarium/karr_chromosome_condensation.py`
  - `data/schemas/per_process_wiring/ChromosomeCondensation.yaml`
  - prior and newly added `tmp/chromcond_*` probes

## Recovered MATLAB pre-warmup surface

I added `tmp/chromcond_extract_prewarmup_state.m` and used the restored MATLAB path to serialize the exact boundary immediately before `ChromosomeCondensation.initializeState()` begins its 20 warmup `evolveState()` calls:

- truncate `sim.processesInInitOrder` immediately before `ChromosomeCondensation`
- run real `sim.initializeState()`
- refresh the target with `target.copyFromState()`
- save process-local counts, target `mcg16807` state scalar, and sparse chromosome fields

Saved artifact:

- `tmp/chromcond_prewarmup_state.mat`
- SHA256: `d85a918ba5d405903c2b6d3d86691617c3c6e9305a99a8ca2296acba9926d950`

Artifact contents confirmed with `bin\oc-py.cmd tmp/chromcond_prewarmup_inspect.py`:

- `seed=0`
- `target_init_order_slot_1based=12`
- pre-warmup local `substrates=[37948, 3795, 7590, 324390814, 13662]`
- pre-warmup local `enzymes=[80, 0]`
- pre-warmup local `boundEnzymes=[0, 0]`
- pre-warmup `randStream.type=mcg16807`
- pre-warmup `randStream.state=931316785`
- pre-warmup `complexBoundSites={1:51, 165:2, 181:28, 193:4}`
- pre-warmup `monomerBoundSites={101:1}`

## Hash binding

Fixture / source hashes used in this restart:

- `data/karr_fixtures/per_process/ChromosomeCondensation_flat.mat`
  - `d8a5813d3010ac2af315e0ca964be0a8d68d230da02a93ee0d699c1696a96883`
- `data/karr_fixtures/per_process/Chromosome_flat.mat`
  - `e4c05522d28db93e0a3c73dcc7e6a3f9e526c47ef1119aa7c6d5624a7557d602`
- `data/karr_fixtures/per_process/Metabolite.json`
  - `7e633af3d511b21dbac8eb4f38b12656729b2a8a320d68b32e4855b3ffa13de7`
- WholeCell `ChromosomeCondensation.m`
  - `6a0c51deadd476b6f2aecfa143b68dc23c13f42e5a37bdb2cb924d3d0812c5d9`
- WholeCell `Process.m`
  - `4de6c9b86a0eb9a01915e81f9f7d9a0abb96804f1e0fb1c6c6bd030abac25cbb`
- WholeCell `ChromosomeProcessAspect.m`
  - `cc424f887bae0d653ec449289b0e60d845d26038ac5ed1859c61dcc386589f75`
- WholeCell `RandStream.m`
  - `2ba41e2ff7ee023b1164f2ff9f3b2053063398dff0c06d0d564c498a5b42da89`
- WholeCell `@Simulation/initializeState.m`
  - `efc1a8c530653149af70b10adcd3b4948e5a338bd17ad9dc11978ebcf5bdb648`
- WholeCell opaque fixture `src_test/.../ChromosomeCondensation.mat`
  - `8551e9d068ee971080ad75029567d16b0b81ad5616b65a98bd28838915d0965f`

## What I changed

Production-side source-faithfulness change:

- `opencell/vivarium/karr_chromosome_condensation.py`
  - `_exclude_regions_literal()` now mirrors MATLAB `Chromosome.excludeRegions()` using `excLens(end)` in both branch conditions instead of the indexed matched interval lens.
  - `_sample_binding_regions_literal()` now calls the exact `MatlabRandStream.randsample(...)` helper for weighted region choice instead of a hand-rolled threshold picker.

New / updated restart probes:

- `tmp/chromcond_prewarmup_inspect.py`
- `tmp/chromcond_prewarmup_replay_probe.py`
- `tmp/chromcond_validate_warmup_state.m`

## Replay findings from the recovered pre-warmup state

I used `tmp/chromcond_prewarmup_replay_probe.py` to replay the warmup from the captured boundary and compare the tick-0 no-hint new SMC sites against the hidden Karr state.

Known hidden Karr tick-0 new SMC sites:

- `[(172651, 0), (189029, 0), (510535, 0)]`

Important observation:

- later init-order processes do mutate the chromosome after the recovered pre-warmup boundary and before tick 0
- pre-warmup vs hidden tick-0-before shows:
  - complex `1`: `51 -> 47`
  - complex `181`: `28 -> 23`
  - complex `200`: `0 -> 40`
  - complex `82` (SMC-ADP): `0 -> 78`

So the hidden tick-0 `78` SMC count is not a safe direct oracle for the immediate warmup endpoint by itself.

Warmup variants tried from the recovered boundary:

1. `evolveState`-style bookkeeping, with inner `randperm`
2. `evolveState`-style bookkeeping, without inner `randperm`
3. replay-`next_update` bookkeeping, with inner `randperm`
4. replay-`next_update` bookkeeping, without inner `randperm`

None reproduced the hidden tick-0 new SMC sites exactly.

Representative outcomes:

- `evolveState` + inner `randperm`
  - post-warmup RNG state: `755788785`
  - tick-0 new SMC sites: `[(172486, 0), (189341, 0), (507997, 0)]`
- `evolveState` without inner `randperm`
  - post-warmup RNG state: `550280594`
  - tick-0 new SMC sites: `[(172504, 0), (189016, 0), (509308, 0)]`
- replay-`next_update` + inner `randperm`
  - post-warmup RNG state: `934013488`
  - tick-0 new SMC sites: `[(172634, 0), (189421, 0), (509597, 0)]`
- replay-`next_update` without inner `randperm`
  - post-warmup RNG state: `1381806990`
  - tick-0 new SMC sites: `[(172547, 0), (190815, 0), (506097, 0)]`

This means the problem is no longer “missing pre-warmup surface.” The remaining gap is in the literal warmup / bind geometry semantics that still differ from WholeCell source behavior.

## Current strict-rubric status

`bin\oc-py.cmd tmp/_strict_classify.py`

- `{'name': 'ChromosomeCondensation', 'verdict': 'FAIL', 'bit_identity_failures': 1, 'karr_active': 66, 'oc_fired_on_karr_active': 66, 'fire_rate_when_karr_active': 1.0, 'n_ticks': 100}`

So the row is still a deterministic bit-identity failure, not an activity / fire-rate failure.

## Verification run

Green:

- `bin\oc-pytest.cmd tests/vivarium/test_karr_chromosome_condensation.py -q`
  - `6 passed`
- `bin\oc-pytest.cmd tests/vivarium/test_karr_chromosome_condensation_l2_replay.py -q`
  - `1 passed`
- `bin\oc-pytest.cmd tests/util/test_matlab_rng.py -q`
  - `23 passed, 3 xpassed`
- `bin\oc-py.cmd -m ruff check opencell/vivarium/karr_chromosome_condensation.py tmp/chromcond_prewarmup_inspect.py tmp/chromcond_prewarmup_replay_probe.py`
  - PASS

Still failing on the real target surface:

- strict rubric remains `FAIL` for `ChromosomeCondensation`

## Remaining blocker

The remaining blocker is now precise:

- I need one live validation pass of the actual MATLAB warmup endpoint from the recovered pre-warmup boundary to separate:
  - wrong OC warmup bookkeeping / bind geometry
  - from any remaining misunderstanding of how WholeCell arrives at the post-warmup process/RNG state

I prepared `tmp/chromcond_validate_warmup_state.m` for that purpose, but I could not execute it because both shared MATLAB slots were occupied by other active worktrees during this turn:

- `l22-ppii`
- `l22-dnas`

Without that live validation, I can narrow the source gap, but I cannot honestly claim bit-identical / `GENUINE` closure.

## Next step

When a MATLAB slot opens, run:

```powershell
& "C:\Users\sdrona\.copilot\session-state\5c51d44b-5a9f-4b23-85ff-0fddaadf2212\files\with_matlab_slot.ps1" `
  -Worktree "E:\opencell-worktrees\wave-l21-chromcond" `
  -Tag "l21-chromcond" `
  -MatlabExpression "run(fullfile('E:/opencell-worktrees/wave-l21-chromcond','tmp','chromcond_validate_warmup_state.m'))"
```

Then compare the reported post-warmup:

- `randStream.state`
- local `enzymes`
- local `boundEnzymes`
- chromosome `complexBoundSites == SMC_ADP`

against the four replay variants above and patch the remaining literal bind-region semantics accordingly.
