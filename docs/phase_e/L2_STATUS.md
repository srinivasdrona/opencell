# L2 status — 28 processes × 3 rungs

Single source of truth for the L2-green campaign. Update on every sweep,
re-extraction, or schema-audit run. Do not edit from memory — always cross-check
against the source files listed under Provenance below.

Last updated: **2026-05-30 (09:45 IST)** (L2.0 **SWEEP COMPLETE — 28/28 GREEN** via Bucket A codex agent (`6137c79` + `e38170a` on main, fast-forwarded to sweep `542e287`); verify agent confirmed **L2.1 baseline 9-GREEN preserved**, zero regressions. Bucket GREEN **9**, Pattern D RED **19**. L2.1 remains the next campaign.)

## Rung definitions

| Rung | What it tests | Failure mode |
|---|---|---|
| L2.0 | Observable schema: does OC declare the same wid / port surface as Karr? | Static, isolated context. AMBER if partial overlap, RED if no overlap. |
| L2.1 | Per-process bit-identity replay: overlay Karr `states_before` into OC state, run `next_update`, compare to Karr `states_after`. | Dynamic, single-tick, deterministic. GREEN means byte-equal. |
| L2.2 | Stochastic distributional fidelity across many runs (σ-bands pre-registered). | Not yet started. |

## Headline (2026-05-30)

| | GREEN | AMBER | RED | ERROR | not-run |
|---|---|---|---|---|---|
| L2.0 | **28** | 0 | 0 | 0 | 0 |
| L2.1 | **9** | — | **19** | 0 | 0 |
| L2.2 | — | — | — | — | **28** |

## Per-process matrix

