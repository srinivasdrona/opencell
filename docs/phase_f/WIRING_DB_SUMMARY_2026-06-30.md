# Wiring DB Cross-Row Validation Summary

- Source rows: `28`
- Canonical roster size: `28`
- Validator status: `FAIL`
- Validator exit code captured in file: `1`

## Coverage

| Process | YAML size (KB) | methods.*.status distribution |
| --- | ---: | --- |
| ChromosomeCondensation | 17.0 | implemented=0, partial=2, not_implemented=1, other=0 |
| ChromosomeSegregation | 13.6 | implemented=0, partial=2, not_implemented=1, other=0 |
| Cytokinesis | 13.3 | implemented=1, partial=1, not_implemented=1, other=0 |
| DNADamage | 16.4 | implemented=0, partial=1, not_implemented=2, other=0 |
| DNARepair | 17.1 | implemented=0, partial=2, not_implemented=1, other=0 |
| DNASupercoiling | 22.0 | implemented=0, partial=2, not_implemented=1, other=0 |
| FtsZPolymerization | 13.4 | implemented=0, partial=2, not_implemented=1, other=0 |
| HostInteraction | 8.9 | implemented=0, partial=1, not_implemented=2, other=0 |
| MacromolecularComplexation | 15.8 | implemented=1, partial=1, not_implemented=1, other=0 |
| Metabolism | 22.1 | implemented=1, partial=2, not_implemented=0, other=0 |
| ProteinActivation | 15.0 | implemented=1, partial=0, not_implemented=2, other=0 |
| ProteinDecay | 20.2 | implemented=0, partial=2, not_implemented=1, other=0 |
| ProteinFolding | 13.6 | implemented=0, partial=2, not_implemented=1, other=0 |
| ProteinModification | 15.1 | implemented=1, partial=1, not_implemented=1, other=0 |
| ProteinProcessingI | 15.3 | implemented=0, partial=2, not_implemented=1, other=0 |
| ProteinProcessingII | 18.5 | implemented=0, partial=2, not_implemented=1, other=0 |
| ProteinTranslocation | 15.3 | implemented=0, partial=2, not_implemented=1, other=0 |
| RNADecay | 14.4 | implemented=0, partial=2, not_implemented=1, other=0 |
| RNAModification | 19.3 | implemented=0, partial=2, not_implemented=1, other=0 |
| RNAProcessing | 18.0 | implemented=0, partial=2, not_implemented=1, other=0 |
| Replication | 16.2 | implemented=0, partial=2, not_implemented=1, other=0 |
| ReplicationInitiation | 17.0 | implemented=0, partial=2, not_implemented=1, other=0 |
| RibosomeAssembly | 21.0 | implemented=2, partial=0, not_implemented=1, other=0 |
| TerminalOrganelleAssembly | 19.1 | implemented=0, partial=1, not_implemented=2, other=0 |
| Transcription | 19.6 | implemented=0, partial=2, not_implemented=1, other=0 |
| TranscriptionalRegulation | 9.7 | implemented=1, partial=0, not_implemented=2, other=0 |
| Translation | 21.2 | implemented=0, partial=2, not_implemented=1, other=0 |
| tRNAAminoacylation | 22.4 | implemented=0, partial=2, not_implemented=1, other=0 |

28/28 rows present. Method status aggregate: implemented=8, partial=44, not_implemented=32, other=0.

## Schema Conformance

