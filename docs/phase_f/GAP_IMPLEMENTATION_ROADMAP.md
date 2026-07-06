# Gap-Implementation Roadmap — closing the 11 L1b method-completeness gaps

**Status:** Track A (implement 11 missing Karr runtime behaviors) — **COMPLETE**
(S1-S5 done; gate `l1b_method_completeness.py` PASS 115/115, gap 0). Track B
(wiring-row conformance) — loop started (HB1-HB6).
**Ladder position:** L1b (oracle-free). No L2 work until all 28 processes are
L1a + L1b green. See `plan.md` L-ladder.
**Substrate:** `data/karr_method_inventory/oc_method_map.yaml` (gate:
`scripts/l1b_method_completeness.py`, PASS; all 11 `gap` entries now
`confirmed`/`inlined`).

## Track A completion (S1-S5, 2026-07-03)

| Subsystem | Commit(s) | Result |
|---|---|---|
| S1 DNASupercoiling→tx fold-change | `52d16ea` | output-only port; no regressions |
| S2 Replication SSB cycle | `f54a7b5` | fixture-backed, process-RNG; pre-existing-only failures |
| S3 MunI R-M (DNADamage+DNARepair) | `0ea4aad`+`cc4aa83` | coupled port; **introduced DNARepair L2-replay regression → L2.1** (`l2-regress-dnarepair-replay-s3`) |
| S4 DNARepair DisA scan | `1ad8a73` | built on S3 state; clean |
| S5 ProteinDecay proteolysis | `1822b33`+`71d07ca` | full port from light (Misfold/Refold/DegradeAborted) |

## Track B loop (HB1-HB6)

3-role loop: Opus 4.8 planner / gpt-5.3-codex doer / Sonnet 5 checker. Queue
`hb-1`..`hb-6` (see session todos). Exhaustive coverage (operator: sampling can't
prove output matches Karr). GPT-5.4-critiqued design D1-D7 (see plan.md handoff).
HB1 (extract Karr stoichiometry) partial: 6/28 extracted, 22 BLOCKER — needs
re-run against `.m`/WholeCellKB (matrix not in flat fixtures). A2/A4 assigned to
runtime gates L2.0a/L2.4 (static gate cannot prove scheduler order / runtime
projection); A1/A3/A3b + exhaustive-stoich are Half B static scope.

## Framing (operator-ratified 2026-07-03)

- Implementing the 11 gaps is **structural port work in service of L1b green** —
  NOT per-subsystem L2.1/L2.2 validation. The ladder is not skipped.
- L1b has two halves; both must go green for all 28 before any L2 work:
  - **Half A — method-completeness:** implement the 11 gaps (this roadmap).
  - **Half B — wiring-row conformance:** rebuild the enforcing gate + author
    truthful rows (the 1,623-defect fix). Comes AFTER Half A, because
    implementing biology changes code and would stale any rows truthed first.
- All execution is delegated to **codex (gpt-5.3-codex)**; the orchestrator
  plans, reviews, merges, pushes.

## The 11 gaps → 5 biological subsystems

| # | Subsystem | Gap methods (Karr) | Size | State | Coupling |
|---|---|---|---:|---|---|
| S1 | DNASupercoiling→Transcription feedback | `calcRNAPolymeraseBindingProbFoldChange` | 34 L | superhelical density → `tx_rate_fold_change` | consumer already wired |
| S2 | Replication SSB cycle | `dissociateFreeSSBComplexes`, `freeAndBindSSBs` | 80 L | chromosome ssDNA + SSB 8-mers | fork-local pair |
| S3 | MunI restriction-modification | DNADamage `calcNumberVulnerableSites`, `calcResourceRequirements_Current`; DNARepair `evolveState_Modification`, `evolveState_Restriction` | 117 L | chromosome methylation/restriction sites | DNADamage↔DNARepair coupled — implement jointly |
| S4 | DNARepair DisA scan | `evolveState_DisA` | 12 L | chromosome damage state | folds onto S3 |
| S5 | ProteinDecay proteolysis | `evolveState_MisfoldProteins`, `evolveState_RefoldProteins`, `evolveState_DegradeAbortedPolypeptides` | 215 L | protein misfolded/aborted state | Misfold/Refold homeostatic pair |

## Sequence (dependency-ordered; each = structural port → map entry flips → gate green)

1. **S1** — smallest, self-contained, consumer already wired. Pipe-cleaner for the
   implement→map-flip→gate loop.
2. **S2** — fork-local 2-method pair; introduces stochastic rebind.
3. **S3** — largest coupled subsystem (DNADamage + DNARepair); implement + flip
   its 4 entries jointly.
4. **S4** — DisA scan; tiny, coherent only after S3's chromosome damage-state.
5. **S5** — ProteinDecay proteolysis; Misfold+Refold pair, then DegradeAborted.

## Per-step contract (what "done" means at L1b)

For each subsystem, codex:
1. Ports the named Karr method(s) into the process's OC file(s), faithful to the
   `.m` source, following existing OC patterns, no naked biology numbers.
2. Confirms the code imports cleanly and the process's existing tests still pass
   (or documents expected changes).
3. Updates `data/karr_method_inventory/oc_method_map.yaml` entries from `gap` to
   `confirmed`/`inlined` with a resolving `file:symbol:line` anchor + evidence note.
4. Runs `bin\oc-py scripts/l1b_method_completeness.py` — must stay PASS with the
   subsystem's gaps now resolved.
5. Commits with STATUS.

Orchestrator then reviews the diff, runs the gate, and pushes.

## Not in scope here
- Bit-for-bit oracle validation (L2.1), distributional (L2.2), allocator (L2.0a),
  conservation (L2.4) — all later, all 28 at once, after L1b green.
- Half B (wiring-row enforcing gate + row truthing) — separate track after Track A.
