# All-29 Chassis Key Status — 2026-05-27

Coverage matrix for `build_karr_chassis_v6` expected keys:
- 28 Karr biological processes
- 1 OpenCell shim (`karr_cell_cycle_coordinator`)

Baseline source for rows 1-28: `docs/phase_e/PROCESS_STATUS_ALL_28.md`.

## Master matrix — 29 chassis keys

| Row | Chassis key | Status | Evidence |
|---:|---|---|---|
| 1 | `karr_replication` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 2 | `karr_replication_initiation` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 3 | `karr_dna_supercoiling` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 4 | `karr_chromosome_condensation` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 5 | `karr_chromosome_segregation` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 6 | `karr_dna_damage` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 7 | `karr_dna_repair` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 8 | `karr_ftsz_polymerization` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 9 | `karr_cytokinesis` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 10 | `karr_terminal_organelle_assembly` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 11 | `karr_cell_cycle_coordinator` | ✅ present (shim) | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 12 | `karr_host_interaction` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 13 | `karr_rna_decay` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 14 | `karr_rna_processing` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 15 | `karr_rna_modification` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 16 | `karr_trna_aminoacylation` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 17 | `karr_ribosome_assembly` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 18 | `karr_protein_processing_i` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 19 | `karr_protein_processing_ii` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 20 | `karr_protein_folding` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 21 | `karr_protein_modification` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 22 | `karr_protein_translocation` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 23 | `karr_protein_activation` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 24 | `karr_protein_decay_light` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 25 | `karr_macromolecular_complexation` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 26 | `karr_metabolism` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 27 | `karr_transcription` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 28 | `karr_translation` | ✅ present | In `CHASSIS_V6_EXPECTED_PROCESS_KEYS` + v6 integration tests |
| 29 | `karr_transcriptional_regulation` | 🟢 L1-green (was ⚫ MISSING) | Real process module + real `next_update` + dedicated vivarium tests + included in v6 key tuple |

## Gap notes / trace bytes evidence

- Row 29 closure evidence:
  - Fixture present and loadable: `data/karr_fixtures/per_process/TranscriptionalRegulation_flat.mat` (`374,502` bytes).
  - Canonical Karr native 100-tick trace present: `E:\opencell\data\m1_sources\karr_native\per_process_traces\TranscriptionalRegulation_100ticks.mat` (`258,112` bytes).
  - Process test coverage: `tests/vivarium/test_karr_transcriptional_regulation.py` (includes fold-change path and TF-presence regulation path).
