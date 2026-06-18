# L2.5 Pair Tracker — actual pass/fail status per shared-pool pair

**Generated:** 2026-06-18 (Day 32 EOD)
**Source of truth for L2.5 status. PROCESS_STATUS_ALL_29.md L2.5 column points here.**
**Machine-loadable companion:** [`data/schemas/l25_pair_list.toml`](../../data/schemas/l25_pair_list.toml) (pair derivation, no status field)
**Catalog reference:** [`l2_2_design_a/PROCESS_CATALOG.yaml`](./l2_2_design_a/PROCESS_CATALOG.yaml) `l2_5_gate:` section

---

## Scope (from `l25_pair_list.toml`, schema_version 1.0)

| Bucket | Count | Notes |
|---|---:|---|
| **Total pairs computed** (28 choose 2) | **378** | |
| Disjoint (no shared WIDs, OUT OF L2.5 SCOPE) | 122 | No allocator contention possible; not tested |
| **L2.5 honest-required (shared-pool)** | **256** | Per-side oracle: bit-identity (det) or distributional (stoch) |
| ↳ Stochastic ↔ Stochastic (SS) | 211 | Both sides distributional |
| ↳ Deterministic ↔ Stochastic (DS) | 43 | Det side bit-identity, stoch side distributional |
| ↳ Deterministic ↔ Deterministic (DD) | 2 | Both sides bit-identity (strictest) |

## Scoreboard (Day-32 EOD)

| Status | Count | Source |
|---|---:|---|
| 🟢 **PASS** | **10** | 1 SS + 7 DS + 2 DD |
| 🔴 FAIL | 28 | 28 DS (failure-class breakdown below) |
| ⚪ SKIPPED | 8 | 8 DS (no-op trace / sparse-event; need event-window) |
| ⬜ UNTESTED | 210 | 210 SS (only Translation+RNAProcessing wired) |
| ➖ OUT OF SCOPE | 122 | Disjoint (no shared WIDs) |
| — | — | — |
| **TOTAL** | **378** | |

---

## 🟢 PASS — 10 pairs

### SS (1)

| Pair | Test file | Notes |
|---|---|---|
| Translation + RNAProcessing | `test_l2_2_translation_plus_rna_processing_v2.py::test_l25_no_hints` | First SS green; gated by Translation evolveState port (`02e354a`) |

### DS (7) — from `test_l25_deterministic_stochastic_pairs.py`

| Pair | Notes |
|---|---|
| ChromosomeCondensation + DNARepair | |
| ChromosomeCondensation + Replication | |
| ChromosomeCondensation + Translation | |
| ChromosomeSegregation + DNARepair | |
| ChromosomeSegregation + ProteinFolding | |
| ChromosomeSegregation + Translation | |
| ChromosomeSegregation + tRNAAminoacylation | |

### DD (2) — from dedicated test files

| Pair | Test file | Notes |
|---|---|---|
| ChromosomeCondensation + ChromosomeSegregation | `test_l25_chromosome_condensation_plus_segregation.py` | Originally FAILED with CAUSE_4 (predicted); now PASS after H5+H6 harness fixes |
| HostInteraction + TerminalOrganelleAssembly | `test_l25_host_interaction_plus_terminal_organelle.py` | First-try PASS |

---

## 🔴 FAIL — 28 DS pairs (by failure class)

Failure-class roll-up (precise per-pair classification TBD; counts from latest sweep before EOD):
- **CAUSE_5** (intrinsic replay divergence — "no-hints channel parity gap") — ~16 pairs
- **CAUSE_4** (genuine upstream pollution, post classifier fix) — 4 pairs
- **CAUSE_UNCLASSIFIED** (subclass A: H2O multi-tick drift, 6; subclass B: MG_020 cross-observable, 2) — 8 pairs

