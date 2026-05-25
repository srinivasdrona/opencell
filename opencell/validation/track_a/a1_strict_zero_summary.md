# Track-A1 Strict-Zero Rollout Summary

## Site-by-site changes
| Site | Contract change | Diff lines (+/-) | Strict-zero test |
| --- | --- | --- | --- |
| `opencell/vivarium/karr_chromosome_condensation.py` | `_allocated_or_state`: removed global fallback, return nonnegative allocation only | `+1/-3` | `tests/unit/test_karr_chromosome_condensation_strict_zero.py::test_karr_chromosome_condensation_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_chromosome_segregation.py` | `_allocated_or_state`: removed global fallback, return nonnegative allocation only | `+1/-3` | `tests/unit/test_karr_chromosome_segregation_strict_zero.py::test_karr_chromosome_segregation_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_cytokinesis.py` | `_allocated_or_state`: removed global fallback, return nonnegative allocation only | `+1/-3` | `tests/unit/test_karr_cytokinesis_strict_zero.py::test_karr_cytokinesis_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_dna_repair.py` | `_allocated_or_state`: removed global fallback, return nonnegative allocation only | `+1/-3` | `tests/unit/test_karr_dna_repair_strict_zero.py::test_karr_dna_repair_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_dna_supercoiling.py` | `_allocated_or_state`: removed global fallback, return nonnegative allocation only | `+1/-3` | `tests/unit/test_karr_dna_supercoiling_strict_zero.py::test_karr_dna_supercoiling_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_replication.py` | `_allocated_or_state`: removed global fallback, return allocated-only nonnegative int | `+1/-3` | `tests/unit/test_karr_replication_strict_zero.py::test_karr_replication_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_replication_initiation.py` | `_allocated_or_state`: removed global fallback, return nonnegative allocation only | `+1/-3` | `tests/unit/test_karr_replication_initiation_strict_zero.py::test_karr_replication_initiation_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_protein_folding.py` | `_allocated_or_free`: removed global fallback, return nonnegative allocation only | `+1/-3` | `tests/unit/test_karr_protein_folding_strict_zero.py::test_karr_protein_folding_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_protein_translocation.py` | `_available_atp`: removed fallback to `states["substrates"][ATP]` | `+1/-3` | `tests/unit/test_karr_protein_translocation_strict_zero.py::test_karr_protein_translocation_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_protein_modification.py` | inline ternary replaced with `max(0.0, allocated)` | `+1/-4` | `tests/unit/test_karr_protein_modification_strict_zero.py::test_karr_protein_modification_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_protein_processing_i.py` | inline ternary replaced with `max(0.0, allocated)` | `+1/-4` | `tests/unit/test_karr_protein_processing_i_strict_zero.py::test_karr_protein_processing_i_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_protein_processing_ii.py` | inline ternary replaced with `max(0.0, allocated)` | `+1/-4` | `tests/unit/test_karr_protein_processing_ii_strict_zero.py::test_karr_protein_processing_ii_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_rna_modification.py` | inline ternary replaced with `max(0.0, allocated)` | `+1/-4` | `tests/unit/test_karr_rna_modification_strict_zero.py::test_karr_rna_modification_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_rna_processing.py` | inline ternary replaced with `max(0.0, allocated)` | `+1/-4` | `tests/unit/test_karr_rna_processing_strict_zero.py::test_karr_rna_processing_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_trna_aminoacylation.py` | inline ternary replaced with `max(0.0, allocated)` | `+1/-4` | `tests/unit/test_karr_trna_aminoacylation_strict_zero.py::test_karr_trna_aminoacylation_strict_zero_no_global_fallback` |
| `opencell/vivarium/karr_ftsz_polymerization.py` | behavior unchanged; added canonical comment on presence-based strict-zero pattern | `+1/-0` | existing: `tests/vivarium/test_karr_ftsz_polymerization.py::test_allocation_contract_zero_alloc_no_gtp_consumption` |

## Totals
- Total LOC added: `616`
- Total LOC removed: `51`

## Skipped sites
- FtsZ fallback logic was already presence-based strict-zero compliant; no behavior change applied.
