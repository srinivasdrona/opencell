# Audit Report Consolidation

## Role

You are the **audit consolidator**. Four audits + a critique produced 12+ artifacts across 4 branches. This investigation phase needs ONE consolidated report on `main` so future work has a single landing pad.

You are not adding new findings. You aggregate, dedupe, cross-reference, and produce a single readable consolidated report.

## Worktree & branch

- Worktree: `E:\opencell-worktrees\swarm-audit-consolidation` (already created)
- Branch: `swarm/audit-consolidation`
- WSL: `wsl -e bash -lc "cd /mnt/e/opencell-worktrees/swarm-audit-consolidation && source /mnt/e/opencell/.venv-wsl/bin/activate && <cmd>"`

## Budget

~60k context.

## Inputs (read all)

1. **Reducer original output** (`swarm/reducer` branch):
   - `E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\swarm_report.md`
   - `E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\bugs_to_fix.md`
   - `E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\expected_active_set.json`
   - `E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\fix-fleet-queue.md`
   - `E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\spot_check_log.jsonl`
   - `E:\opencell-worktrees\swarm-reducer\opencell\validation\swarm\gpt55_critique.md` (the structural critique that triggered the second audit pass)

2. **Composition audit** (`swarm/composition` branch):
   - `E:\opencell-worktrees\swarm-composition\opencell\validation\swarm\composition\composition_audit.md`
   - `composition_table.csv`, `composition_l0.json`, `composition_l1.json`, `composition_l2.json`, `composition_l7.json`

3. **Allocator-completeness audit** (`swarm/allocator-completeness` branch):
   - `E:\opencell-worktrees\swarm-allocator\opencell\validation\swarm\allocator\allocator_audit.md`
   - `allocator_matrix.csv`, `cross_layer_observations.md`

4. **L5 helper-semantics investigation** (`swarm/l5-semantics` branch):
   - `E:\opencell-worktrees\swarm-l5-semantics\opencell\validation\swarm\l5\zero_grant_contract_recommendation.md`
   - `karr_zero_grant_behavior.md`, `l5_call_sites.csv`

## Output

Produce ONE consolidated report under `opencell/validation/swarm/consolidated/`:

### 1. `CONSOLIDATED_AUDIT_REPORT.md` (~6-10 KB)

Structure:

- **Executive summary** (~300 words): scope of the audit phase (1 reducer + 3 secondary audits + 1 critique), what changed vs reducer's original 19 blocks_b1 catalog, what made it through, what was refuted, and the headline Track-A scope.

- **Audit chronology**: short timeline of the 5 audit passes with dates and branches.

- **Findings catalog (revised)**: for each of the reducer's original 19 blocks_b1 findings, state its **post-secondary-audit status**:
  - `confirmed` (corroborated by L0/L1/L2/L3/L4/L5/L6/L7 audits) — Track-A scope
  - `recategorized` (real but moved to a different layer)
  - `refuted` (positive code evidence shows no bug) — drop
  - `gated` (needs precondition like fixture rebuild or v3 re-audit)
  
  Use a table or tagged list. Cite the secondary-audit source for each verdict.

- **New findings surfaced**: items NOT in the reducer's blocks_b1 list but raised by the secondary audits. Notable: ProteinTranslocation L3 (allocator agent), 28/28 single-snapshot fixtures (composition L7), 9 helper sites beyond the critique's 6 (L5).

- **Critique's structural verdict — closure**: for each of the GPT-5.5 critique's 4 numbered concerns (allocator-bypass partitioning, t0-cluster instability, audit redundancy, missing composition layer), state how the secondary audits addressed it. Cite specifically.

- **Track-A scope (locked)**: the 5 PRs (A1-A5) with layer, scope, LOC, dependencies. Stop here — do not author the fix PRs, just hand them a clean specification.

- **Deferred work**: items requiring decisions or other audits before they unblock (fixture pipeline rebuild, central-dogma re-audit, etc.)

- **Open questions**: anything still unresolved.

### 2. `findings_index.csv` (~5 KB)

Flat table for grep-ability. One row per finding (whether from reducer or secondary):
```
finding_id, source_audit, process_name, layer, original_severity, post_audit_status, track_a_pr, citation_file, citation_line, notes
```

## Methodology

- Cite ALL sources with `file:line`. The provenance trail is the point of the consolidated report.
- Do NOT contradict any individual audit without explicit citation — defer to the most-specific audit on each topic (composition for L0/L1/L2/L7, allocator for L3/L4/L6, L5 for helper semantics).
- No new analysis — purely cross-reference and rollup.
- Length discipline: 6-10 KB. If you blow past 12 KB, you're rewriting individual audits — STOP and trim.

## Commit discipline

One commit. Trailer:
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`

After commit, **the operator will merge `swarm/audit-consolidation` to main** as the canonical audit phase wrap-up. You do not push, you do not merge.

## What success looks like

A reader who opens `CONSOLIDATED_AUDIT_REPORT.md` cold should understand the entire 5-audit phase without reading any of the 12 source artifacts — the report cites them but reads coherently on its own. The Track-A PR authors should be able to take the locked scope section and start work immediately.