| Process | schema_version | schema_date | provenance complete | missing provenance fields | validator issues |
| --- | --- | --- | --- | --- | --- |
| ChromosomeCondensation | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| ChromosomeSegregation | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| Cytokinesis | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| DNADamage | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| DNARepair | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| DNASupercoiling | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| FtsZPolymerization | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; unit_conversion_chain.steps[0].anchor: lines must match start-end; unit_conversion_chain.steps[2].anchor: lines must match start-end; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| HostInteraction | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| MacromolecularComplexation | 1.0 | missing | no | matlab_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list |
| Metabolism | 1.0 | 2026-06-29 | yes | none | none |
| ProteinActivation | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| ProteinDecay | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| ProteinFolding | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| ProteinModification | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; unit_conversion_chain.steps[0].anchor: lines must match start-end; unit_conversion_chain.steps[2].anchor: lines must match start-end; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| ProteinProcessingI | 1.0 | missing | yes | none | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD |
| ProteinProcessingII | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| ProteinTranslocation | 1.0 | missing | no | matlab_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list |
| RNADecay | 1.0 | missing | no | matlab_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list |
| RNAModification | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| RNAProcessing | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| Replication | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| ReplicationInitiation | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| RibosomeAssembly | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| TerminalOrganelleAssembly | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; compartment_routing[0]: mismatch=True does not match compartments 'membrane'/'membrane'; compartment_routing[1]: mismatch=True does not match compartments 'cytosol'/'cytosol'; compartment_routing[2]: mismatch=True does not match compartments 'cytosol'/'cytosol'; compartment_routing[3]: mismatch=True does not match compartments 'membrane'/'membrane'; compartment_routing[4]: mismatch=True does not match compartments 'cytosol'/'cytosol'; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| Transcription | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| TranscriptionalRegulation | 1.0 | missing | no | last_audited, audited_by, oc_commit_sha, matlab_files_referenced, oc_files_referenced | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list |
| Translation | 1.0 | missing | yes | none | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD |
| tRNAAminoacylation | 1.0 | missing | yes | none | missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD |

Schema-version tally: `28` rows at `1.0`, `0` other. Schema-date tally: `1` rows at or after `2026-06-29`, `27` other or missing.
Provenance completeness: `4` rows have all five required provenance fields; field coverage = last_audited `7`, audited_by `7`, oc_commit_sha `7`, matlab_files_referenced `4`, oc_files_referenced `7`.

## Audit Traceability Hooks (A1-A4)

| Process | A1 allocator cap | A2 process order | A3 LP bounds source | A3b consumption clip | A4 compartment merge |
| --- | --- | --- | --- | --- | --- |
| ChromosomeCondensation | yes | yes | yes | no | yes |
| ChromosomeSegregation | yes | yes | yes | no | yes |
| Cytokinesis | yes | yes | yes | no | yes |
| DNADamage | yes | yes | yes | no | yes |
| DNARepair | yes | yes | yes | no | yes |
| DNASupercoiling | yes | yes | yes | no | yes |
| FtsZPolymerization | yes | yes | yes | no | yes |
| HostInteraction | yes | yes | yes | no | yes |
| MacromolecularComplexation | yes | yes | yes | no | yes |
| Metabolism | yes | yes | yes | no | yes |
| ProteinActivation | yes | yes | yes | no | yes |
| ProteinDecay | yes | yes | yes | no | yes |
| ProteinFolding | yes | yes | yes | no | yes |
| ProteinModification | yes | yes | yes | no | yes |
| ProteinProcessingI | yes | yes | yes | no | yes |
| ProteinProcessingII | yes | yes | yes | no | yes |
| ProteinTranslocation | yes | yes | yes | no | yes |
| RNADecay | yes | yes | yes | no | yes |
| RNAModification | yes | yes | yes | no | yes |
| RNAProcessing | yes | yes | yes | no | yes |
| Replication | yes | yes | yes | no | yes |
| ReplicationInitiation | yes | yes | yes | no | yes |
| RibosomeAssembly | yes | yes | yes | no | yes |
| TerminalOrganelleAssembly | yes | yes | yes | no | yes |
| Transcription | yes | yes | yes | no | yes |
| TranscriptionalRegulation | yes | yes | yes | no | yes |
| Translation | yes | yes | yes | no | yes |
| tRNAAminoacylation | yes | yes | yes | no | yes |

Hook tally: A1 `28`, A2 `28`, A3 `28`, A3b `0`, A4 `28`.

## Cross-Row Consistency

Validator summary: `53` reciprocal dependency mismatches, `2` cyclic ordering violations, `0` missing canonical rows.

