# Phase B Final — build_karr_chassis_v4 (full Phase B integration)

**Status**: design ready · **Estimated wall**: 45 min · **Final turn of Phase B**

## Why this turn

After all 11 Phase B processes ship, this turn wires them together into `build_karr_chassis_v4` — the chassis that covers **17 of 28 Karr processes (~61%)**. It also runs the extended ratchet validation across the full RNA + protein maturation pathway.

This is to Phase B what chassis_v3 was to Phase A3 — the empirical proof that the architectural design works at full scope.

## Wiring topology

Add to chassis_v3 (which already has 6 processes + 3 Steps):

**New processes**: 11 from Phase B turns 1-11
**New Steps**: 4 RequestCalculators (D2 already exists from v3; add RibAsm + tRNAAminoacylation + ProteinDecay-extended + RNA-pathway aggregate)

**Total chassis_v4**: 17 Processes + 4-7 Steps, all coordinated via KarrAllocationStep.

```
build_karr_chassis_v4(m1_model, m2_model, m3_model, ...):
  composite = {
    "processes": {
      # From chassis_v3
      "karr_m1": m1,
      "karr_transcription_v3": m2_v3,
      "karr_translation_v3": m3_v3,
      "karr_d2_real": d2_real,
      "karr_protein_decay_light": decay_light,
      # New from Phase B
      "karr_trna_aminoacylation": trna_aminoacylation,
      "karr_ribosome_assembly": ribosome_assembly,
      "karr_transcriptional_regulation": tx_regulation,  # modifies M2v3 via tx_rate_fold_change store
      "karr_rna_processing": rna_processing,
      "karr_rna_modification": rna_modification,
      "karr_protein_processing_i": pp1,
      "karr_protein_processing_ii": pp2,
      "karr_protein_modification": p_mod,
      "karr_protein_folding": p_folding,
      "karr_protein_translocation": p_trans,
      "karr_protein_activation": p_activation,
    },
    "steps": {
      # From chassis_v3
      "karr_allocation_step": allocation,
      "request_calculator_d2": req_d2,
      "request_calculator_pd": req_pd,
      # New from Phase B
      "request_calculator_ribasm": req_ribasm,
      "request_calculator_trna": req_trna,
      "request_calculator_rna_pathway": req_rna,  # aggregate for processing + modification
      "request_calculator_protein_pathway": req_protein,  # aggregate for proc + mod + folding + trans
    },
    "topology": {
      # ... all the port wiring ...
    },
  }
  return Engine(composite=composite, ...)
```

## Tests (10 tests, integration grade)

1. **test_chassis_v4_builds**
2. **test_chassis_v4_10_ticks_smoke**
3. **test_chassis_v4_full_protein_pipeline_10_ticks**: trace a single nascent protein from translation → ProteinProcessingI (deformylation) → ProteinFolding (chaperone + ions) → ProteinModification → ProteinActivation. Verify mass-conservation across all transitions.
4. **test_chassis_v4_full_rna_pipeline_10_ticks**: trace a polycistronic 30S precursor from M2v3 transcription → RNAProcessing (cleavage) → RNAModification (methylation/etc.) → mature rRNA available for RibosomeAssembly
5. **test_chassis_v4_ribosome_assembly_consumes_gtpases**: track GTPase counts across 100 ticks; verify GTP allocation correctly throttles assembly under scarcity
6. **test_chassis_v4_extended_ratchet_closure** (HEADLINE, 2000 ticks): all 17 processes running together for 2000 ticks at Δt=1s. Steady-state criterion: top-20 most-abundant complexes, top-20 most-abundant proteins, charged-tRNA fraction all within 25% drift between mid-run (ticks 800-1200) and late-run (ticks 1500-2000)
7. **test_chassis_v4_steady_state_charged_trna_67pct**: same 2000-tick run, charged-tRNA fraction at end is 67% ± 10% (matches Karr's `initializeState`)
8. **test_chassis_v3_still_works**: regression — `build_karr_chassis_v3` still produces identical output to pre-Phase-B baseline
9. **test_chassis_v4_all_writers_accumulate**: probe-4-style verification that all multi-writer leaves use accumulate
10. **test_chassis_v4_tick_rate**: chassis_v4 with 17 processes runs at >5 ticks/s (degradation from chassis_v3's 61 ticks/s is acceptable; <5 ticks/s is a perf flag)

## Acceptance criteria

- All 10 tests pass
- 2000-tick ratchet test is the headline gate
- Commit: `pb-final: build_karr_chassis_v4 + full Phase B integration validation`

## Out of scope

- Performance optimization beyond keeping chassis tick rate above 5/s
- Phase C (DNA + cell cycle) — separate phase
- Cell division / cytokinesis — Phase C

## Wallclock projection at this point

After pb-final lands:
- A3.3 chassis_v3: 6/28 processes (21%)
- Phase B chassis_v4: 17/28 processes (61%)
- Phase C target: 27/28 processes (96%)
- Phase D target: 28/28 (100%)
- Phase E: Karr validation against 28 phenotypes

We'd be ~3-4 months into the 9-month v1.0 trajectory.