| # | Process | L2.0 | L2.1 | L2.1 pattern | First mismatch |
|---|---|---|---|---|---|
| 1 | ChromosomeCondensation     | AMBER | RED   | D | t=0 substrates idx=0 72→75 |
| 2 | ChromosomeSegregation      | AMBER | GREEN | — | (no-op trace, OC also no-op) |
| 3 | Cytokinesis                | AMBER | GREEN | — | bit-identical after Pattern A refactor |
| 4 | DNADamage                  | RED   | GREEN | — | Karr oracle noise (`karr=2.8e-11`) snapped to 0; harness now tolerates ≤1e-9 oracle residue (commit `ea5a2bf`) |
| 5 | DNARepair                  | AMBER | **GREEN** | — | RM MunI methylation side-reaction added (`AMET -> AHCYS + H`); +14 lines in `karr_dna_repair.py`; sweep commit `7c17ec9` (cherry-picked from worktree `9fe6ba2`) |
| 6 | DNASupercoiling            | AMBER | RED   | D | t=0 boundEnzymes[0] oc=0 karr=3 diff=-3 (post `58e851d`: gyrase free-pool decrement emitted on bind; residue surface shifted from enzymes[0]+3 to boundEnzymes[0]-3, productive wip) |
| 7 | FtsZPolymerization         | AMBER | RED   | D | t=0 substrates idx=1 34→32 |
| 8 | HostInteraction            | RED   | GREEN | — | (no-op trace, OC also no-op) |
| 9 | MacromolecularComplexation | AMBER | GREEN | — | 100/100 bit-identical (the real GREEN) |
| 10 | Metabolism                | AMBER | RED   | D | t=0 substrates[10]=ADP oc=3622 karr=0 — WID order verified via fixture/substrateIndexs_adp=11; real biology gap (OC `next_update` doesn't consume ADP) |
| 11 | ProteinActivation         | AMBER | RED   | D | length fixed; t=28 substrates idx=2 diff=1 (late drift) |
| 12 | ProteinDecay              | AMBER | RED   | D | t=3 substrates[0] oc=0 karr=6 — real biology; complexs/monomers naive np.arange projection (canonical deferred — complexs mutates only 2/100 ticks vs substrates 41/100, biology dominates) |
| 13 | ProteinFolding            | AMBER | **GREEN** | — | Closed at sweep `a2b3285` (worktree `725ff1e`): replay overlay zeroed chaperone enzymes and OC hard-gated chaperone folding on ATP; aligned to MATLAB catalytic-enzyme gate semantics (`ProteinFolding.m:533-537,570`) |
| 14 | ProteinModification       | AMBER | RED   | D | length fixed via `_active_protein_indices`; t=43 real biology drift |
| 15 | ProteinProcessingI        | AMBER | **GREEN** | — | H2O residue closed via enzyme-counts fallback to `protein.counts` (commit `b6b6cbe` on `audit/l2-1-sweep-v2`; methionine aminopeptidase was treated as absent in replay state; +6/-1 in `karr_protein_processing_i.py`) |
| 16 | ProteinProcessingII       | AMBER | RED   | D | t=3 substrates[0]=H2O oc=140259 karr=140258 diff=+1 after productive WIP `3524332` (from `82c64d5`): closed tick-2 processedMonomers[429]=MG_417_MONOMER via MATLAB pass-through semantics (`ProteinProcessingII.m:350-353,356-357`) |
| 17 | ProteinTranslocation      | AMBER | GREEN | — | SRP-vs-direct pathway corrected to MATLAB `signalSequenceType ∈ {lipoprotein, secretory}` + first-infeasible halt (commit `699f1c4` on `audit/l2-1-sweep-v2`; 100/100 ticks bit-identical) |
| 18 | Replication               | AMBER | RED   | D | t=0 substrates idx=4 649→695 |
| 19 | ReplicationInitiation     | AMBER | RED   | D | t=0 boundEnzymes[1] oc=23 karr=25 diff=-2 (post `e3cfb21`: DnaA ATP/ADP delta emission + `enzymes` removed from pass-through; productive wip — boundEnzymes now the residue surface) |
| 20 | RibosomeAssembly          | AMBER | RED   | D | t=96 substrates idx=0 153→155 |
| 21 | RNADecay                  | AMBER | RED   | D | t=0 substrates idx=1 20→0 |
| 22 | RNAModification           | AMBER | RED   | D | t=6 substrates[2]=AMP +1 (post `9acdb32` revert; Path X cofactor patch tried then reverted — made worse to +7; baseline AMP residue remains the working signal) |
| 23 | RNAProcessing             | AMBER | RED   | D | t=4 processedRNAs idx=140 0→1 |
| 24 | TerminalOrganelleAssembly | RED   | RED   | D | t=6 substrates idx=4 27→26 |
| 25 | Transcription             | AMBER | RED   | D | Pattern A residue closed via `np.arange(4)` substrate projection (commit `d8fa1a5` on `audit/l2-1-sweep-v2`; ATP/CTP/GTP/UTP honest prefix); new fingerprint t=0 substrates[0] oc=13879 karr=13906 diff=-27 (stochastic post-B, needs ensemble check) |
| 26 | TranscriptionalRegulation | RED   | RED   | D | t=15 enzymes idx=3 oc=1 karr=0 |
| 27 | Translation               | AMBER | RED   | D | t=0 enzymes[3] oc=65 karr=77 diff=-12 (post `8baa161`: IF3↔30S/30S_IF3 initiation mutation added in `karr_translation_v3.py`; first-fail shifted off enzymes[2] +13 → enzymes[3] -12, productive) |
| 28 | tRNAAminoacylation        | AMBER | RED   | D | t=0 substrates idx=2 668→631 |

## L2.1 RED pattern taxonomy

| Pattern | Count | Hypothesis | Suggested fix surface |
|---|---|---|---|
| A: wid-length drift | 0 (was 2) | **Closed (again)**: Transcription + Translation residue closed via Path A honest-prefix projection (commits `d8fa1a5`, `d779951`). Both now Pattern D with seed-sensitive fingerprints — D close-out should be ensemble-checked, not single-trace bit-identity. | — (closed) |
| B: non-integral counts | 0 (was 3) | **Closed**: DNADamage was Karr oracle float noise (~2.8e-11), fixed in harness via integer-snap when `|frac| < 1e-9` (commit `ea5a2bf`, principle logged as DECISION `l2-harness-integrality-asymmetry`). Transcription + Translation were real OC bugs — integerized via unbiased `floor + Bernoulli(frac)` with seeded RNG (commits `fe0b9d5`, `9d54886`); revealed A residue underneath. | — (closed) |
| C: enzyme vector mismatch (t=0) | 0 (was 4) | Resolved: per-test `_PASS_THROUGH` set was declared but not honored in the projection loop. Fix landed in commit `43d5620`. All 4 migrated to Pattern D with informative t>0 fingerprints. ReplicationInitiation's `_PASS_THROUGH` for enzymes is incorrect (enzymes ARE mutated by binding) and stays Pattern D. | — (closed) |
| D: real biology drift | 19 (was 21) | ProteinFolding closed to GREEN at `a2b3285` (chaperone-overlay + ATP-gating mismatch fix). ProteinProcessingII shifted to later/finer residue (`t=3 substrates[0]=H2O +1`) after WIP `3524332`; DNASupercoiling shifted residue surface to `boundEnzymes[0]-3` after WIP `58e851d`. | Per-process fanout triage remains dominant. |

## Priority for next moves

1. **Wave 8 landed one GREEN + one productive shift** — ProteinFolding is now L2.1 GREEN (`a2b3285`/`725ff1e`); ProteinProcessingII WIP `3524332` closed the tick-2 monomer residue and exposed later `t=3 substrates[0]=H2O +1` as current first-fail.
2. **RNAModification was re-fired with corrected trace input and remains in progress** — latest captured worktree status still indicates active investigation (no closing commit yet).
3. **Wave 9 fanout is active** — FtsZPolymerization, RNADecay, and ChromosomeCondensation worktrees are in flight.
4. **Global harness hypotheses H2/H3 are empirically refuted** — no additional harness-side global probes are planned for now.
5. **H1 (`_PASS_THROUGH` centralization) is deferred indefinitely** — current evidence after H2/H3 refutation weakens a global-frame explanation; standing direction remains to continue per-process fanout until all L2.0 + L2.1 are GREEN.

## Cross-rung observations

- **L2.0 GREEN = 0 across all 28**: nobody currently has full schema overlap with Karr. The 24 AMBERs share `substrates` only; OC routes enzyme state via different port names (`protein` / `complex` / `chromosome` / `tf_binding`).
- **HostInteraction L2.0=RED but L2.1=GREEN**: OC doesn't claim to emit substrates (schema RED), but when forced to run via overlay it no-ops, matching Karr's quiet trace. L2.1 GREEN ≠ L2.0 GREEN.
- **2 processes are L2.0 RED + L2.1 RED**: TerminalOrganelleAssembly, TranscriptionalRegulation (DNADamage is L2.0 RED + L2.1 GREEN; HostInteraction is L2.0 RED + L2.1 GREEN). These need schema work before further L2.1 progress is meaningful.

## Provenance

- L2.0: `docs/phase_e/L2_0_SCHEMA_AUDIT.md` + `docs/phase_e/L2_0_SCHEMA_AUDIT.json` (generated by `scripts/probe_l2_0_schema_audit.py`). On `main`, currently uncommitted.
- L2.1 active 19: `STATUS_l2_1_sweep.md` on branch `audit/l2-1-sweep-v2` (worktree `E:\opencell-worktrees\l2-1-sweep-v2`). 19 tests in `tests/vivarium/test_karr_*_l2_replay.py`. Sweep progression verified from `8951a11` through `a2b3285` (`58e851d`, `cad12e3`, `3524332`, `a2b3285` as the latest wave 6/7/8 deltas).
- Wave reports: `E:\opencell-worktrees\harness-h2-allocator\H2_REPORT.md` (H2 A/B refutation), `E:\opencell-worktrees\harness-h3-storefanout\H3_REPORT.md` (H3 refutation + no-regression gate), and `E:\opencell-worktrees\wave8-rnamod\STATUS.attempt1.md` (latest captured RNAMod status before re-fire remains in-progress).
- L2.1 traces: `data/m1_sources/karr_native/per_process_traces_v2/*.mat` (28 files, gitignored). Generated by `scripts/matlab/extract_per_process_traces_v2.m` on branch `audit/l2-matlab-reextract-v2`.

## How to update this doc

When re-running a sweep or audit:

1. Run the sweep / audit and capture the STATUS file in the worktree.
2. Update the headline row, the per-process matrix, and the pattern taxonomy.
3. Append a new "Last updated" date with a one-line note on what changed.
4. Commit on `main` with message `docs(l2): refresh L2_STATUS after <sweep name>`.

When the manual update step starts hurting (likely after 2-3 more sweeps),
write a regen script: `scripts/regen_l2_status.py` reads from
`docs/phase_e/L2_0_SCHEMA_AUDIT.json` and each worktree's
`STATUS_l2_1_sweep.md`, rebuilds this doc.