First mismatches:
- <ChromosomeCondensation produces_inputs_for=[Metabolism], Metabolism consumes_outputs_of=[]>
- <ChromosomeSegregation produces_inputs_for=[Cytokinesis], Cytokinesis consumes_outputs_of=[Metabolism]>
- <ChromosomeSegregation produces_inputs_for=[Metabolism], Metabolism consumes_outputs_of=[]>
- <Cytokinesis produces_inputs_for=[Metabolism], Metabolism consumes_outputs_of=[]>
- <DNADamage produces_inputs_for=[DNARepair], DNARepair consumes_outputs_of=[Metabolism]>
- <DNARepair produces_inputs_for=[Metabolism], Metabolism consumes_outputs_of=[]>
- <DNASupercoiling produces_inputs_for=[Metabolism], Metabolism consumes_outputs_of=[]>
- <FtsZPolymerization produces_inputs_for=[Cytokinesis], Cytokinesis consumes_outputs_of=[Metabolism]>
- <MacromolecularComplexation produces_inputs_for=[RibosomeAssembly], RibosomeAssembly consumes_outputs_of=[Transcription, RNAProcessing, RNAModification, Translation, ProteinProcessingI, ProteinProcessingII]>
- <MacromolecularComplexation produces_inputs_for=[Translation], Translation consumes_outputs_of=[Transcription, RNAProcessing, RNAModification, tRNAAminoacylation, Metabolism]>
- <MacromolecularComplexation produces_inputs_for=[Transcription], Transcription consumes_outputs_of=[Metabolism]>
- <MacromolecularComplexation produces_inputs_for=[ProteinTranslocation], ProteinTranslocation consumes_outputs_of=[Translation]>
- <Metabolism produces_inputs_for=[RNAModification], RNAModification consumes_outputs_of=[RNAProcessing]>
- <Metabolism produces_inputs_for=[RNADecay], RNADecay consumes_outputs_of=[Transcription, RNAProcessing, RNAModification, tRNAAminoacylation]>
- <Metabolism produces_inputs_for=[ProteinProcessingI], ProteinProcessingI consumes_outputs_of=[Translation]>
- <Metabolism produces_inputs_for=[ProteinProcessingII], ProteinProcessingII consumes_outputs_of=[Translation, ProteinProcessingI, ProteinTranslocation]>
- <Metabolism produces_inputs_for=[ProteinTranslocation], ProteinTranslocation consumes_outputs_of=[Translation]>
- <Metabolism produces_inputs_for=[ProteinDecay], ProteinDecay consumes_outputs_of=[Translation, ProteinFolding, ProteinProcessingI, ProteinProcessingII, MacromolecularComplexation]>
- <Metabolism produces_inputs_for=[ProteinFolding], ProteinFolding consumes_outputs_of=[Translation, ProteinProcessingI, MacromolecularComplexation, RibosomeAssembly]>
- <Metabolism produces_inputs_for=[ProteinModification], ProteinModification consumes_outputs_of=[Translation, ProteinProcessingI, ProteinProcessingII, ProteinFolding]>
- ... `33` more omitted

Cyclic ordering:
- Translation hard_before tRNAAminoacylation and tRNAAminoacylation hard_before Translation
- tRNAAminoacylation hard_before Translation and Translation hard_before tRNAAminoacylation

Row-level validation failures:
- ChromosomeCondensation: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- ChromosomeSegregation: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- Cytokinesis: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- DNADamage: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- DNARepair: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- DNASupercoiling: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- FtsZPolymerization: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; unit_conversion_chain.steps[0].anchor: lines must match start-end; unit_conversion_chain.steps[2].anchor: lines must match start-end; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- HostInteraction: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- MacromolecularComplexation: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list
- ProteinActivation: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- ProteinDecay: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- ProteinFolding: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- ProteinModification: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; unit_conversion_chain.steps[0].anchor: lines must match start-end; unit_conversion_chain.steps[2].anchor: lines must match start-end; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- ProteinProcessingI: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD
- ProteinProcessingII: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- ProteinTranslocation: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list
- RNADecay: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list
- RNAModification: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- RNAProcessing: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- Replication: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- ReplicationInitiation: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- RibosomeAssembly: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- TerminalOrganelleAssembly: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; compartment_routing[0]: mismatch=True does not match compartments 'membrane'/'membrane'; compartment_routing[1]: mismatch=True does not match compartments 'cytosol'/'cytosol'; compartment_routing[2]: mismatch=True does not match compartments 'cytosol'/'cytosol'; compartment_routing[3]: mismatch=True does not match compartments 'membrane'/'membrane'; compartment_routing[4]: mismatch=True does not match compartments 'cytosol'/'cytosol'; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- Transcription: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- TranscriptionalRegulation: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD; provenance.last_audited missing or not YYYY-MM-DD; provenance.matlab_files_referenced: expected non-empty list; provenance.oc_files_referenced: expected non-empty list
- Translation: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD
- tRNAAminoacylation: missing top-level keys: schema_date; schema_date missing or not YYYY-MM-DD

