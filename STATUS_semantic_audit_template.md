# STATUS — Semantic Audit Template (2026-07-01)

## Verdict
- **COMPLETE**
- Core deliverables shipped: 4/4 required
- Optional deliverable shipped: yes (`scripts/build_semantic_audit_prompts.py`)

## What Was Built
- Added methodology template: `docs/prompts/SEMANTIC_AUDIT_TEMPLATE.md`
  - Includes Purpose, S1-S6 scope, verdict vocabulary, output shape, attribution rules, mechanical criteria.
  - Includes DT-required sections: contract, inventory, decision ledger, verification claims, open questions, risks.
- Added runnable per-process prompt template: `docs/prompts/PROMPT_semantic_audit_TEMPLATE.md`
  - Slot-1 and Slot-2 references included.
  - Placeholder set includes `{PROCESS_NAME}`, `{PROCESS_SLUG}`, `{MATLAB_FILE}`, `{MATLAB_SUPPORT_FILES}`, `{OC_FILES}`.
  - Enforces output path, table format, budget, and commit trailer.
- Added worked example audit: `docs/phase_f/audits/Metabolism_semantic_audit.md`
  - Claim table includes all S1-S6 categories.
  - Surfaces A1-A4 as `CODE_DEVIATES`.
  - Aggregate: VERIFIED=13, ROW_WRONG=0, CODE_DEVIATES=4, MISSING=0.
- Added optional generator script: `scripts/build_semantic_audit_prompts.py`
  - Reads all 28 process rows.
  - Substitutes template placeholders.
  - Emits concrete prompts to `E:\opencell-worktree-prompts\`.

## Verification
- `bin\oc-py scripts/build_semantic_audit_prompts.py --dry-run`
  - Result: 28 rows discovered, 28 prompts rendered.
- `bin\oc-py scripts/build_semantic_audit_prompts.py`
  - Result: 28 concrete prompt files emitted under `E:\opencell-worktree-prompts\`.
- Manual artifact checks:
  - Required docs exist at target paths.
  - Metabolism worked example table matches required column schema.
  - Prompt template includes required slot structure and commit trailer instruction.

## Open Questions For Operator
- Completeness policy for exemplar rows: keep exemplar-scoped (`judgment=required`) or force strict `MISSING` for omitted MATLAB surfaces?
- Should ordering stay inside S6 for now, or should a dedicated S7 ordering category be introduced after first fleet pass?
- Should we enforce a cap on discretionary claims (`judgment=required`) per process to keep fleet outputs comparable?

## Recommended Next Step
1. Run the generated 28 prompt files with codex agents to produce `docs/phase_f/audits/*_semantic_audit.md` fleet outputs.
2. Aggregate fleet verdict counts and produce a row-remediation queue for all `ROW_WRONG` and `MISSING` claims.
3. Re-run L1b after row remediation to establish structural + semantic alignment baseline.

