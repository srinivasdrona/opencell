# L2 status — 28 processes × 3 rungs

Single source of truth for the L2-green campaign. Update on every sweep,
re-extraction, or schema-audit run. Do not edit from memory — always cross-check
against the source files listed under Provenance below.

Last updated: **2026-05-29 (~23:55 IST)** (after wave 5/6 — **DNARepair L2.1 GREEN** via RM MunI methylation side-reaction (sweep `7c17ec9`, worktree `9fe6ba2`); +14 lines. Bucket GREEN 7→**8**, D 21→20. Plus 4 productive WIP shifts on sweep at `7c17ec9`: Translation `enzymes[3]-12`, ReplicationInitiation `boundEnzymes[1]-2`, DNASupercoiling `enzymes[0]+3`, RNAProcessing `unprocessedRNAs[73]+1`. DNASupercoiling deep-close + harness pattern hunt still running.)

## Rung definitions

| Rung | What it tests | Failure mode |
|---|---|---|
| L2.0 | Observable schema: does OC declare the same wid / port surface as Karr? | Static, isolated context. AMBER if partial overlap, RED if no overlap. |
| L2.1 | Per-process bit-identity replay: overlay Karr `states_before` into OC state, run `next_update`, compare to Karr `states_after`. | Dynamic, single-tick, deterministic. GREEN means byte-equal. |
| L2.2 | Stochastic distributional fidelity across many runs (σ-bands pre-registered). | Not yet started. |

## Headline (2026-05-29)

| | GREEN | AMBER | RED | ERROR | not-run |
|---|---|---|---|---|---|
| L2.0 | 0 | 24 | 4 | 0 | 0 |
| L2.1 | **8** | — | **20** | 0 | 0 |
| L2.2 | — | — | — | — | **28** |

## Per-process matrix

