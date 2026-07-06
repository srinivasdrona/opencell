# HB4 Status

## Scope

- Write `scripts/migrate_wiring_rows_to_v2.py`.
- Deterministically migrate the 27 v1 wiring rows in `data/schemas/per_process_wiring/*.yaml`.
- Skip `Metabolism.yaml` and `_schema.yaml`.
- Preserve honest statuses and all unrelated content.

## Baseline

- Repo rules read from `SESSION_CONTEXT.md`.
- Wrapper execution confirmed via `cmd /c bin\oc-py ...` and `cmd /c bin\oc-pytest ...`.
- Baseline gate before migration:

```text
L1b wiring conformance: FAIL (0/28 rows PASS)
graph checks:
- no_dependency_cycles: PASS
  - validated acyclic dependency/order graph (28 nodes, 40 edges)
per-check failures:
- check_schema_conformance: 27 (ChromosomeCondensation, ChromosomeSegregation, Cytokinesis, DNADamage, DNARepair, DNASupercoiling, FtsZPolymerization, HostInteraction, MacromolecularComplexation, ProteinActivation, ProteinDecay, ProteinFolding, ProteinModification, ProteinProcessingI, ProteinProcessingII, ProteinTranslocation, RNADecay, RNAModification, RNAProcessing, Replication, ReplicationInitiation, RibosomeAssembly, TerminalOrganelleAssembly, Transcription, TranscriptionalRegulation, Translation, tRNAAminoacylation)
- check_stoichiometry_oracle_matches: 27 (ChromosomeCondensation, ChromosomeSegregation, Cytokinesis, DNADamage, DNARepair, DNASupercoiling, FtsZPolymerization, HostInteraction, MacromolecularComplexation, ProteinActivation, ProteinDecay, ProteinFolding, ProteinModification, ProteinProcessingI, ProteinProcessingII, ProteinTranslocation, RNADecay, RNAModification, RNAProcessing, Replication, ReplicationInitiation, RibosomeAssembly, TerminalOrganelleAssembly, Transcription, TranscriptionalRegulation, Translation, tRNAAminoacylation)
- check_half_a_b_consistency: 0
- check_a_invariants: 27 (ChromosomeCondensation, ChromosomeSegregation, Cytokinesis, DNADamage, DNARepair, DNASupercoiling, FtsZPolymerization, HostInteraction, MacromolecularComplexation, ProteinActivation, ProteinDecay, ProteinFolding, ProteinModification, ProteinProcessingI, ProteinProcessingII, ProteinTranslocation, RNADecay, RNAModification, RNAProcessing, Replication, ReplicationInitiation, RibosomeAssembly, TerminalOrganelleAssembly, Transcription, TranscriptionalRegulation, Translation, tRNAAminoacylation)
- check_matlab_anchors_resolve: 0
- check_oc_anchors_resolve: 0
- check_consume_produce_wids_in_schema_toml: 0
- check_allocator_requests_wids_in_schema_toml: 0
- check_unit_conversion_chain_coherent: 0
- check_ordering_constraints_reference_valid_processes: 0
- check_dependency_symmetry: 16 (ChromosomeSegregation, DNADamage, FtsZPolymerization, HostInteraction, MacromolecularComplexation, ProteinActivation, ProteinDecay, ProteinFolding, ProteinModification, RNADecay, RNAModification, RibosomeAssembly, TerminalOrganelleAssembly, TranscriptionalRegulation, Translation, tRNAAminoacylation)
- check_orphan_consume_wids: 20 (ChromosomeCondensation, ChromosomeSegregation, DNARepair, DNASupercoiling, FtsZPolymerization, MacromolecularComplexation, Metabolism, ProteinDecay, ProteinFolding, ProteinModification, ProteinProcessingII, ProteinTranslocation, RNAModification, RNAProcessing, Replication, ReplicationInitiation, RibosomeAssembly, Transcription, Translation, tRNAAminoacylation)
- check_deviations_reference_valid_anchors: 0
```

## Progress Log

