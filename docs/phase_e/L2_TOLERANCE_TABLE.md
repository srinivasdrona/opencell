# L2 Tolerance Table

Generated: 2026-06-01 12:56:55 UTC

## 1. Methodology

- Inputs: `/mnt/e/opencell/artifacts/ensemble_wave2_post_l1c_20260528_123756/seed_*/process_traces/*.csv` (read-only), using filename intersection across discovered seeds.
- Canonical process set: 28 `karr_*` names discovered from `tests/vivarium/test_karr_*_l2_replay.py`.
- Sample ticks: `(1000, 3000, 5000)`.
- Per-observable at each sampled tick: `mu=mean(across seeds)`, `sigma=std(across seeds)`, `rtol=3*sigma/max(abs(mu),1)`, `atol=3*sigma`.
- Per-observable tolerance: max across sampled ticks (conservative mid-cycle band).
- Per-process tolerance: median across observables for `rtol` and `atol` (conservative-but-not-pessimistic against single-observable outliers).
- Energy observables (`ATP,GTP,AMP,GMP,ADP,GDP,H+,H2O,Pi,PPi`) are recorded explicitly; if they widen the roll-up median, they are excluded from roll-up median only.

## 2. Per-process table

| process_name | n_seeds | n_observables | rtol_median | atol_median | rtol_max_obs | atol_max_obs | worst_observable | notes |
|---|---:|---:|---:|---:|---:|---:|---|---|
| karr_dna_repair | 4 | 6 | 1.78864 | 1.78864 | 1.8 | 4.5 | nhej_like |  |
| karr_transcription | 4 | 527 | 6.56223e-06 | 6.56223e-06 | 0.000721929 | 0.000721929 | MG471 | energy-observables=ATP,GTP |
| karr_chromosome_condensation | 4 | 1 | 0 | 0 | 0 | 0 | condensation_level |  |
| karr_dna_supercoiling | 4 | 2 | 0 | 0 | 0 | 0 | ATP | energy-observables=ATP,H2O |
| karr_ftsz_polymerization | 4 | 3 | 0 | 0 | 4.12311 | 6.18466 | ftsz_ring_count | energy-observables=GTP |
| karr_metabolism | 4 | 238 | 0 | 0 | 3.41061e-13 | 3.41061e-13 | PYR | energy-observables=ADP,AMP,ATP,GDP,GMP,GTP,H2O |
| karr_protein_decay | 4 | 302 | 0 | 0 | 0 | 0 | DNA_POLYMERASE_CORE | trace-alias=karr_protein_decay_light |
| karr_protein_folding | 4 | 243 | 0 | 0 | 0 | 0 | ATP | energy-observables=ATP |
| karr_protein_modification | 4 | 14 | 0 | 0 | 0 | 0 | ADP | energy-observables=ADP,ATP |
| karr_protein_processing_i | 4 | 101 | 0 | 0 | 0 | 0 | FOR | energy-observables=H2O |
| karr_protein_processing_ii | 4 | 96 | 0 | 0 | 0 | 0 | MG_005_MONOMER |  |
| karr_protein_translocation | 4 | 7 | 0 | 0 | 0 | 0 | ADP | energy-observables=ADP,ATP,H2O |
| karr_rna_decay | 4 | 1 | 0 | 0 | 0 | 0 | H2O | energy-observables=H2O |
| karr_rna_modification | 4 | 6 | 0 | 0 | 0 | 0 | AHCYS |  |
| karr_transcriptional_regulation | 4 | 3 | 0 | 0 | 0 | 0 | TU_008 |  |
| karr_translation | 4 | 118 | 0 | 0 | 0 | 0 | ALA |  |
| karr_trna_aminoacylation | 4 | 1 | 0 | 0 | 0 | 0 | __noop__ |  |
| karr_chromosome_segregation | 4 | 0 | NA | NA | NA | NA | NA | no-ensemble-data |
| karr_cytokinesis | 4 | 0 | NA | NA | NA | NA | NA | no-ensemble-data |
| karr_dna_damage | 4 | 0 | NA | NA | NA | NA | NA | no-ensemble-data |
| karr_host_interaction | 4 | 0 | NA | NA | NA | NA | NA | no-ensemble-data |
| karr_macromolecular_complexation | 4 | 0 | NA | NA | NA | NA | NA | no-ensemble-data |
| karr_protein_activation | 4 | 0 | NA | NA | NA | NA | NA | no-ensemble-data |
| karr_replication | 4 | 0 | NA | NA | NA | NA | NA | no-ensemble-data |
| karr_replication_initiation | 4 | 0 | NA | NA | NA | NA | NA | no-ensemble-data |
| karr_ribosome_assembly | 4 | 0 | NA | NA | NA | NA | NA | no-ensemble-data |
| karr_rna_processing | 4 | 0 | NA | NA | NA | NA | NA | no-ensemble-data |
| karr_terminal_organelle_assembly | 4 | 0 | NA | NA | NA | NA | NA | no-ensemble-data |