## Known Deviations Summary

- ChromosomeCondensation: OC is Karr-light v1 aggregate condensation, not the full per-position chromosome topology.; OC merges request emission into next_update instead of a standalone request-calculator method.; OC uses `_allocated_or_state`, so zero-grant ticks can still read the global substrate pool.; Karr initializeState performs a 20-step warm-up loop with ATP/H2O set to Inf; OC seeds from fixture and trace defaults instead.
- ChromosomeSegregation: OC exposes continuous segregation_progress and daughter_pole_positions to support downstream chassis logic; the Karr source description is boolean and event-gated.; OC adds optional include_topoiv_gate and gtp_cost_override parameters; the Karr extract only exposes gtpCost and the four core segregation proteins.
- Cytokinesis: OC embeds request emission in `KarrCytokinesisProcess.next_update` and bases the water request on ring geometry / hydrolysis opportunity, while MATLAB's `calcResourceRequirements_Current` requests water from the current FtsZ-GTP polymer count.; The OC port preserves a zero-valued GTP request key for compatibility, but Cytokinesis.m only requests water.; The MATLAB class has a separate lifecycle resource method; the OC port does not expose a separate lifecycle calculator.
- DNADamage: The current OC port is lesion-creation only; it does not implement the full reactionSmallMoleculeStoichiometryMatrix / reactionDNAStoichiometryMatrix / reactionRadiationStoichiometryMatrix chemistry described in the extract.; The current OC port bypasses allocator mediation entirely and reads `states["substrates"]` directly.; Repair chemistry, lesion-specific arrays, and any downstream DNARepair coupling are deferred to a later port.; Trace-derived kind rates are optional; when the trace file is unavailable, the OC port falls back to configured per-kind rates.
- DNARepair: Karr executes six randomly ordered repair subfunctions; OC collapses the process to one aggregated pathway-level update.; OC models only ATP/dNTP repair demand plus the conditional AMET -> AHCYS + H restriction/modification side effect.; Karr ligation/polymerization products such as AMP, PPI, and NMN are visible in the fixture chemistry but are not emitted by the current OC port.; The raw MATLAB source file was not present in this checkout, so MATLAB-side evidence is anchored to the DNARepair extract and the generic allocation docs rather than a direct .m read.
- DNASupercoiling: OC merges the request calculation and per-tick update into one next_update controller, while MATLAB splits calcResourceRequirements_Current and evolveState.; OC makes dt explicit in the request controller and sparse chromosome update, while the MATLAB current-request body relies on the simulation tick / fixture step size implicitly.; OC does not expose the MATLAB RNAPolymerase fold-change matrix helper; it surfaces only the supercoiled chromosome state.; OC uses a sparse chromosome-store/replay-hint implementation rather than the MATLAB doubleStrandedRegions / monomerBoundSites / complexBoundSites control surface.
- FtsZPolymerization: The raw MATLAB `.m` file was not present in this checkout; MATLAB anchors therefore use the checked-in extract doc rather than a direct source-file read.; OC emits the GTP request directly from `next_update` instead of a separate request-calculator module.; OC reads allocated GTP from `substrates_allocated[self.name]` but still keeps a direct substrate-store fallback path for the no-allocation case.
- HostInteraction: OC replaces Karr's boolean host cascade with a Karr-light aggregate adhesion model (`host_adhesion_strength` and `host_attached`).; OC reads `cell.terminal_organelle_count` plus `protein.counts`; Karr reads its own `host` state and `enzymes` array.; No substrate stoichiometry or allocator request surface exists in the current OC port because HostInteraction's fixture has no substrate WIDs.
- MacromolecularComplexation: OC's _per_cluster_mc samples a Poisson multiplicity and can form multiple complexes per iteration; Karr forms exactly one copy per Monte Carlo iteration.; OC adds a cluster-1 fallback from _closed_form_bounds into _per_cluster_mc when the deterministic bound appears to overconsume; that guard is not present in the preserved Karr excerpt.
- Metabolism: A1: compare the request formula here against `Simulation.evolveState` allocation and `karr_allocation_step.py:232-280`.; A2: compare ordering constraints against `Simulation.evolveState`'s randperm constraint set.; A3: the current OC LP bounds source is `internal_pool`, not Karr's allocation-derived source.; A3b: consumption clipping is grep-able in `opencell/m1/karr_metabolism_writeback.py`.; A4: shared-pool projection merges compartments in `project_to_flat_per_wid`.
- ProteinActivation: none
- ProteinDecay: OC is ProteinDecayLightProcess, a complex-decay-only subset of MATLAB ProteinDecay; misfold/refold, aborted-polypeptide decay, and full monomer decay are not implemented.; The OC process never reads `substrates_allocated`; it reads `states['substrates']` directly and emits direct substrate deltas in `next_update`.; The OC allocator alias maps `protein_decay_light` to `karr_protein_decay_light`, so the request key differs from the process slug.; The OC port flattens Karr's compartmented ProteinDecay surfaces into a per-WID substrate projection.
- ProteinFolding: The current OC request helper is shared across protein maturation and only explicitly surfaces ATP, FE2, MG, and ZN for ProteinFolding; the Karr prosthetic-ion surface is broader (including K/MN/NA/Fe3), and those are not request-emitted by the shared helper.; The current OC runtime omits the fixture channels unfoldedComplexs and foldedComplexs, even though the Karr fixture exposes them.; The raw MATLAB ProteinFolding.m body was absent from this checkout, so the MATLAB-side method anchors are reconstructed from the process extract and downstream audit notes.
- ProteinModification: OC has a replay-only trace_hint.unmodifiedMonomers_next short-circuit that bypasses the biology sampler when present.; OC reads substrates from substrates_allocated[self.name] rather than the global substrates store; this is equivalent under scheduler control but different plumbing.; OC retains a legacy _n_completed scratch vector and a max_stochastic_iterations cap for replay/test compatibility; MATLAB does not expose those implementation details.
- ProteinProcessingI: OC uses a strict-zero allocator contract: `next_update` reads `substrates_allocated[self.name]` and never falls back to `substrates`.; OC samples events with `multivariate_hypergeometric` (or a fallback choice loop) instead of MATLAB's `stochasticRound` + `mnrnd` + `min` clipping.; MATLAB keeps the request and state-update logic inside `ProteinProcessingI.m`; OC splits them between `RequestCalculatorProteinPathway` and `KarrProteinProcessingIProcess`.; No standalone `calcFluxBounds` implementation exists for this process in the current OC port.
- ProteinProcessingII: OC reads from substrates_allocated[self.name] with a strict-zero guard instead of falling back to the global substrates pool.; OC request calculation is availability-based (_request_from_available) rather than the exact MATLAB min(enzyme-limit, monomer-count) request formula.; The nominal diacylglycerolCys chemistry product named in the MATLAB comment is not materialized by either implementation.; ProteinProcessingII has no calcFluxBounds analogue in the current OC port.
- ProteinTranslocation: OC batches translocation per species and phase, while Karr randomizes individual monomer copies in one mixed randperm and stops on the first infeasible copy.; OC reads allocator-granted ATP/GTP/H2O from `substrates_allocated` and raw enzyme counts; Karr uses current substrate pools and rate-scaled translocase/SRP capacities.; OC request magnitude uses a current-pool floor (`max(need, current_pool)`), which can over-request relative to pure need.; OC represents moved proteins with `protein.location` plus `protein.unprocessed_counts` deltas instead of Karr's compartment-resolved monomer matrix.; OC excludes `MG_191_MONOMER` and `MG_192_MONOMER` during fixture loading, which makes terminal-organelle handling a load-time omission rather than a compartment remap.
- RNADecay: OC folds request emission into next_update instead of exposing a dedicated RequestCalculator class.; OC adds a trace-hint short-circuit for replay harnesses that is not part of the Karr extract.; OC includes fallback initialization and half-life guards that are absent from the local RNADecay extract.; The raw MATLAB source file is absent in this checkout, so MATLAB anchors use checked-in extracts rather than the original .m body.
- RNAModification: OC splits enzyme inputs into protein.counts and complex.counts; MATLAB uses one enzyme vector.; OC request emission is handled by shared RequestCalculatorRNAPathway instead of a process-local request method.; OC next_update uses an explicit max_stochastic_iterations cap and zero-fallback guards; MATLAB uses an unbounded while true loop.
- RNAProcessing: OC RequestCalculatorRNAPathway is shared with RNAModification and requests the current available substrate pool when active; it does not reproduce the MATLAB enzyme/unprocessedRNA cap literally.; OC next_update consumes from substrates_allocated[self.name], while MATLAB evolves from the local substrates state.; OC omits the MATLAB intergenicRNAs state/output entirely; the replay port only updates substrates and rna.counts.; OC prefixes colliding processed RNA IDs with processed:: to keep mature and nascent pools from cancelling in the shared rna.counts store.; OC can source enzyme counts from protein/complex stores when an explicit enzymes store is absent; MATLAB reads this.enzymes directly.
- Replication: OC request logic is embedded in KarrReplicationProcess.next_update instead of a standalone request-calculator class.; The current OC port is a light-bulk fork-progress replay; SSB binding/release, Okazaki geometry, and RNAP collision dwell/pause remain deferred.; The raw MATLAB Replication.m file was not present in this worktree, so the row uses the checked-in Karr extract docs and allocation notes as the source proxy.; No Replication-specific calcFluxBounds helper exists in the current OC repository state.
- ReplicationInitiation: OC emits and consumes allocator state inside next_update instead of a dedicated request-calculator class.; OC initialization is fixture/bootstrap based and does not reproduce MATLAB's final-conditions or theory steady-state solve.; MATLAB's calcFluxBounds slot is absent for this process, so the schema-required row entry is marked not_implemented.
- RibosomeAssembly: OC splits request generation into RequestCalculatorRibAsm while MATLAB keeps the allocator request on the process class.; MATLAB calcResourceRequirements_Current hardcodes getGtpPerComplex(2) in both particle terms; OC RequestCalculatorRibAsm computes hydrolysis demand from each particle's actual n_gtpases_per_particle.; OC collapses initializeState into construction-time fixture loading instead of exposing a runtime initialization callback.; OC returns early when allocated GTP or H2O is non-positive, while Karr only returns early when GTP is zero.
- TerminalOrganelleAssembly: The OC port is Karr-light: it tracks coarse assembled counters in `cell.terminal_organelle_count` and `cell.terminal_organelle_components_assembled` instead of MATLAB's full in-place substrate matrix loop.; The OC port adds a trace-hint override plus a compartment-transfer fallback for `substrates`; MATLAB only performs the localization loop.; The OC port bypasses allocator mediation entirely and never emits a dedicated request calculator for this process.
- Transcription: Current OC allocator requests only ATP/CTP/GTP/UTP; MATLAB calcResourceRequirements_Current also requests water.; Current OC evolveState is a mechanism-based transcription wrapper, not the MATLAB RNAP state-machine implementation.; Legacy KarrTranscriptionProcess bypasses allocator mediation and writes direct substrate deltas when used without the allocator-budget path.; OC bootstrap is split across constructor fixture loads, ports_schema defaults, and composite wiring rather than a single initializeState method.
- TranscriptionalRegulation: The raw MATLAB .m file is absent from this checkout; source anchors use the checked-in extract/design docs instead.; OC does not implement a request-calculator surface for this process; it reads protein.counts / complex.counts directly.; OC initializes tf_binding from the first tick rather than performing Karr's documented t=0 pre-binding sweep.
- Translation: MATLAB requests GTP/H2O, while current OC requests the 20 standard amino-acid pools through RequestCalculatorTranslation.; Current OC still reads GTP/H2O directly from states['substrates'] inside the biology helper, so the runtime is mixed rather than pure allocation.; MATLAB's substrate vocabulary includes FMET; current OC exposes only the 20 standard amino acids and uses MET as the initiator-residue surrogate.; MATLAB writes GDP/PI/H as substrate byproducts; current OC writes protein.unprocessed_counts instead and does not emit those metabolites.; MATLAB's full charged-tRNA/polymerize bookkeeping is collapsed in OC into a fixture-backed synthesis-rate surrogate plus stochastic rounding.
- tRNAAminoacylation: OC request logic is split into RequestCalculatorTRNA and uses an availability-based approximation; ATP scales as avail * 25.0 instead of matching MATLAB's exact min(...) expression.; OC _compute_rna_fluxes adds a max_stochastic_iterations guard and rounds reaction events / substrate deltas with np.rint; MATLAB uses an unbounded while-loop and direct matrix writeback.; OC retains legacy vector-to-WID fallbacks for RNA state inputs; MATLAB reads structured process state directly.; MATLAB initializeState explicitly reseeds the free/aminoacylated RNA split; the OC port relies on fixture/chassis setup instead of a process-local initializer.

