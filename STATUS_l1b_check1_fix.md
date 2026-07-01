# STATUS — L1b Check 1 Tooling Fix (2026-07-01)

## Slot 1: DELIBERATE_ACTION_PREFIX_v2

Beat 1 - Pause and name the contract:
- Objective: close L1b Check 1 tooling gaps (encoding, mirror-path portability, derived-doc anchors) so row-vs-code verification can complete deterministically.

Beat 2 - Point at the surface:
- Updated tooling: `scripts/l1b_verify_wiring.py`.
- Updated row data: `data/schemas/per_process_wiring/DNASupercoiling.yaml` and regenerated `data/schemas/per_process_wiring/_combined.yaml`.
- Updated tests: `tests/integration/test_l1b_verify_wiring.py`.
- Updated decision ledger: `docs/phase_f/L1B_WIRING_CONFORMANT_GATE.md` (D6/D7/D8).
- Updated report artifact: `tmp/l1b_after_check1_fix.txt`.

Beat 3 - Verbalize expected outcome:
- `bin\oc-py scripts/l1b_verify_wiring.py --out tmp/l1b_after_check1_fix.txt --format md` should report `28/28 PASS`.

Beat 4 - Invert (pre-mortem):
- Risk considered: permissive `.md` handling could over-admit weak anchors and hide source drift.
- Mitigation: `.md` handling emits explicit warnings and `.m` verification remains strict; mirror rewrites also emit warnings.

Beat 5 - Act, then verify:
- Implemented and validated all requested checks and artifacts; L1b is now `28/28 PASS`.

## Scope Completed
- Fix A: MATLAB read path now uses UTF-8 with Latin-1 fallback on `UnicodeDecodeError` only.
- Fix B: Check 1 now supports defensive mirror-path rewrite (`E:/opencell-mirrors/opencell/...` -> repo-relative) with warning, and DNASupercoiling row is canonicalized to `data/m1_sources/...`.
- Fix C: Check 1 now supports `.md` extract-doc anchors with permissive matching and warning.
- Tests added:
  - `test_check1_latin1_matlab_file_decodes`
  - `test_check1_mirror_path_rewrite`
  - `test_check1_md_extract_doc_permissive`
- Decision ledger updated with D6/D7/D8.

## Verification
- `bin\oc-py scripts/l1b_verify_wiring.py --out tmp/l1b_after_check1_fix.txt --format md` -> PASS (`28/28`, `0 FAIL`).
- `bin\oc-py scripts/build_wiring_db.py --validate-only` -> PASS.
- `bin\oc-pytest tests/integration/test_l1b_verify_wiring.py` -> PASS (`9 passed`).

## Operator Recommendation
- Prefer canonical MATLAB `.m` anchors whenever available.
- Treat `.md` extract-doc anchors as second-class documentation anchors and use them only when canonical `.m` anchors are not feasible.