### Energy-observable detail

| process_name | observable | rtol | atol | included_in_rollup_median |
|---|---|---:|---:|---|
| karr_dna_supercoiling | ATP | 0 | 0 | yes |
| karr_dna_supercoiling | H2O | 0 | 0 | yes |
| karr_ftsz_polymerization | GTP | 0 | 0 | yes |
| karr_metabolism | ADP | 0 | 0 | yes |
| karr_metabolism | AMP | 2.78747e-13 | 2.78747e-13 | yes |
| karr_metabolism | ATP | 2.95367e-13 | 2.95367e-13 | yes |
| karr_metabolism | GDP | 0 | 0 | yes |
| karr_metabolism | GMP | 0 | 0 | yes |
| karr_metabolism | GTP | 0 | 0 | yes |
| karr_metabolism | H2O | 7.38418e-14 | 7.38418e-14 | yes |
| karr_protein_folding | ATP | 0 | 0 | yes |
| karr_protein_modification | ADP | 0 | 0 | yes |
| karr_protein_modification | ATP | 0 | 0 | yes |
| karr_protein_processing_i | H2O | 0 | 0 | yes |
| karr_protein_translocation | ADP | 0 | 0 | yes |
| karr_protein_translocation | ATP | 0 | 0 | yes |
| karr_protein_translocation | H2O | 0 | 0 | yes |
| karr_rna_decay | H2O | 0 | 0 | yes |
| karr_transcription | ATP | 0 | 0 | yes |
| karr_transcription | GTP | 0 | 0 | yes |

## 3. Coverage gaps

- Canonical processes discovered: 28; with ensemble data: 17; no ensemble data: 11.
- `karr_chromosome_segregation`: `no-ensemble-data` (TODO: add to ensemble wave output or use fallback default tolerance).
- `karr_cytokinesis`: `no-ensemble-data` (TODO: add to ensemble wave output or use fallback default tolerance).
- `karr_dna_damage`: `no-ensemble-data` (TODO: add to ensemble wave output or use fallback default tolerance).
- `karr_host_interaction`: `no-ensemble-data` (TODO: add to ensemble wave output or use fallback default tolerance).
- `karr_macromolecular_complexation`: `no-ensemble-data` (TODO: add to ensemble wave output or use fallback default tolerance).
- `karr_protein_activation`: `no-ensemble-data` (TODO: add to ensemble wave output or use fallback default tolerance).
- `karr_replication`: `no-ensemble-data` (TODO: add to ensemble wave output or use fallback default tolerance).
- `karr_replication_initiation`: `no-ensemble-data` (TODO: add to ensemble wave output or use fallback default tolerance).
- `karr_ribosome_assembly`: `no-ensemble-data` (TODO: add to ensemble wave output or use fallback default tolerance).
- `karr_rna_processing`: `no-ensemble-data` (TODO: add to ensemble wave output or use fallback default tolerance).
- `karr_terminal_organelle_assembly`: `no-ensemble-data` (TODO: add to ensemble wave output or use fallback default tolerance).
