# STATUS_L22_PPII_FOLLOWUP

## In Progress

- Follow-up to `STATUS_L22_PPII.md`.
- Current focus:
  - add opt-in active-window manifest support to `scripts/l22_evidence/h12.py`
  - keep default H12 behavior unchanged when no manifest is supplied
  - build and validate a 50-seed `ProteinProcessingII` active-window manifest
  - rerun the real H12 producer on that manifest

## Checkpoints

- Started by re-reading:
  - `SESSION_CONTEXT.md`
  - `STATUS_L22_PPII.md`
  - `docs/phase_f/CHECKPOINT_2026-08-11.md`
  - `data/karr_vendored_source/ProteinProcessingII.m`
  - `scripts/l22_evidence/h12.py`
  - H12 producer/tests touching PPII, artifact validation, and side-index wiring
- Environment note:
  - this worktree's `data/m1_sources/karr_native/` is sparse, so the new
    manifest support must tolerate explicit per-seed trace paths instead of
    assuming every seed exists under the repo-local canonical tree
- Loader checkpoint:
  - added opt-in `--trace-window-manifest` support to `scripts/l22_evidence/h12.py`
  - added synthetic coverage in `tests/scripts/test_h12_trace_window_manifest.py`
  - targeted WSL-wrapper verification:
    - PASS:
      - `tests/scripts/test_h12_trace_window_manifest.py`
      - `tests/scripts/test_h12_artifact.py`
      - `tests/scripts/test_h12_anticheat.py`
    - unrelated baseline failure observed when broadening to
      `tests/scripts/test_h12_evidence_wiring.py`:
      - `MacromolecularComplexation.closed_form_dominant` is currently
        `candidate`, while that test file still asserts
        `confirmed_biology_validated`
      - not introduced by this change; left untouched for this track

## Open Work

- Implement manifest-backed oracle loading and CLI plumbing.
- Add/update tests for manifest-backed loading and the expected PPII verdict
  transition.
- Acquire `E:\opencell-worktrees\.opencell-matlab-lock` before any long MATLAB
  extraction/search work.
- If the lock is unavailable, stop after shipping the loader/tests/28-seed
  manifest subset and report `READY_FOR_MATLAB_22`.