| # | Process | L2.0 | L2.1 | L2.1 pattern | First mismatch |
|---|---|---|---|---|---|
| 1 | ChromosomeCondensation     | AMBER | RED   | D | t=0 substrates idx=0 72→75 |
| 2 | ChromosomeSegregation      | AMBER | GREEN | — | (no-op trace, OC also no-op) |
| 3 | Cytokinesis                | AMBER | GREEN | — | bit-identical after Pattern A refactor |
| 4 | DNADamage                  | RED   | GREEN | — | Karr oracle noise (`karr=2.8e-11`) snapped to 0; harness now tolerates ≤1e-9 oracle residue (commit `ea5a2bf`) |
| 5 | DNARepair                  | AMBER | **GREEN** | — | RM MunI methylation side-reaction added (`AMET -> AHCYS + H`); +14 lines in `karr_dna_repair.py`; sweep commit `7c17ec9` (cherry-picked from worktree `9fe6ba2`) |
| 6 | DNASupercoiling            | AMBER | RED   | D | t=0 enzymes[0] oc=3 karr=0 diff=+3 (post `946509a`: ATP-H emit + bound-pool sampling reduced substrates[0] +58 → enzymes[0] +3; productive wip) |
| 7 | FtsZPolymerization         | AMBER | RED   | D | t=0 substrates idx=1 34→32 |
| 8 | HostInteraction            | RED   | GREEN | — | (no-op trace, OC also no-op) |
| 9 | MacromolecularComplexation | AMBER | GREEN | — | 100/100 bit-identical (the real GREEN) |
| 10 | Metabolism                | AMBER | RED   | D | t=0 substrates[10]=ADP oc=3622 karr=0 — WID order verified via fixture/substrateIndexs_adp=11; real biology gap (OC `next_update` doesn't consume ADP) |
| 11 | ProteinActivation         | AMBER | RED   | D | length fixed; t=28 substrates idx=2 diff=1 (late drift) |
| 12 | ProteinDecay              | AMBER | RED   | D | t=3 substrates[0] oc=0 karr=6 — real biology; complexs/monomers naive np.arange projection (canonical deferred — complexs mutates only 2/100 ticks vs substrates 41/100, biology dominates) |
| 13 | ProteinFolding            | AMBER | RED   | D | t=2 foldedMonomers idx=429 oc=0 karr=1 (was C, _PASS_THROUGH fixed) |
| 14 | ProteinModification       | AMBER | RED   | D | length fixed via `_active_protein_indices`; t=43 real biology drift |
| 15 | ProteinProcessingI        | AMBER | **GREEN** | — | H2O residue closed via enzyme-counts fallback to `protein.counts` (commit `b6b6cbe` on `audit/l2-1-sweep-v2`; methionine aminopeptidase was treated as absent in replay state; +6/-1 in `karr_protein_processing_i.py`) |
| 16 | ProteinProcessingII       | AMBER | RED   | D | t=2 unprocessedMonomers idx=429 diff=1 (was C, _PASS_THROUGH fixed) |
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
| D: real biology drift | 21 (was 22) | -ProteinProcessingI (now GREEN via enzyme-counts fallback). RNAMod stochastic-round revert kept AMP baseline. Translation clamp closed -57 negative-count bug, residue shifted to enzymes[2]+13. | Per-process triage, slowest. |

## Priority for next moves

1. **Pattern D quick wins (remaining)** — per Pattern D triage (commit `2f1f531` on `audit/pattern-d-triage`): #1 ProteinTranslocation **DONE** (commit `699f1c4`). Next: #2 RNAModification (t=0 modifiedRNAs[0] diff=-35, transition-cap suspected, 10-30 lines), #3 ProteinProcessingI (t=1 substrates diff=+3, cleavage/deformyl rounding), #4 ProteinActivation (large refactor, deferred).
2. **L2.0 RED schema work** — 4 processes (DNADamage now GREEN'd by oracle clamp, leaving TerminalOrganelleAssembly, TranscriptionalRegulation, HostInteraction). Per L2.0 RED triage (commit `5ba13ba`): **not blocking L2.1 closure**; schema work emerges organically as D quick-wins land. Recommended order if pursued: TranscriptionalRegulation > TerminalOrganelleAssembly.
4. **Defensive global pass** — propagate the `_PASS_THROUGH` honoring branch to the other ~22 tests (safe; no GREEN deltas expected, but defensive correctness).
5. **L2.2 methodology design** — still nothing (σ-band pre-registration, ensemble harness).
6. **Pattern D long tail** — 21 processes, slowest path.
7. **Deferred: ProteinDecay canonical complexs/monomers projection** — only needed if/when substrate biology gap is closed and complexs/monomers become the new first-fail (unlikely given mutation-frequency ratio).

## Cross-rung observations

- **L2.0 GREEN = 0 across all 28**: nobody currently has full schema overlap with Karr. The 24 AMBERs share `substrates` only; OC routes enzyme state via different port names (`protein` / `complex` / `chromosome` / `tf_binding`).
- **HostInteraction L2.0=RED but L2.1=GREEN**: OC doesn't claim to emit substrates (schema RED), but when forced to run via overlay it no-ops, matching Karr's quiet trace. L2.1 GREEN ≠ L2.0 GREEN.
- **3 processes are L2.0 RED + L2.1 RED**: TerminalOrganelleAssembly, TranscriptionalRegulation (was 3; DNADamage flipped to L2.0 RED + L2.1 GREEN after harness oracle-snap fix). These need schema work before further L2.1 progress is meaningful.

## Provenance

- L2.0: `docs/phase_e/L2_0_SCHEMA_AUDIT.md` + `docs/phase_e/L2_0_SCHEMA_AUDIT.json` (generated by `scripts/probe_l2_0_schema_audit.py`). On `main`, currently uncommitted.
- L2.1 active 19: `STATUS_l2_1_sweep.md` on branch `audit/l2-1-sweep-v2` (worktree `E:\opencell-worktrees\l2-1-sweep-v2`). 19 tests in `tests/vivarium/test_karr_*_l2_replay.py`. Commits `9435c15` through `2a48d69`.
- L2.1 extension 9: same branch + worktree. Commits `a4b8422`, `3ef618f`, `a69f03a`, `5033140` (quiet-process upgrade).
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
