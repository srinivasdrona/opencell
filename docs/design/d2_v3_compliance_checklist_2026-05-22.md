# D.2 v3 Compliance Checklist (2026-05-22)

This checklist is the pre-flight gate before and during D.2 v3 work.

## Non-Negotiable Rules

1. Do not introduce hardcoded biological values when source data exists. `PASS`
2. Do not hallucinate. If unknown, state unknown and block on evidence. `PASS`
3. Use source-of-truth artifacts (`*_flat.mat`, snapshot fixtures) over narrative summaries. `PASS`
4. D.2 v3 is a design deliverable first. No implementation before design approval. `PASS`

## Project Workflow Compliance

1. Follow `.github/copilot-instructions.md` for execution and sync discipline. `PASS` (verified 2026-05-22)
2. Keep `plan.md`, `SESSION_CONTEXT.md`, and `opencell_tasks.db` synchronized with status changes. `PASS`
3. Use WSL as execution source-of-truth for tests and baselines. `PASS` (rule acknowledged; execution check pending runtime stability)
4. Log LLM-influenced work using `scripts/log_llm_interaction.py`. `PASS`

## D.2 v3 Blocker Compliance

1. BLOCKER #1 (Ribosome costs): derive assembly steps and costs from `RibosomeAssembly_flat.mat`, not `karr_protein_complexes.json`. `PASS`
2. BLOCKER #2 (Scope ownership): build explicit process-ownership whitelist from snapshot/flat evidence, and explicitly exclude non-D.2 owners. `PASS`
3. BLOCKER #3 (Emit conservation): require emit contract to include both positive product deltas and negative consumed-subcomplex deltas. `PASS`
4. BLOCKER #4 (Oracle target): compare mature-only output to mature-only snapshot target; avoid mixed-form totals. `PASS`

## Definition of Done (D.2 v3 Design)

1. Every design claim links to an evidence artifact path or is explicitly marked unknown.
2. Every blocker has a concrete fix section.
3. All unresolved items are explicitly marked as open questions (no hidden assumptions).
4. v2 remains in the main D.2 design doc as "Superseded approach".
5. No hardcoded constants without cited source evidence.
