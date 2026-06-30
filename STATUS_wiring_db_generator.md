# Wiring DB Generator Status

## What Was Built

- Added `scripts/build_wiring_db.py`, a single-file CLI that:
  - discovers per-process wiring rows under `data/schemas/per_process_wiring/`
  - skips `_*.yaml` files
  - validates rows against the wiring contract described in `_schema.yaml`
  - runs cross-row checks for reciprocal dependency edges, cyclic hard-before ordering, and canonical roster completeness
  - emits `data/schemas/per_process_wiring/_combined.yaml` when run without `--validate-only`
- Added `tests/integration/test_build_wiring_db.py`, covering:
  - validate-only smoke behavior on the live wiring directory
  - combined YAML emission and top-level structure
  - reciprocal dependency mismatch detection
  - cyclic ordering detection

## Current Validation Output

- Command: `bin\oc-py scripts/build_wiring_db.py --validate-only`
- Exit code: `1`
- Row-level failures:
  - `Metabolism` is missing `schema_date`
  - `Metabolism` is missing the prompt-required provenance fields `last_audited`, `matlab_files_referenced`, and `oc_files_referenced`
- Cross-row summary:
  - `12 reciprocal mismatches`
  - `0 cyclic ordering`
  - `27 missing rows`
- The generator currently reports the live partial state as `FAIL`, which is expected until the remaining per-process rows land.

## Combined YAML

- Command: `bin\oc-py scripts/build_wiring_db.py --out data/schemas/per_process_wiring/_combined.yaml`
- Result: `_combined.yaml` was emitted successfully.
- Current emitted metadata includes `validation_status: FAIL` and `generator_commit: unknown` because the WSL subprocess could not resolve Git metadata in this environment.

## Tests

- Command: `bin\oc-pytest tests/integration/test_build_wiring_db.py -v`
- Result: `3 passed, 1 skipped`
- The validate-only smoke test is skipped in the current partial-state repo because there are fewer than 28 wiring rows checked in right now.

## Open Questions

- Should the checked-in wiring rows be updated to the prompt-required provenance shape (`last_audited`, `matlab_files_referenced`, `oc_files_referenced`) so validate-only can go green once the remaining rows land?
- Should the combined-file header treat Git commit capture as required, or is the current `unknown` fallback acceptable in WSL subprocesses?