| Pair | Suspected class | Notes |
|---|---|---|
| ChromosomeCondensation + DNASupercoiling | CAUSE_5 | |
| ChromosomeCondensation + FtsZPolymerization | CAUSE_5 | |
| ChromosomeCondensation + Metabolism | CAUSE_5 | confirmed: no-hints substrate writeback gap @ `karr_metabolism.py:355-357` |
| ChromosomeCondensation + ProteinDecay | CAUSE_UNCLASSIFIED (subclass B) | MG_020_MONOMER cross-observable |
| ChromosomeCondensation + ProteinFolding | CAUSE_4 | ATP upstream |
| ChromosomeCondensation + ProteinModification | CAUSE_5 | |
| ChromosomeCondensation + ProteinProcessingI | CAUSE_UNCLASSIFIED (subclass A) | H2O drift |
| ChromosomeCondensation + ProteinProcessingII | CAUSE_UNCLASSIFIED (subclass A) | H2O drift |
| ChromosomeCondensation + ProteinTranslocation | CAUSE_4 | ATP upstream |
| ChromosomeCondensation + RNADecay | CAUSE_5 | |
| ChromosomeCondensation + RNAProcessing | CAUSE_UNCLASSIFIED (subclass A) | H2O drift (after classifier fix) |
| ChromosomeCondensation + ReplicationInitiation | CAUSE_5 | confirmed: no-hints enzymes/boundEnzymes writeback gap @ `karr_replication_initiation.py:354-401` |
| ChromosomeCondensation + Transcription | CAUSE_5 | |
| ChromosomeCondensation + tRNAAminoacylation | CAUSE_4 | |
| ChromosomeSegregation + DNASupercoiling | CAUSE_5 | |
| ChromosomeSegregation + FtsZPolymerization | CAUSE_5 | |
| ChromosomeSegregation + Metabolism | CAUSE_5 | (same class as Cond+Metab) |
| ChromosomeSegregation + ProteinDecay | CAUSE_UNCLASSIFIED (subclass B) | |
| ChromosomeSegregation + ProteinModification | CAUSE_5 | |
| ChromosomeSegregation + ProteinProcessingI | CAUSE_UNCLASSIFIED (subclass A) | |
| ChromosomeSegregation + ProteinProcessingII | CAUSE_UNCLASSIFIED (subclass A) | |
| ChromosomeSegregation + ProteinTranslocation | CAUSE_4 | |
| ChromosomeSegregation + RNADecay | CAUSE_5 | |
| ChromosomeSegregation + RNAProcessing | CAUSE_UNCLASSIFIED (subclass A) | |
| ChromosomeSegregation + Replication | CAUSE_5 | (Cond+Replication PASSES; Seg-paired version FAILS — interesting) |
| ChromosomeSegregation + ReplicationInitiation | CAUSE_5 | |
| ChromosomeSegregation + Transcription | CAUSE_5 | |
| HostInteraction + Metabolism | CAUSE_5 | (same class as Cond+Metab) |

---

## ⚪ SKIPPED — 8 DS pairs (no-op trace / sparse-event)

Skipped because one or both processes produces a no-op trace at seed 0 in the 100-tick window. Need event-window MATLAB re-extraction (same approach as RibosomeAssembly at L2.2).

| Pair | Reason |
|---|---|
| ChromosomeCondensation + Cytokinesis | Cytokinesis no-op (post GTP fix) |
| ChromosomeSegregation + Cytokinesis | Cytokinesis no-op |
| ChromosomeCondensation + DNADamage | DNADamage radiation-gated quiescent |
| ChromosomeSegregation + DNADamage | DNADamage quiescent |
| ChromosomeCondensation + RNAModification | RNAModification no-op in window |
| ChromosomeSegregation + RNAModification | RNAModification no-op |
| ChromosomeCondensation + RibosomeAssembly | RibosomeAssembly no-op (legacy) |
| ChromosomeSegregation + RibosomeAssembly | RibosomeAssembly no-op |

---

## ⬜ UNTESTED — 210 SS pairs

Only 1 of 211 SS pairs has a test (Translation+RNAProcessing). The other 210 are listed in `l25_pair_list.toml` with `pair_oracle_complexity = "stochastic_stochastic"`.

**Plan (per-day):** scaffold the 210 SS pairs into a parametrized test file (mirror of `test_l25_deterministic_stochastic_pairs.py`) once the DS/DD failure modes have been resolved enough to give signal-not-noise.

---

## ➖ OUT OF SCOPE — 122 disjoint pairs

No shared WIDs → no allocator contention possible → no L2.5 test required. Enumerated in `l25_pair_list.toml` where `l25_honest_required = false`.

---

## Refresh discipline

Update this tracker:

- After every L2.5 pair test sweep that changes the green/red count.
- Whenever a new pair test is wired or a class of failures is reclassified.
- At end of day if any L2.5-relevant commit landed.

The tracker is human-edited (not autogenerated); the pair derivation in `l25_pair_list.toml` IS autogenerated. If the pair list changes (process added/removed, schema bumped), this tracker needs to be reconciled by hand.
