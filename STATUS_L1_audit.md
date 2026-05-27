# STATUS_L1_audit.md

## Final counts
- L1-IMPLEMENTED-FIRING: 11 / 28
- L1-IMPLEMENTED-GATED: 15 / 28
- L1-STUB: 2 / 28
- L1-green total: 26 / 28

## Top-3 surprising findings
1. `karr_rna_modification` is FIRING at 32,400t (all 4 seeds non-header traces) even though the earlier 200t probe looked nearly dead.
2. `karr_dna_damage` is fully DEAD at 32,400t (header-only traces in all seeds), not just sparse/partial as earlier short-horizon assumptions suggested.
3. `karr_protein_activation` resolves as a strict L1 STUB under the new ladder: `next_update` is a 10-line rule writeback and never emits non-header activity traces in wave2.

## Top-5 STUB-blocking fanout (ranked by downstream unblock)
- Strict STUBs discovered in this chassis key set are only two; items 3-5 are immediate near-stub gates that most block L2 fanout.
1. `karr_cell_cycle_coordinator` (strict STUB, cell-division control hinge)
2. `karr_protein_activation` (strict STUB, protein post-processing chain hinge)
3. `karr_trna_aminoacylation` (near-stub gate; central dogma throughput limiter)
4. `karr_replication_initiation` (near-stub gate; DNA dynamics + division unlock)
5. `karr_rna_processing` (near-stub gate; RNA maturation branch unlock)

## Recommended next Codex session
- Start with `docs/design/01_Metabolism.md` L2 spec v3 rewrite (current v2 is the standing template debt), then immediately fan out L2 specs for `karr_transcription` and `karr_translation` using the new Table 2 artifact links.