## Process Roster

Canonical Karr roster (`28`): ChromosomeCondensation, ChromosomeSegregation, Cytokinesis, DNADamage, DNARepair, DNASupercoiling, FtsZPolymerization, HostInteraction, MacromolecularComplexation, Metabolism, ProteinActivation, ProteinDecay, ProteinFolding, ProteinModification, ProteinProcessingI, ProteinProcessingII, ProteinTranslocation, RNADecay, RNAModification, RNAProcessing, Replication, ReplicationInitiation, RibosomeAssembly, TerminalOrganelleAssembly, Transcription, TranscriptionalRegulation, Translation, tRNAAminoacylation.
DB roster (`28`): ChromosomeCondensation, ChromosomeSegregation, Cytokinesis, DNADamage, DNARepair, DNASupercoiling, FtsZPolymerization, HostInteraction, MacromolecularComplexation, Metabolism, ProteinActivation, ProteinDecay, ProteinFolding, ProteinModification, ProteinProcessingI, ProteinProcessingII, ProteinTranslocation, RNADecay, RNAModification, RNAProcessing, Replication, ReplicationInitiation, RibosomeAssembly, TerminalOrganelleAssembly, Transcription, TranscriptionalRegulation, Translation, tRNAAminoacylation.
Difference: none; the DB roster matches the canonical Karr roster exactly.

