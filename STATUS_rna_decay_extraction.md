# STATUS — rna_decay extraction (L2.1 replay)

## Beat 1-5 block

### Beat 1 — Contract
- Required behavior: `tests/vivarium/test_karr_rna_decay_l2_replay.py` must replay RNADecay from per-tick Karr `states_before` state such that decay-driving RNA counts are restored like MATLAB `setForTest` semantics, not inferred from static fixture defaults.
- Done property: either (a) replay flips GREEN with `tick=0, substrates[0]` mismatch removed, or (b) we prove the replay trace lacks RNA-pool state so this cannot be fixed inside test/process code alone.

### Beat 2 — Surface
- Read surfaces:
  - `opencell/vivarium/karr_rna_decay.py`
  - `tests/vivarium/test_karr_rna_decay_l2_replay.py`
  - `tests/vivarium/l2_replay_common.py`
  - `scripts/extract_per_process_fixtures.py`
  - `scripts/extract_per_process_schema.py`
  - `docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md`
  - `docs/prompts/FIX_TEMPLATE_L2_REPLAY.md`
  - `docs/karr_extracts/process/01_Metabolism.md` (repo path replacement for missing `docs/architecture/L2_specs/01_Metabolism.md`)
  - `E:/opencell/data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/RNADecay.m` (source-of-truth MATLAB process)
  - `tests/vivarium/test_karr_dna_supercoiling_l2_replay.py` (sister replay pattern)
- Suspect patterns confirmed:
  - Replay test overlays only `substrates`, `enzymes`, `boundEnzymes`.
  - `RnaDecayLightProcess.next_update` reads `states['rna']['counts']`; if all zero it falls back to `self._fixture_rna_counts` (static init snapshot).
  - RNADecay trace has no RNA observable in `states_before`, so there is nothing to overlay for true per-tick RNA restoration.

### Beat 3 — Expected outcome
- Falsifier command if input existed: `pytest tests/vivarium/test_karr_rna_decay_l2_replay.py -v --tb=short`.
- Expected value if fix path were available: first mismatch `tick=0, observable=substrates, index=0 (AMP), diff=+1` becomes `diff=0`.
- Actual precondition observed: trace does not provide `rnas`/`rna` observable, so this expected change is not reachable by test-overlay wiring alone.

### Beat 4 — Inversion pre-mortem
- Failure mode 1: pass-like behavior by silently keeping fixture fallback (`_fixture_rna_counts`) instead of restoring trace RNA state.
- Failure mode 2: pass-like behavior by introducing oracle reads in production update path (Rule 8 violation).
- Failure mode 3: adding a tick-specific branch or tolerance relaxation that masks the same `tick=0 AMP +1` residue.

### Beat 5 — Act then verify
- Step executed: trace inspection only (per hard rule for missing RNA observable).
- Command:
  - `python -c "import h5py, pathlib; ... RNADecay_100ticks.mat ... print(keys/states_before/states_after/metadata)"`
- Measured result:
  - `states_before: ['boundEnzymes', 'enzymes', 'substrates']`
  - `states_after:  ['boundEnzymes', 'enzymes', 'substrates']`
  - No `rnas` / `rna` dataset present.
- Rule-driven stop: per case hard rule, stopped after Beat 5 step 1 diagnosis; no process/test code edits attempted.

## Trace inspection result
- `RNADecay_100ticks.mat` exists at `E:/opencell/data/m1_sources/karr_native/per_process_traces_v2/RNADecay_100ticks.mat`.
- Trace omits RNA-pool observable entirely.
- Therefore, Path A (in-test RNA overlay) is not possible in current artifacts.

## Fingerprint status
- Baseline fingerprint from task context remains the active known failure signature:
  - `tick=0, substrates[0] (AMP), diff=+1`.
- Not re-run in this turn after diagnosis, because the hard rule requires stop-at-step-1 when `rnas` is absent.

## Verification
- Rule 8 (no per-tick oracle reads in `opencell/vivarium/`): preserved; no production code changes made.
- Files modified in this run: only this status file.

## Verdict
- Honest RED with diagnosis type (b): **trace does not record RNA pool**.
- Required next action is extraction-pipeline extension (MATLAB side / trace schema) to include RNADecay RNA counts per tick (and optionally per-process `randStream` state if mismatch persists after RNA overlay is possible).

## Class-A transfer note
- This is a transferable hidden-state seeding pattern: any process whose `next_update` is linear/proportional in an internal species pool but whose L2 replay overlays only effectors (substrates/enzymes) is vulnerable to tick-0 one-count residues.
- Likely candidates: transcription/translation-adjacent processes with large `rna`/`protein` pools where fixtures currently provide static snapshots but traces do not expose the driving pool.
