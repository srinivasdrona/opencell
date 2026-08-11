# STATUS: L22 DNADamage

**Date:** 2026-08-12
**Checkpoint base:** `docs/phase_f/CHECKPOINT_2026-08-11.md`
**Authoritative contract:** `DNADamage`, `harness_type=event_class`, `M_ticks=20`, `N_seeds=50`, primary projection = `damage_event_present` plus 7 chromosome `delta_nnz` channels including `hollidayJunctions`.
**Current overall state:** lane 1 committed green (`e90444f`); lane 2 code/tests/preflight green locally; no shared index/catalog edits made; real MATLAB extraction not launched because the required shared-lock acquisition surface is unavailable in this checkout.

## Slot 1 — Deliberate Action Prefix

1. Close the structural chromosome-channel gap first, then extend the stimulus-conditioned extraction path, then attempt real MATLAB execution only after code/tests/preflight are green.
2. Work surfaces: `opencell/vivarium/karr_dna_damage.py`, DNADamage tests, `scripts/matlab/extract_per_process_traces_v2.m`, event/planning helpers, and DNADamage stimulus artifacts only.
3. Done means either a real stimulus-conditioned Karr-vs-OC verdict exists with all 8 channels measurable, or an exact MATLAB/source blocker is recorded as `READY_FOR_MATLAB`.
4. Pre-mortem: the likely false-green modes are (a) treating no-stimulus traces as positive evidence, (b) leaving `hollidayJunctions` silently unwired, or (c) adding an extractor override that is not identity-bound in metadata and can be confused with the old quiescent traces.

## Slot 2 — Composition / Replay Guardrails

- No shared catalog/index mutation in this worktree.
- Existing no-stimulus DNADamage traces are not counted as positive evidence.
- The OC-only mechanism canary remains non-gating.
- Event-window metadata remains the required shape for any new fixed-window stimulus traces.

## Lane 1 — Holliday Junction Port

**Verdict:** GREEN

### Change

- Added `hollidayJunctions` to the real DNADamage chromosome sparse-field schema/update path in `opencell/vivarium/karr_dna_damage.py`.
- Extended DNADamage unit/replay field lists so state templates and update application include `hollidayJunctions`.
- Updated the live mechanism-canary expectations so the field is measured rather than reported as structurally absent.

### Verification

- `bin\oc-py.cmd -m pytest tests/vivarium/test_karr_dna_damage.py::test_emits_substrate_requests_from_vulnerable_site_rates -q`
- `bin\oc-py.cmd -m pytest tests/vivarium/test_karr_dna_damage_l2_replay.py::test_karr_dna_damage_l2_replay_identity_per_tick -q`
- `bin\oc-py.cmd -m pytest tests/scripts/test_dna_damage_mechanism_canary.py::test_structurally_absent_fields_are_schema_derived_not_hardcoded -q`

All three targeted checks passed under the WSL-backed wrapper.

## Lane 2 — Stimulus-Conditioned Karr Cohort

**State:** GREEN_FOR_PREFLIGHT, `READY_FOR_MATLAB`

### Required outcome

- Extend the canonical MATLAB extractor so a source-backed UVB or gamma substrate condition can be requested explicitly.
- Persist enough metadata that a stimulus-conditioned trace cannot be confused with the existing quiescent no-stimulus traces.
- Pre-register the 50-seed x 20-tick UVB/gamma cohort without editing shared indexes.
- If MATLAB is unavailable after code/preflight is ready, stop with an exact `READY_FOR_MATLAB` blocker.

### Change

- Extended `scripts/matlab/extract_per_process_traces_v2.m` with an optional `extraction_opts` surface for:
  - `condition_label`
  - `metadata_identity_json` persisted as `metadata.extraction_identity_json`
  - real scheduler-path `per_process_substrate_overrides` applied before `calcResourceRequirements_Current()` and again after allocation injection but before `evolveState()`
- Extended `scripts/l2_event/launcher.py` so fixed-window specs can carry:
  - exact `extraction_identity_json`
  - nested MATLAB struct payloads via `matlab_extraction_opts`
  - validate-before-skip refusal on wrong or missing `metadata.extraction_identity_json`
- Added `scripts/l2_event/dna_damage_stimulus_cohort.py`, a MATLAB-free preregistration/preflight planner for:
  - `uvb_mechanism`
  - `gamma_mechanism`
  - 50 seeds labeled `2000..2049`
  - canonical condition-rooted outputs under `data/m1_sources/karr_native/dnadamage_stimulus_cohort/<condition>/per_process_traces_v2_event_s<seed>/DNADamage_20ticks.mat`
- Updated `scripts/dna_damage_mechanism_canary.py` so the biological blocker contract now points at the real stimulus cohort preflight instead of the old “extractor has no override argument” gap.

### Verification

- `bin\oc-py.cmd -m pytest tests/scripts/test_extract_per_process_traces_v2_static.py -q`
- `bin\oc-py.cmd -m pytest tests/scripts/test_l2_event_launcher.py -q`
- `bin\oc-py.cmd -m pytest tests/scripts/test_dna_damage_stimulus_cohort.py -q`
- `bin\oc-py.cmd -m pytest tests/scripts/test_dna_damage_mechanism_canary.py -q`

All four targeted WSL-backed checks passed:
- extractor static contract: `7 passed`
- launcher: `78 passed`
- DNADamage stimulus cohort planner: `3 passed`
- DNADamage mechanism canary: `15 passed`

### MATLAB blocker

- `matlab.exe` is present at `E:\MATLAB\bin\matlab.exe`.
- Karr source roots are present at `E:\opencell\data\m1_sources\karr_native` and `E:\opencell\data\m1_sources\WholeCell`.
- No shared MATLAB lock acquisition helper/surface is discoverable in this worktree under `bin/`, `scripts/`, or the task-read docs, and the host MATLAB license is documented elsewhere in-repo as single-seat/serialized.
- Per task instructions, I therefore did **not** launch an unlocked extraction run. The exact stop point is:

`READY_FOR_MATLAB`: code, tests, and stimulus cohort preflight are green; real UVB/gamma MATLAB extraction awaits the shared lock mechanism so a 50-seed source-backed event verdict can be produced safely.