- Read `scripts/l1b_verify_wiring.py` for `_resolve_anchor_path`, `_resolve_matlab_anchor_path`, `_SymbolCollector`, and `FileCache.symbols()`.
- Read `data/schemas/per_process_wiring/Metabolism.yaml` as the v2 reference shape.
- Verified `data/karr_method_inventory/karr_stoichiometry/*.json` contains row-matched oracle records for all 27 target processes.
- Wrote `scripts/migrate_wiring_rows_to_v2.py`.
- Verified the script compiles with `cmd /c bin\oc-py -m py_compile scripts/migrate_wiring_rows_to_v2.py`.

## Script Behavior

- Loads YAML with `ruamel.yaml` round-trip mode when available; the dry-run confirmed `ruamel`.
- Reuses `scripts/l1b_verify_wiring.py` helpers for `_resolve_anchor_path`, `_resolve_matlab_anchor_path`, `_parse_line_span`, and `FileCache.symbols()`.
- Renames `methods` to `integration_touchpoints` and keeps only:
  - `calcResourceRequirements_Current`
  - `evolveState`
  - `calcFluxBounds`
- Fills missing method-source anchor symbols by copying the parent `matlab.symbol` or `oc.symbol`.
- Walks the full row recursively and fills every remaining `source_anchor.symbol` only when it can extract an enclosing Python/MATLAB symbol from the cited file/lines.
- Adds `stoichiometry_oracle` from `data/karr_method_inventory/karr_stoichiometry/<Process>.json`.
- Adds `kind` to all consume/produce stoichiometry entries.
- Strips the v1 escape-hatch note sentence from `process.notes` if present.
- Supports `--dry-run` and `--report-json` for audit-first execution.

## Dry-Run Result

- Command:

```text
cmd /c bin\oc-py scripts/migrate_wiring_rows_to_v2.py --dry-run --report-json tmp/hb4_migration_dry_run.json
```

- Totals:
  - `rows_total=27`
  - `copy_parent_fills_total=162`
  - `source_extract_fills_total=879`
  - `unresolved_total=125`
  - `rows_without_unresolved=9`
  - `rows_with_unresolved=18`
  - `rows_blocked=[]`
- Unresolved-anchor type breakdown:
  - `.md`: 115
  - `.py`: 10
- Rows with zero unresolved anchors:
  - `ChromosomeCondensation, Cytokinesis, ProteinProcessingI, ProteinProcessingII, RNAProcessing, ReplicationInitiation, RibosomeAssembly, TerminalOrganelleAssembly, Translation`
- Machine-readable report written to `tmp/hb4_migration_dry_run.json`.

## Commit SHAs

- Script commit: `9d67b61` (`hb4: add deterministic wiring row migrator`)
- Status/report commit: `6191e35` (`hb4: record dry-run migration report`)
- Migrated-row commit: not created; dry-run stop condition prevented in-place row writes

## Stop Decision

- The prompt's stop condition fired: `125` unresolved anchors is "many".
- Most unresolved anchors are doc-backed `.md` references, which the spec does not permit me to symbol-fill by extraction.
- The remaining unresolved `.py` anchors are module-header / top-of-file spans with no enclosing def/class at the cited start line, so the spec also does not permit inventing symbols there.
- Because of that, I did **not** run the in-place migration on the 27 rows, did **not** run a post-migration gate, and did **not** run the integration test suite. Forcing the write would leave many rows still failing `check_schema_conformance`, which is exactly the hollow-green failure the task warns against.

## Gate After

- Not run.
- Reason: dry-run found `125` unresolved anchors, so execution stopped before rewriting row files.

## Test After

- Not run.
- Reason: prompt-directed early stop after script + dry-run report.

## Per-Row Fill Report

