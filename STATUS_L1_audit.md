# STATUS_L1_audit.md

## Final counts (corrected 2026-05-27 20:50 IST after probe + tracker reconciliation)
- L1-IMPLEMENTED-FIRING: 11 / 28 Karr-with-impl
- L1-IMPLEMENTED-GATED: 16 / 28 Karr-with-impl  (was 15; `karr_protein_activation` reclassified STUB → GATED after `probe_pact.py` confirmed 6/6 activation rules fire under per-signal perturbation)
- L1-STUB: 0 / 28 Karr-with-impl  (was 2; both reclassified — see below)
- L1-SHIM (exempt from Karr-parity): 1 (`karr_cell_cycle_coordinator`, no Karr `.m` counterpart)
- L1-MISSING (Karr process not in v6 chassis): 1 (`karr_transcriptional_regulation`)
- L1-green total (Karr-with-impl, FIRING+GATED): 27 / 28 Karr
- v6 chassis key bookkeeping: 28 keys = 27 Karr-with-impl L1-green + 1 SHIM (Karr-parity N/A)
- Total-Karr-process bookkeeping: 28 Karr processes per source = 27 in v6 + 1 MISSING (TR)
- This tracker row count: 29 rows = 28 v6 keys + 1 MISSING-from-v6 Karr process

## Reclassifications (2026-05-27 20:50 IST)
1. `karr_cell_cycle_coordinator`: STUB → SHIM. Has a real `Step` with ~150 lines of coordination logic in `opencell/vivarium/karr_cell_cycle_coordinator.py`, but no Karr `.m` counterpart exists. Exempt from Karr-parity ladder by source-parity contract. Track as OpenCell-original integration shim.
2. `karr_protein_activation`: STUB → GATED. The codex audit was over-strict. Module is 210 lines, loads boolean activation rules from `ProteinActivation_flat.mat`, evaluates via AST-safe sandbox per tick. `probe_pact.py` (2026-05-27 diagnostic) confirmed all 6 regulated proteins (MG_085_HEXAMER under G6P>5, MG_409_DIMER under PI>20, MG_127/205/236 stress sensors, MG_101 inverse-gluconate) flip correctly under per-signal perturbation. Code is L1-green; dead trace in wave2-base is explained by upstream input signals (G6P, PI, stress stimuli, temperature) never moving — classic GATED, not STUB.

## Missing-from-v6 discovery (2026-05-27 20:50 IST)
`karr_transcriptional_regulation` is **not in v6 chassis** — Karr extract #10, MATLAB source (`TranscriptionalRegulation.m`), and `.mat` fixture all present, but no Python implementation in `opencell/vivarium/`, and not in `CHASSIS_V6_EXPECTED_PROCESS_KEYS` (`opencell/vivarium/karr_composite.py:123-152`). Extract header declares OpenCell status as NOT-STARTED. Probable contributor to broken regulatory landscape (transcription FIRING but no regulatory feedback in v6). This is the highest-priority L0→L1 item: implementation queued as a dedicated codex session against the Karr extract + `.m` source + flat.mat fixture.

## Top-3 surprising findings
1. `karr_rna_modification` is FIRING at 32,400t (all 4 seeds non-header traces) even though the earlier 200t probe looked nearly dead.
2. `karr_dna_damage` is fully DEAD at 32,400t (header-only traces in all seeds), not just sparse/partial as earlier short-horizon assumptions suggested.
3. **`karr_transcriptional_regulation` is missing entirely from v6** — not a STUB, not a GATED process, just absent. Caught only because operator double-checked the 28-vs-29 count.

## Top-5 fanout (ranked by downstream unblock, post-reclass)
1. **`karr_transcriptional_regulation` (MISSING — implement)**: highest priority. Karr regulator of transcription; absence likely contributes to multiple downstream GATED processes never receiving correct demand signals.
2. `karr_trna_aminoacylation` (GATED gate; central dogma throughput limiter; starves translation and all protein post-processing).
3. `karr_replication_initiation` (GATED gate; DNA dynamics + division unlock).
4. `karr_rna_processing` (GATED gate; RNA maturation branch unlock).
5. `karr_cell_cycle_coordinator` (SHIM disposition decision: keep as documented integration shim OR decompose into Karr-native replication/segregation/cytokinesis hand-offs).

## Recommended next Codex session
1. **First: implement `karr_transcriptional_regulation`.** Port `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/TranscriptionalRegulation.m` to `opencell/vivarium/karr_transcriptional_regulation.py`. Use `docs/karr_extracts/process/10_TranscriptionalRegulation.md` as spec, `data/karr_fixtures/per_process/TranscriptionalRegulation_flat.mat` for fixture-driven init. Add to v6 chassis tuple. Wire ports. Add tests. Brings v6 chassis to 29 keys (28 Karr + 1 SHIM) and Karr-fidelity ladder to 28/28 Karr-with-impl.
2. **Then**: `docs/design/01_Metabolism.md` L2 spec v3 rewrite (current v2 is standing template debt), then fan out L2 specs for `karr_transcription`, `karr_transcriptional_regulation` (newly implemented), and `karr_translation` using the Table 2 artifact links.
