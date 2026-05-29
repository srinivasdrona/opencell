# L2 status — 28 processes × 3 rungs

Single source of truth for the L2-green campaign. Update on every sweep,
re-extraction, or schema-audit run. Do not edit from memory — always cross-check
against the source files listed under Provenance below.

Last updated: **2026-05-29** (after Pattern A harness scale-out — `project_karr_vector` extended with literal-index projection, all 7 Pattern A tests refactored; 1 promoted to GREEN, 4 advanced to Pattern D, 2 blocked on deeper layout work)

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
| L2.1 | 4 | — | 24 | 0 | 0 |
| L2.2 | — | — | — | — | **28** |

## Per-process matrix

| # | Process | L2.0 | L2.1 | L2.1 pattern | First mismatch |
|---|---|---|---|---|---|
| 1 | ChromosomeCondensation     | AMBER | RED   | D | t=0 substrates idx=0 72→75 |
| 2 | ChromosomeSegregation      | AMBER | GREEN | — | (no-op trace, OC also no-op) |
| 3 | Cytokinesis                | AMBER | GREEN | — | bit-identical after Pattern A refactor |
| 4 | DNADamage                  | RED   | RED   | B | t=0 substrates idx=39 karr=2.8e-11 (non-integral) |
| 5 | DNARepair                  | AMBER | RED   | D | t=8 substrates idx=2 1→0 |
| 6 | DNASupercoiling            | AMBER | RED   | D | t=0 substrates idx=0 847→905 |
| 7 | FtsZPolymerization         | AMBER | RED   | D | t=0 substrates idx=1 34→32 |
| 8 | HostInteraction            | RED   | GREEN | — | (no-op trace, OC also no-op) |
| 9 | MacromolecularComplexation | AMBER | GREEN | — | 100/100 bit-identical (the real GREEN) |
| 10 | Metabolism                | AMBER | RED   | A* | length fixed (np.arange(585)); t=0 substrates idx=10 oc=3622 karr=0 — WID-order mismatch suspected |
| 11 | ProteinActivation         | AMBER | RED   | D | length fixed; t=28 substrates idx=2 diff=1 (late drift) |
| 12 | ProteinDecay              | AMBER | RED   | A | monomers length fixed (np.arange(482)); NEW length drift on complexs 7236→147, needs fixture-driven extraction |
| 13 | ProteinFolding            | AMBER | RED   | C | t=0 enzymes idx=2 46→0 |
| 14 | ProteinModification       | AMBER | RED   | D | length fixed via `_active_protein_indices`; t=43 real biology drift |
| 15 | ProteinProcessingI        | AMBER | RED   | C | t=0 enzymes idx=1 38→0 |
| 16 | ProteinProcessingII       | AMBER | RED   | C | t=0 enzymes idx=0 58→0 |
| 17 | ProteinTranslocation      | AMBER | RED   | D | length fixed (np.arange(482)); t=2 substrates idx=1 diff=2 |
| 18 | Replication               | AMBER | RED   | D | t=0 substrates idx=4 649→695 |
| 19 | ReplicationInitiation     | AMBER | RED   | C | t=0 enzymes idx=1 0→2 |
| 20 | RibosomeAssembly          | AMBER | RED   | D | t=96 substrates idx=0 153→155 |
| 21 | RNADecay                  | AMBER | RED   | D | t=0 substrates idx=1 20→0 |
| 22 | RNAModification           | AMBER | RED   | D | length fixed via `_active_rna_indices`; t=0 modifiedRNAs[0] oc=0 karr=35 (init seeding) |
| 23 | RNAProcessing             | AMBER | RED   | D | t=4 processedRNAs idx=140 0→1 |
| 24 | TerminalOrganelleAssembly | RED   | RED   | D | t=6 substrates idx=4 27→26 |
| 25 | Transcription             | AMBER | RED   | B | t=0 ATP delta -53.97 (non-integral) |
| 26 | TranscriptionalRegulation | RED   | RED   | D | t=15 enzymes idx=3 oc=1 karr=0 |
| 27 | Translation               | AMBER | RED   | B | t=0 ALA delta -56.53 (non-integral) |
| 28 | tRNAAminoacylation        | AMBER | RED   | D | t=0 substrates idx=2 668→631 |

## L2.1 RED pattern taxonomy

| Pattern | Count | Hypothesis | Suggested fix surface |
|---|---|---|---|
| A: wid-length drift | 2 (was 7) | Remaining after harness scale-out: Metabolism (WID-order mismatch suspected, not pure layout) + ProteinDecay (complexs needs fixture-driven extraction). | Trace-metadata inspection + fixture-driven projection. |
| B: non-integral counts | 3 | Real OC bug — `next_update` emits float deltas, violating count integrality (Rule 2). | Process-specific math (Transcription, Translation, DNADamage). |
| C: enzyme vector mismatch (t=0) | 4 | OC's enzyme reconstruction from `boundEnzymes_before` differs from Karr's. | Likely one shared `project_observable_from_state` / `overlay` fix. |
| D: real biology drift | 15 (was 11) | Per-process semantics drift between OC and Karr. +4 promoted from A: RNAMod, PTransloc, PActivation, ProteinMod. | Per-process triage, slowest. |

## Priority for next moves

1. **Pattern A residue** — 2 processes left. Metabolism: inspect trace metadata for WID order, build WID-mapped index. ProteinDecay: extract complexs column-index from fixture (`complex_col_by_wid` line 83 of `karr_protein_decay_light.py`).
2. **Pattern C enzyme reconstruction** — 4 processes (ProteinFolding, ProteinProcessingI/II, ReplicationInitiation), likely one shared fix in projection/overlay logic. Highest upside-per-effort after Pattern A residue.
3. **Pattern D quick wins** — RNAModification's t=0 oc=0/karr=35 modifiedRNAs[0] is the cleanest init-seeding lead. ProteinTranslocation (t=2) and ProteinActivation (t=28) are 1-bit-near-GREEN.
4. **Pattern B Rule-2 violations** — real OC bug, 3 processes, scoped per-process.
5. **L2.2 methodology design** — still nothing (σ-band pre-registration, ensemble harness).
6. **Pattern D long tail** — 11 original Pattern D processes, slowest path.

## Cross-rung observations

- **L2.0 GREEN = 0 across all 28**: nobody currently has full schema overlap with Karr. The 24 AMBERs share `substrates` only; OC routes enzyme state via different port names (`protein` / `complex` / `chromosome` / `tf_binding`).
- **HostInteraction L2.0=RED but L2.1=GREEN**: OC doesn't claim to emit substrates (schema RED), but when forced to run via overlay it no-ops, matching Karr's quiet trace. L2.1 GREEN ≠ L2.0 GREEN.
- **3 processes are L2.0 RED + L2.1 RED**: DNADamage, TerminalOrganelleAssembly, TranscriptionalRegulation. These need schema work before L2.1 progress is meaningful.

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