```text
ChromosomeCondensation | copy=6 | extract=34 | unresolved=0 | dropped=calcResourceRequirements_LifeCycle,initializeState,calcNewRegions
ChromosomeSegregation | copy=6 | extract=16 | unresolved=7 | dropped=-
Cytokinesis | copy=6 | extract=23 | unresolved=0 | dropped=calcResourceRequirements_LifeCycle
DNADamage | copy=6 | extract=22 | unresolved=12 | dropped=-
DNARepair | copy=6 | extract=45 | unresolved=11 | dropped=-
DNASupercoiling | copy=6 | extract=35 | unresolved=2 | dropped=initializeConstants,calcResourceRequirements_LifeCycle,initializeState,calcRNAPolymeraseBindingProbFoldChange,buildEnzymeProperties
FtsZPolymerization | copy=6 | extract=15 | unresolved=10 | dropped=-
HostInteraction | copy=6 | extract=18 | unresolved=1 | dropped=-
MacromolecularComplexation | copy=6 | extract=19 | unresolved=14 | dropped=buildProteinComplexs_bounds,buildProteinComplexs_montecarlokinetic
ProteinActivation | copy=6 | extract=17 | unresolved=15 | dropped=-
ProteinDecay | copy=6 | extract=41 | unresolved=1 | dropped=calcResourceRequirements_LifeCycle
ProteinFolding | copy=6 | extract=22 | unresolved=9 | dropped=-
ProteinModification | copy=6 | extract=25 | unresolved=6 | dropped=-
ProteinProcessingI | copy=6 | extract=27 | unresolved=0 | dropped=initializeConstants
ProteinProcessingII | copy=6 | extract=30 | unresolved=0 | dropped=initializeConstants,copyFromState,copyToState,allocateMemoryForState,calcResourceRequirements_LifeCycle
ProteinTranslocation | copy=6 | extract=15 | unresolved=11 | dropped=-
RNADecay | copy=6 | extract=16 | unresolved=11 | dropped=-
RNAModification | copy=6 | extract=40 | unresolved=1 | dropped=-
RNAProcessing | copy=6 | extract=31 | unresolved=0 | dropped=calcResourceRequirements_LifeCycle,getDryWeight
Replication | copy=6 | extract=34 | unresolved=5 | dropped=-
ReplicationInitiation | copy=6 | extract=35 | unresolved=0 | dropped=initializeState,initializeStateBasedOnFinalConditions,initializeStateBasedOnTheory
RibosomeAssembly | copy=6 | extract=145 | unresolved=0 | dropped=initializeConstants,initializeState,calcResourceRequirements_LifeCycle
TerminalOrganelleAssembly | copy=6 | extract=49 | unresolved=0 | dropped=initializeConstants,calcResourceRequirements_LifeCycle
Transcription | copy=6 | extract=36 | unresolved=2 | dropped=initializeState,computeRNAPolymeraseTUBindingProbabilities
TranscriptionalRegulation | copy=6 | extract=7 | unresolved=5 | dropped=-
Translation | copy=6 | extract=41 | unresolved=0 | dropped=initializeConstants
tRNAAminoacylation | copy=6 | extract=41 | unresolved=2 | dropped=initializeConstants,initializeSpeciesNetwork,calcResourceRequirements_LifeCycle,initializeState
```

## Unresolved Anchors

