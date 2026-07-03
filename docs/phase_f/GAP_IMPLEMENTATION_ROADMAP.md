# Gap-Implementation Roadmap — closing the 11 L1b method-completeness gaps

**Status:** Track A (implement 11 missing Karr runtime behaviors) — in progress.
**Ladder position:** L1b (oracle-free). No L2 work until all 28 processes are
L1a + L1b green. See `plan.md` L-ladder.
**Substrate:** `data/karr_method_inventory/oc_method_map.yaml` (gate:
`scripts/l1b_method_completeness.py`, currently PASS with 11 `gap` entries that
must become `confirmed`/`inlined`).

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
