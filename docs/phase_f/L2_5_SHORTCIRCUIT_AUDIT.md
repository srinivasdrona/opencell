# L2.1/L2.2 hidden short-circuits — comprehensive audit (Day-35, 2026-06-22)

**Discovered 12 processes with hint-driven short-circuits**, where L2.1/L2.2 trace_hint short-circuits bypass the underlying biology computation. L2.1 + L2.2 passed because of these shortcuts; honest L2.5 mode is the first gate that exercises the real biology.

## Severity classes

- **FULL_BYPASS**: `return self._next_update_from_trace_hint(...)` — entire `next_update` returns hint-derived values, biology never runs
- **CHEMISTRY_BYPASS**: substrate deltas read verbatim from hint; biology computation skipped
- **GATED_BIOLOGY**: biology runs but its outputs (e.g. `n_bound`) are gated on hint values; without hint, biology is silently disabled
- **CHANNEL_OVERLAY**: hint values overwrite biology-computed values for selected channels
- **DUAL_PATH**: explicit `use_trace_hint` flag selects between hint and biology paths
- **REPLAY_GUARD**: monkey-patched termination/release timing tied to L2.1 replay schedule

## The catalog

| # | Process | File | Lines | Class | What gets bypassed |
|---|---|---|---|---|---|
| 1 | **Replication** | karr_replication.py | 891-894 | FULL_BYPASS | Entire `next_update` if `boundEnzymes_next` / `enzymes_next` / `chromosome_next` in hint |
| 2 | **ReplicationInitiation** | karr_replication_initiation.py | 290-293 | FULL_BYPASS | Entire `next_update` if `boundEnzymes_next` / `enzymes_next` in hint |
| 3 | **Metabolism** | karr_metabolism.py | 340-354 | CHEMISTRY_BYPASS | Entire FBA solver bypassed; `return {"substrates": hint_delta}` if hint present |
| 4 | **RNADecay** | karr_rna_decay.py | 262-296, 304-314 | CHEMISTRY_BYPASS | Poisson decay sampler skipped; explicit comment "no-op for L2.1 harness" |
| 5 | **ProteinDecayLight** | karr_protein_decay_light.py | 450-460 | CHEMISTRY_BYPASS | "Mirrors karr_rna_decay short-circuit" — stochastic decay sampler skipped |
| 6 | **Transcription** | karr_transcription.py | 300-310, 659-665 | CHEMISTRY_BYPASS | NTP consumption from hint; "avoids polymerase-slot simulation drift" |
| 7 | **TerminalOrganelleAssembly** | karr_terminal_organelle_assembly.py | 334-353, 424-428 | CHEMISTRY_BYPASS | Substrate deltas from hint preferred over biology compartment-transfer fallback |
| 8 | **ChromosomeCondensation** | karr_chromosome_condensation.py | 338-373, 380-381 | GATED_BIOLOGY | `n_bound` derived from `bound_next_hint`; if hint absent and biology returns 0, chemistry skipped (Day-35 found bug, partial port at `81600c1`/`7662d5b`) |
| 9 | **DNASupercoiling** | karr_dna_supercoiling.py | 405-413, 539-541, 592-598 | CHANNEL_OVERLAY | `substrates_next_effective` overwritten by hint; `linkingNumbers` from hint; replay_mode flag drives multiple paths |
| 10 | **FtsZPolymerization** | karr_ftsz_polymerization.py | 228-234 | CHEMISTRY_BYPASS | Substrate delta computed from hint transition; biology path is fallback |
| 11 | **ProteinModification** | karr_protein_modification.py | 255-265, 298-310 | GATED_BIOLOGY | `protein_fluxes_from_trace_hint` preferred; biology sampler only fires if hint missing |
| 12 | **TranscriptionalRegulation** | karr_transcriptional_regulation.py | 427-460 | CHANNEL_OVERLAY | `bound_delta` and `enzyme_delta` computed from hint deltas |
| 13 | **Translation** | karr_translation.py | 307-539 (guard) | REPLAY_GUARD | Monkey-patched `_l21_trace_hint_active` flag; termination tied to `_L21_REPLAY_TERMINATION_SCHEDULE` |
| 14 | **TranslationV3** | karr_translation_v3.py | 437-580 | DUAL_PATH | Explicit `use_trace_hint` flag selects between `_enzyme_channel_deltas_from_trace_hint` and `_termination_count_from_replay_schedule` |

## What's actually clean (no trace_hint usage)

These 17 process files don't reference trace_hint at all (categorically clean):

- karr_allocation_step, karr_cell_cycle_coordinator, karr_chromosome_segregation,
  karr_composite, karr_cytokinesis, karr_dna_damage, karr_dna_repair,
  karr_host_interaction, karr_macromolecular_complexation, karr_observability_step,
  karr_protein_activation, karr_protein_folding, karr_protein_processing_i,
  karr_protein_processing_ii, karr_protein_translocation, karr_request_calculators,
  karr_ribosome_assembly, karr_rna_modification, karr_rna_processing,
  karr_transcription_v2, karr_transcription_v3, karr_translation_v2,
  karr_trna_aminoacylation

Importantly: **ChromosomeSegregation has NO trace_hint usage**, which matches the Day-35 Seg audit (commit `678928c`) that found all Seg pair failures are blamed on the stochastic partner, not Seg itself.

## L2.1/L2.2 implications

For each of the 12-14 processes with short-circuits, what L2.1 + L2.2 actually validated:

- **What was tested**: substrate deltas exactly match the trace (because they ARE the trace under hint mode)
- **What was NOT tested**: whether the biology sampler computes the right substrate deltas from internal state

This is **systematic oracle leakage**. The L-ladder design intended L2.1 to validate per-tick biology; the implementation short-circuits the biology and validates "harness can apply pre-recorded deltas correctly."

## Day-35 finding context

This is consistent with the Day-35 RNADecay probe (commit `231e2da`):
- L2.5 isolated counterfactual replay (no hints): RNADecay decays 124 AMP at tick 0
- Karr trace says: 20 AMP at tick 0
- OC over-decays by 6×

The same magnitude of drift likely exists in most of the 12 short-circuit processes.

## Next-step recommendation

Two parallel tracks:

1. **Update L2.1 acceptance rubric** to require honest-mode replay (no trace_hint short-circuits). This is the L2.1 promise the project was supposed to make.
2. **Honest-mode biology audit per process** — for each of the 12, run isolated no-hints replay (using harness via `disable_trace_hints=True`) and capture the per-tick drift magnitude.

Both are multi-day efforts. The catalog above is the inventory; the work is removing the short-circuits one by one and validating the biology underneath.