```text
ChromosomeSegregation | unit_conversion_chain.steps[0].anchor | docs/design/pc-t5-segregation.md | 68-90
ChromosomeSegregation | source_anchors.matlab_blocks.docstring_and_gate | docs/karr_extracts/process/08_ChromosomeSegregation.md | 49-75
ChromosomeSegregation | source_anchors.matlab_blocks.strict_zero_evidence | opencell/validation/swarm/l5/karr_zero_grant_behavior.md | 29-64
ChromosomeSegregation | source_anchors.matlab_blocks.allocation_loop | docs/karr_extracts/architecture/01_simulation_loop.md | 122-194
ChromosomeSegregation | source_anchors.matlab_blocks.phase_c_design | docs/design/pc-t5-segregation.md | 17-90
ChromosomeSegregation | source_anchors.oc_blocks.canonical_complex_lookup | opencell/vivarium/karr_chromosome_segregation.py | 77-92
ChromosomeSegregation | deviations.lp_bounds_source.matlab_anchor | docs/design/pc-t5-segregation.md | 17-26
DNADamage | consume_stoichiometry[0].matlab_anchor | docs/karr_extracts/process/04_DNADamage.md | 146-178
DNADamage | consume_stoichiometry[1].matlab_anchor | docs/karr_extracts/process/04_DNADamage.md | 146-178
DNADamage | consume_stoichiometry[2].matlab_anchor | docs/karr_extracts/process/04_DNADamage.md | 146-178
DNADamage | produce_stoichiometry[0].matlab_anchor | docs/karr_extracts/process/04_DNADamage.md | 170-178
DNADamage | produce_stoichiometry[1].matlab_anchor | docs/karr_extracts/process/04_DNADamage.md | 170-178
DNADamage | produce_stoichiometry[2].matlab_anchor | docs/karr_extracts/process/04_DNADamage.md | 170-178
DNADamage | produce_stoichiometry[3].matlab_anchor | docs/karr_extracts/process/04_DNADamage.md | 170-178
DNADamage | source_anchors.matlab_blocks.biology_summary | docs/karr_extracts/process/04_DNADamage.md | 14-63
DNADamage | source_anchors.matlab_blocks.knowledge_base_and_rates | docs/karr_extracts/process/04_DNADamage.md | 65-120
DNADamage | source_anchors.matlab_blocks.representation_and_simulation | docs/karr_extracts/process/04_DNADamage.md | 122-179
DNADamage | source_anchors.oc_blocks.module_header | opencell/vivarium/karr_dna_damage.py | 1-10
DNADamage | deviations.lp_bounds_source.matlab_anchor | docs/karr_extracts/process/04_DNADamage.md | 146-179
DNARepair | consume_stoichiometry[0].matlab_anchor | docs/karr_extracts/process/05_DNARepair.md | 257-294
DNARepair | produce_stoichiometry[0].matlab_anchor | docs/karr_extracts/process/05_DNARepair.md | 257-294
DNARepair | produce_stoichiometry[1].matlab_anchor | docs/karr_extracts/process/05_DNARepair.md | 257-294
DNARepair | produce_stoichiometry[2].matlab_anchor | docs/karr_extracts/process/05_DNARepair.md | 183-194
DNARepair | produce_stoichiometry[3].matlab_anchor | docs/karr_extracts/process/05_DNARepair.md | 183-194
DNARepair | source_anchors.matlab_blocks.process_header | docs/karr_extracts/process/05_DNARepair.md | 1-6
DNARepair | source_anchors.matlab_blocks.repair_description | docs/karr_extracts/process/05_DNARepair.md | 16-94
DNARepair | source_anchors.matlab_blocks.substrate_and_enzyme_setup | docs/karr_extracts/process/05_DNARepair.md | 246-270
DNARepair | source_anchors.matlab_blocks.repair_loop | docs/karr_extracts/process/05_DNARepair.md | 275-294
DNARepair | source_anchors.matlab_blocks.allocator_request | docs/karr_extracts/architecture/01_simulation_loop.md | 125-160
DNARepair | deviations.lp_bounds_source.matlab_anchor | docs/karr_extracts/architecture/01_simulation_loop.md | 125-160
DNASupercoiling | integration_touchpoints.calcResourceRequirements_Current.oc.supporting[2] | opencell/vivarium/karr_allocation_step.py | 79-84
DNASupercoiling | source_anchors.oc_blocks.allocator_consumer_vector | opencell/vivarium/karr_allocation_step.py | 79-84
FtsZPolymerization | consume_stoichiometry[0].matlab_anchor | docs/karr_extracts/process/25_FtsZPolymerization.md | 29-37
FtsZPolymerization | consume_stoichiometry[1].matlab_anchor | docs/karr_extracts/process/25_FtsZPolymerization.md | 20-37
FtsZPolymerization | consume_stoichiometry[2].matlab_anchor | docs/karr_extracts/process/25_FtsZPolymerization.md | 29-37
FtsZPolymerization | produce_stoichiometry[0].matlab_anchor | docs/karr_extracts/process/25_FtsZPolymerization.md | 29-37
FtsZPolymerization | produce_stoichiometry[1].matlab_anchor | docs/karr_extracts/process/25_FtsZPolymerization.md | 29-37
FtsZPolymerization | produce_stoichiometry[2].matlab_anchor | docs/karr_extracts/process/25_FtsZPolymerization.md | 29-37
FtsZPolymerization | source_anchors.matlab_blocks.process_summary | docs/karr_extracts/process/25_FtsZPolymerization.md | 11-37
FtsZPolymerization | source_anchors.matlab_blocks.allocation_block | docs/karr_extracts/architecture/01_simulation_loop.md | 148-161
FtsZPolymerization | source_anchors.matlab_blocks.global_order | docs/karr_extracts/architecture/01_simulation_loop.md | 172-180
FtsZPolymerization | deviations.lp_bounds_source.matlab_anchor | docs/karr_extracts/process/25_FtsZPolymerization.md | 29-37
HostInteraction | source_anchors.oc_blocks.module_docstring | opencell/vivarium/karr_host_interaction.py | 1-24
MacromolecularComplexation | consume_stoichiometry[0].matlab_anchor | docs/design/a3_step3_joint_design_v1.md | 114-115
MacromolecularComplexation | consume_stoichiometry[1].matlab_anchor | docs/design/a3_step3_joint_design_v1.md | 114-115
MacromolecularComplexation | consume_stoichiometry[2].matlab_anchor | docs/design/a3_step3_joint_design_v1.md | 114-115
MacromolecularComplexation | consume_stoichiometry[3].matlab_anchor | docs/design/a3_step3_joint_design_v1.md | 114-115
MacromolecularComplexation | produce_stoichiometry[0].matlab_anchor | docs/design/a3_step3_joint_design_v1.md | 114-115
MacromolecularComplexation | produce_stoichiometry[1].matlab_anchor | docs/design/a3_step3_joint_design_v1.md | 114-115
MacromolecularComplexation | produce_stoichiometry[2].matlab_anchor | docs/design/a3_step3_joint_design_v1.md | 114-115
MacromolecularComplexation | produce_stoichiometry[3].matlab_anchor | docs/design/a3_step3_joint_design_v1.md | 114-115
MacromolecularComplexation | source_anchors.matlab_blocks.resource_req_zero | docs/design/a33_turn3_d2_real.md | 85-87
MacromolecularComplexation | source_anchors.matlab_blocks.evolve_state_main | docs/design/a3_step3_joint_design_v1.md | 89-117
MacromolecularComplexation | source_anchors.matlab_blocks.closed_form_cluster | docs/design/a3_step3_joint_design_v1.md | 121-129
MacromolecularComplexation | source_anchors.matlab_blocks.competitive_cluster | docs/design/a3_step3_joint_design_v1.md | 133-171
MacromolecularComplexation | source_anchors.matlab_blocks.allocator_sequence | docs/phase_f/L2_5_HARNESS_DESIGN.md | 88-91
MacromolecularComplexation | deviations.lp_bounds_source.matlab_anchor | docs/design/a33_turn3_d2_real.md | 85-87
ProteinActivation | consume_stoichiometry[0].matlab_anchor | docs/karr_extracts/process/20_ProteinActivation.md | 102-117
ProteinActivation | consume_stoichiometry[1].matlab_anchor | docs/karr_extracts/process/20_ProteinActivation.md | 102-117
ProteinActivation | consume_stoichiometry[2].matlab_anchor | docs/karr_extracts/process/20_ProteinActivation.md | 102-117
ProteinActivation | consume_stoichiometry[3].matlab_anchor | docs/karr_extracts/process/20_ProteinActivation.md | 102-117
ProteinActivation | produce_stoichiometry[0].matlab_anchor | docs/karr_extracts/process/20_ProteinActivation.md | 102-117
ProteinActivation | produce_stoichiometry[1].matlab_anchor | docs/karr_extracts/process/20_ProteinActivation.md | 102-117
ProteinActivation | produce_stoichiometry[2].matlab_anchor | docs/karr_extracts/process/20_ProteinActivation.md | 102-117
ProteinActivation | produce_stoichiometry[3].matlab_anchor | docs/karr_extracts/process/20_ProteinActivation.md | 102-117
ProteinActivation | source_anchors.matlab_blocks.class_identity | docs/karr_extracts/process/20_ProteinActivation.md | 1-7
ProteinActivation | source_anchors.matlab_blocks.biology_and_rule_scope | docs/karr_extracts/process/20_ProteinActivation.md | 13-47
ProteinActivation | source_anchors.matlab_blocks.rule_syntax | docs/karr_extracts/process/20_ProteinActivation.md | 49-68
ProteinActivation | source_anchors.matlab_blocks.representation_and_initialization | docs/karr_extracts/process/20_ProteinActivation.md | 76-100
ProteinActivation | source_anchors.matlab_blocks.evolve_state | docs/karr_extracts/process/20_ProteinActivation.md | 102-117
ProteinActivation | source_anchors.oc_blocks.module_and_fixture_load | opencell/vivarium/karr_protein_activation.py | 1-19
ProteinActivation | deviations.lp_bounds_source.matlab_anchor | docs/karr_extracts/process/20_ProteinActivation.md | 49-117
ProteinDecay | source_anchors.oc_blocks.allocator_key_mapping | opencell/vivarium/karr_allocation_step.py | 18-24
ProteinFolding | consume_stoichiometry[1].matlab_anchor | docs/karr_extracts/process/19_ProteinFolding.md | 1-175
ProteinFolding | consume_stoichiometry[2].matlab_anchor | docs/karr_extracts/process/19_ProteinFolding.md | 1-175
ProteinFolding | consume_stoichiometry[5].matlab_anchor | docs/karr_extracts/process/19_ProteinFolding.md | 1-175
ProteinFolding | consume_stoichiometry[6].matlab_anchor | docs/karr_extracts/process/19_ProteinFolding.md | 1-175
ProteinFolding | source_anchors.matlab_blocks.process_docstring_and_reconstruction | docs/karr_extracts/process/19_ProteinFolding.md | 1-175
ProteinFolding | source_anchors.matlab_blocks.catalytic_enzyme_gate_semantics | docs/phase_e/L2_STATUS.md | 41-41
ProteinFolding | source_anchors.matlab_blocks.stochastic_selection_note | docs/phase_f/L2_2_STOCHASTIC_AUDIT.md | 49-49
ProteinFolding | source_anchors.matlab_blocks.protein_pipeline_design | docs/design/pb_final_chassis_v4_integration.md | 65-65
ProteinFolding | deviations.lp_bounds_source.matlab_anchor | docs/karr_extracts/process/19_ProteinFolding.md | 1-175
ProteinModification | consume_stoichiometry[1].matlab_anchor | docs/design/pb_turn8_protein_modification.md | 5-21
ProteinModification | consume_stoichiometry[2].matlab_anchor | docs/design/pb_turn8_protein_modification.md | 5-21
ProteinModification | produce_stoichiometry[1].matlab_anchor | docs/design/pb_turn8_protein_modification.md | 14-21
ProteinModification | source_anchors.matlab_blocks.class_and_scope | docs/design/pb_turn8_protein_modification.md | 1-24
ProteinModification | source_anchors.matlab_blocks.lifecycle_context | docs/design/pb_final_chassis_v4_integration.md | 65-65
ProteinModification | deviations.lp_bounds_source.matlab_anchor | docs/design/pb_turn8_protein_modification.md | 14-21
ProteinTranslocation | consume_stoichiometry[0].matlab_anchor | docs/phase_f/sut_audits/ptransloc_oc_vs_karr.md | 70-72
ProteinTranslocation | consume_stoichiometry[1].matlab_anchor | docs/karr_extracts/process/22_ProteinTranslocation.md | 107-110
ProteinTranslocation | consume_stoichiometry[2].matlab_anchor | docs/phase_f/sut_audits/ptransloc_oc_vs_karr.md | 70-72
ProteinTranslocation | produce_stoichiometry[0].matlab_anchor | docs/phase_f/sut_audits/ptransloc_oc_vs_karr.md | 63-72
ProteinTranslocation | produce_stoichiometry[1].matlab_anchor | docs/phase_f/sut_audits/ptransloc_oc_vs_karr.md | 63-72
ProteinTranslocation | produce_stoichiometry[2].matlab_anchor | docs/phase_f/sut_audits/ptransloc_oc_vs_karr.md | 63-72
ProteinTranslocation | produce_stoichiometry[3].matlab_anchor | docs/phase_f/sut_audits/ptransloc_oc_vs_karr.md | 63-72
ProteinTranslocation | source_anchors.matlab_blocks.docstring_summary | docs/karr_extracts/process/22_ProteinTranslocation.md | 1-131
ProteinTranslocation | source_anchors.matlab_blocks.request_terms | docs/karr_extracts/process/22_ProteinTranslocation.md | 103-111
ProteinTranslocation | source_anchors.matlab_blocks.evolve_state | docs/phase_f/sut_audits/ptransloc_oc_vs_karr.md | 48-72
ProteinTranslocation | deviations.lp_bounds_source.matlab_anchor | docs/karr_extracts/process/22_ProteinTranslocation.md | 103-111
RNADecay | consume_stoichiometry[0].matlab_anchor | docs/karr_extracts/process/13_RNADecay.md | 84-92
RNADecay | produce_stoichiometry[0].matlab_anchor | docs/karr_extracts/process/13_RNADecay.md | 91-92
RNADecay | produce_stoichiometry[1].matlab_anchor | docs/karr_extracts/process/13_RNADecay.md | 91-92
RNADecay | produce_stoichiometry[2].matlab_anchor | docs/karr_extracts/process/13_RNADecay.md | 91-92
RNADecay | produce_stoichiometry[3].matlab_anchor | docs/karr_extracts/process/13_RNADecay.md | 91-92
RNADecay | produce_stoichiometry[4].matlab_anchor | docs/karr_extracts/process/13_RNADecay.md | 91-92
RNADecay | source_anchors.matlab_blocks.process_docstring | docs/karr_extracts/process/13_RNADecay.md | 16-92
RNADecay | source_anchors.matlab_blocks.allocation_loop | docs/karr_extracts/architecture/03_variable_allocation.md | 10-23
RNADecay | source_anchors.matlab_blocks.simulation_order | docs/karr_extracts/architecture/01_simulation_loop.md | 166-197
RNADecay | source_anchors.matlab_blocks.allocation_consumer_inventory | docs/design/allocation_consumer_enrollment.md | 13-24
RNADecay | deviations.lp_bounds_source.matlab_anchor | docs/karr_extracts/process/13_RNADecay.md | 75-92
RNAModification | source_anchors.matlab_blocks.simulation_ordering | docs/phase_f/L2_5_HARNESS_DESIGN.md | 83-89
Replication | consume_stoichiometry[4].matlab_anchor | docs/karr_extracts/process/03_Replication.md | 114-131
Replication | source_anchors.matlab_blocks.process_header | docs/karr_extracts/process/03_Replication.md | 1-17
Replication | source_anchors.matlab_blocks.simulation_subfunctions | docs/karr_extracts/process/03_Replication.md | 103-173
Replication | source_anchors.matlab_blocks.allocator_loop | docs/karr_extracts/architecture/03_variable_allocation.md | 13-23
Replication | deviations.lp_bounds_source.matlab_anchor | docs/karr_extracts/process/03_Replication.md | 103-173
Transcription | integration_touchpoints.evolveState.oc.supporting[1] | opencell/m2/transcription_v2.py | 1-95
Transcription | source_anchors.oc_blocks.mechanism_helper | opencell/m2/transcription_v2.py | 1-95
TranscriptionalRegulation | source_anchors.matlab_blocks.process_docstring | docs/karr_extracts/process/10_TranscriptionalRegulation.md | 1-123
TranscriptionalRegulation | source_anchors.matlab_blocks.allocation_surface | docs/karr_extracts/architecture/03_variable_allocation.md | 7-29
TranscriptionalRegulation | source_anchors.matlab_blocks.simulation_ordering | docs/karr_extracts/architecture/01_simulation_loop.md | 148-180
TranscriptionalRegulation | source_anchors.matlab_blocks.regulatory_summary | docs/design/pb_turn3_transcriptional_regulation.md | 7-32
TranscriptionalRegulation | deviations.lp_bounds_source.matlab_anchor | docs/karr_extracts/process/10_TranscriptionalRegulation.md | 79-106
tRNAAminoacylation | source_anchors.matlab_blocks.simulation_ordering | docs/karr_extracts/architecture/01_simulation_loop.md | 172-179
tRNAAminoacylation | source_anchors.oc_blocks.module_fixture_loaders | opencell/vivarium/karr_trna_aminoacylation.py | 54-64
```

## Pending

- Commit the script separately.
- Hand off the unresolved-anchor inventory for planner follow-up.