## Recommended Cleanup Actions

- **P0**: fix every row-level validation failure before anyone treats the DB as authoritative. That includes the missing `schema_date` field, the incomplete provenance blocks, the malformed unit-conversion anchors, and the `TerminalOrganelleAssembly` compartment-routing mismatch booleans.
- **P1**: reconcile the reciprocal dependency mismatches row by row so every `produces_inputs_for` edge is mirrored by the partner row's `consumes_outputs_of` list, and confirm the two cyclic ordering edges between `Translation` and `tRNAAminoacylation` are intentional.
- **P2**: normalize the schema-version/date story and triage deviations into an explicit keep-fix-drop queue, especially any rows that still carry broad allocator or LP-bound caveats.

## Connection to L2.4 Work (was "L1c" prior to 2026-07-02)

This wiring DB is the machine-readable substrate that the L2.4 gate can read instead of re-deriving wiring from prose. It consolidates allocator formulas, ordering constraints, LP-bound provenance, compartment-merge flags, and cross-process edges into a row-per-process contract. That gives the L2.4 gate a stable place to compare chassis wiring against the canonical Karr model before lower-rung greens are promoted. In the `2026-06-29 | opencell | l1c-skipped-lower-rung-greens-misread` decision, that was the missing piece: L1a/L2.1/L2.2 could not see the A1-A4 integration bugs, but this DB can surface them directly. (The decision slug retains "l1c" for historical accuracy; the gate is now L2.4 per `2026-07-02 | opencell | ladder-rename-l1c-to-l2_4`.)

